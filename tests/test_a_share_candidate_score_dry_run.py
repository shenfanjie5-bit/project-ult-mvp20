import json
from pathlib import Path

from scripts import audit_a_share_candidate_score_dry_run as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_candidate_score_dry_run_emits_nodes_for_bridge_contracts(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.json"
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
                    "dp_id": "L6.mult.dcf",
                    "score_target": "valuation_rerating",
                    "candidate_status": "ready_for_manual_design_candidate",
                    "recommended_source_route": "manual_design_review",
                    "candidate_input_ready": True,
                },
                {
                    "dp_id": "L6.priced.realization_risk",
                    "score_target": "priced_in_discount",
                    "candidate_status": "ready_for_manual_design_candidate",
                    "recommended_source_route": "manual_design_review",
                    "candidate_input_ready": True,
                },
                {
                    "dp_id": "L7.reflex.tag",
                    "score_target": "reflexivity_multiplier",
                    "candidate_status": "ready_for_manual_design_candidate",
                    "recommended_source_route": "manual_design_review",
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
                    "dp_id": "L8.val.slope_risk_off",
                    "score_target": "risk_discount",
                    "candidate_status": "ready_for_manual_design_candidate",
                    "recommended_source_route": "manual_design_review",
                    "candidate_input_ready": True,
                },
            ]
        },
    )

    report = audit.build_report(candidate_path, "000001.SZ")

    assert report["summary"]["candidate_ready_rows_checked"] == 6
    assert report["summary"]["bridge_signal_ready_count"] == 6
    assert report["summary"]["node_emitted_count"] == 6
    assert report["summary"]["final_score_target_ready_count"] == 6
    assert report["summary"]["bridge_blocked_dp_ids"] == []
    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L6.mult.dcf"]["bridge_payload"]["scalar"] == 0.15
    assert by_dp["L6.priced.realization_risk"]["bridge_signal"] == 0.2
    assert by_dp["L7.trade.gamma"]["bridge_signal"] == 0.0
    assert "Candidate-ready rows checked: `6`" in audit.render_markdown(report)


def test_candidate_score_dry_run_skips_not_ready_rows(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.json"
    _write_json(
        candidate_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "score_target": "fundamental_score",
                    "candidate_status": "ready_for_local_llm_candidate",
                    "recommended_source_route": "local_llm_closed_loop",
                    "candidate_input_ready": False,
                }
            ]
        },
    )

    report = audit.build_report(candidate_path, "000001.SZ")

    assert report["summary"]["candidate_ready_rows_checked"] == 0
    assert report["summary"]["bridge_blocked_count"] == 0
