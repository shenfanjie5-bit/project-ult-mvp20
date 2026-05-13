"""Incremental Neo4j live graph synchronization for promotion plans."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterator
from datetime import date, datetime, time
from typing import Any

from graph_engine.client import Neo4jClient
from graph_engine.models import GraphAssertionRecord, GraphEdgeRecord, GraphNodeRecord, PromotionPlan
from graph_engine.schema.definitions import NodeLabel, RelationshipType

_SAFE_PROPERTY_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED_PROPERTY_NAMES = {
    "assertion_id",
    "assertion_type",
    "canonical_entity_id",
    "confidence",
    "created_at",
    "edge_id",
    "evidence",
    "evidence_json",
    "label",
    "node_id",
    "properties",
    "properties_json",
    "relationship_type",
    "source_node_id",
    "target_node_id",
    "updated_at",
    "weight",
}


def sync_live_graph(
    promotion_batch: PromotionPlan,
    client: Neo4jClient,
    *,
    batch_size: int = 1000,
) -> None:
    """Mirror promoted canonical records into Neo4j with idempotent MERGE queries."""

    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")

    _validate_dynamic_identifiers(promotion_batch)
    query, parameters = _sync_query_and_parameters(promotion_batch, batch_size)
    if query:
        rows = client.execute_write(query, parameters)
        _raise_for_missing_endpoints(rows)


def _sync_query_and_parameters(
    promotion_batch: PromotionPlan,
    batch_size: int,
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    parameters: dict[str, Any] = {}
    clause_index = 0

    rows_by_label: dict[NodeLabel, list[dict[str, Any]]] = defaultdict(list)
    for node_record in promotion_batch.node_records:
        label = _node_label(node_record.label)
        rows_by_label[label].append(_node_row(node_record))

    for label, rows in rows_by_label.items():
        label_identifier = _quote_identifier(label.value)
        for batch in _batched(rows, batch_size):
            parameter_name = f"node_rows_{clause_index}"
            result_name = f"synced_nodes_{clause_index}"
            parameters[parameter_name] = batch
            clauses.append(_node_sync_clause(label_identifier, parameter_name, result_name))
            clause_index += 1

    rows_by_type: dict[RelationshipType, list[dict[str, Any]]] = defaultdict(list)
    for edge_record in promotion_batch.edge_records:
        relationship_type = _relationship_type(edge_record.relationship_type)
        rows_by_type[relationship_type].append(_edge_row(edge_record))

    for relationship_type, rows in rows_by_type.items():
        relationship_identifier = _quote_identifier(relationship_type.value)
        for batch in _batched(rows, batch_size):
            parameter_name = f"edge_rows_{clause_index}"
            result_name = f"synced_edges_{clause_index}"
            parameters[parameter_name] = batch
            clauses.append(_edge_sync_clause(relationship_identifier, parameter_name, result_name))
            clause_index += 1

    assertion_rows = [
        _assertion_row(assertion_record)
        for assertion_record in promotion_batch.assertion_records
    ]
    for batch in _batched(assertion_rows, batch_size):
        parameter_name = f"assertion_source_rows_{clause_index}"
        result_name = f"synced_assertions_{clause_index}"
        parameters[parameter_name] = batch
        clauses.append(_assertion_source_sync_clause(parameter_name, result_name))
        clause_index += 1

    assertion_target_rows = [
        row for row in assertion_rows if row["target_node_id"] is not None
    ]
    for batch in _batched(assertion_target_rows, batch_size):
        parameter_name = f"assertion_target_rows_{clause_index}"
        result_name = f"synced_assertion_targets_{clause_index}"
        parameters[parameter_name] = batch
        clauses.append(_assertion_target_sync_clause(parameter_name, result_name))
        clause_index += 1

    if not clauses:
        return "", {}

    required_endpoint_node_ids = _referenced_endpoint_node_ids(promotion_batch) - {
        node_record.node_id for node_record in promotion_batch.node_records
    }
    parameters["required_endpoint_node_ids"] = sorted(required_endpoint_node_ids)
    return _sync_transaction_query(clauses), parameters


def _sync_transaction_query(clauses: list[str]) -> str:
    mutation_clauses = "\n".join(clauses)
    return f"""
WITH $required_endpoint_node_ids AS required_endpoint_node_ids
CALL {{
    WITH required_endpoint_node_ids
    UNWIND required_endpoint_node_ids AS node_id
    OPTIONAL MATCH (n {{node_id: node_id}})
    WITH node_id, count(n) AS match_count
    WHERE match_count = 0
    RETURN collect(node_id) AS missing_endpoint_node_ids
}}
CALL {{
    WITH missing_endpoint_node_ids
    WITH missing_endpoint_node_ids
    WHERE size(missing_endpoint_node_ids) = 0
{mutation_clauses}
    RETURN 1 AS mutation_applied
    UNION
    WITH missing_endpoint_node_ids
    WITH missing_endpoint_node_ids
    WHERE size(missing_endpoint_node_ids) > 0
    RETURN 0 AS mutation_applied
}}
RETURN missing_endpoint_node_ids, mutation_applied
"""


def _node_sync_clause(
    label_identifier: str,
    parameter_name: str,
    result_name: str,
) -> str:
    return f"""
CALL {{
    UNWIND ${parameter_name} AS row
    MERGE (n:{label_identifier} {{node_id: row.node_id}})
    SET n = row.neo4j_properties
    RETURN count(n) AS {result_name}
}}
"""


def _edge_sync_clause(
    relationship_identifier: str,
    parameter_name: str,
    result_name: str,
) -> str:
    return f"""
CALL {{
    UNWIND ${parameter_name} AS row
    CALL {{
        WITH row
        MATCH ()-[stale {{edge_id: row.edge_id}}]->()
        WHERE startNode(stale).node_id <> row.source_node_id
           OR endNode(stale).node_id <> row.target_node_id
           OR stale.relationship_type <> row.relationship_type
        DELETE stale
        RETURN count(*) AS stale_deleted_count
    }}
    MATCH (source {{node_id: row.source_node_id}})
    MATCH (target {{node_id: row.target_node_id}})
    MERGE (source)-[r:{relationship_identifier} {{edge_id: row.edge_id}}]->(target)
    SET r = row.neo4j_properties
    RETURN count(r) AS {result_name}
}}
"""


def _assertion_source_sync_clause(parameter_name: str, result_name: str) -> str:
    assertion_label = _quote_identifier(NodeLabel.ASSERTION.value)
    assertion_link_type = _quote_identifier(RelationshipType.ASSERTION_LINK.value)
    return f"""
CALL {{
    UNWIND ${parameter_name} AS row
    MATCH (source {{node_id: row.source_node_id}})
    MERGE (assertion:{assertion_label} {{node_id: row.assertion_id}})
    SET assertion.assertion_id = row.assertion_id,
        assertion.assertion_type = row.assertion_type,
        assertion.confidence = row.confidence,
        assertion.evidence_json = row.evidence_json,
        assertion.source_node_id = row.source_node_id,
        assertion.target_node_id = row.target_node_id,
        assertion.created_at = row.created_at
    MERGE (source)-[link:{assertion_link_type} {{
        assertion_id: row.assertion_id,
        role: "source"
    }}]->(assertion)
    SET link.assertion_id = row.assertion_id,
        link.role = "source",
        link.created_at = row.created_at
    RETURN count(assertion) AS {result_name}
}}
"""


def _assertion_target_sync_clause(parameter_name: str, result_name: str) -> str:
    assertion_label = _quote_identifier(NodeLabel.ASSERTION.value)
    assertion_link_type = _quote_identifier(RelationshipType.ASSERTION_LINK.value)
    return f"""
CALL {{
    UNWIND ${parameter_name} AS row
    MATCH (assertion:{assertion_label} {{node_id: row.assertion_id}})
    MATCH (target {{node_id: row.target_node_id}})
    MERGE (assertion)-[link:{assertion_link_type} {{
        assertion_id: row.assertion_id,
        role: "target"
    }}]->(target)
    SET link.assertion_id = row.assertion_id,
        link.role = "target",
        link.created_at = row.created_at
    RETURN count(link) AS {result_name}
}}
"""


def _raise_for_missing_endpoints(rows: list[dict[str, Any]]) -> None:
    if not isinstance(rows, list):
        return
    if not rows:
        raise RuntimeError("live graph sync did not return endpoint validation status")

    raw_missing_node_ids = rows[0].get("missing_endpoint_node_ids", [])
    if not isinstance(raw_missing_node_ids, list):
        raw_missing_node_ids = []
    missing_node_ids = sorted(str(node_id) for node_id in raw_missing_node_ids)
    if missing_node_ids:
        raise ValueError(
            "live graph is missing endpoint nodes: "
            + ", ".join(missing_node_ids),
        )

    if rows[0].get("mutation_applied") == 0:
        raise RuntimeError("live graph sync did not apply mutations")


def _referenced_endpoint_node_ids(promotion_batch: PromotionPlan) -> set[str]:
    node_ids: set[str] = set()
    for edge_record in promotion_batch.edge_records:
        node_ids.add(edge_record.source_node_id)
        node_ids.add(edge_record.target_node_id)
    for assertion_record in promotion_batch.assertion_records:
        node_ids.add(assertion_record.source_node_id)
        if assertion_record.target_node_id is not None:
            node_ids.add(assertion_record.target_node_id)
    return node_ids


def _node_row(node_record: GraphNodeRecord) -> dict[str, Any]:
    safe_properties = _safe_properties(node_record.properties)
    neo4j_properties = {
        "node_id": node_record.node_id,
        "canonical_entity_id": node_record.canonical_entity_id,
        "label": node_record.label,
        "properties_json": _structured_payload_json(node_record.properties),
        "created_at": node_record.created_at,
        "updated_at": node_record.updated_at,
        **safe_properties,
    }
    return {
        "node_id": node_record.node_id,
        "canonical_entity_id": node_record.canonical_entity_id,
        "label": node_record.label,
        "properties_json": neo4j_properties["properties_json"],
        "safe_properties": safe_properties,
        "safe_property_keys": sorted(safe_properties),
        "neo4j_properties": neo4j_properties,
        "created_at": node_record.created_at,
        "updated_at": node_record.updated_at,
    }


def _edge_row(edge_record: GraphEdgeRecord) -> dict[str, Any]:
    safe_properties = _safe_properties(edge_record.properties)
    neo4j_properties = {
        "edge_id": edge_record.edge_id,
        "source_node_id": edge_record.source_node_id,
        "target_node_id": edge_record.target_node_id,
        "relationship_type": edge_record.relationship_type,
        "weight": edge_record.weight,
        "properties_json": _structured_payload_json(edge_record.properties),
        "created_at": edge_record.created_at,
        "updated_at": edge_record.updated_at,
        **safe_properties,
    }
    return {
        "edge_id": edge_record.edge_id,
        "source_node_id": edge_record.source_node_id,
        "target_node_id": edge_record.target_node_id,
        "relationship_type": edge_record.relationship_type,
        "weight": edge_record.weight,
        "properties_json": neo4j_properties["properties_json"],
        "safe_properties": safe_properties,
        "safe_property_keys": sorted(safe_properties),
        "neo4j_properties": neo4j_properties,
        "created_at": edge_record.created_at,
        "updated_at": edge_record.updated_at,
    }


def _assertion_row(assertion_record: GraphAssertionRecord) -> dict[str, Any]:
    return {
        "assertion_id": assertion_record.assertion_id,
        "source_node_id": assertion_record.source_node_id,
        "target_node_id": assertion_record.target_node_id,
        "assertion_type": assertion_record.assertion_type,
        "evidence_json": _structured_payload_json(assertion_record.evidence),
        "confidence": assertion_record.confidence,
        "created_at": assertion_record.created_at,
    }


def _safe_properties(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in properties.items()
        if _is_safe_property_name(key) and _is_neo4j_property_value(value)
    }


def _structured_payload_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        default=_json_default,
        separators=(",", ":"),
        sort_keys=True,
    )


def _json_default(value: Any) -> str:
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return str(value)


def _is_neo4j_property_value(value: Any) -> bool:
    if _is_neo4j_scalar_property_value(value):
        return True
    if isinstance(value, list):
        return _is_neo4j_scalar_list_property_value(value)
    return False


def _is_neo4j_scalar_list_property_value(value: list[Any]) -> bool:
    if not value:
        return True

    first_type = _neo4j_scalar_property_type(value[0])
    if first_type is None:
        return False
    return all(_neo4j_scalar_property_type(item) is first_type for item in value)


def _is_neo4j_scalar_property_value(value: Any) -> bool:
    return _neo4j_scalar_property_type(value) is not None


def _neo4j_scalar_property_type(
    value: Any,
) -> type[str] | type[bool] | type[int] | type[float] | None:
    if isinstance(value, str):
        return str
    if isinstance(value, bool):
        return bool
    if isinstance(value, int):
        return int
    if isinstance(value, float):
        return float
    return None


def _is_safe_property_name(property_name: str) -> bool:
    return (
        property_name not in _RESERVED_PROPERTY_NAMES
        and _SAFE_PROPERTY_NAME_PATTERN.fullmatch(property_name) is not None
    )


def _validate_dynamic_identifiers(promotion_batch: PromotionPlan) -> None:
    for node_record in promotion_batch.node_records:
        _node_label(node_record.label)
    for edge_record in promotion_batch.edge_records:
        _relationship_type(edge_record.relationship_type)


def _node_label(value: str) -> NodeLabel:
    try:
        return NodeLabel(value)
    except ValueError as exc:
        raise ValueError(f"unsupported node label: {value!r}") from exc


def _relationship_type(value: str) -> RelationshipType:
    try:
        return RelationshipType(value)
    except ValueError as exc:
        raise ValueError(f"unsupported relationship type: {value!r}") from exc


def _quote_identifier(identifier: str) -> str:
    return f"`{identifier.replace('`', '``')}`"


def _batched(rows: list[dict[str, Any]], batch_size: int) -> Iterator[list[dict[str, Any]]]:
    for start in range(0, len(rows), batch_size):
        yield rows[start : start + batch_size]
