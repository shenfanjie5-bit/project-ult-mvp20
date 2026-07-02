#!/usr/bin/env python3
"""Classify DOCKCASE CSV full-scan issues by current MVP impact."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_unknown_acquisition_backlog import ROOT, _portable_path  # noqa: E402


AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_FULL_SCAN_PROGRESS_PATH = AUDIT_DIR / "dockcase_csv_full_scan_progress_2026-06-19.json"
DEFAULT_FILE_EVIDENCE_PATH = AUDIT_DIR / "dockcase_csv_file_evidence_2026-06-19.json"
DEFAULT_JSON_OUTPUT = AUDIT_DIR / "dockcase_csv_quality_impact_2026-06-20.json"
DEFAULT_MD_OUTPUT = AUDIT_DIR / "dockcase_csv_quality_impact_2026-06-20.md"

ISSUE_POLICIES: dict[str, dict[str, str]] = {
    "index_by_symbol_bundle_mismatch": {
        "impact": "current_mvp_non_blocking",
        "scope": "index_bundle_metadata",
        "rationale": "Index-by-symbol bundle naming mismatch does not feed current A-share score, BFF, graph, or PIT scoring inputs.",
    },
    "duplicate_grain_key_sample": {
        "impact": "current_mvp_non_blocking",
        "scope": "raw_csv_history",
        "rationale": "Current runtime hot store uses primary-key upserts and audited materialization hashes; raw CSV duplicate samples are retained for offline dedup review.",
    },
    "sparse_columns_lt_5pct_non_empty": {
        "impact": "current_mvp_non_blocking",
        "scope": "optional_statement_columns",
        "rationale": "Sparse optional financial columns are not promoted to Known score inputs without field-level validity audits.",
    },
    "invalid_ts_code": {
        "impact": "current_mvp_non_blocking",
        "scope": "non_equity_or_legacy_symbols",
        "rationale": "Invalid raw-code samples are dominated by fund/index/legacy symbols and are filtered before A-share target scoring.",
    },
    "high_empty_cell_ratio_signature": {
        "impact": "current_mvp_non_blocking",
        "scope": "wide_optional_tables",
        "rationale": "High-empty signatures are wide optional tables; field-level collectors and bridge audits decide score eligibility.",
    },
    "no_sampled_rows": {
        "impact": "current_mvp_non_blocking",
        "scope": "header_only_files",
        "rationale": "Full file evidence identifies four header-only/tail-empty files; they are not current score/backtest inputs.",
    },
    "invalid_numeric": {
        "impact": "watchlist",
        "scope": "raw_numeric_cells",
        "rationale": "Numeric parse issues are rare versus total cells and require per-source review before any direct CSV-backed promotion.",
    },
    "invalid_date": {
        "impact": "watchlist",
        "scope": "raw_date_cells",
        "rationale": "Date parse issues are rare versus scanned rows; current hot-store freshness uses collector timestamps and audited source rows.",
    },
    "ohlc_invariant_violation": {
        "impact": "watchlist",
        "scope": "historical_market_bars",
        "rationale": "OHLC invariant violations matter for offline bar repair, but current score and BFF are served from hot.sqlite/derived artifacts.",
    },
    "zero_ohlc_no_trade_carry_forward": {
        "impact": "watchlist",
        "scope": "historical_market_bars",
        "rationale": "Zero-traffic carry-forward rows are legitimate no-trade cases for some securities and must be handled by bar-specific loaders.",
    },
    "stale_primary_market_date_gt_45d": {
        "impact": "watchlist",
        "scope": "inactive_or_legacy_files",
        "rationale": "Stale raw files are expected for inactive/legacy symbols; current runtime freshness is audited separately in BFF/score paths.",
    },
    "future_primary_date_gt_7d": {
        "impact": "watchlist",
        "scope": "raw_date_cells",
        "rationale": "Future dates remain review items, but the current MVP does not ingest raw CSV rows directly into score without collector/source validation.",
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _summary_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, Mapping) else payload


def build_report(
    *,
    full_scan_progress_path: Path,
    file_evidence_path: Path,
) -> dict[str, Any]:
    full_scan = _load_json(full_scan_progress_path)
    file_evidence = _load_json(file_evidence_path)
    full_scan_summary = _summary_payload(full_scan)
    file_evidence_summary = _summary_payload(file_evidence)
    issue_counts = full_scan_summary.get("issue_counts") or {}
    rows: list[dict[str, Any]] = []
    for issue, count in sorted(issue_counts.items()):
        policy = ISSUE_POLICIES.get(
            str(issue),
            {
                "impact": "watchlist",
                "scope": "unclassified_raw_csv_issue",
                "rationale": "No current-MVP blocking rule exists; retain as watchlist until source-specific use is proposed.",
            },
        )
        rows.append(
            {
                "issue": str(issue),
                "count": int(count or 0),
                "impact": policy["impact"],
                "scope": policy["scope"],
                "rationale": policy["rationale"],
            }
        )
    blocking_rows = [row for row in rows if row["impact"] == "blocking"]
    watchlist_rows = [row for row in rows if row["impact"] == "watchlist"]
    non_blocking_rows = [row for row in rows if row["impact"] == "current_mvp_non_blocking"]
    read_error_count = sum(
        int(full_scan_summary.get(key) or 0)
        for key in (
            "header_read_error_count",
            "row_read_error_count",
            "row_width_mismatch_count",
            "range_overlap_count",
            "range_gap_count",
        )
    )
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "full_scan_progress_path": _portable_path(full_scan_progress_path),
            "file_evidence_path": _portable_path(file_evidence_path),
        },
        "summary": {
            "total_business_csv_files": int(full_scan_summary.get("total_business_csv_files") or 0),
            "csv_files_scanned": int(full_scan_summary.get("csv_files_scanned") or 0),
            "coverage_ratio_of_business_csv_files": float(
                full_scan_summary.get("coverage_ratio_of_business_csv_files") or 0.0
            ),
            "rows_scanned": int(full_scan_summary.get("rows_scanned") or 0),
            "file_evidence_count": int(file_evidence_summary.get("file_evidence_count") or 0),
            "read_or_shape_error_count": read_error_count,
            "blocking_issue_type_count": len(blocking_rows),
            "blocking_issue_total_count": sum(row["count"] for row in blocking_rows),
            "watchlist_issue_type_count": len(watchlist_rows),
            "watchlist_issue_total_count": sum(row["count"] for row in watchlist_rows),
            "current_mvp_non_blocking_issue_type_count": len(non_blocking_rows),
            "current_mvp_non_blocking_issue_total_count": sum(row["count"] for row in non_blocking_rows),
            "current_mvp_data_quality_actionable_gap_count": len(blocking_rows),
            "score_mutation": "none; this audit classifies existing full-scan evidence only",
        },
        "blocking_rows": blocking_rows,
        "watchlist_rows": watchlist_rows,
        "rows": rows,
    }


def _md_table_row(values: list[Any]) -> str:
    return "| " + " | ".join(str(value) for value in values) + " |"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# DOCKCASE CSV quality impact audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- CSV scan coverage: `{summary['csv_files_scanned']}` / `{summary['total_business_csv_files']}` ({summary['coverage_ratio_of_business_csv_files']})",
        f"- Rows scanned: `{summary['rows_scanned']}`",
        f"- Read/shape errors: `{summary['read_or_shape_error_count']}`",
        f"- Current-MVP data-quality actionable gaps: `{summary['current_mvp_data_quality_actionable_gap_count']}`",
        f"- Watchlist issue types: `{summary['watchlist_issue_type_count']}`",
        f"- Non-blocking issue types: `{summary['current_mvp_non_blocking_issue_type_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Issues",
        "",
        "| Issue | Count | Impact | Scope |",
        "|---|---:|---|---|",
    ]
    for row in report.get("rows") or []:
        lines.append(
            _md_table_row(
                [
                    f"`{row['issue']}`",
                    row["count"],
                    f"`{row['impact']}`",
                    row["scope"],
                ]
            )
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-scan-progress-path", type=Path, default=DEFAULT_FULL_SCAN_PROGRESS_PATH)
    parser.add_argument("--file-evidence-path", type=Path, default=DEFAULT_FILE_EVIDENCE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        full_scan_progress_path=args.full_scan_progress_path,
        file_evidence_path=args.file_evidence_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
