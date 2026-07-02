import json
from pathlib import Path

from scripts import audit_a_share_unknown_business_metric_value_selection_gate as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_value_selection_gate_blocks_review_required_candidates(tmp_path: Path) -> None:
    acquisition_path = tmp_path / "acquisition.json"
    value_review_path = tmp_path / "value_review.json"
    _write_json(
        acquisition_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "score_target": "fundamental_score",
                    "metric_candidate_status": "market_denominator_required",
                    "source_review": {
                        "missing_formula_inputs": ["market share or TAM denominator"]
                    },
                },
                {
                    "dp_id": "L0.demand.frequency",
                    "score_target": "fundamental_score",
                    "metric_candidate_status": "cadence_source_required",
                    "source_review": {
                        "missing_formula_inputs": ["order or transaction cadence"]
                    },
                },
            ]
        },
    )
    _write_json(
        value_review_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "source_scope_verdict": "review_a_share_or_domestic_scope",
                    "missing_before_known": [
                        "reviewed_source_scope",
                        "reviewed_formula_policy",
                    ],
                    "candidate_value_options": [
                        {
                            "option_id": "unit:1",
                            "formula_probe_payload": {
                                "confidence": 0.36,
                                "review_status": "review_required",
                                "value_json": {"review_required": True},
                            },
                            "bridge_validation": {
                                "final_score_target_ready": True,
                            },
                        }
                    ],
                }
            ]
        },
    )

    report = audit.build_report(
        acquisition_path=acquisition_path,
        value_review_path=value_review_path,
    )

    assert report["summary"]["business_metric_selection_row_count"] == 2
    assert report["summary"]["value_review_packet_count"] == 1
    assert report["summary"]["candidate_value_option_count"] == 1
    assert report["summary"]["bridge_probe_ready_option_count"] == 1
    assert report["summary"]["review_value_selection_required_count"] == 1
    assert report["summary"]["source_metric_missing_count"] == 1
    assert report["summary"]["auto_selectable_count"] == 0
    assert report["summary"]["selected_value_json_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert (
        by_dp["L0.demand.penetration"]["selection_gate_status"]
        == "review_value_selection_required"
    )
    assert by_dp["L0.demand.penetration"]["auto_selectable"] is False
    assert by_dp["L0.demand.frequency"]["selection_gate_status"] == "source_metric_missing"
    assert "Auto-selectable values: `0`" in audit.render_markdown(report)


def test_value_selection_gate_marks_review_policy_draft_ready(tmp_path: Path) -> None:
    acquisition_path = tmp_path / "acquisition.json"
    value_review_path = tmp_path / "value_review.json"
    value_policy_draft_path = tmp_path / "value_policy_draft.json"
    _write_json(
        acquisition_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "score_target": "fundamental_score",
                    "metric_candidate_status": "market_denominator_required",
                    "source_review": {
                        "missing_formula_inputs": ["market share or TAM denominator"]
                    },
                },
                {
                    "dp_id": "L0.demand.frequency",
                    "score_target": "fundamental_score",
                    "metric_candidate_status": "cadence_source_required",
                    "source_review": {
                        "missing_formula_inputs": ["order or transaction cadence"]
                    },
                },
            ]
        },
    )
    _write_json(
        value_review_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "source_scope_verdict": "review_a_share_or_domestic_scope",
                    "missing_before_known": [
                        "reviewed_source_scope",
                        "reviewed_formula_policy",
                    ],
                    "candidate_value_options": [
                        {
                            "option_id": "unit:1",
                            "formula_probe_payload": {
                                "confidence": 0.36,
                                "review_status": "review_required",
                                "value_json": {"review_required": True},
                            },
                            "bridge_validation": {
                                "final_score_target_ready": True,
                            },
                        }
                    ],
                }
            ]
        },
    )
    _write_json(
        value_policy_draft_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "draft_contract_valid": True,
                    "source_scope_confirmed": True,
                    "proposed_raw_value": 40.0,
                    "proposed_value_json": {
                        "score": 0.4,
                        "raw_value": 40.0,
                        "unit": "percent",
                    },
                    "bridge_validation": {
                        "final_score_target_ready": True,
                    },
                    "known_draft_sufficient": False,
                    "runtime_write_allowed": False,
                    "production_write_allowed": False,
                    "missing_before_known": [
                        "reviewed_numeric_value_selection",
                        "reviewed_bounds",
                        "reviewed_formula_policy",
                        "issuer_or_industry_applicability_review",
                        "approval_record",
                    ],
                }
            ]
        },
    )

    report = audit.build_report(
        acquisition_path=acquisition_path,
        value_review_path=value_review_path,
        value_policy_draft_path=value_policy_draft_path,
    )

    assert report["summary"]["business_metric_selection_row_count"] == 2
    assert report["summary"]["value_review_packet_count"] == 1
    assert report["summary"]["review_value_selection_required_count"] == 0
    assert report["summary"]["review_value_policy_draft_ready_count"] == 1
    assert report["summary"]["value_policy_draft_ready_count"] == 1
    assert report["summary"]["proposed_value_json_count"] == 1
    assert report["summary"]["source_metric_missing_count"] == 1
    assert report["summary"]["auto_selectable_count"] == 0
    assert report["summary"]["selected_value_json_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert (
        by_dp["L0.demand.penetration"]["selection_gate_status"]
        == "review_value_policy_draft_ready"
    )
    assert by_dp["L0.demand.penetration"]["value_policy_draft_ready"] is True
    assert by_dp["L0.demand.penetration"]["proposed_value_json"]["score"] == 0.4
    assert by_dp["L0.demand.penetration"]["known_draft_sufficient"] is False
    assert by_dp["L0.demand.frequency"]["selection_gate_status"] == "source_metric_missing"
    markdown = audit.render_markdown(report)
    assert "Review value-policy draft ready: `1`" in markdown
    assert "Proposed value JSONs: `1`" in markdown
