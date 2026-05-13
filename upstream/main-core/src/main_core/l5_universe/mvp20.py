"""MVP20 fixed decision pool helpers."""

from __future__ import annotations

from collections.abc import Sequence

from main_core.common.errors import MainCoreError
from main_core.common.schemas.feature_bundle import FeatureSignalBundle
from main_core.common.schemas.pool import OfficialAlphaPool
from main_core.common.schemas.world_state import WorldStateSnapshot
from main_core.common.types import EntityId
from main_core.l5_universe.service import select_official_alpha_pool
from main_core.l5_universe.types import (
    MVP20_DECISION_POOL_CAPACITY,
    MVP20_MANIFEST_TARGET_FREEZE_REASON,
    MVP20DecisionPoolSpec,
    PoolSelectionConfig,
)


def select_mvp20_decision_pool(
    world_state: WorldStateSnapshot,
    bundles: Sequence[FeatureSignalBundle],
    manifest_targets: Sequence[EntityId] | MVP20DecisionPoolSpec,
    *,
    target_freeze_reason: str = MVP20_MANIFEST_TARGET_FREEZE_REASON,
) -> OfficialAlphaPool:
    """Select the fixed 20-entity official alpha pool from manifest targets only.

    Extra bundles may be supplied for related-entity context, but they are not
    eligible for L5 pool selection or downstream L7 recommendations.
    """

    spec = _resolve_spec(
        manifest_targets,
        target_freeze_reason=target_freeze_reason,
    )
    bundle_by_entity = _current_bundle_by_entity(world_state, bundles)
    target_bundles = _target_bundles(spec, bundle_by_entity)

    return select_official_alpha_pool(
        world_state,
        target_bundles,
        config=PoolSelectionConfig(
            capacity=MVP20_DECISION_POOL_CAPACITY,
            observation_limit=MVP20_DECISION_POOL_CAPACITY,
        ),
        frozen_entities=spec.frozen_entities(),
    )


def _resolve_spec(
    manifest_targets: Sequence[EntityId] | MVP20DecisionPoolSpec,
    *,
    target_freeze_reason: str,
) -> MVP20DecisionPoolSpec:
    if isinstance(manifest_targets, MVP20DecisionPoolSpec):
        return manifest_targets
    return MVP20DecisionPoolSpec.from_manifest_targets(
        tuple(manifest_targets),
        target_freeze_reason=target_freeze_reason,
    )


def _current_bundle_by_entity(
    world_state: WorldStateSnapshot,
    bundles: Sequence[FeatureSignalBundle],
) -> dict[str, FeatureSignalBundle]:
    bundle_by_entity: dict[str, FeatureSignalBundle] = {}
    for bundle in bundles:
        if bundle.cycle_id != world_state.cycle_id:
            raise MainCoreError("bundle cycle_id must match world_state.cycle_id")

        entity_id = str(bundle.entity_id)
        if entity_id in bundle_by_entity:
            raise MainCoreError("duplicate entity_id in FeatureSignalBundle input")
        bundle_by_entity[entity_id] = bundle
    return bundle_by_entity


def _target_bundles(
    spec: MVP20DecisionPoolSpec,
    bundle_by_entity: dict[str, FeatureSignalBundle],
) -> list[FeatureSignalBundle]:
    missing_entity_ids = [
        str(entity_id)
        for entity_id in spec.manifest_targets
        if str(entity_id) not in bundle_by_entity
    ]
    if missing_entity_ids:
        raise MainCoreError(
            "manifest_targets must be present in current FeatureSignalBundle input: "
            f"{', '.join(missing_entity_ids)}",
        )
    return [
        bundle_by_entity[str(entity_id)]
        for entity_id in spec.manifest_targets
    ]


__all__ = ["select_mvp20_decision_pool"]
