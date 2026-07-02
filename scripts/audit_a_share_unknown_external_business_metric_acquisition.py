#!/usr/bin/env python3
"""Screen external/text business-metric evidence for A-share Unknown tasks.

This read-only audit executes the external/text business-metric portion of the
Unknown acquisition backlog. It packages what local runtime, structured-source,
and overlay evidence can support for frequency, penetration, and replacement.
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

from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_BACKLOG_PATH = (
    ROOT / "docs/audit/a_share_unknown_acquisition_backlog_2026-06-19.json"
)
DEFAULT_LOCAL_STRUCTURED_REVIEW_PATH = (
    ROOT / "docs/audit/a_share_local_structured_source_review_packets_2026-06-19.json"
)
DEFAULT_SINGLE_DEPENDENCY_OPTIONS_PATH = (
    ROOT / "docs/audit/a_share_local_single_dependency_unknown_source_options_2026-06-19.json"
)
DEFAULT_LOCAL_STRUCTURED_OPTIONS_PATH = (
    ROOT / "docs/audit/a_share_local_structured_unknown_source_options_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_external_business_metric_acquisition_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_external_business_metric_acquisition_2026-06-19.md"
)
DEFAULT_STOCK_OVERLAY_ROOT = ROOT / "config/stock_overlays"

EXTERNAL_BUSINESS_DP_IDS = {
    "L0.demand.frequency",
    "L0.demand.penetration",
    "L0.demand.replacement",
}

FREQUENCY_CONTEXT_DP_IDS = {
    "L4.volume.frequency",
    "L4.volume.foot_traffic",
    "L4.volume.orders",
    "L4.volume.sales",
    "L4.volume.shipments",
    "L4.volume.users",
}
PENETRATION_CONTEXT_DP_IDS = {
    "L1.position.market_share",
    "L2.segment.revenue_share",
    "L4.share.customer_channel",
    "L4.share.market",
    "L4.share.substitution",
}


def _rows_by_dp(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = dict(row)
    return rows


def _tasks(backlog: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in backlog.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("dp_id") not in EXTERNAL_BUSINESS_DP_IDS:
            continue
        if row.get("acquisition_track") != "external_or_text_business_metric":
            continue
        rows.append(dict(row))
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    return rows


def _runtime_dependency_ready(row: Mapping[str, Any] | None) -> bool:
    if not row:
        return False
    return bool(row.get("runtime_dependency_ready"))


def _runtime_dependency_count(row: Mapping[str, Any] | None) -> int:
    if not row:
        return 0
    return len(row.get("runtime_dependency_summary") or [])


def _local_structured_option(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "runtime_dependency_ready": _runtime_dependency_ready(row),
        "runtime_dependency_count": _runtime_dependency_count(row),
        "resolution_status": row.get("resolution_status"),
        "required_evidence": row.get("required_evidence") or [],
        "overlay_candidate_dp_ids": row.get("overlay_candidate_dp_ids") or [],
        "candidate_source_routes": row.get("candidate_source_routes") or [],
    }


def _source_review_option(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "source_review_packet_status": row.get("source_review_packet_status"),
        "candidate_columns": row.get("candidate_columns") or [],
        "missing_formula_inputs": row.get("missing_formula_inputs") or [],
        "excluded_false_positive_count": int(row.get("excluded_false_positive_count") or 0),
        "direct_known_ready": bool(row.get("direct_known_ready")),
        "formula_inputs_ready": bool(row.get("formula_inputs_ready")),
        "next_tushare_action": row.get("next_tushare_action"),
        "llm_or_web_fallback": row.get("llm_or_web_fallback"),
    }


def _single_dependency_option(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "runtime_dependency_ready": _runtime_dependency_ready(row),
        "runtime_dependency_count": _runtime_dependency_count(row),
        "resolution_status": row.get("resolution_status"),
        "direct_replacement_cycle_source_ready": bool(
            row.get("direct_replacement_cycle_source_ready")
        ),
        "required_evidence": row.get("required_evidence") or [],
        "overlay_candidate_dp_ids": row.get("overlay_candidate_dp_ids") or [],
        "candidate_source_routes": row.get("candidate_source_routes") or [],
        "lifecycle_source_required": bool(row.get("lifecycle_source_required")),
        "reviewed_policy_required": bool(row.get("reviewed_policy_required")),
        "dependency_limit": row.get("dependency_limit"),
    }


def _is_a_share_ts_code(ts_code: str) -> bool:
    return ts_code.endswith((".SZ", ".SH", ".BJ"))


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


def _overlay_context_group(dp_id: str) -> str:
    if dp_id == "L0.demand.frequency":
        return "frequency_direct"
    if dp_id == "L0.demand.penetration":
        return "penetration_direct"
    if dp_id in FREQUENCY_CONTEXT_DP_IDS:
        return "frequency_context"
    if dp_id in PENETRATION_CONTEXT_DP_IDS:
        return "penetration_context"
    return ""


def _sample_overlay_context(
    *,
    path: Path,
    ts_code: str,
    industry_id: str,
    node: Mapping[str, Any],
) -> dict[str, Any]:
    value_keys = node.get("value_keys")
    if not isinstance(value_keys, list):
        value_keys = []
    return {
        "path": _portable_path(path),
        "ts_code": ts_code,
        "industry_id": industry_id,
        "dp_id": node.get("dp_id"),
        "status": node.get("data_status") or node.get("status"),
        "confidence": node.get("confidence"),
        "last_updated": node.get("last_updated"),
        "value_keys": sorted(str(key) for key in value_keys),
        "metric_name": node.get("metric_name"),
        "unit": node.get("unit"),
        "period": node.get("period"),
        "evidence_source_count": int(node.get("evidence_source_count") or 0),
    }


def _finalize_overlay_node(
    *,
    path: Path,
    ts_code: str,
    industry_id: str,
    node: Mapping[str, Any],
    summary: dict[str, Any],
    sample_contexts: dict[str, list[dict[str, Any]]],
    seen_dp_ids: set[str],
) -> None:
    dp_id = str(node.get("dp_id") or "")
    if not dp_id or dp_id in seen_dp_ids:
        return
    group = _overlay_context_group(dp_id)
    if not group:
        return
    seen_dp_ids.add(dp_id)
    status = str(node.get("data_status") or node.get("status") or "")
    if status not in {"Known", "Unknown"}:
        return
    key = f"{group}_{status.lower()}_node_count"
    summary[key] = int(summary.get(key) or 0) + 1
    if status == "Known" and group in sample_contexts and len(sample_contexts[group]) < 5:
        sample_contexts[group].append(
            _sample_overlay_context(
                path=path,
                ts_code=ts_code,
                industry_id=industry_id,
                node=node,
            )
        )


def _scan_overlay_file(
    path: Path,
    *,
    summary: dict[str, Any],
    sample_contexts: dict[str, list[dict[str, Any]]],
) -> None:
    ts_code = ""
    industry_id = ""
    current_node: dict[str, Any] | None = None
    in_value = False
    in_evidence_sources = False
    seen_dp_ids: set[str] = set()
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
                            seen_dp_ids=seen_dp_ids,
                        )
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
                    for key in (
                        "metric_name",
                        "period",
                        "raw_value",
                        "score",
                        "unit",
                        "value",
                    ):
                        value = _line_value(line, key)
                        if value is not None:
                            current_node[key] = value
                            value_keys = current_node.setdefault("value_keys", [])
                            if isinstance(value_keys, list) and key not in value_keys:
                                value_keys.append(key)
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
            seen_dp_ids=seen_dp_ids,
        )


def _overlay_business_context_summary(overlay_root: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "overlay_root": _portable_path(overlay_root),
        "available": False,
        "direct_business_metric_source_ready": False,
        "direct_formula_input": False,
        "files_checked": 0,
        "a_share_files_checked": 0,
        "read_error_count": 0,
        "frequency_context_known_node_count": 0,
        "frequency_context_unknown_node_count": 0,
        "penetration_context_known_node_count": 0,
        "penetration_context_unknown_node_count": 0,
        "frequency_direct_known_node_count": 0,
        "frequency_direct_unknown_node_count": 0,
        "penetration_direct_known_node_count": 0,
        "penetration_direct_unknown_node_count": 0,
        "sample_frequency_contexts": [],
        "sample_penetration_contexts": [],
        "review_required": True,
        "reason_not_direct_source": (
            "Stock overlays contain adjacent volume/share context, but the current "
            "external-business-metric gate still requires reviewed source scope, "
            "denominator, period, and formula policy before Known scoring."
        ),
    }
    if not overlay_root.exists():
        return {**summary, "reason": "stock_overlay_root_missing"}

    sample_contexts: dict[str, list[dict[str, Any]]] = {
        "frequency_context": [],
        "penetration_context": [],
    }
    for path in sorted(overlay_root.glob("*/*.yaml")):
        summary["files_checked"] += 1
        _scan_overlay_file(path, summary=summary, sample_contexts=sample_contexts)

    summary["available"] = bool(
        summary["frequency_context_known_node_count"]
        or summary["penetration_context_known_node_count"]
    )
    summary["sample_frequency_contexts"] = sample_contexts["frequency_context"]
    summary["sample_penetration_contexts"] = sample_contexts["penetration_context"]
    return summary


def _overlay_business_context_for_dp(
    dp_id: str, context: Mapping[str, Any]
) -> dict[str, Any] | None:
    if dp_id == "L0.demand.frequency":
        return {
            "available": bool(context.get("frequency_context_known_node_count")),
            "dp_id": dp_id,
            "candidate_context_dp_ids": sorted(FREQUENCY_CONTEXT_DP_IDS),
            "context_known_node_count": int(
                context.get("frequency_context_known_node_count") or 0
            ),
            "context_unknown_node_count": int(
                context.get("frequency_context_unknown_node_count") or 0
            ),
            "direct_known_node_count": int(
                context.get("frequency_direct_known_node_count") or 0
            ),
            "direct_unknown_node_count": int(
                context.get("frequency_direct_unknown_node_count") or 0
            ),
            "sample_contexts": context.get("sample_frequency_contexts") or [],
            "direct_business_metric_source_ready": False,
            "direct_formula_input": False,
            "review_required": True,
            "reason_not_direct_source": context.get("reason_not_direct_source"),
        }
    if dp_id == "L0.demand.penetration":
        return {
            "available": bool(context.get("penetration_context_known_node_count")),
            "dp_id": dp_id,
            "candidate_context_dp_ids": sorted(PENETRATION_CONTEXT_DP_IDS),
            "context_known_node_count": int(
                context.get("penetration_context_known_node_count") or 0
            ),
            "context_unknown_node_count": int(
                context.get("penetration_context_unknown_node_count") or 0
            ),
            "direct_known_node_count": int(
                context.get("penetration_direct_known_node_count") or 0
            ),
            "direct_unknown_node_count": int(
                context.get("penetration_direct_unknown_node_count") or 0
            ),
            "sample_contexts": context.get("sample_penetration_contexts") or [],
            "direct_business_metric_source_ready": False,
            "direct_formula_input": False,
            "review_required": True,
            "reason_not_direct_source": context.get("reason_not_direct_source"),
        }
    return None


def _group(name: str, status: str, evidence: str, blockers: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "evidence": evidence,
        "blockers": blockers,
        "ready_for_metric": status == "ready",
    }


def _metric_groups(
    dp_id: str,
    *,
    task: Mapping[str, Any],
    local_option: Mapping[str, Any],
    source_review: Mapping[str, Any],
    single_option: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if dp_id == "L0.demand.frequency":
        return [
            _group(
                "revenue_context",
                "supporting_context",
                f"runtime dependencies={task.get('source_dependencies') or []}",
                ["revenue/revenue growth cannot separate order count or usage cadence"],
            ),
            _group(
                "direct_cadence_source",
                "missing",
                f"candidate columns={source_review.get('candidate_columns') or []}",
                source_review.get("missing_formula_inputs") or [
                    "order count, transaction count, shipment frequency, or usage cadence is required"
                ],
            ),
            _group(
                "normalization_denominator",
                "missing",
                "active customer/user/channel denominator not present",
                ["cadence cannot be normalized without customer, user, channel, or installed-base denominator"],
            ),
            _group(
                "decomposition_policy",
                "missing",
                "no reviewed decomposition policy",
                ["review must separate cadence from ASP, mix, and revenue growth"],
            ),
        ]
    if dp_id == "L0.demand.penetration":
        return [
            _group(
                "company_numerator_context",
                "supporting_context",
                f"runtime dependencies={task.get('source_dependencies') or []}",
                ["revenue can only provide company context, not a penetration value by itself"],
            ),
            _group(
                "market_denominator",
                "missing",
                f"candidate columns={source_review.get('candidate_columns') or []}",
                source_review.get("missing_formula_inputs") or [
                    "market share, TAM, installed-base, or user-base denominator is required"
                ],
            ),
            _group(
                "scope_alignment",
                "missing",
                "no same-scope numerator/denominator mapping",
                ["company numerator and market denominator must share geography, product, unit, and period"],
            ),
            _group(
                "source_precedence_policy",
                "missing",
                "no reviewed source precedence policy",
                ["reviewed source precedence and bounds are required before scoring"],
            ),
        ]
    if dp_id == "L0.demand.replacement":
        overlay_hints = single_option.get("overlay_candidate_dp_ids") or []
        return [
            _group(
                "revenue_context",
                "supporting_context",
                f"runtime dependency ready={single_option.get('runtime_dependency_ready')}",
                ["revenue cannot distinguish replacement demand from new demand"],
            ),
            _group(
                "overlay_hints",
                "supporting_context",
                f"overlay hints={len(overlay_hints)}",
                ["overlay hints are reviewer context only, not direct replacement-cycle evidence"],
            ),
            _group(
                "lifecycle_or_installed_base_source",
                "missing",
                f"direct replacement-cycle source ready={single_option.get('direct_replacement_cycle_source_ready')}",
                single_option.get("required_evidence") or [
                    "product lifecycle, installed base, renewal trend, or replacement-cycle source is required"
                ],
            ),
            _group(
                "replacement_policy",
                "missing",
                "reviewed replacement-cycle policy absent",
                ["review must separate replacement demand from new demand and revenue scalar"],
            ),
        ]
    return []


def _row(
    *,
    task: Mapping[str, Any],
    local_structured_row: Mapping[str, Any] | None,
    source_review_row: Mapping[str, Any] | None,
    single_dependency_row: Mapping[str, Any] | None,
    overlay_business_context: Mapping[str, Any],
) -> dict[str, Any]:
    dp_id = str(task.get("dp_id") or "")
    source_review = _source_review_option(source_review_row)
    local_option = _local_structured_option(local_structured_row)
    single_option = _single_dependency_option(single_dependency_row)
    overlay_business_context_candidate = _overlay_business_context_for_dp(
        dp_id, overlay_business_context
    )
    groups = _metric_groups(
        dp_id,
        task=task,
        local_option=local_option,
        source_review=source_review,
        single_option=single_option,
    )
    ready_group_count = sum(1 for group in groups if group["ready_for_metric"])
    metric_inputs_ready = all(group["ready_for_metric"] for group in groups)
    if dp_id == "L0.demand.frequency":
        status = "cadence_source_required"
    elif dp_id == "L0.demand.penetration":
        status = "market_denominator_required"
    else:
        status = "lifecycle_replacement_cycle_required"
    return {
        "task_id": task.get("task_id"),
        "dp_id": dp_id,
        "score_target": task.get("score_target"),
        "data_status": "Unknown",
        "acquisition_track": task.get("acquisition_track"),
        "source_priority": task.get("source_priority"),
        "source_dependencies": task.get("source_dependencies") or [],
        "source_review": source_review,
        "local_structured_option": local_option,
        "single_dependency_option": single_option,
        "overlay_business_context_candidate_available": bool(
            overlay_business_context_candidate
            and overlay_business_context_candidate.get("available")
        ),
        "overlay_business_context_candidate": overlay_business_context_candidate,
        "business_metric_groups": groups,
        "business_metric_group_count": len(groups),
        "business_metric_group_ready_count": ready_group_count,
        "runtime_dependency_ready": bool(
            local_option.get("runtime_dependency_ready")
            or single_option.get("runtime_dependency_ready")
        ),
        "runtime_overlay_hint_count": len(single_option.get("overlay_candidate_dp_ids") or []),
        "excluded_false_positive_count": int(
            source_review.get("excluded_false_positive_count") or 0
        ),
        "metric_inputs_ready": metric_inputs_ready,
        "metric_candidate_status": status,
        "ready_for_known_draft": False,
        "ready_for_approval": False,
        "review_required": True,
        "safe_to_upsert_without_review": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "score_mutation": "none",
    }


def _validation_errors(row: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not row.get("dp_id"):
        errors.append("dp_id is required")
    if row.get("data_status") != "Unknown":
        errors.append("data_status must stay Unknown")
    if not row.get("business_metric_groups"):
        errors.append("business_metric_groups are required")
    if row.get("metric_inputs_ready") is not False:
        errors.append("metric_inputs_ready must be false until all groups are ready")
    if row.get("ready_for_known_draft") is not False:
        errors.append("ready_for_known_draft must be false")
    if row.get("ready_for_approval") is not False:
        errors.append("ready_for_approval must be false")
    if row.get("runtime_write_allowed") is not False:
        errors.append("runtime_write_allowed must be false")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    return errors


def build_report(
    *,
    backlog_path: Path,
    local_structured_review_path: Path,
    single_dependency_options_path: Path,
    local_structured_options_path: Path,
    stock_overlay_root: Path = DEFAULT_STOCK_OVERLAY_ROOT,
) -> dict[str, Any]:
    started = time.time()
    backlog = _load_json(backlog_path)
    source_review = _load_json(local_structured_review_path)
    single_dependency_options = _load_json(single_dependency_options_path)
    local_structured_options = _load_json(local_structured_options_path)
    source_review_by_dp = _rows_by_dp(source_review)
    single_dependency_by_dp = _rows_by_dp(single_dependency_options)
    local_structured_by_dp = _rows_by_dp(local_structured_options)
    overlay_business_context = _overlay_business_context_summary(stock_overlay_root)

    rows = [
        _row(
            task=task,
            local_structured_row=local_structured_by_dp.get(str(task.get("dp_id") or "")),
            source_review_row=source_review_by_dp.get(str(task.get("dp_id") or "")),
            single_dependency_row=single_dependency_by_dp.get(str(task.get("dp_id") or "")),
            overlay_business_context=overlay_business_context,
        )
        for task in _tasks(backlog)
    ]
    rows.sort(key=lambda row: str(row["dp_id"]))
    for row in rows:
        errors = _validation_errors(row)
        row["packet_contract_valid"] = not errors
        row["packet_validation_errors"] = errors

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "backlog_path": _portable_path(backlog_path),
            "local_structured_review_path": _portable_path(local_structured_review_path),
            "single_dependency_options_path": _portable_path(single_dependency_options_path),
            "local_structured_options_path": _portable_path(local_structured_options_path),
            "stock_overlay_root": _portable_path(stock_overlay_root),
        },
        "summary": {
            "external_business_metric_task_count": len(rows),
            "runtime_dependency_ready_count": sum(
                1 for row in rows if row["runtime_dependency_ready"]
            ),
            "runtime_overlay_hint_count": sum(
                int(row["runtime_overlay_hint_count"]) for row in rows
            ),
            "business_metric_group_count": sum(
                int(row["business_metric_group_count"]) for row in rows
            ),
            "business_metric_group_ready_count": sum(
                int(row["business_metric_group_ready_count"]) for row in rows
            ),
            "rows_with_supporting_runtime_context_count": sum(
                1
                for row in rows
                if any(
                    group["status"] == "supporting_context"
                    for group in row["business_metric_groups"]
                )
            ),
            "rows_with_overlay_business_context_candidate_count": sum(
                1 for row in rows if row["overlay_business_context_candidate_available"]
            ),
            "overlay_stock_files_checked": int(
                overlay_business_context.get("files_checked") or 0
            ),
            "overlay_a_share_files_checked": int(
                overlay_business_context.get("a_share_files_checked") or 0
            ),
            "overlay_read_error_count": int(
                overlay_business_context.get("read_error_count") or 0
            ),
            "overlay_business_context_known_node_count": int(
                overlay_business_context.get("frequency_context_known_node_count") or 0
            )
            + int(overlay_business_context.get("penetration_context_known_node_count") or 0),
            "overlay_frequency_context_known_node_count": int(
                overlay_business_context.get("frequency_context_known_node_count") or 0
            ),
            "overlay_penetration_context_known_node_count": int(
                overlay_business_context.get("penetration_context_known_node_count") or 0
            ),
            "overlay_frequency_direct_known_node_count": int(
                overlay_business_context.get("frequency_direct_known_node_count") or 0
            ),
            "overlay_penetration_direct_known_node_count": int(
                overlay_business_context.get("penetration_direct_known_node_count") or 0
            ),
            "overlay_frequency_direct_unknown_node_count": int(
                overlay_business_context.get("frequency_direct_unknown_node_count") or 0
            ),
            "overlay_penetration_direct_unknown_node_count": int(
                overlay_business_context.get("penetration_direct_unknown_node_count") or 0
            ),
            "rows_with_direct_business_metric_source_count": 0,
            "rows_requiring_external_or_text_source_count": len(rows),
            "excluded_false_positive_count": sum(
                int(row["excluded_false_positive_count"]) for row in rows
            ),
            "metric_inputs_ready_count": sum(
                1 for row in rows if row["metric_inputs_ready"]
            ),
            "ready_for_known_draft_count": sum(
                1 for row in rows if row["ready_for_known_draft"]
            ),
            "ready_for_approval_count": sum(1 for row in rows if row["ready_for_approval"]),
            "packet_contract_valid_count": sum(
                1 for row in rows if row["packet_contract_valid"]
            ),
            "packet_contract_invalid_count": sum(
                1 for row in rows if not row["packet_contract_valid"]
            ),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "overlay_business_context": overlay_business_context,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown external business metric acquisition",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- External business metric tasks: `{summary['external_business_metric_task_count']}`",
        f"- Runtime dependency-ready tasks: `{summary['runtime_dependency_ready_count']}`",
        f"- Runtime overlay hints: `{summary['runtime_overlay_hint_count']}`",
        f"- Business metric groups: `{summary['business_metric_group_count']}`",
        f"- Business metric groups ready: `{summary['business_metric_group_ready_count']}`",
        f"- Rows with supporting runtime context: `{summary['rows_with_supporting_runtime_context_count']}`",
        f"- Rows with overlay business context candidates: `{summary['rows_with_overlay_business_context_candidate_count']}`",
        f"- Overlay A-share files checked: `{summary['overlay_a_share_files_checked']}`",
        f"- Overlay business context Known nodes: `{summary['overlay_business_context_known_node_count']}`",
        f"- Overlay frequency context Known nodes: `{summary['overlay_frequency_context_known_node_count']}`",
        f"- Overlay penetration context Known nodes: `{summary['overlay_penetration_context_known_node_count']}`",
        f"- Overlay frequency direct Known/Unknown nodes: `{summary['overlay_frequency_direct_known_node_count']}`/`{summary['overlay_frequency_direct_unknown_node_count']}`",
        f"- Overlay penetration direct Known/Unknown nodes: `{summary['overlay_penetration_direct_known_node_count']}`/`{summary['overlay_penetration_direct_unknown_node_count']}`",
        f"- Rows with direct business metric source: `{summary['rows_with_direct_business_metric_source_count']}`",
        f"- Rows requiring external/text source: `{summary['rows_requiring_external_or_text_source_count']}`",
        f"- Excluded false positives: `{summary['excluded_false_positive_count']}`",
        f"- Metric inputs ready: `{summary['metric_inputs_ready_count']}`",
        f"- Ready for Known draft: `{summary['ready_for_known_draft_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | status | groups ready | runtime context | overlay context | false positives | production write |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['metric_candidate_status']}` | "
            f"{row['business_metric_group_ready_count']}/{row['business_metric_group_count']} | "
            f"{'yes' if row['runtime_dependency_ready'] else 'no'} | "
            f"{'yes' if row['overlay_business_context_candidate_available'] else 'no'} | "
            f"{row['excluded_false_positive_count']} | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Frequency and penetration have revenue context and adjacent overlay business context, but no direct reviewed cadence, denominator, or source-policy evidence.",
            "- Replacement has revenue context and overlay hints, but no direct lifecycle or replacement-cycle source.",
            "- These acquisition rows remain Unknown and cannot write to runtime scoring.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backlog-path", type=Path, default=DEFAULT_BACKLOG_PATH)
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
    parser.add_argument(
        "--local-structured-options-path",
        type=Path,
        default=DEFAULT_LOCAL_STRUCTURED_OPTIONS_PATH,
    )
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
        backlog_path=args.backlog_path,
        local_structured_review_path=args.local_structured_review_path,
        single_dependency_options_path=args.single_dependency_options_path,
        local_structured_options_path=args.local_structured_options_path,
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
