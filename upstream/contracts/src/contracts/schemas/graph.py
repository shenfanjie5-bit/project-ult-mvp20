"""Graph engine shared schemas."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from contracts.core import (
    AwareDatetime,
    ContractBaseModel,
    CycleId,
    Direction,
    EvidenceRef,
    NodeId,
    Score,
    SectorId,
    VersionString,
)
from contracts.core.types import NonEmptyString
from contracts.schemas.entities import EntityReference
from contracts.schemas.ex_payloads import Ex3CandidateGraphDelta


CandidateGraphDelta = Ex3CandidateGraphDelta


class GraphNode(ContractBaseModel):
    """Graph node persisted in a graph snapshot."""

    node_id: NodeId
    labels: list[NonEmptyString] = Field(min_length=1)
    properties: dict[str, object] = Field(default_factory=dict)
    entity: EntityReference | None = None


class GraphEdge(ContractBaseModel):
    """Graph edge persisted in a graph snapshot."""

    edge_id: NonEmptyString
    source_node: NodeId
    target_node: NodeId
    relation_type: NonEmptyString
    properties: dict[str, object] = Field(default_factory=dict)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class GraphSnapshot(ContractBaseModel):
    """Published graph-engine snapshot contract."""

    graph_snapshot_id: NonEmptyString
    cycle_id: CycleId
    version: VersionString
    created_at: AwareDatetime
    node_count: int = Field(ge=0, strict=True)
    edge_count: int = Field(ge=0, strict=True)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def counts_must_match_payloads(self) -> Self:
        """Keep declared snapshot counts and edges aligned with payloads."""

        if self.node_count != len(self.nodes):
            raise ValueError("node_count must match number of nodes")

        if self.edge_count != len(self.edges):
            raise ValueError("edge_count must match number of edges")

        node_ids = {node.node_id for node in self.nodes}
        missing_source_nodes = sorted(
            {
                edge.source_node
                for edge in self.edges
                if edge.source_node not in node_ids
            }
        )
        missing_target_nodes = sorted(
            {
                edge.target_node
                for edge in self.edges
                if edge.target_node not in node_ids
            }
        )
        if missing_source_nodes or missing_target_nodes:
            details = []
            if missing_source_nodes:
                details.append(f"source_node={', '.join(missing_source_nodes)}")
            if missing_target_nodes:
                details.append(f"target_node={', '.join(missing_target_nodes)}")
            raise ValueError(
                "graph snapshot edges must reference declared nodes: "
                + "; ".join(details)
            )

        return self


class GraphImpactSnapshot(ContractBaseModel):
    """Published graph-engine impact snapshot contract."""

    impact_snapshot_id: NonEmptyString
    cycle_id: CycleId
    version: VersionString
    created_at: AwareDatetime
    target_entities: list[EntityReference] = Field(min_length=1)
    affected_entities: list[EntityReference] = Field(default_factory=list)
    affected_sectors: list[SectorId] = Field(default_factory=list)
    direction: Direction
    impact_score: Score
    evidence_refs: list[EvidenceRef] = Field(min_length=1)


__all__ = [
    "CandidateGraphDelta",
    "GraphNode",
    "GraphEdge",
    "GraphSnapshot",
    "GraphImpactSnapshot",
]
