import json
from pathlib import Path

from scripts import audit_a_share_event_text_unknown_source_options as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _draft_row(dp_id: str) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "risk_discount",
        "draft_status": "unknown_event_text_classification_required",
        "source_dependencies": ["L9.media.report"],
        "draft_payload": {
            "data_status": "Unknown",
            "value_json": {
                "blocked_reason": "event_text_classification_required",
                "required_policy": "target_event_direction_magnitude_transmission",
            },
        },
    }


def _classification_row(dp_id: str) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "risk_discount",
        "classification_status": "classification_input_ready",
        "headline_input_count": 3,
        "unique_headline_count": 1,
    }


def _body_row(
    dp_id: str,
    *,
    target_hits: list[str] | None = None,
    direct_hits: list[str] | None = None,
    broad_hits: list[str] | None = None,
    classifier_ready: bool = False,
) -> dict:
    return {
        "dp_id": dp_id,
        "url_count": 1,
        "url_fetch_ok_count": 1,
        "body_text_available_count": 1,
        "target_keyword_hits": target_hits or [],
        "direct_transmission_keyword_hits": direct_hits or [],
        "broad_market_transmission_keyword_hits": broad_hits or [],
        "body_signal_sufficient_for_classifier": classifier_ready,
    }


def test_event_text_unknown_source_options_classifies_source_gaps(
    tmp_path: Path,
) -> None:
    event_text_path = tmp_path / "event_text.json"
    classification_path = tmp_path / "classification.json"
    sufficiency_path = tmp_path / "sufficiency.json"
    body_path = tmp_path / "body.json"
    dp_ids = [
        "L0.policy.regulation",
        "L0.policy.tax_trade",
        "L0.tech.ai_automation",
        "L8.shock.supply_break",
    ]
    _write_json(event_text_path, {"rows": [_draft_row(dp_id) for dp_id in dp_ids]})
    _write_json(
        classification_path,
        {"rows": [_classification_row(dp_id) for dp_id in dp_ids]},
    )
    _write_json(
        sufficiency_path,
        {"rows": [{"dp_id": dp_id, "sufficiency_status": "needs_review"} for dp_id in dp_ids]},
    )
    _write_json(
        body_path,
        {
            "rows": [
                _body_row(
                    "L0.policy.regulation",
                    target_hits=["监管"],
                    broad_hits=["中国A50"],
                ),
                _body_row("L0.policy.tax_trade", target_hits=["关税"]),
                _body_row("L0.tech.ai_automation", broad_hits=["中国A50"]),
                _body_row(
                    "L8.shock.supply_break",
                    target_hits=["供应中断"],
                    direct_hits=["A股供应链"],
                    classifier_ready=True,
                ),
            ]
        },
    )

    report = audit.build_report(
        event_text_path=event_text_path,
        classification_inputs_path=classification_path,
        sufficiency_path=sufficiency_path,
        url_fetchability_path=body_path,
    )

    assert report["summary"]["unknown_event_text_count"] == 4
    assert report["summary"]["classification_input_ready_count"] == 4
    assert report["summary"]["body_text_available_count"] == 4
    assert report["summary"]["target_event_evidence_present_count"] == 3
    assert report["summary"]["direct_a_share_transmission_present_count"] == 1
    assert report["summary"]["broad_market_transmission_only_count"] == 2
    assert report["summary"]["classifier_ready_for_review_count"] == 1
    assert report["summary"]["candidate_requires_target_event_evidence_count"] == 1
    assert report["summary"]["candidate_requires_direct_a_share_transmission_count"] == 2
    assert report["summary"]["auto_known_candidate_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    rows = {row["dp_id"]: row for row in report["rows"]}
    assert (
        rows["L0.policy.regulation"]["resolution_status"]
        == "requires_direct_a_share_transmission_not_broad_market"
    )
    assert (
        rows["L0.policy.tax_trade"]["resolution_status"]
        == "requires_direct_a_share_transmission"
    )
    assert (
        rows["L0.tech.ai_automation"]["resolution_status"]
        == "requires_target_event_evidence"
    )
    assert rows["L8.shock.supply_break"]["resolution_status"] == "requires_classifier_review"
    assert all(not row["production_write_allowed"] for row in report["rows"])
    assert "Direct A-share transmission present: `1`" in audit.render_markdown(report)


def test_event_text_unknown_source_options_keeps_missing_inputs_gated(
    tmp_path: Path,
) -> None:
    event_text_path = tmp_path / "event_text.json"
    classification_path = tmp_path / "classification.json"
    sufficiency_path = tmp_path / "sufficiency.json"
    body_path = tmp_path / "body.json"
    _write_json(event_text_path, {"rows": [_draft_row("L0.compete.new_entrant")]})
    _write_json(classification_path, {"rows": []})
    _write_json(sufficiency_path, {"rows": []})
    _write_json(body_path, {"rows": []})

    report = audit.build_report(
        event_text_path=event_text_path,
        classification_inputs_path=classification_path,
        sufficiency_path=sufficiency_path,
        url_fetchability_path=body_path,
    )

    assert report["summary"]["unknown_event_text_count"] == 1
    assert report["summary"]["classification_input_ready_count"] == 0
    assert report["summary"]["body_text_available_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    row = report["rows"][0]
    assert row["resolution_status"] == "requires_classification_input"
    assert row["review_required"] is True
    assert row["safe_to_upsert_without_review"] is False


def test_current_event_text_unknown_source_options_report_matches_real_gate() -> None:
    path = Path("docs/audit/a_share_event_text_unknown_source_options_2026-06-19.json")
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["unknown_event_text_count"] == 2
    assert report["summary"]["classification_input_ready_count"] == 2
    assert report["summary"]["body_text_available_count"] == 2
    assert report["summary"]["target_event_evidence_present_count"] == 0
    assert report["summary"]["direct_a_share_transmission_present_count"] == 0
    assert report["summary"]["broad_market_transmission_only_count"] == 2
    assert report["summary"]["classifier_ready_for_review_count"] == 0
    assert report["summary"]["candidate_requires_target_event_evidence_count"] == 2
    assert report["summary"]["candidate_requires_direct_a_share_transmission_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0


def test_current_goal_coverage_includes_event_text_unknown_source_options() -> None:
    source_path = Path("docs/audit/a_share_event_text_unknown_source_options_2026-06-19.json")
    goal_path = Path("docs/audit/goal_coverage_2026-06-19.json")

    source_summary = json.loads(source_path.read_text(encoding="utf-8"))["summary"]
    goal_report = json.loads(goal_path.read_text(encoding="utf-8"))
    a_share_row = next(
        row
        for row in goal_report["requirements"]
        if row["requirement_id"] == "a_share_score_field_path"
    )

    assert (
        a_share_row["evidence"]["event_text_unknown_source_options_summary"]
        == source_summary
    )
    assert "event_text_unknown_source_options" in a_share_row["evidence_strength"]
    assert (
        "Event-text Unknown source-options audit reviews 2 Unknown rows"
        in a_share_row["remaining_gap"]
    )
    assert any(
        "2 event-text target-event evidence required" in blocker
        for blocker in goal_report["summary"]["completion_blockers"]
    )
