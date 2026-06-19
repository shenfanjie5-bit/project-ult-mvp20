#!/usr/bin/env python3
"""Preflight approved A-share runtime write-plan entries before any UPSERT.

The approval gate can approve a payload hash, but ``realtime_current`` requires
an explicit ``ts_code`` scope for every row. This audit is read-only: it checks
whether approved write-plan entries contain enough target-scope information to
be converted into controlled runtime UPSERT batches.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_APPROVAL_GATE_PATH = (
    ROOT / "docs/audit/a_share_review_approval_gate_2026-06-19.json"
)
DEFAULT_TARGET_SCOPE_PATH = (
    ROOT / "docs/audit/a_share_runtime_write_target_scope_2026-06-19.json"
)
DEFAULT_BATCH_PLAN_PATH = (
    ROOT / "docs/audit/a_share_runtime_write_batch_plan_2026-06-19.json"
)
DEFAULT_EXECUTION_PATH = (
    ROOT / "docs/audit/a_share_runtime_write_execution_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_runtime_write_preflight_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_runtime_write_preflight_2026-06-19.md"


def _write_plan_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("write_plan") or report.get("rows") or []
    return [
        dict(row)
        for row in rows
        if isinstance(row, Mapping)
        and row.get("runtime_write_allowed") is True
        and row.get("production_write_allowed") is False
    ]


def _target_ts_codes(row: Mapping[str, Any]) -> list[str]:
    raw = row.get("target_ts_codes")
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    raw_single = row.get("ts_code") or row.get("target_ts_code")
    if raw_single:
        return [str(raw_single)]
    return []


def _runtime_source(row: Mapping[str, Any]) -> str | None:
    approval = row.get("approval")
    approval_id = approval.get("approval_id") if isinstance(approval, Mapping) else None
    if approval_id:
        return f"a_share_review_approval_gate:{approval_id}"
    payload_hash = row.get("payload_sha256")
    if payload_hash:
        return f"a_share_review_approval_gate:{payload_hash}"
    return None


def _target_scope_rows_by_dp_id(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = row
    return rows


def _target_scope_candidate(
    row: Mapping[str, Any],
    target_scope_by_dp_id: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    dp_id = str(row.get("dp_id") or "")
    candidate = target_scope_by_dp_id.get(dp_id)
    if not candidate:
        return None
    if candidate.get("payload_sha256") != row.get("payload_sha256"):
        return None
    return candidate


def _batch_plan_rows_by_dp_id(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = row
    return rows


def _batch_plan_candidate(
    row: Mapping[str, Any],
    target_scope_candidate: Mapping[str, Any] | None,
    batch_plan_by_dp_id: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    dp_id = str(row.get("dp_id") or "")
    candidate = batch_plan_by_dp_id.get(dp_id)
    if not candidate:
        return None
    if candidate.get("payload_sha256") != row.get("payload_sha256"):
        return None
    if target_scope_candidate and candidate.get("target_scope_sha256") != (
        target_scope_candidate.get("target_scope_sha256")
    ):
        return None
    return candidate


def _execution_rows_by_dp_id(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = row
    return rows


def _execution_candidate(
    row: Mapping[str, Any],
    batch_plan_candidate: Mapping[str, Any] | None,
    execution_by_dp_id: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    dp_id = str(row.get("dp_id") or "")
    candidate = execution_by_dp_id.get(dp_id)
    if not candidate:
        return None
    if candidate.get("payload_sha256") != row.get("payload_sha256"):
        return None
    if batch_plan_candidate:
        if candidate.get("target_scope_sha256") != batch_plan_candidate.get(
            "target_scope_sha256"
        ):
            return None
        if candidate.get("batch_plan_sha256") != batch_plan_candidate.get(
            "batch_plan_sha256"
        ):
            return None
    return candidate


def _execution_completed(candidate: Mapping[str, Any] | None) -> bool:
    if not candidate:
        return False
    if candidate.get("execution_status") not in {"executed", "completed"}:
        return False
    if candidate.get("runtime_write_attempted") is not True:
        return False
    if candidate.get("runtime_write_completed") is not True:
        return False
    if candidate.get("backup_completed") is not True:
        return False
    if candidate.get("production_write_allowed") is not False:
        return False
    if candidate.get("validation_errors"):
        return False
    planned = int(candidate.get("planned_upsert_row_count") or 0)
    written = int(
        candidate.get("upserted_row_count")
        or candidate.get("runtime_rows_written")
        or 0
    )
    verified = int(candidate.get("post_write_verified_row_count") or 0)
    return planned > 0 and written == planned and verified == planned


def _row_preflight(
    row: Mapping[str, Any],
    *,
    target_scope_by_dp_id: Mapping[str, Mapping[str, Any]] | None = None,
    batch_plan_by_dp_id: Mapping[str, Mapping[str, Any]] | None = None,
    execution_by_dp_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    target_ts_codes = _target_ts_codes(row)
    target_scope_by_dp_id = target_scope_by_dp_id or {}
    batch_plan_by_dp_id = batch_plan_by_dp_id or {}
    execution_by_dp_id = execution_by_dp_id or {}
    target_scope_candidate = (
        None
        if target_ts_codes
        else _target_scope_candidate(row, target_scope_by_dp_id)
    )
    target_scope_status = None
    target_scope_candidate_count = 0
    candidate_runtime_rows_would_write = 0
    batch_plan_status = None
    batch_plan_planned_upsert_rows = 0
    batch_plan_rows_to_insert = 0
    batch_plan_rows_to_update = 0
    batch_plan_existing_rows_to_backup = 0
    batch_plan_approved = False
    runtime_execution_status = None
    runtime_execution_completed = False
    runtime_execution_rows_written = 0
    runtime_execution_post_write_verified_rows = 0
    runtime_source = _runtime_source(row)
    value_json = row.get("value_json")
    confidence = row.get("confidence")
    data_status = row.get("data_status")
    blocking_reasons: list[str] = []
    if not target_ts_codes:
        if (
            target_scope_candidate
            and target_scope_candidate.get("target_scope_contract_valid") is True
            and target_scope_candidate.get("target_scope_status")
            in {"review_required", "scope_approved_batch_plan_required"}
        ):
            target_scope_status = str(target_scope_candidate.get("target_scope_status"))
            target_scope_candidate_count = int(
                target_scope_candidate.get("candidate_target_ts_code_count") or 0
            )
            candidate_runtime_rows_would_write = int(
                target_scope_candidate.get("candidate_runtime_rows_would_write") or 0
            )
            if target_scope_status == "scope_approved_batch_plan_required":
                batch_plan = _batch_plan_candidate(
                    row,
                    target_scope_candidate,
                    batch_plan_by_dp_id,
                )
                if batch_plan and batch_plan.get("batch_plan_contract_valid") is True:
                    batch_plan_status = str(batch_plan.get("batch_plan_status"))
                    batch_plan_planned_upsert_rows = int(
                        batch_plan.get("planned_upsert_row_count") or 0
                    )
                    batch_plan_rows_to_insert = int(
                        batch_plan.get("rows_to_insert_count") or 0
                    )
                    batch_plan_rows_to_update = int(
                        batch_plan.get("rows_to_update_count") or 0
                    )
                    batch_plan_existing_rows_to_backup = int(
                        batch_plan.get("existing_rows_to_backup_count") or 0
                    )
                    batch_plan_approved = bool(batch_plan.get("batch_plan_approved"))
                    if batch_plan_approved:
                        execution = _execution_candidate(
                            row,
                            batch_plan,
                            execution_by_dp_id,
                        )
                        runtime_execution_status = (
                            str(execution.get("execution_status"))
                            if execution
                            else None
                        )
                        runtime_execution_rows_written = int(
                            (execution or {}).get("upserted_row_count")
                            or (execution or {}).get("runtime_rows_written")
                            or 0
                        )
                        runtime_execution_post_write_verified_rows = int(
                            (execution or {}).get("post_write_verified_row_count") or 0
                        )
                        runtime_execution_completed = _execution_completed(execution)
                        if not runtime_execution_completed:
                            blocking_reasons.append(
                                "runtime_backup_and_execution_log_required"
                                if execution is None
                                else "runtime_execution_report_invalid"
                            )
                    else:
                        blocking_reasons.append(
                            "controlled_batch_plan_requires_review_approval"
                        )
                else:
                    blocking_reasons.append("controlled_batch_upsert_plan_required")
            else:
                blocking_reasons.append("target_scope_candidate_requires_review_approval")
        else:
            blocking_reasons.append("missing_target_ts_code_or_target_universe_scope")
    if not row.get("dp_id"):
        blocking_reasons.append("missing_dp_id")
    if data_status not in {"Known", "NotApplicable"}:
        blocking_reasons.append("data_status_must_be_known_or_not_applicable")
    if not isinstance(value_json, Mapping):
        blocking_reasons.append("value_json_must_be_object")
    if not isinstance(confidence, (int, float)):
        blocking_reasons.append("confidence_must_be_numeric")
    if not runtime_source:
        blocking_reasons.append("missing_runtime_source")
    if row.get("production_write_allowed") is not False:
        blocking_reasons.append("production_write_must_remain_false")
    if row.get("runtime_write_allowed") is not True:
        blocking_reasons.append("runtime_write_not_approved")

    upsert_ready = not blocking_reasons and not runtime_execution_completed
    return {
        "dp_id": row.get("dp_id"),
        "score_target": row.get("score_target"),
        "data_status": data_status,
        "payload_sha256": row.get("payload_sha256"),
        "approval_id": (row.get("approval") or {}).get("approval_id")
        if isinstance(row.get("approval"), Mapping)
        else None,
        "target_ts_code_count": len(target_ts_codes),
        "target_ts_codes_sample": target_ts_codes[:5],
        "target_scope_status": target_scope_status,
        "target_scope_candidate_count": target_scope_candidate_count,
        "candidate_runtime_rows_would_write": candidate_runtime_rows_would_write,
        "batch_plan_status": batch_plan_status,
        "batch_plan_planned_upsert_rows": batch_plan_planned_upsert_rows,
        "batch_plan_rows_to_insert": batch_plan_rows_to_insert,
        "batch_plan_rows_to_update": batch_plan_rows_to_update,
        "batch_plan_existing_rows_to_backup": batch_plan_existing_rows_to_backup,
        "batch_plan_approved": batch_plan_approved,
        "runtime_execution_status": runtime_execution_status,
        "runtime_execution_completed": runtime_execution_completed,
        "runtime_execution_rows_written": runtime_execution_rows_written,
        "runtime_execution_post_write_verified_rows": (
            runtime_execution_post_write_verified_rows
        ),
        "runtime_source": runtime_source,
        "value_json_ready": isinstance(value_json, Mapping),
        "confidence_ready": isinstance(confidence, (int, float)),
        "upsert_ready": upsert_ready,
        "blocking_reasons": blocking_reasons,
        "runtime_write_attempted": runtime_execution_completed,
        "runtime_rows_would_write": len(target_ts_codes) if upsert_ready else 0,
        "production_write_allowed": False,
        "score_mutation": "none",
        "required_next_evidence": [
            "explicit target ts_code list or audited target-universe expansion contract",
            "controlled batch UPSERT plan with backup/rollback path",
            "post-write score-field closure rerun",
        ],
    }


def build_report(
    *,
    approval_gate_path: Path,
    target_scope_path: Path | None = None,
    batch_plan_path: Path | None = None,
    execution_path: Path | None = None,
) -> dict[str, Any]:
    started = time.time()
    target_scope_report = (
        _load_json(target_scope_path)
        if target_scope_path is not None and target_scope_path.exists()
        else {}
    )
    batch_plan_report = (
        _load_json(batch_plan_path)
        if batch_plan_path is not None and batch_plan_path.exists()
        else {}
    )
    execution_report = (
        _load_json(execution_path)
        if execution_path is not None and execution_path.exists()
        else {}
    )
    target_scope_by_dp_id = _target_scope_rows_by_dp_id(target_scope_report)
    batch_plan_by_dp_id = _batch_plan_rows_by_dp_id(batch_plan_report)
    execution_by_dp_id = _execution_rows_by_dp_id(execution_report)
    rows = [
        _row_preflight(
            row,
            target_scope_by_dp_id=target_scope_by_dp_id,
            batch_plan_by_dp_id=batch_plan_by_dp_id,
            execution_by_dp_id=execution_by_dp_id,
        )
        for row in _write_plan_rows(_load_json(approval_gate_path))
    ]
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    reason_counts: Counter[str] = Counter()
    for row in rows:
        reason_counts.update(str(reason) for reason in row["blocking_reasons"])
    executable = [row for row in rows if row["upsert_ready"]]
    executed = [row for row in rows if row["runtime_execution_completed"]]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "approval_gate_path": _portable_path(approval_gate_path),
            "target_scope_path": _portable_path(target_scope_path)
            if target_scope_path is not None
            else None,
            "batch_plan_path": _portable_path(batch_plan_path)
            if batch_plan_path is not None
            else None,
            "execution_path": _portable_path(execution_path)
            if execution_path is not None
            else None,
        },
        "summary": {
            "approved_write_plan_entry_count": len(rows),
            "upsert_ready_entry_count": len(executable),
            "executed_entry_count": len(executed),
            "blocked_entry_count": len(rows) - len(executable) - len(executed),
            "missing_target_scope_count": reason_counts.get(
                "missing_target_ts_code_or_target_universe_scope", 0
            ),
            "runtime_rows_would_write_count": sum(
                int(row["runtime_rows_would_write"]) for row in rows
            ),
            "target_scope_candidate_count": sum(
                1 for row in rows if row["target_scope_candidate_count"]
            ),
            "target_scope_review_required_count": reason_counts.get(
                "target_scope_candidate_requires_review_approval", 0
            ),
            "controlled_batch_plan_required_count": reason_counts.get(
                "controlled_batch_upsert_plan_required", 0
            ),
            "batch_plan_candidate_count": sum(
                1 for row in rows if row["batch_plan_status"]
            ),
            "batch_plan_review_required_count": reason_counts.get(
                "controlled_batch_plan_requires_review_approval", 0
            ),
            "batch_plan_approved_count": sum(
                1 for row in rows if row["batch_plan_approved"]
            ),
            "runtime_backup_execution_required_count": reason_counts.get(
                "runtime_backup_and_execution_log_required", 0
            ),
            "runtime_execution_report_invalid_count": reason_counts.get(
                "runtime_execution_report_invalid", 0
            ),
            "runtime_execution_completed_count": len(executed),
            "runtime_execution_rows_written_count": sum(
                int(row["runtime_execution_rows_written"]) for row in rows
            ),
            "runtime_execution_post_write_verified_row_count": sum(
                int(row["runtime_execution_post_write_verified_rows"])
                for row in rows
            ),
            "batch_plan_planned_upsert_rows_count": sum(
                int(row["batch_plan_planned_upsert_rows"]) for row in rows
            ),
            "batch_plan_rows_to_insert_count": sum(
                int(row["batch_plan_rows_to_insert"]) for row in rows
            ),
            "batch_plan_rows_to_update_count": sum(
                int(row["batch_plan_rows_to_update"]) for row in rows
            ),
            "batch_plan_existing_rows_to_backup_count": sum(
                int(row["batch_plan_existing_rows_to_backup"]) for row in rows
            ),
            "candidate_runtime_rows_would_write_count": sum(
                int(row["candidate_runtime_rows_would_write"]) for row in rows
            ),
            "runtime_write_attempted_count": len(executed),
            "production_write_allowed_count": 0,
            "blocking_reason_counts": dict(sorted(reason_counts.items())),
            "score_mutation": "none; preflight is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share runtime write preflight",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Approved write-plan entries: `{summary['approved_write_plan_entry_count']}`",
        f"- Upsert-ready entries: `{summary['upsert_ready_entry_count']}`",
        f"- Executed entries: `{summary.get('executed_entry_count', 0)}`",
        f"- Blocked entries: `{summary['blocked_entry_count']}`",
        f"- Missing target scope: `{summary['missing_target_scope_count']}`",
        f"- Target-scope candidates: `{summary.get('target_scope_candidate_count', 0)}`",
        f"- Target-scope review required: `{summary.get('target_scope_review_required_count', 0)}`",
        f"- Controlled batch plans required: `{summary.get('controlled_batch_plan_required_count', 0)}`",
        f"- Batch-plan candidates: `{summary.get('batch_plan_candidate_count', 0)}`",
        f"- Batch-plan review required: `{summary.get('batch_plan_review_required_count', 0)}`",
        f"- Batch-plan approved: `{summary.get('batch_plan_approved_count', 0)}`",
        f"- Runtime backup/execution required: `{summary.get('runtime_backup_execution_required_count', 0)}`",
        f"- Runtime execution completed: `{summary.get('runtime_execution_completed_count', 0)}`",
        f"- Runtime execution rows written: `{summary.get('runtime_execution_rows_written_count', 0)}`",
        f"- Runtime execution verified rows: `{summary.get('runtime_execution_post_write_verified_row_count', 0)}`",
        f"- Batch-plan planned UPSERT rows: `{summary.get('batch_plan_planned_upsert_rows_count', 0)}`",
        f"- Batch-plan existing rows requiring backup: `{summary.get('batch_plan_existing_rows_to_backup_count', 0)}`",
        f"- Candidate runtime rows that would write if approved: `{summary.get('candidate_runtime_rows_would_write_count', 0)}`",
        f"- Runtime rows that would write: `{summary['runtime_rows_would_write_count']}`",
        f"- Runtime writes attempted: `{summary['runtime_write_attempted_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | status | target scope | upsert ready | executed | blockers | runtime writes attempted |",
        "|---|---|---:|---:|---:|---|---:|",
    ]
    for row in report["rows"]:
        blockers = ", ".join(row["blocking_reasons"]) or "none"
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['data_status']}` | "
            f"{row['target_ts_code_count']} | "
            f"{'yes' if row['upsert_ready'] else 'no'} | "
            f"{'yes' if row.get('runtime_execution_completed') else 'no'} | "
            f"{blockers} | "
            f"{'yes' if row['runtime_write_attempted'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Approval alone is insufficient for realtime_current UPSERT.",
            "- Each runtime write still needs explicit target ts_code scope or an audited target-universe expansion contract.",
            "- This audit creates no runtime rows and no production writes.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-gate-path", type=Path, default=DEFAULT_APPROVAL_GATE_PATH)
    parser.add_argument("--target-scope-path", type=Path, default=DEFAULT_TARGET_SCOPE_PATH)
    parser.add_argument("--batch-plan-path", type=Path, default=DEFAULT_BATCH_PLAN_PATH)
    parser.add_argument("--execution-path", type=Path, default=DEFAULT_EXECUTION_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    args = parser.parse_args()

    report = build_report(
        approval_gate_path=args.approval_gate_path,
        target_scope_path=args.target_scope_path,
        batch_plan_path=args.batch_plan_path,
        execution_path=args.execution_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
