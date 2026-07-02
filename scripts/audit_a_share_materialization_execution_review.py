#!/usr/bin/env python3
"""Review a completed A-share materialization execution against backup/current DB.

This is a read-only post-execution audit. It does not rerun the execution
preflight, because the preflight is intentionally first-run state-sensitive.
Instead it compares the recorded backup, the approved batch plan, and the
current runtime DB to verify value contracts and expose timestamp-only no-op
side effects from the completed execution.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_approval_materialization_batch_plan import (  # noqa: E402
    DEFAULT_JSON_OUTPUT as DEFAULT_BATCH_PLAN_PATH,
)
from scripts.audit_a_share_approval_materialization_batch_execution_preflight import (  # noqa: E402
    DEFAULT_RUNTIME_DB_PATH,
)
from scripts.audit_a_share_runtime_write_batch_plan import _canonical_value_json  # noqa: E402
from scripts.audit_a_share_unknown_acquisition_backlog import ROOT, _portable_path  # noqa: E402


AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_EXECUTION_PATH = (
    AUDIT_DIR / "a_share_approval_materialization_batch_execution_2026-06-20.json"
)
DEFAULT_JSON_OUTPUT = AUDIT_DIR / "a_share_materialization_execution_review_2026-06-20.json"
DEFAULT_MD_OUTPUT = AUDIT_DIR / "a_share_materialization_execution_review_2026-06-20.md"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _planned_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        row
        for row in payload.get("planned_rows") or []
        if isinstance(row, Mapping) and row.get("ts_code") and row.get("dp_id")
    ]


def _fetch_row(conn: sqlite3.Connection, ts_code: str, dp_id: str) -> Mapping[str, Any] | None:
    row = conn.execute(
        """
        select value_json, data_status, confidence, source, updated_at
        from realtime_current where ts_code = ? and dp_id = ?
        """,
        (ts_code, dp_id),
    ).fetchone()
    if row is None:
        return None
    return {
        "value_json": row[0],
        "data_status": row[1],
        "confidence": row[2],
        "source": row[3],
        "updated_at": row[4],
    }


def _matches_plan(db_row: Mapping[str, Any] | None, planned: Mapping[str, Any]) -> bool:
    if db_row is None:
        return False
    try:
        db_value = _canonical_value_json(json.loads(str(db_row.get("value_json"))))
    except (json.JSONDecodeError, TypeError):
        return False
    return (
        db_value == _canonical_value_json(planned.get("value_json") or {})
        and db_row.get("data_status") == planned.get("data_status")
        and db_row.get("source") == planned.get("source")
        and float(db_row.get("confidence") or 0) == float(planned.get("confidence") or 0)
    )


def build_report(
    *,
    execution_path: Path,
    batch_plan_path: Path,
    runtime_db_path: Path,
) -> dict[str, Any]:
    execution = _load_json(execution_path)
    batch_plan = _load_json(batch_plan_path)
    backup_path = Path(str((execution.get("backup") or {}).get("backup_path") or ""))
    if not backup_path.is_absolute():
        backup_path = ROOT / backup_path
    rows = _planned_rows(batch_plan)
    value_contract_errors: list[str] = []
    missing_current_count = 0
    inserted_since_backup_count = 0
    existing_compared_count = 0
    existing_value_unchanged_count = 0
    existing_value_changed_count = 0
    noop_updated_at_changed_count = 0
    noop_updated_at_preserved_count = 0
    samples: list[dict[str, Any]] = []

    with sqlite3.connect(f"file:{runtime_db_path}?mode=ro", uri=True) as current:
        with sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True) as backup:
            for planned in rows:
                ts_code = str(planned.get("ts_code") or "")
                dp_id = str(planned.get("dp_id") or "")
                current_row = _fetch_row(current, ts_code, dp_id)
                backup_row = _fetch_row(backup, ts_code, dp_id)
                if current_row is None:
                    missing_current_count += 1
                    value_contract_errors.append(f"{ts_code}:{dp_id}:missing_current")
                    continue
                if not _matches_plan(current_row, planned):
                    value_contract_errors.append(f"{ts_code}:{dp_id}:current_contract_mismatch")
                if backup_row is None:
                    inserted_since_backup_count += 1
                    continue
                existing_compared_count += 1
                if _matches_plan(backup_row, planned):
                    existing_value_unchanged_count += 1
                    if backup_row.get("updated_at") == current_row.get("updated_at"):
                        noop_updated_at_preserved_count += 1
                    else:
                        noop_updated_at_changed_count += 1
                        if len(samples) < 5:
                            samples.append(
                                {
                                    "ts_code": ts_code,
                                    "dp_id": dp_id,
                                    "backup_updated_at": backup_row.get("updated_at"),
                                    "current_updated_at": current_row.get("updated_at"),
                                }
                            )
                else:
                    existing_value_changed_count += 1

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "execution_path": _portable_path(execution_path),
            "batch_plan_path": _portable_path(batch_plan_path),
            "runtime_db_path": _portable_path(runtime_db_path),
            "backup_path": _portable_path(backup_path),
        },
        "summary": {
            "planned_row_count": len(rows),
            "current_value_contract_error_count": len(value_contract_errors),
            "missing_current_count": missing_current_count,
            "inserted_since_backup_count": inserted_since_backup_count,
            "existing_compared_count": existing_compared_count,
            "existing_value_unchanged_count": existing_value_unchanged_count,
            "existing_value_changed_count": existing_value_changed_count,
            "noop_updated_at_preserved_count": noop_updated_at_preserved_count,
            "noop_updated_at_changed_count": noop_updated_at_changed_count,
            "score_mutation": "none; post-execution review is read-only",
        },
        "value_contract_errors": value_contract_errors[:100],
        "noop_updated_at_changed_samples": samples,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share materialization execution review",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Planned rows: `{summary['planned_row_count']}`",
        f"- Current value contract errors: `{summary['current_value_contract_error_count']}`",
        f"- Inserted since backup: `{summary['inserted_since_backup_count']}`",
        f"- Existing compared: `{summary['existing_compared_count']}`",
        f"- Existing value unchanged: `{summary['existing_value_unchanged_count']}`",
        f"- Existing value changed: `{summary['existing_value_changed_count']}`",
        f"- No-op updated_at preserved: `{summary['noop_updated_at_preserved_count']}`",
        f"- No-op updated_at changed: `{summary['noop_updated_at_changed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Timestamp-only No-op Drift Samples",
        "",
        "| ts_code | dp_id | backup_updated_at | current_updated_at |",
        "|---|---|---:|---:|",
    ]
    for row in report.get("noop_updated_at_changed_samples") or []:
        lines.append(
            "| "
            f"`{row['ts_code']}` | "
            f"`{row['dp_id']}` | "
            f"{row['backup_updated_at']} | "
            f"{row['current_updated_at']} |"
        )
    if not report.get("noop_updated_at_changed_samples"):
        lines.append("| none | none | 0 | 0 |")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-path", type=Path, default=DEFAULT_EXECUTION_PATH)
    parser.add_argument("--batch-plan-path", type=Path, default=DEFAULT_BATCH_PLAN_PATH)
    parser.add_argument("--runtime-db-path", type=Path, default=DEFAULT_RUNTIME_DB_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        execution_path=args.execution_path,
        batch_plan_path=args.batch_plan_path,
        runtime_db_path=args.runtime_db_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
