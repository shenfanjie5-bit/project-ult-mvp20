import json
from pathlib import Path

from scripts import audit_a_share_event_text_market_doc_review_packets as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _market_row(dp_id: str, same_sentence_count: int, examples: list[dict] | None) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "target_keywords": ["价格战"],
        "docs_with_target_evidence": 2,
        "docs_with_direct_transmission": 2,
        "docs_with_target_and_direct": 2,
        "docs_with_same_sentence_target_direct": same_sentence_count,
        "docs_with_broad_market_only": 0,
        "retained_examples": examples or [],
    }


def test_event_text_market_doc_review_packets_keeps_outputs_review_only(
    tmp_path: Path,
) -> None:
    market_path = tmp_path / "market.json"
    unknown_path = tmp_path / "unknown.json"
    _write_json(
        market_path,
        {
            "rows": [
                _market_row(
                    "L0.compete.price_war",
                    1,
                    [
                        {
                            "market_relative_path": "news/price.html",
                            "title": "光伏出口退税取消进入倒计时",
                            "same_sentence_hits": [
                                {
                                    "target_hits": ["价格战"],
                                    "direct_transmission_hits": ["出口"],
                                    "excerpt": "依赖出口退税打价格战的中小企业更加不利。",
                                }
                            ],
                            "excerpt": "依赖出口退税打价格战的中小企业更加不利。",
                        }
                    ],
                ),
                _market_row("L0.compete.new_entrant", 0, []),
            ]
        },
    )
    _write_json(
        unknown_path,
        {
            "rows": [
                {"dp_id": "L0.compete.price_war", "score_target": "fundamental_score"},
                {"dp_id": "L0.compete.new_entrant", "score_target": "fundamental_score"},
            ]
        },
    )

    report = audit.build_report(
        market_doc_evidence_path=market_path,
        event_unknown_path=unknown_path,
    )

    assert report["summary"]["event_text_packet_count"] == 2
    assert report["summary"]["market_doc_review_ready_count"] == 1
    assert report["summary"]["requires_direct_transmission_link_count"] == 1
    assert report["summary"]["candidate_example_count"] == 1
    assert report["summary"]["packet_contract_valid_count"] == 2
    assert report["summary"]["packet_contract_invalid_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    rows = {row["dp_id"]: row for row in report["rows"]}
    assert (
        rows["L0.compete.price_war"]["classification_packet_status"]
        == "market_doc_review_ready"
    )
    assert rows["L0.compete.price_war"]["data_status"] == "Unknown"
    assert rows["L0.compete.price_war"]["candidate_examples"]
    assert rows["L0.compete.price_war"]["production_write_allowed"] is False
    assert (
        rows["L0.compete.new_entrant"]["classification_packet_status"]
        == "requires_direct_transmission_link"
    )
    assert rows["L0.compete.new_entrant"]["candidate_examples"] == []
    assert "Market-doc review-ready: `1`" in audit.render_markdown(report)


def test_current_event_text_market_doc_review_packets_report_matches_gate() -> None:
    path = Path("docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json")
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["event_text_packet_count"] == 12
    assert report["summary"]["market_doc_review_ready_count"] == 11
    assert report["summary"]["requires_target_event_evidence_count"] == 0
    assert report["summary"]["requires_direct_transmission_link_count"] == 1
    assert report["summary"]["candidate_example_count"] == 53
    assert report["summary"]["packet_contract_valid_count"] == 12
    assert report["summary"]["packet_contract_invalid_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0


def test_current_goal_coverage_includes_event_text_market_doc_review_packets() -> None:
    source_path = Path(
        "docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json"
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
        a_share_row["evidence"]["event_text_market_doc_review_packets_summary"]
        == source_summary
    )
    assert "event_text_market_doc_review_packets" in a_share_row["evidence_strength"]
    assert (
        "Event-text market-doc review packets package 12 packets"
        in a_share_row["remaining_gap"]
    )
