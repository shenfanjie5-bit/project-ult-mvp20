from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_a_share_approval_target_scope_readiness as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_approval_target_scope_readiness_classifies_approval_only_gap(
    tmp_path: Path,
) -> None:
    packets_path = tmp_path / "approval_packets.json"
    risk_path = tmp_path / "risk.json"
    samples_path = tmp_path / "samples.json"
    target_scope_path = tmp_path / "target_scope.json"

    _write_json(
        packets_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "score_target": "fundamental_score",
                    "source_kind": "local_structured_policy_pilot",
                    "data_status": "Known",
                    "confidence": 0.36,
                    "final_score_target_ready": True,
                    "approval_gate_status": "approval_missing",
                    "approval_payload_hash_matches_manifest": True,
                    "approval_record_template_contract_valid": True,
                    "value_json": {"score": 0.1},
                },
                {
                    "dp_id": "L0.policy.regulation",
                    "score_target": "risk_discount",
                    "source_kind": "event_text_policy_pilot",
                    "data_status": "Known",
                    "confidence": 0.44,
                    "final_score_target_ready": True,
                    "approval_gate_status": "approval_missing",
                    "approval_payload_hash_matches_manifest": True,
                    "approval_record_template_contract_valid": True,
                    "value_json": {"score": -0.2},
                },
                {
                    "dp_id": "L9.media.short_report",
                    "score_target": "expectation_gap",
                    "source_kind": "deterministic_candidate_staging",
                    "data_status": "Known",
                    "confidence": 0.9,
                    "final_score_target_ready": True,
                    "approval_gate_status": "approval_missing",
                    "approval_payload_hash_matches_manifest": True,
                    "approval_record_template_contract_valid": True,
                    "value_json": {"score": 0.0},
                },
            ]
        },
    )
    _write_json(
        risk_path,
        {
            "rows": [
                {"dp_id": "L0.cost.cac", "risk_class": "bulk_structured_review_candidate"},
                {
                    "dp_id": "L0.policy.regulation",
                    "risk_class": "individual_event_evidence_review_required",
                },
                {"dp_id": "L9.media.short_report", "risk_class": "deterministic"},
            ]
        },
    )
    _write_json(
        samples_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "source_sample_route": "bulk_review_source_sample",
                    "source_sample_reviewer_packet_complete": True,
                    "source_sample_payload_matches_candidate": True,
                },
                {
                    "dp_id": "L0.policy.regulation",
                    "source_sample_route": "event_approval_source_sample",
                    "source_sample_reviewer_packet_complete": True,
                    "source_sample_payload_matches_candidate": True,
                },
                {
                    "dp_id": "L9.media.short_report",
                    "source_sample_route": "deterministic",
                    "source_sample_reviewer_packet_complete": True,
                    "source_sample_payload_matches_candidate": True,
                },
            ]
        },
    )
    _write_json(
        target_scope_path,
        {"summary": {"target_scope_candidate_count": 2}},
    )

    report = audit.build_report(
        approval_packets_path=packets_path,
        risk_review_path=risk_path,
        source_sample_coverage_path=samples_path,
        target_scope_path=target_scope_path,
    )

    summary = report["summary"]
    assert summary["approval_packet_count"] == 3
    assert summary["source_sample_reviewer_packet_complete_count"] == 3
    assert summary["source_sample_payload_match_count"] == 3
    assert summary["target_scope_ready_after_approval_count"] == 1
    assert summary["target_scope_policy_required_count"] == 2
    assert summary["per_stock_value_materialization_required_count"] == 1
    assert summary["market_or_event_scope_policy_required_count"] == 1
    assert summary["approval_only_not_sufficient_count"] == 2
    assert summary["safe_runtime_write_after_approval_count"] == 1
    assert summary["runtime_materialization_ready_count"] == 0

    by_dp_id = {row["dp_id"]: row for row in report["rows"]}
    assert (
        by_dp_id["L0.cost.cac"]["required_next_step"]
        == "per_stock_value_materialization_required"
    )
    assert (
        by_dp_id["L0.policy.regulation"]["required_next_step"]
        == "market_or_event_scope_policy_required"
    )
    assert (
        by_dp_id["L9.media.short_report"]["target_scope_status"]
        == "existing_target_scope_policy_ready"
    )
