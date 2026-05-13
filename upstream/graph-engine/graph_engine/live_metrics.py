"""Shared live graph metric reads and checksum helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from graph_engine.client import Neo4jClient

LIVE_GRAPH_METRICS_QUERY = """
CALL {
    MATCH (node)
    WITH node
    ORDER BY coalesce(node.node_id, elementId(node)) ASC
    RETURN count(node) AS node_count,
           collect({
               labels: labels(node),
               node_id: node.node_id,
               canonical_entity_id: node.canonical_entity_id,
               properties: properties(node)
           }) AS nodes
}
CALL {
    MATCH (node)
    UNWIND labels(node) AS label
    WITH label, count(*) AS count
    ORDER BY label ASC
    RETURN collect({label: label, count: count}) AS label_counts
}
CALL {
    MATCH (source)-[relationship]->(target)
    WITH source, relationship, target
    ORDER BY coalesce(relationship.edge_id, elementId(relationship)) ASC
    RETURN count(relationship) AS edge_count,
           collect({
               source_node_id: source.node_id,
               target_node_id: target.node_id,
               relationship_type: type(relationship),
               edge_id: relationship.edge_id,
               properties: properties(relationship)
           }) AS relationships
}
RETURN node_count, edge_count, label_counts, nodes, relationships
"""


@dataclass(frozen=True)
class LiveGraphMetrics:
    """Validated live graph metrics and structural payloads."""

    node_count: int
    edge_count: int
    key_label_counts: dict[str, int]
    checksum: str
    nodes: list[dict[str, Any]]
    relationships: list[dict[str, Any]]


def read_live_graph_metrics(
    client: Neo4jClient,
    *,
    strict: bool = True,
) -> tuple[int, int, dict[str, int], str]:
    """Read node/edge counts, label counts, and structural checksum."""

    metrics = read_live_graph_metric_payload(client, strict=strict)
    return metrics.node_count, metrics.edge_count, metrics.key_label_counts, metrics.checksum


def read_live_graph_metric_payload(
    client: Neo4jClient,
    *,
    strict: bool = True,
) -> LiveGraphMetrics:
    """Read live graph metrics with the normalized structural payload."""

    rows = client.execute_read(LIVE_GRAPH_METRICS_QUERY)
    if strict:
        row = _single_metrics_row(rows)
        node_count = _int_field(row, "node_count")
        edge_count = _int_field(row, "edge_count")
        key_label_counts = _strict_label_counts(row["label_counts"])
        nodes = _list_field(row, "nodes")
        relationships = _list_field(row, "relationships")
    else:
        row = rows[0] if isinstance(rows, list) and rows else {}
        if not isinstance(row, Mapping):
            row = {}
        node_count = int(row.get("node_count", 0))
        edge_count = int(row.get("edge_count", 0))
        key_label_counts = _permissive_label_counts(row.get("label_counts"))
        nodes = _permissive_list(row.get("nodes"))
        relationships = _permissive_list(row.get("relationships"))

    normalized_nodes = [_jsonable_mapping(node) for node in nodes]
    normalized_relationships = [
        _jsonable_mapping(relationship)
        for relationship in relationships
    ]
    payload = {
        "node_count": node_count,
        "edge_count": edge_count,
        "nodes": sorted_payload_list(normalized_nodes),
        "relationships": sorted_payload_list(normalized_relationships),
    }
    return LiveGraphMetrics(
        node_count=node_count,
        edge_count=edge_count,
        key_label_counts=key_label_counts,
        checksum=checksum_payload(payload),
        nodes=normalized_nodes,
        relationships=normalized_relationships,
    )


def sorted_payload_list(values: list[Any]) -> list[Any]:
    """Return a JSON-normalized, stable-order payload list."""

    normalized_values = [_jsonable(value) for value in values]
    return sorted(normalized_values, key=_stable_json)


def checksum_payload(payload: Any) -> str:
    """Return a stable SHA-256 checksum for a JSON-compatible payload."""

    encoded = _stable_json(_jsonable(payload)).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _single_metrics_row(rows: object) -> Mapping[str, Any]:
    if not isinstance(rows, list) or len(rows) != 1:
        raise ValueError("Neo4j graph metrics query returned malformed rows")
    row = rows[0]
    if not isinstance(row, Mapping):
        raise ValueError("Neo4j graph metrics query returned a malformed row")
    required_fields = {"node_count", "edge_count", "label_counts", "nodes", "relationships"}
    if not required_fields <= row.keys():
        raise ValueError("Neo4j graph metrics query returned an incomplete row")
    return row


def _int_field(row: Mapping[str, Any], field_name: str) -> int:
    value = row[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Neo4j graph metrics field {field_name!r} is malformed")
    if value < 0:
        raise ValueError(f"Neo4j graph metrics field {field_name!r} cannot be negative")
    return value


def _list_field(row: Mapping[str, Any], field_name: str) -> list[Any]:
    value = row[field_name]
    if not isinstance(value, list):
        raise ValueError(f"Neo4j graph metrics field {field_name!r} is malformed")
    return value


def _strict_label_counts(value: object) -> dict[str, int]:
    if not isinstance(value, list):
        raise ValueError("Neo4j graph metrics field 'label_counts' is malformed")

    counts: dict[str, int] = {}
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("Neo4j graph metrics field 'label_counts' is malformed")
        label = item.get("label")
        count = item.get("count")
        if not isinstance(label, str):
            raise ValueError("Neo4j graph metrics label count is missing a string label")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("Neo4j graph metrics label count is malformed")
        counts[label] = count
    return counts


def _permissive_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value


def _permissive_label_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, list):
        return {}
    counts: dict[str, int] = {}
    for row in value:
        if not isinstance(row, Mapping):
            continue
        label = row.get("label")
        if label is None:
            continue
        counts[str(label)] = int(row.get("count", 0))
    return counts


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, nested_value in sorted(value.items(), key=lambda item: str(item[0])):
            string_key = str(key)
            if string_key == "labels" and isinstance(nested_value, list):
                normalized[string_key] = sorted(
                    (_jsonable(item) for item in nested_value),
                    key=_stable_json,
                )
            else:
                normalized[string_key] = _jsonable(nested_value)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted((_jsonable(item) for item in value), key=_stable_json)

    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)


def _jsonable_mapping(value: Any) -> dict[str, Any]:
    normalized = _jsonable(value)
    if not isinstance(normalized, dict):
        raise ValueError("Neo4j graph metrics payload contains a malformed mapping")
    return normalized
