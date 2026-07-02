from pathlib import Path

import pandas as pd

from scripts.refresh_dockcase_a_share_eod import append_snapshot_row


def test_append_snapshot_row_appends_once_and_sorts_desc(tmp_path: Path) -> None:
    path = tmp_path / "000001.SZ+平安银行.csv"
    path.write_text(
        "ts_code,trade_date,close\n"
        "000001.SZ,20260623,10.1\n"
        "000001.SZ,20260621,9.9\n",
        encoding="utf-8",
    )

    result = append_snapshot_row(
        path=path,
        row={"ts_code": "000001.SZ", "trade_date": "20260624", "close": 10.3},
        key="trade_date",
        trade_date="20260624",
    )

    assert result.status == "appended"
    assert result.rows_added == 1
    out = pd.read_csv(path, dtype={"trade_date": str})
    assert out["trade_date"].tolist() == ["20260624", "20260623", "20260621"]

    duplicate = append_snapshot_row(
        path=path,
        row={"ts_code": "000001.SZ", "trade_date": "20260624", "close": 10.3},
        key="trade_date",
        trade_date="20260624",
    )
    assert duplicate.status == "already_current"
    out2 = pd.read_csv(path, dtype={"trade_date": str})
    assert len(out2) == 3


def test_append_snapshot_row_dry_run_does_not_write(tmp_path: Path) -> None:
    path = tmp_path / "000001.SZ+平安银行.csv"
    path.write_text(
        "ts_code,trade_date,close\n"
        "000001.SZ,20260623,10.1\n",
        encoding="utf-8",
    )

    result = append_snapshot_row(
        path=path,
        row={"ts_code": "000001.SZ", "trade_date": "20260624", "close": 10.3},
        key="trade_date",
        trade_date="20260624",
        dry_run=True,
    )

    assert result.status == "would_append"
    out = pd.read_csv(path, dtype={"trade_date": str})
    assert out["trade_date"].tolist() == ["20260623"]
