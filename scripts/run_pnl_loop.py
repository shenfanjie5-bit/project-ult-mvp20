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
    ap.add_argument("--asof", default=None, help="override snapshot date (testing)")
    a = ap.parse_args()

    from mvp20 import pnl_loop
    from mvp20.server import ServerConfig

    out: dict = {}
    t0 = time.time()

    if a.eval_only:
        out["evaluate"] = pnl_loop.evaluate()
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    from pit_backtest import calendar as pcal
    from pit_backtest import collector, prices

    pro = collector.get_pro()
    today = a.asof or pcal._ashare_today()
    sessions = pcal.open_sessions(pro, today, lookback_days=600)

    if not a.no_snapshot:
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
    out["evaluate"] = pnl_loop.evaluate()
    out["elapsed_s"] = round(time.time() - t0, 1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    raise SystemExit(main())
