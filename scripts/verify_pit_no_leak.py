#!/usr/bin/env python
"""Standalone PIT leakage verifier. Exit non-zero on any HARD violation.

Usage: python scripts/verify_pit_no_leak.py [backtest.sqlite]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pit_backtest import leakage_audit, store  # noqa: E402


def main() -> int:
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else store.DEFAULT_DB
    rep = leakage_audit.run_full_audit(db)
    print(f"=== PIT leakage audit ({db}) ===")
    print(f"base_dates: {rep['base_dates']}")
    for asof, a in rep["per_asof"].items():
        print(f"\n[{asof}] rows={a['n_rows']} HARD={len(a['hard'])} WARN={len(a['warn'])}")
        # show per-dp max observation date (eyeball that all <= asof)
        over = {dp: d for dp, d in a["dp_max_date"].items() if d > asof}
        print(f"   max obs-date <= asof for {len(a['dp_max_date'])} dp_ids; "
              f"{'NONE over' if not over else 'OVER: ' + str(over)}")
        for v in a["hard"][:10]:
            print("   HARD:", v)
        for v in a["warn"][:5]:
            print("   warn:", v)
    print(f"\nreturns: n={rep['returns']['n']} HARD={len(rep['returns']['hard'])}")
    for v in rep["returns"]["hard"][:10]:
        print("   HARD:", v)
    if rep["artifacts"]["warn"]:
        print("artifacts:", rep["artifacts"]["warn"])
    print(f"\nTOTAL: hard={rep['hard_total']} warn={rep['warn_total']} -> "
          f"{'PASS' if rep['ok'] else 'FAIL'}")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
