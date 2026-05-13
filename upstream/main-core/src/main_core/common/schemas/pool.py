"""L5 formal official alpha pool schema."""

from __future__ import annotations

from pydantic import Field, model_validator

from main_core.common.schemas.base import FormalObjectBase
from main_core.common.types import CycleId, EntityId


class OfficialAlphaPool(FormalObjectBase):
    """Formal L5 official alpha pool described in §9.3."""

    cycle_id: CycleId
    observation_pool_size: int = Field(
        ge=0,
        description=(
            "Number of service-validated current-cycle entities eligible for L5 "
            "selection, including ranked observation candidates plus any "
            "service-validated frozen entities. freeze_reason_map is audit metadata and "
            "does not expand this eligibility bound."
        ),
    )
    official_alpha_pool_capacity: int = Field(default=100, ge=1, le=100)
    selected_entities: list[EntityId]
    added_entities: list[EntityId]
    removed_entities: list[EntityId]
    freeze_reason_map: dict[EntityId, str]

    @model_validator(mode="after")
    def validate_selected_entities_capacity(self) -> OfficialAlphaPool:
        """Require selected_entities to fit within the official pool capacity."""

        if len(self.selected_entities) > self.official_alpha_pool_capacity:
            raise ValueError("selected_entities length must be <= official_alpha_pool_capacity")
        if len(self.selected_entities) > self.observation_pool_size:
            raise ValueError(
                "selected_entities length must be <= observation_pool_size",
            )
        selected_entity_ids = {str(entity_id) for entity_id in self.selected_entities}
        freeze_reason_entity_ids = {str(entity_id) for entity_id in self.freeze_reason_map}
        if not freeze_reason_entity_ids <= selected_entity_ids:
            raise ValueError("freeze_reason_map keys must be present in selected_entities")
        return self


__all__ = ["OfficialAlphaPool"]
