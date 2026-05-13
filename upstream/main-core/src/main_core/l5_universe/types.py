"""Configuration types for L5 universe selection."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self

from main_core.common.errors import MainCoreError
from main_core.common.types import EntityId

MAX_OFFICIAL_ALPHA_POOL_CAPACITY = 100
MVP20_DECISION_POOL_CAPACITY = 20
MVP20_MANIFEST_TARGET_FREEZE_REASON = "mvp20 manifest target"


@dataclass(frozen=True)
class PoolSelectionConfig:
    """Runtime configuration for observation and official alpha pool selection."""

    capacity: int = MAX_OFFICIAL_ALPHA_POOL_CAPACITY
    observation_limit: int | None = None
    min_candidate_score: float | None = None

    def __post_init__(self) -> None:
        """Validate the formal capacity hard bound before a pool is built."""

        if not isinstance(self.capacity, int) or isinstance(self.capacity, bool):
            raise MainCoreError("official_alpha_pool_capacity must be an integer")
        if not 1 <= self.capacity <= MAX_OFFICIAL_ALPHA_POOL_CAPACITY:
            raise MainCoreError(
                "official_alpha_pool_capacity must be between 1 and 100",
            )
        if (
            self.observation_limit is not None
            and (
                not isinstance(self.observation_limit, int)
                or isinstance(self.observation_limit, bool)
                or self.observation_limit < 0
            )
        ):
            raise MainCoreError("observation_limit must be a non-negative integer")


@dataclass(frozen=True)
class MVP20DecisionPoolSpec:
    """Runtime manifest target spec for the fixed 20-entity decision pool."""

    manifest_targets: tuple[EntityId, ...]
    target_freeze_reason: str = MVP20_MANIFEST_TARGET_FREEZE_REASON

    def __post_init__(self) -> None:
        """Normalize and validate manifest targets without changing public contracts."""

        object.__setattr__(
            self,
            "manifest_targets",
            _normalize_manifest_targets(self.manifest_targets),
        )
        if (
            not isinstance(self.target_freeze_reason, str)
            or not self.target_freeze_reason.strip()
        ):
            raise MainCoreError("target_freeze_reason must be a non-empty string")

    @classmethod
    def from_manifest_targets(
        cls,
        manifest_targets: Sequence[EntityId],
        *,
        target_freeze_reason: str = MVP20_MANIFEST_TARGET_FREEZE_REASON,
    ) -> Self:
        """Build a validated MVP20 decision pool spec from manifest target ids."""

        return cls(
            manifest_targets=tuple(manifest_targets),
            target_freeze_reason=target_freeze_reason,
        )

    def frozen_entities(self) -> dict[EntityId, str]:
        """Return freeze metadata that pins every manifest target into the pool."""

        return {
            EntityId(str(entity_id)): self.target_freeze_reason
            for entity_id in self.manifest_targets
        }


def _normalize_manifest_targets(
    manifest_targets: Sequence[EntityId],
) -> tuple[EntityId, ...]:
    normalized_targets: list[EntityId] = []
    seen_entity_ids: set[str] = set()

    for entity_id in manifest_targets:
        entity_id_value = str(entity_id).strip()
        if not entity_id_value:
            raise MainCoreError("manifest_targets must contain non-empty entity_id")
        if entity_id_value in seen_entity_ids:
            raise MainCoreError("manifest_targets must not contain duplicate entity_id")
        seen_entity_ids.add(entity_id_value)
        normalized_targets.append(EntityId(entity_id_value))

    if len(normalized_targets) != MVP20_DECISION_POOL_CAPACITY:
        raise MainCoreError("mvp20 decision pool requires exactly 20 manifest_targets")
    return tuple(normalized_targets)


__all__ = [
    "MAX_OFFICIAL_ALPHA_POOL_CAPACITY",
    "MVP20_DECISION_POOL_CAPACITY",
    "MVP20_MANIFEST_TARGET_FREEZE_REASON",
    "MVP20DecisionPoolSpec",
    "PoolSelectionConfig",
]
