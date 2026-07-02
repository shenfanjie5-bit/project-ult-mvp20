import json
from pathlib import Path

from scripts import audit_a_share_local_single_dependency_unknown_source_options as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _draft_row(dp_id: str) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "draft_status": "unknown_policy_required",
        "draft_payload": {
            "data_status": "Unknown",
            "value_json": {
                "blocked_reason": "revenue_only_cannot_identify_replacement_cycle",
                "required_policy": "replacement demand needs lifecycle evidence",
            },
        },
    }


def _candidate(dp_id: str) -> dict:
    dep = {
        "dp_id": "L5.is.revenue",
        "row_count": 1755,
        "known_count": 1755,
        "ts_code_count": 1755,
        "namespace_counts": {"stock": 1755},
        "latest_updated_at_iso": "2026-06-11T07:49:14+00:00",
        "sample_rows": [
            {
                "ts_code": "000001.SZ",
                "data_status": "Known",
                "source": "tushare:income",
                "value_json_compact": {
                    "scalar": 35277000000.0,
                    "unit": "元",
                    "period": "20260331",
                },
            }
        ],
    }
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "candidate_status": "ready_for_local_llm_candidate",
        "source_dependencies": ["L5.is.revenue"],
        "dependency_evidence": {
            "L5.is.revenue": {
                "row_count": 1755,
                "known_count": 1755,
                "source_counts": {"tushare:income": 1640, "fmp:income-statement": 115},
                "namespace_counts": {"stock": 1755},
            }
        },
        "candidate_input": {
            "target_dp_id": dp_id,
            "score_target": "fundamental_score",
            "dependencies": [dep],
        },
    }


def _write_overlay(root: Path) -> None:
    path = root / "AI_COMPUTE" / "688256.SH.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
schema_version: 1
ts_code: 688256.SH
industry_id: AI_COMPUTE
nodes:
  - dp_id: L3.product.lifecycle
    status: Known
    data_status: Known
    confidence: 0.68
    last_updated: '2026-06-02T22:30:00+08:00'
    value:
      phase: 成长
      competitive_score: 4.0
      evidence_summary: annual report lifecycle context
    evidence_sources:
      - kind: local_dp_id
        dp_id: L9.disclosure.annual_report
  - dp_id: L0.demand.replacement
    status: Unknown
    data_status: Unknown
""",
        encoding="utf-8",
    )

def test_single_dependency_unknown_source_options_keeps_replacement_review_gated(
    tmp_path: Path,
) -> None:
    single_path = tmp_path / "single.json"
    candidate_path = tmp_path / "candidate.json"
    overlay_root = tmp_path / "stock_overlays"
    _write_overlay(overlay_root)
    _write_json(single_path, {"rows": [_draft_row("L0.demand.replacement")]})
    _write_json(candidate_path, {"rows": [_candidate("L0.demand.replacement")]})

    report = audit.build_report(
        single_path,
        candidate_path,
        stock_overlay_root=overlay_root,
    )

    assert report["summary"]["unknown_local_single_dependency_count"] == 1
    assert report["summary"]["existing_runtime_dependency_ready_count"] == 1
    assert report["summary"]["direct_replacement_cycle_source_ready_count"] == 0
    assert report["summary"]["overlay_candidate_hint_count"] == 1
    assert report["summary"]["rows_with_overlay_lifecycle_context_candidate_count"] == 1
    assert report["summary"]["overlay_lifecycle_known_node_count"] == 1
    assert report["summary"]["overlay_replacement_known_node_count"] == 0
    assert report["summary"]["overlay_replacement_unknown_node_count"] == 1
    assert report["summary"]["candidate_requires_lifecycle_source_count"] == 1
    assert report["summary"]["candidate_requires_review_policy_count"] == 1
    assert report["summary"]["lifecycle_policy_review_template_count"] == 1
    assert report["summary"]["lifecycle_policy_review_template_contract_valid_count"] == 1
    assert report["summary"]["lifecycle_policy_review_template_contract_invalid_count"] == 0
    assert report["summary"]["lifecycle_policy_review_template_blank_pending_count"] == 1
    assert report["summary"]["lifecycle_policy_review_template_input_ready_count"] == 0
    assert report["summary"]["auto_known_candidate_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    row = report["rows"][0]
    assert row["dp_id"] == "L0.demand.replacement"
    assert row["runtime_dependency_ready"] is True
    assert row["direct_replacement_cycle_source_ready"] is False
    assert row["overlay_lifecycle_context_candidate_available"] is True
    assert (
        row["overlay_lifecycle_context_candidate"]["direct_replacement_cycle_source_ready"]
        is False
    )
    assert row["lifecycle_policy_review_template_contract_valid"] is True
    assert row["lifecycle_policy_review_template_validation_errors"] == []
    template = row["lifecycle_policy_review_template"]
    assert template["template_status"] == "review_fill_required"
    assert template["review_scope"] == "replacement_lifecycle_policy"
    assert template["reviewer"] == ""
    assert template["reviewed_at"] == ""
    assert template["review_decision"] == ""
    assert template["overlay_lifecycle_known_node_count"] == 1
    assert template["overlay_replacement_known_node_count"] == 0
    assert template["overlay_replacement_unknown_node_count"] == 1
    assert template["source_dependency_dp_ids"] == ["L5.is.revenue"]
    assert template["lifecycle_source_accepted"] is False
    assert template["replacement_cycle_mapping_accepted"] is False
    assert template["known_draft_allowed"] is False
    assert template["auto_known_allowed"] is False
    assert template["safe_to_upsert_without_review"] is False
    assert template["production_write_allowed"] is False
    assert row["resolution_status"] == "requires_lifecycle_or_replacement_cycle_source"
    assert row["known_draft_sufficient"] is False
    assert row["approval_ready"] is False
    assert row["review_required"] is True
    assert row["production_write_allowed"] is False
    assert "Direct replacement-cycle source-ready rows: `0`" in audit.render_markdown(report)
    assert "Lifecycle-policy review templates: `1`" in audit.render_markdown(report)


def test_single_dependency_unknown_source_options_keeps_missing_candidate_gated(
    tmp_path: Path,
) -> None:
    single_path = tmp_path / "single.json"
    candidate_path = tmp_path / "candidate.json"
    overlay_root = tmp_path / "stock_overlays"
    _write_json(single_path, {"rows": [_draft_row("L0.demand.replacement")]})
    _write_json(candidate_path, {"rows": []})

    report = audit.build_report(
        single_path,
        candidate_path,
        stock_overlay_root=overlay_root,
    )

    assert report["summary"]["unknown_local_single_dependency_count"] == 1
    assert report["summary"]["existing_runtime_dependency_ready_count"] == 0
    assert report["summary"]["rows_with_overlay_lifecycle_context_candidate_count"] == 0
    assert report["summary"]["lifecycle_policy_review_template_count"] == 0
    row = report["rows"][0]
    assert row["runtime_dependency_ready"] is False
    assert row["lifecycle_policy_review_template"] is None
    assert row["lifecycle_policy_review_template_contract_valid"] is False
    assert row["lifecycle_policy_review_template_validation_errors"] == []
    assert row["known_draft_sufficient"] is False
    assert row["approval_ready"] is False
    assert row["review_required"] is True
    assert row["safe_to_upsert_without_review"] is False


def test_current_single_dependency_unknown_source_options_report_matches_expected_gate() -> None:
    path = Path(
        "docs/audit/a_share_local_single_dependency_unknown_source_options_2026-06-19.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["unknown_local_single_dependency_count"] == 1
    assert report["summary"]["existing_runtime_dependency_ready_count"] == 1
    assert report["summary"]["direct_replacement_cycle_source_ready_count"] == 0
    assert report["summary"]["rows_with_overlay_lifecycle_context_candidate_count"] == 1
    assert report["summary"]["overlay_lifecycle_known_node_count"] > 0
    assert report["summary"]["overlay_replacement_unknown_node_count"] > 0
    assert report["summary"]["candidate_requires_lifecycle_source_count"] == 1
    assert report["summary"]["candidate_requires_review_policy_count"] == 1
    assert report["summary"]["lifecycle_policy_review_template_count"] == 1
    assert report["summary"]["lifecycle_policy_review_template_contract_valid_count"] == 1
    assert report["summary"]["lifecycle_policy_review_template_contract_invalid_count"] == 0
    assert report["summary"]["lifecycle_policy_review_template_blank_pending_count"] == 1
    assert report["summary"]["lifecycle_policy_review_template_input_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0


def test_current_goal_coverage_includes_single_dependency_unknown_source_options() -> None:
    source_path = Path(
        "docs/audit/a_share_local_single_dependency_unknown_source_options_2026-06-19.json"
    )
    goal_path = Path("docs/audit/goal_coverage_2026-06-19.json")

    source_summary = json.loads(source_path.read_text(encoding="utf-8"))["summary"]
    goal_report = json.loads(goal_path.read_text(encoding="utf-8"))
    a_share_row = next(
        row
        for row in goal_report["requirements"]
        if row["requirement_id"] == "a_share_score_field_path"
    )

    assert (
        a_share_row["evidence"]["single_dependency_unknown_source_options_summary"]
        == source_summary
    )
    rows = a_share_row["evidence"]["single_dependency_unknown_source_options_rows"]
    assert len(rows) == 1
    assert rows[0]["dp_id"] == "L0.demand.replacement"
    assert rows[0]["source_dependencies"] == ["L5.is.revenue"]
    assert rows[0]["resolution_status"] == "requires_lifecycle_or_replacement_cycle_source"
    assert rows[0]["lifecycle_policy_review_template_contract_valid"] is True
    assert rows[0]["known_draft_sufficient"] is False
    assert rows[0]["approval_ready"] is False
    assert rows[0]["production_write_allowed"] is False
    assert "single_dependency_unknown_source_options" in a_share_row["evidence_strength"]
    assert (
        "Local single-dependency Unknown source-options audit reviews 1 Unknown rows"
        in a_share_row["remaining_gap"]
    )
    assert any(
        "1 single-dependency lifecycle sources required" in blocker
        for blocker in goal_report["summary"]["completion_blockers"]
    )
