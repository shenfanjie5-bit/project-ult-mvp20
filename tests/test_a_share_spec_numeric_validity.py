import json
from pathlib import Path

from scripts.audit_a_share_spec_numeric_validity import build_report, render_markdown


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_spec_numeric_validity_keeps_current_and_candidate_gates_separate(
    tmp_path: Path,
) -> None:
    field_closure_path = tmp_path / "field_closure.json"
    dry_run_path = tmp_path / "dry_run.json"
    staging_path = tmp_path / "staging.json"
    value_contracts_path = tmp_path / "value_contracts.json"
    review_manifest_path = tmp_path / "review_manifest.json"
    approval_gate_path = tmp_path / "approval_gate.json"
    unknown_closure_path = tmp_path / "unknown_closure.json"

    _write_json(
        field_closure_path,
        {
            "summary": {
                "configured_spec_total_dp_ids": 4,
                "runtime_trace_spec_total_dp_ids": 4,
                "spec_total_matches_runtime": True,
                "score_relevant_spec_dp_ids": 3,
                "blocking_gap_dp_ids": 2,
                "candidate_ready_blocking_gap_dp_ids": 2,
            },
            "rows": [
                {
                    "dp_id": "L7.flow.active_inflow",
                    "score_target": "funding_score",
                    "score_relevant": True,
                    "closure_status": "closed_reaches_final_score",
                },
                {
                    "dp_id": "L0.cost.cac",
                    "score_target": "fundamental_score",
                    "score_relevant": True,
                    "closure_status": "valid_real_but_formula_unmapped",
                },
                {
                    "dp_id": "L0.tech.substitute_tech",
                    "score_target": "fundamental_score",
                    "score_relevant": True,
                    "closure_status": "no_valid_a_share_target_data",
                },
                {
                    "dp_id": "L9.audit.note",
                    "score_target": "audit_only",
                    "score_relevant": False,
                    "closure_status": "non_scoring_spec",
                },
            ],
        },
    )
    _write_json(
        dry_run_path,
        {
            "summary": {
                "bridge_signal_ready_count": 2,
                "final_score_target_ready_count": 2,
            },
            "rows": [
                {"dp_id": "L0.cost.cac", "bridge_signal_ready": True},
                {"dp_id": "L0.tech.substitute_tech", "bridge_signal_ready": True},
            ],
        },
    )
    _write_json(
        staging_path,
        {
            "summary": {
                "staging_payload_count": 2,
                "staging_payload_bridge_ready_count": 1,
            },
            "rows": [
                {"dp_id": "L0.cost.cac", "payload_status": "deterministic_neutral_review_payload"},
                {"dp_id": "L0.tech.substitute_tech", "payload_status": "requires_generator_output"},
            ],
        },
    )
    _write_json(
        value_contracts_path,
        {
            "summary": {
                "bridge_validated_concrete_count": 1,
                "placeholder_payload_valid_count": 1,
            },
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "validation_mode": "concrete",
                    "contract_valid": True,
                },
                {
                    "dp_id": "L0.tech.substitute_tech",
                    "validation_mode": "placeholder",
                    "contract_valid": True,
                },
            ],
        },
    )
    _write_json(
        review_manifest_path,
        {
            "summary": {
                "bridge_ready_concrete_count": 1,
                "review_gated_unknown_count": 1,
            },
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "review_entry_status": "review_ready_concrete",
                    "bridge_ready_concrete": True,
                    "safe_to_upsert_without_review": False,
                    "production_write_allowed": False,
                },
                {
                    "dp_id": "L0.tech.substitute_tech",
                    "review_entry_status": "review_gated_unknown",
                    "bridge_ready_concrete": False,
                    "safe_to_upsert_without_review": False,
                    "production_write_allowed": False,
                },
            ],
        },
    )
    _write_json(
        approval_gate_path,
        {
            "summary": {
                "review_ready_concrete_count": 1,
                "approval_missing_count": 1,
                "approved_runtime_write_count": 0,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
            },
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "final_score_target_ready": True,
                    "runtime_write_allowed": False,
                    "production_write_allowed": False,
                }
            ],
        },
    )
    _write_json(
        unknown_closure_path,
        {
            "summary": {
                "unknown_closure_row_count": 1,
                "auto_known_ready_count": 0,
                "approval_ready_count": 0,
            },
            "rows": [
                {
                    "dp_id": "L0.tech.substitute_tech",
                    "closure_route": "market_document_event_evidence",
                    "next_action_bucket": "event_text_classification_required",
                }
            ],
        },
    )

    report = build_report(
        field_closure_path=field_closure_path,
        dry_run_path=dry_run_path,
        staging_path=staging_path,
        value_contracts_path=value_contracts_path,
        review_manifest_path=review_manifest_path,
        approval_gate_path=approval_gate_path,
        unknown_closure_path=unknown_closure_path,
    )

    assert report["summary"]["current_final_score_numeric_dp_ids"] == 1
    assert report["summary"]["current_score_relevant_not_final_score_dp_ids"] == 2
    assert report["summary"]["valid_runtime_information_formula_unmapped_dp_ids"] == 1
    assert report["summary"]["review_ready_concrete_final_score_dp_ids"] == 1
    assert report["summary"]["review_gated_unknown_dp_ids"] == 1
    assert report["summary"]["approved_runtime_write_count"] == 0
    assert report["summary"]["safe_to_upsert_without_review_count"] == 0
    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.cost.cac"]["candidate_gate_status"] == (
        "review_ready_concrete_approval_missing"
    )
    assert by_dp["L0.tech.substitute_tech"]["candidate_gate_status"] == (
        "review_gated_unknown"
    )
    assert by_dp["L0.tech.substitute_tech"]["final_score_target_ready_after_review"] is False
    assert "Current numeric final-score fields: `1` / `3`" in render_markdown(report)
