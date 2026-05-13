"""Tests for L5 official alpha pool selection service."""

from __future__ import annotations

from typing import Any

import pytest

from main_core.common.errors import MainCoreError
from main_core.common.schemas import FeatureSignalBundle, OfficialAlphaPool, WorldStateSnapshot
from main_core.l5_universe import PoolSelectionConfig, select_official_alpha_pool
from main_core.l5_universe.types import MAX_OFFICIAL_ALPHA_POOL_CAPACITY

DEFAULT_OBSERVATION_SIZE = 3
THRESHOLDED_OBSERVATION_SIZE = 2
FROZEN_INCLUSIVE_OBSERVATION_SIZE = 2
TWO_ENTITY_CAPACITY = 2


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
    score: float,
    *,
    cycle_id: str = "cycle_l5",
    signal_values: dict[str, Any] | None = None,
) -> FeatureSignalBundle:
    return FeatureSignalBundle(
        cycle_id=cycle_id,
        entity_id=entity_id,
        feature_values={"momentum": score},
        signal_values=signal_values or {},
        graph_features={},
        feature_weight_multiplier={"momentum": 1.0},
    )


def _pool(
    *,
    selected_entities: list[str],
    freeze_reason_map: dict[str, str] | None = None,
) -> OfficialAlphaPool:
    return OfficialAlphaPool(
        cycle_id="cycle_l5",
        observation_pool_size=len(selected_entities),
        official_alpha_pool_capacity=100,
        selected_entities=selected_entities,
        added_entities=[],
        removed_entities=[],
        freeze_reason_map=freeze_reason_map or {},
    )


def test_select_official_alpha_pool_selects_ranked_candidates_with_capacity() -> None:
    pool = select_official_alpha_pool(
        _world_state(),
        [
            _bundle("ENT_A", 2.0),
            _bundle("ENT_B", 3.0),
            _bundle("ENT_C", 1.0),
        ],
        capacity=2,
    )

    assert pool.cycle_id == "cycle_l5"
    assert pool.observation_pool_size == DEFAULT_OBSERVATION_SIZE
    assert pool.official_alpha_pool_capacity == TWO_ENTITY_CAPACITY
    assert pool.selected_entities == ("ENT_B", "ENT_A")
    assert pool.added_entities == ("ENT_B", "ENT_A")
    assert pool.removed_entities == ()
    assert (
        len(pool.selected_entities)
        <= pool.official_alpha_pool_capacity
        <= MAX_OFFICIAL_ALPHA_POOL_CAPACITY
    )


def test_select_official_alpha_pool_records_thresholded_observation_pool_size() -> None:
    pool = select_official_alpha_pool(
        _world_state(),
        [
            _bundle("ENT_A", 3.0),
            _bundle("ENT_B", 2.0),
            _bundle("ENT_C", 0.5),
        ],
        config=PoolSelectionConfig(capacity=1, min_candidate_score=1.0),
    )

    assert pool.observation_pool_size == THRESHOLDED_OBSERVATION_SIZE
    assert pool.selected_entities == ("ENT_A",)


def test_select_official_alpha_pool_prioritizes_frozen_entities() -> None:
    previous_pool = _pool(
        selected_entities=["ENT_A", "ENT_C"],
        freeze_reason_map={"ENT_C": "existing core freeze"},
    )

    pool = select_official_alpha_pool(
        _world_state(),
        [
            _bundle("ENT_A", 10.0),
            _bundle("ENT_B", 9.0),
            _bundle("ENT_C", 0.0),
        ],
        previous_pool=previous_pool,
        capacity=2,
    )

    assert pool.selected_entities == ("ENT_C", "ENT_A")
    assert pool.added_entities == ()
    assert pool.removed_entities == ()
    assert pool.freeze_reason_map == {"ENT_C": "existing core freeze"}


def test_select_official_alpha_pool_carries_frozen_entities_outside_threshold() -> None:
    previous_pool = _pool(
        selected_entities=["ENT_C"],
        freeze_reason_map={"ENT_C": "existing core freeze"},
    )

    pool = select_official_alpha_pool(
        _world_state(),
        [
            _bundle("ENT_A", 10.0),
            _bundle("ENT_B", 0.5),
            _bundle("ENT_C", 0.0),
        ],
        previous_pool=previous_pool,
        config=PoolSelectionConfig(capacity=2, min_candidate_score=1.0),
    )

    assert pool.observation_pool_size == FROZEN_INCLUSIVE_OBSERVATION_SIZE
    assert pool.selected_entities == ("ENT_C", "ENT_A")
    assert pool.freeze_reason_map == {"ENT_C": "existing core freeze"}


def test_select_official_alpha_pool_counts_frozen_entities_outside_observation_limit() -> None:
    previous_pool = _pool(
        selected_entities=["ENT_C"],
        freeze_reason_map={"ENT_C": "existing core freeze"},
    )

    pool = select_official_alpha_pool(
        _world_state(),
        [
            _bundle("ENT_A", 10.0),
            _bundle("ENT_B", 9.0),
            _bundle("ENT_C", 0.0),
        ],
        previous_pool=previous_pool,
        config=PoolSelectionConfig(capacity=2, observation_limit=1),
    )

    assert pool.observation_pool_size == FROZEN_INCLUSIVE_OBSERVATION_SIZE
    assert pool.selected_entities == ("ENT_C", "ENT_A")
    assert pool.freeze_reason_map == {"ENT_C": "existing core freeze"}


def test_select_official_alpha_pool_merges_explicit_frozen_entities() -> None:
    pool = select_official_alpha_pool(
        _world_state(),
        [
            _bundle("ENT_A", 10.0),
            _bundle("ENT_B", 9.0),
        ],
        capacity=2,
        frozen_entities={"ENT_B": "manual freeze"},
    )

    assert pool.selected_entities == ("ENT_B", "ENT_A")
    assert pool.freeze_reason_map == {"ENT_B": "manual freeze"}


def test_select_official_alpha_pool_computes_added_and_removed_entities() -> None:
    previous_pool = _pool(selected_entities=["ENT_A", "ENT_C"])

    pool = select_official_alpha_pool(
        _world_state(),
        [
            _bundle("ENT_A", 2.0),
            _bundle("ENT_B", 3.0),
            _bundle("ENT_C", 1.0),
        ],
        previous_pool=previous_pool,
        capacity=2,
    )

    assert pool.selected_entities == ("ENT_B", "ENT_A")
    assert pool.added_entities == ("ENT_B",)
    assert pool.removed_entities == ("ENT_C",)


def test_select_official_alpha_pool_rejects_too_many_frozen_entities() -> None:
    previous_pool = _pool(
        selected_entities=["ENT_A", "ENT_B"],
        freeze_reason_map={
            "ENT_A": "freeze A",
            "ENT_B": "freeze B",
        },
    )

    with pytest.raises(MainCoreError, match="frozen entity count"):
        select_official_alpha_pool(
            _world_state(),
            [
                _bundle("ENT_A", 2.0),
                _bundle("ENT_B", 3.0),
            ],
            previous_pool=previous_pool,
            capacity=1,
        )


def test_select_official_alpha_pool_rejects_stale_previous_pool_freeze() -> None:
    previous_pool = _pool(
        selected_entities=["ENT_STALE"],
        freeze_reason_map={"ENT_STALE": "stale core freeze"},
    )

    with pytest.raises(MainCoreError, match="frozen entities must be present"):
        select_official_alpha_pool(
            _world_state(),
            [_bundle("ENT_A", 2.0)],
            previous_pool=previous_pool,
            capacity=2,
        )


def test_select_official_alpha_pool_rejects_explicit_frozen_entity_without_bundle() -> None:
    with pytest.raises(MainCoreError, match="frozen entities must be present"):
        select_official_alpha_pool(
            _world_state(),
            [_bundle("ENT_A", 2.0)],
            frozen_entities={"ENT_STALE": "manual freeze"},
            capacity=2,
        )


@pytest.mark.parametrize("capacity", [0, 101])
def test_select_official_alpha_pool_rejects_capacity_outside_bounds(capacity: int) -> None:
    with pytest.raises(MainCoreError, match="official_alpha_pool_capacity"):
        select_official_alpha_pool(
            _world_state(),
            [_bundle("ENT_A", 1.0)],
            capacity=capacity,
        )


def test_select_official_alpha_pool_rejects_empty_bundles() -> None:
    with pytest.raises(MainCoreError, match="bundles"):
        select_official_alpha_pool(_world_state(), [])


def test_select_official_alpha_pool_rejects_cycle_mismatch() -> None:
    with pytest.raises(MainCoreError, match="cycle_id"):
        select_official_alpha_pool(
            _world_state("cycle_l5"),
            [_bundle("ENT_A", 1.0, cycle_id="other_cycle")],
        )


def test_select_official_alpha_pool_rejects_duplicate_entity_id() -> None:
    with pytest.raises(MainCoreError, match="duplicate entity_id"):
        select_official_alpha_pool(
            _world_state(),
            [
                _bundle("ENT_A", 1.0),
                _bundle("ENT_A", 2.0),
            ],
        )
