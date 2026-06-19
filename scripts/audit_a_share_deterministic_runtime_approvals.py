#!/usr/bin/env python3
"""Create runtime approval records for deterministic A-share review packets.

This is deliberately narrow. It approves only deterministic staging payloads
whose semantics are hard-gated by existing evidence and whose bridge contracts
are already ready. It does not approve event-LLM, local policy, manual policy,
or Unknown packets, and it never writes production score data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_review_approval_gate import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    _payload_hash,
    _validate_approval,
)
from scripts.audit_a_share_local_single_dependency_policy_drafts import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_APPROVALS_OUTPUT = ROOT / "docs/audit/a_share_review_approvals_2026-06-19.json"
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_deterministic_runtime_approvals_2026-06-19.md"
)


def _short_report_policy(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    value = payload.get("value_json")
    value = value if isinstance(value, Mapping) else {}
    errors: list[str] = []
    if payload.get("data_status") != "Known":
        errors.append("short-report payload must be Known")
    if value.get("score") != 0.0:
        errors.append("short-report score must be neutral 0.0")
    if int(value.get("news_html_files_scanned") or 0) <= 0:
        errors.append("short-report scan must include market HTML files")
    if int(value.get("direct_a_share_short_report_documents") or 0) != 0:
        errors.append("direct A-share short-report hits must be zero")
    return not errors, errors


def _gamma_not_applicable_policy(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    value = payload.get("value_json")
    value = value if isinstance(value, Mapping) else {}
    errors: list[str] = []
    if payload.get("data_status") != "NotApplicable":
        errors.append("gamma payload must be NotApplicable")
    if payload.get("bridge_entry_data_status") != "Known":
        errors.append("gamma bridge entry must be Known neutral")
    if value.get("multiplier") != 1.0:
        errors.append("gamma multiplier must be neutral 1.0")
    if value.get("applicability") != "a_share_single_stock_no_listed_option":
        errors.append("gamma applicability must state no listed single-stock option")
    return not errors, errors


DETERMINISTIC_POLICIES: dict[str, Callable[[Mapping[str, Any]], tuple[bool, list[str]]]] = {
    "L7.trade.gamma": _gamma_not_applicable_policy,
    "L9.media.short_report": _short_report_policy,
}


def _approval_id(dp_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", dp_id).strip("-").lower()
    return f"codex-deterministic-20260619-{slug}"


def _approval_record(
    *,
    row: Mapping[str, Any],
    payload_sha256: str,
    approved_at: str,
) -> dict[str, Any]:
    return {
        "approval_id": _approval_id(str(row.get("dp_id") or "")),
        "dp_id": row.get("dp_id"),
        "approval_status": "approved",
        "approval_scope": "runtime_write",
        "reviewer": "codex-deterministic-review",
        "approved_at": approved_at,
        "payload_sha256": payload_sha256,
        "risk_acknowledged": True,
        "review_basis": "deterministic staging payload with neutral/NotApplicable score impact and ready bridge contract",
        "source_kind": row.get("source_kind"),
        "source_report": row.get("source_report"),
        "score_target": row.get("score_target"),
        "data_status": row.get("data_status"),
        "production_write_allowed": False,
    }


def _decision_for_row(
    row: Mapping[str, Any],
    *,
    approved_at: str,
) -> dict[str, Any]:
    dp_id = str(row.get("dp_id") or "")
    payload = row.get("review_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    payload_sha256 = _payload_hash(payload)
    errors: list[str] = []

    if dp_id not in DETERMINISTIC_POLICIES:
        return {
            "dp_id": dp_id,
            "score_target": row.get("score_target"),
            "source_kind": row.get("source_kind"),
            "data_status": row.get("data_status"),
            "approval_decision": "not_in_deterministic_policy",
            "payload_sha256": payload_sha256,
            "approval_record": None,
            "validation_errors": [],
        }
    if row.get("source_kind") != "deterministic_candidate_staging":
        errors.append("source_kind must be deterministic_candidate_staging")
    if row.get("review_entry_status") != "review_ready_concrete":
        errors.append("review_entry_status must be review_ready_concrete")
    if row.get("bridge_ready_concrete") is not True:
        errors.append("bridge_ready_concrete must be true")
    if (row.get("contract_validation") or {}).get("contract_valid") is not True:
        errors.append("contract_validation.contract_valid must be true")
    if row.get("safe_to_upsert_without_review") is not False:
        errors.append("safe_to_upsert_without_review must be false")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    if float(payload.get("confidence") or 0.0) < 0.6:
        errors.append("confidence must be at least 0.6 for deterministic approval")

    policy_ok, policy_errors = DETERMINISTIC_POLICIES[dp_id](payload)
    if not policy_ok:
        errors.extend(policy_errors)

    if errors:
        return {
            "dp_id": dp_id,
            "score_target": row.get("score_target"),
            "source_kind": row.get("source_kind"),
            "data_status": row.get("data_status"),
            "approval_decision": "deterministic_policy_rejected",
            "payload_sha256": payload_sha256,
            "approval_record": None,
            "validation_errors": errors,
        }

    approval = _approval_record(
        row=row,
        payload_sha256=payload_sha256,
        approved_at=approved_at,
    )
    _record, approval_errors = _validate_approval(
        dp_id=dp_id,
        payload_sha256=payload_sha256,
        records=[approval],
    )
    return {
        "dp_id": dp_id,
        "score_target": row.get("score_target"),
        "source_kind": row.get("source_kind"),
        "data_status": row.get("data_status"),
        "approval_decision": "approved_deterministic_runtime_write",
        "payload_sha256": payload_sha256,
        "approval_record": approval if not approval_errors else None,
        "validation_errors": approval_errors,
    }


def build_report(*, manifest_path: Path, approved_at: str | None = None) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    approved_at = approved_at or dt.datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    rows = [
        _decision_for_row(row, approved_at=approved_at)
        for row in manifest.get("rows") or []
        if isinstance(row, Mapping)
    ]
    approvals = [
        row["approval_record"]
        for row in rows
        if isinstance(row.get("approval_record"), Mapping)
    ]
    decision_counts = Counter(str(row.get("approval_decision") or "") for row in rows)
    source_kind_counts = Counter(
        str(row.get("source_kind") or "") for row in rows if row.get("approval_record")
    )
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {"manifest_path": _portable_path(manifest_path)},
        "summary": {
            "manifest_row_count": len(rows),
            "deterministic_policy_count": len(DETERMINISTIC_POLICIES),
            "approval_record_count": len(approvals),
            "approved_deterministic_runtime_write_count": decision_counts.get(
                "approved_deterministic_runtime_write", 0
            ),
            "deterministic_policy_rejected_count": decision_counts.get(
                "deterministic_policy_rejected", 0
            ),
            "not_in_deterministic_policy_count": decision_counts.get(
                "not_in_deterministic_policy", 0
            ),
            "approval_contract_valid_count": sum(
                1 for row in rows if row.get("approval_record") is not None
            ),
            "production_write_allowed_count": 0,
            "source_kind_counts": dict(sorted(source_kind_counts.items())),
            "decision_counts": dict(sorted(decision_counts.items())),
            "score_mutation": "approval records only; no realtime_current or production score mutation",
        },
        "approvals": approvals,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share deterministic runtime approvals",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Manifest rows checked: `{summary['manifest_row_count']}`",
        f"- Approval records: `{summary['approval_record_count']}`",
        f"- Approved deterministic runtime writes: `{summary['approved_deterministic_runtime_write_count']}`",
        f"- Deterministic policy rejected: `{summary['deterministic_policy_rejected_count']}`",
        f"- Non-deterministic rows left unapproved: `{summary['not_in_deterministic_policy_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Approved Records",
        "",
        "| dp_id | target | status | approval_id | payload hash |",
        "|---|---|---|---|---|",
    ]
    for approval in report.get("approvals") or []:
        lines.append(
            "| "
            f"`{approval['dp_id']}` | "
            f"`{approval.get('score_target', '-')}` | "
            f"`{approval.get('data_status', '-')}` | "
            f"`{approval['approval_id']}` | "
            f"`{str(approval.get('payload_sha256') or '')[:12]}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Only deterministic neutral / NotApplicable staging payloads are approved here.",
            "- Event-text, local-policy, manual-policy, and Unknown packets remain unapproved.",
            "- Approval scope is `runtime_write`; production writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_APPROVALS_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--approved-at", default=None)
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        manifest_path=args.manifest_path,
        approved_at=args.approved_at,
    )
    if not args.no_write:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        args.md_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"ok": True, **report["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
