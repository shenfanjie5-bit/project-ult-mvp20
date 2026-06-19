#!/usr/bin/env python3
"""Create deterministic approval records for A-share runtime target scopes.

This is deliberately narrow and read-only. It approves only target-scope
candidates that already have valid contracts and deterministic neutral payload
semantics, and it never writes ``runtime/hot.sqlite``.
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

from scripts.audit_a_share_runtime_write_target_scope import (  # noqa: E402
    DEFAULT_JSON_OUTPUT as DEFAULT_TARGET_SCOPE_PATH,
)
from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_APPROVALS_OUTPUT = ROOT / "docs/audit/a_share_runtime_scope_approvals_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_runtime_scope_approvals_2026-06-19.md"

DETERMINISTIC_SCOPE_DP_IDS = {
    "L7.trade.gamma",
    "L9.media.short_report",
}


def _approval_id(dp_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", dp_id).strip("-").lower()
    return f"codex-runtime-scope-20260619-{slug}"


def _target_scope_policy_errors(row: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    dp_id = str(row.get("dp_id") or "")
    payload = row.get("target_scope_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    policy = row.get("target_scope_policy")
    policy = policy if isinstance(policy, Mapping) else {}
    value_requirements = payload.get("value_requirements")
    value_requirements = value_requirements if isinstance(value_requirements, Mapping) else {}
    if dp_id not in DETERMINISTIC_SCOPE_DP_IDS:
        errors.append("dp_id_not_in_deterministic_scope_policy")
    if row.get("target_scope_contract_valid") is not True:
        errors.append("target_scope_contract_must_be_valid")
    if row.get("target_scope_status") not in {
        "review_required",
        "scope_approved_batch_plan_required",
    }:
        errors.append("target_scope_status_must_be_review_required")
    if not row.get("target_scope_sha256"):
        errors.append("target_scope_sha256_must_be_present")
    if int(row.get("candidate_target_ts_code_count") or 0) <= 0:
        errors.append("candidate_target_ts_code_count_must_be_positive")
    if row.get("runtime_write_attempted") is not False:
        errors.append("runtime_write_attempted_must_be_false")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_allowed_must_be_false")
    if policy.get("scope_kind") != "current_a_share_single_stock_universe":
        errors.append("scope_kind_must_be_current_a_share_single_stock_universe")
    if dp_id == "L7.trade.gamma":
        if value_requirements.get("multiplier") != 1.0:
            errors.append("gamma_multiplier_must_be_neutral_1_0")
        if (
            value_requirements.get("applicability")
            != "a_share_single_stock_no_listed_option"
        ):
            errors.append("gamma_applicability_must_match_no_listed_option_policy")
    if dp_id == "L9.media.short_report":
        if value_requirements.get("score") != 0.0:
            errors.append("short_report_score_must_be_neutral_0_0")
        if value_requirements.get("event_state") != "none_observed":
            errors.append("short_report_event_state_must_be_none_observed")
        if value_requirements.get("direct_a_share_short_report_documents") != 0:
            errors.append("direct_a_share_short_report_documents_must_be_zero")
    return errors


def _approval_record(
    row: Mapping[str, Any],
    *,
    approved_at: str,
) -> dict[str, Any]:
    return {
        "approval_id": _approval_id(str(row.get("dp_id") or "")),
        "dp_id": row.get("dp_id"),
        "approval_status": "approved",
        "approval_scope": "runtime_target_scope",
        "reviewer": "codex-deterministic-scope-review",
        "approved_at": approved_at,
        "target_scope_sha256": row.get("target_scope_sha256"),
        "payload_sha256": row.get("payload_sha256"),
        "risk_acknowledged": True,
        "review_basis": "deterministic neutral target-universe expansion with config/runtime A-share exact match",
        "target_scope_kind": (row.get("target_scope_policy") or {}).get("scope_kind")
        if isinstance(row.get("target_scope_policy"), Mapping)
        else None,
        "candidate_target_ts_code_count": row.get("candidate_target_ts_code_count"),
        "candidate_runtime_rows_would_write": row.get(
            "candidate_runtime_rows_would_write"
        ),
        "production_write_allowed": False,
    }


def _decision_for_row(row: Mapping[str, Any], *, approved_at: str) -> dict[str, Any]:
    errors = _target_scope_policy_errors(row)
    approval = None if errors else _approval_record(row, approved_at=approved_at)
    return {
        "dp_id": row.get("dp_id"),
        "score_target": row.get("score_target"),
        "target_scope_status": row.get("target_scope_status"),
        "target_scope_sha256": row.get("target_scope_sha256"),
        "candidate_target_ts_code_count": row.get("candidate_target_ts_code_count"),
        "approval_decision": "approved_runtime_target_scope"
        if approval
        else "scope_policy_rejected",
        "approval_record": approval,
        "validation_errors": errors,
    }


def build_report(
    *,
    target_scope_path: Path,
    approved_at: str | None = None,
) -> dict[str, Any]:
    payload = _load_json(target_scope_path)
    approved_at = approved_at or dt.datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    rows = [
        _decision_for_row(row, approved_at=approved_at)
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
        "inputs": {"target_scope_path": _portable_path(target_scope_path)},
        "summary": {
            "target_scope_row_count": len(rows),
            "scope_approval_record_count": len(approvals),
            "approved_runtime_target_scope_count": decision_counts.get(
                "approved_runtime_target_scope", 0
            ),
            "scope_policy_rejected_count": decision_counts.get(
                "scope_policy_rejected", 0
            ),
            "candidate_runtime_rows_would_write_count": sum(
                int(record.get("candidate_runtime_rows_would_write") or 0)
                for record in approvals
            ),
            "runtime_write_attempted_count": 0,
            "production_write_allowed_count": 0,
            "decision_counts": dict(sorted(decision_counts.items())),
            "score_mutation": "scope approval records only; no realtime_current or production score mutation",
        },
        "scope_approvals": approvals,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share runtime scope approvals",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Target-scope rows checked: `{summary['target_scope_row_count']}`",
        f"- Scope approval records: `{summary['scope_approval_record_count']}`",
        f"- Approved runtime target scopes: `{summary['approved_runtime_target_scope_count']}`",
        f"- Scope policy rejected: `{summary['scope_policy_rejected_count']}`",
        f"- Candidate runtime rows that would write if later approved: `{summary['candidate_runtime_rows_would_write_count']}`",
        f"- Runtime writes attempted: `{summary['runtime_write_attempted_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Approved Scope Records",
        "",
        "| dp_id | approval_id | target count | scope hash |",
        "|---|---|---:|---|",
    ]
    for approval in report.get("scope_approvals") or []:
        lines.append(
            "| "
            f"`{approval['dp_id']}` | "
            f"`{approval['approval_id']}` | "
            f"{approval.get('candidate_target_ts_code_count', 0)} | "
            f"`{str(approval.get('target_scope_sha256') or '')[:12]}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- These records approve only the deterministic target-universe expansion contract.",
            "- They do not create a controlled UPSERT batch and do not write runtime rows.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-scope-path", type=Path, default=DEFAULT_TARGET_SCOPE_PATH)
    parser.add_argument("--approvals-output", type=Path, default=DEFAULT_APPROVALS_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    args = parser.parse_args()

    report = build_report(target_scope_path=args.target_scope_path)
    args.approvals_output.parent.mkdir(parents=True, exist_ok=True)
    args.approvals_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
