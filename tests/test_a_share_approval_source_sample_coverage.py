import json
from pathlib import Path

from scripts import audit_a_share_approval_source_sample_coverage as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _approval(dp_id: str, risk_class: str, source_kind: str = "local_structured_policy_pilot") -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "source_kind": source_kind,
        "payload_sha256": f"hash-{dp_id}",
        "approval_gate_status": "approval_missing",
        "approval_payload_hash_matches_manifest": True,
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
        "_risk_class": risk_class,
    }


def _risk(approval: dict) -> dict:
    return {
        "dp_id": approval["dp_id"],
        "risk_class": approval["_risk_class"],
        "risk_reasons": ["unit reason"],
    }


def _source_row(dp_id: str, *, template_key: str, complete: bool = True) -> dict:
    return {
        "dp_id": dp_id,
        "reviewer_packet_complete": complete,
        "source_payload_matches_candidate": True,
        template_key: True,
    }


def test_approval_source_sample_coverage_merges_all_routes(tmp_path: Path) -> None:
    bulk = _approval("L0.cost.cac", "bulk_structured_review_candidate")
    event = _approval(
        "L0.compete.price_war",
        "individual_event_evidence_review_required",
        source_kind="event_text_policy_pilot",
    )
    individual = _approval(
        "L8.shock.supply_break",
        "individual_policy_review_required",
        source_kind="event_text_policy_pilot",
    )
    _write_json(tmp_path / "approval.json", {"rows": [bulk, event, individual]})
    _write_json(tmp_path / "risk.json", {"rows": [_risk(bulk), _risk(event), _risk(individual)]})
    _write_json(
        tmp_path / "bulk.json",
        {
            "rows": [
                _source_row(
                    bulk["dp_id"],
                    template_key="approval_record_draft_blank_contract_valid",
                )
            ]
        },
    )
    _write_json(
        tmp_path / "event.json",
        {
            "rows": [
                _source_row(
                    event["dp_id"],
                    template_key="event_evidence_review_template_contract_valid",
                ),
                _source_row(
                    individual["dp_id"],
                    template_key="event_evidence_review_template_contract_valid",
                ),
            ]
        },
    )
    _write_json(
        tmp_path / "individual.json",
        {
            "rows": [
                _source_row(
                    individual["dp_id"],
                    template_key="individual_review_template_contract_valid",
                )
            ]
        },
    )

    report = audit.build_report(
        approval_path=tmp_path / "approval.json",
        risk_path=tmp_path / "risk.json",
        bulk_source_path=tmp_path / "bulk.json",
        event_source_path=tmp_path / "event.json",
        individual_source_path=tmp_path / "individual.json",
    )

    assert report["summary"]["approval_packet_count"] == 3
    assert report["summary"]["source_sample_supported_packet_count"] == 3
    assert report["summary"]["source_sample_found_count"] == 3
    assert report["summary"]["source_sample_reviewer_packet_complete_count"] == 3
    assert report["summary"]["source_sample_review_template_contract_valid_count"] == 3
    assert report["summary"]["approval_record_template_blank_contract_valid_count"] == 3
    assert report["summary"]["approval_input_ready_count"] == 3
    assert report["summary"]["approval_input_not_ready_count"] == 0
    assert report["summary"]["supplemental_event_source_sample_complete_count"] == 1
    assert report["summary"]["source_sample_route_counts"] == {
        "bulk_review_source_sample": 1,
        "event_approval_source_sample": 1,
        "individual_review_source_sample": 1,
    }
    assert "Approval inputs ready: `3`" in audit.render_markdown(report)


def test_approval_source_sample_coverage_flags_missing_source_sample(tmp_path: Path) -> None:
    approval = _approval("L0.cost.cac", "bulk_structured_review_candidate")
    _write_json(tmp_path / "approval.json", {"rows": [approval]})
    _write_json(tmp_path / "risk.json", {"rows": [_risk(approval)]})
    _write_json(tmp_path / "bulk.json", {"rows": []})
    _write_json(tmp_path / "event.json", {"rows": []})
    _write_json(tmp_path / "individual.json", {"rows": []})

    report = audit.build_report(
        approval_path=tmp_path / "approval.json",
        risk_path=tmp_path / "risk.json",
        bulk_source_path=tmp_path / "bulk.json",
        event_source_path=tmp_path / "event.json",
        individual_source_path=tmp_path / "individual.json",
    )
    row = report["rows"][0]

    assert report["summary"]["source_sample_found_count"] == 0
    assert report["summary"]["approval_input_ready_count"] == 0
    assert report["summary"]["approval_input_not_ready_count"] == 1
    assert row["source_sample_route"] == "bulk_review_source_sample"
    assert row["source_sample_found"] is False
