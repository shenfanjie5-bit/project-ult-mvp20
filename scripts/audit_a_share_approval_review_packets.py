#!/usr/bin/env python3
"""Extract approval-review packets for concrete A-share candidate values.

This report is a read-only review bundle. It gathers the 12 concrete packets
that already validate and bridge to final-score targets, then attaches payload
hashes and incomplete approval templates. It never marks a packet approved.
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
DEFAULT_MANIFEST_PATH = ROOT / "docs/audit/a_share_review_staging_manifest_2026-06-19.json"
DEFAULT_APPROVAL_GATE_PATH = ROOT / "docs/audit/a_share_review_approval_gate_2026-06-19.json"
DEFAULT_NEXT_ACTIONS_PATH = ROOT / "docs/audit/a_share_completion_next_actions_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_approval_review_packets_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_approval_review_packets_2026-06-19.md"


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


def _rows_by_dp(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = dict(row)
    return rows


def _payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fallback_template(dp_id: str, payload_sha256: str) -> dict[str, Any]:
    return {
        "approval_id": "",
        "dp_id": dp_id,
        "approval_status": "",
        "approval_scope": "runtime_write",
        "reviewer": "",
        "approved_at": "",
        "payload_sha256": payload_sha256,
        "risk_acknowledged": False,
        "template_status": "review_fill_required",
    }


def _template_errors(
    *,
    template: Mapping[str, Any],
    dp_id: str,
    payload_sha256: str,
) -> list[str]:
    errors: list[str] = []
    if template.get("approval_id") != "":
        errors.append("approval_id must be blank in template")
    if template.get("dp_id") != dp_id:
        errors.append("dp_id must match review packet")
    if template.get("approval_status") != "":
        errors.append("approval_status must be blank in template")
    if template.get("approval_scope") != "runtime_write":
        errors.append("approval_scope must be runtime_write")
    if template.get("reviewer") != "":
        errors.append("reviewer must be blank in template")
    if template.get("approved_at") != "":
        errors.append("approved_at must be blank in template")
    if template.get("payload_sha256") != payload_sha256:
        errors.append("payload_sha256 must match review payload")
    if template.get("risk_acknowledged") is not False:
        errors.append("risk_acknowledged must be false in template")
    if template.get("template_status") != "review_fill_required":
        errors.append("template_status must be review_fill_required")
    return errors


def _is_review_packet_ready(manifest_row: Mapping[str, Any]) -> bool:
    bridge = manifest_row.get("bridge_validation")
    bridge = bridge if isinstance(bridge, Mapping) else {}
    return (
        manifest_row.get("review_entry_status") == "review_ready_concrete"
        and bool(manifest_row.get("source_contract_valid"))
        and bool(manifest_row.get("bridge_ready_concrete"))
        and bool(bridge.get("final_score_target_ready"))
    )


def _review_packet(
    manifest_row: Mapping[str, Any],
    approval_row: Mapping[str, Any] | None,
    next_action_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    dp_id = str(manifest_row.get("dp_id") or "")
    payload = manifest_row.get("review_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    payload_sha256 = _payload_hash(payload)
    approval_payload_sha256 = str((approval_row or {}).get("payload_sha256") or "")
    approval_payload_hash_matches_manifest = (
        bool(approval_payload_sha256) and approval_payload_sha256 == payload_sha256
    )
    approval_gate_status = str((approval_row or {}).get("approval_gate_status") or "")
    if (
        approval_gate_status == "approved_runtime_write"
        and not approval_payload_hash_matches_manifest
    ):
        approval_gate_status = "approval_hash_mismatch"
    approval_template = None
    if approval_gate_status != "approved_runtime_write":
        approval_template = (next_action_row or {}).get("approval_record_template")
    if approval_gate_status != "approved_runtime_write" and not isinstance(
        approval_template, Mapping
    ):
        approval_template = _fallback_template(dp_id, payload_sha256)
    template_validation_errors = (
        _template_errors(
            template=approval_template,
            dp_id=dp_id,
            payload_sha256=payload_sha256,
        )
        if isinstance(approval_template, Mapping)
        else []
    )
    value_json = payload.get("value_json")
    value_json = value_json if isinstance(value_json, Mapping) else {}
    bridge = manifest_row.get("bridge_validation")
    bridge = bridge if isinstance(bridge, Mapping) else {}
    return {
        "dp_id": dp_id,
        "score_target": manifest_row.get("score_target"),
        "source_kind": manifest_row.get("source_kind"),
        "source_report": manifest_row.get("source_report"),
        "source_dependencies": manifest_row.get("source_dependencies") or [],
        "data_status": manifest_row.get("data_status"),
        "payload_sha256": payload_sha256,
        "approval_payload_sha256": approval_payload_sha256,
        "approval_payload_hash_matches_manifest": (
            approval_payload_hash_matches_manifest
        ),
        "value_json": value_json,
        "confidence": payload.get("confidence"),
        "evidence_refs": payload.get("evidence_refs") or [],
        "rationale": payload.get("rationale"),
        "bridge_validation": bridge,
        "final_score_target_ready": bool(bridge.get("final_score_target_ready")),
        "approval_gate_status": approval_gate_status,
        "approval_record_template": (
            dict(approval_template) if isinstance(approval_template, Mapping) else None
        ),
        "approval_record_template_contract_valid": not template_validation_errors,
        "approval_record_template_validation_errors": template_validation_errors,
        "review_checklist": [
            "confirm field semantics and score_target are correct",
            "inspect evidence_refs and source dependencies",
            "confirm value_json bounds and neutral/NotApplicable handling",
            "confirm bridge_validation.final_score_target_ready is true",
            "confirm confidence is acceptable for runtime write",
            "fill approval_status=approved only after review",
            "set risk_acknowledged=true only after accepting score impact",
        ],
        "runtime_write_allowed": bool((approval_row or {}).get("runtime_write_allowed"))
        and approval_gate_status == "approved_runtime_write",
        "production_write_allowed": False,
    }


def build_report(
    *,
    manifest_path: Path,
    approval_gate_path: Path,
    next_actions_path: Path,
) -> dict[str, Any]:
    started = time.time()
    manifest = _load_json(manifest_path)
    approval_gate = _load_json(approval_gate_path)
    approval_gate_summary = approval_gate.get("summary") or {}
    next_actions = _load_json(next_actions_path)
    approval_rows = _rows_by_dp(approval_gate)
    next_action_rows = _rows_by_dp(next_actions)
    manifest_rows = [
        row for row in (manifest.get("rows") or []) if isinstance(row, Mapping)
    ]
    skipped_not_ready_rows = [
        str(row.get("dp_id") or "")
        for row in manifest_rows
        if row.get("review_entry_status") == "review_ready_concrete"
        and not _is_review_packet_ready(row)
    ]
    rows = [
        _review_packet(
            row,
            approval_rows.get(str(row.get("dp_id") or "")),
            next_action_rows.get(str(row.get("dp_id") or "")),
        )
        for row in manifest_rows
        if _is_review_packet_ready(row)
    ]
    rows.sort(key=lambda row: (str(row.get("score_target") or ""), str(row["dp_id"])))
    score_target_counts = Counter(str(row.get("score_target") or "") for row in rows)
    source_kind_counts = Counter(str(row.get("source_kind") or "") for row in rows)
    data_status_counts = Counter(str(row.get("data_status") or "") for row in rows)
    invalid_template_rows = [
        row
        for row in rows
        if row.get("approval_record_template") is not None
        and not row.get("approval_record_template_contract_valid")
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "manifest_path": _portable_path(manifest_path),
            "approval_gate_path": _portable_path(approval_gate_path),
            "next_actions_path": _portable_path(next_actions_path),
        },
        "summary": {
            "approval_review_packet_count": len(rows),
            "known_packet_count": data_status_counts.get("Known", 0),
            "not_applicable_packet_count": data_status_counts.get("NotApplicable", 0),
            "final_score_target_ready_count": sum(
                1 for row in rows if row.get("final_score_target_ready")
            ),
            "approval_missing_count": sum(
                1 for row in rows if row.get("approval_gate_status") == "approval_missing"
            ),
            "approval_record_template_count": sum(
                1 for row in rows if row.get("approval_record_template")
            ),
            "approval_record_template_contract_valid_count": sum(
                1
                for row in rows
                if row.get("approval_record_template") is not None
                and row.get("approval_record_template_contract_valid")
            ),
            "approval_record_template_contract_invalid_count": len(invalid_template_rows),
            "approval_record_template_invalid_dp_ids": [
                str(row.get("dp_id") or "") for row in invalid_template_rows
            ],
            "skipped_not_bridge_or_contract_ready_count": len(skipped_not_ready_rows),
            "skipped_not_bridge_or_contract_ready_dp_ids": skipped_not_ready_rows,
            "approval_payload_hash_mismatch_count": sum(
                1
                for row in rows
                if row.get("approval_payload_sha256")
                and not row.get("approval_payload_hash_matches_manifest")
            ),
            "approved_runtime_write_count": int(
                approval_gate_summary.get("approved_runtime_write_count") or 0
            ),
            "write_plan_count": int(approval_gate_summary.get("write_plan_count") or 0),
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "score_target_counts": dict(sorted(score_target_counts.items())),
            "source_kind_counts": dict(sorted(source_kind_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share approval review packets",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Approval-review packets: `{summary['approval_review_packet_count']}`",
        f"- Known packets: `{summary['known_packet_count']}`",
        f"- NotApplicable packets: `{summary['not_applicable_packet_count']}`",
        f"- Final-score-target ready: `{summary['final_score_target_ready_count']}`",
        f"- Missing approvals: `{summary['approval_missing_count']}`",
        f"- Approval templates: `{summary['approval_record_template_count']}`",
        f"- Approval template contracts valid: `{summary['approval_record_template_contract_valid_count']}`",
        f"- Approval template contracts invalid: `{summary['approval_record_template_contract_invalid_count']}`",
        f"- Skipped not bridge/contract ready: `{summary['skipped_not_bridge_or_contract_ready_count']}`",
        f"- Approval payload hash mismatches: `{summary['approval_payload_hash_mismatch_count']}`",
        f"- Approved runtime writes: `{summary['approved_runtime_write_count']}`",
        f"- Write-plan entries: `{summary['write_plan_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Packets",
        "",
        "| dp_id | target | status | source | confidence | payload hash | bridge-ready |",
        "|---|---|---|---|---:|---|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row.get('score_target', '-')}` | "
            f"`{row.get('data_status', '-')}` | "
            f"`{row.get('source_kind', '-')}` | "
            f"{row.get('confidence')} | "
            f"`{str(row.get('payload_sha256') or '')[:12]}` | "
            f"{'yes' if row.get('final_score_target_ready') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- These packets are review-ready, not approved.",
            "- Approval templates are intentionally incomplete and cannot be used as valid approvals without reviewer input.",
            "- The report does not write runtime values or change scores.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--approval-gate-path", type=Path, default=DEFAULT_APPROVAL_GATE_PATH)
    parser.add_argument("--next-actions-path", type=Path, default=DEFAULT_NEXT_ACTIONS_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        manifest_path=args.manifest_path,
        approval_gate_path=args.approval_gate_path,
        next_actions_path=args.next_actions_path,
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
