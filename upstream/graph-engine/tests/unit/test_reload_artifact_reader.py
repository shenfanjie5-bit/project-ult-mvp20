from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from contracts.schemas.entities import EntityReference
from contracts.schemas.graph import GraphEdge, GraphNode
from graph_engine.client import Neo4jClient
from graph_engine.models import (
    ColdReloadPlan,
    GraphEdgeRecord,
    GraphMetricsSnapshot,
    GraphNodeRecord,
    GraphSnapshot,
    Neo4jGraphStatus,
    PromotionPlan,
)
from graph_engine.reload import (
    ArtifactCanonicalReader,
    CanonicalArtifactError,
    CanonicalArtifactNotFound,
)
from graph_engine.reload import service as reload_service
from graph_engine.schema.definitions import NodeLabel, RelationshipType
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


def test_artifact_canonical_reader_reads_persisted_cold_reload_plan(
    tmp_path: Path,
) -> None:
    plan = _reload_plan()
    artifact_path = tmp_path / "cold_reload_plan.json"
    _write_json(artifact_path, plan.model_dump(mode="json"))

    loaded = ArtifactCanonicalReader().read_cold_reload_plan(str(artifact_path))

    assert loaded == plan


def test_artifact_canonical_reader_rejects_inconsistent_cold_reload_plan(
    tmp_path: Path,
) -> None:
    plan = _reload_plan().model_copy(
        update={"expected_snapshot": _snapshot(graph_generation_id=4).model_copy(
            update={"node_count": 3},
        )},
    )
    artifact_path = tmp_path / "cold_reload_plan.json"
    _write_json(artifact_path, plan.model_dump(mode="json"))

    with pytest.raises(CanonicalArtifactError, match="record counts disagree"):
        ArtifactCanonicalReader().read_cold_reload_plan(str(artifact_path))


def test_cold_reload_uses_persisted_artifact_reader_before_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _reload_plan()
    artifact_path = tmp_path / "cold_reload_plan.json"
    _write_json(artifact_path, {"payload": plan.model_dump(mode="json")})
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
    monkeypatch.setattr(
        reload_service,
        "check_live_graph_consistency",
        lambda *args, **kwargs: True,
    )
    status_manager = GraphStatusManager(
        InMemoryStatusStore(_status(graph_generation_id=3)),
        clock=lambda: NOW,
    )

    status = reload_service.cold_reload(
        str(artifact_path),
        client=MagicMock(spec=Neo4jClient),
        canonical_reader=ArtifactCanonicalReader(),
        status_manager=status_manager,
        schema_manager=RecordingSchemaManager(),  # type: ignore[arg-type]
        batch_size=11,
    )

    promotion_batch = captured["promotion_batch"]
    assert isinstance(promotion_batch, PromotionPlan)
    assert promotion_batch.node_records == plan.node_records
    assert promotion_batch.edge_records == plan.edge_records
    assert promotion_batch.selection_ref == f"cold-reload:{artifact_path}"
    assert captured["batch_size"] == 11
    assert status.graph_status == "ready"
    assert status.graph_generation_id == plan.expected_snapshot.graph_generation_id


def test_artifact_canonical_reader_reads_graph_snapshot_bundle(
    tmp_path: Path,
) -> None:
    graph_snapshot = _graph_snapshot()
    artifact_path = tmp_path / "graph_snapshot.json"
    _write_json(
        artifact_path,
        {
            "payload": {
                "graph_snapshot": graph_snapshot.model_dump(mode="json"),
                "projection_name": "graph_engine_reload_from_artifact",
            },
        },
    )

    plan = ArtifactCanonicalReader().read_cold_reload_plan(str(artifact_path))

    assert plan.snapshot_ref == str(artifact_path)
    assert plan.cycle_id == graph_snapshot.cycle_id
    assert plan.expected_snapshot.snapshot_id == graph_snapshot.graph_snapshot_id
    assert plan.expected_snapshot.graph_generation_id == 4
    assert plan.expected_snapshot.node_count == 2
    assert plan.expected_snapshot.edge_count == 1
    assert plan.projection_name == "graph_engine_reload_from_artifact"
    assert [record.node_id for record in plan.node_records] == ["node-1", "node-2"]
    assert [record.edge_id for record in plan.edge_records] == ["edge-1"]
    assert plan.node_records[0].properties == {"ticker": "AAA"}
    assert plan.edge_records[0].properties == {
        "evidence_refs": ["fact-edge-1"],
        "weight": 0.7,
    }


def test_artifact_canonical_reader_does_not_parse_numeric_checksum_as_generation(
    tmp_path: Path,
) -> None:
    graph_snapshot = _graph_snapshot().model_copy(
        update={"graph_snapshot_id": "graph-snapshot-cycle-1-4-123456789012"},
    )
    artifact_path = tmp_path / "graph_snapshot.json"
    _write_json(
        artifact_path,
        {"payload": {"graph_snapshot": graph_snapshot.model_dump(mode="json")}},
    )

    plan = ArtifactCanonicalReader().read_cold_reload_plan(str(artifact_path))

    assert plan.expected_snapshot.graph_generation_id == 4


def test_artifact_canonical_reader_resolves_relative_snapshot_ref_from_root(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "snapshots" / "snapshot-ref-1.json"
    artifact_path.parent.mkdir()
    _write_json(artifact_path, _reload_plan().model_dump(mode="json"))

    plan = ArtifactCanonicalReader(tmp_path / "snapshots").read_cold_reload_plan(
        "snapshot-ref-1",
    )

    assert plan.snapshot_ref == "snapshot-ref-1"


def test_artifact_canonical_reader_rejects_missing_artifact(tmp_path: Path) -> None:
    with pytest.raises(CanonicalArtifactNotFound, match="canonical artifact not found"):
        ArtifactCanonicalReader(tmp_path).read_cold_reload_plan("missing-snapshot")


def test_artifact_canonical_reader_rejects_invalid_json(tmp_path: Path) -> None:
    artifact_path = tmp_path / "broken.json"
    artifact_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(CanonicalArtifactError, match="not valid JSON"):
        ArtifactCanonicalReader().read_cold_reload_plan(str(artifact_path))


def test_artifact_canonical_reader_rejects_impact_only_artifact(tmp_path: Path) -> None:
    artifact_path = tmp_path / "graph_impact_snapshot.json"
    _write_json(
        artifact_path,
        {
            "payload": {
                "impact_snapshot_id": "impact-1",
                "cycle_id": "cycle-1",
                "evidence_refs": ["fact-1"],
            },
        },
    )

    with pytest.raises(CanonicalArtifactError, match="cold_reload_plan or graph_snapshot"):
        ArtifactCanonicalReader().read_cold_reload_plan(str(artifact_path))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _reload_plan() -> ColdReloadPlan:
    return ColdReloadPlan(
        snapshot_ref="snapshot-ref-1",
        cycle_id="cycle-1",
        expected_snapshot=_snapshot(graph_generation_id=4),
        node_records=[
            _node_record("node-1", "entity-1"),
            _node_record("node-2", "entity-2"),
        ],
        edge_records=[_edge_record()],
        assertion_records=[],
        projection_name="graph_engine_reload_cycle_1",
        created_at=NOW,
    )


def _status(*, graph_generation_id: int) -> Neo4jGraphStatus:
    return Neo4jGraphStatus(
        graph_status="ready",
        graph_generation_id=graph_generation_id,
        node_count=2,
        edge_count=1,
        key_label_counts={"Entity": 2},
        checksum="old-checksum",
        last_verified_at=NOW,
        last_reload_at=None,
    )


def _snapshot(*, graph_generation_id: int) -> GraphMetricsSnapshot:
    return GraphMetricsSnapshot(
        cycle_id="cycle-1",
        snapshot_id="snapshot-1",
        graph_generation_id=graph_generation_id,
        node_count=2,
        edge_count=1,
        key_label_counts={"Entity": 2},
        checksum="ready-checksum",
        created_at=NOW,
    )


def _node_record(node_id: str, canonical_entity_id: str) -> GraphNodeRecord:
    return GraphNodeRecord(
        node_id=node_id,
        canonical_entity_id=canonical_entity_id,
        label=NodeLabel.ENTITY.value,
        properties={"ticker": canonical_entity_id.upper()},
        created_at=NOW,
        updated_at=NOW,
    )


def _edge_record() -> GraphEdgeRecord:
    return GraphEdgeRecord(
        edge_id="edge-1",
        source_node_id="node-1",
        target_node_id="node-2",
        relationship_type=RelationshipType.SUPPLY_CHAIN.value,
        properties={"source": "filing", "evidence_refs": ["fact-edge-1"]},
        weight=0.7,
        created_at=NOW,
        updated_at=NOW,
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
                    source_properties={"weight": 0.7, "evidence_refs": ["fact-edge-1"]},
                ),
                evidence_refs=["fact-edge-1"],
            ),
        ],
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
