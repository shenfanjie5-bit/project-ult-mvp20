#!/usr/bin/env python3
"""Initialise the SQLite hot-snapshot database under ``runtime/hot.sqlite``.

Idempotent: re-running is safe. Run once before starting the collector.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mvp20.storage import init_db  # noqa: E402


def main() -> int:
    db_path = ROOT / "runtime" / "hot.sqlite"
    init_db(db_path)
    print(f"initialised {db_path} ({db_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
