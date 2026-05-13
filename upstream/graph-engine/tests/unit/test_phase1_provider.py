from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from contracts.schemas.entities import EntityReference
from contracts.schemas.graph import GraphEdge, GraphNode
from graph_engine.client import Neo4jClient
from graph_engine.live_metrics import read_live_graph_metrics
from graph_engine.models import (
    GraphImpactSnapshot,
    GraphSnapshot,
    Neo4jGraphStatus,
    PromotionPlan,
)
from graph_engine.providers import (
    GRAPH_PHASE1_RESOURCE_KEY,
    GraphPhase1Service,
    GraphPromotionAssetResult,
    GraphSnapshotAssetRequest,
    build_graph_phase1_provider,
    prove_cold_reload_artifact,
)
from graph_engine.providers.phase1 import _cycle_binding_from_phase0
from graph_engine.reload import ArtifactCanonicalReader, CanonicalArtifactError
from graph_engine.reload import service as reload_service
from graph_engine.reload.service import metrics_snapshot_from_graph_snapshot
from graph_engine.schema.definitions import NodeLabel, RelationshipType
from graph_engine.snapshots import FormalArtifactSnapshotWriter
from graph_engine.status import GraphStatusManager
from tests.fakes import InMemoryStatusStore

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)


class RecordingSchemaManager:
    def __init__(self) -> None:
        self.drop_calls = 0

    def drop_all(self, **kwargs: object) -> None:
        self.drop_calls += 1

    def apply_schema(self) -> None:
        return None

    def verify_schema(self) -> bool:
        return True


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


class RecordingSnapshotWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[GraphSnapshot, GraphImpactSnapshot]] = []

    def write_snapshots(
        self,
        graph_snapshot: GraphSnapshot,
        impact_snapshot: GraphImpactSnapshot,
    ) -> None:
        self.calls.append((graph_snapshot, impact_snapshot))


class MissingGDSClient:
    def __init__(self) -> None:
        self.nodes = [
            {
                "labels": ["Entity"],
                "node_id": "node-1",
                "canonical_entity_id": "entity-1",
                "properties": {"node_id": "node-1"},
            },
            {
                "labels": ["Entity"],
                "node_id": "node-2",
                "canonical_entity_id": "entity-2",
                "properties": {"node_id": "node-2"},
            },
        ]
        self.relationships = [
            {
                "source_node_id": "node-1",
                "target_node_id": "node-2",
                "relationship_type": "SUPPLY_CHAIN",
                "edge_id": "edge-1",
                "properties": {
                    "edge_id": "edge-1",
                    "evidence_refs": ["fact-1"],
                },
            },
        ]

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if "gds." in query:
            raise RuntimeError(
                "There is no procedure with the name `gds.graph.exists` registered",
            )
        if "RETURN node_count, edge_count, label_counts, nodes, relationships" in query:
            return [
                {
                    "node_count": len(self.nodes),
                    "edge_count": len(self.relationships),
                    "label_counts": [{"label": "Entity", "count": 2}],
                    "nodes": self.nodes,
                    "relationships": self.relationships,
                },
            ]
        return []

    def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if "gds." in query:
            raise RuntimeError(
                "There is no procedure with the name `gds.graph.project` registered",
            )
        return []


def test_phase1_provider_assets_have_required_ancestry() -> None:
    """Asset shapes are independent of the runtime; pass a sentinel runtime
    so the provider construction does not require live env (M2.3a-2: the
    no-arg ``build_graph_phase1_provider()`` now triggers env-driven runtime
    construction which would fail in this unit-test venv)."""

    dagster = pytest.importorskip("dagster")

    class _SentinelRuntime:
        def promote_graph(self, request):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        def compute_graph_snapshot(self, request):  # type: ignore[no-untyped-def]
            raise NotImplementedError

    provider = build_graph_phase1_provider(runtime=_SentinelRuntime())

    asset_by_key = {
        asset_key: asset_def
        for asset_def in provider.get_assets()
        for asset_key in getattr(asset_def, "keys", ())
    }
    promotion_key = dagster.AssetKey(["graph_promotion"])
    snapshot_key = dagster.AssetKey(["graph_snapshot"])

    assert set(asset_by_key) == {promotion_key, snapshot_key}
    assert (
        asset_by_key[promotion_key].group_names_by_key[promotion_key]
        == "phase1"
    )
    assert asset_by_key[snapshot_key].group_names_by_key[snapshot_key] == "phase1"
    assert {
        dagster.AssetKey(["phase0_readiness_ping"]),
        dagster.AssetKey(["candidate_freeze"]),
        dagster.AssetKey(["graph_status"]),
    } <= _dependency_keys(asset_by_key[promotion_key], promotion_key)
    assert promotion_key in _dependency_keys(asset_by_key[snapshot_key], snapshot_key)

    resources = provider.get_resources()
    assert set(resources) == {GRAPH_PHASE1_RESOURCE_KEY}


def test_phase1_requires_frozen_candidate_selection_ref() -> None:
    with pytest.raises(ValueError, match="frozen selection_ref"):
        _cycle_binding_from_phase0(
            {"cycle_id": "CYCLE_20260427"},
            context=object(),
        )

    with pytest.raises(ValueError, match="must expose cycle_id"):
        _cycle_binding_from_phase0(
            {"selection_ref": "cycle_candidate_selection:CYCLE_20260427"},
            context=object(),
        )

    assert _cycle_binding_from_phase0(
        {
            "cycle_id": "CYCLE_20260427",
            "selection_ref": "cycle_candidate_selection:CYCLE_20260427",
        },
        context=object(),
    ) == ("CYCLE_20260427", "cycle_candidate_selection:CYCLE_20260427")


def test_phase1_snapshot_runtime_missing_gds_fails_closed_without_artifact_write() -> None:
    client = MissingGDSClient()
    node_count, edge_count, key_label_counts, checksum = read_live_graph_metrics(  # type: ignore[arg-type]
        client,
    )
    writer = RecordingSnapshotWriter()
    status_manager = GraphStatusManager(
        InMemoryStatusStore(
            _status(
                graph_generation_id=5,
                node_count=node_count,
                edge_count=edge_count,
                key_label_counts=key_label_counts,
                checksum=checksum,
            ),
        ),
    )
    runtime = GraphPhase1Service(
        candidate_reader=object(),  # type: ignore[arg-type]
        entity_reader=object(),  # type: ignore[arg-type]
        canonical_writer=object(),  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
        status_manager=status_manager,
        regime_reader=StaticRegimeReader(),
        snapshot_writer=writer,
        graph_name="unit-missing-gds",
    )

    with pytest.raises(RuntimeError, match="^GDS plugin not available$"):
        runtime.compute_graph_snapshot(
            GraphSnapshotAssetRequest(
                cycle_id="cycle-1",
                world_state_ref="world-state-1",
                graph_generation_id=5,
                promotion=_promotion_result(graph_generation_id=5),
            ),
        )

    assert writer.calls == []


def test_cold_reload_artifact_count_mismatch_fails_closed(tmp_path: Path) -> None:
    snapshot_ref, expected_status = _write_formal_artifact(tmp_path)
    payload = json.loads(Path(snapshot_ref).read_text(encoding="utf-8"))
    payload["graph_snapshot"]["node_count"] = 3
    Path(snapshot_ref).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(
        CanonicalArtifactError,
        match="graph snapshot artifact is invalid|record counts disagree",
    ):
        prove_cold_reload_artifact(
            snapshot_ref,
            artifact_reader=ArtifactCanonicalReader(),
            expected_status=expected_status,
        )


def test_cold_reload_artifact_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    snapshot_ref, expected_status = _write_formal_artifact(tmp_path)
    stale_status = expected_status.model_copy(update={"checksum": "stale-checksum"})

    with pytest.raises(ValueError, match="checksum"):
        prove_cold_reload_artifact(
            snapshot_ref,
            artifact_reader=ArtifactCanonicalReader(),
            expected_status=stale_status,
        )


def test_cold_reload_from_persisted_formal_artifact_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_ref, expected_status = _write_formal_artifact(tmp_path)
    captured: dict[str, Any] = {}

    def fake_sync_live_graph(
        promotion_batch: PromotionPlan,
        sync_client: Neo4jClient,
        *,
        batch_size: int,
    ) -> None:
        captured["promotion_batch"] = promotion_batch
        captured["sync_client"] = sync_client
        captured["batch_size"] = batch_size

    monkeypatch.setattr(reload_service, "sync_live_graph", fake_sync_live_graph)
    monkeypatch.setattr(reload_service, "rebuild_gds_projection", lambda *args, **kwargs: None)
    monkeypatch.setattr(reload_service, "check_live_graph_consistency", lambda *args, **kwargs: True)

    status = reload_service.cold_reload(
        snapshot_ref,
        client=MagicMock(spec=Neo4jClient),
        canonical_reader=ArtifactCanonicalReader(),
        status_manager=GraphStatusManager(
            InMemoryStatusStore(_status(graph_generation_id=3)),
            clock=lambda: NOW,
        ),
        schema_manager=RecordingSchemaManager(),  # type: ignore[arg-type]
        batch_size=17,
    )

    assert status.graph_status == "ready"
    assert status.graph_generation_id == expected_status.graph_generation_id
    assert status.node_count == expected_status.node_count
    assert status.edge_count == expected_status.edge_count
    assert status.checksum == expected_status.checksum
    assert captured["batch_size"] == 17
    assert captured["promotion_batch"].node_records
    assert captured["promotion_batch"].edge_records


def test_formal_artifact_writer_does_not_parse_numeric_checksum_as_generation(
    tmp_path: Path,
) -> None:
    graph_snapshot = _graph_snapshot().model_copy(
        update={"graph_snapshot_id": "graph-snapshot-cycle-1-4-123456789012"},
    )
    writer = FormalArtifactSnapshotWriter(tmp_path)

    payload = writer.artifact_payload(graph_snapshot, _impact_snapshot())

    assert payload["graph_generation_id"] == 4


def _write_formal_artifact(tmp_path: Path) -> tuple[str, Neo4jGraphStatus]:
    graph_snapshot = _graph_snapshot()
    metrics = metrics_snapshot_from_graph_snapshot(
        graph_snapshot,
        graph_generation_id=4,
    )
    expected_status = _status(
        graph_generation_id=metrics.graph_generation_id,
        node_count=metrics.node_count,
        edge_count=metrics.edge_count,
        key_label_counts=metrics.key_label_counts,
        checksum=metrics.checksum,
    )
    writer = FormalArtifactSnapshotWriter(tmp_path)
    writer.write_snapshots(graph_snapshot, _impact_snapshot())
    assert writer.last_artifact_ref is not None
    proof = prove_cold_reload_artifact(
        writer.last_artifact_ref,
        artifact_reader=ArtifactCanonicalReader(),
        expected_status=expected_status,
    )
    assert proof.graph_generation_id == expected_status.graph_generation_id
    return writer.last_artifact_ref, expected_status


def _dependency_keys(asset_def: object, asset_key: object) -> set[object]:
    keys: set[object] = set()
    for attribute_name in (
        "asset_deps",
        "dependency_keys_by_key",
        "deps_by_key",
    ):
        dependency_mapping = getattr(asset_def, attribute_name, None)
        if isinstance(dependency_mapping, Mapping):
            keys.update(dependency_mapping.get(asset_key, ()))
    keys.update(getattr(asset_def, "dependency_keys", ()) or ())
    return keys


def _promotion_result(*, graph_generation_id: int) -> GraphPromotionAssetResult:
    return GraphPromotionAssetResult(
        cycle_id="cycle-1",
        selection_ref="cycle_candidate_selection:cycle-1",
        graph_generation_id=graph_generation_id,
        delta_ids=(),
        plan=PromotionPlan(
            cycle_id="cycle-1",
            selection_ref="cycle_candidate_selection:cycle-1",
            delta_ids=[],
            node_records=[],
            edge_records=[],
            assertion_records=[],
            created_at=NOW,
        ),
        graph_status=_status(graph_generation_id=graph_generation_id),
    )


def _status(
    *,
    graph_generation_id: int,
    node_count: int = 2,
    edge_count: int = 1,
    key_label_counts: dict[str, int] | None = None,
    checksum: str = "ready-checksum",
) -> Neo4jGraphStatus:
    return Neo4jGraphStatus(
        graph_status="ready",
        graph_generation_id=graph_generation_id,
        node_count=node_count,
        edge_count=edge_count,
        key_label_counts={"Entity": 2} if key_label_counts is None else key_label_counts,
        checksum=checksum,
        last_verified_at=NOW,
        last_reload_at=None,
    )


def _graph_snapshot() -> GraphSnapshot:
    return GraphSnapshot(
        graph_snapshot_id="graph-snapshot-cycle-1-4-abc",
        cycle_id="cycle-1",
        version="v0.1.3",
        created_at=NOW,
        node_count=2,
        edge_count=1,
        nodes=[
            GraphNode(
                node_id="node-1",
                labels=["Entity"],
                properties=_live_metric_node_properties(
                    "node-1",
                    "entity-1",
                    source_properties={"ticker": "AAA"},
                ),
                entity=EntityReference(
                    entity_id="entity-1",
                    entity_type="equity",
                    canonical_id_rule_version="ent-id-rule-v1",
                ),
            ),
            GraphNode(
                node_id="node-2",
                labels=["Entity"],
                properties=_live_metric_node_properties(
                    "node-2",
                    "entity-2",
                    source_properties={"ticker": "BBB"},
                ),
                entity=EntityReference(
                    entity_id="entity-2",
                    entity_type="equity",
                    canonical_id_rule_version="ent-id-rule-v1",
                ),
            ),
        ],
        edges=[
            GraphEdge(
                edge_id="edge-1",
                source_node="node-1",
                target_node="node-2",
                relation_type=RelationshipType.SUPPLY_CHAIN.value,
                properties=_live_metric_edge_properties(
                    "edge-1",
                    "node-1",
                    "node-2",
                    source_properties={
                        "weight": 0.7,
                        "evidence_refs": ["fact-edge-1"],
                    },
                ),
                evidence_refs=["fact-edge-1"],
            ),
        ],
    )


def _impact_snapshot() -> GraphImpactSnapshot:
    return GraphImpactSnapshot(
        impact_snapshot_id="impact-1",
        cycle_id="cycle-1",
        version="v0.1.3",
        created_at=NOW,
        target_entities=[
            EntityReference(
                entity_id="entity-2",
                entity_type="equity",
                canonical_id_rule_version="ent-id-rule-v1",
            ),
        ],
        affected_entities=[
            EntityReference(
                entity_id="entity-2",
                entity_type="equity",
                canonical_id_rule_version="ent-id-rule-v1",
            ),
        ],
        affected_sectors=[],
        direction="bullish",
        impact_score=0.7,
        evidence_refs=["fact-edge-1"],
    )


def _live_metric_node_properties(
    node_id: str,
    canonical_entity_id: str,
    *,
    source_properties: dict[str, object],
) -> dict[str, object]:
    return {
        "node_id": node_id,
        "canonical_entity_id": canonical_entity_id,
        "label": NodeLabel.ENTITY.value,
        "properties_json": json.dumps(source_properties, sort_keys=True),
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
        **source_properties,
    }


def _live_metric_edge_properties(
    edge_id: str,
    source_node_id: str,
    target_node_id: str,
    *,
    source_properties: dict[str, object],
) -> dict[str, object]:
    return {
        "edge_id": edge_id,
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "relationship_type": RelationshipType.SUPPLY_CHAIN.value,
        "weight": source_properties["weight"],
        "properties_json": json.dumps(source_properties, sort_keys=True),
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
        **source_properties,
    }
