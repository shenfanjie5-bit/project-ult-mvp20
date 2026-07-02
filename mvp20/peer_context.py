"""R-3a — cross-sectional peer-context provisioning + cache.

``mvp20.aggregator.build_peer_context`` turns ``{ts_code: realtime_snapshot}``
into the universe distributions the de-common-mode normalizers rank against.
This module gathers those snapshots from the hot DB for a market universe and
caches the result, so per-stock scorers (CLI ``score-company``, the server's
``/score`` handler) can de-common-mode without each re-scanning the universe.

Scope (R-3a / Q2 "A 股池先行"): peer context is built over the **A-share** pool
only. For HK / US stocks (currently data artifacts) callers pass ``None`` and the
normalizers fall back to their original absolute behaviour — so this change is
scoped to A-shares and never perturbs the other markets.

Cache invalidation keys on the hot DB's mtime: when realtime data is refreshed
(``hot.sqlite`` rewritten) the cached populations are rebuilt on next use.
"""
from __future__ import annotations

import json
import os
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from mvp20.aggregator import build_peer_context

#: R-3b.2 — F6 archetype assignments (the sub-track layer) + min pool size for a
#: cross-sectional valuation rank. A pool smaller than this falls back one level
#: (archetype → industry → market).
_ARCHETYPE_YAML = "config/business_model_archetypes.yaml"
_DEFAULT_OVERLAYS_DIR = "config/stock_overlays"
_MIN_POOL = 5
_PEER_CONTEXT_DP_IDS = (
    "L6.priced.run_up",
    "L6.priced.crowdedness",
    "L6.mult.pe",
    "L6.mult.ps",
    "L5.is.eps",
    "L5.is.operating_profit",
    "L5.is.revenue",
    "L5.is.margins",
    "L5.fcst.eps_cf",
    "L5.fcst.revenue_margin",
)


def market_of(ts_code: str) -> str:
    """Coarse market bucket from a ts_code suffix (A / HK / US)."""
    ts = str(ts_code or "")
    if ts.endswith(".SZ") or ts.endswith(".SH") or ts.endswith(".BJ"):
        return "A"
    if ts.endswith(".HK"):
        return "HK"
    return "US"


def _mult_scalar(snap: Mapping[str, Any], dp_id: str) -> float | None:
    """Read a positive ``scalar`` (PE / PS multiple) from a snapshot entry."""
    entry = snap.get(dp_id)
    if not isinstance(entry, Mapping):
        return None
    payload = entry.get("value") if "value" in entry else entry
    if not isinstance(payload, Mapping):
        return None
    try:
        x = float(payload.get("scalar"))
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def _chunked(seq: list[str], size: int) -> Iterable[list[str]]:
    for idx in range(0, len(seq), size):
        yield seq[idx : idx + size]


def _read_peer_snapshots(db_path: Path, codes: Iterable[str]) -> dict[str, Mapping[str, Any]]:
    """Batch-read only the dp_ids needed for peer-context construction.

    This avoids opening the 2GB hot DB once per stock and avoids sentinel rows;
    peer context is a cross-sectional stock-level artifact, so market/industry
    inherited values do not belong in these distributions.
    """

    code_list = sorted({c for c in codes if c})
    if not code_list or not db_path.exists():
        return {}

    snaps: dict[str, dict[str, Any]] = {c: {} for c in code_list}
    dp_placeholders = ",".join(["?"] * len(_PEER_CONTEXT_DP_IDS))
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for code_chunk in _chunked(code_list, 500):
            code_placeholders = ",".join(["?"] * len(code_chunk))
            rows = conn.execute(
                f"""
                SELECT ts_code, dp_id, value_json, data_status, confidence,
                       source, updated_at
                  FROM realtime_current
                 WHERE ts_code IN ({code_placeholders})
                   AND dp_id IN ({dp_placeholders})
                   AND data_status IN ('Known', 'Proxy')
                   AND source NOT LIKE 'mock:%'
                """,
                [*code_chunk, *_PEER_CONTEXT_DP_IDS],
            ).fetchall()
            for ts, dp_id, value_json, status, confidence, source, updated_at in rows:
                try:
                    value = json.loads(value_json)
                except Exception:  # noqa: BLE001
                    continue
                snaps.setdefault(ts, {})[dp_id] = {
                    "value": value,
                    "data_status": status,
                    "confidence": confidence,
                    "source": source,
                    "updated_at": updated_at,
                    "_origin_ts_code": ts,
                }
    finally:
        conn.close()
    return {ts: snap for ts, snap in snaps.items() if snap}


def _overlay_industry_id(fp: Path, overlays_root: Path) -> str | None:
    """Fast top-level industry_id extraction without parsing full overlay YAML."""

    try:
        with fp.open("r", encoding="utf-8") as handle:
            for raw in handle:
                if raw.startswith("nodes:"):
                    break
                if raw.startswith("industry_id:"):
                    value = raw.split(":", 1)[1].strip().strip("\"'")
                    return value or None
    except OSError:
        return None

    parent = fp.parent.name
    root_name = overlays_root.name
    return parent if parent and parent != root_name else None


def _load_ts_taxonomy(
    ts_codes: Iterable[str], overlays_dir: str | Path
) -> tuple[dict[str, str], dict[str, str]]:
    """R-3b.2 sub-track + industry maps for the pool hierarchy.

    archetype ← ``config/business_model_archetypes.yaml`` (F6 assignments, the
    sub-track layer); industry ← each stock's overlay ``industry_id``. Both
    best-effort: a missing file just yields a thinner hierarchy (→ fall back to a
    coarser pool level). Returns ``(ts_to_archetype, ts_to_industry)``.
    """
    import yaml
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

    tsset = {c for c in ts_codes if c}
    ts_to_arch: dict[str, str] = {}
    try:
        doc = yaml.load(
            Path(_ARCHETYPE_YAML).read_text(encoding="utf-8"),
            Loader=loader,
        ) or {}
        for ts, info in (doc.get("assignments") or {}).items():
            if ts in tsset and isinstance(info, Mapping) and info.get("archetype"):
                ts_to_arch[ts] = str(info["archetype"])
    except Exception:  # noqa: BLE001 — no archetypes → archetype level just empty
        pass

    ts_to_ind: dict[str, str] = {}
    od = Path(overlays_dir)
    if od.exists():
        for fp in od.glob("**/*.yaml"):
            ts = fp.stem
            if ts not in tsset or ts in ts_to_ind:
                continue
            iid = _overlay_industry_id(fp, od)
            if iid:
                ts_to_ind[ts] = str(iid)
    return ts_to_arch, ts_to_ind


def build_valuation_pools(
    snapshots: Mapping[str, Mapping[str, Any]],
    ts_to_arch: Mapping[str, str],
    ts_to_ind: Mapping[str, str],
    *,
    n_min: int = _MIN_POOL,
) -> dict[str, Any]:
    """R-3b.2 hierarchical cross-sectional valuation pools.

    For PE (primary) and PS (fallback) separately: group each stock's metric by
    its F6 archetype + industry, then assign each stock to the FINEST level whose
    pool has ≥ ``n_min`` members (archetype → industry → ``MARKET:A``). Returns
    the ``_val_*`` keys consumed by ``aggregator._xs_valuation_signal``:
    ``_val_{pe,ps}_of`` (ts→metric), ``_val_{pe,ps}_pool_of`` (ts→pool key),
    ``_val_{pe,ps}_pool`` (pool key→sorted distribution).
    """

    def collect(dp_id: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for ts, snap in snapshots.items():
            if isinstance(snap, Mapping):
                v = _mult_scalar(snap, dp_id)
                if v is not None:
                    out[ts] = v
        return out

    def resolve(metric_of: dict[str, float]) -> tuple[dict[str, str], dict[str, list[float]]]:
        arch: dict[str, list[float]] = defaultdict(list)
        ind: dict[str, list[float]] = defaultdict(list)
        mkt: list[float] = []
        for ts, v in metric_of.items():
            if ts in ts_to_arch:
                arch[ts_to_arch[ts]].append(v)
            if ts in ts_to_ind:
                ind[ts_to_ind[ts]].append(v)
            mkt.append(v)
        mkt_sorted = sorted(mkt)
        pool_of: dict[str, str] = {}
        pools: dict[str, list[float]] = {}
        for ts in metric_of:
            a = ts_to_arch.get(ts)
            i = ts_to_ind.get(ts)
            if a and len(arch[a]) >= n_min:
                key = f"ARCH:{a}"
                pools.setdefault(key, sorted(arch[a]))
            elif i and len(ind[i]) >= n_min:
                key = f"IND:{i}"
                pools.setdefault(key, sorted(ind[i]))
            else:
                key = "MARKET:A"
                pools.setdefault(key, mkt_sorted)
            pool_of[ts] = key
        return pool_of, pools

    pe_of = collect("L6.mult.pe")
    ps_of = collect("L6.mult.ps")
    pe_pool_of, pe_pools = resolve(pe_of)
    ps_pool_of, ps_pools = resolve(ps_of)
    return {
        "_val_pe_of": pe_of, "_val_pe_pool_of": pe_pool_of, "_val_pe_pool": pe_pools,
        "_val_ps_of": ps_of, "_val_ps_pool_of": ps_pool_of, "_val_ps_pool": ps_pools,
    }


#: (db_path, market) -> (db_mtime, peer_context). Module-level so it survives
#: across requests within a server process; rebuilt when the DB mtime changes.
_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}


def peer_context_for_market(
    db_path,
    universe_ts_codes: Iterable[str],
    market: str,
    *,
    overlays_dir: str | Path = _DEFAULT_OVERLAYS_DIR,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Build (or fetch cached) cross-sectional peer context for ``market``.

    ``universe_ts_codes`` is the full candidate set (any market); we keep only
    those whose ``market_of`` matches, batch-read the small set of hot fields
    needed by peer context, then build:
      * R-3a priced_in pops (``build_peer_context``: run_up / crowdedness), and
      * R-3b.2 hierarchical valuation pools (``build_valuation_pools``: PE / PS).
      * normalized fundamental / forecast baseline maps consumed by selected
        score formulas.
    Returns ``{}`` when no snapshots are available (→ caller passes None / falls
    back to absolute). Cache keys on the DB mtime (realtime refresh → rebuild);
    archetype/overlay edits without a DB rewrite need a process restart.
    """

    db_path = Path(db_path)
    codes = sorted({c for c in universe_ts_codes if c and market_of(c) == market})
    key = (str(db_path), market)
    try:
        mtime = os.path.getmtime(db_path)
    except OSError:
        mtime = 0.0
    if use_cache and key in _CACHE and _CACHE[key][0] == mtime:
        return _CACHE[key][1]

    snaps = _read_peer_snapshots(db_path, codes)
    ctx: dict[str, Any] = build_peer_context(snaps)  # R-3a run_up / crowdedness
    # R-3b.2 valuation pools (A-share scope; other markets get an empty hierarchy
    # → _valuation_pooled False → absolute valr path unchanged).
    ts_to_arch, ts_to_ind = _load_ts_taxonomy(codes, overlays_dir)
    ctx.update(build_valuation_pools(snaps, ts_to_arch, ts_to_ind))
    if use_cache:
        _CACHE[key] = (mtime, ctx)
    return ctx


def clear_cache() -> None:
    """Drop the module cache (tests / forced refresh)."""
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Precomputed artifact — building peer context scans the whole universe (read
# every snapshot + every overlay), which is ~16s on the live DB and MUST NOT run
# inside a per-request scoring path. Instead build it offline (CLI
# ``build-peer-context``, refreshed after derive) and persist a small JSON the
# server / CLI load in <10ms.
# ---------------------------------------------------------------------------

def default_artifact_path(db_path, market: str = "A") -> Path:
    """Conventional artifact location: alongside the hot DB."""
    return Path(db_path).parent / f"peer_context_{market}.json"


def save_peer_context(ctx: Mapping[str, Any], path) -> None:
    import json, os, tempfile
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: a crash / disk-full mid-write must leave the PRIOR artifact
    # intact. A half-written JSON would make load_peer_context return None →
    # silent fallback to degraded absolute valuation for the WHOLE A-share pool
    # (and torn reads for a concurrent /score). Write a sibling temp then rename.
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".peer_context.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(ctx, f)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_peer_context(path) -> dict[str, Any] | None:
    """Load a persisted peer context (None when absent / unreadable, so the
    caller falls back to the original absolute scoring)."""
    import json
    p = Path(path)
    if not p.exists():
        return None
    try:
        ctx = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return ctx or None


def build_and_save_peer_context(
    db_path,
    universe_ts_codes: Iterable[str],
    market: str = "A",
    *,
    out_path=None,
    overlays_dir: str | Path = _DEFAULT_OVERLAYS_DIR,
) -> Path:
    """Build the peer context for ``market`` and persist it. Returns the path."""
    ctx = peer_context_for_market(
        db_path, universe_ts_codes, market,
        overlays_dir=overlays_dir, use_cache=False,
    )
    out = Path(out_path) if out_path else default_artifact_path(db_path, market)
    save_peer_context(ctx, out)
    return out


__all__ = [
    "market_of", "peer_context_for_market", "build_valuation_pools",
    "default_artifact_path", "save_peer_context", "load_peer_context",
    "build_and_save_peer_context", "clear_cache",
]
