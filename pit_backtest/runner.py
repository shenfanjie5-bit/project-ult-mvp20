"""Backtest orchestration: resolve base dates → (collect+derive+peer+score) per
base date → forward-return labels → persist. Resumable at every layer.

Writes only to ``runtime/backtest/``. Never reads the live hot DB for features.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

from pit_backtest import calendar as cal
from pit_backtest import collector, pipeline, prices, store, universe

log = logging.getLogger("pit_backtest.runner")


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=".", text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return None


def _universe_hash(codes: Sequence[str]) -> str:
    return hashlib.sha256("|".join(sorted(codes)).encode()).hexdigest()[:16]


def resolve_dates(pro, today: str | None = None) -> dict[int, str]:
    return cal.resolve_base_dates(pro, today=today, offsets=(30, 60, 90))


def run_scoring(today: str | None = None, *, codes: Sequence[str] | None = None,
                db: Path = store.DEFAULT_DB, resume: bool = True, pro=None,
                progress: bool = True) -> dict:
    """Collect → derive → peer_context → score for all base dates; persist scores."""

    pro = pro or collector.get_pro()
    base = resolve_dates(pro, today)
    codes = list(codes) if codes is not None else universe.ashare_codes()
    ind_of = universe.primary_industry_map()
    log.info("base dates: %s | universe n=%d", base, len(codes))

    store.init(db)
    store.set_manifest("base_dates", base, db)
    store.set_manifest("today", today or base[0], db)
    store.set_manifest("git_sha", _git_sha(), db)
    store.set_manifest("universe_hash", _universe_hash(codes), db)
    store.set_manifest("universe_n", len(codes), db)
    store.set_manifest("adj_mode", "hfq", db)

    done = store.scored_base_dates(db)
    for off in (90, 60, 30):
        asof = base[off]
        if resume and done.get(asof, 0) >= len(codes) * 0.9:
            log.info("base %s already scored (%d) — skip", asof, done.get(asof))
            continue

        def _p(i, n, ts):
            if progress and i % 20 == 0:
                log.info("  collect %s: %d/%d (%s)", asof, i, n, ts)

        db_path, cstats = pipeline.build_pit_for_asof(
            asof, codes, ind_of, resume=resume, pro=pro, progress=_p
        )
        log.info("collected %s: %s", asof, cstats)
        rows = pipeline.score_universe_asof(asof, codes, db_path)
        n = store.put_scores(rows, db)
        log.info("scored %s: %d rows", asof, n)

    return {"base_dates": base, "n_codes": len(codes)}


def compute_returns(today: str | None = None, *, codes: Sequence[str] | None = None,
                    db: Path = store.DEFAULT_DB, pro=None) -> dict:
    """Forward-return labels for the 6 (base, end) pairs from hfq closes."""

    pro = pro or collector.get_pro()
    base = store.get_manifest("base_dates", db) or resolve_dates(pro, today)
    base = {int(k): v for k, v in base.items()}
    codes = list(codes) if codes is not None else universe.ashare_codes()

    dates = sorted(set(base.values()))
    cross = {d: prices.cross_section_hfq_close(pro, d) for d in dates}
    for d in dates:
        log.info("cross-section %s: %d stocks priced", d, len(cross.get(d, {})))
    open_days = cal.open_sessions(pro, base[0])
    pairs = cal.forward_horizon_pairs(base)

    out_rows: list[dict] = []
    for ts in codes:
        for p in pairs:
            bd, ed = p["base_date"], p["end_date"]
            cb, ub, sb = prices.adjusted_close_at(cross, open_days, ts, bd)
            ce, ue, se = prices.adjusted_close_at(cross, open_days, ts, ed)
            fwd = prices.forward_return(cb, ce)
            status = "OK" if fwd is not None else (sb if cb is None else se)
            out_rows.append({
                "ts_code": ts, "base_date": bd, "end_date": ed, "horizon_d": p["horizon_d"],
                "close_base": cb, "close_end": ce, "used_base_date": ub, "used_end_date": ue,
                "fwd_ret": fwd, "status": status,
            })
    n = store.put_returns(out_rows, db)
    n_ok = sum(1 for r in out_rows if r["status"] == "OK")
    log.info("returns: %d rows (%d OK)", n, n_ok)
    return {"rows": n, "ok": n_ok, "pairs": pairs}


def run_all(today: str | None = None, *, codes: Sequence[str] | None = None,
            db: Path = store.DEFAULT_DB, resume: bool = True) -> dict:
    pro = collector.get_pro()
    s = run_scoring(today, codes=codes, db=db, resume=resume, pro=pro)
    r = compute_returns(today, codes=codes, db=db, pro=pro)
    return {"scoring": s, "returns": r}
