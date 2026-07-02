import json
import sqlite3
from pathlib import Path

from scripts import audit_a_share_approval_materialization_batch_execution_preflight as audit
from scripts.audit_a_share_runtime_write_batch_plan import REALTIME_PRIMARY_KEY


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_runtime_db(path: Path, existing_rows: list[tuple[str, str]] | None = None) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            create table realtime_current (
                ts_code text not null,
                dp_id text not null,
                value_json text not null,
                data_status text not null,
                confidence real,
                source text not null,
                updated_at integer not null,
                primary key (ts_code, dp_id)
            ) without rowid
            """
        )
        for ts_code, dp_id in existing_rows or []:
            conn.execute(
                """
                insert into realtime_current
                    (ts_code, dp_id, value_json, data_status, confidence, source, updated_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts_code,
                    dp_id,
                    json.dumps({"old": True}),
                    "Known",
                    0.1,
                    "old-source",
                    1,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _batch_and_gate() -> tuple[dict, dict]:
    value_json = {
        "score": 0.25,
        "drivers": ["L5.is.revenue_yoy"],
        "components": {"revenue_yoy_pct": 9.0},
        "materialization_formula": "score = clamp(tanh(revenue_yoy_pct / 35), -1, 1)",
        "materialization_class": "direct_structured_per_stock_formula",
    }
    planned_rows = [
        {
            "ts_code": "000001.SZ",
            "dp_id": "L0.demand.terminal",
            "score_target": "fundamental_score",
            "value_json": value_json,
            "data_status": "Known",
            "confidence": 0.36,
            "source": "a_share_approval_materialization_batch_plan:L0.demand.terminal",
            "updated_at": "execution_time_epoch_seconds",
            "bridge_signal": 0.25,
        }
    ]
    planned_row_set_sha256 = audit._row_set_hash(planned_rows)
    batch_payload = {
        "operation": "upsert_realtime_current",
        "primary_key": REALTIME_PRIMARY_KEY,
        "dp_id": "L0.demand.terminal",
        "score_target": "fundamental_score",
        "materialization_plan_sha256": "materialization-plan-hash",
        "planned_row_set_sha256": planned_row_set_sha256,
        "target_ts_codes": ["000001.SZ"],
        "row_contract": {
            "data_status": "Known",
            "source": "a_share_approval_materialization_batch_plan:L0.demand.terminal",
            "updated_at": "execution_time_epoch_seconds",
            "per_row_value_json": True,
        },
        "conflict_policy": "upsert_on_primary_key_after_backup",
        "rollback_policy": "restore backed-up rows and delete new primary keys",
    }
    batch_plan_sha256 = audit._canonical_hash(batch_payload)
    batch_plan = {
        "batch_plan_set": {"batch_plan_set_sha256": "set-hash"},
        "planned_rows": planned_rows,
        "rows": [
            {
                "dp_id": "L0.demand.terminal",
                "score_target": "fundamental_score",
                "batch_plan_status": "review_required",
                "batch_plan_contract_valid": True,
                "planned_row_set_sha256": planned_row_set_sha256,
                "batch_plan_sha256": batch_plan_sha256,
                "planned_upsert_row_count": 1,
                "rows_to_insert_count": 1,
                "rows_to_update_count": 0,
                "existing_rows_to_backup_count": 0,
                "noop_existing_rows_count": 0,
                "batch_plan_payload": batch_payload,
                "batch_plan_approved": False,
                "runtime_write_attempted": False,
                "production_write_allowed": False,
            }
        ],
    }
    approval_gate = {
        "rows": [
            {
                "dp_id": "L0.demand.terminal",
                "approval_gate_status": "approved_controlled_formula_batch_plan",
                "runtime_write_allowed": True,
                "batch_plan_sha256": batch_plan_sha256,
            }
        ]
    }
    return batch_plan, approval_gate


def _make_single_row_plan_noop(batch_plan: dict) -> None:
    row = batch_plan["rows"][0]
    row["rows_to_insert_count"] = 0
    row["rows_to_update_count"] = 0
    row["existing_rows_to_backup_count"] = 1
    row["noop_existing_rows_count"] = 1


def _write_matching_runtime_row(path: Path, batch_plan: dict, *, updated_at: int) -> None:
    _write_runtime_db(path)
    planned = batch_plan["planned_rows"][0]
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            insert into realtime_current
                (ts_code, dp_id, value_json, data_status, confidence, source, updated_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                planned["ts_code"],
                planned["dp_id"],
                audit._canonical_value_json(planned["value_json"]),
                planned["data_status"],
                planned["confidence"],
                planned["source"],
                updated_at,
            ),
        )
        conn.commit()


def test_formula_batch_execution_preflight_ready_without_mutation(tmp_path: Path) -> None:
    batch_plan_path = tmp_path / "batch_plan.json"
    gate_path = tmp_path / "gate.json"
    runtime_db_path = tmp_path / "hot.sqlite"
    backup_dir = tmp_path / "backups"
    batch_plan, approval_gate = _batch_and_gate()
    _write_json(batch_plan_path, batch_plan)
    _write_json(gate_path, approval_gate)
    _write_runtime_db(runtime_db_path)

    report = audit.build_report(
        batch_plan_path=batch_plan_path,
        approval_gate_path=gate_path,
        runtime_db_path=runtime_db_path,
        backup_dir=backup_dir,
    )

    summary = report["summary"]
    assert summary["execution_status"] == "dry_run_ready"
    assert summary["approved_batch_plan_count"] == 1
    assert summary["preflight_ready_count"] == 1
    assert summary["runtime_rows_would_write_count"] == 1
    assert summary["runtime_backup_created_count"] == 0
    assert summary["runtime_write_attempted_count"] == 0
    assert not backup_dir.exists()
    with sqlite3.connect(runtime_db_path) as conn:
        assert conn.execute("select count(*) from realtime_current").fetchone()[0] == 0
    assert "dry_run_ready" in audit.render_markdown(report)


def test_formula_batch_execution_execute_backs_up_and_upserts(tmp_path: Path) -> None:
    batch_plan_path = tmp_path / "batch_plan.json"
    gate_path = tmp_path / "gate.json"
    runtime_db_path = tmp_path / "hot.sqlite"
    backup_dir = tmp_path / "backups"
    batch_plan, approval_gate = _batch_and_gate()
    _write_json(batch_plan_path, batch_plan)
    _write_json(gate_path, approval_gate)
    _write_runtime_db(runtime_db_path)

    report = audit.build_report(
        batch_plan_path=batch_plan_path,
        approval_gate_path=gate_path,
        runtime_db_path=runtime_db_path,
        backup_dir=backup_dir,
        execute=True,
    )

    summary = report["summary"]
    assert summary["execution_status"] == "executed"
    assert summary["runtime_backup_created_count"] == 1
    assert summary["runtime_write_attempted_count"] == 1
    assert summary["runtime_write_completed_count"] == 1
    assert summary["runtime_rows_written_count"] == 1
    assert summary["post_write_verified_count"] == 1
    assert summary["post_write_verified_row_count"] == 1
    assert summary["post_write_verification_error_count"] == 0

    backup_path = Path(report["backup"]["backup_path"])
    assert backup_path.exists()
    with sqlite3.connect(backup_path) as conn:
        assert conn.execute("select count(*) from realtime_current").fetchone()[0] == 0
    with sqlite3.connect(runtime_db_path) as conn:
        row = conn.execute(
            """
            select value_json, data_status, confidence, source
            from realtime_current
            where ts_code = '000001.SZ' and dp_id = 'L0.demand.terminal'
            """
        ).fetchone()
    assert json.loads(row[0]) == {
        "components": {"revenue_yoy_pct": 9.0},
        "drivers": ["L5.is.revenue_yoy"],
        "materialization_class": "direct_structured_per_stock_formula",
        "materialization_formula": "score = clamp(tanh(revenue_yoy_pct / 35), -1, 1)",
        "score": 0.25,
    }
    assert row[1:] == (
        "Known",
        0.36,
        "a_share_approval_materialization_batch_plan:L0.demand.terminal",
    )
    assert "executed" in audit.render_markdown(report)


def test_formula_batch_execution_execute_preserves_noop_updated_at(tmp_path: Path) -> None:
    batch_plan_path = tmp_path / "batch_plan.json"
    gate_path = tmp_path / "gate.json"
    runtime_db_path = tmp_path / "hot.sqlite"
    backup_dir = tmp_path / "backups"
    batch_plan, approval_gate = _batch_and_gate()
    _make_single_row_plan_noop(batch_plan)
    _write_json(batch_plan_path, batch_plan)
    _write_json(gate_path, approval_gate)
    _write_matching_runtime_row(runtime_db_path, batch_plan, updated_at=123)

    report = audit.build_report(
        batch_plan_path=batch_plan_path,
        approval_gate_path=gate_path,
        runtime_db_path=runtime_db_path,
        backup_dir=backup_dir,
        execute=True,
    )

    summary = report["summary"]
    assert summary["execution_status"] == "executed"
    assert summary["runtime_backup_created_count"] == 1
    assert summary["runtime_rows_would_write_count"] == 0
    assert summary["runtime_rows_would_noop_count"] == 1
    assert summary["runtime_rows_written_count"] == 0
    assert summary["rows_noop_count"] == 1
    assert summary["noop_rows_preserved_count"] == 1
    assert summary["noop_updated_at_changed_count"] == 0
    assert summary["post_write_verified_row_count"] == 1
    assert summary["post_write_timestamp_verified_row_count"] == 1
    assert summary["post_write_verification_error_count"] == 0

    with sqlite3.connect(runtime_db_path) as conn:
        updated_at = conn.execute(
            """
            select updated_at from realtime_current
            where ts_code = '000001.SZ' and dp_id = 'L0.demand.terminal'
            """
        ).fetchone()[0]
    assert updated_at == 123


def test_formula_batch_execution_preflight_blocks_on_current_db_mismatch(
    tmp_path: Path,
) -> None:
    batch_plan_path = tmp_path / "batch_plan.json"
    gate_path = tmp_path / "gate.json"
    runtime_db_path = tmp_path / "hot.sqlite"
    backup_dir = tmp_path / "backups"
    batch_plan, approval_gate = _batch_and_gate()
    _write_json(batch_plan_path, batch_plan)
    _write_json(gate_path, approval_gate)
    _write_runtime_db(runtime_db_path, existing_rows=[("000001.SZ", "L0.demand.terminal")])

    report = audit.build_report(
        batch_plan_path=batch_plan_path,
        approval_gate_path=gate_path,
        runtime_db_path=runtime_db_path,
        backup_dir=backup_dir,
    )

    assert report["summary"]["execution_status"] == "blocked"
    assert report["summary"]["preflight_ready_count"] == 0
    assert "current_existing_row_count_must_equal_backup_count" in (
        report["rows"][0]["validation_errors"]
    )
    assert "current_insert_count_must_equal_rows_to_insert_count" in (
        report["rows"][0]["validation_errors"]
    )
