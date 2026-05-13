"""Graph and impact snapshot generation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from contracts.core import Direction, __version__ as CONTRACT_VERSION
from contracts.schemas import EntityReference
from contracts.schemas.graph import GraphEdge, GraphNode

from graph_engine.client import Neo4jClient
from graph_engine.evidence import (
    evidence_refs_from_properties,
    evidence_refs_from_value,
)
from graph_engine.live_metrics import (
    LiveGraphMetrics,
    checksum_payload as _checksum_payload,
    read_live_graph_metric_payload,
    read_live_graph_metrics,
)
from graph_engine.models import (
    GraphImpactSnapshot,
    GraphSnapshot,
    Neo4jGraphStatus,
    PropagationChannel,
    PropagationResult,
)
from graph_engine.propagation.context import RegimeContextReader, build_propagation_context
from graph_engine.propagation.pipeline import run_full_propagation
from graph_engine.snapshots.writer import SnapshotWriter
from graph_engine.status import GraphStatusManager, hold_ready_read, require_ready_status

_DEFAULT_SNAPSHOT_CHANNELS: tuple[PropagationChannel, ...] = (
    "fundamental",
    "event",
    "reflexive",
)
# Used only when the canonical record did not carry the entity-registry rule version.
_UNKNOWN_CANONICAL_ID_RULE_VERSION = "unknown"


def build_graph_snapshot(
    cycle_id: str,
    graph_generation_id: int,
    client: Neo4jClient,
    *,
    status_manager: GraphStatusManager,
) -> GraphSnapshot:
    """Read live graph metrics and return a deterministic structural snapshot."""

    with hold_ready_read(status_manager, "graph snapshot generation") as ready_status:
        _validate_generation_input(graph_generation_id, ready_status)
        metrics = _read_graph_metric_payload(client)
        return _graph_snapshot_from_metrics(
            cycle_id,
            graph_generation_id,
            metrics=metrics,
        )


def build_graph_impact_snapshot(
    cycle_id: str,
    world_state_ref: str,
    propagation_result: PropagationResult,
) -> GraphImpactSnapshot:
    """Build the downstream impact snapshot from a propagation result."""

    channel_breakdown = _complete_channel_breakdown(propagation_result.channel_breakdown)
    payload = {
        "cycle_id": cycle_id,
        "graph_generation_id": propagation_result.graph_generation_id,
        "world_state_ref": world_state_ref,
        "activated_paths": propagation_result.activated_paths,
        "impacted_entities": propagation_result.impacted_entities,
        "channel_breakdown": channel_breakdown,
    }
    impact_hash = _checksum_payload(payload)
    affected_entities = _entity_references_from_impacted_entities(
        propagation_result.impacted_entities,
    )
    target_entities = affected_entities or _entity_references_from_paths(
        propagation_result.activated_paths,
    )
    evidence_refs, paths_without_evidence = _evidence_refs_from_paths(
        propagation_result.activated_paths,
    )
    if not target_entities:
        raise ValueError(
            "GraphImpactSnapshot requires at least one target entity "
            f"for cycle_id={cycle_id!r}, world_state_ref={world_state_ref!r}, "
            "graph_generation_id="
            f"{propagation_result.graph_generation_id!r}",
        )
    if paths_without_evidence:
        raise ValueError(
            "GraphImpactSnapshot requires real evidence references for every "
            "activated path "
            f"for cycle_id={cycle_id!r}, world_state_ref={world_state_ref!r}, "
            "graph_generation_id="
            f"{propagation_result.graph_generation_id!r}; "
            f"paths_without_evidence={paths_without_evidence}",
        )
    if not evidence_refs:
        raise ValueError(
            "GraphImpactSnapshot requires at least one real evidence reference "
            f"for cycle_id={cycle_id!r}, world_state_ref={world_state_ref!r}, "
            "graph_generation_id="
            f"{propagation_result.graph_generation_id!r}",
        )

    return GraphImpactSnapshot(
        cycle_id=cycle_id,
        impact_snapshot_id=f"graph-impact-{cycle_id}-{impact_hash[:12]}",
        version=CONTRACT_VERSION,
        created_at=datetime.now(timezone.utc),
        target_entities=target_entities,
        affected_entities=affected_entities,
        affected_sectors=_affected_sectors(propagation_result.impacted_entities),
        direction=_impact_direction(propagation_result.impacted_entities),
        impact_score=_impact_score(propagation_result.impacted_entities),
        evidence_refs=evidence_refs,
    )


def compute_graph_snapshots(
    cycle_id: str,
    world_state_ref: str,
    *,
    client: Neo4jClient,
    graph_generation_id: int | None = None,
    regime_reader: RegimeContextReader,
    snapshot_writer: SnapshotWriter,
    status_manager: GraphStatusManager,
    graph_status: Neo4jGraphStatus | None = None,
    graph_name: str | None = None,
    enabled_channels: Sequence[PropagationChannel] | None = None,
    max_iterations: int = 20,
    result_limit: int = 100,
) -> tuple[GraphSnapshot, GraphImpactSnapshot]:
    """Run full propagation and write graph plus impact snapshots."""

    with hold_ready_read(status_manager, "snapshot generation") as ready_status:
        if graph_status is not None:
            require_ready_status(graph_status)
            _validate_status_matches_ready_status(ready_status, graph_status)
        _validate_generation_input(graph_generation_id, ready_status)
        _validate_pre_propagation_status_and_metrics(ready_status, client)
        requested_channels = list(
            _DEFAULT_SNAPSHOT_CHANNELS if enabled_channels is None else enabled_channels
        )
        context = build_propagation_context(
            cycle_id,
            world_state_ref,
            ready_status.graph_generation_id,
            regime_reader=regime_reader,
            graph_status=ready_status,
            enabled_channels=requested_channels,
        )
        propagation_result = run_full_propagation(
            context,
            client,
            status_manager=status_manager,
            graph_name=graph_name,
            max_iterations=max_iterations,
            result_limit=result_limit,
        )
        graph_snapshot = build_graph_snapshot(
            cycle_id,
            ready_status.graph_generation_id,
            client,
            status_manager=status_manager,
        )
        impact_snapshot = build_graph_impact_snapshot(
            cycle_id,
            world_state_ref,
            propagation_result,
        )
        _validate_publication_status_and_metrics(
            ready_status,
            status_manager,
            client,
        )
        snapshot_writer.write_snapshots(graph_snapshot, impact_snapshot)
        return graph_snapshot, impact_snapshot


def _validate_generation_input(
    graph_generation_id: int | None,
    graph_status: Neo4jGraphStatus,
) -> None:
    if graph_generation_id is None:
        return
    if graph_generation_id != graph_status.graph_generation_id:
        raise ValueError(
            "graph_generation_id disagrees with Neo4jGraphStatus: "
            f"received {graph_generation_id}, "
            f"status has {graph_status.graph_generation_id}",
        )


def _complete_channel_breakdown(channel_breakdown: dict[str, Any]) -> dict[str, Any]:
    completed: dict[str, Any] = {
        channel: channel_breakdown.get(channel, {})
        for channel in _DEFAULT_SNAPSHOT_CHANNELS
    }
    for key, value in channel_breakdown.items():
        if key not in completed and key != "merged":
            completed[key] = value
    completed["merged"] = channel_breakdown.get("merged", {})
    return completed


def _validate_pre_propagation_status_and_metrics(
    ready_status: Neo4jGraphStatus,
    client: Neo4jClient,
) -> None:
    node_count, edge_count, key_label_counts, checksum = _read_graph_metrics(client)
    _validate_status_metrics(
        ready_status,
        node_count=node_count,
        edge_count=edge_count,
        key_label_counts=key_label_counts,
        checksum=checksum,
    )


def _validate_status_metrics(
    graph_status: Neo4jGraphStatus,
    *,
    node_count: int,
    edge_count: int,
    key_label_counts: dict[str, int],
    checksum: str,
) -> None:
    mismatches: list[str] = []
    if graph_status.node_count != node_count:
        mismatches.append(
            f"node_count status={graph_status.node_count} live={node_count}",
        )
    if graph_status.edge_count != edge_count:
        mismatches.append(
            f"edge_count status={graph_status.edge_count} live={edge_count}",
        )
    if graph_status.key_label_counts != key_label_counts:
        mismatches.append(
            "key_label_counts "
            f"status={graph_status.key_label_counts!r} live={key_label_counts!r}",
        )
    if graph_status.checksum != checksum:
        mismatches.append(
            f"checksum status={graph_status.checksum!r} live={checksum!r}",
        )
    if mismatches:
        raise ValueError(
            "live graph metrics disagree with Neo4jGraphStatus: "
            + "; ".join(mismatches),
        )


def _validate_publication_status_and_metrics(
    ready_status: Neo4jGraphStatus,
    status_manager: GraphStatusManager,
    client: Neo4jClient,
) -> None:
    try:
        current_status = require_ready_status(status_manager.get_status())
    except PermissionError as exc:
        raise RuntimeError("ready graph status changed before snapshot publication") from exc
    _validate_status_matches_ready_status(current_status, ready_status)

    node_count, edge_count, key_label_counts, checksum = _read_graph_metrics(client)
    _validate_status_metrics(
        current_status,
        node_count=node_count,
        edge_count=edge_count,
        key_label_counts=key_label_counts,
        checksum=checksum,
    )


def _validate_status_matches_ready_status(
    current_status: Neo4jGraphStatus,
    ready_status: Neo4jGraphStatus,
) -> None:
    checks = (
        (
            "graph_generation_id",
            current_status.graph_generation_id,
            ready_status.graph_generation_id,
        ),
        ("node_count", current_status.node_count, ready_status.node_count),
        ("edge_count", current_status.edge_count, ready_status.edge_count),
        (
            "key_label_counts",
            current_status.key_label_counts,
            ready_status.key_label_counts,
        ),
        ("checksum", current_status.checksum, ready_status.checksum),
    )
    mismatches = [
        f"{field} current={current_value!r} ready={ready_value!r}"
        for field, current_value, ready_value in checks
        if current_value != ready_value
    ]
    if mismatches:
        raise RuntimeError(
            "ready graph status changed before snapshot publication: "
            + "; ".join(mismatches),
        )


def _graph_snapshot_from_metrics(
    cycle_id: str,
    graph_generation_id: int,
    *,
    metrics: LiveGraphMetrics,
) -> GraphSnapshot:
    checksum = metrics.checksum
    return GraphSnapshot(
        cycle_id=cycle_id,
        graph_snapshot_id=f"graph-snapshot-{cycle_id}-{graph_generation_id}-{checksum[:12]}",
        version=CONTRACT_VERSION,
        node_count=metrics.node_count,
        edge_count=metrics.edge_count,
        nodes=[_contract_node(node) for node in metrics.nodes],
        edges=[_contract_edge(relationship) for relationship in metrics.relationships],
        created_at=datetime.now(timezone.utc),
    )


def _read_graph_metrics(client: Neo4jClient) -> tuple[int, int, dict[str, int], str]:
    return read_live_graph_metrics(client, strict=True)


def _read_graph_metric_payload(client: Neo4jClient) -> LiveGraphMetrics:
    return read_live_graph_metric_payload(client, strict=True)


def _contract_node(node: dict[str, Any]) -> GraphNode:
    labels = _string_values(node.get("labels")) or ["Entity"]
    properties = _dict_value(node.get("properties"))
    entity = _entity_reference(
        entity_id=node.get("canonical_entity_id") or properties.get("canonical_entity_id"),
        labels=labels,
        canonical_id_rule_version=(
            node.get("canonical_id_rule_version")
            or properties.get("canonical_id_rule_version")
        ),
    )
    return GraphNode(
        node_id=str(node.get("node_id") or properties.get("node_id") or ""),
        labels=labels,
        properties=properties,
        entity=entity,
    )


def _contract_edge(relationship: dict[str, Any]) -> GraphEdge:
    properties = _dict_value(relationship.get("properties"))
    return GraphEdge(
        edge_id=str(relationship.get("edge_id") or properties.get("edge_id") or ""),
        source_node=str(relationship.get("source_node_id") or ""),
        target_node=str(relationship.get("target_node_id") or ""),
        relation_type=str(relationship.get("relationship_type") or ""),
        properties=properties,
        evidence_refs=evidence_refs_from_properties(properties),
    )


def _entity_references_from_impacted_entities(
    impacted_entities: list[dict[str, Any]],
) -> list[EntityReference]:
    references: list[EntityReference] = []
    seen: set[str] = set()
    for entity in impacted_entities:
        reference = _entity_reference(
            entity_id=entity.get("canonical_entity_id") or entity.get("node_id"),
            labels=entity.get("labels"),
            canonical_id_rule_version=entity.get("canonical_id_rule_version"),
        )
        if reference is None or reference.entity_id in seen:
            continue
        references.append(reference)
        seen.add(reference.entity_id)
    return references


def _entity_references_from_paths(activated_paths: list[dict[str, Any]]) -> list[EntityReference]:
    references: list[EntityReference] = []
    seen: set[str] = set()
    for path in activated_paths:
        for entity_id, labels, canonical_id_rule_version in (
            (
                path.get("source_entity_id") or path.get("source_node_id"),
                path.get("source_labels"),
                path.get("source_canonical_id_rule_version"),
            ),
            (
                path.get("target_entity_id") or path.get("target_node_id"),
                path.get("target_labels"),
                path.get("target_canonical_id_rule_version"),
            ),
        ):
            reference = _entity_reference(
                entity_id=entity_id,
                labels=labels,
                canonical_id_rule_version=canonical_id_rule_version,
            )
            if reference is None or reference.entity_id in seen:
                continue
            references.append(reference)
            seen.add(reference.entity_id)
    return references


def _entity_reference(
    entity_id: Any,
    labels: Any,
    *,
    canonical_id_rule_version: Any = None,
) -> EntityReference | None:
    if entity_id is None or str(entity_id) == "":
        return None
    entity_type = (_string_values(labels) or ["unknown"])[0].lower()
    return EntityReference(
        entity_id=str(entity_id),
        entity_type=entity_type,
        canonical_id_rule_version=(
            str(canonical_id_rule_version)
            if canonical_id_rule_version is not None and str(canonical_id_rule_version)
            else _UNKNOWN_CANONICAL_ID_RULE_VERSION
        ),
    )


def _affected_sectors(impacted_entities: list[dict[str, Any]]) -> list[str]:
    sectors = {
        str(entity.get("node_id"))
        for entity in impacted_entities
        if "Sector" in _string_values(entity.get("labels")) and entity.get("node_id") is not None
    }
    return sorted(sectors)


def _impact_direction(impacted_entities: list[dict[str, Any]]) -> Direction:
    total_score = sum(_float_value(entity.get("score")) for entity in impacted_entities)
    if total_score > 0:
        return Direction.BULLISH
    if total_score < 0:
        return Direction.BEARISH
    return Direction.NEUTRAL


def _impact_score(impacted_entities: list[dict[str, Any]]) -> float:
    total_score = sum(_float_value(entity.get("score")) for entity in impacted_entities)
    return max(-1.0, min(1.0, total_score))


def _evidence_refs_from_paths(
    activated_paths: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    refs: set[str] = set()
    paths_without_evidence: list[str] = []
    for path in activated_paths:
        path_refs = set(evidence_refs_from_value(path.get("evidence_refs")))
        path_refs.update(evidence_refs_from_value(path.get("evidence_ref")))
        path_refs.update(
            evidence_refs_from_value(path.get("evidence"), allow_mapping=True),
        )
        if path_refs:
            refs.update(path_refs)
        else:
            paths_without_evidence.append(_path_identifier(path))
    return sorted(refs), paths_without_evidence


def _path_identifier(path: dict[str, Any]) -> str:
    edge_id = path.get("edge_id")
    if edge_id is not None and str(edge_id):
        return str(edge_id)
    return (
        f"{path.get('source_node_id', '<unknown-source>')}"
        f"->{path.get('target_node_id', '<unknown-target>')}"
    )


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item) for item in value if str(item))
    if value is None:
        return []
    return [str(value)] if str(value) else []


def _float_value(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)
