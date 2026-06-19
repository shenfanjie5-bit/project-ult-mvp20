#!/usr/bin/env python3
"""Merge DockCase CSV full-row scan shards into a progress report."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE_EVIDENCE = ROOT / "docs/audit/dockcase_csv_file_evidence_2026-06-19.json"
DEFAULT_OUTPUT_JSON = ROOT / "docs/audit/dockcase_csv_full_scan_progress_2026-06-19.json"
DEFAULT_OUTPUT_MD = ROOT / "docs/audit/dockcase_csv_full_scan_progress_2026-06-19.md"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _report_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _default_shards(audit_dir: Path) -> list[Path]:
    paths = [audit_dir / "dockcase_csv_full_scan_2026-06-19.json"]
    paths.extend(sorted(audit_dir.glob("dockcase_csv_full_scan_shard_*.json")))
    return [path for path in paths if path.exists()]


def _range_for(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary", {})
    parameters = report.get("parameters", {})
    boundary = summary.get("coverage_boundary", {})
    skip_files = int(parameters.get("skip_files") or boundary.get("skip_files") or 0)
    files_seen = int(summary.get("csv_files_seen") or 0)
    end_file_index = skip_files + files_seen - 1 if files_seen else skip_files - 1
    return {
        "start_file_index": skip_files,
        "end_file_index": end_file_index,
        "files_seen": files_seen,
    }


def build_report(
    shard_paths: list[Path],
    *,
    file_evidence_path: Path,
) -> dict[str, Any]:
    file_evidence = _load_json(file_evidence_path) if file_evidence_path.exists() else {}
    total_business_csv = int(
        (file_evidence.get("summary") or {}).get("csv_files_seen") or 0
    )
    issue_counts: Counter[str] = Counter()
    domain_issue_counts: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    shards: list[dict[str, Any]] = []
    top_issue_files: list[dict[str, Any]] = []

    for path in shard_paths:
        report = _load_json(path)
        summary = report.get("summary", {})
        shard_range = _range_for(report)
        issue_counts.update(summary.get("issue_counts") or {})
        domain_issue_counts.update(summary.get("domain_issue_counts") or {})
        for key in (
            "csv_files_seen",
            "total_bytes",
            "rows_scanned",
            "total_cells",
            "empty_cells",
            "header_read_error_count",
            "row_read_error_count",
            "row_width_mismatch_count",
            "date_invalid_count",
            "numeric_invalid_count",
            "ts_code_invalid_count",
        ):
            totals[key] += int(summary.get(key) or 0)
        shards.append(
            {
                "path": _report_path(path),
                "generated_at": report.get("generated_at"),
                "elapsed_s": report.get("elapsed_s"),
                **shard_range,
                "rows_scanned": summary.get("rows_scanned"),
                "row_read_error_count": summary.get("row_read_error_count"),
                "issue_counts": summary.get("issue_counts", {}),
            }
        )
        for item in report.get("top_issue_files", [])[:20]:
            top_issue_files.append(
                {
                    "source_shard": _report_path(path),
                    **item,
                }
            )

    shards.sort(key=lambda item: int(item["start_file_index"]))
    overlaps: list[dict[str, int]] = []
    gaps: list[dict[str, int]] = []
    previous_end = -1
    for shard in shards:
        start = int(shard["start_file_index"])
        end = int(shard["end_file_index"])
        if start <= previous_end:
            overlaps.append(
                {
                    "start_file_index": start,
                    "previous_end_file_index": previous_end,
                    "overlap_count": previous_end - start + 1,
                }
            )
        elif previous_end >= 0 and start > previous_end + 1:
            gaps.append(
                {
                    "start_file_index": previous_end + 1,
                    "end_file_index": start - 1,
                    "missing_count": start - previous_end - 1,
                }
            )
        previous_end = max(previous_end, end)

    files_scanned = int(totals["csv_files_seen"])
    coverage_ratio = (
        round(files_scanned / total_business_csv, 6) if total_business_csv else 0.0
    )
    top_issue_files.sort(key=lambda item: int(item.get("issue_total") or 0), reverse=True)
    summary = {
        "shard_count": len(shards),
        "total_business_csv_files": total_business_csv,
        "csv_files_scanned": files_scanned,
        "coverage_ratio_of_business_csv_files": coverage_ratio,
        "rows_scanned": int(totals["rows_scanned"]),
        "total_bytes": int(totals["total_bytes"]),
        "total_cells": int(totals["total_cells"]),
        "empty_cells": int(totals["empty_cells"]),
        "empty_cell_ratio": (
            round(totals["empty_cells"] / totals["total_cells"], 6)
            if totals["total_cells"]
            else 0.0
        ),
        "header_read_error_count": int(totals["header_read_error_count"]),
        "row_read_error_count": int(totals["row_read_error_count"]),
        "row_width_mismatch_count": int(totals["row_width_mismatch_count"]),
        "date_invalid_count": int(totals["date_invalid_count"]),
        "numeric_invalid_count": int(totals["numeric_invalid_count"]),
        "ts_code_invalid_count": int(totals["ts_code_invalid_count"]),
        "issue_counts": dict(sorted(issue_counts.items())),
        "domain_issue_counts": dict(sorted(domain_issue_counts.items())),
        "range_overlap_count": len(overlaps),
        "range_gap_count": len(gaps),
        "full_row_semantic_scan_complete": (
            bool(total_business_csv)
            and files_scanned >= total_business_csv
            and not overlaps
            and not gaps
            and int(totals["row_read_error_count"]) == 0
        ),
    }
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scan_mode": "dockcase_csv_full_row_scan_progress",
        "file_evidence_path": _report_path(file_evidence_path),
        "summary": summary,
        "shards": shards,
        "range_overlaps": overlaps,
        "range_gaps": gaps[:100],
        "top_issue_files": top_issue_files[:50],
    }


def write_markdown(report: dict[str, Any], output: Path) -> None:
    summary = report.get("summary", {})
    lines = [
        "# DOCKCASE CSV full-row scan progress",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Shards: `{summary.get('shard_count')}`",
        f"- CSV files scanned: `{summary.get('csv_files_scanned')}` / `{summary.get('total_business_csv_files')}`",
        f"- Coverage ratio: `{summary.get('coverage_ratio_of_business_csv_files')}`",
        f"- Rows scanned: `{summary.get('rows_scanned')}`",
        f"- Row read errors: `{summary.get('row_read_error_count')}`",
        f"- Complete: `{summary.get('full_row_semantic_scan_complete')}`",
        "",
        "## Issue Counts",
        "",
    ]
    issue_counts = summary.get("issue_counts") or {}
    if issue_counts:
        for key, value in sorted(issue_counts.items()):
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- No issues detected in scanned shards.")
    lines.extend(["", "## Shards", "", "| Range | Files | Rows | Path |", "|---|---:|---:|---|"])
    for shard in report.get("shards", []):
        lines.append(
            f"| `{shard.get('start_file_index')}-{shard.get('end_file_index')}` | "
            f"{shard.get('files_seen')} | {shard.get('rows_scanned')} | "
            f"`{shard.get('path')}` |"
        )
    lines.extend(["", "## Top Issue Files", "", "| Path | Issues | Source shard |", "|---|---:|---|"])
    for item in report.get("top_issue_files", [])[:20]:
        lines.append(
            f"| `{item.get('path')}` | {item.get('issue_total')} | `{item.get('source_shard')}` |"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-dir", type=Path, default=ROOT / "docs/audit")
    parser.add_argument("--file-evidence", type=Path, default=DEFAULT_FILE_EVIDENCE)
    parser.add_argument("--shard-json", action="append", type=Path, default=[])
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    shard_paths = args.shard_json or _default_shards(args.audit_dir)
    report = build_report(shard_paths, file_evidence_path=args.file_evidence)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, args.output_md)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
