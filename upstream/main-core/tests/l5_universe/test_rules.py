"""Tests for deterministic L5 candidate ranking rules."""

from __future__ import annotations

from typing import Any

from main_core.common.schemas import FeatureSignalBundle, WorldStateSnapshot
from main_core.l5_universe import PoolSelectionConfig, rank_candidates, score_candidate

SIGNAL_SCORE = 1.5
ALPHA_SCORE = 2.5
MOMENTUM_SCORE = 3.5


def _world_state(cycle_id: str = "cycle_l5") -> WorldStateSnapshot:
    return WorldStateSnapshot(
        cycle_id=cycle_id,
        baseline_regime="neutral",
        llm_delta=0,
        final_regime="neutral",
        llm_rationale="fixture",
        actual_model_used="fixture",
        actual_provider="local",
        fallback_path=[],
    )


def _bundle(
    entity_id: str,
    *,
    cycle_id: str = "cycle_l5",
    feature_values: dict[str, float] | None = None,
    signal_values: dict[str, Any] | None = None,
    feature_weight_multiplier: dict[str, float] | None = None,
) -> FeatureSignalBundle:
    return FeatureSignalBundle(
        cycle_id=cycle_id,
        entity_id=entity_id,
        feature_values=feature_values or {},
        signal_values=signal_values or {},
        graph_features={},
        feature_weight_multiplier=feature_weight_multiplier or {},
    )


def test_score_candidate_uses_documented_precedence() -> None:
    world_state = _world_state()

    assert score_candidate(
        _bundle(
            "ENT_SIGNAL",
            feature_values={"alpha_score": 9.0, "momentum": 8.0},
            signal_values={"candidate_score": SIGNAL_SCORE},
        ),
        world_state,
    ) == SIGNAL_SCORE
    assert score_candidate(
        _bundle("ENT_ALPHA", feature_values={"alpha_score": ALPHA_SCORE, "momentum": 8.0}),
        world_state,
    ) == ALPHA_SCORE
    assert score_candidate(
        _bundle(
            "ENT_MOMENTUM",
            feature_values={"momentum": MOMENTUM_SCORE},
            feature_weight_multiplier={"momentum": 10.0},
        ),
        world_state,
    ) == MOMENTUM_SCORE
    assert score_candidate(_bundle("ENT_MISSING"), world_state) == 0.0


def test_rank_candidates_is_stable_with_entity_id_tie_break() -> None:
    world_state = _world_state()
    bundles = [
        _bundle("ENT_B", signal_values={"candidate_score": 2.0}),
        _bundle("ENT_A", signal_values={"candidate_score": 2.0}),
        _bundle("ENT_C", signal_values={"candidate_score": 3.0}),
    ]

    ranked_once = rank_candidates(world_state, bundles, PoolSelectionConfig(capacity=3))
    ranked_twice = rank_candidates(world_state, bundles, PoolSelectionConfig(capacity=3))

    assert [bundle.entity_id for bundle in ranked_once] == ["ENT_C", "ENT_A", "ENT_B"]
    assert ranked_once == ranked_twice


def test_rank_candidates_applies_score_threshold_before_observation_limit() -> None:
    world_state = _world_state()
    bundles = [
        _bundle("ENT_LOW", signal_values={"candidate_score": 0.5}),
        _bundle("ENT_MID", signal_values={"candidate_score": 1.5}),
        _bundle("ENT_HIGH", signal_values={"candidate_score": 2.5}),
    ]
    config = PoolSelectionConfig(
        capacity=3,
        observation_limit=1,
        min_candidate_score=1.0,
    )

    ranked = rank_candidates(world_state, bundles, config)

    assert [bundle.entity_id for bundle in ranked] == ["ENT_HIGH"]
