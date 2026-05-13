"""Promotion service entry point."""

from __future__ import annotations

from datetime import datetime, timezone

from contracts.schemas import CandidateGraphDelta

from graph_engine.client import Neo4jClient
from graph_engine.live_metrics import read_live_graph_metrics
from graph_engine.models import Neo4jGraphStatus, PromotionPlan
from graph_engine.promotion.interfaces import (
    CandidateDeltaReader,
    CanonicalWriter,
    EntityAnchorReader,
)
from graph_engine.promotion.planner import (
    build_promotion_plan,
    freeze_contract_deltas,
    validate_entity_anchors,
)
from graph_engine.status import GraphStatusManager
from graph_engine.sync import sync_live_graph


def promote_graph_deltas(
    cycle_id: str,
    selection_ref: str,
    *,
    candidate_reader: CandidateDeltaReader,
    entity_reader: EntityAnchorReader,
    canonical_writer: CanonicalWriter,
    client: Neo4jClient | None = None,
    status_manager: GraphStatusManager | None = None,
    sync_to_live_graph: bool = True,
    allowed_relationship_types: set[str] | None = None,
) -> PromotionPlan:
    """Promote selected contract graph deltas, then optionally mirror them to Neo4j."""

    if sync_to_live_graph and client is None:
        raise ValueError("client is required when sync_to_live_graph is True")
    if sync_to_live_graph and status_manager is None:
        raise ValueError("status_manager is required when sync_to_live_graph is True")

    contract_deltas = [
        _require_contract_delta(delta)
        for delta in candidate_reader.read_candidate_graph_deltas(cycle_id, selection_ref)
    ]
    deltas = freeze_contract_deltas(cycle_id, contract_deltas, entity_reader)
    validate_entity_anchors(deltas, entity_reader)
    plan = build_promotion_plan(cycle_id, selection_ref, deltas)
    if allowed_relationship_types is not None:
        _validate_allowed_relationship_types(plan, allowed_relationship_types)

    if sync_to_live_graph and status_manager is not None:
        status_manager.require_ready()

    canonical_writer.write_canonical_records(plan)

    if sync_to_live_graph and client is not None:
        if status_manager is None:
            # Invariant: when sync_to_live_graph is True, the
            # `status_manager.require_ready()` block above already ran, which
            # requires status_manager to be non-None. Retained as explicit
            # raise so the invariant survives `python -O`.
            raise AssertionError(
                "invariant: status_manager must be non-None when sync_to_live_graph "
                "is True (already enforced by require_ready barrier above)"
            )
        _sync_live_graph_with_status_barrier(plan, client, status_manager)

    return plan


def _validate_allowed_relationship_types(
    plan: PromotionPlan,
    allowed_relationship_types: set[str],
) -> None:
    if not allowed_relationship_types:
        raise ValueError("allowed_relationship_types must not be empty when provided")

    relation_types = sorted({edge.relationship_type for edge in plan.edge_records})
    disallowed = [
        relationship_type
        for relationship_type in relation_types
        if relationship_type not in allowed_relationship_types
    ]
    if disallowed:
        raise PermissionError(
            "promotion plan contains relationship types outside the allowlist: "
            + ", ".join(disallowed),
        )


def _require_contract_delta(delta: object) -> CandidateGraphDelta:
    if not isinstance(delta, CandidateGraphDelta):
        raise TypeError(
            "CandidateDeltaReader must return contracts.schemas.CandidateGraphDelta "
            f"values, got {type(delta).__name__}",
        )
    return delta


def _sync_live_graph_with_status_barrier(
    plan: PromotionPlan,
    client: Neo4jClient,
    status_manager: GraphStatusManager,
) -> None:
    """Mirror a promotion only while the ready status token still holds."""

    ready_status, locked_status = status_manager.begin_sync()

    try:
        _require_status_token_unchanged(
            status_manager,
            locked_status,
            "before promotion live sync",
        )
        sync_live_graph(plan, client)
        _require_status_token_unchanged(
            status_manager,
            locked_status,
            "after promotion live sync",
        )
        status_manager.finish_sync(
            expected_status=locked_status,
            ready_status=_ready_status_from_live_graph(client, ready_status),
        )
    except Exception:
        _mark_sync_failed_safely(status_manager, locked_status)
        raise


def _require_status_token_unchanged(
    status_manager: GraphStatusManager,
    expected_status: Neo4jGraphStatus,
    stage: str,
) -> None:
    current_status = status_manager.get_status()
    if current_status != expected_status:
        raise RuntimeError(
            f"graph_status changed {stage}; "
            "live graph mutation must be replayed",
        )


def _mark_sync_failed_safely(
    status_manager: GraphStatusManager,
    locked_status: Neo4jGraphStatus,
) -> None:
    try:
        status_manager.mark_sync_failed(expected_status=locked_status)
    except Exception:  # noqa: BLE001 - preserve the original promotion sync failure.
        return


def _ready_status_from_live_graph(
    client: Neo4jClient,
    previous_ready_status: Neo4jGraphStatus,
) -> Neo4jGraphStatus:
    node_count, edge_count, key_label_counts, checksum = read_live_graph_metrics(client)
    return Neo4jGraphStatus(
        graph_status="ready",
        graph_generation_id=previous_ready_status.graph_generation_id + 1,
        node_count=node_count,
        edge_count=edge_count,
        key_label_counts=key_label_counts,
        checksum=checksum,
        last_verified_at=datetime.now(timezone.utc),
        last_reload_at=previous_ready_status.last_reload_at,
    )
