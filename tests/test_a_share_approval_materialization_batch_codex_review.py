import json
from pathlib import Path

from scripts import audit_a_share_approval_materialization_batch_approval_gate as gate
from scripts import audit_a_share_approval_materialization_batch_codex_review as audit
from scripts.audit_a_share_runtime_write_batch_plan import REALTIME_PRIMARY_KEY


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _valid_batch_plan() -> dict:
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
    materialization_plan_sha256 = "materialization-plan-hash"
    batch_plan_payload = {
        "operation": "upsert_realtime_current",
        "primary_key": REALTIME_PRIMARY_KEY,
        "dp_id": "L0.demand.terminal",
        "score_target": "fundamental_score",
        "materialization_plan_sha256": materialization_plan_sha256,
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
    batch_plan_sha256 = audit._canonical_hash(batch_plan_payload)
    return {
        "batch_plan_set": {
            "batch_plan_set_sha256": "set-hash",
            "batch_plan_hashes": [batch_plan_sha256],
            "approval_scope": gate.APPROVAL_SCOPE,
            "production_write_allowed": False,
        },
        "planned_rows": planned_rows,
        "rows": [
            {
                "dp_id": "L0.demand.terminal",
                "score_target": "fundamental_score",
                "materialization_class": "direct_structured_per_stock_formula",
                "batch_plan_status": "review_required",
                "batch_plan_contract_valid": True,
                "batch_plan_contract_errors": [],
                "materialization_plan_sha256": materialization_plan_sha256,
                "planned_row_set_sha256": planned_row_set_sha256,
                "batch_plan_sha256": batch_plan_sha256,
                "target_ts_code_count": 1,
                "planned_upsert_row_count": 1,
                "bridge_error_count": 0,
                "existing_rows_to_backup_count": 0,
                "noop_existing_rows_count": 0,
                "existing_conflict_row_count": 0,
                "rows_to_update_count": 0,
                "rows_to_insert_count": 1,
                "runtime_source": (
                    "a_share_approval_materialization_batch_plan:"
                    "L0.demand.terminal"
                ),
                "backup_required": True,
                "backup_path_template": "runtime/backups/test.sqlite",
                "rollback_strategy": "restore affected rows from backup",
                "batch_plan_payload": batch_plan_payload,
                "batch_plan_approved": False,
                "runtime_write_attempted": False,
                "production_write_allowed": False,
            }
        ],
    }


def test_codex_review_emits_gate_accepted_approval(tmp_path: Path) -> None:
    batch_plan_path = tmp_path / "batch_plan.json"
    approvals_path = tmp_path / "approvals.json"
    _write_json(batch_plan_path, _valid_batch_plan())

    report = audit.build_report(
        batch_plan_path=batch_plan_path,
        approved_at="2026-06-20T01:00:00+08:00",
    )
    _write_json(approvals_path, {"approvals": report["approvals"]})

    assert report["summary"]["codex_review_approved_count"] == 1
    assert report["summary"]["approval_record_count"] == 1
    approval = report["approvals"][0]
    assert approval["approval_scope"] == gate.APPROVAL_SCOPE
    assert approval["risk_acknowledged"] is True
    assert approval["production_write_allowed"] is False

    gate_report = gate.build_report(
        batch_plan_path=batch_plan_path,
        approvals_path=approvals_path,
    )
    assert gate_report["summary"]["approval_records_seen"] == 1
    assert gate_report["summary"]["approved_controlled_formula_batch_plan_count"] == 1
    assert gate_report["summary"]["approval_missing_count"] == 0
    assert gate_report["summary"]["approved_planned_upsert_row_count"] == 1


def test_codex_review_rejects_invalid_score(tmp_path: Path) -> None:
    batch_plan = _valid_batch_plan()
    batch_plan["planned_rows"][0]["value_json"]["score"] = 2.0
    batch_plan_path = tmp_path / "batch_plan.json"
    _write_json(batch_plan_path, batch_plan)

    report = audit.build_report(batch_plan_path=batch_plan_path)

    assert report["summary"]["codex_review_approved_count"] == 0
    assert report["summary"]["codex_review_rejected_count"] == 1
    assert report["summary"]["approval_record_count"] == 0
    assert "000001.SZ:score_must_be_in_unit_interval" in (
        report["rows"][0]["validation_errors"]
    )
