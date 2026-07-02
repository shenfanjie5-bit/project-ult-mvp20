import json
from pathlib import Path

from scripts import audit_a_share_review_approval_gate as approval_gate
from scripts.audit_a_share_deterministic_runtime_approvals import (
    build_report,
    render_markdown,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _payload(
    dp_id: str,
    score_target: str,
    data_status: str,
    value_json: dict,
    confidence: float,
) -> dict:
    return {
        "target_dp_id": dp_id,
        "score_target": score_target,
        "data_status": data_status,
        "bridge_entry_data_status": "Known"
        if data_status == "NotApplicable"
        else data_status,
        "value_json": value_json,
        "confidence": confidence,
        "evidence_refs": ["docs/audit/unit.json"],
        "rationale": "unit deterministic payload",
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
    }


def _manifest_row(
    dp_id: str,
    score_target: str,
    source_kind: str,
    data_status: str,
    value_json: dict,
    confidence: float = 0.7,
) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "source_kind": source_kind,
        "source_report": "docs/audit/unit.json",
        "review_payload": _payload(
            dp_id,
            score_target,
            data_status,
            value_json,
            confidence,
        ),
        "data_status": data_status,
        "review_entry_status": "review_ready_concrete",
        "contract_validation": {"contract_valid": True, "validation_errors": []},
        "bridge_ready_concrete": True,
        "safe_to_upsert_without_review": False,
        "production_write_allowed": False,
    }


def test_deterministic_runtime_approvals_generate_only_hard_gated_records(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    approvals_path = tmp_path / "approvals.json"

    short_report = _manifest_row(
        "L9.media.short_report",
        "expectation_gap",
        "deterministic_candidate_staging",
        "Known",
        {
            "score": 0.0,
            "event_state": "none_observed",
            "news_html_files_scanned": 14956,
            "strict_short_report_documents": 4,
            "direct_a_share_short_report_documents": 0,
            "foreign_or_market_short_report_documents": 4,
        },
        confidence=0.6,
    )
    gamma = _manifest_row(
        "L7.trade.gamma",
        "gamma_multiplier",
        "deterministic_candidate_staging",
        "NotApplicable",
        {
            "multiplier": 1.0,
            "applicability": "a_share_single_stock_no_listed_option",
        },
        confidence=0.7,
    )
    event_text = _manifest_row(
        "L0.compete.price_war",
        "fundamental_score",
        "event_text_policy_pilot",
        "Known",
        {"score": -0.25},
        confidence=0.46,
    )
    _write_json(manifest_path, {"rows": [short_report, gamma, event_text]})

    report = build_report(
        manifest_path=manifest_path,
        approved_at="2026-06-19T12:00:00+08:00",
    )

    assert report["summary"]["manifest_row_count"] == 3
    assert report["summary"]["approval_record_count"] == 2
    assert report["summary"]["approved_deterministic_runtime_write_count"] == 2
    assert report["summary"]["not_in_deterministic_policy_count"] == 1
    assert report["summary"]["production_write_allowed_count"] == 0
    assert {row["dp_id"] for row in report["approvals"]} == {
        "L7.trade.gamma",
        "L9.media.short_report",
    }
    assert "Approval records: `2`" in render_markdown(report)

    _write_json(approvals_path, {"approvals": report["approvals"]})
    gate_report = approval_gate.build_report(
        manifest_path=manifest_path,
        approvals_path=approvals_path,
    )
    assert gate_report["summary"]["approval_records_seen"] == 2
    assert gate_report["summary"]["approved_runtime_write_count"] == 2
    assert gate_report["summary"]["approval_missing_count"] == 1
    assert gate_report["summary"]["write_plan_count"] == 2
    assert gate_report["summary"]["production_write_allowed_count"] == 0
