import json
from pathlib import Path

from mvp20.field_governance import DataPointGovernance, FieldGovernanceRegistry
from scripts.audit_a_share_spec_score_conversion_path import build_report, render_markdown


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _registry() -> FieldGovernanceRegistry:
    mappings = {
        "L0.current.closed": {
            "field_role": "derived_metric",
            "score_target": "fundamental_score",
            "calculation_type": "ratio_metric",
            "aggregation_policy": "weighted_sum",
            "participates_in_score": True,
        },
        "L0.candidate.ready": {
            "field_role": "derived_metric",
            "score_target": "fundamental_score",
            "calculation_type": "ratio_metric",
            "aggregation_policy": "weighted_sum",
            "participates_in_score": True,
        },
        "L0.formula.missing": {
            "field_role": "derived_metric",
            "score_target": "fundamental_score",
            "calculation_type": "ratio_metric",
            "aggregation_policy": "weighted_sum",
            "participates_in_score": True,
        },
        "L0.input.missing": {
            "field_role": "derived_metric",
            "score_target": "fundamental_score",
            "calculation_type": "ratio_metric",
            "aggregation_policy": "weighted_sum",
            "participates_in_score": True,
        },
        "L0.governance.suppressed": {
            "field_role": "derived_metric",
            "score_target": "fundamental_score",
            "calculation_type": "ratio_metric",
            "aggregation_policy": "weighted_sum",
            "participates_in_score": True,
        },
        "L0.option.na": {
            "field_role": "derived_metric",
            "score_target": "fundamental_score",
            "calculation_type": "ratio_metric",
            "aggregation_policy": "weighted_sum",
            "participates_in_score": True,
        },
        "L9.audit.note": {
            "field_role": "audit",
            "score_target": "audit_only",
            "calculation_type": "none",
            "aggregation_policy": "none",
            "participates_in_score": False,
        },
    }
    return FieldGovernanceRegistry(
        {
            dp_id: DataPointGovernance.from_mapping(dp_id, mapping)
            for dp_id, mapping in mappings.items()
        }
    )


def test_score_conversion_path_summary_separates_readiness_states(tmp_path: Path) -> None:
    field_closure_path = tmp_path / "field_closure.json"
    dry_run_path = tmp_path / "dry_run.json"
    review_manifest_path = tmp_path / "review_manifest.json"
    value_contracts_path = tmp_path / "value_contracts.json"

    _write_json(
        field_closure_path,
        {
            "summary": {"configured_spec_total_dp_ids": 5},
            "rows": [
                {
                    "dp_id": "L0.current.closed",
                    "field_role": "derived_metric",
                    "score_target": "fundamental_score",
                    "participates_in_score": True,
                    "closure_status": "closed_reaches_final_score",
                    "runtime_valid_real_ts_count": 8,
                    "runtime_numeric_signal_ts_count": 8,
                    "effective_score_path_ts_count": 8,
                    "sample_values": [
                        {
                            "ts_code": "000001.SZ",
                            "status": "Known",
                            "source": "tushare:test",
                            "value": {"score": 0.2},
                        }
                    ],
                },
                {
                    "dp_id": "L0.candidate.ready",
                    "field_role": "derived_metric",
                    "score_target": "fundamental_score",
                    "participates_in_score": True,
                    "closure_status": "overlay_only_no_score_candidate",
                    "runtime_valid_real_ts_count": 0,
                    "runtime_numeric_signal_ts_count": 0,
                    "effective_score_path_ts_count": 0,
                },
                {
                    "dp_id": "L0.formula.missing",
                    "field_role": "derived_metric",
                    "score_target": "fundamental_score",
                    "participates_in_score": True,
                    "closure_status": "valid_real_but_formula_unmapped",
                    "runtime_valid_real_ts_count": 3,
                    "runtime_numeric_signal_ts_count": 0,
                    "effective_score_path_ts_count": 0,
                    "sample_values": [
                        {
                            "ts_code": "000001.SZ",
                            "status": "Known",
                            "source": "tushare:test",
                            "value": {"segments": [{"revenue_pct": 40.0}]},
                        }
                    ],
                },
                {
                    "dp_id": "L0.input.missing",
                    "field_role": "derived_metric",
                    "score_target": "fundamental_score",
                    "participates_in_score": True,
                    "closure_status": "no_valid_a_share_target_data",
                    "runtime_valid_real_ts_count": 0,
                    "runtime_numeric_signal_ts_count": 0,
                    "effective_score_path_ts_count": 0,
                },
                {
                    "dp_id": "L9.audit.note",
                    "field_role": "audit",
                    "score_target": "audit_only",
                    "participates_in_score": False,
                    "closure_status": "non_scoring_spec",
                    "runtime_valid_real_ts_count": 0,
                    "runtime_numeric_signal_ts_count": 0,
                    "effective_score_path_ts_count": 0,
                },
            ],
        },
    )
    _write_json(
        dry_run_path,
        {
            "summary": {
                "bridge_signal_ready_count": 1,
                "final_score_target_ready_count": 1,
            },
            "rows": [
                {
                    "dp_id": "L0.candidate.ready",
                    "score_target": "fundamental_score",
                    "bridge_payload_status": "Known",
                    "bridge_payload": {"score": 0.25},
                    "bridge_signal_ready": True,
                    "node_emitted": True,
                    "final_score_target_ready": True,
                }
            ],
        },
    )
    _write_json(
        review_manifest_path,
        {
            "summary": {
                "bridge_ready_concrete_count": 1,
                "review_gated_unknown_count": 0,
            },
            "rows": [
                {
                    "dp_id": "L0.candidate.ready",
                    "review_entry_status": "review_ready_concrete",
                    "bridge_ready_concrete": True,
                    "safe_to_upsert_without_review": False,
                    "production_write_allowed": False,
                }
            ],
        },
    )
    _write_json(
        value_contracts_path,
        {
            "rows": [
                {
                    "dp_id": "L0.candidate.ready",
                    "contract_valid": True,
                }
            ]
        },
    )

    report = build_report(
        field_closure_path=field_closure_path,
        dry_run_path=dry_run_path,
        review_manifest_path=review_manifest_path,
        value_contracts_path=value_contracts_path,
        registry=_registry(),
    )

    summary = report["summary"]
    assert summary["total_checked_count"] == 5
    assert summary["score_relevant_final_target_count"] == 4
    assert summary["current_numeric_final_score_count"] == 1
    assert summary["candidate_numeric_score_path_ready_count"] == 1
    assert summary["numeric_and_score_path_ready_count"] == 2
    assert summary["not_numeric_or_no_formula_count"] == 1
    assert summary["no_current_numeric_input_count"] == 1
    assert summary["no_weight_or_non_scoring_count"] == 1
    assert summary["not_entering_final_score_count"] == 3
    assert summary["production_write_allowed_count"] == 0
    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.candidate.ready"]["candidate_bridge_signal_ready"] is True
    assert by_dp["L0.candidate.ready"]["score_company_route_ready"] is True
    assert by_dp["L0.formula.missing"]["conversion_path_status"] == (
        "not_numeric_no_formula_or_normalizer"
    )
    assert by_dp["L9.audit.note"]["conversion_path_status"] == "no_weight_or_non_scoring"
    assert "Numeric and score-path ready fields: `2`" in render_markdown(report)


def test_score_conversion_path_adds_review_decision_classification(
    tmp_path: Path,
) -> None:
    field_closure_path = tmp_path / "field_closure.json"
    dry_run_path = tmp_path / "dry_run.json"
    review_manifest_path = tmp_path / "review_manifest.json"
    value_contracts_path = tmp_path / "value_contracts.json"
    formula_policy_review_path = tmp_path / "formula_policy_review.json"
    governance_suppression_path = tmp_path / "governance_suppression.json"
    option_universe_na_path = tmp_path / "option_universe_na.json"

    _write_json(
        field_closure_path,
        {
            "summary": {"configured_spec_total_dp_ids": 3},
            "rows": [
                {
                    "dp_id": "L0.formula.missing",
                    "field_role": "derived_metric",
                    "score_target": "fundamental_score",
                    "participates_in_score": True,
                    "closure_status": "valid_real_but_formula_unmapped",
                    "runtime_valid_real_ts_count": 3,
                    "runtime_numeric_signal_ts_count": 0,
                    "effective_score_path_ts_count": 0,
                    "sample_values": [
                        {
                            "ts_code": "000001.SZ",
                            "status": "Known",
                            "source": "tushare:test",
                            "value": {"segments": [{"revenue_pct": 40.0}]},
                        }
                    ],
                },
                {
                    "dp_id": "L0.governance.suppressed",
                    "field_role": "derived_metric",
                    "score_target": "fundamental_score",
                    "participates_in_score": True,
                    "closure_status": "valid_real_but_formula_unmapped",
                    "runtime_valid_real_ts_count": 4,
                    "runtime_numeric_signal_ts_count": 0,
                    "effective_score_path_ts_count": 0,
                    "sample_values": [
                        {
                            "ts_code": "000001.SZ",
                            "status": "Known",
                            "source": "tushare:test",
                            "value": {"raw": 1},
                        }
                    ],
                },
                {
                    "dp_id": "L0.option.na",
                    "field_role": "derived_metric",
                    "score_target": "fundamental_score",
                    "participates_in_score": True,
                    "closure_status": "no_valid_a_share_target_data",
                    "runtime_valid_real_ts_count": 0,
                    "runtime_numeric_signal_ts_count": 0,
                    "effective_score_path_ts_count": 0,
                },
            ],
        },
    )
    _write_json(dry_run_path, {"summary": {}, "rows": []})
    _write_json(review_manifest_path, {"summary": {}, "rows": []})
    _write_json(value_contracts_path, {"summary": {}, "rows": []})
    _write_json(
        formula_policy_review_path,
        {
            "summary": {"formula_policy_packet_count": 1},
            "rows": [
                {
                    "dp_id": "L0.formula.missing",
                    "packet_id": "packet-1",
                    "policy_family": "segment_concentration_and_strategy",
                    "policy_contract_valid": True,
                    "policy_review_status": "formula_policy_review_required",
                    "direct_formula_ready": False,
                    "production_write_allowed": False,
                }
            ],
        },
    )
    _write_json(
        governance_suppression_path,
        {
            "summary": {"suppression_verified_count": 1},
            "rows": [
                {
                    "dp_id": "L0.governance.suppressed",
                    "intent_subtype": "data_only_no_safe_signal",
                    "verification_status": "data_only_suppression_verified",
                    "suppression_verified": True,
                    "production_write_allowed": False,
                }
            ],
        },
    )
    _write_json(
        option_universe_na_path,
        {
            "summary": {"verification_contract_valid_count": 1},
            "rows": [
                {
                    "dp_id": "L0.option.na",
                    "verification_contract_valid": True,
                    "source_universe_required": True,
                    "known_value_allowed_now": False,
                    "na_or_unavailable_allowed_after_review": True,
                    "production_write_allowed": False,
                }
            ],
        },
    )

    report = build_report(
        field_closure_path=field_closure_path,
        dry_run_path=dry_run_path,
        review_manifest_path=review_manifest_path,
        value_contracts_path=value_contracts_path,
        formula_policy_review_path=formula_policy_review_path,
        governance_suppression_path=governance_suppression_path,
        option_universe_na_path=option_universe_na_path,
        registry=_registry(),
    )

    summary = report["summary"]
    assert summary["unresolved_score_relevant_count"] == 3
    assert summary["not_numeric_or_no_formula_count"] == 2
    assert summary["no_current_numeric_input_count"] == 1
    assert summary["formula_policy_review_required_count"] == 1
    assert summary["governance_suppression_verified_count"] == 1
    assert summary["option_universe_na_verified_count"] == 1
    assert summary["verified_non_numeric_exception_count"] == 2
    assert summary["review_decision_backed_not_ready_count"] == 3
    assert summary["remaining_unclassified_conversion_gap_count"] == 0
    assert summary["conversion_path_status_counts"] == {
        "no_current_numeric_input": 1,
        "not_numeric_no_formula_or_normalizer": 2,
    }
    assert summary["review_decision_status_counts"] == {
        "formula_policy_review_required": 1,
        "governance_suppression_verified": 1,
        "option_universe_na_verified": 1,
    }

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.formula.missing"]["conversion_path_status"] == (
        "not_numeric_no_formula_or_normalizer"
    )
    assert by_dp["L0.formula.missing"]["review_decision_status"] == (
        "formula_policy_review_required"
    )
    assert by_dp["L0.governance.suppressed"]["review_decision_status"] == (
        "governance_suppression_verified"
    )
    assert by_dp["L0.option.na"]["conversion_path_status"] == "no_current_numeric_input"
    assert by_dp["L0.option.na"]["review_decision_status"] == (
        "option_universe_na_verified"
    )
    markdown = render_markdown(report)
    assert "Formula-policy review required fields: `1`" in markdown
    assert "Remaining unclassified conversion gaps: `0`" in markdown
