import json
from pathlib import Path

from scripts.audit_a_share_score_conversion_remediation_queue import (
    build_report,
    render_markdown,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_score_conversion_remediation_queue_classifies_unresolved_rows(
    tmp_path: Path,
) -> None:
    conversion_path = tmp_path / "conversion.json"
    priority_path = tmp_path / "priority.json"

    _write_json(
        conversion_path,
        {
            "blocked_score_relevant_rows": [
                {
                    "dp_id": "L5.cf.capex",
                    "score_target": "fundamental_score",
                    "conversion_path_status": "not_numeric_no_formula_or_normalizer",
                    "closure_status": "valid_real_but_formula_unmapped",
                    "runtime_valid_real_ts_count": 1640,
                    "runtime_numeric_signal_ts_count": 0,
                    "score_company_route_ready": True,
                },
                {
                    "dp_id": "L6.mult.peg",
                    "score_target": "valuation_rerating",
                    "conversion_path_status": "not_numeric_no_formula_or_normalizer",
                    "closure_status": "valid_real_but_formula_unmapped",
                    "runtime_valid_real_ts_count": 909,
                    "runtime_numeric_signal_ts_count": 0,
                    "score_company_route_ready": True,
                },
                {
                    "dp_id": "L7.trade.options_cp",
                    "score_target": "options_momentum_multiplier",
                    "conversion_path_status": "no_current_numeric_input",
                    "closure_status": "no_valid_a_share_target_data",
                    "runtime_valid_real_ts_count": 0,
                    "runtime_numeric_signal_ts_count": 0,
                    "score_company_route_ready": True,
                },
            ]
        },
    )
    _write_json(
        priority_path,
        {
            "participating_gap_rows": [
                {
                    "dp_id": "L5.cf.capex",
                    "route": "business_semantics_review",
                    "priority": "P3_governance_or_design_review",
                    "gap_bucket": "design_review",
                    "intent_subtype": "sign_or_business_semantics_required",
                    "blocking_gap": False,
                    "source_data_state": "valid_real",
                    "runtime_source_categories": {"tushare": 1640},
                    "sources": {"tushare:cashflow": 1640},
                    "repair_hint": "capex needs a defined intensity/trend policy",
                },
                {
                    "dp_id": "L6.mult.peg",
                    "route": "intentional_data_only",
                    "priority": "P3_governance_or_design_review",
                    "gap_bucket": "intentional_governance",
                    "intent_subtype": "data_only_no_safe_signal",
                    "blocking_gap": False,
                    "source_data_state": "valid_real",
                    "runtime_source_categories": {"derived": 909},
                    "sources": {"derive:peg": 909},
                    "replacement_dp_id": "L6.state.peg_match",
                    "repair_hint": "scored through L6.state.peg_match",
                },
                {
                    "dp_id": "L7.trade.options_cp",
                    "route": "a_share_listed_options_or_na_required",
                    "priority": "P3_governance_or_design_review",
                    "gap_bucket": "universe_not_applicable",
                    "intent_subtype": "listed_option_universe_required",
                    "blocking_gap": False,
                    "source_data_state": "not_applicable_or_unlicensed",
                    "runtime_source_categories": {},
                    "sources": {},
                    "repair_hint": "requires real option-chain volume/OI",
                },
            ]
        },
    )

    report = build_report(
        conversion_path=conversion_path,
        priority_path=priority_path,
    )
    summary = report["summary"]

    assert summary["unresolved_score_relevant_count"] == 3
    assert summary["existing_current_input_count"] == 2
    assert summary["no_current_input_count"] == 1
    assert summary["score_company_route_ready_count"] == 3
    assert summary["direct_tushare_or_derived_input_count"] == 2
    assert summary["safe_formula_now_count"] == 0
    assert summary["formula_policy_required_count"] == 1
    assert summary["intentional_governance_or_duplicate_count"] == 1
    assert summary["missing_or_not_applicable_source_count"] == 1
    assert summary["production_write_allowed_count"] == 0
    assert summary["missing_priority_dp_ids"] == []

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L5.cf.capex"]["remediation_class"] == "formula_policy_required"
    assert by_dp["L6.mult.peg"]["remediation_class"] == (
        "intentional_governance_or_duplicate"
    )
    assert by_dp["L6.mult.peg"]["replacement_dp_id"] == "L6.state.peg_match"
    assert by_dp["L7.trade.options_cp"]["remediation_class"] == (
        "missing_or_not_applicable_source"
    )
    assert "Safe formula-now fields: `0`" in render_markdown(report)
