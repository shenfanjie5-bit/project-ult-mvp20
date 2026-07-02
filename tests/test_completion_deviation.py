from __future__ import annotations

import json

from scripts.audit_completion_deviation import build_report, render_markdown


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_completion_deviation_report_meets_current_mvp_target(tmp_path):
    a_share = _write_json(
        tmp_path / "a_share.json",
        {
            "summary": {
                "current_mvp_closed_count": 132,
                "current_mvp_denominator_count": 132,
                "current_mvp_final_score_closure_pct": 100.0,
                "current_mvp_deviation_pct": 0.0,
                "current_mvp_actionable_gap_count": 0,
                "raw_current_numeric_final_score_count": 132,
                "raw_score_relevant_final_target_count": 174,
                "current_mvp_excluded_count": 54,
                "score_sink_no_final_score_delta_count": 12,
            }
        },
    )
    score_sink = _write_json(
        tmp_path / "score_sink.json",
        {
            "summary": {
                "candidate_dp_id_count": 12,
                "no_final_score_delta_count": 12,
                "effectful_count": 0,
            }
        },
    )
    execution = _write_json(
        tmp_path / "execution.json",
        {
            "summary": {
                "execution_status": "executed",
                "post_write_verified_row_count": 11006,
                "post_write_verification_error_count": 0,
            }
        },
    )
    materialization_review = _write_json(
        tmp_path / "materialization_review.json",
        {
            "summary": {
                "current_value_contract_error_count": 0,
                "noop_updated_at_changed_count": 0,
            }
        },
    )
    modules = _write_json(
        tmp_path / "modules.json",
        {
            "counts": {
                "locked_total": 14,
                "artifact_callable": 6,
                "normal_dependency_not_service": 1,
                "missing_or_stub_only": 7,
                "replacement_path_verified": 7,
                "replacement_path_unverified": 0,
            }
        },
    )
    bff = _write_json(
        tmp_path / "bff.json",
        {
            "all_ok": True,
            "all_under_threshold": True,
            "max_observed_ms": 42.0,
        },
    )
    dockcase = _write_json(
        tmp_path / "dockcase.json",
        {"summary": {"current_mvp_data_quality_actionable_gap_count": 0}},
    )

    report = build_report(
        a_share_applicability_path=a_share,
        a_share_score_sink_effect_path=score_sink,
        a_share_execution_path=execution,
        a_share_materialization_review_path=materialization_review,
        module_status_path=modules,
        bff_latency_path=bff,
        dockcase_quality_path=dockcase,
    )

    assert report["summary"]["total_completion_pct"] == 100.0
    assert report["summary"]["total_deviation_pct"] == 0.0
    assert report["summary"]["meets_completion_target"] is True
    assert report["summary"]["meets_deviation_target"] is True
    assert len(report["components"]) == 5
    assert "a_share_final_score_closure" in render_markdown(report)
