import json
from pathlib import Path

from scripts import audit_a_share_unknown_external_business_metric_review_packets as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _candidate(dp_id: str, classification: str, numeric_hits: list[str]) -> dict:
    return {
        "dp_id": dp_id,
        "classification": classification,
        "target_hits": ["渗透率"],
        "support_hits": ["市场"],
        "scope_hits": ["行业"],
        "direct_transmission_hits": [],
        "numeric_hits": numeric_hits,
        "title": "候选标题",
        "market_relative_path": f"news/{dp_id}.html",
        "path": f"/Volumes/dockcase2tb/market_data/news/{dp_id}.html",
        "excerpt": "行业渗透率达到12%，市场规模扩大。",
    }


def test_external_business_metric_review_packets_keep_missing_fields(
    tmp_path: Path,
) -> None:
    candidates_path = tmp_path / "candidates.json"
    _write_json(
        candidates_path,
        {
            "summary": {"review_candidate_count": 2},
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "candidate_examples": [
                        _candidate(
                            "L0.demand.penetration",
                            "numeric_review_candidate",
                            ["12%"],
                        ),
                        _candidate(
                            "L0.demand.penetration",
                            "textual_review_candidate",
                            [],
                        ),
                        _candidate(
                            "L0.demand.penetration",
                            "weak_metric_context",
                            ["12%"],
                        ),
                    ],
                }
            ],
        },
    )

    report = audit.build_report(market_doc_candidates_path=candidates_path)

    assert report["summary"]["business_metric_review_packet_count"] == 2
    assert report["summary"]["expected_review_candidate_count"] == 2
    assert report["summary"]["review_candidate_retention_complete"] is True
    assert report["summary"]["numeric_review_packet_count"] == 1
    assert report["summary"]["textual_review_packet_count"] == 1
    assert report["summary"]["metric_inputs_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["packet_contract_valid_count"] == 2
    assert report["summary"]["production_write_allowed_count"] == 0

    packet = report["rows"][0]
    assert packet["data_status"] == "Unknown"
    assert packet["required_fields"]["formula_policy"]["status"] == "review_required"
    assert "formula_policy" in packet["missing_fields"]
    assert packet["runtime_write_allowed"] is False
    assert "Business metric review packets: `2`" in audit.render_markdown(report)


def test_current_external_business_metric_review_packets_match_gate() -> None:
    path = Path(
        "docs/audit/a_share_unknown_external_business_metric_review_packets_2026-06-19.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["business_metric_review_packet_count"] == 99
    assert report["summary"]["expected_review_candidate_count"] == 99
    assert report["summary"]["review_candidate_retention_complete"] is True
    assert report["summary"]["rows_with_review_packets_count"] == 3
    assert report["summary"]["numeric_review_packet_count"] == 49
    assert report["summary"]["textual_review_packet_count"] == 50
    assert report["summary"]["metric_inputs_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
