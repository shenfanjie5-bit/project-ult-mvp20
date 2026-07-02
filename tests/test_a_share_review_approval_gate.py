import json
from pathlib import Path

from scripts import audit_a_share_review_approval_gate as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _payload(dp_id: str, score_target: str, data_status: str, value_json: dict) -> dict:
    return {
        "target_dp_id": dp_id,
        "score_target": score_target,
        "data_status": data_status,
        "bridge_entry_data_status": "Known" if data_status == "NotApplicable" else data_status,
        "value_json": value_json,
        "confidence": 0.6,
        "evidence_refs": ["docs/audit/a_share_review_staging_manifest_2026-06-19.json"],
        "rationale": "review packet rationale",
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "production_write_allowed": False,
    }


def _manifest_row(
    dp_id: str,
    score_target: str,
    data_status: str,
    review_entry_status: str,
    value_json: dict,
) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "source_kind": "unit_test",
        "source_report": "unit.json",
        "review_payload": _payload(dp_id, score_target, data_status, value_json),
        "data_status": data_status,
        "review_entry_status": review_entry_status,
        "contract_validation": {"contract_valid": True, "validation_errors": []},
        "bridge_ready_concrete": review_entry_status == "review_ready_concrete",
        "safe_to_upsert_without_review": False,
        "production_write_allowed": False,
    }


def _approval(dp_id: str, payload_sha256: str, **overrides: object) -> dict:
    record = {
        "approval_id": f"approval-{dp_id}",
        "dp_id": dp_id,
        "approval_status": "approved",
        "approval_scope": "runtime_write",
        "reviewer": "reviewer@example.com",
        "approved_at": "2026-06-19T12:00:00+08:00",
        "payload_sha256": payload_sha256,
        "risk_acknowledged": True,
    }
    record.update(overrides)
    return record


def test_approval_gate_requires_separate_approval_for_concrete_packets(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    approvals_path = tmp_path / "missing-approvals.json"
    _write_json(
        manifest_path,
        {
            "rows": [
                _manifest_row(
                    "L0.cost.cac",
                    "fundamental_score",
                    "Known",
                    "review_ready_concrete",
                    {"score": 0.1},
                ),
                _manifest_row(
                    "L7.trade.gamma",
                    "gamma_multiplier",
                    "NotApplicable",
                    "review_ready_concrete",
                    {"multiplier": 1.0},
                ),
                _manifest_row(
                    "L0.compete.price_war",
                    "fundamental_score",
                    "Unknown",
                    "review_gated_unknown",
                    {
                        "review_required": True,
                        "blocked_reason": "event_text_classification_required",
                    },
                ),
            ]
        },
    )

    report = audit.build_report(manifest_path=manifest_path, approvals_path=approvals_path)

    assert report["summary"]["review_manifest_entries"] == 3
    assert report["summary"]["review_ready_concrete_count"] == 2
    assert report["summary"]["review_gated_unknown_count"] == 1
    assert report["summary"]["approval_records_seen"] == 0
    assert report["summary"]["approval_required_count"] == 2
    assert report["summary"]["approval_missing_count"] == 2
    assert report["summary"]["approved_runtime_write_count"] == 0
    assert report["summary"]["write_plan_count"] == 0
    assert report["summary"]["rejected_approval_count"] == 0
    assert report["summary"]["not_approvable_unknown_count"] == 1
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["approval_gate_status_counts"] == {
        "approval_missing": 2,
        "not_approvable_unknown": 1,
    }
    assert all(len(row["payload_sha256"]) == 64 for row in report["rows"])
    assert "Missing approvals: `2`" in audit.render_markdown(report)


def test_valid_approval_creates_read_only_write_plan(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    approvals_path = tmp_path / "approvals.json"
    row = _manifest_row(
        "L0.cost.cac",
        "fundamental_score",
        "Known",
        "review_ready_concrete",
        {"score": 0.1},
    )
    payload_hash = audit._payload_hash(row["review_payload"])
    _write_json(manifest_path, {"rows": [row]})
    _write_json(approvals_path, {"approvals": [_approval("L0.cost.cac", payload_hash)]})

    report = audit.build_report(manifest_path=manifest_path, approvals_path=approvals_path)

    assert report["summary"]["approval_records_seen"] == 1
    assert report["summary"]["approval_missing_count"] == 0
    assert report["summary"]["approved_runtime_write_count"] == 1
    assert report["summary"]["write_plan_count"] == 1
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["rows"][0]["approval_gate_status"] == "approved_runtime_write"
    assert report["rows"][0]["runtime_write_allowed"] is True
    assert report["rows"][0]["write_plan_entry"]["value_json"] == {"score": 0.1}
    assert report["write_plan"][0]["production_write_allowed"] is False


def test_gate_rejects_hash_mismatch_and_unknown_packet_approval(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    approvals_path = tmp_path / "approvals.json"
    concrete = _manifest_row(
        "L0.cost.cac",
        "fundamental_score",
        "Known",
        "review_ready_concrete",
        {"score": 0.1},
    )
    unknown = _manifest_row(
        "L0.compete.price_war",
        "fundamental_score",
        "Unknown",
        "review_gated_unknown",
        {"review_required": True, "blocked_reason": "classification_required"},
    )
    _write_json(manifest_path, {"rows": [concrete, unknown]})
    _write_json(
        approvals_path,
        {
            "approvals": [
                _approval("L0.cost.cac", "0" * 64),
                _approval("L0.compete.price_war", audit._payload_hash(unknown["review_payload"])),
            ]
        },
    )

    report = audit.build_report(manifest_path=manifest_path, approvals_path=approvals_path)

    assert report["summary"]["approval_records_seen"] == 2
    assert report["summary"]["approval_missing_count"] == 0
    assert report["summary"]["approved_runtime_write_count"] == 0
    assert report["summary"]["write_plan_count"] == 0
    assert report["summary"]["rejected_approval_count"] == 2
    assert report["summary"]["approval_gate_status_counts"] == {
        "approval_rejected": 1,
        "not_approvable_unknown_approval_rejected": 1,
    }
    statuses = {row["dp_id"]: row["approval_gate_status"] for row in report["rows"]}
    assert statuses["L0.cost.cac"] == "approval_rejected"
    assert statuses["L0.compete.price_war"] == "not_approvable_unknown_approval_rejected"


def test_gate_rejects_empty_approval_id(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    approvals_path = tmp_path / "approvals.json"
    row = _manifest_row(
        "L0.cost.cac",
        "fundamental_score",
        "Known",
        "review_ready_concrete",
        {"score": 0.1},
    )
    payload_hash = audit._payload_hash(row["review_payload"])
    _write_json(manifest_path, {"rows": [row]})
    _write_json(
        approvals_path,
        {"approvals": [_approval("L0.cost.cac", payload_hash, approval_id="")]},
    )

    report = audit.build_report(manifest_path=manifest_path, approvals_path=approvals_path)

    assert report["summary"]["approved_runtime_write_count"] == 0
    assert report["summary"]["write_plan_count"] == 0
    assert report["summary"]["rejected_approval_count"] == 1
    assert report["rows"][0]["approval_gate_status"] == "approval_rejected"
    assert "approval_id must be non-empty" in report["rows"][0][
        "approval_validation_errors"
    ]
