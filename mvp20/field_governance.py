"""Field-governance registry for data-point routing and missing balance.

This module intentionally keeps governance outside the SQLite schema. Rules
live in YAML and are copied into overlay node payloads/snapshots as metadata.
The scoring/aggregation layers can then use those metadata fields when they
exist, while older overlays continue to run with legacy inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import re

import yaml


SPEC_TOTAL_DP_IDS = 250

FIELD_ROLES = {
    "identity",
    "structure",
    "raw_input",
    "derived_metric",
    "score_component",
    "multiplier",
    "discount",
    "gate",
    "aggregation",
    "confidence",
    "missing_control",
    "evidence",
    "display",
    "audit",
}

NON_SCORING_ROLES = {
    "identity",
    "structure",
    "raw_input",
    "missing_control",
    "evidence",
    "display",
    "audit",
}

SCORE_TARGETS = {
    "none",
    "node_score",
    "base_score",
    "fundamental_score",
    "expectation_gap",
    "valuation_rerating",
    "capital_sentiment",
    "funding_score",
    "funding_multiplier",
    "theme_multiplier",
    "sentiment_score",
    "sentiment_multiplier",
    "policy_sensitivity_multiplier",
    "market_regime_multiplier",
    "reflexivity_multiplier",
    "liquidity_multiplier",
    "options_momentum_multiplier",
    "gamma_multiplier",
    "valuation_sensitivity_multiplier",
    "rate_sensitivity_multiplier",
    "narrative_sensitivity_multiplier",
    "multiplier_stack",
    "confidence_multiplier",
    "risk_discount",
    "priced_in_discount",
    "uncertainty_discount",
    "optionality_score",
    "event_impulse_score",
    "time_decay",
    "option_priced_in",
    "volatility_risk",
    "valuation_pressure",
    "overheat_risk",
    "parent_score",
    "audit_only",
    "display_only",
}

FALLBACK_POLICIES = {
    "none",
    "not_applicable_remove",
    "unknown_zero_score",
    "proxy_only",
    "proxy_then_neutral",
    "neutral_with_penalty",
    "inactive_zero_weight",
    "optionality_track",
}

MISSING_POLICIES = {
    "known",
    "not_applicable_remove",
    "unknown_reduce_confidence",
    "inactive_zero_weight",
    "low_materiality_fold",
    "optionality_track",
}

CALCULATION_TYPES = {
    "none",
    "raw_value",
    "additive",
    "subtractive",
    "multiplicative_factor",
    "ratio_metric",
    "weighted_contribution",
    "risk_factor",
    "confidence_multiplier",
    "bottleneck_min",
    "and_gate",
    "or_gate",
    "threshold",
    "saturation",
    "scenario_weighted",
    "time_decay",
    "bayesian_update",
    "dedup_correlation",
    "reflexivity",
    "dcf",
}

AGGREGATION_POLICIES = {
    "none",
    "add_uncertainty_penalty",
    "renormalize_siblings",
    "weighted_average",
    "weighted_sum",
    "multiply_chain",
    "subtract_risk",
    "ratio_derive",
    "multiplicative_factor",
    "confidence_adjusted",
    "min_capacity_constraint",
    "and_all_required",
    "or_max_trigger",
    "threshold_trigger",
    "saturation_curve",
    "scenario_probability_weighted",
    "time_decay_half_life",
    "bayesian_confidence_update",
    "deduplicate_correlated_inputs",
    "feedback_loop_limited",
    "discounted_cash_flow",
    "no_aggregation",
}

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_POINT_ROLES_PATH = ROOT_DIR / "config/data_point_roles.yaml"
DEFAULT_SCHEMA_FIELD_ROLES_PATH = ROOT_DIR / "config/schema_field_roles.yaml"
DEFAULT_COVERAGE_AUDIT_PATH = ROOT_DIR / "docs/data_sources/coverage_audit.md"


@dataclass(frozen=True)
class DataPointGovernance:
    dp_id: str
    field_role: str
    score_target: str
    calculation_type: str
    aggregation_policy: str
    missing_policy: str
    fallback_policy: str
    proxy_candidates: tuple[str, ...]
    min_required_coverage: float
    neutral_value: float
    confidence_penalty: float
    participates_in_score: bool
    derived_target: str = "none"
    source_status: str | None = None

    @classmethod
    def from_mapping(
        cls,
        dp_id: str,
        mapping: Mapping[str, Any],
        defaults: Mapping[str, Any] | None = None,
    ) -> "DataPointGovernance":
        defaults = defaults or {}
        merged = {**defaults, **dict(mapping)}
        role = str(merged.get("field_role") or "raw_input")
        target = str(merged.get("score_target") or "none")
        participates = bool(merged.get("participates_in_score", role not in NON_SCORING_ROLES))
        return cls(
            dp_id=dp_id,
            field_role=role,
            score_target=target,
            calculation_type=str(merged.get("calculation_type") or "raw_value"),
            aggregation_policy=str(merged.get("aggregation_policy") or "none"),
            missing_policy=str(merged.get("missing_policy") or "unknown_reduce_confidence"),
            fallback_policy=str(merged.get("fallback_policy") or "unknown_zero_score"),
            proxy_candidates=tuple(str(x) for x in (merged.get("proxy_candidates") or [])),
            min_required_coverage=_float(merged.get("min_required_coverage"), 0.5),
            neutral_value=_float(merged.get("neutral_value"), 0.0),
            confidence_penalty=_float(merged.get("confidence_penalty"), 1.0),
            participates_in_score=participates,
            derived_target=str(merged.get("derived_target") or target),
            source_status=(
                str(merged.get("source_status"))
                if merged.get("source_status") is not None
                else None
            ),
        )

    def as_overlay_fields(self) -> dict[str, Any]:
        return {
            "field_role": self.field_role,
            "score_target": self.score_target,
            "derived_target": self.derived_target,
            "participates_in_score": self.participates_in_score,
            "governance_calculation_type": self.calculation_type,
            "governance_aggregation_policy": self.aggregation_policy,
            "governance_missing_policy": self.missing_policy,
            "fallback_policy": self.fallback_policy,
            "proxy_candidates": list(self.proxy_candidates),
            "min_required_coverage": self.min_required_coverage,
            "neutral_value": self.neutral_value,
            "confidence_penalty": self.confidence_penalty,
            "governance_source_status": self.source_status,
        }


class FieldGovernanceRegistry:
    """In-memory lookup for dp_id and schema-field governance."""

    def __init__(
        self,
        rules: Mapping[str, DataPointGovernance],
        *,
        schema_fields: Mapping[str, Mapping[str, Any]] | None = None,
        schema_version: int | str | None = None,
        source: str | None = None,
    ) -> None:
        self.rules = dict(rules)
        self.schema_fields = {k: dict(v) for k, v in (schema_fields or {}).items()}
        self.schema_version = schema_version
        self.source = source

    def get(self, dp_id: str | None) -> DataPointGovernance | None:
        if not dp_id:
            return None
        return self.rules.get(str(dp_id))

    def apply_to_node(self, node: Mapping[str, Any], *, overwrite: bool = False) -> dict[str, Any]:
        """Return a node copy enriched with governance fields when dp_id matches."""

        out = dict(node)
        rule = self.get(out.get("dp_id"))
        if not rule:
            return out
        for key, value in rule.as_overlay_fields().items():
            if overwrite or key not in out or out.get(key) is None:
                out[key] = value
        if overwrite or not out.get("calculation_type"):
            out["calculation_type"] = rule.calculation_type
        if overwrite or not out.get("aggregation_policy"):
            out["aggregation_policy"] = rule.aggregation_policy
        if overwrite or not out.get("missing_policy"):
            out["missing_policy"] = rule.missing_policy
        return out

    def apply_to_overlay(
        self,
        payload: Mapping[str, Any],
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        out = dict(payload)
        nodes = []
        for node in payload.get("nodes") or []:
            if isinstance(node, Mapping):
                nodes.append(self.apply_to_node(node, overwrite=overwrite))
            else:
                nodes.append(node)
        out["nodes"] = nodes
        out["field_governance_version"] = self.schema_version
        out["field_governance_source"] = self.source
        return out

    def validate_against_spec(
        self,
        spec_dp_ids: set[str] | None = None,
        *,
        expected_total: int = SPEC_TOTAL_DP_IDS,
    ) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        if len(self.rules) != expected_total:
            errors.append(
                f"data_point_roles covers {len(self.rules)} dp_id(s), expected {expected_total}"
            )
        if spec_dp_ids is not None:
            missing = sorted(spec_dp_ids - set(self.rules))
            extra = sorted(set(self.rules) - spec_dp_ids)
            if missing:
                errors.append(f"data_point_roles missing {len(missing)} spec dp_id(s): {missing[:5]}")
            if extra:
                errors.append(f"data_point_roles has {len(extra)} non-spec dp_id(s): {extra[:5]}")

        for dp_id, rule in sorted(self.rules.items()):
            if rule.field_role not in FIELD_ROLES:
                errors.append(f"{dp_id}: invalid field_role {rule.field_role!r}")
            if rule.score_target not in SCORE_TARGETS:
                errors.append(f"{dp_id}: invalid score_target {rule.score_target!r}")
            if rule.derived_target not in SCORE_TARGETS:
                errors.append(f"{dp_id}: invalid derived_target {rule.derived_target!r}")
            if rule.fallback_policy not in FALLBACK_POLICIES:
                errors.append(f"{dp_id}: invalid fallback_policy {rule.fallback_policy!r}")
            if rule.missing_policy not in MISSING_POLICIES:
                errors.append(f"{dp_id}: invalid missing_policy {rule.missing_policy!r}")
            if rule.calculation_type not in CALCULATION_TYPES:
                errors.append(f"{dp_id}: invalid calculation_type {rule.calculation_type!r}")
            if rule.aggregation_policy not in AGGREGATION_POLICIES:
                errors.append(f"{dp_id}: invalid aggregation_policy {rule.aggregation_policy!r}")
            if not 0.0 <= rule.min_required_coverage <= 1.0:
                errors.append(f"{dp_id}: min_required_coverage must be 0..1")
            if not 0.0 <= rule.confidence_penalty <= 1.0:
                errors.append(f"{dp_id}: confidence_penalty must be 0..1")
            if rule.field_role == "raw_input" and (
                rule.participates_in_score or rule.score_target not in {"none", "audit_only"}
            ):
                errors.append(f"{dp_id}: raw_input may not directly participate in final score")
            if rule.field_role in NON_SCORING_ROLES and rule.participates_in_score:
                warnings.append(
                    f"{dp_id}: {rule.field_role} normally should not directly participate in score"
                )
        return errors, warnings


def parse_spec_dp_ids(path: Path = DEFAULT_COVERAGE_AUDIT_PATH) -> set[str]:
    """Parse Section 7 of the coverage audit and return the 250 spec dp_id set."""

    text = path.read_text(encoding="utf-8")
    in_section = False
    out: set[str] = set()
    for line in text.splitlines():
        if line.startswith("## 7."):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section:
            continue
        match = re.match(r"^\|\s*`([^`]+)`\s*\|", line)
        if match:
            out.add(match.group(1))
    return out


def load_field_governance(
    data_point_roles_path: Path = DEFAULT_DATA_POINT_ROLES_PATH,
    schema_field_roles_path: Path = DEFAULT_SCHEMA_FIELD_ROLES_PATH,
    coverage_audit_path: Path = DEFAULT_COVERAGE_AUDIT_PATH,
    *,
    strict: bool = True,
) -> FieldGovernanceRegistry:
    data = _load_yaml(data_point_roles_path)
    schema = _load_yaml(schema_field_roles_path) if schema_field_roles_path.exists() else {}
    defaults = data.get("defaults") or {}
    raw_rules = data.get("data_points") or {}
    rules = {
        str(dp_id): DataPointGovernance.from_mapping(str(dp_id), mapping, defaults)
        for dp_id, mapping in raw_rules.items()
        if isinstance(mapping, Mapping)
    }
    registry = FieldGovernanceRegistry(
        rules,
        schema_fields=schema.get("schema_fields") or {},
        schema_version=data.get("schema_version"),
        source=str(data.get("source") or data_point_roles_path),
    )
    spec_dp_ids = parse_spec_dp_ids(coverage_audit_path) if coverage_audit_path.exists() else None
    errors, _warnings = registry.validate_against_spec(spec_dp_ids)
    if strict and errors:
        raise ValueError("; ".join(errors))
    return registry


def load_default_governance(*, strict: bool = False) -> FieldGovernanceRegistry | None:
    if not DEFAULT_DATA_POINT_ROLES_PATH.exists():
        return None
    return load_field_governance(strict=strict)


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "AGGREGATION_POLICIES",
    "CALCULATION_TYPES",
    "FALLBACK_POLICIES",
    "FIELD_ROLES",
    "NON_SCORING_ROLES",
    "SCORE_TARGETS",
    "SPEC_TOTAL_DP_IDS",
    "DataPointGovernance",
    "FieldGovernanceRegistry",
    "load_default_governance",
    "load_field_governance",
    "parse_spec_dp_ids",
]
