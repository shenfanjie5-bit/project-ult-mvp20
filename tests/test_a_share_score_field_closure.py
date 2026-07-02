import json
from pathlib import Path

import yaml

from scripts.audit_a_share_score_field_closure import build_report


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_score_field_closure_merges_trace_gap_candidate_and_readiness(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.json"
    gap_path = tmp_path / "gap.json"
    candidate_path = tmp_path / "candidate.json"
    readiness_path = tmp_path / "readiness.json"
    spec_path = tmp_path / "roles.yaml"

    _write_json(
        trace_path,
        {
            "summary": {
                "spec_total": 2,
                "participating_spec_dp_ids": 2,
                "score_relevant_spec_dp_ids": 2,
                "effective_score_path_dp_ids": 1,
            },
            "field_rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "field_role": "score_component",
                    "score_target": "fundamental_score",
                    "participates_in_score": True,
                    "runtime_valid_real_ts_count": 0,
                    "runtime_numeric_signal_ts_count": 0,
                    "runtime_bridge_emitted_ts_count": 0,
                    "runtime_blocked_by_overlay_without_score_ts_count": 0,
                    "runtime_numeric_blocked_by_dedup_ts_count": 0,
                    "overlay_present_ts_count": 1,
                    "overlay_score_candidate_ts_count": 0,
                    "effective_score_path_ts_count": 0,
                },
                {
                    "dp_id": "L7.flow.active_inflow",
                    "field_role": "score_component",
                    "score_target": "funding_score",
                    "participates_in_score": True,
                    "runtime_valid_real_ts_count": 1,
                    "runtime_numeric_signal_ts_count": 1,
                    "runtime_bridge_emitted_ts_count": 1,
                    "runtime_blocked_by_overlay_without_score_ts_count": 0,
                    "runtime_numeric_blocked_by_dedup_ts_count": 0,
                    "overlay_present_ts_count": 0,
                    "overlay_score_candidate_ts_count": 0,
                    "effective_score_path_ts_count": 1,
                },
            ],
        },
    )
    _write_json(
        gap_path,
        {
            "summary": {
                "score_completion_blocking_gap_dp_ids": [
                    "L0.cost.cac",
                    "L7.flow.active_inflow",
                ],
            },
            "participating_gap_rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "blocking_gap": True,
                    "priority": "P2_llm_or_web_extraction",
                },
                {
                    "dp_id": "L7.flow.active_inflow",
                    "blocking_gap": True,
                    "priority": "P2_llm_or_web_extraction",
                }
            ],
        },
    )
    _write_json(
        candidate_path,
        {
            "summary": {
                "safe_to_upsert_without_review_count": 0,
            },
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "score_target": "fundamental_score",
                    "candidate_status": "ready_for_local_llm_candidate",
                    "candidate_input_ready": True,
                    "recommended_source_route": "local_llm_closed_loop",
                    "source_dependencies": ["L5.is.sga_rd", "L5.is.revenue"],
                },
                {
                    "dp_id": "L7.flow.active_inflow",
                    "score_target": "funding_score",
                    "candidate_status": "ready_for_local_llm_candidate",
                    "candidate_input_ready": True,
                    "recommended_source_route": "local_llm_closed_loop",
                    "source_dependencies": ["L7.flow.northbound"],
                }
            ],
        },
    )
    _write_json(
        readiness_path,
        {
            "summary": {
                "direct_structured_tushare_remaining": 0,
            },
            "rows": [],
        },
    )
    spec_path.write_text(
        yaml.safe_dump(
            {
                "spec_total_dp_ids": 2,
                "data_points": {
                    "L0.cost.cac": {
                        "source_status": "missing",
                        "calculation_type": "weighted_contribution",
                        "aggregation_policy": "weighted_sum",
                    },
                    "L7.flow.active_inflow": {
                        "source_status": "ok",
                        "calculation_type": "raw_value",
                        "aggregation_policy": "weighted_sum",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    report = build_report(
        trace_path=trace_path,
        gap_path=gap_path,
        candidate_path=candidate_path,
        readiness_path=readiness_path,
        spec_path=spec_path,
    )

    assert report["summary"]["spec_total_matches_runtime"] is True
    assert report["summary"]["blocking_gap_dp_ids"] == 1
    assert report["summary"]["candidate_ready_blocking_gap_dp_ids"] == 1
    assert report["summary"]["closed_score_relevant_dp_ids"] == 1
    assert report["summary"]["direct_structured_tushare_remaining"] == 0
    blocker = report["blocking_rows"][0]
    assert blocker["dp_id"] == "L0.cost.cac"
    assert blocker["closure_status"] == "overlay_only_no_score_candidate"
    assert blocker["repair_route"] == "candidate_generation_required:local_llm_closed_loop"
    closed = {row["dp_id"]: row for row in report["rows"]}["L7.flow.active_inflow"]
    assert closed["closure_status"] == "closed_reaches_final_score"
    assert closed["blocking_gap"] is False
    assert closed["candidate_status"] is None
