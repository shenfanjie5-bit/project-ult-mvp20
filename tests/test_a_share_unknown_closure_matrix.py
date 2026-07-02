import json
from pathlib import Path

from scripts import audit_a_share_unknown_closure_matrix as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _manifest_row(dp_id: str, source_kind: str, source_status: str) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "source_kind": source_kind,
        "source_report": "source.json",
        "source_status": source_status,
        "source_dependencies": ["dep"],
        "data_status": "Unknown",
        "review_entry_status": "review_gated_unknown",
        "source_contract_valid": True,
        "review_payload": {
            "target_dp_id": dp_id,
            "score_target": "fundamental_score",
            "data_status": "Unknown",
            "bridge_entry_data_status": "Unknown",
            "value_json": {
                "review_required": True,
                "blocked_reason": f"{dp_id}:blocked",
                "required_policy": f"{dp_id}:policy",
            },
            "confidence": 0.0,
            "evidence_refs": ["evidence"],
            "rationale": "blocked",
            "review_status": "review_required",
            "safe_to_upsert_without_review": False,
            "production_write_allowed": False,
        },
    }


def _next_action_row(dp_id: str, bucket: str) -> dict:
    return {
        "dp_id": dp_id,
        "approval_gate_status": "not_approvable_unknown",
        "next_action_bucket": bucket,
        "next_action": f"{dp_id}:next",
        "blocked_reason": f"{dp_id}:blocked",
        "required_policy": f"{dp_id}:policy",
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def test_unknown_closure_matrix_classifies_all_unknown_blockers(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    next_path = tmp_path / "next.json"
    event_path = tmp_path / "event.json"
    structured_path = tmp_path / "structured.json"
    single_path = tmp_path / "single.json"

    _write_json(
        manifest_path,
        {
            "rows": [
                _manifest_row(
                    "L0.compete.new_entrant",
                    "event_text_policy_pilot",
                    "unknown_market_doc_evidence_required",
                ),
                _manifest_row(
                    "L0.tech.substitute_tech",
                    "event_text_policy_pilot",
                    "unknown_market_doc_clean_evidence_required",
                ),
                _manifest_row(
                    "L0.cost.rent",
                    "local_structured_policy_pilot",
                    "unknown_policy_required",
                ),
                _manifest_row(
                    "L0.demand.frequency",
                    "local_structured_policy_pilot",
                    "unknown_policy_required",
                ),
                _manifest_row(
                    "L0.demand.penetration",
                    "local_structured_policy_pilot",
                    "unknown_policy_required",
                ),
                _manifest_row(
                    "L0.price.product_asp",
                    "local_structured_policy_pilot",
                    "unknown_policy_required",
                ),
                _manifest_row(
                    "L0.demand.replacement",
                    "local_single_dependency_policy_pilot",
                    "unknown_policy_required",
                ),
            ]
        },
    )
    _write_json(
        next_path,
        {
            "rows": [
                _next_action_row(
                    "L0.compete.new_entrant", "event_text_classification_required"
                ),
                _next_action_row(
                    "L0.tech.substitute_tech", "event_text_classification_required"
                ),
                _next_action_row("L0.cost.rent", "local_structured_mapping_required"),
                _next_action_row(
                    "L0.demand.frequency", "local_structured_mapping_required"
                ),
                _next_action_row(
                    "L0.demand.penetration", "local_structured_mapping_required"
                ),
                _next_action_row(
                    "L0.price.product_asp", "local_structured_mapping_required"
                ),
                _next_action_row(
                    "L0.demand.replacement", "single_dependency_policy_required"
                ),
            ]
        },
    )
    _write_json(
        event_path,
        {
            "rows": [
                {
                    "dp_id": "L0.compete.new_entrant",
                    "classification_packet_status": "requires_direct_transmission_link",
                    "candidate_examples": [],
                    "packet_contract_valid": True,
                },
                {
                    "dp_id": "L0.tech.substitute_tech",
                    "classification_packet_status": "market_doc_review_ready",
                    "candidate_examples": [{"path": "x.html"}],
                    "packet_contract_valid": True,
                },
            ]
        },
    )
    _write_json(
        structured_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.rent",
                    "source_review_packet_status": "review_candidate_ready",
                    "candidate_columns": ["use_right_asset_dep"],
                    "missing_formula_inputs": ["denominator"],
                    "direct_known_ready": False,
                    "formula_inputs_ready": False,
                    "packet_contract_valid": True,
                },
                {
                    "dp_id": "L0.demand.frequency",
                    "source_review_packet_status": "external_source_required",
                    "candidate_columns": [],
                    "missing_formula_inputs": ["orders"],
                    "direct_known_ready": False,
                    "formula_inputs_ready": False,
                    "packet_contract_valid": True,
                },
                {
                    "dp_id": "L0.demand.penetration",
                    "source_review_packet_status": "external_source_required",
                    "candidate_columns": [],
                    "missing_formula_inputs": ["tam"],
                    "direct_known_ready": False,
                    "formula_inputs_ready": False,
                    "packet_contract_valid": True,
                },
                {
                    "dp_id": "L0.price.product_asp",
                    "source_review_packet_status": (
                        "supporting_candidate_needs_quantity_source"
                    ),
                    "candidate_columns": ["bz_item", "bz_sales"],
                    "missing_formula_inputs": ["quantity"],
                    "direct_known_ready": False,
                    "formula_inputs_ready": False,
                    "packet_contract_valid": True,
                },
            ]
        },
    )
    _write_json(
        single_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.replacement",
                    "resolution_status": "requires_lifecycle_or_replacement_cycle_source",
                    "runtime_dependency_ready": True,
                    "direct_replacement_cycle_source_ready": False,
                    "lifecycle_source_required": True,
                    "reviewed_policy_required": True,
                }
            ]
        },
    )

    report = audit.build_report(
        manifest_path=manifest_path,
        next_actions_path=next_path,
        event_review_path=event_path,
        local_structured_review_path=structured_path,
        single_dependency_options_path=single_path,
    )

    assert report["summary"]["unknown_closure_row_count"] == 7
    assert report["summary"]["closure_matrix_row_count"] == 7
    assert report["summary"]["closure_route_assigned_count"] == 7
    assert report["summary"]["missing_closure_route_count"] == 0
    assert report["summary"]["auto_known_ready_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["event_evidence_gap_count"] == 2
    assert report["summary"]["local_structured_formula_review_count"] == 2
    assert report["summary"]["external_business_source_required_count"] == 3
    assert report["summary"]["event_text_classification_required_count"] == 2
    assert report["summary"]["local_structured_mapping_required_count"] == 4
    assert report["summary"]["structured_text_extraction_required_count"] == 0
    assert report["summary"]["single_dependency_policy_required_count"] == 1
    assert report["summary"]["manual_assumption_review_required_count"] == 0
    assert report["summary"]["rows_with_source_candidates_count"] == 3
    assert report["summary"]["formula_inputs_ready_count"] == 0
    assert report["summary"]["closure_contract_valid_count"] == 7
    assert report["summary"]["production_write_allowed_count"] == 0

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.compete.new_entrant"]["closure_blocker_class"] == (
        "direct_event_transmission_evidence_required"
    )
    assert by_dp["L0.tech.substitute_tech"]["closure_blocker_class"] == (
        "clean_substitution_risk_evidence_required"
    )
    assert by_dp["L0.cost.rent"]["closure_blocker_class"] == "formula_policy_required"
    assert by_dp["L0.price.product_asp"]["closure_blocker_class"] == (
        "quantity_or_price_index_source_required"
    )
    assert by_dp["L0.demand.replacement"]["closure_blocker_class"] == (
        "lifecycle_source_and_policy_required"
    )
    assert "Unknown closure rows: `7`" in audit.render_markdown(report)


def test_unknown_closure_matrix_rejects_writable_unknown_row() -> None:
    row = {
        "dp_id": "L0.cost.rent",
        "data_status": "Unknown",
        "auto_known_ready": True,
        "approval_ready": False,
        "runtime_write_allowed": False,
        "production_write_allowed": True,
        "closure_blocker_class": "formula_policy_required",
        "minimum_unlock_evidence": ["formula"],
        "next_action": "review",
        "next_action_bucket": "human_approval_required",
        "source_contract_valid": True,
        "supporting_packet_contract_valid": True,
    }

    errors = audit._validation_errors(row)

    assert "auto_known_ready must be false" in errors
    assert "production_write_allowed must be false" in errors
    assert "Unknown rows must not be in the human approval bucket" in errors
