from __future__ import annotations

import json
from pathlib import Path

from scripts import audit_a_share_approval_materialization_batch_approval_gate as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _batch_plan_payload() -> dict:
    return {
        "batch_plan_set": {
            "batch_plan_set_sha256": "set-hash",
        },
        "rows": [
            {
                "dp_id": "L0.cost.cac",
                "score_target": "fundamental_score",
                "batch_plan_status": "review_required",
                "batch_plan_contract_valid": True,
                "batch_plan_sha256": "plan-hash",
                "materialization_plan_sha256": "materialization-hash",
                "planned_row_set_sha256": "row-set-hash",
                "planned_upsert_row_count": 2,
                "rows_to_insert_count": 2,
                "rows_to_update_count": 0,
                "existing_rows_to_backup_count": 0,
                "backup_required": True,
            }
        ],
    }


def test_formula_batch_approval_gate_emits_blank_template_for_missing_approval(
    tmp_path: Path,
) -> None:
    batch_plan_path = tmp_path / "batch_plan.json"
    approvals_path = tmp_path / "missing_approvals.json"
    _write_json(batch_plan_path, _batch_plan_payload())

    report = audit.build_report(
        batch_plan_path=batch_plan_path,
        approvals_path=approvals_path,
    )

    summary = report["summary"]
    assert summary["batch_plan_row_count"] == 1
    assert summary["batch_plan_contract_valid_count"] == 1
    assert summary["approval_records_seen"] == 0
    assert summary["approval_required_count"] == 1
    assert summary["approval_missing_count"] == 1
    assert summary["approved_controlled_formula_batch_plan_count"] == 0
    assert summary["blank_approval_template_count"] == 1
    assert summary["blank_approval_template_contract_valid_count"] == 1
    assert summary["runtime_write_allowed_count"] == 0

    row = report["rows"][0]
    assert row["approval_gate_status"] == "approval_missing"
    assert row["blank_approval_template"]["batch_plan_sha256"] == "plan-hash"
    assert row["blank_approval_template_contract_valid"] is True
    assert row["runtime_write_allowed"] is False


def test_formula_batch_approval_gate_accepts_hash_bound_approval(
    tmp_path: Path,
) -> None:
    batch_plan_path = tmp_path / "batch_plan.json"
    approvals_path = tmp_path / "approvals.json"
    _write_json(batch_plan_path, _batch_plan_payload())
    _write_json(
        approvals_path,
        {
            "approvals": [
                {
                    "approval_id": "approval-1",
                    "dp_id": "L0.cost.cac",
                    "approval_status": "approved",
                    "approval_scope": audit.APPROVAL_SCOPE,
                    "reviewer": "tester",
                    "approved_at": "2026-06-20T00:00:00+08:00",
                    "batch_plan_sha256": "plan-hash",
                    "batch_plan_set_sha256": "set-hash",
                    "materialization_plan_sha256": "materialization-hash",
                    "planned_row_set_sha256": "row-set-hash",
                    "planned_upsert_row_count": 2,
                    "rows_to_insert_count": 2,
                    "rows_to_update_count": 0,
                    "existing_rows_to_backup_count": 0,
                    "backup_required": True,
                    "risk_acknowledged": True,
                    "production_write_allowed": False,
                }
            ]
        },
    )

    report = audit.build_report(
        batch_plan_path=batch_plan_path,
        approvals_path=approvals_path,
    )

    summary = report["summary"]
    assert summary["approval_records_seen"] == 1
    assert summary["approval_missing_count"] == 0
    assert summary["approved_controlled_formula_batch_plan_count"] == 1
    assert summary["approved_planned_upsert_row_count"] == 2
    assert summary["runtime_write_allowed_count"] == 1
    assert summary["production_write_allowed_count"] == 0

    row = report["rows"][0]
    assert row["approval_gate_status"] == "approved_controlled_formula_batch_plan"
    assert row["approval_validation_errors"] == []
    assert row["runtime_write_allowed"] is True
