import json
from pathlib import Path

from scripts import audit_a_share_unknown_penetration_value_confirmation_gate as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _packet(payload_sha256: str = "a" * 64) -> dict:
    return {
        "dp_id": "L0.demand.penetration",
        "score_target": "fundamental_score",
        "payload_sha256": payload_sha256,
        "proposed_raw_value": 40.0,
        "proposed_value_json": {
            "score": 0.4,
            "raw_value": 40.0,
            "unit": "percent",
        },
        "proposed_payload": {
            "target_dp_id": "L0.demand.penetration",
            "score_target": "fundamental_score",
            "data_status": "Known",
            "value_json": {"score": 0.4},
        },
        "final_score_target_ready": True,
        "value_policy_draft_ready": True,
        "confirmation_packet_contract_valid": True,
        "confirmation_record_template_contract_valid": True,
    }


def _confirmation(payload_sha256: str = "a" * 64, **overrides: object) -> dict:
    record = {
        "confirmation_id": "confirm-penetration-1",
        "dp_id": "L0.demand.penetration",
        "confirmation_status": "confirmed",
        "confirmation_scope": "value_policy",
        "reviewer": "reviewer@example.com",
        "confirmed_at": "2026-06-19T21:00:00+08:00",
        "payload_sha256": payload_sha256,
        "value_selection_accepted": True,
        "bounds_accepted": True,
        "formula_policy_accepted": True,
        "applicability_accepted": True,
        "risk_acknowledged": True,
    }
    record.update(overrides)
    return record


def test_confirmation_gate_blocks_when_confirmation_missing(tmp_path: Path) -> None:
    packets_path = tmp_path / "packets.json"
    confirmations_path = tmp_path / "confirmations.json"
    _write_json(packets_path, {"rows": [_packet()]})

    report = audit.build_report(
        packets_path=packets_path,
        confirmations_path=confirmations_path,
    )

    assert report["summary"]["confirmation_packet_count"] == 1
    assert report["summary"]["confirmation_records_seen"] == 0
    assert report["summary"]["confirmation_missing_count"] == 1
    assert report["summary"]["confirmed_value_policy_count"] == 0
    assert report["summary"]["known_draft_candidate_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["runtime_write_allowed_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    row = report["rows"][0]
    assert row["confirmation_gate_status"] == "confirmation_missing"
    assert row["known_draft_emission_allowed"] is False
    assert row["known_draft_candidate"] is None
    assert "missing confirmation record" in row["confirmation_validation_errors"]
    assert "Missing confirmations: `1`" in audit.render_markdown(report)


def test_confirmation_gate_allows_known_draft_candidate_after_full_confirmation(
    tmp_path: Path,
) -> None:
    packets_path = tmp_path / "packets.json"
    confirmations_path = tmp_path / "confirmations.json"
    payload_hash = "b" * 64
    _write_json(packets_path, {"rows": [_packet(payload_hash)]})
    _write_json(confirmations_path, {"confirmations": [_confirmation(payload_hash)]})

    report = audit.build_report(
        packets_path=packets_path,
        confirmations_path=confirmations_path,
    )

    assert report["summary"]["confirmation_packet_count"] == 1
    assert report["summary"]["confirmation_records_seen"] == 1
    assert report["summary"]["confirmation_missing_count"] == 0
    assert report["summary"]["rejected_confirmation_count"] == 0
    assert report["summary"]["confirmed_value_policy_count"] == 1
    assert report["summary"]["known_draft_candidate_count"] == 1
    assert report["summary"]["known_draft_emission_allowed_count"] == 1
    assert report["summary"]["runtime_write_allowed_count"] == 0
    row = report["rows"][0]
    assert row["confirmation_gate_status"] == "confirmed_value_policy"
    assert row["known_draft_emission_allowed"] is True
    assert row["known_draft_candidate"]["payload_sha256"] == payload_hash
    assert row["known_draft_candidate"]["runtime_write_allowed"] is False
    assert report["known_draft_candidates"][0]["production_write_allowed"] is False


def test_confirmation_gate_rejects_hash_mismatch_and_missing_acceptance(
    tmp_path: Path,
) -> None:
    packets_path = tmp_path / "packets.json"
    confirmations_path = tmp_path / "confirmations.json"
    _write_json(packets_path, {"rows": [_packet("c" * 64)]})
    _write_json(
        confirmations_path,
        {
            "rows": [
                _confirmation(
                    "d" * 64,
                    formula_policy_accepted=False,
                )
            ]
        },
    )

    report = audit.build_report(
        packets_path=packets_path,
        confirmations_path=confirmations_path,
    )

    assert report["summary"]["confirmation_records_seen"] == 1
    assert report["summary"]["rejected_confirmation_count"] == 1
    assert report["summary"]["confirmed_value_policy_count"] == 0
    assert report["summary"]["known_draft_candidate_count"] == 0
    row = report["rows"][0]
    assert row["confirmation_gate_status"] == "confirmation_rejected"
    assert "payload_sha256 must match the canonical proposed payload hash" in row[
        "confirmation_validation_errors"
    ]
    assert "formula_policy_accepted must be true" in row[
        "confirmation_validation_errors"
    ]
