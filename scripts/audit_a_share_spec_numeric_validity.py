#!/usr/bin/env python3
"""Aggregate A-share spec field validity and score-chain evidence.

This read-only report is intentionally stricter than a coverage count.  It
separates three states that are easy to conflate:

1. current runtime/overlay evidence already reaches a final score node;
2. candidate payloads are bridge-compatible but still review gated; and
3. Unknown fields still need source acquisition, formula policy, or approval.

No runtime data is written by this audit.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_FIELD_CLOSURE_PATH = AUDIT_DIR / "a_share_score_field_closure_2026-06-19.json"
DEFAULT_DRY_RUN_PATH = AUDIT_DIR / "a_share_candidate_score_dry_run_2026-06-19.json"
DEFAULT_STAGING_PATH = AUDIT_DIR / "a_share_candidate_staging_payloads_2026-06-19.json"
DEFAULT_VALUE_CONTRACTS_PATH = AUDIT_DIR / "a_share_candidate_value_contracts_2026-06-19.json"
DEFAULT_REVIEW_MANIFEST_PATH = AUDIT_DIR / "a_share_review_staging_manifest_2026-06-19.json"
DEFAULT_APPROVAL_GATE_PATH = AUDIT_DIR / "a_share_review_approval_gate_2026-06-19.json"
DEFAULT_UNKNOWN_CLOSURE_PATH = AUDIT_DIR / "a_share_unknown_closure_matrix_2026-06-19.json"
DEFAULT_JSON_OUTPUT = AUDIT_DIR / "a_share_spec_numeric_validity_2026-06-19.json"
DEFAULT_MD_OUTPUT = AUDIT_DIR / "a_share_spec_numeric_validity_2026-06-19.md"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _summary_int(payload: Mapping[str, Any], key: str) -> int:
    try:
        return int((payload.get("summary") or {}).get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _rows_by_dp(payload: Mapping[str, Any], key: str = "rows") -> dict[str, Mapping[str, Any]]:
    rows = payload.get(key) or []
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            result[dp_id] = row
    return result


def _current_chain_status(field: Mapping[str, Any]) -> str:
    if field.get("score_relevant") is not True:
        return "non_score_relevant"
    closure_status = str(field.get("closure_status") or "")
    if closure_status == "closed_reaches_final_score":
        return "current_numeric_final_score"
    if closure_status == "valid_real_but_formula_unmapped":
        return "valid_runtime_information_formula_unmapped"
    if closure_status == "overlay_only_no_score_candidate":
        return "overlay_information_not_score_candidate"
    if closure_status == "no_valid_a_share_target_data":
        return "no_valid_current_a_share_target_data"
    if closure_status:
        return closure_status
    return "unknown_current_chain_status"


def _candidate_gate_status(
    dp_id: str,
    *,
    review_row: Mapping[str, Any] | None,
    approval_row: Mapping[str, Any] | None,
    dry_run_row: Mapping[str, Any] | None,
    staging_row: Mapping[str, Any] | None,
    value_contract_row: Mapping[str, Any] | None,
    unknown_row: Mapping[str, Any] | None,
) -> str:
    if approval_row and approval_row.get("runtime_write_allowed") is True:
        return "approved_runtime_write"
    if review_row:
        status = str(review_row.get("review_entry_status") or "")
        if status == "review_ready_concrete":
            return "review_ready_concrete_approval_missing"
        if status == "review_gated_unknown":
            return "review_gated_unknown"
        if status:
            return status
    if value_contract_row:
        mode = str(value_contract_row.get("validation_mode") or "")
        if mode == "concrete" and value_contract_row.get("contract_valid") is True:
            return "concrete_contract_valid_review_required"
        if mode == "placeholder" and value_contract_row.get("contract_valid") is True:
            return "placeholder_contract_valid_generator_required"
    if staging_row:
        payload_status = str(staging_row.get("payload_status") or "")
        if payload_status == "requires_generator_output":
            return "placeholder_generator_required"
        if payload_status:
            return "staged_payload_review_required"
    if dry_run_row and dry_run_row.get("bridge_signal_ready") is True:
        return "dry_run_bridge_shape_only"
    if unknown_row:
        return "unknown_closure_required"
    return "none"


def build_report(
    *,
    field_closure_path: Path,
    dry_run_path: Path,
    staging_path: Path,
    value_contracts_path: Path,
    review_manifest_path: Path,
    approval_gate_path: Path,
    unknown_closure_path: Path,
) -> dict[str, Any]:
    field_closure = _load_json(field_closure_path)
    dry_run = _load_json(dry_run_path)
    staging = _load_json(staging_path)
    value_contracts = _load_json(value_contracts_path)
    review_manifest = _load_json(review_manifest_path)
    approval_gate = _load_json(approval_gate_path)
    unknown_closure = _load_json(unknown_closure_path)

    field_rows = [
        row for row in field_closure.get("rows") or [] if isinstance(row, Mapping)
    ]
    dry_run_by_dp = _rows_by_dp(dry_run)
    staging_by_dp = _rows_by_dp(staging)
    value_contracts_by_dp = _rows_by_dp(value_contracts)
    review_by_dp = _rows_by_dp(review_manifest)
    approval_by_dp = _rows_by_dp(approval_gate)
    unknown_by_dp = _rows_by_dp(unknown_closure)

    rows: list[dict[str, Any]] = []
    current_counts: Counter[str] = Counter()
    candidate_counts: Counter[str] = Counter()

    for field in field_rows:
        dp_id = str(field.get("dp_id") or "")
        review_row = review_by_dp.get(dp_id)
        approval_row = approval_by_dp.get(dp_id)
        dry_run_row = dry_run_by_dp.get(dp_id)
        staging_row = staging_by_dp.get(dp_id)
        value_contract_row = value_contracts_by_dp.get(dp_id)
        unknown_row = unknown_by_dp.get(dp_id)
        current_status = _current_chain_status(field)
        candidate_status = _candidate_gate_status(
            dp_id,
            review_row=review_row,
            approval_row=approval_row,
            dry_run_row=dry_run_row,
            staging_row=staging_row,
            value_contract_row=value_contract_row,
            unknown_row=unknown_row,
        )
        current_counts[current_status] += 1
        candidate_counts[candidate_status] += 1
        rows.append(
            {
                "dp_id": dp_id,
                "score_target": field.get("score_target"),
                "score_relevant": field.get("score_relevant") is True,
                "closure_status": field.get("closure_status"),
                "current_score_chain_status": current_status,
                "candidate_gate_status": candidate_status,
                "current_final_score_numeric": current_status == "current_numeric_final_score",
                "current_valid_but_not_final_score": bool(
                    field.get("score_relevant") is True
                    and current_status != "current_numeric_final_score"
                ),
                "candidate_bridge_shape_ready": bool(
                    dry_run_row and dry_run_row.get("bridge_signal_ready") is True
                ),
                "review_ready_concrete": bool(
                    review_row
                    and review_row.get("review_entry_status") == "review_ready_concrete"
                ),
                "review_gated_unknown": bool(
                    review_row
                    and review_row.get("review_entry_status") == "review_gated_unknown"
                ),
                "final_score_target_ready_after_review": bool(
                    (
                        approval_row
                        and approval_row.get("final_score_target_ready") is True
                    )
                    or (
                        review_row
                        and review_row.get("bridge_ready_concrete") is True
                    )
                ),
                "safe_to_upsert_without_review": bool(
                    (review_row or approval_row or {}).get("safe_to_upsert_without_review")
                    is True
                ),
                "production_write_allowed": bool(
                    (review_row or approval_row or {}).get("production_write_allowed")
                    is True
                ),
                "unknown_closure_route": unknown_row.get("closure_route")
                if unknown_row
                else None,
                "next_action_bucket": unknown_row.get("next_action_bucket")
                if unknown_row
                else None,
            }
        )

    summary = field_closure.get("summary") or {}
    score_relevant = int(summary.get("score_relevant_spec_dp_ids") or 0)
    current_numeric = current_counts["current_numeric_final_score"]
    score_relevant_not_final = max(score_relevant - current_numeric, 0)
    completion_pct = round((current_numeric / score_relevant) * 100, 2) if score_relevant else 0.0
    report = {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "field_closure_path": _portable_path(field_closure_path),
            "dry_run_path": _portable_path(dry_run_path),
            "staging_path": _portable_path(staging_path),
            "value_contracts_path": _portable_path(value_contracts_path),
            "review_manifest_path": _portable_path(review_manifest_path),
            "approval_gate_path": _portable_path(approval_gate_path),
            "unknown_closure_path": _portable_path(unknown_closure_path),
        },
        "summary": {
            "configured_spec_total_dp_ids": int(summary.get("configured_spec_total_dp_ids") or 0),
            "runtime_trace_spec_total_dp_ids": int(summary.get("runtime_trace_spec_total_dp_ids") or 0),
            "spec_total_matches_runtime": bool(summary.get("spec_total_matches_runtime")),
            "field_row_count": len(rows),
            "score_relevant_spec_dp_ids": score_relevant,
            "current_final_score_numeric_dp_ids": current_numeric,
            "current_score_relevant_completion_pct": completion_pct,
            "current_score_relevant_not_final_score_dp_ids": score_relevant_not_final,
            "valid_runtime_information_formula_unmapped_dp_ids": current_counts[
                "valid_runtime_information_formula_unmapped"
            ],
            "overlay_information_not_score_candidate_dp_ids": current_counts[
                "overlay_information_not_score_candidate"
            ],
            "no_valid_current_a_share_target_data_dp_ids": current_counts[
                "no_valid_current_a_share_target_data"
            ],
            "actionable_blocking_gap_dp_ids": int(summary.get("blocking_gap_dp_ids") or 0),
            "candidate_ready_blocking_gap_dp_ids": int(
                summary.get("candidate_ready_blocking_gap_dp_ids") or 0
            ),
            "candidate_dry_run_bridge_ready_dp_ids": _summary_int(
                dry_run, "bridge_signal_ready_count"
            ),
            "candidate_dry_run_final_score_target_ready_dp_ids": _summary_int(
                dry_run, "final_score_target_ready_count"
            ),
            "staging_payload_count": _summary_int(staging, "staging_payload_count"),
            "staging_bridge_ready_payload_count": _summary_int(
                staging, "staging_payload_bridge_ready_count"
            ),
            "value_contract_concrete_bridge_validated_count": _summary_int(
                value_contracts, "bridge_validated_concrete_count"
            ),
            "value_contract_placeholder_payload_count": _summary_int(
                value_contracts, "placeholder_payload_valid_count"
            ),
            "review_ready_concrete_final_score_dp_ids": _summary_int(
                review_manifest, "bridge_ready_concrete_count"
            ),
            "review_gated_unknown_dp_ids": _summary_int(
                review_manifest, "review_gated_unknown_count"
            ),
            "approval_review_packet_count": _summary_int(
                approval_gate, "review_ready_concrete_count"
            ),
            "approval_missing_count": _summary_int(approval_gate, "approval_missing_count"),
            "approved_runtime_write_count": _summary_int(
                approval_gate, "approved_runtime_write_count"
            ),
            "safe_to_upsert_without_review_count": _summary_int(
                approval_gate, "safe_to_upsert_without_review_count"
            ),
            "production_write_allowed_count": _summary_int(
                approval_gate, "production_write_allowed_count"
            ),
            "unknown_closure_row_count": _summary_int(
                unknown_closure, "unknown_closure_row_count"
            ),
            "unknown_auto_known_ready_count": _summary_int(
                unknown_closure, "auto_known_ready_count"
            ),
            "unknown_approval_ready_count": _summary_int(
                unknown_closure, "approval_ready_count"
            ),
            "current_score_chain_status_counts": dict(sorted(current_counts.items())),
            "candidate_gate_status_counts": dict(sorted(candidate_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "score_relevant_not_final_rows": [
            row for row in rows if row["current_valid_but_not_final_score"]
        ],
        "review_gated_unknown_rows": [
            row for row in rows if row["review_gated_unknown"]
        ],
        "rows": rows,
    }
    return report


def _md_table_row(values: list[Any]) -> str:
    return "| " + " | ".join(str(v) for v in values) + " |"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share spec numeric-validity audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        f"- Spec total config/runtime: `{summary['configured_spec_total_dp_ids']}` / `{summary['runtime_trace_spec_total_dp_ids']}`",
        f"- Spec total matches runtime: `{summary['spec_total_matches_runtime']}`",
        f"- Current numeric final-score fields: `{summary['current_final_score_numeric_dp_ids']}` / `{summary['score_relevant_spec_dp_ids']}` (`{summary['current_score_relevant_completion_pct']}%`)",
        f"- Score-relevant fields not currently in final score: `{summary['current_score_relevant_not_final_score_dp_ids']}`",
        f"- Actionable blocking gaps: `{summary['actionable_blocking_gap_dp_ids']}`",
        f"- Candidate dry-run bridge-ready fields: `{summary['candidate_dry_run_bridge_ready_dp_ids']}`",
        f"- Review-ready concrete final-score packets: `{summary['review_ready_concrete_final_score_dp_ids']}`",
        f"- Review-gated Unknown packets: `{summary['review_gated_unknown_dp_ids']}`",
        f"- Approved runtime writes: `{summary['approved_runtime_write_count']}`",
        f"- Safe to upsert without review: `{summary['safe_to_upsert_without_review_count']}`",
        "",
        "## Current Chain Status",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["current_score_chain_status_counts"].items():
        lines.append(_md_table_row([f"`{status}`", count]))

    lines.extend(
        [
            "",
            "## Candidate Gate Status",
            "",
            "| Status | Count |",
            "|---|---:|",
        ]
    )
    for status, count in summary["candidate_gate_status_counts"].items():
        lines.append(_md_table_row([f"`{status}`", count]))

    lines.extend(
        [
            "",
            "## Review-gated Unknown Rows",
            "",
            "| dp_id | target | current chain | next action |",
            "|---|---|---|---|",
        ]
    )
    for row in report.get("review_gated_unknown_rows") or []:
        lines.append(
            _md_table_row(
                [
                    f"`{row['dp_id']}`",
                    f"`{row['score_target']}`",
                    f"`{row['current_score_chain_status']}`",
                    f"`{row.get('next_action_bucket') or '-'}`",
                ]
            )
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `current_numeric_final_score` is the only state counted as already reaching the current production final-score path.",
            "- Candidate dry-run bridge readiness proves the payload shape can become a numeric realtime node; it does not prove the business value is correct.",
            "- Review-ready concrete packets are still gated because approval records are missing and runtime writes remain disabled.",
            "- Review-gated Unknown packets still lack source evidence, formula policy, or mapping required to produce a bounded value.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--field-closure-path", type=Path, default=DEFAULT_FIELD_CLOSURE_PATH)
    parser.add_argument("--dry-run-path", type=Path, default=DEFAULT_DRY_RUN_PATH)
    parser.add_argument("--staging-path", type=Path, default=DEFAULT_STAGING_PATH)
    parser.add_argument("--value-contracts-path", type=Path, default=DEFAULT_VALUE_CONTRACTS_PATH)
    parser.add_argument("--review-manifest-path", type=Path, default=DEFAULT_REVIEW_MANIFEST_PATH)
    parser.add_argument("--approval-gate-path", type=Path, default=DEFAULT_APPROVAL_GATE_PATH)
    parser.add_argument("--unknown-closure-path", type=Path, default=DEFAULT_UNKNOWN_CLOSURE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        field_closure_path=args.field_closure_path,
        dry_run_path=args.dry_run_path,
        staging_path=args.staging_path,
        value_contracts_path=args.value_contracts_path,
        review_manifest_path=args.review_manifest_path,
        approval_gate_path=args.approval_gate_path,
        unknown_closure_path=args.unknown_closure_path,
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
