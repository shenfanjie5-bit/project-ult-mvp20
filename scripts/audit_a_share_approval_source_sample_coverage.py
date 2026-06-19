#!/usr/bin/env python3
"""Merge source-sample coverage for all A-share approval packets.

Bulk, event, and individual-review source-sample audits each cover a slice of
the human approval queue. This read-only gate verifies that every current
approval-review packet has the expected source-sample support and blank
review/approval templates before any reviewer fills approval records.
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


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APPROVAL_PATH = ROOT / "docs/audit/a_share_approval_review_packets_2026-06-19.json"
DEFAULT_RISK_PATH = ROOT / "docs/audit/a_share_approval_packet_risk_review_2026-06-19.json"
DEFAULT_BULK_SOURCE_PATH = (
    ROOT / "docs/audit/a_share_bulk_review_source_samples_2026-06-19.json"
)
DEFAULT_EVENT_SOURCE_PATH = (
    ROOT / "docs/audit/a_share_event_approval_source_samples_2026-06-19.json"
)
DEFAULT_INDIVIDUAL_SOURCE_PATH = (
    ROOT / "docs/audit/a_share_individual_review_source_samples_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_approval_source_sample_coverage_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_approval_source_sample_coverage_2026-06-19.md"
)

BULK_RISK_CLASSES = {
    "bulk_structured_review_candidate",
    "borderline_structured_text_review_candidate",
}
EVENT_EVIDENCE_RISK_CLASS = "individual_event_evidence_review_required"
INDIVIDUAL_RISK_CLASSES = {
    "individual_structured_review_required",
    "individual_policy_review_required",
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
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = dict(row)
    return rows


def _approval_template_blank_and_valid(template: Mapping[str, Any]) -> bool:
    return bool(
        template.get("approval_id") == ""
        and template.get("approval_status") == ""
        and template.get("approval_scope") == "runtime_write"
        and template.get("reviewer") == ""
        and template.get("approved_at") == ""
        and template.get("risk_acknowledged") is False
        and template.get("template_status") == "review_fill_required"
    )


def _source_route(risk_class: str) -> str:
    if risk_class in BULK_RISK_CLASSES:
        return "bulk_review_source_sample"
    if risk_class == EVENT_EVIDENCE_RISK_CLASS:
        return "event_approval_source_sample"
    if risk_class in INDIVIDUAL_RISK_CLASSES:
        return "individual_review_source_sample"
    return "unsupported"


def _sample_row_for_route(
    *,
    dp_id: str,
    route: str,
    bulk_rows: Mapping[str, dict[str, Any]],
    event_rows: Mapping[str, dict[str, Any]],
    individual_rows: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    if route == "bulk_review_source_sample":
        return dict(bulk_rows.get(dp_id, {}))
    if route == "event_approval_source_sample":
        return dict(event_rows.get(dp_id, {}))
    if route == "individual_review_source_sample":
        return dict(individual_rows.get(dp_id, {}))
    return {}


def _template_contract_valid(route: str, sample_row: Mapping[str, Any]) -> bool:
    if route == "bulk_review_source_sample":
        return bool(sample_row.get("approval_record_draft_blank_contract_valid"))
    if route == "event_approval_source_sample":
        return bool(sample_row.get("event_evidence_review_template_contract_valid"))
    if route == "individual_review_source_sample":
        return bool(sample_row.get("individual_review_template_contract_valid"))
    return False


def _candidate_row(
    *,
    approval: Mapping[str, Any],
    risk_row: Mapping[str, Any],
    bulk_rows: Mapping[str, dict[str, Any]],
    event_rows: Mapping[str, dict[str, Any]],
    individual_rows: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    dp_id = str(approval.get("dp_id") or "")
    risk_class = str(risk_row.get("risk_class") or "")
    route = _source_route(risk_class)
    sample_row = _sample_row_for_route(
        dp_id=dp_id,
        route=route,
        bulk_rows=bulk_rows,
        event_rows=event_rows,
        individual_rows=individual_rows,
    )
    approval_template = approval.get("approval_record_template")
    approval_template = approval_template if isinstance(approval_template, Mapping) else {}
    approval_template_valid = bool(
        approval.get("approval_record_template_contract_valid")
        and _approval_template_blank_and_valid(approval_template)
    )
    source_sample_found = bool(sample_row)
    source_sample_complete = bool(sample_row.get("reviewer_packet_complete"))
    source_payload_matches = bool(sample_row.get("source_payload_matches_candidate"))
    source_template_valid = _template_contract_valid(route, sample_row)
    supplemental_event_row = (
        event_rows.get(dp_id, {})
        if route == "individual_review_source_sample"
        and approval.get("source_kind") == "event_text_policy_pilot"
        else {}
    )
    supplemental_event_complete = (
        bool(supplemental_event_row.get("reviewer_packet_complete"))
        if supplemental_event_row
        else None
    )
    approval_input_ready = bool(
        approval_template_valid
        and source_sample_found
        and source_sample_complete
        and source_payload_matches
        and source_template_valid
    )
    if supplemental_event_complete is False:
        approval_input_ready = False
    return {
        "dp_id": dp_id,
        "score_target": approval.get("score_target"),
        "source_kind": approval.get("source_kind"),
        "risk_class": risk_class,
        "risk_reasons": list(risk_row.get("risk_reasons") or []),
        "source_sample_route": route,
        "source_sample_found": source_sample_found,
        "source_sample_reviewer_packet_complete": source_sample_complete,
        "source_sample_payload_matches_candidate": source_payload_matches,
        "source_sample_review_template_contract_valid": source_template_valid,
        "supplemental_event_source_sample_complete": supplemental_event_complete,
        "approval_record_template_blank_contract_valid": approval_template_valid,
        "approval_gate_status": approval.get("approval_gate_status"),
        "approval_payload_hash_matches_manifest": approval.get(
            "approval_payload_hash_matches_manifest"
        ),
        "payload_sha256": approval.get("payload_sha256"),
        "approval_input_ready": approval_input_ready,
        "approved_runtime_write": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def build_report(
    *,
    approval_path: Path,
    risk_path: Path,
    bulk_source_path: Path,
    event_source_path: Path,
    individual_source_path: Path,
) -> dict[str, Any]:
    started = time.time()
    approvals = _load_json(approval_path)
    risk_rows = _rows_by_dp(_load_json(risk_path))
    bulk_rows = _rows_by_dp(_load_json(bulk_source_path))
    event_rows = _rows_by_dp(_load_json(event_source_path))
    individual_rows = _rows_by_dp(_load_json(individual_source_path))
    rows = []
    for approval in approvals.get("rows") or []:
        if not isinstance(approval, Mapping):
            continue
        dp_id = str(approval.get("dp_id") or "")
        rows.append(
            _candidate_row(
                approval=approval,
                risk_row=risk_rows.get(dp_id, {}),
                bulk_rows=bulk_rows,
                event_rows=event_rows,
                individual_rows=individual_rows,
            )
        )
    rows.sort(key=lambda row: (str(row.get("source_sample_route") or ""), str(row.get("dp_id") or "")))
    route_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    for row in rows:
        route = str(row.get("source_sample_route") or "")
        risk_class = str(row.get("risk_class") or "")
        route_counts[route] = route_counts.get(route, 0) + 1
        risk_counts[risk_class] = risk_counts.get(risk_class, 0) + 1
    summary = {
        "approval_packet_count": len(rows),
        "source_sample_supported_packet_count": sum(
            1 for row in rows if row["source_sample_route"] != "unsupported"
        ),
        "source_sample_found_count": sum(1 for row in rows if row["source_sample_found"]),
        "source_sample_reviewer_packet_complete_count": sum(
            1 for row in rows if row["source_sample_reviewer_packet_complete"]
        ),
        "source_sample_payload_matches_candidate_count": sum(
            1 for row in rows if row["source_sample_payload_matches_candidate"]
        ),
        "source_sample_review_template_contract_valid_count": sum(
            1 for row in rows if row["source_sample_review_template_contract_valid"]
        ),
        "approval_record_template_blank_contract_valid_count": sum(
            1 for row in rows if row["approval_record_template_blank_contract_valid"]
        ),
        "approval_input_ready_count": sum(1 for row in rows if row["approval_input_ready"]),
        "approval_input_not_ready_count": sum(
            1 for row in rows if not row["approval_input_ready"]
        ),
        "supplemental_event_source_sample_complete_count": sum(
            1 for row in rows if row["supplemental_event_source_sample_complete"] is True
        ),
        "unsupported_risk_class_count": sum(
            1 for row in rows if row["source_sample_route"] == "unsupported"
        ),
        "source_sample_route_counts": dict(sorted(route_counts.items())),
        "risk_class_counts": dict(sorted(risk_counts.items())),
        "approved_runtime_write_count": 0,
        "runtime_write_allowed_count": 0,
        "production_write_allowed_count": 0,
        "score_mutation": "none; approval source-sample coverage is read-only and does not alter realtime_current",
    }
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "approval_path": _portable_path(approval_path),
            "risk_path": _portable_path(risk_path),
            "bulk_source_path": _portable_path(bulk_source_path),
            "event_source_path": _portable_path(event_source_path),
            "individual_source_path": _portable_path(individual_source_path),
        },
        "summary": summary,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share approval source-sample coverage gate",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Approval packets checked: `{summary['approval_packet_count']}`",
        f"- Source-sample supported packets: `{summary['source_sample_supported_packet_count']}`",
        f"- Source samples found: `{summary['source_sample_found_count']}`",
        f"- Source-sample reviewer packets complete: `{summary['source_sample_reviewer_packet_complete_count']}`",
        f"- Source payloads match candidates: `{summary['source_sample_payload_matches_candidate_count']}`",
        f"- Source-sample review templates valid: `{summary['source_sample_review_template_contract_valid_count']}`",
        f"- Approval templates blank/valid: `{summary['approval_record_template_blank_contract_valid_count']}`",
        f"- Approval inputs ready: `{summary['approval_input_ready_count']}`",
        f"- Approval inputs not ready: `{summary['approval_input_not_ready_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Coverage Matrix",
        "",
        "| dp_id | risk | route | source sample | source template | approval template | approval input |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row.get('dp_id')}` | "
            f"`{row.get('risk_class')}` | "
            f"`{row.get('source_sample_route')}` | "
            f"{'yes' if row.get('source_sample_reviewer_packet_complete') else 'no'} | "
            f"{'yes' if row.get('source_sample_review_template_contract_valid') else 'no'} | "
            f"{'yes' if row.get('approval_record_template_blank_contract_valid') else 'no'} | "
            f"{'yes' if row.get('approval_input_ready') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Approval-input ready means the packet has traceable source samples and valid blank templates; it is not an approval.",
            "- Runtime writes remain blocked until a reviewer fills approval records with matching payload hashes and risk acknowledgement.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval-path", type=Path, default=DEFAULT_APPROVAL_PATH)
    parser.add_argument("--risk-path", type=Path, default=DEFAULT_RISK_PATH)
    parser.add_argument("--bulk-source-path", type=Path, default=DEFAULT_BULK_SOURCE_PATH)
    parser.add_argument("--event-source-path", type=Path, default=DEFAULT_EVENT_SOURCE_PATH)
    parser.add_argument(
        "--individual-source-path", type=Path, default=DEFAULT_INDIVIDUAL_SOURCE_PATH
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        approval_path=args.approval_path,
        risk_path=args.risk_path,
        bulk_source_path=args.bulk_source_path,
        event_source_path=args.event_source_path,
        individual_source_path=args.individual_source_path,
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
