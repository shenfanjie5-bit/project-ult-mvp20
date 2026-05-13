from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Literal
from unittest.mock import MagicMock

import pytest

from contracts.schemas.entities import EntityReference
from contracts.schemas.graph import GraphEdge, GraphNode
from graph_engine.client import Neo4jClient
from graph_engine.models import (
    ColdReloadPlan,
    GraphEdgeRecord,
    GraphMetricsSnapshot,
    GraphSnapshot,
    GraphNodeRecord,
    Neo4jGraphStatus,
    PromotionPlan,
)
from graph_engine.reload import service as reload_service
from graph_engine.reload.projection import rebuild_gds_projection
from graph_engine.schema.definitions import NodeLabel, RelationshipType
from graph_engine.schema.manager import DROP_ALL_CONFIRMATION_TOKEN
from graph_engine.status import GraphStatusManager
from tests.fakes import InMemoryStatusStore

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)


class RecordingStatusManager(GraphStatusManager):
    def __init__(
        self,
        store: InMemoryStatusStore,
        order: list[str],
    ) -> None:
        super().__init__(store, clock=lambda: NOW)
        self.order = order

    def mark_rebuilding(self) -> Neo4jGraphStatus:
        self.order.append("mark_rebuilding")
        return super().mark_rebuilding()

    def mark_ready(
        self,
        *,
        node_count: int,
        edge_count: int,
        key_label_counts: dict[str, int],
        checksum: str,
        graph_generation_id: int | None = None,
        reload_completed: bool = False,
    ) -> Neo4jGraphStatus:
        self.order.append("mark_ready")
        return super().mark_ready(
            node_count=node_count,
            edge_count=edge_count,
            key_label_counts=key_label_counts,
            checksum=checksum,
            graph_generation_id=graph_generation_id,
            reload_completed=reload_completed,
        )

    def mark_failed(
        self,
        *,
        node_count: int = 0,
        edge_count: int = 0,
        key_label_counts: dict[str, int] | None = None,
        checksum: str = "failed",
    ) -> Neo4jGraphStatus:
        self.order.append("mark_failed")
        return super().mark_failed(
            node_count=node_count,
            edge_count=edge_count,
            key_label_counts=key_label_counts,
            checksum=checksum,
        )


class StaticCanonicalReader:
    def __init__(
        self,
        plan: ColdReloadPlan | None = None,
        *,
        error: Exception | None = None,
        order: list[str] | None = None,
    ) -> None:
        self.plan = plan
        self.error = error
        self.order = order
        self.calls: list[str] = []

    def read_cold_reload_plan(self, snapshot_ref: str) -> ColdReloadPlan:
        if self.order is not None:
            self.order.append("read_cold_reload_plan")
        self.calls.append(snapshot_ref)
        if self.error is not None:
            raise self.error
        if self.plan is None:
            raise RuntimeError("reload plan not configured")
        return self.plan


class RecordingSchemaManager:
    def __init__(
        self,
        order: list[str],
        *,
        verify_result: bool = True,
        apply_error: Exception | None = None,
        drop_error: Exception | None = None,
    ) -> None:
        self.order = order
        self.verify_result = verify_result
        self.apply_error = apply_error
        self.drop_error = drop_error
        self.drop_calls: list[dict[str, Any]] = []

    def drop_all(
        self,
        *,
        confirmation_token: str | None = None,
        graph_status: object | None = None,
        test_mode: bool = False,
    ) -> None:
        self.order.append("drop_all")
        self.drop_calls.append(
            {
                "confirmation_token": confirmation_token,
                "graph_status": graph_status,
                "test_mode": test_mode,
            },
        )
        if self.drop_error is not None:
            raise self.drop_error

    def apply_schema(self) -> None:
        self.order.append("apply_schema")
        if self.apply_error is not None:
            raise self.apply_error

    def verify_schema(self) -> bool:
        self.order.append("verify_schema")
        return self.verify_result


def test_cold_reload_success_path_uses_required_order_and_ready_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    plan = _reload_plan()
    store = InMemoryStatusStore(_status(graph_generation_id=3))
    status_manager = RecordingStatusManager(store, order)
    schema_manager = RecordingSchemaManager(order)
    client = MagicMock(spec=Neo4jClient)
    captured_sync: dict[str, object] = {}

    def fake_sync_live_graph(
        promotion_batch: PromotionPlan,
        sync_client: Neo4jClient,
        *,
        batch_size: int,
    ) -> None:
        order.append("sync_live_graph")
        captured_sync["promotion_batch"] = promotion_batch
        captured_sync["client"] = sync_client
        captured_sync["batch_size"] = batch_size

    def fake_rebuild_gds_projection(
        projection_client: Neo4jClient,
        projection_name: str,
    ) -> None:
        order.append("rebuild_gds_projection")
        assert getattr(projection_client, "_client", projection_client) is client
        assert projection_name == plan.projection_name

    def fake_check_live_graph_consistency(
        snapshot_ref: str,
        *,
        client: Neo4jClient,
        snapshot_reader: object,
        status_manager: object | None = None,
        require_ready: bool = True,
    ) -> bool:
        order.append("check_live_graph_consistency")
        assert snapshot_ref == plan.snapshot_ref
        assert client is not None
        assert status_manager is None
        assert require_ready is False
        assert snapshot_reader.read_graph_snapshot(snapshot_ref) == plan.expected_snapshot
        return True

    monkeypatch.setattr(reload_service, "sync_live_graph", fake_sync_live_graph)
    monkeypatch.setattr(reload_service, "rebuild_gds_projection", fake_rebuild_gds_projection)
    monkeypatch.setattr(
        reload_service,
        "check_live_graph_consistency",
        fake_check_live_graph_consistency,
    )

    status = reload_service.cold_reload(
        plan.snapshot_ref,
        client=client,
        canonical_reader=StaticCanonicalReader(plan, order=order),
        status_manager=status_manager,
        schema_manager=schema_manager,  # type: ignore[arg-type]
        batch_size=17,
    )

    assert order == [
        "mark_rebuilding",
        "read_cold_reload_plan",
        "drop_all",
        "sync_live_graph",
        "apply_schema",
        "verify_schema",
        "rebuild_gds_projection",
        "check_live_graph_consistency",
        "mark_ready",
    ]
    assert schema_manager.drop_calls == [
        {
            "confirmation_token": DROP_ALL_CONFIRMATION_TOKEN,
            "graph_status": store.writes[0],
            "test_mode": False,
        },
    ]
    assert store.writes[0].graph_status == "rebuilding"
    assert status.graph_status == "ready"
    assert status.graph_generation_id == plan.expected_snapshot.graph_generation_id
    assert status.node_count == plan.expected_snapshot.node_count
    assert status.edge_count == plan.expected_snapshot.edge_count
    assert status.key_label_counts == plan.expected_snapshot.key_label_counts
    assert status.checksum == plan.expected_snapshot.checksum
    assert status.last_verified_at == NOW
    assert status.last_reload_at == NOW
    promotion_batch = captured_sync["promotion_batch"]
    assert isinstance(promotion_batch, PromotionPlan)
    assert promotion_batch.selection_ref == f"cold-reload:{plan.snapshot_ref}"
    assert promotion_batch.delta_ids == []
    assert promotion_batch.node_records == plan.node_records
    assert promotion_batch.edge_records == plan.edge_records
    assert getattr(captured_sync["client"], "_client", captured_sync["client"]) is client
    assert captured_sync["batch_size"] == 17


def test_metrics_snapshot_from_graph_snapshot_derives_cold_reload_expected_snapshot() -> None:
    graph_snapshot = GraphSnapshot(
        graph_snapshot_id="graph-snapshot-cycle-1-4-abc",
        cycle_id="cycle-1",
        version="v0.1.3",
        created_at=NOW,
        node_count=2,
        edge_count=1,
        nodes=[
            GraphNode(
                node_id="node-2",
                labels=["Entity"],
                properties=_live_metric_node_properties(
                    "node-2",
                    "entity-2",
                    label="Entity",
                    source_properties={"ticker": "BBB"},
                ),
                entity=EntityReference(
                    entity_id="entity-2",
                    entity_type="equity",
                    canonical_id_rule_version="ent-id-rule-v1",
                ),
            ),
            GraphNode(
                node_id="node-1",
                labels=["Entity"],
                properties=_live_metric_node_properties(
                    "node-1",
                    "entity-1",
                    label="Entity",
                    source_properties={"ticker": "AAA"},
                ),
                entity=EntityReference(
                    entity_id="entity-1",
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
                    relationship_type=RelationshipType.SUPPLY_CHAIN.value,
                    source_properties={"weight": 0.7, "evidence_refs": ["fact-edge-1"]},
                ),
                evidence_refs=["fact-edge-1"],
            ),
        ],
    )

    metrics = reload_service.metrics_snapshot_from_graph_snapshot(
        graph_snapshot,
        graph_generation_id=4,
    )
    repeated = reload_service.metrics_snapshot_from_graph_snapshot(
        graph_snapshot,
        graph_generation_id=4,
    )

    assert metrics == repeated
    assert metrics.snapshot_id == graph_snapshot.graph_snapshot_id
    assert metrics.graph_generation_id == 4
    assert metrics.node_count == 2
    assert metrics.edge_count == 1
    assert metrics.key_label_counts == {"Entity": 2}
    assert metrics.checksum


def test_metrics_snapshot_from_graph_snapshot_rejects_compact_snapshot_properties() -> None:
    graph_snapshot = _compact_graph_snapshot()

    with pytest.raises(ValueError, match="live-metric-shaped node properties"):
        reload_service.metrics_snapshot_from_graph_snapshot(
            graph_snapshot,
            graph_generation_id=4,
        )


def test_metrics_snapshot_from_graph_snapshot_rejects_multi_label_nodes() -> None:
    graph_snapshot = _compact_graph_snapshot(
        first_node_labels=["Entity", "Sector"],
    )

    with pytest.raises(ValueError, match="single-label nodes"):
        reload_service.metrics_snapshot_from_graph_snapshot(
            graph_snapshot,
            graph_generation_id=4,
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"batch_size": 0}, "batch_size"),
        ({"timeout_seconds": 0.0}, "timeout_seconds"),
    ],
)
def test_cold_reload_rejects_invalid_parameters_before_destructive_clear(
    kwargs: dict[str, object],
    message: str,
) -> None:
    order: list[str] = []
    store = InMemoryStatusStore(_status())
    reader = StaticCanonicalReader(_reload_plan())
    schema_manager = RecordingSchemaManager(order)

    with pytest.raises(ValueError, match=message):
        reload_service.cold_reload(
            "snapshot-ref-1",
            client=MagicMock(spec=Neo4jClient),
            canonical_reader=reader,
            status_manager=RecordingStatusManager(store, order),
            schema_manager=schema_manager,  # type: ignore[arg-type]
            **kwargs,
        )

    assert order == []
    assert reader.calls == []
    assert schema_manager.drop_calls == []
    assert store.status == _status()


def test_cold_reload_sync_failure_marks_failed_and_preserves_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    store = InMemoryStatusStore(_status(graph_generation_id=3))

    def fake_sync_live_graph(
        promotion_batch: PromotionPlan,
        sync_client: Neo4jClient,
        *,
        batch_size: int,
    ) -> None:
        order.append("sync_live_graph")
        raise RuntimeError("sync failed")

    monkeypatch.setattr(reload_service, "sync_live_graph", fake_sync_live_graph)

    with pytest.raises(RuntimeError, match="sync failed"):
        reload_service.cold_reload(
            "snapshot-ref-1",
            client=MagicMock(spec=Neo4jClient),
            canonical_reader=StaticCanonicalReader(_reload_plan()),
            status_manager=RecordingStatusManager(store, order),
            schema_manager=RecordingSchemaManager(order),  # type: ignore[arg-type]
        )

    assert store.status is not None
    assert store.status.graph_status == "failed"
    assert "mark_failed" in order
    assert "mark_ready" not in order


def test_cold_reload_schema_verify_failure_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    store = InMemoryStatusStore(_status(graph_generation_id=3))
    monkeypatch.setattr(reload_service, "sync_live_graph", _ordered_sync(order))

    with pytest.raises(RuntimeError, match="schema verification failed"):
        reload_service.cold_reload(
            "snapshot-ref-1",
            client=MagicMock(spec=Neo4jClient),
            canonical_reader=StaticCanonicalReader(_reload_plan()),
            status_manager=RecordingStatusManager(store, order),
            schema_manager=RecordingSchemaManager(order, verify_result=False),  # type: ignore[arg-type]
        )

    assert store.status is not None
    assert store.status.graph_status == "failed"
    assert "rebuild_gds_projection" not in order
    assert "mark_ready" not in order


def test_cold_reload_consistency_mismatch_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    store = InMemoryStatusStore(_status(graph_generation_id=3))
    monkeypatch.setattr(reload_service, "sync_live_graph", _ordered_sync(order))
    monkeypatch.setattr(reload_service, "rebuild_gds_projection", _ordered_projection(order))

    def fake_check_live_graph_consistency(*args: object, **kwargs: object) -> bool:
        order.append("check_live_graph_consistency")
        return False

    monkeypatch.setattr(
        reload_service,
        "check_live_graph_consistency",
        fake_check_live_graph_consistency,
    )

    with pytest.raises(RuntimeError, match="consistency check failed"):
        reload_service.cold_reload(
            "snapshot-ref-1",
            client=MagicMock(spec=Neo4jClient),
            canonical_reader=StaticCanonicalReader(_reload_plan()),
            status_manager=RecordingStatusManager(store, order),
            schema_manager=RecordingSchemaManager(order),  # type: ignore[arg-type]
        )

    assert store.status is not None
    assert store.status.graph_status == "failed"
    assert "mark_ready" not in order


def test_cold_reload_gds_missing_marks_failed_and_preserves_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    store = InMemoryStatusStore(_status(graph_generation_id=3))
    monkeypatch.setattr(reload_service, "sync_live_graph", _ordered_sync(order))

    def fake_rebuild_gds_projection(
        projection_client: Neo4jClient,
        projection_name: str,
    ) -> None:
        order.append("rebuild_gds_projection")
        raise RuntimeError("GDS plugin not available")

    monkeypatch.setattr(reload_service, "rebuild_gds_projection", fake_rebuild_gds_projection)

    with pytest.raises(RuntimeError, match="^GDS plugin not available$"):
        reload_service.cold_reload(
            "snapshot-ref-1",
            client=MagicMock(spec=Neo4jClient),
            canonical_reader=StaticCanonicalReader(_reload_plan()),
            status_manager=RecordingStatusManager(store, order),
            schema_manager=RecordingSchemaManager(order),  # type: ignore[arg-type]
        )

    assert store.status is not None
    assert store.status.graph_status == "failed"
    assert "mark_ready" not in order


def test_cold_reload_timeout_after_rebuilding_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    store = InMemoryStatusStore(_status(graph_generation_id=3))
    times = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(reload_service, "monotonic", lambda: next(times))

    with pytest.raises(reload_service.ColdReloadTimeoutError, match="read_cold_reload_plan"):
        reload_service.cold_reload(
            "snapshot-ref-1",
            client=MagicMock(spec=Neo4jClient),
            canonical_reader=StaticCanonicalReader(_reload_plan()),
            status_manager=RecordingStatusManager(store, order),
            schema_manager=RecordingSchemaManager(order),  # type: ignore[arg-type]
            timeout_seconds=1.0,
        )

    assert store.status is not None
    assert store.status.graph_status == "failed"
    assert order == ["mark_rebuilding", "mark_failed"]


def test_cold_reload_timeout_during_blocking_stage_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    store = InMemoryStatusStore(_status(graph_generation_id=3))
    unblock_sync = threading.Event()

    def blocking_sync_live_graph(
        promotion_batch: PromotionPlan,
        sync_client: Neo4jClient,
        *,
        batch_size: int,
    ) -> None:
        order.append("sync_live_graph")
        unblock_sync.wait()

    monkeypatch.setattr(reload_service, "sync_live_graph", blocking_sync_live_graph)

    try:
        with pytest.raises(
            reload_service.ColdReloadTimeoutError,
            match="during sync_live_graph",
        ):
            reload_service.cold_reload(
                "snapshot-ref-1",
                client=MagicMock(spec=Neo4jClient),
                canonical_reader=StaticCanonicalReader(_reload_plan()),
                status_manager=RecordingStatusManager(store, order),
                schema_manager=RecordingSchemaManager(order),  # type: ignore[arg-type]
                timeout_seconds=0.1,
            )
    finally:
        unblock_sync.set()

    assert store.status is not None
    assert store.status.graph_status == "failed"
    assert "sync_live_graph" in order
    assert "mark_failed" in order
    assert "mark_ready" not in order


def test_cold_reload_timeout_blocks_background_post_timeout_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    store = InMemoryStatusStore(_status(graph_generation_id=3))
    release_late_write = threading.Event()
    late_write_finished = threading.Event()
    client = MagicMock(spec=Neo4jClient)
    client.execute_write.side_effect = AssertionError(
        "timeout barrier must block post-timeout writes before Neo4j",
    )

    def blocking_sync_live_graph(
        promotion_batch: PromotionPlan,
        sync_client: Neo4jClient,
        *,
        batch_size: int,
    ) -> None:
        order.append("sync_live_graph")
        release_late_write.wait(timeout=5)
        try:
            sync_client.execute_write("CREATE (:LateWriteAfterTimeout)", {})
        except reload_service.ColdReloadTimeoutError:
            order.append("late_write_blocked")
        finally:
            late_write_finished.set()

    monkeypatch.setattr(reload_service, "sync_live_graph", blocking_sync_live_graph)

    with pytest.raises(
        reload_service.ColdReloadTimeoutError,
        match="during sync_live_graph",
    ):
        reload_service.cold_reload(
            "snapshot-ref-1",
            client=client,
            canonical_reader=StaticCanonicalReader(_reload_plan()),
            status_manager=RecordingStatusManager(store, order),
            schema_manager=RecordingSchemaManager(order),  # type: ignore[arg-type]
            timeout_seconds=0.1,
        )

    release_late_write.set()
    assert late_write_finished.wait(timeout=5)
    client.execute_write.assert_not_called()
    assert "late_write_blocked" in order
    assert store.status is not None
    assert store.status.graph_status == "failed"
    assert "mark_ready" not in order


def test_rebuild_gds_projection_drops_existing_projection_and_creates_full_projection() -> None:
    client = MagicMock(spec=Neo4jClient)
    client.execute_read.side_effect = [
        [{"exists": True}],
        [{"relationship_types": [RelationshipType.SUPPLY_CHAIN.value]}],
    ]

    rebuild_gds_projection(client, "graph_engine_reload")

    assert client.execute_read.call_count == 2
    assert "gds.graph.exists" in client.execute_read.call_args_list[0].args[0]
    assert client.execute_read.call_args_list[0].args[1] == {
        "projection_name": "graph_engine_reload",
    }
    assert "collect(DISTINCT type(relationship))" in client.execute_read.call_args_list[1].args[0]
    assert client.execute_write.call_count == 2
    drop_query, drop_parameters = client.execute_write.call_args_list[0].args
    create_query, create_parameters = client.execute_write.call_args_list[1].args
    assert "gds.graph.drop" in drop_query
    assert drop_parameters == {"projection_name": "graph_engine_reload"}
    assert "gds.graph.project" in create_query
    assert create_parameters["node_projection"] == [label.value for label in NodeLabel]
    assert set(create_parameters["relationship_projection"]) == {"SUPPLY_CHAIN"}
    assert create_parameters["relationship_projection"]["SUPPLY_CHAIN"]["properties"] == {
        "weight": {"property": "weight", "defaultValue": 1.0},
    }


def test_rebuild_gds_projection_creates_without_drop_when_projection_absent() -> None:
    client = MagicMock(spec=Neo4jClient)
    client.execute_read.side_effect = [
        [{"exists": False}],
        [{"relationship_types": [RelationshipType.EVENT_IMPACT.value]}],
    ]

    rebuild_gds_projection(client, "graph_engine_reload")

    assert client.execute_write.call_count == 1
    assert "gds.graph.project" in client.execute_write.call_args.args[0]
    assert set(client.execute_write.call_args.args[1]["relationship_projection"]) == {
        "EVENT_IMPACT",
    }


def test_rebuild_gds_projection_rejects_unknown_live_relationship_types() -> None:
    client = MagicMock(spec=Neo4jClient)
    client.execute_read.side_effect = [
        [{"exists": False}],
        [{"relationship_types": ["UNKNOWN_EDGE"]}],
    ]

    with pytest.raises(ValueError, match="unsupported relationship types"):
        rebuild_gds_projection(client, "graph_engine_reload")

    client.execute_write.assert_not_called()


def test_rebuild_gds_projection_normalizes_missing_gds_errors() -> None:
    client = MagicMock(spec=Neo4jClient)
    client.execute_read.side_effect = RuntimeError(
        "There is no procedure with the name `gds.graph.exists` registered",
    )

    with pytest.raises(RuntimeError, match="^GDS plugin not available$"):
        rebuild_gds_projection(client, "graph_engine_reload")

    client.execute_write.assert_not_called()


def test_rebuild_gds_projection_preserves_non_missing_gds_runtime_errors() -> None:
    client = MagicMock(spec=Neo4jClient)
    client.execute_read.side_effect = [
        [{"exists": False}],
        [{"relationship_types": [RelationshipType.SUPPLY_CHAIN.value]}],
    ]
    client.execute_write.side_effect = RuntimeError("gds.graph.project failed at runtime")

    with pytest.raises(RuntimeError, match="failed at runtime"):
        rebuild_gds_projection(client, "graph_engine_reload")


def _ordered_sync(order: list[str]) -> object:
    def fake_sync_live_graph(
        promotion_batch: PromotionPlan,
        sync_client: Neo4jClient,
        *,
        batch_size: int,
    ) -> None:
        order.append("sync_live_graph")

    return fake_sync_live_graph


def _ordered_projection(order: list[str]) -> object:
    def fake_rebuild_gds_projection(
        projection_client: Neo4jClient,
        projection_name: str,
    ) -> None:
        order.append("rebuild_gds_projection")

    return fake_rebuild_gds_projection


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


def _status(
    *,
    graph_status: Literal["ready", "rebuilding", "failed"] = "ready",
    graph_generation_id: int = 3,
) -> Neo4jGraphStatus:
    return Neo4jGraphStatus(
        graph_status=graph_status,
        graph_generation_id=graph_generation_id,
        node_count=2,
        edge_count=1,
        key_label_counts={"Entity": 2},
        checksum="old-checksum",
        last_verified_at=NOW if graph_status == "ready" else None,
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


def _compact_graph_snapshot(
    *,
    first_node_labels: list[str] | None = None,
) -> GraphSnapshot:
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
                labels=first_node_labels or ["Entity"],
                properties={"ticker": "AAA"},
                entity=EntityReference(
                    entity_id="entity-1",
                    entity_type="equity",
                    canonical_id_rule_version="ent-id-rule-v1",
                ),
            ),
            GraphNode(
                node_id="node-2",
                labels=["Entity"],
                properties={"ticker": "BBB"},
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
                properties={"weight": 0.7},
                evidence_refs=["fact-edge-1"],
            ),
        ],
    )


def _live_metric_node_properties(
    node_id: str,
    canonical_entity_id: str,
    *,
    label: str,
    source_properties: dict[str, object],
) -> dict[str, object]:
    return {
        "node_id": node_id,
        "canonical_entity_id": canonical_entity_id,
        "label": label,
        "properties_json": '{"ticker":"'
        + str(source_properties["ticker"])
        + '"}',
        "created_at": NOW,
        "updated_at": NOW,
        **source_properties,
    }


def _live_metric_edge_properties(
    edge_id: str,
    source_node_id: str,
    target_node_id: str,
    *,
    relationship_type: str,
    source_properties: dict[str, object],
) -> dict[str, object]:
    return {
        "edge_id": edge_id,
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "relationship_type": relationship_type,
        "weight": source_properties["weight"],
        "properties_json": '{"evidence_refs":["fact-edge-1"],"weight":0.7}',
        "created_at": NOW,
        "updated_at": NOW,
        **source_properties,
    }
