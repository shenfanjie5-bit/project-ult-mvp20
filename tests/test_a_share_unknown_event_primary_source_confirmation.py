import json
from pathlib import Path

from scripts import audit_a_share_unknown_event_primary_source_confirmation as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_html(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"<html><head><title>{title}</title></head><body>{body}</body></html>",
        encoding="utf-8",
    )


def test_primary_source_confirmation_scans_non_community_sources(
    tmp_path: Path,
) -> None:
    market_root = tmp_path / "market_data"
    _write_html(
        market_root / "news/eastmoney_guba/2026/02/noisy.html",
        "股吧线索",
        "阿里平头哥竞争对手正在崛起，影响寒武纪产业链。",
    )
    _write_html(
        market_root / "news/cls_flash/2026/02/support.html",
        "阿里云算力产品调价",
        "平头哥真武810E等算力卡产品价格上涨。",
    )
    _write_html(
        market_root / "news/cls_flash/2026/02/confirm.html",
        "寒武纪面临竞争压力",
        "阿里平头哥算力卡崛起，成为寒武纪AI芯片竞争对手并挤压A股产业链订单。",
    )
    strict_review_path = tmp_path / "strict_review.json"
    _write_json(
        strict_review_path,
        {
            "rows": [
                {
                    "packet_id": "L0.compete.new_entrant#strict_review_candidate#1",
                    "dp_id": "L0.compete.new_entrant",
                    "score_target": "fundamental_score",
                    "strict_candidate_status": "requires_primary_source_confirmation",
                    "candidate": {
                        "title": "低置信线索",
                        "excerpt": "以阿里平头哥为代表的竞争对手正在迅速崛起",
                    },
                }
            ]
        },
    )

    report = audit.build_report(
        strict_review_path=strict_review_path,
        market_root=market_root,
    )

    assert report["summary"]["primary_confirmation_packet_count"] == 1
    assert report["summary"]["market_html_files_scanned"] == 3
    assert report["summary"]["local_candidate_count"] == 2
    assert report["summary"]["local_high_quality_confirmation_candidate_count"] == 1
    assert report["summary"]["local_supporting_context_only_count"] == 1
    assert report["summary"]["classifier_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    row = report["rows"][0]
    assert row["local_confirmation_status"] == "local_high_quality_confirmation_candidates_found"
    assert all(
        "eastmoney_guba" not in (candidate["market_relative_path"] or "")
        for candidate in row["candidate_examples"]
    )
    assert "Supporting-context-only candidates are insufficient" in audit.render_markdown(
        report
    )
