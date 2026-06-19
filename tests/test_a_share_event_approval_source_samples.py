import json
from pathlib import Path

from scripts import audit_a_share_event_approval_source_samples as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_doc(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"<html><head><title>Unit doc</title></head><body>{text}</body></html>",
        encoding="utf-8",
    )


def _candidate(dp_id: str, *, include_runtime_ref: bool = True) -> dict:
    dockcase_ref = "dockcase:news/unit.html"
    evidence_refs = [
        "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json",
        "docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json",
        "docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json",
        dockcase_ref,
    ]
    if include_runtime_ref:
        evidence_refs.append("runtime:realtime_current:L9.media.report")
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "source_kind": "event_text_policy_pilot",
        "source_report": "docs/audit/source.json",
        "source_dependencies": ["L9.media.report"],
        "data_status": "Known",
        "payload_sha256": f"hash-{dp_id}",
        "confidence": 0.42,
        "value_json": {
            "score": 0.2,
            "drivers": ["market_doc:unit"],
            "components": {
                "classification": "unit_event",
                "market_doc_examples": 1,
                "same_sentence_evidence_count": 1,
                "target_hits": ["突破"],
                "direct_transmission_hits": ["A股"],
            },
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
    }


def _source_row(candidate: dict) -> dict:
    return {
        "dp_id": candidate["dp_id"],
        "draft_status": "draft_known_market_doc_review_required",
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


def _market_review_row(candidate: dict) -> dict:
    return {
        "dp_id": candidate["dp_id"],
        "classification_packet_status": "market_doc_review_ready",
        "candidate_examples": [
            {
                "market_relative_path": "news/unit.html",
                "target_hits": ["突破"],
                "direct_transmission_hits": ["A股"],
            }
        ],
        "packet_contract_valid": True,
        "production_write_allowed": False,
    }


def test_event_approval_source_samples_validate_traceability(tmp_path: Path) -> None:
    market_root = tmp_path / "market_data"
    _write_doc(market_root / "news/unit.html", "A股产业链出现技术突破。")
    candidate = _candidate("L0.tech.breakthrough")
    _write_json(tmp_path / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json", {})
    _write_json(
        tmp_path / "docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json",
        {},
    )
    _write_json(tmp_path / "docs/audit/source.json", {"rows": [_source_row(candidate)]})
    _write_json(
        tmp_path / "docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json",
        {"rows": [_market_review_row(candidate)]},
    )
    _write_json(
        tmp_path / "risk.json",
        {
            "rows": [
                {
                    "dp_id": candidate["dp_id"],
                    "risk_class": "individual_event_evidence_review_required",
                    "risk_reasons": ["unit reason"],
                }
            ]
        },
    )
    approval_path = tmp_path / "approval.json"
    _write_json(approval_path, {"rows": [candidate]})

    report = audit.build_report(
        approval_path=approval_path,
        risk_path=tmp_path / "risk.json",
        market_review_path=(
            tmp_path
            / "docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json"
        ),
        market_root=market_root,
        repo_root=tmp_path,
    )
    row = report["rows"][0]

    assert report["summary"]["event_text_approval_packet_count"] == 1
    assert report["summary"]["individual_event_evidence_review_required_count"] == 1
    assert report["summary"]["source_payload_matches_candidate_count"] == 1
    assert report["summary"]["market_doc_review_refs_complete_count"] == 1
    assert report["summary"]["dockcase_ref_count"] == 1
    assert report["summary"]["dockcase_file_exists_count"] == 1
    assert report["summary"]["dockcase_keyword_evidence_ready_count"] == 1
    assert report["summary"]["event_evidence_review_template_contract_valid_count"] == 1
    assert report["summary"]["event_evidence_review_template_blank_pending_count"] == 1
    assert report["summary"]["reviewer_packet_complete_count"] == 1
    assert report["summary"]["runtime_write_allowed_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert row["event_evidence_review_template"]["approval_allowed"] is False
    assert "Reviewer packets complete: `1`" in audit.render_markdown(report)


def test_event_approval_source_samples_flags_missing_inputs(tmp_path: Path) -> None:
    market_root = tmp_path / "market_data"
    candidate = _candidate("L0.tech.breakthrough", include_runtime_ref=False)
    _write_json(tmp_path / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json", {})
    _write_json(
        tmp_path / "docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json",
        {},
    )
    _write_json(tmp_path / "docs/audit/source.json", {"rows": [_source_row(candidate)]})
    _write_json(
        tmp_path / "docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json",
        {"rows": [_market_review_row(candidate)]},
    )
    approval_path = tmp_path / "approval.json"
    _write_json(approval_path, {"rows": [candidate]})

    report = audit.build_report(
        approval_path=approval_path,
        risk_path=tmp_path / "missing-risk.json",
        market_review_path=(
            tmp_path
            / "docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json"
        ),
        market_root=market_root,
        repo_root=tmp_path,
    )
    row = report["rows"][0]

    assert report["summary"]["runtime_dependency_ref_complete_count"] == 0
    assert report["summary"]["dockcase_file_missing_count"] == 1
    assert report["summary"]["reviewer_packet_complete_count"] == 0
    assert row["missing_runtime_dependency_refs"] == ["L9.media.report"]
    assert row["missing_dockcase_refs"] == ["dockcase:news/unit.html"]
