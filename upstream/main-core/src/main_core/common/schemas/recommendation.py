"""L7 formal recommendation schema."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import model_validator

from main_core.common.schemas.base import FormalObjectBase
from main_core.common.types import CycleId, EntityId

ActionType = Literal["buy", "hold", "reduce", "inconclusive"]
TriggerSource = Literal["system", "human_decision"]


class RecommendationSnapshot(FormalObjectBase):
    """Formal L7 recommendation snapshot described in §9.3."""

    cycle_id: CycleId
    entity_id: EntityId
    action_type: ActionType
    rating: str | None
    confidence: float | None
    triggered_by: TriggerSource
    override_applied: bool
    constraints_applied: dict[str, Any]

    @model_validator(mode="after")
    def validate_inconclusive_confidence(self) -> RecommendationSnapshot:
        """Inconclusive recommendations must not carry confidence."""

        if self.action_type == "inconclusive" and self.confidence is not None:
            raise ValueError("inconclusive recommendations must have confidence=None")
        return self


__all__ = ["ActionType", "RecommendationSnapshot", "TriggerSource"]
