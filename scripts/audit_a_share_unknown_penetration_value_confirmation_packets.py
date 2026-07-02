#!/usr/bin/env python3
"""Prepare human confirmation packets for L0.demand.penetration value policy.

This report packages the current reviewer-facing value-policy draft into a
hash-bound confirmation packet. The confirmation template is intentionally
blank and cannot authorize runtime writes. A later reviewer must explicitly
accept value selection, bounds, formula policy, applicability, and score impact
before a Known draft can be emitted by a separate controlled step.
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


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VALUE_POLICY_DRAFT_PATH = (
    ROOT / "docs/audit/a_share_unknown_penetration_value_policy_draft_2026-06-19.json"
)
DEFAULT_VALUE_SELECTION_GATE_PATH = (
    ROOT
    / "docs/audit/a_share_unknown_business_metric_value_selection_gate_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_penetration_value_confirmation_packets_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_penetration_value_confirmation_packets_2026-06-19.md"
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


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in payload.get("rows") or [] if isinstance(row, Mapping)]


def _rows_by_dp(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _rows(payload):
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            out[dp_id] = row
    return out


def _payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _confirmation_template(dp_id: str, payload_sha256: str) -> dict[str, Any]:
    return {
        "confirmation_id": "",
        "dp_id": dp_id,
        "confirmation_status": "",
        "confirmation_scope": "value_policy",
        "reviewer": "",
        "confirmed_at": "",
        "payload_sha256": payload_sha256,
        "value_selection_accepted": False,
        "bounds_accepted": False,
        "formula_policy_accepted": False,
        "applicability_accepted": False,
        "risk_acknowledged": False,
        "template_status": "review_fill_required",
    }


def _template_errors(
    template: Mapping[str, Any], *, dp_id: str, payload_sha256: str
) -> list[str]:
    expected = {
        "confirmation_id": "",
        "dp_id": dp_id,
        "confirmation_status": "",
        "confirmation_scope": "value_policy",
        "reviewer": "",
        "confirmed_at": "",
        "payload_sha256": payload_sha256,
        "value_selection_accepted": False,
        "bounds_accepted": False,
        "formula_policy_accepted": False,
        "applicability_accepted": False,
        "risk_acknowledged": False,
        "template_status": "review_fill_required",
    }
    errors: list[str] = []
    for key, expected_value in expected.items():
        if template.get(key) != expected_value:
            errors.append(f"{key} must be {expected_value!r}")
    return errors


def _packet_errors(draft: Mapping[str, Any], selection_gate_row: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    proposed_payload = draft.get("proposed_payload")
    proposed_payload = proposed_payload if isinstance(proposed_payload, Mapping) else {}
    proposed_value_json = draft.get("proposed_value_json")
    proposed_value_json = (
        proposed_value_json if isinstance(proposed_value_json, Mapping) else {}
    )
    bridge = draft.get("bridge_validation")
    bridge = bridge if isinstance(bridge, Mapping) else {}
    if draft.get("dp_id") != "L0.demand.penetration":
        errors.append("dp_id must be L0.demand.penetration")
    if not draft.get("draft_contract_valid"):
        errors.append("draft contract must be valid")
    if not draft.get("source_scope_confirmed"):
        errors.append("source scope must be confirmed")
    if not proposed_payload:
        errors.append("proposed_payload must be present")
    if not proposed_value_json:
        errors.append("proposed_value_json must be present")
    if proposed_value_json.get("review_required") is not True:
        errors.append("proposed_value_json.review_required must be true")
    if proposed_payload.get("review_status") != "review_required":
        errors.append("proposed_payload.review_status must be review_required")
    if proposed_payload.get("safe_to_upsert_without_review") is not False:
        errors.append("proposed payload must not be safe to upsert without review")
    if not bridge.get("final_score_target_ready"):
        errors.append("proposed payload must bridge to final-score target")
    if draft.get("known_draft_sufficient"):
        errors.append("draft must remain below Known-draft sufficient")
    if draft.get("approval_ready"):
        errors.append("draft must not be approval-ready")
    if draft.get("runtime_write_allowed"):
        errors.append("draft must not allow runtime writes")
    if draft.get("production_write_allowed"):
        errors.append("draft must not allow production writes")
    if selection_gate_row and not selection_gate_row.get("value_policy_draft_ready"):
        errors.append("selection gate must mark value_policy_draft_ready")
    return errors


def _confirmation_packet(
    draft: Mapping[str, Any], selection_gate_row: Mapping[str, Any]
) -> dict[str, Any]:
    dp_id = str(draft.get("dp_id") or "")
    proposed_payload = draft.get("proposed_payload")
    proposed_payload = proposed_payload if isinstance(proposed_payload, Mapping) else {}
    proposed_value_json = draft.get("proposed_value_json")
    proposed_value_json = (
        proposed_value_json if isinstance(proposed_value_json, Mapping) else {}
    )
    payload_sha256 = _payload_hash(proposed_payload) if proposed_payload else ""
    template = _confirmation_template(dp_id, payload_sha256)
    template_validation_errors = _template_errors(
        template, dp_id=dp_id, payload_sha256=payload_sha256
    )
    packet_validation_errors = _packet_errors(draft, selection_gate_row)
    bridge = draft.get("bridge_validation")
    bridge = bridge if isinstance(bridge, Mapping) else {}
    return {
        "dp_id": dp_id,
        "score_target": draft.get("score_target"),
        "value_review_packet_id": draft.get("value_review_packet_id"),
        "payload_sha256": payload_sha256,
        "source_scope_confirmed": bool(draft.get("source_scope_confirmed")),
        "proposed_raw_value": draft.get("proposed_raw_value"),
        "proposed_value_json": proposed_value_json,
        "proposed_payload": proposed_payload,
        "bridge_validation": dict(bridge),
        "final_score_target_ready": bool(bridge.get("final_score_target_ready")),
        "selection_gate_status": selection_gate_row.get("selection_gate_status"),
        "value_policy_draft_ready": bool(
            selection_gate_row.get("value_policy_draft_ready")
        ),
        "confirmation_record_template": template,
        "confirmation_record_template_contract_valid": not template_validation_errors,
        "confirmation_record_template_validation_errors": template_validation_errors,
        "confirmation_packet_contract_valid": not packet_validation_errors,
        "confirmation_packet_validation_errors": packet_validation_errors,
        "review_status": "review_required",
        "review_checklist": [
            "confirm the 40% source value is the intended issuer/industry metric",
            "confirm domestic listed-company electronic-gas scope is applicable to this stock universe",
            "confirm score = clamp(raw_percent / 100, 0, 1) is the accepted formula policy",
            "confirm bounds score_min=0 and score_max=1",
            "confirm runtime score impact is acceptable before any later Known draft",
            "fill confirmation_status=confirmed only after review",
            "set all acceptance booleans and risk_acknowledged=true only after review",
        ],
        "missing_before_known": [
            str(item) for item in draft.get("missing_before_known") or []
        ],
        "known_draft_sufficient": False,
        "approval_ready": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def build_report(
    *, value_policy_draft_path: Path, value_selection_gate_path: Path
) -> dict[str, Any]:
    started = time.time()
    value_policy_draft = _load_json(value_policy_draft_path)
    value_selection_gate = _load_json(value_selection_gate_path)
    gate_by_dp = _rows_by_dp(value_selection_gate)
    rows = [
        _confirmation_packet(draft, gate_by_dp.get(str(draft.get("dp_id") or ""), {}))
        for draft in _rows(value_policy_draft)
        if str(draft.get("dp_id") or "") == "L0.demand.penetration"
    ]
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    status_counts = Counter(str(row.get("review_status") or "") for row in rows)
    invalid_packets = [
        row for row in rows if not row.get("confirmation_packet_contract_valid")
    ]
    invalid_templates = [
        row
        for row in rows
        if not row.get("confirmation_record_template_contract_valid")
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "value_policy_draft_path": _portable_path(value_policy_draft_path),
            "value_selection_gate_path": _portable_path(value_selection_gate_path),
        },
        "summary": {
            "value_confirmation_packet_count": len(rows),
            "review_required_packet_count": status_counts.get("review_required", 0),
            "source_scope_confirmed_count": sum(
                1 for row in rows if row.get("source_scope_confirmed")
            ),
            "proposed_value_json_count": sum(
                1 for row in rows if row.get("proposed_value_json")
            ),
            "final_score_target_ready_count": sum(
                1 for row in rows if row.get("final_score_target_ready")
            ),
            "value_policy_draft_ready_count": sum(
                1 for row in rows if row.get("value_policy_draft_ready")
            ),
            "confirmation_record_template_count": sum(
                1 for row in rows if row.get("confirmation_record_template")
            ),
            "confirmation_record_template_contract_valid_count": len(rows)
            - len(invalid_templates),
            "confirmation_record_template_contract_invalid_count": len(invalid_templates),
            "confirmation_record_template_invalid_dp_ids": [
                str(row.get("dp_id") or "") for row in invalid_templates
            ],
            "confirmation_packet_contract_valid_count": len(rows) - len(invalid_packets),
            "confirmation_packet_contract_invalid_count": len(invalid_packets),
            "confirmation_packet_contract_invalid_dp_ids": [
                str(row.get("dp_id") or "") for row in invalid_packets
            ],
            "known_draft_sufficient_count": 0,
            "approval_ready_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "score_mutation": "none; confirmation packets only and no realtime_current mutation",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown penetration value confirmation packets",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Confirmation packets: `{summary['value_confirmation_packet_count']}`",
        f"- Review-required packets: `{summary['review_required_packet_count']}`",
        f"- Source scope confirmed: `{summary['source_scope_confirmed_count']}`",
        f"- Proposed value JSONs: `{summary['proposed_value_json_count']}`",
        f"- Final-score-target ready: `{summary['final_score_target_ready_count']}`",
        f"- Value-policy draft ready: `{summary['value_policy_draft_ready_count']}`",
        f"- Confirmation templates: `{summary['confirmation_record_template_count']}`",
        f"- Confirmation template contracts valid: `{summary['confirmation_record_template_contract_valid_count']}`",
        f"- Confirmation packet contracts valid: `{summary['confirmation_packet_contract_valid_count']}`",
        f"- Known-draft sufficient: `{summary['known_draft_sufficient_count']}`",
        f"- Approval-ready rows: `{summary['approval_ready_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Packets",
        "",
        "| dp_id | raw value | score | payload hash | template valid | packet valid | missing before Known |",
        "|---|---:|---:|---|---:|---:|---|",
    ]
    for row in report["rows"]:
        value = row.get("proposed_value_json") or {}
        lines.append(
            "| "
            f"`{row.get('dp_id')}` | "
            f"{row.get('proposed_raw_value')} | "
            f"{value.get('score')} | "
            f"`{str(row.get('payload_sha256') or '')[:12]}` | "
            f"{'yes' if row.get('confirmation_record_template_contract_valid') else 'no'} | "
            f"{'yes' if row.get('confirmation_packet_contract_valid') else 'no'} | "
            f"{', '.join(row.get('missing_before_known') or [])} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Confirmation packets are reviewer work items, not runtime approvals.",
            "- Confirmation templates are intentionally incomplete and cannot pass any write gate.",
            "- A later controlled step may emit a Known draft only after value selection, bounds, formula policy, applicability, and score impact are confirmed.",
            "- This report writes no runtime data and changes no scores.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--value-policy-draft-path",
        type=Path,
        default=DEFAULT_VALUE_POLICY_DRAFT_PATH,
    )
    parser.add_argument(
        "--value-selection-gate-path",
        type=Path,
        default=DEFAULT_VALUE_SELECTION_GATE_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        value_policy_draft_path=args.value_policy_draft_path,
        value_selection_gate_path=args.value_selection_gate_path,
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
