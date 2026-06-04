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

import os
from typing import Iterable, Mapping, Sequence

from mvp20.aggregator import build_peer_context


def market_of(ts_code: str) -> str:
    """Coarse market bucket from a ts_code suffix (A / HK / US)."""
    ts = str(ts_code or "")
    if ts.endswith(".SZ") or ts.endswith(".SH") or ts.endswith(".BJ"):
        return "A"
    if ts.endswith(".HK"):
        return "HK"
    return "US"


#: (db_path, market) -> (db_mtime, peer_context). Module-level so it survives
#: across requests within a server process; rebuilt when the DB mtime changes.
_CACHE: dict[tuple[str, str], tuple[float, dict[str, list[float]]]] = {}


def peer_context_for_market(
    db_path,
    universe_ts_codes: Iterable[str],
    market: str,
    *,
    use_cache: bool = True,
) -> dict[str, list[float]]:
    """Build (or fetch cached) cross-sectional peer context for ``market``.

    ``universe_ts_codes`` is the full candidate set (any market); we keep only
    those whose ``market_of`` matches, read each one's hot snapshot, and hand the
    bundle to ``build_peer_context``. Returns ``{}`` when no snapshots are
    available (→ caller passes None / falls back to absolute).
    """

    from mvp20.storage import read_hot_snapshot  # local: keep import cheap

    codes = sorted({c for c in universe_ts_codes if c and market_of(c) == market})
    key = (str(db_path), market)
    try:
        mtime = os.path.getmtime(db_path)
    except OSError:
        mtime = 0.0
    if use_cache and key in _CACHE and _CACHE[key][0] == mtime:
        return _CACHE[key][1]

    snaps: dict[str, Mapping] = {}
    for c in codes:
        try:
            snaps[c] = read_hot_snapshot(db_path, c)
        except Exception:  # noqa: BLE001 — a missing snapshot just drops out
            continue
    ctx = build_peer_context(snaps)
    if use_cache:
        _CACHE[key] = (mtime, ctx)
    return ctx


def clear_cache() -> None:
    """Drop the module cache (tests / forced refresh)."""
    _CACHE.clear()


__all__ = ["market_of", "peer_context_for_market", "clear_cache"]
