#!/usr/bin/env python3
"""Prioritize external business-metric review packets by remaining blockers.

This read-only audit groups the 99 candidate-level review packets for
frequency, penetration, and replacement by the exact fields still missing
before a Known draft could be reviewed.
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

from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_REVIEW_PACKETS_PATH = (
    ROOT / "docs/audit/a_share_unknown_external_business_metric_review_packets_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_external_business_metric_readiness_queue_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_external_business_metric_readiness_queue_2026-06-19.md"
)

POLICY_ONLY_MISSING = ("bounds", "formula_policy")


def _missing_key(packet: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(field) for field in packet.get("missing_fields") or [])


def _priority(packet: Mapping[str, Any]) -> str:
    missing = set(_missing_key(packet))
    if tuple(_missing_key(packet)) == POLICY_ONLY_MISSING:
        return "P0_formula_policy_only"
    if "denominator_or_normalizer" in missing:
        return "P2_denominator_required"
    if "period" in missing or "unit" in missing:
        return "P1_period_or_unit_required"
    return "P3_other_review_required"


def _next_action(packet: Mapping[str, Any]) -> str:
    priority = _priority(packet)
    if priority == "P0_formula_policy_only":
        return "review bounds, source scope, formula policy, and value_json only"
    if priority == "P1_period_or_unit_required":
        return "extract or review period/unit before formula-policy review"
    if priority == "P2_denominator_required":
        return "find or validate denominator/normalizer before numeric conversion"
    return "review remaining missing fields before Known draft"


def _packet_row(packet: Mapping[str, Any]) -> dict[str, Any]:
    missing = list(_missing_key(packet))
    return {
        "packet_id": packet.get("packet_id"),
        "dp_id": packet.get("dp_id"),
        "candidate_classification": packet.get("candidate_classification"),
        "priority": _priority(packet),
        "next_action": _next_action(packet),
        "missing_fields": missing,
        "numeric_hits": packet.get("numeric_hits") or [],
        "market_relative_path": packet.get("market_relative_path"),
        "title": packet.get("title"),
        "excerpt": packet.get("excerpt"),
        "metric_inputs_ready": False,
        "known_draft_sufficient": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def _combo_rows(packets: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, ...]] = Counter(_missing_key(packet) for packet in packets)
    return [
        {"missing_fields": list(fields), "count": count}
        for fields, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _dp_priority_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    dp_ids = sorted({str(row.get("dp_id") or "") for row in rows if row.get("dp_id")})
    priorities = [
        "P0_formula_policy_only",
        "P1_period_or_unit_required",
        "P2_denominator_required",
        "P3_other_review_required",
    ]
    for dp_id in dp_ids:
        dp_rows = [row for row in rows if row.get("dp_id") == dp_id]
        priority_counts = {
            priority: sum(1 for row in dp_rows if row["priority"] == priority)
            for priority in priorities
        }
        out.append(
            {
                "dp_id": dp_id,
                "packet_count": len(dp_rows),
                "priority_counts": priority_counts,
                "top_next_action": next(
                    (
                        priority
                        for priority in priorities
                        if priority_counts.get(priority, 0) > 0
                    ),
                    "none",
                ),
            }
        )
    return out


def build_report(*, review_packets_path: Path) -> dict[str, Any]:
    started = time.time()
    review_packets = _load_json(review_packets_path)
    packets = [
        packet
        for packet in review_packets.get("rows") or []
        if isinstance(packet, Mapping)
    ]
    rows = [_packet_row(packet) for packet in packets]
    rows.sort(
        key=lambda row: (
            str(row["priority"]),
            str(row["dp_id"]),
            str(row.get("market_relative_path") or ""),
            str(row.get("excerpt") or ""),
        )
    )
    priority_counts = Counter(str(row["priority"]) for row in rows)
    missing_field_counts = Counter(
        field for row in rows for field in row.get("missing_fields", [])
    )
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "review_packets_path": _portable_path(review_packets_path),
        },
        "summary": {
            "business_metric_review_packet_count": len(rows),
            "formula_policy_only_candidate_count": priority_counts.get(
                "P0_formula_policy_only", 0
            ),
            "period_or_unit_required_count": priority_counts.get(
                "P1_period_or_unit_required", 0
            ),
            "denominator_required_count": priority_counts.get(
                "P2_denominator_required", 0
            ),
            "other_review_required_count": priority_counts.get(
                "P3_other_review_required", 0
            ),
            "missing_denominator_count": missing_field_counts.get(
                "denominator_or_normalizer", 0
            ),
            "missing_period_count": missing_field_counts.get("period", 0),
            "missing_unit_count": missing_field_counts.get("unit", 0),
            "missing_bounds_count": missing_field_counts.get("bounds", 0),
            "missing_formula_policy_count": missing_field_counts.get(
                "formula_policy", 0
            ),
            "metric_inputs_ready_count": 0,
            "known_draft_sufficient_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "priority_counts": dict(sorted(priority_counts.items())),
            "missing_field_counts": dict(sorted(missing_field_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "missing_field_combinations": _combo_rows(packets),
        "dp_priority_rows": _dp_priority_rows(rows),
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown external business metric readiness queue",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Review packets: `{summary['business_metric_review_packet_count']}`",
        f"- P0 formula-policy-only candidates: `{summary['formula_policy_only_candidate_count']}`",
        f"- P1 period/unit required: `{summary['period_or_unit_required_count']}`",
        f"- P2 denominator required: `{summary['denominator_required_count']}`",
        f"- Metric inputs ready: `{summary['metric_inputs_ready_count']}`",
        f"- Known-draft sufficient: `{summary['known_draft_sufficient_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## dp_id Priority Split",
        "",
        "| dp_id | packets | P0 | P1 | P2 | top next action |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in report["dp_priority_rows"]:
        counts = row["priority_counts"]
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"{row['packet_count']} | "
            f"{counts.get('P0_formula_policy_only', 0)} | "
            f"{counts.get('P1_period_or_unit_required', 0)} | "
            f"{counts.get('P2_denominator_required', 0)} | "
            f"`{row['top_next_action']}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- P0 packets are closest to a Known draft but still require reviewed bounds and formula policy.",
            "- P1 packets need period or unit extraction before formula review.",
            "- P2 packets need a denominator or normalizer before numeric conversion.",
            "- Runtime and production writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-packets-path", type=Path, default=DEFAULT_REVIEW_PACKETS_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(review_packets_path=args.review_packets_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
