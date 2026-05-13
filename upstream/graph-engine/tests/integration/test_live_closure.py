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
    CandidateGraphDelta,
    GraphNodeRecord,
    Neo4jGraphStatus,
    PromotionPlan,
)
from graph_engine.providers import (
    GraphPhase1Service,
    GraphPromotionAssetRequest,
    GraphSnapshotAssetRequest,
)
from graph_engine.reload import ArtifactCanonicalReader, cold_reload
from graph_engine.schema.definitions import NodeLabel
from graph_engine.schema.manager import DROP_ALL_CONFIRMATION_TOKEN, SchemaManager
from graph_engine.snapshots import FormalArtifactSnapshotWriter
from graph_engine.status import GraphStatusManager
from graph_engine.sync import sync_live_graph
from tests.fakes import InMemoryStatusStore

pytestmark = pytest.mark.skipif(
    os.getenv("NEO4J_PASSWORD") is None,
    reason="NEO4J_PASSWORD is not set; live closure integration test requires a database.",
)

NOW = datetime(2026, 4, 28, 1, 2, 3, tzinfo=timezone.utc)


class StaticCandidateReader:
    def __init__(self, deltas: list[CandidateGraphDelta]) -> None:
        self.deltas = deltas

    def read_candidate_graph_deltas(
        self,
        cycle_id: str,
        selection_ref: str,
    ) -> list[CandidateGraphDelta]:
        return self.deltas


class StaticEntityReader:
    def __init__(self, node_entity_ids: dict[str, str]) -> None:
        self.node_entity_ids = node_entity_ids
        self.entity_ids = set(node_entity_ids.values())

    def canonical_entity_ids_for_node_ids(self, node_ids: set[str]) -> dict[str, str]:
        return {
            node_id: self.node_entity_ids[node_id]
            for node_id in node_ids
            if node_id in self.node_entity_ids
        }

    def existing_entity_ids(self, entity_ids: set[str]) -> set[str]:
        return entity_ids & self.entity_ids


class CapturingCanonicalWriter:
    def __init__(self) -> None:
        self.plans: list[PromotionPlan] = []

    def write_canonical_records(self, plan: PromotionPlan) -> None:
        self.plans.append(plan)


class StaticRegimeReader:
    def read_regime_context(self, world_state_ref: str) -> dict[str, Any]:
        return {
            "world_state_ref": world_state_ref,
            "channel_multipliers": {
                "fundamental": 1.0,
                "event": 1.0,
                "reflexive": 1.0,
            },
            "regime_multipliers": {
                "fundamental": 1.0,
                "event": 1.0,
                "reflexive": 1.0,
            },
            "decay_policy": {"default": 1.0},
        }


def test_candidate_delta_to_artifact_backed_cold_reload_live_closure(tmp_path) -> None:
    pytest.importorskip("neo4j")

    prefix = f"live-closure-{uuid4().hex}"
    cycle_id = f"{prefix}-cycle"
    selection_ref = f"cycle_candidate_selection:{cycle_id}"
    world_state_ref = f"world-state:{prefix}-previous-cycle"
    source_node_id = f"{prefix}-source"
    target_node_id = f"{prefix}-target"
    evidence_ref = f"{prefix}-fact"
    delta_id = f"{prefix}-edge"
    node_entity_ids = {
        source_node_id: f"{prefix}-entity-source",
        target_node_id: f"{prefix}-entity-target",
    }
    propagation_projection = f"graph_engine_live_closure_{uuid4().hex}"
    reload_projection = f"graph_engine_live_reload_{uuid4().hex}"
    artifact_reader = ArtifactCanonicalReader(default_projection_name=reload_projection)
    canonical_writer = CapturingCanonicalWriter()

    with Neo4jClient(load_config_from_env()) as client:
        if not client.verify_connectivity():
            pytest.skip("Neo4j is not reachable with the configured environment.")
        _require_gds_available(client)

        schema_manager = SchemaManager(client)
        _drop_projection_if_present(client, propagation_projection)
        _drop_projection_if_present(client, reload_projection)
        schema_manager.drop_all(
            confirmation_token=DROP_ALL_CONFIRMATION_TOKEN,
            test_mode=True,
        )
        schema_manager.apply_schema()
        assert schema_manager.verify_schema() is True

        try:
            sync_live_graph(
                _seed_node_plan(cycle_id, selection_ref, source_node_id, target_node_id),
                client,
            )
            status_manager = GraphStatusManager(
                InMemoryStatusStore(_status_from_live_graph(client, graph_generation_id=1)),
                clock=lambda: NOW,
            )
            service = GraphPhase1Service(
                candidate_reader=StaticCandidateReader(
                    [
                        _candidate_delta(
                            delta_id=delta_id,
                            source_node_id=source_node_id,
                            target_node_id=target_node_id,
                            evidence_ref=evidence_ref,
                        ),
                    ],
                ),
                entity_reader=StaticEntityReader(node_entity_ids),
                canonical_writer=canonical_writer,
                client=client,
                status_manager=status_manager,
                regime_reader=StaticRegimeReader(),
                snapshot_writer=FormalArtifactSnapshotWriter(tmp_path),
                artifact_reader=artifact_reader,
                graph_name=propagation_projection,
                result_limit=20,
            )

            promotion = service.promote_graph(
                GraphPromotionAssetRequest(
                    cycle_id=cycle_id,
                    selection_ref=selection_ref,
                    phase0_readiness={"ready": True},
                    candidate_freeze={
                        "cycle_id": cycle_id,
                        "selection_ref": selection_ref,
                    },
                    graph_status=status_manager.require_ready(),
                ),
            )
            snapshot_result = service.compute_graph_snapshot(
                GraphSnapshotAssetRequest(
                    cycle_id=cycle_id,
                    world_state_ref=world_state_ref,
                    graph_generation_id=promotion.graph_generation_id,
                    promotion=promotion,
                ),
            )
            reload_plan = artifact_reader.read_cold_reload_plan(
                snapshot_result.artifact_ref,
            )
            reloaded_status = cold_reload(
                snapshot_result.artifact_ref,
                client=client,
                canonical_reader=artifact_reader,
                status_manager=status_manager,
                schema_manager=schema_manager,
            )
        finally:
            _drop_projection_if_present(client, propagation_projection)
            _drop_projection_if_present(client, reload_projection)
            schema_manager.drop_all(
                confirmation_token=DROP_ALL_CONFIRMATION_TOKEN,
                test_mode=True,
            )

    assert [plan.delta_ids for plan in canonical_writer.plans] == [[delta_id]]
    assert promotion.delta_ids == (delta_id,)
    assert snapshot_result.graph_snapshot.node_count == 2
    assert snapshot_result.graph_snapshot.edge_count == 1
    assert snapshot_result.impact_snapshot.evidence_refs == [evidence_ref]
    assert snapshot_result.cold_reload_proof.snapshot_ref == snapshot_result.artifact_ref
    assert reload_plan.projection_name == reload_projection
    assert reload_plan.node_records
    assert reload_plan.edge_records
    assert reloaded_status.graph_status == "ready"
    assert reloaded_status.graph_generation_id == reload_plan.expected_snapshot.graph_generation_id
    assert reloaded_status.node_count == reload_plan.expected_snapshot.node_count
    assert reloaded_status.edge_count == reload_plan.expected_snapshot.edge_count
    assert reloaded_status.checksum == reload_plan.expected_snapshot.checksum


def _require_gds_available(client: Neo4jClient) -> None:
    try:
        version_rows = client.execute_read(
            "CALL gds.version() YIELD gdsVersion RETURN gdsVersion",
        )
        exists_rows = client.execute_read(
            "CALL gds.graph.exists($graph_name) YIELD exists RETURN exists",
            {"graph_name": "graph_engine_live_closure_probe"},
        )
    except Exception as exc:  # noqa: BLE001 - normalize optional GDS absence to a skip.
        if _is_missing_gds_error(exc):
            pytest.skip("GDS plugin is not available in the configured Neo4j instance.")
        raise
    assert version_rows and version_rows[0].get("gdsVersion")
    assert exists_rows and exists_rows[0].get("exists") is False


def _is_missing_gds_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "gds." in message and any(
        marker in message
        for marker in (
            "no procedure",
            "not registered",
            "unknown procedure",
            "procedure not found",
        )
    )


def _seed_node_plan(
    cycle_id: str,
    selection_ref: str,
    source_node_id: str,
    target_node_id: str,
) -> PromotionPlan:
    return PromotionPlan(
        cycle_id=cycle_id,
        selection_ref=f"{selection_ref}:seed-nodes",
        delta_ids=[],
        node_records=[
            _node_record(source_node_id, f"{source_node_id}-entity"),
            _node_record(target_node_id, f"{target_node_id}-entity"),
        ],
        edge_records=[],
        assertion_records=[],
        created_at=NOW,
    )


def _node_record(node_id: str, canonical_entity_id: str) -> GraphNodeRecord:
    return GraphNodeRecord(
        node_id=node_id,
        canonical_entity_id=canonical_entity_id,
        label=NodeLabel.ENTITY.value,
        properties={
            "canonical_id_rule_version": "ent-id-rule-v1",
            "integration_prefix": node_id,
        },
        created_at=NOW,
        updated_at=NOW,
    )


def _candidate_delta(
    *,
    delta_id: str,
    source_node_id: str,
    target_node_id: str,
    evidence_ref: str,
) -> CandidateGraphDelta:
    return CandidateGraphDelta(
        delta_id=delta_id,
        delta_type="add_edge",
        source_node=source_node_id,
        target_node=target_node_id,
        relation_type="supply_contract",
        properties={
            "evidence_confidence": 0.95,
            "evidence_refs": [evidence_ref],
            "integration_prefix": delta_id,
            "recency_decay": 1.0,
            "weight": 0.8,
        },
        evidence=[evidence_ref],
        subsystem_id="subsystem-news",
    )


def _status_from_live_graph(
    client: Neo4jClient,
    *,
    graph_generation_id: int,
) -> Neo4jGraphStatus:
    node_count, edge_count, key_label_counts, checksum = read_live_graph_metrics(client)
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


def _drop_projection_if_present(client: Neo4jClient, projection_name: str) -> None:
    try:
        rows = client.execute_read(
            "CALL gds.graph.exists($projection_name) YIELD exists RETURN exists",
            {"projection_name": projection_name},
        )
        if rows and rows[0].get("exists") is True:
            client.execute_write(
                "CALL gds.graph.drop($projection_name) YIELD graphName RETURN graphName",
                {"projection_name": projection_name},
            )
    except Exception as exc:  # noqa: BLE001 - cleanup should not fail when GDS is absent.
        if not _is_missing_gds_error(exc):
            raise
