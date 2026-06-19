import json
from pathlib import Path

from scripts import audit_a_share_candidate_staging_payloads as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _dry_row(dp_id: str) -> dict:
    return {
        "dp_id": dp_id,
        "bridge_signal_ready": True,
        "node_emitted": True,
        "final_score_target_ready": True,
    }


def _safety_row(dp_id: str, safety_class: str) -> dict:
    return {
        "dp_id": dp_id,
        "upsert_safety_class": safety_class,
    }


def test_candidate_staging_payloads_split_deterministic_and_generator_rows(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.json"
    dry_run_path = tmp_path / "dry.json"
    safety_path = tmp_path / "safety.json"
    _write_json(
        candidate_path,
        {
            "rows": [
                {
                    "dp_id": "L9.media.short_report",
                    "score_target": "expectation_gap",
                    "candidate_status": "ready_for_web_event_candidate",
                    "recommended_source_route": "web_event_extraction",
                    "candidate_input": {
                        "short_report_evidence": {
                            "news_html_files_scanned": 14956,
                            "strict_short_report_documents": 4,
                            "direct_a_share_short_report_documents": 0,
                            "foreign_or_market_short_report_documents": 4,
                        },
                        "required_output_schema": {"value_json": "event payload"},
                    },
                },
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "candidate_status": "ready_for_manual_design_candidate",
                    "recommended_source_route": "manual_design_review",
                    "candidate_input": {
                        "required_output_schema": {
                            "data_status": "NotApplicable | Known | Unknown",
                            "value_json": {"multiplier": "neutral 1.0"},
                        }
                    },
                },
                {
                    "dp_id": "L0.cost.cac",
                    "score_target": "fundamental_score",
                    "candidate_status": "ready_for_local_llm_candidate",
                    "recommended_source_route": "local_llm_closed_loop",
                    "candidate_input": {
                        "required_output_schema": {
                            "value_json": "object with reviewed score"
                        }
                    },
                },
            ]
        },
    )
    _write_json(
        dry_run_path,
        {
            "rows": [
                _dry_row("L9.media.short_report"),
                _dry_row("L7.trade.gamma"),
                _dry_row("L0.cost.cac"),
            ]
        },
    )
    _write_json(
        safety_path,
        {
            "rows": [
                _safety_row("L9.media.short_report", "neutral_candidate_review_required"),
                _safety_row("L7.trade.gamma", "not_applicable_candidate_review_required"),
                _safety_row("L0.cost.cac", "review_required"),
            ]
        },
    )

    report = audit.build_report(candidate_path, dry_run_path, safety_path)

    assert report["summary"]["candidate_rows_checked"] == 3
    assert report["summary"]["staging_payload_count"] == 3
    assert report["summary"]["deterministic_staging_payload_count"] == 2
    assert report["summary"]["placeholder_payload_count"] == 1
    assert report["summary"]["generator_required_count"] == 1
    assert report["summary"]["staging_payload_bridge_ready_count"] == 2
    assert report["summary"]["production_write_allowed_count"] == 0
    by_dp = {row["dp_id"]: row for row in report["rows"]}
    short_payload = by_dp["L9.media.short_report"]["staging_payload"]["value_json"]
    assert short_payload["score"] == 0.0
    assert short_payload["event_state"] == "none_observed"
    assert (
        by_dp["L9.media.short_report"]["payload_status"]
        == "deterministic_neutral_review_payload"
    )
    assert (
        by_dp["L7.trade.gamma"]["staging_payload"]["value_json"]["applicability"]
        == "a_share_single_stock_no_listed_option"
    )
    assert by_dp["L7.trade.gamma"]["staging_payload"]["data_status"] == "NotApplicable"
    assert by_dp["L7.trade.gamma"]["staging_payload"]["bridge_entry_data_status"] == "Known"
    assert by_dp["L0.cost.cac"]["staging_payload"]["data_status"] == "Unknown"
    assert by_dp["L0.cost.cac"]["staging_payload"]["value_json"] == {
        "review_required": True
    }
    assert by_dp["L0.cost.cac"]["staging_payload"]["review_status"] == "review_required"
    assert (
        by_dp["L0.cost.cac"]["staging_payload"]["safe_to_upsert_without_review"]
        is False
    )
    assert by_dp["L0.cost.cac"]["next_action"] == "generate_local_llm_candidate"
    markdown = audit.render_markdown(report)
    assert "Deterministic staging payloads: `2`" in markdown


def test_candidate_staging_payloads_blocks_safety_blocked_rows(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.json"
    dry_run_path = tmp_path / "dry.json"
    safety_path = tmp_path / "safety.json"
    _write_json(
        candidate_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "score_target": "fundamental_score",
                    "candidate_status": "ready_for_local_llm_candidate",
                    "recommended_source_route": "local_llm_closed_loop",
                }
            ]
        },
    )
    _write_json(dry_run_path, {"rows": [_dry_row("L0.cost.cac")]})
    _write_json(safety_path, {"rows": [_safety_row("L0.cost.cac", "blocked")]})

    report = audit.build_report(candidate_path, dry_run_path, safety_path)

    assert report["summary"]["blocked_count"] == 1
    assert report["summary"]["staging_payload_count"] == 0
    assert report["summary"]["generator_required_count"] == 0
    assert report["rows"][0]["payload_status"] == "blocked"
    assert report["rows"][0]["staging_payload"] is None
    assert report["rows"][0]["production_write_allowed"] is False
