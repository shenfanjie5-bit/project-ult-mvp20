"""Persistent graph-domain records shared by graph-engine workflows."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal, Self, get_args

from contracts.schemas import (
    CandidateGraphDelta,
    GraphImpactSnapshot,
    GraphSnapshot,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from graph_engine.evidence import evidence_refs_from_properties
from graph_engine.schema.definitions import RelationshipType

__all__ = [
    "CandidateGraphDelta",
    "ColdReloadPlan",
    "FrozenGraphDelta",
    "GraphAssertionRecord",
    "GraphEdgeRecord",
    "GraphImpactSnapshot",
    "GraphMetricsSnapshot",
    "GraphPropagationPathQueryResult",
    "GraphNodeRecord",
    "GraphQueryResult",
    "GraphSnapshot",
    "Neo4jGraphStatus",
    "PropagationChannel",
    "PropagationContext",
    "PropagationResult",
    "PromotionPlan",
    "ReadonlySimulationRequest",
]

PropagationChannel = Literal["fundamental", "event", "reflexive"]
_ALLOWED_PROPAGATION_CHANNELS: frozenset[str] = frozenset(get_args(PropagationChannel))
_PROPAGATABLE_RELATIONSHIP_TYPES: frozenset[str] = frozenset(
    {
        RelationshipType.SUPPLY_CHAIN.value,
        RelationshipType.OWNERSHIP.value,
        RelationshipType.INDUSTRY_CHAIN.value,
        RelationshipType.SECTOR_MEMBERSHIP.value,
        RelationshipType.EVENT_IMPACT.value,
        RelationshipType.CO_HOLDING.value,
        RelationshipType.NORTHBOUND_HOLD.value,
    }
)
_PROPAGATION_CHANNEL_PROPERTY_NAMES: tuple[str, ...] = (
    "propagation_channel",
    "channel",
    "impact_channel",
)


class GraphNodeRecord(BaseModel):
    """Canonical graph node persisted in Layer A."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    node_id: str = Field(min_length=1)
    canonical_entity_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    properties: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class GraphEdgeRecord(BaseModel):
    """Canonical graph relationship persisted in Layer A."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    edge_id: str = Field(min_length=1)
    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    relationship_type: str = Field(min_length=1)
    properties: dict[str, Any]
    weight: float = Field(default=1.0, ge=0.0)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _propagatable_edges_require_evidence_refs(self) -> Self:
        if not _is_propagatable_edge(self.relationship_type, self.properties):
            return self

        evidence_refs = evidence_refs_from_properties(self.properties)
        if not evidence_refs:
            raise ValueError(
                "propagatable GraphEdgeRecord requires evidence_ref or evidence_refs",
            )

        self.properties = {
            **self.properties,
            "evidence_refs": evidence_refs,
        }
        return self


class GraphAssertionRecord(BaseModel):
    """Canonical assertion and evidence record."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    assertion_id: str = Field(min_length=1)
    source_node_id: str = Field(min_length=1)
    target_node_id: str | None
    assertion_type: str = Field(min_length=1)
    evidence: dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime


def _is_propagatable_edge(
    relationship_type: str,
    properties: dict[str, Any],
) -> bool:
    if relationship_type in _PROPAGATABLE_RELATIONSHIP_TYPES:
        return True
    return any(
        _is_propagation_channel(properties.get(property_name))
        for property_name in _PROPAGATION_CHANNEL_PROPERTY_NAMES
    )


def _is_propagation_channel(value: Any) -> bool:
    if isinstance(value, (list, tuple, set)):
        return any(_is_propagation_channel(item) for item in value)
    return isinstance(value, str) and value in _ALLOWED_PROPAGATION_CHANNELS


class FrozenGraphDelta(BaseModel):
    """Internal frozen candidate change waiting for graph promotion."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    delta_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    delta_type: Literal["node_add", "edge_add", "edge_update", "assertion_add"]
    source_entity_ids: list[str] = Field(min_length=1)
    payload: dict[str, Any]
    validation_status: Literal["validated", "rejected", "frozen"]


class PromotionPlan(BaseModel):
    """Runtime plan for promoting frozen graph deltas into the canonical graph."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    cycle_id: str = Field(min_length=1)
    selection_ref: str = Field(min_length=1)
    delta_ids: list[str]
    node_records: list[GraphNodeRecord]
    edge_records: list[GraphEdgeRecord]
    assertion_records: list[GraphAssertionRecord]
    created_at: datetime


class PropagationContext(BaseModel):
    """Runtime context for one read-only propagation run."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    cycle_id: str = Field(min_length=1)
    world_state_ref: str = Field(min_length=1)
    graph_generation_id: int = Field(ge=0)
    enabled_channels: list[PropagationChannel] = Field(min_length=1)
    channel_multipliers: dict[str, float]
    regime_multipliers: dict[str, float]
    decay_policy: dict[str, Any]
    regime_context: dict[str, Any]

    @field_validator("enabled_channels")
    @classmethod
    def _validate_enabled_channels(
        cls,
        enabled_channels: list[PropagationChannel],
    ) -> list[PropagationChannel]:
        if not enabled_channels:
            raise ValueError("enabled_channels must not be empty")
        unknown_channels = [
            channel for channel in enabled_channels if channel not in _ALLOWED_PROPAGATION_CHANNELS
        ]
        if unknown_channels:
            raise ValueError(f"unknown propagation channels: {unknown_channels}")
        if len(set(enabled_channels)) != len(enabled_channels):
            raise ValueError("enabled_channels must not contain duplicates")
        return enabled_channels


class PropagationResult(BaseModel):
    """Serializable propagation output used to build impact snapshots."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    cycle_id: str = Field(min_length=1)
    graph_generation_id: int = Field(ge=0)
    activated_paths: list[dict[str, Any]]
    impacted_entities: list[dict[str, Any]]
    channel_breakdown: dict[str, Any]


class ReadonlySimulationRequest(BaseModel):
    """Runtime request for one read-only local impact simulation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    cycle_id: str = Field(min_length=1)
    world_state_ref: str = Field(min_length=1)
    graph_generation_id: int = Field(ge=0)
    depth: int = Field(default=2, ge=0, le=6)
    enabled_channels: list[PropagationChannel] = Field(min_length=1)
    channel_multipliers: dict[str, float]
    regime_multipliers: dict[str, float]
    decay_policy: dict[str, Any]
    regime_context: dict[str, Any]
    result_limit: int = Field(default=100, ge=1, le=1000)
    max_iterations: int = Field(default=20, ge=1)
    projection_name: str | None = Field(default=None, min_length=1)

    @field_validator("enabled_channels")
    @classmethod
    def _validate_enabled_channels(
        cls,
        enabled_channels: list[PropagationChannel],
    ) -> list[PropagationChannel]:
        if not enabled_channels:
            raise ValueError("enabled_channels must not be empty")
        unknown_channels = [
            channel for channel in enabled_channels if channel not in _ALLOWED_PROPAGATION_CHANNELS
        ]
        if unknown_channels:
            raise ValueError(f"unknown propagation channels: {unknown_channels}")
        if len(set(enabled_channels)) != len(enabled_channels):
            raise ValueError("enabled_channels must not contain duplicates")
        return enabled_channels

    @field_validator("channel_multipliers", "regime_multipliers")
    @classmethod
    def _validate_multiplier_keys(cls, multipliers: dict[str, float]) -> dict[str, float]:
        unknown_channels = [
            channel for channel in multipliers if channel not in _ALLOWED_PROPAGATION_CHANNELS
        ]
        if unknown_channels:
            raise ValueError(f"unknown propagation channels: {unknown_channels}")
        invalid_channels = [
            channel
            for channel, multiplier in multipliers.items()
            if not math.isfinite(float(multiplier)) or float(multiplier) < 0.0
        ]
        if invalid_channels:
            raise ValueError(
                "multipliers must be finite non-negative values for channels: "
                f"{invalid_channels}",
            )
        return multipliers

    @model_validator(mode="after")
    def _enabled_channels_require_multipliers(self) -> Self:
        missing_channel_multipliers = [
            channel
            for channel in self.enabled_channels
            if channel not in self.channel_multipliers
        ]
        if missing_channel_multipliers:
            raise ValueError(
                "channel_multipliers must include every enabled channel: "
                f"{missing_channel_multipliers}",
            )

        missing_regime_multipliers = [
            channel
            for channel in self.enabled_channels
            if channel not in self.regime_multipliers
        ]
        if missing_regime_multipliers:
            raise ValueError(
                "regime_multipliers must include every enabled channel: "
                f"{missing_regime_multipliers}",
            )
        return self


class GraphQueryResult(BaseModel):
    """Status-gated read-only live graph query result."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    graph_generation_id: int = Field(ge=0)
    subgraph_nodes: list[dict[str, Any]]
    subgraph_edges: list[dict[str, Any]]
    status: Literal["ready"]
    seed_entities: list[str] = Field(default_factory=list)
    depth: int = Field(default=0, ge=0)
    result_limit: int = Field(default=0, ge=0)
    truncated: bool = False
    truncation: dict[str, Any] = Field(default_factory=dict)


class GraphPropagationPathQueryResult(BaseModel):
    """Status-gated read-only propagation path query result."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    graph_generation_id: int = Field(ge=0)
    paths: list[dict[str, Any]]
    status: Literal["ready"]
    seed_entities: list[str] = Field(default_factory=list)
    depth: int = Field(default=0, ge=0)
    result_limit: int = Field(default=0, ge=0)
    truncated: bool = False
    truncation: dict[str, Any] = Field(default_factory=dict)


class GraphMetricsSnapshot(BaseModel):
    """Internal structural metrics used for status and consistency checks."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    cycle_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    graph_generation_id: int = Field(ge=0)
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    key_label_counts: dict[str, int]
    checksum: str = Field(min_length=1)
    created_at: datetime


class ColdReloadPlan(BaseModel):
    """Runtime plan for rebuilding Neo4j from canonical graph truth."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    snapshot_ref: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    expected_snapshot: GraphMetricsSnapshot
    node_records: list[GraphNodeRecord]
    edge_records: list[GraphEdgeRecord]
    assertion_records: list[GraphAssertionRecord]
    projection_name: str = Field(min_length=1)
    created_at: datetime


class Neo4jGraphStatus(BaseModel):
    """Current live graph status stored outside Neo4j."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    graph_status: Literal["ready", "rebuilding", "failed"]
    graph_generation_id: int = Field(ge=0)
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    key_label_counts: dict[str, int]
    checksum: str = Field(min_length=1)
    last_verified_at: datetime | None
    last_reload_at: datetime | None
    writer_lock_token: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _writer_lock_requires_ready_status(self) -> Self:
        if self.writer_lock_token is not None and self.graph_status != "ready":
            raise ValueError("writer_lock_token requires graph_status='ready'")
        return self
