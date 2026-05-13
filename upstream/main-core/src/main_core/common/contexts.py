"""Runtime context models passed through explicit main-core protocols."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from main_core.common.errors import AlphaAnalyzerError
from main_core.common.schemas import (
    FeatureSignalBundle,
    WorldStateSnapshot,
)
from main_core.common.types import CycleId, EntityId


class AlphaAnalysisContext(BaseModel):
    """Frozen L6 runtime context for analyzer protocol calls."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: CycleId
    entity_id: EntityId
    feature_bundle: FeatureSignalBundle
    world_state: WorldStateSnapshot
    similar_cases: list[dict[str, Any]] = Field(default_factory=list)


def validate_alpha_analysis_context(
    entity_id: EntityId,
    context: AlphaAnalysisContext,
) -> None:
    """Validate the L6 analyzer input contract before provider work."""

    if entity_id != context.entity_id:
        raise AlphaAnalyzerError("entity_id must match context.entity_id")
    if context.feature_bundle.cycle_id != context.cycle_id:
        raise AlphaAnalyzerError(
            "context.feature_bundle.cycle_id must match context.cycle_id",
        )
    if context.world_state.cycle_id != context.cycle_id:
        raise AlphaAnalyzerError(
            "context.world_state.cycle_id must match context.cycle_id",
        )
    if context.feature_bundle.entity_id != context.entity_id:
        raise AlphaAnalyzerError(
            "context.feature_bundle.entity_id must match context.entity_id",
        )


class WorldStateInputs(BaseModel):
    """Frozen L4 runtime inputs for world-state policy evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: CycleId
    feature_bundle: FeatureSignalBundle
    macro_context: dict[str, Any] = Field(default_factory=dict)
    graph_impact: dict[str, Any] = Field(default_factory=dict)


class RecommendationConstraintInputs(BaseModel):
    """Frozen L7 runtime inputs for recommendation constraint gates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    world_state: WorldStateSnapshot
    risk_context: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AlphaAnalysisContext",
    "RecommendationConstraintInputs",
    "WorldStateInputs",
    "validate_alpha_analysis_context",
]
