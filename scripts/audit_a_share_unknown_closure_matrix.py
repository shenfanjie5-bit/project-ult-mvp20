#!/usr/bin/env python3
"""Build a closure matrix for remaining A-share Unknown score gaps.

This report is deliberately read-only. It joins the review manifest, next-action
queue, and source-review packets so the remaining Unknown rows have one
authoritative blocker class and next step.
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


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_PATH = ROOT / "docs/audit/a_share_review_staging_manifest_2026-06-19.json"
DEFAULT_NEXT_ACTIONS_PATH = ROOT / "docs/audit/a_share_completion_next_actions_2026-06-19.json"
DEFAULT_EVENT_REVIEW_PATH = (
    ROOT / "docs/audit/a_share_event_text_market_doc_review_packets_2026-06-19.json"
)
DEFAULT_LOCAL_STRUCTURED_REVIEW_PATH = (
    ROOT / "docs/audit/a_share_local_structured_source_review_packets_2026-06-19.json"
)
DEFAULT_SINGLE_DEPENDENCY_OPTIONS_PATH = (
    ROOT / "docs/audit/a_share_local_single_dependency_unknown_source_options_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_unknown_closure_matrix_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_unknown_closure_matrix_2026-06-19.md"


BLOCKER_BY_DP: dict[str, dict[str, Any]] = {
    "L0.compete.new_entrant": {
        "closure_blocker_class": "direct_event_transmission_evidence_required",
        "closure_track": "market_document_event_evidence",
        "minimum_unlock_evidence": [
            "same-sentence or same-paragraph new-entrant event",
            "direct A-share, listed-company, sector, supply-chain, trade, or policy transmission link",
            "reviewed direction, magnitude, and bounded value_json",
        ],
    },
    "L0.tech.substitute_tech": {
        "closure_blocker_class": "clean_substitution_risk_evidence_required",
        "closure_track": "market_document_event_evidence",
        "minimum_unlock_evidence": [
            "at least two clean same-sentence examples where a substitute technology threatens A-share companies, industries, boards, or supply chains",
            "explicit exclusion of domestic import-substitution opportunity, foreign macro substitution, trade-law replacement, and broad non-A-share market commentary",
            "reviewed direction, magnitude, and bounded value_json",
        ],
    },
    "L0.cost.rent": {
        "closure_blocker_class": "formula_policy_required",
        "closure_track": "local_structured_formula_review",
        "minimum_unlock_evidence": [
            "reviewed decision on whether use_right_asset_dep is an acceptable lease-burden proxy",
            "reviewed denominator and conservative cap/floor",
            "bounded value_json formula that bridges into the final score path",
        ],
    },
    "L0.demand.frequency": {
        "closure_blocker_class": "external_business_source_required",
        "closure_track": "external_or_text_business_metric",
        "minimum_unlock_evidence": [
            "order, transaction, shipment, usage, or customer cadence source",
            "reviewed decomposition that separates cadence from ASP and revenue growth",
            "bounded value_json formula that bridges into the final score path",
        ],
    },
    "L0.demand.penetration": {
        "closure_blocker_class": "external_business_source_required",
        "closure_track": "external_or_text_business_metric",
        "minimum_unlock_evidence": [
            "market-share, TAM, user-base, installed-base, or governed industry denominator source",
            "company numerator mapped to the same market denominator",
            "bounded value_json formula that bridges into the final score path",
        ],
    },
    "L0.price.product_asp": {
        "closure_blocker_class": "quantity_or_price_index_source_required",
        "closure_track": "local_structured_formula_review",
        "minimum_unlock_evidence": [
            "unit volume, shipment volume, product quantity, or governed price index",
            "mapping from business-segment row to ASP-bearing product",
            "bounded value_json formula that bridges into the final score path",
        ],
    },
    "L0.demand.replacement": {
        "closure_blocker_class": "lifecycle_source_and_policy_required",
        "closure_track": "external_or_text_business_metric",
        "minimum_unlock_evidence": [
            "product lifecycle, installed-base, active device/customer stock, or renewal-cycle source",
            "reviewed policy separating replacement cycle demand from revenue scalar",
            "bounded value_json formula that bridges into the final score path",
        ],
    },
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


def _manifest_unknown_rows(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in manifest.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("data_status") == "Unknown":
            rows.append(dict(row))
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    return rows


def _event_evidence(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    candidate_examples = row.get("candidate_examples") or []
    return {
        "classification_packet_status": row.get("classification_packet_status"),
        "blocked_reason": row.get("blocked_reason"),
        "candidate_doc_counts": row.get("candidate_doc_counts") or {},
        "candidate_example_count": len(candidate_examples)
        if isinstance(candidate_examples, list)
        else 0,
        "required_evidence": row.get("required_evidence") or [],
        "packet_contract_valid": bool(row.get("packet_contract_valid")),
    }


def _local_structured_evidence(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "source_review_packet_status": row.get("source_review_packet_status"),
        "candidate_columns": row.get("candidate_columns") or [],
        "empty_candidate_columns": row.get("empty_candidate_columns") or [],
        "available_formula_inputs": row.get("available_formula_inputs") or [],
        "missing_formula_inputs": row.get("missing_formula_inputs") or [],
        "direct_known_ready": bool(row.get("direct_known_ready")),
        "formula_inputs_ready": bool(row.get("formula_inputs_ready")),
        "packet_contract_valid": bool(row.get("packet_contract_valid")),
    }


def _single_dependency_evidence(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "resolution_status": row.get("resolution_status"),
        "runtime_dependency_ready": bool(row.get("runtime_dependency_ready")),
        "direct_replacement_cycle_source_ready": bool(
            row.get("direct_replacement_cycle_source_ready")
        ),
        "lifecycle_source_required": bool(row.get("lifecycle_source_required")),
        "reviewed_policy_required": bool(row.get("reviewed_policy_required")),
        "required_evidence": row.get("required_evidence") or [],
        "overlay_candidate_dp_ids": row.get("overlay_candidate_dp_ids") or [],
    }


def _best_evidence(
    *,
    source_kind: str,
    dp_id: str,
    event_rows: Mapping[str, Mapping[str, Any]],
    local_structured_rows: Mapping[str, Mapping[str, Any]],
    single_dependency_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if source_kind == "event_text_policy_pilot":
        return _event_evidence(event_rows.get(dp_id))
    if source_kind == "local_structured_policy_pilot":
        return _local_structured_evidence(local_structured_rows.get(dp_id))
    if source_kind == "local_single_dependency_policy_pilot":
        return _single_dependency_evidence(single_dependency_rows.get(dp_id))
    return {}


def _row(
    manifest_row: Mapping[str, Any],
    next_action_row: Mapping[str, Any] | None,
    event_rows: Mapping[str, Mapping[str, Any]],
    local_structured_rows: Mapping[str, Mapping[str, Any]],
    single_dependency_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    dp_id = str(manifest_row.get("dp_id") or "")
    source_kind = str(manifest_row.get("source_kind") or "")
    policy = BLOCKER_BY_DP.get(dp_id, {})
    review_payload = manifest_row.get("review_payload")
    review_payload = review_payload if isinstance(review_payload, Mapping) else {}
    value_json = review_payload.get("value_json")
    value_json = value_json if isinstance(value_json, Mapping) else {}
    next_action_row = next_action_row or {}
    best_evidence = _best_evidence(
        source_kind=source_kind,
        dp_id=dp_id,
        event_rows=event_rows,
        local_structured_rows=local_structured_rows,
        single_dependency_rows=single_dependency_rows,
    )
    source_contract_valid = bool(manifest_row.get("source_contract_valid"))
    best_packet_valid = bool(best_evidence.get("packet_contract_valid", True))
    return {
        "dp_id": dp_id,
        "score_target": manifest_row.get("score_target"),
        "source_kind": source_kind,
        "source_report": manifest_row.get("source_report"),
        "data_status": "Unknown",
        "review_entry_status": manifest_row.get("review_entry_status"),
        "approval_gate_status": next_action_row.get("approval_gate_status"),
        "next_action_bucket": next_action_row.get("next_action_bucket"),
        "closure_track": policy.get("closure_track", "unknown_resolution"),
        "closure_blocker_class": policy.get(
            "closure_blocker_class", "unknown_resolution_required"
        ),
        "blocked_reason": value_json.get("blocked_reason")
        or next_action_row.get("blocked_reason"),
        "required_policy": value_json.get("required_policy")
        or next_action_row.get("required_policy"),
        "minimum_unlock_evidence": policy.get("minimum_unlock_evidence") or [],
        "current_best_evidence": best_evidence,
        "auto_known_ready": False,
        "approval_ready": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "source_contract_valid": source_contract_valid,
        "supporting_packet_contract_valid": best_packet_valid,
        "safe_closure_state": (
            "blocked_until_evidence_or_policy"
            if next_action_row.get("next_action_bucket") != "human_approval_required"
            else "unexpected_human_approval_bucket"
        ),
        "next_action": next_action_row.get("next_action"),
        "source_dependencies": manifest_row.get("source_dependencies") or [],
        "evidence_refs": review_payload.get("evidence_refs") or [],
    }


def _validation_errors(row: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not row.get("dp_id"):
        errors.append("dp_id is required")
    if row.get("data_status") != "Unknown":
        errors.append("closure rows must stay Unknown")
    if row.get("auto_known_ready") is not False:
        errors.append("auto_known_ready must be false")
    if row.get("approval_ready") is not False:
        errors.append("approval_ready must be false")
    if row.get("runtime_write_allowed") is not False:
        errors.append("runtime_write_allowed must be false")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    if not row.get("closure_blocker_class"):
        errors.append("closure_blocker_class is required")
    if not row.get("minimum_unlock_evidence"):
        errors.append("minimum_unlock_evidence is required")
    if not row.get("next_action"):
        errors.append("next_action is required")
    if row.get("next_action_bucket") == "human_approval_required":
        errors.append("Unknown rows must not be in the human approval bucket")
    if row.get("source_contract_valid") is not True:
        errors.append("source_contract_valid must be true")
    if row.get("supporting_packet_contract_valid") is not True:
        errors.append("supporting packet contract must be true")
    return errors


def build_report(
    *,
    manifest_path: Path,
    next_actions_path: Path,
    event_review_path: Path,
    local_structured_review_path: Path,
    single_dependency_options_path: Path,
) -> dict[str, Any]:
    started = time.time()
    manifest = _load_json(manifest_path)
    next_actions = _load_json(next_actions_path)
    event_review = _load_json(event_review_path)
    local_structured_review = _load_json(local_structured_review_path)
    single_dependency_options = _load_json(single_dependency_options_path)

    next_action_rows = _rows_by_dp(next_actions)
    event_rows = _rows_by_dp(event_review)
    local_structured_rows = _rows_by_dp(local_structured_review)
    single_dependency_rows = _rows_by_dp(single_dependency_options)

    rows = [
        _row(
            row,
            next_action_rows.get(str(row.get("dp_id") or "")),
            event_rows,
            local_structured_rows,
            single_dependency_rows,
        )
        for row in _manifest_unknown_rows(manifest)
    ]
    rows.sort(key=lambda row: (str(row["closure_track"]), str(row["dp_id"])))
    for row in rows:
        errors = _validation_errors(row)
        row["closure_contract_valid"] = not errors
        row["closure_validation_errors"] = errors

    blocker_counts = Counter(str(row["closure_blocker_class"]) for row in rows)
    track_counts = Counter(str(row["closure_track"]) for row in rows)
    next_action_counts = Counter(str(row.get("next_action_bucket") or "") for row in rows)
    closure_route_assigned_count = sum(
        1
        for row in rows
        if row.get("closure_blocker_class")
        and row.get("closure_track")
        and row.get("next_action_bucket")
    )
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "manifest_path": _portable_path(manifest_path),
            "next_actions_path": _portable_path(next_actions_path),
            "event_review_path": _portable_path(event_review_path),
            "local_structured_review_path": _portable_path(local_structured_review_path),
            "single_dependency_options_path": _portable_path(
                single_dependency_options_path
            ),
        },
        "summary": {
            "closure_matrix_row_count": len(rows),
            "unknown_closure_row_count": len(rows),
            "closure_route_assigned_count": closure_route_assigned_count,
            "missing_closure_route_count": len(rows) - closure_route_assigned_count,
            "review_ready_concrete_count": int(
                (manifest.get("summary") or {}).get("review_ready_concrete_count") or 0
            ),
            "review_gated_unknown_count": int(
                (manifest.get("summary") or {}).get("review_gated_unknown_count") or 0
            ),
            "approval_ready_packet_count": int(
                (next_actions.get("summary") or {}).get("approval_ready_packet_count") or 0
            ),
            "auto_known_ready_count": sum(1 for row in rows if row["auto_known_ready"]),
            "approval_ready_count": sum(1 for row in rows if row["approval_ready"]),
            "review_required_count": len(rows),
            "event_evidence_gap_count": sum(
                1 for row in rows if row["closure_track"] == "market_document_event_evidence"
            ),
            "local_structured_formula_review_count": sum(
                1 for row in rows if row["closure_track"] == "local_structured_formula_review"
            ),
            "external_business_source_required_count": sum(
                1 for row in rows if row["closure_track"] == "external_or_text_business_metric"
            ),
            "rows_with_source_candidates_count": sum(
                1
                for row in rows
                if (row["current_best_evidence"].get("candidate_columns") or [])
                or int(row["current_best_evidence"].get("candidate_example_count") or 0) > 0
            ),
            "formula_inputs_ready_count": sum(
                1
                for row in rows
                if row["current_best_evidence"].get("formula_inputs_ready") is True
            ),
            "event_text_classification_required_count": next_action_counts.get(
                "event_text_classification_required", 0
            ),
            "local_structured_mapping_required_count": next_action_counts.get(
                "local_structured_mapping_required", 0
            ),
            "structured_text_extraction_required_count": next_action_counts.get(
                "structured_text_extraction_required", 0
            ),
            "single_dependency_policy_required_count": next_action_counts.get(
                "single_dependency_policy_required", 0
            ),
            "manual_assumption_review_required_count": next_action_counts.get(
                "manual_assumption_review_required", 0
            ),
            "direct_known_ready_count": 0,
            "closure_contract_valid_count": sum(
                1 for row in rows if row["closure_contract_valid"]
            ),
            "closure_contract_invalid_count": sum(
                1 for row in rows if not row["closure_contract_valid"]
            ),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "closure_blocker_class_counts": dict(sorted(blocker_counts.items())),
            "closure_track_counts": dict(sorted(track_counts.items())),
            "next_action_bucket_counts": dict(sorted(next_action_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown closure matrix",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Unknown closure rows: `{summary['unknown_closure_row_count']}`",
        f"- Closure routes assigned: `{summary['closure_route_assigned_count']}`",
        f"- Missing closure routes: `{summary['missing_closure_route_count']}`",
        f"- Review-ready concrete rows: `{summary['review_ready_concrete_count']}`",
        f"- Review-gated Unknown rows: `{summary['review_gated_unknown_count']}`",
        f"- Approval-ready concrete packets: `{summary['approval_ready_packet_count']}`",
        f"- Auto Known-ready rows: `{summary['auto_known_ready_count']}`",
        f"- Approval-ready Unknown rows: `{summary['approval_ready_count']}`",
        f"- Event evidence gaps: `{summary['event_evidence_gap_count']}`",
        f"- Local structured formula reviews: `{summary['local_structured_formula_review_count']}`",
        f"- External/text business sources required: `{summary['external_business_source_required_count']}`",
        f"- Rows with source candidates: `{summary['rows_with_source_candidates_count']}`",
        f"- Formula inputs ready: `{summary['formula_inputs_ready_count']}`",
        f"- Contract valid rows: `{summary['closure_contract_valid_count']}`",
        f"- Contract invalid rows: `{summary['closure_contract_invalid_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | blocker class | current evidence | auto Known | next action bucket |",
        "|---|---|---|---:|---|",
    ]
    for row in report["rows"]:
        evidence = row.get("current_best_evidence") or {}
        if row["source_kind"] == "event_text_policy_pilot":
            evidence_text = (
                f"{evidence.get('classification_packet_status', '-')}, "
                f"examples={evidence.get('candidate_example_count', 0)}"
            )
        elif row["source_kind"] == "local_structured_policy_pilot":
            evidence_text = (
                f"{evidence.get('source_review_packet_status', '-')}, "
                f"columns={len(evidence.get('candidate_columns') or [])}, "
                f"missing_inputs={len(evidence.get('missing_formula_inputs') or [])}"
            )
        elif row["source_kind"] == "local_single_dependency_policy_pilot":
            evidence_text = (
                f"{evidence.get('resolution_status', '-')}, "
                f"runtime_dep={bool(evidence.get('runtime_dependency_ready'))}"
            )
        else:
            evidence_text = "-"
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['closure_blocker_class']}` | "
            f"{evidence_text} | "
            f"{'yes' if row['auto_known_ready'] else 'no'} | "
            f"`{row.get('next_action_bucket', '-')}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- None of the remaining Unknown rows is auto Known-ready or approval-ready.",
            "- `L0.cost.rent` and `L0.price.product_asp` have local structured source candidates, but neither has complete formula inputs.",
            "- `L0.compete.new_entrant` and `L0.tech.substitute_tech` remain event-evidence problems, not approval problems.",
            "- `L0.demand.frequency`, `L0.demand.penetration`, and `L0.demand.replacement` need external or text-derived business metrics before a value can be scored.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--next-actions-path", type=Path, default=DEFAULT_NEXT_ACTIONS_PATH)
    parser.add_argument("--event-review-path", type=Path, default=DEFAULT_EVENT_REVIEW_PATH)
    parser.add_argument(
        "--local-structured-review-path",
        type=Path,
        default=DEFAULT_LOCAL_STRUCTURED_REVIEW_PATH,
    )
    parser.add_argument(
        "--single-dependency-options-path",
        type=Path,
        default=DEFAULT_SINGLE_DEPENDENCY_OPTIONS_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        manifest_path=args.manifest_path,
        next_actions_path=args.next_actions_path,
        event_review_path=args.event_review_path,
        local_structured_review_path=args.local_structured_review_path,
        single_dependency_options_path=args.single_dependency_options_path,
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
