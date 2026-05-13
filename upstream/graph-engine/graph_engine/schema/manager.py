"""Schema lifecycle operations for the Neo4j live graph."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any

from graph_engine.client import Neo4jClient
from graph_engine.schema.definitions import NodeLabel
from graph_engine.schema.indexes import get_constraint_statements, get_index_statements

_SCHEMA_NAME_PATTERN = re.compile(r"^CREATE\s+(?:INDEX|CONSTRAINT)\s+(\S+)\s+", re.IGNORECASE)
_NODE_INDEX_PATTERN = re.compile(
    r"^CREATE\s+INDEX\s+(\S+)\s+IF\s+NOT\s+EXISTS\s+"
    r"FOR\s+\(\w+:([^)]+)\)\s+ON\s+\(\w+\.([^)]+)\)$",
    re.IGNORECASE,
)
_RELATIONSHIP_INDEX_PATTERN = re.compile(
    r"^CREATE\s+INDEX\s+(\S+)\s+IF\s+NOT\s+EXISTS\s+"
    r"FOR\s+\(\)-\[\w+:([^\]]+)\]-\(\)\s+ON\s+\(\w+\.([^)]+)\)$",
    re.IGNORECASE,
)
_NODE_UNIQUENESS_CONSTRAINT_PATTERN = re.compile(
    r"^CREATE\s+CONSTRAINT\s+(\S+)\s+IF\s+NOT\s+EXISTS\s+"
    r"FOR\s+\(\w+:([^)]+)\)\s+REQUIRE\s+\w+\.([^\s]+)\s+IS\s+UNIQUE$",
    re.IGNORECASE,
)
_GRAPH_ENGINE_SCHEMA_NAME_PREFIX = "graph_"
DROP_ALL_CONFIRMATION_TOKEN = "DROP_GRAPH_ENGINE_LIVE_GRAPH"
_DROP_ALL_TEST_MODE_ENV = "GRAPH_ENGINE_SCHEMA_MANAGER_TEST_MODE"


class SchemaManager:
    """Apply, verify, and clear the Neo4j schema used by graph-engine."""

    def __init__(self, client: Neo4jClient) -> None:
        self.client = client

    def apply_schema(self) -> None:
        """Create all required constraints and indexes using idempotent DDL."""

        for statement in [*get_constraint_statements(), *get_index_statements()]:
            self.client.execute_write(statement)

    def verify_schema(self) -> bool:
        """Check that every required schema object exists with the expected shape."""

        try:
            constraint_rows = self.client.execute_read(
                "SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, "
                "properties RETURN name, type, entityType, labelsOrTypes, properties"
            )
            index_rows = self.client.execute_read(
                "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, "
                "properties RETURN name, type, entityType, labelsOrTypes, properties"
            )
        except Exception:  # noqa: BLE001 - verification should fail closed.
            return False

        actual_constraints = _schema_metadata_by_name(constraint_rows)
        actual_indexes = _schema_metadata_by_name(index_rows)

        return _expected_constraint_metadata().items() <= actual_constraints.items() and (
            _expected_index_metadata().items() <= actual_indexes.items()
        )

    def drop_all(
        self,
        *,
        confirmation_token: str | None = None,
        graph_status: object | None = None,
        test_mode: bool = False,
    ) -> None:
        """Delete graph-engine data and schema after explicit destructive gating."""

        _assert_drop_all_allowed(
            confirmation_token=confirmation_token,
            graph_status=graph_status,
            test_mode=test_mode,
        )

        for label in NodeLabel:
            self.client.execute_write(
                f"MATCH (n:{_quote_identifier(label.value)}) DETACH DELETE n"
            )

        constraint_rows = self.client.execute_read("SHOW CONSTRAINTS YIELD name RETURN name")
        for constraint_name in _extract_schema_names(constraint_rows):
            if not _is_graph_engine_schema_name(constraint_name):
                continue
            self.client.execute_write(
                f"DROP CONSTRAINT {_quote_identifier(constraint_name)} IF EXISTS"
            )

        index_rows = self.client.execute_read(
            "SHOW INDEXES YIELD name, type RETURN name, type"
        )
        for row in index_rows:
            index_name = row.get("name")
            index_type = row.get("type")
            if (
                isinstance(index_name, str)
                and index_type != "LOOKUP"
                and _is_graph_engine_schema_name(index_name)
            ):
                self.client.execute_write(f"DROP INDEX {_quote_identifier(index_name)} IF EXISTS")


def _assert_drop_all_allowed(
    *,
    confirmation_token: str | None,
    graph_status: object | None,
    test_mode: bool,
) -> None:
    if confirmation_token != DROP_ALL_CONFIRMATION_TOKEN:
        raise PermissionError(
            "drop_all requires confirmation_token="
            f"{DROP_ALL_CONFIRMATION_TOKEN!r}",
        )

    if _graph_status_value(graph_status) == "rebuilding":
        return

    if test_mode or os.getenv(_DROP_ALL_TEST_MODE_ENV) == "1":
        return

    raise PermissionError(
        "drop_all requires graph_status='rebuilding' or explicit test mode",
    )


def _graph_status_value(graph_status: object | None) -> str | None:
    if isinstance(graph_status, str):
        return graph_status
    if isinstance(graph_status, Mapping):
        value = graph_status.get("graph_status")
        return value if isinstance(value, str) else None

    value = getattr(graph_status, "graph_status", None)
    return value if isinstance(value, str) else None


def _extract_schema_names(rows: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for row in rows:
        name = row.get("name")
        if isinstance(name, str):
            names.add(name)

        collected_names = row.get("names")
        if isinstance(collected_names, list):
            names.update(item for item in collected_names if isinstance(item, str))
    return names


def _schema_metadata_by_name(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = _schema_metadata(row)
        if entry is not None:
            metadata[entry["name"]] = entry
    return metadata


def _schema_metadata(row: Mapping[str, Any]) -> dict[str, Any] | None:
    name = row.get("name")
    schema_type = row.get("type")
    entity_type = row.get("entityType")
    labels_or_types = _string_tuple(row.get("labelsOrTypes"))
    properties = _string_tuple(row.get("properties"))

    if not isinstance(name, str) or not isinstance(schema_type, str):
        return None
    if not isinstance(entity_type, str):
        return None
    if labels_or_types is None or properties is None:
        return None

    return {
        "name": name,
        "type": schema_type.upper(),
        "entityType": entity_type.upper(),
        "labelsOrTypes": labels_or_types,
        "properties": properties,
    }


def _expected_index_metadata() -> dict[str, dict[str, Any]]:
    return {
        metadata["name"]: metadata
        for metadata in (
            _parse_index_statement(statement) for statement in get_index_statements()
        )
    }


def _expected_constraint_metadata() -> dict[str, dict[str, Any]]:
    return {
        metadata["name"]: metadata
        for metadata in (
            _parse_constraint_statement(statement)
            for statement in get_constraint_statements()
        )
    }


def _parse_index_statement(statement: str) -> dict[str, Any]:
    node_match = _NODE_INDEX_PATTERN.match(statement)
    if node_match is not None:
        name, label, property_name = node_match.groups()
        return {
            "name": name,
            "type": "RANGE",
            "entityType": "NODE",
            "labelsOrTypes": (label,),
            "properties": (property_name,),
        }

    relationship_match = _RELATIONSHIP_INDEX_PATTERN.match(statement)
    if relationship_match is not None:
        name, relationship_type, property_name = relationship_match.groups()
        return {
            "name": name,
            "type": "RANGE",
            "entityType": "RELATIONSHIP",
            "labelsOrTypes": (relationship_type,),
            "properties": (property_name,),
        }

    raise ValueError(f"unsupported index statement: {statement}")


def _parse_constraint_statement(statement: str) -> dict[str, Any]:
    match = _NODE_UNIQUENESS_CONSTRAINT_PATTERN.match(statement)
    if match is None:
        raise ValueError(f"unsupported constraint statement: {statement}")

    name, label, property_name = match.groups()
    return {
        "name": name,
        "type": "UNIQUENESS",
        "entityType": "NODE",
        "labelsOrTypes": (label,),
        "properties": (property_name,),
    }


def _string_tuple(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, (list, tuple)):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def _extract_statement_name(statement: str) -> str:
    match = _SCHEMA_NAME_PATTERN.match(statement)
    if match is None:
        raise ValueError(f"schema statement does not include a name: {statement}")
    return match.group(1)


def _is_graph_engine_schema_name(name: str) -> bool:
    return name.startswith(_GRAPH_ENGINE_SCHEMA_NAME_PREFIX)


def _quote_identifier(identifier: str) -> str:
    return f"`{identifier.replace('`', '``')}`"
