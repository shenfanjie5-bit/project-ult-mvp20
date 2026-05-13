from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from graph_engine.client import Neo4jClient
from graph_engine.config import load_config_from_env
from graph_engine.live_metrics import read_live_graph_metrics
from graph_engine.models import GraphSnapshot, Neo4jGraphStatus
from graph_engine.schema.manager import SchemaManager
from graph_engine.snapshots import build_graph_snapshot
from graph_engine.status import GraphStatusManager, check_live_graph_consistency
from tests.fakes import InMemoryStatusStore

pytestmark = pytest.mark.skipif(
    os.getenv("NEO4J_PASSWORD") is None,
    reason="NEO4J_PASSWORD is not set; Neo4j status integration tests require a database.",
)

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)


class StaticSnapshotReader:
    def __init__(self, snapshot: GraphSnapshot) -> None:
        self.snapshot = snapshot

    def read_graph_snapshot(self, snapshot_ref: str) -> GraphSnapshot:
        return self.snapshot


def test_live_graph_consistency_matches_snapshot_and_detects_mutation() -> None:
    pytest.importorskip("neo4j")

    prefix = f"status-{uuid4().hex}"
    source_node_id = f"{prefix}-source"
    target_node_id = f"{prefix}-target"
    edge_id = f"{prefix}-edge"

    with Neo4jClient(load_config_from_env()) as client:
        if not client.verify_connectivity():
            pytest.skip("Neo4j is not reachable with the configured environment.")

        manager = SchemaManager(client)
        manager.apply_schema()
        assert manager.verify_schema() is True

        try:
            client.execute_write(
                """
CREATE (source:Entity {
    node_id: $source_node_id,
    canonical_entity_id: $source_entity_id,
    label: "Entity",
    properties_json: "{}"
})
CREATE (target:Entity {
    node_id: $target_node_id,
    canonical_entity_id: $target_entity_id,
    label: "Entity",
    properties_json: "{}"
})
CREATE (source)-[:SUPPLY_CHAIN {
    edge_id: $edge_id,
    relationship_type: "SUPPLY_CHAIN",
    weight: 1.0,
    properties_json: "{}"
}]->(target)
""",
                {
                    "source_node_id": source_node_id,
                    "source_entity_id": f"{prefix}-entity-source",
                    "target_node_id": target_node_id,
                    "target_entity_id": f"{prefix}-entity-target",
                    "edge_id": edge_id,
                },
            )
            snapshot = build_graph_snapshot(
                "cycle-status",
                11,
                client,
                status_manager=GraphStatusManager(
                    InMemoryStatusStore(_status_for_generation(11)),
                ),
            )
            node_count, edge_count, key_label_counts, checksum = read_live_graph_metrics(client)
            status_manager = GraphStatusManager(
                InMemoryStatusStore(
                    _status_from_metrics(
                        graph_generation_id=11,
                        node_count=node_count,
                        edge_count=edge_count,
                        key_label_counts=key_label_counts,
                        checksum=checksum,
                    )
                ),
                clock=lambda: NOW,
            )
            snapshot_reader = StaticSnapshotReader(snapshot)

            assert (
                check_live_graph_consistency(
                    "snapshot-1",
                    client=client,
                    snapshot_reader=snapshot_reader,
                    status_manager=status_manager,
                )
                is True
            )

            client.execute_write(
                "MATCH (node {node_id: $node_id}) SET node.status_mutation = $value",
                {"node_id": source_node_id, "value": "changed"},
            )

            assert (
                check_live_graph_consistency(
                    "snapshot-1",
                    client=client,
                    snapshot_reader=snapshot_reader,
                    status_manager=status_manager,
                )
                is False
            )
        finally:
            client.execute_write(
                "MATCH (node) WHERE node.node_id IN $node_ids DETACH DELETE node",
                {"node_ids": [source_node_id, target_node_id]},
            )


def _status_from_metrics(
    *,
    graph_generation_id: int,
    node_count: int,
    edge_count: int,
    key_label_counts: dict[str, int],
    checksum: str,
) -> Neo4jGraphStatus:
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


def _status_for_generation(graph_generation_id: int) -> Neo4jGraphStatus:
    return Neo4jGraphStatus(
        graph_status="ready",
        graph_generation_id=graph_generation_id,
        node_count=0,
        edge_count=0,
        key_label_counts={},
        checksum="pending",
        last_verified_at=NOW,
        last_reload_at=None,
    )
