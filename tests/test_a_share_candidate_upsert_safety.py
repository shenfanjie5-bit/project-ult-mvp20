import json
from pathlib import Path

from scripts import audit_a_share_candidate_upsert_safety as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _dry_row(dp_id: str) -> dict:
    return {
        "dp_id": dp_id,
        "bridge_signal_ready": True,
        "node_emitted": True,
        "final_score_target_ready": True,
    }


def test_candidate_upsert_safety_keeps_ready_rows_review_gated(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.json"
    dry_run_path = tmp_path / "dry.json"
    short_report_path = tmp_path / "short.json"
    _write_json(
        candidate_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "score_target": "fundamental_score",
                    "candidate_status": "ready_for_local_llm_candidate",
                    "recommended_source_route": "local_llm_closed_loop",
                    "candidate_input_ready": True,
                },
                {
                    "dp_id": "L9.media.short_report",
                    "score_target": "expectation_gap",
                    "candidate_status": "ready_for_web_event_candidate",
                    "recommended_source_route": "web_event_extraction",
                    "candidate_input_ready": True,
                },
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "candidate_status": "ready_for_manual_design_candidate",
                    "recommended_source_route": "manual_design_review",
                    "candidate_input_ready": True,
                },
                {
                    "dp_id": "L6.mult.dcf",
                    "score_target": "valuation_rerating",
                    "candidate_status": "ready_for_manual_design_candidate",
                    "recommended_source_route": "manual_design_review",
                    "candidate_input_ready": True,
                },
            ]
        },
    )
    _write_json(
        dry_run_path,
        {
            "rows": [
                _dry_row("L0.cost.cac"),
                _dry_row("L9.media.short_report"),
                _dry_row("L7.trade.gamma"),
                _dry_row("L6.mult.dcf"),
            ]
        },
    )
    _write_json(
        short_report_path,
        {"summary": {"direct_a_share_short_report_documents": 0}},
    )

    report = audit.build_report(candidate_path, dry_run_path, short_report_path)

    assert report["summary"]["candidate_rows_checked"] == 4
    assert report["summary"]["candidate_input_ready_count"] == 4
    assert report["summary"]["bridge_ready_count"] == 4
    assert report["summary"]["review_gated_count"] == 4
    assert report["summary"]["blocked_count"] == 0
    assert report["summary"]["safe_to_upsert_without_review_count"] == 0
    assert report["summary"]["upsert_safety_class_counts"] == {
        "neutral_candidate_review_required": 1,
        "not_applicable_candidate_review_required": 1,
        "review_required": 2,
    }
    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert (
        by_dp["L9.media.short_report"]["upsert_safety_class"]
        == "neutral_candidate_review_required"
    )
    assert (
        by_dp["L7.trade.gamma"]["upsert_safety_class"]
        == "not_applicable_candidate_review_required"
    )
    assert by_dp["L6.mult.dcf"]["upsert_action"] == "review_then_stage"
    markdown = audit.render_markdown(report)
    assert "Safe to upsert without review: `0`" in markdown
    assert "`neutral_candidate_review_required`" in markdown


def test_candidate_upsert_safety_blocks_missing_dry_run_row(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.json"
    dry_run_path = tmp_path / "dry.json"
    _write_json(
        candidate_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "score_target": "fundamental_score",
                    "candidate_status": "ready_for_local_llm_candidate",
                    "recommended_source_route": "local_llm_closed_loop",
                    "candidate_input_ready": True,
                }
            ]
        },
    )
    _write_json(dry_run_path, {"rows": []})

    report = audit.build_report(candidate_path, dry_run_path, None)

    assert report["summary"]["candidate_rows_checked"] == 1
    assert report["summary"]["bridge_ready_count"] == 0
    assert report["summary"]["review_gated_count"] == 0
    assert report["summary"]["blocked_count"] == 1
    assert report["summary"]["blocked_dp_ids"] == ["L0.cost.cac"]
    assert report["summary"]["safe_to_upsert_without_review_count"] == 0
    assert report["rows"][0]["upsert_safety_class"] == "blocked"
    assert "dry-run row is missing" in report["rows"][0]["reason"]


def test_candidate_upsert_safety_blocks_non_final_target(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.json"
    dry_run_path = tmp_path / "dry.json"
    _write_json(
        candidate_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "score_target": "display_only",
                    "candidate_status": "ready_for_local_llm_candidate",
                    "recommended_source_route": "local_llm_closed_loop",
                    "candidate_input_ready": True,
                }
            ]
        },
    )
    _write_json(dry_run_path, {"rows": [_dry_row("L0.cost.cac")]})

    report = audit.build_report(candidate_path, dry_run_path, None)

    assert report["summary"]["blocked_count"] == 1
    assert report["rows"][0]["upsert_safety_class"] == "blocked"
    assert "not a final scoring target" in report["rows"][0]["reason"]
