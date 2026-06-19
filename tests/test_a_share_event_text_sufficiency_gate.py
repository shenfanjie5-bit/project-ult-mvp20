import json
from pathlib import Path

from scripts import audit_a_share_event_text_sufficiency_gate as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _row(
    dp_id: str,
    matched_headlines: list[dict],
    *,
    full_text: bool = False,
) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "risk_discount",
        "screening_status": "screened_target_and_transmission_keyword_hit_requires_review",
        "source_dependencies": ["L9.media.report"],
        "headline_input_count": len(matched_headlines),
        "unique_headline_count": len(matched_headlines),
        "full_article_text_available": full_text,
        "title_level_only": not full_text,
        "matched_headlines": matched_headlines,
    }


def _headline(
    title: str,
    *,
    target: list[str] | None = None,
    transmission: list[str] | None = None,
) -> dict:
    return {
        "title": title,
        "time": "2026-06-19T01:00:00",
        "url": "https://example.test/article",
        "source": "unit",
        "dependency_dp_id": "L9.media.report",
        "target_keyword_hits": target or [],
        "a_share_transmission_keyword_hits": transmission or [],
    }


def test_sufficiency_gate_rejects_separate_target_and_a50_headlines(
    tmp_path: Path,
) -> None:
    preclassification_path = tmp_path / "preclassification.json"
    _write_json(
        preclassification_path,
        {
            "rows": [
                _row(
                    "L8.shock.black_swan",
                    [
                        _headline("霍尔木兹海峡开始有大型商船通行", target=["霍尔木兹"]),
                        _headline("富时中国A50指数期货夜盘收跌", transmission=["A50", "中国A50", "期货"]),
                    ],
                )
            ]
        },
    )

    report = audit.build_report(preclassification_path=preclassification_path)

    assert report["summary"]["sufficiency_packet_count"] == 1
    assert report["summary"]["target_headline_packet_count"] == 1
    assert report["summary"]["broad_market_only_transmission_packet_count"] == 1
    assert report["summary"]["same_headline_target_and_any_transmission_packet_count"] == 0
    assert report["summary"]["same_headline_target_and_direct_transmission_packet_count"] == 0
    assert report["summary"]["title_signal_sufficient_for_classifier_count"] == 0
    assert report["summary"]["known_candidate_allowed_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    row = report["rows"][0]
    assert row["sufficiency_status"] == (
        "insufficient_target_hit_with_broad_market_only_transmission"
    )
    assert row["title_signal_sufficient_for_classifier"] is False
    assert row["known_candidate_allowed"] is False
    assert row["safe_to_upsert_without_review"] is False
    assert "Sufficiency packets: `1`" in audit.render_markdown(report)


def test_sufficiency_gate_requires_full_text_for_same_headline_direct_signal(
    tmp_path: Path,
) -> None:
    preclassification_path = tmp_path / "preclassification.json"
    _write_json(
        preclassification_path,
        {
            "rows": [
                _row(
                    "L0.policy.tax_trade",
                    [
                        _headline(
                            "出口管制冲击A股上市公司供应链",
                            target=["出口管制"],
                            transmission=["A股", "上市公司", "供应链"],
                        )
                    ],
                ),
                _row(
                    "L0.policy.tax_trade",
                    [
                        _headline(
                            "出口管制冲击A股上市公司供应链",
                            target=["出口管制"],
                            transmission=["A股", "上市公司", "供应链"],
                        )
                    ],
                    full_text=True,
                ),
            ]
        },
    )

    report = audit.build_report(preclassification_path=preclassification_path)

    assert report["summary"]["same_headline_target_and_direct_transmission_packet_count"] == 2
    assert report["summary"]["title_signal_sufficient_for_classifier_count"] == 2
    assert report["summary"]["known_candidate_allowed_count"] == 0
    statuses = [row["sufficiency_status"] for row in report["rows"]]
    assert statuses == [
        "candidate_same_headline_direct_transmission_needs_full_text",
        "candidate_full_text_review_required",
    ]
