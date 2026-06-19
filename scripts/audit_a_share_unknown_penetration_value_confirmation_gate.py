#!/usr/bin/env python3
"""Validate human confirmations for L0.demand.penetration value policy.

The value-confirmation packet is not itself approval. This gate requires a
separate confirmation record tied to the exact proposed payload hash before a
later controlled step may emit a Known draft. It remains read-only and never
writes runtime values.
"""

from __future__ import annotations

import argparse
import datetime as dt
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
DEFAULT_PACKETS_PATH = (
    ROOT
    / "docs/audit/a_share_unknown_penetration_value_confirmation_packets_2026-06-19.json"
)
DEFAULT_CONFIRMATIONS_PATH = (
    ROOT / "docs/audit/a_share_unknown_penetration_value_confirmations_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_penetration_value_confirmation_gate_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_penetration_value_confirmation_gate_2026-06-19.md"
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


def _confirmation_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_records = payload.get("confirmations", payload.get("rows", []))
    if not isinstance(raw_records, list):
        return []
    return [dict(record) for record in raw_records if isinstance(record, Mapping)]


def _records_by_dp(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        dp_id = str(record.get("dp_id") or "")
        if dp_id:
            out.setdefault(dp_id, []).append(record)
    return out


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _confirmation_snapshot(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return {
        "confirmation_id": record.get("confirmation_id"),
        "dp_id": record.get("dp_id"),
        "confirmation_status": record.get("confirmation_status"),
        "confirmation_scope": record.get("confirmation_scope"),
        "reviewer": record.get("reviewer"),
        "confirmed_at": record.get("confirmed_at"),
        "payload_sha256": record.get("payload_sha256"),
        "value_selection_accepted": record.get("value_selection_accepted"),
        "bounds_accepted": record.get("bounds_accepted"),
        "formula_policy_accepted": record.get("formula_policy_accepted"),
        "applicability_accepted": record.get("applicability_accepted"),
        "risk_acknowledged": record.get("risk_acknowledged"),
    }


def _validate_confirmation(
    *,
    dp_id: str,
    payload_sha256: str,
    records: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[str]]:
    if not records:
        return None, ["missing confirmation record"]
    if len(records) > 1:
        return records[0], ["multiple confirmation records for dp_id"]
    record = records[0]
    errors: list[str] = []
    if record.get("dp_id") != dp_id:
        errors.append("confirmation dp_id does not match packet dp_id")
    if not _nonempty_string(record.get("confirmation_id")):
        errors.append("confirmation_id must be non-empty")
    if record.get("confirmation_status") != "confirmed":
        errors.append("confirmation_status must be confirmed")
    if record.get("confirmation_scope") != "value_policy":
        errors.append("confirmation_scope must be value_policy")
    if not _nonempty_string(record.get("reviewer")):
        errors.append("reviewer must be non-empty")
    if not _nonempty_string(record.get("confirmed_at")):
        errors.append("confirmed_at must be non-empty")
    if record.get("payload_sha256") != payload_sha256:
        errors.append("payload_sha256 must match the canonical proposed payload hash")
    for key in (
        "value_selection_accepted",
        "bounds_accepted",
        "formula_policy_accepted",
        "applicability_accepted",
        "risk_acknowledged",
    ):
        if record.get(key) is not True:
            errors.append(f"{key} must be true")
    return record, errors


def _known_draft_candidate(
    *,
    packet: Mapping[str, Any],
    payload_sha256: str,
    confirmation: Mapping[str, Any],
) -> dict[str, Any]:
    proposed_payload = packet.get("proposed_payload")
    proposed_payload = proposed_payload if isinstance(proposed_payload, Mapping) else {}
    return {
        "dp_id": packet.get("dp_id"),
        "score_target": packet.get("score_target"),
        "data_status": "Known",
        "payload_sha256": payload_sha256,
        "proposed_payload": proposed_payload,
        "confirmation": {
            "confirmation_id": confirmation.get("confirmation_id"),
            "reviewer": confirmation.get("reviewer"),
            "confirmed_at": confirmation.get("confirmed_at"),
            "confirmation_scope": confirmation.get("confirmation_scope"),
        },
        "known_draft_emission_allowed": True,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def build_report(*, packets_path: Path, confirmations_path: Path) -> dict[str, Any]:
    started = time.time()
    packets = _load_json(packets_path)
    confirmation_payload = _load_json(confirmations_path)
    confirmations_file_exists = confirmations_path.exists()
    confirmation_records = _confirmation_records(confirmation_payload)
    records_by_dp = _records_by_dp(confirmation_records)
    packet_rows = _rows(packets)
    packet_dp_ids = {str(row.get("dp_id") or "") for row in packet_rows}
    orphan_records = [
        _confirmation_snapshot(record)
        for record in confirmation_records
        if str(record.get("dp_id") or "") not in packet_dp_ids
    ]

    rows: list[dict[str, Any]] = []
    known_draft_candidates: list[dict[str, Any]] = []
    for packet in packet_rows:
        dp_id = str(packet.get("dp_id") or "")
        payload_sha256 = str(packet.get("payload_sha256") or "")
        records = records_by_dp.get(dp_id, [])
        record, validation_errors = _validate_confirmation(
            dp_id=dp_id,
            payload_sha256=payload_sha256,
            records=records,
        )
        packet_errors: list[str] = []
        if packet.get("confirmation_packet_contract_valid") is not True:
            packet_errors.append("confirmation packet contract must be valid")
        if packet.get("confirmation_record_template_contract_valid") is not True:
            packet_errors.append("confirmation template contract must be valid")
        if not packet.get("final_score_target_ready"):
            packet_errors.append("confirmation packet must bridge to final-score target")
        if not packet.get("value_policy_draft_ready"):
            packet_errors.append("value-policy draft must be ready")

        if packet_errors:
            gate_status = "packet_contract_invalid"
            all_errors = packet_errors + validation_errors
        elif not records:
            gate_status = "confirmation_missing"
            all_errors = ["missing confirmation record"]
        elif validation_errors:
            gate_status = "confirmation_rejected"
            all_errors = validation_errors
        else:
            gate_status = "confirmed_value_policy"
            all_errors = []

        known_draft_candidate = None
        if gate_status == "confirmed_value_policy":
            known_draft_candidate = _known_draft_candidate(
                packet=packet,
                payload_sha256=payload_sha256,
                confirmation=record or {},
            )
            known_draft_candidates.append(known_draft_candidate)

        rows.append(
            {
                "dp_id": dp_id,
                "score_target": packet.get("score_target"),
                "payload_sha256": payload_sha256,
                "confirmation_gate_status": gate_status,
                "confirmation_record_count": len(records),
                "confirmation_record": _confirmation_snapshot(record),
                "confirmation_validation_errors": all_errors,
                "proposed_raw_value": packet.get("proposed_raw_value"),
                "proposed_value_json": packet.get("proposed_value_json") or {},
                "final_score_target_ready": bool(packet.get("final_score_target_ready")),
                "value_policy_draft_ready": bool(packet.get("value_policy_draft_ready")),
                "known_draft_candidate": known_draft_candidate,
                "known_draft_emission_allowed": (
                    gate_status == "confirmed_value_policy"
                ),
                "approval_ready": False,
                "runtime_write_allowed": False,
                "production_write_allowed": False,
            }
        )

    status_counts = Counter(str(row.get("confirmation_gate_status") or "") for row in rows)
    rejected_count = status_counts.get("confirmation_rejected", 0) + len(orphan_records)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "packets_path": _portable_path(packets_path),
            "confirmations_path": _portable_path(confirmations_path),
            "confirmations_file_exists": confirmations_file_exists,
        },
        "summary": {
            "confirmation_packet_count": len(rows),
            "confirmation_required_count": len(rows),
            "confirmation_records_seen": len(confirmation_records),
            "orphan_confirmation_record_count": len(orphan_records),
            "orphan_confirmation_records": orphan_records,
            "confirmation_missing_count": status_counts.get("confirmation_missing", 0),
            "rejected_confirmation_count": rejected_count,
            "confirmed_value_policy_count": status_counts.get(
                "confirmed_value_policy", 0
            ),
            "packet_contract_invalid_count": status_counts.get(
                "packet_contract_invalid", 0
            ),
            "known_draft_candidate_count": len(known_draft_candidates),
            "known_draft_emission_allowed_count": len(known_draft_candidates),
            "approval_ready_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "confirmation_gate_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; confirmation gate only and no realtime_current mutation",
        },
        "known_draft_candidates": known_draft_candidates,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown penetration value confirmation gate",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Confirmation packets: `{summary['confirmation_packet_count']}`",
        f"- Confirmation records seen: `{summary['confirmation_records_seen']}`",
        f"- Missing confirmations: `{summary['confirmation_missing_count']}`",
        f"- Rejected confirmations: `{summary['rejected_confirmation_count']}`",
        f"- Confirmed value policies: `{summary['confirmed_value_policy_count']}`",
        f"- Known draft candidates: `{summary['known_draft_candidate_count']}`",
        f"- Approval-ready rows: `{summary['approval_ready_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Gate statuses",
        "",
        "| status | count |",
        "|---|---:|",
    ]
    for status, count in summary["confirmation_gate_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")
    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | status | records | known draft allowed | errors |",
            "|---|---|---:|---:|---|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row.get('dp_id')}` | "
            f"`{row.get('confirmation_gate_status')}` | "
            f"{row.get('confirmation_record_count')} | "
            f"{'yes' if row.get('known_draft_emission_allowed') else 'no'} | "
            f"{'; '.join(row.get('confirmation_validation_errors') or []) or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- A confirmation record must be separate from the packet and must match the proposed payload hash.",
            "- Missing or rejected confirmations cannot emit Known drafts.",
            "- Confirmed value policies can feed a later Known-draft step, but this gate still allows no runtime or production writes.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packets-path", type=Path, default=DEFAULT_PACKETS_PATH)
    parser.add_argument(
        "--confirmations-path", type=Path, default=DEFAULT_CONFIRMATIONS_PATH
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        packets_path=args.packets_path,
        confirmations_path=args.confirmations_path,
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
