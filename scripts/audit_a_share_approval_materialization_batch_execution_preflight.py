#!/usr/bin/env python3
"""Preflight approved A-share formula materialization batch execution.

This is the final read-only gate before backup/execution. It validates that
the approved formula batch-plan hashes still match the current runtime DB state
and that every planned row can be inserted/updated exactly as approved. It does
not create a backup and does not mutate ``runtime/hot.sqlite``.
"""

from __future__ import annotations

import argparse
import datetime as dt
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

from mvp20.aggregator import _realtime_signal  # noqa: E402
from scripts.audit_a_share_approval_materialization_batch_plan import (  # noqa: E402
    DEFAULT_JSON_OUTPUT as DEFAULT_BATCH_PLAN_PATH,
)
from scripts.audit_a_share_approval_materialization_batch_approval_gate import (  # noqa: E402
    DEFAULT_JSON_OUTPUT as DEFAULT_APPROVAL_GATE_PATH,
)
from scripts.audit_a_share_approval_materialization_plan import _round  # noqa: E402
from scripts.audit_a_share_runtime_write_batch_plan import (  # noqa: E402
    REALTIME_PRIMARY_KEY,
    _canonical_hash,
    _canonical_value_json,
)
from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_RUNTIME_DB_PATH = ROOT / "runtime/hot.sqlite"
DEFAULT_BACKUP_DIR = ROOT / "runtime/backups"
DEFAULT_JSON_OUTPUT = (
    AUDIT_DIR
    / "a_share_approval_materialization_batch_execution_preflight_2026-06-20.json"
)
DEFAULT_MD_OUTPUT = (
    AUDIT_DIR
    / "a_share_approval_materialization_batch_execution_preflight_2026-06-20.md"
)


def _schema_errors(conn: sqlite3.Connection) -> list[str]:
    columns = conn.execute("pragma table_info(realtime_current)").fetchall()
    names = {str(row[1]) for row in columns}
    pk_columns = [
        str(row[1])
        for row in sorted(
            (row for row in columns if int(row[5] or 0) > 0),
            key=lambda row: int(row[5]),
        )
    ]
    required = {
        "ts_code",
        "dp_id",
        "value_json",
        "data_status",
        "confidence",
        "source",
        "updated_at",
    }
    errors: list[str] = []
    missing = sorted(required - names)
    if missing:
        errors.append(f"realtime_current_missing_columns:{','.join(missing)}")
    if pk_columns != REALTIME_PRIMARY_KEY:
        errors.append("realtime_current_primary_key_must_be_ts_code_dp_id")
    return errors


def _planned_rows_by_dp(payload: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in payload.get("planned_rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if not dp_id:
            continue
        grouped.setdefault(dp_id, []).append(dict(row))
    for rows in grouped.values():
        rows.sort(key=lambda item: str(item.get("ts_code") or ""))
    return grouped


def _gate_rows_by_dp(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = row
    return rows


def _fetch_existing_rows(
    conn: sqlite3.Connection,
    *,
    dp_id: str,
    ts_codes: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(ts_codes), 500):
        chunk = ts_codes[offset : offset + 500]
        if not chunk:
            continue
        placeholders = ",".join("?" for _ in chunk)
        sql = (
            "select ts_code, value_json, data_status, confidence, source, updated_at "
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
                    "updated_at": db_row[5],
                }
            )
    rows.sort(key=lambda item: str(item.get("ts_code") or ""))
    return rows


def _row_set_hash(planned_rows: list[Mapping[str, Any]]) -> str | None:
    if not planned_rows:
        return None
    return _canonical_hash(
        [
            {
                "ts_code": row.get("ts_code"),
                "dp_id": row.get("dp_id"),
                "value_json": row.get("value_json"),
                "data_status": row.get("data_status"),
                "confidence": row.get("confidence"),
                "source": row.get("source"),
            }
            for row in sorted(planned_rows, key=lambda item: str(item.get("ts_code") or ""))
        ]
    )


def _noop_existing_count(
    existing_rows: list[Mapping[str, Any]],
    planned_by_ts_code: Mapping[str, Mapping[str, Any]],
) -> int:
    count = 0
    for existing in existing_rows:
        ts_code = str(existing.get("ts_code") or "")
        planned = planned_by_ts_code.get(ts_code)
        if not planned:
            continue
        try:
            existing_value = _canonical_value_json(json.loads(str(existing["value_json"])))
        except (json.JSONDecodeError, TypeError):
            continue
        try:
            existing_confidence = float(existing.get("confidence"))
        except (TypeError, ValueError):
            continue
        if existing_value != _canonical_value_json(planned.get("value_json")):
            continue
        if existing.get("data_status") != planned.get("data_status"):
            continue
        if existing.get("source") != planned.get("source"):
            continue
        if existing_confidence != float(planned.get("confidence") or 0):
            continue
        count += 1
    return count


def _planned_row_errors(
    planned: Mapping[str, Any],
    *,
    dp_id: str,
    score_target: str,
) -> list[str]:
    errors: list[str] = []
    ts_code = str(planned.get("ts_code") or "")
    value_json = planned.get("value_json")
    value_json = value_json if isinstance(value_json, Mapping) else {}
    score = value_json.get("score")
    if planned.get("dp_id") != dp_id:
        errors.append(f"{ts_code}:planned_dp_id_must_match_row")
    if planned.get("score_target") != score_target:
        errors.append(f"{ts_code}:planned_score_target_must_match_row")
    if planned.get("data_status") != "Known":
        errors.append(f"{ts_code}:planned_data_status_must_be_known")
    if not isinstance(planned.get("confidence"), (int, float)) or isinstance(
        planned.get("confidence"), bool
    ):
        errors.append(f"{ts_code}:planned_confidence_must_be_numeric")
    elif not 0 <= float(planned.get("confidence") or 0) <= 1:
        errors.append(f"{ts_code}:planned_confidence_must_be_between_0_and_1")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        errors.append(f"{ts_code}:score_must_be_numeric")
        return errors
    if not -1 <= float(score) <= 1:
        errors.append(f"{ts_code}:score_must_be_in_unit_interval")
    bridge_signal = _realtime_signal(dp_id, dict(value_json), score_target, ts_code=ts_code)
    if bridge_signal is None:
        errors.append(f"{ts_code}:bridge_signal_must_be_present")
    elif _round(bridge_signal) != planned.get("bridge_signal"):
        errors.append(f"{ts_code}:bridge_signal_must_match_planned_value")
    return errors


def _row_validation(
    row: Mapping[str, Any],
    *,
    gate_row: Mapping[str, Any] | None,
    planned_rows: list[Mapping[str, Any]],
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    errors: list[str] = []
    dp_id = str(row.get("dp_id") or "")
    score_target = str(row.get("score_target") or "")
    payload = row.get("batch_plan_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    gate_row = gate_row if isinstance(gate_row, Mapping) else {}
    target_ts_codes = [str(item.get("ts_code") or "") for item in planned_rows]
    target_ts_codes_payload = [
        str(item) for item in payload.get("target_ts_codes") or [] if str(item).strip()
    ]

    if gate_row.get("approval_gate_status") != "approved_controlled_formula_batch_plan":
        errors.append("approval_gate_status_must_be_approved")
    if gate_row.get("runtime_write_allowed") is not True:
        errors.append("approval_gate_runtime_write_allowed_must_be_true")
    if gate_row.get("batch_plan_sha256") != row.get("batch_plan_sha256"):
        errors.append("approval_gate_batch_plan_hash_must_match_row")
    if row.get("batch_plan_contract_valid") is not True:
        errors.append("batch_plan_contract_must_be_valid")
    if row.get("batch_plan_status") != "review_required":
        errors.append("batch_plan_status_must_be_review_required")
    if row.get("batch_plan_approved") is not False:
        errors.append("batch_plan_source_row_must_remain_unexecuted")
    if row.get("runtime_write_attempted") is not False:
        errors.append("runtime_write_attempted_must_be_false")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_allowed_must_be_false")
    if payload.get("operation") != "upsert_realtime_current":
        errors.append("operation_must_be_upsert_realtime_current")
    if payload.get("primary_key") != REALTIME_PRIMARY_KEY:
        errors.append("primary_key_must_match_realtime_current")
    if payload.get("dp_id") != dp_id:
        errors.append("payload_dp_id_must_match_row")
    if payload.get("score_target") != score_target:
        errors.append("payload_score_target_must_match_row")
    if payload.get("planned_row_set_sha256") != row.get("planned_row_set_sha256"):
        errors.append("payload_row_set_hash_must_match_row")
    if row.get("batch_plan_sha256") != _canonical_hash(payload):
        errors.append("batch_plan_sha256_must_match_payload")
    if payload.get("conflict_policy") != "upsert_on_primary_key_after_backup":
        errors.append("conflict_policy_must_require_backup")
    if not str(payload.get("rollback_policy") or "").strip():
        errors.append("rollback_policy_must_be_present")

    planned_count = int(row.get("planned_upsert_row_count") or 0)
    rows_to_insert = int(row.get("rows_to_insert_count") or 0)
    rows_to_update = int(row.get("rows_to_update_count") or 0)
    rows_to_backup = int(row.get("existing_rows_to_backup_count") or 0)
    expected_noop = int(row.get("noop_existing_rows_count") or 0)
    if len(planned_rows) != planned_count:
        errors.append("planned_rows_count_must_match_batch_plan")
    if len(set(target_ts_codes)) != len(target_ts_codes):
        errors.append("planned_rows_must_have_unique_target_keys")
    if set(target_ts_codes_payload) != set(target_ts_codes):
        errors.append("payload_target_ts_codes_must_match_planned_rows")
    if _row_set_hash(planned_rows) != row.get("planned_row_set_sha256"):
        errors.append("planned_row_set_sha256_must_match_planned_rows")

    for planned in planned_rows:
        errors.extend(
            _planned_row_errors(planned, dp_id=dp_id, score_target=score_target)
        )

    existing_rows = _fetch_existing_rows(conn, dp_id=dp_id, ts_codes=target_ts_codes)
    planned_by_ts = {str(item.get("ts_code") or ""): item for item in planned_rows}
    current_existing = len(existing_rows)
    current_noop = _noop_existing_count(existing_rows, planned_by_ts)
    current_update = current_existing - current_noop
    current_insert = len(target_ts_codes) - current_existing
    if current_existing != rows_to_backup:
        errors.append("current_existing_row_count_must_equal_backup_count")
    if current_noop != expected_noop:
        errors.append("current_noop_row_count_must_equal_plan_noop_count")
    if current_update != rows_to_update:
        errors.append("current_update_count_must_equal_rows_to_update_count")
    if current_insert != rows_to_insert:
        errors.append("current_insert_count_must_equal_rows_to_insert_count")

    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "batch_plan_sha256": row.get("batch_plan_sha256"),
        "planned_row_set_sha256": row.get("planned_row_set_sha256"),
        "validation_errors": sorted(set(errors)),
        "target_ts_code_count": len(target_ts_codes),
        "target_ts_codes_sample": target_ts_codes[:10],
        "planned_upsert_row_count": planned_count,
        "rows_to_insert_count": rows_to_insert,
        "rows_to_update_count": rows_to_update,
        "existing_rows_to_backup_count": rows_to_backup,
        "current_existing_row_count": current_existing,
        "current_noop_row_count": current_noop,
        "current_update_row_count": current_update,
        "current_insert_row_count": current_insert,
    }


def build_report(
    *,
    batch_plan_path: Path,
    approval_gate_path: Path,
    runtime_db_path: Path,
    backup_dir: Path,
) -> dict[str, Any]:
    started = time.time()
    batch_plan = _load_json(batch_plan_path)
    approval_gate = _load_json(approval_gate_path)
    planned_by_dp = _planned_rows_by_dp(batch_plan)
    gate_by_dp = _gate_rows_by_dp(approval_gate)
    batch_rows = [row for row in batch_plan.get("rows") or [] if isinstance(row, Mapping)]
    approved_rows = [
        row
        for row in batch_rows
        if gate_by_dp.get(str(row.get("dp_id") or ""), {}).get("approval_gate_status")
        == "approved_controlled_formula_batch_plan"
    ]
    with sqlite3.connect(f"file:{runtime_db_path}?mode=ro", uri=True) as conn:
        schema_errors = _schema_errors(conn)
        validation_rows = [
            _row_validation(
                row,
                gate_row=gate_by_dp.get(str(row.get("dp_id") or "")),
                planned_rows=planned_by_dp.get(str(row.get("dp_id") or ""), []),
                conn=conn,
            )
            for row in approved_rows
        ]
    for row in validation_rows:
        row["validation_errors"] = sorted(set([*schema_errors, *row["validation_errors"]]))
        row["preflight_status"] = (
            "dry_run_ready" if not row["validation_errors"] else "blocked"
        )
        row["backup_required"] = row["preflight_status"] == "dry_run_ready"
        row["backup_path_template"] = (
            f"{_portable_path(backup_dir)}/hot.sqlite.before_a_share_formula_batch_"
            f"{str(row.get('batch_plan_sha256') or '')[:12]}.sqlite"
            if row["backup_required"]
            else None
        )
        row["runtime_rows_would_write"] = (
            row["planned_upsert_row_count"]
            if row["preflight_status"] == "dry_run_ready"
            else 0
        )
        row["runtime_write_attempted"] = False
        row["production_write_allowed"] = False
    ready_rows = [row for row in validation_rows if row["preflight_status"] == "dry_run_ready"]
    reason_counts: Counter[str] = Counter()
    for row in validation_rows:
        reason_counts.update(str(error) for error in row["validation_errors"])
    execution_status = (
        "dry_run_ready"
        if validation_rows and len(ready_rows) == len(validation_rows)
        else "blocked"
    )
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "batch_plan_path": _portable_path(batch_plan_path),
            "approval_gate_path": _portable_path(approval_gate_path),
            "runtime_db_path": _portable_path(runtime_db_path),
            "backup_dir": _portable_path(backup_dir),
        },
        "batch_plan_set": batch_plan.get("batch_plan_set") or {},
        "summary": {
            "execution_status": execution_status,
            "batch_plan_entry_count": len(batch_rows),
            "approved_batch_plan_count": len(approved_rows),
            "preflight_checked_count": len(validation_rows),
            "preflight_ready_count": len(ready_rows),
            "preflight_blocked_count": len(validation_rows) - len(ready_rows),
            "planned_upsert_row_count": sum(
                int(row["planned_upsert_row_count"]) for row in validation_rows
            ),
            "runtime_rows_would_write_count": sum(
                int(row["runtime_rows_would_write"]) for row in ready_rows
            ),
            "rows_to_insert_count": sum(int(row["rows_to_insert_count"]) for row in ready_rows),
            "rows_to_update_count": sum(int(row["rows_to_update_count"]) for row in ready_rows),
            "existing_rows_to_backup_count": sum(
                int(row["existing_rows_to_backup_count"]) for row in ready_rows
            ),
            "runtime_backup_required_count": len(ready_rows),
            "runtime_backup_created_count": 0,
            "runtime_write_attempted_count": 0,
            "runtime_write_completed_count": 0,
            "post_write_verified_row_count": 0,
            "production_write_allowed_count": 0,
            "blocking_reason_counts": dict(sorted(reason_counts.items())),
            "score_mutation": "none; execution preflight is read-only and does not alter realtime_current",
        },
        "rows": validation_rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share formula materialization batch execution preflight",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Execution status: `{summary['execution_status']}`",
        f"- Approved batch plans: `{summary['approved_batch_plan_count']}`",
        f"- Preflight ready: `{summary['preflight_ready_count']}`",
        f"- Preflight blocked: `{summary['preflight_blocked_count']}`",
        f"- Runtime rows would write: `{summary['runtime_rows_would_write_count']}`",
        f"- Runtime backups created: `{summary['runtime_backup_created_count']}`",
        f"- Runtime writes attempted: `{summary['runtime_write_attempted_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | status | planned rows | inserts | updates | backup rows | would write | blockers |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report.get("rows") or []:
        blockers = ", ".join(row.get("validation_errors") or []) or "none"
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['preflight_status']}` | "
            f"{row['planned_upsert_row_count']} | "
            f"{row['rows_to_insert_count']} | "
            f"{row['rows_to_update_count']} | "
            f"{row['existing_rows_to_backup_count']} | "
            f"{row['runtime_rows_would_write']} | "
            f"{blockers} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `dry_run_ready` means approved formula plans still match the current runtime DB.",
            "- This preflight does not create a backup and does not execute UPSERTs.",
            "- The next step is an explicit backup plus bounded runtime UPSERT execution.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-plan-path", type=Path, default=DEFAULT_BATCH_PLAN_PATH)
    parser.add_argument("--approval-gate-path", type=Path, default=DEFAULT_APPROVAL_GATE_PATH)
    parser.add_argument("--runtime-db-path", type=Path, default=DEFAULT_RUNTIME_DB_PATH)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        batch_plan_path=args.batch_plan_path,
        approval_gate_path=args.approval_gate_path,
        runtime_db_path=args.runtime_db_path,
        backup_dir=args.backup_dir,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
