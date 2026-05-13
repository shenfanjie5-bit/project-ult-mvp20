"""Tests for ``mvp20.fingerprint`` — Z2 source-fingerprint engine.

Covers:

* ``_row_fingerprint`` determinism + value_json key-order invariance
  + filing-class period folding.
* ``compute_dependency_fingerprint`` multi-dep combination and
  per-dp_id priority (ts_code-specific over MARKET sentinel).
* ``is_refresh_triggered`` decision matrix across ``static_picture``,
  ``explicit_refresh``, ``quarterly_filing``, ``event_driven``,
  ``source_fingerprint_changed``, missing-baseline, no-deps, and
  no-source-data scenarios.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from mvp20.fingerprint import (
    FILING_SOURCE_DP_IDS,
    _candidate_ts_codes,
    _normalize_value,
    _row_fingerprint,
    compute_dependency_fingerprint,
    is_refresh_triggered,
)


# ---------------------------------------------------------------------------
# Fixtures — build a tiny in-memory SQLite that matches the
# ``realtime_current`` schema used by storage.py.
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path, rows: list[tuple]) -> Path:
    """Materialise a SQLite db with the realtime_current schema.

    ``rows``: list of ``(ts_code, dp_id, value_json, data_status,
    confidence, source, updated_at)`` tuples.
    """

    db_path = tmp_path / "hot.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
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
            )
            """
        )
        conn.executemany(
            "INSERT INTO realtime_current VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


# ---------------------------------------------------------------------------
# _normalize_value
# ---------------------------------------------------------------------------


def test_normalize_value_handles_invalid_json() -> None:
    assert _normalize_value("not json {") == "not json {"
    assert _normalize_value("") == ""


def test_normalize_value_sorts_dict_keys() -> None:
    a = _normalize_value('{"b": 2, "a": 1}')
    b = _normalize_value('{"a": 1, "b": 2}')
    assert a == b


# ---------------------------------------------------------------------------
# _row_fingerprint
# ---------------------------------------------------------------------------


def test_row_fingerprint_is_deterministic() -> None:
    row = ("L5.is.revenue", '{"scalar": 100}', "Known", 0.9, "tushare", 1700000000)
    assert _row_fingerprint(row) == _row_fingerprint(row)


def test_row_fingerprint_value_json_key_order_invariant() -> None:
    row_a = (
        "L3.channel.mix",
        '{"b": 2, "a": 1}',
        "Known",
        0.8,
        "tushare",
        1700000000,
    )
    row_b = (
        "L3.channel.mix",
        '{"a": 1, "b": 2}',
        "Known",
        0.8,
        "tushare",
        1700000000,
    )
    assert _row_fingerprint(row_a) == _row_fingerprint(row_b)


def test_row_fingerprint_changes_on_value_diff() -> None:
    row_a = ("L3.channel.mix", '{"a": 1}', "Known", 0.8, "tushare", 1700000000)
    row_b = ("L3.channel.mix", '{"a": 2}', "Known", 0.8, "tushare", 1700000000)
    assert _row_fingerprint(row_a) != _row_fingerprint(row_b)


def test_row_fingerprint_filing_dp_id_folds_period() -> None:
    # Same source row, same updated_at, but different period → different hash
    row_a = (
        "L5.is.revenue",
        '{"scalar": 100, "period": "20260331"}',
        "Known",
        0.9,
        "tushare",
        1700000000,
    )
    row_b = (
        "L5.is.revenue",
        '{"scalar": 100, "period": "20251231"}',
        "Known",
        0.9,
        "tushare",
        1700000000,
    )
    assert "L5.is.revenue" in FILING_SOURCE_DP_IDS
    assert _row_fingerprint(row_a) != _row_fingerprint(row_b)


def test_row_fingerprint_non_filing_dp_id_does_not_fold_period() -> None:
    # For a non-filing dp_id, the period key (if present) is just part of
    # value_json normal hashing, not the filing extras path.
    row_a = (
        "L3.channel.mix",
        '{"foo": 1}',
        "Known",
        0.9,
        "tushare",
        1700000000,
    )
    # Same content, just literal hash must be deterministic
    assert "L3.channel.mix" not in FILING_SOURCE_DP_IDS
    assert _row_fingerprint(row_a) == _row_fingerprint(row_a)


# ---------------------------------------------------------------------------
# _candidate_ts_codes
# ---------------------------------------------------------------------------


def test_candidate_ts_codes_a_share() -> None:
    assert _candidate_ts_codes("000063.SZ") == ["000063.SZ", "MARKET:CN"]
    assert _candidate_ts_codes("600519.SH") == ["600519.SH", "MARKET:CN"]


def test_candidate_ts_codes_hk_us() -> None:
    assert _candidate_ts_codes("0700.HK") == ["0700.HK", "MARKET:HK"]
    assert _candidate_ts_codes("NVDA.US") == ["NVDA.US", "MARKET:US"]


def test_candidate_ts_codes_industry_sentinel() -> None:
    # Industry sentinels don't suffix-match any market — only the literal
    # candidate is returned.
    assert _candidate_ts_codes("INDUSTRY:AI_COMPUTE") == ["INDUSTRY:AI_COMPUTE"]


# ---------------------------------------------------------------------------
# compute_dependency_fingerprint
# ---------------------------------------------------------------------------


def test_compute_fp_returns_none_when_no_deps(tmp_path: Path) -> None:
    db = _make_db(tmp_path, [])
    assert compute_dependency_fingerprint("000063.SZ", [], db) is None


def test_compute_fp_returns_none_when_db_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope.sqlite"
    assert compute_dependency_fingerprint(
        "000063.SZ", ["L5.is.revenue"], missing
    ) is None


def test_compute_fp_returns_none_when_no_rows(tmp_path: Path) -> None:
    # DB exists but realtime_current is empty
    db = _make_db(tmp_path, [])
    assert compute_dependency_fingerprint(
        "000063.SZ", ["L5.is.revenue"], db
    ) is None


def test_compute_fp_single_dep_hits_ts_code_row(tmp_path: Path) -> None:
    db = _make_db(
        tmp_path,
        [
            (
                "000063.SZ",
                "L5.is.revenue",
                '{"scalar": 100, "period": "20260331"}',
                "Known",
                0.9,
                "tushare",
                1700000000,
            )
        ],
    )
    fp = compute_dependency_fingerprint("000063.SZ", ["L5.is.revenue"], db)
    assert fp is not None
    assert len(fp) == 16
    # Determinism
    assert compute_dependency_fingerprint(
        "000063.SZ", ["L5.is.revenue"], db
    ) == fp


def test_compute_fp_multi_dep_order_invariant(tmp_path: Path) -> None:
    db = _make_db(
        tmp_path,
        [
            (
                "000063.SZ",
                "L5.is.revenue",
                '{"scalar": 100}',
                "Known",
                0.9,
                "tushare",
                1700000000,
            ),
            (
                "000063.SZ",
                "L5.is.gross_margin",
                '{"scalar": 0.4}',
                "Known",
                0.9,
                "tushare",
                1700000000,
            ),
        ],
    )
    fp_a = compute_dependency_fingerprint(
        "000063.SZ", ["L5.is.revenue", "L5.is.gross_margin"], db
    )
    fp_b = compute_dependency_fingerprint(
        "000063.SZ", ["L5.is.gross_margin", "L5.is.revenue"], db
    )
    assert fp_a is not None
    assert fp_a == fp_b


def test_compute_fp_changes_when_underlying_value_changes(tmp_path: Path) -> None:
    db_a = _make_db(
        tmp_path / "a",
        [
            (
                "000063.SZ",
                "L5.is.revenue",
                '{"scalar": 100, "period": "20260331"}',
                "Known",
                0.9,
                "tushare",
                1700000000,
            )
        ],
    )
    db_b = _make_db(
        tmp_path / "b",
        [
            (
                "000063.SZ",
                "L5.is.revenue",
                '{"scalar": 200, "period": "20260331"}',  # value changed
                "Known",
                0.9,
                "tushare",
                1700000001,
            )
        ],
    )
    fp_a = compute_dependency_fingerprint("000063.SZ", ["L5.is.revenue"], db_a)
    fp_b = compute_dependency_fingerprint("000063.SZ", ["L5.is.revenue"], db_b)
    assert fp_a is not None and fp_b is not None
    assert fp_a != fp_b


def test_compute_fp_falls_back_to_market_sentinel(tmp_path: Path) -> None:
    # No per-ts row, only MARKET:CN row exists. fingerprint must still
    # be computed from the MARKET row.
    db = _make_db(
        tmp_path,
        [
            (
                "MARKET:CN",
                "L9.macro.geo",
                '{"event": "tariff_2026"}',
                "Known",
                0.9,
                "akshare",
                1700000000,
            )
        ],
    )
    fp = compute_dependency_fingerprint("000063.SZ", ["L9.macro.geo"], db)
    assert fp is not None


def test_compute_fp_ts_code_row_outranks_market(tmp_path: Path) -> None:
    # Both rows exist; the ts_code-specific one must win — so different
    # MARKET value should not change the result.
    rows_a = [
        (
            "000063.SZ",
            "L5.is.revenue",
            '{"scalar": 100}',
            "Known",
            0.9,
            "tushare",
            1700000000,
        ),
        (
            "MARKET:CN",
            "L5.is.revenue",
            '{"scalar": 1, "note": "MARKET"}',
            "Known",
            0.9,
            "tushare",
            1700000000,
        ),
    ]
    rows_b = [
        rows_a[0],  # same ts_code row
        (
            "MARKET:CN",
            "L5.is.revenue",
            '{"scalar": 9999, "note": "MARKET"}',  # different MARKET
            "Known",
            0.9,
            "tushare",
            1700000000,
        ),
    ]
    db_a = _make_db(tmp_path / "a", rows_a)
    db_b = _make_db(tmp_path / "b", rows_b)
    fp_a = compute_dependency_fingerprint("000063.SZ", ["L5.is.revenue"], db_a)
    fp_b = compute_dependency_fingerprint("000063.SZ", ["L5.is.revenue"], db_b)
    assert fp_a == fp_b


# ---------------------------------------------------------------------------
# is_refresh_triggered
# ---------------------------------------------------------------------------


def _gov(trigger: str, deps: list[str] | None = None) -> dict:
    return {
        "route": "llm_close",
        "model_tier": "analysis",
        "refresh_trigger": trigger,
        "source_dependencies": deps or [],
    }


def test_is_refresh_static_picture_never_refreshes(tmp_path: Path) -> None:
    db = _make_db(tmp_path, [])
    node = {"data_status": "Known", "source_fingerprint_at_fill": None}
    ok, reason = is_refresh_triggered(
        node, _gov("static_picture", ["L5.is.revenue"]), db, "000063.SZ"
    )
    assert ok is False
    assert reason == "static_picture"


def test_is_refresh_explicit_only_never_refreshes(tmp_path: Path) -> None:
    db = _make_db(tmp_path, [])
    node = {"data_status": "Known", "source_fingerprint_at_fill": "abc123"}
    ok, reason = is_refresh_triggered(
        node, _gov("explicit_refresh", ["L5.is.revenue"]), db, "000063.SZ"
    )
    assert ok is False
    assert reason == "explicit_refresh_only"


def test_is_refresh_no_deps_returns_false(tmp_path: Path) -> None:
    db = _make_db(tmp_path, [])
    node = {"data_status": "Known", "source_fingerprint_at_fill": "abc123"}
    ok, reason = is_refresh_triggered(
        node, _gov("quarterly_filing", []), db, "000063.SZ"
    )
    assert ok is False
    assert reason == "no_source_dependencies"


def test_is_refresh_no_source_data_returns_false(tmp_path: Path) -> None:
    db = _make_db(tmp_path, [])  # empty
    node = {"data_status": "Known", "source_fingerprint_at_fill": "abc123"}
    ok, reason = is_refresh_triggered(
        node, _gov("quarterly_filing", ["L5.is.revenue"]), db, "000063.SZ"
    )
    assert ok is False
    assert reason == "no_source_data"


def test_is_refresh_baseline_missing_triggers(tmp_path: Path) -> None:
    db = _make_db(
        tmp_path,
        [
            (
                "000063.SZ",
                "L5.is.revenue",
                '{"scalar": 100, "period": "20260331"}',
                "Known",
                0.9,
                "tushare",
                1700000000,
            )
        ],
    )
    # Legacy node: status Known, but no source_fingerprint_at_fill yet
    node = {"data_status": "Known"}
    ok, reason = is_refresh_triggered(
        node, _gov("quarterly_filing", ["L5.is.revenue"]), db, "000063.SZ"
    )
    assert ok is True
    assert reason == "fingerprint_baseline_missing"


def test_is_refresh_unchanged_returns_false(tmp_path: Path) -> None:
    rows = [
        (
            "000063.SZ",
            "L5.is.revenue",
            '{"scalar": 100, "period": "20260331"}',
            "Known",
            0.9,
            "tushare",
            1700000000,
        )
    ]
    db = _make_db(tmp_path, rows)
    current = compute_dependency_fingerprint(
        "000063.SZ", ["L5.is.revenue"], db
    )
    assert current is not None
    node = {"data_status": "Known", "source_fingerprint_at_fill": current}
    ok, reason = is_refresh_triggered(
        node, _gov("quarterly_filing", ["L5.is.revenue"]), db, "000063.SZ"
    )
    assert ok is False
    assert reason == "fingerprint_unchanged"


def test_is_refresh_changed_triggers(tmp_path: Path) -> None:
    db = _make_db(
        tmp_path,
        [
            (
                "000063.SZ",
                "L5.is.revenue",
                '{"scalar": 100, "period": "20260331"}',
                "Known",
                0.9,
                "tushare",
                1700000000,
            )
        ],
    )
    # Pretend a prior fingerprint was stored that doesn't match current
    node = {
        "data_status": "Known",
        "source_fingerprint_at_fill": "0000000000000000",
    }
    ok, reason = is_refresh_triggered(
        node, _gov("quarterly_filing", ["L5.is.revenue"]), db, "000063.SZ"
    )
    assert ok is True
    assert reason == "source_changed_quarterly_filing"


def test_is_refresh_event_driven_changed_triggers(tmp_path: Path) -> None:
    db = _make_db(
        tmp_path,
        [
            (
                "MARKET:CN",
                "L9.media.report",
                '{"event_id": "evt-2026-001"}',
                "Known",
                0.9,
                "akshare",
                1700000000,
            )
        ],
    )
    node = {
        "data_status": "Known",
        "source_fingerprint_at_fill": "stale_value_here",
    }
    ok, reason = is_refresh_triggered(
        node, _gov("event_driven", ["L9.media.report"]), db, "000063.SZ"
    )
    assert ok is True
    assert reason == "source_changed_event_driven"


def test_is_refresh_source_fingerprint_changed_trigger(tmp_path: Path) -> None:
    db = _make_db(
        tmp_path,
        [
            (
                "000063.SZ",
                "L3.channel.mix",
                '{"online": 0.6, "offline": 0.4}',
                "Known",
                0.9,
                "tushare",
                1700000000,
            )
        ],
    )
    node = {"data_status": "Known", "source_fingerprint_at_fill": "deadbeefdeadbeef"}
    ok, reason = is_refresh_triggered(
        node,
        _gov("source_fingerprint_changed", ["L3.channel.mix"]),
        db,
        "000063.SZ",
    )
    assert ok is True
    assert reason == "source_changed_source_fingerprint_changed"
