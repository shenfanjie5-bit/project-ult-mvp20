"""Synthetic graph generation and loading helpers for Neo4j benchmark runs."""

from __future__ import annotations

import random
import json
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

from graph_engine.client import Neo4jClient

_RANDOM_SEED = 42
_SYNTHETIC_BENCHMARK_PROPERTY = "synthetic_benchmark"
_DEFAULT_CLEAR_BATCH_SIZE = 10_000
_IDENTIFIER_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "_"
)


def generate_synthetic_nodes(count: int, labels: list[str]) -> list[dict[str, Any]]:
    """Generate benchmark nodes with stable ids and pseudo-random labels."""

    if count < 0:
        raise ValueError("count must be non-negative")
    _validate_non_empty_strings(labels, "labels")

    rng = random.Random(_RANDOM_SEED)
    return [
        {
            "node_id": f"synthetic-node-{index:08d}",
            "canonical_entity_id": f"synthetic-entity-{index:08d}",
            "label": rng.choice(labels),
            "properties": {
                "synthetic_benchmark": True,
                "ordinal": index,
                "name": f"Synthetic Entity {index}",
            },
        }
        for index in range(count)
    ]


def generate_synthetic_edges(
    nodes: list[dict[str, Any]],
    edge_count: int,
    relationship_types: list[str],
) -> list[dict[str, Any]]:
    """Generate benchmark edges with valid source and target node references."""

    if edge_count < 0:
        raise ValueError("edge_count must be non-negative")
    if edge_count == 0:
        return []
    if not nodes:
        raise ValueError("nodes must be non-empty when edge_count is positive")
    _validate_non_empty_strings(relationship_types, "relationship_types")

    node_refs = [(_node_id(node), _row_string(node, "label")) for node in nodes]
    rng = random.Random(_RANDOM_SEED + 1)
    node_count = len(node_refs)

    edges: list[dict[str, Any]] = []
    for index in range(edge_count):
        source_index = index % node_count
        target_index = rng.randrange(node_count)
        if node_count > 1 and target_index == source_index:
            target_index = (target_index + 1) % node_count

        source_node_id, source_label = node_refs[source_index]
        target_node_id, target_label = node_refs[target_index]
        relationship_type = rng.choice(relationship_types)
        weight = round(rng.uniform(0.1, 1.0), 6)
        edges.append(
            {
                "edge_id": f"synthetic-edge-{index:09d}",
                "source_node_id": source_node_id,
                "target_node_id": target_node_id,
                "source_label": source_label,
                "target_label": target_label,
                "relationship_type": relationship_type,
                "weight": weight,
                "properties": {
                    "synthetic_benchmark": True,
                    "ordinal": index,
                    "weight": weight,
                },
            }
        )

    return edges


def load_synthetic_graph(
    client: Neo4jClient,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    batch_size: int = 5000,
) -> None:
    """Load synthetic nodes and relationships into Neo4j using batched MERGE."""

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    for label, rows in _group_by(nodes, "label").items():
        query = (
            f"UNWIND $rows AS row\n"
            f"MERGE (n:{_quote_identifier(label)} {{node_id: row.node_id}})\n"
            "SET n.canonical_entity_id = row.canonical_entity_id,\n"
            "    n.label = row.label,\n"
            "    n.properties_json = row.properties_json,\n"
            "    n += row.properties"
        )
        for batch in _batched(rows, batch_size):
            client.execute_write(query, {"rows": [_write_row(row) for row in batch]})

    node_labels_by_id = {_node_id(node): _row_string(node, "label") for node in nodes}
    edge_rows = _normalize_edge_rows(edges, node_labels_by_id)
    for (relationship_type, source_label, target_label), rows in _group_edges(edge_rows).items():
        query = (
            "UNWIND $rows AS row\n"
            f"MATCH (source:{_quote_identifier(source_label)} "
            "{node_id: row.source_node_id})\n"
            f"MATCH (target:{_quote_identifier(target_label)} "
            "{node_id: row.target_node_id})\n"
            f"MERGE (source)-[r:{_quote_identifier(relationship_type)} "
            "{edge_id: row.edge_id}]->(target)\n"
            "SET r.relationship_type = row.relationship_type,\n"
            "    r.weight = row.weight,\n"
            "    r.properties_json = row.properties_json,\n"
            "    r += row.properties"
        )
        for batch in _batched(rows, batch_size):
            client.execute_write(query, {"rows": [_write_row(row) for row in batch]})


def clear_graph(
    client: Neo4jClient,
    batch_size: int = _DEFAULT_CLEAR_BATCH_SIZE,
) -> None:
    """Delete only graph artifacts explicitly marked as synthetic benchmark data."""

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    relationship_query = (
        "MATCH ()-[r]->()\n"
        f"WHERE r.{_SYNTHETIC_BENCHMARK_PROPERTY} = true\n"
        "WITH r LIMIT $batch_size\n"
        "WITH collect(r) AS relationships, count(r) AS deleted\n"
        "FOREACH (rel IN relationships | DELETE rel)\n"
        "RETURN deleted"
    )
    node_query = (
        "MATCH (n)\n"
        f"WHERE n.{_SYNTHETIC_BENCHMARK_PROPERTY} = true\n"
        "WITH n LIMIT $batch_size\n"
        "WITH collect(n) AS nodes, count(n) AS deleted\n"
        "FOREACH (node IN nodes | DETACH DELETE node)\n"
        "RETURN deleted"
    )
    _delete_in_batches(client, relationship_query, batch_size)
    _delete_in_batches(client, node_query, batch_size)


def _validate_non_empty_strings(values: list[str], field_name: str) -> None:
    if not values:
        raise ValueError(f"{field_name} must be non-empty")
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError(f"{field_name} must only contain non-empty strings")


def _node_id(node: dict[str, Any]) -> str:
    value = node.get("node_id")
    if not isinstance(value, str) or not value:
        raise ValueError("every node must include a non-empty node_id")
    return value


def _row_string(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"every row must include a non-empty {key}")
    return value


def _group_by(rows: Iterable[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_row_string(row, key)].append(row)
    return dict(grouped)


def _normalize_edge_rows(
    edges: Iterable[dict[str, Any]],
    node_labels_by_id: dict[str, str],
) -> list[dict[str, Any]]:
    normalized_edges: list[dict[str, Any]] = []
    for edge in edges:
        source_node_id = _row_string(edge, "source_node_id")
        target_node_id = _row_string(edge, "target_node_id")
        normalized = dict(edge)
        normalized["source_label"] = _edge_label(
            edge,
            "source_label",
            source_node_id,
            node_labels_by_id,
        )
        normalized["target_label"] = _edge_label(
            edge,
            "target_label",
            target_node_id,
            node_labels_by_id,
        )
        normalized_edges.append(normalized)
    return normalized_edges


def _write_row(row: dict[str, Any]) -> dict[str, Any]:
    write_row = dict(row)
    properties = write_row.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    write_row["properties"] = dict(properties)
    write_row["properties_json"] = json.dumps(properties, sort_keys=True)
    return write_row


def _edge_label(
    edge: dict[str, Any],
    label_key: str,
    node_id: str,
    node_labels_by_id: dict[str, str],
) -> str:
    value = edge.get(label_key)
    if isinstance(value, str) and value:
        return value
    try:
        return node_labels_by_id[node_id]
    except KeyError as exc:
        raise ValueError(f"edge references unknown node_id: {node_id}") from exc


def _group_edges(
    rows: Iterable[dict[str, Any]],
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            _row_string(row, "relationship_type"),
            _row_string(row, "source_label"),
            _row_string(row, "target_label"),
        )
        grouped[key].append(row)
    return dict(grouped)


def _delete_in_batches(
    client: Neo4jClient,
    query: str,
    batch_size: int,
) -> None:
    while True:
        rows = client.execute_write(query, {"batch_size": batch_size})
        deleted = _deleted_count(rows)
        if deleted < batch_size:
            return


def _deleted_count(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    value = rows[0].get("deleted", 0)
    return value if isinstance(value, int) else int(value)


def _batched(
    rows: Sequence[dict[str, Any]],
    batch_size: int,
) -> Iterator[list[dict[str, Any]]]:
    for start in range(0, len(rows), batch_size):
        yield list(rows[start : start + batch_size])


def _quote_identifier(identifier: str) -> str:
    if not identifier or any(character not in _IDENTIFIER_CHARS for character in identifier):
        raise ValueError(f"invalid Neo4j identifier: {identifier!r}")
    return f"`{identifier}`"
