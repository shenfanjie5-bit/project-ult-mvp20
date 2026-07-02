import json
from pathlib import Path

from scripts import audit_a_share_local_structured_policy_drafts as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _readiness_row(dp_id: str) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "route_bucket": "local_structured_llm_required",
        "dependency_readiness": "all_dependencies_have_material_known_coverage",
    }


def _sample(ts_code: str, value: dict) -> dict:
    return {
        "ts_code": ts_code,
        "data_status": "Known",
        "confidence": 0.8,
        "source": "test",
        "value_json_compact": value,
    }


def _dep(dp_id: str, values: list[dict]) -> dict:
    return {
        "dp_id": dp_id,
        "row_count": len(values),
        "known_count": len(values),
        "sample_rows": [_sample(f"00000{idx}.SZ", value) for idx, value in enumerate(values, start=1)],
    }


def _candidate(dp_id: str, deps: list[dict]) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "source_dependencies": [dep["dp_id"] for dep in deps],
        "candidate_input": {
            "target_dp_id": dp_id,
            "score_target": "fundamental_score",
            "dependencies": deps,
        },
    }


def _fixture_candidate_rows() -> list[dict]:
    revenue_growth = _dep("L5.is.revenue_growth", [{"yoy_pct": 20.0}, {"yoy_pct": 10.0}])
    revenue = _dep("L5.is.revenue", [{"scalar": 1000.0}, {"scalar": 1200.0}])
    sga_rd = _dep(
        "L5.is.sga_rd",
        [{"sga_rd_ratio_revenue": 0.12}, {"sga_rd_ratio_revenue": 0.16}],
    )
    labor = _dep(
        "L4.cost.labor",
        [
            {"labor_cost_pct": 16.0, "labor_cost_yoy_pct": -2.0},
            {"labor_cost_pct": 18.0, "labor_cost_yoy_pct": 1.0},
        ],
    )
    capex = _dep("L5.cf.capex", [{"scalar": 50.0}, {"scalar": 60.0}])
    ppe = _dep(
        "L5.bs.goodwill_ppe",
        [{"fix_assets_ppe": 1000.0}, {"fix_assets_ppe": 1200.0}],
    )
    cycle = _dep("L4.eff.cycle", [{"ccc_days": 45.0}, {"ccc_days": 75.0}])
    turnover = _dep("L4.eff.turnover", [{"inventory_turnover_days": 80.0}])
    gross_margin = _dep("L5.is.gross_margin", [{"scalar": 0.24}])
    raw_material = _dep("L0.cost.raw_material", [{"score": -0.1}])
    return [
        _candidate("L0.cost.cac", [sga_rd, revenue]),
        _candidate("L0.cost.labor", [sga_rd, labor]),
        _candidate("L0.cost.rent", [ppe, capex]),
        _candidate("L0.demand.frequency", [revenue, revenue_growth]),
        _candidate("L0.demand.penetration", [revenue, revenue_growth]),
        _candidate("L0.demand.terminal", [revenue, revenue_growth]),
        _candidate("L0.price.contract_spot", [raw_material, gross_margin]),
        _candidate("L0.price.product_asp", [revenue, gross_margin]),
        _candidate("L0.supply.capacity", [capex, ppe]),
        _candidate("L0.supply.chain_eff", [turnover, cycle]),
    ]


def test_local_structured_policy_drafts_builds_review_packets(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    dp_ids = [
        "L0.cost.cac",
        "L0.cost.labor",
        "L0.cost.rent",
        "L0.demand.frequency",
        "L0.demand.penetration",
        "L0.demand.terminal",
        "L0.price.contract_spot",
        "L0.price.product_asp",
        "L0.supply.capacity",
        "L0.supply.chain_eff",
    ]
    _write_json(readiness_path, {"rows": [_readiness_row(dp_id) for dp_id in dp_ids]})
    _write_json(candidate_path, {"rows": _fixture_candidate_rows()})

    report = audit.build_report(readiness_path, candidate_path)

    assert report["summary"]["local_structured_task_count"] == 10
    assert report["summary"]["draft_known_count"] == 6
    assert report["summary"]["draft_unknown_count"] == 4
    assert report["summary"]["draft_contract_valid_count"] == 10
    assert report["summary"]["draft_contract_invalid_count"] == 0
    assert report["summary"]["bridge_validated_known_count"] == 6
    assert report["summary"]["safe_to_upsert_without_review_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.cost.cac"]["draft_payload"]["data_status"] == "Known"
    assert by_dp["L0.cost.labor"]["draft_payload"]["data_status"] == "Known"
    assert by_dp["L0.demand.terminal"]["draft_payload"]["data_status"] == "Known"
    assert by_dp["L0.price.contract_spot"]["draft_payload"]["data_status"] == "Known"
    assert by_dp["L0.price.contract_spot"]["draft_status"] == (
        "draft_known_pass_through_review_required"
    )
    assert by_dp["L0.price.contract_spot"]["bridge_validation"][
        "final_score_target_ready"
    ]
    assert by_dp["L0.price.contract_spot"]["draft_payload"][
        "safe_to_upsert_without_review"
    ] is False
    assert by_dp["L0.supply.capacity"]["draft_payload"]["data_status"] == "Known"
    assert by_dp["L0.supply.chain_eff"]["draft_payload"]["data_status"] == "Known"
    assert by_dp["L0.price.product_asp"]["draft_payload"]["data_status"] == "Unknown"
    assert (
        by_dp["L0.price.product_asp"]["draft_payload"]["value_json"]["blocked_reason"]
        == "revenue_and_margin_cannot_identify_unit_asp_without_volume_mix"
    )
    assert "Draft Known review packets: `6`" in audit.render_markdown(report)


def test_local_structured_policy_drafts_marks_missing_candidate_unknown(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(readiness_path, {"rows": [_readiness_row("L0.cost.cac")]})
    _write_json(candidate_path, {"rows": []})

    report = audit.build_report(readiness_path, candidate_path)

    assert report["summary"]["draft_known_count"] == 0
    assert report["summary"]["draft_unknown_count"] == 1
    row = report["rows"][0]
    assert row["draft_status"] == "unknown_missing_candidate_evidence"
    assert row["contract_validation"]["contract_valid"]
