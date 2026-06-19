#!/usr/bin/env python3
"""Emit review-only Known drafts after penetration value confirmation.

This report consumes the value-confirmation gate. Only rows with a confirmed
value policy may become Known draft candidates for a later staging step. The
report is read-only: it does not create approval records, does not write
runtime values, and does not mutate production scores.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_review_staging_manifest import _bridge_validation  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIRMATION_GATE_PATH = (
    ROOT
    / "docs/audit/a_share_unknown_penetration_value_confirmation_gate_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_penetration_confirmed_known_drafts_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_penetration_confirmed_known_drafts_2026-06-19.md"
)


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _validate_known_draft(candidate: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    dp_id = str(candidate.get("dp_id") or "")
    score_target = str(candidate.get("score_target") or "")
    payload = candidate.get("proposed_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    value_json = payload.get("value_json")
    value_json = value_json if isinstance(value_json, Mapping) else {}
    confirmation = candidate.get("confirmation")
    confirmation = confirmation if isinstance(confirmation, Mapping) else {}
    payload_sha256 = str(candidate.get("payload_sha256") or "")

    if dp_id != "L0.demand.penetration":
        errors.append("dp_id must be L0.demand.penetration")
    if score_target != "fundamental_score":
        errors.append("score_target must be fundamental_score")
    if not payload:
        errors.append("proposed_payload must be present")
    if payload.get("target_dp_id") != dp_id:
        errors.append("payload target_dp_id must match dp_id")
    if payload.get("score_target") != score_target:
        errors.append("payload score_target must match candidate score_target")
    if payload.get("data_status") != "Known":
        errors.append("payload data_status must be Known")
    if payload.get("bridge_entry_data_status") not in {None, "Known"}:
        errors.append("bridge_entry_data_status must be Known if present")
    if not value_json:
        errors.append("payload value_json must be present")
    if value_json.get("review_required") is not True:
        errors.append("value_json.review_required must stay true before staging")
    score = _safe_float(value_json.get("score"))
    if score is None or not 0.0 <= score <= 1.0:
        errors.append("value_json.score must be finite and in [0, 1]")
    if payload.get("review_status") != "review_required":
        errors.append("payload review_status must remain review_required")
    if payload.get("safe_to_upsert_without_review") is not False:
        errors.append("safe_to_upsert_without_review must be false")
    if payload.get("production_write_allowed") is True:
        errors.append("production_write_allowed must not be true")
    if payload_sha256 != _payload_hash(payload):
        errors.append("payload_sha256 must match proposed_payload")
    if not confirmation.get("confirmation_id"):
        errors.append("confirmation_id must be present")
    if not confirmation.get("reviewer"):
        errors.append("confirmation reviewer must be present")
    if not confirmation.get("confirmed_at"):
        errors.append("confirmation confirmed_at must be present")
    bridge = _bridge_validation(dp_id, score_target, payload) if payload else {}
    if not bridge.get("final_score_target_ready"):
        errors.append("known draft payload must bridge to final-score target")
    return bridge, errors


def _emitted_row(candidate: Mapping[str, Any]) -> dict[str, Any]:
    bridge, errors = _validate_known_draft(candidate)
    payload = candidate.get("proposed_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    return {
        "dp_id": candidate.get("dp_id"),
        "score_target": candidate.get("score_target"),
        "source_kind": "penetration_confirmed_value_policy",
        "source_report": "a_share_unknown_penetration_value_confirmation_gate_2026-06-19.json",
        "known_draft_status": "known_draft_emitted" if not errors else "known_draft_contract_invalid",
        "data_status": "Known",
        "payload_sha256": candidate.get("payload_sha256"),
        "draft_payload": dict(payload),
        "confirmation": candidate.get("confirmation") or {},
        "bridge_validation": bridge,
        "final_score_target_ready": bool(bridge.get("final_score_target_ready")),
        "known_draft_contract_valid": not errors,
        "known_draft_validation_errors": errors,
        "ready_for_review_staging": not errors,
        "approval_ready": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def _blocked_row(gate_row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "dp_id": gate_row.get("dp_id"),
        "score_target": gate_row.get("score_target"),
        "source_kind": "penetration_confirmed_value_policy",
        "source_report": "a_share_unknown_penetration_value_confirmation_gate_2026-06-19.json",
        "known_draft_status": f"blocked_{gate_row.get('confirmation_gate_status') or 'unknown'}",
        "data_status": "Unknown",
        "payload_sha256": gate_row.get("payload_sha256"),
        "draft_payload": None,
        "confirmation": gate_row.get("confirmation_record"),
        "bridge_validation": {},
        "final_score_target_ready": bool(gate_row.get("final_score_target_ready")),
        "known_draft_contract_valid": False,
        "known_draft_validation_errors": [
            str(item) for item in gate_row.get("confirmation_validation_errors") or []
        ],
        "ready_for_review_staging": False,
        "approval_ready": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def build_report(*, confirmation_gate_path: Path) -> dict[str, Any]:
    started = time.time()
    confirmation_gate = _load_json(confirmation_gate_path)
    candidates = [
        dict(row)
        for row in confirmation_gate.get("known_draft_candidates") or []
        if isinstance(row, Mapping)
    ]
    candidate_dp_ids = {str(row.get("dp_id") or "") for row in candidates}
    rows = [_emitted_row(candidate) for candidate in candidates]
    for gate_row in confirmation_gate.get("rows") or []:
        if not isinstance(gate_row, Mapping):
            continue
        dp_id = str(gate_row.get("dp_id") or "")
        if dp_id and dp_id not in candidate_dp_ids:
            rows.append(_blocked_row(gate_row))

    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    status_counts = Counter(str(row.get("known_draft_status") or "") for row in rows)
    valid_rows = [row for row in rows if row.get("known_draft_contract_valid")]
    invalid_rows = [
        row
        for row in rows
        if row.get("known_draft_status") == "known_draft_contract_invalid"
    ]
    emitted_rows = [
        row for row in rows if row.get("known_draft_status") == "known_draft_emitted"
    ]
    blocked_rows = [
        row
        for row in rows
        if str(row.get("known_draft_status") or "").startswith("blocked_")
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "confirmation_gate_path": _portable_path(confirmation_gate_path),
        },
        "summary": {
            "confirmation_gate_row_count": len(confirmation_gate.get("rows") or []),
            "confirmed_value_policy_candidate_count": len(candidates),
            "known_draft_row_count": len(rows),
            "known_draft_emitted_count": len(emitted_rows),
            "known_draft_blocked_count": len(blocked_rows),
            "known_draft_contract_valid_count": len(valid_rows),
            "known_draft_contract_invalid_count": len(invalid_rows),
            "ready_for_review_staging_count": sum(
                1 for row in rows if row.get("ready_for_review_staging")
            ),
            "final_score_target_ready_count": sum(
                1 for row in emitted_rows if row.get("final_score_target_ready")
            ),
            "approval_ready_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "known_draft_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; Known draft audit only and no realtime_current mutation",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown penetration confirmed Known drafts",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Confirmation-gate rows: `{summary['confirmation_gate_row_count']}`",
        f"- Confirmed value-policy candidates: `{summary['confirmed_value_policy_candidate_count']}`",
        f"- Known draft rows: `{summary['known_draft_row_count']}`",
        f"- Known drafts emitted: `{summary['known_draft_emitted_count']}`",
        f"- Known drafts blocked: `{summary['known_draft_blocked_count']}`",
        f"- Known draft contracts valid: `{summary['known_draft_contract_valid_count']}`",
        f"- Ready for review staging: `{summary['ready_for_review_staging_count']}`",
        f"- Approval-ready rows: `{summary['approval_ready_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Statuses",
        "",
        "| status | count |",
        "|---|---:|",
    ]
    for status, count in summary["known_draft_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")
    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | status | ready for staging | errors |",
            "|---|---|---:|---|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row.get('dp_id')}` | "
            f"`{row.get('known_draft_status')}` | "
            f"{'yes' if row.get('ready_for_review_staging') else 'no'} | "
            f"{'; '.join(row.get('known_draft_validation_errors') or []) or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This report only emits Known drafts when the confirmation gate has a confirmed value policy.",
            "- Emitted drafts are still review-only and require later staging/approval before runtime writes.",
            "- The current report writes no runtime data and changes no scores.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirmation-gate-path",
        type=Path,
        default=DEFAULT_CONFIRMATION_GATE_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(confirmation_gate_path=args.confirmation_gate_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
