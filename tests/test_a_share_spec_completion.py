"""Tests for scripts/check_a_share_spec_completion.py."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_a_share_spec_completion",
        ROOT / "scripts" / "check_a_share_spec_completion.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


asc = _load_module()


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE realtime_current (
                ts_code TEXT NOT NULL,
                dp_id TEXT NOT NULL,
                value_json TEXT NOT NULL,
                data_status TEXT NOT NULL,
                confidence REAL,
                source TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (ts_code, dp_id)
            ) WITHOUT ROWID;

            CREATE TABLE overlay_manifest (
                ts_code TEXT NOT NULL,
                industry_id TEXT NOT NULL,
                overlay_path TEXT NOT NULL,
                period TEXT,
                primary_industry INTEGER NOT NULL DEFAULT 0,
                checksum TEXT,
                compiled_at INTEGER NOT NULL,
                PRIMARY KEY (ts_code, industry_id)
            ) WITHOUT ROWID;

            CREATE TABLE company_node_instance (
                ts_code TEXT NOT NULL,
                industry_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                dp_id TEXT,
                payload_json TEXT NOT NULL,
                data_status TEXT,
                required_level TEXT,
                missing_policy TEXT,
                calculation_type TEXT,
                aggregation_policy TEXT,
                materiality REAL,
                confidence REAL,
                source_overlay_path TEXT,
                PRIMARY KEY (ts_code, industry_id, node_id)
            ) WITHOUT ROWID;
            """
        )
        conn.executemany(
            """
            INSERT INTO realtime_current
            (ts_code, dp_id, value_json, data_status, confidence, source, updated_at)
            VALUES (?, ?, '{}', ?, 0.8, ?, 1)
            """,
            [
                ("000001.SZ", "L1.a", "Known", "tushare:test"),
                ("000001.SZ", "L2.b", "Inactive", "akshare:test"),
                ("000001.SZ", "L8.h", "Known", "mock:test"),
                ("00700.HK", "L3.c", "Known", "hk:test"),
                ("MARKET:CN", "L6.f", "Known", "tushare:macro"),
                ("INDUSTRY:TEST", "L7.g", "Known", "mock:industry"),
            ],
        )
        conn.execute(
            """
            INSERT INTO overlay_manifest
            (ts_code, industry_id, overlay_path, period, primary_industry, checksum, compiled_at)
            VALUES ('000001.SZ', 'TEST', 'x', '2026Q1', 1, 'abc', 1)
            """
        )
        conn.executemany(
            """
            INSERT INTO company_node_instance
            (
                ts_code, industry_id, node_id, dp_id, payload_json, data_status,
                required_level, missing_policy, calculation_type, aggregation_policy,
                materiality, confidence, source_overlay_path
            )
            VALUES (?, ?, ?, ?, '{}', ?, 'conditional_required',
                    'unknown_reduce_confidence', 'raw_value', 'none', NULL, 0.7, 'x')
            """,
            [
                ("000001.SZ", "TEST", "n1", "L3.c", "Known"),
                ("000001.SZ", "TEST", "n2", "L4.d", "Unknown"),
                ("000001.SZ", "TEST", "n3", "L5.e", "Optionality"),
                ("AAPL.US", "TEST", "n4", "L4.d", "Known"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def test_a_share_completion_combines_sqlite_and_overlay(tmp_path: Path) -> None:
    db = tmp_path / "hot.sqlite"
    _make_db(db)
    spec = {
        "L1.a": {"source_status": "missing"},
        "L2.b": {"source_status": "$"},
        "L3.c": {"source_status": "✓"},
        "L4.d": {"source_status": "✓"},
        "L5.e": {"source_status": "missing"},
        "L6.f": {"source_status": "✓"},
        "L7.g": {"source_status": "missing"},
        "L8.h": {"source_status": "missing"},
    }

    report = asc.build_completion_report(spec=spec, db_path=db, labels={})

    assert report["a_share_realtime"]["ts_codes"] == 1
    assert report["a_share_realtime"]["spec_dp_handled"] == 3
    assert report["a_share_realtime"]["spec_dp_real_handled"] == 2
    assert report["a_share_effective_realtime"]["spec_dp_handled_including_mock"] == 5
    assert report["a_share_effective_realtime"]["spec_dp_real_handled"] == 3
    assert report["a_share_effective_realtime"]["spec_dp_mock_only"] == 2
    assert report["a_share_overlay"]["spec_dp_handled"] == 2
    assert report["combined"]["spec_dp_handled"] == 5
    assert report["combined"]["gap_count"] == 3
    assert {row["dp_id"] for row in report["gaps"]} == {"L4.d", "L7.g", "L8.h"}

    flags = report["flags"]
    assert {row["dp_id"] for row in flags["missing_but_a_share_hard_data"]} == {"L1.a"}
    assert {row["dp_id"] for row in flags["premium_but_a_share_hard_data"]} == {"L2.b"}
    assert {row["dp_id"] for row in flags["missing_but_a_share_overlay_handled"]} == {"L5.e"}
    assert {row["dp_id"] for row in flags["mock_only_effective_realtime"]} == {"L7.g", "L8.h"}
    assert {row["dp_id"] for row in flags["full_source_status_but_absent_on_a_share"]} == {"L4.d"}


def test_render_markdown_includes_summary(tmp_path: Path) -> None:
    db = tmp_path / "hot.sqlite"
    _make_db(db)
    report = asc.build_completion_report(
        spec={"L1.a": {"source_status": "missing"}},
        db_path=db,
        labels={"L1.a": {"layer": "L1", "label": "alpha", "coverage_summary": "x"}},
    )

    md = asc.render_markdown(report)

    assert "# A-share spec field completion" in md
    assert "Combined real A-share handled fields" in md
    assert "`L1.a`" in md
