"""Tests for mvp20.history: Parquet minute archive + DuckDB query + compact."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")
pytest.importorskip("duckdb")

from mvp20.history import (  # noqa: E402
    append_minute_parquet,
    compact_date,
    query_history,
)


@pytest.fixture()
def history_dir(tmp_path: Path) -> Path:
    return tmp_path / "history"


def test_append_creates_minute_partition(history_dir: Path) -> None:
    now = int(time.time())
    batch = [
        ("300750.SZ", "L7.flow.netbuy", {"scalar": 1.0}, "Known", 0.8, "tushare", now),
        ("300750.SZ", "L7.trade.iv", {"scalar": 0.35}, "Known", 0.7, "futu", now),
    ]
    out = append_minute_parquet(history_dir, batch)
    assert out.exists()
    assert out.suffix == ".parquet"
    assert "partition_minute=" in out.name

    # Verify schema + row count
    table = pq.read_table(out)
    assert table.num_rows == 2
    assert set(table.column_names) == {
        "ts_code", "dp_id", "value_json", "data_status",
        "confidence", "source", "updated_at",
    }


def test_append_same_minute_concatenates(history_dir: Path) -> None:
    now = int(time.time())
    append_minute_parquet(history_dir, [
        ("X.SH", "dp1", {"v": 1}, "Known", None, "src", now),
    ])
    append_minute_parquet(history_dir, [
        ("X.SH", "dp2", {"v": 2}, "Known", None, "src", now),
    ])
    minute_files = list((history_dir / "minute").glob("*.parquet"))
    assert len(minute_files) == 1  # same minute → one file
    table = pq.read_table(minute_files[0])
    assert table.num_rows == 2


def test_query_history_returns_time_ordered_points(history_dir: Path) -> None:
    base = int(time.time()) - 100
    # Insert across two minute buckets
    append_minute_parquet(history_dir, [
        ("X.SH", "L7.flow.netbuy", {"scalar": 1.0}, "Known", 0.5, "src", base),
    ])
    # Small sleep to ensure different minute key
    time.sleep(0.01)
    append_minute_parquet(history_dir, [
        ("X.SH", "L7.flow.netbuy", {"scalar": 2.0}, "Known", 0.5, "src", base + 60),
    ])

    points = query_history(history_dir, "X.SH", "L7.flow.netbuy",
                           since_unix=base - 10, until_unix=base + 120)
    assert len(points) == 2
    # Time-ordered
    assert points[0]["updated_at"] < points[1]["updated_at"]
    assert points[0]["value"] == {"scalar": 1.0}
    assert points[1]["value"] == {"scalar": 2.0}


def test_query_history_empty_when_no_files(history_dir: Path) -> None:
    assert query_history(history_dir, "X.SH", "dp1", 0, None) == []


def test_query_history_respects_since_until(history_dir: Path) -> None:
    base = int(time.time()) - 1000
    append_minute_parquet(history_dir, [
        ("X.SH", "dp1", {"v": 1}, "Known", None, "src", base),
        ("X.SH", "dp1", {"v": 2}, "Known", None, "src", base + 500),
        ("X.SH", "dp1", {"v": 3}, "Known", None, "src", base + 900),
    ])
    points = query_history(history_dir, "X.SH", "dp1",
                           since_unix=base + 100, until_unix=base + 600)
    assert len(points) == 1
    assert points[0]["value"] == {"v": 2}


def test_compact_date_merges_minute_files(history_dir: Path) -> None:
    # Create three minute files for "today" by directly writing parquet with
    # fixed names — bypass real datetime to make this test deterministic.
    minute_dir = history_dir / "minute"
    minute_dir.mkdir(parents=True)
    base = int(time.time())
    for i in range(3):
        table = pa.table({
            "ts_code": ["X.SH"], "dp_id": [f"dp{i}"],
            "value_json": [f'{{"v": {i}}}'], "data_status": ["Known"],
            "confidence": [0.5], "source": ["src"],
            "updated_at": [base + i],
        })
        pq.write_table(table, minute_dir / f"partition_minute=20260101_120{i}.parquet")

    out = compact_date(history_dir, "20260101", delete_source=True)
    assert out is not None
    assert out.exists()
    assert out.name == "date=2026-01-01.parquet"

    # All 3 rows present, source files removed
    table = pq.read_table(out)
    assert table.num_rows == 3
    remaining = list(minute_dir.glob("partition_minute=20260101_*.parquet"))
    assert remaining == []


def test_compact_date_no_op_when_no_source(history_dir: Path) -> None:
    out = compact_date(history_dir, "20260101")
    assert out is None
