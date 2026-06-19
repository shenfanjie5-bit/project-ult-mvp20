import json
from pathlib import Path

from scripts import audit_a_share_unknown_event_strict_review_packets as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_strict_review_packets_triage_low_quality_and_false_positive(
    tmp_path: Path,
) -> None:
    strict_gate_path = tmp_path / "strict_gate.json"
    _write_json(
        strict_gate_path,
        {
            "rows": [
                {
                    "dp_id": "L0.compete.new_entrant",
                    "score_target": "fundamental_score",
                    "strict_gate_status": "strict_review_candidates_found",
                    "candidate_examples": [
                        {
                            "market_relative_path": "news/eastmoney_guba/a.html",
                            "title": "竞争对手正在迅速崛起_股吧",
                            "excerpt": "以阿里平头哥为代表的竞争对手正在迅速崛起。",
                            "strict_gate_verdict": "strict_review_candidate",
                            "strict_hits": ["竞争对手"],
                            "direct_transmission_hits": ["产业链"],
                        }
                    ],
                },
                {
                    "dp_id": "L0.tech.substitute_tech",
                    "score_target": "fundamental_score",
                    "strict_gate_status": "strict_review_candidates_found",
                    "candidate_examples": [
                        {
                            "market_relative_path": "news/cls_flash/b.html",
                            "title": "3天2板江顺科技",
                            "excerpt": "公司主营业务之一为铝型材挤压模具及配件产品。",
                            "strict_gate_verdict": "strict_review_candidate",
                            "strict_hits": ["挤压"],
                            "direct_transmission_hits": ["板块"],
                        },
                        {
                            "market_relative_path": "news/cls_flash/c.html",
                            "title": "替代技术威胁光伏产业链",
                            "excerpt": "替代技术威胁A股板块，或造成部分上市公司份额流失。",
                            "strict_gate_verdict": "strict_review_candidate",
                            "strict_hits": ["替代技术", "份额流失"],
                            "direct_transmission_hits": ["A股", "板块"],
                        },
                    ],
                },
            ]
        },
    )

    report = audit.build_report(strict_gate_path=strict_gate_path)

    assert report["summary"]["strict_review_packet_count"] == 3
    assert report["summary"]["source_quality_low_confidence_count"] == 1
    assert report["summary"]["source_quality_secondary_newswire_count"] == 2
    assert report["summary"]["requires_primary_source_confirmation_count"] == 1
    assert report["summary"]["requires_manual_review_count"] == 1
    assert report["summary"]["deterministic_rejected_count"] == 1
    assert report["summary"]["classifier_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    by_reason = {
        row["strict_candidate_reason"]: row
        for row in report["rows"]
    }
    assert (
        by_reason["community_or_forum_source_cannot_support_known_value"][
            "strict_candidate_status"
        ]
        == "requires_primary_source_confirmation"
    )
    assert (
        by_reason["false_positive_process_term_not_substitution_risk"][
            "strict_candidate_status"
        ]
        == "deterministic_rejected"
    )
    assert "narrow the strict-source review queue" in audit.render_markdown(report)
