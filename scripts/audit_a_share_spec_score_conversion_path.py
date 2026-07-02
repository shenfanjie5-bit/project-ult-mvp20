#!/usr/bin/env python3
"""Audit whether A-share spec fields can become numeric score inputs.

This audit is deliberately read-only. It does not scan DOCKCASE and does not
write runtime state. It combines current audit artifacts with the production
normalization/scoring code path:

field closure / candidate dry-run artifacts
-> governance score target and weighting
-> _realtime_signal numeric conversion
-> synthesize_realtime_nodes
-> score_company route probe

The report separates "already in the current final score" from "the existing
normalization and score route can accept a reviewed value".
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mvp20.aggregator import _realtime_signal, synthesize_realtime_nodes  # noqa: E402
from mvp20.field_governance import (  # noqa: E402
    DataPointGovernance,
    FieldGovernanceRegistry,
    load_default_governance,
)
from mvp20.scoring import score_company  # noqa: E402

AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_FIELD_CLOSURE_PATH = AUDIT_DIR / "a_share_score_field_closure_2026-06-19.json"
DEFAULT_DRY_RUN_PATH = AUDIT_DIR / "a_share_candidate_score_dry_run_2026-06-19.json"
DEFAULT_REVIEW_MANIFEST_PATH = AUDIT_DIR / "a_share_review_staging_manifest_2026-06-19.json"
DEFAULT_VALUE_CONTRACTS_PATH = AUDIT_DIR / "a_share_candidate_value_contracts_2026-06-19.json"
DEFAULT_FORMULA_POLICY_REVIEW_PATH = (
    AUDIT_DIR / "a_share_formula_policy_review_packets_2026-06-19.json"
)
DEFAULT_GOVERNANCE_SUPPRESSION_PATH = (
    AUDIT_DIR / "a_share_governance_suppression_verification_2026-06-19.json"
)
DEFAULT_OPTION_UNIVERSE_NA_PATH = (
    AUDIT_DIR / "a_share_option_universe_na_verification_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = AUDIT_DIR / "a_share_spec_score_conversion_path_2026-06-19.json"
DEFAULT_MD_OUTPUT = AUDIT_DIR / "a_share_spec_score_conversion_path_2026-06-19.md"

NON_FINAL_TARGETS = {
    "none",
    "audit_only",
    "display_only",
    "parent_score",
    "node_score",
}

ROLE_COMPONENT_NEUTRALS = {
    "expectation_gap": 0.0,
    "valuation_rerating": 0.0,
    "funding_score": 0.0,
    "sentiment_score": 0.0,
    "capital_sentiment": 0.0,
    "risk_discount": 0.0,
    "valuation_pressure": 0.0,
    "priced_in_discount": 0.0,
    "funding_multiplier": 1.0,
    "theme_multiplier": 1.0,
    "policy_sensitivity_multiplier": 1.0,
    "market_regime_multiplier": 1.0,
    "reflexivity_multiplier": 1.0,
    "liquidity_multiplier": 1.0,
    "valuation_sensitivity_multiplier": 1.0,
    "multiplier_stack": 1.0,
    "confidence_multiplier": 1.0,
}

READY_CONVERSION_STATUSES = {
    "current_numeric_final_score",
    "candidate_numeric_score_path_ready",
    "sample_numeric_score_path_ready",
}

def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _rows_by_dp(payload: Mapping[str, Any], key: str = "rows") -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in payload.get(key) or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            out[dp_id] = row
    return out


def _summary_int(payload: Mapping[str, Any], key: str) -> int:
    try:
        return int((payload.get("summary") or {}).get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, set):
        return [_json_safe(v) for v in sorted(value, key=str)]
    return value


def _path_input(path: Path | None) -> str | None:
    return _portable_path(path) if path is not None else None


def _rule_for_row(
    registry: FieldGovernanceRegistry | None,
    row: Mapping[str, Any],
) -> DataPointGovernance | None:
    dp_id = str(row.get("dp_id") or "")
    rule = registry.get(dp_id) if registry is not None else None
    if rule is not None:
        return rule
    if not dp_id:
        return None
    return DataPointGovernance.from_mapping(
        dp_id,
        {
            "field_role": row.get("field_role") or "raw_input",
            "score_target": row.get("score_target") or "none",
            "calculation_type": row.get("calculation_type") or "raw_value",
            "aggregation_policy": row.get("aggregation_policy") or "none",
            "participates_in_score": bool(row.get("participates_in_score")),
            "source_status": row.get("source_status"),
        },
    )


def _is_final_score_target(rule: DataPointGovernance | None) -> bool:
    return bool(
        rule
        and rule.participates_in_score
        and rule.score_target not in NON_FINAL_TARGETS
    )


def _sample_entry(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    samples = row.get("sample_values") or []
    for sample in samples:
        if isinstance(sample, Mapping) and "value" in sample:
            return sample
    return None


def _bridge_probe(
    *,
    dp_id: str,
    value: Any,
    data_status: str,
    source: str,
    confidence: float,
    score_target: str | None,
    registry: FieldGovernanceRegistry | None,
    sample_ts_code: str,
) -> dict[str, Any]:
    signal = _realtime_signal(dp_id, value, score_target, ts_code=sample_ts_code)
    entry = {
        "value": value,
        "data_status": data_status,
        "confidence": confidence,
        "source": source,
        "updated_at": 1_800_000_000,
    }
    nodes = synthesize_realtime_nodes(
        {dp_id: entry},
        registry,
        existing_dp_ids=set(),
        ts_code=sample_ts_code,
    )
    node = nodes[0] if nodes else None
    return {
        "signal": signal,
        "signal_ready": signal is not None,
        "node_emitted": node is not None,
        "node_score": (node.get("value") or {}).get("score") if node else None,
        "node_direction": node.get("direction") if node else None,
    }


def _score_route_probe(
    *,
    rule: DataPointGovernance | None,
    sample_ts_code: str,
) -> dict[str, Any]:
    if rule is None:
        return {
            "final_score_route_ready": False,
            "reason": "missing_governance",
        }
    if not rule.participates_in_score:
        return {
            "final_score_route_ready": False,
            "reason": "governance_participates_in_score_false",
        }
    if rule.score_target in NON_FINAL_TARGETS:
        return {
            "final_score_route_ready": False,
            "reason": f"non_final_score_target:{rule.score_target}",
        }

    node_id = f"{sample_ts_code}:{rule.dp_id}:conversion_probe:rt"
    probe_score = 0.2
    if rule.score_target == "confidence_multiplier":
        probe_score = 0.0
    flat_node = {
        "node_id": node_id,
        "dp_id": rule.dp_id,
        "score": probe_score,
        "short_score": probe_score,
        "medium_score": probe_score,
        "long_score": probe_score,
        "confidence": 0.7,
        "score_target": rule.score_target,
        "field_role": rule.field_role,
        "participates_in_score": rule.participates_in_score,
        "synthetic_realtime": True,
    }
    try:
        scored = score_company(
            {"ts_code": sample_ts_code, "industry_id": "AUDIT", "nodes": []},
            {node_id: flat_node},
        )
    except Exception as exc:  # pragma: no cover - defensive audit payload
        return {
            "final_score_route_ready": False,
            "reason": f"score_company_error:{type(exc).__name__}",
        }

    role_components = scored.get("role_components") or {}
    final_score = scored.get("final_score") or {}
    components = final_score.get("components") or {}
    changed_role_components = {
        key: value
        for key, value in role_components.items()
        if abs(_safe_float(value, ROLE_COMPONENT_NEUTRALS.get(key, 0.0))
               - ROLE_COMPONENT_NEUTRALS.get(key, 0.0)) > 1e-12
    }
    base_score = _safe_float(final_score.get("base_score"), 0.0)
    component_non_neutral = any(
        abs(_safe_float(components.get(key), 0.0)) > 1e-12
        for key in (
            "fundamental",
            "expectation_gap",
            "valuation_rerating",
            "capital_sentiment",
            "risk",
            "priced_in",
        )
    )
    confidence_changed = (
        abs(_safe_float(components.get("confidence_multiplier"), 1.0) - 1.0)
        > 1e-12
    )
    return {
        "final_score_route_ready": True,
        "reason": "score_company_route_available",
        "base_score_probe": round(base_score, 6),
        "base_score_changed": abs(base_score) > 1e-12,
        "component_changed": component_non_neutral or confidence_changed,
        "changed_role_components": _json_safe(changed_role_components),
    }


def _conversion_status(
    *,
    score_relevant: bool,
    current_final_score_numeric: bool,
    candidate_ready: bool,
    sample_ready: bool,
    route_ready: bool,
    row: Mapping[str, Any],
) -> str:
    if not score_relevant:
        return "no_weight_or_non_scoring"
    if current_final_score_numeric:
        return "current_numeric_final_score"
    if candidate_ready and route_ready:
        return "candidate_numeric_score_path_ready"
    if sample_ready and route_ready:
        return "sample_numeric_score_path_ready"
    if row.get("runtime_valid_real_ts_count"):
        return "not_numeric_no_formula_or_normalizer"
    if row.get("runtime_numeric_signal_ts_count") and not row.get("effective_score_path_ts_count"):
        return "numeric_but_not_entering_final_score"
    return "no_current_numeric_input"


def _review_decision_status(
    *,
    conversion_status: str,
    formula_policy_review_required: bool,
    governance_suppression_verified: bool,
    option_universe_na_verified: bool,
) -> str | None:
    if conversion_status in READY_CONVERSION_STATUSES or conversion_status == "no_weight_or_non_scoring":
        return None
    if formula_policy_review_required:
        return "formula_policy_review_required"
    if governance_suppression_verified:
        return "governance_suppression_verified"
    if option_universe_na_verified:
        return "option_universe_na_verified"
    return None


def build_report(
    *,
    field_closure_path: Path,
    dry_run_path: Path,
    review_manifest_path: Path,
    value_contracts_path: Path,
    formula_policy_review_path: Path | None = None,
    governance_suppression_path: Path | None = None,
    option_universe_na_path: Path | None = None,
    sample_ts_code: str = "000001.SZ",
    registry: FieldGovernanceRegistry | None = None,
) -> dict[str, Any]:
    field_closure = _load_json(field_closure_path)
    dry_run = _load_json(dry_run_path)
    review_manifest = _load_json(review_manifest_path)
    value_contracts = _load_json(value_contracts_path)
    formula_policy_review = (
        _load_json(formula_policy_review_path)
        if formula_policy_review_path is not None and formula_policy_review_path.exists()
        else {}
    )
    governance_suppression = (
        _load_json(governance_suppression_path)
        if governance_suppression_path is not None and governance_suppression_path.exists()
        else {}
    )
    option_universe_na = (
        _load_json(option_universe_na_path)
        if option_universe_na_path is not None and option_universe_na_path.exists()
        else {}
    )
    if registry is None:
        registry = load_default_governance(strict=False)

    dry_by_dp = _rows_by_dp(dry_run)
    review_by_dp = _rows_by_dp(review_manifest)
    value_contracts_by_dp = _rows_by_dp(value_contracts)
    formula_by_dp = _rows_by_dp(formula_policy_review)
    governance_by_dp = _rows_by_dp(governance_suppression)
    option_by_dp = _rows_by_dp(option_universe_na)

    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    review_status_counts: Counter[str] = Counter()
    target_counts: Counter[str] = Counter()
    calculation_counts: Counter[str] = Counter()

    for field in field_closure.get("rows") or []:
        if not isinstance(field, Mapping):
            continue
        dp_id = str(field.get("dp_id") or "")
        rule = _rule_for_row(registry, field)
        score_target = str(rule.score_target if rule else field.get("score_target") or "none")
        score_relevant = _is_final_score_target(rule)
        current_final_score_numeric = (
            field.get("closure_status") == "closed_reaches_final_score"
            and score_relevant
        )
        route_probe = _score_route_probe(rule=rule, sample_ts_code=sample_ts_code)

        dry_row = dry_by_dp.get(dp_id)
        candidate_probe = None
        if dry_row and "bridge_payload" in dry_row:
            candidate_probe = _bridge_probe(
                dp_id=dp_id,
                value=dry_row.get("bridge_payload"),
                data_status=str(dry_row.get("bridge_payload_status") or "Known"),
                source="candidate:score_conversion_path_audit",
                confidence=0.7,
                score_target=score_target,
                registry=registry,
                sample_ts_code=sample_ts_code,
            )

        sample = _sample_entry(field)
        sample_probe = None
        if sample is not None:
            sample_probe = _bridge_probe(
                dp_id=dp_id,
                value=sample.get("value"),
                data_status=str(sample.get("status") or "Known"),
                source=str(sample.get("source") or "sample:audit"),
                confidence=0.7,
                score_target=score_target,
                registry=registry,
                sample_ts_code=str(sample.get("ts_code") or sample_ts_code),
            )

        candidate_ready = bool(
            candidate_probe
            and candidate_probe["signal_ready"]
            and candidate_probe["node_emitted"]
        )
        sample_ready = bool(
            sample_probe
            and sample_probe["signal_ready"]
            and sample_probe["node_emitted"]
        )
        route_ready = bool(route_probe.get("final_score_route_ready"))
        formula_row = formula_by_dp.get(dp_id)
        governance_row = governance_by_dp.get(dp_id)
        option_row = option_by_dp.get(dp_id)
        formula_policy_review_required = bool(
            formula_row
            and formula_row.get("policy_contract_valid")
            and formula_row.get("policy_review_status")
            == "formula_policy_review_required"
            and formula_row.get("direct_formula_ready") is False
            and formula_row.get("production_write_allowed") is False
        )
        governance_suppression_verified = bool(
            governance_row
            and governance_row.get("suppression_verified")
            and governance_row.get("production_write_allowed") is False
        )
        option_universe_na_verified = bool(
            option_row
            and option_row.get("verification_contract_valid")
            and option_row.get("source_universe_required")
            and option_row.get("known_value_allowed_now") is False
            and option_row.get("production_write_allowed") is False
        )
        status = _conversion_status(
            score_relevant=score_relevant,
            current_final_score_numeric=current_final_score_numeric,
            candidate_ready=candidate_ready,
            sample_ready=sample_ready,
            route_ready=route_ready,
            row=field,
        )
        review_decision_status = _review_decision_status(
            conversion_status=status,
            formula_policy_review_required=formula_policy_review_required,
            governance_suppression_verified=governance_suppression_verified,
            option_universe_na_verified=option_universe_na_verified,
        )
        status_counts[status] += 1
        if review_decision_status:
            review_status_counts[review_decision_status] += 1
        target_counts[score_target] += 1
        calculation_counts[str(rule.calculation_type if rule else field.get("calculation_type") or "none")] += 1

        review_row = review_by_dp.get(dp_id)
        value_contract_row = value_contracts_by_dp.get(dp_id)
        rows.append(
            {
                "dp_id": dp_id,
                "field_role": rule.field_role if rule else field.get("field_role"),
                "score_target": score_target,
                "calculation_type": rule.calculation_type if rule else field.get("calculation_type"),
                "aggregation_policy": rule.aggregation_policy if rule else field.get("aggregation_policy"),
                "participates_in_score": bool(rule.participates_in_score if rule else field.get("participates_in_score")),
                "score_relevant_final_target": score_relevant,
                "closure_status": field.get("closure_status"),
                "conversion_path_status": status,
                "review_decision_status": review_decision_status,
                "current_final_score_numeric": current_final_score_numeric,
                "candidate_bridge_signal_ready": bool(candidate_probe and candidate_probe["signal_ready"]),
                "candidate_node_emitted": bool(candidate_probe and candidate_probe["node_emitted"]),
                "candidate_final_score_target_ready_from_artifact": bool(
                    dry_row and dry_row.get("final_score_target_ready")
                ),
                "sample_bridge_signal_ready": bool(sample_probe and sample_probe["signal_ready"]),
                "sample_node_emitted": bool(sample_probe and sample_probe["node_emitted"]),
                "score_company_route_ready": route_ready,
                "score_company_route_probe": route_probe,
                "candidate_probe": candidate_probe,
                "sample_probe": sample_probe,
                "review_entry_status": review_row.get("review_entry_status") if review_row else None,
                "bridge_ready_concrete": bool(review_row and review_row.get("bridge_ready_concrete")),
                "contract_valid": bool(value_contract_row and value_contract_row.get("contract_valid")),
                "formula_policy_review_required": formula_policy_review_required,
                "formula_policy_packet_id": formula_row.get("packet_id") if formula_row else None,
                "formula_policy_family": formula_row.get("policy_family") if formula_row else None,
                "formula_policy_contract_valid": bool(
                    formula_row and formula_row.get("policy_contract_valid")
                ),
                "formula_direct_formula_ready": bool(
                    formula_row and formula_row.get("direct_formula_ready")
                ),
                "governance_suppression_verified": governance_suppression_verified,
                "governance_intent_subtype": governance_row.get("intent_subtype") if governance_row else None,
                "governance_verification_status": governance_row.get("verification_status") if governance_row else None,
                "option_universe_na_verified": option_universe_na_verified,
                "option_source_universe_required": bool(
                    option_row and option_row.get("source_universe_required")
                ),
                "option_na_or_unavailable_allowed_after_review": bool(
                    option_row
                    and option_row.get("na_or_unavailable_allowed_after_review")
                ),
                "safe_to_upsert_without_review": bool(
                    review_row and review_row.get("safe_to_upsert_without_review")
                ),
                "production_write_allowed": bool(
                    review_row and review_row.get("production_write_allowed")
                ),
                "runtime_valid_real_ts_count": int(field.get("runtime_valid_real_ts_count") or 0),
                "runtime_numeric_signal_ts_count": int(field.get("runtime_numeric_signal_ts_count") or 0),
                "effective_score_path_ts_count": int(field.get("effective_score_path_ts_count") or 0),
            }
        )

    total_checked = len(rows)
    score_relevant_count = sum(1 for row in rows if row["score_relevant_final_target"])
    current_numeric_count = sum(1 for row in rows if row["current_final_score_numeric"])
    candidate_ready_count = sum(
        1
        for row in rows
        if row["conversion_path_status"] == "candidate_numeric_score_path_ready"
    )
    sample_ready_count = sum(
        1
        for row in rows
        if row["conversion_path_status"] == "sample_numeric_score_path_ready"
    )
    numeric_and_score_ready_count = sum(
        1
        for row in rows
        if row["conversion_path_status"] in READY_CONVERSION_STATUSES
    )
    unresolved_score_relevant_count = sum(
        1
        for row in rows
        if row["score_relevant_final_target"]
        and row["conversion_path_status"] not in READY_CONVERSION_STATUSES
    )
    remaining_unclassified_conversion_gap_count = sum(
        1
        for row in rows
        if row["score_relevant_final_target"]
        and row["conversion_path_status"] not in READY_CONVERSION_STATUSES
        and not row["review_decision_status"]
    )
    formula_policy_required_count = review_status_counts["formula_policy_review_required"]
    governance_verified_count = review_status_counts["governance_suppression_verified"]
    option_verified_count = review_status_counts["option_universe_na_verified"]
    no_weight_count = status_counts["no_weight_or_non_scoring"]
    not_numeric_or_no_formula_count = status_counts["not_numeric_no_formula_or_normalizer"]
    no_current_numeric_input_count = status_counts["no_current_numeric_input"]
    numeric_but_not_final_count = status_counts["numeric_but_not_entering_final_score"]
    not_entering_final_score_count = total_checked - numeric_and_score_ready_count

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "field_closure_path": _portable_path(field_closure_path),
            "dry_run_path": _portable_path(dry_run_path),
            "review_manifest_path": _portable_path(review_manifest_path),
            "value_contracts_path": _portable_path(value_contracts_path),
            "formula_policy_review_path": _path_input(formula_policy_review_path),
            "governance_suppression_path": _path_input(governance_suppression_path),
            "option_universe_na_path": _path_input(option_universe_na_path),
            "sample_ts_code": sample_ts_code,
            "dockcase_scan": "not_performed",
        },
        "summary": {
            "total_checked_count": total_checked,
            "configured_spec_total_dp_ids": int(
                (field_closure.get("summary") or {}).get("configured_spec_total_dp_ids")
                or total_checked
            ),
            "score_relevant_final_target_count": score_relevant_count,
            "current_numeric_final_score_count": current_numeric_count,
            "candidate_numeric_score_path_ready_count": candidate_ready_count,
            "sample_numeric_score_path_ready_count": sample_ready_count,
            "numeric_and_score_path_ready_count": numeric_and_score_ready_count,
            "unresolved_score_relevant_count": unresolved_score_relevant_count,
            "formula_policy_review_required_count": formula_policy_required_count,
            "governance_suppression_verified_count": governance_verified_count,
            "option_universe_na_verified_count": option_verified_count,
            "verified_non_numeric_exception_count": (
                governance_verified_count + option_verified_count
            ),
            "review_decision_backed_not_ready_count": (
                formula_policy_required_count
                + governance_verified_count
                + option_verified_count
            ),
            "remaining_unclassified_conversion_gap_count": (
                remaining_unclassified_conversion_gap_count
            ),
            "not_numeric_or_no_formula_count": not_numeric_or_no_formula_count,
            "no_current_numeric_input_count": no_current_numeric_input_count,
            "no_weight_or_non_scoring_count": no_weight_count,
            "numeric_but_not_entering_final_score_count": numeric_but_not_final_count,
            "not_entering_final_score_count": not_entering_final_score_count,
            "candidate_dry_run_bridge_ready_artifact_count": _summary_int(
                dry_run, "bridge_signal_ready_count"
            ),
            "candidate_dry_run_final_score_target_ready_artifact_count": _summary_int(
                dry_run, "final_score_target_ready_count"
            ),
            "review_ready_concrete_count": _summary_int(
                review_manifest, "bridge_ready_concrete_count"
            ),
            "review_gated_unknown_count": _summary_int(
                review_manifest, "review_gated_unknown_count"
            ),
            "formula_policy_packet_artifact_count": _summary_int(
                formula_policy_review, "formula_policy_packet_count"
            ),
            "governance_suppression_artifact_verified_count": _summary_int(
                governance_suppression, "suppression_verified_count"
            ),
            "option_universe_na_artifact_valid_count": _summary_int(
                option_universe_na, "verification_contract_valid_count"
            ),
            "safe_to_upsert_without_review_count": sum(
                1 for row in rows if row["safe_to_upsert_without_review"]
            ),
            "production_write_allowed_count": sum(
                1 for row in rows if row["production_write_allowed"]
            ),
            "conversion_path_status_counts": dict(sorted(status_counts.items())),
            "review_decision_status_counts": dict(sorted(review_status_counts.items())),
            "score_target_counts": dict(sorted(target_counts.items())),
            "calculation_type_counts": dict(sorted(calculation_counts.items())),
            "score_mutation": "none; this audit is read-only",
        },
        "blocked_score_relevant_rows": [
            row
            for row in rows
            if row["score_relevant_final_target"]
            and row["conversion_path_status"] not in READY_CONVERSION_STATUSES
        ],
        "rows": _json_safe(rows),
    }


def _md_table_row(values: list[Any]) -> str:
    return "| " + " | ".join(str(v) for v in values) + " |"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share spec score conversion-path audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        f"- DOCKCASE scan: `{report['inputs']['dockcase_scan']}`",
        f"- Total checked: `{summary['total_checked_count']}`",
        f"- Score-relevant final targets: `{summary['score_relevant_final_target_count']}`",
        f"- Current numeric final-score fields: `{summary['current_numeric_final_score_count']}`",
        f"- Candidate numeric score-path ready fields: `{summary['candidate_numeric_score_path_ready_count']}`",
        f"- Numeric and score-path ready fields: `{summary['numeric_and_score_path_ready_count']}`",
        f"- Unresolved score-relevant fields: `{summary['unresolved_score_relevant_count']}`",
        f"- Formula-policy review required fields: `{summary['formula_policy_review_required_count']}`",
        f"- Governance suppression verified fields: `{summary['governance_suppression_verified_count']}`",
        f"- Option-universe / N/A verified fields: `{summary['option_universe_na_verified_count']}`",
        f"- Review-decision backed not-ready fields: `{summary['review_decision_backed_not_ready_count']}`",
        f"- Remaining unclassified conversion gaps: `{summary['remaining_unclassified_conversion_gap_count']}`",
        f"- Not numeric / no formula or normalizer: `{summary['not_numeric_or_no_formula_count']}`",
        f"- No current numeric input: `{summary['no_current_numeric_input_count']}`",
        f"- No weight or non-scoring: `{summary['no_weight_or_non_scoring_count']}`",
        f"- Not entering final score: `{summary['not_entering_final_score_count']}`",
        "",
        "## Conversion Status",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["conversion_path_status_counts"].items():
        lines.append(_md_table_row([f"`{status}`", count]))

    lines.extend(
        [
            "",
            "## Blocked Score-Relevant Rows",
            "",
            "| dp_id | target | status | closure | review evidence | runtime valid | runtime numeric |",
            "|---|---|---|---|---|---:|---:|",
        ]
    )
    for row in report.get("blocked_score_relevant_rows") or []:
        review_evidence = ""
        if row.get("formula_policy_review_required"):
            review_evidence = row.get("formula_policy_family") or "formula_policy"
        elif row.get("governance_suppression_verified"):
            review_evidence = row.get("governance_verification_status") or "governance"
        elif row.get("option_universe_na_verified"):
            review_evidence = "listed_option_universe_or_na"
        lines.append(
            _md_table_row(
                [
                    f"`{row['dp_id']}`",
                    f"`{row['score_target']}`",
                    f"`{row['conversion_path_status']}`",
                    f"`{row['closure_status']}`",
                    f"`{review_evidence}`" if review_evidence else "",
                    row["runtime_valid_real_ts_count"],
                    row["runtime_numeric_signal_ts_count"],
                ]
            )
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `current_numeric_final_score` means the field already has current A-share evidence reaching the final-score path.",
            "- `candidate_numeric_score_path_ready` means a dry-run candidate payload can be normalized, emitted as a realtime node, and routed by `score_company`; it is not a production write.",
            "- `formula_policy_review_required` means real current inputs exist and the score route is available, but a direct formula needs explicit reviewed policy before runtime writing.",
            "- `governance_suppression_verified` means the non-numeric field is intentionally suppressed, duplicated, data-only, or replaced by another scored path.",
            "- `option_universe_na_verified` means A-share option/IV fields have no current legitimate listed-option source and may only remain Unknown/Unavailable or become reviewed N/A.",
            "- `not_numeric_no_formula_or_normalizer` means current real runtime values exist, but `_realtime_signal` has no formula/normalizer for that payload shape.",
            "- `no_weight_or_non_scoring` means governance does not route the field into a final score target.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--field-closure-path", type=Path, default=DEFAULT_FIELD_CLOSURE_PATH)
    parser.add_argument("--dry-run-path", type=Path, default=DEFAULT_DRY_RUN_PATH)
    parser.add_argument("--review-manifest-path", type=Path, default=DEFAULT_REVIEW_MANIFEST_PATH)
    parser.add_argument("--value-contracts-path", type=Path, default=DEFAULT_VALUE_CONTRACTS_PATH)
    parser.add_argument(
        "--formula-policy-review-path",
        type=Path,
        default=DEFAULT_FORMULA_POLICY_REVIEW_PATH,
    )
    parser.add_argument(
        "--governance-suppression-path",
        type=Path,
        default=DEFAULT_GOVERNANCE_SUPPRESSION_PATH,
    )
    parser.add_argument(
        "--option-universe-na-path",
        type=Path,
        default=DEFAULT_OPTION_UNIVERSE_NA_PATH,
    )
    parser.add_argument("--sample-ts-code", default="000001.SZ")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        field_closure_path=args.field_closure_path,
        dry_run_path=args.dry_run_path,
        review_manifest_path=args.review_manifest_path,
        value_contracts_path=args.value_contracts_path,
        formula_policy_review_path=args.formula_policy_review_path,
        governance_suppression_path=args.governance_suppression_path,
        option_universe_na_path=args.option_universe_na_path,
        sample_ts_code=args.sample_ts_code,
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
