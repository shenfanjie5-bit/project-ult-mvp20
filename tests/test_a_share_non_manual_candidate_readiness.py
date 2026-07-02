import json
from pathlib import Path

from scripts import audit_a_share_non_manual_candidate_readiness as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _task(dp_id: str, score_target: str, kind: str) -> dict:
    value_json = {"magnitude": "finite number in [0, 1]"} if score_target == "risk_discount" else {"score": "finite signed number in [-1, 1]"}
    return {
        "task_id": f"a_share_candidate::{kind}::{dp_id}",
        "dp_id": dp_id,
        "score_target": score_target,
        "generator_kind": kind,
        "current_contract_valid": True,
        "output_contract": {
            "target_dp_id": dp_id,
            "score_target": score_target,
            "value_json": value_json,
            "safe_to_upsert_without_review": False,
        },
    }


def _dep(dp_id: str, row_count: int, known_count: int, value: dict) -> dict:
    return {
        "dp_id": dp_id,
        "row_count": row_count,
        "known_count": known_count,
        "namespace_counts": {"stock": row_count},
        "latest_updated_at_iso": "2026-06-19T00:00:00+00:00",
        "sample_rows": [
            {
                "ts_code": "000001.SZ",
                "data_status": "Known",
                "confidence": 0.7,
                "source": "test",
                "value_json_compact": value,
            }
        ],
    }


def _candidate(dp_id: str, score_target: str, route: str, deps: list[dict]) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "candidate_status": "ready_for_local_llm_candidate",
        "recommended_source_route": route,
        "candidate_input": {
            "target_dp_id": dp_id,
            "score_target": score_target,
            "dependencies": deps,
        },
    }


def test_non_manual_candidate_readiness_classifies_local_and_event_tasks(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(
        queue_path,
        {
            "tasks": [
                _task("L0.cost.cac", "fundamental_score", "local_llm_candidate"),
                _task("L0.demand.user_count", "fundamental_score", "local_llm_candidate"),
                _task("L0.demand.replacement", "fundamental_score", "local_llm_candidate"),
                _task("L8.shock.black_swan", "risk_discount", "event_llm_candidate"),
                _task("L6.mult.dcf", "valuation_rerating", "manual_policy_candidate"),
            ]
        },
    )
    _write_json(
        candidate_path,
        {
            "rows": [
                _candidate(
                    "L0.cost.cac",
                    "fundamental_score",
                    "local_llm_closed_loop",
                    [
                        _dep("L5.is.sga_rd", 100, 95, {"sga_rd_ratio_revenue": 0.2}),
                        _dep("L5.is.revenue", 100, 100, {"scalar": 1000.0}),
                    ],
                ),
                _candidate(
                    "L0.demand.user_count",
                    "fundamental_score",
                    "local_llm_closed_loop",
                    [
                        _dep("L5.is.revenue", 100, 100, {"scalar": 1000.0}),
                        _dep(
                            "L9.disclosure.qa_recent",
                            10,
                            9,
                            {"top_qa": [{"question": "q", "answer": "a"}]},
                        ),
                    ],
                ),
                _candidate(
                    "L0.demand.replacement",
                    "fundamental_score",
                    "local_llm_closed_loop",
                    [_dep("L5.is.revenue", 100, 100, {"scalar": 1000.0})],
                ),
                _candidate(
                    "L8.shock.black_swan",
                    "risk_discount",
                    "event_llm_from_runtime_news",
                    [
                        _dep(
                            "L9.media.report",
                            1,
                            1,
                            {"event_active": True, "top_headlines": [{"title": "news"}]},
                        ),
                        _dep(
                            "L9.macro.geo",
                            1,
                            1,
                            {"event_active": True, "top_headlines": [{"title": "geo"}]},
                        ),
                    ],
                ),
            ]
        },
    )

    report = audit.build_report(queue_path, candidate_path)

    assert report["summary"]["non_manual_task_count"] == 4
    assert report["summary"]["generator_kind_counts"] == {
        "event_llm_candidate": 1,
        "local_llm_candidate": 3,
    }
    assert report["summary"]["placeholder_contract_valid_count"] == 4
    assert report["summary"]["output_contract_shape_valid_count"] == 4
    assert report["summary"]["bridge_probe_ready_count"] == 4
    assert report["summary"]["deterministic_known_draft_allowed_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.cost.cac"]["route_bucket"] == "local_structured_llm_required"
    assert by_dp["L0.demand.user_count"]["route_bucket"] == "local_structured_text_llm_required"
    assert by_dp["L0.demand.replacement"]["route_bucket"] == "local_single_dependency_policy_required"
    assert by_dp["L8.shock.black_swan"]["route_bucket"] == "event_text_classification_required"
    assert by_dp["L8.shock.black_swan"]["bridge_validation"]["final_score_target_ready"]
    assert "Bridge probes ready: `4`" in audit.render_markdown(report)


def test_non_manual_candidate_readiness_marks_missing_candidate_evidence(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(
        queue_path,
        {"tasks": [_task("L0.cost.cac", "fundamental_score", "local_llm_candidate")]},
    )
    _write_json(candidate_path, {"rows": []})

    report = audit.build_report(queue_path, candidate_path)

    assert report["summary"]["non_manual_task_count"] == 1
    row = report["rows"][0]
    assert row["dependency_readiness"] == "missing_candidate_evidence"
    assert row["source_dependencies"] == []
    assert row["bridge_validation"]["final_score_target_ready"]
