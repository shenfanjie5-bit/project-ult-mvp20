import json
from pathlib import Path

from scripts import audit_a_share_candidate_generation_queue as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _row(dp_id: str, score_target: str, route: str, action: str, status: str) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "recommended_source_route": route,
        "next_action": action,
        "payload_status": status,
        "staging_payload": {
            "evidence_refs": [
                "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json",
                f"runtime:realtime_current:{dp_id}.dep",
            ]
        },
    }


def test_candidate_generation_queue_groups_generator_required_tasks(tmp_path: Path) -> None:
    staging_path = tmp_path / "staging.json"
    contract_path = tmp_path / "contracts.json"
    _write_json(
        staging_path,
        {
            "rows": [
                _row(
                    "L0.compete.new_entrant",
                    "fundamental_score",
                    "event_llm_from_runtime_news",
                    "generate_event_llm_candidate",
                    "requires_generator_output",
                ),
                _row(
                    "L0.cost.cac",
                    "fundamental_score",
                    "local_llm_closed_loop",
                    "generate_local_llm_candidate",
                    "requires_generator_output",
                ),
                _row(
                    "L6.mult.dcf",
                    "valuation_rerating",
                    "manual_design_review",
                    "generate_manual_policy_candidate",
                    "requires_generator_output",
                ),
                _row(
                    "L9.media.short_report",
                    "expectation_gap",
                    "web_event_extraction",
                    "review_neutral_or_unknown_payload",
                    "deterministic_neutral_review_payload",
                ),
            ]
        },
    )
    _write_json(
        contract_path,
        {
            "rows": [
                {"dp_id": "L0.compete.new_entrant", "contract_valid": True},
                {"dp_id": "L0.cost.cac", "contract_valid": True},
                {"dp_id": "L6.mult.dcf", "contract_valid": True},
                {"dp_id": "L9.media.short_report", "contract_valid": True},
            ]
        },
    )

    report = audit.build_report(staging_path, contract_path)

    assert report["summary"]["generator_required_task_count"] == 3
    assert report["summary"]["skipped_non_generator_count"] == 1
    assert report["summary"]["generator_kind_counts"] == {
        "event_llm_candidate": 1,
        "local_llm_candidate": 1,
        "manual_policy_candidate": 1,
    }
    assert report["summary"]["all_tasks_have_valid_placeholder_contract"] is True
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["batches"]["event_llm_candidate"] == ["L0.compete.new_entrant"]
    by_dp = {task["dp_id"]: task for task in report["tasks"]}
    assert by_dp["L6.mult.dcf"]["output_contract"]["value_json"][
        "scalar"
    ] == "finite number in [-1, 1]"
    assert by_dp["L0.cost.cac"]["output_contract"]["value_json"][
        "score"
    ] == "finite signed number in [-1, 1]"
    assert "Generator-required tasks: `3`" in audit.render_markdown(report)


def test_candidate_generation_queue_flags_invalid_placeholder_contract(tmp_path: Path) -> None:
    staging_path = tmp_path / "staging.json"
    contract_path = tmp_path / "contracts.json"
    _write_json(
        staging_path,
        {
            "rows": [
                _row(
                    "L0.cost.cac",
                    "fundamental_score",
                    "local_llm_closed_loop",
                    "generate_local_llm_candidate",
                    "requires_generator_output",
                )
            ]
        },
    )
    _write_json(contract_path, {"rows": [{"dp_id": "L0.cost.cac", "contract_valid": False}]})

    report = audit.build_report(staging_path, contract_path)

    assert report["summary"]["generator_required_task_count"] == 1
    assert report["summary"]["all_tasks_have_valid_placeholder_contract"] is False
    assert report["tasks"][0]["current_contract_valid"] is False
