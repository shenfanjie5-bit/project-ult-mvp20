"""Override business record schema."""

from __future__ import annotations

from datetime import datetime

from pydantic import field_validator

from main_core.common.schemas.base import FormalObjectBase
from main_core.common.schemas.recommendation import ActionType
from main_core.common.types import CycleId, EntityId


class OverrideRecord(FormalObjectBase):
    """Human override record for L7 recommendation decisions."""

    cycle_id: CycleId
    entity_id: EntityId
    submitted_by: str
    action_type: ActionType
    rationale: str
    submitted_at: datetime

    @field_validator("submitted_at")
    @classmethod
    def validate_submitted_at_is_utc(cls, value: datetime) -> datetime:
        """Require timezone-aware UTC datetimes so comparisons cannot crash."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("submitted_at must be a timezone-aware UTC datetime")
        return value


__all__ = ["OverrideRecord"]
