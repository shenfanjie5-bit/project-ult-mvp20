"""Fixtures for L6 alpha analysis tests."""

from __future__ import annotations

import pytest

from main_core.common.contexts import AlphaAnalysisContext
from main_core.common.schemas import FeatureSignalBundle, WorldStateSnapshot


@pytest.fixture
def feature_bundle() -> FeatureSignalBundle:
    return FeatureSignalBundle(
        cycle_id="cycle_l6",
        entity_id="ENT_A",
        feature_values={"momentum": 4.2, "quality": 1.5},
        signal_values={"signal": "positive"},
        graph_features={"centrality": 0.3},
        feature_weight_multiplier={"momentum": 2.5, "quality": 1.0},
    )


@pytest.fixture
def world_state() -> WorldStateSnapshot:
    return WorldStateSnapshot(
        cycle_id="cycle_l6",
        baseline_regime="neutral",
        llm_delta=0,
        final_regime="neutral",
        llm_rationale="fixture",
        actual_model_used="fixture",
        actual_provider="local",
        fallback_path=[],
    )


@pytest.fixture
def analysis_context(
    feature_bundle: FeatureSignalBundle,
    world_state: WorldStateSnapshot,
) -> AlphaAnalysisContext:
    return AlphaAnalysisContext(
        cycle_id="cycle_l6",
        entity_id="ENT_A",
        feature_bundle=feature_bundle,
        world_state=world_state,
        similar_cases=[{"entity_id": "ENT_B", "score": 0.4}],
    )
