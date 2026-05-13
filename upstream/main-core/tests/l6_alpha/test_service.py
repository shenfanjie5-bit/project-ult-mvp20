"""Tests for the L6 single-stock service entrypoint."""

from __future__ import annotations

from main_core.common.contexts import AlphaAnalysisContext
from main_core.common.schemas import FeatureSignalBundle, OfficialAlphaPool, WorldStateSnapshot
from main_core.l6_alpha import analyze_stock


def test_analyze_stock_uses_default_single_prompt_analyzer(
    analysis_context: AlphaAnalysisContext,
) -> None:
    result = analyze_stock("ENT_A", analysis_context)

    assert result.entity_id == "ENT_A"
    assert result.analyzer_type == "single_prompt_v1"
    assert result.status == "ok"


def test_analyze_stock_consumes_upstream_pool_world_state_and_feature_context() -> None:
    cycle_id = "cycle_l6_integration"
    feature_bundle = FeatureSignalBundle(
        cycle_id=cycle_id,
        entity_id="ENT_CORE",
        feature_values={"momentum": 6.0},
        signal_values={"signal": "positive"},
        graph_features={},
        feature_weight_multiplier={"momentum": 3.0},
    )
    world_state = WorldStateSnapshot(
        cycle_id=cycle_id,
        baseline_regime="neutral",
        llm_delta=1,
        final_regime="risk_on",
        llm_rationale="risk appetite improved",
        actual_model_used="fixture",
        actual_provider="local",
        fallback_path=[],
    )
    pool = OfficialAlphaPool(
        cycle_id=cycle_id,
        observation_pool_size=1,
        official_alpha_pool_capacity=100,
        selected_entities=["ENT_CORE"],
        added_entities=["ENT_CORE"],
        removed_entities=[],
        freeze_reason_map={},
    )
    context = AlphaAnalysisContext(
        cycle_id=cycle_id,
        entity_id=pool.selected_entities[0],
        feature_bundle=feature_bundle,
        world_state=world_state,
        similar_cases=[],
    )

    result = analyze_stock(pool.selected_entities[0], context)

    assert result.cycle_id == cycle_id
    assert result.entity_id == "ENT_CORE"
    assert result.analyzer_type == "single_prompt_v1"
