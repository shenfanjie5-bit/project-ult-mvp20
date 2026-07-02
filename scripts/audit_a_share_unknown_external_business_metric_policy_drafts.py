#!/usr/bin/env python3
"""Draft review-only formula policies for P0 external business-metric packets.

The readiness queue identifies P0 packets where the retained snippet already
has candidate scope, denominator/normalizer, period, and unit evidence. This
audit drafts the formula-policy handoff for those packets without selecting a
Known value or allowing score writes.
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

from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_READINESS_QUEUE_PATH = (
    ROOT / "docs/audit/a_share_unknown_external_business_metric_readiness_queue_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_external_business_metric_policy_drafts_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_external_business_metric_policy_drafts_2026-06-19.md"
)


def _draft_id(row: Mapping[str, Any]) -> str:
    raw = "|".join(
        [
            str(row.get("packet_id") or ""),
            str(row.get("dp_id") or ""),
            str(row.get("market_relative_path") or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _policy_template(dp_id: str) -> dict[str, Any]:
    if dp_id == "L0.demand.frequency":
        return {
            "metric_family": "cadence_or_repeat_usage",
            "candidate_unit_policy": "percentage_or_count_only_if_the_snippet_directly_measures frequency, repeat purchase, transaction cadence, or active usage",
            "raw_value_selection": "exclude dates, forward CAGR, order-size, and generic demand-growth percentages",
            "draft_bounds": {
                "ratio_min": 0.0,
                "ratio_max": 1.0,
                "count_min": 0.0,
                "count_max_review_required": True,
            },
            "score_mapping_policy": "positive cadence signal only after reviewer confirms business cadence and normalizer",
        }
    if dp_id == "L0.demand.penetration":
        return {
            "metric_family": "penetration_or_market_share",
            "candidate_unit_policy": "percentage or ratio measuring same-scope penetration, coverage, market share, or installed base share",
            "raw_value_selection": "exclude dates, stock-price moves, financing coverage, unrelated regional market share, and generic CAGR",
            "draft_bounds": {
                "ratio_min": 0.0,
                "ratio_max": 1.0,
                "percent_min": 0.0,
                "percent_max": 100.0,
            },
            "score_mapping_policy": "higher reviewed penetration/share can become a positive demand signal only with same-scope denominator",
        }
    return {
        "metric_family": "external_business_metric",
        "candidate_unit_policy": "review required",
        "raw_value_selection": "review required",
        "draft_bounds": {"review_required": True},
        "score_mapping_policy": "review required",
    }


def _review_blockers(row: Mapping[str, Any]) -> list[str]:
    return [
        "review candidate source scope and issuer relevance",
        "select one business metric value from numeric_hits",
        "reject dates, monetary values, growth rates, and market-price moves when they are not the target metric",
        "approve bounds and formula policy before Known draft creation",
        "keep Unknown if source scope, period, denominator, or unit is ambiguous",
    ]


def _policy_review_template(packet: Mapping[str, Any]) -> dict[str, Any]:
    formula_policy = packet.get("formula_policy_template")
    if not isinstance(formula_policy, Mapping):
        formula_policy = {}
    value_json_template = packet.get("value_json_template")
    if not isinstance(value_json_template, Mapping):
        value_json_template = {}
    return {
        "template_status": "review_fill_required",
        "policy_draft_id": packet.get("policy_draft_id"),
        "source_packet_id": packet.get("source_packet_id"),
        "dp_id": packet.get("dp_id"),
        "score_target": packet.get("score_target"),
        "review_scope": "external_business_metric_formula_policy",
        "metric_family": formula_policy.get("metric_family"),
        "numeric_hits": list(packet.get("numeric_hits") or []),
        "value_json_template": dict(value_json_template),
        "reviewer": "",
        "reviewed_at": "",
        "source_scope_accepted": False,
        "numeric_value_selected": False,
        "unit_period_scope_accepted": False,
        "bounds_accepted": False,
        "formula_policy_accepted": False,
        "value_json_ready": False,
        "known_draft_allowed": False,
        "production_write_allowed": False,
    }


def _policy_review_template_errors(
    template: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> list[str]:
    formula_policy = packet.get("formula_policy_template")
    if not isinstance(formula_policy, Mapping):
        formula_policy = {}
    expected = {
        "template_status": "review_fill_required",
        "policy_draft_id": packet.get("policy_draft_id"),
        "source_packet_id": packet.get("source_packet_id"),
        "dp_id": packet.get("dp_id"),
        "score_target": packet.get("score_target"),
        "review_scope": "external_business_metric_formula_policy",
        "metric_family": formula_policy.get("metric_family"),
        "numeric_hits": list(packet.get("numeric_hits") or []),
        "reviewer": "",
        "reviewed_at": "",
    }
    errors: list[str] = []
    for key, expected_value in expected.items():
        if template.get(key) != expected_value:
            errors.append(f"{key} must be {expected_value!r}")
    if template.get("value_json_template") != packet.get("value_json_template"):
        errors.append("value_json_template must match policy draft")
    for key in (
        "source_scope_accepted",
        "numeric_value_selected",
        "unit_period_scope_accepted",
        "bounds_accepted",
        "formula_policy_accepted",
        "value_json_ready",
        "known_draft_allowed",
        "production_write_allowed",
    ):
        if template.get(key) is not False:
            errors.append(f"{key} must be false in blank template")
    return errors


def _draft_packet(row: Mapping[str, Any]) -> dict[str, Any]:
    dp_id = str(row.get("dp_id") or "")
    packet = {
        "policy_draft_id": _draft_id(row),
        "source_packet_id": row.get("packet_id"),
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "data_status": "Unknown",
        "readiness_priority": row.get("priority"),
        "candidate_classification": row.get("candidate_classification"),
        "numeric_hits": row.get("numeric_hits") or [],
        "title": row.get("title"),
        "market_relative_path": row.get("market_relative_path"),
        "excerpt": row.get("excerpt"),
        "policy_draft_status": "formula_policy_review_required",
        "formula_policy_template": _policy_template(dp_id),
        "value_json_template": {
            "data_status": "Unknown",
            "metric_family": _policy_template(dp_id)["metric_family"],
            "raw_value": None,
            "unit": "review_required",
            "period": "review_required",
            "scope": "review_required",
            "bounds": "review_required",
            "formula_policy": "review_required",
            "source_packet_id": row.get("packet_id"),
        },
        "review_blockers": _review_blockers(row),
        "missing_before_known": [
            "reviewed_source_scope",
            "reviewed_numeric_value",
            "reviewed_bounds",
            "reviewed_formula_policy",
            "approval_record",
        ],
        "metric_inputs_ready": False,
        "known_draft_sufficient": False,
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "score_mutation": "none",
    }
    policy_review_template = _policy_review_template(packet)
    policy_review_template_errors = _policy_review_template_errors(
        policy_review_template,
        packet,
    )
    packet = {
        **packet,
        "policy_review_template": policy_review_template,
        "policy_review_template_contract_valid": not policy_review_template_errors,
        "policy_review_template_validation_errors": policy_review_template_errors,
    }
    errors = _validation_errors(packet)
    return {
        **packet,
        "policy_contract_valid": not errors,
        "policy_validation_errors": errors,
    }


def _validation_errors(packet: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not packet.get("policy_draft_id"):
        errors.append("policy_draft_id is required")
    if not packet.get("source_packet_id"):
        errors.append("source_packet_id is required")
    if packet.get("data_status") != "Unknown":
        errors.append("data_status must remain Unknown")
    if packet.get("readiness_priority") != "P0_formula_policy_only":
        errors.append("policy drafts only accept P0 formula-policy-only packets")
    if packet.get("metric_inputs_ready") is not False:
        errors.append("metric_inputs_ready must remain false")
    if packet.get("known_draft_sufficient") is not False:
        errors.append("known_draft_sufficient must remain false")
    if packet.get("review_status") != "review_required":
        errors.append("review_status must be review_required")
    if packet.get("runtime_write_allowed") is not False:
        errors.append("runtime_write_allowed must be false")
    if packet.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    if not packet.get("review_blockers"):
        errors.append("review_blockers are required")
    if packet.get("policy_review_template_contract_valid") is not True:
        errors.append("policy_review_template contract must be valid")
    errors.extend(
        str(item) for item in packet.get("policy_review_template_validation_errors") or []
    )
    return errors


def build_report(*, readiness_queue_path: Path) -> dict[str, Any]:
    started = time.time()
    readiness_queue = _load_json(readiness_queue_path)
    p0_rows = [
        row
        for row in readiness_queue.get("rows") or []
        if isinstance(row, Mapping) and row.get("priority") == "P0_formula_policy_only"
    ]
    drafts = [_draft_packet(row) for row in p0_rows]
    drafts.sort(
        key=lambda row: (
            str(row.get("dp_id") or ""),
            str(row.get("market_relative_path") or ""),
            str(row.get("excerpt") or ""),
        )
    )
    by_dp = Counter(str(row.get("dp_id") or "") for row in drafts)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "readiness_queue_path": _portable_path(readiness_queue_path),
        },
        "summary": {
            "p0_source_packet_count": len(p0_rows),
            "policy_draft_packet_count": len(drafts),
            "formula_policy_review_required_count": len(drafts),
            "value_json_template_count": len(drafts),
            "policy_review_template_count": sum(
                1 for row in drafts if row["policy_review_template"]
            ),
            "policy_review_template_contract_valid_count": sum(
                1 for row in drafts if row["policy_review_template_contract_valid"]
            ),
            "policy_review_template_contract_invalid_count": sum(
                1
                for row in drafts
                if row["policy_review_template"]
                and not row["policy_review_template_contract_valid"]
            ),
            "policy_review_template_blank_pending_count": sum(
                1
                for row in drafts
                if (
                    isinstance(row.get("policy_review_template"), Mapping)
                    and row["policy_review_template"].get("template_status")
                    == "review_fill_required"
                    and row["policy_review_template"].get("reviewer") == ""
                    and row["policy_review_template"].get("reviewed_at") == ""
                )
            ),
            "policy_review_template_input_ready_count": 0,
            "metric_inputs_ready_count": 0,
            "known_draft_sufficient_count": 0,
            "policy_contract_valid_count": sum(
                1 for row in drafts if row["policy_contract_valid"]
            ),
            "policy_contract_invalid_count": sum(
                1 for row in drafts if not row["policy_contract_valid"]
            ),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "policy_draft_counts_by_dp_id": dict(sorted(by_dp.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": drafts,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown external business metric policy drafts",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- P0 source packets: `{summary['p0_source_packet_count']}`",
        f"- Policy draft packets: `{summary['policy_draft_packet_count']}`",
        f"- Formula-policy review required: `{summary['formula_policy_review_required_count']}`",
        f"- Value JSON templates: `{summary['value_json_template_count']}`",
        f"- Policy review templates: `{summary['policy_review_template_count']}`",
        f"- Policy review template contracts valid: `{summary['policy_review_template_contract_valid_count']}`",
        f"- Policy review template contracts invalid: `{summary['policy_review_template_contract_invalid_count']}`",
        f"- Policy review templates blank pending: `{summary['policy_review_template_blank_pending_count']}`",
        f"- Policy review template inputs ready: `{summary['policy_review_template_input_ready_count']}`",
        f"- Metric inputs ready: `{summary['metric_inputs_ready_count']}`",
        f"- Known-draft sufficient: `{summary['known_draft_sufficient_count']}`",
        f"- Policy contracts valid: `{summary['policy_contract_valid_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Policy Draft Counts By dp_id",
        "",
        "| dp_id | drafts |",
        "|---|---:|",
    ]
    for dp_id, count in summary["policy_draft_counts_by_dp_id"].items():
        lines.append(f"| `{dp_id}` | {count} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Drafts provide review templates for bounds and formula policy only.",
            "- They do not select a Known value and cannot be written to runtime.",
            "- A reviewed value_json and matching approval record are still required.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness-queue-path", type=Path, default=DEFAULT_READINESS_QUEUE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(readiness_queue_path=args.readiness_queue_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
