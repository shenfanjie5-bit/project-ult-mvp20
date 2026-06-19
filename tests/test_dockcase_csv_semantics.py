import json
import datetime as dt
from pathlib import Path

from scripts import audit_dockcase_csv_semantics


def test_dockcase_csv_semantics_samples_by_header_signature(tmp_path: Path) -> None:
    root = tmp_path / "database_all"
    root.mkdir()
    (root / "daily_a.csv").write_text(
        "ts_code,trade_date,close,amount,name\n"
        "000001.SZ,20260101,10.5,1000,平安银行\n"
        "000002.SZ,20260102,11.5,1200,万科A\n",
        encoding="utf-8",
    )
    (root / "daily_b.csv").write_text(
        "ts_code,trade_date,close,amount,name\n"
        "000003.SZ,20260103,12.5,1300,招商银行\n",
        encoding="utf-8",
    )
    (root / "finance.csv").write_text(
        "ts_code,ann_date,revenue,profit\n"
        "000001.SZ,20260431,not-number,20\n"
        "bad-code,20260101,100,30\n",
        encoding="utf-8",
    )

    report = audit_dockcase_csv_semantics.scan_csv_semantics(
        root,
        files_per_signature=2,
        rows_per_file=10,
        prunes=(),
        as_of_date=dt.date(2026, 1, 4),
    )

    assert report["exists"] is True
    assert report["summary"]["csv_files_seen"] == 3
    assert report["summary"]["signature_count"] == 2
    assert report["summary"]["selected_signature_count"] == 2
    assert report["summary"]["sampled_signature_count"] == 2
    assert report["summary"]["selected_files"] == 3
    assert report["summary"]["sampled_files"] == 3
    assert report["summary"]["sampled_rows"] == 5
    assert report["summary"]["coverage_gaps"] == {
        "header_read_error_files": 0,
        "unsampled_signatures": 0,
        "signatures_selected_but_no_sampled_rows": 0,
        "csv_files_not_selected_for_row_sampling": 0,
        "csv_files_selected_but_no_sampled_rows": 0,
        "bounded_row_sampling": True,
    }
    assert report["summary"]["sampling_coverage"] == {
        "sampled_signature_ratio": 1.0,
        "selected_file_ratio_of_grouped_csv": 1.0,
        "sampled_file_ratio_of_grouped_csv": 1.0,
        "sampled_rows_per_sampled_file": 1.67,
    }

    by_columns = {tuple(row["columns"]): row for row in report["signatures"]}
    daily = by_columns[("ts_code", "trade_date", "close", "amount", "name")]
    assert daily["file_count"] == 2
    assert daily["selected_files"] == 2
    assert daily["sampled_rows"] == 3
    assert daily["issue_counts"] == {}
    assert daily["column_profiles"]["date"][0]["min"] == "2026-01-01"
    assert daily["column_profiles"]["numeric"][0]["column"] == "close"

    finance = by_columns[("ts_code", "ann_date", "revenue", "profit")]
    assert finance["issue_counts"]["invalid_date"] == 1
    assert finance["issue_counts"]["invalid_ts_code"] == 1
    assert finance["issue_counts"]["invalid_numeric"] == 1


def test_dockcase_csv_semantics_reports_sampling_limits(tmp_path: Path) -> None:
    root = tmp_path / "database_all"
    root.mkdir()
    for idx in range(4):
        (root / f"daily_{idx}.csv").write_text(
            "ts_code,trade_date,close\n"
            f"00000{idx}.SZ,20260101,{10 + idx}\n",
            encoding="utf-8",
        )

    report = audit_dockcase_csv_semantics.scan_csv_semantics(
        root,
        files_per_signature=1,
        rows_per_file=10,
        prunes=(),
        as_of_date=dt.date(2026, 1, 2),
    )

    summary = report["summary"]
    assert summary["csv_files_seen"] == 4
    assert summary["signature_count"] == 1
    assert summary["selected_files"] == 1
    assert summary["sampled_files"] == 1
    assert summary["unselected_files_due_to_signature_file_limit"] == 3
    assert summary["coverage_gaps"]["csv_files_not_selected_for_row_sampling"] == 3
    assert summary["sampling_coverage"]["selected_file_ratio_of_grouped_csv"] == 0.25
    assert summary["sampling_coverage"]["sampled_file_ratio_of_grouped_csv"] == 0.25
    assert summary["high_file_count_sampling_limits"][0][
        "unselected_files_due_to_limit"
    ] == 3
    signature = report["signatures"][0]
    assert signature["selected_files"] == 1
    assert signature["unselected_files_due_to_limit"] == 3


def test_dockcase_csv_semantics_skips_appledouble_sidecars(tmp_path: Path) -> None:
    root = tmp_path / "database_all"
    root.mkdir()
    (root / "daily.csv").write_text(
        "ts_code,trade_date,close\n000001.SZ,20260101,10\n",
        encoding="utf-8",
    )
    (root / "._daily.csv").write_bytes(b"\x00\x05\x16\x07Mac OS X resource fork")

    report = audit_dockcase_csv_semantics.scan_csv_semantics(
        root,
        files_per_signature=2,
        rows_per_file=10,
        prunes=(),
        as_of_date=dt.date(2026, 1, 2),
    )

    assert report["summary"]["csv_files_seen"] == 1
    assert report["summary"]["signature_count"] == 1
    assert report["signatures"][0]["examples"] == ["daily.csv"]


def test_dockcase_csv_semantics_detects_width_and_sparse_columns(tmp_path: Path) -> None:
    root = tmp_path / "database_all"
    root.mkdir()
    (root / "bad.csv").write_text(
        "ts_code,trade_date,value,mostly_empty\n"
        "000001.SZ,20260101,1,\n"
        "000002.SZ,20260102\n",
        encoding="utf-8",
    )

    report = audit_dockcase_csv_semantics.scan_csv_semantics(
        root,
        files_per_signature=1,
        rows_per_file=10,
        prunes=(),
    )

    signature = report["signatures"][0]
    assert signature["row_width_mismatch_count"] == 1
    assert signature["issue_counts"]["row_width_mismatch"] == 1
    assert signature["issue_counts"]["sparse_columns_lt_5pct_non_empty"] == 1


def test_dockcase_csv_semantics_uses_head_tail_sampling(tmp_path: Path) -> None:
    root = tmp_path / "database_all"
    root.mkdir()
    rows = [
        f"000001.SZ,202601{day:02d},{10 + day}\n"
        for day in range(1, 11)
    ]
    (root / "history.csv").write_text(
        "ts_code,trade_date,close\n" + "".join(rows),
        encoding="utf-8",
    )

    report = audit_dockcase_csv_semantics.scan_csv_semantics(
        root,
        files_per_signature=1,
        rows_per_file=4,
        prunes=(),
        as_of_date=dt.date(2026, 1, 11),
    )

    signature = report["signatures"][0]
    date_profile = signature["column_profiles"]["date"][0]
    assert signature["sampled_rows"] == 4
    assert date_profile["min"] == "2026-01-01"
    assert date_profile["max"] == "2026-01-10"
    assert signature["freshness"]["lag_days"] == 1


def test_dockcase_csv_semantics_detects_domain_invariants(tmp_path: Path) -> None:
    root = tmp_path / "database_all" / "股票数据" / "行情数据" / "历史日线" / "by_symbol"
    root.mkdir(parents=True)
    (root / "000001.SZ+平安银行.csv").write_text(
        "ts_code,trade_date,open,high,low,close\n"
        "000002.SZ,20260101,10,9,8,11\n"
        "000002.SZ,20260101,10,12,9,11\n",
        encoding="utf-8",
    )

    report = audit_dockcase_csv_semantics.scan_csv_semantics(
        tmp_path / "database_all",
        files_per_signature=1,
        rows_per_file=10,
        prunes=(),
        as_of_date=dt.date(2026, 1, 2),
    )

    signature = report["signatures"][0]
    assert signature["issue_counts"]["by_symbol_code_mismatch"] == 2
    assert signature["issue_counts"]["ohlc_invariant_violation"] == 1
    assert signature["issue_counts"]["duplicate_grain_key_sample"] == 1
    assert signature["domain_issue_examples_by_code"]["ohlc_invariant_violation"] == [
        {
            "issue": "ohlc_invariant_violation",
            "path": "股票数据/行情数据/历史日线/by_symbol/000001.SZ+平安银行.csv",
            "open": 10.0,
            "high": 9.0,
            "low": 8.0,
            "close": 11.0,
        }
    ]
    assert report["summary"]["domain_issue_counts"] == {
        "by_symbol_code_mismatch": 2,
        "ohlc_invariant_violation": 1,
        "duplicate_grain_key_sample": 1,
    }


def test_dockcase_csv_semantics_classifies_zero_ohlc_no_trade_rows(tmp_path: Path) -> None:
    root = tmp_path / "database_all" / "股票数据" / "行情数据" / "备用行情" / "by_symbol"
    root.mkdir(parents=True)
    (root / "000002.SZ+万科A.csv").write_text(
        "ts_code,trade_date,open,high,low,close,pre_close,change,pct_change,vol,amount\n"
        "000002.SZ,20170717,0,0,0,24.59,24.59,0,0,0,0\n",
        encoding="utf-8",
    )

    report = audit_dockcase_csv_semantics.scan_csv_semantics(
        tmp_path / "database_all",
        files_per_signature=1,
        rows_per_file=10,
        prunes=(),
        as_of_date=dt.date(2026, 1, 2),
    )

    signature = report["signatures"][0]
    assert "ohlc_invariant_violation" not in signature["issue_counts"]
    assert signature["issue_counts"]["zero_ohlc_no_trade_carry_forward"] == 1
    assert signature["domain_issue_examples_by_code"]["zero_ohlc_no_trade_carry_forward"] == [
        {
            "issue": "zero_ohlc_no_trade_carry_forward",
            "path": "股票数据/行情数据/备用行情/by_symbol/000002.SZ+万科A.csv",
            "open": 0.0,
            "high": 0.0,
            "low": 0.0,
            "close": 24.59,
        }
    ]
    assert report["summary"]["domain_issue_counts"] == {
        "zero_ohlc_no_trade_carry_forward": 1,
    }


def test_dockcase_csv_semantics_classifies_index_bundle_mismatch(tmp_path: Path) -> None:
    root = (
        tmp_path
        / "database_all"
        / "指数专题"
        / "申万行业指数日行情"
        / "by_symbol"
    )
    root.mkdir(parents=True)
    (root / "114701.MI+MSCI中国_食品饮料与烟草.csv").write_text(
        "ts_code,trade_date,open,high,low,close\n"
        "859951.SI,20260101,10,12,9,11\n",
        encoding="utf-8",
    )

    report = audit_dockcase_csv_semantics.scan_csv_semantics(
        tmp_path / "database_all",
        files_per_signature=1,
        rows_per_file=10,
        prunes=(),
        as_of_date=dt.date(2026, 1, 2),
    )

    signature = report["signatures"][0]
    assert "by_symbol_code_mismatch" not in signature["issue_counts"]
    assert signature["issue_counts"]["index_by_symbol_bundle_mismatch"] == 1
    assert report["summary"]["domain_issue_counts"] == {
        "index_by_symbol_bundle_mismatch": 1,
    }


def test_dockcase_csv_semantics_dedupes_grain_within_file_only(tmp_path: Path) -> None:
    root = tmp_path / "database_all"
    root.mkdir()
    (root / "a.csv").write_text(
        "ts_code,trade_date,close\n"
        "000001.SZ,20260101,1\n"
        "000001.SZ,20260101,2\n",
        encoding="utf-8",
    )
    (root / "b.csv").write_text(
        "ts_code,trade_date,close\n"
        "000001.SZ,20260101,3\n",
        encoding="utf-8",
    )

    report = audit_dockcase_csv_semantics.scan_csv_semantics(
        root,
        files_per_signature=2,
        rows_per_file=10,
        prunes=(),
        as_of_date=dt.date(2026, 1, 2),
    )

    signature = report["signatures"][0]
    assert signature["issue_counts"]["duplicate_grain_key_sample"] == 1
    assert signature["domain_issue_examples"] == [
        {
            "issue": "duplicate_grain_key_sample",
            "path": "a.csv",
            "key_columns": ["ts_code", "trade_date"],
            "key_values": ["000001.SZ", "20260101"],
        }
    ]


def test_dockcase_csv_semantics_uses_event_specific_grain(tmp_path: Path) -> None:
    root = tmp_path / "database_all"
    root.mkdir()
    (root / "holders.csv").write_text(
        "ts_code,ann_date,holder_name,change_vol,after_share\n"
        "000001.SZ,20260101,A,100,1000\n"
        "000001.SZ,20260101,A,200,1200\n",
        encoding="utf-8",
    )

    report = audit_dockcase_csv_semantics.scan_csv_semantics(
        root,
        files_per_signature=1,
        rows_per_file=10,
        prunes=(),
        as_of_date=dt.date(2026, 1, 2),
    )

    signature = report["signatures"][0]
    assert "duplicate_grain_key_sample" not in signature["issue_counts"]


def test_dockcase_csv_semantics_writes_markdown(tmp_path: Path) -> None:
    report = {
        "generated_at": "2026-06-18T00:00:00+0800",
        "elapsed_s": 1.2,
        "data_root": "/tmp/database_all",
        "scan_mode": "header_signature_stratified_bounded_row_semantics",
        "summary": {
            "csv_files_seen": 1,
            "files_grouped_by_signature": 1,
            "signature_count": 1,
            "selected_signature_count": 1,
            "sampled_signature_count": 1,
            "selected_files": 1,
            "sampled_files": 1,
            "sampled_rows": 2,
            "header_read_error_count": 0,
            "sampling_coverage": {
                "sampled_signature_ratio": 1.0,
                "selected_file_ratio_of_grouped_csv": 1.0,
                "sampled_file_ratio_of_grouped_csv": 1.0,
                "sampled_rows_per_sampled_file": 2.0,
            },
            "coverage_gaps": {
                "header_read_error_files": 0,
                "unsampled_signatures": 0,
                "signatures_selected_but_no_sampled_rows": 0,
                "csv_files_not_selected_for_row_sampling": 0,
                "csv_files_selected_but_no_sampled_rows": 0,
                "bounded_row_sampling": True,
            },
            "issue_counts": {},
            "domain_issue_counts": {},
            "high_issue_signatures": [],
            "high_file_count_sampling_limits": [],
            "no_sampled_row_signatures": [],
        },
        "parameters": {"sample_strategy": "head_tail", "as_of_date": "2026-06-18"},
        "signatures": [
            {
                "signature_rank": 1,
                "file_count": 1,
                "selected_files": 1,
                "sampled_files": 1,
                "sampled_rows": 2,
                "empty_cell_ratio": 0.0,
                "issue_counts": {},
                "columns": ["ts_code", "trade_date", "close"],
                "examples": ["daily.csv"],
            }
        ],
    }
    out = tmp_path / "report.md"

    audit_dockcase_csv_semantics.write_markdown(json.loads(json.dumps(report)), out)

    text = out.read_text(encoding="utf-8")
    assert "DOCKCASE CSV stratified semantic audit" in text
    assert "Sampled files / rows" in text
    assert "Domain Issue Counts" in text
    assert "`daily.csv`" in text
