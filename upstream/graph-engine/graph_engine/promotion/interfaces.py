"""Protocol boundaries for graph promotion dependencies."""

from __future__ import annotations

from typing import Protocol

from contracts.schemas import CandidateGraphDelta

from graph_engine.models import PromotionPlan


class CandidateDeltaReader(Protocol):
    """Read contract candidate deltas from the upstream canonical input surface."""

    def read_candidate_graph_deltas(
        self,
        cycle_id: str,
        selection_ref: str,
    ) -> list[CandidateGraphDelta]:
        """Return contract graph deltas selected for promotion."""


class EntityAnchorReader(Protocol):
    """Read endpoint mappings and public entity-registry anchors."""

    def canonical_entity_ids_for_node_ids(self, node_ids: set[str]) -> dict[str, str]:
        """Return canonical entity ids for graph node ids referenced by contract deltas."""

    def existing_entity_ids(self, entity_ids: set[str]) -> set[str]:
        """Return entity ids that already exist as canonical entity-registry anchors."""


class CanonicalWriter(Protocol):
    """Persist promoted records into Layer A canonical storage."""

    def write_canonical_records(self, plan: PromotionPlan) -> None:
        """Write canonical graph records for a promotion plan."""
