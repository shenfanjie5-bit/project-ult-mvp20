import json
from pathlib import Path

import yaml

from scripts.audit_a_share_current_mvp_score_applicability import build_report


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_current_mvp_score_applicability_excludes_review_gated_fields(tmp_path: Path) -> None:
    field_closure_path = tmp_path / "field_closure.json"
    conversion_path = tmp_path / "conversion.json"
    execution_path = tmp_path / "execution.json"
    config_path = tmp_path / "applicability.yaml"

    _write_json(
        field_closure_path,
        {
            "summary": {},
            "rows": [
                {
                    "dp_id": "L0.closed",
                    "score_target": "fundamental_score",
                    "closure_status": "closed_reaches_final_score",
                    "blocking_gap": False,
                },
                {
                    "dp_id": "L0.event",
                    "score_target": "fundamental_score",
                    "closure_status": "no_valid_a_share_target_data",
                    "blocking_gap": True,
                    "repair_route": "candidate_generation_required:event_llm_from_runtime_news",
                    "safe_to_upsert_without_review": False,
                },
                {
                    "dp_id": "L2.segment.revenue_share",
                    "score_target": "fundamental_score",
                    "closure_status": "valid_real_but_formula_unmapped",
                    "blocking_gap": False,
                },
                {
                    "dp_id": "L6.mult.ps",
                    "score_target": "valuation_rerating",
                    "closure_status": "valid_real_but_formula_unmapped",
                    "blocking_gap": False,
                },
            ],
        },
    )
    _write_json(
        conversion_path,
        {
            "rows": [
                {
                    "dp_id": "L0.closed",
                    "score_target": "fundamental_score",
                    "score_relevant_final_target": True,
                    "current_final_score_numeric": True,
                    "conversion_path_status": "current_numeric_final_score",
                },
                {
                    "dp_id": "L0.event",
                    "score_target": "fundamental_score",
                    "score_relevant_final_target": True,
                    "current_final_score_numeric": False,
                    "conversion_path_status": "no_current_numeric_input",
                },
                {
                    "dp_id": "L2.segment.revenue_share",
                    "score_target": "fundamental_score",
                    "score_relevant_final_target": True,
                    "current_final_score_numeric": False,
                    "conversion_path_status": "not_numeric_no_formula_or_normalizer",
                    "review_decision_status": "formula_policy_review_required",
                },
                {
                    "dp_id": "L6.mult.ps",
                    "score_target": "valuation_rerating",
                    "score_relevant_final_target": True,
                    "current_final_score_numeric": False,
                    "conversion_path_status": "sample_numeric_score_path_ready",
                },
            ]
        },
    )
    _write_json(
        execution_path,
        {
            "summary": {
                "execution_status": "executed",
                "post_write_verified_row_count": 10,
            }
        },
    )
    config_path.write_text(
        yaml.safe_dump(
            {
                "exclusion_policies": {
                    "no_valid_target_data_requires_unapproved_generation": {
                        "mvp_applicability": "excluded_from_current_mvp_denominator",
                    },
                    "formula_policy_review_required": {
                        "mvp_applicability": "excluded_from_current_mvp_denominator",
                    },
                    "valuation_peer_context_superseded": {
                        "mvp_applicability": "excluded_from_current_mvp_denominator",
                        "replacement_signal": "L6.state.peer_compare",
                        "applies_when": {"dp_id_in": ["L6.mult.ps"]},
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    report = build_report(
        field_closure_path=field_closure_path,
        conversion_path=conversion_path,
        execution_path=execution_path,
        config_path=config_path,
    )

    summary = report["summary"]
    assert summary["raw_score_relevant_final_target_count"] == 4
    assert summary["raw_current_numeric_final_score_count"] == 1
    assert summary["current_mvp_denominator_count"] == 1
    assert summary["current_mvp_closed_count"] == 1
    assert summary["current_mvp_final_score_closure_pct"] == 100.0
    assert summary["current_mvp_actionable_gap_count"] == 0
    assert summary["excluded_reason_counts"] == {
        "formula_policy_review_required": 1,
        "no_valid_target_data_requires_unapproved_generation": 1,
        "valuation_peer_context_superseded": 1,
    }
