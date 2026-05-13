#!/usr/bin/env python
"""Check Raw Zone directory health."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from data_platform.raw.health import RawHealthIssue, RawHealthReport, check_raw_zone


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    partition_date = None
    if args.date is not None:
        try:
            partition_date = _parse_date(args.date)
        except ValueError as exc:
            report = RawHealthReport(
                root=Path(args.root or "."),
                checked_artifacts=0,
                issues=[
                    RawHealthIssue(
                        severity="error",
                        path=Path(args.root or "."),
                        code="invalid_date",
                        message=str(exc),
                    )
                ],
            )
            _print_report(report, as_json=args.as_json)
            return 1

    report = check_raw_zone(
        args.root,
        source_id=args.source,
        dataset=args.dataset,
        partition_date=partition_date,
        deep=args.deep,
    )
    _print_report(report, as_json=args.as_json)
    return 0 if report.ok else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Raw Zone manifest and artifact health")
    parser.add_argument("--root", help="Raw Zone root. Defaults to DP_RAW_ZONE_PATH settings.")
    parser.add_argument("--source", help="Limit checks to one source_id")
    parser.add_argument("--dataset", help="Limit checks to one dataset")
    parser.add_argument("--date", help="Limit checks to one partition date: YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--deep", action="store_true", help="Read artifacts and validate row counts")
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit stable machine-readable JSON",
    )
    return parser


def _parse_date(value: str) -> date:
    if len(value) == 8 and value.isdigit():
        return datetime.strptime(value, "%Y%m%d").date()
    return date.fromisoformat(value)


def _print_report(report: RawHealthReport, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(_report_to_dict(report), ensure_ascii=False, sort_keys=True))
        return

    status = "ok" if report.ok else "error"
    print(
        f"Raw Zone health: {status}; "
        f"checked_artifacts={report.checked_artifacts}; root={report.root}"
    )
    for issue in report.issues:
        print(f"{issue.severity} {issue.code} {issue.path}: {issue.message}")


def _report_to_dict(report: RawHealthReport) -> dict[str, Any]:
    return {
        "root": str(report.root),
        "checked_artifacts": report.checked_artifacts,
        "ok": report.ok,
        "issues": [
            {
                **asdict(issue),
                "path": str(issue.path),
            }
            for issue in report.issues
        ],
    }


if __name__ == "__main__":
    sys.exit(main())
