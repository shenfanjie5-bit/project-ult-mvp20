"""Phase 0 consistency checks between canonical snapshots and the live graph."""

from __future__ import annotations

import logging
from typing import Protocol, TypeAlias

from graph_engine.client import Neo4jClient
from graph_engine.evidence import evidence_refs_from_value
from graph_engine.live_metrics import checksum_payload, read_live_graph_metrics, sorted_payload_list
from graph_engine.models import GraphMetricsSnapshot, GraphSnapshot, Neo4jGraphStatus
from graph_engine.status.manager import GraphStatusManager, hold_ready_read

_LOGGER = logging.getLogger(__name__)
ConsistencySnapshot: TypeAlias = GraphMetricsSnapshot | GraphSnapshot


class CanonicalSnapshotReader(Protocol):
    """Read canonical graph snapshots from the data-platform/Iceberg boundary."""

    def read_graph_snapshot(self, snapshot_ref: str) -> ConsistencySnapshot:
        """Return the canonical snapshot referenced by snapshot_ref."""


def check_live_graph_consistency(
    snapshot_ref: str,
    *,
    client: Neo4jClient,
    snapshot_reader: CanonicalSnapshotReader,
    status_manager: GraphStatusManager | None = None,
    require_ready: bool = True,
) -> bool:
    """Return whether live Neo4j metrics match the canonical graph snapshot."""

    if require_ready:
        if status_manager is None:
            raise ValueError("status_manager is required when require_ready=True")
        with hold_ready_read(status_manager, "live graph consistency") as status:
            return _check_live_graph_consistency_after_status(
                snapshot_ref,
                client=client,
                snapshot_reader=snapshot_reader,
                status=status,
            )

    current_status = _resolve_status(status_manager)
    return _check_live_graph_consistency_after_status(
        snapshot_ref,
        client=client,
        snapshot_reader=snapshot_reader,
        status=current_status,
    )


def _check_live_graph_consistency_after_status(
    snapshot_ref: str,
    *,
    client: Neo4jClient,
    snapshot_reader: CanonicalSnapshotReader,
    status: Neo4jGraphStatus | None,
) -> bool:
    try:
        snapshot = snapshot_reader.read_graph_snapshot(snapshot_ref)
        (
            snapshot_generation_id,
            snapshot_node_count,
            snapshot_edge_count,
            snapshot_labels,
            snapshot_checksum,
        ) = _snapshot_metric_values(snapshot)
    except Exception:
        _LOGGER.exception(
            "live graph consistency snapshot read failed",
            extra={"snapshot_ref": snapshot_ref, "failure_stage": "snapshot_read"},
        )
        return False

    if status is not None and snapshot_generation_id is None:
        _LOGGER.warning(
            "live graph consistency snapshot missing generation metadata",
            extra={
                "snapshot_ref": snapshot_ref,
                "failure_stage": "result_validation",
                "status_generation_id": status.graph_generation_id,
            },
        )
        return False

    try:
        node_count, edge_count, key_label_counts, checksum = _read_live_graph_metrics(client)
    except Exception:
        _LOGGER.exception(
            "live graph consistency live graph read failed",
            extra={"snapshot_ref": snapshot_ref, "failure_stage": "live_graph_read"},
        )
        return False

    if (
        status is not None
        and snapshot_generation_id != status.graph_generation_id
    ):
        _LOGGER.warning(
            "live graph consistency generation mismatch",
            extra={
                "snapshot_ref": snapshot_ref,
                "failure_stage": "result_validation",
                "snapshot_generation_id": snapshot_generation_id,
                "status_generation_id": status.graph_generation_id,
            },
        )
        return False

    mismatches = [
        field_name
        for field_name, snapshot_value, live_value in (
            ("node_count", snapshot_node_count, node_count),
            ("edge_count", snapshot_edge_count, edge_count),
            ("key_label_counts", snapshot_labels, key_label_counts),
            ("checksum", snapshot_checksum, checksum),
        )
        if snapshot_value != live_value
    ]
    if mismatches:
        _LOGGER.warning(
            "live graph consistency metric mismatch",
            extra={
                "snapshot_ref": snapshot_ref,
                "failure_stage": "result_validation",
                "mismatches": mismatches,
            },
        )
        return False
    return True


def _resolve_status(
    status_manager: GraphStatusManager | None,
) -> Neo4jGraphStatus | None:
    if status_manager is None:
        return None
    try:
        return status_manager.get_status()
    except LookupError:
        return None


def _read_live_graph_metrics(client: Neo4jClient) -> tuple[int, int, dict[str, int], str]:
    return read_live_graph_metrics(client, strict=True)


def _snapshot_metric_values(
    snapshot: ConsistencySnapshot,
) -> tuple[int | None, int, int, dict[str, int], str]:
    if isinstance(snapshot, GraphMetricsSnapshot):
        return (
            snapshot.graph_generation_id,
            snapshot.node_count,
            snapshot.edge_count,
            snapshot.key_label_counts,
            snapshot.checksum,
        )

    key_label_counts: dict[str, int] = {}
    nodes = []
    for node in snapshot.nodes:
        labels = sorted(str(label) for label in node.labels)
        for label in labels:
            key_label_counts[label] = key_label_counts.get(label, 0) + 1
        properties = dict(node.properties)
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
            }
        )

    relationships = []
    for edge in snapshot.edges:
        properties = dict(edge.properties)
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
            }
        )
    payload = {
        "node_count": snapshot.node_count,
        "edge_count": snapshot.edge_count,
        "nodes": sorted_payload_list(nodes),
        "relationships": sorted_payload_list(relationships),
    }
    return (
        None,
        snapshot.node_count,
        snapshot.edge_count,
        key_label_counts,
        checksum_payload(payload),
    )
