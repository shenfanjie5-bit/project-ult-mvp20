import json
from pathlib import Path

from scripts import audit_a_share_manual_policy_unknown_source_options as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _draft_row(dp_id: str) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "valuation_rerating",
        "manual_policy_name": "bounded_dcf_assumption_candidate",
        "draft_status": "unknown_assumptions_required",
        "draft_payload": {
            "data_status": "Unknown",
            "value_json": {
                "blocked_reason": "dcf_assumptions_require_review",
                "required_assumptions": [
                    "discount_rate",
                    "terminal_growth",
                    "forecast_horizon",
                    "normalized_fcf",
                ],
            },
        },
    }


def _dep(dp_id: str, row_count: int = 10, known_count: int = 10) -> dict:
    return {
        "dp_id": dp_id,
        "row_count": row_count,
        "known_count": known_count,
        "ts_code_count": row_count,
        "namespace_counts": {"stock": row_count},
        "latest_updated_at_iso": "2026-06-11T07:49:14+00:00",
        "sample_rows": [
            {
                "ts_code": "000001.SZ",
                "data_status": "Known",
                "source": "test",
                "value_json_compact": {"scalar": 1.0},
            }
        ],
    }


def _candidate(dp_id: str) -> dict:
    deps = [
        _dep("L5.cf.fcf"),
        _dep("L5.is.revenue_growth"),
        _dep("L6.sens.rates"),
        _dep("L6.sens.growth_margin"),
        _dep("L6.sens.cashflow"),
        _dep("L6.mult.mcap_fcf"),
    ]
    return {
        "dp_id": dp_id,
        "score_target": "valuation_rerating",
        "candidate_status": "ready_for_manual_design_candidate",
        "recommended_source_route": "manual_design_review",
        "source_dependencies": [dep["dp_id"] for dep in deps],
        "dependency_evidence": {
            dep["dp_id"]: {
                "row_count": dep["row_count"],
                "known_count": dep["known_count"],
                "source_counts": {"test": dep["row_count"]},
                "namespace_counts": dep["namespace_counts"],
            }
            for dep in deps
        },
        "candidate_input": {
            "target_dp_id": dp_id,
            "score_target": "valuation_rerating",
            "dependencies": deps,
        },
    }


def test_manual_policy_unknown_source_options_keeps_dcf_review_gated(
    tmp_path: Path,
) -> None:
    manual_path = tmp_path / "manual.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(manual_path, {"rows": [_draft_row("L6.mult.dcf")]})
    _write_json(candidate_path, {"rows": [_candidate("L6.mult.dcf")]})

    report = audit.build_report(manual_path, candidate_path)

    assert report["summary"]["unknown_manual_policy_count"] == 1
    assert report["summary"]["dependency_pack_ready_count"] == 1
    assert report["summary"]["direct_reviewed_assumption_ready_count"] == 0
    assert report["summary"]["required_assumption_count"] == 4
    assert report["summary"]["candidate_requires_assumption_review_count"] == 1
    assert report["summary"]["candidate_requires_review_policy_count"] == 1
    assert report["summary"]["auto_known_candidate_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    row = report["rows"][0]
    assert row["dp_id"] == "L6.mult.dcf"
    assert row["dependency_pack_ready"] is True
    assert row["direct_reviewed_assumption_ready"] is False
    assert row["resolution_status"] == "requires_reviewed_dcf_assumptions"
    assert row["required_assumptions"] == [
        "discount_rate",
        "terminal_growth",
        "forecast_horizon",
        "normalized_fcf",
    ]
    assert row["production_write_allowed"] is False
    assert "Direct reviewed-assumption-ready rows: `0`" in audit.render_markdown(report)


def test_manual_policy_unknown_source_options_keeps_missing_candidate_gated(
    tmp_path: Path,
) -> None:
    manual_path = tmp_path / "manual.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(manual_path, {"rows": [_draft_row("L6.mult.dcf")]})
    _write_json(candidate_path, {"rows": []})

    report = audit.build_report(manual_path, candidate_path)

    assert report["summary"]["unknown_manual_policy_count"] == 1
    assert report["summary"]["dependency_pack_ready_count"] == 0
    row = report["rows"][0]
    assert row["dependency_pack_ready"] is False
    assert row["review_required"] is True
    assert row["safe_to_upsert_without_review"] is False


def test_current_manual_policy_unknown_source_options_report_matches_expected_gate() -> None:
    path = Path("docs/audit/a_share_manual_policy_unknown_source_options_2026-06-19.json")
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["unknown_manual_policy_count"] == 0
    assert report["summary"]["dependency_pack_ready_count"] == 0
    assert report["summary"]["direct_reviewed_assumption_ready_count"] == 0
    assert report["summary"]["required_assumption_count"] == 0
    assert report["summary"]["candidate_requires_assumption_review_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0


def test_current_goal_coverage_includes_manual_policy_unknown_source_options() -> None:
    source_path = Path("docs/audit/a_share_manual_policy_unknown_source_options_2026-06-19.json")
    goal_path = Path("docs/audit/goal_coverage_2026-06-19.json")

    source_summary = json.loads(source_path.read_text(encoding="utf-8"))["summary"]
    goal_report = json.loads(goal_path.read_text(encoding="utf-8"))
    a_share_row = next(
        row
        for row in goal_report["requirements"]
        if row["requirement_id"] == "a_share_score_field_path"
    )

    assert (
        a_share_row["evidence"]["manual_policy_unknown_source_options_summary"]
        == source_summary
    )
    assert "manual_policy_unknown_source_options" in a_share_row["evidence_strength"]
    assert (
        "Manual-policy Unknown source-options audit reviews 0 Unknown rows"
        in a_share_row["remaining_gap"]
    )
    assert any(
        "0 manual-policy required assumptions" in blocker
        for blocker in goal_report["summary"]["completion_blockers"]
    )
