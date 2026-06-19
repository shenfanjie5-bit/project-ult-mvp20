#!/usr/bin/env python3
"""Full-row semantic scan for DockCase business CSV files.

The older DockCase audits prove all-file header/head-tail evidence and bounded
semantic samples.  This pass reads every non-empty row for every business CSV it
is asked to scan, writes one compact evidence row per file to gzip JSONL, and
keeps only aggregate counters plus top issue files in the JSON report.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import audit_dockcase_csv_semantics as base


DEFAULT_DATA_ROOT = Path("/Volumes/dockcase2tb/database_all")
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/dockcase_csv_full_scan_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/dockcase_csv_full_scan_2026-06-19.md"
DEFAULT_EVIDENCE_JSONL_GZ = ROOT / "docs/audit/dockcase_csv_full_scan_2026-06-19.jsonl.gz"


def _header_signature(columns: tuple[str, ...]) -> str:
    raw = "\x1f".join(columns).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def _iter_all_rows(path: Path) -> Iterable[tuple[str, ...]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)
        for row in reader:
            if any(cell.strip() for cell in row):
                yield tuple(row)


def _scan_file(path: Path, root: Path, *, as_of_date) -> dict[str, Any]:
    rel = base._rel(path, root)
    size = int(path.stat().st_size)
    try:
        header = base._read_header(path)
    except Exception as exc:  # noqa: BLE001
        return {
            "path": rel,
            "bytes": size,
            "header_read_ok": False,
            "header_error": str(exc),
            "rows_scanned": 0,
            "issue_counts": {"header_read_error": 1},
        }

    sig = base.SignatureSample(columns=header, file_count=1, examples=[rel])
    for column in header:
        sig.column_profiles.setdefault(column, base.ColumnProfile())
    row_read_errors: list[str] = []
    try:
        for row in _iter_all_rows(path):
            sig.sampled_rows += 1
            sig.total_cells += len(sig.columns)
            if len(row) != len(sig.columns):
                sig.row_width_mismatch_count += 1
                if len(sig.row_width_mismatch_examples) < 5:
                    sig.row_width_mismatch_examples.append(
                        {
                            "path": rel,
                            "column_count": len(sig.columns),
                            "row_width": len(row),
                        }
                    )
            base._check_domain_row(sig, rel, row)
            for idx, column in enumerate(sig.columns):
                value = row[idx] if idx < len(row) else ""
                base._profile_value(sig, column, value)
    except Exception as exc:  # noqa: BLE001
        row_read_errors.append(str(exc))

    sig.sampled_files = 1 if sig.sampled_rows else 0
    payload = base._signature_payload(1, sig, as_of_date=as_of_date)
    issue_counts = Counter(payload.get("issue_counts") or {})
    if row_read_errors:
        issue_counts["csv_row_read_error"] += len(row_read_errors)
    date_invalid = 0
    numeric_invalid = 0
    ts_code_invalid = 0
    sparse_column_count = 0
    for item in payload.get("column_profiles", {}).get("date", []):
        date_invalid += int(item.get("invalid") or 0)
    for item in payload.get("column_profiles", {}).get("numeric", []):
        numeric_invalid += int(item.get("numeric_invalid") or 0)
    for item in payload.get("column_profiles", {}).get("ts_code", []):
        ts_code_invalid += int(item.get("invalid") or 0)
    sparse_column_count = len(payload.get("column_profiles", {}).get("sparse", []))
    return {
        "path": rel,
        "bytes": size,
        "header_read_ok": True,
        "header_signature_sha256": _header_signature(header),
        "column_count": len(header),
        "rows_scanned": sig.sampled_rows,
        "total_cells": sig.total_cells,
        "empty_cells": sig.empty_cells,
        "empty_cell_ratio": payload.get("empty_cell_ratio"),
        "row_width_mismatch_count": sig.row_width_mismatch_count,
        "date_invalid_count": date_invalid,
        "numeric_invalid_count": numeric_invalid,
        "ts_code_invalid_count": ts_code_invalid,
        "sparse_column_count": sparse_column_count,
        "freshness": payload.get("freshness", {}),
        "domain_issue_counts": payload.get("domain_issue_counts", {}),
        "issue_counts": dict(sorted(issue_counts.items())),
        "issue_examples_by_code": payload.get("domain_issue_examples_by_code", {}),
        "row_read_errors": row_read_errors[:5],
        "columns_sample": list(header[:20]),
    }


def build_report(
    data_root: Path,
    *,
    evidence_jsonl_gz: Path,
    skip_files: int = 0,
    max_files: int | None,
    prunes: tuple[str, ...] = base.DEFAULT_PRUNES,
    as_of_date,
    progress_every: int = 0,
) -> dict[str, Any]:
    started = time.time()
    summary_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    domain_issue_counts: Counter[str] = Counter()
    signature_counts: Counter[str] = Counter()
    signature_rows: Counter[str] = Counter()
    signature_issues: dict[str, Counter[str]] = defaultdict(Counter)
    top_issue_files: list[dict[str, Any]] = []
    header_errors: list[dict[str, str]] = []
    row_read_errors: list[dict[str, Any]] = []

    evidence_jsonl_gz.parent.mkdir(parents=True, exist_ok=True)

    if not data_root.exists():
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "elapsed_s": 0.0,
            "data_root": str(data_root),
            "exists": False,
            "scan_mode": "missing_data_root",
            "summary": {"csv_files_seen": 0, "full_row_semantic_scan": False},
        }

    with gzip.open(evidence_jsonl_gz, "wt", encoding="utf-8") as out:
        selected_idx = 0
        for idx, path in enumerate(base._walk_csv(data_root, prunes), start=1):
            if idx <= skip_files:
                continue
            selected_idx += 1
            if max_files is not None and selected_idx > max_files:
                break
            row = _scan_file(path, data_root, as_of_date=as_of_date)
            out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            summary_counts["csv_files_seen"] += 1
            summary_counts["total_bytes"] += int(row.get("bytes") or 0)
            summary_counts["rows_scanned"] += int(row.get("rows_scanned") or 0)
            summary_counts["total_cells"] += int(row.get("total_cells") or 0)
            summary_counts["empty_cells"] += int(row.get("empty_cells") or 0)
            summary_counts["row_width_mismatch_count"] += int(
                row.get("row_width_mismatch_count") or 0
            )
            summary_counts["date_invalid_count"] += int(row.get("date_invalid_count") or 0)
            summary_counts["numeric_invalid_count"] += int(row.get("numeric_invalid_count") or 0)
            summary_counts["ts_code_invalid_count"] += int(row.get("ts_code_invalid_count") or 0)
            if not row.get("header_read_ok"):
                header_errors.append({"path": row["path"], "error": row.get("header_error", "")})
            if row.get("row_read_errors"):
                row_read_errors.append({"path": row["path"], "errors": row["row_read_errors"]})
            issue_counts.update(row.get("issue_counts") or {})
            domain_issue_counts.update(row.get("domain_issue_counts") or {})
            signature = row.get("header_signature_sha256")
            if signature:
                signature = str(signature)
                signature_counts[signature] += 1
                signature_rows[signature] += int(row.get("rows_scanned") or 0)
                signature_issues[signature].update(row.get("issue_counts") or {})
            file_issue_total = sum(int(v) for v in (row.get("issue_counts") or {}).values())
            if file_issue_total:
                top_issue_files.append(
                    {
                        "path": row["path"],
                        "rows_scanned": row.get("rows_scanned"),
                        "issue_total": file_issue_total,
                        "issue_counts": row.get("issue_counts"),
                    }
                )
                top_issue_files.sort(key=lambda item: int(item["issue_total"]), reverse=True)
                del top_issue_files[50:]
            if (
                progress_every
                and summary_counts["csv_files_seen"] % progress_every == 0
            ):
                out.flush()
                print(
                    json.dumps(
                        {
                            "files": summary_counts["csv_files_seen"],
                            "rows": summary_counts["rows_scanned"],
                            "elapsed_s": round(time.time() - started, 1),
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )

    files_seen = int(summary_counts["csv_files_seen"])
    full_scan = max_files is None
    top_signatures = []
    for signature, file_count in signature_counts.most_common(20):
        top_signatures.append(
            {
                "header_signature_sha256": signature,
                "files": file_count,
                "rows_scanned": int(signature_rows[signature]),
                "issue_counts": dict(sorted(signature_issues[signature].items())),
            }
        )
    summary = {
        "csv_files_seen": files_seen,
        "total_bytes": int(summary_counts["total_bytes"]),
        "rows_scanned": int(summary_counts["rows_scanned"]),
        "total_cells": int(summary_counts["total_cells"]),
        "empty_cells": int(summary_counts["empty_cells"]),
        "empty_cell_ratio": (
            round(summary_counts["empty_cells"] / summary_counts["total_cells"], 6)
            if summary_counts["total_cells"]
            else 0.0
        ),
        "header_read_error_count": len(header_errors),
        "row_read_error_count": len(row_read_errors),
        "signature_count": len(signature_counts),
        "row_width_mismatch_count": int(summary_counts["row_width_mismatch_count"]),
        "date_invalid_count": int(summary_counts["date_invalid_count"]),
        "numeric_invalid_count": int(summary_counts["numeric_invalid_count"]),
        "ts_code_invalid_count": int(summary_counts["ts_code_invalid_count"]),
        "issue_counts": dict(sorted(issue_counts.items())),
        "domain_issue_counts": dict(sorted(domain_issue_counts.items())),
        "full_row_semantic_scan": full_scan,
        "coverage_boundary": {
            "all_business_csv_files_selected": full_scan,
            "all_selected_files_read_to_eof": len(row_read_errors) == 0,
            "full_row_semantic_scan": full_scan and len(row_read_errors) == 0,
            "max_files_limit": max_files,
            "skip_files": skip_files,
        },
    }
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - started, 3),
        "data_root": str(data_root),
        "exists": True,
        "scan_mode": "all_selected_business_csv_full_row_semantics",
        "parameters": {
            "max_files": max_files,
            "skip_files": skip_files,
            "as_of_date": as_of_date.isoformat(),
            "prunes": list(prunes),
        },
        "summary": summary,
        "file_evidence_storage": {
            "format": "jsonl.gz",
            "path": str(evidence_jsonl_gz),
            "row_count": files_seen,
        },
        "header_read_errors": header_errors[:100],
        "row_read_errors": row_read_errors[:100],
        "top_issue_files": top_issue_files,
        "top_header_signatures": top_signatures,
    }


def write_markdown(report: dict[str, Any], output: Path) -> None:
    summary = report.get("summary", {})
    boundary = summary.get("coverage_boundary", {})
    lines = [
        "# DOCKCASE CSV full-row semantic scan",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Data root: `{report.get('data_root')}`",
        f"- Scan mode: `{report.get('scan_mode')}`",
        f"- Elapsed: `{report.get('elapsed_s')}` seconds",
        f"- CSV files scanned: `{summary.get('csv_files_seen')}`",
        f"- Rows scanned: `{summary.get('rows_scanned')}`",
        f"- Header signatures: `{summary.get('signature_count')}`",
        f"- Header read errors: `{summary.get('header_read_error_count')}`",
        f"- Row read errors: `{summary.get('row_read_error_count')}`",
        f"- Full row semantic scan: `{summary.get('full_row_semantic_scan')}`",
        "",
        "## Coverage Boundary",
        "",
        "| Boundary | Value |",
        "|---|---:|",
    ]
    for key, value in boundary.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Issue Counts", ""])
    issue_counts = summary.get("issue_counts") or {}
    if issue_counts:
        for key, value in sorted(issue_counts.items()):
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- No semantic issues detected in the selected full-row scan.")
    lines.extend(["", "## Domain Issue Counts", ""])
    domain_issue_counts = summary.get("domain_issue_counts") or {}
    if domain_issue_counts:
        for key, value in sorted(domain_issue_counts.items()):
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- No domain-invariant issues detected.")
    lines.extend(
        [
            "",
            "## Top Issue Files",
            "",
            "| Path | Rows | Issue total | Issues |",
            "|---|---:|---:|---|",
        ]
    )
    for row in report.get("top_issue_files", [])[:20]:
        issues = ", ".join(
            f"{key}={value}" for key, value in sorted((row.get("issue_counts") or {}).items())
        )
        lines.append(
            f"| `{row.get('path')}` | {row.get('rows_scanned')} | "
            f"{row.get('issue_total')} | {issues or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Top Header Signatures",
            "",
            "| SHA-256 | Files | Rows scanned | Issues |",
            "|---|---:|---:|---|",
        ]
    )
    for row in report.get("top_header_signatures", [])[:20]:
        issues = ", ".join(
            f"{key}={value}" for key, value in sorted((row.get("issue_counts") or {}).items())
        )
        lines.append(
            f"| `{row.get('header_signature_sha256')}` | {row.get('files')} | "
            f"{row.get('rows_scanned')} | {issues or '-'} |"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--evidence-jsonl-gz", type=Path, default=DEFAULT_EVIDENCE_JSONL_GZ)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--skip-files", type=int, default=0)
    parser.add_argument("--as-of-date", default=time.strftime("%Y-%m-%d"))
    parser.add_argument("--progress-every", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        args.data_root,
        evidence_jsonl_gz=args.evidence_jsonl_gz,
        skip_files=args.skip_files,
        max_files=args.max_files,
        as_of_date=dt.date.fromisoformat(args.as_of_date),
        progress_every=args.progress_every,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, args.output_md)
    print(json.dumps(report.get("summary", {}), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
