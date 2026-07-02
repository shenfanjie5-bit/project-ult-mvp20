#!/usr/bin/env python3
"""Package local-structured source candidates into review packets.

The source-candidate audit identifies which DOCKCASE/Tushare fields can help
close four local-structured A-share Unknown rows. This handoff layer turns those
findings into reviewer packets and records the missing formula inputs that still
prevent Known score values. It never writes runtime values or approvals.
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

from scripts.audit_a_share_local_single_dependency_policy_drafts import (
    ROOT,
    _load_json,
    _portable_path,
)
from scripts.audit_a_share_local_structured_source_candidates import (
    DEFAULT_JSON_OUTPUT as DEFAULT_SOURCE_CANDIDATES_PATH,
)
from scripts.audit_a_share_local_structured_unknown_source_options import (
    DEFAULT_JSON_OUTPUT as DEFAULT_UNKNOWN_OPTIONS_PATH,
)


DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_local_structured_source_review_packets_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_local_structured_source_review_packets_2026-06-19.md"
)


FIELD_REVIEW_POLICIES: dict[str, dict[str, Any]] = {
    "L0.cost.rent": {
        "packet_status": "review_candidate_ready",
        "candidate_use": "lease_burden_proxy_review",
        "available_formula_inputs": ["use_right_asset_dep"],
        "missing_formula_inputs": [
            "rent expense or lease payment amount",
            "lease-liability denominator or revenue denominator",
            "reviewed conservative proxy formula and score bounds",
        ],
        "review_questions": [
            "Is use_right_asset_dep acceptable as a lease-burden proxy for this field?",
            "Should the denominator be revenue, operating cash flow, or total cost?",
            "What cap/floor keeps the proxy from overstating rent burden?",
        ],
    },
    "L0.demand.frequency": {
        "packet_status": "external_source_required",
        "candidate_use": "no_catalog_business_frequency_source",
        "available_formula_inputs": [],
        "missing_formula_inputs": [
            "order count, transaction count, shipment frequency, or usage cadence",
            "active customer or user denominator when cadence is normalized",
            "reviewed decomposition separating cadence from ASP and revenue growth",
        ],
        "review_questions": [
            "Which source controls customer/order/usage frequency for this company?",
            "Is the field inapplicable for the business model, or only missing?",
            "Can text evidence be converted into a bounded cadence signal?",
        ],
    },
    "L0.demand.penetration": {
        "packet_status": "external_source_required",
        "candidate_use": "no_catalog_tam_or_share_source",
        "available_formula_inputs": [],
        "missing_formula_inputs": [
            "market share or TAM denominator",
            "company installed base, customer base, or relevant revenue numerator",
            "reviewed source precedence for industry denominator",
        ],
        "review_questions": [
            "Which TAM/share/installed-base source is authoritative for this company?",
            "Does the available company disclosure align to the same market denominator?",
            "Should the field stay Unknown until governed industry denominators exist?",
        ],
    },
    "L0.price.product_asp": {
        "packet_status": "supporting_candidate_needs_quantity_source",
        "candidate_use": "product_mix_and_revenue_numerator_review",
        "available_formula_inputs": ["bz_item", "bz_sales", "bz_cost", "bz_profit"],
        "missing_formula_inputs": [
            "unit volume, shipment volume, or product quantity",
            "product-level price index when volume is unavailable",
            "reviewed mapping from business-segment item to ASP-bearing product",
        ],
        "review_questions": [
            "Which bz_item rows are product rows rather than geography or industry rows?",
            "Can product revenue be paired with a reviewed unit/shipment source?",
            "Should the packet be used only for mix context until quantity is found?",
        ],
    },
}


def _rows_by_dp(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = dict(row)
    return rows


def _candidate_columns(matches: list[Mapping[str, Any]]) -> list[str]:
    columns: list[str] = []
    for match in matches:
        column = str(match.get("column") or "")
        if column and column not in columns:
            columns.append(column)
    return columns


def _source_examples(matches: list[Mapping[str, Any]]) -> list[str]:
    examples: list[str] = []
    for match in matches:
        for example in match.get("examples") or []:
            example_str = str(example)
            if example_str and example_str not in examples:
                examples.append(example_str)
    return examples[:5]


def _validation_errors(packet: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not packet.get("dp_id"):
        errors.append("dp_id is required")
    if not packet.get("score_target"):
        errors.append("score_target is required")
    if packet.get("data_status") != "Unknown":
        errors.append("data_status must stay Unknown")
    if packet.get("review_status") != "review_required":
        errors.append("review_status must be review_required")
    if packet.get("direct_known_ready") is not False:
        errors.append("direct_known_ready must be false")
    if packet.get("formula_inputs_ready") is not False:
        errors.append("formula_inputs_ready must be false")
    if packet.get("safe_to_upsert_without_review") is not False:
        errors.append("safe_to_upsert_without_review must be false")
    if packet.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    status = str(packet.get("source_review_packet_status") or "")
    if status in {"review_candidate_ready", "supporting_candidate_needs_quantity_source"}:
        if not packet.get("candidate_columns"):
            errors.append("candidate packet requires candidate_columns")
        if not packet.get("source_examples"):
            errors.append("candidate packet requires source_examples")
    return errors


def _packet(
    candidate_row: Mapping[str, Any],
    unknown_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    dp_id = str(candidate_row.get("dp_id") or "")
    policy = FIELD_REVIEW_POLICIES.get(dp_id, {})
    review_candidates = [
        match
        for match in candidate_row.get("review_candidates") or []
        if isinstance(match, Mapping)
    ]
    supporting_candidates = [
        match
        for match in candidate_row.get("supporting_candidates") or []
        if isinstance(match, Mapping)
    ]
    empty_candidates = [
        match
        for match in candidate_row.get("empty_candidates") or []
        if isinstance(match, Mapping)
    ]
    candidate_matches = review_candidates + supporting_candidates
    candidate_columns = _candidate_columns(candidate_matches)
    packet = {
        "dp_id": dp_id,
        "score_target": candidate_row.get("score_target")
        or (unknown_row or {}).get("score_target"),
        "data_status": "Unknown",
        "source_review_packet_status": policy.get(
            "packet_status", "review_policy_required"
        ),
        "candidate_use": policy.get("candidate_use", "review_required"),
        "candidate_status": candidate_row.get("candidate_status"),
        "direct_known_ready": False,
        "formula_inputs_ready": False,
        "candidate_columns": candidate_columns,
        "empty_candidate_columns": _candidate_columns(empty_candidates),
        "available_formula_inputs": list(policy.get("available_formula_inputs") or []),
        "missing_formula_inputs": list(policy.get("missing_formula_inputs") or []),
        "review_questions": list(policy.get("review_questions") or []),
        "review_candidate_count": int(candidate_row.get("review_candidate_count") or 0),
        "supporting_candidate_count": int(candidate_row.get("supporting_candidate_count") or 0),
        "empty_candidate_count": int(candidate_row.get("empty_candidate_count") or 0),
        "excluded_false_positive_count": int(
            candidate_row.get("excluded_false_positive_count") or 0
        ),
        "source_examples": _source_examples(candidate_matches),
        "source_candidate_refs": candidate_matches,
        "empty_candidate_refs": empty_candidates,
        "direct_known_blocker": candidate_row.get("direct_known_blocker"),
        "next_tushare_action": candidate_row.get("next_tushare_action"),
        "llm_or_web_fallback": candidate_row.get("llm_or_web_fallback"),
        "source_reports": [
            "docs/audit/a_share_local_structured_source_candidates_2026-06-19.json",
            "docs/audit/a_share_local_structured_unknown_source_options_2026-06-19.json",
        ],
        "review_checklist": [
            "confirm candidate field semantics match the target dp_id",
            "confirm all required formula inputs are present before Known scoring",
            "reject stock market, shareholder, index, or trading fields as business proxies",
            "keep data_status=Unknown until a bounded value_json formula is reviewed",
            "do not approve runtime writes from this packet alone",
        ],
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "production_write_allowed": False,
        "score_mutation": "none",
    }
    errors = _validation_errors(packet)
    return {
        **packet,
        "packet_contract_valid": not errors,
        "packet_validation_errors": errors,
    }


def build_report(
    *,
    source_candidates_path: Path,
    unknown_options_path: Path,
) -> dict[str, Any]:
    started = time.time()
    source_candidates = _load_json(source_candidates_path)
    unknown_rows = _rows_by_dp(_load_json(unknown_options_path))
    packets = [
        _packet(row, unknown_rows.get(str(row.get("dp_id") or "")))
        for row in source_candidates.get("rows") or []
        if isinstance(row, Mapping)
    ]
    packets.sort(key=lambda row: str(row.get("dp_id") or ""))
    status_counts: dict[str, int] = {}
    for packet in packets:
        status = str(packet["source_review_packet_status"])
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "source_candidates_path": _portable_path(source_candidates_path),
            "unknown_options_path": _portable_path(unknown_options_path),
        },
        "summary": {
            "local_structured_source_review_packet_count": len(packets),
            "review_candidate_ready_count": status_counts.get("review_candidate_ready", 0),
            "supporting_candidate_needs_quantity_source_count": status_counts.get(
                "supporting_candidate_needs_quantity_source", 0
            ),
            "external_source_required_count": status_counts.get(
                "external_source_required", 0
            ),
            "direct_known_ready_count": sum(
                1 for packet in packets if packet["direct_known_ready"]
            ),
            "formula_inputs_ready_count": sum(
                1 for packet in packets if packet["formula_inputs_ready"]
            ),
            "candidate_packet_count": sum(
                1 for packet in packets if packet["candidate_columns"]
            ),
            "candidate_column_count": sum(
                len(packet["candidate_columns"]) for packet in packets
            ),
            "empty_candidate_column_count": sum(
                len(packet["empty_candidate_columns"]) for packet in packets
            ),
            "excluded_false_positive_count": sum(
                int(packet["excluded_false_positive_count"]) for packet in packets
            ),
            "packet_contract_valid_count": sum(
                1 for packet in packets if packet["packet_contract_valid"]
            ),
            "packet_contract_invalid_count": sum(
                1 for packet in packets if not packet["packet_contract_valid"]
            ),
            "review_required_count": len(packets),
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "source_review_packet_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": packets,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share local structured source review packets",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Source-review packets: `{summary['local_structured_source_review_packet_count']}`",
        f"- Review candidate ready: `{summary['review_candidate_ready_count']}`",
        f"- Supporting candidate needs quantity source: `{summary['supporting_candidate_needs_quantity_source_count']}`",
        f"- External source required: `{summary['external_source_required_count']}`",
        f"- Direct Known-ready: `{summary['direct_known_ready_count']}`",
        f"- Formula inputs ready: `{summary['formula_inputs_ready_count']}`",
        f"- Candidate packets: `{summary['candidate_packet_count']}`",
        f"- Candidate columns: `{summary['candidate_column_count']}`",
        f"- Empty candidate columns: `{summary['empty_candidate_column_count']}`",
        f"- Excluded false positives: `{summary['excluded_false_positive_count']}`",
        f"- Packet contracts valid: `{summary['packet_contract_valid_count']}`",
        f"- Packet contracts invalid: `{summary['packet_contract_invalid_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | status | candidates | missing formula inputs | contract | production write |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row.get('source_review_packet_status', '-')}` | "
            f"{len(row.get('candidate_columns') or [])} | "
            f"{len(row.get('missing_formula_inputs') or [])} | "
            f"{'yes' if row.get('packet_contract_valid') else 'no'} | "
            f"{'yes' if row.get('production_write_allowed') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `L0.cost.rent` has a reviewable lease-burden proxy candidate, but formula inputs are not complete.",
            "- `L0.price.product_asp` has product-mix and revenue/cost support, but still needs unit volume, shipment volume, or a governed price index.",
            "- `L0.demand.frequency` and `L0.demand.penetration` require external business sources or text/web extraction.",
            "- All packets remain Unknown, review-required, and non-writable.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-candidates-path",
        type=Path,
        default=DEFAULT_SOURCE_CANDIDATES_PATH,
    )
    parser.add_argument(
        "--unknown-options-path",
        type=Path,
        default=DEFAULT_UNKNOWN_OPTIONS_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        source_candidates_path=args.source_candidates_path,
        unknown_options_path=args.unknown_options_path,
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
