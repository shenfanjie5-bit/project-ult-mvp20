from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts import audit_a_share_approval_materialization_plan as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _insert(conn: sqlite3.Connection, ts_code: str, dp_id: str, value: dict) -> None:
    conn.execute(
        "insert into realtime_current(ts_code, dp_id, value_json) values (?, ?, ?)",
        (ts_code, dp_id, json.dumps(value, ensure_ascii=False)),
    )


def test_materialization_plan_splits_formula_text_and_event_scope(
    tmp_path: Path,
) -> None:
    target_scope_path = tmp_path / "target_scope.json"
    manifest_path = tmp_path / "manifest.json"
    runtime_db_path = tmp_path / "hot.sqlite"
    universe_path = tmp_path / "universe.yaml"

    _write_json(
        target_scope_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "score_target": "fundamental_score",
                    "source_kind": "local_structured_policy_pilot",
                },
                {
                    "dp_id": "L0.demand.user_count",
                    "score_target": "fundamental_score",
                    "source_kind": "local_structured_text_policy_pilot",
                },
                {
                    "dp_id": "L0.compete.price_war",
                    "score_target": "fundamental_score",
                    "source_kind": "event_text_policy_pilot",
                },
                {
                    "dp_id": "L6.mult.dcf",
                    "score_target": "valuation_rerating",
                    "source_kind": "manual_policy_pilot",
                },
            ]
        },
    )
    _write_json(
        manifest_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "source_dependencies": ["L5.is.sga_rd"],
                    "review_payload": {"value_json": {"score": 0.1}},
                },
                {
                    "dp_id": "L0.demand.user_count",
                    "source_dependencies": ["L9.disclosure.qa_recent"],
                    "review_payload": {
                        "value_json": {
                            "score": 0.2,
                            "components": {
                                "qa_user_count_demand_match_count": 2,
                                "evidence_examples": [
                                    {"ts_code": "000001.SZ"},
                                    {"ts_code": "000002.SZ"},
                                ],
                            },
                        }
                    },
                },
                {
                    "dp_id": "L0.compete.price_war",
                    "source_dependencies": ["L9.media.report"],
                    "review_payload": {"value_json": {"score": -0.2}},
                },
                {
                    "dp_id": "L6.mult.dcf",
                    "source_dependencies": ["L5.cf.fcf"],
                    "review_payload": {"value_json": {"score": -0.3}},
                },
            ]
        },
    )
    universe_path.write_text(
        "constituents:\n"
        "  - ts_code: 000001.SZ\n"
        "  - ts_code: 000002.SZ\n"
        "  - ts_code: AAPL.US\n",
        encoding="utf-8",
    )
    conn = sqlite3.connect(runtime_db_path)
    conn.execute(
        "create table realtime_current(ts_code text, dp_id text, value_json text)"
    )
    _insert(
        conn,
        "000001.SZ",
        "L5.is.sga_rd",
        {"sga_rd_ratio_revenue": 0.12},
    )
    _insert(
        conn,
        "000002.SZ",
        "L5.is.sga_rd",
        {"sga_rd_ratio_revenue": 0.24},
    )
    conn.commit()
    conn.close()

    report = audit.build_report(
        target_scope_readiness_path=target_scope_path,
        review_manifest_path=manifest_path,
        runtime_db_path=runtime_db_path,
        universe_path=universe_path,
    )

    summary = report["summary"]
    assert summary["approval_packet_count"] == 4
    assert summary["a_share_universe_count"] == 2
    assert summary["fundamental_packet_count"] == 3
    assert summary["direct_structured_formula_packet_count"] == 1
    assert summary["direct_structured_formula_plan_ready_count"] == 1
    assert summary["text_evidence_full_match_export_required_count"] == 0
    assert summary["text_evidence_subset_plan_ready_count"] == 1
    assert summary["runtime_materialization_plan_ready_count"] == 2
    assert summary["market_or_event_scope_policy_required_count"] == 2
    assert summary["runtime_write_allowed_count"] == 0
    assert summary["production_write_allowed_count"] == 0

    by_dp_id = {row["dp_id"]: row for row in report["rows"]}
    assert (
        by_dp_id["L0.cost.cac"]["materialization_class"]
        == "direct_structured_per_stock_formula"
    )
    assert by_dp_id["L0.cost.cac"]["target_ts_code_count"] == 2
    assert by_dp_id["L0.cost.cac"]["bridge_ready_count"] == 2
    assert (
        by_dp_id["L0.demand.user_count"]["required_next_step"]
        == "approve_text_evidence_subset_materialization_plan"
    )
    assert (
        by_dp_id["L0.demand.user_count"]["materialization_class"]
        == "text_evidence_subset_per_stock"
    )
    assert by_dp_id["L0.demand.user_count"]["evidence_example_ts_code_count"] == 2
    assert (
        by_dp_id["L0.compete.price_war"]["required_next_step"]
        == "approve_market_or_event_target_scope_policy"
    )
    assert (
        by_dp_id["L6.mult.dcf"]["materialization_class"]
        == "market_or_event_scope_policy_required"
    )


def test_grain_join_plan_uses_universe_industry_ids(tmp_path: Path) -> None:
    target_scope_path = tmp_path / "target_scope.json"
    manifest_path = tmp_path / "manifest.json"
    runtime_db_path = tmp_path / "hot.sqlite"
    universe_path = tmp_path / "universe.yaml"

    _write_json(
        target_scope_path,
        {
            "rows": [
                {
                    "dp_id": "L0.price.contract_spot",
                    "score_target": "fundamental_score",
                    "source_kind": "local_structured_policy_pilot",
                }
            ]
        },
    )
    _write_json(
        manifest_path,
        {
            "rows": [
                {
                    "dp_id": "L0.price.contract_spot",
                    "source_dependencies": [
                        "L0.cost.raw_material",
                        "L5.is.gross_margin",
                    ],
                    "review_payload": {
                        "value_json": {
                            "score": 0.1,
                            "components": {
                                "grain_join_policy": {
                                    "join_ready_a_share_count": 1,
                                }
                            },
                        }
                    },
                }
            ]
        },
    )
    universe_path.write_text(
        "constituents:\n"
        "  - ts_code: 000001.SZ\n"
        "    industry_ids: [AI_COMPUTE]\n"
        "  - ts_code: 000002.SZ\n"
        "    industry_ids: [CONSUMER_ELECTRONICS]\n",
        encoding="utf-8",
    )
    conn = sqlite3.connect(runtime_db_path)
    conn.execute(
        "create table realtime_current(ts_code text, dp_id text, value_json text)"
    )
    _insert(
        conn,
        "INDUSTRY:AI_COMPUTE",
        "L0.cost.raw_material",
        {"avg_pct_change": 0.3},
    )
    _insert(conn, "000001.SZ", "L5.is.gross_margin", {"scalar": 0.35})
    _insert(conn, "000002.SZ", "L5.is.gross_margin", {"scalar": 0.35})
    conn.commit()
    conn.close()

    report = audit.build_report(
        target_scope_readiness_path=target_scope_path,
        review_manifest_path=manifest_path,
        runtime_db_path=runtime_db_path,
        universe_path=universe_path,
    )

    summary = report["summary"]
    row = report["rows"][0]
    assert summary["grain_join_plan_ready_count"] == 1
    assert summary["runtime_materialization_plan_ready_count"] == 1
    assert row["materialization_class"] == "structured_formula_grain_join_per_stock"
    assert row["target_ts_code_count"] == 1
    assert row["target_ts_codes_sample"] == ["000001.SZ"]
    assert row["missing_input_reason_counts"] == {"missing_raw_material": 1}
