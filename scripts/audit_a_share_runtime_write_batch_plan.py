#!/usr/bin/env python3
"""Build a read-only controlled batch plan for approved A-share runtime writes.

The target-scope audit can prove that an approved neutral payload applies to the
current A-share universe, but that still is not an executable write. This audit
packages the exact affected primary keys, value template, pre-write conflict
counts, backup requirement, and rollback rule for review. It never writes
``runtime/hot.sqlite``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_runtime_write_preflight import (  # noqa: E402
    DEFAULT_APPROVAL_GATE_PATH,
    _runtime_source,
    _write_plan_rows,
)
from scripts.audit_a_share_runtime_write_target_scope import (  # noqa: E402
    DEFAULT_JSON_OUTPUT as DEFAULT_TARGET_SCOPE_PATH,
)
from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_RUNTIME_DB_PATH = ROOT / "runtime/hot.sqlite"
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_runtime_write_batch_plan_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_runtime_write_batch_plan_2026-06-19.md"
DEFAULT_BATCH_APPROVALS_PATH = (
    ROOT / "docs/audit/a_share_runtime_write_batch_approvals_2026-06-19.json"
)

REQUIRED_REALTIME_COLUMNS = {
    "ts_code",
    "dp_id",
    "value_json",
    "data_status",
    "confidence",
    "source",
    "updated_at",
}
REALTIME_PRIMARY_KEY = ["ts_code", "dp_id"]
CHUNK_SIZE = 500


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_value_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _write_plan_by_dp_id(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for row in _write_plan_rows(report):
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = row
    return rows


def _approved_target_scope_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in report.get("rows") or []:
        if (
            isinstance(row, Mapping)
            and row.get("target_scope_status") == "scope_approved_batch_plan_required"
        ):
            rows.append(dict(row))
    return rows


def _target_ts_codes(row: Mapping[str, Any]) -> list[str]:
    payload = row.get("target_scope_payload")
    if not isinstance(payload, Mapping):
        return []
    raw = payload.get("candidate_target_ts_codes")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def _schema_evidence(conn: sqlite3.Connection) -> dict[str, Any]:
    columns = conn.execute("pragma table_info(realtime_current)").fetchall()
    column_names = [str(row[1]) for row in columns]
    pk_columns = [
        str(row[1])
        for row in sorted(
            (row for row in columns if int(row[5] or 0) > 0),
            key=lambda row: int(row[5]),
        )
    ]
    missing_columns = sorted(REQUIRED_REALTIME_COLUMNS - set(column_names))
    return {
        "table": "realtime_current",
        "column_names": column_names,
        "required_columns": sorted(REQUIRED_REALTIME_COLUMNS),
        "missing_required_columns": missing_columns,
        "primary_key_columns": pk_columns,
        "primary_key_valid": pk_columns == REALTIME_PRIMARY_KEY,
        "schema_contract_valid": not missing_columns
        and pk_columns == REALTIME_PRIMARY_KEY,
    }


def _chunked(values: list[str], size: int = CHUNK_SIZE) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _existing_rows(
    conn: sqlite3.Connection,
    *,
    dp_id: str,
    ts_codes: list[str],
) -> list[dict[str, Any]]:
    if not ts_codes:
        return []
    rows: list[dict[str, Any]] = []
    for chunk in _chunked(ts_codes):
        placeholders = ",".join("?" for _ in chunk)
        sql = (
            "select ts_code, value_json, data_status, confidence, source "
            "from realtime_current "
            f"where dp_id = ? and ts_code in ({placeholders})"
        )
        for db_row in conn.execute(sql, [dp_id, *chunk]).fetchall():
            rows.append(
                {
                    "ts_code": db_row[0],
                    "value_json": db_row[1],
                    "data_status": db_row[2],
                    "confidence": db_row[3],
                    "source": db_row[4],
                }
            )
    rows.sort(key=lambda row: str(row["ts_code"]))
    return rows


def _value_json_matches(left_text: str, right_value: Any) -> bool:
    try:
        left_value = json.loads(left_text)
    except json.JSONDecodeError:
        return False
    return _canonical_value_json(left_value) == _canonical_value_json(right_value)


def _noop_existing_count(
    existing_rows: list[Mapping[str, Any]],
    *,
    value_json: Any,
    data_status: str,
    confidence: float,
    source: str,
) -> int:
    count = 0
    for row in existing_rows:
        if not _value_json_matches(str(row.get("value_json") or ""), value_json):
            continue
        if row.get("data_status") != data_status:
            continue
        if row.get("source") != source:
            continue
        try:
            row_confidence = float(row.get("confidence"))
        except (TypeError, ValueError):
            continue
        if row_confidence == float(confidence):
            count += 1
    return count


def _plan_errors(
    *,
    target_scope_row: Mapping[str, Any],
    write_plan_row: Mapping[str, Any] | None,
    target_ts_codes: list[str],
    schema: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if target_scope_row.get("target_scope_contract_valid") is not True:
        errors.append("target_scope_contract_must_be_valid")
    if target_scope_row.get("target_scope_approval_valid") is not True:
        errors.append("target_scope_approval_must_be_valid")
    if not target_scope_row.get("target_scope_sha256"):
        errors.append("target_scope_sha256_must_be_present")
    if not target_ts_codes:
        errors.append("target_ts_codes_must_be_non_empty")
    if write_plan_row is None:
        errors.append("matching_write_plan_row_required")
        return errors
    if write_plan_row.get("payload_sha256") != target_scope_row.get("payload_sha256"):
        errors.append("payload_sha256_must_match_write_plan")
    if write_plan_row.get("runtime_write_allowed") is not True:
        errors.append("runtime_write_must_be_approved")
    if write_plan_row.get("production_write_allowed") is not False:
        errors.append("production_write_must_remain_false")
    if not isinstance(write_plan_row.get("value_json"), Mapping):
        errors.append("value_json_must_be_object")
    if write_plan_row.get("data_status") not in {"Known", "NotApplicable"}:
        errors.append("data_status_must_be_known_or_not_applicable")
    if not isinstance(write_plan_row.get("confidence"), (int, float)):
        errors.append("confidence_must_be_numeric")
    if not _runtime_source(write_plan_row):
        errors.append("runtime_source_must_be_derivable")
    if schema.get("schema_contract_valid") is not True:
        errors.append("realtime_current_schema_contract_must_be_valid")
    return errors


def _batch_approval_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_records = payload.get("batch_approvals", payload.get("approvals", []))
    if not isinstance(raw_records, list):
        return []
    return [dict(record) for record in raw_records if isinstance(record, Mapping)]


def _batch_approvals_by_dp_id(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    by_dp_id: dict[str, Mapping[str, Any]] = {}
    for record in _batch_approval_records(payload):
        dp_id = str(record.get("dp_id") or "")
        if dp_id:
            by_dp_id[dp_id] = record
    return by_dp_id


def _batch_approval_errors(
    *,
    row: Mapping[str, Any],
    batch_plan_sha256: str | None,
    approval: Mapping[str, Any] | None,
) -> list[str]:
    if approval is None:
        return ["missing batch-plan approval record"]
    errors: list[str] = []
    if approval.get("dp_id") != row.get("dp_id"):
        errors.append("batch approval dp_id must match batch-plan row")
    if approval.get("approval_status") != "approved":
        errors.append("batch approval_status must be approved")
    if approval.get("approval_scope") != "controlled_runtime_batch_plan":
        errors.append("batch approval_scope must be controlled_runtime_batch_plan")
    if not approval.get("approval_id"):
        errors.append("batch approval_id must be non-empty")
    if not approval.get("reviewer"):
        errors.append("batch reviewer must be non-empty")
    if not approval.get("approved_at"):
        errors.append("batch approved_at must be non-empty")
    if approval.get("batch_plan_sha256") != batch_plan_sha256:
        errors.append("batch_plan_sha256 must match canonical batch-plan payload")
    if approval.get("payload_sha256") != row.get("payload_sha256"):
        errors.append("payload_sha256 must match batch-plan row")
    if approval.get("target_scope_sha256") != row.get("target_scope_sha256"):
        errors.append("target_scope_sha256 must match batch-plan row")
    if approval.get("risk_acknowledged") is not True:
        errors.append("batch risk_acknowledged must be true")
    if approval.get("backup_required") is not True:
        errors.append("batch backup_required must be true")
    if approval.get("production_write_allowed") is not False:
        errors.append("batch production_write_allowed must be false")
    return errors


def _row_batch_plan(
    target_scope_row: Mapping[str, Any],
    *,
    write_plan_by_dp_id: Mapping[str, Mapping[str, Any]],
    conn: sqlite3.Connection,
    schema: Mapping[str, Any],
    batch_approvals_by_dp_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    dp_id = str(target_scope_row.get("dp_id") or "")
    write_plan_row = write_plan_by_dp_id.get(dp_id)
    target_ts_codes = _target_ts_codes(target_scope_row)
    errors = _plan_errors(
        target_scope_row=target_scope_row,
        write_plan_row=write_plan_row,
        target_ts_codes=target_ts_codes,
        schema=schema,
    )
    contract_valid = not errors and write_plan_row is not None
    existing = (
        _existing_rows(conn, dp_id=dp_id, ts_codes=target_ts_codes)
        if contract_valid
        else []
    )
    value_json = write_plan_row.get("value_json") if write_plan_row else None
    data_status = str(write_plan_row.get("data_status")) if write_plan_row else ""
    confidence = float(write_plan_row.get("confidence")) if write_plan_row else 0.0
    runtime_source = _runtime_source(write_plan_row) if write_plan_row else None
    value_json_sha256 = _canonical_hash(value_json) if isinstance(value_json, Mapping) else None
    noop_count = (
        _noop_existing_count(
            existing,
            value_json=value_json,
            data_status=data_status,
            confidence=confidence,
            source=str(runtime_source),
        )
        if contract_valid
        else 0
    )
    plan_payload = (
        {
            "operation": "upsert_realtime_current",
            "primary_key": REALTIME_PRIMARY_KEY,
            "dp_id": dp_id,
            "score_target": target_scope_row.get("score_target"),
            "payload_sha256": target_scope_row.get("payload_sha256"),
            "target_scope_sha256": target_scope_row.get("target_scope_sha256"),
            "target_scope_approval_id": (
                target_scope_row.get("target_scope_approval") or {}
            ).get("approval_id")
            if isinstance(target_scope_row.get("target_scope_approval"), Mapping)
            else None,
            "target_ts_codes": target_ts_codes,
            "row_template": {
                "value_json": value_json,
                "value_json_sha256": value_json_sha256,
                "data_status": data_status,
                "confidence": confidence,
                "source": runtime_source,
                "updated_at": "execution_time_epoch_seconds",
            },
            "conflict_policy": "upsert_on_primary_key_after_backup",
            "rollback_policy": (
                "restore backed-up rows for affected primary keys and delete "
                "new primary keys that did not exist before the batch"
            ),
        }
        if contract_valid
        else None
    )
    batch_plan_sha256 = _canonical_hash(plan_payload) if plan_payload else None
    approval = (batch_approvals_by_dp_id or {}).get(dp_id)
    approval_errors = (
        _batch_approval_errors(
            row={
                "dp_id": dp_id,
                "payload_sha256": target_scope_row.get("payload_sha256"),
                "target_scope_sha256": target_scope_row.get("target_scope_sha256"),
            },
            batch_plan_sha256=batch_plan_sha256,
            approval=approval,
        )
        if contract_valid
        else ["batch_plan_contract_invalid"]
    )
    batch_plan_approved = contract_valid and not approval_errors
    batch_plan_status = (
        "batch_plan_approved_backup_required"
        if batch_plan_approved
        else "review_required"
        if contract_valid
        else "blocked_contract_invalid"
    )
    blocking_reasons = (
        ["runtime_backup_and_execution_log_required"]
        if batch_plan_approved
        else [
            "controlled_batch_plan_requires_review_approval"
            if contract_valid
            else "batch_plan_contract_invalid"
        ]
    )
    return {
        "dp_id": dp_id,
        "score_target": target_scope_row.get("score_target"),
        "data_status": data_status if write_plan_row else target_scope_row.get("data_status"),
        "payload_sha256": target_scope_row.get("payload_sha256"),
        "approval_id": target_scope_row.get("approval_id"),
        "target_scope_sha256": target_scope_row.get("target_scope_sha256"),
        "target_scope_approval_id": (
            target_scope_row.get("target_scope_approval") or {}
        ).get("approval_id")
        if isinstance(target_scope_row.get("target_scope_approval"), Mapping)
        else None,
        "batch_plan_status": batch_plan_status,
        "batch_plan_contract_valid": contract_valid,
        "batch_plan_contract_errors": errors,
        "batch_plan_sha256": batch_plan_sha256,
        "batch_plan_approval": approval if batch_plan_approved else None,
        "batch_plan_approval_valid": batch_plan_approved,
        "batch_plan_approval_errors": approval_errors,
        "value_json_sha256": value_json_sha256,
        "target_ts_code_count": len(target_ts_codes),
        "target_ts_codes_sample": target_ts_codes[:10],
        "planned_upsert_row_count": len(target_ts_codes) if contract_valid else 0,
        "existing_rows_to_backup_count": len(existing),
        "existing_rows_sample": existing[:5],
        "existing_conflict_row_count": len(existing),
        "noop_existing_rows_count": noop_count,
        "rows_to_update_count": len(existing),
        "rows_to_insert_count": (
            len(target_ts_codes) - len(existing) if contract_valid else 0
        ),
        "runtime_source": runtime_source,
        "backup_required": contract_valid,
        "backup_path_template": (
            "runtime/backups/hot.sqlite.before_a_share_runtime_write_batch_"
            f"{str(batch_plan_sha256 or '')[:12]}.sqlite"
            if contract_valid
            else None
        ),
        "rollback_strategy": (
            "restore affected pre-write rows from the backup snapshot; delete "
            "affected primary keys absent from the backup snapshot"
            if contract_valid
            else None
        ),
        "batch_plan_payload": plan_payload,
        "batch_plan_approved": batch_plan_approved,
        "upsert_ready": False,
        "blocking_reasons": blocking_reasons,
        "runtime_write_attempted": False,
        "production_write_allowed": False,
        "score_mutation": "none",
        "required_next_evidence": [
            "review approval for the controlled batch plan hash",
            "runtime database backup at the declared backup path",
            "bounded UPSERT execution log and post-write score-field closure rerun",
        ],
    }


def build_report(
    *,
    approval_gate_path: Path,
    target_scope_path: Path,
    runtime_db_path: Path,
    batch_approvals_path: Path | None = None,
) -> dict[str, Any]:
    started = time.time()
    approval_gate = _load_json(approval_gate_path)
    target_scope = _load_json(target_scope_path)
    batch_approvals_payload = (
        _load_json(batch_approvals_path)
        if batch_approvals_path is not None and batch_approvals_path.exists()
        else {}
    )
    batch_approvals = _batch_approvals_by_dp_id(batch_approvals_payload)
    write_plan = _write_plan_by_dp_id(approval_gate)
    conn = sqlite3.connect(f"file:{runtime_db_path}?mode=ro", uri=True)
    try:
        schema = _schema_evidence(conn)
        rows = [
            _row_batch_plan(
                row,
                write_plan_by_dp_id=write_plan,
                conn=conn,
                schema=schema,
                batch_approvals_by_dp_id=batch_approvals,
            )
            for row in _approved_target_scope_rows(target_scope)
        ]
    finally:
        conn.close()
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    reason_counts: Counter[str] = Counter()
    for row in rows:
        reason_counts.update(str(reason) for reason in row["blocking_reasons"])
    valid_rows = [row for row in rows if row["batch_plan_contract_valid"]]
    plan_hashes = [row["batch_plan_sha256"] for row in valid_rows]
    batch_plan_set_payload = {
        "runtime_db_path": _portable_path(runtime_db_path),
        "target_scope_path": _portable_path(target_scope_path),
        "batch_plan_hashes": plan_hashes,
    }
    batch_set_sha256 = _canonical_hash(batch_plan_set_payload) if plan_hashes else None
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "approval_gate_path": _portable_path(approval_gate_path),
            "target_scope_path": _portable_path(target_scope_path),
            "runtime_db_path": _portable_path(runtime_db_path),
            "batch_approvals_path": _portable_path(batch_approvals_path)
            if batch_approvals_path is not None
            else None,
        },
        "runtime_schema": schema,
        "batch_plan_set": {
            "batch_plan_set_sha256": batch_set_sha256,
            "batch_plan_set_id": f"a-share-runtime-batch-{str(batch_set_sha256 or '')[:12]}"
            if batch_set_sha256
            else None,
            "batch_plan_hashes": plan_hashes,
            "approval_scope": "controlled_runtime_batch_plan",
            "production_write_allowed": False,
        },
        "summary": {
            "scope_approved_entry_count": len(rows),
            "batch_plan_entry_count": len(rows),
            "batch_plan_contract_valid_count": len(valid_rows),
            "batch_plan_contract_invalid_count": len(rows) - len(valid_rows),
            "batch_plan_review_required_count": sum(
                1 for row in rows if row["batch_plan_status"] == "review_required"
            ),
            "batch_plan_approved_count": sum(
                1 for row in rows if row["batch_plan_approved"]
            ),
            "planned_upsert_row_count": sum(
                int(row["planned_upsert_row_count"]) for row in rows
            ),
            "rows_to_insert_count": sum(int(row["rows_to_insert_count"]) for row in rows),
            "rows_to_update_count": sum(int(row["rows_to_update_count"]) for row in rows),
            "existing_rows_to_backup_count": sum(
                int(row["existing_rows_to_backup_count"]) for row in rows
            ),
            "existing_conflict_row_count": sum(
                int(row["existing_conflict_row_count"]) for row in rows
            ),
            "noop_existing_rows_count": sum(
                int(row["noop_existing_rows_count"]) for row in rows
            ),
            "backup_required_count": sum(1 for row in rows if row["backup_required"]),
            "upsert_ready_entry_count": 0,
            "blocked_entry_count": len(rows),
            "runtime_write_attempted_count": 0,
            "production_write_allowed_count": 0,
            "blocking_reason_counts": dict(sorted(reason_counts.items())),
            "score_mutation": "none; batch plan audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    batch_set = report.get("batch_plan_set") or {}
    lines = [
        "# A-share runtime write controlled batch plan",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Batch plan set: `{batch_set.get('batch_plan_set_id')}`",
        f"- Scope-approved entries: `{summary['scope_approved_entry_count']}`",
        f"- Batch-plan entries: `{summary['batch_plan_entry_count']}`",
        f"- Contract-valid batch plans: `{summary['batch_plan_contract_valid_count']}`",
        f"- Contract-invalid batch plans: `{summary['batch_plan_contract_invalid_count']}`",
        f"- Batch-plan review required: `{summary['batch_plan_review_required_count']}`",
        f"- Batch-plan approved: `{summary['batch_plan_approved_count']}`",
        f"- Planned UPSERT rows: `{summary['planned_upsert_row_count']}`",
        f"- Rows to insert: `{summary['rows_to_insert_count']}`",
        f"- Rows to update: `{summary['rows_to_update_count']}`",
        f"- Existing rows requiring backup: `{summary['existing_rows_to_backup_count']}`",
        f"- Runtime writes attempted: `{summary['runtime_write_attempted_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | status | target rows | inserts | updates | backup rows | plan hash | blockers |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in report["rows"]:
        blockers = ", ".join(row["blocking_reasons"]) or "none"
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['batch_plan_status']}` | "
            f"{row['planned_upsert_row_count']} | "
            f"{row['rows_to_insert_count']} | "
            f"{row['rows_to_update_count']} | "
            f"{row['existing_rows_to_backup_count']} | "
            f"`{str(row.get('batch_plan_sha256') or '')[:12]}` | "
            f"{blockers} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This is a review packet for a controlled batch write, not an UPSERT command.",
            "- A later write step must create the declared backup before changing runtime rows.",
            "- This audit creates no runtime rows and no production writes.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-gate-path", type=Path, default=DEFAULT_APPROVAL_GATE_PATH)
    parser.add_argument("--target-scope-path", type=Path, default=DEFAULT_TARGET_SCOPE_PATH)
    parser.add_argument("--runtime-db-path", type=Path, default=DEFAULT_RUNTIME_DB_PATH)
    parser.add_argument("--batch-approvals-path", type=Path, default=DEFAULT_BATCH_APPROVALS_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    args = parser.parse_args()

    report = build_report(
        approval_gate_path=args.approval_gate_path,
        target_scope_path=args.target_scope_path,
        runtime_db_path=args.runtime_db_path,
        batch_approvals_path=args.batch_approvals_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
