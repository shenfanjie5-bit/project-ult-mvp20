from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from graph_engine.client import Neo4jClient
from graph_engine.config import load_config_from_env
from graph_engine.live_metrics import read_live_graph_metrics
from graph_engine.models import Neo4jGraphStatus, ReadonlySimulationRequest
from graph_engine.query import simulate_readonly_impact
from graph_engine.schema.manager import SchemaManager
from graph_engine.status import GraphStatusManager
from tests.fakes import InMemoryStatusStore

pytestmark = pytest.mark.skipif(
    os.getenv("NEO4J_PASSWORD") is None,
    reason="NEO4J_PASSWORD is not set; Neo4j simulation integration tests require a database.",
)

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)


def test_readonly_simulation_runs_on_seed_subgraph_without_live_graph_mutation() -> None:
    pytest.importorskip("neo4j")
    prefix = f"sim-{uuid4().hex}"
    node_ids = [
        f"{prefix}-source",
        f"{prefix}-fundamental",
        f"{prefix}-event",
        f"{prefix}-reflexive",
        f"{prefix}-outside-a",
        f"{prefix}-outside-b",
    ]

    with Neo4jClient(load_config_from_env()) as client:
        if not client.verify_connectivity():
            pytest.skip("Neo4j is not reachable with the configured environment.")

        manager = SchemaManager(client)
        manager.apply_schema()
        assert manager.verify_schema() is True

        try:
            _create_simulation_graph(client, prefix)
            before = read_live_graph_metrics(client)
            status_manager = GraphStatusManager(
                InMemoryStatusStore(_ready_status(before, graph_generation_id=41)),
            )
            try:
                result = simulate_readonly_impact(
                    [f"{prefix}-entity-source"],
                    _request(prefix, graph_generation_id=41),
                    client=client,
                    status_manager=status_manager,
                )
            except RuntimeError as exc:
                if str(exc) == "GDS plugin not available":
                    pytest.skip("GDS plugin is not available in the configured Neo4j instance.")
                raise
            after = read_live_graph_metrics(client)
        finally:
            client.execute_write(
                "MATCH (node) WHERE node.node_id IN $node_ids DETACH DELETE node",
                {"node_ids": node_ids},
            )

    assert after == before
    assert result["status"] == "ready"
    assert result["interim"] is True
    assert result["graph_generation_id"] == 41
    assert "impact_snapshot_id" not in result
    assert "snapshot_id" not in result
    edge_channels = {(path["edge_id"], path["channel"]) for path in result["activated_paths"]}
    assert (f"{prefix}-supply-edge", "fundamental") in edge_channels
    assert (f"{prefix}-event-edge", "event") in edge_channels
    assert (f"{prefix}-reflexive-edge", "reflexive") in edge_channels
    assert f"{prefix}-outside-edge" not in {path["edge_id"] for path in result["activated_paths"]}
    assert result["channel_breakdown"]["merged"]["enabled_channels"] == [
        "event",
        "fundamental",
        "reflexive",
    ]


def _create_simulation_graph(client: Neo4jClient, prefix: str) -> None:
    client.execute_write(
        """
CREATE (source:Entity {
    node_id: $source_node_id,
    canonical_entity_id: $source_entity_id,
    label: "Entity",
    properties_json: $source_properties_json
})
CREATE (fundamental:Entity {
    node_id: $fundamental_node_id,
    canonical_entity_id: $fundamental_entity_id,
    label: "Entity",
    properties_json: $fundamental_properties_json
})
CREATE (event:Entity {
    node_id: $event_node_id,
    canonical_entity_id: $event_entity_id,
    label: "Entity",
    properties_json: $event_properties_json
})
CREATE (reflexive:Entity {
    node_id: $reflexive_node_id,
    canonical_entity_id: $reflexive_entity_id,
    label: "Entity",
    properties_json: $reflexive_properties_json
})
CREATE (outside_a:Entity {
    node_id: $outside_a_node_id,
    canonical_entity_id: $outside_a_entity_id,
    label: "Entity",
    properties_json: $outside_a_properties_json
})
CREATE (outside_b:Entity {
    node_id: $outside_b_node_id,
    canonical_entity_id: $outside_b_entity_id,
    label: "Entity",
    properties_json: $outside_b_properties_json
})
CREATE (source)-[:SUPPLY_CHAIN {
    edge_id: $supply_edge_id,
    relationship_type: "SUPPLY_CHAIN",
    weight: 2.0
}]->(fundamental)
CREATE (source)-[:EVENT_IMPACT {
    edge_id: $event_edge_id,
    relationship_type: "EVENT_IMPACT",
    propagation_channel: "event",
    weight: 3.0
}]->(event)
CREATE (source)-[:OWNERSHIP {
    edge_id: $reflexive_edge_id,
    relationship_type: "OWNERSHIP",
    propagation_channel: "reflexive",
    weight: 4.0
}]->(reflexive)
CREATE (outside_a)-[:SUPPLY_CHAIN {
    edge_id: $outside_edge_id,
    relationship_type: "SUPPLY_CHAIN",
    weight: 99.0
}]->(outside_b)
""",
        {
            "event_edge_id": f"{prefix}-event-edge",
            "event_entity_id": f"{prefix}-entity-event",
            "event_node_id": f"{prefix}-event",
            "event_properties_json": '{"name": "event"}',
            "fundamental_entity_id": f"{prefix}-entity-fundamental",
            "fundamental_node_id": f"{prefix}-fundamental",
            "fundamental_properties_json": '{"name": "fundamental"}',
            "outside_a_entity_id": f"{prefix}-entity-outside-a",
            "outside_a_node_id": f"{prefix}-outside-a",
            "outside_a_properties_json": '{"name": "outside-a"}',
            "outside_b_entity_id": f"{prefix}-entity-outside-b",
            "outside_b_node_id": f"{prefix}-outside-b",
            "outside_b_properties_json": '{"name": "outside-b"}',
            "outside_edge_id": f"{prefix}-outside-edge",
            "reflexive_edge_id": f"{prefix}-reflexive-edge",
            "reflexive_entity_id": f"{prefix}-entity-reflexive",
            "reflexive_node_id": f"{prefix}-reflexive",
            "reflexive_properties_json": '{"name": "reflexive"}',
            "source_entity_id": f"{prefix}-entity-source",
            "source_node_id": f"{prefix}-source",
            "source_properties_json": '{"name": "source"}',
            "supply_edge_id": f"{prefix}-supply-edge",
        },
    )


def _request(prefix: str, *, graph_generation_id: int) -> ReadonlySimulationRequest:
    return ReadonlySimulationRequest(
        cycle_id=f"{prefix}-cycle",
        world_state_ref=f"{prefix}-world-state",
        graph_generation_id=graph_generation_id,
        depth=1,
        enabled_channels=["fundamental", "event", "reflexive"],
        channel_multipliers={
            "fundamental": 1.0,
            "event": 1.0,
            "reflexive": 1.0,
        },
        regime_multipliers={
            "fundamental": 1.0,
            "event": 1.0,
            "reflexive": 1.0,
        },
        decay_policy={"default": 1.0},
        regime_context={"source": "integration"},
        result_limit=20,
        max_iterations=5,
        projection_name=f"{prefix}-projection",
    )


def _ready_status(
    metrics: tuple[int, int, dict[str, int], str],
    *,
    graph_generation_id: int,
) -> Neo4jGraphStatus:
    node_count, edge_count, key_label_counts, checksum = metrics
    return Neo4jGraphStatus(
        graph_status="ready",
        graph_generation_id=graph_generation_id,
        node_count=node_count,
        edge_count=edge_count,
        key_label_counts=key_label_counts,
        checksum=checksum,
        last_verified_at=NOW,
        last_reload_at=None,
    )
