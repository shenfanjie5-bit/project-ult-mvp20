"""Tests for MVP20 fixed manifest target decision pool selection."""

from __future__ import annotations

import pytest

from main_core.common.errors import MainCoreError
from main_core.common.schemas import FeatureSignalBundle, WorldStateSnapshot
from main_core.l5_universe import (
    MVP20_DECISION_POOL_CAPACITY,
    MVP20DecisionPoolSpec,
    select_mvp20_decision_pool,
)


def _world_state(cycle_id: str = "cycle_mvp20") -> WorldStateSnapshot:
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
    score: float,
    *,
    cycle_id: str = "cycle_mvp20",
) -> FeatureSignalBundle:
    return FeatureSignalBundle(
        cycle_id=cycle_id,
        entity_id=entity_id,
        feature_values={"momentum": score},
        signal_values={"candidate_score": score},
        graph_features={},
        feature_weight_multiplier={"momentum": 1.0},
    )


def _manifest_targets() -> tuple[str, ...]:
    ordered_indexes = (5, 1, 4, 2, 3, *range(6, MVP20_DECISION_POOL_CAPACITY + 1))
    return tuple(f"ENT_T{index:02d}" for index in ordered_indexes)


def test_mvp20_spec_freezes_manifest_targets_in_manifest_order() -> None:
    manifest_targets = _manifest_targets()

    spec = MVP20DecisionPoolSpec.from_manifest_targets(manifest_targets)

    assert spec.manifest_targets == manifest_targets
    assert tuple(spec.frozen_entities()) == manifest_targets


def test_select_mvp20_decision_pool_uses_only_manifest_targets() -> None:
    manifest_targets = _manifest_targets()
    target_bundles = [
        _bundle(entity_id, float(index))
        for index, entity_id in enumerate(manifest_targets)
    ]
    related_bundles = [
        _bundle("ENT_RELATED_HIGH_A", 999.0),
        _bundle("ENT_RELATED_HIGH_B", 998.0),
    ]

    pool = select_mvp20_decision_pool(
        _world_state(),
        [*related_bundles, *target_bundles],
        manifest_targets,
    )

    assert pool.official_alpha_pool_capacity == MVP20_DECISION_POOL_CAPACITY
    assert pool.observation_pool_size == MVP20_DECISION_POOL_CAPACITY
    assert pool.selected_entities == manifest_targets
    assert tuple(pool.freeze_reason_map) == manifest_targets
    assert "ENT_RELATED_HIGH_A" not in pool.selected_entities
    assert "ENT_RELATED_HIGH_B" not in pool.selected_entities


@pytest.mark.parametrize("target_count", [19, 21])
def test_select_mvp20_decision_pool_requires_exactly_20_manifest_targets(
    target_count: int,
) -> None:
    manifest_targets = tuple(f"ENT_T{index:02d}" for index in range(1, target_count + 1))
    bundles = [
        _bundle(entity_id, float(index))
        for index, entity_id in enumerate(manifest_targets)
    ]

    with pytest.raises(MainCoreError, match="exactly 20"):
        select_mvp20_decision_pool(_world_state(), bundles, manifest_targets)


def test_select_mvp20_decision_pool_requires_current_bundle_for_each_target() -> None:
    manifest_targets = _manifest_targets()
    bundles = [
        _bundle(entity_id, float(index))
        for index, entity_id in enumerate(manifest_targets[:-1])
    ]

    with pytest.raises(MainCoreError, match="manifest_targets must be present"):
        select_mvp20_decision_pool(_world_state(), bundles, manifest_targets)
