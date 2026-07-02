#!/usr/bin/env python3
"""Classify source options for A-share event-text Unknown drafts.

The event-text pilot keeps 12 rows Unknown because headlines and fetched CLS
article bodies still do not provide a reviewed target event plus direct A-share
transmission path. This read-only audit records which text evidence is ready
and what source/classification work is still required.
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


DEFAULT_EVENT_TEXT_PATH = ROOT / "docs/audit/a_share_event_text_policy_drafts_2026-06-19.json"
DEFAULT_CLASSIFICATION_INPUTS_PATH = (
    ROOT / "docs/audit/a_share_event_text_classification_inputs_2026-06-19.json"
)
DEFAULT_SUFFICIENCY_PATH = ROOT / "docs/audit/a_share_event_text_sufficiency_gate_2026-06-19.json"
DEFAULT_URL_FETCHABILITY_PATH = ROOT / "docs/audit/a_share_event_text_url_fetchability_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_event_text_unknown_source_options_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_event_text_unknown_source_options_2026-06-19.md"


def _rows_by_dp(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            out[dp_id] = row
    return out


def _unknown_event_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        payload = row.get("draft_payload")
        if isinstance(payload, Mapping) and payload.get("data_status") == "Unknown":
            rows.append(row)
    return rows


def _payload_value(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = row.get("draft_payload")
    if not isinstance(payload, Mapping):
        return {}
    value = payload.get("value_json")
    return value if isinstance(value, Mapping) else {}


def _resolution_status(body_row: Mapping[str, Any] | None) -> str:
    if not isinstance(body_row, Mapping):
        return "requires_classification_input"
    if int(body_row.get("body_text_available_count") or 0) <= 0:
        return "requires_body_text_fetch"
    if body_row.get("body_signal_sufficient_for_classifier"):
        return "requires_classifier_review"
    if not body_row.get("target_keyword_hits"):
        return "requires_target_event_evidence"
    if not body_row.get("direct_transmission_keyword_hits"):
        if body_row.get("broad_market_transmission_keyword_hits"):
            return "requires_direct_a_share_transmission_not_broad_market"
        return "requires_direct_a_share_transmission"
    return "requires_reviewed_event_classification"


def _required_evidence(status: str) -> list[str]:
    if status == "requires_target_event_evidence":
        return [
            "headline/body evidence for the target event concept",
            "direction and magnitude relevant to the target dp_id",
            "reviewed A-share transmission path after target event is found",
        ]
    if status == "requires_direct_a_share_transmission_not_broad_market":
        return [
            "direct A-share, listed-company, industry, supply-chain, trade, FX, or policy transmission",
            "same article/body paragraph connecting the target event to that transmission",
            "classifier/reviewer decision for direction and magnitude",
        ]
    if status == "requires_direct_a_share_transmission":
        return [
            "direct A-share or industry transmission evidence",
            "same-source link between target event and affected A-share path",
            "classifier/reviewer decision for direction and magnitude",
        ]
    if status == "requires_classifier_review":
        return [
            "reviewed concept classification",
            "reviewed direction and magnitude",
            "reviewed A-share transmission path",
        ]
    return [
        "classification-ready event text",
        "target event evidence",
        "direct A-share transmission evidence",
    ]


def _source_routes(status: str) -> list[str]:
    routes = [
        "use current fetched CLS body text as bounded classifier input",
        "collect additional issuer/industry text when current article is broad-market-only",
        "keep output as review packet until concept, direction, magnitude, and transmission are approved",
    ]
    if status == "requires_target_event_evidence":
        routes.insert(1, "search targeted industry/news text for the dp_id event concept")
    if "transmission" in status:
        routes.insert(1, "search for direct A-share/industry/supply-chain transmission evidence")
    return routes


def build_report(
    *,
    event_text_path: Path,
    classification_inputs_path: Path,
    sufficiency_path: Path,
    url_fetchability_path: Path,
) -> dict[str, Any]:
    started = time.time()
    event_text = _load_json(event_text_path)
    classification_rows = _rows_by_dp(_load_json(classification_inputs_path))
    sufficiency_rows = _rows_by_dp(_load_json(sufficiency_path))
    body_rows = _rows_by_dp(_load_json(url_fetchability_path))
    rows: list[dict[str, Any]] = []

    for source_row in _unknown_event_rows(event_text):
        dp_id = str(source_row.get("dp_id") or "")
        body_row = body_rows.get(dp_id)
        classification_row = classification_rows.get(dp_id)
        sufficiency_row = sufficiency_rows.get(dp_id)
        status = _resolution_status(body_row)
        value_json = _payload_value(source_row)
        rows.append(
            {
                "dp_id": dp_id,
                "score_target": source_row.get("score_target"),
                "draft_status": source_row.get("draft_status"),
                "blocked_reason": value_json.get("blocked_reason"),
                "required_policy": value_json.get("required_policy"),
                "source_dependencies": source_row.get("source_dependencies") or [],
                "classification_input_ready": (
                    (classification_row or {}).get("classification_status")
                    == "classification_input_ready"
                ),
                "headline_input_count": int(
                    (classification_row or {}).get("headline_input_count") or 0
                ),
                "unique_headline_count": int(
                    (classification_row or {}).get("unique_headline_count") or 0
                ),
                "url_count": int((body_row or {}).get("url_count") or 0),
                "url_fetch_ok_count": int((body_row or {}).get("url_fetch_ok_count") or 0),
                "body_text_available_count": int(
                    (body_row or {}).get("body_text_available_count") or 0
                ),
                "target_keyword_hits": list((body_row or {}).get("target_keyword_hits") or []),
                "direct_transmission_keyword_hits": list(
                    (body_row or {}).get("direct_transmission_keyword_hits") or []
                ),
                "broad_market_transmission_keyword_hits": list(
                    (body_row or {}).get("broad_market_transmission_keyword_hits") or []
                ),
                "body_signal_sufficient_for_classifier": bool(
                    (body_row or {}).get("body_signal_sufficient_for_classifier")
                ),
                "sufficiency_status": (sufficiency_row or {}).get("sufficiency_status"),
                "resolution_status": status,
                "required_evidence": _required_evidence(status),
                "candidate_source_routes": _source_routes(status),
                "classifier_ready_for_review": bool(
                    (body_row or {}).get("body_signal_sufficient_for_classifier")
                ),
                "auto_known_candidate_allowed": False,
                "review_required": True,
                "safe_to_upsert_without_review": False,
                "production_write_allowed": False,
            }
        )

    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["resolution_status"])
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "event_text_path": _portable_path(event_text_path),
            "classification_inputs_path": _portable_path(classification_inputs_path),
            "sufficiency_path": _portable_path(sufficiency_path),
            "url_fetchability_path": _portable_path(url_fetchability_path),
        },
        "summary": {
            "unknown_event_text_count": len(rows),
            "classification_input_ready_count": sum(
                1 for row in rows if row["classification_input_ready"]
            ),
            "body_text_available_count": sum(
                1 for row in rows if row["body_text_available_count"] > 0
            ),
            "target_event_evidence_present_count": sum(
                1 for row in rows if row["target_keyword_hits"]
            ),
            "direct_a_share_transmission_present_count": sum(
                1 for row in rows if row["direct_transmission_keyword_hits"]
            ),
            "broad_market_transmission_only_count": sum(
                1
                for row in rows
                if row["broad_market_transmission_keyword_hits"]
                and not row["direct_transmission_keyword_hits"]
            ),
            "classifier_ready_for_review_count": sum(
                1 for row in rows if row["classifier_ready_for_review"]
            ),
            "candidate_requires_target_event_evidence_count": sum(
                1
                for row in rows
                if row["resolution_status"] == "requires_target_event_evidence"
            ),
            "candidate_requires_direct_a_share_transmission_count": sum(
                1
                for row in rows
                if row["resolution_status"]
                in {
                    "requires_direct_a_share_transmission",
                    "requires_direct_a_share_transmission_not_broad_market",
                }
            ),
            "auto_known_candidate_count": sum(
                1 for row in rows if row["auto_known_candidate_allowed"]
            ),
            "review_required_count": sum(1 for row in rows if row["review_required"]),
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "resolution_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share event-text Unknown source options",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Unknown event-text rows: `{summary['unknown_event_text_count']}`",
        f"- Classification inputs ready: `{summary['classification_input_ready_count']}`",
        f"- Body text available: `{summary['body_text_available_count']}`",
        f"- Target-event evidence present: `{summary['target_event_evidence_present_count']}`",
        f"- Direct A-share transmission present: `{summary['direct_a_share_transmission_present_count']}`",
        f"- Broad-market-only transmission: `{summary['broad_market_transmission_only_count']}`",
        f"- Classifier-ready for review: `{summary['classifier_ready_for_review_count']}`",
        f"- Target-event evidence still required: `{summary['candidate_requires_target_event_evidence_count']}`",
        f"- Direct A-share transmission still required: `{summary['candidate_requires_direct_a_share_transmission_count']}`",
        f"- Auto Known candidates allowed: `{summary['auto_known_candidate_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Resolution Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["resolution_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | class input | body text | target event | direct transmission | status | production write |",
            "|---|---:|---:|---:|---:|---|---:|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"{'yes' if row['classification_input_ready'] else 'no'} | "
            f"{'yes' if row['body_text_available_count'] else 'no'} | "
            f"{'yes' if row['target_keyword_hits'] else 'no'} | "
            f"{'yes' if row['direct_transmission_keyword_hits'] else 'no'} | "
            f"`{row['resolution_status']}` | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Current event-text data is fetchable and usable as bounded review input, but it is not sufficient for automatic Known values.",
            "- Nine rows still lack target-event evidence in the fetched body text.",
            "- Three rows have target-event evidence but still lack direct A-share transmission; broad China A50/futures hits are not enough.",
            "- Production score-affecting writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-text-path", type=Path, default=DEFAULT_EVENT_TEXT_PATH)
    parser.add_argument(
        "--classification-inputs-path",
        type=Path,
        default=DEFAULT_CLASSIFICATION_INPUTS_PATH,
    )
    parser.add_argument("--sufficiency-path", type=Path, default=DEFAULT_SUFFICIENCY_PATH)
    parser.add_argument(
        "--url-fetchability-path",
        type=Path,
        default=DEFAULT_URL_FETCHABILITY_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        event_text_path=args.event_text_path,
        classification_inputs_path=args.classification_inputs_path,
        sufficiency_path=args.sufficiency_path,
        url_fetchability_path=args.url_fetchability_path,
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
