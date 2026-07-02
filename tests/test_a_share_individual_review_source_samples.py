import json
from pathlib import Path

from scripts import audit_a_share_individual_review_source_samples as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _candidate(
    dp_id: str,
    *,
    risk_class: str = "individual_structured_review_required",
    source_kind: str = "local_structured_text_policy_pilot",
    score_target: str = "fundamental_score",
    include_runtime_ref: bool = True,
) -> dict:
    source_dependencies = ["L9.disclosure.qa_recent"]
    evidence_refs = [
        "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json",
        "docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json",
    ]
    if include_runtime_ref:
        evidence_refs.append("runtime:realtime_current:L9.disclosure.qa_recent")
    components = {"sample_avg": 1.0}
    if source_kind == "local_structured_text_policy_pilot":
        components["evidence_examples"] = [
            {
                "ts_code": "000001.SZ",
                "date": "20260619",
                "keyword_hits": ["订单"],
                "question": "订单情况？",
                "answer": "订单增长。",
            }
        ]
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "source_kind": source_kind,
        "source_report": "docs/audit/source.json",
        "source_dependencies": source_dependencies,
        "data_status": "Known",
        "payload_sha256": f"hash-{dp_id}",
        "confidence": 0.4,
        "value_json": {
            "score": 0.1,
            "drivers": source_dependencies,
            "components": components,
        },
        "evidence_refs": evidence_refs,
        "rationale": "unit rationale",
        "approval_record_template": {
            "approval_id": "",
            "dp_id": dp_id,
            "approval_status": "",
            "approval_scope": "runtime_write",
            "reviewer": "",
            "approved_at": "",
            "payload_sha256": f"hash-{dp_id}",
            "risk_acknowledged": False,
            "template_status": "review_fill_required",
        },
        "approval_record_template_contract_valid": True,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "_risk_class": risk_class,
    }


def _source_row(candidate: dict) -> dict:
    return {
        "dp_id": candidate["dp_id"],
        "draft_status": "draft_known_review_required",
        "draft_payload": {
            "target_dp_id": candidate["dp_id"],
            "score_target": candidate["score_target"],
            "data_status": candidate["data_status"],
            "value_json": candidate["value_json"],
            "confidence": candidate["confidence"],
            "evidence_refs": candidate["evidence_refs"],
            "rationale": candidate["rationale"],
        },
        "contract_validation": {"contract_valid": True, "validation_errors": []},
        "bridge_validation": {"final_score_target_ready": True},
    }


def _risk_row(candidate: dict) -> dict:
    return {
        "dp_id": candidate["dp_id"],
        "risk_class": candidate["_risk_class"],
        "risk_reasons": ["unit reason"],
    }


def test_individual_review_source_samples_validate_traceability(tmp_path: Path) -> None:
    structured = _candidate("L0.demand.user_count")
    event_policy = _candidate(
        "L8.shock.supply_break",
        risk_class="individual_policy_review_required",
        source_kind="event_text_policy_pilot",
        score_target="risk_discount",
    )
    _write_json(tmp_path / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json", {})
    _write_json(
        tmp_path / "docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json",
        {},
    )
    _write_json(
        tmp_path / "docs/audit/source.json",
        {"rows": [_source_row(structured), _source_row(event_policy)]},
    )
    _write_json(
        tmp_path / "risk.json",
        {"rows": [_risk_row(structured), _risk_row(event_policy)]},
    )
    _write_json(
        tmp_path / "event-source.json",
        {"rows": [{"dp_id": event_policy["dp_id"], "reviewer_packet_complete": True}]},
    )
    approval_path = tmp_path / "approval.json"
    _write_json(approval_path, {"rows": [structured, event_policy]})

    report = audit.build_report(
        approval_path=approval_path,
        risk_path=tmp_path / "risk.json",
        event_source_path=tmp_path / "event-source.json",
        repo_root=tmp_path,
    )
    by_dp = {row["dp_id"]: row for row in report["rows"]}

    assert report["summary"]["individual_review_source_sample_count"] == 2
    assert report["summary"]["individual_structured_review_required_count"] == 1
    assert report["summary"]["individual_policy_review_required_count"] == 1
    assert report["summary"]["source_payload_matches_candidate_count"] == 2
    assert report["summary"]["evidence_refs_complete_count"] == 2
    assert report["summary"]["text_sample_evidence_ready_count"] == 1
    assert report["summary"]["event_source_sample_reviewer_packet_complete_count"] == 1
    assert report["summary"]["individual_review_template_contract_valid_count"] == 2
    assert report["summary"]["individual_review_template_blank_pending_count"] == 2
    assert report["summary"]["reviewer_packet_complete_count"] == 2
    assert report["summary"]["runtime_write_allowed_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert (
        by_dp["L0.demand.user_count"]["individual_review_template"]["review_scope"]
        == "structured_proxy_semantic_review"
    )
    assert (
        by_dp["L8.shock.supply_break"]["individual_review_template"]["review_scope"]
        == "event_score_target_policy_review"
    )
    assert "Reviewer packets complete: `2`" in audit.render_markdown(report)


def test_individual_review_source_samples_flags_missing_runtime_ref(tmp_path: Path) -> None:
    candidate = _candidate("L0.demand.user_count", include_runtime_ref=False)
    _write_json(tmp_path / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json", {})
    _write_json(
        tmp_path / "docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json",
        {},
    )
    _write_json(tmp_path / "docs/audit/source.json", {"rows": [_source_row(candidate)]})
    _write_json(tmp_path / "risk.json", {"rows": [_risk_row(candidate)]})
    approval_path = tmp_path / "approval.json"
    _write_json(approval_path, {"rows": [candidate]})

    report = audit.build_report(
        approval_path=approval_path,
        risk_path=tmp_path / "risk.json",
        event_source_path=tmp_path / "missing-event-source.json",
        repo_root=tmp_path,
    )
    row = report["rows"][0]

    assert report["summary"]["evidence_refs_complete_count"] == 0
    assert report["summary"]["reviewer_packet_complete_count"] == 0
    assert row["missing_runtime_dependency_refs"] == ["L9.disclosure.qa_recent"]
