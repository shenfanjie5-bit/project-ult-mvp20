import json
from pathlib import Path

from scripts import audit_a_share_unknown_event_evidence_adjudication as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_unknown_event_evidence_adjudication_splits_clean_and_false_positive_candidates(
    tmp_path: Path,
) -> None:
    candidate_path = tmp_path / "candidates.json"
    closure_path = tmp_path / "closure.json"
    _write_json(
        candidate_path,
        {
            "rows": [
                {
                    "dp_id": "L0.compete.new_entrant",
                    "score_target": "fundamental_score",
                    "candidate_status": "local_window_review_candidates_found",
                    "review_candidate_count": 2,
                    "candidate_examples": [
                        {
                            "title": "外部厂商跨界进入储能市场",
                            "classification": "review_candidate",
                            "market_relative_path": "news/entrant-clean.html",
                            "excerpt": "外部厂商跨界进入储能市场，A股产业链份额和价格压力上升。",
                        },
                        {
                            "title": "北方稀土成立新公司建设产线",
                            "classification": "review_candidate",
                            "market_relative_path": "news/entrant-incumbent.html",
                            "excerpt": "北方稀土公告称，公司拟以自有资金合资成立新公司，并以新公司为主体建设项目，纳入公司合并报表范围。",
                        },
                    ],
                },
                {
                    "dp_id": "L0.tech.substitute_tech",
                    "score_target": "fundamental_score",
                    "candidate_status": "clean_risk_review_candidates_found",
                    "review_candidate_count": 2,
                    "candidate_examples": [
                        {
                            "title": "AI替代风险冲击软件板块",
                            "classification": "clean_risk_review_candidate",
                            "market_relative_path": "news/sub-clean.html",
                            "excerpt": "替代技术加速落地，A股软件板块面临被替代风险和份额流失。",
                        },
                        {
                            "title": "公司产品规模化替代进口设备",
                            "classification": "clean_risk_review_candidate",
                            "market_relative_path": "news/sub-import.html",
                            "excerpt": "公司产品在PCB领域已规模化替代进口设备，产业链受益。",
                        },
                    ],
                },
            ]
        },
    )
    _write_json(
        closure_path,
        {
            "rows": [
                {
                    "dp_id": "L0.compete.new_entrant",
                    "score_target": "fundamental_score",
                    "blocked_reason": "market_doc_direct_transmission_link_required",
                },
                {
                    "dp_id": "L0.tech.substitute_tech",
                    "score_target": "fundamental_score",
                    "blocked_reason": "market_doc_clean_substitution_risk_evidence_required",
                },
            ]
        },
    )

    report = audit.build_report(candidate_path=candidate_path, closure_path=closure_path)

    assert report["summary"]["event_unknown_adjudication_row_count"] == 2
    assert report["summary"]["candidate_examples_reviewed_count"] == 4
    assert report["summary"]["accepted_candidate_count"] == 2
    assert report["summary"]["rejected_or_ambiguous_candidate_count"] == 2
    assert report["summary"]["remaining_unknown_count"] == 2
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["adjudication_contract_valid_count"] == 2
    assert report["summary"]["adjudication_contract_invalid_count"] == 0
    rows = {row["dp_id"]: row for row in report["rows"]}
    assert rows["L0.compete.new_entrant"]["accepted_candidate_count"] == 1
    assert rows["L0.tech.substitute_tech"]["accepted_candidate_count"] == 1
    assert "rejected_incumbent_expansion" in rows["L0.compete.new_entrant"][
        "adjudication_verdict_counts"
    ]
    assert "rejected_opportunity_or_import_substitution" in rows[
        "L0.tech.substitute_tech"
    ]["adjudication_verdict_counts"]
    assert "Accepted candidates: `2`" in audit.render_markdown(report)


def test_current_unknown_event_evidence_adjudication_report_matches_gate() -> None:
    path = Path("docs/audit/a_share_unknown_event_evidence_adjudication_2026-06-19.json")
    if not path.exists():
        return
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["event_unknown_adjudication_row_count"] == 2
    assert report["summary"]["accepted_candidate_count"] == 0
    assert report["summary"]["remaining_unknown_count"] == 2
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["auto_known_ready_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
