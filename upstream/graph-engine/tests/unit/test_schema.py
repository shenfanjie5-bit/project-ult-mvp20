from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from graph_engine.schema.definitions import NodeLabel, RelationshipType
from graph_engine.schema.indexes import get_constraint_statements, get_index_statements
from graph_engine.schema.manager import DROP_ALL_CONFIRMATION_TOKEN, SchemaManager


def test_node_label_enum_covers_core_labels() -> None:
    assert {label.name for label in NodeLabel} == {
        "ENTITY",
        "SECTOR",
        "INDUSTRY",
        "REGION",
        "EVENT",
        "ASSERTION",
    }


def test_relationship_type_enum_covers_core_relationships() -> None:
    assert {relationship.name for relationship in RelationshipType} == {
        "SUPPLY_CHAIN",
        "OWNERSHIP",
        "INDUSTRY_CHAIN",
        "SECTOR_MEMBERSHIP",
        "EVENT_IMPACT",
        "ASSERTION_LINK",
        "CO_HOLDING",
        "NORTHBOUND_HOLD",
    }
    assert "TOP_SHAREHOLDER" not in {relationship.name for relationship in RelationshipType}
    assert "PLEDGE_STATUS" not in {relationship.name for relationship in RelationshipType}
    assert "MAJOR_CUSTOMER" not in {relationship.name for relationship in RelationshipType}
    assert "MAJOR_SUPPLIER" not in {relationship.name for relationship in RelationshipType}


def test_get_index_statements_returns_idempotent_cypher() -> None:
    statements = get_index_statements()

    assert len(statements) >= 4
    assert all(statement.startswith("CREATE INDEX ") for statement in statements)
    assert all(" IF NOT EXISTS " in statement for statement in statements)
    assert all(" ON " in statement for statement in statements)


def test_get_constraint_statements_returns_idempotent_cypher() -> None:
    statements = get_constraint_statements()

    assert len(statements) >= 2
    assert all(statement.startswith("CREATE CONSTRAINT ") for statement in statements)
    assert all(" IF NOT EXISTS " in statement for statement in statements)
    assert any("node_id IS UNIQUE" in statement for statement in statements)


def test_schema_manager_apply_schema_executes_constraints_then_indexes(
    mock_neo4j_client: MagicMock,
) -> None:
    manager = SchemaManager(mock_neo4j_client)

    manager.apply_schema()

    executed = [call.args[0] for call in mock_neo4j_client.execute_write.call_args_list]
    assert executed == [*get_constraint_statements(), *get_index_statements()]


def test_schema_manager_verify_schema_returns_true_when_required_names_exist(
    mock_neo4j_client: MagicMock,
) -> None:
    mock_neo4j_client.execute_read.side_effect = [
        _constraint_metadata_rows(),
        _index_metadata_rows(),
    ]

    assert SchemaManager(mock_neo4j_client).verify_schema() is True


def test_schema_manager_verify_schema_returns_false_when_required_structure_differs(
    mock_neo4j_client: MagicMock,
) -> None:
    mismatched_indexes = _index_metadata_rows()
    mismatched_indexes[0] = {**mismatched_indexes[0], "properties": ["wrong_property"]}
    mock_neo4j_client.execute_read.side_effect = [
        _constraint_metadata_rows(),
        mismatched_indexes,
    ]

    assert SchemaManager(mock_neo4j_client).verify_schema() is False


def test_schema_manager_verify_schema_returns_false_on_read_error(
    mock_neo4j_client: MagicMock,
) -> None:
    mock_neo4j_client.execute_read.side_effect = RuntimeError("unavailable")

    assert SchemaManager(mock_neo4j_client).verify_schema() is False


def test_schema_manager_drop_all_requires_confirmation(
    mock_neo4j_client: MagicMock,
) -> None:
    with pytest.raises(PermissionError, match="confirmation_token"):
        SchemaManager(mock_neo4j_client).drop_all()

    mock_neo4j_client.execute_write.assert_not_called()
    mock_neo4j_client.execute_read.assert_not_called()


def test_schema_manager_drop_all_requires_rebuild_state_or_test_mode(
    mock_neo4j_client: MagicMock,
) -> None:
    with pytest.raises(PermissionError, match="rebuilding"):
        SchemaManager(mock_neo4j_client).drop_all(
            confirmation_token=DROP_ALL_CONFIRMATION_TOKEN,
            graph_status="ready",
        )

    mock_neo4j_client.execute_write.assert_not_called()
    mock_neo4j_client.execute_read.assert_not_called()


def test_schema_manager_drop_all_deletes_graph_engine_data_and_schema(
    mock_neo4j_client: MagicMock,
) -> None:
    mock_neo4j_client.execute_read.side_effect = [
        [{"name": "graph_constraint_one"}, {"name": "other_constraint"}],
        [
            {"name": "graph_index_one", "type": "RANGE"},
            {"name": "other_index", "type": "RANGE"},
            {"name": "graph_lookup", "type": "LOOKUP"},
        ],
    ]

    SchemaManager(mock_neo4j_client).drop_all(
        confirmation_token=DROP_ALL_CONFIRMATION_TOKEN,
        graph_status={"graph_status": "rebuilding"},
    )

    executed = [call.args[0] for call in mock_neo4j_client.execute_write.call_args_list]
    assert executed == [
        *(f"MATCH (n:`{label.value}`) DETACH DELETE n" for label in NodeLabel),
        "DROP CONSTRAINT `graph_constraint_one` IF EXISTS",
        "DROP INDEX `graph_index_one` IF EXISTS",
    ]


def test_schema_manager_drop_all_allows_explicit_test_mode(
    mock_neo4j_client: MagicMock,
) -> None:
    mock_neo4j_client.execute_read.side_effect = [[], []]

    SchemaManager(mock_neo4j_client).drop_all(
        confirmation_token=DROP_ALL_CONFIRMATION_TOKEN,
        test_mode=True,
    )

    executed = [call.args[0] for call in mock_neo4j_client.execute_write.call_args_list]
    assert executed == [
        *(f"MATCH (n:`{label.value}`) DETACH DELETE n" for label in NodeLabel),
    ]


def _constraint_metadata_rows() -> list[dict[str, object]]:
    return [
        {
            "name": f"graph_{label.value.lower()}_node_id_unique",
            "type": "UNIQUENESS",
            "entityType": "NODE",
            "labelsOrTypes": [label.value],
            "properties": ["node_id"],
        }
        for label in NodeLabel
    ]


def _index_metadata_rows() -> list[dict[str, object]]:
    return [
        {
            "name": "graph_entity_canonical_entity_id_index",
            "type": "RANGE",
            "entityType": "NODE",
            "labelsOrTypes": ["Entity"],
            "properties": ["canonical_entity_id"],
        },
        {
            "name": "graph_entity_label_index",
            "type": "RANGE",
            "entityType": "NODE",
            "labelsOrTypes": ["Entity"],
            "properties": ["label"],
        },
        {
            "name": "graph_event_cycle_id_index",
            "type": "RANGE",
            "entityType": "NODE",
            "labelsOrTypes": ["Event"],
            "properties": ["cycle_id"],
        },
        {
            "name": "graph_assertion_type_index",
            "type": "RANGE",
            "entityType": "NODE",
            "labelsOrTypes": ["Assertion"],
            "properties": ["assertion_type"],
        },
        {
            "name": "graph_supply_chain_weight_index",
            "type": "RANGE",
            "entityType": "RELATIONSHIP",
            "labelsOrTypes": ["SUPPLY_CHAIN"],
            "properties": ["weight"],
        },
        {
            "name": "graph_event_impact_confidence_index",
            "type": "RANGE",
            "entityType": "RELATIONSHIP",
            "labelsOrTypes": ["EVENT_IMPACT"],
            "properties": ["confidence"],
        },
    ]
