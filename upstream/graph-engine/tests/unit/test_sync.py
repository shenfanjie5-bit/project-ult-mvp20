from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from graph_engine.client import Neo4jClient
from graph_engine.models import GraphAssertionRecord, GraphEdgeRecord, GraphNodeRecord, PromotionPlan
from graph_engine.schema.definitions import NodeLabel, RelationshipType
from graph_engine.sync import sync_live_graph

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)


def test_sync_live_graph_uses_idempotent_merge_queries() -> None:
    client = MagicMock(spec=Neo4jClient)
    plan = _promotion_plan(
        node_records=[
            _node_record("node-1", "entity-1"),
            _node_record("node-2", "entity-2"),
        ],
        edge_records=[_edge_record()],
        assertion_records=[_assertion_record()],
    )

    sync_live_graph(plan, client)

    queries = [call.args[0] for call in client.execute_write.call_args_list]
    assert len(queries) == 1
    assert any("MERGE" in query for query in queries)
    assert any("MERGE (n:`Entity` {node_id: row.node_id})" in query for query in queries)
    assert any(
        "MERGE (source)-[r:`SUPPLY_CHAIN` {edge_id: row.edge_id}]->(target)" in query
        for query in queries
    )
    assert any(
        "MERGE (assertion:`Assertion` {node_id: row.assertion_id})" in query
        for query in queries
    )
    assert queries[0].count("`ASSERTION_LINK`") == 2
    assert "n.properties = row.properties" not in queries[0]
    assert "r.properties = row.properties" not in queries[0]
    assert "assertion.evidence = row.evidence" not in queries[0]
    assert "SET n = row.neo4j_properties" in queries[0]
    assert "SET r = row.neo4j_properties" in queries[0]
    assert "assertion.evidence_json = row.evidence_json" in queries[0]
    assert "SET n[stale_property_key] = null" not in queries[0]
    assert "SET r[stale_property_key] = null" not in queries[0]
    assert "NOT property_key IN row.safe_property_keys" not in queries[0]
    assert "reserved_property_names" not in client.execute_write.call_args.args[1]


def test_sync_live_graph_batches_rows_by_node_label() -> None:
    client = MagicMock(spec=Neo4jClient)
    plan = _promotion_plan(
        node_records=[
            _node_record("node-1", "entity-1"),
            _node_record("node-2", "entity-2"),
        ],
    )

    sync_live_graph(plan, client, batch_size=1)

    assert client.execute_write.call_count == 1
    parameters = client.execute_write.call_args.args[1]
    row_batches = [parameters["node_rows_0"], parameters["node_rows_1"]]
    assert row_batches == [
        [_expected_node_row("node-1", "entity-1")],
        [_expected_node_row("node-2", "entity-2")],
    ]


def test_sync_live_graph_batches_edges_by_relationship_type() -> None:
    client = MagicMock(spec=Neo4jClient)
    plan = _promotion_plan(
        edge_records=[
            _edge_record("edge-1", relationship_type=RelationshipType.SUPPLY_CHAIN.value),
            _edge_record("edge-2", relationship_type=RelationshipType.OWNERSHIP.value),
        ],
    )

    sync_live_graph(plan, client)

    queries = [call.args[0] for call in client.execute_write.call_args_list]
    assert len(queries) == 1
    assert any("[r:`SUPPLY_CHAIN`" in query for query in queries)
    assert any("[r:`OWNERSHIP`" in query for query in queries)
    assert client.execute_write.call_args.args[1]["required_endpoint_node_ids"] == [
        "node-1",
        "node-2",
    ]
    client.execute_read.assert_not_called()


def test_sync_live_graph_rejects_missing_edge_endpoints_from_write_transaction() -> None:
    client = MagicMock(spec=Neo4jClient)
    client.execute_write.return_value = [
        {"missing_endpoint_node_ids": ["node-1"], "mutation_applied": 0},
    ]
    plan = _promotion_plan(edge_records=[_edge_record()])

    with pytest.raises(ValueError, match="node-1"):
        sync_live_graph(plan, client)

    client.execute_read.assert_not_called()
    client.execute_write.assert_called_once()
    assert "MATCH (n {node_id: node_id})" in client.execute_write.call_args.args[0]


def test_sync_live_graph_rejects_missing_external_endpoints_before_mutation_branch() -> None:
    client = MagicMock(spec=Neo4jClient)
    client.execute_write.return_value = [
        {"missing_endpoint_node_ids": ["node-2"], "mutation_applied": 0},
    ]
    plan = _promotion_plan(
        node_records=[_node_record("node-1", "entity-1")],
        edge_records=[_edge_record()],
    )

    with pytest.raises(ValueError, match="node-2"):
        sync_live_graph(plan, client)

    client.execute_read.assert_not_called()
    client.execute_write.assert_called_once()
    query = client.execute_write.call_args.args[0]
    parameters = client.execute_write.call_args.args[1]
    assert parameters["required_endpoint_node_ids"] == ["node-2"]
    assert query.index("WHERE size(missing_endpoint_node_ids) = 0") < query.index(
        "MERGE (n:`Entity`",
    )


def test_sync_live_graph_rejects_missing_assertion_endpoints_from_write_transaction() -> None:
    client = MagicMock(spec=Neo4jClient)
    client.execute_write.return_value = [
        {"missing_endpoint_node_ids": ["node-2"], "mutation_applied": 0},
    ]
    plan = _promotion_plan(assertion_records=[_assertion_record()])

    with pytest.raises(ValueError, match="node-2"):
        sync_live_graph(plan, client)

    client.execute_read.assert_not_called()
    client.execute_write.assert_called_once()


def test_sync_live_graph_deletes_stale_edge_endpoint_before_merge() -> None:
    client = MagicMock(spec=Neo4jClient)
    plan = _promotion_plan(
        edge_records=[
            _edge_record("edge-1", target_node_id="node-3"),
        ],
    )

    sync_live_graph(plan, client)

    queries = [call.args[0] for call in client.execute_write.call_args_list]
    assert len(queries) == 1
    assert "MATCH ()-[stale {edge_id: row.edge_id}]->()" in queries[0]
    assert "DELETE stale" in queries[0]
    assert (
        "MERGE (source)-[r:`SUPPLY_CHAIN` {edge_id: row.edge_id}]->(target)"
        in queries[0]
    )
    assert queries[0].index("DELETE stale") < queries[0].index(
        "MERGE (source)-[r:`SUPPLY_CHAIN`",
    )
    client.execute_read.assert_not_called()


def test_sync_live_graph_does_not_split_stale_delete_and_replacement_writes() -> None:
    client = MagicMock(spec=Neo4jClient)
    client.execute_write.side_effect = RuntimeError("replacement failed")
    plan = _promotion_plan(
        edge_records=[
            _edge_record("edge-1", target_node_id="node-3"),
        ],
    )

    with pytest.raises(RuntimeError, match="replacement failed"):
        sync_live_graph(plan, client)

    assert client.execute_write.call_count == 1
    query = client.execute_write.call_args.args[0]
    assert "DELETE stale" in query
    assert "MERGE (source)-[r:`SUPPLY_CHAIN` {edge_id: row.edge_id}]->(target)" in query
    client.execute_read.assert_not_called()


def test_sync_live_graph_expands_only_safe_properties() -> None:
    client = MagicMock(spec=Neo4jClient)
    properties = {
        "ticker": "ULT",
        "tags": ["supply-chain", "issuer"],
        "metadata": {"risk_level": "high"},
        "bad-key": "ignored",
        "nested_list": [{"source": "filing"}],
        "node_id": "not-overwritten",
        "properties_json": "not-overwritten",
        "nullable": None,
    }
    plan = _promotion_plan(
        node_records=[
            _node_record(
                "node-1",
                "entity-1",
                properties=properties,
            )
        ],
    )

    sync_live_graph(plan, client)

    rows = client.execute_write.call_args.args[1]["node_rows_0"]
    assert rows[0]["properties_json"] == _json_payload(properties)
    assert rows[0]["safe_properties"] == {
        "tags": ["supply-chain", "issuer"],
        "ticker": "ULT",
    }
    assert rows[0]["neo4j_properties"] == {
        "node_id": "node-1",
        "canonical_entity_id": "entity-1",
        "label": NodeLabel.ENTITY.value,
        "properties_json": _json_payload(properties),
        "created_at": NOW,
        "updated_at": NOW,
        "tags": ["supply-chain", "issuer"],
        "ticker": "ULT",
    }
    assert rows[0]["safe_property_keys"] == ["tags", "ticker"]
    assert "properties" not in rows[0]


def test_sync_live_graph_routes_neo4j_incompatible_lists_to_json_only() -> None:
    client = MagicMock(spec=Neo4jClient)
    properties = {
        "empty_list": [],
        "string_aliases": ["ULT", "ULT-A"],
        "int_scores": [1, 2],
        "bool_flags": [True, False],
        "mixed_aliases": ["ULT", 123],
        "mixed_bool_int": [True, 1],
        "nullable_aliases": ["ULT", None],
    }
    plan = _promotion_plan(
        node_records=[
            _node_record(
                "node-1",
                "entity-1",
                properties=properties,
            )
        ],
    )

    sync_live_graph(plan, client)

    row = client.execute_write.call_args.args[1]["node_rows_0"][0]
    assert row["properties_json"] == _json_payload(properties)
    assert row["safe_properties"] == {
        "bool_flags": [True, False],
        "empty_list": [],
        "int_scores": [1, 2],
        "string_aliases": ["ULT", "ULT-A"],
    }
    assert row["safe_property_keys"] == [
        "bool_flags",
        "empty_list",
        "int_scores",
        "string_aliases",
    ]


def test_sync_live_graph_serializes_edge_properties_and_assertion_evidence() -> None:
    client = MagicMock(spec=Neo4jClient)
    edge_properties = {
        "source": "filing",
        "details": {"form": "10-K"},
        "confidence_band": ["medium", "high"],
        "evidence_refs": ["fact-edge-1"],
        "properties_json": "not-overwritten",
    }
    assertion_evidence = {
        "source": "contract",
        "documents": [{"document_id": "doc-1"}],
    }
    plan = _promotion_plan(
        edge_records=[_edge_record(properties=edge_properties)],
        assertion_records=[_assertion_record(evidence=assertion_evidence)],
    )

    sync_live_graph(plan, client)

    parameters = client.execute_write.call_args.args[1]
    edge_row = parameters["edge_rows_0"][0]
    assertion_row = parameters["assertion_source_rows_1"][0]
    assert edge_row["properties_json"] == _json_payload(edge_properties)
    assert edge_row["safe_properties"] == {
        "confidence_band": ["medium", "high"],
        "evidence_refs": ["fact-edge-1"],
        "source": "filing",
    }
    assert edge_row["neo4j_properties"] == {
        "edge_id": "edge-1",
        "source_node_id": "node-1",
        "target_node_id": "node-2",
        "relationship_type": RelationshipType.SUPPLY_CHAIN.value,
        "weight": 0.7,
        "properties_json": _json_payload(edge_properties),
        "created_at": NOW,
        "updated_at": NOW,
        "confidence_band": ["medium", "high"],
        "evidence_refs": ["fact-edge-1"],
        "source": "filing",
    }
    assert edge_row["safe_property_keys"] == [
        "confidence_band",
        "evidence_refs",
        "source",
    ]
    assert "properties" not in edge_row
    assert assertion_row["evidence_json"] == _json_payload(assertion_evidence)
    assert "evidence" not in assertion_row


def test_sync_live_graph_rejects_invalid_node_label_before_writing() -> None:
    client = MagicMock(spec=Neo4jClient)
    plan = _promotion_plan(
        node_records=[_node_record("node-1", "entity-1", label="BadLabel")],
    )

    with pytest.raises(ValueError, match="unsupported node label"):
        sync_live_graph(plan, client)

    client.execute_write.assert_not_called()


def test_sync_live_graph_rejects_invalid_relationship_type_before_writing() -> None:
    client = MagicMock(spec=Neo4jClient)
    plan = _promotion_plan(
        node_records=[_node_record("node-1", "entity-1")],
        edge_records=[_edge_record(relationship_type="BAD_TYPE")],
    )

    with pytest.raises(ValueError, match="unsupported relationship type"):
        sync_live_graph(plan, client)

    client.execute_write.assert_not_called()


def test_sync_live_graph_rejects_invalid_batch_size() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        sync_live_graph(_promotion_plan(), MagicMock(spec=Neo4jClient), batch_size=0)


def _promotion_plan(
    *,
    node_records: list[GraphNodeRecord] | None = None,
    edge_records: list[GraphEdgeRecord] | None = None,
    assertion_records: list[GraphAssertionRecord] | None = None,
) -> PromotionPlan:
    return PromotionPlan(
        cycle_id="cycle-1",
        selection_ref="selection-1",
        delta_ids=["delta-1"],
        node_records=node_records or [],
        edge_records=edge_records or [],
        assertion_records=assertion_records or [],
        created_at=NOW,
    )


def _node_record(
    node_id: str,
    canonical_entity_id: str,
    *,
    label: str = NodeLabel.ENTITY.value,
    properties: dict[str, object] | None = None,
) -> GraphNodeRecord:
    return GraphNodeRecord(
        node_id=node_id,
        canonical_entity_id=canonical_entity_id,
        label=label,
        properties=properties or {"ticker": "ULT"},
        created_at=NOW,
        updated_at=NOW,
    )


def _edge_record(
    edge_id: str = "edge-1",
    *,
    source_node_id: str = "node-1",
    target_node_id: str = "node-2",
    relationship_type: str = RelationshipType.SUPPLY_CHAIN.value,
    properties: dict[str, object] | None = None,
) -> GraphEdgeRecord:
    resolved_properties = (
        {"source": "filing", "evidence_refs": [f"fact-{edge_id}"]}
        if properties is None
        else properties
    )
    return GraphEdgeRecord(
        edge_id=edge_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relationship_type=relationship_type,
        properties=resolved_properties,
        weight=0.7,
        created_at=NOW,
        updated_at=NOW,
    )


def _assertion_record(
    *,
    evidence: dict[str, object] | None = None,
) -> GraphAssertionRecord:
    return GraphAssertionRecord(
        assertion_id="assertion-1",
        source_node_id="node-1",
        target_node_id="node-2",
        assertion_type="risk",
        evidence=evidence or {"source": "contract"},
        confidence=0.8,
        created_at=NOW,
    )


def _expected_node_row(node_id: str, canonical_entity_id: str) -> dict[str, object]:
    properties_json = _json_payload({"ticker": "ULT"})
    return {
        "node_id": node_id,
        "canonical_entity_id": canonical_entity_id,
        "label": NodeLabel.ENTITY.value,
        "properties_json": properties_json,
        "safe_properties": {"ticker": "ULT"},
        "safe_property_keys": ["ticker"],
        "neo4j_properties": {
            "node_id": node_id,
            "canonical_entity_id": canonical_entity_id,
            "label": NodeLabel.ENTITY.value,
            "properties_json": properties_json,
            "created_at": NOW,
            "updated_at": NOW,
            "ticker": "ULT",
        },
        "created_at": NOW,
        "updated_at": NOW,
    }


def _json_payload(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)
