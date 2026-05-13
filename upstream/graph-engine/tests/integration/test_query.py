from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from graph_engine.client import Neo4jClient
from graph_engine.config import load_config_from_env
from graph_engine.models import Neo4jGraphStatus
from graph_engine.query import query_propagation_paths, query_subgraph
from graph_engine.schema.manager import SchemaManager
from graph_engine.status import GraphStatusManager
from tests.fakes import InMemoryStatusStore

pytestmark = pytest.mark.skipif(
    os.getenv("NEO4J_PASSWORD") is None,
    reason="NEO4J_PASSWORD is not set; Neo4j query integration tests require a database.",
)

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)


def test_query_subgraph_seed_lookup_depth_and_empty_results() -> None:
    pytest.importorskip("neo4j")
    prefix = f"query-{uuid4().hex}"
    node_ids = _node_ids(prefix)

    with Neo4jClient(load_config_from_env()) as client:
        if not client.verify_connectivity():
            pytest.skip("Neo4j is not reachable with the configured environment.")

        manager = SchemaManager(client)
        manager.apply_schema()
        assert manager.verify_schema() is True
        status_manager = GraphStatusManager(InMemoryStatusStore(_ready_status()))

        try:
            _create_query_graph(client, prefix)

            by_entity = query_subgraph(
                [f"{prefix}-entity-source", f"{prefix}-entity-source"],
                1,
                client=client,
                status_manager=status_manager,
            )
            by_node = query_subgraph(
                [node_ids["source"]],
                1,
                client=client,
                status_manager=status_manager,
            )
            depth_two = query_subgraph(
                [f"{prefix}-entity-source"],
                2,
                client=client,
                status_manager=status_manager,
            )
            depth_zero = query_subgraph(
                [f"{prefix}-entity-source"],
                0,
                client=client,
                status_manager=status_manager,
            )
            isolated = query_subgraph(
                [f"{prefix}-entity-isolated"],
                2,
                client=client,
                status_manager=status_manager,
            )
            missing = query_subgraph(
                [f"{prefix}-entity-missing"],
                1,
                client=client,
                status_manager=status_manager,
            )
        finally:
            client.execute_write(
                "MATCH (node) WHERE node.node_id IN $node_ids DETACH DELETE node",
                {"node_ids": list(node_ids.values())},
            )

    assert by_entity.graph_generation_id == 17
    assert by_entity.status == "ready"
    assert [node["node_id"] for node in by_entity.subgraph_nodes] == [
        node_ids["middle"],
        node_ids["source"],
    ]
    assert [edge["edge_id"] for edge in by_entity.subgraph_edges] == [f"{prefix}-edge-1"]
    assert [node["node_id"] for node in by_node.subgraph_nodes] == [
        node_ids["middle"],
        node_ids["source"],
    ]
    assert [node["node_id"] for node in depth_two.subgraph_nodes] == [
        node_ids["middle"],
        node_ids["source"],
        node_ids["target"],
    ]
    assert [edge["edge_id"] for edge in depth_two.subgraph_edges] == [
        f"{prefix}-edge-1",
        f"{prefix}-edge-2",
    ]
    assert [node["node_id"] for node in depth_zero.subgraph_nodes] == [node_ids["source"]]
    assert depth_zero.subgraph_edges == []
    assert [node["node_id"] for node in isolated.subgraph_nodes] == [node_ids["isolated"]]
    assert isolated.subgraph_edges == []
    assert missing.subgraph_nodes == []
    assert missing.subgraph_edges == []


def test_query_propagation_paths_uses_effective_channel_filter() -> None:
    pytest.importorskip("neo4j")
    prefix = f"query-path-{uuid4().hex}"
    node_ids = _node_ids(prefix)

    with Neo4jClient(load_config_from_env()) as client:
        if not client.verify_connectivity():
            pytest.skip("Neo4j is not reachable with the configured environment.")

        manager = SchemaManager(client)
        manager.apply_schema()
        assert manager.verify_schema() is True
        status_manager = GraphStatusManager(InMemoryStatusStore(_ready_status()))

        try:
            _create_query_graph(client, prefix)
            all_paths = query_propagation_paths(
                [f"{prefix}-entity-source"],
                2,
                client=client,
                status_manager=status_manager,
            )
            event_paths = query_propagation_paths(
                [f"{prefix}-entity-source"],
                2,
                client=client,
                status_manager=status_manager,
                channels=["event"],
            )
            depth_zero = query_propagation_paths(
                [f"{prefix}-entity-source"],
                0,
                client=client,
                status_manager=status_manager,
            )
        finally:
            client.execute_write(
                "MATCH (node) WHERE node.node_id IN $node_ids DETACH DELETE node",
                {"node_ids": list(node_ids.values())},
            )

    assert all_paths.status == "ready"
    assert all_paths.seed_entities == [f"{prefix}-entity-source"]
    assert all_paths.depth == 2
    assert {(path["edge_id"], path["channel"]) for path in all_paths.paths} == {
        (f"{prefix}-edge-1", "fundamental"),
        (f"{prefix}-edge-2", "event"),
    }
    assert event_paths.paths == [
        {
            "channel": "event",
            "edge_id": f"{prefix}-edge-2",
            "source_node_id": node_ids["middle"],
            "target_node_id": node_ids["target"],
            "relationship_type": "EVENT_IMPACT",
            "score": 0.4,
            "path_length": 2,
            "properties": {"kind": "event"},
        }
    ]
    assert depth_zero.paths == []


def _create_query_graph(client: Neo4jClient, prefix: str) -> None:
    node_ids = _node_ids(prefix)
    client.execute_write(
        """
CREATE (source:Entity {
    node_id: $source_node_id,
    canonical_entity_id: $source_entity_id,
    label: "Entity",
    properties_json: $source_properties_json
})
CREATE (middle:Entity {
    node_id: $middle_node_id,
    canonical_entity_id: $middle_entity_id,
    label: "Entity",
    properties_json: $middle_properties_json
})
CREATE (target:Entity {
    node_id: $target_node_id,
    canonical_entity_id: $target_entity_id,
    label: "Entity",
    properties_json: $target_properties_json
})
CREATE (isolated:Entity {
    node_id: $isolated_node_id,
    canonical_entity_id: $isolated_entity_id,
    label: "Entity",
    properties_json: $isolated_properties_json
})
CREATE (source)-[:SUPPLY_CHAIN {
    edge_id: $edge_one_id,
    relationship_type: "SUPPLY_CHAIN",
    weight: 0.6,
    properties_json: $edge_one_properties_json
}]->(middle)
CREATE (middle)-[:EVENT_IMPACT {
    edge_id: $edge_two_id,
    relationship_type: "EVENT_IMPACT",
    propagation_channel: "event",
    weight: 0.4,
    properties_json: $edge_two_properties_json
}]->(target)
""",
        {
            "edge_one_id": f"{prefix}-edge-1",
            "edge_one_properties_json": '{"kind": "supply"}',
            "edge_two_id": f"{prefix}-edge-2",
            "edge_two_properties_json": '{"kind": "event"}',
            "isolated_entity_id": f"{prefix}-entity-isolated",
            "isolated_node_id": node_ids["isolated"],
            "isolated_properties_json": '{"name": "isolated"}',
            "middle_entity_id": f"{prefix}-entity-middle",
            "middle_node_id": node_ids["middle"],
            "middle_properties_json": '{"name": "middle"}',
            "source_entity_id": f"{prefix}-entity-source",
            "source_node_id": node_ids["source"],
            "source_properties_json": '{"name": "source"}',
            "target_entity_id": f"{prefix}-entity-target",
            "target_node_id": node_ids["target"],
            "target_properties_json": '{"name": "target"}',
        },
    )


def _node_ids(prefix: str) -> dict[str, str]:
    return {
        "isolated": f"{prefix}-isolated",
        "middle": f"{prefix}-middle",
        "source": f"{prefix}-source",
        "target": f"{prefix}-target",
    }


def _ready_status() -> Neo4jGraphStatus:
    return Neo4jGraphStatus(
        graph_status="ready",
        graph_generation_id=17,
        node_count=4,
        edge_count=2,
        key_label_counts={"Entity": 4},
        checksum="query-ready",
        last_verified_at=NOW,
        last_reload_at=None,
    )
