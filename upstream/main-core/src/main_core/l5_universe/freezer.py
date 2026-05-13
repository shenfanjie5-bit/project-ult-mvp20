"""Frozen entity handling for L5 official alpha pool selection."""

from __future__ import annotations

from collections.abc import Mapping

from main_core.common.errors import MainCoreError
from main_core.common.schemas.pool import OfficialAlphaPool
from main_core.common.types import EntityId


def merge_frozen_entities(
    previous_pool: OfficialAlphaPool | None,
    frozen_entities: Mapping[EntityId, str] | None,
) -> dict[EntityId, str]:
    """Merge previous and explicit freeze reasons without rewriting prior reasons."""

    merged: dict[EntityId, str] = {}

    if previous_pool is not None:
        previous_freeze_reason_map = dict(previous_pool.freeze_reason_map)
        for entity_id in previous_pool.selected_entities:
            if entity_id in previous_freeze_reason_map:
                merged[EntityId(str(entity_id))] = previous_freeze_reason_map[entity_id]

        for entity_id, reason in sorted(
            previous_freeze_reason_map.items(),
            key=lambda item: str(item[0]),
        ):
            merged.setdefault(EntityId(str(entity_id)), reason)

    for entity_id, reason in dict(frozen_entities or {}).items():
        merged.setdefault(EntityId(str(entity_id)), reason)

    return merged


def ensure_frozen_entities_fit_capacity(
    freeze_reason_map: Mapping[EntityId, str],
    capacity: int,
) -> None:
    """Reject pools where frozen entities alone would exceed capacity."""

    if len(freeze_reason_map) > capacity:
        raise MainCoreError("frozen entity count exceeds official_alpha_pool_capacity")


__all__ = ["ensure_frozen_entities_fit_capacity", "merge_frozen_entities"]
