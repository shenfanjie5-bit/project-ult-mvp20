#!/usr/bin/env python3
"""Extract blank confirmation templates for L0.demand.penetration review.

This bundle is intentionally not a reviewer confirmation input. It copies the
blank ``confirmation_record_template`` objects from the confirmation-packet
audit, validates that reviewer/status/timestamp fields remain empty and all
acceptance booleans remain false, and keeps every write/escalation count at 0.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACKETS_PATH = (
    ROOT
    / "docs/audit/a_share_unknown_penetration_value_confirmation_packets_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_penetration_value_confirmation_templates_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_penetration_value_confirmation_templates_2026-06-19.md"
)
FORBIDDEN_CONFIRMATIONS_PATH = (
    ROOT / "docs/audit/a_share_unknown_penetration_value_confirmations_2026-06-19.json"
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


def _template_errors(template: Mapping[str, Any], packet: Mapping[str, Any]) -> list[str]:
    dp_id = str(packet.get("dp_id") or "")
    payload_sha256 = str(packet.get("payload_sha256") or "")
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
    if packet.get("confirmation_record_template_contract_valid") is not True:
        errors.append("source packet template contract must be valid")
    if packet.get("confirmation_packet_contract_valid") is not True:
        errors.append("source confirmation packet contract must be valid")
    for key in (
        "known_draft_sufficient",
        "approval_ready",
        "runtime_write_allowed",
        "production_write_allowed",
    ):
        if packet.get(key) is True:
            errors.append(f"source packet {key} must not be true")
    return errors


def _template_row(packet: Mapping[str, Any]) -> dict[str, Any]:
    template = packet.get("confirmation_record_template")
    template = template if isinstance(template, Mapping) else {}
    errors = _template_errors(template, packet)
    return {
        "dp_id": packet.get("dp_id"),
        "score_target": packet.get("score_target"),
        "source_report": "a_share_unknown_penetration_value_confirmation_packets_2026-06-19.json",
        "source_value_review_packet_id": packet.get("value_review_packet_id"),
        "payload_sha256": packet.get("payload_sha256"),
        "confirmation_record_template": dict(template),
        "blank_pending_template": not errors,
        "blank_pending_template_contract_valid": not errors,
        "blank_pending_template_validation_errors": errors,
        "confirmation_record_input_ready": False,
        "confirmed_template": False,
        "known_draft_sufficient": False,
        "approval_ready": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def build_report(*, packets_path: Path) -> dict[str, Any]:
    started = time.time()
    packets = _load_json(packets_path)
    packet_rows = [
        row
        for row in _rows(packets)
        if str(row.get("dp_id") or "") == "L0.demand.penetration"
    ]
    rows = [_template_row(packet) for packet in packet_rows]
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    invalid_rows = [
        row for row in rows if not row.get("blank_pending_template_contract_valid")
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "packets_path": _portable_path(packets_path),
            "forbidden_confirmations_path": _portable_path(FORBIDDEN_CONFIRMATIONS_PATH),
            "forbidden_confirmations_file_exists": FORBIDDEN_CONFIRMATIONS_PATH.exists(),
            "forbidden_confirmations_file_created": False,
        },
        "summary": {
            "source_confirmation_packet_count": len(packet_rows),
            "confirmation_template_bundle_count": len(rows),
            "confirmation_template_count": len(rows),
            "blank_pending_template_count": sum(
                1 for row in rows if row.get("blank_pending_template")
            ),
            "blank_pending_template_contract_valid_count": len(rows) - len(invalid_rows),
            "blank_pending_template_contract_invalid_count": len(invalid_rows),
            "blank_pending_template_invalid_dp_ids": [
                str(row.get("dp_id") or "") for row in invalid_rows
            ],
            "confirmation_record_input_ready_count": 0,
            "confirmed_template_count": 0,
            "known_draft_sufficient_count": 0,
            "approval_ready_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "score_mutation": "none; template bundle only and no realtime_current mutation",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown penetration value confirmation templates",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Source confirmation packets: `{summary['source_confirmation_packet_count']}`",
        f"- Confirmation templates: `{summary['confirmation_template_count']}`",
        f"- Blank pending templates: `{summary['blank_pending_template_count']}`",
        f"- Blank pending template contracts valid: `{summary['blank_pending_template_contract_valid_count']}`",
        f"- Confirmation-record inputs ready: `{summary['confirmation_record_input_ready_count']}`",
        f"- Confirmed templates: `{summary['confirmed_template_count']}`",
        f"- Known-draft sufficient: `{summary['known_draft_sufficient_count']}`",
        f"- Approval-ready rows: `{summary['approval_ready_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Templates",
        "",
        "| dp_id | payload hash | blank pending | input ready | errors |",
        "|---|---|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row.get('dp_id')}` | "
            f"`{str(row.get('payload_sha256') or '')[:12]}` | "
            f"{'yes' if row.get('blank_pending_template') else 'no'} | "
            f"{'yes' if row.get('confirmation_record_input_ready') else 'no'} | "
            f"{'; '.join(row.get('blank_pending_template_validation_errors') or []) or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This bundle is copied only from confirmation-packet templates.",
            "- It is not the reviewer confirmation input file and must not be renamed into one.",
            "- Blank templates cannot emit Known drafts, approval-ready rows, runtime writes, or production writes.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packets-path", type=Path, default=DEFAULT_PACKETS_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(packets_path=args.packets_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
