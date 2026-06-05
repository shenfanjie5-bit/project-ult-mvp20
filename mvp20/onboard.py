"""Add-stock onboarding: recognize a raw market+code, then run the analysis
pipeline as an async job.

Phase 1 (P1) backend for the frontend "add a stock to the pool" feature:

* ``recognize(market, code)`` — resolve a user-typed code into a canonical
  ``ts_code`` + name + a *suggested* industry_id (from
  ``config/tushare_industry_map.yaml``; the UI lets the user confirm/override).
  A-share is fully resolved via tushare ``stock_basic``; HK/US are
  format-validated with best-effort naming (full HK/US resolution is P3).

* ``onboard(...)`` / job model — see ``onboard_job.py`` wiring (P1 step 2).

The module is intentionally import-light at top level so the read-only server
can import ``recognize`` cheaply; tushare is only touched inside the call.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parent.parent
HOT_DB_PATH = ROOT / "runtime" / "hot.sqlite"
UNIVERSE_PATH = ROOT / "config" / "mvp20.universe.yaml"
INDUSTRIES_PATH = ROOT / "config" / "mvp20.industries.yaml"
INDUSTRY_MAP_PATH = ROOT / "config" / "tushare_industry_map.yaml"

# market → ts_code suffix(es) to probe. A-share spans 3 exchanges; we resolve
# the exact one from stock_basic rather than guessing.
_A_SUFFIXES = (".SZ", ".SH", ".BJ")

_CODE_RE = {
    "A": re.compile(r"^\d{6}$"),
    "HK": re.compile(r"^\d{4,5}$"),
    "US": re.compile(r"^[A-Za-z][A-Za-z.\-]{0,8}$"),
}

# in-process cache for the 5k-row stock_basic table (TTL refresh).
_BASIC_CACHE: dict[str, Any] = {"ts": 0.0, "rows": None}
_BASIC_TTL_S = 3600.0
_BASIC_LOCK = threading.Lock()

# in-process TTL cache for the HK/US basic tables (same TTL as A-share).
# Keyed by the tushare endpoint name ("hk_basic" / "us_basic").
_HK_US_BASIC_CACHE: dict[str, dict[str, Any]] = {}

# M1/M2: serializes the onboard admission + universe write + the
# universe→generate→compile pipeline so concurrent jobs don't (a) both pass the
# already_in_pool check then double-append, or (b) interleave overlay/DB writes.
# This is a plain re-entrant-free Lock held only for short critical sections in
# _add_to_universe and around the run_onboard pipeline body.
_ONBOARD_PIPELINE_LOCK = threading.Lock()

# H2: bounded active-job guard. Tracks the set of ts_codes with a pending or
# running onboard job and caps the number of concurrent jobs. Guarded by
# _ACTIVE_JOBS_LOCK. start_onboard_job registers under this lock; the worker
# unregisters on completion (success or error).
_ACTIVE_JOBS_LOCK = threading.Lock()
_ACTIVE_JOBS: set[str] = set()
MAX_ACTIVE_ONBOARD_JOBS = 2


# ---------------------------------------------------------------------------
# config helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def list_industry_ids(*, include_pending: bool = False) -> list[dict]:
    """Active industry_ids (graph_status=present), for the UI dropdown."""
    data = _load_yaml(INDUSTRIES_PATH)
    out: list[dict] = []
    for ind in data.get("industries", []):
        status = ind.get("graph_status")
        if status != "present" and not include_pending:
            continue
        out.append({
            "industry_id": ind.get("id"),
            "name": ind.get("name_cn") or ind.get("name") or ind.get("id"),
            "status": status,
        })
    return out


def _industry_map() -> dict[str, list[str]]:
    data = _load_yaml(INDUSTRY_MAP_PATH)
    return data.get("mappings") or {}


def _suggest_industries(tushare_industry: str | None) -> list[str]:
    if not tushare_industry:
        return []
    return list(_industry_map().get(tushare_industry, []))


def already_in_pool(ts_code: str) -> bool:
    uni = _load_yaml(UNIVERSE_PATH)
    for c in uni.get("constituents", []):
        if str(c.get("ts_code", "")).upper() == ts_code.upper():
            return True
    return False


# ---------------------------------------------------------------------------
# tushare stock_basic (A-share resolution)
# ---------------------------------------------------------------------------


def _stock_basic_a(force: bool = False) -> list[dict]:
    """Cached tushare stock_basic for all listed A-shares. [] on failure."""
    now = time.time()
    with _BASIC_LOCK:
        rows = _BASIC_CACHE["rows"]
        if rows is not None and not force and (now - _BASIC_CACHE["ts"]) < _BASIC_TTL_S:
            return rows
    try:
        from mvp20.sources import tushare_source as ts
        pro = ts._get_pro_api()
        if pro is None:
            return []
        df = pro.stock_basic(
            exchange="", list_status="L",
            fields="ts_code,symbol,name,industry,market",
        )
        rows = df.to_dict(orient="records") if df is not None else []
    except Exception:  # noqa: BLE001 — tushare/network failure → empty
        rows = []
    with _BASIC_LOCK:
        _BASIC_CACHE["rows"] = rows
        _BASIC_CACHE["ts"] = now
    return rows


def _recognize_a(code: str) -> dict:
    rows = _stock_basic_a()
    if not rows:
        return {"ok": False, "reason": "stock_basic unavailable (tushare/network)"}
    matches = [r for r in rows if str(r.get("symbol")) == code]
    if not matches:
        return {"ok": False, "reason": f"A-share code {code} not found in stock_basic"}
    if len(matches) > 1:
        # extremely rare; prefer the SH/SZ main board over .BJ (every A-share
        # ts_code ends with one of .SZ/.SH/.BJ, so the prior endswith(_A_SUFFIXES)
        # key was always True → a no-op; sort SH/SZ ahead of .BJ instead).
        matches.sort(key=lambda r: 0 if str(r.get("ts_code", "")).endswith((".SH", ".SZ")) else 1)
    r = matches[0]
    tind = r.get("industry")
    cands = _suggest_industries(tind)
    return {
        "ok": True,
        "ts_code": r.get("ts_code"),
        "name": r.get("name"),
        "tushare_industry": tind,
        "suggested_industry_id": cands[0] if cands else None,
        "candidate_industry_ids": cands,
    }


def _hk_us_basic(fn: str, force: bool = False) -> list[dict]:
    """Cached tushare hk_basic/us_basic rows (TTL refresh, mirrors the A-share
    ``_stock_basic_a`` cache). [] on failure / endpoint unavailable."""
    now = time.time()
    with _BASIC_LOCK:
        entry = _HK_US_BASIC_CACHE.get(fn)
        if entry is not None and not force and (now - entry["ts"]) < _BASIC_TTL_S:
            return entry["rows"]
    try:
        from mvp20.sources import tushare_source as ts
        pro = ts._get_pro_api()
        if pro is None or not hasattr(pro, fn):
            rows: list[dict] = []
        else:
            df = getattr(pro, fn)()
            rows = df.to_dict(orient="records") if df is not None and len(df) else []
    except Exception:  # noqa: BLE001 — tushare/network failure → empty
        rows = []
    with _BASIC_LOCK:
        _HK_US_BASIC_CACHE[fn] = {"rows": rows, "ts": now}
    return rows


def _recognize_hk_us(market: str, code: str) -> dict:
    """HK/US: format-validate + canonical ts_code; best-effort name via tushare
    hk_basic/us_basic if the account has it. No industry suggestion yet (P3)."""
    suffix = ".HK" if market == "HK" else ".US"
    ts_code = (code.zfill(5) if market == "HK" else code.upper()) + suffix
    name = None
    fn = "hk_basic" if market == "HK" else "us_basic"
    for r in _hk_us_basic(fn):
        if str(r.get("ts_code", "")).upper() == ts_code.upper():
            name = r.get("name")
            break
    return {
        "ok": True,
        "ts_code": ts_code,
        "name": name,
        "tushare_industry": None,
        "suggested_industry_id": None,
        "candidate_industry_ids": [],
        "note": "HK/US recognition is format-only; name best-effort (P3 will add full resolution).",
    }


def recognize(market: str, code: str) -> dict:
    """Resolve raw (market, code) → canonical ts_code + name + industry hint.

    Returns a dict with ``ok`` and, when ok, ``ts_code``/``name``/
    ``tushare_industry``/``suggested_industry_id``/``candidate_industry_ids``,
    plus ``already_in_pool`` and the full ``all_industry_ids`` list for the UI.
    """
    market = (market or "").strip().upper()
    code = (code or "").strip()
    base = {
        "market": market, "input_code": code,
        "all_industry_ids": list_industry_ids(),
    }
    if market not in _CODE_RE:
        return {**base, "ok": False, "reason": f"unknown market {market!r} (use A/HK/US)"}
    if not _CODE_RE[market].match(code):
        return {**base, "ok": False, "reason": f"code {code!r} not valid for market {market}"}

    res = _recognize_a(code) if market == "A" else _recognize_hk_us(market, code)
    if not res.get("ok"):
        return {**base, **res}
    res["already_in_pool"] = already_in_pool(res["ts_code"])
    return {**base, **res}


# ---------------------------------------------------------------------------
# onboard job: state table + pipeline
# ---------------------------------------------------------------------------

# Step list (also the progress bar the frontend renders). The first 8 produce
# the *preliminary* result; the last 3 are the async codex *full* completion.
ONBOARD_STEPS = [
    "universe", "generate_overlays", "collect", "annual_report",
    "derive", "compile", "build_peer_context", "score_preliminary",  # → ready_preliminary
    "codex_fill", "recompile", "rescore",              # → ready_full
]


def _onboard_db_init(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onboard_jobs (
                job_id TEXT PRIMARY KEY, ts_code TEXT, name TEXT,
                industry_id TEXT, status TEXT, step TEXT, step_idx INTEGER,
                total_steps INTEGER, error TEXT, preliminary_json TEXT,
                full_json TEXT, created_at INTEGER, updated_at INTEGER
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _job_create(db_path: Path, ts_code: str, name: str, industry_id: str) -> str:
    job_id = uuid.uuid4().hex[:16]
    now = int(time.time())
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO onboard_jobs (job_id, ts_code, name, industry_id, "
            "status, step, step_idx, total_steps, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (job_id, ts_code, name, industry_id, "pending", "queued", -1,
             len(ONBOARD_STEPS), now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return job_id


def _job_update(db_path: Path, job_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = int(time.time())
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"UPDATE onboard_jobs SET {cols} WHERE job_id = ?",
                     (*fields.values(), job_id))
        conn.commit()
    finally:
        conn.close()


def get_job(db_path: Path, job_id: str) -> dict | None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM onboard_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    if row is None:
        return None
    d = dict(row)
    for k in ("preliminary_json", "full_json"):
        if d.get(k):
            try:
                d[k.replace("_json", "")] = json.loads(d[k])
            except (ValueError, TypeError):
                pass
        d.pop(k, None)
    return d


# ---- universe mutation (comment-preserving textual append) ----------------


def _add_to_universe(ts_code: str, name: str, industry_id: str) -> bool:
    """Append a constituent to universe.yaml (constituents is the last top-level
    key, so a textual append preserves all comments + existing entries).
    Returns False if already present.

    The read-modify-write is made atomic (write a temp file in the same dir +
    ``os.replace``) so a concurrent reader never sees a truncated/half-written
    universe.yaml. The duplicate re-check still runs here, but callers MUST hold
    ``_ONBOARD_PIPELINE_LOCK`` across this call to close the check→append TOCTOU
    window between concurrent onboard jobs.
    """
    if already_in_pool(ts_code):
        return False
    block = (
        f"  - ts_code: {ts_code}\n"
        f"    name: {json.dumps(name or ts_code, ensure_ascii=False)}\n"
        f"    role: target\n"
        f"    pool: regular\n"
        f"    industry_ids: [{industry_id}]\n"
    )
    text = UNIVERSE_PATH.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    new_text = text + block
    fd, tmp = tempfile.mkstemp(
        dir=str(UNIVERSE_PATH.parent), prefix=UNIVERSE_PATH.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        os.replace(tmp, UNIVERSE_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return True


# ---- pipeline steps -------------------------------------------------------


def _run_cli(args: list[str], timeout: int = 900) -> tuple[int, str]:
    """Run `python -m mvp20.cli <args>` in the repo root."""
    proc = subprocess.run(
        [sys.executable, "-m", "mvp20.cli", *args],
        cwd=str(ROOT), capture_output=True, text=True, timeout=timeout,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _score(ts_code: str, db_path: Path) -> dict:
    """score-company → parsed {short, medium, long, signal, mode, top_path}."""
    rc, out = _run_cli(["score-company", "--ts-code", ts_code, "--db", str(db_path)],
                       timeout=180)
    for line in out.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 6 and parts[0] == ts_code:
            try:
                return {
                    "ts_code": parts[0], "mode": parts[1],
                    "short": float(parts[2]), "medium": float(parts[3]),
                    "long": float(parts[4]), "signal": parts[5],
                    "top_path": parts[6] if len(parts) > 6 else None,
                }
            except (ValueError, IndexError):
                continue
    return {"ts_code": ts_code, "error": "score line not parsed", "raw_tail": out[-300:]}


def _verify_compiled_snapshot(db_path: Path, ts_code: str) -> bool:
    """Return True if a compiled overlay snapshot exists for ``ts_code``.

    compile-overlays recompiles the whole set and exits non-zero on an
    *unrelated* overlay error elsewhere, so its return code alone can't tell us
    whether THIS stock compiled. We check the compiled snapshot directly. The
    user-visible score does not read this snapshot (it reads YAML + realtime),
    so absence is a non-fatal staleness flag for the /stock-overlay API only.
    """
    try:
        from mvp20.storage import read_compiled_graph_snapshot
        return read_compiled_graph_snapshot(db_path, ts_code) is not None
    except Exception:  # noqa: BLE001 — never let the verification crash the job
        return False


def run_onboard(
    db_path: Path, ts_code: str, name: str, industry_id: str, *,
    do_codex: bool = True, year: int = 2025,
    progress: Callable[[int, str], None] | None = None,
    on_preliminary: Callable[[dict], None] | None = None,
) -> dict:
    """Synchronous onboarding pipeline for one stock. Returns the result dict
    (preliminary score, and full score if do_codex). Raises on hard failure."""

    def step(idx: int) -> None:
        if progress:
            progress(idx, ONBOARD_STEPS[idx])

    is_a = ts_code.upper().endswith(_A_SUFFIXES)

    # M1/M2: serialize the universe-mutation + overlay/DB-write section so two
    # concurrent onboard jobs can't double-append to universe.yaml or interleave
    # overlay/compiled-DB writes. The lock is released before the (minutes-long)
    # collect/derive/score/codex work so it never becomes a global bottleneck.
    with _ONBOARD_PIPELINE_LOCK:
        # 1. universe (atomic write; re-check happens inside _add_to_universe,
        #    now under this lock so the check→append window is closed).
        step(0)
        _add_to_universe(ts_code, name, industry_id)

        # 2. generate-overlays — SCOPED to just this ts_code. A full
        #    (universe-wide) regeneration would re-run merge_preserve over every
        #    other stock and reset their *event-driven* Inactive nodes back to
        #    Unknown (those transient Inactive nodes are intentionally NOT
        #    preserved), degrading their data_coverage. This call is therefore
        #    NOT idempotent universe-wide; --only-ts-code touches only this
        #    stock's shell (merge-preserve still protects its own Known/N/A/
        #    Optionality/non-event-Inactive cells).
        step(1)
        rc, out = _run_cli(["generate-overlays", "--only-ts-code", ts_code])
        if rc != 0:
            raise RuntimeError(f"generate-overlays failed: {out[-300:]}")

    # 3. collect (single stock)
    step(2)
    sys.path.insert(0, str(ROOT / "scripts"))
    import collector  # noqa: E402
    from mvp20.storage import upsert_realtime  # noqa: E402
    stock = {"ts_code": ts_code, "name": name, "industry_ids": [industry_id]}
    rows = collector.fetch_real_batch([stock], 0)
    if rows:
        upsert_realtime(db_path, rows)

    # 4. annual report (A-share only)
    step(3)
    if is_a:
        try:
            from scripts.fetch_annual_report import fetch_and_ingest
            fetch_and_ingest(ts_code, year, db_path)
        except Exception:  # noqa: BLE001 — annual report is best-effort
            pass

    # 5. derive (single stock: Tier-0 + snapshot Tier 1-4)
    step(4)
    from mvp20.derive import derive_all, DeriveRunner
    derive_all(db_path, ts_codes=[ts_code], a_share_only=is_a)
    DeriveRunner(db_path).run_all([ts_code])

    # 6. compile. NOTE: the user-visible score below is computed from the YAML
    #    overlay + the realtime snapshot directly (see score-company), NOT from
    #    this compiled snapshot — so a failed compile does NOT corrupt the score.
    #    compile/recompile only refresh the separate compiled snapshot that the
    #    /stock-overlay API serves. We still verify THIS stock landed a fresh
    #    snapshot and surface a non-fatal flag if it didn't (stale /stock-overlay
    #    for this stock), rather than silently swallowing the compile result.
    step(5)
    with _ONBOARD_PIPELINE_LOCK:
        rc, out = _run_cli(["compile-overlays", "--db", str(db_path)])
    compile_ok = _verify_compiled_snapshot(db_path, ts_code)

    # 7. build cross-sectional peer-context so THIS newly-added stock enters the
    #    valuation pools BEFORE it is scored. Without it, score-company loads a
    #    stale artifact lacking the new stock → _xs_valuation_signal returns None
    #    → its valuation_rerating / priced_in fall back to the pre-R-3 absolute
    #    path (the "leader punished by valuation" regression quantified in the
    #    R-6 audit: valr drift up to ~0.19). A-share pool only (HK/US peer_context
    #    is an un-scored data artifact). Pipeline-locked; best-effort — a failed
    #    rebuild leaves the prior artifact (score still works, valuation slightly
    #    stale) rather than failing the whole onboarding.
    step(6)
    peer_context_warning: str | None = None
    if is_a:
        try:
            from mvp20.peer_context import build_and_save_peer_context
            _codes = [fp.stem for fp in (ROOT / "config" / "stock_overlays").glob("**/*.yaml")]
            with _ONBOARD_PIPELINE_LOCK:
                build_and_save_peer_context(
                    db_path, _codes, "A",
                    overlays_dir=ROOT / "config" / "stock_overlays",
                )
        except Exception as exc:  # noqa: BLE001 — best-effort, but NOT silent
            # save_peer_context writes atomically, so a failure leaves the PRIOR
            # artifact intact and existing stocks are unaffected; only THIS new
            # stock is absent from the pool → its valuation_rerating / priced_in
            # fall back to the pre-R-3 absolute path. Surface it rather than hand
            # back a silently-degraded score.
            logging.getLogger(__name__).warning(
                "onboard build_peer_context failed for %s: %s", ts_code, exc
            )
            peer_context_warning = (
                "peer-context rebuild failed; this stock's cross-sectional "
                "valuation fell back to the absolute path until the next build"
            )

    # 8. preliminary score
    step(7)
    preliminary = _score(ts_code, db_path)
    if isinstance(preliminary, dict):
        if not compile_ok:
            preliminary.setdefault(
                "compile_warning",
                "stock-overlay compiled snapshot not refreshed (score is unaffected; "
                "/stock-overlay may be stale for this stock)",
            )
        if peer_context_warning:
            preliminary.setdefault("valuation_warning", peer_context_warning)
    result: dict = {"ts_code": ts_code, "preliminary": preliminary}
    # Surface the preliminary score the moment it's ready so the frontend can
    # show it while the (minutes-long) codex fill continues running.
    if on_preliminary:
        on_preliminary(preliminary)

    if not do_codex:
        return result

    # 9. codex hardened-low fill (reuses the Phase-C1 machinery: the schema-
    #    hardened prompt-gen + low-effort runner). codex edits the overlay.
    step(8)
    prompt_path = Path("/tmp") / f"codex_onboard_{ts_code.replace('.', '_')}.md"
    subprocess.run(
        [sys.executable, "scripts/codex_prompt_gen.py",
         "--industry", industry_id, "--ts-code", ts_code, "--out", str(prompt_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120,
    )
    if prompt_path.exists():
        env = {**os.environ, "CODEX_WORKDIR": str(ROOT)}
        subprocess.run(
            ["bash", "scripts/codex_run_prompt_low.sh", str(prompt_path)],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=1800,
        )

    # 10. recompile (materialize the codex fill into the compiled snapshot that
    #    the /stock-overlay API serves). Serialized with other onboard jobs'
    #    compiled-DB writes via the pipeline lock.
    step(9)
    with _ONBOARD_PIPELINE_LOCK:
        _run_cli(["compile-overlays", "--db", str(db_path)])

    # 11. rescore (full)
    step(10)
    result["full"] = _score(ts_code, db_path)
    return result


# ---------------------------------------------------------------------------
# H2: bounded active-job admission. server.handle_onboard calls
# ``try_reserve_onboard_slot`` before starting a job and gets back a structured
# reason it can map to an HTTP status. The reservation is released by the worker
# (or by the caller if it decides not to start after reserving).
# ---------------------------------------------------------------------------


def active_onboard_count() -> int:
    with _ACTIVE_JOBS_LOCK:
        return len(_ACTIVE_JOBS)


def try_reserve_onboard_slot(ts_code: str) -> tuple[bool, str | None]:
    """Atomically reserve a concurrency slot for ``ts_code``.

    Returns ``(True, None)`` on success. On failure returns ``(False, reason)``
    where reason is ``"duplicate"`` (a pending/running job already exists for
    this ts_code) or ``"at_capacity"`` (>= MAX_ACTIVE_ONBOARD_JOBS in flight).
    The caller MUST release the slot via ``release_onboard_slot`` when the job
    terminates (start_onboard_job wires this into the worker automatically).
    """
    key = ts_code.upper()
    with _ACTIVE_JOBS_LOCK:
        if key in _ACTIVE_JOBS:
            return False, "duplicate"
        if len(_ACTIVE_JOBS) >= MAX_ACTIVE_ONBOARD_JOBS:
            return False, "at_capacity"
        _ACTIVE_JOBS.add(key)
        return True, None


def release_onboard_slot(ts_code: str) -> None:
    with _ACTIVE_JOBS_LOCK:
        _ACTIVE_JOBS.discard(ts_code.upper())


def start_onboard_job(
    db_path: Path, ts_code: str, name: str, industry_id: str, *,
    do_codex: bool = True, _reserved: bool = False,
) -> str:
    """Create an onboard job + run it on a daemon thread. Returns job_id.

    H2: a concurrency slot is reserved for ``ts_code`` before the thread starts.
    Pass ``_reserved=True`` when the caller already reserved the slot via
    ``try_reserve_onboard_slot`` (server.handle_onboard does this so it can map
    the failure to an HTTP status). When not pre-reserved we reserve here and
    raise RuntimeError if the guard rejects (duplicate / at capacity). The slot
    is always released when the worker terminates (success or error).
    """
    if not _reserved:
        ok, reason = try_reserve_onboard_slot(ts_code)
        if not ok:
            raise RuntimeError(f"onboard slot unavailable: {reason}")
    _onboard_db_init(db_path)
    job_id = _job_create(db_path, ts_code, name, industry_id)

    def _worker() -> None:
        def prog(idx: int, step_name: str) -> None:
            _job_update(db_path, job_id, step=step_name, step_idx=idx, status="running")

        def on_prelim(prelim: dict) -> None:
            # Persist the preliminary score mid-run (status stays "running").
            # The frontend keys off the *presence* of `preliminary` to render the
            # early score card while the codex fill is still in flight.
            _job_update(db_path, job_id,
                        preliminary_json=json.dumps(prelim, ensure_ascii=False))

        try:
            res = run_onboard(db_path, ts_code, name, industry_id,
                              do_codex=do_codex, progress=prog, on_preliminary=on_prelim)
            # M4: _score returns {"error": ...} on a parse failure (it never
            # raises), so a non-scored stock must NOT be reported as success.
            prelim = res.get("preliminary")
            full = res.get("full")
            err = None
            if isinstance(prelim, dict) and prelim.get("error"):
                err = f"preliminary score failed: {prelim['error']}"
            elif do_codex and isinstance(full, dict) and full.get("error"):
                err = f"full score failed: {full['error']}"
            if err is not None:
                _job_update(db_path, job_id, status="error", error=err[:500],
                            step="done", step_idx=len(ONBOARD_STEPS),
                            preliminary_json=json.dumps(prelim, ensure_ascii=False),
                            full_json=json.dumps(full, ensure_ascii=False) if full else None)
            else:
                _job_update(db_path, job_id, status="ready_full" if do_codex else "ready_preliminary",
                            step="done", step_idx=len(ONBOARD_STEPS),
                            preliminary_json=json.dumps(prelim, ensure_ascii=False),
                            full_json=json.dumps(full, ensure_ascii=False) if full else None)
        except Exception as exc:  # noqa: BLE001
            _job_update(db_path, job_id, status="error", error=str(exc)[:500])
        finally:
            release_onboard_slot(ts_code)

    threading.Thread(target=_worker, daemon=True, name=f"onboard-{ts_code}").start()
    return job_id
