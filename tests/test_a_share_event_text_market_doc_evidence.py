import json
from pathlib import Path

from scripts import audit_a_share_event_text_market_doc_evidence as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _html(title: str, body: str) -> str:
    return f"<html><head><title>{title}</title></head><body>{body}</body></html>"


def _unknown_row(dp_id: str) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "risk_discount",
        "production_write_allowed": False,
    }


def test_event_text_market_doc_evidence_finds_review_candidates(
    tmp_path: Path,
) -> None:
    event_unknown_path = tmp_path / "event_unknown.json"
    market_root = tmp_path / "market"
    news_dir = market_root / "news" / "cls_flash"
    news_dir.mkdir(parents=True)
    _write_json(
        event_unknown_path,
        {
            "rows": [
                _unknown_row("L0.compete.price_war"),
                _unknown_row("L0.compete.new_entrant"),
                _unknown_row("L0.tech.ai_automation"),
            ]
        },
    )
    (news_dir / "price.html").write_text(
        _html(
            "光伏出口退税取消进入倒计时",
            "业内认为，依赖出口退税打价格战的中小企业更加不利。",
        ),
        encoding="utf-8",
    )
    (news_dir / "entrant.html").write_text(
        _html("新玩家入局", "新玩家入局智能终端市场，后续影响待观察。"),
        encoding="utf-8",
    )
    (news_dir / "noise.html").write_text(
        _html(
            "无关正文",
            "正文无关。财联社声明：仅供参考。热门解锁 AI产业链板块。",
        ),
        encoding="utf-8",
    )

    report = audit.build_report(
        event_unknown_path=event_unknown_path,
        market_root=market_root,
    )

    assert report["summary"]["unknown_event_text_rows_checked"] == 3
    assert report["summary"]["market_html_files_scanned"] == 3
    assert report["summary"]["market_html_read_error_count"] == 0
    assert report["summary"]["rows_with_market_doc_target_evidence_count"] == 2
    assert report["summary"]["rows_with_same_sentence_candidate_count"] == 1
    assert report["summary"]["rows_still_requiring_target_evidence_count"] == 1
    assert report["summary"]["rows_still_requiring_direct_transmission_link_count"] == 1
    assert report["summary"]["market_doc_review_candidate_count"] == 1
    assert report["summary"]["production_write_allowed_count"] == 0

    rows = {row["dp_id"]: row for row in report["rows"]}
    assert (
        rows["L0.compete.price_war"]["resolution_status"]
        == "market_docs_candidate_requires_review"
    )
    assert (
        rows["L0.compete.new_entrant"]["resolution_status"]
        == "market_docs_require_direct_transmission_link"
    )
    assert (
        rows["L0.tech.ai_automation"]["resolution_status"]
        == "market_docs_require_target_event_evidence"
    )
    assert rows["L0.compete.price_war"]["retained_examples"][0]["same_sentence_hits"]
    assert "Market-doc review candidates: `1`" in audit.render_markdown(report)


def test_current_event_text_market_doc_evidence_report_matches_gate() -> None:
    path = Path("docs/audit/a_share_event_text_market_doc_evidence_2026-06-19.json")
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["unknown_event_text_rows_checked"] == 12
    assert report["summary"]["market_html_files_scanned"] == 14956
    assert report["summary"]["market_html_read_error_count"] == 0
    assert report["summary"]["rows_with_market_doc_target_evidence_count"] == 12
    assert report["summary"]["rows_with_same_sentence_candidate_count"] == 11
    assert report["summary"]["rows_still_requiring_target_evidence_count"] == 0
    assert report["summary"]["rows_still_requiring_direct_transmission_link_count"] == 1
    assert report["summary"]["market_doc_review_candidate_count"] == 11
    assert report["summary"]["production_write_allowed_count"] == 0


def test_current_goal_coverage_includes_event_text_market_doc_evidence() -> None:
    source_path = Path("docs/audit/a_share_event_text_market_doc_evidence_2026-06-19.json")
    goal_path = Path("docs/audit/goal_coverage_2026-06-19.json")

    source_summary = json.loads(source_path.read_text(encoding="utf-8"))["summary"]
    goal_report = json.loads(goal_path.read_text(encoding="utf-8"))
    a_share_row = next(
        row
        for row in goal_report["requirements"]
        if row["requirement_id"] == "a_share_score_field_path"
    )

    assert (
        a_share_row["evidence"]["event_text_market_doc_evidence_summary"]
        == source_summary
    )
    assert "event_text_market_doc_evidence" in a_share_row["evidence_strength"]
    assert (
        "Event-text market-doc evidence scan checks 12 Unknown rows"
        in a_share_row["remaining_gap"]
    )
