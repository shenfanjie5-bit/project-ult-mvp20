#!/usr/bin/env python3
"""Execute approved A-share runtime batch plans with backup evidence.

The batch-plan audit is intentionally read-only. This script is the bounded
write step: it validates the approved plan hashes against the current
``realtime_current`` primary keys, creates a SQLite backup snapshot, then runs
the planned UPSERT inside a single transaction. By default it dry-runs; pass
``--execute`` to mutate the runtime database.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_runtime_write_batch_plan import (  # noqa: E402
    REALTIME_PRIMARY_KEY,
)
from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_BATCH_PLAN_PATH = (
    ROOT / "docs/audit/a_share_runtime_write_batch_plan_2026-06-19.json"
)
DEFAULT_RUNTIME_DB_PATH = ROOT / "runtime/hot.sqlite"
DEFAULT_BACKUP_DIR = ROOT / "runtime/backups"
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_runtime_write_execution_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_runtime_write_execution_2026-06-19.md"
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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _chunked(values: list[str], size: int = CHUNK_SIZE) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _approved_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in report.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        if (
            row.get("batch_plan_contract_valid") is True
            and row.get("batch_plan_approved") is True
        ):
            rows.append(dict(row))
    rows.sort(key=lambda item: str(item.get("dp_id") or ""))
    return rows


def _fetch_existing_rows(
    conn: sqlite3.Connection,
    *,
    dp_id: str,
    ts_codes: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk in _chunked(ts_codes):
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
    rows.sort(key=lambda item: str(item["ts_code"]))
    return rows


def _count_matching_rows(
    conn: sqlite3.Connection,
    *,
    dp_id: str,
    ts_codes: list[str],
    value_json: Any,
    data_status: str,
    confidence: float,
    source: str,
) -> int:
    expected_value = _canonical_value_json(value_json)
    matches = 0
    for row in _fetch_existing_rows(conn, dp_id=dp_id, ts_codes=ts_codes):
        try:
            actual_value = _canonical_value_json(json.loads(str(row["value_json"])))
        except (json.JSONDecodeError, TypeError):
            continue
        if actual_value != expected_value:
            continue
        if row["data_status"] != data_status or row["source"] != source:
            continue
        try:
            row_confidence = float(row["confidence"])
        except (TypeError, ValueError):
            continue
        if row_confidence == float(confidence):
            matches += 1
    return matches


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


def _row_validation(
    row: Mapping[str, Any],
    *,
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    errors: list[str] = []
    dp_id = str(row.get("dp_id") or "")
    plan = row.get("batch_plan_payload")
    if row.get("batch_plan_status") != "batch_plan_approved_backup_required":
        errors.append("batch_plan_status_must_be_approved_backup_required")
    if row.get("batch_plan_contract_valid") is not True:
        errors.append("batch_plan_contract_must_be_valid")
    if row.get("batch_plan_approved") is not True:
        errors.append("batch_plan_must_be_approved")
    if row.get("runtime_write_attempted") is not False:
        errors.append("batch_plan_must_not_already_attempt_runtime_write")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_must_remain_false")
    if not isinstance(plan, Mapping):
        errors.append("batch_plan_payload_must_be_object")
        plan = {}
    if plan.get("operation") != "upsert_realtime_current":
        errors.append("operation_must_be_upsert_realtime_current")
    if plan.get("primary_key") != REALTIME_PRIMARY_KEY:
        errors.append("primary_key_must_be_ts_code_dp_id")
    if plan.get("dp_id") != dp_id:
        errors.append("batch_plan_payload_dp_id_must_match_row")
    if plan.get("payload_sha256") != row.get("payload_sha256"):
        errors.append("payload_sha256_must_match_batch_plan_payload")
    if plan.get("target_scope_sha256") != row.get("target_scope_sha256"):
        errors.append("target_scope_sha256_must_match_batch_plan_payload")

    ts_codes_raw = plan.get("target_ts_codes")
    target_ts_codes = [str(item) for item in ts_codes_raw or [] if str(item).strip()]
    if not isinstance(ts_codes_raw, list) or not target_ts_codes:
        errors.append("target_ts_codes_must_be_non_empty_list")
    if len(set(target_ts_codes)) != len(target_ts_codes):
        errors.append("target_ts_codes_must_be_unique")
    planned_count = int(row.get("planned_upsert_row_count") or 0)
    if len(target_ts_codes) != planned_count:
        errors.append("target_ts_code_count_must_equal_planned_upsert_row_count")

    template = plan.get("row_template")
    if not isinstance(template, Mapping):
        errors.append("row_template_must_be_object")
        template = {}
    value_json = template.get("value_json")
    data_status = str(template.get("data_status") or "")
    confidence = template.get("confidence")
    source = str(template.get("source") or "")
    if not isinstance(value_json, Mapping):
        errors.append("row_template_value_json_must_be_object")
    if data_status not in {"Known", "NotApplicable"}:
        errors.append("row_template_data_status_must_be_known_or_not_applicable")
    if not isinstance(confidence, (int, float)):
        errors.append("row_template_confidence_must_be_numeric")
    if not source:
        errors.append("row_template_source_must_be_non_empty")
    if template.get("value_json_sha256") != _canonical_hash(value_json):
        errors.append("row_template_value_json_sha256_must_match")
    if row.get("batch_plan_sha256") != _canonical_hash(plan):
        errors.append("batch_plan_sha256_must_match_canonical_payload")

    existing_rows = (
        _fetch_existing_rows(conn, dp_id=dp_id, ts_codes=target_ts_codes)
        if target_ts_codes and not errors
        else []
    )
    existing_count = len(existing_rows)
    expected_updates = int(row.get("rows_to_update_count") or 0)
    expected_backup = int(row.get("existing_rows_to_backup_count") or 0)
    expected_inserts = int(row.get("rows_to_insert_count") or 0)
    if existing_count != expected_updates:
        errors.append("current_existing_row_count_must_equal_rows_to_update_count")
    if existing_count != expected_backup:
        errors.append("current_existing_row_count_must_equal_backup_count")
    if len(target_ts_codes) - existing_count != expected_inserts:
        errors.append("current_insert_count_must_equal_rows_to_insert_count")

    return {
        "dp_id": dp_id,
        "batch_plan_sha256": row.get("batch_plan_sha256"),
        "target_ts_codes": target_ts_codes,
        "row_template": {
            "value_json": value_json,
            "data_status": data_status,
            "confidence": float(confidence) if isinstance(confidence, (int, float)) else None,
            "source": source,
        },
        "existing_rows": existing_rows,
        "validation_errors": errors,
        "planned_upsert_row_count": planned_count,
        "rows_to_insert_count": expected_inserts,
        "rows_to_update_count": expected_updates,
        "existing_rows_to_backup_count": expected_backup,
    }


def _create_backup(
    *,
    runtime_db_path: Path,
    backup_dir: Path,
    batch_plan_set_id: str,
) -> tuple[Path, str]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%d%H%M%S")
    safe_set_id = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in batch_plan_set_id
    )
    backup_path = backup_dir / f"hot.sqlite.before_{safe_set_id}_{timestamp}.sqlite"
    with sqlite3.connect(str(runtime_db_path)) as source:
        with sqlite3.connect(str(backup_path)) as dest:
            source.backup(dest)
            quick_check = dest.execute("pragma quick_check").fetchone()[0]
    shutil.copystat(runtime_db_path, backup_path)
    return backup_path, str(quick_check)


def _execute_upserts(
    *,
    runtime_db_path: Path,
    validations: list[Mapping[str, Any]],
    updated_at: int,
) -> int:
    rows: list[tuple[str, str, str, str, float | None, str, int]] = []
    for item in validations:
        template = item["row_template"]
        for ts_code in item["target_ts_codes"]:
            rows.append(
                (
                    ts_code,
                    str(item["dp_id"]),
                    _canonical_value_json(template["value_json"]),
                    str(template["data_status"]),
                    template["confidence"],
                    str(template["source"]),
                    updated_at,
                )
            )
    if not rows:
        return 0
    with sqlite3.connect(str(runtime_db_path), isolation_level=None) as conn:
        conn.execute("begin immediate")
        try:
            conn.executemany(
                """
                insert into realtime_current
                    (ts_code, dp_id, value_json, data_status, confidence, source, updated_at)
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict (ts_code, dp_id) do update set
                    value_json = excluded.value_json,
                    data_status = excluded.data_status,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    return len(rows)


def build_report(
    *,
    batch_plan_path: Path,
    runtime_db_path: Path,
    backup_dir: Path,
    execute: bool = False,
) -> dict[str, Any]:
    started = time.time()
    batch_plan = _load_json(batch_plan_path)
    batch_set = batch_plan.get("batch_plan_set") or {}
    batch_plan_set_id = str(batch_set.get("batch_plan_set_id") or "a-share-runtime-batch")
    batch_plan_set_sha256 = batch_set.get("batch_plan_set_sha256")
    approved_rows = _approved_rows(batch_plan)
    validation_rows: list[dict[str, Any]]
    schema_validation_errors: list[str]
    with sqlite3.connect(f"file:{runtime_db_path}?mode=ro", uri=True) as conn:
        schema_validation_errors = _schema_errors(conn)
        validation_rows = [
            _row_validation(row, conn=conn)
            for row in approved_rows
        ]
    for item in validation_rows:
        item["validation_errors"] = [
            *schema_validation_errors,
            *item["validation_errors"],
        ]
    ready_rows = [row for row in validation_rows if not row["validation_errors"]]
    reason_counts: Counter[str] = Counter()
    for row in validation_rows:
        reason_counts.update(str(error) for error in row["validation_errors"])

    execution_status = (
        "dry_run_ready" if len(ready_rows) == len(validation_rows) else "blocked"
    )
    backup_path: Path | None = None
    backup_quick_check: str | None = None
    runtime_rows_written = 0
    updated_at: int | None = None
    backup_sha256: str | None = None
    backup_size_bytes: int | None = None
    if execute and execution_status == "dry_run_ready" and ready_rows:
        backup_path, backup_quick_check = _create_backup(
            runtime_db_path=runtime_db_path,
            backup_dir=backup_dir,
            batch_plan_set_id=batch_plan_set_id,
        )
        backup_sha256 = _file_sha256(backup_path)
        backup_size_bytes = backup_path.stat().st_size
        updated_at = int(time.time())
        runtime_rows_written = _execute_upserts(
            runtime_db_path=runtime_db_path,
            validations=ready_rows,
            updated_at=updated_at,
        )
        execution_status = "executed"
    elif execute and not ready_rows:
        execution_status = "blocked"

    post_errors: list[str] = []
    post_match_counts_by_dp_id: dict[str, int] = {}
    post_verified_count = 0
    post_write_verified_row_count = 0
    if execution_status == "executed":
        with sqlite3.connect(f"file:{runtime_db_path}?mode=ro", uri=True) as conn:
            for row in ready_rows:
                template = row["row_template"]
                match_count = _count_matching_rows(
                    conn,
                    dp_id=str(row["dp_id"]),
                    ts_codes=list(row["target_ts_codes"]),
                    value_json=template["value_json"],
                    data_status=str(template["data_status"]),
                    confidence=float(template["confidence"]),
                    source=str(template["source"]),
                )
                post_match_counts_by_dp_id[str(row["dp_id"])] = match_count
                if match_count == int(row["planned_upsert_row_count"]):
                    post_verified_count += 1
                    post_write_verified_row_count += match_count
                else:
                    post_errors.append(
                        f"{row['dp_id']}:post_write_match_count:{match_count}"
                    )

    rows: list[dict[str, Any]] = []
    for row in validation_rows:
        status = (
            "executed"
            if execution_status == "executed" and not row["validation_errors"]
            else "dry_run_ready"
            if execution_status == "dry_run_ready" and not row["validation_errors"]
            else "blocked"
        )
        rows.append(
            {
                "dp_id": row["dp_id"],
                "payload_sha256": next(
                    (
                        original.get("payload_sha256")
                        for original in approved_rows
                        if original.get("dp_id") == row["dp_id"]
                    ),
                    None,
                ),
                "target_scope_sha256": next(
                    (
                        original.get("target_scope_sha256")
                        for original in approved_rows
                        if original.get("dp_id") == row["dp_id"]
                    ),
                    None,
                ),
                "batch_plan_sha256": row["batch_plan_sha256"],
                "batch_plan_set_sha256": batch_plan_set_sha256,
                "execution_status": status,
                "validation_errors": row["validation_errors"],
                "target_ts_code_count": len(row["target_ts_codes"]),
                "target_ts_codes_sample": row["target_ts_codes"][:10],
                "planned_upsert_row_count": row["planned_upsert_row_count"],
                "rows_to_insert_count": row["rows_to_insert_count"],
                "rows_to_update_count": row["rows_to_update_count"],
                "existing_rows_to_backup_count": row["existing_rows_to_backup_count"],
                "backup_required": status in {"executed", "dry_run_ready"},
                "backup_completed": backup_path is not None and status == "executed",
                "runtime_rows_written": row["planned_upsert_row_count"]
                if status == "executed"
                else 0,
                "backup_path": _portable_path(backup_path) if backup_path else None,
                "backup_sha256": backup_sha256,
                "backup_size_bytes": backup_size_bytes,
                "updated_at": updated_at,
                "runtime_write_completed": status == "executed",
                "upserted_row_count": row["planned_upsert_row_count"]
                if status == "executed"
                else 0,
                "post_write_verified_row_count": post_match_counts_by_dp_id.get(
                    str(row["dp_id"]), 0
                ),
                "post_write_verified": status == "executed"
                and not any(
                    str(error).startswith(f"{row['dp_id']}:") for error in post_errors
                ),
                "runtime_write_attempted": status == "executed",
                "production_write_allowed": False,
                "rollback_strategy": (
                    "restore from backup snapshot or replay affected pre-write rows; "
                    "delete affected primary keys absent from the backup snapshot"
                )
                if backup_path
                else None,
            }
        )

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "batch_plan_path": _portable_path(batch_plan_path),
            "runtime_db_path": _portable_path(runtime_db_path),
            "backup_dir": _portable_path(backup_dir),
            "execute": execute,
        },
        "batch_plan_set": batch_set,
        "backup": {
            "backup_created": backup_path is not None,
            "backup_path": _portable_path(backup_path) if backup_path else None,
            "backup_quick_check": backup_quick_check,
            "backup_sha256": backup_sha256,
            "backup_size_bytes": backup_size_bytes,
        },
        "summary": {
            "execution_status": execution_status,
            "batch_plan_entry_count": len(batch_plan.get("rows") or []),
            "approved_batch_plan_count": len(approved_rows),
            "approved_controlled_batch_plan_count": len(approved_rows),
            "execution_ready_count": len(ready_rows),
            "execution_blocked_count": len(validation_rows) - len(ready_rows),
            "planned_upsert_row_count": sum(
                int(row["planned_upsert_row_count"]) for row in validation_rows
            ),
            "backup_required_count": len(ready_rows),
            "runtime_backup_created_count": 1 if backup_path else 0,
            "backup_completed_count": len(ready_rows) if backup_path else 0,
            "backup_failed_count": 0,
            "runtime_write_attempted_count": len(ready_rows)
            if execution_status == "executed"
            else 0,
            "runtime_write_completed_count": len(ready_rows)
            if execution_status == "executed"
            else 0,
            "runtime_write_failed_count": 0,
            "runtime_rows_written_count": runtime_rows_written,
            "upserted_row_count": runtime_rows_written,
            "rows_inserted_count": sum(int(row["rows_to_insert_count"]) for row in ready_rows)
            if execution_status == "executed"
            else 0,
            "rows_updated_count": sum(int(row["rows_to_update_count"]) for row in ready_rows)
            if execution_status == "executed"
            else 0,
            "existing_rows_backed_up_count": sum(
                int(row["existing_rows_to_backup_count"]) for row in ready_rows
            )
            if backup_path
            else 0,
            "post_write_verified_count": post_verified_count,
            "post_write_verified_row_count": post_write_verified_row_count,
            "post_write_verification_error_count": len(post_errors),
            "production_write_allowed_count": 0,
            "blocking_reason_counts": dict(sorted(reason_counts.items())),
            "score_mutation": (
                "runtime write executed; realtime_current was mutated with approved neutral A-share rows"
                if execution_status == "executed"
                else "none; dry-run or blocked execution did not alter realtime_current"
            ),
        },
        "post_write_errors": post_errors,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    backup = report.get("backup") or {}
    lines = [
        "# A-share runtime write execution",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Execution status: `{summary['execution_status']}`",
        f"- Approved batch plans: `{summary['approved_batch_plan_count']}`",
        f"- Execution-ready rows: `{summary['execution_ready_count']}`",
        f"- Execution-blocked rows: `{summary['execution_blocked_count']}`",
        f"- Backup created: `{backup.get('backup_created')}`",
        f"- Backup path: `{backup.get('backup_path')}`",
        f"- Backup quick_check: `{backup.get('backup_quick_check')}`",
        f"- Runtime write attempts: `{summary['runtime_write_attempted_count']}`",
        f"- Runtime write completions: `{summary['runtime_write_completed_count']}`",
        f"- Runtime rows written: `{summary['runtime_rows_written_count']}`",
        f"- Rows inserted: `{summary['rows_inserted_count']}`",
        f"- Rows updated: `{summary['rows_updated_count']}`",
        f"- Post-write verified rows: `{summary['post_write_verified_count']}`",
        f"- Post-write verification errors: `{summary['post_write_verification_error_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | status | target rows | inserts | updates | backup rows | written | plan hash |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['execution_status']}` | "
            f"{row['planned_upsert_row_count']} | "
            f"{row['rows_to_insert_count']} | "
            f"{row['rows_to_update_count']} | "
            f"{row['existing_rows_to_backup_count']} | "
            f"{row['runtime_rows_written']} | "
            f"`{str(row.get('batch_plan_sha256') or '')[:12]}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `dry_run_ready` means all safety checks passed but no DB mutation occurred.",
            "- `executed` means a SQLite backup was created before the bounded UPSERT.",
            "- `production_write_allowed_count` remains zero; this writes only the local runtime DB.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-plan-path", type=Path, default=DEFAULT_BATCH_PLAN_PATH)
    parser.add_argument("--runtime-db-path", type=Path, default=DEFAULT_RUNTIME_DB_PATH)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="create a backup and mutate runtime/hot.sqlite after validation",
    )
    args = parser.parse_args()

    report = build_report(
        batch_plan_path=args.batch_plan_path,
        runtime_db_path=args.runtime_db_path,
        backup_dir=args.backup_dir,
        execute=args.execute,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
