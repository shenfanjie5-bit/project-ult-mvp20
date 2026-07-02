#!/usr/bin/env python3
"""Validate the explicit approval gate for A-share review packets.

The review staging manifest can make concrete candidate packets review-ready,
but it is not an approval list. This audit verifies that runtime-write approval
requires a separate approval record tied to the exact review payload hash.
It remains read-only and never mutates realtime_current.
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
DEFAULT_APPROVALS_PATH = ROOT / "docs/audit/a_share_review_approvals_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_review_approval_gate_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_review_approval_gate_2026-06-19.md"


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


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _approval_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_records = payload.get("approvals", payload.get("rows", []))
    if not isinstance(raw_records, list):
        return []
    return [dict(record) for record in raw_records if isinstance(record, Mapping)]


def _records_by_dp(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_dp: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        dp_id = str(record.get("dp_id") or "")
        if dp_id:
            by_dp.setdefault(dp_id, []).append(record)
    return by_dp


def _approval_snapshot(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return {
        "approval_id": record.get("approval_id"),
        "dp_id": record.get("dp_id"),
        "approval_status": record.get("approval_status"),
        "approval_scope": record.get("approval_scope"),
        "reviewer": record.get("reviewer"),
        "approved_at": record.get("approved_at"),
        "payload_sha256": record.get("payload_sha256"),
        "risk_acknowledged": record.get("risk_acknowledged"),
    }


def _validate_approval(
    *,
    dp_id: str,
    payload_sha256: str,
    records: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[str]]:
    if not records:
        return None, ["missing approval record"]
    if len(records) > 1:
        return records[0], ["multiple approval records for dp_id"]
    record = records[0]
    errors: list[str] = []
    if record.get("dp_id") != dp_id:
        errors.append("approval dp_id does not match manifest dp_id")
    if not _nonempty_string(record.get("approval_id")):
        errors.append("approval_id must be non-empty")
    if record.get("approval_status") != "approved":
        errors.append("approval_status must be approved")
    if record.get("approval_scope") != "runtime_write":
        errors.append("approval_scope must be runtime_write")
    if not _nonempty_string(record.get("reviewer")):
        errors.append("reviewer must be non-empty")
    if not _nonempty_string(record.get("approved_at")):
        errors.append("approved_at must be non-empty")
    if record.get("payload_sha256") != payload_sha256:
        errors.append("payload_sha256 must match the canonical review payload hash")
    if record.get("risk_acknowledged") is not True:
        errors.append("risk_acknowledged must be true")
    return record, errors


def _write_plan_entry(
    *,
    row: Mapping[str, Any],
    payload_sha256: str,
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    payload = row.get("review_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    return {
        "dp_id": row.get("dp_id"),
        "score_target": row.get("score_target"),
        "data_status": payload.get("bridge_entry_data_status", payload.get("data_status")),
        "value_json": payload.get("value_json"),
        "confidence": payload.get("confidence"),
        "evidence_refs": payload.get("evidence_refs") or [],
        "payload_sha256": payload_sha256,
        "approval": {
            "approval_id": approval.get("approval_id"),
            "reviewer": approval.get("reviewer"),
            "approved_at": approval.get("approved_at"),
            "approval_scope": approval.get("approval_scope"),
        },
        "runtime_write_allowed": True,
        "production_write_allowed": False,
    }


def build_report(*, manifest_path: Path, approvals_path: Path) -> dict[str, Any]:
    started = time.time()
    manifest = _load_json(manifest_path)
    approval_payload = _load_json(approvals_path)
    approvals_file_exists = approvals_path.exists()
    approvals = _approval_records(approval_payload)
    approvals_by_dp = _records_by_dp(approvals)

    rows: list[dict[str, Any]] = []
    write_plan: list[dict[str, Any]] = []
    manifest_rows = [
        row for row in (manifest.get("rows") or []) if isinstance(row, Mapping)
    ]
    manifest_dp_ids = {str(row.get("dp_id") or "") for row in manifest_rows}
    orphan_records = [
        _approval_snapshot(record)
        for record in approvals
        if str(record.get("dp_id") or "") not in manifest_dp_ids
    ]

    for source_row in manifest_rows:
        dp_id = str(source_row.get("dp_id") or "")
        payload = source_row.get("review_payload")
        payload = payload if isinstance(payload, Mapping) else {}
        payload_sha256 = _payload_hash(payload)
        review_entry_status = str(source_row.get("review_entry_status") or "")
        data_status = str(source_row.get("data_status") or payload.get("data_status") or "")
        records = approvals_by_dp.get(dp_id, [])
        approval_record, approval_errors = _validate_approval(
            dp_id=dp_id,
            payload_sha256=payload_sha256,
            records=records,
        )
        write_entry = None
        if review_entry_status == "review_ready_concrete":
            if not records:
                gate_status = "approval_missing"
                approval_errors = ["missing approval record"]
            elif approval_errors:
                gate_status = "approval_rejected"
            else:
                gate_status = "approved_runtime_write"
                write_entry = _write_plan_entry(
                    row=source_row,
                    payload_sha256=payload_sha256,
                    approval=approval_record or {},
                )
                write_plan.append(write_entry)
        elif review_entry_status == "review_gated_unknown":
            if records:
                gate_status = "not_approvable_unknown_approval_rejected"
                approval_errors = [
                    "Unknown review payloads cannot be approved for runtime write"
                ]
            else:
                gate_status = "not_approvable_unknown"
                approval_errors = []
            approval_record = records[0] if records else None
        else:
            if records:
                gate_status = "not_approvable_manifest_entry_approval_rejected"
                approval_errors = [
                    "manifest entry is not review_ready_concrete"
                ]
            else:
                gate_status = "not_approvable_manifest_entry"
                approval_errors = []
            approval_record = records[0] if records else None

        rows.append(
            {
                "dp_id": dp_id,
                "score_target": source_row.get("score_target"),
                "source_kind": source_row.get("source_kind"),
                "source_report": source_row.get("source_report"),
                "review_entry_status": review_entry_status,
                "data_status": data_status,
                "bridge_ready_concrete": bool(source_row.get("bridge_ready_concrete")),
                "contract_valid": bool(
                    (source_row.get("contract_validation") or {}).get("contract_valid")
                ),
                "safe_to_upsert_without_review": False,
                "production_write_allowed": False,
                "payload_sha256": payload_sha256,
                "approval_gate_status": gate_status,
                "approval_record_count": len(records),
                "approval_record": _approval_snapshot(approval_record),
                "approval_validation_errors": approval_errors,
                "runtime_write_allowed": gate_status == "approved_runtime_write",
                "write_plan_entry": write_entry,
            }
        )

    status_counts = Counter(str(row.get("approval_gate_status") or "") for row in rows)
    concrete_rows = [
        row for row in rows if row.get("review_entry_status") == "review_ready_concrete"
    ]
    unknown_rows = [
        row for row in rows if row.get("review_entry_status") == "review_gated_unknown"
    ]
    rejected_statuses = {
        "approval_rejected",
        "not_approvable_unknown_approval_rejected",
        "not_approvable_manifest_entry_approval_rejected",
    }
    rejected_row_count = sum(
        1 for row in rows if row.get("approval_gate_status") in rejected_statuses
    )

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "manifest_path": _portable_path(manifest_path),
            "approvals_path": _portable_path(approvals_path),
            "approvals_file_exists": approvals_file_exists,
        },
        "summary": {
            "review_manifest_entries": len(rows),
            "review_ready_concrete_count": len(concrete_rows),
            "review_gated_unknown_count": len(unknown_rows),
            "approval_records_seen": len(approvals),
            "orphan_approval_record_count": len(orphan_records),
            "orphan_approval_records": orphan_records,
            "approval_required_count": len(concrete_rows),
            "approval_missing_count": sum(
                1 for row in rows if row.get("approval_gate_status") == "approval_missing"
            ),
            "rejected_approval_count": rejected_row_count + len(orphan_records),
            "approved_runtime_write_count": sum(
                1
                for row in rows
                if row.get("approval_gate_status") == "approved_runtime_write"
            ),
            "write_plan_count": len(write_plan),
            "not_approvable_unknown_count": len(unknown_rows),
            "approval_gate_status_counts": dict(sorted(status_counts.items())),
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "write_plan": write_plan,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share review approval gate",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Review manifest entries: `{summary['review_manifest_entries']}`",
        f"- Concrete packets requiring approval: `{summary['approval_required_count']}`",
        f"- Approval records seen: `{summary['approval_records_seen']}`",
        f"- Missing approvals: `{summary['approval_missing_count']}`",
        f"- Rejected approvals: `{summary['rejected_approval_count']}`",
        f"- Approved runtime writes: `{summary['approved_runtime_write_count']}`",
        f"- Write-plan entries: `{summary['write_plan_count']}`",
        f"- Not-approvable Unknown packets: `{summary['not_approvable_unknown_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Gate Status Counts",
        "",
        "| Gate status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["approval_gate_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | target | data status | review status | gate status | approval records | write-plan | payload hash |",
            "|---|---|---|---|---|---:|---:|---|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row.get('score_target', '-')}` | "
            f"`{row.get('data_status', '-')}` | "
            f"`{row.get('review_entry_status', '-')}` | "
            f"`{row.get('approval_gate_status', '-')}` | "
            f"{row.get('approval_record_count', 0)} | "
            f"{'yes' if row.get('write_plan_entry') else 'no'} | "
            f"`{str(row.get('payload_sha256') or '')[:12]}` |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This audit is read-only; it does not write runtime values or mutate score inputs.",
            "- A concrete packet needs a separate approval record with `approval_scope=runtime_write`, a reviewer, an approval timestamp, `risk_acknowledged=true`, and an exact payload hash match.",
            "- Unknown packets remain review-gated and are not approvable for runtime writes.",
            "- A write-plan entry is evidence of approval, not execution of a production write.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--approvals-path", type=Path, default=DEFAULT_APPROVALS_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        manifest_path=args.manifest_path,
        approvals_path=args.approvals_path,
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
