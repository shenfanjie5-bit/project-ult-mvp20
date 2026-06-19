#!/usr/bin/env python3
"""Create read-only approval records for A-share runtime batch plans.

This approves only the controlled batch-plan hashes. It does not create a
database backup, does not execute UPSERTs, and does not mutate
``runtime/hot.sqlite``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_runtime_write_batch_plan import (  # noqa: E402
    DEFAULT_JSON_OUTPUT as DEFAULT_BATCH_PLAN_PATH,
    REALTIME_PRIMARY_KEY,
)
from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_APPROVALS_OUTPUT = (
    ROOT / "docs/audit/a_share_runtime_write_batch_approvals_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_runtime_write_batch_approvals_2026-06-19.md"
)

DETERMINISTIC_BATCH_DP_IDS = {
    "L7.trade.gamma",
    "L9.media.short_report",
}


def _approval_id(dp_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", dp_id).strip("-").lower()
    return f"codex-runtime-batch-20260619-{slug}"


def _batch_plan_policy_errors(row: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    dp_id = str(row.get("dp_id") or "")
    payload = row.get("batch_plan_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    row_template = payload.get("row_template")
    row_template = row_template if isinstance(row_template, Mapping) else {}
    target_ts_codes = payload.get("target_ts_codes")
    target_ts_codes = target_ts_codes if isinstance(target_ts_codes, list) else []
    planned_rows = int(row.get("planned_upsert_row_count") or 0)
    rows_to_insert = int(row.get("rows_to_insert_count") or 0)
    rows_to_update = int(row.get("rows_to_update_count") or 0)
    backup_rows = int(row.get("existing_rows_to_backup_count") or 0)

    if dp_id not in DETERMINISTIC_BATCH_DP_IDS:
        errors.append("dp_id_not_in_deterministic_batch_policy")
    if row.get("batch_plan_contract_valid") is not True:
        errors.append("batch_plan_contract_must_be_valid")
    if row.get("batch_plan_status") not in {
        "review_required",
        "batch_plan_approved_backup_required",
    }:
        errors.append("batch_plan_status_must_be_review_required")
    if not row.get("batch_plan_sha256"):
        errors.append("batch_plan_sha256_must_be_present")
    if not row.get("target_scope_sha256"):
        errors.append("target_scope_sha256_must_be_present")
    if not row.get("target_scope_approval_id"):
        errors.append("target_scope_approval_id_must_be_present")
    if planned_rows <= 0:
        errors.append("planned_upsert_row_count_must_be_positive")
    if len(target_ts_codes) != planned_rows:
        errors.append("target_ts_code_count_must_match_planned_upsert_rows")
    if rows_to_insert + rows_to_update != planned_rows:
        errors.append("insert_plus_update_count_must_equal_planned_rows")
    if backup_rows != rows_to_update:
        errors.append("backup_rows_must_match_update_rows")
    if row.get("backup_required") is not True:
        errors.append("backup_required_must_be_true")
    if row.get("runtime_write_attempted") is not False:
        errors.append("runtime_write_attempted_must_be_false")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_allowed_must_be_false")
    if payload.get("operation") != "upsert_realtime_current":
        errors.append("operation_must_be_upsert_realtime_current")
    if payload.get("primary_key") != REALTIME_PRIMARY_KEY:
        errors.append("primary_key_must_match_realtime_current")
    if payload.get("conflict_policy") != "upsert_on_primary_key_after_backup":
        errors.append("conflict_policy_must_require_backup")
    if not row_template.get("source"):
        errors.append("row_template_source_must_be_present")
    if not row_template.get("value_json_sha256"):
        errors.append("row_template_value_json_hash_must_be_present")
    return errors


def _approval_record(
    row: Mapping[str, Any],
    *,
    approved_at: str,
    batch_plan_set: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "approval_id": _approval_id(str(row.get("dp_id") or "")),
        "dp_id": row.get("dp_id"),
        "approval_status": "approved",
        "approval_scope": "controlled_runtime_batch_plan",
        "reviewer": "codex-deterministic-batch-plan-review",
        "approved_at": approved_at,
        "batch_plan_sha256": row.get("batch_plan_sha256"),
        "batch_plan_set_sha256": batch_plan_set.get("batch_plan_set_sha256"),
        "payload_sha256": row.get("payload_sha256"),
        "target_scope_sha256": row.get("target_scope_sha256"),
        "target_scope_approval_id": row.get("target_scope_approval_id"),
        "planned_upsert_row_count": row.get("planned_upsert_row_count"),
        "rows_to_insert_count": row.get("rows_to_insert_count"),
        "rows_to_update_count": row.get("rows_to_update_count"),
        "existing_rows_to_backup_count": row.get("existing_rows_to_backup_count"),
        "backup_required": True,
        "risk_acknowledged": True,
        "review_basis": "controlled batch plan hash binds target primary keys, value template, source, backup requirement, and rollback policy",
        "production_write_allowed": False,
    }


def _decision_for_row(
    row: Mapping[str, Any],
    *,
    approved_at: str,
    batch_plan_set: Mapping[str, Any],
) -> dict[str, Any]:
    errors = _batch_plan_policy_errors(row)
    approval = (
        None
        if errors
        else _approval_record(
            row,
            approved_at=approved_at,
            batch_plan_set=batch_plan_set,
        )
    )
    return {
        "dp_id": row.get("dp_id"),
        "score_target": row.get("score_target"),
        "batch_plan_status": row.get("batch_plan_status"),
        "batch_plan_sha256": row.get("batch_plan_sha256"),
        "planned_upsert_row_count": row.get("planned_upsert_row_count"),
        "approval_decision": "approved_controlled_runtime_batch_plan"
        if approval
        else "batch_plan_policy_rejected",
        "approval_record": approval,
        "validation_errors": errors,
    }


def build_report(
    *,
    batch_plan_path: Path,
    approved_at: str | None = None,
) -> dict[str, Any]:
    payload = _load_json(batch_plan_path)
    approved_at = approved_at or dt.datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    batch_plan_set = payload.get("batch_plan_set")
    batch_plan_set = batch_plan_set if isinstance(batch_plan_set, Mapping) else {}
    rows = [
        _decision_for_row(
            row,
            approved_at=approved_at,
            batch_plan_set=batch_plan_set,
        )
        for row in payload.get("rows") or []
        if isinstance(row, Mapping)
    ]
    approvals = [
        row["approval_record"]
        for row in rows
        if isinstance(row.get("approval_record"), Mapping)
    ]
    decision_counts = Counter(str(row.get("approval_decision") or "") for row in rows)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {"batch_plan_path": _portable_path(batch_plan_path)},
        "summary": {
            "batch_plan_row_count": len(rows),
            "batch_approval_record_count": len(approvals),
            "approved_controlled_batch_plan_count": decision_counts.get(
                "approved_controlled_runtime_batch_plan", 0
            ),
            "batch_policy_rejected_count": decision_counts.get(
                "batch_plan_policy_rejected", 0
            ),
            "planned_upsert_row_count": sum(
                int(record.get("planned_upsert_row_count") or 0)
                for record in approvals
            ),
            "rows_to_insert_count": sum(
                int(record.get("rows_to_insert_count") or 0)
                for record in approvals
            ),
            "rows_to_update_count": sum(
                int(record.get("rows_to_update_count") or 0)
                for record in approvals
            ),
            "existing_rows_to_backup_count": sum(
                int(record.get("existing_rows_to_backup_count") or 0)
                for record in approvals
            ),
            "runtime_write_attempted_count": 0,
            "production_write_allowed_count": 0,
            "decision_counts": dict(sorted(decision_counts.items())),
            "score_mutation": "batch approval records only; no realtime_current or production score mutation",
        },
        "batch_approvals": approvals,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share runtime write batch approvals",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Batch-plan rows checked: `{summary['batch_plan_row_count']}`",
        f"- Batch approval records: `{summary['batch_approval_record_count']}`",
        f"- Approved controlled batch plans: `{summary['approved_controlled_batch_plan_count']}`",
        f"- Batch policy rejected: `{summary['batch_policy_rejected_count']}`",
        f"- Planned UPSERT rows covered: `{summary['planned_upsert_row_count']}`",
        f"- Runtime writes attempted: `{summary['runtime_write_attempted_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Approved Batch Records",
        "",
        "| dp_id | approval_id | planned rows | plan hash |",
        "|---|---|---:|---|",
    ]
    for approval in report.get("batch_approvals") or []:
        lines.append(
            "| "
            f"`{approval['dp_id']}` | "
            f"`{approval['approval_id']}` | "
            f"{approval.get('planned_upsert_row_count', 0)} | "
            f"`{str(approval.get('batch_plan_sha256') or '')[:12]}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- These records approve only the controlled batch-plan hashes.",
            "- They do not create a runtime backup and do not execute UPSERTs.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-plan-path", type=Path, default=DEFAULT_BATCH_PLAN_PATH)
    parser.add_argument("--approvals-output", type=Path, default=DEFAULT_APPROVALS_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    args = parser.parse_args()

    report = build_report(batch_plan_path=args.batch_plan_path)
    args.approvals_output.parent.mkdir(parents=True, exist_ok=True)
    args.approvals_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
