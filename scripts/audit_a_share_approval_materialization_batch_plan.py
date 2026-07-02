#!/usr/bin/env python3
"""Build review-required batch plans for A-share formula materialization.

This audit packages the seven direct structured formula materialization plans
into controlled runtime batch-plan records. It remains read-only: no approval
records are created and no ``realtime_current`` rows are written.
"""

from __future__ import annotations

import argparse
import copy
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
from scripts.audit_a_share_approval_materialization_plan import (  # noqa: E402
    DIRECT_STRUCTURED_FORMULAS,
    DEFAULT_JSON_OUTPUT as DEFAULT_MATERIALIZATION_PLAN_PATH,
    DEFAULT_REVIEW_MANIFEST_PATH,
    DEFAULT_RUNTIME_DB_PATH,
    DEFAULT_UNIVERSE_PATH,
    _config_a_share_codes,
    _config_a_share_industry_map,
    _runtime_values_by_dp,
    _round,
    _safe_float,
)
from scripts.audit_a_share_runtime_write_batch_plan import (  # noqa: E402
    REALTIME_PRIMARY_KEY,
    _canonical_hash,
    _canonical_value_json,
    _schema_evidence,
)
from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_JSON_OUTPUT = (
    AUDIT_DIR / "a_share_approval_materialization_batch_plan_2026-06-20.json"
)
DEFAULT_MD_OUTPUT = (
    AUDIT_DIR / "a_share_approval_materialization_batch_plan_2026-06-20.md"
)
PLAN_READY_CLASSES = {
    "direct_structured_per_stock_formula",
    "structured_formula_grain_join_per_stock",
    "text_evidence_subset_per_stock",
}


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_rows = payload.get("rows") or []
    if not isinstance(raw_rows, list):
        return []
    return [dict(row) for row in raw_rows if isinstance(row, Mapping)]


def _by_dp_id(rows: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            out[dp_id] = row
    return out


def _existing_rows(
    conn: sqlite3.Connection,
    *,
    dp_id: str,
    ts_codes: list[str],
) -> list[dict[str, Any]]:
    if not ts_codes:
        return []
    rows: list[dict[str, Any]] = []
    chunk_size = 500
    for offset in range(0, len(ts_codes), chunk_size):
        chunk = ts_codes[offset : offset + chunk_size]
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


def _manifest_confidence(manifest_row: Mapping[str, Any]) -> float:
    payload = manifest_row.get("review_payload")
    if isinstance(payload, Mapping):
        raw = payload.get("confidence")
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return float(raw)
    return 0.5


def _runtime_source(dp_id: str) -> str:
    return f"a_share_approval_materialization_batch_plan:{dp_id}"


def _planned_rows_for_dp(
    materialization_row: Mapping[str, Any],
    *,
    manifest_row: Mapping[str, Any],
    a_share_codes: list[str],
    industry_by_ts_code: Mapping[str, str],
    runtime_values: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], list[str]]:
    dp_id = str(materialization_row.get("dp_id") or "")
    materialization_class = str(materialization_row.get("materialization_class") or "")
    confidence = _manifest_confidence(manifest_row)
    planned_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    if materialization_class == "text_evidence_subset_per_stock":
        payload = manifest_row.get("review_payload")
        payload = payload if isinstance(payload, Mapping) else {}
        base_value_json = payload.get("value_json")
        base_value_json = dict(base_value_json) if isinstance(base_value_json, Mapping) else {}
        components = base_value_json.get("components")
        components = dict(components) if isinstance(components, Mapping) else {}
        examples = [
            example
            for example in components.get("evidence_examples") or []
            if isinstance(example, Mapping)
        ]
        examples_by_ts: dict[str, list[Mapping[str, Any]]] = {}
        for example in examples:
            ts_code = str(example.get("ts_code") or "")
            if ts_code:
                examples_by_ts.setdefault(ts_code, []).append(example)
        for ts_code in sorted(examples_by_ts):
            value_json = copy.deepcopy(base_value_json)
            value_json["materialization_class"] = materialization_class
            value_json["materialization_formula"] = (
                "reviewed company QA text evidence; materialize only retained "
                "evidence_example ts_codes"
            )
            value_components = dict(value_json.get("components") or {})
            value_components["evidence_examples"] = [
                dict(example) for example in examples_by_ts[ts_code]
            ]
            value_json["components"] = value_components
            bridge_signal = _realtime_signal(
                dp_id,
                value_json,
                str(materialization_row.get("score_target") or "fundamental_score"),
                ts_code=ts_code,
            )
            if bridge_signal is None:
                errors.append(f"{ts_code}:bridge_signal_missing")
                continue
            planned_rows.append(
                {
                    "ts_code": ts_code,
                    "dp_id": dp_id,
                    "score_target": materialization_row.get("score_target"),
                    "value_json": value_json,
                    "data_status": "Known",
                    "confidence": confidence,
                    "source": _runtime_source(dp_id),
                    "updated_at": "execution_time_epoch_seconds",
                    "bridge_signal": _round(bridge_signal),
                }
            )
        return planned_rows, errors

    if materialization_class == "structured_formula_grain_join_per_stock":
        deps = ["L0.cost.raw_material", "L5.is.gross_margin"]
        formula_text = str(materialization_row.get("formula") or "")
        for ts_code in a_share_codes:
            industry_id = industry_by_ts_code.get(ts_code)
            raw_material = (
                runtime_values.get("L0.cost.raw_material", {}).get(f"INDUSTRY:{industry_id}")
                if industry_id
                else None
            )
            gross_margin = runtime_values.get("L5.is.gross_margin", {}).get(ts_code)
            raw_pct = _safe_float((raw_material or {}).get("avg_pct_change"))
            gross_margin_value = _safe_float((gross_margin or {}).get("scalar"))
            if raw_pct is None or gross_margin_value is None:
                continue
            raw_material_relief_component = -(raw_pct / 3.0)
            gross_margin_buffer_component = (gross_margin_value - 0.20) / 0.50
            score = max(
                -1.0,
                min(1.0, raw_material_relief_component + gross_margin_buffer_component),
            )
            value_json = {
                "score": _round(score),
                "drivers": deps,
                "components": {
                    "industry_id": industry_id,
                    "raw_material_avg_pct_change": _round(raw_pct),
                    "gross_margin": _round(gross_margin_value),
                    "raw_material_relief_component": _round(raw_material_relief_component),
                    "gross_margin_buffer_component": _round(gross_margin_buffer_component),
                },
                "materialization_formula": formula_text,
                "materialization_class": materialization_class,
            }
            bridge_signal = _realtime_signal(
                dp_id,
                value_json,
                str(materialization_row.get("score_target") or "fundamental_score"),
                ts_code=ts_code,
            )
            if bridge_signal is None:
                errors.append(f"{ts_code}:bridge_signal_missing")
                continue
            planned_rows.append(
                {
                    "ts_code": ts_code,
                    "dp_id": dp_id,
                    "score_target": materialization_row.get("score_target"),
                    "value_json": value_json,
                    "data_status": "Known",
                    "confidence": confidence,
                    "source": _runtime_source(dp_id),
                    "updated_at": "execution_time_epoch_seconds",
                    "bridge_signal": _round(bridge_signal),
                }
            )
        return planned_rows, errors

    deps, formula, formula_text = DIRECT_STRUCTURED_FORMULAS[dp_id]
    for ts_code in a_share_codes:
        values = {dep: runtime_values.get(dep, {}).get(ts_code, {}) for dep in deps}
        score, components = formula(values)
        if score is None:
            continue
        value_json = {
            "score": _round(score),
            "drivers": deps,
            "components": components,
            "materialization_formula": formula_text,
            "materialization_class": "direct_structured_per_stock_formula",
        }
        bridge_signal = _realtime_signal(
            dp_id,
            value_json,
            str(materialization_row.get("score_target") or "fundamental_score"),
            ts_code=ts_code,
        )
        if bridge_signal is None:
            errors.append(f"{ts_code}:bridge_signal_missing")
            continue
        planned_rows.append(
            {
                "ts_code": ts_code,
                "dp_id": dp_id,
                "score_target": materialization_row.get("score_target"),
                "value_json": value_json,
                "data_status": "Known",
                "confidence": confidence,
                "source": _runtime_source(dp_id),
                "updated_at": "execution_time_epoch_seconds",
                "bridge_signal": _round(bridge_signal),
            }
        )
    return planned_rows, errors


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
            for row in planned_rows
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
        if planned is None:
            continue
        try:
            existing_confidence = float(existing.get("confidence"))
        except (TypeError, ValueError):
            continue
        if existing.get("data_status") != planned.get("data_status"):
            continue
        if existing.get("source") != planned.get("source"):
            continue
        if existing_confidence != float(planned.get("confidence") or 0):
            continue
        if str(existing.get("value_json") or "") != _canonical_value_json(
            planned.get("value_json")
        ):
            continue
        count += 1
    return count


def _plan_contract_errors(
    *,
    materialization_row: Mapping[str, Any],
    planned_rows: list[Mapping[str, Any]],
    bridge_errors: list[str],
    schema: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if materialization_row.get("runtime_materialization_plan_ready") is not True:
        errors.append("runtime_materialization_plan_must_be_ready")
    if materialization_row.get("materialization_class") not in PLAN_READY_CLASSES:
        errors.append("materialization_class_must_be_plan_ready")
    if not planned_rows:
        errors.append("planned_rows_must_be_non_empty")
    if bridge_errors:
        errors.append("all_planned_rows_must_bridge_to_score")
    if schema.get("schema_contract_valid") is not True:
        errors.append("realtime_current_schema_contract_must_be_valid")
    return errors


def _batch_plan_for_row(
    materialization_row: Mapping[str, Any],
    *,
    manifest_row: Mapping[str, Any],
    a_share_codes: list[str],
    industry_by_ts_code: Mapping[str, str],
    runtime_values: Mapping[str, Mapping[str, Mapping[str, Any]]],
    conn: sqlite3.Connection,
    schema: Mapping[str, Any],
) -> dict[str, Any]:
    dp_id = str(materialization_row.get("dp_id") or "")
    planned_rows, bridge_errors = _planned_rows_for_dp(
        materialization_row,
        manifest_row=manifest_row,
        a_share_codes=a_share_codes,
        industry_by_ts_code=industry_by_ts_code,
        runtime_values=runtime_values,
    )
    target_ts_codes = [str(row["ts_code"]) for row in planned_rows]
    row_set_sha256 = _row_set_hash(planned_rows)
    existing = _existing_rows(conn, dp_id=dp_id, ts_codes=target_ts_codes)
    planned_by_ts = {str(row["ts_code"]): row for row in planned_rows}
    noop_count = _noop_existing_count(existing, planned_by_ts)
    contract_errors = _plan_contract_errors(
        materialization_row=materialization_row,
        planned_rows=planned_rows,
        bridge_errors=bridge_errors,
        schema=schema,
    )
    contract_valid = not contract_errors
    materialization_plan_payload = {
        "dp_id": dp_id,
        "score_target": materialization_row.get("score_target"),
        "materialization_class": materialization_row.get("materialization_class"),
        "source_dependencies": materialization_row.get("source_dependencies") or [],
        "formula": materialization_row.get("formula"),
        "target_ts_codes": target_ts_codes,
        "planned_row_set_sha256": row_set_sha256,
        "planned_row_count": len(planned_rows),
    }
    materialization_plan_sha256 = (
        _canonical_hash(materialization_plan_payload) if planned_rows else None
    )
    batch_plan_payload = (
        {
            "operation": "upsert_realtime_current",
            "primary_key": REALTIME_PRIMARY_KEY,
            "dp_id": dp_id,
            "score_target": materialization_row.get("score_target"),
            "materialization_plan_sha256": materialization_plan_sha256,
            "planned_row_set_sha256": row_set_sha256,
            "target_ts_codes": target_ts_codes,
            "row_contract": {
                "data_status": "Known",
                "source": _runtime_source(dp_id),
                "updated_at": "execution_time_epoch_seconds",
                "per_row_value_json": True,
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
    batch_plan_sha256 = _canonical_hash(batch_plan_payload) if batch_plan_payload else None
    return {
        "dp_id": dp_id,
        "score_target": materialization_row.get("score_target"),
        "materialization_class": materialization_row.get("materialization_class"),
        "batch_plan_status": "review_required" if contract_valid else "blocked_contract_invalid",
        "batch_plan_contract_valid": contract_valid,
        "batch_plan_contract_errors": contract_errors,
        "materialization_plan_sha256": materialization_plan_sha256,
        "planned_row_set_sha256": row_set_sha256,
        "batch_plan_sha256": batch_plan_sha256,
        "target_ts_code_count": len(target_ts_codes),
        "target_ts_codes_sample": target_ts_codes[:10],
        "planned_upsert_row_count": len(planned_rows) if contract_valid else 0,
        "planned_rows_sample": planned_rows[:5],
        "bridge_error_count": len(bridge_errors),
        "bridge_error_sample": bridge_errors[:10],
        "existing_rows_to_backup_count": len(existing),
        "existing_rows_sample": existing[:5],
        "noop_existing_rows_count": noop_count,
        "existing_conflict_row_count": len(existing) - noop_count,
        "rows_to_update_count": len(existing) - noop_count,
        "rows_to_insert_count": max(0, len(planned_rows) - len(existing)),
        "runtime_source": _runtime_source(dp_id),
        "backup_required": contract_valid,
        "backup_path_template": (
            "runtime/backups/hot.sqlite.before_a_share_formula_batch_"
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
        "batch_plan_payload": batch_plan_payload,
        "batch_plan_approved": False,
        "batch_plan_approval_valid": False,
        "batch_plan_approval_errors": ["controlled_batch_plan_requires_review_approval"]
        if contract_valid
        else ["batch_plan_contract_invalid"],
        "upsert_ready": False,
        "blocking_reasons": ["controlled_batch_plan_requires_review_approval"]
        if contract_valid
        else ["batch_plan_contract_invalid"],
        "runtime_write_attempted": False,
        "production_write_allowed": False,
        "score_mutation": "none",
        "required_next_evidence": [
            "review approval for the controlled formula materialization batch-plan hash",
            "runtime database backup at the declared backup path",
            "bounded UPSERT execution log and post-write score-field closure rerun",
        ],
        "planned_rows": planned_rows,
    }


def build_report(
    *,
    materialization_plan_path: Path,
    review_manifest_path: Path,
    runtime_db_path: Path,
    universe_path: Path,
) -> dict[str, Any]:
    started = time.time()
    materialization_plan = _load_json(materialization_plan_path)
    review_manifest = _load_json(review_manifest_path)
    manifest_by_dp = _by_dp_id(_rows(review_manifest))
    plan_rows = [
        row
        for row in _rows(materialization_plan)
        if row.get("materialization_class") in PLAN_READY_CLASSES
        and row.get("runtime_materialization_plan_ready") is True
    ]
    a_share_codes = _config_a_share_codes(universe_path)
    industry_by_ts_code = _config_a_share_industry_map(universe_path)
    formula_deps = {
        dep
        for deps, _formula, _text in DIRECT_STRUCTURED_FORMULAS.values()
        for dep in deps
    }
    formula_deps.update({"L0.cost.raw_material", "L5.is.gross_margin"})
    runtime_values = _runtime_values_by_dp(runtime_db_path, formula_deps)
    conn = sqlite3.connect(f"file:{runtime_db_path}?mode=ro", uri=True)
    try:
        schema = _schema_evidence(conn)
        rows = [
            _batch_plan_for_row(
                row,
                manifest_row=manifest_by_dp.get(str(row.get("dp_id") or ""), {}),
                a_share_codes=a_share_codes,
                industry_by_ts_code=industry_by_ts_code,
                runtime_values=runtime_values,
                conn=conn,
                schema=schema,
            )
            for row in plan_rows
        ]
    finally:
        conn.close()
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    all_planned_rows = [
        planned_row for row in rows for planned_row in row.get("planned_rows", [])
    ]
    row_set_sha256 = _canonical_hash(all_planned_rows) if all_planned_rows else None
    valid_rows = [row for row in rows if row.get("batch_plan_contract_valid")]
    reason_counts: Counter[str] = Counter()
    for row in rows:
        reason_counts.update(str(reason) for reason in row.get("blocking_reasons") or [])
    batch_plan_set_payload = {
        "runtime_db_path": _portable_path(runtime_db_path),
        "materialization_plan_path": _portable_path(materialization_plan_path),
        "batch_plan_hashes": [
            row.get("batch_plan_sha256")
            for row in valid_rows
            if row.get("batch_plan_sha256")
        ],
        "planned_row_set_sha256": row_set_sha256,
    }
    batch_plan_set_sha256 = (
        _canonical_hash(batch_plan_set_payload) if valid_rows else None
    )
    output_rows = []
    for row in rows:
        compact = dict(row)
        compact.pop("planned_rows", None)
        output_rows.append(compact)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "materialization_plan_path": _portable_path(materialization_plan_path),
            "review_manifest_path": _portable_path(review_manifest_path),
            "runtime_db_path": _portable_path(runtime_db_path),
            "universe_path": _portable_path(universe_path),
        },
        "runtime_schema": schema,
        "batch_plan_set": {
            "batch_plan_set_sha256": batch_plan_set_sha256,
            "batch_plan_set_id": f"a-share-formula-batch-{str(batch_plan_set_sha256 or '')[:12]}"
            if batch_plan_set_sha256
            else None,
            "planned_row_set_sha256": row_set_sha256,
            "batch_plan_hashes": [
                row.get("batch_plan_sha256")
                for row in valid_rows
                if row.get("batch_plan_sha256")
            ],
            "approval_scope": "controlled_formula_materialization_batch_plan",
            "production_write_allowed": False,
        },
        "summary": {
            "direct_formula_plan_count": len(plan_rows),
            "batch_plan_entry_count": len(rows),
            "batch_plan_contract_valid_count": len(valid_rows),
            "batch_plan_contract_invalid_count": len(rows) - len(valid_rows),
            "batch_plan_review_required_count": sum(
                1 for row in rows if row.get("batch_plan_status") == "review_required"
            ),
            "batch_plan_approved_count": 0,
            "planned_upsert_row_count": sum(
                int(row.get("planned_upsert_row_count") or 0) for row in rows
            ),
            "rows_to_insert_count": sum(
                int(row.get("rows_to_insert_count") or 0) for row in rows
            ),
            "rows_to_update_count": sum(
                int(row.get("rows_to_update_count") or 0) for row in rows
            ),
            "existing_rows_to_backup_count": sum(
                int(row.get("existing_rows_to_backup_count") or 0) for row in rows
            ),
            "existing_conflict_row_count": sum(
                int(row.get("existing_conflict_row_count") or 0) for row in rows
            ),
            "noop_existing_rows_count": sum(
                int(row.get("noop_existing_rows_count") or 0) for row in rows
            ),
            "backup_required_count": sum(1 for row in rows if row.get("backup_required")),
            "upsert_ready_entry_count": 0,
            "blocked_entry_count": len(rows),
            "runtime_write_attempted_count": 0,
            "production_write_allowed_count": 0,
            "blocking_reason_counts": dict(sorted(reason_counts.items())),
            "score_mutation": "none; formula materialization batch-plan audit is read-only and does not alter realtime_current",
        },
        "planned_rows_sha256": row_set_sha256,
        "planned_rows": all_planned_rows,
        "rows": output_rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    batch_set = report.get("batch_plan_set") or {}
    lines = [
        "# A-share approval materialization batch plan",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Batch plan set: `{batch_set.get('batch_plan_set_id')}`",
        f"- Direct formula plans: `{summary['direct_formula_plan_count']}`",
        f"- Batch-plan entries: `{summary['batch_plan_entry_count']}`",
        f"- Contract-valid batch plans: `{summary['batch_plan_contract_valid_count']}`",
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
        "| dp_id | status | planned rows | inserts | updates | backup rows | plan hash | blockers |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in report["rows"]:
        blockers = ", ".join(row.get("blocking_reasons") or []) or "none"
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
            "- This packages formula materialization into review-required controlled batch plans.",
            "- The row-set hash binds the computed per-stock values from the current runtime inputs.",
            "- This audit creates no approval records, performs no UPSERTs, and allows no production writes.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--materialization-plan-path",
        type=Path,
        default=DEFAULT_MATERIALIZATION_PLAN_PATH,
    )
    parser.add_argument(
        "--review-manifest-path", type=Path, default=DEFAULT_REVIEW_MANIFEST_PATH
    )
    parser.add_argument("--runtime-db-path", type=Path, default=DEFAULT_RUNTIME_DB_PATH)
    parser.add_argument("--universe-path", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        materialization_plan_path=args.materialization_plan_path,
        review_manifest_path=args.review_manifest_path,
        runtime_db_path=args.runtime_db_path,
        universe_path=args.universe_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
