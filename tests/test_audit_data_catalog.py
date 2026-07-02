import sqlite3
from pathlib import Path

from scripts import audit_data_catalog


def test_data_catalog_reads_csv_headers_and_prunes(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.csv").write_text("ts_code,trade_date,close\n000001.SZ,20260101,1\n",
                                encoding="utf-8")
    (root / "b.csv").write_text("ts_code,trade_date,close\n000002.SZ,20260101,2\n",
                                encoding="utf-8")
    ignored = root / "_workspace" / ".venv"
    ignored.mkdir(parents=True)
    (ignored / "ignored.csv").write_text("bad\n1\n", encoding="utf-8")

    catalog = audit_data_catalog.scan_root(
        root,
        prunes=("_workspace/.venv",),
        csv_header_limit=0,
        csv_row_sample_limit=2,
        sample_limit=5,
        max_header_bytes=1024,
        max_json_bytes=1024,
        max_html_bytes=1024,
        sqlite_table_limit=5,
    )
    data = audit_data_catalog._catalog_json(catalog, top_headers=5)

    assert data["csv_files"] == 2
    assert data["csv_headers_read"] == 2
    assert data["csv_data_rows_sampled"] == 2
    assert data["csv_row_width_mismatch_count"] == 0
    assert data["csv_header_signature_count"] == 1
    assert data["csv_header_signatures"][0]["count"] == 2
    assert data["csv_header_signatures"][0]["columns"] == [
        "ts_code", "trade_date", "close",
    ]
    assert data["csv_header_signatures"][0]["sample_rows"][0]["values"] == {
        "ts_code": "000001.SZ",
        "trade_date": "20260101",
        "close": "1",
    }


def test_data_catalog_detects_sampled_csv_row_width_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    (root / "bad.csv").write_text("a,b,c\n1,2\n", encoding="utf-8")

    catalog = audit_data_catalog.scan_root(
        root,
        prunes=(),
        csv_header_limit=0,
        csv_row_sample_limit=1,
        sample_limit=5,
        max_header_bytes=1024,
        max_json_bytes=1024,
        max_html_bytes=1024,
        sqlite_table_limit=5,
    )
    data = audit_data_catalog._catalog_json(catalog, top_headers=5)

    assert data["csv_data_rows_sampled"] == 1
    assert data["csv_row_width_mismatch_count"] == 1
    assert data["csv_row_width_mismatch_examples"] == [
        {"path": "bad.csv", "column_count": 3, "row_width": 2},
    ]
    assert data["csv_header_signatures"][0]["row_width_mismatch_count"] == 1


def test_data_catalog_counts_header_only_csv_files(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    (root / "empty.csv").write_text("a,b,c\n", encoding="utf-8")

    catalog = audit_data_catalog.scan_root(
        root,
        prunes=(),
        csv_header_limit=0,
        csv_row_sample_limit=1,
        sample_limit=5,
        max_header_bytes=1024,
        max_json_bytes=1024,
        max_html_bytes=1024,
        sqlite_table_limit=5,
    )
    data = audit_data_catalog._catalog_json(catalog, top_headers=5)

    assert data["csv_headers_read"] == 1
    assert data["csv_data_rows_sampled"] == 0
    assert data["csv_files_without_sampled_data_row"] == 1
    assert data["csv_files_without_sampled_data_row_examples"] == ["empty.csv"]


def test_data_catalog_reads_sqlite_schema(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    db = root / "sample.sqlite"
    con = sqlite3.connect(db)
    try:
        con.execute("create table scores(ts_code text primary key, score real)")
        con.commit()
    finally:
        con.close()

    catalog = audit_data_catalog.scan_root(
        root,
        prunes=(),
        csv_header_limit=0,
        csv_row_sample_limit=1,
        sample_limit=5,
        max_header_bytes=1024,
        max_json_bytes=1024,
        max_html_bytes=1024,
        sqlite_table_limit=5,
    )
    data = audit_data_catalog._catalog_json(catalog, top_headers=5)

    assert data["sqlite_files"] == 1
    assert data["sqlite_schema_error_count"] == 0
    assert data["sqlite_schemas"][0]["table_count"] == 1
    assert data["sqlite_schemas"][0]["tables"][0]["table"] == "scores"
