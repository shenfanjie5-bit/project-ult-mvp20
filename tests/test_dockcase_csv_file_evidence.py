from pathlib import Path

from scripts import audit_dockcase_csv_file_evidence


def test_dockcase_csv_file_evidence_records_every_business_csv(tmp_path: Path) -> None:
    root = tmp_path / "database_all"
    root.mkdir()
    (root / "daily.csv").write_text(
        "ts_code,trade_date,close\n"
        "000001.SZ,20260101,10\n"
        "000001.SZ,20260102,11\n",
        encoding="utf-8",
    )
    (root / "header_only.csv").write_text(
        "ts_code,trade_date,close\n",
        encoding="utf-8",
    )
    (root / "width_mismatch.csv").write_text(
        "ts_code,trade_date,close\n"
        "000002.SZ,20260101,10\n"
        "000002.SZ,20260102,11,extra\n",
        encoding="utf-8",
    )
    (root / "._daily.csv").write_bytes(b"\x00\x05\x16\x07Mac OS X resource fork")

    report = audit_dockcase_csv_file_evidence.build_report(
        root,
        sample_bytes=256,
        prunes=(),
    )

    summary = report["summary"]
    assert summary["csv_files_seen"] == 3
    assert summary["file_evidence_count"] == 3
    assert summary["all_seen_files_have_evidence_rows"] is True
    assert summary["all_seen_files_have_head_tail_fingerprint"] is True
    assert summary["header_read_error_count"] == 0
    assert summary["files_with_data_row_evidence"] == 2
    assert summary["header_only_or_no_tail_data_files"] == 1
    assert summary["first_tail_width_mismatch_count"] == 1
    assert summary["coverage_boundary"] == {
        "all_business_csv_files_have_file_evidence": True,
        "full_row_semantic_scan": False,
        "tail_row_is_derived_from_tail_byte_sample": True,
    }

    by_path = {row["path"]: row for row in report["file_evidence"]}
    assert set(by_path) == {"daily.csv", "header_only.csv", "width_mismatch.csv"}
    assert by_path["daily.csv"]["data_row_evidence"] == "header_first_tail"
    assert by_path["header_only.csv"]["data_row_evidence"] == "header_only_or_empty"
    assert by_path["width_mismatch.csv"]["first_tail_width_mismatch"] is True
    assert all(row["head_tail_sha256"] for row in by_path.values())


def test_dockcase_csv_file_evidence_writes_markdown(tmp_path: Path) -> None:
    report = {
        "generated_at": "2026-06-19T00:00:00+0800",
        "elapsed_s": 1.0,
        "data_root": "/tmp/database_all",
        "scan_mode": "all_business_csv_file_evidence",
        "summary": {
            "csv_files_seen": 1,
            "file_evidence_count": 1,
            "signature_count": 1,
            "header_read_error_count": 0,
            "fingerprint_error_count": 0,
            "files_with_data_row_evidence": 1,
            "first_tail_width_mismatch_count": 0,
            "top_column_counts": [{"column_count": 3, "files": 1}],
            "top_header_signatures": [{"header_signature_sha256": "abc", "files": 1}],
        },
    }
    out = tmp_path / "evidence.md"

    audit_dockcase_csv_file_evidence.write_markdown(report, out)

    text = out.read_text(encoding="utf-8")
    assert "DOCKCASE CSV file evidence audit" in text
    assert "Every business CSV gets a file-level evidence row" in text
    assert "`abc`" in text
