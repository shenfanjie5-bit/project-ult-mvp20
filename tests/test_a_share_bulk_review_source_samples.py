import json
from pathlib import Path

from scripts import audit_a_share_bulk_review_source_samples as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _candidate(
    dp_id: str,
    *,
    requires_sample_check: bool = False,
    source_report: str = "docs/audit/source.json",
) -> dict:
    value_json = {
        "score": 0.1,
        "drivers": ["dep.a"],
        "components": {"sample_avg": 1.0},
    }
    if requires_sample_check:
        value_json["components"]["evidence_examples"] = [
            {
                "ts_code": "000001.SZ",
                "date": "20260619",
                "keyword_hits": ["渠道"],
                "question": "渠道情况？",
                "answer": "渠道稳定。",
            }
        ]
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "source_kind": "local_structured_text_policy_pilot"
        if requires_sample_check
        else "local_structured_policy_pilot",
        "source_report": source_report,
        "source_dependencies": ["dep.a"],
        "data_status": "Known",
        "payload_sha256": f"hash-{dp_id}",
        "confidence": 0.4,
        "impact_value": 0.1,
        "value_json": value_json,
        "evidence_refs": [
            "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json",
            "runtime:realtime_current:dep.a",
        ],
        "rationale": "unit rationale",
        "risk_class": "borderline_structured_text_review_candidate"
        if requires_sample_check
        else "bulk_structured_review_candidate",
        "risk_reasons": ["unit reason"],
        "approval_record_draft": {
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
        "approval_record_draft_contract_valid": True,
        "requires_sample_check": requires_sample_check,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
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


def test_bulk_review_source_samples_validate_traceability(tmp_path: Path) -> None:
    source_report = "docs/audit/source.json"
    bulk = _candidate("L0.cost.cac", source_report=source_report)
    borderline = _candidate(
        "L0.supply.channel_service",
        requires_sample_check=True,
        source_report=source_report,
    )
    _write_json(tmp_path / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json", {})
    _write_json(
        tmp_path / source_report,
        {"rows": [_source_row(bulk), _source_row(borderline)]},
    )
    bulk_path = tmp_path / "bulk.json"
    _write_json(bulk_path, {"rows": [bulk, borderline]})

    report = audit.build_report(bulk_path=bulk_path, repo_root=tmp_path)
    by_dp = {row["dp_id"]: row for row in report["rows"]}

    assert report["summary"]["candidate_count"] == 2
    assert report["summary"]["strict_bulk_candidate_count"] == 1
    assert report["summary"]["borderline_sample_check_candidate_count"] == 1
    assert report["summary"]["source_report_exists_count"] == 2
    assert report["summary"]["source_report_row_found_count"] == 2
    assert report["summary"]["source_payload_matches_candidate_count"] == 2
    assert report["summary"]["evidence_refs_complete_count"] == 2
    assert report["summary"]["borderline_sample_evidence_ready_count"] == 1
    assert report["summary"]["reviewer_packet_complete_count"] == 2
    assert report["summary"]["runtime_write_allowed_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert by_dp["L0.supply.channel_service"]["sample_evidence_count"] == 1
    assert by_dp["L0.cost.cac"]["approval_record_draft_blank_contract_valid"] is True
    assert "Reviewer packets complete: `2`" in audit.render_markdown(report)


def test_bulk_review_source_samples_flags_missing_dependency_ref(tmp_path: Path) -> None:
    candidate = _candidate("L0.cost.cac")
    candidate["evidence_refs"] = ["docs/audit/a_share_gap_candidate_evidence_2026-06-19.json"]
    _write_json(tmp_path / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json", {})
    _write_json(tmp_path / "docs/audit/source.json", {"rows": [_source_row(candidate)]})
    bulk_path = tmp_path / "bulk.json"
    _write_json(bulk_path, {"rows": [candidate]})

    report = audit.build_report(bulk_path=bulk_path, repo_root=tmp_path)
    row = report["rows"][0]

    assert report["summary"]["evidence_refs_complete_count"] == 0
    assert report["summary"]["reviewer_packet_complete_count"] == 0
    assert row["missing_runtime_dependency_refs"] == ["dep.a"]
