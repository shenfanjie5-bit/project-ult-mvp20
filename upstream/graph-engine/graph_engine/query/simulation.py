"""Read-only local impact simulation over bounded GDS projections."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Protocol, cast
from uuid import uuid4

from graph_engine.client import Neo4jClient
from graph_engine.models import (
    Neo4jGraphStatus,
    PropagationChannel,
    PropagationContext,
    PropagationResult,
    ReadonlySimulationRequest,
)
from graph_engine.propagation._gds import execute_gds_read, execute_gds_write
from graph_engine.propagation.channels import (
    PROPAGATION_CHANNELS_BY_RELATIONSHIP_TYPE,
    effective_channel_selector,
)
from graph_engine.propagation.pipeline import run_full_propagation
from graph_engine.query.service import (
    _read_subgraph,
    _validated_depth,
    _validated_result_limit,
    _validated_seed_entities,
)
from graph_engine.status import GraphStatusManager, hold_ready_read

MAX_SIMULATION_DEPTH = 6
_SAFE_PROJECTION_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")
_PROJECTION_NAME_LIMIT = 120
_DEFAULT_CHANNELS: tuple[PropagationChannel, ...] = (
    "fundamental",
    "event",
    "reflexive",
)


class _SimulationClient(Protocol):
    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ...

    def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ...


def simulate_readonly_impact(
    seed_entities: list[str],
    context: ReadonlySimulationRequest,
    *,
    client: Neo4jClient,
    status_manager: GraphStatusManager,
) -> dict[str, Any]:
    """Run a local interim propagation simulation without mutating the live graph."""

    seed_list = _validated_seed_entities(seed_entities)
    depth = _validated_depth(context.depth, max_depth=MAX_SIMULATION_DEPTH)
    result_limit = _validated_result_limit(context.result_limit)
    projection_name = _default_projection_name(context)

    with hold_ready_read(status_manager, "readonly local impact simulation") as ready_status:
        if ready_status.graph_generation_id != context.graph_generation_id:
            raise ValueError(
                "ReadonlySimulationRequest graph_generation_id disagrees with Neo4jGraphStatus: "
                f"context={context.graph_generation_id}, "
                f"status={ready_status.graph_generation_id}",
            )

        bounded_subgraph = _read_subgraph(
            seed_list,
            depth,
            client=client,
            result_limit=result_limit,
        )
        nodes, edges = bounded_subgraph
        subgraph = _subgraph_payload(
            seed_list,
            depth,
            result_limit,
            nodes,
            edges,
            bounded_subgraph.truncation,
        )

        if not nodes or not edges:
            propagation_result = _empty_propagation_result(
                context,
                reason="empty_subgraph" if not nodes else "empty_relationship_set",
            )
        else:
            projection_client = _ReadonlyProjectionClient(
                client,
                node_ids=_node_ids(nodes),
                edges=edges,
                projection_names=_projection_names(
                    projection_name,
                    context.enabled_channels,
                ),
            )
            propagation_result = _run_scoped_propagation(
                context,
                projection_name=projection_name,
                client=projection_client,
                ready_status=ready_status,
            )

    if propagation_result.graph_generation_id != context.graph_generation_id:
        raise ValueError(
            "PropagationResult graph_generation_id disagrees with ReadonlySimulationRequest: "
            f"result={propagation_result.graph_generation_id}, "
            f"context={context.graph_generation_id}",
        )

    return {
        "status": "ready",
        "interim": True,
        "cycle_id": context.cycle_id,
        "world_state_ref": context.world_state_ref,
        "graph_generation_id": context.graph_generation_id,
        "seed_entities": seed_list,
        "depth": depth,
        "result_limit": result_limit,
        "truncated": bounded_subgraph.truncated,
        "truncation": bounded_subgraph.truncation,
        "subgraph": subgraph,
        "activated_paths": propagation_result.activated_paths,
        "impacted_entities": propagation_result.impacted_entities,
        "channel_breakdown": propagation_result.channel_breakdown,
        "projection_name": projection_name,
    }


def _run_scoped_propagation(
    request: ReadonlySimulationRequest,
    *,
    projection_name: str,
    client: "_ReadonlyProjectionClient",
    ready_status: Neo4jGraphStatus,
) -> PropagationResult:
    projection_names = _projection_names(projection_name, request.enabled_channels)
    _assert_projection_names_available(client, projection_names)
    try:
        return run_full_propagation(
            _simulation_context(request),
            cast(Neo4jClient, client),
            status_manager=cast(GraphStatusManager, _HeldReadyStatusManager(ready_status)),
            graph_name=projection_name,
            max_iterations=request.max_iterations,
            result_limit=request.result_limit,
        )
    finally:
        _drop_projections(client, client.created_projection_names, suppress_missing_gds=True)


def _default_projection_name(context: ReadonlySimulationRequest) -> str:
    if context.projection_name is not None:
        return _unique_projection_name(context.projection_name)

    cycle_component = _safe_projection_component(context.cycle_id)
    return _unique_projection_name(f"graph_engine_readonly_sim_{cycle_component}")


def _drop_projection_if_exists(client: _SimulationClient, graph_name: str) -> None:
    rows = execute_gds_read(
        cast(Neo4jClient, client),
        "CALL gds.graph.exists($graph_name) YIELD exists RETURN exists",
        {"graph_name": graph_name},
    )
    if rows and rows[0].get("exists") is True:
        execute_gds_write(
            cast(Neo4jClient, client),
            "CALL gds.graph.drop($graph_name) YIELD graphName RETURN graphName",
            {"graph_name": graph_name},
        )


def _create_readonly_projection(
    client: _SimulationClient,
    graph_name: str,
    node_ids: list[str],
    edge_ids: list[str],
) -> int:
    if not node_ids or not edge_ids:
        return 0

    rows = execute_gds_write(
        cast(Neo4jClient, client),
        """
MATCH (source)-[relationship]->(target)
WHERE source.node_id IN $node_ids
  AND target.node_id IN $node_ids
  AND relationship.edge_id IN $edge_ids
WITH gds.graph.project(
    $graph_name,
    source,
    target,
    {
        relationshipType: type(relationship),
        relationshipProperties: {
            weight: coalesce(relationship.weight, 1.0)
        }
    }
) AS projection
RETURN projection.graphName AS graphName,
       projection.nodeCount AS nodeCount,
       projection.relationshipCount AS relationshipCount
""",
        {
            "edge_ids": edge_ids,
            "graph_name": graph_name,
            "node_ids": node_ids,
        },
    )
    if not rows:
        return 0
    return int(rows[0].get("relationshipCount") or 0)


def _simulation_context(request: ReadonlySimulationRequest) -> PropagationContext:
    return PropagationContext(
        cycle_id=request.cycle_id,
        world_state_ref=request.world_state_ref,
        graph_generation_id=request.graph_generation_id,
        enabled_channels=list(request.enabled_channels),
        channel_multipliers=dict(request.channel_multipliers),
        regime_multipliers=dict(request.regime_multipliers),
        decay_policy=dict(request.decay_policy),
        regime_context=dict(request.regime_context),
    )


class _HeldReadyStatusManager:
    def __init__(self, ready_status: Neo4jGraphStatus) -> None:
        self._ready_status = ready_status

    @contextmanager
    def ready_read(self) -> Iterator[Neo4jGraphStatus]:
        yield self._ready_status


class _ReadonlyProjectionClient:
    def __init__(
        self,
        client: Neo4jClient,
        *,
        node_ids: list[str],
        edges: list[dict[str, Any]],
        projection_names: list[str],
    ) -> None:
        self._client = client
        self._node_ids = node_ids
        self._edge_ids_by_channel = _edge_ids_by_channel(edges)
        self._owned_projection_names = set(projection_names)
        self._created_projection_names: set[str] = set()

    @property
    def created_projection_names(self) -> list[str]:
        return sorted(self._created_projection_names)

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params = parameters or {}
        if _is_gds_graph_exists(query):
            graph_name = _graph_name_from_parameters(params)
            return self._read_owned_projection_exists(graph_name)
        if _is_activated_path_read(query):
            channel = _channel_from_query(query, params)
            if channel is None:
                raise PermissionError(
                    "readonly simulation activated-path reads require a resolvable channel",
                )
            return _read_scoped_activated_path_rows(
                self._client,
                channel=channel,
                node_ids=self._node_ids,
                edge_ids=self._edge_ids_by_channel.get(channel, []),
                parameters=params,
            )
        return self._client.execute_read(query, parameters)

    def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params = parameters or {}
        if _is_gds_projection_project(query):
            graph_name = _graph_name_from_parameters(params)
            self._require_owned_projection(graph_name)
            self._ensure_projection_available(graph_name)
            channel = _channel_from_query(query, params)
            edge_ids = (
                self._edge_ids_by_channel.get(channel, [])
                if channel is not None
                else _all_edge_ids(self._edge_ids_by_channel)
            )
            relationship_count = _create_readonly_projection(
                self._client,
                graph_name,
                self._node_ids,
                edge_ids,
            )
            if relationship_count > 0:
                self._created_projection_names.add(graph_name)
            return [
                {
                    "graphName": graph_name,
                    "nodeCount": len(self._node_ids),
                    "relationshipCount": relationship_count,
                }
            ]
        if "gds.graph.drop" in query:
            graph_name = _graph_name_from_parameters(params)
            self._require_owned_projection(graph_name)
            if not _is_gds_projection_drop(query):
                raise PermissionError(
                    "readonly simulation only permits scoped GDS projection drop",
                )
            if graph_name not in self._created_projection_names:
                raise PermissionError(
                    "readonly simulation cannot drop a projection it did not create",
                )
            rows = self._client.execute_write(query, parameters)
            self._created_projection_names.discard(graph_name)
            return rows
        raise PermissionError("readonly simulation only permits GDS projection writes")

    def _read_owned_projection_exists(self, graph_name: str) -> list[dict[str, Any]]:
        self._require_owned_projection(graph_name)
        rows = execute_gds_read(
            self._client,
            "CALL gds.graph.exists($graph_name) YIELD exists RETURN exists",
            {"graph_name": graph_name},
        )
        if rows and rows[0].get("exists") is True and graph_name not in self._created_projection_names:
            raise ValueError(f"GDS projection name already exists: {graph_name}")
        return rows

    def _ensure_projection_available(self, graph_name: str) -> None:
        rows = self._read_owned_projection_exists(graph_name)
        if rows and rows[0].get("exists") is True:
            raise ValueError(f"GDS projection name already exists: {graph_name}")

    def _require_owned_projection(self, graph_name: str) -> None:
        if graph_name not in self._owned_projection_names:
            raise PermissionError(
                "readonly simulation can only manage projections owned by this invocation",
            )


def _read_scoped_activated_path_rows(
    client: Neo4jClient,
    *,
    channel: str,
    node_ids: list[str],
    edge_ids: list[str],
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    if not node_ids or not edge_ids:
        return []

    rows = client.execute_read(
        f"""
MATCH (source)-[relationship]->(target)
WHERE source.node_id IN $node_ids
  AND target.node_id IN $node_ids
  AND relationship.edge_id IN $edge_ids
  AND {effective_channel_selector(channel)}
WITH source,
     relationship,
     target,
     coalesce(relationship.weight, 1.0) AS relation_weight,
     coalesce(relationship.evidence_confidence, 1.0) AS evidence_confidence,
     coalesce(relationship.recency_decay, 1.0) AS recency_decay
WITH source,
     relationship,
     target,
     relation_weight,
     evidence_confidence,
     recency_decay,
     relation_weight
         * evidence_confidence
         * $channel_multiplier
         * $regime_multiplier
         * recency_decay AS path_score
RETURN source.node_id AS source_node_id,
       source.canonical_entity_id AS source_entity_id,
       labels(source) AS source_labels,
       target.node_id AS target_node_id,
       target.canonical_entity_id AS target_entity_id,
       labels(target) AS target_labels,
       relationship.edge_id AS edge_id,
       type(relationship) AS relationship_type,
       relation_weight,
       evidence_confidence,
       recency_decay,
       path_score
ORDER BY path_score DESC,
         source_node_id ASC,
         relationship_type ASC,
         target_node_id ASC,
         edge_id ASC
LIMIT $result_limit
""",
        {
            "channel_multiplier": float(parameters.get("channel_multiplier", 1.0)),
            "edge_ids": edge_ids,
            "node_ids": node_ids,
            "regime_multiplier": float(parameters.get("regime_multiplier", 1.0)),
            "result_limit": int(parameters.get("result_limit", 100)),
        },
    )
    return rows


def _drop_projections(
    client: _SimulationClient,
    projection_names: list[str],
    *,
    suppress_missing_gds: bool,
) -> None:
    for projection_name in projection_names:
        try:
            _drop_projection_if_exists(client, projection_name)
        except RuntimeError as exc:
            if suppress_missing_gds and str(exc) == "GDS plugin not available":
                continue
            raise


def _assert_projection_names_available(
    client: _SimulationClient,
    projection_names: list[str],
) -> None:
    for projection_name in projection_names:
        rows = execute_gds_read(
            cast(Neo4jClient, client),
            "CALL gds.graph.exists($graph_name) YIELD exists RETURN exists",
            {"graph_name": projection_name},
        )
        if rows and rows[0].get("exists") is True:
            raise ValueError(f"GDS projection name already exists: {projection_name}")


def _projection_names(base_name: str, enabled_channels: list[PropagationChannel]) -> list[str]:
    if len(enabled_channels) == 1:
        names = [base_name]
    else:
        names = [f"{base_name}-{channel}" for channel in enabled_channels]
    return list(dict.fromkeys(names))


def _unique_projection_name(value: str) -> str:
    owner_token = uuid4().hex[:12]
    max_prefix_length = _PROJECTION_NAME_LIMIT - len(owner_token) - 1
    prefix = _safe_projection_name(value)[:max_prefix_length].strip("_-")
    if not prefix:
        prefix = "graph_engine_readonly_sim"
    return f"{prefix}_{owner_token}"


def _safe_projection_name(value: str) -> str:
    normalized = _SAFE_PROJECTION_PATTERN.sub("_", value).strip("_-")
    if not normalized:
        raise ValueError("projection_name must contain a safe graph name component")
    return normalized[:_PROJECTION_NAME_LIMIT]


def _safe_projection_component(value: str) -> str:
    return (_SAFE_PROJECTION_PATTERN.sub("_", value).strip("_-") or "cycle")[:48]


def _subgraph_payload(
    seed_entities: list[str],
    depth: int,
    result_limit: int,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    truncation: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "seed_entities": seed_entities,
        "depth": depth,
        "result_limit": result_limit,
        "nodes": nodes,
        "relationships": edges,
        "truncated": bool(truncation.get("truncated")),
        "truncation": dict(truncation),
    }


def _empty_propagation_result(
    request: ReadonlySimulationRequest,
    *,
    reason: str,
) -> PropagationResult:
    channel_breakdown: dict[str, Any] = {
        channel: {
            "status": "empty",
            "reason": reason,
            "path_selector": effective_channel_selector(channel),
            "path_count": 0,
            "impacted_entity_count": 0,
            "total_path_score": 0.0,
            "channel_multiplier": float(request.channel_multipliers[channel]),
            "regime_multiplier": float(request.regime_multipliers[channel]),
        }
        for channel in request.enabled_channels
    }
    channel_breakdown["merged"] = {
        "enabled_channels": sorted(request.enabled_channels),
        "path_count": 0,
        "impacted_entity_count": 0,
        "total_path_score": 0.0,
        "result_limit": request.result_limit,
    }
    return PropagationResult(
        cycle_id=request.cycle_id,
        graph_generation_id=request.graph_generation_id,
        activated_paths=[],
        impacted_entities=[],
        channel_breakdown=channel_breakdown,
    )


def _node_ids(nodes: list[dict[str, Any]]) -> list[str]:
    return _unique_text_values(node.get("node_id") for node in nodes)


def _edge_ids_by_channel(edges: list[dict[str, Any]]) -> dict[str, list[str]]:
    edge_ids_by_channel: dict[str, list[str]] = {channel: [] for channel in _DEFAULT_CHANNELS}
    for edge in edges:
        edge_id = edge.get("edge_id")
        if edge_id is None:
            continue
        for channel in _edge_channels(edge):
            edge_ids_by_channel.setdefault(channel, []).append(str(edge_id))
    return {
        channel: _unique_text_values(edge_ids)
        for channel, edge_ids in edge_ids_by_channel.items()
    }


def _edge_channels(edge: Mapping[str, Any]) -> tuple[str, ...]:
    properties = edge.get("properties")
    property_map = properties if isinstance(properties, Mapping) else {}
    for property_name in ("propagation_channel", "channel", "impact_channel"):
        explicit_channels = _coerced_channels(property_map.get(property_name))
        if explicit_channels:
            return explicit_channels

    relationship_type = edge.get("relationship_type")
    if relationship_type is None:
        return ()
    return PROPAGATION_CHANNELS_BY_RELATIONSHIP_TYPE.get(str(relationship_type), ())


def _coerced_channels(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    raw_values = value if isinstance(value, (list, tuple, set)) else (value,)
    allowed_channels = set(_DEFAULT_CHANNELS)
    return tuple(
        channel
        for channel in _unique_text_values(list(raw_values))
        if channel in allowed_channels
    )


def _unique_text_values(values: Iterator[Any] | list[Any]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        unique_values.append(text)
    return unique_values


def _all_edge_ids(edge_ids_by_channel: Mapping[str, list[str]]) -> list[str]:
    return _unique_text_values(
        edge_id for edge_ids in edge_ids_by_channel.values() for edge_id in edge_ids
    )


def _is_gds_graph_exists(query: str) -> bool:
    return "gds.graph.exists" in query


def _is_gds_projection_project(query: str) -> bool:
    return "gds.graph.project" in query


def _is_gds_projection_drop(query: str) -> bool:
    return _normalized_cypher(query) == (
        "call gds.graph.drop($graph_name) yield graphname return graphname"
    )


def _normalized_cypher(query: str) -> str:
    return " ".join(query.lower().split())


def _is_activated_path_read(query: str) -> bool:
    return (
        "MATCH (source)-[relationship]->(target)" in query
        and "path_score" in query
        and "gds.graph.project" not in query
    )


def _channel_from_query(
    query: str,
    parameters: Mapping[str, Any],
) -> PropagationChannel | None:
    for channel in _DEFAULT_CHANNELS:
        if f'= "{channel}"' in query:
            return channel

    graph_name = parameters.get("graph_name")
    if isinstance(graph_name, str):
        for channel in _DEFAULT_CHANNELS:
            if graph_name.endswith(f"-{channel}"):
                return channel
    return None


def _graph_name_from_parameters(parameters: Mapping[str, Any]) -> str:
    graph_name = parameters.get("graph_name")
    if not isinstance(graph_name, str) or not graph_name:
        raise ValueError("GDS projection calls require graph_name")
    return graph_name
