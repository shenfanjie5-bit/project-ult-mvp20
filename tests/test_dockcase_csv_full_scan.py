import datetime as dt
import gzip
import json
from pathlib import Path

from scripts import audit_dockcase_csv_full_scan as audit


def _jsonl_rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_dockcase_csv_full_scan_reads_all_rows_and_writes_jsonl(tmp_path: Path) -> None:
    root = tmp_path / "database_all"
    root.mkdir()
    (root / "daily.csv").write_text(
        "ts_code,trade_date,open,high,low,close,amount\n"
        "000001.SZ,20260101,10,11,9,10.5,100\n"
        "000001.SZ,20260102,10,9,8,11,200\n"
        "bad-code,20260132,10,11,9,not-number,abc\n",
        encoding="utf-8",
    )
    (root / "header_only.csv").write_text("ts_code,trade_date,close\n", encoding="utf-8")
    (root / "._daily.csv").write_bytes(b"\x00\x05\x16\x07Mac OS X resource fork")
    evidence = tmp_path / "full.jsonl.gz"

    report = audit.build_report(
        root,
        evidence_jsonl_gz=evidence,
        max_files=None,
        prunes=(),
        as_of_date=dt.date(2026, 1, 3),
    )

    summary = report["summary"]
    assert summary["csv_files_seen"] == 2
    assert summary["rows_scanned"] == 3
    assert summary["full_row_semantic_scan"] is True
    assert summary["coverage_boundary"] == {
        "all_business_csv_files_selected": True,
        "all_selected_files_read_to_eof": True,
        "full_row_semantic_scan": True,
        "max_files_limit": None,
        "skip_files": 0,
    }
    assert summary["issue_counts"]["invalid_date"] == 1
    assert summary["issue_counts"]["invalid_numeric"] >= 1
    assert summary["issue_counts"]["invalid_ts_code"] == 1
    assert summary["issue_counts"]["ohlc_invariant_violation"] == 1
    assert summary["issue_counts"]["no_sampled_rows"] == 1

    rows = _jsonl_rows(evidence)
    by_path = {row["path"]: row for row in rows}
    assert set(by_path) == {"daily.csv", "header_only.csv"}
    assert by_path["daily.csv"]["rows_scanned"] == 3
    assert by_path["daily.csv"]["date_invalid_count"] == 1
    assert by_path["daily.csv"]["ts_code_invalid_count"] == 1
    assert by_path["header_only.csv"]["rows_scanned"] == 0


def test_dockcase_csv_full_scan_respects_max_files_boundary(tmp_path: Path) -> None:
    root = tmp_path / "database_all"
    root.mkdir()
    for idx in range(3):
        (root / f"{idx}.csv").write_text(
            "ts_code,trade_date,close\n"
            f"00000{idx}.SZ,20260101,{10 + idx}\n",
            encoding="utf-8",
        )
    evidence = tmp_path / "limited.jsonl.gz"

    report = audit.build_report(
        root,
        evidence_jsonl_gz=evidence,
        skip_files=1,
        max_files=2,
        prunes=(),
        as_of_date=dt.date(2026, 1, 2),
    )

    assert report["summary"]["csv_files_seen"] == 2
    assert report["summary"]["rows_scanned"] == 2
    assert report["summary"]["full_row_semantic_scan"] is False
    assert report["summary"]["coverage_boundary"]["max_files_limit"] == 2
    assert report["summary"]["coverage_boundary"]["skip_files"] == 1
    rows = _jsonl_rows(evidence)
    assert len(rows) == 2
    assert "0.csv" not in {row["path"] for row in rows}


def test_dockcase_csv_full_scan_writes_markdown(tmp_path: Path) -> None:
    report = {
        "generated_at": "2026-06-19T00:00:00+0800",
        "elapsed_s": 1.0,
        "data_root": "/tmp/database_all",
        "scan_mode": "all_selected_business_csv_full_row_semantics",
        "summary": {
            "csv_files_seen": 1,
            "rows_scanned": 2,
            "signature_count": 1,
            "header_read_error_count": 0,
            "row_read_error_count": 0,
            "full_row_semantic_scan": True,
            "coverage_boundary": {
                "all_business_csv_files_selected": True,
                "all_selected_files_read_to_eof": True,
                "full_row_semantic_scan": True,
                "max_files_limit": None,
                "skip_files": 0,
            },
            "issue_counts": {"invalid_date": 1},
            "domain_issue_counts": {},
        },
        "top_issue_files": [
            {
                "path": "daily.csv",
                "rows_scanned": 2,
                "issue_total": 1,
                "issue_counts": {"invalid_date": 1},
            }
        ],
        "top_header_signatures": [
            {
                "header_signature_sha256": "abc",
                "files": 1,
                "rows_scanned": 2,
                "issue_counts": {"invalid_date": 1},
            }
        ],
    }
    out = tmp_path / "full.md"

    audit.write_markdown(report, out)

    text = out.read_text(encoding="utf-8")
    assert "DOCKCASE CSV full-row semantic scan" in text
    assert "`invalid_date`: 1" in text
    assert "`daily.csv`" in text
