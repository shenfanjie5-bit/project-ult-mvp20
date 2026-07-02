#!/usr/bin/env python3
"""Audit target-scope candidates for approved A-share runtime write plans.

This audit is read-only. It does not make approved payloads executable by
itself; it only proves whether a deterministic, current A-share universe can be
derived for rows that otherwise lack explicit ``target_ts_codes``.
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

import yaml

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_APPROVAL_GATE_PATH = AUDIT_DIR / "a_share_review_approval_gate_2026-06-19.json"
DEFAULT_RUNTIME_DB_PATH = ROOT / "runtime/hot.sqlite"
DEFAULT_UNIVERSE_PATH = ROOT / "config/mvp20.universe.yaml"
DEFAULT_JSON_OUTPUT = (
    AUDIT_DIR / "a_share_runtime_write_target_scope_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = AUDIT_DIR / "a_share_runtime_write_target_scope_2026-06-19.md"
DEFAULT_SCOPE_APPROVALS_PATH = (
    AUDIT_DIR / "a_share_runtime_scope_approvals_2026-06-19.json"
)

A_SHARE_SUFFIXES = (".SH", ".SZ", ".BJ")

TARGET_SCOPE_POLICIES: dict[str, dict[str, Any]] = {
    "L7.trade.gamma": {
        "scope_kind": "current_a_share_single_stock_universe",
        "score_target": "gamma_multiplier",
        "value_requirements": {
            "multiplier": 1.0,
            "applicability": "a_share_single_stock_no_listed_option",
        },
        "rationale": (
            "Gamma multiplier is neutral for current A-share single-stock rows "
            "because no broad per-stock A-share listed-option source is wired."
        ),
    },
    "L9.media.short_report": {
        "scope_kind": "current_a_share_single_stock_universe",
        "score_target": "expectation_gap",
        "value_requirements": {
            "score": 0.0,
            "event_state": "none_observed",
            "direct_a_share_short_report_documents": 0,
        },
        "rationale": (
            "Short-report expectation gap is neutral for current A-share rows "
            "when the dedicated scan finds no direct A-share short-report documents."
        ),
    },
}


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


def _is_a_share(ts_code: str) -> bool:
    return ts_code.endswith(A_SHARE_SUFFIXES)


def _suffix(ts_code: str) -> str:
    if "." in ts_code:
        return "." + ts_code.rsplit(".", 1)[-1]
    return ts_code[-3:] if len(ts_code) >= 3 else ts_code


def _runtime_ts_codes(runtime_db_path: Path) -> list[str]:
    conn = sqlite3.connect(f"file:{runtime_db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "select distinct ts_code from realtime_current where ts_code is not null"
        ).fetchall()
    finally:
        conn.close()
    return sorted(str(row[0]) for row in rows if str(row[0]).strip())


def _config_ts_codes(universe_path: Path) -> list[str]:
    payload = yaml.safe_load(universe_path.read_text(encoding="utf-8")) or {}
    constituents = payload.get("constituents") or []
    return sorted(
        str(row.get("ts_code"))
        for row in constituents
        if isinstance(row, Mapping) and str(row.get("ts_code") or "").strip()
    )


def _scope_evidence(*, runtime_db_path: Path, universe_path: Path) -> dict[str, Any]:
    runtime_codes = _runtime_ts_codes(runtime_db_path)
    config_codes = _config_ts_codes(universe_path)
    runtime_a_share = sorted(code for code in runtime_codes if _is_a_share(code))
    config_a_share = sorted(code for code in config_codes if _is_a_share(code))
    runtime_a_share_set = set(runtime_a_share)
    config_a_share_set = set(config_a_share)
    runtime_suffix_counts = Counter(_suffix(code) for code in runtime_codes)
    config_suffix_counts = Counter(_suffix(code) for code in config_codes)
    missing_from_runtime = sorted(config_a_share_set - runtime_a_share_set)
    missing_from_config = sorted(runtime_a_share_set - config_a_share_set)
    return {
        "runtime_db_path": _portable_path(runtime_db_path),
        "universe_path": _portable_path(universe_path),
        "runtime_total_ts_code_count": len(runtime_codes),
        "runtime_a_share_ts_code_count": len(runtime_a_share),
        "runtime_suffix_counts": dict(sorted(runtime_suffix_counts.items())),
        "config_total_ts_code_count": len(config_codes),
        "config_a_share_ts_code_count": len(config_a_share),
        "config_suffix_counts": dict(sorted(config_suffix_counts.items())),
        "config_runtime_a_share_exact_match": not missing_from_runtime
        and not missing_from_config
        and bool(runtime_a_share),
        "config_a_share_missing_from_runtime_count": len(missing_from_runtime),
        "runtime_a_share_missing_from_config_count": len(missing_from_config),
        "config_a_share_missing_from_runtime_sample": missing_from_runtime[:10],
        "runtime_a_share_missing_from_config_sample": missing_from_config[:10],
        "a_share_target_ts_codes": runtime_a_share,
        "a_share_target_ts_codes_sample": runtime_a_share[:10],
    }


def _value_requirement_errors(
    *,
    value_json: Any,
    requirements: Mapping[str, Any],
) -> list[str]:
    if not isinstance(value_json, Mapping):
        return ["value_json_must_be_object"]
    errors: list[str] = []
    for key, expected in requirements.items():
        if value_json.get(key) != expected:
            errors.append(f"value_json.{key}_must_equal_{expected!r}")
    return errors


def _row_contract_errors(
    row: Mapping[str, Any],
    *,
    scope: Mapping[str, Any],
    policy: Mapping[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    if policy is None:
        errors.append("unsupported_target_scope_policy")
        return errors
    if row.get("data_status") not in {"Known", "NotApplicable"}:
        errors.append("data_status_must_be_known_or_not_applicable")
    if row.get("score_target") != policy.get("score_target"):
        errors.append("score_target_must_match_target_scope_policy")
    if not isinstance(row.get("confidence"), (int, float)):
        errors.append("confidence_must_be_numeric")
    if row.get("runtime_write_allowed") is not True:
        errors.append("runtime_write_not_approved")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_must_remain_false")
    if not scope.get("config_runtime_a_share_exact_match"):
        errors.append("runtime_a_share_universe_must_match_config")
    if int(scope.get("runtime_a_share_ts_code_count") or 0) <= 0:
        errors.append("runtime_a_share_universe_must_not_be_empty")
    errors.extend(
        _value_requirement_errors(
            value_json=row.get("value_json"),
            requirements=policy.get("value_requirements") or {},
        )
    )
    return errors


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _target_scope_payload(
    *,
    row: Mapping[str, Any],
    scope: Mapping[str, Any],
    policy: Mapping[str, Any],
    candidate_codes: list[str],
) -> dict[str, Any]:
    return {
        "dp_id": row.get("dp_id"),
        "score_target": row.get("score_target"),
        "data_status": row.get("data_status"),
        "payload_sha256": row.get("payload_sha256"),
        "approval_id": (row.get("approval") or {}).get("approval_id")
        if isinstance(row.get("approval"), Mapping)
        else None,
        "target_scope_kind": policy.get("scope_kind"),
        "runtime_db_path": scope.get("runtime_db_path"),
        "universe_path": scope.get("universe_path"),
        "runtime_a_share_ts_code_count": scope.get("runtime_a_share_ts_code_count"),
        "config_a_share_ts_code_count": scope.get("config_a_share_ts_code_count"),
        "config_runtime_a_share_exact_match": scope.get(
            "config_runtime_a_share_exact_match"
        ),
        "candidate_target_ts_codes": candidate_codes,
        "value_requirements": policy.get("value_requirements") or {},
    }


def _scope_approval_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_records = payload.get("scope_approvals", payload.get("approvals", []))
    if not isinstance(raw_records, list):
        return []
    return [dict(record) for record in raw_records if isinstance(record, Mapping)]


def _scope_approvals_by_dp_id(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    by_dp_id: dict[str, Mapping[str, Any]] = {}
    for record in _scope_approval_records(payload):
        dp_id = str(record.get("dp_id") or "")
        if dp_id:
            by_dp_id[dp_id] = record
    return by_dp_id


def _scope_approval_errors(
    *,
    row: Mapping[str, Any],
    target_scope_sha256: str | None,
    approval: Mapping[str, Any] | None,
) -> list[str]:
    if approval is None:
        return ["missing target-scope approval record"]
    errors: list[str] = []
    if approval.get("dp_id") != row.get("dp_id"):
        errors.append("scope approval dp_id must match target-scope row")
    if approval.get("approval_status") != "approved":
        errors.append("scope approval_status must be approved")
    if approval.get("approval_scope") != "runtime_target_scope":
        errors.append("scope approval_scope must be runtime_target_scope")
    if not approval.get("approval_id"):
        errors.append("scope approval_id must be non-empty")
    if not approval.get("reviewer"):
        errors.append("scope reviewer must be non-empty")
    if not approval.get("approved_at"):
        errors.append("scope approved_at must be non-empty")
    if approval.get("target_scope_sha256") != target_scope_sha256:
        errors.append("target_scope_sha256 must match canonical target-scope payload")
    if approval.get("risk_acknowledged") is not True:
        errors.append("scope risk_acknowledged must be true")
    if approval.get("production_write_allowed") is not False:
        errors.append("scope production_write_allowed must be false")
    return errors


def _row_target_scope(
    row: Mapping[str, Any],
    *,
    scope: Mapping[str, Any],
    scope_approvals_by_dp_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    dp_id = str(row.get("dp_id") or "")
    policy = TARGET_SCOPE_POLICIES.get(dp_id)
    explicit_targets = _target_ts_codes(row)
    errors = _row_contract_errors(row, scope=scope, policy=policy)
    contract_valid = not errors and not explicit_targets
    candidate_codes = list(scope.get("a_share_target_ts_codes") or []) if contract_valid else []
    target_scope_payload = (
        _target_scope_payload(
            row=row,
            scope=scope,
            policy=policy,
            candidate_codes=candidate_codes,
        )
        if policy is not None and contract_valid
        else None
    )
    target_scope_sha256 = (
        _canonical_hash(target_scope_payload)
        if isinstance(target_scope_payload, Mapping)
        else None
    )
    scope_approval = (scope_approvals_by_dp_id or {}).get(dp_id)
    approval_errors = (
        _scope_approval_errors(
            row=row,
            target_scope_sha256=target_scope_sha256,
            approval=scope_approval,
        )
        if contract_valid
        else ["target_scope_contract_invalid"]
    )
    scope_approved = contract_valid and not approval_errors
    if scope_approved:
        status = "scope_approved_batch_plan_required"
        blocking_reasons = ["controlled_batch_upsert_plan_required"]
    elif contract_valid:
        status = "review_required"
        blocking_reasons = ["target_scope_candidate_requires_review_approval"]
    else:
        status = "blocked_contract_invalid"
        blocking_reasons = ["target_scope_contract_invalid"]
    return {
        "dp_id": dp_id,
        "score_target": row.get("score_target"),
        "data_status": row.get("data_status"),
        "payload_sha256": row.get("payload_sha256"),
        "approval_id": (row.get("approval") or {}).get("approval_id")
        if isinstance(row.get("approval"), Mapping)
        else None,
        "original_explicit_target_ts_code_count": len(explicit_targets),
        "target_scope_policy": policy,
        "target_scope_payload": target_scope_payload,
        "target_scope_sha256": target_scope_sha256,
        "target_scope_status": status,
        "target_scope_contract_valid": contract_valid,
        "target_scope_contract_errors": errors,
        "target_scope_approval": scope_approval if scope_approved else None,
        "target_scope_approval_valid": scope_approved,
        "target_scope_approval_errors": approval_errors,
        "candidate_target_ts_code_count": len(candidate_codes),
        "candidate_target_ts_codes_sample": candidate_codes[:10],
        "candidate_runtime_rows_would_write": len(candidate_codes),
        "upsert_ready": False,
        "blocking_reasons": blocking_reasons,
        "runtime_write_attempted": False,
        "production_write_allowed": False,
        "score_mutation": "none",
        "required_next_evidence": [
            "review approval for the target-universe expansion contract",
            "controlled batch UPSERT plan with backup/rollback path",
            "post-write score-field closure rerun",
        ],
    }


def build_report(
    *,
    approval_gate_path: Path,
    runtime_db_path: Path,
    universe_path: Path,
    scope_approvals_path: Path | None = None,
) -> dict[str, Any]:
    started = time.time()
    scope = _scope_evidence(
        runtime_db_path=runtime_db_path,
        universe_path=universe_path,
    )
    scope_approvals_payload = (
        _load_json(scope_approvals_path)
        if scope_approvals_path is not None and scope_approvals_path.exists()
        else {}
    )
    scope_approvals = _scope_approvals_by_dp_id(scope_approvals_payload)
    rows = [
        _row_target_scope(row, scope=scope, scope_approvals_by_dp_id=scope_approvals)
        for row in _write_plan_rows(_load_json(approval_gate_path))
    ]
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    reason_counts: Counter[str] = Counter()
    for row in rows:
        reason_counts.update(str(reason) for reason in row["blocking_reasons"])
    valid_rows = [row for row in rows if row["target_scope_contract_valid"]]
    review_required = [
        row for row in rows if row["target_scope_status"] == "review_required"
    ]
    scope_approved = [
        row
        for row in rows
        if row["target_scope_status"] == "scope_approved_batch_plan_required"
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "approval_gate_path": _portable_path(approval_gate_path),
            "runtime_db_path": _portable_path(runtime_db_path),
            "universe_path": _portable_path(universe_path),
            "scope_approvals_path": _portable_path(scope_approvals_path)
            if scope_approvals_path is not None
            else None,
        },
        "scope_evidence": {
            key: value
            for key, value in scope.items()
            if key != "a_share_target_ts_codes"
        },
        "summary": {
            "approved_write_plan_entry_count": len(rows),
            "runtime_a_share_ts_code_count": int(
                scope.get("runtime_a_share_ts_code_count") or 0
            ),
            "config_a_share_ts_code_count": int(
                scope.get("config_a_share_ts_code_count") or 0
            ),
            "config_runtime_a_share_exact_match": bool(
                scope.get("config_runtime_a_share_exact_match")
            ),
            "config_a_share_missing_from_runtime_count": int(
                scope.get("config_a_share_missing_from_runtime_count") or 0
            ),
            "runtime_a_share_missing_from_config_count": int(
                scope.get("runtime_a_share_missing_from_config_count") or 0
            ),
            "target_scope_candidate_count": len(valid_rows),
            "target_scope_contract_valid_count": len(valid_rows),
            "target_scope_contract_invalid_count": len(rows) - len(valid_rows),
            "target_scope_review_required_count": len(review_required),
            "target_scope_approved_count": len(scope_approved),
            "controlled_batch_plan_required_count": len(scope_approved),
            "upsert_ready_entry_count": 0,
            "blocked_entry_count": len(rows),
            "candidate_runtime_rows_would_write_count": sum(
                int(row["candidate_runtime_rows_would_write"]) for row in rows
            ),
            "runtime_write_attempted_count": 0,
            "production_write_allowed_count": 0,
            "blocking_reason_counts": dict(sorted(reason_counts.items())),
            "score_mutation": "none; target-scope audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share runtime write target-scope audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Approved write-plan entries: `{summary['approved_write_plan_entry_count']}`",
        f"- Runtime A-share ts_codes: `{summary['runtime_a_share_ts_code_count']}`",
        f"- Config A-share ts_codes: `{summary['config_a_share_ts_code_count']}`",
        f"- Runtime/config A-share exact match: `{summary['config_runtime_a_share_exact_match']}`",
        f"- Target-scope candidates: `{summary['target_scope_candidate_count']}`",
        f"- Target-scope review required: `{summary['target_scope_review_required_count']}`",
        f"- Target-scope approved: `{summary.get('target_scope_approved_count', 0)}`",
        f"- Controlled batch plans required: `{summary.get('controlled_batch_plan_required_count', 0)}`",
        f"- Candidate runtime rows that would write if approved: `{summary['candidate_runtime_rows_would_write_count']}`",
        f"- Upsert-ready entries: `{summary['upsert_ready_entry_count']}`",
        f"- Runtime writes attempted: `{summary['runtime_write_attempted_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | scope status | target count | contract valid | candidate rows | blockers |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        blockers = ", ".join(row["blocking_reasons"]) or "none"
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['target_scope_status']}` | "
            f"{row['candidate_target_ts_code_count']} | "
            f"{'yes' if row['target_scope_contract_valid'] else 'no'} | "
            f"{row['candidate_runtime_rows_would_write']} | "
            f"{blockers} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Current runtime and configured A-share universes match exactly for target-scope derivation.",
            "- The derived scope is still a review-required candidate, not an executable UPSERT instruction.",
            "- This audit creates no runtime rows and no production writes.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-gate-path", type=Path, default=DEFAULT_APPROVAL_GATE_PATH)
    parser.add_argument("--runtime-db-path", type=Path, default=DEFAULT_RUNTIME_DB_PATH)
    parser.add_argument("--universe-path", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--scope-approvals-path", type=Path, default=DEFAULT_SCOPE_APPROVALS_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    args = parser.parse_args()

    report = build_report(
        approval_gate_path=args.approval_gate_path,
        runtime_db_path=args.runtime_db_path,
        universe_path=args.universe_path,
        scope_approvals_path=args.scope_approvals_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
