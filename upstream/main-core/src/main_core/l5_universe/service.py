"""Service entrypoint for selecting the formal L5 official alpha pool."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from main_core.common.errors import MainCoreError
from main_core.common.schemas.feature_bundle import FeatureSignalBundle
from main_core.common.schemas.pool import OfficialAlphaPool
from main_core.common.schemas.world_state import WorldStateSnapshot
from main_core.common.types import EntityId
from main_core.l5_universe.freezer import (
    ensure_frozen_entities_fit_capacity,
    merge_frozen_entities,
)
from main_core.l5_universe.rules import rank_candidates
from main_core.l5_universe.types import PoolSelectionConfig


def select_official_alpha_pool(  # noqa: PLR0913
    world_state: WorldStateSnapshot,
    bundles: Sequence[FeatureSignalBundle],
    *,
    previous_pool: OfficialAlphaPool | None = None,
    capacity: int = 100,
    frozen_entities: Mapping[EntityId, str] | None = None,
    config: PoolSelectionConfig | None = None,
) -> OfficialAlphaPool:
    """Select the formal official alpha pool for one cycle."""

    active_config = config or PoolSelectionConfig(capacity=capacity)
    bundle_list = list(bundles)
    current_entity_ids = _validate_inputs(world_state, bundle_list)

    freeze_reason_map = merge_frozen_entities(previous_pool, frozen_entities)
    _ensure_frozen_entities_have_current_bundles(
        freeze_reason_map,
        current_entity_ids,
    )
    ensure_frozen_entities_fit_capacity(freeze_reason_map, active_config.capacity)

    observation_candidates = rank_candidates(world_state, bundle_list, active_config)
    selected_entities = _select_entities(
        observation_candidates,
        freeze_reason_map,
        active_config.capacity,
    )
    added_entities, removed_entities = _diff_selected_entities(
        previous_pool,
        selected_entities,
    )

    return OfficialAlphaPool(
        cycle_id=world_state.cycle_id,
        observation_pool_size=_count_eligible_entities(
            observation_candidates,
            freeze_reason_map,
        ),
        official_alpha_pool_capacity=active_config.capacity,
        selected_entities=selected_entities,
        added_entities=added_entities,
        removed_entities=removed_entities,
        freeze_reason_map=freeze_reason_map,
    )


def _validate_inputs(
    world_state: WorldStateSnapshot,
    bundles: Sequence[FeatureSignalBundle],
) -> set[str]:
    if not bundles:
        raise MainCoreError("bundles must not be empty")

    seen_entity_ids: set[str] = set()
    for bundle in bundles:
        if bundle.cycle_id != world_state.cycle_id:
            raise MainCoreError("bundle cycle_id must match world_state.cycle_id")

        entity_id = str(bundle.entity_id)
        if entity_id in seen_entity_ids:
            raise MainCoreError("duplicate entity_id in FeatureSignalBundle input")
        seen_entity_ids.add(entity_id)
    return seen_entity_ids


def _ensure_frozen_entities_have_current_bundles(
    freeze_reason_map: Mapping[EntityId, str],
    current_entity_ids: set[str],
) -> None:
    """Require each frozen entity to have current L3 feature inputs."""

    missing_entity_ids = sorted(
        str(entity_id)
        for entity_id in freeze_reason_map
        if str(entity_id) not in current_entity_ids
    )
    if missing_entity_ids:
        raise MainCoreError(
            "frozen entities must be present in current FeatureSignalBundle input: "
            f"{', '.join(missing_entity_ids)}",
        )


def _select_entities(
    observation_candidates: Sequence[FeatureSignalBundle],
    freeze_reason_map: Mapping[EntityId, str],
    capacity: int,
) -> list[EntityId]:
    selected_entities: list[EntityId] = []
    selected_entity_ids: set[str] = set()

    for entity_id in freeze_reason_map:
        _append_if_room(
            selected_entities,
            selected_entity_ids,
            EntityId(str(entity_id)),
            capacity,
        )

    for bundle in observation_candidates:
        _append_if_room(
            selected_entities,
            selected_entity_ids,
            EntityId(str(bundle.entity_id)),
            capacity,
        )

    return selected_entities


def _count_eligible_entities(
    observation_candidates: Sequence[FeatureSignalBundle],
    freeze_reason_map: Mapping[EntityId, str],
) -> int:
    """Count the validated frozen-inclusive pool the schema uses as its bound."""

    eligible_entity_ids = {str(bundle.entity_id) for bundle in observation_candidates}
    eligible_entity_ids.update(str(entity_id) for entity_id in freeze_reason_map)
    return len(eligible_entity_ids)


def _append_if_room(
    selected_entities: list[EntityId],
    selected_entity_ids: set[str],
    entity_id: EntityId,
    capacity: int,
) -> None:
    entity_id_value = str(entity_id)
    if entity_id_value in selected_entity_ids or len(selected_entities) >= capacity:
        return

    selected_entities.append(entity_id)
    selected_entity_ids.add(entity_id_value)


def _diff_selected_entities(
    previous_pool: OfficialAlphaPool | None,
    selected_entities: Sequence[EntityId],
) -> tuple[list[EntityId], list[EntityId]]:
    if previous_pool is None:
        return list(selected_entities), []

    previous_entity_ids = {str(entity_id) for entity_id in previous_pool.selected_entities}
    selected_entity_ids = {str(entity_id) for entity_id in selected_entities}
    added_entities = [
        entity_id
        for entity_id in selected_entities
        if str(entity_id) not in previous_entity_ids
    ]
    removed_entities = [
        EntityId(str(entity_id))
        for entity_id in previous_pool.selected_entities
        if str(entity_id) not in selected_entity_ids
    ]
    return added_entities, removed_entities


__all__ = ["select_official_alpha_pool"]
