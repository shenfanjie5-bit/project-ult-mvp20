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
import os
import re
import sqlite3
import subprocess
import sys
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
        # extremely rare; prefer the SH/SZ main board over others
        matches.sort(key=lambda r: str(r.get("ts_code", "")).endswith(_A_SUFFIXES), reverse=True)
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


def _recognize_hk_us(market: str, code: str) -> dict:
    """HK/US: format-validate + canonical ts_code; best-effort name via tushare
    hk_basic/us_basic if the account has it. No industry suggestion yet (P3)."""
    suffix = ".HK" if market == "HK" else ".US"
    ts_code = (code.zfill(5) if market == "HK" else code.upper()) + suffix
    name = None
    fn = "hk_basic" if market == "HK" else "us_basic"
    try:
        from mvp20.sources import tushare_source as ts
        pro = ts._get_pro_api()
        if pro is not None and hasattr(pro, fn):
            df = getattr(pro, fn)()
            if df is not None and len(df):
                hit = df[df["ts_code"].astype(str).str.upper() == ts_code.upper()]
                if len(hit):
                    name = hit.iloc[0].get("name")
    except Exception:  # noqa: BLE001
        name = None
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

# Step list (also the progress bar the frontend renders). The first 7 produce
# the *preliminary* result; the last 3 are the async codex *full* completion.
ONBOARD_STEPS = [
    "universe", "generate_overlays", "collect", "annual_report",
    "derive", "compile", "score_preliminary",          # → ready_preliminary
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
    Returns False if already present."""
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
    UNIVERSE_PATH.write_text(text + block, encoding="utf-8")
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

    # 1. universe
    step(0)
    _add_to_universe(ts_code, name, industry_id)

    # 2. generate-overlays (full but idempotent + merge-preserve)
    step(1)
    rc, out = _run_cli(["generate-overlays"])
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

    # 6. compile
    step(5)
    rc, out = _run_cli(["compile-overlays", "--db", str(db_path)])
    # compile may exit non-zero on an unrelated overlay error elsewhere; only
    # fail if THIS stock didn't compile — checked implicitly by the score next.

    # 7. preliminary score
    step(6)
    preliminary = _score(ts_code, db_path)
    result: dict = {"ts_code": ts_code, "preliminary": preliminary}
    # Surface the preliminary score the moment it's ready so the frontend can
    # show it while the (minutes-long) codex fill continues running.
    if on_preliminary:
        on_preliminary(preliminary)

    if not do_codex:
        return result

    # 8. codex hardened-low fill (reuses the Phase-C1 machinery: the schema-
    #    hardened prompt-gen + low-effort runner). codex edits the overlay.
    step(7)
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

    # 9. recompile (materialize the codex fill)
    step(8)
    _run_cli(["compile-overlays", "--db", str(db_path)])

    # 10. rescore (full)
    step(9)
    result["full"] = _score(ts_code, db_path)
    return result


def start_onboard_job(
    db_path: Path, ts_code: str, name: str, industry_id: str, *,
    do_codex: bool = True,
) -> str:
    """Create an onboard job + run it on a daemon thread. Returns job_id."""
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
            _job_update(db_path, job_id, status="ready_full" if do_codex else "ready_preliminary",
                        step="done", step_idx=len(ONBOARD_STEPS),
                        preliminary_json=json.dumps(res.get("preliminary"), ensure_ascii=False),
                        full_json=json.dumps(res.get("full"), ensure_ascii=False) if res.get("full") else None)
        except Exception as exc:  # noqa: BLE001
            _job_update(db_path, job_id, status="error", error=str(exc)[:500])

    threading.Thread(target=_worker, daemon=True, name=f"onboard-{ts_code}").start()
    return job_id
