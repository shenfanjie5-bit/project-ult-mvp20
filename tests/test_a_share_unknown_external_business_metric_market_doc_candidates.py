import json
from pathlib import Path

from scripts import (
    audit_a_share_unknown_external_business_metric_market_doc_candidates as audit,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _task(dp_id: str) -> dict:
    return {
        "task_id": f"task-{dp_id}",
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "acquisition_track": "external_or_text_business_metric",
        "source_priority": "source",
    }


def _write_html(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"<html><head><title>{title}</title></head><body>{body}</body></html>",
        encoding="utf-8",
    )


def test_external_business_metric_market_doc_scan_packages_review_candidates(
    tmp_path: Path,
) -> None:
    backlog_path = tmp_path / "backlog.json"
    market_root = tmp_path / "market_data"
    _write_json(
        backlog_path,
        {
            "rows": [
                _task("L0.demand.frequency"),
                _task("L0.demand.penetration"),
                _task("L0.demand.replacement"),
            ]
        },
    )
    _write_html(
        market_root / "news" / "candidate.html",
        "业务指标候选",
        (
            "公司会员复购率达到35%，订单频次提升，A股上市公司用户活跃。"
            "产品渗透率达到12%，行业市场规模扩大，上市公司销量增长。"
            "家电以旧换新推动更新需求，存量设备更换周期约8年，A股产业链受益。"
        ),
    )
    _write_html(
        market_root / "news" / "rejected.html",
        "股吧评论",
        "股吧网友评论复购，但没有业务口径。",
    )

    report = audit.build_report(
        backlog_path=backlog_path,
        market_root=market_root,
        retained_examples_per_dp=4,
    )

    assert report["summary"]["business_metric_market_doc_task_count"] == 3
    assert report["summary"]["market_html_files_scanned"] == 2
    assert report["summary"]["market_html_read_error_count"] == 0
    assert report["summary"]["rows_with_review_candidates_count"] == 3
    assert report["summary"]["review_candidate_count"] == 3
    assert report["summary"]["numeric_review_candidate_count"] == 3
    assert report["summary"]["weak_candidate_count"] == 0
    assert report["summary"]["rejected_candidate_count"] == 1
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["metric_inputs_ready_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["packet_contract_valid_count"] == 3

    rows = {row["dp_id"]: row for row in report["rows"]}
    assert rows["L0.demand.frequency"]["candidate_status"] == (
        "local_cadence_review_candidates_found"
    )
    assert rows["L0.demand.penetration"]["candidate_status"] == (
        "local_penetration_review_candidates_found"
    )
    assert rows["L0.demand.replacement"]["candidate_status"] == (
        "local_replacement_review_candidates_found"
    )
    assert rows["L0.demand.frequency"]["rejected_candidate_count"] == 1
    assert "Review candidates: `3`" in audit.render_markdown(report)


def test_current_external_business_metric_market_doc_report_matches_gate() -> None:
    path = Path(
        "docs/audit/"
        "a_share_unknown_external_business_metric_market_doc_candidates_2026-06-19.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["business_metric_market_doc_task_count"] == 3
    assert report["summary"]["market_html_read_error_count"] == 0
    assert report["summary"]["rows_with_review_candidates_count"] >= 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["metric_inputs_ready_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
