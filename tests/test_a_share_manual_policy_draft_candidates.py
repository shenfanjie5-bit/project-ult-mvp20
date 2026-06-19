import json
from pathlib import Path

from scripts import audit_a_share_manual_policy_draft_candidates as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _task(dp_id: str, score_target: str) -> dict:
    return {
        "task_id": f"a_share_candidate::manual_policy_candidate::{dp_id}",
        "dp_id": dp_id,
        "score_target": score_target,
        "generator_kind": "manual_policy_candidate",
    }


def _dep(dp_id: str, row_count: int, known_count: int, samples: list[dict]) -> dict:
    return {
        "dp_id": dp_id,
        "row_count": row_count,
        "known_count": known_count,
        "sample_rows": [
            {
                "ts_code": f"00000{idx}.SZ",
                "data_status": "Known",
                "confidence": 0.6,
                "source": "test",
                "value_json_compact": sample,
            }
            for idx, sample in enumerate(samples, start=1)
        ],
    }


def _candidate(dp_id: str, score_target: str, deps: list[dict]) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "candidate_status": "ready_for_manual_design_candidate",
        "recommended_source_route": "manual_design_review",
        "source_dependencies": [dep["dp_id"] for dep in deps],
        "candidate_input": {
            "target_dp_id": dp_id,
            "score_target": score_target,
            "dependencies": deps,
            "manual_design_policy": {"policy_name": f"policy::{dp_id}"},
        },
    }


def _fixtures(tmp_path: Path) -> tuple[Path, Path]:
    queue_path = tmp_path / "queue.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(
        queue_path,
        {
            "tasks": [
                _task("L6.mult.dcf", "valuation_rerating"),
                _task("L6.priced.realization_risk", "priced_in_discount"),
                _task("L7.reflex.tag", "reflexivity_multiplier"),
                _task("L8.val.slope_risk_off", "risk_discount"),
                {
                    "task_id": "a_share_candidate::local_llm_candidate::L0.cost.cac",
                    "dp_id": "L0.cost.cac",
                    "score_target": "fundamental_score",
                    "generator_kind": "local_llm_candidate",
                },
            ]
        },
    )
    _write_json(
        candidate_path,
        {
            "rows": [
                _candidate(
                    "L6.mult.dcf",
                    "valuation_rerating",
                    [
                        _dep("L5.cf.fcf", 10, 10, [{"scalar": 100.0}]),
                        _dep("L5.is.revenue_growth", 10, 10, [{"yoy_pct": 8.0}]),
                        _dep("L6.sens.rates", 10, 10, [{"multiplier": 1.0}]),
                        _dep("L6.sens.growth_margin", 10, 10, [{"multiplier": 0.9}]),
                        _dep("L6.sens.cashflow", 10, 10, [{"multiplier": 0.8}]),
                        _dep("L6.mult.mcap_fcf", 10, 10, [{"scalar": 12.0}]),
                    ],
                ),
                _candidate(
                    "L6.priced.realization_risk",
                    "priced_in_discount",
                    [
                        _dep(
                            "L6.priced.run_up",
                            100,
                            90,
                            [{"d20_pct": 0.10}, {"d20_pct": -0.05}, {"d5_pct": 0.04}],
                        ),
                        _dep("L6.priced.news_age", 100, 90, [{"magnitude": 0.6}]),
                        _dep("L5.surprise.preprice", 100, 20, [{"score": 0.2}]),
                        _dep("L8.val.priced_in", 100, 100, [{"priced_in_score": 0.2}]),
                    ],
                ),
                _candidate(
                    "L7.reflex.tag",
                    "reflexivity_multiplier",
                    [
                        _dep(
                            "L7.flow.active_inflow",
                            100,
                            100,
                            [{"main_net": 50000}, {"main_net": -5000}],
                        ),
                        _dep("L7.mood.fomo", 100, 100, [{"score": 0.2}]),
                        _dep("L7.mood.media_social", 100, 5, [{"rank_overall": 10}]),
                        _dep("L6.priced.run_up", 100, 90, [{"d20_pct": 0.05}]),
                    ],
                ),
                _candidate(
                    "L8.val.slope_risk_off",
                    "risk_discount",
                    [
                        _dep(
                            "L6.path.second_derivative",
                            100,
                            90,
                            [{"second_derivative": -0.004}, {"second_derivative": -0.006}],
                        ),
                        _dep("L8.val.overvalued", 100, 90, [{"max_quantile": 0.7}]),
                        _dep("L7.env.risk_appetite", 100, 90, [{"multiplier": 0.98}]),
                        _dep("L9.macro.rates", 2, 1, [{"lpr_1y_change_bp": -10.0}]),
                        _dep("L6.state.expansion_compression", 100, 10, [{"score": 0.1}]),
                    ],
                ),
            ]
        },
    )
    return queue_path, candidate_path


def test_manual_policy_draft_candidates_builds_review_only_known_and_unknown(tmp_path: Path) -> None:
    queue_path, candidate_path = _fixtures(tmp_path)

    report = audit.build_report(queue_path, candidate_path)

    assert report["summary"]["manual_policy_task_count"] == 4
    assert report["summary"]["draft_payload_count"] == 4
    assert report["summary"]["draft_known_count"] == 4
    assert report["summary"]["draft_unknown_count"] == 0
    assert report["summary"]["draft_contract_valid_count"] == 4
    assert report["summary"]["draft_contract_invalid_count"] == 0
    assert report["summary"]["draft_contract_invalid_dp_ids"] == []
    assert report["summary"]["bridge_validated_known_count"] == 4
    assert report["summary"]["bridge_blocked_known_count"] == 0
    assert report["summary"]["review_required_count"] == 4
    assert report["summary"]["pilot_only_count"] == 4
    assert report["summary"]["safe_to_upsert_without_review_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["draft_status_counts"] == {
        "draft_known_standard_dcf_assumption_review_required": 1,
        "draft_known_review_required": 3,
    }

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    dcf = by_dp["L6.mult.dcf"]["draft_payload"]
    assert dcf["data_status"] == "Known"
    assert -1.0 <= dcf["value_json"]["score"] <= 1.0
    assert 0.0 <= dcf["value_json"]["magnitude"] <= 1.0
    assert dcf["value_json"]["drivers"]
    assert dcf["value_json"]["dcf_assumptions"]["discount_rate"] > 0
    assert dcf["value_json"]["dcf_assumptions"]["forecast_horizon_years"] == 5
    assert dcf["safe_to_upsert_without_review"] is False
    assert by_dp["L6.mult.dcf"]["contract_validation"]["contract_valid"] is True
    assert by_dp["L6.mult.dcf"]["bridge_validation"]["final_score_target_ready"]

    realization = by_dp["L6.priced.realization_risk"]["draft_payload"]
    assert realization["data_status"] == "Known"
    assert 0.0 <= realization["value_json"]["magnitude"] <= 1.0
    assert realization["value_json"]["drivers"]
    assert by_dp["L6.priced.realization_risk"]["contract_validation"][
        "contract_valid"
    ] is True
    assert by_dp["L6.priced.realization_risk"]["bridge_validation"][
        "final_score_target_ready"
    ]

    reflex = by_dp["L7.reflex.tag"]["draft_payload"]
    assert reflex["value_json"]["tag"] in {
        "positive_feedback",
        "exhausted_feedback",
        "neutral",
    }
    assert 0.0 < reflex["value_json"]["multiplier"] <= 2.0

    slope = by_dp["L8.val.slope_risk_off"]["draft_payload"]
    assert 0.0 <= slope["value_json"]["magnitude"] <= 1.0
    assert slope["value_json"]["drivers"]
    assert "Draft contracts valid: `4`" in audit.render_markdown(report)
    assert "Known drafts bridge-validated: `4`" in audit.render_markdown(report)


def test_manual_policy_draft_candidates_keep_missing_evidence_unknown(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(
        queue_path,
        {"tasks": [_task("L8.val.slope_risk_off", "risk_discount")]},
    )
    _write_json(candidate_path, {"rows": []})

    report = audit.build_report(queue_path, candidate_path)

    assert report["summary"]["manual_policy_task_count"] == 1
    assert report["summary"]["draft_known_count"] == 0
    assert report["summary"]["draft_unknown_count"] == 1
    assert report["summary"]["draft_contract_valid_count"] == 1
    assert report["summary"]["safe_to_upsert_without_review_count"] == 0
    row = report["rows"][0]
    assert row["draft_status"] == "unknown_missing_candidate_evidence"
    assert row["draft_payload"]["value_json"]["blocked_reason"] == "missing_candidate_evidence"
