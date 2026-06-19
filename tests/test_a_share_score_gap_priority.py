import json
import math

from scripts.audit_a_share_score_gap_priority import (
    PEER_CONTEXT_SUPPRESSED,
    build_report,
    json_safe,
    parse_field_strategy,
    priority,
    source_route,
)
from mvp20.aggregator import _VALR_SUPPRESSED_WHEN_POOLED


def _row(dp_id: str, *, cats: dict[str, int], valid: int, role: str = "score_component", target: str = "fundamental_score") -> dict:
    return {
        "dp_id": dp_id,
        "field_role": role,
        "score_target": target,
        "runtime_valid_real_ts_count": valid,
        "runtime_numeric_signal_ts_count": 0,
        "overlay_score_candidate_ts_count": 0,
        "effective_score_path_ts_count": 0,
        "runtime_source_categories": cats,
        "runtime_sources": {"tushare:test": valid} if cats.get("tushare") else {},
    }


def test_source_route_separates_intentional_and_formula_ready() -> None:
    suppressed = _row(
        "L6.mult.ps",
        cats={"tushare": 1000},
        valid=1000,
        role="derived_metric",
        target="valuation_rerating",
    )
    formula_ready = _row("L0.cost.raw_material", cats={"tushare": 1000}, valid=1000)
    formula_ready_media_no_valid = _row(
        "L9.media.report",
        cats={"akshare": 1000},
        valid=0,
        target="expectation_gap",
    )
    structured_no_valid = _row("L9.media.unclassified", cats={"akshare": 1000}, valid=0)
    formula_ready_no_valid = _row(
        "L5.surprise.beat_miss",
        cats={"tushare": 1000},
        valid=0,
        target="expectation_gap",
    )
    formula_ready_fx_no_valid = _row(
        "L9.macro.fx",
        cats={"tushare": 1000},
        valid=0,
        target="risk_discount",
    )
    formula_ready_block_no_valid = _row(
        "L9.capital.etf_block",
        cats={"akshare": 1000},
        valid=0,
        target="expectation_gap",
    )
    formula_ready_compete_no_valid = _row(
        "L9.industry.compete_risk",
        cats={"akshare": 1000},
        valid=0,
        target="risk_discount",
    )
    formula_ready_policy_no_valid = _row(
        "L9.industry.policy_change",
        cats={"akshare": 1000},
        valid=0,
        target="policy_sensitivity_multiplier",
    )
    derived_no_valid = _row("L99.synthetic_derived", cats={"derived": 1000}, valid=0)
    data_only = _row(
        "L7.trade.margin_short",
        cats={"tushare": 1000},
        valid=1000,
        target="funding_score",
    )
    valuation_context = _row(
        "L6.mult.pe",
        cats={"tushare": 1000},
        valid=1400,
        role="derived_metric",
        target="valuation_rerating",
    )
    normalized = _row(
        "L5.is.eps",
        cats={"tushare": 1000},
        valid=1641,
        target="fundamental_score",
    )
    baseline = _row(
        "L5.fcst.eps_cf",
        cats={"tushare": 1000},
        valid=1300,
        target="expectation_gap",
    )
    semantic_review = _row(
        "L5.cf.capex",
        cats={"tushare": 1000},
        valid=1640,
        target="fundamental_score",
    )
    alias_duplicate = _row(
        "L9.company.mgmt_litigation",
        cats={"tushare": 1000},
        valid=389,
        target="risk_discount",
    )
    fallback_duplicate = _row(
        "L9.media.social_buzz",
        cats={"tushare": 1000},
        valid=79,
        target="expectation_gap",
    )
    derived_bridge = _row(
        "L7.mood.media_social",
        cats={"tushare": 1000},
        valid=79,
        target="sentiment_score",
    )
    block_trade = _row(
        "L7.flow.block_trade",
        cats={"tushare": 1000},
        valid=115,
        target="funding_score",
    )
    a_share_option = _row(
        "L7.trade.options_cp",
        cats={},
        valid=0,
        target="options_momentum_multiplier",
    )
    wired_pending_refresh = _row(
        "L5.surprise.preprice",
        cats={},
        valid=0,
        target="expectation_gap",
    )
    industry_inventory_pending = _row(
        "L10.industry.inventory_orders",
        cats={},
        valid=0,
        role="confidence",
        target="confidence_multiplier",
    )
    industry_price_pending = _row(
        "L10.industry.sales_price",
        cats={},
        valid=0,
        role="confidence",
        target="confidence_multiplier",
    )

    assert source_route(suppressed, {}) == "intentional_peer_context_suppressed"
    assert priority(suppressed, source_route(suppressed, {})) == "P3_governance_or_design_review"
    assert source_route(formula_ready, {}) == "existing_structured_runtime_formula"
    assert priority(formula_ready, source_route(formula_ready, {})) == "P0_add_formula_high_coverage"
    assert source_route(structured_no_valid, {}) == "structured_runtime_present_no_valid_data"
    assert (
        priority(structured_no_valid, source_route(structured_no_valid, {}))
        == "P2_refresh_or_validate_structured_data"
    )
    assert (
        source_route(formula_ready_no_valid, {})
        == "conditional_formula_ready_pending_valid_data"
    )
    assert (
        source_route(formula_ready_fx_no_valid, {})
        == "conditional_formula_ready_pending_valid_data"
    )
    assert (
        source_route(formula_ready_block_no_valid, {})
        == "conditional_formula_ready_pending_valid_data"
    )
    assert (
        source_route(formula_ready_compete_no_valid, {})
        == "conditional_formula_ready_pending_valid_data"
    )
    assert (
        source_route(formula_ready_policy_no_valid, {})
        == "conditional_formula_ready_pending_valid_data"
    )
    assert (
        source_route(formula_ready_media_no_valid, {})
        == "conditional_formula_ready_pending_valid_data"
    )
    assert (
        priority(formula_ready_no_valid, source_route(formula_ready_no_valid, {}))
        == "P2_refresh_or_validate_structured_data"
    )
    assert source_route(derived_no_valid, {}) == "derived_runtime_present_no_valid_data"
    assert (
        priority(derived_no_valid, source_route(derived_no_valid, {}))
        == "P2_refresh_or_validate_structured_data"
    )
    assert source_route(data_only, {}) == "intentional_data_only"
    assert source_route(valuation_context, {}) == "valuation_peer_context_review"
    assert priority(valuation_context, source_route(valuation_context, {})) == "P3_governance_or_design_review"
    assert source_route(normalized, {}) == "normalization_required_formula"
    assert priority(normalized, source_route(normalized, {})) == "P1_add_normalized_or_baseline_formula"
    assert source_route(baseline, {}) == "baseline_required_formula"
    assert priority(baseline, source_route(baseline, {})) == "P1_add_normalized_or_baseline_formula"
    assert source_route(semantic_review, {}) == "business_semantics_review"
    assert priority(semantic_review, source_route(semantic_review, {})) == "P3_governance_or_design_review"
    assert source_route(alias_duplicate, {}) == "intentional_alias_duplicate"
    assert priority(alias_duplicate, source_route(alias_duplicate, {})) == "P3_governance_or_design_review"
    assert source_route(fallback_duplicate, {}) == "intentional_fallback_duplicate"
    assert priority(fallback_duplicate, source_route(fallback_duplicate, {})) == "P3_governance_or_design_review"
    assert source_route(derived_bridge, {}) == "intentional_derived_bridge_review"
    assert priority(derived_bridge, source_route(derived_bridge, {})) == "P3_governance_or_design_review"
    assert source_route(block_trade, {}) == "business_semantics_review"
    assert priority(block_trade, source_route(block_trade, {})) == "P3_governance_or_design_review"
    assert source_route(a_share_option, {}) == "a_share_listed_options_or_na_required"
    assert (
        priority(a_share_option, source_route(a_share_option, {}))
        == "P3_governance_or_design_review"
    )
    assert (
        source_route(wired_pending_refresh, {})
        == "structured_collector_wired_pending_refresh"
    )
    assert (
        priority(wired_pending_refresh, source_route(wired_pending_refresh, {}))
        == "P1_refresh_runtime_data"
    )
    assert (
        source_route(industry_inventory_pending, {})
        == "structured_collector_wired_pending_refresh"
    )
    assert (
        priority(industry_inventory_pending, source_route(industry_inventory_pending, {}))
        == "P1_refresh_runtime_data"
    )
    assert (
        source_route(industry_price_pending, {})
        == "structured_collector_wired_pending_refresh"
    )
    assert (
        priority(industry_price_pending, source_route(industry_price_pending, {}))
        == "P1_refresh_runtime_data"
    )
    assert PEER_CONTEXT_SUPPRESSED == set(_VALR_SUPPRESSED_WHEN_POOLED)


def test_build_report_counts_formula_gap_routes() -> None:
    field_rows = [
        _row("L6.mult.ps", cats={"tushare": 1000}, valid=1000, role="derived_metric", target="valuation_rerating"),
        _row("L0.cost.raw_material", cats={"tushare": 1000}, valid=1000),
        _row("L8.gov.fraud_control", cats={}, valid=0, target="risk_discount"),
    ]
    trace = {
        "summary": {
            "dp_id_lists": {
                "score_relevant_valid_real_but_no_numeric_formula": [
                    "L6.mult.ps",
                    "L0.cost.raw_material",
                ],
                "participating_gap": [
                    "L6.mult.ps",
                    "L0.cost.raw_material",
                    "L8.gov.fraud_control",
                ],
            }
        },
        "field_rows": field_rows,
    }
    strategy = {"L8.gov.fraud_control": {"bucket": "C", "state": "missing"}}

    report = build_report(trace, strategy)

    assert report["summary"]["score_relevant_formula_gap_dp_ids"] == 2
    assert report["summary"]["actionable_formula_gap_dp_ids"] == 1
    assert report["summary"]["governance_or_intentional_formula_gap_dp_ids"] == 1
    assert report["summary"]["formula_gap_by_route"] == {
        "existing_structured_runtime_formula": 1,
        "intentional_peer_context_suppressed": 1,
    }
    assert report["summary"]["formula_gap_by_bucket"] == {
        "blocking_actionable": 1,
        "intentional_governance": 1,
    }
    assert report["summary"]["participating_gap_by_route"]["llm_or_web_required"] == 1
    assert report["summary"]["participating_gap_by_bucket"]["blocking_actionable"] == 2
    assert report["summary"]["participating_gap_by_bucket"]["intentional_governance"] == 1
    assert report["summary"]["conditional_formula_ready_pending_valid_data_dp_ids"] == []
    ps_row = next(row for row in report["participating_gap_rows"] if row["dp_id"] == "L6.mult.ps")
    assert ps_row["gap_bucket"] == "intentional_governance"
    assert ps_row["intent_subtype"] == "peer_context_suppressed"
    assert ps_row["replacement_dp_id"] == "L6.state.peer_compare"
    assert ps_row["blocking_gap"] is False
    actionable = report["summary"]["score_completion_blocking_gap_dp_ids"]
    assert "L6.mult.ps" not in actionable
    assert "L0.cost.raw_material" in actionable


def test_parse_field_strategy_extracts_bucket_state(tmp_path) -> None:
    path = tmp_path / "strategy.md"
    path.write_text(
        "#### `L8.gov.fraud_control` — 财务造假/内控  *(bucket C, spec `○`, state `missing`)*\n",
        encoding="utf-8",
    )

    parsed = parse_field_strategy(path)

    assert parsed["L8.gov.fraud_control"] == {
        "bucket": "C",
        "spec": "○",
        "state": "missing",
    }


def test_json_safe_converts_non_finite_values_for_strict_json() -> None:
    payload = {"nan": math.nan, "inf": float("inf"), "nested": [-float("inf"), 1.0]}

    safe = json_safe(payload)

    assert safe == {"nan": None, "inf": None, "nested": [None, 1.0]}
    json.dumps(safe, allow_nan=False)
