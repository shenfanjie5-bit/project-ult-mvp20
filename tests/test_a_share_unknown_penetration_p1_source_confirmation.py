import json
from pathlib import Path

from scripts import audit_a_share_unknown_penetration_p1_source_confirmation as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_penetration_p1_source_confirmation_reads_html_scope(tmp_path: Path) -> None:
    market_root = tmp_path / "market"
    html_path = market_root / "news/cls_flash/2026/03/p1.html"
    html_path.parent.mkdir(parents=True)
    html_path.write_text(
        "<html><body>华泰证券指出，电子气体景气有望加速。"
        "2024年我国上市公司电子气体市场份额占国内市场规模40%，"
        "国产化率有望提高。</body></html>",
        encoding="utf-8",
    )
    priority_path = tmp_path / "priority.json"
    _write_json(
        priority_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "value_review_packet_id": "p1",
                    "priority_bucket": "P1_preferred_source_scope_review",
                    "source_quality": "secondary_market_doc",
                    "title": "华泰证券：供需向好下电子气体景气或加速",
                    "market_relative_path": "news/cls_flash/2026/03/p1.html",
                    "excerpt": "2024年我国上市公司电子气体市场份额占国内市场规模40%。",
                    "candidate_values": [{"raw_token": "40%"}],
                }
            ]
        },
    )

    report = audit.build_report(
        priority_path=priority_path,
        market_data_root=market_root,
    )

    assert report["summary"]["p1_candidate_count"] == 1
    assert report["summary"]["source_file_found_count"] == 1
    assert report["summary"]["raw_value_token_confirmed_count"] == 1
    assert report["summary"]["source_scope_confirmed_count"] == 1
    assert report["summary"]["selected_raw_value_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["runtime_write_allowed_count"] == 0
    row = report["rows"][0]
    assert row["source_scope_confirmed"] is True
    assert row["confirmation_checks"]["market_denominator_present"] is True
    assert row["selected_value_json"] is None
    assert "Source scope confirmed: `1`" in audit.render_markdown(report)
