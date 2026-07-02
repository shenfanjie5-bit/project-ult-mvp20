#!/usr/bin/env python3
"""Package strict-source event candidates into review packets.

The strict-source gate narrows two event Unknown rows to a small candidate set,
but those candidates still need source-quality and context review before any
classification or score value can be trusted. This audit is read-only: it
triages the strict review candidates, records obvious false positives, and
keeps all score-affecting writes disabled.
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


DEFAULT_STRICT_GATE_PATH = (
    ROOT / "docs/audit/a_share_unknown_event_strict_source_gate_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_event_strict_review_packets_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_event_strict_review_packets_2026-06-19.md"
)


def _as_text(candidate: Mapping[str, Any]) -> str:
    return " ".join(
        str(candidate.get(key) or "")
        for key in ("title", "excerpt", "market_relative_path")
    )


def _source_quality(candidate: Mapping[str, Any]) -> str:
    text = _as_text(candidate)
    if "eastmoney_guba" in text or "股吧" in text or "财富号" in text:
        return "low_confidence_community_source"
    if "cls_flash" in text or "财联社" in text:
        return "secondary_newswire"
    return "unreviewed_secondary_source"


def _source_review_status(dp_id: str, candidate: Mapping[str, Any]) -> tuple[str, str]:
    text = _as_text(candidate)
    quality = _source_quality(candidate)
    if quality == "low_confidence_community_source":
        return (
            "requires_primary_source_confirmation",
            "community_or_forum_source_cannot_support_known_value",
        )
    if dp_id == "L0.compete.new_entrant":
        return (
            "requires_manual_review",
            "new_entrant_candidate_requires_named_external_entrant_and_direct_transmission_review",
        )
    if "铝型材挤压" in text or "挤压模具" in text:
        return (
            "deterministic_rejected",
            "false_positive_process_term_not_substitution_risk",
        )
    if "德国" in text and "中国车企竞争" in text:
        return (
            "deterministic_rejected",
            "foreign_industry_pressure_without_direct_a_share_substitution_value",
        )
    if "光伏行业恢复健康" in text or "优胜劣汰" in text:
        return (
            "deterministic_rejected",
            "cycle_clearance_or_overcapacity_not_substitute_technology_risk",
        )
    if "光环效应" in text or "资产规模大" in text or "HALO" in text:
        return (
            "deterministic_rejected",
            "macro_strategy_or_factor_context_not_substitute_technology_risk",
        )
    if "俄罗斯天然气" in text or "中东LNG" in text or "热泵产品销售提升" in text:
        return (
            "deterministic_rejected",
            "geopolitical_import_shift_or_demand_opportunity_not_negative_substitute_risk",
        )
    return (
        "requires_manual_review",
        "strict_candidate_requires_human_context_review",
    )


def _required_next_evidence(status: str, reason: str) -> list[str]:
    if status == "requires_primary_source_confirmation":
        return [
            "replace community/forum lead with primary filing, exchange disclosure, company source, or high-quality research/news source",
            "confirm target event and direct A-share transmission in the same source context",
            "review direction and bounded magnitude before classification",
        ]
    if status == "requires_manual_review":
        return [
            "confirm the snippet is not boilerplate, recommendation copy, or broad market context",
            "confirm target event concept matches the dp_id",
            "confirm direct A-share company/sector/supply-chain transmission and bounded direction/magnitude",
        ]
    return [
        f"do not promote because {reason}",
        "retain as rejected evidence only",
    ]


def _packet(
    *,
    row: Mapping[str, Any],
    candidate: Mapping[str, Any],
    candidate_index: int,
) -> dict[str, Any]:
    dp_id = str(row.get("dp_id") or "")
    status, reason = _source_review_status(dp_id, candidate)
    source_quality = _source_quality(candidate)
    packet = {
        "packet_id": f"{dp_id}#strict_review_candidate#{candidate_index}",
        "dp_id": dp_id,
        "score_target": row.get("score_target"),
        "data_status": "Unknown",
        "strict_gate_status": row.get("strict_gate_status"),
        "source_quality": source_quality,
        "strict_candidate_status": status,
        "strict_candidate_reason": reason,
        "required_next_evidence": _required_next_evidence(status, reason),
        "candidate": {
            "title": candidate.get("title"),
            "market_relative_path": candidate.get("market_relative_path"),
            "excerpt": candidate.get("excerpt"),
            "strict_hits": candidate.get("strict_hits") or [],
            "direct_transmission_hits": candidate.get("direct_transmission_hits") or [],
            "strict_gate_reason": candidate.get("strict_gate_reason"),
        },
        "source_reports": [
            "docs/audit/a_share_unknown_event_strict_source_gate_2026-06-19.json",
        ],
        "classifier_ready": False,
        "known_draft_sufficient": False,
        "approval_ready": False,
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
        errors.append("data_status must remain Unknown")
    if packet.get("classifier_ready") is not False:
        errors.append("classifier_ready must be false")
    if packet.get("known_draft_sufficient") is not False:
        errors.append("known_draft_sufficient must be false")
    if packet.get("approval_ready") is not False:
        errors.append("approval_ready must be false")
    if packet.get("safe_to_upsert_without_review") is not False:
        errors.append("safe_to_upsert_without_review must be false")
    if packet.get("runtime_write_allowed") is not False:
        errors.append("runtime_write_allowed must be false")
    if packet.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    if packet.get("strict_candidate_status") not in {
        "requires_primary_source_confirmation",
        "requires_manual_review",
        "deterministic_rejected",
    }:
        errors.append("strict_candidate_status is invalid")
    return errors


def _review_candidates(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidates = row.get("candidate_examples")
    if not isinstance(candidates, list):
        return []
    return [
        candidate
        for candidate in candidates
        if isinstance(candidate, Mapping)
        and candidate.get("strict_gate_verdict") == "strict_review_candidate"
    ]


def build_report(*, strict_gate_path: Path) -> dict[str, Any]:
    started = time.time()
    strict_gate = _load_json(strict_gate_path)
    packets: list[dict[str, Any]] = []
    for row in strict_gate.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        for index, candidate in enumerate(_review_candidates(row), start=1):
            packets.append(_packet(row=row, candidate=candidate, candidate_index=index))
    packets.sort(key=lambda packet: str(packet["packet_id"]))
    status_counts = Counter(str(packet["strict_candidate_status"]) for packet in packets)
    source_quality_counts = Counter(str(packet["source_quality"]) for packet in packets)
    row_counts = Counter(str(packet["dp_id"]) for packet in packets)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "strict_gate_path": _portable_path(strict_gate_path),
        },
        "summary": {
            "strict_review_packet_count": len(packets),
            "strict_review_rows_count": len(row_counts),
            "source_quality_low_confidence_count": source_quality_counts.get(
                "low_confidence_community_source", 0
            ),
            "source_quality_secondary_newswire_count": source_quality_counts.get(
                "secondary_newswire", 0
            ),
            "requires_primary_source_confirmation_count": status_counts.get(
                "requires_primary_source_confirmation", 0
            ),
            "requires_manual_review_count": status_counts.get(
                "requires_manual_review", 0
            ),
            "deterministic_rejected_count": status_counts.get(
                "deterministic_rejected", 0
            ),
            "classifier_ready_count": 0,
            "known_draft_sufficient_count": 0,
            "approval_ready_count": 0,
            "packet_contract_valid_count": sum(
                1 for packet in packets if packet["packet_contract_valid"]
            ),
            "packet_contract_invalid_count": sum(
                1 for packet in packets if not packet["packet_contract_valid"]
            ),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "strict_candidate_status_counts": dict(sorted(status_counts.items())),
            "source_quality_counts": dict(sorted(source_quality_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": packets,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share event Unknown strict review packets",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Strict review packets: `{summary['strict_review_packet_count']}`",
        f"- Rows represented: `{summary['strict_review_rows_count']}`",
        f"- Low-confidence community/forum source packets: `{summary['source_quality_low_confidence_count']}`",
        f"- Secondary-newswire packets: `{summary['source_quality_secondary_newswire_count']}`",
        f"- Requires primary-source confirmation: `{summary['requires_primary_source_confirmation_count']}`",
        f"- Requires manual review: `{summary['requires_manual_review_count']}`",
        f"- Deterministic rejected: `{summary['deterministic_rejected_count']}`",
        f"- Classifier-ready packets: `{summary['classifier_ready_count']}`",
        f"- Known-draft sufficient packets: `{summary['known_draft_sufficient_count']}`",
        f"- Approval-ready packets: `{summary['approval_ready_count']}`",
        f"- Packet contracts valid: `{summary['packet_contract_valid_count']}`",
        f"- Packet contracts invalid: `{summary['packet_contract_invalid_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| packet | dp_id | source quality | status | reason | contract | production write |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['packet_id']}` | "
            f"`{row['dp_id']}` | "
            f"`{row['source_quality']}` | "
            f"`{row['strict_candidate_status']}` | "
            f"`{row['strict_candidate_reason']}` | "
            f"{'yes' if row.get('packet_contract_valid') else 'no'} | "
            f"{'yes' if row.get('production_write_allowed') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- These packets narrow the strict-source review queue; they do not accept evidence.",
            "- Low-confidence community/forum leads require primary-source confirmation before classification.",
            "- Deterministically rejected packets are retained only as negative evidence.",
            "- Classifier-ready, Known-draft-sufficient, approval-ready, runtime writes, and production writes remain zero.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict-gate-path", type=Path, default=DEFAULT_STRICT_GATE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    args = parser.parse_args()

    report = build_report(strict_gate_path=args.strict_gate_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
