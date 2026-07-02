import json
from pathlib import Path

from scripts import audit_a_share_unknown_external_business_metric_value_review_packets as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _shortlist_row(
    row_id: str,
    tokens: list[str],
    status: str = "value_candidate_shortlist_review_required",
) -> dict:
    return {
        "value_candidate_adjudication_id": row_id,
        "dp_id": "L0.demand.penetration",
        "score_target": "fundamental_score",
        "data_status": "Unknown",
        "adjudication_status": status,
        "source_scope_verdict": "review_a_share_or_domestic_scope",
        "title": "A股公司市场份额提升",
        "market_relative_path": f"news/{row_id}.html",
        "excerpt": "上市公司在国内细分市场市占率达到12%。",
        "value_candidate_tokens": [{"token": token, "unit": "percent"} for token in tokens],
    }


def test_value_review_packets_probe_formula_bridge_but_do_not_select_value(
    tmp_path: Path,
) -> None:
    value_candidates_path = tmp_path / "value_candidates.json"
    _write_json(
        value_candidates_path,
        {
            "rows": [
                _shortlist_row("good", ["12%", "15%"]),
                _shortlist_row("skip", ["30%"], "scope_rejected"),
            ]
        },
    )

    report = audit.build_report(value_candidates_path=value_candidates_path)

    assert report["summary"]["shortlist_source_row_count"] == 1
    assert report["summary"]["value_review_packet_count"] == 1
    assert report["summary"]["candidate_value_option_count"] == 2
    assert report["summary"]["bridge_probe_ready_option_count"] == 2
    assert report["summary"]["selected_raw_value_count"] == 0
    assert report["summary"]["metric_inputs_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["value_review_contract_valid_count"] == 1

    packet = report["rows"][0]
    assert packet["data_status"] == "Unknown"
    assert packet["selected_raw_value"] is None
    assert packet["selected_value_json"] is None
    scores = [
        option["formula_probe_score"] for option in packet["candidate_value_options"]
    ]
    assert scores == [0.12, 0.15]
    assert all(
        option["bridge_validation"]["final_score_target_ready"]
        for option in packet["candidate_value_options"]
    )
    assert "Bridge-probe-ready options: `2`" in audit.render_markdown(report)


def test_current_external_business_metric_value_review_packets_match_gate() -> None:
    path = Path(
        "docs/audit/a_share_unknown_external_business_metric_value_review_packets_2026-06-19.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["shortlist_source_row_count"] == 6
    assert report["summary"]["value_review_packet_count"] == 6
    assert report["summary"]["candidate_value_option_count"] == 8
    assert report["summary"]["bridge_probe_ready_option_count"] == 8
    assert report["summary"]["selected_raw_value_count"] == 0
    assert report["summary"]["selected_value_json_count"] == 0
    assert report["summary"]["metric_inputs_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["value_review_contract_valid_count"] == 6
    assert report["summary"]["production_write_allowed_count"] == 0
