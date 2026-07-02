#!/usr/bin/env python3
"""Rank remaining DockCase semantic-audit work from existing evidence.

The full DockCase CSV semantic pass is intentionally signature-stratified. This
script does not rescan the 54G warehouse; it turns that bounded evidence into a
machine-readable backlog so the next exhaustive or incremental passes can target
the largest and riskiest gaps first.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "docs/audit/dockcase_csv_semantics_2026-06-18.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/dockcase_semantic_backlog_2026-06-18.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/dockcase_semantic_backlog_2026-06-18.md"


ISSUE_WEIGHTS = {
    "row_width_mismatch": 8.0,
    "csv_read_error": 8.0,
    "ohlc_invariant_violation": 7.0,
    "negative_ohlc_value": 7.0,
    "by_symbol_code_mismatch": 6.0,
    "index_by_symbol_bundle_mismatch": 5.0,
    "future_primary_date_gt_7d": 5.0,
    "invalid_date": 4.0,
    "invalid_numeric": 4.0,
    "invalid_ts_code": 4.0,
    "duplicate_grain_key_sample": 3.0,
    "zero_ohlc_no_trade_carry_forward": 3.0,
    "high_empty_cell_ratio_signature": 2.0,
    "sparse_columns_lt_5pct_non_empty": 1.0,
    "stale_primary_market_date_gt_45d": 1.0,
    "no_sampled_rows": 6.0,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _issue_score(issue_counts: Mapping[str, Any]) -> float:
    score = 0.0
    for issue, count in issue_counts.items():
        try:
            n = float(count)
        except (TypeError, ValueError):
            continue
        score += ISSUE_WEIGHTS.get(str(issue), 1.0) * n
    return score


def _row_backlog(row: Mapping[str, Any]) -> dict[str, Any]:
    file_count = int(row.get("file_count") or 0)
    selected_files = int(row.get("selected_files") or 0)
    sampled_files = int(row.get("sampled_files") or 0)
    sampled_rows = int(row.get("sampled_rows") or 0)
    unselected = int(row.get("unselected_files_due_to_limit") or 0)
    issue_counts = dict(row.get("issue_counts") or {})
    issue_score = _issue_score(issue_counts)
    coverage_gap_score = (
        unselected
        + max(selected_files - sampled_files, 0) * 10
        + (file_count * 10 if sampled_rows == 0 else 0)
    )
    priority_score = round(coverage_gap_score + issue_score * 25, 3)
    return {
        "signature_rank": row.get("signature_rank"),
        "file_count": file_count,
        "selected_files": selected_files,
        "sampled_files": sampled_files,
        "sampled_rows": sampled_rows,
        "unselected_files_due_to_limit": unselected,
        "selected_files_without_sampled_rows": max(selected_files - sampled_files, 0),
        "issue_score": round(issue_score, 3),
        "priority_score": priority_score,
        "issue_counts": issue_counts,
        "columns": list(row.get("columns") or [])[:20],
        "examples": list(row.get("examples") or [])[:5],
        "freshness": row.get("freshness") or {},
    }


def build_report(input_path: Path) -> dict[str, Any]:
    source = _load(input_path)
    summary = source.get("summary") or {}
    signatures = [_row_backlog(row) for row in source.get("signatures", [])]
    signatures.sort(
        key=lambda row: (
            float(row["priority_score"]),
            int(row["unselected_files_due_to_limit"]),
            int(row["file_count"]),
        ),
        reverse=True,
    )

    unselected_files = int(summary.get("unselected_files_due_to_signature_file_limit") or 0)
    no_sampled = [
        row for row in signatures
        if int(row["sampled_rows"]) == 0 or int(row["selected_files_without_sampled_rows"]) > 0
    ]
    issue_heavy = [row for row in signatures if row["issue_counts"]]
    high_volume = [row for row in signatures if int(row["unselected_files_due_to_limit"]) > 0]
    next_batches = {
        "p0_no_sampled_rows": no_sampled[:20],
        "p1_high_issue_signatures": sorted(
            issue_heavy,
            key=lambda row: (float(row["issue_score"]), int(row["file_count"])),
            reverse=True,
        )[:20],
        "p1_high_volume_unselected_files": high_volume[:20],
    }

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_path": str(input_path),
        "status": "ready",
        "summary": {
            "source_scan_mode": source.get("scan_mode"),
            "csv_files_seen": summary.get("csv_files_seen"),
            "signature_count": summary.get("signature_count"),
            "sampled_signature_count": summary.get("sampled_signature_count"),
            "sampled_files": summary.get("sampled_files"),
            "sampled_rows": summary.get("sampled_rows"),
            "unselected_files_due_to_signature_file_limit": unselected_files,
            "signatures_with_no_sampled_rows_or_empty_selected_files": len(no_sampled),
            "signatures_with_sampled_issues": len(issue_heavy),
            "top_priority_signature_rank": signatures[0]["signature_rank"] if signatures else None,
            "completion_status": (
                "not_complete"
                if unselected_files or no_sampled
                else "semantic_signature_sampling_complete"
            ),
        },
        "next_batches": next_batches,
        "ranked_backlog": signatures[:100],
    }


def write_markdown(report: dict[str, Any], output: Path) -> None:
    summary = report["summary"]
    lines = [
        "# DOCKCASE semantic audit backlog",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Source: `{report.get('source_path')}`",
        f"- Completion status: `{summary.get('completion_status')}`",
        f"- CSV files seen: `{summary.get('csv_files_seen')}`",
        f"- Header signatures: `{summary.get('signature_count')}`",
        f"- Sampled files / rows: `{summary.get('sampled_files')}` / `{summary.get('sampled_rows')}`",
        f"- Unselected CSV files due to per-signature cap: `{summary.get('unselected_files_due_to_signature_file_limit')}`",
        f"- Signatures with no sampled rows or empty selected files: `{summary.get('signatures_with_no_sampled_rows_or_empty_selected_files')}`",
        f"- Signatures with sampled issues: `{summary.get('signatures_with_sampled_issues')}`",
        "",
        "## Next Batches",
        "",
    ]
    for label, rows in report.get("next_batches", {}).items():
        lines.extend([f"### `{label}`", ""])
        if not rows:
            lines.extend(["- None.", ""])
            continue
        lines.extend([
            "| Rank | Files | Unselected | Sampled rows | Issue score | Priority | Columns | Example |",
            "|---:|---:|---:|---:|---:|---:|---|---|",
        ])
        for row in rows[:10]:
            columns = ", ".join(row["columns"][:6])
            example = row["examples"][0] if row["examples"] else ""
            lines.append(
                f"| `{row['signature_rank']}` | `{row['file_count']}` | "
                f"`{row['unselected_files_due_to_limit']}` | `{row['sampled_rows']}` | "
                f"`{row['issue_score']}` | `{row['priority_score']}` | "
                f"`{columns}` | `{example}` |"
            )
        lines.append("")
    lines.extend([
        "## Interpretation",
        "",
        "This backlog does not claim full semantic completion. It ranks the exact",
        "remaining bounded-sampling gaps from the existing DockCase CSV semantic",
        "audit so follow-up passes can target high-volume signatures, no-row",
        "signatures, and issue-heavy signatures first.",
        "",
    ])
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument("--markdown-output", default=str(DEFAULT_MD_OUTPUT))
    args = parser.parse_args()

    report = build_report(Path(args.input))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.markdown_output))
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
