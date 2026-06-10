#!/usr/bin/env python3
"""Nightly driver for the production P&L feedback loop (mvp20.pnl_loop).

Run AFTER market close (Asia/Shanghai). Idempotent at every step — safe to
re-run, resumes partial snapshots, never recomputes existing returns.

  .venv/bin/python scripts/run_pnl_loop.py            # snapshot + returns + eval
  .venv/bin/python scripts/run_pnl_loop.py --no-snapshot   # only mature + eval
  .venv/bin/python scripts/run_pnl_loop.py --eval-only

Cron example (22:30 CST nightly, after tushare EOD data settles):
  30 22 * * 1-5  cd <repo> && .venv/bin/python scripts/run_pnl_loop.py >> runtime/pnl_loop.cron.log 2>&1

Snapshot scores the FULL onboarded universe through the same request path the
UI uses (server.handle_score), so the loop measures exactly what users see.
Skips silently when today is not an open session (weekends/holidays).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

os.environ.setdefault("DOCKCASE_WRITEBACK", "0")
os.environ.setdefault("DOCKCASE_CACHE", "1")
sys.path.insert(0, os.getcwd())

log = logging.getLogger("pnl_loop")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-snapshot", action="store_true")
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--full-recompute", action="store_true",
                    help="recompute all eval metrics, not just new pairs")
    ap.add_argument("--asof", default=None, help="must equal today (guard only)")
    a = ap.parse_args()

    from mvp20 import pnl_loop
    from mvp20.server import ServerConfig

    out: dict = {}
    t0 = time.time()

    if a.eval_only:
        out["evaluate"] = pnl_loop.evaluate(full_recompute=a.full_recompute)
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    from datetime import datetime
    from zoneinfo import ZoneInfo

    from pit_backtest import calendar as pcal
    from pit_backtest import collector, prices

    pro = collector.get_pro()
    real_today = pcal._ashare_today()
    # No back-dating: a snapshot scores LIVE hot.sqlite state, so labelling it
    # with a past session would fabricate look-ahead "alpha" the moment
    # fill_returns matures it. --asof exists only for forward-compatible
    # testing and must equal the real Asia/Shanghai date.
    if a.asof and a.asof != real_today:
        print(f"ERROR: --asof {a.asof} != today {real_today}; back-dated "
              f"snapshots are dishonest by construction (scores use live state)",
              file=sys.stderr)
        return 2
    today = real_today
    sessions = pcal.open_sessions(pro, today, lookback_days=600)

    # After-close gate: before 15:30 Asia/Shanghai on an open session, today's
    # close does not exist yet — (a) a snapshot now would be mid-session state
    # mislabelled as the day's reading; (b) today must not count as a matured
    # return endpoint. Snapshot is skipped and today is dropped from the
    # session list used for maturation.
    now_cn = datetime.now(ZoneInfo("Asia/Shanghai"))
    market_closed = (now_cn.hour, now_cn.minute) >= (15, 30)
    if sessions and sessions[-1] == today and not market_closed:
        log.info("before 15:30 CST on open session %s — snapshot deferred, "
                 "today excluded from maturation", today)
        out["snapshot"] = {"asof": today, "status": "market_open", "scored": 0}
        sessions = sessions[:-1]
    elif not a.no_snapshot:
        if sessions and sessions[-1] == today:
            cfg = ServerConfig()
            universe = pnl_loop.list_universe(cfg.stock_overlays_dir)
            score_fn = pnl_loop.production_score_fn(cfg)

            def _p(i, n, ts):
                log.info("snapshot %s: %d/%d (%.0fs)", today, i, n, time.time() - t0)

            out["snapshot"] = pnl_loop.snapshot_scores(
                today, universe, score_fn, progress=_p
            )
        else:
            out["snapshot"] = {"asof": today, "status": "not_a_session", "scored": 0}
            log.info("%s is not an open session — snapshot skipped", today)

    out["fill_returns"] = pnl_loop.fill_returns(
        sessions, lambda d: prices.cross_section_hfq_close(pro, d)
    )
    out["evaluate"] = pnl_loop.evaluate(full_recompute=a.full_recompute)
    out["elapsed_s"] = round(time.time() - t0, 1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    raise SystemExit(main())
