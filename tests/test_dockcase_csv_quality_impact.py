import json
from pathlib import Path

from scripts.audit_dockcase_csv_quality_impact import build_report


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_dockcase_csv_quality_impact_classifies_non_blocking_and_watchlist(tmp_path: Path) -> None:
    full_scan_path = tmp_path / "full_scan_progress.json"
    file_evidence_path = tmp_path / "file_evidence.json"
    _write_json(
        full_scan_path,
        {
            "total_business_csv_files": 10,
            "csv_files_scanned": 10,
            "coverage_ratio_of_business_csv_files": 1.0,
            "rows_scanned": 1000,
            "header_read_error_count": 0,
            "row_read_error_count": 0,
            "row_width_mismatch_count": 0,
            "range_overlap_count": 0,
            "range_gap_count": 0,
            "issue_counts": {
                "index_by_symbol_bundle_mismatch": 20,
                "ohlc_invariant_violation": 2,
            },
        },
    )
    _write_json(file_evidence_path, {"file_evidence_count": 10})

    report = build_report(
        full_scan_progress_path=full_scan_path,
        file_evidence_path=file_evidence_path,
    )

    summary = report["summary"]
    assert summary["read_or_shape_error_count"] == 0
    assert summary["current_mvp_data_quality_actionable_gap_count"] == 0
    assert summary["current_mvp_non_blocking_issue_total_count"] == 20
    assert summary["watchlist_issue_total_count"] == 2
    by_issue = {row["issue"]: row for row in report["rows"]}
    assert by_issue["index_by_symbol_bundle_mismatch"]["impact"] == (
        "current_mvp_non_blocking"
    )
    assert by_issue["ohlc_invariant_violation"]["impact"] == "watchlist"
