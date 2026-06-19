import json
from pathlib import Path

from scripts.audit_dockcase_backlog_batch import build_report


def _write_csv(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_backlog_batch_matches_signature_and_samples_rows(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "signatures": [
                    {
                        "signature_rank": 46,
                        "columns": ["ts_code", "trade_date", "open", "close", "high", "low"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    data_root = tmp_path / "database_all"
    header = "ts_code,trade_date,open,close,high,low\n"
    _write_csv(
        data_root / "指数专题/国际主要指数/by_symbol/000001.SH+a.csv",
        header + "000001.SH,20260618,10,11,12,9\n000001.SH,20260619,10,13,9,8\n",
    )
    _write_csv(
        data_root / "指数专题/国际主要指数/by_symbol/000002.SH+b.csv",
        header + "000002.SH,20260618,10,10,10,10\n",
    )
    _write_csv(
        data_root / "other.csv",
        "x,y\n1,2\n",
    )

    report = build_report(
        source,
        data_root,
        ranks={46},
        max_files_per_signature=10,
        rows_per_file=10,
        as_of_date=__import__("datetime").date(2026, 6, 19),
    )

    assert report["summary"]["matched_files"] == 2
    assert report["summary"]["sampled_files"] == 2
    assert report["summary"]["sampled_rows"] == 3
    assert report["summary"]["issue_counts"]["ohlc_invariant_violation"] == 1
    row = report["signatures"][0]
    assert row["target_signature_rank"] == 46
    assert row["matched_files"] == 2


def test_backlog_batch_reports_header_only_signature(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "signatures": [
                    {
                        "signature_rank": 121,
                        "columns": ["group", "api", "label", "path", "normalized_path", "rate_limit"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    data_root = tmp_path / "database_all"
    _write_csv(
        data_root / "_workspace/_meta/manifests/master_dictionary_index.csv",
        "group,api,label,path,normalized_path,rate_limit\n",
    )

    report = build_report(
        source,
        data_root,
        ranks={121},
        max_files_per_signature=10,
        rows_per_file=10,
        as_of_date=__import__("datetime").date(2026, 6, 19),
    )

    assert report["summary"]["matched_files"] == 1
    assert report["summary"]["sampled_files"] == 0
    assert report["summary"]["sampled_rows"] == 0
    row = report["signatures"][0]
    assert row["target_signature_rank"] == 121
    assert row["columns"] == ["group", "api", "label", "path", "normalized_path", "rate_limit"]
