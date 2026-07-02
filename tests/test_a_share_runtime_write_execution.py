import json
import sqlite3
from pathlib import Path

from scripts import audit_a_share_runtime_write_execution as audit


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


def _batch_plan_row(
    *,
    dp_id: str = "L7.trade.gamma",
    target_ts_codes: list[str] | None = None,
    rows_to_insert: int = 1,
    rows_to_update: int = 1,
    existing_rows_to_backup: int = 1,
    approved: bool = True,
) -> dict:
    target_ts_codes = target_ts_codes or ["000001.SZ", "600000.SH"]
    value_json = {
        "multiplier": 1.0,
        "applicability": "a_share_single_stock_no_listed_option",
    }
    plan_payload = {
        "operation": "upsert_realtime_current",
        "primary_key": ["ts_code", "dp_id"],
        "dp_id": dp_id,
        "score_target": "gamma_multiplier",
        "payload_sha256": "payload-hash",
        "target_scope_sha256": "scope-hash",
        "target_scope_approval_id": "scope-approved",
        "target_ts_codes": target_ts_codes,
        "row_template": {
            "value_json": value_json,
            "value_json_sha256": audit._canonical_hash(value_json),
            "data_status": "Known",
            "confidence": 0.7,
            "source": "a_share_review_approval_gate:approved-gamma",
            "updated_at": "execution_time_epoch_seconds",
        },
        "conflict_policy": "upsert_on_primary_key_after_backup",
        "rollback_policy": "restore backed-up rows and delete new primary keys",
    }
    return {
        "dp_id": dp_id,
        "score_target": "gamma_multiplier",
        "data_status": "Known",
        "payload_sha256": "payload-hash",
        "target_scope_sha256": "scope-hash",
        "batch_plan_status": "batch_plan_approved_backup_required",
        "batch_plan_contract_valid": True,
        "batch_plan_sha256": audit._canonical_hash(plan_payload),
        "batch_plan_approved": approved,
        "planned_upsert_row_count": len(target_ts_codes),
        "rows_to_insert_count": rows_to_insert,
        "rows_to_update_count": rows_to_update,
        "existing_rows_to_backup_count": existing_rows_to_backup,
        "runtime_source": "a_share_review_approval_gate:approved-gamma",
        "batch_plan_payload": plan_payload,
        "runtime_write_attempted": False,
        "production_write_allowed": False,
    }


def test_runtime_write_execution_backs_up_and_upserts(tmp_path: Path) -> None:
    runtime_db_path = tmp_path / "hot.sqlite"
    backup_dir = tmp_path / "backups"
    batch_plan_path = tmp_path / "batch_plan.json"
    _write_runtime_db(runtime_db_path, existing_rows=[("600000.SH", "L7.trade.gamma")])
    _write_json(
        batch_plan_path,
        {
            "batch_plan_set": {"batch_plan_set_id": "a-share-runtime-batch-test"},
            "rows": [_batch_plan_row()],
        },
    )

    report = audit.build_report(
        batch_plan_path=batch_plan_path,
        runtime_db_path=runtime_db_path,
        backup_dir=backup_dir,
        execute=True,
    )

    summary = report["summary"]
    assert summary["execution_status"] == "executed"
    assert summary["runtime_backup_created_count"] == 1
    assert summary["runtime_write_attempted_count"] == 1
    assert summary["runtime_write_completed_count"] == 1
    assert summary["runtime_rows_written_count"] == 2
    assert summary["rows_inserted_count"] == 1
    assert summary["rows_updated_count"] == 1
    assert summary["post_write_verified_count"] == 1
    assert summary["production_write_allowed_count"] == 0

    backup_path = Path(report["backup"]["backup_path"])
    assert backup_path.exists()
    with sqlite3.connect(backup_path) as conn:
        old = conn.execute(
            """
            select value_json, source from realtime_current
            where ts_code = '600000.SH' and dp_id = 'L7.trade.gamma'
            """
        ).fetchone()
        inserted = conn.execute(
            """
            select count(*) from realtime_current
            where ts_code = '000001.SZ' and dp_id = 'L7.trade.gamma'
            """
        ).fetchone()[0]
    assert old == (json.dumps({"old": True}), "old-source")
    assert inserted == 0

    with sqlite3.connect(runtime_db_path) as conn:
        rows = conn.execute(
            """
            select ts_code, value_json, data_status, confidence, source
            from realtime_current
            where dp_id = 'L7.trade.gamma'
            order by ts_code
            """
        ).fetchall()
    assert [row[0] for row in rows] == ["000001.SZ", "600000.SH"]
    assert [json.loads(row[1]) for row in rows] == [
        {
            "applicability": "a_share_single_stock_no_listed_option",
            "multiplier": 1.0,
        },
        {
            "applicability": "a_share_single_stock_no_listed_option",
            "multiplier": 1.0,
        },
    ]
    assert all(row[2] == "Known" for row in rows)
    assert all(row[3] == 0.7 for row in rows)
    assert all(row[4] == "a_share_review_approval_gate:approved-gamma" for row in rows)
    assert "Backup created" in audit.render_markdown(report)


def test_runtime_write_execution_dry_run_does_not_mutate(tmp_path: Path) -> None:
    runtime_db_path = tmp_path / "hot.sqlite"
    backup_dir = tmp_path / "backups"
    batch_plan_path = tmp_path / "batch_plan.json"
    _write_runtime_db(runtime_db_path, existing_rows=[("600000.SH", "L7.trade.gamma")])
    _write_json(
        batch_plan_path,
        {
            "batch_plan_set": {"batch_plan_set_id": "a-share-runtime-batch-test"},
            "rows": [_batch_plan_row()],
        },
    )

    report = audit.build_report(
        batch_plan_path=batch_plan_path,
        runtime_db_path=runtime_db_path,
        backup_dir=backup_dir,
        execute=False,
    )

    assert report["summary"]["execution_status"] == "dry_run_ready"
    assert report["summary"]["runtime_rows_written_count"] == 0
    assert report["backup"]["backup_created"] is False
    assert not backup_dir.exists()
    with sqlite3.connect(runtime_db_path) as conn:
        count = conn.execute("select count(*) from realtime_current").fetchone()[0]
        source = conn.execute(
            "select source from realtime_current where ts_code = '600000.SH'"
        ).fetchone()[0]
    assert count == 1
    assert source == "old-source"


def test_runtime_write_execution_blocks_when_plan_no_longer_matches_db(
    tmp_path: Path,
) -> None:
    runtime_db_path = tmp_path / "hot.sqlite"
    backup_dir = tmp_path / "backups"
    batch_plan_path = tmp_path / "batch_plan.json"
    _write_runtime_db(runtime_db_path)
    _write_json(
        batch_plan_path,
        {
            "batch_plan_set": {"batch_plan_set_id": "a-share-runtime-batch-test"},
            "rows": [_batch_plan_row()],
        },
    )

    report = audit.build_report(
        batch_plan_path=batch_plan_path,
        runtime_db_path=runtime_db_path,
        backup_dir=backup_dir,
        execute=True,
    )

    summary = report["summary"]
    assert summary["execution_status"] == "blocked"
    assert summary["runtime_backup_created_count"] == 0
    assert summary["runtime_write_attempted_count"] == 0
    assert "current_existing_row_count_must_equal_rows_to_update_count" in (
        report["rows"][0]["validation_errors"]
    )
    assert not backup_dir.exists()
    with sqlite3.connect(runtime_db_path) as conn:
        assert conn.execute("select count(*) from realtime_current").fetchone()[0] == 0
