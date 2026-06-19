import json
from pathlib import Path

from scripts import audit_a_share_unknown_penetration_value_priority as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _packet(
    packet_id: str,
    verdict: str,
    path: str,
    token: str = "40%",
) -> dict:
    return {
        "value_review_packet_id": packet_id,
        "dp_id": "L0.demand.penetration",
        "score_target": "fundamental_score",
        "source_scope_verdict": verdict,
        "title": f"title {packet_id}",
        "market_relative_path": path,
        "excerpt": "unit excerpt",
        "candidate_value_options": [
            {
                "option_id": f"{packet_id}:1",
                "raw_token": token,
                "raw_percent": float(token.rstrip("%")),
                "formula_probe_score": float(token.rstrip("%")) / 100.0,
                "bridge_validation": {"final_score_target_ready": True},
                "option_contract_valid": True,
            }
        ],
    }


def test_penetration_value_priority_ranks_review_sources(tmp_path: Path) -> None:
    value_review_path = tmp_path / "value_review.json"
    _write_json(
        value_review_path,
        {
            "rows": [
                _packet(
                    "preferred",
                    "review_a_share_or_domestic_scope",
                    "news/cls_flash/2026/03/preferred.html",
                ),
                _packet(
                    "community",
                    "review_a_share_or_domestic_scope",
                    "news/eastmoney_guba/2026/02/community.html",
                ),
                _packet(
                    "industry",
                    "review_domestic_or_industry_scope",
                    "news/cls_flash/2026/02/industry.html",
                ),
                _packet(
                    "forecast",
                    "review_forecast_or_assumption_scope",
                    "news/ths_news/2026/02/forecast.html",
                ),
            ]
        },
    )

    report = audit.build_report(value_review_path=value_review_path)

    assert report["summary"]["penetration_value_review_packet_count"] == 4
    assert report["summary"]["candidate_value_option_count"] == 4
    assert report["summary"]["bridge_probe_ready_option_count"] == 4
    assert report["summary"]["preferred_source_scope_review_count"] == 1
    assert report["summary"]["industry_scope_review_count"] == 1
    assert report["summary"]["forecast_or_assumption_review_count"] == 1
    assert report["summary"]["low_confidence_community_review_count"] == 1
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["runtime_write_allowed_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["rows"][0]["priority_bucket"] == "P1_preferred_source_scope_review"
    assert "Value-review packets: `4`" in audit.render_markdown(report)
