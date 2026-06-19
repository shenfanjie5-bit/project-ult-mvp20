import json

from scripts.audit_dockcase_semantic_backlog import build_report


def test_dockcase_semantic_backlog_prioritizes_remaining_gaps(tmp_path):
    payload = {
        "scan_mode": "header_signature_stratified_bounded_row_semantics",
        "summary": {
            "csv_files_seen": 103,
            "signature_count": 3,
            "sampled_signature_count": 2,
            "sampled_files": 2,
            "sampled_rows": 20,
            "unselected_files_due_to_signature_file_limit": 98,
        },
        "signatures": [
            {
                "signature_rank": 1,
                "file_count": 100,
                "selected_files": 2,
                "sampled_files": 2,
                "sampled_rows": 20,
                "unselected_files_due_to_limit": 98,
                "issue_counts": {},
                "columns": ["ts_code", "trade_date", "close"],
                "examples": ["股票数据/行情数据/日线行情/by_symbol/000001.SZ.csv"],
            },
            {
                "signature_rank": 2,
                "file_count": 2,
                "selected_files": 2,
                "sampled_files": 2,
                "sampled_rows": 20,
                "unselected_files_due_to_limit": 0,
                "issue_counts": {"ohlc_invariant_violation": 3},
                "columns": ["ts_code", "trade_date", "open", "high", "low", "close"],
                "examples": ["bad.csv"],
            },
            {
                "signature_rank": 3,
                "file_count": 1,
                "selected_files": 1,
                "sampled_files": 0,
                "sampled_rows": 0,
                "unselected_files_due_to_limit": 0,
                "issue_counts": {"no_sampled_rows": 1},
                "columns": ["ts_code"],
                "examples": ["empty.csv"],
            },
        ],
    }
    path = tmp_path / "dockcase.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = build_report(path)

    summary = report["summary"]
    assert summary["completion_status"] == "not_complete"
    assert summary["unselected_files_due_to_signature_file_limit"] == 98
    assert report["next_batches"]["p0_no_sampled_rows"][0]["signature_rank"] == 3
    assert report["next_batches"]["p1_high_issue_signatures"][0]["signature_rank"] == 2
    assert report["next_batches"]["p1_high_volume_unselected_files"][0]["signature_rank"] == 1
