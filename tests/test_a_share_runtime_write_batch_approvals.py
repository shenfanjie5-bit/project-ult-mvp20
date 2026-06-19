import json
from pathlib import Path

from scripts import audit_a_share_runtime_write_batch_approvals as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_runtime_write_batch_approvals_accept_valid_batch_plans(
    tmp_path: Path,
) -> None:
    batch_plan_path = tmp_path / "batch_plan.json"
    _write_json(
        batch_plan_path,
        {
            "batch_plan_set": {
                "batch_plan_set_sha256": "set-hash",
                "approval_scope": "controlled_runtime_batch_plan",
                "production_write_allowed": False,
            },
            "rows": [
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "payload_sha256": "gamma-payload",
                    "target_scope_sha256": "gamma-scope",
                    "target_scope_approval_id": "scope-gamma",
                    "batch_plan_status": "review_required",
                    "batch_plan_contract_valid": True,
                    "batch_plan_sha256": "gamma-plan",
                    "planned_upsert_row_count": 2,
                    "rows_to_insert_count": 1,
                    "rows_to_update_count": 1,
                    "existing_rows_to_backup_count": 1,
                    "backup_required": True,
                    "runtime_write_attempted": False,
                    "production_write_allowed": False,
                    "batch_plan_payload": {
                        "operation": "upsert_realtime_current",
                        "primary_key": ["ts_code", "dp_id"],
                        "target_ts_codes": ["000001.SZ", "600000.SH"],
                        "row_template": {
                            "source": "a_share_review_approval_gate:approved-gamma",
                            "value_json_sha256": "value-hash",
                        },
                        "conflict_policy": "upsert_on_primary_key_after_backup",
                    },
                },
                {
                    "dp_id": "L9.media.short_report",
                    "score_target": "expectation_gap",
                    "payload_sha256": "short-report-payload",
                    "target_scope_sha256": "short-report-scope",
                    "target_scope_approval_id": "scope-short-report",
                    "batch_plan_status": "review_required",
                    "batch_plan_contract_valid": True,
                    "batch_plan_sha256": "short-report-plan",
                    "planned_upsert_row_count": 2,
                    "rows_to_insert_count": 2,
                    "rows_to_update_count": 0,
                    "existing_rows_to_backup_count": 0,
                    "backup_required": True,
                    "runtime_write_attempted": False,
                    "production_write_allowed": False,
                    "batch_plan_payload": {
                        "operation": "upsert_realtime_current",
                        "primary_key": ["ts_code", "dp_id"],
                        "target_ts_codes": ["000001.SZ", "600000.SH"],
                        "row_template": {
                            "source": "a_share_review_approval_gate:approved-short-report",
                            "value_json_sha256": "value-hash",
                        },
                        "conflict_policy": "upsert_on_primary_key_after_backup",
                    },
                },
            ],
        },
    )

    report = audit.build_report(
        batch_plan_path=batch_plan_path,
        approved_at="2026-06-19T20:00:00+08:00",
    )

    summary = report["summary"]
    assert summary["batch_plan_row_count"] == 2
    assert summary["batch_approval_record_count"] == 2
    assert summary["approved_controlled_batch_plan_count"] == 2
    assert summary["batch_policy_rejected_count"] == 0
    assert summary["planned_upsert_row_count"] == 4
    assert summary["rows_to_insert_count"] == 3
    assert summary["rows_to_update_count"] == 1
    assert summary["existing_rows_to_backup_count"] == 1
    assert summary["runtime_write_attempted_count"] == 0
    assert summary["production_write_allowed_count"] == 0
    approvals_by_dp = {row["dp_id"]: row for row in report["batch_approvals"]}
    assert approvals_by_dp["L7.trade.gamma"]["approval_scope"] == (
        "controlled_runtime_batch_plan"
    )
    assert approvals_by_dp["L9.media.short_report"]["batch_plan_sha256"] == (
        "short-report-plan"
    )
    assert "approve only the controlled batch-plan hashes" in audit.render_markdown(report)


def test_runtime_write_batch_approvals_reject_invalid_batch_plan(
    tmp_path: Path,
) -> None:
    batch_plan_path = tmp_path / "batch_plan.json"
    _write_json(
        batch_plan_path,
        {
            "rows": [
                {
                    "dp_id": "L7.trade.gamma",
                    "batch_plan_status": "review_required",
                    "batch_plan_contract_valid": True,
                    "batch_plan_sha256": "gamma-plan",
                    "target_scope_sha256": "gamma-scope",
                    "target_scope_approval_id": "scope-gamma",
                    "planned_upsert_row_count": 2,
                    "rows_to_insert_count": 2,
                    "rows_to_update_count": 1,
                    "existing_rows_to_backup_count": 0,
                    "backup_required": True,
                    "runtime_write_attempted": False,
                    "production_write_allowed": False,
                    "batch_plan_payload": {
                        "operation": "upsert_realtime_current",
                        "primary_key": ["ts_code", "dp_id"],
                        "target_ts_codes": ["000001.SZ", "600000.SH"],
                        "row_template": {
                            "source": "source",
                            "value_json_sha256": "value-hash",
                        },
                        "conflict_policy": "upsert_on_primary_key_after_backup",
                    },
                }
            ]
        },
    )

    report = audit.build_report(batch_plan_path=batch_plan_path)

    assert report["summary"]["batch_approval_record_count"] == 0
    assert report["summary"]["batch_policy_rejected_count"] == 1
    row = report["rows"][0]
    assert row["approval_decision"] == "batch_plan_policy_rejected"
    assert "insert_plus_update_count_must_equal_planned_rows" in row["validation_errors"]
    assert "backup_rows_must_match_update_rows" in row["validation_errors"]
