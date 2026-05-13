from __future__ import annotations

from pathlib import Path

import yaml

from mvp20.field_governance import (
    FIELD_ROLES,
    SPEC_TOTAL_DP_IDS,
    load_field_governance,
    parse_spec_dp_ids,
)


ROOT = Path(__file__).resolve().parents[1]


def test_data_point_roles_cover_all_250_spec_ids() -> None:
    spec_ids = parse_spec_dp_ids(ROOT / "docs/data_sources/coverage_audit.md")
    registry = load_field_governance(strict=True)

    assert len(spec_ids) == SPEC_TOTAL_DP_IDS
    assert set(registry.rules) == spec_ids


def test_governance_roles_and_policies_are_valid() -> None:
    registry = load_field_governance(strict=True)
    errors, warnings = registry.validate_against_spec(
        parse_spec_dp_ids(ROOT / "docs/data_sources/coverage_audit.md")
    )

    assert errors == []
    assert warnings == []


def test_raw_input_does_not_directly_participate_in_final_score() -> None:
    registry = load_field_governance(strict=True)
    raw_rules = [rule for rule in registry.rules.values() if rule.field_role == "raw_input"]

    assert raw_rules
    assert all(not rule.participates_in_score for rule in raw_rules)
    assert all(rule.score_target == "none" for rule in raw_rules)


def test_p0_semantic_calibration_for_reviewed_groups() -> None:
    registry = load_field_governance(strict=True)

    assert registry.get("L0.sentiment.sector_heat").score_target == "theme_multiplier"
    assert registry.get("L0.sentiment.social").score_target == "sentiment_score"
    assert registry.get("L7.flow.active_inflow").score_target == "funding_score"
    assert registry.get("L7.mood.theme").score_target == "theme_multiplier"
    assert registry.get("L6.priced.news_age").derived_target == "time_decay"
    assert registry.get("L6.sens.growth_margin").score_target == "valuation_sensitivity_multiplier"
    assert registry.get("L2.newbiz.uncertainty").score_target == "uncertainty_discount"
    policy_change = registry.get("L9.industry.policy_change")
    assert policy_change.field_role == "multiplier"
    assert policy_change.score_target == "policy_sensitivity_multiplier"
    assert policy_change.calculation_type == "multiplicative_factor"
    assert policy_change.neutral_value == 1.0

    multiplier_rules = [
        rule for rule in registry.rules.values() if rule.field_role == "multiplier"
    ]
    assert multiplier_rules
    assert all(rule.neutral_value == 1.0 for rule in multiplier_rules)


def test_schema_field_roles_use_fixed_14_role_set() -> None:
    payload = yaml.safe_load(
        (ROOT / "config/schema_field_roles.yaml").read_text(encoding="utf-8")
    )

    assert set(payload["field_roles"]) == FIELD_ROLES
    assert "theme_multiplier" in payload["score_targets"]
    assert "policy_sensitivity_multiplier" in payload["score_targets"]
    assert "time_decay" in payload["derived_targets"]
    assert payload["schema_fields"]["node_id"]["field_role"] == "identity"
    assert payload["schema_fields"]["confidence"]["field_role"] == "confidence"


def test_registry_enriches_node_without_overwriting_legacy_formula_fields() -> None:
    registry = load_field_governance(strict=True)
    node = {
        "node_id": "x:L5.is.gross_margin",
        "dp_id": "L5.is.gross_margin",
        "calculation_type": "weighted_contribution",
        "aggregation_policy": "weighted_sum",
        "missing_policy": "unknown_reduce_confidence",
    }

    enriched = registry.apply_to_node(node)

    assert enriched["field_role"] == "derived_metric"
    assert enriched["score_target"] == "fundamental_score"
    assert enriched["calculation_type"] == "weighted_contribution"
    assert enriched["governance_calculation_type"] == "ratio_metric"
    assert enriched["governance_aggregation_policy"] == "weighted_sum"
    assert enriched["governance_missing_policy"] == "unknown_reduce_confidence"
