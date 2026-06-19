import json
from pathlib import Path

from scripts import audit_a_share_completion_next_actions as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _manifest_row(
    dp_id: str,
    score_target: str,
    data_status: str,
    review_entry_status: str,
    source_kind: str,
    value_json: dict | None = None,
) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "source_kind": source_kind,
        "source_report": "unit.json",
        "source_dependencies": ["dep.a"],
        "data_status": data_status,
        "review_entry_status": review_entry_status,
        "review_payload": {
            "target_dp_id": dp_id,
            "score_target": score_target,
            "data_status": data_status,
            "value_json": value_json or {"score": 0.1},
        },
    }


def _approval_row(
    dp_id: str,
    payload_sha256: str,
    approval_gate_status: str = "approval_missing",
) -> dict:
    return {
        "dp_id": dp_id,
        "payload_sha256": payload_sha256,
        "approval_gate_status": approval_gate_status,
        "runtime_write_allowed": approval_gate_status == "approved_runtime_write",
    }


def test_completion_next_actions_splits_approval_and_unknown_work(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    approval_gate_path = tmp_path / "approval_gate.json"
    rows = [
        _manifest_row(
            "L0.cost.cac",
            "fundamental_score",
            "Known",
            "review_ready_concrete",
            "local_structured_policy_pilot",
        ),
        _manifest_row(
            "L7.trade.gamma",
            "gamma_multiplier",
            "NotApplicable",
            "review_ready_concrete",
            "deterministic_candidate_staging",
        ),
        _manifest_row(
            "L0.compete.price_war",
            "fundamental_score",
            "Unknown",
            "review_gated_unknown",
            "event_text_policy_pilot",
            {
                "blocked_reason": "event_text_requires_price_war_classification",
                "required_policy": "price-war classification",
            },
        ),
        _manifest_row(
            "L0.cost.rent",
            "fundamental_score",
            "Unknown",
            "review_gated_unknown",
            "local_structured_policy_pilot",
            {"blocked_reason": "rent_mapping_required"},
        ),
        _manifest_row(
            "L0.demand.user_count",
            "fundamental_score",
            "Unknown",
            "review_gated_unknown",
            "local_structured_text_policy_pilot",
            {"blocked_reason": "qa_recent_requires_customer_user_extraction"},
        ),
        _manifest_row(
            "L0.demand.replacement",
            "fundamental_score",
            "Unknown",
            "review_gated_unknown",
            "local_single_dependency_policy_pilot",
            {"blocked_reason": "replacement_policy_required"},
        ),
        _manifest_row(
            "L6.mult.dcf",
            "valuation_rerating",
            "Unknown",
            "review_gated_unknown",
            "manual_policy_pilot",
            {"required_assumptions": ["discount_rate"]},
        ),
    ]
    _write_json(manifest_path, {"rows": rows})
    _write_json(
        approval_gate_path,
        {
            "summary": {"approved_runtime_write_count": 1, "write_plan_count": 1},
            "rows": [
                _approval_row(
                    "L0.cost.cac",
                    audit._payload_hash(rows[0]["review_payload"]),
                ),
                _approval_row(
                    "L7.trade.gamma",
                    audit._payload_hash(rows[1]["review_payload"]),
                    approval_gate_status="approved_runtime_write",
                ),
            ],
        },
    )

    report = audit.build_report(
        manifest_path=manifest_path,
        approval_gate_path=approval_gate_path,
    )

    assert report["summary"]["actionable_gap_count"] == 7
    assert report["summary"]["approval_ready_packet_count"] == 1
    assert report["summary"]["runtime_write_plan_ready_count"] == 1
    assert report["summary"]["approval_record_template_count"] == 1
    assert report["summary"]["unknown_resolution_required_count"] == 5
    assert report["summary"]["event_text_classification_required_count"] == 1
    assert report["summary"]["local_structured_mapping_required_count"] == 1
    assert report["summary"]["structured_text_extraction_required_count"] == 1
    assert report["summary"]["single_dependency_policy_required_count"] == 1
    assert report["summary"]["manual_assumption_review_required_count"] == 1
    assert report["summary"]["approved_runtime_write_count"] == 1
    assert report["summary"]["write_plan_count"] == 1
    assert report["summary"]["production_write_allowed_count"] == 0
    buckets = {row["dp_id"]: row["next_action_bucket"] for row in report["rows"]}
    assert buckets["L0.cost.cac"] == "human_approval_required"
    assert buckets["L7.trade.gamma"] == "runtime_write_plan_ready"
    assert buckets["L0.compete.price_war"] == "event_text_classification_required"
    assert buckets["L0.cost.rent"] == "local_structured_mapping_required"
    assert buckets["L0.demand.user_count"] == "structured_text_extraction_required"
    assert buckets["L0.demand.replacement"] == "single_dependency_policy_required"
    assert buckets["L6.mult.dcf"] == "manual_assumption_review_required"
    approval_template = next(
        row["approval_record_template"]
        for row in report["rows"]
        if row["dp_id"] == "L0.cost.cac"
    )
    assert approval_template["approval_status"] == ""
    assert approval_template["risk_acknowledged"] is False
    assert approval_template["template_status"] == "review_fill_required"
    assert approval_template["payload_sha256"] == audit._payload_hash(
        rows[0]["review_payload"]
    )
    assert "Approval templates: `1`" in audit.render_markdown(report)
    assert "Runtime write-plan ready: `1`" in audit.render_markdown(report)


def test_completion_next_actions_rejects_stale_approval_hash(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    approval_gate_path = tmp_path / "approval_gate.json"
    row = _manifest_row(
        "L7.trade.gamma",
        "gamma_multiplier",
        "NotApplicable",
        "review_ready_concrete",
        "deterministic_candidate_staging",
    )
    _write_json(manifest_path, {"rows": [row]})
    _write_json(
        approval_gate_path,
        {
            "summary": {"approved_runtime_write_count": 1, "write_plan_count": 1},
            "rows": [
                _approval_row(
                    "L7.trade.gamma",
                    "stale",
                    approval_gate_status="approved_runtime_write",
                ),
            ],
        },
    )

    report = audit.build_report(
        manifest_path=manifest_path,
        approval_gate_path=approval_gate_path,
    )

    assert report["summary"]["runtime_write_plan_ready_count"] == 0
    assert report["summary"]["approval_ready_packet_count"] == 1
    assert report["summary"]["approval_payload_hash_mismatch_count"] == 1
    only_row = report["rows"][0]
    assert only_row["approval_gate_status"] == "approval_hash_mismatch"
    assert only_row["runtime_write_allowed"] is False
    assert only_row["approval_record_template"]["payload_sha256"] == audit._payload_hash(
        row["review_payload"]
    )
