from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from graph_engine.client import Neo4jClient
from graph_engine.config import load_config_from_env
from graph_engine.live_metrics import read_live_graph_metrics
from graph_engine.models import (
    GraphEdgeRecord,
    GraphImpactSnapshot,
    GraphNodeRecord,
    GraphSnapshot,
    Neo4jGraphStatus,
    PromotionPlan,
)
from graph_engine.schema.definitions import NodeLabel, RelationshipType
from graph_engine.schema.manager import SchemaManager
from graph_engine.snapshots import compute_graph_snapshots
from graph_engine.status import GraphStatusManager
from graph_engine.sync import sync_live_graph
from tests.fakes import InMemoryStatusStore

pytestmark = pytest.mark.skipif(
    os.getenv("NEO4J_PASSWORD") is None,
    reason="NEO4J_PASSWORD is not set; Neo4j propagation integration tests require a database.",
)

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)


class StaticRegimeReader:
    def read_regime_context(self, world_state_ref: str) -> dict[str, Any]:
        return {
            "world_state_ref": world_state_ref,
            "channel_multipliers": {"fundamental": 1.0},
            "regime_multipliers": {"fundamental": 1.0},
            "decay_policy": {"default": 1.0},
        }


class CapturingSnapshotWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[GraphSnapshot, GraphImpactSnapshot]] = []

    def write_snapshots(
        self,
        graph_snapshot: GraphSnapshot,
        impact_snapshot: GraphImpactSnapshot,
    ) -> None:
        self.calls.append((graph_snapshot, impact_snapshot))


def test_compute_graph_snapshots_runs_fundamental_pagerank_on_promoted_graph() -> None:
    pytest.importorskip("neo4j")

    prefix = f"000-propagation-snapshot-{uuid4().hex}"
    source_node_id = f"{prefix}-source"
    target_node_id = f"{prefix}-target"
    edge_id = f"{prefix}-edge"
    evidence_ref = f"{prefix}-fact-1"
    node_ids = [source_node_id, target_node_id]
    writer = CapturingSnapshotWriter()

    with Neo4jClient(load_config_from_env()) as client:
        if not client.verify_connectivity():
            pytest.skip("Neo4j is not reachable with the configured environment.")

        manager = SchemaManager(client)
        manager.apply_schema()
        assert manager.verify_schema() is True

        try:
            sync_live_graph(
                _promotion_plan(source_node_id, target_node_id, edge_id, evidence_ref),
                client,
            )
            node_count, edge_count, key_label_counts, checksum = read_live_graph_metrics(client)
            graph_status = Neo4jGraphStatus(
                graph_status="ready",
                graph_generation_id=1,
                node_count=node_count,
                edge_count=edge_count,
                key_label_counts=key_label_counts,
                checksum=checksum,
                last_verified_at=NOW,
                last_reload_at=None,
            )
            status_manager = GraphStatusManager(InMemoryStatusStore(graph_status))

            try:
                graph_snapshot, impact_snapshot = compute_graph_snapshots(
                    "cycle-1",
                    "world-state-1",
                    client=client,
                    graph_generation_id=1,
                    regime_reader=StaticRegimeReader(),
                    snapshot_writer=writer,
                    status_manager=status_manager,
                    graph_name=f"{prefix}-projection",
                )
            except RuntimeError as exc:
                if str(exc) == "GDS plugin not available":
                    pytest.skip("GDS plugin is not available in the configured Neo4j instance.")
                raise
        finally:
            client.execute_write(
                "MATCH (node) WHERE node.node_id IN $node_ids DETACH DELETE node",
                {"node_ids": node_ids},
            )

    assert graph_snapshot.node_count >= 2
    assert graph_snapshot.edge_count >= 1
    assert impact_snapshot.affected_entities
    assert impact_snapshot.evidence_refs == [evidence_ref]
    assert writer.calls == [(graph_snapshot, impact_snapshot)]


def _promotion_plan(
    source_node_id: str,
    target_node_id: str,
    edge_id: str,
    evidence_ref: str,
) -> PromotionPlan:
    return PromotionPlan(
        cycle_id="cycle-1",
        selection_ref="selection-1",
        delta_ids=["delta-1", "delta-2", "delta-3"],
        node_records=[
            _node_record(source_node_id, f"{source_node_id}-entity"),
            _node_record(target_node_id, f"{target_node_id}-entity"),
        ],
        edge_records=[_edge_record(source_node_id, target_node_id, edge_id, evidence_ref)],
        assertion_records=[],
        created_at=NOW,
    )


def _node_record(node_id: str, canonical_entity_id: str) -> GraphNodeRecord:
    return GraphNodeRecord(
        node_id=node_id,
        canonical_entity_id=canonical_entity_id,
        label=NodeLabel.ENTITY.value,
        properties={"integration_prefix": node_id},
        created_at=NOW,
        updated_at=NOW,
    )


def _edge_record(
    source_node_id: str,
    target_node_id: str,
    edge_id: str,
    evidence_ref: str,
) -> GraphEdgeRecord:
    return GraphEdgeRecord(
        edge_id=edge_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relationship_type=RelationshipType.SUPPLY_CHAIN.value,
        properties={
            "integration_prefix": edge_id,
            "evidence_confidence": 0.9,
            "evidence_refs": [evidence_ref],
            "recency_decay": 1.0,
        },
        weight=10.0,
        created_at=NOW,
        updated_at=NOW,
    )
