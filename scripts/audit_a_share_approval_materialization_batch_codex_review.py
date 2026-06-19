#!/usr/bin/env python3
"""Codex review for A-share formula materialization batch approvals.

The batch-plan audit creates controlled formula UPSERT plans. This script
performs an independent deterministic review of those plans and emits approval
records only for rows whose hashes, formula output rows, bridge signals, and
backup/write contracts all validate. It does not mutate ``runtime/hot.sqlite``.
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

from mvp20.aggregator import _realtime_signal  # noqa: E402
from scripts.audit_a_share_approval_materialization_batch_plan import (  # noqa: E402
    DEFAULT_JSON_OUTPUT as DEFAULT_BATCH_PLAN_PATH,
    PLAN_READY_CLASSES,
)
from scripts.audit_a_share_approval_materialization_batch_approval_gate import (  # noqa: E402
    APPROVAL_SCOPE,
)
from scripts.audit_a_share_approval_materialization_plan import _round  # noqa: E402
from scripts.audit_a_share_runtime_write_batch_plan import (  # noqa: E402
    REALTIME_PRIMARY_KEY,
    _canonical_hash,
)
from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_APPROVALS_OUTPUT = (
    AUDIT_DIR / "a_share_approval_materialization_batch_approvals_2026-06-20.json"
)
DEFAULT_JSON_OUTPUT = (
    AUDIT_DIR / "a_share_approval_materialization_batch_codex_review_2026-06-20.json"
)
DEFAULT_MD_OUTPUT = (
    AUDIT_DIR / "a_share_approval_materialization_batch_codex_review_2026-06-20.md"
)
REVIEWER = "codex-formula-materialization-batch-review"


def _approval_id(dp_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", dp_id).strip("-").lower()
    return f"codex-formula-batch-review-{slug}"


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


def _score_values(planned_rows: list[Mapping[str, Any]]) -> list[float]:
    scores: list[float] = []
    for row in planned_rows:
        value_json = row.get("value_json")
        if not isinstance(value_json, Mapping):
            continue
        score = value_json.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            scores.append(float(score))
    return scores


def _distribution(scores: list[float]) -> dict[str, float | int | None]:
    if not scores:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "avg": None,
            "positive": 0,
            "negative": 0,
            "zero": 0,
        }
    return {
        "count": len(scores),
        "min": round(min(scores), 6),
        "max": round(max(scores), 6),
        "avg": round(sum(scores) / len(scores), 6),
        "positive": sum(1 for score in scores if score > 0),
        "negative": sum(1 for score in scores if score < 0),
        "zero": sum(1 for score in scores if score == 0),
    }


def _review_errors(
    row: Mapping[str, Any],
    *,
    planned_rows: list[Mapping[str, Any]],
    batch_plan_set: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    dp_id = str(row.get("dp_id") or "")
    payload = row.get("batch_plan_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    target_ts_codes_raw = payload.get("target_ts_codes")
    target_ts_codes = [
        str(item) for item in target_ts_codes_raw or [] if str(item).strip()
    ]
    planned_ts_codes = [str(item.get("ts_code") or "") for item in planned_rows]
    planned_ts_set = set(planned_ts_codes)

    if row.get("batch_plan_contract_valid") is not True:
        errors.append("batch_plan_contract_must_be_valid")
    if row.get("batch_plan_status") != "review_required":
        errors.append("batch_plan_status_must_be_review_required")
    materialization_class = str(row.get("materialization_class") or "")
    if materialization_class not in PLAN_READY_CLASSES:
        errors.append("materialization_class_must_be_plan_ready_class")
    if row.get("score_target") != "fundamental_score":
        errors.append("score_target_must_be_fundamental_score")
    if row.get("backup_required") is not True:
        errors.append("backup_required_must_be_true")
    if row.get("batch_plan_approved") is not False:
        errors.append("batch_plan_must_not_already_be_approved")
    if row.get("runtime_write_attempted") is not False:
        errors.append("runtime_write_attempted_must_be_false")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_allowed_must_be_false")
    if not row.get("backup_path_template"):
        errors.append("backup_path_template_must_be_present")
    if not row.get("rollback_strategy"):
        errors.append("rollback_strategy_must_be_present")
    if row.get("batch_plan_sha256") not in set(batch_plan_set.get("batch_plan_hashes") or []):
        errors.append("batch_plan_sha256_must_be_in_batch_plan_set")

    if payload.get("operation") != "upsert_realtime_current":
        errors.append("operation_must_be_upsert_realtime_current")
    if payload.get("primary_key") != REALTIME_PRIMARY_KEY:
        errors.append("primary_key_must_match_realtime_current")
    if payload.get("dp_id") != dp_id:
        errors.append("payload_dp_id_must_match_row")
    if payload.get("score_target") != row.get("score_target"):
        errors.append("payload_score_target_must_match_row")
    if payload.get("materialization_plan_sha256") != row.get(
        "materialization_plan_sha256"
    ):
        errors.append("payload_materialization_plan_hash_must_match_row")
    if payload.get("planned_row_set_sha256") != row.get("planned_row_set_sha256"):
        errors.append("payload_row_set_hash_must_match_row")
    if row.get("batch_plan_sha256") != _canonical_hash(payload):
        errors.append("batch_plan_sha256_must_match_payload")
    if payload.get("conflict_policy") != "upsert_on_primary_key_after_backup":
        errors.append("conflict_policy_must_require_backup")
    if not str(payload.get("rollback_policy") or "").strip():
        errors.append("rollback_policy_must_be_present")

    row_contract = payload.get("row_contract")
    row_contract = row_contract if isinstance(row_contract, Mapping) else {}
    if row_contract.get("data_status") != "Known":
        errors.append("row_contract_data_status_must_be_known")
    if row_contract.get("source") != row.get("runtime_source"):
        errors.append("row_contract_source_must_match_runtime_source")
    if row_contract.get("updated_at") != "execution_time_epoch_seconds":
        errors.append("row_contract_updated_at_must_be_execution_placeholder")
    if row_contract.get("per_row_value_json") is not True:
        errors.append("row_contract_must_require_per_row_value_json")

    planned_count = int(row.get("planned_upsert_row_count") or 0)
    rows_to_insert = int(row.get("rows_to_insert_count") or 0)
    rows_to_update = int(row.get("rows_to_update_count") or 0)
    backup_rows = int(row.get("existing_rows_to_backup_count") or 0)
    noop_rows = int(row.get("noop_existing_rows_count") or 0)
    conflict_rows = int(row.get("existing_conflict_row_count") or 0)
    if planned_count <= 0:
        errors.append("planned_upsert_row_count_must_be_positive")
    if len(planned_rows) != planned_count:
        errors.append("planned_rows_count_must_match_batch_plan")
    if len(target_ts_codes) != planned_count:
        errors.append("target_ts_code_count_must_match_planned_count")
    if len(set(target_ts_codes)) != len(target_ts_codes):
        errors.append("target_ts_codes_must_be_unique")
    if set(target_ts_codes) != planned_ts_set:
        errors.append("target_ts_codes_must_match_planned_rows")
    if len(planned_ts_set) != len(planned_ts_codes):
        errors.append("planned_rows_must_have_unique_target_keys")
    if rows_to_insert + rows_to_update + noop_rows != planned_count:
        errors.append("insert_update_noop_counts_must_equal_planned_count")
    if backup_rows != rows_to_update + noop_rows:
        errors.append("backup_rows_must_match_existing_planned_rows")
    if conflict_rows != rows_to_update:
        errors.append("conflict_rows_must_match_update_rows")
    if _row_set_hash(planned_rows) != row.get("planned_row_set_sha256"):
        errors.append("planned_row_set_sha256_must_match_planned_rows")

    for planned in planned_rows:
        ts_code = str(planned.get("ts_code") or "")
        value_json = planned.get("value_json")
        value_json = value_json if isinstance(value_json, Mapping) else {}
        score = value_json.get("score")
        if planned.get("dp_id") != dp_id:
            errors.append(f"{ts_code}:planned_dp_id_must_match_row")
        if planned.get("score_target") != row.get("score_target"):
            errors.append(f"{ts_code}:planned_score_target_must_match_row")
        if planned.get("data_status") != "Known":
            errors.append(f"{ts_code}:planned_data_status_must_be_known")
        if planned.get("source") != row.get("runtime_source"):
            errors.append(f"{ts_code}:planned_source_must_match_runtime_source")
        if planned.get("updated_at") != "execution_time_epoch_seconds":
            errors.append(f"{ts_code}:planned_updated_at_must_be_placeholder")
        if not isinstance(planned.get("confidence"), (int, float)) or isinstance(
            planned.get("confidence"), bool
        ):
            errors.append(f"{ts_code}:planned_confidence_must_be_numeric")
        else:
            confidence = float(planned.get("confidence") or 0)
            if not 0 <= confidence <= 1:
                errors.append(f"{ts_code}:planned_confidence_must_be_between_0_and_1")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            errors.append(f"{ts_code}:score_must_be_numeric")
            continue
        if not -1 <= float(score) <= 1:
            errors.append(f"{ts_code}:score_must_be_in_unit_interval")
        if value_json.get("materialization_class") != materialization_class:
            errors.append(f"{ts_code}:value_materialization_class_must_match")
        if not isinstance(value_json.get("drivers"), list) or not value_json.get(
            "drivers"
        ):
            errors.append(f"{ts_code}:drivers_must_be_non_empty")
        if not isinstance(value_json.get("components"), Mapping):
            errors.append(f"{ts_code}:components_must_be_object")
        if not value_json.get("materialization_formula"):
            errors.append(f"{ts_code}:materialization_formula_must_be_present")
        bridge_signal = _realtime_signal(
            dp_id,
            dict(value_json),
            str(row.get("score_target") or ""),
            ts_code=ts_code,
        )
        if bridge_signal is None:
            errors.append(f"{ts_code}:bridge_signal_must_be_present")
        elif _round(bridge_signal) != planned.get("bridge_signal"):
            errors.append(f"{ts_code}:bridge_signal_must_match_planned_value")
    return sorted(set(errors))


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
        "approval_scope": APPROVAL_SCOPE,
        "reviewer": REVIEWER,
        "approved_at": approved_at,
        "batch_plan_sha256": row.get("batch_plan_sha256"),
        "batch_plan_set_sha256": batch_plan_set.get("batch_plan_set_sha256"),
        "materialization_plan_sha256": row.get("materialization_plan_sha256"),
        "planned_row_set_sha256": row.get("planned_row_set_sha256"),
        "planned_upsert_row_count": row.get("planned_upsert_row_count"),
        "rows_to_insert_count": row.get("rows_to_insert_count"),
        "rows_to_update_count": row.get("rows_to_update_count"),
        "existing_rows_to_backup_count": row.get("existing_rows_to_backup_count"),
        "backup_required": True,
        "risk_acknowledged": True,
        "review_basis": (
            "Codex verified batch-plan hash, materialized row-set hash, per-row score "
            "range, bridge-signal conversion, insert/update/backup counts, and "
            "rollback policy; approval is runtime-only and keeps production writes disabled."
        ),
        "production_write_allowed": False,
    }


def _decision_for_row(
    row: Mapping[str, Any],
    *,
    planned_rows: list[Mapping[str, Any]],
    approved_at: str,
    batch_plan_set: Mapping[str, Any],
) -> dict[str, Any]:
    errors = _review_errors(row, planned_rows=planned_rows, batch_plan_set=batch_plan_set)
    approval = (
        None
        if errors
        else _approval_record(row, approved_at=approved_at, batch_plan_set=batch_plan_set)
    )
    scores = _score_values(planned_rows)
    return {
        "dp_id": row.get("dp_id"),
        "score_target": row.get("score_target"),
        "batch_plan_sha256": row.get("batch_plan_sha256"),
        "planned_row_set_sha256": row.get("planned_row_set_sha256"),
        "planned_upsert_row_count": row.get("planned_upsert_row_count"),
        "rows_to_insert_count": row.get("rows_to_insert_count"),
        "rows_to_update_count": row.get("rows_to_update_count"),
        "existing_rows_to_backup_count": row.get("existing_rows_to_backup_count"),
        "review_decision": "approved_controlled_formula_batch_plan"
        if approval
        else "formula_batch_review_rejected",
        "approval_record": approval,
        "validation_errors": errors,
        "score_distribution": _distribution(scores),
    }


def build_report(
    *,
    batch_plan_path: Path,
    approved_at: str | None = None,
) -> dict[str, Any]:
    batch_plan = _load_json(batch_plan_path)
    approved_at = approved_at or dt.datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    batch_plan_set = batch_plan.get("batch_plan_set")
    batch_plan_set = batch_plan_set if isinstance(batch_plan_set, Mapping) else {}
    grouped_planned = _planned_rows_by_dp(batch_plan)
    rows = [
        _decision_for_row(
            row,
            planned_rows=grouped_planned.get(str(row.get("dp_id") or ""), []),
            approved_at=approved_at,
            batch_plan_set=batch_plan_set,
        )
        for row in batch_plan.get("rows") or []
        if isinstance(row, Mapping)
    ]
    approvals = [
        row["approval_record"]
        for row in rows
        if isinstance(row.get("approval_record"), Mapping)
    ]
    decision_counts = Counter(str(row.get("review_decision") or "") for row in rows)
    approved_scores = [
        score
        for row in rows
        if row.get("approval_record")
        for score in _score_values(grouped_planned.get(str(row.get("dp_id") or ""), []))
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {"batch_plan_path": _portable_path(batch_plan_path)},
        "summary": {
            "batch_plan_row_count": len(rows),
            "codex_review_approved_count": len(approvals),
            "codex_review_rejected_count": decision_counts.get(
                "formula_batch_review_rejected", 0
            ),
            "approval_record_count": len(approvals),
            "planned_upsert_row_count": sum(
                int(row.get("planned_upsert_row_count") or 0) for row in rows
            ),
            "approved_planned_upsert_row_count": sum(
                int(record.get("planned_upsert_row_count") or 0)
                for record in approvals
            ),
            "rows_to_insert_count": sum(
                int(record.get("rows_to_insert_count") or 0) for record in approvals
            ),
            "rows_to_update_count": sum(
                int(record.get("rows_to_update_count") or 0) for record in approvals
            ),
            "existing_rows_to_backup_count": sum(
                int(record.get("existing_rows_to_backup_count") or 0)
                for record in approvals
            ),
            "approved_score_distribution": _distribution(approved_scores),
            "runtime_write_attempted_count": 0,
            "production_write_allowed_count": 0,
            "decision_counts": dict(sorted(decision_counts.items())),
            "score_mutation": "approval records only; no realtime_current or production score mutation",
        },
        "approvals": approvals,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share formula materialization Codex batch review",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Batch-plan rows checked: `{summary['batch_plan_row_count']}`",
        f"- Codex review approved: `{summary['codex_review_approved_count']}`",
        f"- Codex review rejected: `{summary['codex_review_rejected_count']}`",
        f"- Approval records emitted: `{summary['approval_record_count']}`",
        f"- Approved planned UPSERT rows: `{summary['approved_planned_upsert_row_count']}`",
        f"- Runtime writes attempted: `{summary['runtime_write_attempted_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | review decision | planned rows | score min | score max | errors |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in report.get("rows") or []:
        distribution = row.get("score_distribution") or {}
        errors = ", ".join(row.get("validation_errors") or []) or "none"
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['review_decision']}` | "
            f"{row.get('planned_upsert_row_count', 0)} | "
            f"{distribution.get('min')} | "
            f"{distribution.get('max')} | "
            f"{errors} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Approval records authorize only the controlled formula batch-plan hashes.",
            "- The review does not create a runtime backup and does not execute UPSERTs.",
            "- Production writes remain disabled even after approval.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-plan-path", type=Path, default=DEFAULT_BATCH_PLAN_PATH)
    parser.add_argument("--approvals-output", type=Path, default=DEFAULT_APPROVALS_OUTPUT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(batch_plan_path=args.batch_plan_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    args.approvals_output.write_text(
        json.dumps(
            {
                "generated_at": report["generated_at"],
                "source_review_path": _portable_path(args.json_output),
                "summary": report["summary"],
                "approvals": report["approvals"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
