import json
import sqlite3
from pathlib import Path

from scripts import audit_a_share_runtime_write_batch_plan as audit


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


def test_runtime_write_batch_plan_packages_review_required_plan(
    tmp_path: Path,
) -> None:
    approval_gate_path = tmp_path / "approval_gate.json"
    target_scope_path = tmp_path / "target_scope.json"
    runtime_db_path = tmp_path / "hot.sqlite"

    _write_runtime_db(runtime_db_path, existing_rows=[("600000.SH", "L7.trade.gamma")])
    _write_json(
        approval_gate_path,
        {
            "write_plan": [
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "data_status": "Known",
                    "value_json": {
                        "multiplier": 1.0,
                        "applicability": "a_share_single_stock_no_listed_option",
                    },
                    "confidence": 0.7,
                    "payload_sha256": "gamma",
                    "approval": {"approval_id": "approved-gamma"},
                    "runtime_write_allowed": True,
                    "production_write_allowed": False,
                }
            ]
        },
    )
    _write_json(
        target_scope_path,
        {
            "rows": [
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "data_status": "Known",
                    "payload_sha256": "gamma",
                    "approval_id": "approved-gamma",
                    "target_scope_status": "scope_approved_batch_plan_required",
                    "target_scope_contract_valid": True,
                    "target_scope_approval_valid": True,
                    "target_scope_sha256": "scope-hash",
                    "target_scope_approval": {"approval_id": "scope-approved"},
                    "target_scope_payload": {
                        "candidate_target_ts_codes": ["000001.SZ", "600000.SH"]
                    },
                }
            ]
        },
    )

    report = audit.build_report(
        approval_gate_path=approval_gate_path,
        target_scope_path=target_scope_path,
        runtime_db_path=runtime_db_path,
    )

    summary = report["summary"]
    assert summary["scope_approved_entry_count"] == 1
    assert summary["batch_plan_contract_valid_count"] == 1
    assert summary["batch_plan_contract_invalid_count"] == 0
    assert summary["batch_plan_review_required_count"] == 1
    assert summary["batch_plan_approved_count"] == 0
    assert summary["planned_upsert_row_count"] == 2
    assert summary["rows_to_insert_count"] == 1
    assert summary["rows_to_update_count"] == 1
    assert summary["existing_rows_to_backup_count"] == 1
    assert summary["runtime_write_attempted_count"] == 0
    assert summary["production_write_allowed_count"] == 0

    row = report["rows"][0]
    assert row["batch_plan_status"] == "review_required"
    assert row["batch_plan_sha256"]
    assert row["batch_plan_payload"]["primary_key"] == ["ts_code", "dp_id"]
    assert row["batch_plan_payload"]["row_template"]["source"] == (
        "a_share_review_approval_gate:approved-gamma"
    )
    assert row["blocking_reasons"] == [
        "controlled_batch_plan_requires_review_approval"
    ]
    assert "This audit creates no runtime rows" in audit.render_markdown(report)


def test_runtime_write_batch_plan_blocks_unapproved_target_scope(
    tmp_path: Path,
) -> None:
    approval_gate_path = tmp_path / "approval_gate.json"
    target_scope_path = tmp_path / "target_scope.json"
    runtime_db_path = tmp_path / "hot.sqlite"

    _write_runtime_db(runtime_db_path)
    _write_json(
        approval_gate_path,
        {
            "write_plan": [
                {
                    "dp_id": "L9.media.short_report",
                    "score_target": "expectation_gap",
                    "data_status": "Known",
                    "value_json": {"score": 0.0},
                    "confidence": 0.6,
                    "payload_sha256": "short-report",
                    "approval": {"approval_id": "approved-short-report"},
                    "runtime_write_allowed": True,
                    "production_write_allowed": False,
                }
            ]
        },
    )
    _write_json(
        target_scope_path,
        {
            "rows": [
                {
                    "dp_id": "L9.media.short_report",
                    "score_target": "expectation_gap",
                    "payload_sha256": "short-report",
                    "target_scope_status": "scope_approved_batch_plan_required",
                    "target_scope_contract_valid": True,
                    "target_scope_approval_valid": False,
                    "target_scope_sha256": "scope-hash",
                    "target_scope_payload": {
                        "candidate_target_ts_codes": ["000001.SZ"]
                    },
                }
            ]
        },
    )

    report = audit.build_report(
        approval_gate_path=approval_gate_path,
        target_scope_path=target_scope_path,
        runtime_db_path=runtime_db_path,
    )

    assert report["summary"]["batch_plan_contract_valid_count"] == 0
    assert report["summary"]["batch_plan_contract_invalid_count"] == 1
    assert report["summary"]["planned_upsert_row_count"] == 0
    row = report["rows"][0]
    assert row["batch_plan_status"] == "blocked_contract_invalid"
    assert "target_scope_approval_must_be_valid" in row["batch_plan_contract_errors"]
    assert row["blocking_reasons"] == ["batch_plan_contract_invalid"]


def test_runtime_write_batch_plan_accepts_matching_batch_approval(
    tmp_path: Path,
) -> None:
    approval_gate_path = tmp_path / "approval_gate.json"
    target_scope_path = tmp_path / "target_scope.json"
    runtime_db_path = tmp_path / "hot.sqlite"
    batch_approvals_path = tmp_path / "batch_approvals.json"

    _write_runtime_db(runtime_db_path)
    _write_json(
        approval_gate_path,
        {
            "write_plan": [
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "data_status": "Known",
                    "value_json": {
                        "multiplier": 1.0,
                        "applicability": "a_share_single_stock_no_listed_option",
                    },
                    "confidence": 0.7,
                    "payload_sha256": "gamma",
                    "approval": {"approval_id": "approved-gamma"},
                    "runtime_write_allowed": True,
                    "production_write_allowed": False,
                }
            ]
        },
    )
    _write_json(
        target_scope_path,
        {
            "rows": [
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "data_status": "Known",
                    "payload_sha256": "gamma",
                    "approval_id": "approved-gamma",
                    "target_scope_status": "scope_approved_batch_plan_required",
                    "target_scope_contract_valid": True,
                    "target_scope_approval_valid": True,
                    "target_scope_sha256": "scope-hash",
                    "target_scope_approval": {"approval_id": "scope-approved"},
                    "target_scope_payload": {
                        "candidate_target_ts_codes": ["000001.SZ"]
                    },
                }
            ]
        },
    )
    draft = audit.build_report(
        approval_gate_path=approval_gate_path,
        target_scope_path=target_scope_path,
        runtime_db_path=runtime_db_path,
    )
    batch_plan_sha256 = draft["rows"][0]["batch_plan_sha256"]
    _write_json(
        batch_approvals_path,
        {
            "batch_approvals": [
                {
                    "approval_id": "batch-approval-1",
                    "dp_id": "L7.trade.gamma",
                    "approval_status": "approved",
                    "approval_scope": "controlled_runtime_batch_plan",
                    "reviewer": "reviewer",
                    "approved_at": "2026-06-19T20:00:00+08:00",
                    "batch_plan_sha256": batch_plan_sha256,
                    "payload_sha256": "gamma",
                    "target_scope_sha256": "scope-hash",
                    "risk_acknowledged": True,
                    "backup_required": True,
                    "production_write_allowed": False,
                }
            ]
        },
    )

    report = audit.build_report(
        approval_gate_path=approval_gate_path,
        target_scope_path=target_scope_path,
        runtime_db_path=runtime_db_path,
        batch_approvals_path=batch_approvals_path,
    )

    summary = report["summary"]
    assert summary["batch_plan_review_required_count"] == 0
    assert summary["batch_plan_approved_count"] == 1
    row = report["rows"][0]
    assert row["batch_plan_status"] == "batch_plan_approved_backup_required"
    assert row["batch_plan_approval_valid"] is True
    assert row["blocking_reasons"] == ["runtime_backup_and_execution_log_required"]
