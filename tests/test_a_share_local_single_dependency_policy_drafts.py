import json
from pathlib import Path

from scripts import audit_a_share_local_single_dependency_policy_drafts as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _readiness_row(dp_id: str) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "route_bucket": "local_single_dependency_policy_required",
        "dependency_readiness": "all_dependencies_have_material_known_coverage",
    }


def _dep(dp_id: str, value: dict) -> dict:
    return {
        "dp_id": dp_id,
        "row_count": 10,
        "known_count": 10,
        "sample_rows": [
            {
                "ts_code": "000001.SZ",
                "data_status": "Known",
                "value_json_compact": value,
            }
        ],
    }


def _candidate(dp_id: str, dep: dict) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "source_dependencies": [dep["dp_id"]],
        "candidate_input": {
            "target_dp_id": dp_id,
            "score_target": "fundamental_score",
            "dependencies": [dep],
        },
    }


def test_local_single_dependency_policy_drafts_builds_bounded_review_packets(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(
        readiness_path,
        {
            "rows": [
                _readiness_row("L0.price.pricing_power"),
                _readiness_row("L0.supply.inventory"),
                _readiness_row("L0.demand.replacement"),
            ]
        },
    )
    _write_json(
        candidate_path,
        {
            "rows": [
                _candidate(
                    "L0.price.pricing_power",
                    _dep("L5.is.gross_margin", {"scalar": 0.32}),
                ),
                _candidate(
                    "L0.supply.inventory",
                    _dep("L5.bs.inventory", {"inventory_to_assets": 0.10}),
                ),
                _candidate(
                    "L0.demand.replacement",
                    _dep("L5.is.revenue", {"scalar": 1000.0}),
                ),
            ]
        },
    )

    report = audit.build_report(readiness_path, candidate_path)

    assert report["summary"]["single_dependency_task_count"] == 3
    assert report["summary"]["draft_known_count"] == 2
    assert report["summary"]["draft_unknown_count"] == 1
    assert report["summary"]["draft_contract_valid_count"] == 3
    assert report["summary"]["draft_contract_invalid_count"] == 0
    assert report["summary"]["bridge_validated_known_count"] == 2
    assert report["summary"]["safe_to_upsert_without_review_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    pricing = by_dp["L0.price.pricing_power"]["draft_payload"]
    assert pricing["data_status"] == "Known"
    assert 0.0 < pricing["value_json"]["score"] <= 1.0
    assert by_dp["L0.price.pricing_power"]["bridge_validation"]["final_score_target_ready"]

    inventory = by_dp["L0.supply.inventory"]["draft_payload"]
    assert inventory["data_status"] == "Known"
    assert 0.0 < inventory["value_json"]["score"] <= 1.0
    assert by_dp["L0.supply.inventory"]["contract_validation"]["contract_valid"]

    replacement = by_dp["L0.demand.replacement"]["draft_payload"]
    assert replacement["data_status"] == "Unknown"
    assert (
        replacement["value_json"]["blocked_reason"]
        == "revenue_only_cannot_identify_replacement_cycle"
    )
    assert "Draft Known review packets: `2`" in audit.render_markdown(report)


def test_local_single_dependency_policy_drafts_marks_missing_candidate_unknown(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    candidate_path = tmp_path / "candidate.json"
    _write_json(readiness_path, {"rows": [_readiness_row("L0.price.pricing_power")]})
    _write_json(candidate_path, {"rows": []})

    report = audit.build_report(readiness_path, candidate_path)

    assert report["summary"]["draft_known_count"] == 0
    assert report["summary"]["draft_unknown_count"] == 1
    row = report["rows"][0]
    assert row["draft_status"] == "unknown_missing_candidate_evidence"
    assert row["contract_validation"]["contract_valid"]
