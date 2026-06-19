#!/usr/bin/env python3
"""Build one canonical review manifest for A-share candidate drafts.

This audit merges the deterministic staging payloads and the later local/event
policy draft reports into a single review-only manifest. It is deliberately
read-only: entries can be ready for human review, but none are approved for
runtime writes without a separate approval step.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from mvp20.aggregator import _realtime_signal, synthesize_realtime_nodes
from mvp20.field_governance import load_default_governance


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STAGING_PATH = ROOT / "docs/audit/a_share_candidate_staging_payloads_2026-06-19.json"
DEFAULT_VALUE_CONTRACTS_PATH = ROOT / "docs/audit/a_share_candidate_value_contracts_2026-06-19.json"
DEFAULT_EVENT_TEXT_PATH = ROOT / "docs/audit/a_share_event_text_policy_drafts_2026-06-19.json"
DEFAULT_LOCAL_STRUCTURED_PATH = ROOT / "docs/audit/a_share_local_structured_policy_drafts_2026-06-19.json"
DEFAULT_LOCAL_STRUCTURED_TEXT_PATH = ROOT / "docs/audit/a_share_local_structured_text_policy_drafts_2026-06-19.json"
DEFAULT_SINGLE_DEPENDENCY_PATH = ROOT / "docs/audit/a_share_local_single_dependency_policy_drafts_2026-06-19.json"
DEFAULT_MANUAL_POLICY_PATH = ROOT / "docs/audit/a_share_manual_policy_draft_candidates_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_review_staging_manifest_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_review_staging_manifest_2026-06-19.md"

FINAL_SCORE_EXCLUDED_TARGETS = {
    "none",
    "audit_only",
    "display_only",
    "parent_score",
    "node_score",
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


def _rows_by_dp(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = row
    return rows


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _bridge_validation(dp_id: str, score_target: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    value_json = payload.get("value_json")
    signal = _realtime_signal(dp_id, value_json, score_target, ts_code="000001.SZ")
    registry = load_default_governance(strict=False)
    entry = {
        "value": value_json,
        "data_status": payload.get("bridge_entry_data_status", payload.get("data_status")),
        "confidence": payload.get("confidence", 0.5),
        "source": "candidate:review_staging_manifest",
        "updated_at": 1_800_000_000,
    }
    nodes = (
        synthesize_realtime_nodes(
            {dp_id: entry},
            registry,
            existing_dp_ids=set(),
            ts_code="000001.SZ",
        )
        if registry is not None
        else []
    )
    node = nodes[0] if nodes else None
    return {
        "bridge_signal": signal,
        "bridge_signal_ready": signal is not None,
        "node_emitted": node is not None,
        "node_score": (node.get("value") or {}).get("score") if node else None,
        "node_synthetic_realtime": bool(node and node.get("synthetic_realtime")),
        "final_score_target_ready": bool(
            node is not None and score_target not in FINAL_SCORE_EXCLUDED_TARGETS
        ),
    }


def _validate_entry(
    *,
    dp_id: str,
    score_target: str,
    payload: Mapping[str, Any] | None,
    source_contract_valid: bool | None,
    source_bridge: Mapping[str, Any],
    production_write_allowed: bool,
) -> dict[str, Any]:
    errors: list[str] = []
    if payload is None:
        return {"contract_valid": False, "validation_errors": ["missing review payload"]}
    if payload.get("target_dp_id") != dp_id:
        errors.append("target_dp_id does not match dp_id")
    if payload.get("score_target") != score_target:
        errors.append("score_target does not match score_target")
    data_status = payload.get("data_status")
    if data_status not in {"Known", "Unknown", "NotApplicable"}:
        errors.append("data_status must be Known, Unknown, or NotApplicable")
    bridge_entry_data_status = payload.get("bridge_entry_data_status", data_status)
    if bridge_entry_data_status not in {"Known", "Unknown", "NotApplicable"}:
        errors.append("bridge_entry_data_status must be Known, Unknown, or NotApplicable")
    confidence = _safe_float(payload.get("confidence"))
    if confidence is None or not 0.0 <= confidence <= 1.0:
        errors.append("confidence must be finite and in [0, 1]")
    evidence_refs = payload.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs or not all(
        _nonempty_string(ref) for ref in evidence_refs
    ):
        errors.append("evidence_refs must be a non-empty list of strings")
    if not _nonempty_string(payload.get("rationale")):
        errors.append("rationale must be non-empty")
    if payload.get("review_status") != "review_required":
        errors.append("review_status must be review_required")
    if payload.get("safe_to_upsert_without_review") is not False:
        errors.append("safe_to_upsert_without_review must be false")
    if production_write_allowed is not False:
        errors.append("production_write_allowed must be false")
    if source_contract_valid is False:
        errors.append("source contract is invalid")
    value_json = payload.get("value_json")
    if not isinstance(value_json, Mapping):
        errors.append("value_json must be an object")
        value_json = {}
    if data_status == "Unknown":
        if value_json.get("review_required") is not True:
            errors.append("Unknown value_json.review_required must be true")
        if not (
            _nonempty_string(value_json.get("blocked_reason"))
            or _nonempty_string(value_json.get("required_policy"))
            or isinstance(value_json.get("required_assumptions"), list)
        ):
            errors.append("Unknown payload must explain the blocked policy or assumptions")
    else:
        bridge_ready = bool(source_bridge.get("final_score_target_ready"))
        if not bridge_ready:
            recomputed_bridge = _bridge_validation(dp_id, score_target, payload)
            bridge_ready = bool(recomputed_bridge.get("final_score_target_ready"))
        if not bridge_ready:
            errors.append("concrete payload does not bridge to a final score target")
        if value_json.get("review_required") is True:
            errors.append("concrete payload must not be a review_required placeholder")
    return {"contract_valid": not errors, "validation_errors": errors}


def _staging_entry(
    row: Mapping[str, Any],
    value_contract_rows: Mapping[str, Mapping[str, Any]],
    source_report: str,
) -> dict[str, Any] | None:
    payload_status = str(row.get("payload_status") or "")
    if not payload_status.startswith("deterministic_"):
        return None
    dp_id = str(row.get("dp_id") or "")
    value_contract = value_contract_rows.get(dp_id, {})
    return {
        "dp_id": dp_id,
        "score_target": str(row.get("score_target") or ""),
        "source_kind": "deterministic_candidate_staging",
        "source_report": source_report,
        "source_status": payload_status,
        "source_dependencies": row.get("source_dependencies") or [],
        "review_payload": row.get("staging_payload"),
        "source_contract_valid": value_contract.get("contract_valid"),
        "bridge_validation": row.get("staging_bridge_validation") or value_contract.get("bridge_validation") or {},
        "production_write_allowed": bool(row.get("production_write_allowed")),
    }


def _draft_entry(row: Mapping[str, Any], source_kind: str, source_report: str) -> dict[str, Any]:
    payload = row.get("draft_payload")
    payload = payload if isinstance(payload, Mapping) else {}
    return {
        "dp_id": str(row.get("dp_id") or ""),
        "score_target": str(row.get("score_target") or payload.get("score_target") or ""),
        "source_kind": source_kind,
        "source_report": source_report,
        "source_status": str(row.get("draft_status") or payload.get("draft_status") or ""),
        "source_dependencies": row.get("source_dependencies") or [],
        "review_payload": payload,
        "source_contract_valid": (row.get("contract_validation") or {}).get("contract_valid"),
        "bridge_validation": row.get("bridge_validation") or {},
        "production_write_allowed": bool(row.get("production_write_allowed")),
    }


def _candidate_ids(staging: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    for row in staging.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            ids.append(dp_id)
    return ids


def build_report(
    *,
    staging_path: Path,
    value_contracts_path: Path,
    event_text_path: Path,
    local_structured_path: Path,
    local_structured_text_path: Path,
    single_dependency_path: Path,
    manual_policy_path: Path,
) -> dict[str, Any]:
    started = time.time()
    staging = _load_json(staging_path)
    value_contracts = _load_json(value_contracts_path)
    value_contract_rows = _rows_by_dp(value_contracts)
    event_text = _load_json(event_text_path)
    local_structured = _load_json(local_structured_path)
    local_structured_text = _load_json(local_structured_text_path)
    single_dependency = _load_json(single_dependency_path)
    manual_policy = _load_json(manual_policy_path)

    selected: dict[str, dict[str, Any]] = {}
    for row in staging.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        entry = _staging_entry(row, value_contract_rows, _portable_path(staging_path))
        if entry is not None:
            selected[entry["dp_id"]] = entry

    for source_kind, source_report, report in (
        ("event_text_policy_pilot", event_text_path, event_text),
        ("local_structured_policy_pilot", local_structured_path, local_structured),
        ("local_structured_text_policy_pilot", local_structured_text_path, local_structured_text),
        ("local_single_dependency_policy_pilot", single_dependency_path, single_dependency),
        ("manual_policy_pilot", manual_policy_path, manual_policy),
    ):
        for row in report.get("rows") or []:
            if not isinstance(row, Mapping):
                continue
            entry = _draft_entry(row, source_kind, _portable_path(source_report))
            if entry["dp_id"]:
                selected[entry["dp_id"]] = entry

    candidate_ids = _candidate_ids(staging)
    missing_ids = [dp_id for dp_id in candidate_ids if dp_id not in selected]
    rows: list[dict[str, Any]] = []
    for dp_id in candidate_ids:
        entry = selected.get(dp_id)
        if entry is None:
            rows.append(
                {
                    "dp_id": dp_id,
                    "review_entry_status": "missing_review_entry",
                    "contract_validation": {
                        "contract_valid": False,
                        "validation_errors": ["missing canonical review entry"],
                    },
                    "production_write_allowed": False,
                }
            )
            continue
        payload = entry.get("review_payload")
        validation = _validate_entry(
            dp_id=entry["dp_id"],
            score_target=entry["score_target"],
            payload=payload if isinstance(payload, Mapping) else None,
            source_contract_valid=entry.get("source_contract_valid"),
            source_bridge=entry.get("bridge_validation") or {},
            production_write_allowed=bool(entry.get("production_write_allowed")),
        )
        data_status = payload.get("data_status") if isinstance(payload, Mapping) else None
        bridge_ready = bool((entry.get("bridge_validation") or {}).get("final_score_target_ready"))
        if data_status in {"Known", "NotApplicable"} and validation["contract_valid"]:
            review_entry_status = "review_ready_concrete"
        elif data_status == "Unknown" and validation["contract_valid"]:
            review_entry_status = "review_gated_unknown"
        else:
            review_entry_status = "invalid_or_blocked"
        rows.append(
            {
                **entry,
                "data_status": data_status,
                "review_entry_status": review_entry_status,
                "contract_validation": validation,
                "bridge_ready_concrete": bool(
                    data_status in {"Known", "NotApplicable"} and bridge_ready
                ),
                "safe_to_upsert_without_review": bool(
                    isinstance(payload, Mapping)
                    and payload.get("safe_to_upsert_without_review")
                ),
                "production_write_allowed": bool(entry.get("production_write_allowed")),
            }
        )

    status_counts = Counter(str(row.get("review_entry_status") or "") for row in rows)
    data_status_counts = Counter(str(row.get("data_status") or "missing") for row in rows)
    source_kind_counts = Counter(str(row.get("source_kind") or "missing") for row in rows)
    invalid_rows = [row for row in rows if not row["contract_validation"]["contract_valid"]]
    concrete_rows = [row for row in rows if row.get("data_status") in {"Known", "NotApplicable"}]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "staging_path": _portable_path(staging_path),
            "value_contracts_path": _portable_path(value_contracts_path),
            "event_text_path": _portable_path(event_text_path),
            "local_structured_path": _portable_path(local_structured_path),
            "local_structured_text_path": _portable_path(local_structured_text_path),
            "single_dependency_path": _portable_path(single_dependency_path),
            "manual_policy_path": _portable_path(manual_policy_path),
        },
        "summary": {
            "candidate_blocking_rows": len(candidate_ids),
            "review_manifest_entries": len(rows),
            "candidate_rows_with_review_entry": len(rows) - len(missing_ids),
            "missing_review_entry_count": len(missing_ids),
            "missing_review_entry_dp_ids": missing_ids,
            "review_ready_concrete_count": sum(
                1 for row in rows if row.get("review_entry_status") == "review_ready_concrete"
            ),
            "review_gated_unknown_count": sum(
                1 for row in rows if row.get("review_entry_status") == "review_gated_unknown"
            ),
            "known_payload_count": sum(1 for row in rows if row.get("data_status") == "Known"),
            "not_applicable_payload_count": sum(
                1 for row in rows if row.get("data_status") == "NotApplicable"
            ),
            "unknown_payload_count": sum(1 for row in rows if row.get("data_status") == "Unknown"),
            "contract_valid_count": sum(1 for row in rows if row["contract_validation"]["contract_valid"]),
            "contract_invalid_count": len(invalid_rows),
            "contract_invalid_dp_ids": [row["dp_id"] for row in invalid_rows],
            "bridge_ready_concrete_count": sum(1 for row in rows if row.get("bridge_ready_concrete")),
            "review_entry_status_counts": dict(sorted(status_counts.items())),
            "data_status_counts": dict(sorted(data_status_counts.items())),
            "source_kind_counts": dict(sorted(source_kind_counts.items())),
            "safe_to_upsert_without_review_count": sum(
                1 for row in rows if row.get("safe_to_upsert_without_review")
            ),
            "production_write_allowed_count": sum(
                1 for row in rows if row.get("production_write_allowed")
            ),
            "approved_runtime_write_count": 0,
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share review staging manifest",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Candidate blocking rows: `{summary['candidate_blocking_rows']}`",
        f"- Review manifest entries: `{summary['review_manifest_entries']}`",
        f"- Review-ready concrete entries: `{summary['review_ready_concrete_count']}`",
        f"- Review-gated Unknown entries: `{summary['review_gated_unknown_count']}`",
        f"- Contracts valid: `{summary['contract_valid_count']}`",
        f"- Contracts invalid: `{summary['contract_invalid_count']}`",
        f"- Concrete entries bridge-ready: `{summary['bridge_ready_concrete_count']}`",
        f"- Safe to upsert without review: `{summary['safe_to_upsert_without_review_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Approved runtime writes: `{summary['approved_runtime_write_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Source Kind Counts",
        "",
        "| Source kind | Count |",
        "|---|---:|",
    ]
    for source, count in summary["source_kind_counts"].items():
        lines.append(f"| `{source}` | {count} |")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | target | source | data status | review status | contract | bridge-ready | write allowed |",
            "|---|---|---|---|---|---:|---:|---:|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row.get('score_target', '-')}` | "
            f"`{row.get('source_kind', '-')}` | "
            f"`{row.get('data_status', '-')}` | "
            f"`{row.get('review_entry_status', '-')}` | "
            f"{'yes' if row['contract_validation'].get('contract_valid') else 'no'} | "
            f"{'yes' if row.get('bridge_ready_concrete') else '-'} | "
            f"{'yes' if row.get('production_write_allowed') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The manifest is a review queue, not an approval list.",
            "- Concrete entries are bridge-ready but still require human approval before any runtime write.",
            "- Unknown entries document the exact policy/classification blocker that prevents a Known score value.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-path", type=Path, default=DEFAULT_STAGING_PATH)
    parser.add_argument("--value-contracts-path", type=Path, default=DEFAULT_VALUE_CONTRACTS_PATH)
    parser.add_argument("--event-text-path", type=Path, default=DEFAULT_EVENT_TEXT_PATH)
    parser.add_argument("--local-structured-path", type=Path, default=DEFAULT_LOCAL_STRUCTURED_PATH)
    parser.add_argument("--local-structured-text-path", type=Path, default=DEFAULT_LOCAL_STRUCTURED_TEXT_PATH)
    parser.add_argument("--single-dependency-path", type=Path, default=DEFAULT_SINGLE_DEPENDENCY_PATH)
    parser.add_argument("--manual-policy-path", type=Path, default=DEFAULT_MANUAL_POLICY_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        staging_path=args.staging_path,
        value_contracts_path=args.value_contracts_path,
        event_text_path=args.event_text_path,
        local_structured_path=args.local_structured_path,
        local_structured_text_path=args.local_structured_text_path,
        single_dependency_path=args.single_dependency_path,
        manual_policy_path=args.manual_policy_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
