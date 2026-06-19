import json
from pathlib import Path

from scripts import audit_dockcase_csv_full_scan_progress as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _shard(skip: int, files: int, rows: int, issue_counts: dict | None = None) -> dict:
    return {
        "generated_at": "2026-06-19T00:00:00+0800",
        "elapsed_s": 1.0,
        "parameters": {"skip_files": skip, "max_files": files},
        "summary": {
            "csv_files_seen": files,
            "total_bytes": files * 100,
            "rows_scanned": rows,
            "total_cells": rows * 3,
            "empty_cells": rows,
            "header_read_error_count": 0,
            "row_read_error_count": 0,
            "row_width_mismatch_count": 0,
            "date_invalid_count": issue_counts.get("invalid_date", 0) if issue_counts else 0,
            "numeric_invalid_count": 0,
            "ts_code_invalid_count": 0,
            "issue_counts": issue_counts or {},
            "domain_issue_counts": {},
            "coverage_boundary": {
                "skip_files": skip,
                "max_files_limit": files,
                "full_row_semantic_scan": False,
            },
        },
        "top_issue_files": [
            {
                "path": f"{skip}.csv",
                "rows_scanned": rows,
                "issue_total": sum((issue_counts or {}).values()),
                "issue_counts": issue_counts or {},
            }
        ],
    }


def test_full_scan_progress_merges_contiguous_shards(tmp_path: Path) -> None:
    evidence = tmp_path / "dockcase_csv_file_evidence_2026-06-19.json"
    shard_a = tmp_path / "dockcase_csv_full_scan_2026-06-19.json"
    shard_b = tmp_path / "dockcase_csv_full_scan_shard_000200_000399.json"
    _write_json(evidence, {"summary": {"csv_files_seen": 1000}})
    _write_json(shard_a, _shard(0, 200, 1000, {"invalid_date": 2}))
    _write_json(shard_b, _shard(200, 200, 1500, {"ohlc_invariant_violation": 1}))

    report = audit.build_report([shard_a, shard_b], file_evidence_path=evidence)

    summary = report["summary"]
    assert summary["shard_count"] == 2
    assert summary["total_business_csv_files"] == 1000
    assert summary["csv_files_scanned"] == 400
    assert summary["coverage_ratio_of_business_csv_files"] == 0.4
    assert summary["rows_scanned"] == 2500
    assert summary["issue_counts"] == {
        "invalid_date": 2,
        "ohlc_invariant_violation": 1,
    }
    assert summary["range_overlap_count"] == 0
    assert summary["range_gap_count"] == 0
    assert summary["full_row_semantic_scan_complete"] is False


def test_full_scan_progress_detects_gaps_and_overlaps(tmp_path: Path) -> None:
    evidence = tmp_path / "dockcase_csv_file_evidence_2026-06-19.json"
    shard_a = tmp_path / "a.json"
    shard_b = tmp_path / "b.json"
    shard_c = tmp_path / "c.json"
    _write_json(evidence, {"summary": {"csv_files_seen": 1000}})
    _write_json(shard_a, _shard(0, 100, 100))
    _write_json(shard_b, _shard(90, 10, 10))
    _write_json(shard_c, _shard(150, 10, 10))

    report = audit.build_report([shard_a, shard_b, shard_c], file_evidence_path=evidence)

    assert report["summary"]["range_overlap_count"] == 1
    assert report["summary"]["range_gap_count"] == 1
    assert report["range_overlaps"][0]["overlap_count"] == 10
    assert report["range_gaps"][0]["missing_count"] == 50


def test_full_scan_progress_writes_markdown(tmp_path: Path) -> None:
    report = {
        "generated_at": "2026-06-19T00:00:00+0800",
        "summary": {
            "shard_count": 1,
            "csv_files_scanned": 200,
            "total_business_csv_files": 1000,
            "coverage_ratio_of_business_csv_files": 0.2,
            "rows_scanned": 123,
            "row_read_error_count": 0,
            "full_row_semantic_scan_complete": False,
            "issue_counts": {"invalid_date": 1},
        },
        "shards": [
            {
                "start_file_index": 0,
                "end_file_index": 199,
                "files_seen": 200,
                "rows_scanned": 123,
                "path": "shard.json",
            }
        ],
        "top_issue_files": [
            {"path": "bad.csv", "issue_total": 1, "source_shard": "shard.json"}
        ],
    }
    out = tmp_path / "progress.md"

    audit.write_markdown(report, out)

    text = out.read_text(encoding="utf-8")
    assert "DOCKCASE CSV full-row scan progress" in text
    assert "`invalid_date`: 1" in text
    assert "`0-199`" in text
