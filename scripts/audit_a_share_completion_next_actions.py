#!/usr/bin/env python3
"""Build the next-action queue for improving A-share spec completion.

This report is deliberately read-only. It separates packets that only need
human runtime-write approval from Unknown packets that still need evidence,
classification, mapping, or manual assumptions before they can become concrete
review packets.
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
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_completion_next_actions_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_completion_next_actions_2026-06-19.md"


BUCKET_ORDER = {
    "runtime_write_plan_ready": 0,
    "human_approval_required": 1,
    "event_text_classification_required": 2,
    "local_structured_mapping_required": 3,
    "structured_text_extraction_required": 4,
    "single_dependency_policy_required": 5,
    "manual_assumption_review_required": 6,
    "unknown_resolution_required": 7,
}


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
    out: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            out[dp_id] = dict(row)
    return out


def _approval_template(dp_id: str, payload_sha256: str) -> dict[str, Any]:
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


def _payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unknown_bucket(source_kind: str) -> tuple[str, str, list[str]]:
    if source_kind == "event_text_policy_pilot":
        return (
            "event_text_classification_required",
            "Classify source headlines/events into concept, direction, magnitude, and A-share transmission path; emit a bounded Known review packet or keep Unknown with stronger blocker evidence.",
            [
                "classified event concept",
                "direction and magnitude",
                "A-share transmission path",
                "evidence refs and rationale",
            ],
        )
    if source_kind == "local_structured_policy_pilot":
        return (
            "local_structured_mapping_required",
            "Review a structured financial/business mapping formula and bounds before emitting a Known review packet.",
            [
                "dependency values",
                "reviewed business mapping formula",
                "numeric bounds",
                "evidence refs and rationale",
            ],
        )
    if source_kind == "local_structured_text_policy_pilot":
        return (
            "structured_text_extraction_required",
            "Extract the relevant business signal from QA/IR text and map it to a bounded Known review packet.",
            [
                "text snippet or structured extraction",
                "classification target",
                "direction and magnitude",
                "evidence refs and rationale",
            ],
        )
    if source_kind == "local_single_dependency_policy_pilot":
        return (
            "single_dependency_policy_required",
            "Define a reviewed single-dependency policy before emitting a Known review packet.",
            [
                "single dependency value",
                "reviewed policy mapping",
                "bounds or neutral fallback",
                "evidence refs and rationale",
            ],
        )
    if source_kind == "manual_policy_pilot":
        return (
            "manual_assumption_review_required",
            "Review the required assumptions and sensitivity bounds before emitting a Known review packet.",
            [
                "reviewed assumptions",
                "sensitivity bounds",
                "calculation rationale",
                "evidence refs",
            ],
        )
    return (
        "unknown_resolution_required",
        "Resolve the Unknown blocker with source-backed evidence and a reviewed conversion contract.",
        ["source-backed evidence", "reviewed conversion contract", "evidence refs"],
    )


def _next_action_row(
    manifest_row: Mapping[str, Any],
    approval_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    dp_id = str(manifest_row.get("dp_id") or "")
    payload = manifest_row.get("review_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    value_json = payload.get("value_json")
    value_json = value_json if isinstance(value_json, Mapping) else {}
    review_entry_status = str(manifest_row.get("review_entry_status") or "")
    source_kind = str(manifest_row.get("source_kind") or "")
    manifest_payload_sha256 = _payload_hash(payload)
    approval_payload_sha256 = str((approval_row or {}).get("payload_sha256") or "")
    approval_payload_hash_matches_manifest = (
        bool(approval_payload_sha256)
        and approval_payload_sha256 == manifest_payload_sha256
    )
    approval_gate_status = str((approval_row or {}).get("approval_gate_status") or "")
    effective_approval_gate_status = approval_gate_status
    if (
        approval_gate_status == "approved_runtime_write"
        and not approval_payload_hash_matches_manifest
    ):
        effective_approval_gate_status = "approval_hash_mismatch"

    if review_entry_status == "review_ready_concrete":
        if effective_approval_gate_status == "approved_runtime_write":
            bucket = "runtime_write_plan_ready"
            next_action = (
                "Runtime-write approval is valid and a write-plan entry exists; "
                "execute only through the controlled runtime upsert path."
            )
            required_evidence = [
                "validated approval record",
                "matching payload_sha256",
                "write-plan entry",
                "production_write_allowed=false",
            ]
            template = None
        else:
            bucket = "human_approval_required"
            next_action = (
                "Human reviewer must inspect the concrete review packet and, if accepted, "
                "create a separate approval record whose payload_sha256 matches this packet."
            )
            required_evidence = [
                "reviewer identity",
                "approved_at timestamp",
                "approval_status=approved",
                "approval_scope=runtime_write",
                "risk_acknowledged=true",
                "matching payload_sha256",
            ]
            template = _approval_template(dp_id, manifest_payload_sha256)
    else:
        bucket, next_action, required_evidence = _unknown_bucket(source_kind)
        template = None

    return {
        "dp_id": dp_id,
        "score_target": manifest_row.get("score_target"),
        "source_kind": source_kind,
        "source_report": manifest_row.get("source_report"),
        "source_dependencies": manifest_row.get("source_dependencies") or [],
        "data_status": manifest_row.get("data_status"),
        "review_entry_status": review_entry_status,
        "approval_gate_status": effective_approval_gate_status or None,
        "approval_payload_sha256": approval_payload_sha256,
        "payload_sha256": manifest_payload_sha256,
        "approval_payload_hash_matches_manifest": (
            approval_payload_hash_matches_manifest
        ),
        "next_action_bucket": bucket,
        "next_action": next_action,
        "required_evidence": required_evidence,
        "blocked_reason": value_json.get("blocked_reason"),
        "required_policy": value_json.get("required_policy"),
        "required_assumptions": value_json.get("required_assumptions") or [],
        "approval_record_template": template,
        "runtime_write_allowed": bool((approval_row or {}).get("runtime_write_allowed"))
        and effective_approval_gate_status == "approved_runtime_write",
        "production_write_allowed": False,
    }


def build_report(*, manifest_path: Path, approval_gate_path: Path) -> dict[str, Any]:
    started = time.time()
    manifest = _load_json(manifest_path)
    approval_gate = _load_json(approval_gate_path)
    approval_rows = _rows_by_dp(approval_gate)

    rows = [
        _next_action_row(row, approval_rows.get(str(row.get("dp_id") or "")))
        for row in (manifest.get("rows") or [])
        if isinstance(row, Mapping)
    ]
    rows.sort(
        key=lambda row: (
            BUCKET_ORDER.get(str(row.get("next_action_bucket") or ""), 99),
            str(row.get("dp_id") or ""),
        )
    )
    bucket_counts = Counter(str(row["next_action_bucket"]) for row in rows)
    source_kind_counts = Counter(str(row.get("source_kind") or "") for row in rows)
    approval_template_rows = [
        row for row in rows if row.get("approval_record_template") is not None
    ]
    hash_mismatch_rows = [
        row
        for row in rows
        if row.get("approval_payload_sha256")
        and not row.get("approval_payload_hash_matches_manifest")
    ]

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "manifest_path": _portable_path(manifest_path),
            "approval_gate_path": _portable_path(approval_gate_path),
        },
        "summary": {
            "actionable_gap_count": len(rows),
            "approval_ready_packet_count": bucket_counts.get("human_approval_required", 0),
            "runtime_write_plan_ready_count": bucket_counts.get(
                "runtime_write_plan_ready", 0
            ),
            "approval_record_template_count": len(approval_template_rows),
            "approval_payload_hash_mismatch_count": len(hash_mismatch_rows),
            "approval_payload_hash_mismatch_dp_ids": [
                str(row.get("dp_id") or "") for row in hash_mismatch_rows
            ],
            "unknown_resolution_required_count": len(rows)
            - bucket_counts.get("human_approval_required", 0)
            - bucket_counts.get("runtime_write_plan_ready", 0),
            "event_text_classification_required_count": bucket_counts.get(
                "event_text_classification_required", 0
            ),
            "local_structured_mapping_required_count": bucket_counts.get(
                "local_structured_mapping_required", 0
            ),
            "structured_text_extraction_required_count": bucket_counts.get(
                "structured_text_extraction_required", 0
            ),
            "single_dependency_policy_required_count": bucket_counts.get(
                "single_dependency_policy_required", 0
            ),
            "manual_assumption_review_required_count": bucket_counts.get(
                "manual_assumption_review_required", 0
            ),
            "approved_runtime_write_count": int(
                (approval_gate.get("summary") or {}).get("approved_runtime_write_count") or 0
            ),
            "write_plan_count": int(
                (approval_gate.get("summary") or {}).get("write_plan_count") or 0
            ),
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "next_action_bucket_counts": dict(sorted(bucket_counts.items())),
            "source_kind_counts": dict(sorted(source_kind_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share completion next actions",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Actionable gaps: `{summary['actionable_gap_count']}`",
        f"- Approval-ready packets: `{summary['approval_ready_packet_count']}`",
        f"- Runtime write-plan ready: `{summary['runtime_write_plan_ready_count']}`",
        f"- Approval templates: `{summary['approval_record_template_count']}`",
        f"- Approval payload hash mismatches: `{summary['approval_payload_hash_mismatch_count']}`",
        f"- Unknown resolution required: `{summary['unknown_resolution_required_count']}`",
        f"- Approved runtime writes: `{summary['approved_runtime_write_count']}`",
        f"- Write-plan entries: `{summary['write_plan_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Next Action Buckets",
        "",
        "| Bucket | Count |",
        "|---|---:|",
    ]
    for bucket, count in summary["next_action_bucket_counts"].items():
        lines.append(f"| `{bucket}` | {count} |")
    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | target | data status | source | next action bucket | blocker |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in report["rows"]:
        blocker = row.get("blocked_reason") or row.get("required_policy") or "-"
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row.get('score_target', '-')}` | "
            f"`{row.get('data_status', '-')}` | "
            f"`{row.get('source_kind', '-')}` | "
            f"`{row.get('next_action_bucket', '-')}` | "
            f"{blocker} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Approval templates are incomplete by design and are not valid approval records.",
            "- Unknown rows need evidence/classification/mapping before they can become concrete review packets.",
            "- This report does not write runtime values and does not reduce score blockers by itself.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--approval-gate-path", type=Path, default=DEFAULT_APPROVAL_GATE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        manifest_path=args.manifest_path,
        approval_gate_path=args.approval_gate_path,
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
