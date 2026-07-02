import json
from pathlib import Path

from scripts import audit_a_share_approval_review_packets as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _manifest_row(
    dp_id: str,
    review_entry_status: str,
    data_status: str,
    source_kind: str = "unit_source",
) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "source_kind": source_kind,
        "source_report": "unit.json",
        "source_dependencies": ["dep.a"],
        "data_status": data_status,
        "review_entry_status": review_entry_status,
        "review_payload": {
            "target_dp_id": dp_id,
            "score_target": "fundamental_score",
            "data_status": data_status,
            "bridge_entry_data_status": data_status,
            "value_json": {"score": 0.1} if data_status == "Known" else {"review_required": True},
            "confidence": 0.4,
            "evidence_refs": ["unit:evidence"],
            "rationale": "unit rationale",
        },
        "source_contract_valid": True,
        "bridge_ready_concrete": data_status == "Known",
        "bridge_validation": {
            "final_score_target_ready": data_status == "Known",
            "node_emitted": data_status == "Known",
        },
    }


def test_approval_review_packets_extract_only_concrete_packets(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    approval_gate_path = tmp_path / "approval_gate.json"
    next_actions_path = tmp_path / "next_actions.json"
    concrete = _manifest_row("L0.cost.cac", "review_ready_concrete", "Known")
    approved = _manifest_row("L7.trade.gamma", "review_ready_concrete", "Known")
    unknown = _manifest_row("L0.cost.rent", "review_gated_unknown", "Unknown")
    concrete_hash = audit._payload_hash(concrete["review_payload"])
    approved_hash = audit._payload_hash(approved["review_payload"])
    _write_json(manifest_path, {"rows": [concrete, approved, unknown]})
    _write_json(
        approval_gate_path,
        {
            "summary": {"approved_runtime_write_count": 1, "write_plan_count": 1},
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "approval_gate_status": "approval_missing",
                    "payload_sha256": concrete_hash,
                    "runtime_write_allowed": False,
                },
                {
                    "dp_id": "L7.trade.gamma",
                    "approval_gate_status": "approved_runtime_write",
                    "payload_sha256": approved_hash,
                    "runtime_write_allowed": True,
                }
            ]
        },
    )
    _write_json(
        next_actions_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "approval_record_template": {
                        "approval_id": "",
                        "dp_id": "L0.cost.cac",
                        "approval_status": "",
                        "approval_scope": "runtime_write",
                        "reviewer": "",
                        "approved_at": "",
                        "payload_sha256": concrete_hash,
                        "risk_acknowledged": False,
                        "template_status": "review_fill_required",
                    },
                }
            ]
        },
    )

    report = audit.build_report(
        manifest_path=manifest_path,
        approval_gate_path=approval_gate_path,
        next_actions_path=next_actions_path,
    )

    assert report["summary"]["approval_review_packet_count"] == 2
    assert report["summary"]["known_packet_count"] == 2
    assert report["summary"]["not_applicable_packet_count"] == 0
    assert report["summary"]["final_score_target_ready_count"] == 2
    assert report["summary"]["approval_missing_count"] == 1
    assert report["summary"]["approval_record_template_count"] == 1
    assert report["summary"]["approval_record_template_contract_valid_count"] == 1
    assert report["summary"]["approval_record_template_contract_invalid_count"] == 0
    assert report["summary"]["skipped_not_bridge_or_contract_ready_count"] == 0
    assert report["summary"]["approval_payload_hash_mismatch_count"] == 0
    assert report["summary"]["approved_runtime_write_count"] == 1
    assert report["summary"]["write_plan_count"] == 1
    assert report["summary"]["production_write_allowed_count"] == 0
    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.cost.cac"]["approval_record_template"]["approval_status"] == ""
    assert by_dp["L0.cost.cac"]["approval_record_template"]["risk_acknowledged"] is False
    assert by_dp["L0.cost.cac"]["approval_record_template_contract_valid"] is True
    assert by_dp["L7.trade.gamma"]["approval_record_template"] is None
    assert by_dp["L7.trade.gamma"]["runtime_write_allowed"] is True
    assert "Approval-review packets: `2`" in audit.render_markdown(report)
    assert "Write-plan entries: `1`" in audit.render_markdown(report)


def test_approval_review_packets_reject_template_contract_mismatch(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    approval_gate_path = tmp_path / "approval_gate.json"
    next_actions_path = tmp_path / "next_actions.json"
    concrete = _manifest_row("L0.cost.cac", "review_ready_concrete", "Known")
    concrete_hash = audit._payload_hash(concrete["review_payload"])
    _write_json(manifest_path, {"rows": [concrete]})
    _write_json(
        approval_gate_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "approval_gate_status": "approval_missing",
                    "payload_sha256": concrete_hash,
                }
            ]
        },
    )
    _write_json(
        next_actions_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "approval_record_template": {
                        "approval_id": "",
                        "dp_id": "L0.cost.labor",
                        "approval_status": "",
                        "approval_scope": "runtime_write",
                        "reviewer": "",
                        "approved_at": "",
                        "payload_sha256": concrete_hash,
                        "risk_acknowledged": False,
                        "template_status": "review_fill_required",
                    },
                }
            ]
        },
    )

    report = audit.build_report(
        manifest_path=manifest_path,
        approval_gate_path=approval_gate_path,
        next_actions_path=next_actions_path,
    )

    assert report["summary"]["approval_record_template_contract_valid_count"] == 0
    assert report["summary"]["approval_record_template_contract_invalid_count"] == 1
    assert report["summary"]["approval_record_template_invalid_dp_ids"] == [
        "L0.cost.cac"
    ]
    assert report["rows"][0]["approval_record_template_contract_valid"] is False
    assert "dp_id must match review packet" in report["rows"][0][
        "approval_record_template_validation_errors"
    ]


def test_approval_review_packets_skip_concrete_without_bridge_contract_ready(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    approval_gate_path = tmp_path / "approval_gate.json"
    next_actions_path = tmp_path / "next_actions.json"
    not_ready = _manifest_row("L0.cost.cac", "review_ready_concrete", "Known")
    not_ready["bridge_ready_concrete"] = False
    _write_json(manifest_path, {"rows": [not_ready]})
    _write_json(approval_gate_path, {"summary": {}, "rows": []})
    _write_json(next_actions_path, {"rows": []})

    report = audit.build_report(
        manifest_path=manifest_path,
        approval_gate_path=approval_gate_path,
        next_actions_path=next_actions_path,
    )

    assert report["summary"]["approval_review_packet_count"] == 0
    assert report["summary"]["skipped_not_bridge_or_contract_ready_count"] == 1
    assert report["summary"]["skipped_not_bridge_or_contract_ready_dp_ids"] == [
        "L0.cost.cac"
    ]
