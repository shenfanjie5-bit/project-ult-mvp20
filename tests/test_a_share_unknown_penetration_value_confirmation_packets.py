import json
from pathlib import Path

from scripts import audit_a_share_unknown_penetration_value_confirmation_packets as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_penetration_value_confirmation_packet_is_review_only(
    tmp_path: Path,
) -> None:
    value_policy_draft_path = tmp_path / "value_policy_draft.json"
    value_selection_gate_path = tmp_path / "value_selection_gate.json"
    proposed_payload = {
        "target_dp_id": "L0.demand.penetration",
        "score_target": "fundamental_score",
        "data_status": "Known",
        "bridge_entry_data_status": "Known",
        "confidence": 0.36,
        "value_json": {
            "score": 0.4,
            "raw_value": 40.0,
            "unit": "percent",
            "review_required": True,
            "bounds": {"score_min": 0.0, "score_max": 1.0},
        },
        "evidence_refs": ["unit:evidence"],
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
    }
    _write_json(
        value_policy_draft_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "score_target": "fundamental_score",
                    "value_review_packet_id": "p1",
                    "source_scope_confirmed": True,
                    "proposed_raw_value": 40.0,
                    "proposed_value_json": proposed_payload["value_json"],
                    "proposed_payload": proposed_payload,
                    "bridge_validation": {"final_score_target_ready": True},
                    "draft_contract_valid": True,
                    "review_status": "review_required",
                    "known_draft_sufficient": False,
                    "approval_ready": False,
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
    _write_json(
        value_selection_gate_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "selection_gate_status": "review_value_policy_draft_ready",
                    "value_policy_draft_ready": True,
                }
            ]
        },
    )

    report = audit.build_report(
        value_policy_draft_path=value_policy_draft_path,
        value_selection_gate_path=value_selection_gate_path,
    )

    assert report["summary"]["value_confirmation_packet_count"] == 1
    assert report["summary"]["review_required_packet_count"] == 1
    assert report["summary"]["source_scope_confirmed_count"] == 1
    assert report["summary"]["proposed_value_json_count"] == 1
    assert report["summary"]["final_score_target_ready_count"] == 1
    assert report["summary"]["value_policy_draft_ready_count"] == 1
    assert report["summary"]["confirmation_record_template_count"] == 1
    assert report["summary"]["confirmation_record_template_contract_valid_count"] == 1
    assert report["summary"]["confirmation_packet_contract_valid_count"] == 1
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["runtime_write_allowed_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    row = report["rows"][0]
    expected_hash = audit._payload_hash(proposed_payload)
    assert row["payload_sha256"] == expected_hash
    assert row["confirmation_record_template"]["payload_sha256"] == expected_hash
    assert row["confirmation_record_template"]["confirmation_status"] == ""
    assert row["confirmation_record_template"]["confirmation_scope"] == "value_policy"
    assert row["confirmation_record_template"]["value_selection_accepted"] is False
    assert row["confirmation_record_template"]["risk_acknowledged"] is False
    assert row["confirmation_packet_contract_valid"] is True
    assert row["known_draft_sufficient"] is False
    assert row["approval_ready"] is False
    assert row["runtime_write_allowed"] is False
    markdown = audit.render_markdown(report)
    assert "Confirmation packets: `1`" in markdown
    assert "Runtime writes allowed: `0`" in markdown


def test_penetration_value_confirmation_packet_rejects_missing_gate_ready(
    tmp_path: Path,
) -> None:
    value_policy_draft_path = tmp_path / "value_policy_draft.json"
    value_selection_gate_path = tmp_path / "value_selection_gate.json"
    _write_json(
        value_policy_draft_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "score_target": "fundamental_score",
                    "source_scope_confirmed": True,
                    "proposed_value_json": {"score": 0.4, "review_required": True},
                    "proposed_payload": {
                        "review_status": "review_required",
                        "safe_to_upsert_without_review": False,
                    },
                    "bridge_validation": {"final_score_target_ready": True},
                    "draft_contract_valid": True,
                    "known_draft_sufficient": False,
                    "approval_ready": False,
                    "runtime_write_allowed": False,
                    "production_write_allowed": False,
                }
            ]
        },
    )
    _write_json(
        value_selection_gate_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "selection_gate_status": "review_value_selection_required",
                    "value_policy_draft_ready": False,
                }
            ]
        },
    )

    report = audit.build_report(
        value_policy_draft_path=value_policy_draft_path,
        value_selection_gate_path=value_selection_gate_path,
    )

    assert report["summary"]["confirmation_packet_contract_valid_count"] == 0
    assert report["summary"]["confirmation_packet_contract_invalid_count"] == 1
    assert report["summary"]["runtime_write_allowed_count"] == 0
    assert "selection gate must mark value_policy_draft_ready" in report["rows"][0][
        "confirmation_packet_validation_errors"
    ]
