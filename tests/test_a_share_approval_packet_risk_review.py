import json
from pathlib import Path

from scripts import audit_a_share_approval_packet_risk_review as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _packet(
    dp_id: str,
    source_kind: str,
    score_target: str = "fundamental_score",
    confidence: float = 0.4,
    value_json: dict | None = None,
    *,
    final_score_target_ready: bool = True,
    payload_hash_matches: bool = True,
    template_valid: bool = True,
) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "source_kind": source_kind,
        "data_status": "Known",
        "confidence": confidence,
        "value_json": value_json or {"score": 0.1},
        "approval_gate_status": "approval_missing",
        "payload_sha256": f"hash-{dp_id}",
        "approval_payload_hash_matches_manifest": payload_hash_matches,
        "approval_record_template_contract_valid": template_valid,
        "final_score_target_ready": final_score_target_ready,
        "evidence_refs": ["runtime:dep"],
    }


def test_risk_review_splits_bulk_and_individual_packets(tmp_path: Path) -> None:
    packets_path = tmp_path / "packets.json"
    _write_json(
        packets_path,
        {
            "rows": [
                _packet(
                    "L0.cost.cac",
                    "local_structured_policy_pilot",
                    confidence=0.36,
                    value_json={"score": 0.02},
                ),
                _packet(
                    "L0.compete.price_war",
                    "event_text_policy_pilot",
                    confidence=0.46,
                    value_json={"score": -0.25},
                ),
                _packet(
                    "L6.mult.dcf",
                    "manual_policy_pilot",
                    score_target="valuation_rerating",
                    confidence=0.32,
                    value_json={"score": -0.67},
                ),
                _packet(
                    "L0.price.contract_spot",
                    "local_structured_policy_pilot",
                    confidence=0.32,
                    value_json={"score": -0.06},
                ),
            ]
        },
    )

    report = audit.build_report(packets_path=packets_path)
    by_dp = {row["dp_id"]: row for row in report["rows"]}

    assert report["summary"]["packet_count"] == 4
    assert report["summary"]["bulk_structured_review_candidate_count"] == 1
    assert report["summary"]["individual_review_required_count"] == 3
    assert report["summary"]["auto_approval_allowed_count"] == 0
    assert report["summary"]["runtime_write_allowed_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert by_dp["L0.cost.cac"]["risk_class"] == "bulk_structured_review_candidate"
    assert (
        by_dp["L0.compete.price_war"]["risk_class"]
        == "individual_event_evidence_review_required"
    )
    assert (
        by_dp["L6.mult.dcf"]["risk_class"]
        == "individual_policy_review_required"
    )
    assert (
        by_dp["L0.price.contract_spot"]["risk_class"]
        == "individual_structured_review_required"
    )
    assert "Bulk structured-review candidates: `1`" in audit.render_markdown(report)


def test_risk_review_blocks_contract_drift(tmp_path: Path) -> None:
    packets_path = tmp_path / "packets.json"
    _write_json(
        packets_path,
        {
            "rows": [
                _packet(
                    "L0.cost.cac",
                    "local_structured_policy_pilot",
                    payload_hash_matches=False,
                )
            ]
        },
    )

    report = audit.build_report(packets_path=packets_path)

    assert report["summary"]["do_not_approve_until_contract_fixed_count"] == 1
    assert report["summary"]["do_not_approve_until_contract_fixed_dp_ids"] == [
        "L0.cost.cac"
    ]
    assert report["rows"][0]["risk_class"] == "do_not_approve_until_contract_fixed"
    assert "approval payload hash does not match manifest" in report["rows"][0][
        "risk_reasons"
    ]
