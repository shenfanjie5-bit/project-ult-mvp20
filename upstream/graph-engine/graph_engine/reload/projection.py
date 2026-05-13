"""GDS projection rebuild for the cold reload lifecycle."""

from __future__ import annotations

from typing import Any

from graph_engine.client import Neo4jClient
from graph_engine.schema.definitions import NodeLabel, RelationshipType


def rebuild_gds_projection(client: Neo4jClient, projection_name: str) -> None:
    """Drop and recreate the named GDS projection for the full live graph."""

    _drop_projection_if_exists(client, projection_name)
    relationship_projection = {
        relationship_type.value: {
            "type": relationship_type.value,
            "orientation": "NATURAL",
            "properties": {
                "weight": {
                    "property": "weight",
                    "defaultValue": 1.0,
                },
            },
        }
        for relationship_type in _existing_graph_engine_relationship_types(client)
    }
    _execute_gds_write(
        client,
        """
CALL gds.graph.project($projection_name, $node_projection, $relationship_projection)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount
""",
        {
            "projection_name": projection_name,
            "node_projection": [label.value for label in NodeLabel],
            "relationship_projection": relationship_projection,
        },
    )


def _drop_projection_if_exists(client: Neo4jClient, projection_name: str) -> None:
    rows = _execute_gds_read(
        client,
        "CALL gds.graph.exists($projection_name) YIELD exists RETURN exists",
        {"projection_name": projection_name},
    )
    if rows and rows[0].get("exists") is True:
        _execute_gds_write(
            client,
            "CALL gds.graph.drop($projection_name) YIELD graphName RETURN graphName",
            {"projection_name": projection_name},
        )


def _existing_graph_engine_relationship_types(client: Neo4jClient) -> list[RelationshipType]:
    rows = client.execute_read(
        """
MATCH ()-[relationship]->()
RETURN collect(DISTINCT type(relationship)) AS relationship_types
""",
    )
    raw_relationship_types = rows[0].get("relationship_types", []) if rows else []
    if not isinstance(raw_relationship_types, list):
        raw_relationship_types = []
    live_relationship_types = {
        str(relationship_type)
        for relationship_type in raw_relationship_types
        if str(relationship_type)
    }
    supported_relationship_types = {
        relationship_type.value
        for relationship_type in RelationshipType
    }
    unsupported_relationship_types = sorted(
        live_relationship_types - supported_relationship_types,
    )
    if unsupported_relationship_types:
        raise ValueError(
            "live graph contains unsupported relationship types: "
            + ", ".join(unsupported_relationship_types),
        )
    return [
        relationship_type
        for relationship_type in RelationshipType
        if relationship_type.value in live_relationship_types
    ]


def _execute_gds_read(
    client: Neo4jClient,
    query: str,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        return client.execute_read(query, parameters)
    except Exception as exc:
        if _is_missing_gds_error(exc):
            raise RuntimeError("GDS plugin not available") from exc
        raise


def _execute_gds_write(
    client: Neo4jClient,
    query: str,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        return client.execute_write(query, parameters)
    except Exception as exc:
        if _is_missing_gds_error(exc):
            raise RuntimeError("GDS plugin not available") from exc
        raise


def _is_missing_gds_error(exc: Exception) -> bool:
    message = str(exc).lower()
    missing_markers = (
        "no procedure",
        "not registered",
        "unknown procedure",
        "procedure not found",
    )
    return "gds." in message and any(marker in message for marker in missing_markers)
