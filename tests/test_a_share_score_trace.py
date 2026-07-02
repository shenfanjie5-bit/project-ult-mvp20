import json
import math
import sqlite3
from pathlib import Path

from mvp20.field_governance import DataPointGovernance, FieldGovernanceRegistry
from scripts.audit_a_share_score_trace import (
    build_score_trace_report,
    has_usable_value,
    is_mock_source,
    json_safe,
    source_category,
)


def _registry() -> FieldGovernanceRegistry:
    return FieldGovernanceRegistry({
        dp_id: DataPointGovernance.from_mapping(dp_id, mapping)
        for dp_id, mapping in {
            "L7.flow.active_inflow": {
                "field_role": "score_component",
                "score_target": "funding_score",
                "participates_in_score": True,
            },
            "L7.mood.analyst_rating": {
                "field_role": "score_component",
                "score_target": "sentiment_score",
                "participates_in_score": True,
            },
            "L7.trade.margin_short": {
                "field_role": "score_component",
                "score_target": "funding_score",
                "participates_in_score": True,
            },
            "L6.priced.run_up": {
                "field_role": "discount",
                "score_target": "priced_in_discount",
                "participates_in_score": True,
            },
            "L11.mode": {
                "field_role": "audit",
                "score_target": "audit_only",
                "participates_in_score": False,
            },
            "L10.industry.inventory_orders": {
                "field_role": "confidence",
                "score_target": "confidence_multiplier",
                "participates_in_score": True,
            },
        }.items()
    })


def _write_hot_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE realtime_current (
                ts_code TEXT,
                dp_id TEXT,
                value_json TEXT,
                data_status TEXT,
                confidence REAL,
                source TEXT,
                updated_at INTEGER
            );
            CREATE TABLE overlay_manifest (
                ts_code TEXT,
                industry_id TEXT,
                primary_industry INTEGER
            );
            CREATE TABLE company_node_instance (
                ts_code TEXT,
                industry_id TEXT,
                dp_id TEXT,
                data_status TEXT
            );
            CREATE TABLE company_graph_snapshot (
                ts_code TEXT
            );
            """
        )
        rows = [
            (
                "000001.SZ",
                "L7.flow.active_inflow",
                {"main_net": 50000},
                "Known",
                0.9,
                "tushare:moneyflow",
                1_700_000_000,
            ),
            (
                "000001.SZ",
                "L7.mood.analyst_rating",
                {"avg_rating_score": 5.0},
                "Known",
                0.8,
                "tushare:stk_factor",
                1_700_000_001,
            ),
            (
                "000001.SZ",
                "L7.trade.margin_short",
                {"margin_balance": 100.0},
                "Known",
                0.7,
                "tushare:margin_detail",
                1_700_000_002,
            ),
            (
                "000001.SZ",
                "L6.priced.run_up",
                {"d20_pct": 0.2},
                "Known",
                0.7,
                "mock:fixture",
                1_700_000_003,
            ),
            (
                "000001.SZ",
                "L11.mode",
                "WATCH",
                "Known",
                1.0,
                "derive:l11_mode",
                1_700_000_004,
            ),
            (
                "INDUSTRY:TEST_INDUSTRY",
                "L10.industry.inventory_orders",
                {"scope": "macro_manufacturing_proxy", "new_orders_pmi": 52.0},
                "Proxy",
                0.6,
                "tushare:cn_pmi.industry_validation",
                1_700_000_005,
            ),
        ]
        conn.executemany(
            """
            INSERT INTO realtime_current
            (ts_code, dp_id, value_json, data_status, confidence, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (ts, dp, json.dumps(value), status, conf, source, updated)
                for ts, dp, value, status, conf, source, updated in rows
            ],
        )
        conn.execute(
            "INSERT INTO overlay_manifest VALUES (?, ?, ?)",
            ("000001.SZ", "TEST_INDUSTRY", 1),
        )
        conn.execute("INSERT INTO company_graph_snapshot VALUES (?)", ("000001.SZ",))
        conn.commit()
    finally:
        conn.close()


def _write_overlay(overlays_dir: Path) -> None:
    industry_dir = overlays_dir / "TEST_INDUSTRY"
    industry_dir.mkdir(parents=True)
    (industry_dir / "000001.SZ.yaml").write_text(
        """
ts_code: 000001.SZ
industry_id: TEST_INDUSTRY
nodes:
  - node_id: 000001.SZ:blocked-flow
    dp_id: L7.flow.active_inflow
    data_status: Unknown
    value: null
    direction: positive
""",
        encoding="utf-8",
    )


def test_source_helpers_classify_mock_and_empty_values() -> None:
    assert is_mock_source("mock:fixture")
    assert source_category("tushare:moneyflow") == "tushare"
    assert source_category("akshare:index") == "akshare"
    assert not has_usable_value({})
    assert has_usable_value(0)


def test_json_safe_converts_non_finite_values_for_strict_json() -> None:
    payload = {"nan": math.nan, "inf": float("inf"), "nested": [-float("inf"), 1.0]}

    safe = json_safe(payload)

    assert safe == {"nan": None, "inf": None, "nested": [None, 1.0]}
    json.dumps(safe, allow_nan=False)


def test_build_score_trace_report_separates_numeric_formula_and_bridge(tmp_path: Path) -> None:
    db_path = tmp_path / "hot.sqlite"
    overlays_dir = tmp_path / "stock_overlays"
    industry_dir = tmp_path / "industry_overlays"
    _write_hot_db(db_path)
    _write_overlay(overlays_dir)
    industry_dir.mkdir()

    report = build_score_trace_report(
        db_path=db_path,
        overlays_dir=overlays_dir,
        industry_dir=industry_dir,
        registry=_registry(),
        sample_ts_codes=[],
        peer_context=None,
    )

    summary = report["summary"]
    assert summary["spec_total"] == 6
    assert summary["runtime_valid_real_dp_ids"] == 5
    assert summary["runtime_valid_real_direct_dp_ids"] == 4
    assert summary["runtime_valid_real_sentinel_dp_ids"] == 1
    assert summary["runtime_numeric_signal_dp_ids"] == 3
    assert summary["runtime_numeric_signal_direct_dp_ids"] == 2
    assert summary["runtime_numeric_signal_sentinel_dp_ids"] == 1
    assert summary["runtime_bridge_emitted_dp_ids"] == 3
    assert summary["mock_only_dp_ids"] == 1
    assert "L7.trade.margin_short" in summary["dp_id_lists"]["valid_real_but_no_numeric_formula"]
    assert "L11.mode" in summary["dp_id_lists"]["valid_real_but_no_numeric_formula"]
    assert (
        summary["dp_id_lists"]["score_relevant_valid_real_but_no_numeric_formula"]
        == ["L7.trade.margin_short"]
    )
    assert summary["dp_id_lists"]["non_scoring_valid_runtime_no_numeric"] == ["L11.mode"]
    assert "L7.flow.active_inflow" in summary["dp_id_lists"]["effective_score_path"]
    assert summary["dp_id_lists"]["runtime_valid_real_sentinel"] == [
        "L10.industry.inventory_orders"
    ]
    assert summary["dp_id_lists"]["runtime_numeric_signal_sentinel"] == [
        "L10.industry.inventory_orders"
    ]
    assert summary["dp_id_lists"]["numeric_runtime_blocked_by_non_scoring_overlay"] == []
    assert "L7.mood.analyst_rating" in summary["dp_id_lists"]["effective_score_path"]
