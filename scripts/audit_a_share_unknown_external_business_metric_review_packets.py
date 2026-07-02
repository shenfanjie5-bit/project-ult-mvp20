#!/usr/bin/env python3
"""Package external business-metric market-doc candidates into review packets.

This handoff layer turns local DOCKCASE candidate snippets for frequency,
penetration, and replacement demand into candidate-level review packets. It
does not produce Known values, formulas, approvals, or runtime writes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
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


DEFAULT_MARKET_DOC_CANDIDATES_PATH = (
    ROOT
    / "docs/audit/a_share_unknown_external_business_metric_market_doc_candidates_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_external_business_metric_review_packets_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_external_business_metric_review_packets_2026-06-19.md"
)

REVIEW_CLASSIFICATIONS = {"numeric_review_candidate", "textual_review_candidate"}
PERIOD_RE = re.compile(r"(?:20\d{2}|19\d{2}|上半年|下半年|季度|一季度|二季度|三季度|四季度|年度|全年)")


def _packet_id(candidate: Mapping[str, Any], index: int) -> str:
    raw = "|".join(
        [
            str(candidate.get("dp_id") or ""),
            str(candidate.get("market_relative_path") or candidate.get("path") or ""),
            str(candidate.get("excerpt") or ""),
            str(index),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _classification_bucket(candidate: Mapping[str, Any]) -> str:
    classification = str(candidate.get("classification") or "")
    if classification in REVIEW_CLASSIFICATIONS:
        return classification
    return "not_review_candidate"


def _period_present(candidate: Mapping[str, Any]) -> bool:
    text = f"{candidate.get('title') or ''} {candidate.get('excerpt') or ''}"
    if PERIOD_RE.search(text):
        return True
    return any("年" in str(hit) or "月" in str(hit) for hit in candidate.get("numeric_hits") or [])


def _unit_present(candidate: Mapping[str, Any]) -> bool:
    return bool(candidate.get("numeric_hits"))


def _denominator_present(dp_id: str, candidate: Mapping[str, Any]) -> bool:
    excerpt = str(candidate.get("excerpt") or "")
    support_hits = set(candidate.get("support_hits") or [])
    if dp_id == "L0.demand.frequency":
        return bool(support_hits.intersection({"用户", "客户", "会员"}))
    if dp_id == "L0.demand.penetration":
        return bool({"市场", "行业", "空间", "规模"}.intersection(support_hits)) or "市场" in excerpt
    if dp_id == "L0.demand.replacement":
        return bool({"存量", "保有量"}.intersection(support_hits))
    return False


def _required_fields(dp_id: str, candidate: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    support_hits = candidate.get("support_hits") or []
    scope_hits = candidate.get("scope_hits") or []
    direct_hits = candidate.get("direct_transmission_hits") or []
    numeric_hits = candidate.get("numeric_hits") or []
    numerator_present = bool(support_hits)
    scope_present = bool(scope_hits or direct_hits)
    denominator_present = _denominator_present(dp_id, candidate)
    period_present = _period_present(candidate)
    unit_present = _unit_present(candidate)
    return {
        "metric_scope": {
            "status": "candidate_present" if scope_present else "missing",
            "evidence": scope_hits + direct_hits,
        },
        "numerator_or_metric_observation": {
            "status": "candidate_present" if numerator_present else "missing",
            "evidence": support_hits + numeric_hits,
        },
        "denominator_or_normalizer": {
            "status": "candidate_present" if denominator_present else "missing",
            "evidence": support_hits if denominator_present else [],
        },
        "period": {
            "status": "candidate_present" if period_present else "missing",
            "evidence": [hit for hit in numeric_hits if "年" in str(hit) or "月" in str(hit)],
        },
        "unit": {
            "status": "candidate_present" if unit_present else "missing",
            "evidence": numeric_hits,
        },
        "bounds": {
            "status": "review_required",
            "evidence": [],
        },
        "formula_policy": {
            "status": "review_required",
            "evidence": [],
        },
    }


def _missing_fields(required_fields: Mapping[str, Mapping[str, Any]]) -> list[str]:
    missing = []
    for name, detail in required_fields.items():
        if detail.get("status") != "candidate_present":
            missing.append(name)
    return missing


def _candidate_packet(candidate: Mapping[str, Any], index: int) -> dict[str, Any]:
    dp_id = str(candidate.get("dp_id") or "")
    required_fields = _required_fields(dp_id, candidate)
    missing = _missing_fields(required_fields)
    classification = str(candidate.get("classification") or "")
    packet = {
        "packet_id": _packet_id(candidate, index),
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "data_status": "Unknown",
        "candidate_index": index,
        "candidate_classification": classification,
        "review_packet_status": "candidate_review_required",
        "metric_inputs_ready": False,
        "known_draft_sufficient": False,
        "required_fields": required_fields,
        "missing_fields": missing,
        "target_hits": candidate.get("target_hits") or [],
        "support_hits": candidate.get("support_hits") or [],
        "scope_hits": candidate.get("scope_hits") or [],
        "direct_transmission_hits": candidate.get("direct_transmission_hits") or [],
        "numeric_hits": candidate.get("numeric_hits") or [],
        "title": candidate.get("title"),
        "market_relative_path": candidate.get("market_relative_path"),
        "path": candidate.get("path"),
        "excerpt": candidate.get("excerpt"),
        "review_checklist": [
            "confirm snippet is primary article text and not boilerplate",
            "confirm metric concept matches the dp_id",
            "confirm numerator/denominator/scope/period/unit are aligned",
            "define bounds and formula policy before any Known draft",
            "keep Unknown unless a reviewer approves a bounded value_json",
        ],
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "score_mutation": "none",
    }
    errors = _validation_errors(packet)
    return {
        **packet,
        "packet_contract_valid": not errors,
        "packet_validation_errors": errors,
    }


def _validation_errors(packet: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not packet.get("packet_id"):
        errors.append("packet_id is required")
    if not packet.get("dp_id"):
        errors.append("dp_id is required")
    if packet.get("data_status") != "Unknown":
        errors.append("data_status must stay Unknown")
    if packet.get("metric_inputs_ready") is not False:
        errors.append("metric_inputs_ready must stay false")
    if packet.get("known_draft_sufficient") is not False:
        errors.append("known_draft_sufficient must stay false")
    if packet.get("review_status") != "review_required":
        errors.append("review_status must be review_required")
    if packet.get("safe_to_upsert_without_review") is not False:
        errors.append("safe_to_upsert_without_review must be false")
    if packet.get("runtime_write_allowed") is not False:
        errors.append("runtime_write_allowed must be false")
    if packet.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    if not packet.get("missing_fields"):
        errors.append("candidate packet must retain missing fields before Known draft")
    return errors


def _review_candidates(candidate_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in candidate_report.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        for candidate in row.get("candidate_examples") or []:
            if not isinstance(candidate, Mapping):
                continue
            if _classification_bucket(candidate) not in REVIEW_CLASSIFICATIONS:
                continue
            candidates.append(dict(candidate))
    candidates.sort(
        key=lambda candidate: (
            str(candidate.get("dp_id") or ""),
            str(candidate.get("market_relative_path") or ""),
            str(candidate.get("excerpt") or ""),
        )
    )
    return candidates


def build_report(*, market_doc_candidates_path: Path) -> dict[str, Any]:
    started = time.time()
    candidate_report = _load_json(market_doc_candidates_path)
    expected_review_count = int(
        candidate_report.get("summary", {}).get("review_candidate_count") or 0
    )
    review_candidates = _review_candidates(candidate_report)
    packets = [
        _candidate_packet(candidate, index)
        for index, candidate in enumerate(review_candidates, start=1)
    ]
    by_dp: dict[str, int] = {}
    by_classification: dict[str, int] = {}
    for packet in packets:
        dp_id = str(packet["dp_id"])
        by_dp[dp_id] = by_dp.get(dp_id, 0) + 1
        classification = str(packet["candidate_classification"])
        by_classification[classification] = by_classification.get(classification, 0) + 1
    retained_complete = len(packets) == expected_review_count
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "market_doc_candidates_path": _portable_path(market_doc_candidates_path),
        },
        "summary": {
            "business_metric_review_packet_count": len(packets),
            "expected_review_candidate_count": expected_review_count,
            "review_candidate_retention_complete": retained_complete,
            "rows_with_review_packets_count": len(by_dp),
            "numeric_review_packet_count": by_classification.get(
                "numeric_review_candidate", 0
            ),
            "textual_review_packet_count": by_classification.get(
                "textual_review_candidate", 0
            ),
            "metric_inputs_ready_count": sum(
                1 for packet in packets if packet["metric_inputs_ready"]
            ),
            "known_draft_sufficient_count": sum(
                1 for packet in packets if packet["known_draft_sufficient"]
            ),
            "packets_with_scope_candidate_count": sum(
                1
                for packet in packets
                if packet["required_fields"]["metric_scope"]["status"]
                == "candidate_present"
            ),
            "packets_with_denominator_candidate_count": sum(
                1
                for packet in packets
                if packet["required_fields"]["denominator_or_normalizer"]["status"]
                == "candidate_present"
            ),
            "packets_with_period_candidate_count": sum(
                1
                for packet in packets
                if packet["required_fields"]["period"]["status"] == "candidate_present"
            ),
            "packets_with_unit_candidate_count": sum(
                1
                for packet in packets
                if packet["required_fields"]["unit"]["status"] == "candidate_present"
            ),
            "packet_contract_valid_count": sum(
                1 for packet in packets if packet["packet_contract_valid"]
            ),
            "packet_contract_invalid_count": sum(
                1 for packet in packets if not packet["packet_contract_valid"]
            ),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "packet_counts_by_dp_id": dict(sorted(by_dp.items())),
            "packet_counts_by_classification": dict(sorted(by_classification.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": packets,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown external business metric review packets",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Business metric review packets: `{summary['business_metric_review_packet_count']}`",
        f"- Expected review candidates: `{summary['expected_review_candidate_count']}`",
        f"- Review candidate retention complete: `{summary['review_candidate_retention_complete']}`",
        f"- Rows with review packets: `{summary['rows_with_review_packets_count']}`",
        f"- Numeric review packets: `{summary['numeric_review_packet_count']}`",
        f"- Textual review packets: `{summary['textual_review_packet_count']}`",
        f"- Metric inputs ready: `{summary['metric_inputs_ready_count']}`",
        f"- Known-draft sufficient: `{summary['known_draft_sufficient_count']}`",
        f"- Packet contracts valid: `{summary['packet_contract_valid_count']}`",
        f"- Packet contracts invalid: `{summary['packet_contract_invalid_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Packet Counts By dp_id",
        "",
        "| dp_id | packets |",
        "|---|---:|",
    ]
    for dp_id, count in summary["packet_counts_by_dp_id"].items():
        lines.append(f"| `{dp_id}` | {count} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Packets are candidate-level reviewer inputs, not scoreable Known values.",
            "- Each packet retains missing fields for scope, denominator, period, unit, bounds, or formula policy.",
            "- Runtime and production writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--market-doc-candidates-path",
        type=Path,
        default=DEFAULT_MARKET_DOC_CANDIDATES_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(market_doc_candidates_path=args.market_doc_candidates_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
