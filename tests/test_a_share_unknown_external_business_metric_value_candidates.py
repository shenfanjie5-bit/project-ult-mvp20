import json
from pathlib import Path

from scripts import audit_a_share_unknown_external_business_metric_value_candidates as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _policy_row(
    dp_id: str,
    policy_draft_id: str,
    numeric_hits: list[str],
    title: str,
    excerpt: str,
) -> dict:
    return {
        "policy_draft_id": policy_draft_id,
        "source_packet_id": f"src-{policy_draft_id}",
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "data_status": "Unknown",
        "candidate_classification": "numeric_review_candidate",
        "numeric_hits": numeric_hits,
        "title": title,
        "market_relative_path": f"news/{policy_draft_id}.html",
        "excerpt": excerpt,
    }


def test_value_candidates_reject_dates_foreign_scope_and_keep_review_shortlist(
    tmp_path: Path,
) -> None:
    policy_path = tmp_path / "policy.json"
    _write_json(
        policy_path,
        {
            "rows": [
                _policy_row(
                    "L0.demand.penetration",
                    "good",
                    ["2025年", "12%"],
                    "A股公司市场份额提升",
                    "上市公司在国内细分市场市占率达到12%。",
                ),
                _policy_row(
                    "L0.demand.penetration",
                    "foreign",
                    ["0.8%", "1月"],
                    "欧盟市场份额",
                    "欧盟1月新车市场份额为0.8%。",
                ),
                _policy_row(
                    "L0.demand.frequency",
                    "frequency",
                    ["55%"],
                    "需求增长",
                    "未来十年复合年均增长超55%。",
                ),
            ]
        },
    )

    report = audit.build_report(policy_draft_path=policy_path)

    assert report["summary"]["policy_draft_packet_count"] == 3
    assert report["summary"]["value_candidate_adjudication_row_count"] == 3
    assert report["summary"]["rows_with_value_candidate_tokens_count"] == 2
    assert report["summary"]["value_candidate_token_count"] == 2
    assert report["summary"]["rejected_numeric_token_count"] == 3
    assert report["summary"]["shortlist_review_required_count"] == 1
    assert report["summary"]["scope_rejected_count"] == 1
    assert report["summary"]["no_scoreable_numeric_candidate_count"] == 1
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["value_candidate_contract_valid_count"] == 3

    rows = {row["policy_draft_id"]: row for row in report["rows"]}
    assert rows["good"]["adjudication_status"] == (
        "value_candidate_shortlist_review_required"
    )
    assert rows["good"]["value_candidate_tokens"] == [{"token": "12%", "unit": "percent"}]
    assert rows["foreign"]["adjudication_status"] == "scope_rejected"
    assert rows["frequency"]["adjudication_status"] == "no_scoreable_numeric_candidate"
    assert "Shortlist review required: `1`" in audit.render_markdown(report)


def test_current_external_business_metric_value_candidates_match_gate() -> None:
    path = Path(
        "docs/audit/a_share_unknown_external_business_metric_value_candidates_2026-06-19.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["policy_draft_packet_count"] == 18
    assert report["summary"]["value_candidate_adjudication_row_count"] == 18
    assert report["summary"]["rows_with_value_candidate_tokens_count"] == 9
    assert report["summary"]["value_candidate_token_count"] == 13
    assert report["summary"]["rejected_numeric_token_count"] == 31
    assert report["summary"]["shortlist_review_required_count"] == 6
    assert report["summary"]["scope_rejected_count"] == 3
    assert report["summary"]["scope_ambiguous_count"] == 0
    assert report["summary"]["no_scoreable_numeric_candidate_count"] == 9
    assert report["summary"]["metric_inputs_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["value_candidate_contract_valid_count"] == 18
    assert report["summary"]["production_write_allowed_count"] == 0
