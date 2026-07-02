#!/usr/bin/env python3
"""Audit target-scope readiness for A-share approval packets.

Approval records alone are not enough to make a review packet safe to write into
``realtime_current``. A runtime write also needs a target stock scope or a
per-stock materialization path. This audit stays read-only and classifies the
current approval packets by that target-scope requirement.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_runtime_write_target_scope import (  # noqa: E402
    TARGET_SCOPE_POLICIES,
)
from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_APPROVAL_PACKETS_PATH = (
    AUDIT_DIR / "a_share_approval_review_packets_2026-06-19.json"
)
DEFAULT_RISK_REVIEW_PATH = (
    AUDIT_DIR / "a_share_approval_packet_risk_review_2026-06-19.json"
)
DEFAULT_SOURCE_SAMPLE_COVERAGE_PATH = (
    AUDIT_DIR / "a_share_approval_source_sample_coverage_2026-06-19.json"
)
DEFAULT_TARGET_SCOPE_PATH = (
    AUDIT_DIR / "a_share_runtime_write_target_scope_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    AUDIT_DIR / "a_share_approval_target_scope_readiness_2026-06-20.json"
)
DEFAULT_MD_OUTPUT = (
    AUDIT_DIR / "a_share_approval_target_scope_readiness_2026-06-20.md"
)

PER_STOCK_SCORE_TARGETS = {"fundamental_score"}
MARKET_OR_EVENT_SCOPE_TARGETS = {
    "priced_in_discount",
    "reflexivity_multiplier",
    "risk_discount",
    "valuation_rerating",
}


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_rows = payload.get("rows") or []
    if not isinstance(raw_rows, list):
        return []
    return [dict(row) for row in raw_rows if isinstance(row, Mapping)]


def _by_dp_id(rows: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    by_dp_id: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            by_dp_id[dp_id] = row
    return by_dp_id


def _risk_class(row: Mapping[str, Any]) -> str:
    raw = row.get("risk_class")
    if raw:
        return str(raw)
    raw_counts = row.get("risk_class_counts")
    if isinstance(raw_counts, Mapping) and raw_counts:
        return ",".join(sorted(str(key) for key in raw_counts))
    return "unknown"


def _source_sample_route(row: Mapping[str, Any]) -> str:
    raw = row.get("source_sample_route")
    return str(raw) if raw else "unknown"


def _sample_complete(row: Mapping[str, Any]) -> bool:
    return bool(
        row.get("source_sample_reviewer_packet_complete")
        or row.get("reviewer_packet_complete")
    )


def _sample_payload_matches(row: Mapping[str, Any]) -> bool:
    return bool(
        row.get("source_sample_payload_matches_candidate")
        or row.get("source_payload_matches_candidate")
    )


def _target_ts_codes(row: Mapping[str, Any]) -> list[str]:
    raw = row.get("target_ts_codes")
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    raw_single = row.get("ts_code") or row.get("target_ts_code")
    if raw_single:
        return [str(raw_single)]
    value_json = row.get("value_json")
    value_json = value_json if isinstance(value_json, Mapping) else {}
    raw_value_targets = value_json.get("target_ts_codes")
    if isinstance(raw_value_targets, list):
        return [str(item) for item in raw_value_targets if str(item).strip()]
    return []


def _scope_requirement(score_target: str) -> str:
    if score_target in PER_STOCK_SCORE_TARGETS:
        return "per_stock_value_materialization_required"
    if score_target in MARKET_OR_EVENT_SCOPE_TARGETS:
        return "market_or_event_scope_policy_required"
    return "explicit_target_scope_policy_required"


def _row_status(
    packet: Mapping[str, Any],
    *,
    risk_row: Mapping[str, Any] | None,
    sample_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    dp_id = str(packet.get("dp_id") or "")
    score_target = str(packet.get("score_target") or "")
    explicit_targets = _target_ts_codes(packet)
    has_existing_policy = dp_id in TARGET_SCOPE_POLICIES
    final_score_ready = packet.get("final_score_target_ready") is True
    approval_missing = packet.get("approval_gate_status") == "approval_missing"

    if explicit_targets:
        scope_status = "explicit_target_scope_ready"
        blocking_reasons: list[str] = []
    elif has_existing_policy:
        scope_status = "existing_target_scope_policy_ready"
        blocking_reasons = []
    else:
        scope_status = "target_scope_policy_required"
        blocking_reasons = [_scope_requirement(score_target)]

    target_scope_ready = scope_status in {
        "explicit_target_scope_ready",
        "existing_target_scope_policy_ready",
    }
    runtime_materialization_ready = (
        final_score_ready and target_scope_ready and not approval_missing
    )

    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "source_kind": packet.get("source_kind"),
        "data_status": packet.get("data_status"),
        "confidence": packet.get("confidence"),
        "approval_gate_status": packet.get("approval_gate_status"),
        "final_score_target_ready": final_score_ready,
        "approval_payload_hash_matches_manifest": packet.get(
            "approval_payload_hash_matches_manifest"
        )
        is True,
        "approval_record_template_contract_valid": packet.get(
            "approval_record_template_contract_valid"
        )
        is True,
        "risk_class": _risk_class(risk_row or {}),
        "source_sample_route": _source_sample_route(sample_row or {}),
        "source_sample_reviewer_packet_complete": _sample_complete(sample_row or {}),
        "source_sample_payload_matches_candidate": _sample_payload_matches(
            sample_row or {}
        ),
        "has_explicit_target_ts_codes": bool(explicit_targets),
        "explicit_target_ts_code_count": len(explicit_targets),
        "existing_target_scope_policy": has_existing_policy,
        "target_scope_status": scope_status,
        "target_scope_blocking_reasons": blocking_reasons,
        "target_scope_ready_after_approval": target_scope_ready,
        "runtime_materialization_ready": runtime_materialization_ready,
        "production_write_allowed": False,
        "required_next_step": (
            "approval_record"
            if target_scope_ready and approval_missing
            else "runtime_write_plan"
            if runtime_materialization_ready
            else blocking_reasons[0]
            if blocking_reasons
            else "none"
        ),
    }


def build_report(
    *,
    approval_packets_path: Path,
    risk_review_path: Path,
    source_sample_coverage_path: Path,
    target_scope_path: Path,
) -> dict[str, Any]:
    approval_packets = _load_json(approval_packets_path)
    risk_review = _load_json(risk_review_path)
    source_sample_coverage = _load_json(source_sample_coverage_path)
    target_scope = _load_json(target_scope_path)

    risk_by_dp = _by_dp_id(_rows(risk_review))
    sample_by_dp = _by_dp_id(_rows(source_sample_coverage))
    rows = [
        _row_status(
            packet,
            risk_row=risk_by_dp.get(str(packet.get("dp_id") or "")),
            sample_row=sample_by_dp.get(str(packet.get("dp_id") or "")),
        )
        for packet in _rows(approval_packets)
    ]

    scope_status_counts = Counter(str(row["target_scope_status"]) for row in rows)
    score_target_counts = Counter(str(row["score_target"]) for row in rows)
    source_kind_counts = Counter(str(row.get("source_kind") or "") for row in rows)
    required_next_step_counts = Counter(str(row["required_next_step"]) for row in rows)
    risk_class_counts = Counter(str(row["risk_class"]) for row in rows)

    target_scope_summary = target_scope.get("summary") or {}
    existing_supported_dp_ids = sorted(TARGET_SCOPE_POLICIES)
    target_scope_policy_required_rows = [
        row for row in rows if row["target_scope_status"] == "target_scope_policy_required"
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "approval_packets_path": _portable_path(approval_packets_path),
            "risk_review_path": _portable_path(risk_review_path),
            "source_sample_coverage_path": _portable_path(source_sample_coverage_path),
            "target_scope_path": _portable_path(target_scope_path),
        },
        "summary": {
            "approval_packet_count": len(rows),
            "final_score_target_ready_count": sum(
                1 for row in rows if row["final_score_target_ready"]
            ),
            "approval_missing_count": sum(
                1 for row in rows if row["approval_gate_status"] == "approval_missing"
            ),
            "source_sample_reviewer_packet_complete_count": sum(
                1 for row in rows if row["source_sample_reviewer_packet_complete"]
            ),
            "source_sample_payload_match_count": sum(
                1 for row in rows if row["source_sample_payload_matches_candidate"]
            ),
            "existing_target_scope_policy_count": len(existing_supported_dp_ids),
            "existing_target_scope_policy_dp_ids": existing_supported_dp_ids,
            "supported_by_existing_target_scope_policy_count": sum(
                1 for row in rows if row["existing_target_scope_policy"]
            ),
            "explicit_target_scope_count": sum(
                1 for row in rows if row["has_explicit_target_ts_codes"]
            ),
            "target_scope_ready_after_approval_count": sum(
                1 for row in rows if row["target_scope_ready_after_approval"]
            ),
            "target_scope_policy_required_count": len(target_scope_policy_required_rows),
            "per_stock_value_materialization_required_count": sum(
                1
                for row in target_scope_policy_required_rows
                if row["required_next_step"]
                == "per_stock_value_materialization_required"
            ),
            "market_or_event_scope_policy_required_count": sum(
                1
                for row in target_scope_policy_required_rows
                if row["required_next_step"]
                == "market_or_event_scope_policy_required"
            ),
            "explicit_target_scope_policy_required_count": sum(
                1
                for row in target_scope_policy_required_rows
                if row["required_next_step"]
                == "explicit_target_scope_policy_required"
            ),
            "runtime_materialization_ready_count": sum(
                1 for row in rows if row["runtime_materialization_ready"]
            ),
            "approval_only_not_sufficient_count": sum(
                1
                for row in rows
                if row["approval_gate_status"] == "approval_missing"
                and not row["target_scope_ready_after_approval"]
            ),
            "safe_runtime_write_after_approval_count": sum(
                1
                for row in rows
                if row["target_scope_ready_after_approval"]
                and row["final_score_target_ready"]
            ),
            "production_write_allowed_count": 0,
            "scope_status_counts": dict(sorted(scope_status_counts.items())),
            "score_target_counts": dict(sorted(score_target_counts.items())),
            "source_kind_counts": dict(sorted(source_kind_counts.items())),
            "risk_class_counts": dict(sorted(risk_class_counts.items())),
            "required_next_step_counts": dict(sorted(required_next_step_counts.items())),
            "runtime_target_scope_candidate_count": int(
                target_scope_summary.get("target_scope_candidate_count") or 0
            ),
            "score_mutation": "none; target-scope readiness audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share approval target-scope readiness",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Approval packets checked: `{summary['approval_packet_count']}`",
        f"- Final-score-target ready packets: `{summary['final_score_target_ready_count']}`",
        f"- Approval missing: `{summary['approval_missing_count']}`",
        f"- Source-sample reviewer packets complete: `{summary['source_sample_reviewer_packet_complete_count']}`",
        f"- Existing runtime target-scope policy dp_ids: `{', '.join(summary['existing_target_scope_policy_dp_ids'])}`",
        f"- Supported by existing target-scope policy: `{summary['supported_by_existing_target_scope_policy_count']}`",
        f"- Explicit target scopes present: `{summary['explicit_target_scope_count']}`",
        f"- Target-scope ready after approval: `{summary['target_scope_ready_after_approval_count']}`",
        f"- Target-scope policy required: `{summary['target_scope_policy_required_count']}`",
        f"- Per-stock value materialization required: `{summary['per_stock_value_materialization_required_count']}`",
        f"- Market/event scope policy required: `{summary['market_or_event_scope_policy_required_count']}`",
        f"- Runtime materialization ready: `{summary['runtime_materialization_ready_count']}`",
        f"- Approval-only not sufficient: `{summary['approval_only_not_sufficient_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Scope Status Counts",
        "",
        "| Scope status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["scope_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")
    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | target | source kind | risk class | scope status | next step | final-score ready | sample complete |",
            "|---|---|---|---|---|---|---:|---:|",
        ]
    )
    for row in report.get("rows") or []:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['score_target']}` | "
            f"`{row.get('source_kind', '-')}` | "
            f"`{row.get('risk_class', '-')}` | "
            f"`{row['target_scope_status']}` | "
            f"`{row['required_next_step']}` | "
            f"{'yes' if row['final_score_target_ready'] else 'no'} | "
            f"{'yes' if row['source_sample_reviewer_packet_complete'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Approval records are necessary but not sufficient for these packets.",
            "- Current runtime target-scope expansion is only defined for deterministic neutral/NotApplicable policies.",
            "- Fundamental packets need per-stock materialization or an explicit target-scope policy before runtime writes.",
            "- Non-fundamental policy/event packets need a reviewed market/event scope policy before runtime writes.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--approval-packets-path", type=Path, default=DEFAULT_APPROVAL_PACKETS_PATH
    )
    parser.add_argument("--risk-review-path", type=Path, default=DEFAULT_RISK_REVIEW_PATH)
    parser.add_argument(
        "--source-sample-coverage-path",
        type=Path,
        default=DEFAULT_SOURCE_SAMPLE_COVERAGE_PATH,
    )
    parser.add_argument("--target-scope-path", type=Path, default=DEFAULT_TARGET_SCOPE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        approval_packets_path=args.approval_packets_path,
        risk_review_path=args.risk_review_path,
        source_sample_coverage_path=args.source_sample_coverage_path,
        target_scope_path=args.target_scope_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
