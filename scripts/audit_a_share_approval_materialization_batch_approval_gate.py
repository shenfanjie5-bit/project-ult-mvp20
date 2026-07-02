#!/usr/bin/env python3
"""Validate approval gate for formula materialization batch plans.

The materialization batch-plan audit packages reviewable UPSERT plans, but a
separate approval record is still required before backup/execution preflight.
This audit is read-only: it validates any supplied approval records and emits
blank hash-bound templates for missing approvals.
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

from scripts.audit_a_share_approval_materialization_batch_plan import (  # noqa: E402
    DEFAULT_JSON_OUTPUT as DEFAULT_BATCH_PLAN_PATH,
)
from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_APPROVALS_PATH = (
    AUDIT_DIR / "a_share_approval_materialization_batch_approvals_2026-06-20.json"
)
DEFAULT_JSON_OUTPUT = (
    AUDIT_DIR / "a_share_approval_materialization_batch_approval_gate_2026-06-20.json"
)
DEFAULT_MD_OUTPUT = (
    AUDIT_DIR / "a_share_approval_materialization_batch_approval_gate_2026-06-20.md"
)
APPROVAL_SCOPE = "controlled_formula_materialization_batch_plan"


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _approval_id(dp_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", dp_id).strip("-").lower()
    return f"codex-formula-batch-review-{slug}"


def _approval_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("approvals", payload.get("batch_approvals", payload.get("rows", [])))
    if not isinstance(raw, list):
        return []
    return [dict(row) for row in raw if isinstance(row, Mapping)]


def _records_by_dp(records: list[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    by_dp: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        dp_id = str(record.get("dp_id") or "")
        if dp_id:
            by_dp.setdefault(dp_id, []).append(record)
    return by_dp


def _template_for_row(row: Mapping[str, Any], batch_plan_set: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "approval_id": _approval_id(str(row.get("dp_id") or "")),
        "dp_id": row.get("dp_id"),
        "approval_status": "",
        "approval_scope": APPROVAL_SCOPE,
        "reviewer": "",
        "approved_at": "",
        "batch_plan_sha256": row.get("batch_plan_sha256"),
        "batch_plan_set_sha256": batch_plan_set.get("batch_plan_set_sha256"),
        "materialization_plan_sha256": row.get("materialization_plan_sha256"),
        "planned_row_set_sha256": row.get("planned_row_set_sha256"),
        "planned_upsert_row_count": row.get("planned_upsert_row_count"),
        "rows_to_insert_count": row.get("rows_to_insert_count"),
        "rows_to_update_count": row.get("rows_to_update_count"),
        "existing_rows_to_backup_count": row.get("existing_rows_to_backup_count"),
        "backup_required": row.get("backup_required"),
        "risk_acknowledged": "",
        "review_basis": (
            "Approve only after reviewing the direct formula, target primary keys, "
            "planned row-set hash, backup/rollback rule, and score impact."
        ),
        "production_write_allowed": False,
    }


def _template_errors(template: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    required_bound_fields = [
        "approval_id",
        "dp_id",
        "approval_scope",
        "batch_plan_sha256",
        "batch_plan_set_sha256",
        "materialization_plan_sha256",
        "planned_row_set_sha256",
        "planned_upsert_row_count",
        "rows_to_insert_count",
        "rows_to_update_count",
        "existing_rows_to_backup_count",
        "review_basis",
    ]
    for field in required_bound_fields:
        if template.get(field) in {None, ""}:
            errors.append(f"{field}_must_be_bound")
    if template.get("approval_status") != "":
        errors.append("blank_template_approval_status_must_be_empty")
    if template.get("reviewer") != "":
        errors.append("blank_template_reviewer_must_be_empty")
    if template.get("approved_at") != "":
        errors.append("blank_template_approved_at_must_be_empty")
    if template.get("risk_acknowledged") != "":
        errors.append("blank_template_risk_acknowledged_must_be_empty")
    if template.get("approval_scope") != APPROVAL_SCOPE:
        errors.append("approval_scope_must_match_formula_batch_scope")
    if template.get("backup_required") is not True:
        errors.append("backup_required_must_be_true")
    if template.get("production_write_allowed") is not False:
        errors.append("production_write_allowed_must_be_false")
    return errors


def _approval_errors(
    *,
    row: Mapping[str, Any],
    approval: Mapping[str, Any],
    batch_plan_set: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    checks = {
        "dp_id": row.get("dp_id"),
        "approval_scope": APPROVAL_SCOPE,
        "batch_plan_sha256": row.get("batch_plan_sha256"),
        "batch_plan_set_sha256": batch_plan_set.get("batch_plan_set_sha256"),
        "materialization_plan_sha256": row.get("materialization_plan_sha256"),
        "planned_row_set_sha256": row.get("planned_row_set_sha256"),
        "planned_upsert_row_count": row.get("planned_upsert_row_count"),
        "rows_to_insert_count": row.get("rows_to_insert_count"),
        "rows_to_update_count": row.get("rows_to_update_count"),
        "existing_rows_to_backup_count": row.get("existing_rows_to_backup_count"),
    }
    for field, expected in checks.items():
        if approval.get(field) != expected:
            errors.append(f"{field}_must_match_batch_plan")
    if not _nonempty(approval.get("approval_id")):
        errors.append("approval_id_must_be_non_empty")
    if approval.get("approval_status") != "approved":
        errors.append("approval_status_must_be_approved")
    if not _nonempty(approval.get("reviewer")):
        errors.append("reviewer_must_be_non_empty")
    if not _nonempty(approval.get("approved_at")):
        errors.append("approved_at_must_be_non_empty")
    if approval.get("backup_required") is not True:
        errors.append("backup_required_must_be_true")
    if approval.get("risk_acknowledged") is not True:
        errors.append("risk_acknowledged_must_be_true")
    if approval.get("production_write_allowed") is not False:
        errors.append("production_write_allowed_must_be_false")
    return errors


def _row_decision(
    row: Mapping[str, Any],
    *,
    records: list[Mapping[str, Any]],
    batch_plan_set: Mapping[str, Any],
) -> dict[str, Any]:
    template = _template_for_row(row, batch_plan_set)
    template_errors = _template_errors(template)
    if row.get("batch_plan_contract_valid") is not True:
        status = "batch_plan_contract_invalid"
        approval = None
        approval_errors = ["batch_plan_contract_must_be_valid"]
    elif not records:
        status = "approval_missing"
        approval = None
        approval_errors = ["missing approval record"]
    elif len(records) > 1:
        status = "approval_rejected"
        approval = dict(records[0])
        approval_errors = ["multiple approval records for dp_id"]
    else:
        approval = dict(records[0])
        approval_errors = _approval_errors(
            row=row,
            approval=approval,
            batch_plan_set=batch_plan_set,
        )
        status = "approved_controlled_formula_batch_plan" if not approval_errors else "approval_rejected"
    return {
        "dp_id": row.get("dp_id"),
        "score_target": row.get("score_target"),
        "batch_plan_status": row.get("batch_plan_status"),
        "batch_plan_contract_valid": row.get("batch_plan_contract_valid") is True,
        "batch_plan_sha256": row.get("batch_plan_sha256"),
        "materialization_plan_sha256": row.get("materialization_plan_sha256"),
        "planned_row_set_sha256": row.get("planned_row_set_sha256"),
        "planned_upsert_row_count": row.get("planned_upsert_row_count"),
        "approval_gate_status": status,
        "approval_record_count": len(records),
        "approval_record": approval,
        "approval_validation_errors": approval_errors,
        "blank_approval_template": template,
        "blank_approval_template_contract_valid": not template_errors,
        "blank_approval_template_validation_errors": template_errors,
        "runtime_write_allowed": status == "approved_controlled_formula_batch_plan",
        "production_write_allowed": False,
    }


def build_report(*, batch_plan_path: Path, approvals_path: Path) -> dict[str, Any]:
    batch_plan = _load_json(batch_plan_path)
    approvals_payload = _load_json(approvals_path)
    approvals_file_exists = approvals_path.exists()
    approval_records = _approval_records(approvals_payload)
    records_by_dp = _records_by_dp(approval_records)
    batch_plan_set = batch_plan.get("batch_plan_set")
    batch_plan_set = batch_plan_set if isinstance(batch_plan_set, Mapping) else {}
    rows = [
        _row_decision(
            row,
            records=records_by_dp.get(str(row.get("dp_id") or ""), []),
            batch_plan_set=batch_plan_set,
        )
        for row in batch_plan.get("rows") or []
        if isinstance(row, Mapping)
    ]
    batch_dp_ids = {str(row.get("dp_id") or "") for row in rows}
    orphan_records = [
        dict(record)
        for record in approval_records
        if str(record.get("dp_id") or "") not in batch_dp_ids
    ]
    status_counts = Counter(str(row["approval_gate_status"]) for row in rows)
    approved_rows = [
        row for row in rows if row["approval_gate_status"] == "approved_controlled_formula_batch_plan"
    ]
    rejected_rows = [row for row in rows if row["approval_gate_status"] == "approval_rejected"]
    templates = [row["blank_approval_template"] for row in rows]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "batch_plan_path": _portable_path(batch_plan_path),
            "approvals_path": _portable_path(approvals_path),
            "approvals_file_exists": approvals_file_exists,
        },
        "summary": {
            "batch_plan_row_count": len(rows),
            "batch_plan_contract_valid_count": sum(
                1 for row in rows if row["batch_plan_contract_valid"]
            ),
            "approval_records_seen": len(approval_records),
            "orphan_approval_record_count": len(orphan_records),
            "approval_required_count": sum(
                1 for row in rows if row["batch_plan_contract_valid"]
            ),
            "approval_missing_count": status_counts.get("approval_missing", 0),
            "approval_rejected_count": len(rejected_rows) + len(orphan_records),
            "approved_controlled_formula_batch_plan_count": len(approved_rows),
            "blank_approval_template_count": len(templates),
            "blank_approval_template_contract_valid_count": sum(
                1 for row in rows if row["blank_approval_template_contract_valid"]
            ),
            "planned_upsert_row_count": sum(
                int(row.get("planned_upsert_row_count") or 0) for row in rows
            ),
            "approved_planned_upsert_row_count": sum(
                int(row.get("planned_upsert_row_count") or 0) for row in approved_rows
            ),
            "runtime_write_allowed_count": sum(
                1 for row in rows if row["runtime_write_allowed"]
            ),
            "production_write_allowed_count": 0,
            "approval_gate_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; approval gate is read-only and does not alter realtime_current",
        },
        "blank_approval_templates": templates,
        "orphan_approval_records": orphan_records,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share formula materialization batch approval gate",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Batch-plan rows checked: `{summary['batch_plan_row_count']}`",
        f"- Contract-valid batch plans: `{summary['batch_plan_contract_valid_count']}`",
        f"- Approval records seen: `{summary['approval_records_seen']}`",
        f"- Approval required: `{summary['approval_required_count']}`",
        f"- Approval missing: `{summary['approval_missing_count']}`",
        f"- Approval rejected: `{summary['approval_rejected_count']}`",
        f"- Approved formula batch plans: `{summary['approved_controlled_formula_batch_plan_count']}`",
        f"- Blank approval templates: `{summary['blank_approval_template_count']}`",
        f"- Planned UPSERT rows covered: `{summary['planned_upsert_row_count']}`",
        f"- Approved planned UPSERT rows: `{summary['approved_planned_upsert_row_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | gate status | planned rows | plan hash | template valid |",
        "|---|---|---:|---|---:|",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['approval_gate_status']}` | "
            f"{row.get('planned_upsert_row_count', 0)} | "
            f"`{str(row.get('batch_plan_sha256') or '')[:12]}` | "
            f"{'yes' if row.get('blank_approval_template_contract_valid') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The batch plans are packaged, but approval records are still missing.",
            "- Blank templates are hash-bound review inputs, not approvals.",
            "- Runtime backup/execution remains blocked until valid approvals exist.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-plan-path", type=Path, default=DEFAULT_BATCH_PLAN_PATH)
    parser.add_argument("--approvals-path", type=Path, default=DEFAULT_APPROVALS_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        batch_plan_path=args.batch_plan_path,
        approvals_path=args.approvals_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
