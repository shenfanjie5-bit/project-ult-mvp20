"""Tests for mvp20.storage: SQLite hot-snapshot read/write."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from mvp20.storage import (
    init_db,
    read_available_overlay_industries,
    read_compiled_graph_snapshot,
    read_freshness_meta,
    read_hot_snapshot,
    read_hot_snapshot_changed_since,
    read_overlay_alerts,
    replace_compiled_overlays,
    update_freshness,
    upsert_realtime,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "hot.sqlite"
    init_db(p)
    return p


def test_init_db_idempotent(db_path: Path) -> None:
    init_db(db_path)
    init_db(db_path)
    assert db_path.exists()


def test_field_governance_does_not_migrate_compiled_node_schema(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(company_node_instance)")
        }

    assert "field_role" not in cols
    assert "score_target" not in cols


def test_upsert_then_read_returns_snapshot(db_path: Path) -> None:
    now = int(time.time())
    upsert_realtime(db_path, [
        ("300750.SZ", "L7.flow.netbuy", {"scalar": 1.2}, "Known", 0.8, "tushare", now),
        ("300750.SZ", "L7.trade.iv", {"scalar": 0.35}, "Known", 0.7, "futu", now),
        ("NVDA.US", "L7.flow.netbuy", {"scalar": 5_000_000.0}, "Known", 0.9, "fmp", now),
    ])

    snap = read_hot_snapshot(db_path, "300750.SZ")
    assert set(snap.keys()) == {"L7.flow.netbuy", "L7.trade.iv"}
    assert snap["L7.flow.netbuy"]["value"] == {"scalar": 1.2}
    assert snap["L7.flow.netbuy"]["source"] == "tushare"
    assert snap["L7.flow.netbuy"]["data_status"] == "Known"
    assert snap["L7.flow.netbuy"]["age_seconds"] >= 0


def test_upsert_overwrites_same_key(db_path: Path) -> None:
    t0 = int(time.time())
    upsert_realtime(db_path, [
        ("300750.SZ", "L7.flow.netbuy", {"scalar": 1.0}, "Known", 0.5, "tushare", t0),
    ])
    upsert_realtime(db_path, [
        ("300750.SZ", "L7.flow.netbuy", {"scalar": 2.0}, "Known", 0.9, "tushare", t0 + 10),
    ])
    snap = read_hot_snapshot(db_path, "300750.SZ")
    assert snap["L7.flow.netbuy"]["value"] == {"scalar": 2.0}
    assert snap["L7.flow.netbuy"]["confidence"] == 0.9


def test_value_can_be_pre_json_encoded_string(db_path: Path) -> None:
    """Caller may pass either a dict (encoded internally) or a JSON string."""
    now = int(time.time())
    upsert_realtime(db_path, [
        ("X.SH", "dp_a", {"a": 1}, "Known", None, "src", now),
        ("X.SH", "dp_b", json.dumps({"b": 2}), "Known", None, "src", now),
    ])
    snap = read_hot_snapshot(db_path, "X.SH")
    assert snap["dp_a"]["value"] == {"a": 1}
    assert snap["dp_b"]["value"] == {"b": 2}


def test_changed_since_filters_by_updated_at(db_path: Path) -> None:
    base = int(time.time())
    upsert_realtime(db_path, [
        ("X.SH", "old", {"v": 1}, "Known", None, "src", base),
        ("X.SH", "new1", {"v": 2}, "Known", None, "src", base + 10),
        ("X.SH", "new2", {"v": 3}, "Known", None, "src", base + 20),
    ])
    delta = read_hot_snapshot_changed_since(db_path, "X.SH", since_unix=base + 5)
    assert set(delta.keys()) == {"new1", "new2"}


def test_missing_db_returns_empty_snapshot(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.sqlite"
    assert read_hot_snapshot(missing, "X.SH") == {}
    assert read_hot_snapshot_changed_since(missing, "X.SH", 0) == {}
    assert read_freshness_meta(missing) == {}


def test_freshness_stamping(db_path: Path) -> None:
    update_freshness(db_path, layer="realtime", sync_status="ok", is_full=True)
    f = read_freshness_meta(db_path)
    assert f["realtime"]["sync_status"] == "ok"
    assert f["realtime"]["last_full_sync_at"] is not None
    # Partial sync should not clobber last_full_sync_at
    full_at = f["realtime"]["last_full_sync_at"]
    update_freshness(db_path, layer="realtime", sync_status="degraded", is_full=False)
    f2 = read_freshness_meta(db_path)
    assert f2["realtime"]["last_full_sync_at"] == full_at
    assert f2["realtime"]["sync_status"] == "degraded"


def test_read_only_reader_does_not_block_writer(db_path: Path) -> None:
    """WAL mode: a reader and writer can co-exist without deadlock."""
    now = int(time.time())
    upsert_realtime(db_path, [
        ("X.SH", "dp1", {"v": 1}, "Known", None, "src", now),
    ])
    # Reader opens — then writer should still be able to upsert without
    # waiting for the reader to close.
    snap1 = read_hot_snapshot(db_path, "X.SH")
    assert "dp1" in snap1
    upsert_realtime(db_path, [
        ("X.SH", "dp2", {"v": 2}, "Known", None, "src", now + 1),
    ])
    snap2 = read_hot_snapshot(db_path, "X.SH")
    assert "dp2" in snap2


def test_replace_compiled_overlays_keeps_realtime_current(db_path: Path) -> None:
    now = int(time.time())
    upsert_realtime(db_path, [
        ("TEST.SZ", "L7.flow.netbuy", {"scalar": 10}, "Known", 0.8, "test", now),
    ])

    replace_compiled_overlays(
        db_path,
        manifests=[
            {
                "ts_code": "TEST.SZ",
                "industry_id": "A",
                "overlay_path": "config/stock_overlays/A/TEST.SZ.yaml",
                "period": "2026-Q1",
                "primary_industry": 1,
                "overlay_status": "compiled",
                "updated_at": now,
            },
            {
                "ts_code": "TEST.SZ",
                "industry_id": "B",
                "overlay_path": "config/stock_overlays/B/TEST.SZ.yaml",
                "period": "2026-Q1",
                "primary_industry": 0,
                "overlay_status": "compiled",
                "updated_at": now,
            },
        ],
        nodes=[],
        edges=[],
        snapshots=[
            {
                "ts_code": "TEST.SZ",
                "industry_id": "A",
                "payload_json": json.dumps({"ts_code": "TEST.SZ", "industry_id": "A"}),
                "graph_version": "stock-overlay-v2",
                "data_version": "2026-Q1",
                "updated_at": now,
            },
            {
                "ts_code": "TEST.SZ",
                "industry_id": "B",
                "payload_json": json.dumps({"ts_code": "TEST.SZ", "industry_id": "B"}),
                "graph_version": "stock-overlay-v2",
                "data_version": "2026-Q1",
                "updated_at": now,
            },
        ],
        alerts=[
            {
                "alert_id": "TEST.SZ:A:dp:UNKNOWN_CONDITIONAL_REQUIRED",
                "ts_code": "TEST.SZ",
                "industry_id": "A",
                "dp_id": "dp",
                "severity": "WARN",
                "code": "UNKNOWN_CONDITIONAL_REQUIRED",
                "message": "missing",
                "created_at": now,
                "resolved_at": None,
            }
        ],
    )

    assert read_available_overlay_industries(db_path, "TEST.SZ") == ["A", "B"]
    assert read_compiled_graph_snapshot(db_path, "TEST.SZ")["industry_id"] == "A"
    assert read_compiled_graph_snapshot(db_path, "TEST.SZ", "B")["industry_id"] == "B"
    assert read_overlay_alerts(db_path, "TEST.SZ", "A")[0]["severity"] == "WARN"
    assert read_hot_snapshot(db_path, "TEST.SZ")["L7.flow.netbuy"]["value"] == {"scalar": 10}


# ---------------------------------------------------------------------------
# Sentinel ts_code merge (MARKET:* / INDUSTRY:* fallback)
# ---------------------------------------------------------------------------


def _seed_sentinel_fixture(db_path: Path, now: int) -> None:
    """Seed realtime_current with a per-stock row, a MARKET:CN sentinel,
    an INDUSTRY:AI_COMPUTE sentinel, plus an overlay_manifest row mapping
    300750.SZ → primary industry AI_COMPUTE."""
    upsert_realtime(db_path, [
        # Per-stock specific (highest priority)
        ("300750.SZ", "L5.is.revenue",
         {"v": 100}, "Known", 0.9, "tushare:income", now),
        # INDUSTRY-level sentinel (middle priority for industry-tagged stocks)
        ("INDUSTRY:AI_COMPUTE", "L10.industry.fund_flow",
         {"net_amount": -50}, "Known", 0.7, "tushare:moneyflow_ind_ths", now),
        # MARKET-level sentinel (lowest priority)
        ("MARKET:CN", "L10.industry.pmi",
         {"manufacturing": 50.4}, "Known", 0.8, "tushare:cn_pmi", now),
        ("MARKET:CN", "L7.env.rates",
         {"lpr_1y": 3.0}, "Known", 0.85, "tushare:shibor_lpr", now),
        # Unrelated MARKET:US row — must NOT leak into a CN stock's snapshot
        ("MARKET:US", "L7.env.rates",
         {"treasury_10y": 4.42}, "Known", 0.8, "fmp:treasury-rates", now),
    ])
    replace_compiled_overlays(
        db_path,
        manifests=[{
            "ts_code": "300750.SZ",
            "industry_id": "AI_COMPUTE",
            "overlay_path": "config/stock_overlays/AI_COMPUTE/300750.SZ.yaml",
            "period": "2026-Q1",
            "primary_industry": 1,
            "overlay_status": "compiled",
            "updated_at": now,
        }],
        nodes=[],
        edges=[],
        snapshots=[],
        alerts=[],
    )


def test_sentinel_merge_pulls_market_and_industry_for_cn_stock(
    db_path: Path,
) -> None:
    """A CN stock should see its own dp_ids plus INDUSTRY:<id> plus
    MARKET:CN, but NOT MARKET:US (different market)."""
    now = int(time.time())
    _seed_sentinel_fixture(db_path, now)

    snap = read_hot_snapshot(db_path, "300750.SZ")

    # Per-stock row present
    assert "L5.is.revenue" in snap
    assert snap["L5.is.revenue"]["_origin_ts_code"] == "300750.SZ"

    # Industry sentinel merged
    assert "L10.industry.fund_flow" in snap
    assert snap["L10.industry.fund_flow"]["_origin_ts_code"] == "INDUSTRY:AI_COMPUTE"

    # Market sentinel merged (CN)
    assert "L10.industry.pmi" in snap
    assert snap["L10.industry.pmi"]["_origin_ts_code"] == "MARKET:CN"
    assert "L7.env.rates" in snap
    assert snap["L7.env.rates"]["_origin_ts_code"] == "MARKET:CN"
    # Verify the CN row (3.0) won — NOT the US row (4.42).
    assert snap["L7.env.rates"]["value"]["lpr_1y"] == 3.0


def test_sentinel_merge_priority_ts_specific_wins_over_market(
    db_path: Path,
) -> None:
    """If both per-stock and MARKET:CN have the same dp_id, the per-stock
    value wins (highest priority)."""
    now = int(time.time())
    upsert_realtime(db_path, [
        ("MARKET:CN", "L7.env.rates",
         {"lpr_1y": 3.0}, "Known", 0.85, "tushare:shibor_lpr", now),
        ("300750.SZ", "L7.env.rates",
         {"lpr_1y": 99.0}, "Known", 0.95, "manual:override", now),
    ])

    snap = read_hot_snapshot(db_path, "300750.SZ")
    assert snap["L7.env.rates"]["value"]["lpr_1y"] == 99.0
    assert snap["L7.env.rates"]["_origin_ts_code"] == "300750.SZ"


def test_sentinel_merge_can_be_disabled(db_path: Path) -> None:
    """include_sentinels=False keeps the legacy ts_code-only behaviour
    (used by SSE delta where market-wide updates would flood every conn)."""
    now = int(time.time())
    _seed_sentinel_fixture(db_path, now)

    snap = read_hot_snapshot(db_path, "300750.SZ", include_sentinels=False)
    assert "L5.is.revenue" in snap
    assert "L10.industry.fund_flow" not in snap
    assert "L10.industry.pmi" not in snap
    assert "L7.env.rates" not in snap


def test_sentinel_merge_us_stock_picks_market_us(db_path: Path) -> None:
    """A US stock should see MARKET:US sentinel, NOT MARKET:CN."""
    now = int(time.time())
    upsert_realtime(db_path, [
        ("MARKET:US", "L7.env.rates",
         {"treasury_10y": 4.42}, "Known", 0.8, "fmp:treasury-rates", now),
        ("MARKET:CN", "L7.env.rates",
         {"lpr_1y": 3.0}, "Known", 0.85, "tushare:shibor_lpr", now),
        ("NVDA.US", "L5.is.revenue", {"v": 200}, "Known", 0.9, "fmp", now),
    ])

    snap = read_hot_snapshot(db_path, "NVDA.US")
    assert snap["L7.env.rates"]["_origin_ts_code"] == "MARKET:US"
    assert snap["L7.env.rates"]["value"]["treasury_10y"] == 4.42


def test_sentinel_merge_no_overlay_manifest_falls_back_to_market_only(
    db_path: Path,
) -> None:
    """If overlay_manifest has no row for this ts_code, INDUSTRY:* is
    skipped but MARKET:* still merges."""
    now = int(time.time())
    upsert_realtime(db_path, [
        ("MARKET:CN", "L10.industry.pmi",
         {"manufacturing": 50.4}, "Known", 0.8, "tushare:cn_pmi", now),
        ("INDUSTRY:AI_COMPUTE", "L10.industry.fund_flow",
         {"net_amount": -50}, "Known", 0.7, "tushare", now),
        ("999999.SZ", "L5.is.revenue",
         {"v": 1}, "Known", 0.9, "tushare", now),
    ])
    # No overlay_manifest row for 999999.SZ → industries list is empty.

    snap = read_hot_snapshot(db_path, "999999.SZ")
    assert "L10.industry.pmi" in snap                 # MARKET:CN still merges
    assert "L10.industry.fund_flow" not in snap       # no industry mapping
