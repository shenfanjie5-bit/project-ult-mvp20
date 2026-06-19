import json
from pathlib import Path

from scripts import audit_a_share_event_text_preclassification_screen as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _row(dp_id: str, titles: list[str], *, full_text: bool = False) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "source_dependencies": ["L9.media.report"],
        "classification_status": "classification_input_ready",
        "headline_input_count": len(titles),
        "unique_headline_count": len(set(titles)),
        "title_level_input_ready": bool(titles),
        "full_article_text_available": full_text,
        "headline_inputs": [
            {
                "dependency_dp_id": "L9.media.report",
                "title": title,
                "time": "2026-06-19T01:00:00",
                "url": f"https://example.test/{idx}",
                "source": "unit",
            }
            for idx, title in enumerate(titles)
        ],
        "blocked_reason": "unit",
        "required_policy": "unit policy",
    }


def test_event_text_preclassification_keeps_keyword_hits_review_gated(
    tmp_path: Path,
) -> None:
    inputs_path = tmp_path / "classification_inputs.json"
    _write_json(
        inputs_path,
        {
            "rows": [
                _row("L0.compete.price_war", ["A股行业价格战引发板块调整"]),
                _row("L8.shock.black_swan", ["霍尔木兹海峡大型商船通行"]),
                _row("L0.tech.ai_automation", ["纽约时报广场发生枪击"]),
            ]
        },
    )

    report = audit.build_report(classification_inputs_path=inputs_path)

    assert report["summary"]["preclassification_packet_count"] == 3
    assert report["summary"]["packets_screened_count"] == 3
    assert report["summary"]["target_keyword_hit_packet_count"] == 2
    assert report["summary"]["a_share_transmission_hit_packet_count"] == 1
    assert report["summary"]["target_and_transmission_hit_packet_count"] == 1
    assert report["summary"]["direct_known_candidate_count"] == 0
    assert report["summary"]["classified_known_count"] == 0
    assert report["summary"]["safe_to_upsert_without_review_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    rows = {row["dp_id"]: row for row in report["rows"]}
    assert (
        rows["L0.compete.price_war"]["screening_status"]
        == "screened_target_and_transmission_keyword_hit_requires_review"
    )
    assert rows["L0.compete.price_war"]["preclassification_decision"]["data_status"] == "Unknown"
    assert (
        rows["L0.compete.price_war"]["preclassification_decision"][
            "direct_known_candidate_allowed"
        ]
        is False
    )
    assert rows["L0.compete.price_war"]["safe_to_upsert_without_review"] is False
    assert rows["L8.shock.black_swan"]["screening_status"] == (
        "screened_target_keyword_hit_without_a_share_transmission"
    )
    assert rows["L0.tech.ai_automation"]["screening_status"] == "screened_no_target_keyword_hit"
    assert "Preclassification packets: `3`" in audit.render_markdown(report)


def test_event_text_preclassification_deduplicates_titles_and_tracks_full_text(
    tmp_path: Path,
) -> None:
    inputs_path = tmp_path / "classification_inputs.json"
    _write_json(
        inputs_path,
        {
            "rows": [
                _row(
                    "L0.policy.tax_trade",
                    ["人民币汇率波动影响出口", "人民币汇率波动影响出口"],
                    full_text=True,
                )
            ]
        },
    )

    report = audit.build_report(classification_inputs_path=inputs_path)

    assert report["summary"]["title_level_only_count"] == 0
    assert report["summary"]["target_keyword_hit_packet_count"] == 1
    assert report["summary"]["a_share_transmission_hit_packet_count"] == 1
    row = report["rows"][0]
    assert row["matched_headline_count"] == 1
    assert row["full_article_text_available"] is True
    assert row["title_level_only"] is False
