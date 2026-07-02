#!/usr/bin/env python3
"""Package DOCKCASE market-doc event evidence into review packets.

This is the handoff layer between the local market-document evidence scan and a
future classifier/reviewer decision. It records which first-pass event-text rows
have same-sentence target/direct-transmission candidates, but it never converts
them to Known values or writes score data.
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

from scripts.audit_a_share_local_single_dependency_policy_drafts import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_MARKET_DOC_EVIDENCE_PATH = (
    ROOT / "docs/audit/a_share_event_text_market_doc_evidence_2026-06-19.json"
)
DEFAULT_EVENT_UNKNOWN_PATH = (
    ROOT / "docs/audit/a_share_event_text_classification_inputs_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.md"
)


def _rows_by_dp(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = dict(row)
    return rows


def _packet_status(row: Mapping[str, Any]) -> str:
    if int(row.get("docs_with_target_evidence") or 0) <= 0:
        return "requires_target_event_evidence"
    if int(row.get("docs_with_same_sentence_target_direct") or 0) <= 0:
        return "requires_direct_transmission_link"
    return "market_doc_review_ready"


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
    if packet.get("safe_to_upsert_without_review") is not False:
        errors.append("safe_to_upsert_without_review must be false")
    if packet.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    status = str(packet.get("classification_packet_status") or "")
    if status == "market_doc_review_ready":
        examples = packet.get("candidate_examples")
        if not isinstance(examples, list) or not examples:
            errors.append("review-ready packets require candidate_examples")
    return errors


def _packet(row: Mapping[str, Any], unknown_row: Mapping[str, Any] | None) -> dict[str, Any]:
    status = _packet_status(row)
    examples = row.get("retained_examples")
    examples = examples if isinstance(examples, list) else []
    blocked_reason = {
        "market_doc_review_ready": "classifier_review_required",
        "requires_target_event_evidence": "market_doc_target_event_evidence_required",
        "requires_direct_transmission_link": "market_doc_direct_transmission_link_required",
    }[status]
    required_evidence = {
        "market_doc_review_ready": [
            "reviewed target event concept",
            "reviewed direction and magnitude",
            "reviewed A-share transmission path",
            "bounded value_json contract",
        ],
        "requires_target_event_evidence": [
            "target-event evidence from a primary article/body paragraph",
            "same-source direct A-share transmission evidence",
        ],
        "requires_direct_transmission_link": [
            "same-sentence or same-paragraph direct A-share transmission link",
            "reviewed direction and magnitude after the link is found",
        ],
    }[status]
    packet = {
        "dp_id": row.get("dp_id"),
        "score_target": row.get("score_target") or (unknown_row or {}).get("score_target"),
        "data_status": "Unknown",
        "classification_packet_status": status,
        "blocked_reason": blocked_reason,
        "required_evidence": required_evidence,
        "target_keywords": row.get("target_keywords") or [],
        "candidate_doc_counts": {
            "docs_with_target_evidence": row.get("docs_with_target_evidence"),
            "docs_with_direct_transmission": row.get("docs_with_direct_transmission"),
            "docs_with_target_and_direct": row.get("docs_with_target_and_direct"),
            "docs_with_same_sentence_target_direct": row.get(
                "docs_with_same_sentence_target_direct"
            ),
            "docs_with_broad_market_only": row.get("docs_with_broad_market_only"),
        },
        "candidate_examples": examples[:5] if status == "market_doc_review_ready" else [],
        "source_reports": [
            "docs/audit/a_share_event_text_market_doc_evidence_2026-06-19.json",
            "docs/audit/a_share_event_text_classification_inputs_2026-06-19.json",
        ],
        "review_checklist": [
            "confirm the snippet is primary article text, not recommendation/sidebar text",
            "confirm target event concept matches the dp_id",
            "confirm direct A-share or industry transmission is causal and relevant",
            "assign direction and magnitude only after review",
            "keep Unknown if the evidence is broad-market-only or ambiguous",
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
    market_doc_evidence_path: Path,
    event_unknown_path: Path,
) -> dict[str, Any]:
    started = time.time()
    market_doc_evidence = _load_json(market_doc_evidence_path)
    unknown_rows = _rows_by_dp(_load_json(event_unknown_path))
    packets = [
        _packet(row, unknown_rows.get(str(row.get("dp_id") or "")))
        for row in (market_doc_evidence.get("rows") or [])
        if isinstance(row, Mapping)
    ]
    packets.sort(key=lambda row: str(row.get("dp_id") or ""))
    status_counts: dict[str, int] = {}
    for packet in packets:
        status = str(packet["classification_packet_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "market_doc_evidence_path": _portable_path(market_doc_evidence_path),
            "event_unknown_path": _portable_path(event_unknown_path),
        },
        "summary": {
            "event_text_packet_count": len(packets),
            "market_doc_review_ready_count": status_counts.get(
                "market_doc_review_ready", 0
            ),
            "requires_target_event_evidence_count": status_counts.get(
                "requires_target_event_evidence", 0
            ),
            "requires_direct_transmission_link_count": status_counts.get(
                "requires_direct_transmission_link", 0
            ),
            "candidate_example_count": sum(
                len(packet.get("candidate_examples") or []) for packet in packets
            ),
            "packet_contract_valid_count": sum(
                1 for packet in packets if packet["packet_contract_valid"]
            ),
            "packet_contract_invalid_count": sum(
                1 for packet in packets if not packet["packet_contract_valid"]
            ),
            "auto_known_candidate_count": 0,
            "review_required_count": len(packets),
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "classification_packet_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": packets,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share event-text market-doc review packets",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Event-text packets: `{summary['event_text_packet_count']}`",
        f"- Market-doc review-ready: `{summary['market_doc_review_ready_count']}`",
        f"- Requires target-event evidence: `{summary['requires_target_event_evidence_count']}`",
        f"- Requires direct-transmission link: `{summary['requires_direct_transmission_link_count']}`",
        f"- Candidate examples: `{summary['candidate_example_count']}`",
        f"- Packet contracts valid: `{summary['packet_contract_valid_count']}`",
        f"- Packet contracts invalid: `{summary['packet_contract_invalid_count']}`",
        f"- Auto Known candidates allowed: `{summary['auto_known_candidate_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | target | status | examples | contract | production write |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row.get('score_target', '-')}` | "
            f"`{row.get('classification_packet_status', '-')}` | "
            f"{len(row.get('candidate_examples') or [])} | "
            f"{'yes' if row.get('packet_contract_valid') else 'no'} | "
            f"{'yes' if row.get('production_write_allowed') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Review-ready packets are classifier/reviewer inputs only.",
            "- They do not contain Known score values and cannot be written to runtime.",
            "- A separate reviewed classification plus approval gate is still required.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--market-doc-evidence-path",
        type=Path,
        default=DEFAULT_MARKET_DOC_EVIDENCE_PATH,
    )
    parser.add_argument("--event-unknown-path", type=Path, default=DEFAULT_EVENT_UNKNOWN_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        market_doc_evidence_path=args.market_doc_evidence_path,
        event_unknown_path=args.event_unknown_path,
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
