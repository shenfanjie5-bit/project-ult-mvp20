import json
from pathlib import Path

from scripts import audit_a_share_local_formula_source_capability as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _profile(column: str, non_empty: int, empty: int = 0) -> dict:
    return {
        "column": column,
        "non_empty": non_empty,
        "empty": empty,
        "numeric_valid": non_empty,
        "numeric_invalid": 0,
        "parse_ratio": 1 if non_empty else 0,
        "samples": ["1"] if non_empty else [],
    }


def test_local_formula_source_capability_separates_context_from_ready_inputs(
    tmp_path: Path,
) -> None:
    review_packets_path = tmp_path / "review.json"
    semantics_path = tmp_path / "semantics.json"
    file_evidence_path = tmp_path / "files.jsonl"
    tushare_source_path = tmp_path / "tushare_source.py"
    _write_json(
        review_packets_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.rent",
                    "score_target": "fundamental_score",
                    "missing_before_known": ["denominator", "formula_policy"],
                    "candidate_columns": ["use_right_asset_dep"],
                },
                {
                    "dp_id": "L0.price.product_asp",
                    "score_target": "fundamental_score",
                    "missing_before_known": ["quantity_or_price_index", "formula_policy"],
                    "candidate_columns": ["bz_item", "bz_sales"],
                },
            ]
        },
    )
    _write_json(
        semantics_path,
        {
            "signatures": [
                {
                    "signature_rank": 1,
                    "file_count": 3,
                    "columns": ["use_right_asset_dep", "fa_fnc_leases", "n_cashflow_act"],
                    "examples": ["股票数据/财务数据/现金流量表/by_symbol/000001.SZ.csv"],
                    "column_profiles": {
                        "numeric": [
                            _profile("use_right_asset_dep", 2),
                            _profile("n_cashflow_act", 4),
                        ],
                        "sparse": [_profile("fa_fnc_leases", 0, 4)],
                    },
                },
                {
                    "signature_rank": 2,
                    "file_count": 3,
                    "columns": ["bz_item", "bz_sales", "bz_cost", "bz_profit"],
                    "examples": ["股票数据/财务数据/主营业务构成/by_symbol/000001.SZ.csv"],
                    "column_profiles": {
                        "numeric": [
                            _profile("bz_sales", 4),
                            _profile("bz_cost", 4),
                            _profile("bz_profit", 4),
                        ],
                        "categorical_samples": [_profile("bz_item", 4)],
                    },
                },
                {
                    "signature_rank": 3,
                    "file_count": 1,
                    "columns": ["month", "ppi_yoy", "ppi_mp_yoy"],
                    "examples": ["宏观经济/国内宏观/价格指数/工业生产者出厂价格指数（PPI）/all.csv"],
                    "column_profiles": {
                        "numeric": [
                            _profile("ppi_yoy", 4),
                            _profile("ppi_mp_yoy", 4),
                        ]
                    },
                },
                {
                    "signature_rank": 4,
                    "file_count": 1,
                    "columns": ["ts_code", "trade_date", "vol", "amount"],
                    "examples": ["股票数据/行情数据/历史日线/by_symbol/000001.SZ.csv"],
                    "column_profiles": {
                        "numeric": [_profile("vol", 4), _profile("amount", 4)]
                    },
                },
            ]
        },
    )
    _write_jsonl(
        file_evidence_path,
        [
            {"path": "股票数据/财务数据/现金流量表/by_symbol/000001.SZ.csv"},
            {"path": "股票数据/财务数据/主营业务构成/by_symbol/000001.SZ.csv"},
            {"path": "宏观经济/国内宏观/价格指数/工业生产者出厂价格指数（PPI）/all.csv"},
        ],
    )
    tushare_source_path.write_text(
        "pro.cashflow(fields='fa_fnc_leases,use_right_asset_dep,n_cashflow_act')\n"
        "pro.fina_mainbz(fields='bz_item,bz_sales,bz_cost,bz_profit')\n"
        "pro.cn_ppi(fields='month,ppi_yoy,ppi_mp_yoy')\n",
        encoding="utf-8",
    )

    report = audit.build_report(
        review_packets_path=review_packets_path,
        semantics_path=semantics_path,
        file_evidence_path=file_evidence_path,
        tushare_source_path=tushare_source_path,
    )

    assert report["summary"]["local_formula_source_capability_row_count"] == 2
    assert report["summary"]["source_capability_check_count"] == 8
    assert report["summary"]["header_available_but_sample_empty_count"] == 1
    assert report["summary"]["candidate_context_or_proxy_count"] == 3
    assert report["summary"]["external_or_text_required_count"] == 1
    assert report["summary"]["formula_blocker_resolved_by_current_source_count"] == 0
    assert report["summary"]["formula_inputs_ready_after_source_scan_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    rows = {row["dp_id"]: row for row in report["rows"]}
    rent_checks = {
        check["input_name"]: check
        for check in rows["L0.cost.rent"]["source_capability_checks"]
    }
    assert rent_checks["direct_lease_payment"]["source_status"] == (
        "header_available_but_sample_empty"
    )
    assert rent_checks["direct_lease_payment"]["non_empty_profile_hit_count"] == 0
    asp_checks = {
        check["input_name"]: check
        for check in rows["L0.price.product_asp"]["source_capability_checks"]
    }
    assert asp_checks["quantity_or_price_index"]["source_status"] == (
        "external_or_text_required"
    )
    assert asp_checks["quantity_or_price_index"]["trading_volume_false_positive_count"] >= 1
    assert "Formula blockers resolved by current sources: `0`" in audit.render_markdown(report)


def test_current_local_formula_source_capability_report_matches_gate() -> None:
    path = Path("docs/audit/a_share_local_formula_source_capability_2026-06-19.json")
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["local_formula_source_capability_row_count"] == 2
    assert report["summary"]["source_capability_check_count"] == 8
    assert report["summary"]["header_available_but_sample_empty_count"] == 1
    assert report["summary"]["candidate_context_or_proxy_count"] == 3
    assert report["summary"]["review_policy_required_count"] == 3
    assert report["summary"]["external_or_text_required_count"] == 1
    assert report["summary"]["formula_blocker_resolved_by_current_source_count"] == 0
    assert report["summary"]["formula_inputs_ready_after_source_scan_count"] == 0
    assert report["summary"]["formula_probe_available_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
