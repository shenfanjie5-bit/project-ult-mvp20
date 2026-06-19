import json
from pathlib import Path

from scripts import audit_a_share_bulk_review_approval_candidates as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _packet(dp_id: str, source_kind: str = "local_structured_policy_pilot") -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "source_kind": source_kind,
        "source_report": "unit.json",
        "source_dependencies": ["dep.a"],
        "data_status": "Known",
        "payload_sha256": f"hash-{dp_id}",
        "value_json": {"score": 0.1},
        "confidence": 0.4,
        "evidence_refs": ["runtime:dep.a"],
        "rationale": "unit rationale",
    }


def _risk(dp_id: str, risk_class: str) -> dict:
    return {
        "dp_id": dp_id,
        "risk_class": risk_class,
        "risk_reasons": ["unit reason"],
        "impact_value": 0.1,
    }


def test_bulk_review_candidates_extract_only_bulk_and_borderline(
    tmp_path: Path,
) -> None:
    packets_path = tmp_path / "packets.json"
    risk_path = tmp_path / "risk.json"
    _write_json(
        packets_path,
        {
            "rows": [
                _packet("L0.cost.cac"),
                _packet(
                    "L0.supply.channel_service",
                    "local_structured_text_policy_pilot",
                ),
                _packet("L0.compete.price_war", "event_text_policy_pilot"),
            ]
        },
    )
    _write_json(
        risk_path,
        {
            "rows": [
                _risk("L0.cost.cac", "bulk_structured_review_candidate"),
                _risk(
                    "L0.supply.channel_service",
                    "borderline_structured_text_review_candidate",
                ),
                _risk(
                    "L0.compete.price_war",
                    "individual_event_evidence_review_required",
                ),
            ]
        },
    )

    report = audit.build_report(
        packets_path=packets_path,
        risk_review_path=risk_path,
    )
    by_dp = {row["dp_id"]: row for row in report["rows"]}

    assert report["summary"]["candidate_count"] == 2
    assert report["summary"]["strict_bulk_candidate_count"] == 1
    assert report["summary"]["borderline_sample_check_candidate_count"] == 1
    assert report["summary"]["approval_record_draft_count"] == 2
    assert report["summary"]["approval_record_draft_contract_valid_count"] == 2
    assert report["summary"]["auto_approval_allowed_count"] == 0
    assert report["summary"]["runtime_write_allowed_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert by_dp["L0.cost.cac"]["ready_for_bulk_review"] is True
    assert by_dp["L0.cost.cac"]["approval_record_draft"]["approval_status"] == ""
    assert by_dp["L0.cost.cac"]["approval_record_draft"]["risk_acknowledged"] is False
    assert by_dp["L0.supply.channel_service"]["requires_sample_check"] is True
    assert "Candidates: `2`" in audit.render_markdown(report)
