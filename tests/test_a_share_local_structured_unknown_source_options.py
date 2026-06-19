import json
from pathlib import Path

from scripts import audit_a_share_local_structured_unknown_source_options as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _draft_row(dp_id: str, blocked_reason: str = "blocked") -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "draft_status": "unknown_policy_required",
        "draft_payload": {
            "data_status": "Unknown",
            "value_json": {
                "blocked_reason": blocked_reason,
                "required_policy": "reviewed policy required",
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


def _candidate(dp_id: str, deps: list[dict], grain: dict | None = None) -> dict:
    candidate_input = {
        "target_dp_id": dp_id,
        "score_target": "fundamental_score",
        "dependencies": deps,
    }
    if grain is not None:
        candidate_input["grain_join_policy"] = grain
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
        "candidate_input": candidate_input,
    }


def test_local_structured_unknown_source_options_classifies_review_gates(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "local.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(
        local_path,
        {
            "rows": [
                _draft_row("L0.cost.rent"),
                _draft_row("L0.demand.frequency"),
                _draft_row("L0.demand.penetration"),
                _draft_row("L0.price.contract_spot"),
                _draft_row("L0.price.product_asp"),
            ]
        },
    )
    _write_json(
        candidate_path,
        {
            "rows": [
                _candidate(
                    "L0.cost.rent",
                    [
                        _dep("L5.bs.goodwill_ppe", 1756, 1756, {"fix_assets_ppe": 1}),
                        _dep("L5.cf.capex", 1755, 1755, {"scalar": 1}),
                    ],
                ),
                _candidate(
                    "L0.demand.frequency",
                    [
                        _dep("L5.is.revenue", 1755, 1755, {"scalar": 1}),
                        _dep("L5.is.revenue_growth", 1722, 1722, {"yoy_pct": 1}),
                    ],
                ),
                _candidate(
                    "L0.demand.penetration",
                    [
                        _dep("L5.is.revenue", 1755, 1755, {"scalar": 1}),
                        _dep("L5.is.revenue_growth", 1722, 1722, {"yoy_pct": 1}),
                    ],
                ),
                _candidate(
                    "L0.price.contract_spot",
                    [
                        _dep("L0.cost.raw_material", 7, 7, {"avg_pct_change": 0.1}),
                        _dep("L5.is.gross_margin", 1660, 1660, {"scalar": 0.2}),
                    ],
                    grain={
                        "universe_path": "config/mvp20.universe.yaml",
                        "a_share_universe_count": 1641,
                        "raw_material_industry_count": 7,
                        "known_gross_margin_a_share_count": 1546,
                        "join_ready_a_share_count": 1007,
                        "missing_raw_material_a_share_count": 539,
                        "missing_gross_margin_a_share_count": 95,
                    },
                ),
                _candidate(
                    "L0.price.product_asp",
                    [
                        _dep("L5.is.revenue", 1755, 1755, {"scalar": 1}),
                        _dep("L5.is.gross_margin", 1660, 1660, {"scalar": 0.2}),
                    ],
                ),
            ]
        },
    )

    report = audit.build_report(local_path, candidate_path)

    assert report["summary"]["unknown_local_structured_count"] == 5
    assert report["summary"]["existing_runtime_dependency_ready_count"] == 5
    assert report["summary"]["direct_existing_structured_source_ready_count"] == 0
    assert report["summary"]["overlay_candidate_hint_count"] == 5
    assert report["summary"]["candidate_requires_new_mapping_count"] == 4
    assert report["summary"]["candidate_requires_review_policy_count"] == 1
    assert report["summary"]["partial_known_unlock_candidate_count"] == 1
    assert report["summary"]["auto_known_candidate_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.cost.rent"]["runtime_dependency_summary"][0]["source_counts"] == {
        "tushare:test": 1756
    }
    assert by_dp["L0.price.contract_spot"]["partial_known_unlock_candidate"] is True
    assert by_dp["L0.price.contract_spot"]["grain_join_policy"][
        "join_ready_a_share_count"
    ] == 1007
    assert by_dp["L0.price.product_asp"]["auto_known_candidate_allowed"] is False
    assert "Direct structured source-ready rows: `0`" in audit.render_markdown(report)


def test_local_structured_unknown_source_options_keeps_missing_evidence_review_gated(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "local.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(local_path, {"rows": [_draft_row("L0.cost.rent")]})
    _write_json(candidate_path, {"rows": []})

    report = audit.build_report(local_path, candidate_path)

    assert report["summary"]["unknown_local_structured_count"] == 1
    assert report["summary"]["existing_runtime_dependency_ready_count"] == 0
    row = report["rows"][0]
    assert row["runtime_dependency_ready"] is False
    assert row["review_required"] is True
    assert row["production_write_allowed"] is False
