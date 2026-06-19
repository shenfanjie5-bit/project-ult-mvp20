import json
from pathlib import Path

from scripts import audit_a_share_unknown_event_strict_source_gate as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_html(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"<html><head><title>{title}</title></head><body>{body}</body></html>",
        encoding="utf-8",
    )


def test_event_strict_source_gate_keeps_only_strict_candidates(tmp_path: Path) -> None:
    market_root = tmp_path / "market_data"
    _write_html(
        market_root / "news/cls/strict_new.html",
        "外部厂商跨界进入储能市场",
        "外部厂商跨界进入储能市场，抢占A股公司订单并影响供应链议价。",
    )
    _write_html(
        market_root / "news/cls/rejected_new.html",
        "北方稀土拟合资成立新公司",
        "上市公司公告称，公司拟以自有资金合资成立新公司并由子公司建设项目。",
    )
    _write_html(
        market_root / "news/cls/strict_substitute.html",
        "替代技术威胁光伏产业链",
        "替代技术威胁A股板块，或造成部分上市公司份额流失。",
    )
    backlog_path = tmp_path / "backlog.json"
    adjudication_path = tmp_path / "adjudication.json"
    _write_json(
        backlog_path,
        {
            "rows": [
                {"dp_id": "L0.compete.new_entrant", "score_target": "fundamental_score"},
                {"dp_id": "L0.tech.substitute_tech", "score_target": "fundamental_score"},
            ]
        },
    )
    _write_json(
        adjudication_path,
        {
            "rows": [
                {
                    "dp_id": "L0.compete.new_entrant",
                    "adjudication_status": "no_clean_known_candidate_after_adjudication",
                    "accepted_candidate_count": 0,
                },
                {
                    "dp_id": "L0.tech.substitute_tech",
                    "adjudication_status": "no_clean_known_candidate_after_adjudication",
                    "accepted_candidate_count": 0,
                },
            ]
        },
    )

    report = audit.build_report(
        backlog_path=backlog_path,
        adjudication_path=adjudication_path,
        market_root=market_root,
    )

    assert report["summary"]["event_strict_gate_row_count"] == 2
    assert report["summary"]["market_html_files_scanned"] == 3
    assert report["summary"]["rows_with_strict_review_candidates_count"] == 2
    assert report["summary"]["classifier_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.compete.new_entrant"]["strict_review_candidate_count"] == 1
    assert by_dp["L0.tech.substitute_tech"]["strict_review_candidate_count"] == 1
    assert by_dp["L0.compete.new_entrant"]["data_status"] == "Unknown"
    assert "Strict source candidates are still classifier inputs" in audit.render_markdown(
        report
    )
