#!/usr/bin/env python3
"""Classify source options for local single-dependency A-share Unknown drafts.

The local single-dependency pilot keeps ``L0.demand.replacement`` Unknown
because revenue is known but does not identify replacement-cycle demand. This
read-only audit records which current evidence is ready, what source routes
could close the field, and why production writes remain disabled.
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
    DEFAULT_CANDIDATE_PATH,
    ROOT,
    _candidate_rows_by_dp,
    _load_json,
    _portable_path,
)


DEFAULT_SINGLE_DEPENDENCY_PATH = (
    ROOT / "docs/audit/a_share_local_single_dependency_policy_drafts_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_local_single_dependency_unknown_source_options_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_local_single_dependency_unknown_source_options_2026-06-19.md"
)
DEFAULT_STOCK_OVERLAY_ROOT = ROOT / "config/stock_overlays"


SOURCE_OPTION_POLICIES: dict[str, dict[str, Any]] = {
    "L0.demand.replacement": {
        "resolution_status": "requires_lifecycle_or_replacement_cycle_source",
        "lifecycle_source_required": True,
        "reviewed_policy_required": True,
        "dependency_limit": (
            "Revenue is material and current, but it cannot separate replacement-cycle "
            "demand from price, new-customer demand, mix, or one-off project timing."
        ),
        "required_evidence": [
            "product lifecycle or launch/refresh cadence",
            "installed base, fleet size, or active-device/customer stock",
            "replacement cycle months/years or renewal trend",
            "shipment, order, user, or channel evidence that separates replacement from new demand",
        ],
        "overlay_candidate_dp_ids": [
            "L0.demand.replacement",
            "L3.product.lifecycle",
            "L4.volume.frequency",
            "L4.volume.orders",
            "L4.volume.sales",
            "L4.volume.shipments",
            "L4.volume.users",
        ],
        "candidate_source_routes": [
            "map reviewed stock/industry overlays where replacement-cycle evidence already exists",
            "extract product lifecycle and installed-base disclosures from annual reports or exchange Q&A",
            "join governed industry shipment, device/fleet stock, or renewal-cycle datasets",
            "use industry graph priors only as reviewer context, not as automatic Known values",
        ],
    },
}


def _unknown_single_dependency_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
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


def _dependency_records(candidate_row: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(candidate_row, Mapping):
        return []
    candidate_input = candidate_row.get("candidate_input")
    if not isinstance(candidate_input, Mapping):
        return []
    dependency_evidence = candidate_row.get("dependency_evidence")
    if not isinstance(dependency_evidence, Mapping):
        dependency_evidence = {}

    records: list[dict[str, Any]] = []
    for dep in candidate_input.get("dependencies") or []:
        if not isinstance(dep, Mapping):
            continue
        dep_id = str(dep.get("dp_id") or "")
        rich = dependency_evidence.get(dep_id)
        if not isinstance(rich, Mapping):
            rich = {}
        sample_keys: list[str] = []
        for sample in dep.get("sample_rows") or []:
            if not isinstance(sample, Mapping):
                continue
            compact = sample.get("value_json_compact")
            if not isinstance(compact, Mapping):
                continue
            for key in compact:
                if str(key) not in sample_keys:
                    sample_keys.append(str(key))
        records.append(
            {
                "dp_id": dep_id,
                "row_count": int(dep.get("row_count") or rich.get("row_count") or 0),
                "known_count": int(dep.get("known_count") or rich.get("known_count") or 0),
                "ts_code_count": int(dep.get("ts_code_count") or rich.get("ts_code_count") or 0),
                "namespace_counts": dict(dep.get("namespace_counts") or rich.get("namespace_counts") or {}),
                "source_counts": dict(rich.get("source_counts") or {}),
                "latest_updated_at_iso": dep.get("latest_updated_at_iso")
                or rich.get("latest_updated_at_iso"),
                "sample_value_keys": sample_keys,
            }
        )
    return records


def _is_a_share_ts_code(ts_code: str) -> bool:
    return ts_code.endswith((".SZ", ".SH", ".BJ"))


def _compact_node_context(path: Path, payload: Mapping[str, Any], node: Mapping[str, Any]) -> dict[str, Any]:
    evidence_sources = node.get("evidence_sources")
    if not isinstance(evidence_sources, list):
        evidence_sources = []
    value = node.get("value")
    if not isinstance(value, Mapping):
        value = {}
    return {
        "path": _portable_path(path),
        "ts_code": payload.get("ts_code"),
        "industry_id": payload.get("industry_id"),
        "dp_id": node.get("dp_id"),
        "status": node.get("status") or node.get("data_status"),
        "confidence": node.get("confidence"),
        "last_updated": node.get("last_updated"),
        "value_keys": sorted(str(key) for key in value.keys()),
        "phase": value.get("phase"),
        "competitive_score": value.get("competitive_score"),
        "evidence_source_count": len(evidence_sources),
    }


def _clean_scalar(raw: str) -> str:
    value = raw.strip()
    if value in {"null", "None", "~"}:
        return ""
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        return value[1:-1]
    return value


def _line_value(line: str, key: str) -> str | None:
    stripped = line.strip()
    prefixes = (f"{key}:", f"- {key}:")
    for prefix in prefixes:
        if stripped.startswith(prefix):
            return _clean_scalar(stripped[len(prefix) :])
    return None


def _finalize_overlay_node(
    *,
    path: Path,
    ts_code: str,
    industry_id: str,
    node: Mapping[str, Any],
    summary: dict[str, Any],
    sample_contexts: list[dict[str, Any]],
) -> None:
    dp_id = str(node.get("dp_id") or "")
    status = str(node.get("data_status") or node.get("status") or "")
    if dp_id == "L3.product.lifecycle" and status == "Known":
        summary["lifecycle_known_node_count"] += 1
        if len(sample_contexts) < 5:
            sample_contexts.append(
                {
                    "path": _portable_path(path),
                    "ts_code": ts_code,
                    "industry_id": industry_id,
                    "dp_id": dp_id,
                    "status": status,
                    "confidence": node.get("confidence"),
                    "last_updated": node.get("last_updated"),
                    "value_keys": [
                        key
                        for key in ("phase", "competitive_score", "evidence_summary")
                        if node.get(key) not in (None, "")
                    ],
                    "phase": node.get("phase"),
                    "competitive_score": node.get("competitive_score"),
                    "evidence_source_count": int(node.get("evidence_source_count") or 0),
                }
            )
    elif dp_id == "L0.demand.replacement" and status == "Known":
        summary["replacement_known_node_count"] += 1
    elif dp_id == "L0.demand.replacement" and status == "Unknown":
        summary["replacement_unknown_node_count"] += 1


def _scan_overlay_file(
    path: Path,
    *,
    summary: dict[str, Any],
    sample_contexts: list[dict[str, Any]],
) -> None:
    ts_code = ""
    industry_id = ""
    current_node: dict[str, Any] | None = None
    in_value = False
    in_evidence_sources = False
    seen_target_nodes: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not ts_code:
                    value = _line_value(line, "ts_code")
                    if value is not None:
                        ts_code = value
                        if not _is_a_share_ts_code(ts_code):
                            return
                        summary["a_share_files_checked"] += 1
                        continue
                if not industry_id:
                    value = _line_value(line, "industry_id")
                    if value is not None:
                        industry_id = value
                        continue

                stripped = line.strip()
                starts_node = stripped.startswith("- node_id:") or stripped.startswith("- dp_id:")
                if starts_node:
                    if current_node:
                        _finalize_overlay_node(
                            path=path,
                            ts_code=ts_code,
                            industry_id=industry_id,
                            node=current_node,
                            summary=summary,
                            sample_contexts=sample_contexts,
                        )
                        if current_node.get("dp_id") in {
                            "L3.product.lifecycle",
                            "L0.demand.replacement",
                        }:
                            seen_target_nodes.add(str(current_node.get("dp_id")))
                    if seen_target_nodes == {
                        "L3.product.lifecycle",
                        "L0.demand.replacement",
                    }:
                        return
                    current_node = {}
                    in_value = False
                    in_evidence_sources = False
                    dp_id = _line_value(line, "dp_id")
                    if dp_id:
                        current_node["dp_id"] = dp_id
                    continue
                if current_node is None:
                    continue

                if not in_value and not in_evidence_sources:
                    for key in (
                        "dp_id",
                        "status",
                        "data_status",
                        "confidence",
                        "last_updated",
                    ):
                        value = _line_value(line, key)
                        if value is not None:
                            current_node[key] = value
                if stripped == "value:":
                    in_value = True
                    in_evidence_sources = False
                    continue
                if stripped == "evidence_sources:":
                    in_evidence_sources = True
                    in_value = False
                    continue
                if in_value:
                    for key in ("phase", "competitive_score", "evidence_summary"):
                        value = _line_value(line, key)
                        if value is not None:
                            current_node[key] = value
                if in_evidence_sources and stripped.startswith("- kind:"):
                    current_node["evidence_source_count"] = int(
                        current_node.get("evidence_source_count") or 0
                    ) + 1
    except (OSError, UnicodeDecodeError):
        summary["read_error_count"] += 1
        return

    if current_node:
        _finalize_overlay_node(
            path=path,
            ts_code=ts_code,
            industry_id=industry_id,
            node=current_node,
            summary=summary,
            sample_contexts=sample_contexts,
        )


def _overlay_lifecycle_context_summary(overlay_root: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "overlay_root": _portable_path(overlay_root),
        "available": False,
        "direct_replacement_cycle_source_ready": False,
        "direct_formula_input": False,
        "files_checked": 0,
        "a_share_files_checked": 0,
        "read_error_count": 0,
        "lifecycle_known_node_count": 0,
        "replacement_known_node_count": 0,
        "replacement_unknown_node_count": 0,
        "sample_lifecycle_contexts": [],
        "review_required": True,
        "reason_not_direct_source": (
            "Stock overlays contain lifecycle context, but the current single-dependency "
            "gate still requires reviewed mapping to replacement-cycle demand before Known scoring."
        ),
    }
    if not overlay_root.exists():
        return {**summary, "reason": "stock_overlay_root_missing"}

    sample_contexts: list[dict[str, Any]] = []
    for path in sorted(overlay_root.glob("*/*.yaml")):
        summary["files_checked"] += 1
        _scan_overlay_file(path, summary=summary, sample_contexts=sample_contexts)

    summary["available"] = bool(summary["lifecycle_known_node_count"])
    summary["sample_lifecycle_contexts"] = sample_contexts
    return summary


def _lifecycle_policy_review_template(
    *,
    packet_id: str,
    dp_id: str,
    score_target: str,
    dependencies: list[dict[str, Any]],
    lifecycle_context: Mapping[str, Any] | None,
    policy: Mapping[str, Any],
) -> dict[str, Any] | None:
    if dp_id != "L0.demand.replacement":
        return None
    if not lifecycle_context or not lifecycle_context.get("available"):
        return None
    if policy.get("reviewed_policy_required") is not True:
        return None
    return {
        "template_status": "review_fill_required",
        "packet_id": packet_id,
        "dp_id": dp_id,
        "score_target": score_target,
        "review_scope": "replacement_lifecycle_policy",
        "source_dependency_dp_ids": [str(dep.get("dp_id") or "") for dep in dependencies],
        "overlay_context_family": "lifecycle_to_replacement_review",
        "overlay_lifecycle_known_node_count": int(
            lifecycle_context.get("lifecycle_known_node_count") or 0
        ),
        "overlay_replacement_known_node_count": int(
            lifecycle_context.get("replacement_known_node_count") or 0
        ),
        "overlay_replacement_unknown_node_count": int(
            lifecycle_context.get("replacement_unknown_node_count") or 0
        ),
        "required_evidence": list(policy.get("required_evidence") or []),
        "candidate_source_routes": list(policy.get("candidate_source_routes") or []),
        "reviewer": "",
        "reviewed_at": "",
        "review_decision": "",
        "lifecycle_source_accepted": False,
        "installed_base_or_renewal_source_accepted": False,
        "replacement_cycle_mapping_accepted": False,
        "new_vs_replacement_split_accepted": False,
        "score_direction_accepted": False,
        "bounds_or_normalization_accepted": False,
        "known_draft_allowed": False,
        "auto_known_allowed": False,
        "safe_to_upsert_without_review": False,
        "production_write_allowed": False,
    }


def _lifecycle_policy_review_template_errors(
    template: Mapping[str, Any] | None,
    *,
    packet_id: str,
    dp_id: str,
    score_target: str,
    dependencies: list[dict[str, Any]],
    lifecycle_context: Mapping[str, Any] | None,
    policy: Mapping[str, Any],
) -> list[str]:
    if dp_id != "L0.demand.replacement":
        return []
    if not lifecycle_context or not lifecycle_context.get("available"):
        return []
    if policy.get("reviewed_policy_required") is not True:
        return []
    if template is None:
        return ["lifecycle_policy_review_template missing"]

    errors: list[str] = []
    expected = {
        "template_status": "review_fill_required",
        "packet_id": packet_id,
        "dp_id": dp_id,
        "score_target": score_target,
        "review_scope": "replacement_lifecycle_policy",
        "source_dependency_dp_ids": [
            str(dep.get("dp_id") or "") for dep in dependencies
        ],
        "overlay_context_family": "lifecycle_to_replacement_review",
        "overlay_lifecycle_known_node_count": int(
            lifecycle_context.get("lifecycle_known_node_count") or 0
        ),
        "overlay_replacement_known_node_count": int(
            lifecycle_context.get("replacement_known_node_count") or 0
        ),
        "overlay_replacement_unknown_node_count": int(
            lifecycle_context.get("replacement_unknown_node_count") or 0
        ),
        "required_evidence": list(policy.get("required_evidence") or []),
        "candidate_source_routes": list(policy.get("candidate_source_routes") or []),
        "reviewer": "",
        "reviewed_at": "",
        "review_decision": "",
    }
    for key, expected_value in expected.items():
        if template.get(key) != expected_value:
            errors.append(f"{key} must be {expected_value!r}")
    for key in (
        "lifecycle_source_accepted",
        "installed_base_or_renewal_source_accepted",
        "replacement_cycle_mapping_accepted",
        "new_vs_replacement_split_accepted",
        "score_direction_accepted",
        "bounds_or_normalization_accepted",
        "known_draft_allowed",
        "auto_known_allowed",
        "safe_to_upsert_without_review",
        "production_write_allowed",
    ):
        if template.get(key) is not False:
            errors.append(f"{key} must be false in blank template")
    return errors


def build_report(
    single_dependency_path: Path,
    candidate_path: Path,
    *,
    stock_overlay_root: Path = DEFAULT_STOCK_OVERLAY_ROOT,
) -> dict[str, Any]:
    started = time.time()
    single_dependency = _load_json(single_dependency_path)
    candidates = _candidate_rows_by_dp(_load_json(candidate_path))
    lifecycle_context = _overlay_lifecycle_context_summary(stock_overlay_root)
    rows: list[dict[str, Any]] = []

    for source_row in _unknown_single_dependency_rows(single_dependency):
        dp_id = str(source_row.get("dp_id") or "")
        score_target = str(source_row.get("score_target") or "")
        policy = SOURCE_OPTION_POLICIES.get(dp_id, {})
        candidate_row = candidates.get(dp_id)
        dependencies = _dependency_records(candidate_row)
        runtime_dependency_ready = bool(dependencies) and all(
            dep["row_count"] > 0 and dep["known_count"] > 0 for dep in dependencies
        )
        value_json = _payload_value(source_row)
        overlay_lifecycle_context_candidate = (
            lifecycle_context if dp_id == "L0.demand.replacement" else None
        )
        packet_id = f"single_dependency:{dp_id}"
        lifecycle_policy_review_template = _lifecycle_policy_review_template(
            packet_id=packet_id,
            dp_id=dp_id,
            score_target=score_target,
            dependencies=dependencies,
            lifecycle_context=overlay_lifecycle_context_candidate,
            policy=policy,
        )
        lifecycle_policy_review_template_errors = (
            _lifecycle_policy_review_template_errors(
                lifecycle_policy_review_template,
                packet_id=packet_id,
                dp_id=dp_id,
                score_target=score_target,
                dependencies=dependencies,
                lifecycle_context=overlay_lifecycle_context_candidate,
                policy=policy,
            )
        )
        rows.append(
            {
                "single_dependency_source_option_packet_id": packet_id,
                "dp_id": dp_id,
                "score_target": score_target,
                "draft_status": source_row.get("draft_status"),
                "blocked_reason": value_json.get("blocked_reason"),
                "required_policy": value_json.get("required_policy"),
                "candidate_status": candidate_row.get("candidate_status") if candidate_row else None,
                "source_dependencies": candidate_row.get("source_dependencies") if candidate_row else [],
                "runtime_dependency_ready": runtime_dependency_ready,
                "runtime_dependency_summary": dependencies,
                "direct_replacement_cycle_source_ready": False,
                "direct_replacement_cycle_source_reason": (
                    "Current single dependency is revenue only; it does not contain product "
                    "lifecycle, installed-base, renewal, or replacement-cycle evidence."
                ),
                "dependency_limit": policy.get(
                    "dependency_limit",
                    "No reviewed single-dependency source-option policy is defined.",
                ),
                "required_evidence": list(policy.get("required_evidence") or []),
                "overlay_candidate_dp_ids": list(policy.get("overlay_candidate_dp_ids") or []),
                "overlay_lifecycle_context_candidate_available": bool(
                    overlay_lifecycle_context_candidate
                    and overlay_lifecycle_context_candidate.get("available")
                ),
                "overlay_lifecycle_context_candidate": overlay_lifecycle_context_candidate,
                "candidate_source_routes": list(policy.get("candidate_source_routes") or []),
                "lifecycle_policy_review_template": lifecycle_policy_review_template,
                "lifecycle_policy_review_template_contract_valid": (
                    lifecycle_policy_review_template is not None
                    and not lifecycle_policy_review_template_errors
                ),
                "lifecycle_policy_review_template_validation_errors": (
                    lifecycle_policy_review_template_errors
                ),
                "resolution_status": policy.get(
                    "resolution_status",
                    "requires_reviewed_single_dependency_source_policy",
                ),
                "lifecycle_source_required": bool(policy.get("lifecycle_source_required")),
                "reviewed_policy_required": bool(policy.get("reviewed_policy_required")),
                "auto_known_candidate_allowed": False,
                "known_draft_sufficient": False,
                "approval_ready": False,
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
        "single_dependency_path": _portable_path(single_dependency_path),
        "candidate_path": _portable_path(candidate_path),
        "summary": {
            "unknown_local_single_dependency_count": len(rows),
            "existing_runtime_dependency_ready_count": sum(
                1 for row in rows if row["runtime_dependency_ready"]
            ),
            "direct_replacement_cycle_source_ready_count": sum(
                1 for row in rows if row["direct_replacement_cycle_source_ready"]
            ),
            "overlay_candidate_hint_count": sum(
                1 for row in rows if row["overlay_candidate_dp_ids"]
            ),
            "rows_with_overlay_lifecycle_context_candidate_count": sum(
                1 for row in rows if row["overlay_lifecycle_context_candidate_available"]
            ),
            "overlay_lifecycle_known_node_count": int(
                lifecycle_context.get("lifecycle_known_node_count") or 0
            ),
            "overlay_replacement_known_node_count": int(
                lifecycle_context.get("replacement_known_node_count") or 0
            ),
            "overlay_replacement_unknown_node_count": int(
                lifecycle_context.get("replacement_unknown_node_count") or 0
            ),
            "candidate_requires_lifecycle_source_count": sum(
                1 for row in rows if row["lifecycle_source_required"]
            ),
            "candidate_requires_review_policy_count": sum(
                1 for row in rows if row["reviewed_policy_required"]
            ),
            "lifecycle_policy_review_template_count": sum(
                1 for row in rows if row["lifecycle_policy_review_template"]
            ),
            "lifecycle_policy_review_template_contract_valid_count": sum(
                1
                for row in rows
                if row["lifecycle_policy_review_template_contract_valid"]
            ),
            "lifecycle_policy_review_template_contract_invalid_count": sum(
                1
                for row in rows
                if row["lifecycle_policy_review_template"]
                and not row["lifecycle_policy_review_template_contract_valid"]
            ),
            "lifecycle_policy_review_template_blank_pending_count": sum(
                1
                for row in rows
                if (
                    isinstance(row.get("lifecycle_policy_review_template"), Mapping)
                    and row["lifecycle_policy_review_template"].get("template_status")
                    == "review_fill_required"
                    and row["lifecycle_policy_review_template"].get("reviewer") == ""
                    and row["lifecycle_policy_review_template"].get("reviewed_at") == ""
                )
            ),
            "lifecycle_policy_review_template_input_ready_count": 0,
            "auto_known_candidate_count": sum(
                1 for row in rows if row["auto_known_candidate_allowed"]
            ),
            "known_draft_sufficient_count": 0,
            "approval_ready_count": 0,
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
        "# A-share local single-dependency Unknown source options",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Unknown local single-dependency rows: `{summary['unknown_local_single_dependency_count']}`",
        f"- Runtime dependencies ready: `{summary['existing_runtime_dependency_ready_count']}`",
        f"- Direct replacement-cycle source-ready rows: `{summary['direct_replacement_cycle_source_ready_count']}`",
        f"- Overlay/source hints: `{summary['overlay_candidate_hint_count']}`",
        f"- Rows with overlay lifecycle context candidates: `{summary['rows_with_overlay_lifecycle_context_candidate_count']}`",
        f"- Overlay lifecycle Known nodes: `{summary['overlay_lifecycle_known_node_count']}`",
        f"- Overlay replacement Known nodes: `{summary['overlay_replacement_known_node_count']}`",
        f"- Overlay replacement Unknown nodes: `{summary['overlay_replacement_unknown_node_count']}`",
        f"- Lifecycle/replacement-cycle source required: `{summary['candidate_requires_lifecycle_source_count']}`",
        f"- Reviewed policy required: `{summary['candidate_requires_review_policy_count']}`",
        f"- Lifecycle-policy review templates: `{summary['lifecycle_policy_review_template_count']}`",
        f"- Lifecycle-policy review template contracts valid: `{summary['lifecycle_policy_review_template_contract_valid_count']}`",
        f"- Lifecycle-policy review template contracts invalid: `{summary['lifecycle_policy_review_template_contract_invalid_count']}`",
        f"- Lifecycle-policy review templates blank pending: `{summary['lifecycle_policy_review_template_blank_pending_count']}`",
        f"- Lifecycle-policy review template inputs ready: `{summary['lifecycle_policy_review_template_input_ready_count']}`",
        f"- Auto Known candidates allowed: `{summary['auto_known_candidate_count']}`",
        f"- Known-draft sufficient rows: `{summary['known_draft_sufficient_count']}`",
        f"- Approval-ready rows: `{summary['approval_ready_count']}`",
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
            "| dp_id | runtime deps | direct cycle source ready | overlay hints | lifecycle context | policy template | status | production write |",
            "|---|---:|---:|---:|---:|---:|---|---:|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"{'yes' if row['runtime_dependency_ready'] else 'no'} | "
            f"{'yes' if row['direct_replacement_cycle_source_ready'] else 'no'} | "
            f"{len(row['overlay_candidate_dp_ids'])} | "
            f"{'yes' if row['overlay_lifecycle_context_candidate_available'] else 'no'} | "
            f"{'yes' if row.get('lifecycle_policy_review_template_contract_valid') else 'no'} | "
            f"`{row['resolution_status']}` | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Revenue is a ready runtime dependency, but it is not replacement-cycle evidence.",
            "- Local stock overlays contain lifecycle context that can guide review, but it is not direct replacement-cycle source evidence.",
            "- The lifecycle-policy review template is a blank reviewer handoff; it is not classifier-ready, Known-ready, or production-write approval.",
            "- `L0.demand.replacement` needs lifecycle, installed-base, renewal, shipment, user, or reviewed overlay evidence before a Known value is defensible.",
            "- Existing industry graph or stock overlay hints can guide review, but they are not automatic production values.",
            "- Production score-affecting writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--single-dependency-path",
        type=Path,
        default=DEFAULT_SINGLE_DEPENDENCY_PATH,
    )
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument(
        "--stock-overlay-root",
        type=Path,
        default=DEFAULT_STOCK_OVERLAY_ROOT,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        args.single_dependency_path,
        args.candidate_path,
        stock_overlay_root=args.stock_overlay_root,
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
