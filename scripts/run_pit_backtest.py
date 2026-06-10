#!/usr/bin/env python
"""CLI entry for the isolated A-share point-in-time backtest.

Examples:
  python scripts/run_pit_backtest.py --today 20260605            # full run
  python scripts/run_pit_backtest.py --scoring-only              # collect+derive+peer+score
  python scripts/run_pit_backtest.py --returns-only              # forward-return labels
  python scripts/run_pit_backtest.py --report                    # metrics + report

Writes ONLY under runtime/backtest/ and docs/audit/. Never touches the live
runtime/hot.sqlite.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ensure repo root import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pit_backtest import runner, store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="A-share PIT backtest")
    ap.add_argument("--today", default=None, help="anchor date YYYYMMDD (default: Asia/Shanghai today)")
    ap.add_argument("--db", default=str(store.DEFAULT_DB), help="results sqlite")
    ap.add_argument("--no-resume", action="store_true", help="recompute everything")
    ap.add_argument("--scoring-only", action="store_true")
    ap.add_argument("--returns-only", action="store_true")
    ap.add_argument("--report", action="store_true", help="compute metrics + write report")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    db = Path(args.db)
    resume = not args.no_resume

    if args.report:
        from pit_backtest import report
        out = report.build_report(db=db)
        print("report ->", out)
        return 0
    if args.returns_only:
        print(runner.compute_returns(args.today, db=db))
        return 0
    if args.scoring_only:
        print(runner.run_scoring(args.today, db=db, resume=resume))
        return 0
    print(runner.run_all(args.today, db=db, resume=resume))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
