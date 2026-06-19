import json
from pathlib import Path

from scripts import audit_a_share_local_structured_source_candidates as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _unknown_row(dp_id: str) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "resolution_status": "requires_source",
        "runtime_dependency_ready": True,
    }


def _signature(
    rank: int,
    columns: list[str],
    examples: list[str],
    profiles: list[dict],
    *,
    file_count: int = 3,
    sampled_rows: int = 100,
) -> dict:
    return {
        "signature_rank": rank,
        "file_count": file_count,
        "sampled_rows": sampled_rows,
        "columns": columns,
        "examples": examples,
        "column_profiles": {
            "numeric": [
                profile
                for profile in profiles
                if "numeric_valid" in profile or profile.get("parse_ratio") is not None
            ],
            "categorical_samples": [
                profile
                for profile in profiles
                if "numeric_valid" not in profile and profile.get("parse_ratio") is None
            ],
        },
    }


def _numeric_profile(column: str, non_empty: int, empty: int = 0) -> dict:
    return {
        "column": column,
        "non_empty": non_empty,
        "empty": empty,
        "numeric_valid": non_empty,
        "parse_ratio": 1.0,
        "samples": ["1.0"],
        "min": 1.0,
        "max": 1.0,
    }


def test_local_structured_source_candidates_classifies_review_and_supporting_sources(
    tmp_path: Path,
) -> None:
    unknown_path = tmp_path / "unknown.json"
    dockcase_path = tmp_path / "dockcase.json"
    _write_json(
        unknown_path,
        {
            "rows": [
                _unknown_row("L0.cost.rent"),
                _unknown_row("L0.demand.frequency"),
                _unknown_row("L0.demand.penetration"),
                _unknown_row("L0.price.product_asp"),
            ]
        },
    )
    _write_json(
        dockcase_path,
        {
            "summary": {
                "csv_files_seen": 10,
                "signature_count": 4,
                "sampled_signature_count": 4,
                "sampled_files": 4,
                "sampled_rows": 400,
            },
            "signatures": [
                _signature(
                    1,
                    ["ts_code", "use_right_asset_dep", "fa_fnc_leases"],
                    ["股票数据/财务数据/现金流量表/by_symbol/000002.SZ+万科Ａ.csv"],
                    [
                        _numeric_profile("use_right_asset_dep", 31, 102),
                        _numeric_profile("fa_fnc_leases", 0, 133),
                    ],
                ),
                _signature(
                    2,
                    ["ts_code", "trade_date", "turnover_rate", "volume_ratio", "vol"],
                    ["股票数据/行情数据/每日指标/by_symbol/000001.SZ+平安银行.csv"],
                    [
                        _numeric_profile("turnover_rate", 100),
                        _numeric_profile("volume_ratio", 100),
                        _numeric_profile("vol", 100),
                    ],
                ),
                _signature(
                    3,
                    ["ts_code", "end_date", "bz_item", "bz_sales", "bz_cost", "bz_profit"],
                    ["股票数据/财务数据/主营业务构成/by_symbol/300502.SZ+新易盛.csv"],
                    [
                        {"column": "bz_item", "non_empty": 145, "empty": 0, "samples": ["光模块"]},
                        _numeric_profile("bz_sales", 144, 1),
                        _numeric_profile("bz_cost", 88, 57),
                        _numeric_profile("bz_profit", 87, 58),
                    ],
                ),
                _signature(
                    4,
                    ["timestamp_utc", "total_share", "holder_name", "market_amount"],
                    ["_workspace/_meta/qa/tushare_bulk_download_errors.csv"],
                    [
                        {"column": "timestamp_utc", "non_empty": 1, "empty": 0, "samples": ["now"]},
                        _numeric_profile("total_share", 100),
                    ],
                ),
            ],
        },
    )

    report = audit.build_report(unknown_path, dockcase_path)

    assert report["summary"]["unknown_dp_count"] == 4
    assert report["summary"]["direct_known_ready_count"] == 0
    assert report["summary"]["review_candidate_dp_count"] == 2
    assert report["summary"]["review_candidate_match_count"] == 1
    assert report["summary"]["supporting_candidate_match_count"] == 4
    assert report["summary"]["empty_candidate_match_count"] == 1
    assert report["summary"]["production_write_allowed_count"] == 0

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.cost.rent"]["candidate_status"] == "review_candidate_found"
    assert by_dp["L0.cost.rent"]["review_candidates"][0]["column"] == "use_right_asset_dep"
    assert by_dp["L0.cost.rent"]["empty_candidates"][0]["column"] == "fa_fnc_leases"
    assert by_dp["L0.demand.frequency"]["candidate_status"] == "no_direct_catalog_source"
    assert by_dp["L0.demand.frequency"]["excluded_false_positive_count"] >= 1
    assert by_dp["L0.demand.penetration"]["candidate_status"] == "no_direct_catalog_source"
    assert by_dp["L0.price.product_asp"]["candidate_status"] == "supporting_candidate_found"
    assert {match["column"] for match in by_dp["L0.price.product_asp"]["supporting_candidates"]} == {
        "bz_item",
        "bz_sales",
        "bz_cost",
        "bz_profit",
    }
    assert "Direct Known-ready rows: `0`" in audit.render_markdown(report)


def test_local_structured_source_candidates_keeps_unknown_when_catalog_is_empty(
    tmp_path: Path,
) -> None:
    unknown_path = tmp_path / "unknown.json"
    dockcase_path = tmp_path / "dockcase.json"
    _write_json(unknown_path, {"rows": [_unknown_row("L0.demand.frequency")]})
    _write_json(
        dockcase_path,
        {
            "summary": {},
            "signatures": [
                _signature(
                    1,
                    ["ts_code", "revenue"],
                    ["股票数据/财务数据/利润表/by_symbol/000001.SZ+平安银行.csv"],
                    [_numeric_profile("revenue", 10)],
                )
            ],
        },
    )

    report = audit.build_report(unknown_path, dockcase_path)

    assert report["summary"]["unknown_dp_count"] == 1
    assert report["summary"]["direct_known_ready_count"] == 0
    assert report["summary"]["no_direct_catalog_source_count"] == 1
    assert report["rows"][0]["production_write_allowed"] is False
