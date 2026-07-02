import json
from pathlib import Path

from scripts import audit_a_share_unknown_penetration_confirmed_known_drafts as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _payload() -> dict:
    return {
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
        "rationale": "reviewed penetration value policy",
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "production_write_allowed": False,
    }


def test_confirmed_known_drafts_block_when_confirmation_gate_missing(
    tmp_path: Path,
) -> None:
    confirmation_gate_path = tmp_path / "confirmation_gate.json"
    _write_json(
        confirmation_gate_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "score_target": "fundamental_score",
                    "payload_sha256": "a" * 64,
                    "confirmation_gate_status": "confirmation_missing",
                    "confirmation_validation_errors": ["missing confirmation record"],
                    "final_score_target_ready": True,
                }
            ],
            "known_draft_candidates": [],
        },
    )

    report = audit.build_report(confirmation_gate_path=confirmation_gate_path)

    assert report["summary"]["confirmation_gate_row_count"] == 1
    assert report["summary"]["confirmed_value_policy_candidate_count"] == 0
    assert report["summary"]["known_draft_row_count"] == 1
    assert report["summary"]["known_draft_emitted_count"] == 0
    assert report["summary"]["known_draft_blocked_count"] == 1
    assert report["summary"]["known_draft_contract_valid_count"] == 0
    assert report["summary"]["ready_for_review_staging_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["runtime_write_allowed_count"] == 0
    row = report["rows"][0]
    assert row["known_draft_status"] == "blocked_confirmation_missing"
    assert row["draft_payload"] is None
    assert row["ready_for_review_staging"] is False
    assert "Known drafts emitted: `0`" in audit.render_markdown(report)


def test_confirmed_known_drafts_emit_review_only_candidate_after_confirmation(
    tmp_path: Path,
) -> None:
    confirmation_gate_path = tmp_path / "confirmation_gate.json"
    payload = _payload()
    payload_sha256 = audit._payload_hash(payload)
    _write_json(
        confirmation_gate_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "score_target": "fundamental_score",
                    "payload_sha256": payload_sha256,
                    "confirmation_gate_status": "confirmed_value_policy",
                    "final_score_target_ready": True,
                }
            ],
            "known_draft_candidates": [
                {
                    "dp_id": "L0.demand.penetration",
                    "score_target": "fundamental_score",
                    "data_status": "Known",
                    "payload_sha256": payload_sha256,
                    "proposed_payload": payload,
                    "confirmation": {
                        "confirmation_id": "confirm-1",
                        "reviewer": "reviewer@example.com",
                        "confirmed_at": "2026-06-19T21:00:00+08:00",
                        "confirmation_scope": "value_policy",
                    },
                    "known_draft_emission_allowed": True,
                    "runtime_write_allowed": False,
                    "production_write_allowed": False,
                }
            ],
        },
    )

    report = audit.build_report(confirmation_gate_path=confirmation_gate_path)

    assert report["summary"]["confirmed_value_policy_candidate_count"] == 1
    assert report["summary"]["known_draft_emitted_count"] == 1
    assert report["summary"]["known_draft_blocked_count"] == 0
    assert report["summary"]["known_draft_contract_valid_count"] == 1
    assert report["summary"]["ready_for_review_staging_count"] == 1
    assert report["summary"]["final_score_target_ready_count"] == 1
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["runtime_write_allowed_count"] == 0
    row = report["rows"][0]
    assert row["known_draft_status"] == "known_draft_emitted"
    assert row["draft_payload"]["value_json"]["score"] == 0.4
    assert row["known_draft_contract_valid"] is True
    assert row["ready_for_review_staging"] is True
    assert row["approval_ready"] is False
    assert row["runtime_write_allowed"] is False


def test_confirmed_known_drafts_reject_payload_hash_mismatch(tmp_path: Path) -> None:
    confirmation_gate_path = tmp_path / "confirmation_gate.json"
    payload = _payload()
    _write_json(
        confirmation_gate_path,
        {
            "known_draft_candidates": [
                {
                    "dp_id": "L0.demand.penetration",
                    "score_target": "fundamental_score",
                    "payload_sha256": "0" * 64,
                    "proposed_payload": payload,
                    "confirmation": {
                        "confirmation_id": "confirm-1",
                        "reviewer": "reviewer@example.com",
                        "confirmed_at": "2026-06-19T21:00:00+08:00",
                    },
                }
            ]
        },
    )

    report = audit.build_report(confirmation_gate_path=confirmation_gate_path)

    assert report["summary"]["known_draft_emitted_count"] == 0
    assert report["summary"]["known_draft_contract_invalid_count"] == 1
    row = report["rows"][0]
    assert row["known_draft_status"] == "known_draft_contract_invalid"
    assert "payload_sha256 must match proposed_payload" in row[
        "known_draft_validation_errors"
    ]
