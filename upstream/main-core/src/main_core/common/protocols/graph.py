"""Graph-engine protocol contracts shared by main-core layers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from main_core.common.errors import MainCoreError
from main_core.common.types import CycleId, EntityId


class GraphSnapshotError(MainCoreError):
    """Raised when a graph snapshot cannot be consumed safely."""


@dataclass(frozen=True, slots=True)
class GraphImpactRecord:
    """One graph impact row from the read-only graph snapshot surface."""

    cycle_id: CycleId
    entity_id: EntityId
    features: Mapping[str, Any]
    snapshot_id: str


@dataclass(frozen=True, slots=True)
class GraphRegimeContext:
    """Graph regime context read from the graph snapshot surface."""

    cycle_id: CycleId
    snapshot_id: str
    regime_context: Mapping[str, Any]


@runtime_checkable
class GraphEnginePort(Protocol):
    """Read-only graph-engine boundary used by main-core."""

    def read_graph_impact_snapshot(
        self,
        cycle_id: CycleId,
    ) -> Sequence[GraphImpactRecord]:
        """Return per-entity graph impact rows for the requested cycle."""

    def read_graph_regime_context(
        self,
        cycle_id: CycleId,
    ) -> GraphRegimeContext | None:
        """Return graph regime context for the requested cycle, when available."""


__all__ = [
    "GraphEnginePort",
    "GraphImpactRecord",
    "GraphRegimeContext",
    "GraphSnapshotError",
]
