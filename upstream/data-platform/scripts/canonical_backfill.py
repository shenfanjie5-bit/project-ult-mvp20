#!/usr/bin/env python
"""Run a canonical Iceberg table backfill from an explicit DuckDB SELECT."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Sequence

from data_platform.config import get_settings
from data_platform.serving.catalog import load_catalog
from data_platform.serving.schema_evolution import run_canonical_backfill


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill a canonical Iceberg table from a DuckDB SELECT."
    )
    parser.add_argument("--table", required=True, help="canonical table identifier")
    parser.add_argument("--sql-file", required=True, type=Path, help="file containing SELECT SQL")
    parser.add_argument(
        "--duckdb-path",
        type=Path,
        default=None,
        help="DuckDB database path; defaults to DP_DUCKDB_PATH",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the SELECT without writing an Iceberg snapshot",
    )

    try:
        args = parser.parse_args(argv)
        duckdb_path = args.duckdb_path or get_settings().duckdb_path
        select_sql = args.sql_file.read_text(encoding="utf-8")
        result = run_canonical_backfill(
            load_catalog(),
            duckdb_path,
            args.table,
            select_sql,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        error_payload = {"error": type(exc).__name__, "detail": str(exc)}
        print(json.dumps(error_payload, sort_keys=True), file=sys.stderr)
        return 1

    if result is None:
        payload = {"dry_run": True, "row_count": None, "snapshot_id": None, "table": args.table}
    else:
        payload = asdict(result)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
