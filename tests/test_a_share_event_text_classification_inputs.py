import json
from pathlib import Path

from scripts import audit_a_share_event_text_classification_inputs as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _draft_row(dp_id: str, score_target: str = "fundamental_score") -> dict:
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "draft_status": "unknown_event_text_classification_required",
    }


def _dep(dp_id: str, headlines: list[str], *, full_text: bool = False) -> dict:
    value = {
        "count_24h": len(headlines),
        "event_active": bool(headlines),
        "top_headlines": [
            {"title": title, "time": "2026-06-19T01:00:00", "url": f"https://example.test/{idx}"}
            for idx, title in enumerate(headlines)
        ],
    }
    if full_text:
        value["body"] = "full article text"
    return {
        "dp_id": dp_id,
        "row_count": 1,
        "known_count": 1,
        "ts_code_count": 1,
        "namespace_counts": {"market": 1},
        "latest_updated_at_iso": "2026-06-19T00:00:00+00:00",
        "sample_rows": [
            {
                "ts_code": "MARKET:CN",
                "data_status": "Known",
                "source": "unit",
                "value_json_compact": value,
            }
        ],
    }


def _candidate(dp_id: str, deps: list[dict]) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "candidate_input": {
            "target_dp_id": dp_id,
            "score_target": "fundamental_score",
            "dependencies": deps,
        },
    }


def test_event_text_classification_inputs_package_title_level_evidence(tmp_path: Path) -> None:
    event_drafts_path = tmp_path / "event_drafts.json"
    candidate_path = tmp_path / "candidate.json"
    readiness_path = tmp_path / "readiness.json"
    _write_json(
        event_drafts_path,
        {"rows": [_draft_row("L0.compete.price_war"), _draft_row("L0.policy.regulation")]},
    )
    _write_json(
        candidate_path,
        {
            "rows": [
                _candidate(
                    "L0.compete.price_war",
                    [
                        _dep("L9.industry.compete_risk", ["competition headline"]),
                        _dep("L9.media.report", ["market headline"]),
                    ],
                ),
                _candidate(
                    "L0.policy.regulation",
                    [_dep("L9.industry.policy_change", ["policy headline"], full_text=True)],
                ),
            ]
        },
    )
    _write_json(
        readiness_path,
        {
            "rows": [
                {
                    "dp_id": "L0.compete.price_war",
                    "route_bucket": "event_text_classification_required",
                    "dependency_readiness": "all_dependencies_have_material_known_coverage",
                },
                {
                    "dp_id": "L0.policy.regulation",
                    "route_bucket": "event_text_classification_required",
                    "dependency_readiness": "all_dependencies_have_material_known_coverage",
                },
            ]
        },
    )

    report = audit.build_report(
        event_drafts_path=event_drafts_path,
        candidate_path=candidate_path,
        readiness_path=readiness_path,
    )

    assert report["summary"]["classification_input_packet_count"] == 2
    assert report["summary"]["classification_input_ready_count"] == 2
    assert report["summary"]["missing_headline_input_count"] == 0
    assert report["summary"]["headline_input_count"] == 3
    assert report["summary"]["unique_headline_count"] == 3
    assert report["summary"]["full_article_text_available_count"] == 1
    assert report["summary"]["title_level_only_count"] == 1
    assert report["summary"]["classified_known_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    rows = {row["dp_id"]: row for row in report["rows"]}
    assert rows["L0.compete.price_war"]["required_policy"].startswith("needs direct evidence")
    assert rows["L0.compete.price_war"]["classification_schema"]["write_policy"][
        "safe_to_upsert_without_review"
    ] is False
    assert rows["L0.policy.regulation"]["full_article_text_available"] is True
    assert "Classification input packets: `2`" in audit.render_markdown(report)


def test_event_text_classification_inputs_flags_missing_headlines(tmp_path: Path) -> None:
    event_drafts_path = tmp_path / "event_drafts.json"
    candidate_path = tmp_path / "candidate.json"
    readiness_path = tmp_path / "readiness.json"
    _write_json(event_drafts_path, {"rows": [_draft_row("L0.compete.price_war")]})
    _write_json(
        candidate_path,
        {"rows": [_candidate("L0.compete.price_war", [_dep("L9.media.report", [])])]},
    )
    _write_json(readiness_path, {"rows": []})

    report = audit.build_report(
        event_drafts_path=event_drafts_path,
        candidate_path=candidate_path,
        readiness_path=readiness_path,
    )

    assert report["summary"]["classification_input_ready_count"] == 0
    assert report["summary"]["missing_headline_input_count"] == 1
    assert report["rows"][0]["classification_status"] == "missing_headline_input"
