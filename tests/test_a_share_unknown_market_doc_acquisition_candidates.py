import json
from pathlib import Path

from scripts import audit_a_share_unknown_market_doc_acquisition_candidates as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _html(title: str, body: str) -> str:
    return f"<html><head><title>{title}</title></head><body>{body}</body></html>"


def _task(dp_id: str) -> dict:
    return {
        "task_id": f"task-{dp_id}",
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "acquisition_track": "dockcase_market_doc_deep_search",
        "source_priority": "market-doc",
        "production_write_allowed": False,
    }


def test_unknown_market_doc_acquisition_candidates_classify_local_evidence(
    tmp_path: Path,
) -> None:
    backlog_path = tmp_path / "backlog.json"
    market_root = tmp_path / "market"
    news_dir = market_root / "news" / "cls_flash"
    news_dir.mkdir(parents=True)
    _write_json(
        backlog_path,
        {
            "rows": [
                _task("L0.compete.new_entrant"),
                _task("L0.tech.substitute_tech"),
            ]
        },
    )
    (news_dir / "entrant_review.html").write_text(
        _html(
            "北方稀土成立新公司建设产线",
            "北方稀土公告称，公司拟与合作方合资成立新公司建设稀土材料项目。A股产业链供给格局或受影响。",
        ),
        encoding="utf-8",
    )
    (news_dir / "entrant_reject.html").write_text(
        _html(
            "银行理财入局IPO打新潮",
            "银行理财入局IPO打新潮，多家机构参与A股IPO网下配售。",
        ),
        encoding="utf-8",
    )
    (news_dir / "substitute_clean.html").write_text(
        _html(
            "AI替代风险冲击软件板块",
            "人工智能替代技术加速落地，A股软件板块面临被替代风险和估值压力。",
        ),
        encoding="utf-8",
    )
    (news_dir / "substitute_reject.html").write_text(
        _html(
            "产品替代进口设备",
            "公司产品在PCB领域已规模化替代进口设备，产业链受益。",
        ),
        encoding="utf-8",
    )

    report = audit.build_report(
        backlog_path=backlog_path,
        market_root=market_root,
    )

    assert report["summary"]["market_doc_acquisition_task_count"] == 2
    assert report["summary"]["market_html_files_scanned"] == 4
    assert report["summary"]["market_html_read_error_count"] == 0
    assert report["summary"]["rows_with_review_candidates_count"] == 2
    assert report["summary"]["new_entrant_window_candidate_count"] == 2
    assert report["summary"]["new_entrant_review_candidate_count"] >= 1
    assert report["summary"]["substitute_same_sentence_candidate_count"] == 2
    assert report["summary"]["substitute_clean_risk_review_candidate_count"] == 1
    assert report["summary"]["rejected_candidate_count"] >= 2
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    rows = {row["dp_id"]: row for row in report["rows"]}
    assert rows["L0.compete.new_entrant"]["candidate_status"] == (
        "local_window_review_candidates_found"
    )
    assert rows["L0.compete.new_entrant"]["review_candidate_count"] >= 1
    assert rows["L0.compete.new_entrant"]["rejected_candidate_count"] >= 1
    assert rows["L0.tech.substitute_tech"]["candidate_status"] == (
        "insufficient_clean_risk_review_candidates"
    )
    assert rows["L0.tech.substitute_tech"]["production_write_allowed"] is False
    assert "Market-doc acquisition tasks: `2`" in audit.render_markdown(report)


def test_current_unknown_market_doc_acquisition_report_matches_gate() -> None:
    path = Path(
        "docs/audit/a_share_unknown_market_doc_acquisition_candidates_2026-06-19.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["market_doc_acquisition_task_count"] == 2
    assert report["summary"]["market_html_files_scanned"] == 14956
    assert report["summary"]["market_html_read_error_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
