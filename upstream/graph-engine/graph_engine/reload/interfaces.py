"""Canonical full-read boundary for cold reload."""

from __future__ import annotations

from typing import Protocol

from graph_engine.models import ColdReloadPlan


class CanonicalReader(Protocol):
    """Read canonical graph records needed for a full Neo4j rebuild."""

    def read_cold_reload_plan(self, snapshot_ref: str) -> ColdReloadPlan:
        """Return the full rebuild plan for snapshot_ref."""
