"""Snapshot persistence boundary protocols."""

from __future__ import annotations

from typing import Protocol

from graph_engine.models import GraphImpactSnapshot, GraphSnapshot


class SnapshotWriter(Protocol):
    """Write graph snapshots to the Layer A snapshot sink."""

    def write_snapshots(
        self,
        graph_snapshot: GraphSnapshot,
        impact_snapshot: GraphImpactSnapshot,
    ) -> None:
        """Persist a graph snapshot and its matching impact snapshot atomically."""
