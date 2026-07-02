import csv
import json
from pathlib import Path

from scripts import audit_a_share_unknown_local_formula_acquisition_candidates as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _task(dp_id: str) -> dict:
    return {
        "task_id": f"task-{dp_id}",
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "acquisition_track": "local_structured_formula_source",
        "source_priority": "source",
    }


def test_unknown_local_formula_acquisition_candidates_classify_inputs(
    tmp_path: Path,
) -> None:
    backlog_path = tmp_path / "backlog.json"
    source_review_path = tmp_path / "source_review.json"
    unknown_options_path = tmp_path / "unknown_options.json"
    data_root = tmp_path / "database_all"
    rent_rel = "股票数据/财务数据/现金流量表/by_symbol/000001.SZ+测试.csv"
    asp_rel = "股票数据/财务数据/主营业务构成/by_symbol/000002.SZ+测试.csv"
    _write_csv(
        data_root / rent_rel,
        [
            {
                "ts_code": "000001.SZ",
                "use_right_asset_dep": "100",
                "fa_fnc_leases": "",
            }
        ],
    )
    _write_csv(
        data_root / asp_rel,
        [
            {
                "ts_code": "000002.SZ",
                "bz_item": "核心产品",
                "bz_sales": "200",
                "bz_profit": "50",
                "bz_cost": "150",
            },
            {
                "ts_code": "000002.SZ",
                "bz_item": "国外",
                "bz_sales": "80",
                "bz_profit": "20",
                "bz_cost": "60",
            },
        ],
    )
    _write_json(
        backlog_path,
        {"rows": [_task("L0.cost.rent"), _task("L0.price.product_asp")]},
    )
    _write_json(
        source_review_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.rent",
                    "source_review_packet_status": "review_candidate_ready",
                    "candidate_columns": ["use_right_asset_dep"],
                    "empty_candidate_columns": ["fa_fnc_leases"],
                    "missing_formula_inputs": ["denominator", "policy"],
                    "source_examples": [rent_rel],
                },
                {
                    "dp_id": "L0.price.product_asp",
                    "source_review_packet_status": (
                        "supporting_candidate_needs_quantity_source"
                    ),
                    "candidate_columns": [
                        "bz_item",
                        "bz_sales",
                        "bz_profit",
                        "bz_cost",
                    ],
                    "empty_candidate_columns": [],
                    "missing_formula_inputs": ["quantity"],
                    "source_examples": [asp_rel],
                },
            ]
        },
    )
    _write_json(
        unknown_options_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.rent",
                    "runtime_dependency_ready": True,
                    "runtime_dependency_summary": [{"dp_id": "L5.cf.capex"}],
                },
                {
                    "dp_id": "L0.price.product_asp",
                    "runtime_dependency_ready": True,
                    "runtime_dependency_summary": [{"dp_id": "L5.is.revenue"}],
                },
            ]
        },
    )

    report = audit.build_report(
        backlog_path=backlog_path,
        source_review_path=source_review_path,
        unknown_options_path=unknown_options_path,
        data_root=data_root,
    )

    assert report["summary"]["local_formula_acquisition_task_count"] == 2
    assert report["summary"]["runtime_dependency_ready_count"] == 2
    assert report["summary"]["sample_csv_files_checked"] == 2
    assert report["summary"]["sample_csv_files_existing"] == 2
    assert report["summary"]["formula_input_group_count"] == 8
    assert report["summary"]["formula_input_group_ready_count"] == 0
    assert report["summary"]["rows_with_candidate_numerator_count"] == 2
    assert report["summary"]["rows_with_direct_denominator_count"] == 0
    assert report["summary"]["rows_with_quantity_or_price_index_count"] == 0
    assert report["summary"]["formula_inputs_ready_count"] == 0
    assert report["summary"]["ready_for_known_draft_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["packet_contract_valid_count"] == 2

    rows = {row["dp_id"]: row for row in report["rows"]}
    assert rows["L0.cost.rent"]["formula_candidate_status"] == (
        "proxy_available_denominator_policy_missing"
    )
    assert rows["L0.cost.rent"]["csv_sample_evidence"]["column_non_empty"][
        "use_right_asset_dep"
    ] == 1
    assert rows["L0.price.product_asp"]["formula_candidate_status"] == (
        "revenue_mix_available_quantity_missing"
    )
    assert rows["L0.price.product_asp"]["csv_sample_evidence"][
        "bz_item_geography_like_count"
    ] == 1
    assert "Local formula acquisition tasks: `2`" in audit.render_markdown(report)


def test_current_unknown_local_formula_acquisition_report_matches_gate() -> None:
    path = Path(
        "docs/audit/a_share_unknown_local_formula_acquisition_candidates_2026-06-19.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["local_formula_acquisition_task_count"] == 2
    assert report["summary"]["runtime_dependency_ready_count"] == 2
    assert report["summary"]["formula_inputs_ready_count"] == 0
    assert report["summary"]["ready_for_known_draft_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
