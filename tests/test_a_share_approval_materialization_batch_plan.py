from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts import audit_a_share_approval_materialization_batch_plan as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _insert(conn: sqlite3.Connection, ts_code: str, dp_id: str, value: dict) -> None:
    conn.execute(
        """
        insert into realtime_current(
            ts_code, dp_id, value_json, data_status, confidence, source, updated_at
        )
        values (?, ?, ?, 'Known', 0.9, 'test-source', 1)
        """,
        (ts_code, dp_id, json.dumps(value, ensure_ascii=False)),
    )


def test_formula_materialization_batch_plan_is_review_required(tmp_path: Path) -> None:
    materialization_path = tmp_path / "materialization.json"
    manifest_path = tmp_path / "manifest.json"
    runtime_db_path = tmp_path / "hot.sqlite"
    universe_path = tmp_path / "universe.yaml"

    _write_json(
        materialization_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "score_target": "fundamental_score",
                    "materialization_class": "direct_structured_per_stock_formula",
                    "runtime_materialization_plan_ready": True,
                    "source_dependencies": ["L5.is.sga_rd"],
                    "formula": "score = clamp((0.18 - sga_rd_ratio_revenue) / 0.30, -1, 1)",
                }
            ]
        },
    )
    _write_json(
        manifest_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "review_payload": {"confidence": 0.36},
                }
            ]
        },
    )
    universe_path.write_text(
        "constituents:\n"
        "  - ts_code: 000001.SZ\n"
        "  - ts_code: 000002.SZ\n",
        encoding="utf-8",
    )
    conn = sqlite3.connect(runtime_db_path)
    conn.execute(
        """
        create table realtime_current(
            ts_code text not null,
            dp_id text not null,
            value_json text not null,
            data_status text,
            confidence real,
            source text,
            updated_at integer,
            primary key(ts_code, dp_id)
        )
        """
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
        materialization_plan_path=materialization_path,
        review_manifest_path=manifest_path,
        runtime_db_path=runtime_db_path,
        universe_path=universe_path,
    )

    summary = report["summary"]
    assert summary["direct_formula_plan_count"] == 1
    assert summary["batch_plan_entry_count"] == 1
    assert summary["batch_plan_contract_valid_count"] == 1
    assert summary["batch_plan_review_required_count"] == 1
    assert summary["batch_plan_approved_count"] == 0
    assert summary["planned_upsert_row_count"] == 2
    assert summary["rows_to_insert_count"] == 2
    assert summary["runtime_write_attempted_count"] == 0
    assert summary["production_write_allowed_count"] == 0
    assert len(report["planned_rows"]) == 2

    row = report["rows"][0]
    assert row["dp_id"] == "L0.cost.cac"
    assert row["batch_plan_status"] == "review_required"
    assert row["batch_plan_contract_valid"] is True
    assert row["batch_plan_approved"] is False
    assert row["planned_upsert_row_count"] == 2
    assert row["planned_row_set_sha256"]
    assert row["batch_plan_sha256"]
    assert row["blocking_reasons"] == [
        "controlled_batch_plan_requires_review_approval"
    ]
    assert row["planned_rows_sample"][0]["source"] == (
        "a_share_approval_materialization_batch_plan:L0.cost.cac"
    )
