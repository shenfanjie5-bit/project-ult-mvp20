#!/usr/bin/env python3
"""Draft review-only values for A-share manual-policy candidate tasks.

This pilot is deliberately read-only.  It consumes the generation queue and
candidate-evidence audit, drafts bounded review packets for manual-policy rows
that can be derived from existing dependency evidence, and keeps unsupported
rows Unknown.  It never writes ``runtime/hot.sqlite`` or overlay YAML.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from mvp20.aggregator import _realtime_signal, synthesize_realtime_nodes
from mvp20.field_governance import load_default_governance


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUEUE_PATH = ROOT / "docs/audit/a_share_candidate_generation_queue_2026-06-19.json"
DEFAULT_CANDIDATE_PATH = ROOT / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_manual_policy_draft_candidates_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_manual_policy_draft_candidates_2026-06-19.md"
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
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _candidate_rows_by_dp(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = row
    return rows


def _manual_tasks(queue: Mapping[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for task in queue.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if task.get("generator_kind") == "manual_policy_candidate":
            tasks.append(task)
    return tasks


def _deps(candidate_row: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    candidate_input = (
        candidate_row.get("candidate_input")
        if isinstance(candidate_row, Mapping)
        else None
    )
    deps: dict[str, dict[str, Any]] = {}
    if not isinstance(candidate_input, Mapping):
        return deps
    for dep in candidate_input.get("dependencies") or []:
        if not isinstance(dep, dict):
            continue
        dp_id = str(dep.get("dp_id") or "")
        if dp_id:
            deps[dp_id] = dep
    return deps


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _round(value: float) -> float:
    return round(float(value), 6)


def _sample_value_rows(dep: Mapping[str, Any] | None) -> Iterable[Mapping[str, Any]]:
    if not isinstance(dep, Mapping):
        return []
    rows = []
    for sample in dep.get("sample_rows") or []:
        if not isinstance(sample, Mapping):
            continue
        compact = sample.get("value_json_compact")
        if isinstance(compact, Mapping):
            rows.append(compact)
    return rows


def _values(dep: Mapping[str, Any] | None, *keys: str) -> list[float]:
    out: list[float] = []
    for row in _sample_value_rows(dep):
        for key in keys:
            value = _safe_float(row.get(key))
            if value is not None:
                out.append(value)
                break
    return out


def _avg(values: Iterable[float], default: float = 0.0) -> float:
    nums = list(values)
    if not nums:
        return default
    return sum(nums) / len(nums)


def _known_ratio(dep: Mapping[str, Any] | None) -> float:
    if not isinstance(dep, Mapping):
        return 0.0
    row_count = _safe_float(dep.get("row_count")) or 0.0
    known_count = _safe_float(dep.get("known_count")) or 0.0
    if row_count <= 0:
        return 0.0
    return _clip(known_count / row_count)


def _evidence_refs(candidate_row: Mapping[str, Any] | None, deps: Mapping[str, Any]) -> list[str]:
    refs = ["docs/audit/a_share_gap_candidate_evidence_2026-06-19.json"]
    for dep_id in deps:
        refs.append(f"runtime:realtime_current:{dep_id}")
    if isinstance(candidate_row, Mapping):
        route = candidate_row.get("recommended_source_route")
        if route:
            refs.append(f"candidate_route:{route}")
    return list(dict.fromkeys(refs))


def _payload_envelope(
    *,
    dp_id: str,
    score_target: str,
    data_status: str,
    value_json: dict[str, Any],
    confidence: float,
    evidence_refs: list[str],
    rationale: str,
    draft_status: str,
) -> dict[str, Any]:
    return {
        "target_dp_id": dp_id,
        "score_target": score_target,
        "data_status": data_status,
        "bridge_entry_data_status": data_status,
        "value_json": value_json,
        "confidence": _round(_clip(confidence)),
        "evidence_refs": evidence_refs,
        "rationale": rationale,
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "draft_kind": "manual_policy_pilot",
        "draft_status": draft_status,
        "pilot_only": True,
        "production_write_allowed": False,
    }


def _bridge_validation(dp_id: str, score_target: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    value_json = payload.get("value_json")
    signal = _realtime_signal(dp_id, value_json, score_target, ts_code="000001.SZ")
    registry = load_default_governance(strict=False)
    entry = {
        "value": value_json,
        "data_status": payload.get("bridge_entry_data_status", payload.get("data_status")),
        "confidence": payload.get("confidence", 0.5),
        "source": "candidate:manual_policy_pilot",
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
        "node_direction": node.get("direction") if node else None,
        "node_synthetic_realtime": bool(node and node.get("synthetic_realtime")),
        "final_score_target_ready": bool(
            node is not None and score_target not in FINAL_SCORE_EXCLUDED_TARGETS
        ),
    }


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_draft_payload(dp_id: str, score_target: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if payload.get("target_dp_id") != dp_id:
        errors.append("target_dp_id does not match row dp_id")
    if payload.get("score_target") != score_target:
        errors.append("score_target does not match row score_target")
    if payload.get("data_status") not in {"Known", "Unknown", "NotApplicable"}:
        errors.append("data_status must be Known, Unknown, or NotApplicable")
    if payload.get("bridge_entry_data_status") not in {"Known", "Unknown", "NotApplicable"}:
        errors.append("bridge_entry_data_status must be Known, Unknown, or NotApplicable")
    confidence = _safe_float(payload.get("confidence"))
    if confidence is None or not 0.0 <= confidence <= 1.0:
        errors.append("confidence must be a finite number in [0, 1]")
    evidence_refs = payload.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs or not all(
        _nonempty_string(ref) for ref in evidence_refs
    ):
        errors.append("evidence_refs must be a non-empty list of strings")
    if not _nonempty_string(payload.get("rationale")):
        errors.append("rationale must be a non-empty string")
    if payload.get("review_status") != "review_required":
        errors.append("review_status must be review_required")
    if payload.get("safe_to_upsert_without_review") is not False:
        errors.append("safe_to_upsert_without_review must be false")
    if payload.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    if payload.get("pilot_only") is not True:
        errors.append("pilot_only must be true")
    raw_value_json = payload.get("value_json")
    value_json = raw_value_json if isinstance(raw_value_json, Mapping) else None
    if value_json is None:
        errors.append("value_json must be an object")
        value_json = {}

    if payload.get("data_status") == "Unknown":
        if value_json.get("review_required") is not True:
            errors.append("Unknown draft value_json.review_required must be true")
        if not _nonempty_string(value_json.get("blocked_reason")):
            errors.append("Unknown draft must include blocked_reason")
    elif payload.get("data_status") == "Known":
        if dp_id in {"L6.priced.realization_risk", "L8.val.slope_risk_off"}:
            magnitude = _safe_float(value_json.get("magnitude"))
            if magnitude is None or not 0.0 <= magnitude <= 1.0:
                errors.append("magnitude must be finite and in [0, 1]")
            if not isinstance(value_json.get("drivers"), list) or not value_json.get("drivers"):
                errors.append("drivers must be a non-empty list")
        elif dp_id == "L7.reflex.tag":
            multiplier = _safe_float(value_json.get("multiplier"))
            if multiplier is None or not 0.0 < multiplier <= 2.0:
                errors.append("multiplier must be finite and in (0, 2]")
            if value_json.get("tag") not in {
                "positive_feedback",
                "exhausted_feedback",
                "neutral",
            }:
                errors.append("tag must be positive_feedback, exhausted_feedback, or neutral")
        elif dp_id == "L6.mult.dcf":
            score = _safe_float(value_json.get("score"))
            if score is None or not -1.0 <= score <= 1.0:
                errors.append("score must be finite and in [-1, 1]")
            magnitude = _safe_float(value_json.get("magnitude"))
            if magnitude is None or not 0.0 <= magnitude <= 1.0:
                errors.append("magnitude must be finite and in [0, 1]")
            if not isinstance(value_json.get("drivers"), list) or not value_json.get("drivers"):
                errors.append("drivers must be a non-empty list")
            assumptions = value_json.get("dcf_assumptions")
            if not isinstance(assumptions, Mapping):
                errors.append("dcf_assumptions must be an object")
            else:
                required = {
                    "discount_rate",
                    "terminal_growth",
                    "forecast_horizon_years",
                    "normalized_fcf_basis",
                }
                missing = sorted(required - set(assumptions))
                if missing:
                    errors.append(f"dcf_assumptions missing keys: {missing}")
    return {
        "contract_valid": not errors,
        "validation_errors": errors,
    }


def _dcf_review_draft(dp_id: str, score_target: str, candidate_row: Mapping[str, Any] | None, deps: Mapping[str, Any]) -> dict[str, Any]:
    fcf_values = _values(deps.get("L5.cf.fcf"), "scalar")
    revenue_growth_values = _values(deps.get("L5.is.revenue_growth"), "yoy_pct")
    mcap_fcf_values = [v for v in _values(deps.get("L6.mult.mcap_fcf"), "scalar") if v > 0]
    growth_margin_multipliers = _values(deps.get("L6.sens.growth_margin"), "multiplier")
    cashflow_multipliers = _values(deps.get("L6.sens.cashflow"), "multiplier")
    rates_multipliers = _values(deps.get("L6.sens.rates"), "multiplier")

    positive_fcf_ratio = (
        sum(1 for value in fcf_values if value > 0) / len(fcf_values)
        if fcf_values
        else 0.0
    )
    avg_revenue_growth_pct = _avg(revenue_growth_values)
    avg_mcap_fcf = _avg(mcap_fcf_values, default=0.0)
    fcf_yield = (1.0 / avg_mcap_fcf) if avg_mcap_fcf > 0 else 0.0
    avg_growth_margin_multiplier = _avg(growth_margin_multipliers, default=1.0)
    avg_cashflow_multiplier = _avg(cashflow_multipliers, default=1.0)
    avg_rates_multiplier = _avg(rates_multipliers, default=1.0)

    discount_rate = 0.095 + 0.01 * _clip(avg_rates_multiplier - 1.0, -0.5, 0.5)
    terminal_growth = _clip((avg_revenue_growth_pct / 100.0) * 0.25, -0.01, 0.03)
    forecast_horizon_years = 5
    normalized_fcf_basis = (
        "positive_sample_average" if positive_fcf_ratio >= 0.5 else "mixed_or_negative_fcf_penalized"
    )
    valuation_edge = fcf_yield + terminal_growth - discount_rate
    quality_multiplier = _clip(
        0.50 * avg_growth_margin_multiplier + 0.50 * avg_cashflow_multiplier,
        0.25,
        1.25,
    )
    negative_fcf_penalty = (1.0 - positive_fcf_ratio) * 0.30
    raw_score = math.tanh(valuation_edge / 0.08) * quality_multiplier - negative_fcf_penalty
    score = _clip(raw_score, -1.0, 1.0)
    components = {
        "positive_fcf_sample_ratio": _round(positive_fcf_ratio),
        "sample_avg_revenue_growth_pct": _round(avg_revenue_growth_pct),
        "sample_avg_mcap_fcf": _round(avg_mcap_fcf),
        "fcf_yield_proxy": _round(fcf_yield),
        "valuation_edge": _round(valuation_edge),
        "growth_margin_multiplier": _round(avg_growth_margin_multiplier),
        "cashflow_multiplier": _round(avg_cashflow_multiplier),
        "rates_multiplier": _round(avg_rates_multiplier),
        "quality_multiplier": _round(quality_multiplier),
        "negative_fcf_penalty": _round(negative_fcf_penalty),
    }
    return _payload_envelope(
        dp_id=dp_id,
        score_target=score_target,
        data_status="Known",
        value_json={
            "score": _round(score),
            "magnitude": _round(abs(score)),
            "drivers": [
                "L5.cf.fcf",
                "L5.is.revenue_growth",
                "L6.sens.rates",
                "L6.sens.growth_margin",
                "L6.sens.cashflow",
                "L6.mult.mcap_fcf",
            ],
            "dcf_assumptions": {
                "discount_rate": _round(discount_rate),
                "terminal_growth": _round(terminal_growth),
                "forecast_horizon_years": forecast_horizon_years,
                "normalized_fcf_basis": normalized_fcf_basis,
            },
            "components": components,
        },
        confidence=0.32,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Pilot emits a bounded DCF rerating draft from existing FCF, revenue-growth, "
            "rates, sensitivity, and mcap/FCF evidence using explicit conservative "
            "standard assumptions. The output is review-only and must not be written "
            "to runtime without a matching approval record."
        ),
        draft_status="draft_known_standard_dcf_assumption_review_required",
    )


def _realization_risk(dp_id: str, score_target: str, candidate_row: Mapping[str, Any] | None, deps: Mapping[str, Any]) -> dict[str, Any]:
    run_up_values = _values(deps.get("L6.priced.run_up"), "d20_pct", "d5_pct")
    run_up_component = _avg(_clip(max(v, 0.0) / 0.20) for v in run_up_values)
    news_age_component = _avg(_clip(v) for v in _values(deps.get("L6.priced.news_age"), "magnitude", "scalar"))
    preprice_component = _known_ratio(deps.get("L5.surprise.preprice"))
    priced_in_component = _avg(_clip(v) for v in _values(deps.get("L8.val.priced_in"), "priced_in_score"))
    magnitude = _clip(
        0.35 * run_up_component
        + 0.35 * news_age_component
        + 0.15 * preprice_component
        + 0.15 * priced_in_component
    )
    components = {
        "run_up_component": _round(run_up_component),
        "news_age_component": _round(news_age_component),
        "preprice_known_ratio": _round(preprice_component),
        "priced_in_component": _round(priced_in_component),
    }
    return _payload_envelope(
        dp_id=dp_id,
        score_target=score_target,
        data_status="Known",
        value_json={
            "magnitude": _round(magnitude),
            "drivers": [
                "L6.priced.run_up",
                "L6.priced.news_age",
                "L5.surprise.preprice",
                "L8.val.priced_in",
            ],
            "components": components,
        },
        confidence=0.45,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Pilot combines positive recent run-up, fresh catalyst age, sparse preprice coverage, "
            "and current priced-in score into a bounded realization-risk discount for review."
        ),
        draft_status="draft_known_review_required",
    )


def _reflex_tag(dp_id: str, score_target: str, candidate_row: Mapping[str, Any] | None, deps: Mapping[str, Any]) -> dict[str, Any]:
    inflow_values = _values(deps.get("L7.flow.active_inflow"), "main_net")
    inflow_component = _avg(math.tanh(v / 50_000.0) for v in inflow_values)
    fomo_component = _avg(_clip(v) for v in _values(deps.get("L7.mood.fomo"), "score"))
    media_component = _known_ratio(deps.get("L7.mood.media_social"))
    run_up_values = _values(deps.get("L6.priced.run_up"), "d20_pct", "d5_pct")
    run_up_component = _avg(_clip(max(v, 0.0) / 0.20) for v in run_up_values)
    reflex_score = _clip(
        0.35 * max(inflow_component, 0.0)
        + 0.30 * fomo_component
        + 0.15 * media_component
        + 0.20 * run_up_component
    )
    if reflex_score >= 0.35:
        tag = "positive_feedback"
        multiplier = 1.0 + min(reflex_score * 0.12, 0.12)
    elif reflex_score <= 0.08:
        tag = "neutral"
        multiplier = 1.0
    else:
        tag = "neutral"
        multiplier = 1.0 + min(reflex_score * 0.05, 0.03)
    components = {
        "active_inflow_component": _round(inflow_component),
        "fomo_component": _round(fomo_component),
        "media_known_ratio": _round(media_component),
        "run_up_component": _round(run_up_component),
        "reflex_score": _round(reflex_score),
    }
    return _payload_envelope(
        dp_id=dp_id,
        score_target=score_target,
        data_status="Known",
        value_json={
            "multiplier": _round(multiplier),
            "tag": tag,
            "components": components,
        },
        confidence=0.40,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Pilot keeps reflexivity close to neutral because FOMO is moderate and media/social "
            "coverage is sparse, while inflow/run-up samples do not prove a crowded loop."
        ),
        draft_status="draft_known_review_required",
    )


def _slope_risk_off(dp_id: str, score_target: str, candidate_row: Mapping[str, Any] | None, deps: Mapping[str, Any]) -> dict[str, Any]:
    slope_component = _avg(
        _clip(abs(min(v, 0.0)) / 0.02)
        for v in _values(deps.get("L6.path.second_derivative"), "second_derivative")
    )
    overvalued_component = _avg(_clip(v) for v in _values(deps.get("L8.val.overvalued"), "max_quantile"))
    risk_appetite_component = _avg(
        _clip(max(1.0 - v, 0.0))
        for v in _values(deps.get("L7.env.risk_appetite"), "multiplier")
    )
    rate_change_values = _values(deps.get("L9.macro.rates"), "lpr_1y_change_bp", "change_bp")
    rates_component = _avg(_clip(max(v, 0.0) / 50.0) for v in rate_change_values)
    expansion_component = _known_ratio(deps.get("L6.state.expansion_compression"))
    magnitude = _clip(
        0.30 * slope_component
        + 0.30 * overvalued_component
        + 0.20 * risk_appetite_component
        + 0.10 * rates_component
        + 0.10 * expansion_component
    )
    components = {
        "slope_component": _round(slope_component),
        "overvalued_component": _round(overvalued_component),
        "risk_appetite_component": _round(risk_appetite_component),
        "rates_component": _round(rates_component),
        "expansion_known_ratio": _round(expansion_component),
    }
    return _payload_envelope(
        dp_id=dp_id,
        score_target=score_target,
        data_status="Known",
        value_json={
            "magnitude": _round(magnitude),
            "drivers": [
                "L6.path.second_derivative",
                "L8.val.overvalued",
                "L7.env.risk_appetite",
                "L9.macro.rates",
                "L6.state.expansion_compression",
            ],
            "components": components,
        },
        confidence=0.45,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Pilot combines decelerating price/valuation slope, valuation quantile, neutral risk appetite, "
            "non-tightening CN LPR evidence, and sparse compression-state coverage into bounded risk-off magnitude."
        ),
        draft_status="draft_known_review_required",
    )


def _draft_payload(task: Mapping[str, Any], candidate_row: Mapping[str, Any] | None) -> dict[str, Any]:
    dp_id = str(task.get("dp_id") or "")
    score_target = str(task.get("score_target") or "")
    deps = _deps(candidate_row)
    if candidate_row is None:
        return _payload_envelope(
            dp_id=dp_id,
            score_target=score_target,
            data_status="Unknown",
            value_json={"review_required": True, "blocked_reason": "missing_candidate_evidence"},
            confidence=0.0,
            evidence_refs=["docs/audit/a_share_candidate_generation_queue_2026-06-19.json"],
            rationale="Manual-policy task has no matching candidate-evidence row; keep Unknown.",
            draft_status="unknown_missing_candidate_evidence",
        )
    if dp_id == "L6.mult.dcf":
        return _dcf_review_draft(dp_id, score_target, candidate_row, deps)
    if dp_id == "L6.priced.realization_risk":
        return _realization_risk(dp_id, score_target, candidate_row, deps)
    if dp_id == "L7.reflex.tag":
        return _reflex_tag(dp_id, score_target, candidate_row, deps)
    if dp_id == "L8.val.slope_risk_off":
        return _slope_risk_off(dp_id, score_target, candidate_row, deps)
    return _payload_envelope(
        dp_id=dp_id,
        score_target=score_target,
        data_status="Unknown",
        value_json={"review_required": True, "blocked_reason": "unsupported_manual_policy_pilot"},
        confidence=0.0,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale="This manual-policy dp_id is not supported by the pilot generator.",
        draft_status="unknown_unsupported_manual_policy",
    )


def build_report(queue_path: Path, candidate_path: Path) -> dict[str, Any]:
    started = time.time()
    queue = _load_json(queue_path)
    candidate = _load_json(candidate_path)
    candidate_rows = _candidate_rows_by_dp(candidate)
    rows: list[dict[str, Any]] = []
    for task in _manual_tasks(queue):
        dp_id = str(task.get("dp_id") or "")
        candidate_row = candidate_rows.get(dp_id)
        payload = _draft_payload(task, candidate_row)
        bridge = (
            _bridge_validation(dp_id, str(task.get("score_target") or ""), payload)
            if payload.get("data_status") == "Known"
            else {}
        )
        contract = _validate_draft_payload(dp_id, str(task.get("score_target") or ""), payload)
        rows.append(
            {
                "dp_id": dp_id,
                "score_target": task.get("score_target"),
                "task_id": task.get("task_id"),
                "candidate_status": candidate_row.get("candidate_status") if candidate_row else None,
                "source_dependencies": candidate_row.get("source_dependencies") if candidate_row else [],
                "manual_policy_name": (
                    ((candidate_row.get("candidate_input") or {}).get("manual_design_policy") or {}).get("policy_name")
                    if isinstance(candidate_row, Mapping)
                    else None
                ),
                "draft_status": payload.get("draft_status"),
                "draft_payload": payload,
                "contract_validation": contract,
                "bridge_validation": bridge,
                "production_write_allowed": False,
                "note": "review-only pilot draft; no production write is allowed",
            }
        )

    draft_status_counts = Counter(str(row["draft_status"]) for row in rows)
    known_rows = [
        row
        for row in rows
        if (row.get("draft_payload") or {}).get("data_status") == "Known"
    ]
    unknown_rows = [
        row
        for row in rows
        if (row.get("draft_payload") or {}).get("data_status") == "Unknown"
    ]
    invalid_rows = [row for row in rows if not row["contract_validation"]["contract_valid"]]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "queue_path": _portable_path(queue_path),
        "candidate_path": _portable_path(candidate_path),
        "summary": {
            "manual_policy_task_count": len(rows),
            "draft_payload_count": len(rows),
            "draft_known_count": len(known_rows),
            "draft_unknown_count": len(unknown_rows),
            "draft_contract_valid_count": sum(
                1 for row in rows if row["contract_validation"]["contract_valid"]
            ),
            "draft_contract_invalid_count": len(invalid_rows),
            "draft_contract_invalid_dp_ids": [row["dp_id"] for row in invalid_rows],
            "bridge_validated_known_count": sum(
                1 for row in known_rows if row["bridge_validation"].get("final_score_target_ready")
            ),
            "bridge_blocked_known_count": sum(
                1 for row in known_rows if not row["bridge_validation"].get("final_score_target_ready")
            ),
            "review_required_count": sum(
                1
                for row in rows
                if (row.get("draft_payload") or {}).get("review_status") == "review_required"
            ),
            "pilot_only_count": sum(
                1 for row in rows if (row.get("draft_payload") or {}).get("pilot_only") is True
            ),
            "safe_to_upsert_without_review_count": sum(
                1
                for row in rows
                if (row.get("draft_payload") or {}).get("safe_to_upsert_without_review")
            ),
            "production_write_allowed_count": 0,
            "draft_status_counts": dict(sorted(draft_status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share manual-policy draft candidates",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Manual-policy tasks: `{summary['manual_policy_task_count']}`",
        f"- Draft Known review packets: `{summary['draft_known_count']}`",
        f"- Draft Unknown packets: `{summary['draft_unknown_count']}`",
        f"- Draft contracts valid: `{summary['draft_contract_valid_count']}`",
        f"- Draft contracts invalid: `{summary['draft_contract_invalid_count']}`",
        f"- Known drafts bridge-validated: `{summary['bridge_validated_known_count']}`",
        f"- Review required: `{summary['review_required_count']}`",
        f"- Safe to upsert without review: `{summary['safe_to_upsert_without_review_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Draft Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["draft_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | target | draft status | data status | contract | bridge | confidence | value |",
            "|---|---|---|---|---:|---:|---:|---|",
        ]
    )
    for row in report["rows"]:
        payload = row["draft_payload"]
        bridge = row["bridge_validation"]
        contract = row["contract_validation"]
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['score_target']}` | "
            f"`{row['draft_status']}` | "
            f"`{payload['data_status']}` | "
            f"{'yes' if contract.get('contract_valid') else 'no'} | "
            f"{'yes' if bridge.get('final_score_target_ready') else '-'} | "
            f"{payload['confidence']} | "
            f"`{json.dumps(payload['value_json'], ensure_ascii=False, sort_keys=True)}` |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This pilot generates review-only candidate values for manual-policy tasks that can be bounded from existing dependency evidence.",
            "- `L6.mult.dcf` now emits an explicit standard-assumption DCF draft; it remains review-only until approved.",
            "- Known drafts validate only payload shape and bridge reachability; they are not approved production inputs.",
            "- Production score-affecting writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-path", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.queue_path, args.candidate_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
