"""Status-gated read-only query APIs for the live Neo4j graph."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, get_args

from graph_engine.client import Neo4jClient
from graph_engine.models import (
    GraphPropagationPathQueryResult,
    GraphQueryResult,
    PropagationChannel,
)
from graph_engine.propagation.channels import (
    PROPAGATION_CHANNELS_BY_RELATIONSHIP_TYPE,
)
from graph_engine.status import GraphStatusManager

MAX_QUERY_DEPTH = 4
_ALLOWED_CHANNELS: frozenset[str] = frozenset(get_args(PropagationChannel))
_NODE_STRUCTURAL_PROPERTY_KEYS = frozenset(
    {
        "canonical_entity_id",
        "created_at",
        "label",
        "node_id",
        "properties_json",
        "updated_at",
    },
)
_EDGE_STRUCTURAL_PROPERTY_KEYS = frozenset(
    {
        "created_at",
        "edge_id",
        "properties_json",
        "relationship_type",
        "source_node_id",
        "target_node_id",
        "updated_at",
        "weight",
    },
)

@dataclass(frozen=True)
class BoundedSubgraph:
    nodes: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    truncation: dict[str, Any]

    @property
    def truncated(self) -> bool:
        return bool(self.truncation.get("truncated"))

    def __iter__(self) -> Iterator[list[dict[str, Any]]]:
        yield self.nodes
        yield self.relationships


class BoundedPathList(list[dict[str, Any]]):
    def __init__(
        self,
        paths: list[dict[str, Any]],
        *,
        truncation: dict[str, Any],
    ) -> None:
        super().__init__(paths)
        self.truncation = truncation
        self.truncated = bool(truncation.get("truncated"))


def query_subgraph(
    seed_entities: list[str],
    depth: int,
    *,
    client: Neo4jClient,
    status_manager: GraphStatusManager,
    result_limit: int = 500,
    max_depth: int = MAX_QUERY_DEPTH,
) -> GraphQueryResult:
    """Return a deterministic bounded subgraph from a ready live graph."""

    seed_list = _validated_seed_entities(seed_entities)
    validated_depth = _validated_depth(depth, max_depth=max_depth)
    validated_limit = _validated_result_limit(result_limit)
    if status_manager is None:
        raise ValueError("query_subgraph requires status_manager")

    with status_manager.ready_read() as graph_status:
        subgraph = _read_subgraph(
            seed_list,
            validated_depth,
            client=client,
            result_limit=validated_limit,
        )
        return GraphQueryResult(
            graph_generation_id=graph_status.graph_generation_id,
            subgraph_nodes=subgraph.nodes,
            subgraph_edges=subgraph.relationships,
            status="ready",
            seed_entities=seed_list,
            depth=validated_depth,
            result_limit=validated_limit,
            truncated=subgraph.truncated,
            truncation=subgraph.truncation,
        )


def query_propagation_paths(
    seed_entities: list[str],
    depth: int,
    *,
    client: Neo4jClient,
    status_manager: GraphStatusManager,
    channels: list[str] | None = None,
    result_limit: int = 100,
    max_depth: int = MAX_QUERY_DEPTH,
) -> GraphPropagationPathQueryResult:
    """Return read-only propagation path summaries from a ready live graph."""

    seed_list = _validated_seed_entities(seed_entities)
    validated_depth = _validated_depth(depth, max_depth=max_depth)
    validated_limit = _validated_result_limit(result_limit)
    channel_filter = _validated_channels(channels)
    if status_manager is None:
        raise ValueError("query_propagation_paths requires status_manager")

    with status_manager.ready_read() as graph_status:
        paths = _read_propagation_paths(
            seed_list,
            validated_depth,
            client=client,
            channels=channel_filter,
            result_limit=validated_limit,
        )
        return GraphPropagationPathQueryResult(
            graph_generation_id=graph_status.graph_generation_id,
            paths=list(paths),
            status="ready",
            seed_entities=seed_list,
            depth=validated_depth,
            result_limit=validated_limit,
            truncated=paths.truncated,
            truncation=paths.truncation,
        )


def _read_subgraph(
    seed_entities: list[str],
    depth: int,
    *,
    client: Neo4jClient,
    result_limit: int,
) -> BoundedSubgraph:
    seed_rows = _read_seed_rows(
        client,
        seed_entities=seed_entities,
        result_limit=result_limit,
    )

    nodes_by_key: dict[str, dict[str, Any]] = {}
    frontier_node_keys: list[str] = []
    node_limit_reached = len(seed_rows) > result_limit
    for row in seed_rows[:result_limit]:
        node, node_key = _node_from_traversal_row(row)
        if node_key is None or node_key in nodes_by_key:
            continue
        nodes_by_key[node_key] = node
        frontier_node_keys.append(node_key)

    relationships_by_key: dict[str, dict[str, Any]] = {}
    visited_relationship_keys: set[str] = set()
    frontier_limit_reached = False
    relationship_limit_reached = False
    truncated_depths: set[int] = set()
    reached_depth = 0

    for current_depth in range(1, depth + 1):
        if not frontier_node_keys:
            break
        reached_depth = current_depth
        rows = _read_frontier_rows(
            client,
            frontier_node_keys=frontier_node_keys,
            visited_relationship_keys=visited_relationship_keys,
            result_limit=result_limit,
            include_channel=False,
        )
        if len(rows) > result_limit:
            frontier_limit_reached = True
            truncated_depths.add(current_depth)

        previous_node_keys = set(nodes_by_key)
        next_frontier_keys: list[str] = []
        for row in rows[:result_limit]:
            relationship, relationship_key = _relationship_from_traversal_row(row)
            if relationship_key is None or relationship_key in visited_relationship_keys:
                continue
            visited_relationship_keys.add(relationship_key)

            endpoint_nodes = _endpoint_nodes_from_traversal_row(row)
            endpoints_available = True
            for endpoint_key, endpoint_node in endpoint_nodes:
                if endpoint_key is None or endpoint_key in nodes_by_key:
                    continue
                if len(nodes_by_key) >= result_limit:
                    node_limit_reached = True
                    truncated_depths.add(current_depth)
                    endpoints_available = False
                    break
                nodes_by_key[endpoint_key] = endpoint_node

            if not endpoints_available:
                continue
            if len(relationships_by_key) >= result_limit:
                relationship_limit_reached = True
                truncated_depths.add(current_depth)
                break

            relationships_by_key[relationship_key] = relationship
            neighbor_key = _text_or_none(row.get("neighbor_key"))
            if (
                neighbor_key is not None
                and neighbor_key not in previous_node_keys
                and neighbor_key in nodes_by_key
                and neighbor_key not in next_frontier_keys
            ):
                next_frontier_keys.append(neighbor_key)

        frontier_node_keys = next_frontier_keys
        if node_limit_reached or relationship_limit_reached:
            break

    nodes = _normalize_nodes(list(nodes_by_key.values()), result_limit=result_limit)
    included_node_ids = {
        node_id
        for node in nodes
        if (node_id := _text_or_none(node.get("node_id"))) is not None
    }
    relationships = _normalize_edges(
        [
            relationship
            for relationship in relationships_by_key.values()
            if _relationship_endpoints_included(relationship, included_node_ids)
        ],
        result_limit=result_limit,
    )
    truncation = _truncation_metadata(
        depth=depth,
        reached_depth=reached_depth,
        result_limit=result_limit,
        node_count=len(nodes),
        relationship_count=len(relationships),
        path_count=None,
        node_limit_reached=node_limit_reached,
        relationship_limit_reached=relationship_limit_reached,
        path_limit_reached=False,
        frontier_limit_reached=frontier_limit_reached,
        truncated_depths=truncated_depths,
    )
    return BoundedSubgraph(nodes, relationships, truncation)


def _subgraph_query(depth: int) -> str:
    return _seed_nodes_query()


def _seed_nodes_query() -> str:
    return """
MATCH (seed)
WHERE seed.canonical_entity_id IN $seed_entities
   OR seed.node_id IN $seed_entities
WITH DISTINCT seed,
     coalesce(seed.node_id, elementId(seed)) AS node_key
ORDER BY coalesce(seed.node_id, ""),
         coalesce(seed.canonical_entity_id, ""),
         node_key
LIMIT $per_depth_limit
RETURN node_key,
       {
           node_id: seed.node_id,
           canonical_entity_id: seed.canonical_entity_id,
           labels: labels(seed),
           properties: properties(seed)
       } AS node
"""


def _path_query(depth: int) -> str:
    if depth == 0:
        return "RETURN [] AS paths"

    return _frontier_expansion_query(include_channel=True)


def _frontier_expansion_query(*, include_channel: bool) -> str:
    channel_projection = (
        f"{_channel_projection_list_expression()} AS channels"
        if include_channel
        else "null AS channel"
    )
    channel_expansion = (
        "UNWIND channels AS channel"
        if include_channel
        else ""
    )
    channel_filter = (
        "WHERE $channel_filter IS NULL OR channel IN $channel_filter"
        if include_channel
        else ""
    )
    order_by = (
        "ORDER BY coalesce(relationship.weight, 1.0) DESC,\n"
        "         relationship_key,\n"
        "         channel,\n"
        "         source_key,\n"
        "         type(relationship),\n"
        "         target_key,\n"
        "         neighbor_key"
        if include_channel
        else "ORDER BY relationship_key,\n"
        "         source_key,\n"
        "         type(relationship),\n"
        "         target_key,\n"
        "         neighbor_key"
    )
    return f"""
MATCH (frontier)-[relationship]-(neighbor)
WHERE coalesce(frontier.node_id, elementId(frontier)) IN $frontier_node_keys
WITH DISTINCT relationship
WITH relationship,
     startNode(relationship) AS source,
     endNode(relationship) AS target,
     coalesce(relationship.edge_id, elementId(relationship)) AS relationship_key
WITH relationship,
     source,
     target,
     relationship_key,
     coalesce(source.node_id, elementId(source)) AS source_key,
     coalesce(target.node_id, elementId(target)) AS target_key
WHERE NOT (relationship_key IN $visited_relationship_keys)
WITH relationship,
     source,
     target,
     relationship_key,
     source_key,
     target_key,
     CASE
         WHEN source_key IN $frontier_node_keys
              AND NOT (target_key IN $frontier_node_keys) THEN target
         WHEN target_key IN $frontier_node_keys
              AND NOT (source_key IN $frontier_node_keys) THEN source
         WHEN source_key IN $frontier_node_keys THEN target
         ELSE source
     END AS neighbor
WITH relationship,
     source,
     target,
     relationship_key,
     source_key,
     target_key,
     neighbor,
     coalesce(neighbor.node_id, elementId(neighbor)) AS neighbor_key,
     {channel_projection}
{channel_expansion}
{channel_filter}
{order_by}
LIMIT $per_depth_limit
RETURN relationship_key,
       source_key,
       target_key,
       neighbor_key,
       channel,
       {{
           node_id: source.node_id,
           canonical_entity_id: source.canonical_entity_id,
           labels: labels(source),
           properties: properties(source)
       }} AS source,
       {{
           node_id: target.node_id,
           canonical_entity_id: target.canonical_entity_id,
           labels: labels(target),
           properties: properties(target)
       }} AS target,
       {{
           node_id: neighbor.node_id,
           canonical_entity_id: neighbor.canonical_entity_id,
           labels: labels(neighbor),
           properties: properties(neighbor)
       }} AS neighbor,
       {{
           edge_id: relationship.edge_id,
           source_node_id: source.node_id,
           target_node_id: target.node_id,
           relationship_type: type(relationship),
           properties: properties(relationship),
           weight: coalesce(relationship.weight, 1.0)
       }} AS relationship
"""


def _channel_projection_list_expression(relationship_variable: str = "relationship") -> str:
    default_channel_cases = "\n".join(
        (
            f'             WHEN "{relationship_type}" THEN '
            f"{_cypher_string_list(channels)}"
        )
        for relationship_type, channels in PROPAGATION_CHANNELS_BY_RELATIONSHIP_TYPE.items()
    )
    return (
        "CASE\n"
        f"         WHEN {relationship_variable}.propagation_channel IS NOT NULL "
        f"THEN [{relationship_variable}.propagation_channel]\n"
        f"         WHEN {relationship_variable}.channel IS NOT NULL "
        f"THEN [{relationship_variable}.channel]\n"
        f"         WHEN {relationship_variable}.impact_channel IS NOT NULL "
        f"THEN [{relationship_variable}.impact_channel]\n"
        f"         ELSE CASE type({relationship_variable})\n"
        f"{default_channel_cases}\n"
        "             ELSE []\n"
        "         END\n"
        "     END"
    )


def _cypher_string_list(values: tuple[str, ...]) -> str:
    return "[" + ", ".join(f'"{value}"' for value in values) + "]"


def _read_propagation_paths(
    seed_entities: list[str],
    depth: int,
    *,
    client: Neo4jClient,
    channels: list[str] | None,
    result_limit: int,
) -> BoundedPathList:
    if depth == 0:
        return BoundedPathList(
            [],
            truncation=_truncation_metadata(
                depth=depth,
                reached_depth=0,
                result_limit=result_limit,
                node_count=0,
                relationship_count=0,
                path_count=0,
                node_limit_reached=False,
                relationship_limit_reached=False,
                path_limit_reached=False,
                frontier_limit_reached=False,
                truncated_depths=set(),
            ),
        )

    seed_rows = _read_seed_rows(
        client,
        seed_entities=seed_entities,
        result_limit=result_limit,
    )
    nodes_by_key: dict[str, dict[str, Any]] = {}
    frontier_node_keys: list[str] = []
    node_limit_reached = len(seed_rows) > result_limit
    for row in seed_rows[:result_limit]:
        node, node_key = _node_from_traversal_row(row)
        if node_key is None or node_key in nodes_by_key:
            continue
        nodes_by_key[node_key] = node
        frontier_node_keys.append(node_key)

    visited_relationship_keys: set[str] = set()
    paths_by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    channel_set = set(channels) if channels is not None else None
    candidate_limit = result_limit * max(depth, 1)
    frontier_limit_reached = False
    relationship_limit_reached = False
    path_limit_reached = False
    truncated_depths: set[int] = set()
    reached_depth = 0

    for current_depth in range(1, depth + 1):
        if not frontier_node_keys:
            break
        reached_depth = current_depth
        frontier_rows = _read_frontier_rows(
            client,
            frontier_node_keys=frontier_node_keys,
            visited_relationship_keys=visited_relationship_keys,
            result_limit=result_limit,
            include_channel=False,
        )
        path_rows = _read_frontier_rows(
            client,
            frontier_node_keys=frontier_node_keys,
            visited_relationship_keys=visited_relationship_keys,
            result_limit=result_limit,
            include_channel=True,
            channels=channels,
        )
        if len(frontier_rows) > result_limit:
            frontier_limit_reached = True
            truncated_depths.add(current_depth)
        if len(path_rows) > result_limit:
            path_limit_reached = True
            truncated_depths.add(current_depth)

        previous_node_keys = set(nodes_by_key)
        next_frontier_keys: list[str] = []
        for row in frontier_rows[:result_limit]:
            relationship, relationship_key = _relationship_from_traversal_row(row)
            if relationship_key is None or relationship_key in visited_relationship_keys:
                continue
            visited_relationship_keys.add(relationship_key)

            neighbor = row.get("neighbor")
            neighbor_payload = _node_payload(neighbor) if isinstance(neighbor, Mapping) else {}
            neighbor_key = _text_or_none(row.get("neighbor_key"))
            if neighbor_key is not None and neighbor_key not in nodes_by_key:
                if len(nodes_by_key) >= result_limit:
                    node_limit_reached = True
                    truncated_depths.add(current_depth)
                else:
                    nodes_by_key[neighbor_key] = neighbor_payload

            if (
                neighbor_key is not None
                and neighbor_key not in previous_node_keys
                and neighbor_key in nodes_by_key
                and neighbor_key not in next_frontier_keys
            ):
                next_frontier_keys.append(neighbor_key)

        for row in path_rows[:result_limit]:
            relationship, relationship_key = _relationship_from_traversal_row(row)
            if relationship_key is None:
                continue
            channel = _text_or_none(row.get("channel"))
            if channel is None or (channel_set is not None and channel not in channel_set):
                continue
            if len(paths_by_key) >= candidate_limit:
                path_limit_reached = True
                truncated_depths.add(current_depth)
                continue

            path = _path_payload(
                {
                    **relationship,
                    "channel": channel,
                    "path_length": current_depth,
                    "score": relationship.get("weight"),
                },
            )
            key = _path_identity(path)
            paths_by_key.setdefault(key, path)

        frontier_node_keys = next_frontier_keys
        if node_limit_reached and not frontier_node_keys:
            break
        if relationship_limit_reached:
            break

    raw_paths = list(paths_by_key.values())
    paths = _normalize_paths(raw_paths, channels=channels, result_limit=result_limit)
    if len(raw_paths) > result_limit:
        path_limit_reached = True
    truncation = _truncation_metadata(
        depth=depth,
        reached_depth=reached_depth,
        result_limit=result_limit,
        node_count=len(nodes_by_key),
        relationship_count=len(visited_relationship_keys),
        path_count=len(paths),
        node_limit_reached=node_limit_reached,
        relationship_limit_reached=relationship_limit_reached,
        path_limit_reached=path_limit_reached,
        frontier_limit_reached=frontier_limit_reached,
        truncated_depths=truncated_depths,
    )
    return BoundedPathList(paths, truncation=truncation)


def _read_seed_rows(
    client: Neo4jClient,
    *,
    seed_entities: list[str],
    result_limit: int,
) -> list[dict[str, Any]]:
    return client.execute_read(
        _seed_nodes_query(),
        {
            "per_depth_limit": _per_depth_limit(result_limit),
            "seed_entities": seed_entities,
        },
    )


def _read_frontier_rows(
    client: Neo4jClient,
    *,
    frontier_node_keys: list[str],
    visited_relationship_keys: set[str],
    result_limit: int,
    include_channel: bool,
    channels: list[str] | None = None,
) -> list[dict[str, Any]]:
    return client.execute_read(
        _frontier_expansion_query(include_channel=include_channel),
        {
            "channel_filter": channels,
            "frontier_node_keys": frontier_node_keys,
            "per_depth_limit": _per_depth_limit(result_limit),
            "visited_relationship_keys": sorted(visited_relationship_keys),
        },
    )


def _per_depth_limit(result_limit: int) -> int:
    return result_limit + 1


def _node_from_traversal_row(row: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    raw_node = row.get("node")
    if not isinstance(raw_node, Mapping):
        raw_node = row
    node = _node_payload(raw_node)
    return node, _text_or_none(row.get("node_key")) or _node_key(node)


def _relationship_from_traversal_row(
    row: Mapping[str, Any],
) -> tuple[dict[str, Any], str | None]:
    raw_relationship = row.get("relationship")
    if not isinstance(raw_relationship, Mapping):
        raw_relationship = row
    relationship = _edge_payload(raw_relationship)
    return relationship, _text_or_none(row.get("relationship_key")) or _relationship_key(
        relationship,
    )


def _endpoint_nodes_from_traversal_row(
    row: Mapping[str, Any],
) -> list[tuple[str | None, dict[str, Any]]]:
    endpoints: list[tuple[str | None, dict[str, Any]]] = []
    for key_name, node_name in (("source_key", "source"), ("target_key", "target")):
        raw_node = row.get(node_name)
        if not isinstance(raw_node, Mapping):
            continue
        node = _node_payload(raw_node)
        endpoints.append((_text_or_none(row.get(key_name)) or _node_key(node), node))
    return endpoints


def _node_key(node: Mapping[str, Any]) -> str | None:
    node_id = _text_or_none(node.get("node_id"))
    if node_id:
        return node_id
    canonical_entity_id = _text_or_none(node.get("canonical_entity_id"))
    if canonical_entity_id:
        return canonical_entity_id
    return None


def _relationship_key(relationship: Mapping[str, Any]) -> str | None:
    edge_id = _text_or_none(relationship.get("edge_id"))
    if edge_id:
        return edge_id
    source_node_id = _text_or_none(relationship.get("source_node_id"))
    relationship_type = _text_or_none(relationship.get("relationship_type"))
    target_node_id = _text_or_none(relationship.get("target_node_id"))
    if source_node_id is None or relationship_type is None or target_node_id is None:
        return None
    return "|".join((source_node_id, relationship_type, target_node_id))


def _relationship_endpoints_included(
    relationship: Mapping[str, Any],
    included_node_ids: set[str],
) -> bool:
    source_node_id = _text_or_none(relationship.get("source_node_id"))
    target_node_id = _text_or_none(relationship.get("target_node_id"))
    if source_node_id is None or target_node_id is None:
        return False
    return source_node_id in included_node_ids and target_node_id in included_node_ids


def _truncation_metadata(
    *,
    depth: int,
    reached_depth: int,
    result_limit: int,
    node_count: int,
    relationship_count: int,
    path_count: int | None,
    node_limit_reached: bool,
    relationship_limit_reached: bool,
    path_limit_reached: bool,
    frontier_limit_reached: bool,
    truncated_depths: set[int],
) -> dict[str, Any]:
    reasons: list[str] = []
    if node_limit_reached:
        reasons.append("node_limit_reached")
    if relationship_limit_reached:
        reasons.append("relationship_limit_reached")
    if path_limit_reached:
        reasons.append("path_limit_reached")
    if frontier_limit_reached:
        reasons.append("frontier_limit_reached")

    metadata: dict[str, Any] = {
        "truncated": bool(reasons),
        "reasons": reasons,
        "depth": depth,
        "reached_depth": reached_depth,
        "result_limit": result_limit,
        "per_depth_limit": result_limit,
        "node_count": node_count,
        "relationship_count": relationship_count,
        "node_limit_reached": node_limit_reached,
        "relationship_limit_reached": relationship_limit_reached,
        "path_limit_reached": path_limit_reached,
        "frontier_limit_reached": frontier_limit_reached,
        "truncated_depths": sorted(truncated_depths),
    }
    if path_count is not None:
        metadata["path_count"] = path_count
    return metadata


def _node_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    raw_properties = _raw_properties(value)
    return {
        "node_id": _text_or_none(value.get("node_id", raw_properties.get("node_id"))),
        "canonical_entity_id": _text_or_none(
            value.get("canonical_entity_id", raw_properties.get("canonical_entity_id")),
        ),
        "labels": _sorted_text_list(value.get("labels", raw_properties.get("labels", []))),
        "properties": _properties_payload(raw_properties, _NODE_STRUCTURAL_PROPERTY_KEYS),
    }


def _edge_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    raw_properties = _raw_properties(value)
    weight = _float_or_default(value.get("weight", raw_properties.get("weight")), 1.0)
    return {
        "edge_id": _text_or_none(value.get("edge_id", raw_properties.get("edge_id"))),
        "source_node_id": _text_or_none(
            value.get("source_node_id", raw_properties.get("source_node_id")),
        ),
        "target_node_id": _text_or_none(
            value.get("target_node_id", raw_properties.get("target_node_id")),
        ),
        "relationship_type": _text_or_none(
            value.get("relationship_type", raw_properties.get("relationship_type")),
        ),
        "properties": _properties_payload(raw_properties, _EDGE_STRUCTURAL_PROPERTY_KEYS),
        "weight": weight,
    }


def _path_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    raw_properties = _raw_properties(value)
    score = _float_or_default(value.get("score", raw_properties.get("weight")), 1.0)
    path_length = _int_or_default(value.get("path_length"), 1)
    return {
        "channel": _text_or_none(value.get("channel", raw_properties.get("channel"))),
        "edge_id": _text_or_none(value.get("edge_id", raw_properties.get("edge_id"))),
        "source_node_id": _text_or_none(
            value.get("source_node_id", raw_properties.get("source_node_id")),
        ),
        "target_node_id": _text_or_none(
            value.get("target_node_id", raw_properties.get("target_node_id")),
        ),
        "relationship_type": _text_or_none(
            value.get("relationship_type", raw_properties.get("relationship_type")),
        ),
        "score": score,
        "path_length": path_length,
        "properties": _properties_payload(raw_properties, _EDGE_STRUCTURAL_PROPERTY_KEYS),
    }


def _validated_seed_entities(seed_entities: list[str]) -> list[str]:
    if not isinstance(seed_entities, list) or not seed_entities:
        raise ValueError("seed_entities must not be empty")

    seen: set[str] = set()
    normalized: list[str] = []
    for seed_entity in seed_entities:
        if not isinstance(seed_entity, str):
            raise ValueError("seed_entities must contain strings")
        stripped = seed_entity.strip()
        if not stripped:
            raise ValueError("seed_entities must contain non-empty ids")
        if stripped not in seen:
            seen.add(stripped)
            normalized.append(stripped)
    return normalized


def _validated_depth(depth: int, *, max_depth: int) -> int:
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 0:
        raise ValueError("max_depth must be a non-negative integer")
    if isinstance(depth, bool) or not isinstance(depth, int):
        raise ValueError("depth must be an integer")
    if depth < 0:
        raise ValueError("depth must be greater than or equal to zero")
    if depth > max_depth:
        raise ValueError(f"depth must be less than or equal to {max_depth}")
    return depth


def _validated_result_limit(result_limit: int) -> int:
    if isinstance(result_limit, bool) or not isinstance(result_limit, int):
        raise ValueError("result_limit must be an integer")
    if result_limit < 1:
        raise ValueError("result_limit must be greater than or equal to one")
    return result_limit


def _validated_channels(channels: list[str] | None) -> list[str] | None:
    if channels is None:
        return None
    if not isinstance(channels, list) or not channels:
        raise ValueError("channels must be a non-empty list when provided")

    seen: set[str] = set()
    normalized: list[str] = []
    for channel in channels:
        if not isinstance(channel, str):
            raise ValueError("channels must contain strings")
        stripped = channel.strip()
        if not stripped:
            raise ValueError("channels must contain non-empty values")
        if stripped not in _ALLOWED_CHANNELS:
            raise ValueError(f"unknown propagation channel: {stripped}")
        if stripped not in seen:
            seen.add(stripped)
            normalized.append(stripped)
    return normalized


def _normalize_nodes(value: Any, *, result_limit: int) -> list[dict[str, Any]]:
    nodes_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _mapping_rows(value):
        node = _node_payload(item)
        key = _node_identity(node)
        if key not in nodes_by_key:
            nodes_by_key[key] = node
    nodes = list(nodes_by_key.values())
    nodes.sort(key=_node_sort_key)
    return nodes[:result_limit]


def _normalize_edges(value: Any, *, result_limit: int) -> list[dict[str, Any]]:
    edges_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in _mapping_rows(value):
        edge = _edge_payload(item)
        key = _edge_identity(edge)
        if key not in edges_by_key:
            edges_by_key[key] = edge
    edges = list(edges_by_key.values())
    edges.sort(key=_edge_sort_key)
    return edges[:result_limit]


def _normalize_paths(
    value: Any,
    *,
    channels: list[str] | None,
    result_limit: int,
) -> list[dict[str, Any]]:
    channel_set = set(channels) if channels is not None else None
    paths_by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for item in _mapping_rows(value):
        path = _path_payload(item)
        channel = path.get("channel")
        if channel is None:
            continue
        if channel_set is not None and channel not in channel_set:
            continue
        key = _path_identity(path)
        if key not in paths_by_key:
            paths_by_key[key] = path
    paths = list(paths_by_key.values())
    paths.sort(key=_path_sort_key)
    return paths[:result_limit]


def _mapping_rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _raw_properties(value: Mapping[str, Any]) -> dict[str, Any]:
    raw_properties = value.get("properties")
    if isinstance(raw_properties, Mapping):
        return dict(raw_properties)
    return {}


def _properties_payload(
    raw_properties: Mapping[str, Any],
    structural_property_keys: frozenset[str],
) -> dict[str, Any]:
    properties = dict(raw_properties)
    decoded_properties = _decode_json_object(properties.get("properties_json"))
    payload: dict[str, Any] = dict(decoded_properties or {})
    for key, item in properties.items():
        if key not in structural_property_keys:
            payload.setdefault(str(key), item)
    return payload


def _decode_json_object(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict):
        return None
    return decoded


def _node_identity(node: Mapping[str, Any]) -> tuple[str, str]:
    return (
        _sort_text(node.get("node_id")),
        _sort_text(node.get("canonical_entity_id")),
    )


def _edge_identity(edge: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _sort_text(edge.get("edge_id")),
        _sort_text(edge.get("source_node_id")),
        _sort_text(edge.get("relationship_type")),
        _sort_text(edge.get("target_node_id")),
    )


def _path_identity(path: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        _sort_text(path.get("edge_id")),
        _sort_text(path.get("channel")),
        _sort_text(path.get("source_node_id")),
        _sort_text(path.get("relationship_type")),
        _sort_text(path.get("target_node_id")),
    )


def _node_sort_key(node: Mapping[str, Any]) -> tuple[str, str]:
    return (
        _sort_text(node.get("node_id")),
        _sort_text(node.get("canonical_entity_id")),
    )


def _edge_sort_key(edge: Mapping[str, Any]) -> tuple[bool, str, str, str, str]:
    edge_id = _sort_text(edge.get("edge_id"))
    return (
        edge_id == "",
        edge_id,
        _sort_text(edge.get("source_node_id")),
        _sort_text(edge.get("relationship_type")),
        _sort_text(edge.get("target_node_id")),
    )


def _path_sort_key(
    path: Mapping[str, Any],
) -> tuple[float, int, bool, str, str, str, str, str]:
    edge_id = _sort_text(path.get("edge_id"))
    return (
        -_float_or_default(path.get("score"), 0.0),
        _int_or_default(path.get("path_length"), 0),
        edge_id == "",
        edge_id,
        _sort_text(path.get("channel")),
        _sort_text(path.get("source_node_id")),
        _sort_text(path.get("relationship_type")),
        _sort_text(path.get("target_node_id")),
    )


def _sorted_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(str(item) for item in value if item is not None)


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _sort_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _float_or_default(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_or_default(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
