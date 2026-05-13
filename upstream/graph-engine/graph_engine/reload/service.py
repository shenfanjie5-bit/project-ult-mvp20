"""Cold reload orchestration for rebuilding the Neo4j live graph."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from threading import Lock
from time import monotonic
from typing import Any, TypeVar, cast

from graph_engine.client import Neo4jClient
from graph_engine.evidence import evidence_refs_from_value
from graph_engine.live_metrics import checksum_payload, sorted_payload_list
from graph_engine.models import (
    ColdReloadPlan,
    GraphMetricsSnapshot,
    GraphSnapshot,
    Neo4jGraphStatus,
    PromotionPlan,
)
from graph_engine.reload.interfaces import CanonicalReader
from graph_engine.reload.projection import rebuild_gds_projection
from graph_engine.schema.manager import DROP_ALL_CONFIRMATION_TOKEN, SchemaManager
from graph_engine.status import GraphStatusManager, check_live_graph_consistency
from graph_engine.sync import sync_live_graph

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")


class ColdReloadTimeoutError(TimeoutError):
    """Raised when cold reload exceeds its hard runtime budget."""


def cold_reload(
    snapshot_ref: str,
    *,
    client: Neo4jClient,
    canonical_reader: CanonicalReader,
    status_manager: GraphStatusManager,
    schema_manager: SchemaManager | None = None,
    batch_size: int = 1000,
    timeout_seconds: float = 300.0,
) -> Neo4jGraphStatus:
    """Rebuild Neo4j from canonical truth and publish ready status only after verification."""

    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    write_barrier = _ReloadWriteBarrier()
    guarded_client = cast(Neo4jClient, _TimeoutAwareNeo4jClient(client, write_barrier))
    guarded_status_manager = _TimeoutAwareStatusManager(status_manager, write_barrier)
    manager = _schema_manager_with_barrier(schema_manager, guarded_client)
    deadline = monotonic() + timeout_seconds
    entered_rebuilding = False

    try:
        rebuilding_status = _run_stage_with_deadline(
            deadline,
            "mark_rebuilding",
            guarded_status_manager.mark_rebuilding,
            write_barrier,
        )
        entered_rebuilding = True

        plan = _run_stage_with_deadline(
            deadline,
            "read_cold_reload_plan",
            lambda: canonical_reader.read_cold_reload_plan(snapshot_ref),
            write_barrier,
        )

        _run_stage_with_deadline(
            deadline,
            "drop_all",
            lambda: manager.drop_all(
                confirmation_token=DROP_ALL_CONFIRMATION_TOKEN,
                graph_status=rebuilding_status,
            ),
            write_barrier,
        )

        _run_stage_with_deadline(
            deadline,
            "sync_live_graph",
            lambda: sync_live_graph(
                build_reload_promotion_plan(plan, snapshot_ref=snapshot_ref),
                guarded_client,
                batch_size=batch_size,
            ),
            write_barrier,
        )

        _run_stage_with_deadline(deadline, "apply_schema", manager.apply_schema, write_barrier)

        schema_verified = _run_stage_with_deadline(
            deadline,
            "verify_schema",
            manager.verify_schema,
            write_barrier,
        )
        if not schema_verified:
            raise RuntimeError("schema verification failed after cold reload")

        _run_stage_with_deadline(
            deadline,
            "rebuild_gds_projection",
            lambda: rebuild_gds_projection(guarded_client, plan.projection_name),
            write_barrier,
        )

        is_consistent = _run_stage_with_deadline(
            deadline,
            "check_live_graph_consistency",
            lambda: check_live_graph_consistency(
                snapshot_ref,
                client=guarded_client,
                snapshot_reader=_ExpectedSnapshotReader(plan.expected_snapshot),
                require_ready=False,
            ),
            write_barrier,
        )
        if not is_consistent:
            raise RuntimeError("live graph consistency check failed after cold reload")

        return _run_stage_with_deadline(
            deadline,
            "mark_ready",
            lambda: guarded_status_manager.mark_ready(
                node_count=plan.expected_snapshot.node_count,
                edge_count=plan.expected_snapshot.edge_count,
                key_label_counts=plan.expected_snapshot.key_label_counts,
                checksum=plan.expected_snapshot.checksum,
                graph_generation_id=plan.expected_snapshot.graph_generation_id,
                reload_completed=True,
            ),
            write_barrier,
        )
    except Exception:
        if entered_rebuilding:
            _mark_failed_safely(status_manager)
        raise


def build_reload_promotion_plan(
    plan: ColdReloadPlan,
    *,
    snapshot_ref: str,
) -> PromotionPlan:
    """Adapt a cold reload plan into the sync layer's canonical promotion batch."""

    return PromotionPlan(
        cycle_id=plan.cycle_id,
        selection_ref=f"cold-reload:{snapshot_ref}",
        delta_ids=[],
        node_records=plan.node_records,
        edge_records=plan.edge_records,
        assertion_records=plan.assertion_records,
        created_at=plan.created_at,
    )


def metrics_snapshot_from_graph_snapshot(
    graph_snapshot: GraphSnapshot,
    *,
    graph_generation_id: int,
) -> GraphMetricsSnapshot:
    """Derive reload consistency metrics from a live-metric-shaped GraphSnapshot."""

    key_label_counts: dict[str, int] = {}
    nodes: list[dict[str, Any]] = []
    for node in graph_snapshot.nodes:
        labels = sorted(str(label) for label in node.labels)
        _validate_single_label_node(node.node_id, labels)
        for label in labels:
            key_label_counts[label] = key_label_counts.get(label, 0) + 1
        properties = dict(node.properties)
        _validate_live_metric_node_properties(node, labels[0], properties)
        nodes.append(
            {
                "labels": labels,
                "node_id": node.node_id,
                "canonical_entity_id": (
                    node.entity.entity_id
                    if node.entity is not None
                    else properties.get("canonical_entity_id")
                ),
                "properties": properties,
            },
        )

    relationships: list[dict[str, Any]] = []
    for edge in graph_snapshot.edges:
        properties = dict(edge.properties)
        _validate_live_metric_edge_properties(edge, properties)
        evidence_refs = evidence_refs_from_value(edge.evidence_refs)
        if evidence_refs:
            properties["evidence_refs"] = evidence_refs
        relationships.append(
            {
                "source_node_id": edge.source_node,
                "target_node_id": edge.target_node,
                "relationship_type": edge.relation_type,
                "edge_id": edge.edge_id,
                "properties": properties,
            },
        )

    payload = {
        "node_count": graph_snapshot.node_count,
        "edge_count": graph_snapshot.edge_count,
        "nodes": sorted_payload_list(nodes),
        "relationships": sorted_payload_list(relationships),
    }
    return GraphMetricsSnapshot(
        cycle_id=graph_snapshot.cycle_id,
        snapshot_id=graph_snapshot.graph_snapshot_id,
        graph_generation_id=graph_generation_id,
        node_count=graph_snapshot.node_count,
        edge_count=graph_snapshot.edge_count,
        key_label_counts=key_label_counts,
        checksum=checksum_payload(payload),
        created_at=graph_snapshot.created_at,
    )


def _validate_single_label_node(node_id: str, labels: list[str]) -> None:
    if len(labels) != 1:
        raise ValueError(
            "cold reload GraphSnapshot bridge requires single-label nodes; "
            f"node {node_id!r} has labels {labels!r}",
        )


def _validate_live_metric_node_properties(
    node: Any,
    label: str,
    properties: dict[str, Any],
) -> None:
    _require_snapshot_properties(
        "node",
        node.node_id,
        properties,
        {"node_id", "label", "properties_json", "created_at", "updated_at"},
    )
    mismatches = []
    if properties.get("node_id") != node.node_id:
        mismatches.append("node_id")
    if properties.get("label") != label:
        mismatches.append("label")
    if node.entity is not None:
        _require_snapshot_properties(
            "node",
            node.node_id,
            properties,
            {"canonical_entity_id"},
        )
        if properties.get("canonical_entity_id") != node.entity.entity_id:
            mismatches.append("canonical_entity_id")
    if mismatches:
        raise ValueError(
            "cold reload GraphSnapshot bridge requires live-metric-shaped "
            f"node properties for {node.node_id!r}; mismatched "
            + ", ".join(mismatches),
        )


def _validate_live_metric_edge_properties(
    edge: Any,
    properties: dict[str, Any],
) -> None:
    _require_snapshot_properties(
        "edge",
        edge.edge_id,
        properties,
        {
            "edge_id",
            "source_node_id",
            "target_node_id",
            "relationship_type",
            "weight",
            "properties_json",
            "created_at",
            "updated_at",
        },
    )
    mismatches = [
        field_name
        for field_name, expected_value in (
            ("edge_id", edge.edge_id),
            ("source_node_id", edge.source_node),
            ("target_node_id", edge.target_node),
            ("relationship_type", edge.relation_type),
        )
        if properties.get(field_name) != expected_value
    ]
    if mismatches:
        raise ValueError(
            "cold reload GraphSnapshot bridge requires live-metric-shaped "
            f"edge properties for {edge.edge_id!r}; mismatched "
            + ", ".join(mismatches),
        )


def _require_snapshot_properties(
    object_kind: str,
    object_id: str,
    properties: dict[str, Any],
    required_keys: set[str],
) -> None:
    missing_keys = sorted(required_keys - set(properties))
    if missing_keys:
        raise ValueError(
            "cold reload GraphSnapshot bridge requires live-metric-shaped "
            f"{object_kind} properties for {object_id!r}; missing "
            + ", ".join(missing_keys),
        )


class _ExpectedSnapshotReader:
    def __init__(self, snapshot: GraphMetricsSnapshot) -> None:
        self._snapshot = snapshot

    def read_graph_snapshot(self, snapshot_ref: str) -> GraphMetricsSnapshot:
        return self._snapshot


def _run_stage_with_deadline(
    deadline: float,
    stage: str,
    operation: Callable[[], _T],
    write_barrier: "_ReloadWriteBarrier",
) -> _T:
    remaining_seconds = deadline - monotonic()
    if remaining_seconds <= 0:
        raise ColdReloadTimeoutError(f"cold reload timed out before {stage}")

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"cold-reload-{stage}")
    future = executor.submit(operation)
    timed_out = False
    try:
        return future.result(timeout=remaining_seconds)
    except FutureTimeoutError as exc:
        timed_out = True
        write_barrier.expire()
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise ColdReloadTimeoutError(f"cold reload timed out during {stage}") from exc
    finally:
        if not timed_out:
            executor.shutdown(wait=True)


class _ReloadWriteBarrier:
    def __init__(self) -> None:
        self._expired = False
        self._lock = Lock()

    def expire(self) -> None:
        with self._lock:
            self._expired = True

    def assert_open(self, operation: str) -> None:
        with self._lock:
            expired = self._expired
        if expired:
            raise ColdReloadTimeoutError(f"cold reload timed out before {operation}")


class _TimeoutAwareNeo4jClient:
    def __init__(self, client: Neo4jClient, write_barrier: _ReloadWriteBarrier) -> None:
        self._client = client
        self._write_barrier = write_barrier

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._client.execute_read(query, parameters)

    def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self._write_barrier.assert_open("Neo4j write")
        return self._client.execute_write(query, parameters)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class _TimeoutAwareStatusManager:
    def __init__(
        self,
        status_manager: GraphStatusManager,
        write_barrier: _ReloadWriteBarrier,
    ) -> None:
        self._status_manager = status_manager
        self._write_barrier = write_barrier

    def mark_rebuilding(self) -> Neo4jGraphStatus:
        self._write_barrier.assert_open("status write")
        return self._status_manager.mark_rebuilding()

    def mark_ready(self, **kwargs: Any) -> Neo4jGraphStatus:
        self._write_barrier.assert_open("status write")
        return self._status_manager.mark_ready(**kwargs)


def _schema_manager_with_barrier(
    schema_manager: SchemaManager | None,
    guarded_client: Neo4jClient,
) -> SchemaManager:
    if schema_manager is None:
        return SchemaManager(guarded_client)
    if hasattr(schema_manager, "client"):
        setattr(schema_manager, "client", guarded_client)
    return schema_manager


def _mark_failed_safely(status_manager: GraphStatusManager) -> None:
    try:
        status_manager.mark_failed()
    except Exception:  # noqa: BLE001 - preserve the original reload failure.
        _LOGGER.exception("failed to mark cold reload status as failed")
