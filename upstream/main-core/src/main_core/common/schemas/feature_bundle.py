"""L3 runtime feature signal bundle schema."""

from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite
from typing import Any

from pydantic import Field, field_validator

from main_core.common.schemas.base import FormalObjectBase
from main_core.common.types import CycleId, EntityId


def _utc_now() -> datetime:
    return datetime.now(UTC)


class FeatureSignalBundle(FormalObjectBase):
    """Runtime L3 feature and signal bundle described in §9.3."""

    cycle_id: CycleId
    entity_id: EntityId
    feature_values: dict[str, float]
    signal_values: dict[str, Any]
    graph_features: dict[str, Any]
    feature_weight_multiplier: dict[str, float]
    generated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("feature_weight_multiplier")
    @classmethod
    def validate_feature_weight_multiplier(cls, value: dict[str, float]) -> dict[str, float]:
        """Require auditable positive finite feature multipliers."""

        invalid_keys = [
            feature_name
            for feature_name, multiplier in value.items()
            if not isfinite(multiplier) or multiplier <= 0
        ]
        if invalid_keys:
            raise ValueError("feature_weight_multiplier values must be finite and > 0")
        return value


__all__ = ["FeatureSignalBundle"]
