import json
from pathlib import Path

from scripts import audit_a_share_unknown_external_business_metric_policy_drafts as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _row(dp_id: str, packet_id: str, priority: str = "P0_formula_policy_only") -> dict:
    return {
        "packet_id": packet_id,
        "dp_id": dp_id,
        "candidate_classification": "numeric_review_candidate",
        "priority": priority,
        "numeric_hits": ["12%"],
        "title": "候选",
        "market_relative_path": f"news/{packet_id}.html",
        "excerpt": "行业渗透率达到12%，市场规模扩大。",
    }


def test_policy_drafts_package_only_p0_packets(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    _write_json(
        readiness_path,
        {
            "rows": [
                _row("L0.demand.penetration", "p0"),
                _row("L0.demand.replacement", "p2", "P2_denominator_required"),
            ]
        },
    )

    report = audit.build_report(readiness_queue_path=readiness_path)

    assert report["summary"]["p0_source_packet_count"] == 1
    assert report["summary"]["policy_draft_packet_count"] == 1
    assert report["summary"]["formula_policy_review_required_count"] == 1
    assert report["summary"]["value_json_template_count"] == 1
    assert report["summary"]["policy_review_template_count"] == 1
    assert report["summary"]["policy_review_template_contract_valid_count"] == 1
    assert report["summary"]["policy_review_template_contract_invalid_count"] == 0
    assert report["summary"]["policy_review_template_blank_pending_count"] == 1
    assert report["summary"]["policy_review_template_input_ready_count"] == 0
    assert report["summary"]["metric_inputs_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["policy_contract_valid_count"] == 1
    assert report["summary"]["production_write_allowed_count"] == 0

    draft = report["rows"][0]
    assert draft["data_status"] == "Unknown"
    assert draft["source_packet_id"] == "p0"
    assert draft["policy_draft_status"] == "formula_policy_review_required"
    assert draft["value_json_template"]["raw_value"] is None
    assert draft["policy_review_template_contract_valid"] is True
    assert draft["policy_review_template_validation_errors"] == []
    assert draft["policy_review_template"]["review_scope"] == (
        "external_business_metric_formula_policy"
    )
    assert draft["policy_review_template"]["reviewer"] == ""
    assert draft["policy_review_template"]["reviewed_at"] == ""
    assert draft["policy_review_template"]["numeric_value_selected"] is False
    assert draft["policy_review_template"]["value_json_ready"] is False
    assert draft["policy_review_template"]["known_draft_allowed"] is False
    assert draft["policy_review_template"]["production_write_allowed"] is False
    assert draft["runtime_write_allowed"] is False
    assert "Policy draft packets: `1`" in audit.render_markdown(report)
    assert "Policy review templates: `1`" in audit.render_markdown(report)


def test_current_external_business_metric_policy_drafts_match_gate() -> None:
    path = Path(
        "docs/audit/a_share_unknown_external_business_metric_policy_drafts_2026-06-19.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["p0_source_packet_count"] == 18
    assert report["summary"]["policy_draft_packet_count"] == 18
    assert report["summary"]["formula_policy_review_required_count"] == 18
    assert report["summary"]["value_json_template_count"] == 18
    assert report["summary"]["policy_review_template_count"] == 18
    assert report["summary"]["policy_review_template_contract_valid_count"] == 18
    assert report["summary"]["policy_review_template_contract_invalid_count"] == 0
    assert report["summary"]["policy_review_template_blank_pending_count"] == 18
    assert report["summary"]["policy_review_template_input_ready_count"] == 0
    assert report["summary"]["metric_inputs_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["policy_contract_valid_count"] == 18
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["policy_draft_counts_by_dp_id"] == {
        "L0.demand.frequency": 1,
        "L0.demand.penetration": 17,
    }
