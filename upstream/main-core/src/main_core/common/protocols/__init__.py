"""Explicit protocol contracts shared by main-core layers."""

from main_core.common.protocols.analyzer import AnalyzerBase, AnalyzerInterface
from main_core.common.protocols.constraint_provider import (
    RecommendationConstraintProvider,
    RecommendationConstraintProviderBase,
)
from main_core.common.protocols.graph import (
    GraphEnginePort,
    GraphImpactRecord,
    GraphRegimeContext,
    GraphSnapshotError,
)
from main_core.common.protocols.world_state_policy import (
    BoundedLlmDelta,
    WorldStatePolicy,
    WorldStatePolicyBase,
)

__all__ = [
    "AnalyzerBase",
    "AnalyzerInterface",
    "BoundedLlmDelta",
    "GraphEnginePort",
    "GraphImpactRecord",
    "GraphRegimeContext",
    "GraphSnapshotError",
    "RecommendationConstraintProvider",
    "RecommendationConstraintProviderBase",
    "WorldStatePolicy",
    "WorldStatePolicyBase",
]
