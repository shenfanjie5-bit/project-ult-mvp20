import json
from pathlib import Path

from scripts import audit_a_share_local_structured_source_review_packets as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _source_row(
    dp_id: str,
    candidate_status: str,
    review_candidates: list[dict] | None = None,
    supporting_candidates: list[dict] | None = None,
    empty_candidates: list[dict] | None = None,
) -> dict:
    review_candidates = review_candidates or []
    supporting_candidates = supporting_candidates or []
    empty_candidates = empty_candidates or []
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "candidate_status": candidate_status,
        "direct_known_ready": False,
        "direct_known_blocker": "not direct",
        "review_candidate_count": len(review_candidates),
        "supporting_candidate_count": len(supporting_candidates),
        "empty_candidate_count": len(empty_candidates),
        "excluded_false_positive_count": 3,
        "review_candidates": review_candidates,
        "supporting_candidates": supporting_candidates,
        "empty_candidates": empty_candidates,
        "next_tushare_action": "next",
        "llm_or_web_fallback": "fallback",
    }


def _match(column: str) -> dict:
    return {
        "column": column,
        "signature_rank": 1,
        "file_count": 10,
        "sampled_rows": 20,
        "profile": {"column": column, "non_empty": 5},
        "examples": ["股票数据/财务数据/现金流量表/by_symbol/000001.SZ+平安银行.csv"],
    }


def test_local_structured_source_review_packets_package_candidate_states(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.json"
    unknown_path = tmp_path / "unknown.json"
    _write_json(
        source_path,
        {
            "rows": [
                _source_row(
                    "L0.cost.rent",
                    "review_candidate_found",
                    review_candidates=[_match("use_right_asset_dep")],
                    empty_candidates=[_match("fa_fnc_leases")],
                ),
                _source_row("L0.demand.frequency", "no_direct_catalog_source"),
                _source_row("L0.demand.penetration", "no_direct_catalog_source"),
                _source_row(
                    "L0.price.product_asp",
                    "supporting_candidate_found",
                    supporting_candidates=[
                        _match("bz_item"),
                        _match("bz_sales"),
                        _match("bz_cost"),
                        _match("bz_profit"),
                    ],
                ),
            ]
        },
    )
    _write_json(
        unknown_path,
        {
            "rows": [
                {"dp_id": "L0.cost.rent", "score_target": "fundamental_score"},
                {"dp_id": "L0.demand.frequency", "score_target": "fundamental_score"},
                {"dp_id": "L0.demand.penetration", "score_target": "fundamental_score"},
                {"dp_id": "L0.price.product_asp", "score_target": "fundamental_score"},
            ]
        },
    )

    report = audit.build_report(
        source_candidates_path=source_path,
        unknown_options_path=unknown_path,
    )

    assert report["summary"]["local_structured_source_review_packet_count"] == 4
    assert report["summary"]["review_candidate_ready_count"] == 1
    assert report["summary"]["supporting_candidate_needs_quantity_source_count"] == 1
    assert report["summary"]["external_source_required_count"] == 2
    assert report["summary"]["direct_known_ready_count"] == 0
    assert report["summary"]["formula_inputs_ready_count"] == 0
    assert report["summary"]["candidate_packet_count"] == 2
    assert report["summary"]["candidate_column_count"] == 5
    assert report["summary"]["empty_candidate_column_count"] == 1
    assert report["summary"]["packet_contract_valid_count"] == 4
    assert report["summary"]["production_write_allowed_count"] == 0

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.cost.rent"]["source_review_packet_status"] == "review_candidate_ready"
    assert by_dp["L0.cost.rent"]["candidate_columns"] == ["use_right_asset_dep"]
    assert by_dp["L0.cost.rent"]["empty_candidate_columns"] == ["fa_fnc_leases"]
    assert by_dp["L0.cost.rent"]["data_status"] == "Unknown"
    assert by_dp["L0.cost.rent"]["formula_inputs_ready"] is False
    assert by_dp["L0.price.product_asp"]["source_review_packet_status"] == (
        "supporting_candidate_needs_quantity_source"
    )
    assert "bz_sales" in by_dp["L0.price.product_asp"]["candidate_columns"]
    assert by_dp["L0.demand.frequency"]["source_review_packet_status"] == (
        "external_source_required"
    )
    assert by_dp["L0.demand.penetration"]["candidate_columns"] == []
    assert "Source-review packets: `4`" in audit.render_markdown(report)


def test_local_structured_source_review_packets_rejects_writable_packet() -> None:
    packet = {
        "dp_id": "L0.cost.rent",
        "score_target": "fundamental_score",
        "data_status": "Known",
        "review_status": "review_required",
        "direct_known_ready": False,
        "formula_inputs_ready": False,
        "safe_to_upsert_without_review": False,
        "production_write_allowed": True,
        "source_review_packet_status": "review_candidate_ready",
        "candidate_columns": ["use_right_asset_dep"],
        "source_examples": ["x.csv"],
    }

    errors = audit._validation_errors(packet)

    assert "data_status must stay Unknown" in errors
    assert "production_write_allowed must be false" in errors
