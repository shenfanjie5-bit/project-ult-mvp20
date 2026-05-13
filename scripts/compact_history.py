#!/usr/bin/env python3
"""Daily Parquet compaction: merge yesterday's minute files into one daily file.

Run from cron::

    0 1 * * *  cd /path/to/mvp20 && .venv/bin/python scripts/compact_history.py

Idempotent: if already compacted, returns 0 without re-compacting (no source
files to find means a no-op).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mvp20.history import compact_date, compact_yesterday  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history-dir", type=Path, default=ROOT / "runtime" / "history",
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="YYYYMMDD to compact (default: yesterday).",
    )
    parser.add_argument(
        "--keep-source", action="store_true",
        help="Don't delete the per-minute parquet files after compacting.",
    )
    args = parser.parse_args()

    if args.date:
        out = compact_date(args.history_dir, args.date,
                           delete_source=not args.keep_source)
    else:
        out = compact_yesterday(args.history_dir)

    if out is None:
        print(f"[compact] nothing to compact under {args.history_dir / 'minute'}")
        return 0
    size_kb = out.stat().st_size // 1024
    print(f"[compact] wrote {out} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
