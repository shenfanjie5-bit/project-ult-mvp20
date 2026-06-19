#!/usr/bin/env python3
"""Gate external business-metric value candidates before Known draft creation.

This report is deliberately read-only. It reviews the current external/text
business-metric Unknown rows and decides whether any value candidate is strong
enough to be selected automatically. The gate is intentionally conservative:
review-required candidates may be shortlisted, but they do not become Known
drafts or runtime writes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ACQUISITION_PATH = (
    ROOT
    / "docs/audit/a_share_unknown_external_business_metric_acquisition_2026-06-19.json"
)
DEFAULT_VALUE_REVIEW_PATH = (
    ROOT
    / "docs/audit/a_share_unknown_external_business_metric_value_review_packets_2026-06-19.json"
)
DEFAULT_VALUE_POLICY_DRAFT_PATH = (
    ROOT
    / "docs/audit/a_share_unknown_penetration_value_policy_draft_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_business_metric_value_selection_gate_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_business_metric_value_selection_gate_2026-06-19.md"
)

AUTO_SELECTION_CONFIDENCE_MIN = 0.75


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


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in payload.get("rows") or [] if isinstance(row, Mapping)]


def _option_confidence(option: Mapping[str, Any]) -> float:
    payload = option.get("formula_probe_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    try:
        return float(payload.get("confidence") or 0)
    except (TypeError, ValueError):
        return 0.0


def _option_review_required(option: Mapping[str, Any]) -> bool:
    payload = option.get("formula_probe_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    value_json = payload.get("value_json")
    value_json = value_json if isinstance(value_json, Mapping) else {}
    return bool(value_json.get("review_required")) or payload.get("review_status") == "review_required"


def _candidate_options(value_packets: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for packet in value_packets:
        for option in packet.get("candidate_value_options") or []:
            if isinstance(option, Mapping):
                options.append(dict(option))
    return options


def _value_policy_draft_ready(draft: Mapping[str, Any] | None) -> bool:
    if not draft:
        return False
    proposed_value_json = draft.get("proposed_value_json")
    bridge_validation = draft.get("bridge_validation")
    bridge_validation = (
        bridge_validation if isinstance(bridge_validation, Mapping) else {}
    )
    return (
        bool(draft.get("draft_contract_valid"))
        and bool(draft.get("source_scope_confirmed"))
        and isinstance(proposed_value_json, Mapping)
        and bool(bridge_validation.get("final_score_target_ready"))
        and not bool(draft.get("known_draft_sufficient"))
        and not bool(draft.get("runtime_write_allowed"))
        and not bool(draft.get("production_write_allowed"))
    )


def _missing_formula_inputs(acquisition_row: Mapping[str, Any]) -> list[str]:
    source_review = acquisition_row.get("source_review")
    source_review = source_review if isinstance(source_review, Mapping) else {}
    missing = source_review.get("missing_formula_inputs") or []
    if missing:
        return [str(item) for item in missing]
    single_dependency = acquisition_row.get("single_dependency_option")
    single_dependency = single_dependency if isinstance(single_dependency, Mapping) else {}
    required = single_dependency.get("required_evidence") or []
    return [str(item) for item in required]


def _selection_row(
    acquisition_row: Mapping[str, Any],
    value_packets: list[Mapping[str, Any]],
    value_policy_draft_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    dp_id = str(acquisition_row.get("dp_id") or "")
    value_policy_draft_row = (
        value_policy_draft_row if isinstance(value_policy_draft_row, Mapping) else {}
    )
    value_policy_draft_ready = _value_policy_draft_ready(value_policy_draft_row)
    options = _candidate_options(value_packets)
    bridge_ready_options = [
        option
        for option in options
        if isinstance(option.get("bridge_validation"), Mapping)
        and option["bridge_validation"].get("final_score_target_ready")
    ]
    review_required_options = [
        option for option in options if _option_review_required(option)
    ]
    low_confidence_options = [
        option
        for option in options
        if _option_confidence(option) < AUTO_SELECTION_CONFIDENCE_MIN
    ]
    missing_before_known = sorted(
        {
            str(item)
            for packet in value_packets
            for item in (packet.get("missing_before_known") or [])
        }
    )
    if not missing_before_known:
        missing_before_known = _missing_formula_inputs(acquisition_row)
    if value_policy_draft_ready:
        draft_missing = value_policy_draft_row.get("missing_before_known") or []
        if draft_missing:
            missing_before_known = sorted({str(item) for item in draft_missing})

    if not value_packets:
        status = "source_metric_missing"
    elif value_policy_draft_ready:
        status = "review_value_policy_draft_ready"
    elif options and len(low_confidence_options) == 0 and len(review_required_options) == 0:
        status = "auto_selectable"
    else:
        status = "review_value_selection_required"

    auto_selectable = status == "auto_selectable"
    return {
        "dp_id": dp_id,
        "score_target": acquisition_row.get("score_target"),
        "metric_candidate_status": acquisition_row.get("metric_candidate_status"),
        "selection_gate_status": status,
        "value_review_packet_count": len(value_packets),
        "candidate_value_option_count": len(options),
        "bridge_probe_ready_option_count": len(bridge_ready_options),
        "review_required_option_count": len(review_required_options),
        "low_confidence_option_count": len(low_confidence_options),
        "value_policy_draft_present": bool(value_policy_draft_row),
        "value_policy_draft_ready": value_policy_draft_ready,
        "proposed_raw_value": (
            value_policy_draft_row.get("proposed_raw_value")
            if value_policy_draft_ready
            else None
        ),
        "proposed_value_json": (
            value_policy_draft_row.get("proposed_value_json")
            if value_policy_draft_ready
            else None
        ),
        "auto_selectable": auto_selectable,
        "selected_raw_value": None,
        "selected_value_json": None,
        "known_draft_sufficient": False,
        "approval_ready": False,
        "missing_before_known": missing_before_known,
        "value_policy_draft_missing_before_known": (
            [str(item) for item in value_policy_draft_row.get("missing_before_known") or []]
            if value_policy_draft_ready
            else []
        ),
        "source_scope_verdict_counts": dict(
            sorted(
                Counter(
                    str(packet.get("source_scope_verdict") or "")
                    for packet in value_packets
                ).items()
            )
        ),
        "required_next_evidence": _missing_formula_inputs(acquisition_row),
        "safe_to_upsert_without_review": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "selection_contract_valid": True,
        "selection_validation_errors": [],
}


def build_report(
    *,
    acquisition_path: Path,
    value_review_path: Path,
    value_policy_draft_path: Path | None = None,
) -> dict[str, Any]:
    started = time.time()
    acquisition = _load_json(acquisition_path)
    value_review = _load_json(value_review_path)
    value_policy_draft = (
        _load_json(value_policy_draft_path)
        if value_policy_draft_path is not None
        else {}
    )
    packets_by_dp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for packet in _rows(value_review):
        dp_id = str(packet.get("dp_id") or "")
        if dp_id:
            packets_by_dp[dp_id].append(packet)
    draft_by_dp: dict[str, dict[str, Any]] = {}
    for draft in _rows(value_policy_draft):
        dp_id = str(draft.get("dp_id") or "")
        if dp_id and (dp_id not in draft_by_dp or _value_policy_draft_ready(draft)):
            draft_by_dp[dp_id] = draft

    rows = [
        _selection_row(
            row,
            packets_by_dp.get(str(row.get("dp_id") or ""), []),
            draft_by_dp.get(str(row.get("dp_id") or "")),
        )
        for row in _rows(acquisition)
    ]
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    status_counts = Counter(str(row.get("selection_gate_status") or "") for row in rows)
    source_scope_counts: Counter[str] = Counter()
    for row in rows:
        source_scope_counts.update(row.get("source_scope_verdict_counts") or {})

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "acquisition_path": _portable_path(acquisition_path),
            "value_review_path": _portable_path(value_review_path),
            "value_policy_draft_path": (
                _portable_path(value_policy_draft_path)
                if value_policy_draft_path is not None
                else None
            ),
        },
        "summary": {
            "business_metric_selection_row_count": len(rows),
            "value_review_packet_count": sum(
                int(row.get("value_review_packet_count") or 0) for row in rows
            ),
            "candidate_value_option_count": sum(
                int(row.get("candidate_value_option_count") or 0) for row in rows
            ),
            "bridge_probe_ready_option_count": sum(
                int(row.get("bridge_probe_ready_option_count") or 0) for row in rows
            ),
            "review_value_selection_required_count": status_counts.get(
                "review_value_selection_required", 0
            ),
            "review_value_policy_draft_ready_count": status_counts.get(
                "review_value_policy_draft_ready", 0
            ),
            "source_metric_missing_count": status_counts.get("source_metric_missing", 0),
            "auto_selectable_count": status_counts.get("auto_selectable", 0),
            "value_policy_draft_present_count": sum(
                1 for row in rows if row.get("value_policy_draft_present")
            ),
            "value_policy_draft_ready_count": sum(
                1 for row in rows if row.get("value_policy_draft_ready")
            ),
            "proposed_value_json_count": sum(
                1 for row in rows if row.get("proposed_value_json")
            ),
            "selected_value_json_count": sum(
                1 for row in rows if row.get("selected_value_json")
            ),
            "known_draft_sufficient_count": sum(
                1 for row in rows if row.get("known_draft_sufficient")
            ),
            "approval_ready_count": sum(1 for row in rows if row.get("approval_ready")),
            "selection_contract_valid_count": sum(
                1 for row in rows if row.get("selection_contract_valid")
            ),
            "selection_contract_invalid_count": sum(
                1 for row in rows if not row.get("selection_contract_valid")
            ),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "selection_gate_status_counts": dict(sorted(status_counts.items())),
            "source_scope_verdict_counts": dict(sorted(source_scope_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share external business-metric value-selection gate",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Business-metric rows: `{summary['business_metric_selection_row_count']}`",
        f"- Value-review packets: `{summary['value_review_packet_count']}`",
        f"- Candidate value options: `{summary['candidate_value_option_count']}`",
        f"- Bridge-probe-ready options: `{summary['bridge_probe_ready_option_count']}`",
        f"- Review value-selection required: `{summary['review_value_selection_required_count']}`",
        f"- Review value-policy draft ready: `{summary['review_value_policy_draft_ready_count']}`",
        f"- Value-policy draft ready: `{summary['value_policy_draft_ready_count']}`",
        f"- Source metric missing: `{summary['source_metric_missing_count']}`",
        f"- Auto-selectable values: `{summary['auto_selectable_count']}`",
        f"- Proposed value JSONs: `{summary['proposed_value_json_count']}`",
        f"- Selected value JSONs: `{summary['selected_value_json_count']}`",
        f"- Known-draft sufficient: `{summary['known_draft_sufficient_count']}`",
        f"- Approval-ready rows: `{summary['approval_ready_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | status | packets | options | bridge-ready options | value-policy draft ready | missing before Known |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            "| {dp_id} | {status} | {packets} | {options} | {bridge} | {draft_ready} | {missing} |".format(
                dp_id=row["dp_id"],
                status=row["selection_gate_status"],
                packets=row["value_review_packet_count"],
                options=row["candidate_value_option_count"],
                bridge=row["bridge_probe_ready_option_count"],
                draft_ready=int(bool(row.get("value_policy_draft_ready"))),
                missing=", ".join(row.get("missing_before_known") or []) or "-",
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Value candidates that still carry `review_required=true`, low confidence, missing reviewed bounds, or missing formula policy cannot become Known drafts automatically.",
            "- Value-policy-draft-ready rows have a reviewer-facing proposed value JSON and a bridge-ready payload, but they still require explicit review before Known draft creation.",
            "- Bridge-probe-ready means the candidate value shape can reach a final-score target if later reviewed; it does not prove the value is valid information.",
            "- This audit creates no approval records and allows no production writes.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-path", type=Path, default=DEFAULT_ACQUISITION_PATH)
    parser.add_argument("--value-review-path", type=Path, default=DEFAULT_VALUE_REVIEW_PATH)
    parser.add_argument(
        "--value-policy-draft-path",
        type=Path,
        default=DEFAULT_VALUE_POLICY_DRAFT_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    args = parser.parse_args()

    report = build_report(
        acquisition_path=args.acquisition_path,
        value_review_path=args.value_review_path,
        value_policy_draft_path=args.value_policy_draft_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
