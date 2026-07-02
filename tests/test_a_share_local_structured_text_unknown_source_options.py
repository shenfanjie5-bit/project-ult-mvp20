import json
from pathlib import Path

from scripts import audit_a_share_local_structured_text_unknown_source_options as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _draft_row(dp_id: str, blocked_reason: str = "blocked") -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "draft_status": "unknown_text_classification_required",
        "draft_payload": {
            "data_status": "Unknown",
            "value_json": {
                "blocked_reason": blocked_reason,
                "required_policy": "text classification required",
            },
        },
    }


def _dep(dp_id: str, row_count: int, known_count: int, keys: dict) -> dict:
    return {
        "dp_id": dp_id,
        "row_count": row_count,
        "known_count": known_count,
        "ts_code_count": row_count,
        "namespace_counts": {"stock": row_count},
        "latest_updated_at_iso": "2026-06-11T07:49:14+00:00",
        "sample_rows": [
            {
                "ts_code": "000001.SZ",
                "data_status": "Known",
                "source": "test",
                "value_json_compact": keys,
            }
        ],
    }


def _candidate(dp_id: str, deps: list[dict]) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "candidate_status": "ready_for_local_llm_candidate",
        "source_dependencies": [dep["dp_id"] for dep in deps],
        "dependency_evidence": {
            dep["dp_id"]: {
                "row_count": dep["row_count"],
                "known_count": dep["known_count"],
                "source_counts": {"tushare:test": dep["row_count"]},
                "namespace_counts": dep["namespace_counts"],
            }
            for dep in deps
        },
        "candidate_input": {
            "target_dp_id": dp_id,
            "score_target": "fundamental_score",
            "dependencies": deps,
        },
    }


def _qa_dep() -> dict:
    return _dep(
        "L9.disclosure.qa_recent",
        119,
        118,
        {
            "count_recent": 10,
            "top_qa": [
                {
                    "question": "请问股东户数是多少？",
                    "answer": "截至报告期末，公司普通股股东总数为若干户。",
                    "date": "20260529",
                }
            ],
            "latest_date": "20260529",
        },
    )


def test_local_structured_text_unknown_source_options_classifies_text_gates(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "text.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(
        local_path,
        {
            "rows": [
                _draft_row("L0.demand.user_count"),
                _draft_row("L0.price.discount"),
                _draft_row("L0.supply.channel_service"),
            ]
        },
    )
    _write_json(
        candidate_path,
        {
            "rows": [
                _candidate(
                    "L0.demand.user_count",
                    [
                        _dep("L5.is.revenue", 1755, 1755, {"scalar": 100.0}),
                        _qa_dep(),
                    ],
                ),
                _candidate(
                    "L0.price.discount",
                    [
                        _dep("L5.is.gross_margin", 1660, 1660, {"scalar": 0.2}),
                        _qa_dep(),
                    ],
                ),
                _candidate(
                    "L0.supply.channel_service",
                    [
                        _dep(
                            "L5.is.sga_rd",
                            1755,
                            1755,
                            {"sga_rd_ratio_revenue": 0.12},
                        ),
                        _qa_dep(),
                    ],
                ),
            ]
        },
    )

    report = audit.build_report(local_path, candidate_path)

    assert report["summary"]["unknown_local_structured_text_count"] == 3
    assert report["summary"]["existing_runtime_dependency_ready_count"] == 3
    assert report["summary"]["qa_recent_dependency_ready_count"] == 3
    assert report["summary"]["direct_text_classification_ready_count"] == 0
    assert report["summary"]["overlay_candidate_hint_count"] == 3
    assert report["summary"]["candidate_requires_text_classification_count"] == 3
    assert report["summary"]["auto_known_candidate_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.demand.user_count"]["qa_recent_dependency_ready"] is True
    assert by_dp["L0.demand.user_count"]["direct_text_classification_ready"] is False
    assert by_dp["L0.price.discount"]["resolution_status"] == (
        "requires_discount_pricing_text_classification"
    )
    assert by_dp["L0.supply.channel_service"]["runtime_dependency_summary"][1][
        "qa_item_count"
    ] == 1
    assert "Direct text classification-ready rows: `0`" in audit.render_markdown(report)


def test_local_structured_text_unknown_source_options_keeps_missing_candidate_review_gated(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "text.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(local_path, {"rows": [_draft_row("L0.price.discount")]})
    _write_json(candidate_path, {"rows": []})

    report = audit.build_report(local_path, candidate_path)

    assert report["summary"]["unknown_local_structured_text_count"] == 1
    assert report["summary"]["existing_runtime_dependency_ready_count"] == 0
    row = report["rows"][0]
    assert row["runtime_dependency_ready"] is False
    assert row["review_required"] is True
    assert row["production_write_allowed"] is False


def test_current_goal_coverage_includes_local_structured_text_unknown_source_options() -> None:
    source_path = Path(
        "docs/audit/a_share_local_structured_text_unknown_source_options_2026-06-19.json"
    )
    goal_path = Path("docs/audit/goal_coverage_2026-06-19.json")

    source_summary = json.loads(source_path.read_text(encoding="utf-8"))["summary"]
    goal_report = json.loads(goal_path.read_text(encoding="utf-8"))
    a_share_row = next(
        row
        for row in goal_report["requirements"]
        if row["requirement_id"] == "a_share_score_field_path"
    )

    assert (
        a_share_row["evidence"]["local_structured_text_unknown_source_options_summary"]
        == source_summary
    )
    assert (
        "local_structured_text_unknown_source_options"
        in a_share_row["evidence_strength"]
    )
    assert (
        "Local structured-text Unknown source-options audit reviews 0 Unknown rows"
        in a_share_row["remaining_gap"]
    )
    assert any(
        "0 local-structured-text text classifications required" in blocker
        for blocker in goal_report["summary"]["completion_blockers"]
    )
