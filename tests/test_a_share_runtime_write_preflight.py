import json
from pathlib import Path

from scripts import audit_a_share_runtime_write_preflight as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_runtime_write_preflight_blocks_missing_target_scope(tmp_path: Path) -> None:
    approval_gate_path = tmp_path / "approval_gate.json"
    _write_json(
        approval_gate_path,
        {
            "write_plan": [
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "data_status": "Known",
                    "value_json": {"multiplier": 1.0},
                    "confidence": 0.7,
                    "payload_sha256": "abc",
                    "approval": {"approval_id": "approved-1"},
                    "runtime_write_allowed": True,
                    "production_write_allowed": False,
                },
                {
                    "dp_id": "L9.media.short_report",
                    "score_target": "expectation_gap",
                    "data_status": "Known",
                    "target_ts_codes": ["000001.SZ", "600000.SH"],
                    "value_json": {"score": 0.0},
                    "confidence": 0.6,
                    "payload_sha256": "def",
                    "approval": {"approval_id": "approved-2"},
                    "runtime_write_allowed": True,
                    "production_write_allowed": False,
                },
            ]
        },
    )

    report = audit.build_report(approval_gate_path=approval_gate_path)

    assert report["summary"]["approved_write_plan_entry_count"] == 2
    assert report["summary"]["upsert_ready_entry_count"] == 1
    assert report["summary"]["blocked_entry_count"] == 1
    assert report["summary"]["missing_target_scope_count"] == 1
    assert report["summary"]["runtime_rows_would_write_count"] == 2
    assert report["summary"]["runtime_write_attempted_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    by_dp_id = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp_id["L7.trade.gamma"]["upsert_ready"] is False
    assert by_dp_id["L7.trade.gamma"]["blocking_reasons"] == [
        "missing_target_ts_code_or_target_universe_scope"
    ]
    assert by_dp_id["L9.media.short_report"]["upsert_ready"] is True
    assert by_dp_id["L9.media.short_report"]["runtime_rows_would_write"] == 2
    assert "Approval alone is insufficient" in audit.render_markdown(report)


def test_runtime_write_preflight_blocks_review_required_target_scope(
    tmp_path: Path,
) -> None:
    approval_gate_path = tmp_path / "approval_gate.json"
    target_scope_path = tmp_path / "target_scope.json"
    _write_json(
        approval_gate_path,
        {
            "write_plan": [
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "data_status": "Known",
                    "value_json": {"multiplier": 1.0},
                    "confidence": 0.7,
                    "payload_sha256": "abc",
                    "approval": {"approval_id": "approved-1"},
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
                    "payload_sha256": "abc",
                    "target_scope_status": "review_required",
                    "target_scope_contract_valid": True,
                    "candidate_target_ts_code_count": 3,
                    "candidate_runtime_rows_would_write": 3,
                }
            ]
        },
    )

    report = audit.build_report(
        approval_gate_path=approval_gate_path,
        target_scope_path=target_scope_path,
    )

    assert report["summary"]["approved_write_plan_entry_count"] == 1
    assert report["summary"]["upsert_ready_entry_count"] == 0
    assert report["summary"]["blocked_entry_count"] == 1
    assert report["summary"]["missing_target_scope_count"] == 0
    assert report["summary"]["target_scope_candidate_count"] == 1
    assert report["summary"]["target_scope_review_required_count"] == 1
    assert report["summary"]["candidate_runtime_rows_would_write_count"] == 3
    assert report["summary"]["runtime_rows_would_write_count"] == 0
    by_dp_id = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp_id["L7.trade.gamma"]["target_scope_status"] == "review_required"
    assert by_dp_id["L7.trade.gamma"]["target_scope_candidate_count"] == 3
    assert by_dp_id["L7.trade.gamma"]["blocking_reasons"] == [
        "target_scope_candidate_requires_review_approval"
    ]


def test_runtime_write_preflight_blocks_scope_approved_without_batch_plan(
    tmp_path: Path,
) -> None:
    approval_gate_path = tmp_path / "approval_gate.json"
    target_scope_path = tmp_path / "target_scope.json"
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
                    "approval": {"approval_id": "approved-1"},
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
                    "payload_sha256": "short-report",
                    "target_scope_status": "scope_approved_batch_plan_required",
                    "target_scope_contract_valid": True,
                    "candidate_target_ts_code_count": 2,
                    "candidate_runtime_rows_would_write": 2,
                }
            ]
        },
    )

    report = audit.build_report(
        approval_gate_path=approval_gate_path,
        target_scope_path=target_scope_path,
    )

    assert report["summary"]["target_scope_review_required_count"] == 0
    assert report["summary"]["controlled_batch_plan_required_count"] == 1
    assert report["summary"]["candidate_runtime_rows_would_write_count"] == 2
    assert report["summary"]["runtime_rows_would_write_count"] == 0
    by_dp_id = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp_id["L9.media.short_report"]["target_scope_status"] == (
        "scope_approved_batch_plan_required"
    )
    assert by_dp_id["L9.media.short_report"]["blocking_reasons"] == [
        "controlled_batch_upsert_plan_required"
    ]


def test_runtime_write_preflight_blocks_batch_plan_pending_review(
    tmp_path: Path,
) -> None:
    approval_gate_path = tmp_path / "approval_gate.json"
    target_scope_path = tmp_path / "target_scope.json"
    batch_plan_path = tmp_path / "batch_plan.json"
    _write_json(
        approval_gate_path,
        {
            "write_plan": [
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "data_status": "Known",
                    "value_json": {"multiplier": 1.0},
                    "confidence": 0.7,
                    "payload_sha256": "gamma",
                    "approval": {"approval_id": "approved-1"},
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
                    "payload_sha256": "gamma",
                    "target_scope_sha256": "scope-hash",
                    "target_scope_status": "scope_approved_batch_plan_required",
                    "target_scope_contract_valid": True,
                    "candidate_target_ts_code_count": 2,
                    "candidate_runtime_rows_would_write": 2,
                }
            ]
        },
    )
    _write_json(
        batch_plan_path,
        {
            "rows": [
                {
                    "dp_id": "L7.trade.gamma",
                    "payload_sha256": "gamma",
                    "target_scope_sha256": "scope-hash",
                    "batch_plan_status": "review_required",
                    "batch_plan_contract_valid": True,
                    "planned_upsert_row_count": 2,
                    "rows_to_insert_count": 1,
                    "rows_to_update_count": 1,
                    "existing_rows_to_backup_count": 1,
                }
            ]
        },
    )

    report = audit.build_report(
        approval_gate_path=approval_gate_path,
        target_scope_path=target_scope_path,
        batch_plan_path=batch_plan_path,
    )

    summary = report["summary"]
    assert summary["controlled_batch_plan_required_count"] == 0
    assert summary["batch_plan_candidate_count"] == 1
    assert summary["batch_plan_review_required_count"] == 1
    assert summary["batch_plan_planned_upsert_rows_count"] == 2
    assert summary["batch_plan_rows_to_insert_count"] == 1
    assert summary["batch_plan_rows_to_update_count"] == 1
    assert summary["batch_plan_existing_rows_to_backup_count"] == 1
    assert summary["runtime_rows_would_write_count"] == 0
    by_dp_id = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp_id["L7.trade.gamma"]["batch_plan_status"] == "review_required"
    assert by_dp_id["L7.trade.gamma"]["blocking_reasons"] == [
        "controlled_batch_plan_requires_review_approval"
    ]


def test_runtime_write_preflight_blocks_approved_batch_plan_pending_execution(
    tmp_path: Path,
) -> None:
    approval_gate_path = tmp_path / "approval_gate.json"
    target_scope_path = tmp_path / "target_scope.json"
    batch_plan_path = tmp_path / "batch_plan.json"
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
                    "approval": {"approval_id": "approved-1"},
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
                    "payload_sha256": "short-report",
                    "target_scope_sha256": "scope-hash",
                    "target_scope_status": "scope_approved_batch_plan_required",
                    "target_scope_contract_valid": True,
                    "candidate_target_ts_code_count": 2,
                    "candidate_runtime_rows_would_write": 2,
                }
            ]
        },
    )
    _write_json(
        batch_plan_path,
        {
            "rows": [
                {
                    "dp_id": "L9.media.short_report",
                    "payload_sha256": "short-report",
                    "target_scope_sha256": "scope-hash",
                    "batch_plan_status": "batch_plan_approved_backup_required",
                    "batch_plan_contract_valid": True,
                    "batch_plan_approved": True,
                    "planned_upsert_row_count": 2,
                    "rows_to_insert_count": 2,
                    "rows_to_update_count": 0,
                    "existing_rows_to_backup_count": 0,
                }
            ]
        },
    )

    report = audit.build_report(
        approval_gate_path=approval_gate_path,
        target_scope_path=target_scope_path,
        batch_plan_path=batch_plan_path,
    )

    summary = report["summary"]
    assert summary["batch_plan_candidate_count"] == 1
    assert summary["batch_plan_review_required_count"] == 0
    assert summary["batch_plan_approved_count"] == 1
    assert summary["runtime_backup_execution_required_count"] == 1
    assert summary["runtime_rows_would_write_count"] == 0
    by_dp_id = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp_id["L9.media.short_report"]["batch_plan_approved"] is True
    assert by_dp_id["L9.media.short_report"]["blocking_reasons"] == [
        "runtime_backup_and_execution_log_required"
    ]


def test_runtime_write_preflight_recognizes_completed_execution(
    tmp_path: Path,
) -> None:
    approval_gate_path = tmp_path / "approval_gate.json"
    target_scope_path = tmp_path / "target_scope.json"
    batch_plan_path = tmp_path / "batch_plan.json"
    execution_path = tmp_path / "execution.json"
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
                    "approval": {"approval_id": "approved-1"},
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
                    "payload_sha256": "short-report",
                    "target_scope_sha256": "scope-hash",
                    "target_scope_status": "scope_approved_batch_plan_required",
                    "target_scope_contract_valid": True,
                    "candidate_target_ts_code_count": 2,
                    "candidate_runtime_rows_would_write": 2,
                }
            ]
        },
    )
    _write_json(
        batch_plan_path,
        {
            "rows": [
                {
                    "dp_id": "L9.media.short_report",
                    "payload_sha256": "short-report",
                    "target_scope_sha256": "scope-hash",
                    "batch_plan_sha256": "plan-hash",
                    "batch_plan_status": "batch_plan_approved_backup_required",
                    "batch_plan_contract_valid": True,
                    "batch_plan_approved": True,
                    "planned_upsert_row_count": 2,
                    "rows_to_insert_count": 2,
                    "rows_to_update_count": 0,
                    "existing_rows_to_backup_count": 0,
                }
            ]
        },
    )
    _write_json(
        execution_path,
        {
            "rows": [
                {
                    "dp_id": "L9.media.short_report",
                    "payload_sha256": "short-report",
                    "target_scope_sha256": "scope-hash",
                    "batch_plan_sha256": "plan-hash",
                    "execution_status": "executed",
                    "validation_errors": [],
                    "planned_upsert_row_count": 2,
                    "runtime_rows_written": 2,
                    "upserted_row_count": 2,
                    "post_write_verified_row_count": 2,
                    "backup_completed": True,
                    "runtime_write_attempted": True,
                    "runtime_write_completed": True,
                    "production_write_allowed": False,
                }
            ]
        },
    )

    report = audit.build_report(
        approval_gate_path=approval_gate_path,
        target_scope_path=target_scope_path,
        batch_plan_path=batch_plan_path,
        execution_path=execution_path,
    )

    summary = report["summary"]
    assert summary["upsert_ready_entry_count"] == 0
    assert summary["executed_entry_count"] == 1
    assert summary["blocked_entry_count"] == 0
    assert summary["runtime_backup_execution_required_count"] == 0
    assert summary["runtime_execution_completed_count"] == 1
    assert summary["runtime_execution_rows_written_count"] == 2
    assert summary["runtime_execution_post_write_verified_row_count"] == 2
    assert summary["runtime_write_attempted_count"] == 1
    by_dp_id = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp_id["L9.media.short_report"]["runtime_execution_completed"] is True
    assert by_dp_id["L9.media.short_report"]["blocking_reasons"] == []
