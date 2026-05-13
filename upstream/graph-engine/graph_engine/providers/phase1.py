"""Dagster Phase 1 asset factory for graph promotion and snapshots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol

from graph_engine.client import Neo4jClient
from graph_engine.models import GraphImpactSnapshot, GraphSnapshot, Neo4jGraphStatus, PromotionPlan
from graph_engine.promotion import promote_graph_deltas
from graph_engine.promotion.interfaces import (
    CandidateDeltaReader,
    CanonicalWriter,
    EntityAnchorReader,
)
from graph_engine.propagation.context import RegimeContextReader
from graph_engine.reload import ArtifactCanonicalReader, CanonicalReader
from graph_engine.snapshots import SnapshotWriter, compute_graph_snapshots
from graph_engine.status import GraphStatusManager, require_ready_status

PHASE0_READINESS_ASSET_KEY = "phase0_readiness_ping"
PHASE0_CANDIDATE_FREEZE_ASSET_KEY = "candidate_freeze"
PHASE0_GRAPH_STATUS_ASSET_KEY = "graph_status"
PHASE1_GROUP_NAME = "phase1"
PHASE1_GRAPH_PROMOTION_ASSET_KEY = "graph_promotion"
PHASE1_GRAPH_SNAPSHOT_ASSET_KEY = "graph_snapshot"
GRAPH_PHASE1_RESOURCE_KEY = "graph_phase1_runtime"


@dataclass(frozen=True, slots=True)
class GraphPromotionAssetRequest:
    """Runtime input resolved from Phase 0 asset outputs."""

    cycle_id: str
    selection_ref: str
    phase0_readiness: object
    candidate_freeze: object
    graph_status: object


@dataclass(frozen=True, slots=True)
class GraphPromotionAssetResult:
    """Materialized graph promotion result passed to ``graph_snapshot``."""

    cycle_id: str
    selection_ref: str
    graph_generation_id: int
    delta_ids: tuple[str, ...]
    plan: PromotionPlan
    graph_status: Neo4jGraphStatus


@dataclass(frozen=True, slots=True)
class GraphSnapshotAssetRequest:
    """Runtime input for the graph snapshot asset."""

    cycle_id: str
    world_state_ref: str
    graph_generation_id: int
    promotion: GraphPromotionAssetResult


@dataclass(frozen=True, slots=True)
class ColdReloadArtifactProof:
    """Proof that the persisted graph snapshot can seed cold reload."""

    snapshot_ref: str
    cycle_id: str
    snapshot_id: str
    graph_generation_id: int
    node_count: int
    edge_count: int
    key_label_counts: dict[str, int]
    checksum: str


@dataclass(frozen=True, slots=True)
class GraphSnapshotAssetResult:
    """Materialized graph snapshot artifact and cold-reload proof."""

    graph_snapshot_id: str
    impact_snapshot_id: str
    artifact_ref: str
    graph_snapshot: GraphSnapshot
    impact_snapshot: GraphImpactSnapshot
    cold_reload_proof: ColdReloadArtifactProof


class GraphPhase1Runtime(Protocol):
    """Runtime adapter invoked by the Dagster assets."""

    def promote_graph(
        self,
        request: GraphPromotionAssetRequest,
    ) -> GraphPromotionAssetResult:
        """Promote Phase 0 frozen candidate deltas into Layer A and Neo4j."""

    def compute_graph_snapshot(
        self,
        request: GraphSnapshotAssetRequest,
    ) -> GraphSnapshotAssetResult:
        """Compute, persist, and prove a formal-readable graph snapshot."""


class GraphPhase1Service:
    """Default runtime backed by graph-engine services.

    This service expects externally injected adapters for candidate reads,
    entity-registry anchor reads, Layer A writes, and regime context reads.
    Graph-engine does not synthesize Phase 0 data: it only consumes the
    frozen candidate selection reference emitted by Phase 0.
    """

    def __init__(
        self,
        *,
        candidate_reader: CandidateDeltaReader,
        entity_reader: EntityAnchorReader,
        canonical_writer: CanonicalWriter,
        client: Neo4jClient,
        status_manager: GraphStatusManager,
        regime_reader: RegimeContextReader,
        snapshot_writer: SnapshotWriter,
        artifact_reader: CanonicalReader | None = None,
        world_state_ref: str = "world-state:latest",
        graph_name: str | None = None,
        enabled_channels: Sequence[str] | None = None,
        max_iterations: int = 20,
        result_limit: int = 100,
    ) -> None:
        self.candidate_reader = candidate_reader
        self.entity_reader = entity_reader
        self.canonical_writer = canonical_writer
        self.client = client
        self.status_manager = status_manager
        self.regime_reader = regime_reader
        self.snapshot_writer = snapshot_writer
        self.artifact_reader = artifact_reader or ArtifactCanonicalReader()
        self.world_state_ref = world_state_ref
        self.graph_name = graph_name
        self.enabled_channels = enabled_channels
        self.max_iterations = max_iterations
        self.result_limit = result_limit

    def promote_graph(
        self,
        request: GraphPromotionAssetRequest,
    ) -> GraphPromotionAssetResult:
        _ensure_phase0_readiness(request.phase0_readiness)
        phase0_status = _ensure_phase0_graph_status_ready(request.graph_status)
        current_status = self.status_manager.require_ready()
        if phase0_status is not None:
            _validate_phase0_status_matches_runtime(current_status, phase0_status)

        plan = promote_graph_deltas(
            request.cycle_id,
            request.selection_ref,
            candidate_reader=self.candidate_reader,
            entity_reader=self.entity_reader,
            canonical_writer=self.canonical_writer,
            client=self.client,
            status_manager=self.status_manager,
        )
        ready_status = self.status_manager.require_ready()
        return GraphPromotionAssetResult(
            cycle_id=request.cycle_id,
            selection_ref=request.selection_ref,
            graph_generation_id=ready_status.graph_generation_id,
            delta_ids=tuple(plan.delta_ids),
            plan=plan,
            graph_status=ready_status,
        )

    def compute_graph_snapshot(
        self,
        request: GraphSnapshotAssetRequest,
    ) -> GraphSnapshotAssetResult:
        # spec v5.0.1 L466 + audit ⚠️ #11: Layer C must read
        # world_state(N-1), not (N). Guard against the orchestrator
        # accidentally passing the current cycle's ref — that would feed
        # propagation its own output. The orchestrator wiring is
        # responsible for resolving the actual previous-cycle ref;
        # here we only ensure the obvious self-reference is rejected.
        _validate_world_state_ref_is_not_current_cycle(
            request.world_state_ref,
            request.cycle_id,
        )
        graph_snapshot, impact_snapshot = compute_graph_snapshots(
            request.cycle_id,
            request.world_state_ref,
            client=self.client,
            graph_generation_id=request.graph_generation_id,
            regime_reader=self.regime_reader,
            snapshot_writer=self.snapshot_writer,
            status_manager=self.status_manager,
            graph_name=self.graph_name,
            enabled_channels=self.enabled_channels,  # type: ignore[arg-type]
            max_iterations=self.max_iterations,
            result_limit=self.result_limit,
        )
        artifact_ref = _artifact_ref_from_snapshot_writer(
            self.snapshot_writer,
            graph_snapshot,
        )
        proof = prove_cold_reload_artifact(
            artifact_ref,
            artifact_reader=self.artifact_reader,
            expected_status=self.status_manager.require_ready(),
        )
        return GraphSnapshotAssetResult(
            graph_snapshot_id=graph_snapshot.graph_snapshot_id,
            impact_snapshot_id=impact_snapshot.impact_snapshot_id,
            artifact_ref=artifact_ref,
            graph_snapshot=graph_snapshot,
            impact_snapshot=impact_snapshot,
            cold_reload_proof=proof,
        )


class GraphPhase1AssetFactoryProvider:
    """Provider object consumed structurally by orchestrator."""

    def __init__(
        self,
        runtime: GraphPhase1Runtime | None = None,
        *,
        resource_key: str = GRAPH_PHASE1_RESOURCE_KEY,
        world_state_ref: str = "world-state:latest",
    ) -> None:
        self.runtime = runtime
        self.resource_key = resource_key
        self.world_state_ref = world_state_ref

    def get_assets(self) -> tuple[object, ...]:
        dagster = _require_dagster()
        resource_key = self.resource_key
        world_state_ref = self.world_state_ref

        @dagster.asset(
            name=PHASE1_GRAPH_PROMOTION_ASSET_KEY,
            group_name=PHASE1_GROUP_NAME,
            required_resource_keys={resource_key},
        )
        def graph_promotion(
            context,
            phase0_readiness_ping: object,
            candidate_freeze: object,
            graph_status: object,
        ) -> GraphPromotionAssetResult:
            cycle_id, selection_ref = _cycle_binding_from_phase0(
                candidate_freeze,
                context=context,
            )
            runtime = _runtime_from_context(context, resource_key)
            return runtime.promote_graph(
                GraphPromotionAssetRequest(
                    cycle_id=cycle_id,
                    selection_ref=selection_ref,
                    phase0_readiness=phase0_readiness_ping,
                    candidate_freeze=candidate_freeze,
                    graph_status=graph_status,
                ),
            )

        @dagster.asset(
            name=PHASE1_GRAPH_SNAPSHOT_ASSET_KEY,
            group_name=PHASE1_GROUP_NAME,
            required_resource_keys={resource_key},
        )
        def graph_snapshot(
            context,
            graph_promotion: GraphPromotionAssetResult,
        ) -> GraphSnapshotAssetResult:
            runtime = _runtime_from_context(context, resource_key)
            return runtime.compute_graph_snapshot(
                GraphSnapshotAssetRequest(
                    cycle_id=graph_promotion.cycle_id,
                    world_state_ref=_world_state_ref_from_promotion(
                        graph_promotion,
                        default=world_state_ref,
                    ),
                    graph_generation_id=graph_promotion.graph_generation_id,
                    promotion=graph_promotion,
                ),
            )

        return (graph_promotion, graph_snapshot)

    def get_checks(self) -> tuple[object, ...]:
        return ()

    def get_resources(self) -> Mapping[str, object]:
        # Check runtime configuration BEFORE the dagster availability check
        # so the error message ("not configured") is the one callers act on
        # rather than the implicit "Dagster is required" prerequisite.
        if self.runtime is None:
            # Phase 0 pattern (M2.3a-2): raise an explicit error rather than
            # silently substituting a fail-closed runtime that only surfaces
            # at asset-evaluation time. The orchestrator's
            # ``_resolve_graph_phase1_provider`` (or any caller) is expected
            # to either pass a runtime explicitly or call
            # ``build_graph_phase1_runtime_from_env`` ahead of time.
            raise RuntimeError(_FAIL_CLOSED_RUNTIME_MESSAGE)
        dagster = _require_dagster()
        return {
            self.resource_key: dagster.ResourceDefinition.hardcoded_resource(self.runtime),
        }


def build_graph_phase1_provider(
    runtime: GraphPhase1Runtime | None = None,
    *,
    resource_key: str = GRAPH_PHASE1_RESOURCE_KEY,
    world_state_ref: str = "world-state:latest",
) -> GraphPhase1AssetFactoryProvider:
    """Return an orchestrator-compatible graph Phase 1 provider.

    If ``runtime`` is omitted, an env-driven runtime is constructed via
    :func:`build_graph_phase1_runtime_from_env`. Callers that want
    fail-closed behaviour on env misconfiguration must catch
    :class:`EnvironmentError` (cf. orchestrator's
    ``_resolve_graph_phase1_provider`` helper) or use
    :func:`build_fail_closed_graph_phase1_provider` to obtain a provider
    whose runtime is the typed fail-closed stub.
    """

    if runtime is None:
        runtime = build_graph_phase1_runtime_from_env(
            world_state_ref=world_state_ref,
        )
    return GraphPhase1AssetFactoryProvider(
        runtime,
        resource_key=resource_key,
        world_state_ref=world_state_ref,
    )


def build_fail_closed_graph_phase1_provider(
    *,
    resource_key: str = GRAPH_PHASE1_RESOURCE_KEY,
    world_state_ref: str = "world-state:latest",
) -> GraphPhase1AssetFactoryProvider:
    """Construct a Phase 1 provider whose runtime fails closed at evaluation.

    Public alternative to ``build_graph_phase1_provider(runtime=
    _FailClosedGraphPhase1Runtime())`` so callers (e.g. orchestrator's
    ``_default_graph_phase1_provider`` fall-back) do not have to import
    the leading-underscore private class across module boundaries.
    """

    return build_graph_phase1_provider(
        runtime=_FailClosedGraphPhase1Runtime(),
        resource_key=resource_key,
        world_state_ref=world_state_ref,
    )


def build_graph_phase1_runtime_from_env(
    *,
    world_state_ref: str = "world-state:latest",
    candidate_reader: CandidateDeltaReader | None = None,
    entity_reader: EntityAnchorReader | None = None,
    canonical_writer: CanonicalWriter | None = None,
    regime_reader: RegimeContextReader | None = None,
    snapshot_writer: SnapshotWriter | None = None,
) -> GraphPhase1Runtime:
    """Construct a real :class:`GraphPhase1Service` from environment variables.

    Composes the graph-engine owned pieces required by the Phase 1 service:

    * :class:`graph_engine.client.Neo4jClient` from ``NEO4J_*`` env (graph-engine).
    * :class:`graph_engine.status.GraphStatusManager` over
      :class:`graph_engine.status.PostgreSQLStatusStore` from ``DATABASE_URL``.
    * :class:`graph_engine.snapshots.FormalArtifactSnapshotWriter` from
      ``GRAPH_PHASE1_SNAPSHOT_ARTIFACT_ROOT`` (snapshot-writer-internal env).

    Cross-module pieces must be supplied by orchestrator / assembly via the
    Protocol arguments: ``candidate_reader``, ``entity_reader``,
    ``canonical_writer``, and ``regime_reader``. Graph-engine never imports
    data-platform or main-core adapter implementations. Raises
    :class:`EnvironmentError` when env-driven construction of any
    graph-engine-owned piece fails or when a required injected Protocol is
    omitted.
    """

    import os
    from pathlib import Path

    from graph_engine.client import Neo4jClient
    from graph_engine.config import load_config_from_env
    from graph_engine.snapshots import FormalArtifactSnapshotWriter
    from graph_engine.status import GraphStatusManager, PostgreSQLStatusStore

    # --- graph-engine internals (NEO4J_* + DATABASE_URL) -------------------

    try:
        neo4j_config = load_config_from_env()
    except (ValueError, RuntimeError) as exc:
        raise EnvironmentError(
            "Phase 1 runtime requires NEO4J_URI/USER/PASSWORD/DATABASE for "
            "the live-graph client",
        ) from exc

    try:
        store = PostgreSQLStatusStore.from_database_url()
    except (RuntimeError, ValueError) as exc:
        raise EnvironmentError(
            "Phase 1 runtime requires DATABASE_URL pointing at the "
            "PostgreSQL instance hosting neo4j_graph_status",
        ) from exc

    client = Neo4jClient(neo4j_config)
    status_manager = GraphStatusManager(store)

    # --- snapshot writer (graph-engine, FormalArtifactSnapshotWriter) -------

    if snapshot_writer is None:
        artifact_root = os.environ.get("GRAPH_PHASE1_SNAPSHOT_ARTIFACT_ROOT")
        if not artifact_root:
            raise EnvironmentError(
                "Phase 1 runtime requires GRAPH_PHASE1_SNAPSHOT_ARTIFACT_ROOT "
                "for the formal artifact snapshot writer",
            )
        snapshot_writer = FormalArtifactSnapshotWriter(Path(artifact_root))

    # --- injected cross-module adapters ------------------------------------

    missing_dependencies = [
        name
        for name, value in (
            ("candidate_reader", candidate_reader),
            ("entity_reader", entity_reader),
            ("canonical_writer", canonical_writer),
            ("regime_reader", regime_reader),
        )
        if value is None
    ]
    if missing_dependencies:
        raise EnvironmentError(
            "Phase 1 runtime requires injected Protocol adapters for "
            + ", ".join(missing_dependencies)
            + "; graph-engine does not import data-platform or main-core "
            "adapter implementations",
        )

    # --- compose the real service ------------------------------------------

    return GraphPhase1Service(
        candidate_reader=candidate_reader,
        entity_reader=entity_reader,
        canonical_writer=canonical_writer,
        client=client,
        status_manager=status_manager,
        regime_reader=regime_reader,
        snapshot_writer=snapshot_writer,
    )


def prove_cold_reload_artifact(
    snapshot_ref: str,
    *,
    artifact_reader: CanonicalReader,
    expected_status: Neo4jGraphStatus,
) -> ColdReloadArtifactProof:
    """Fail closed unless a persisted artifact can reproduce live metrics."""

    ready_status = require_ready_status(expected_status)
    plan = artifact_reader.read_cold_reload_plan(snapshot_ref)
    snapshot = plan.expected_snapshot
    mismatches: list[str] = []
    for field_name, snapshot_value, status_value in (
        ("graph_generation_id", snapshot.graph_generation_id, ready_status.graph_generation_id),
        ("node_count", snapshot.node_count, ready_status.node_count),
        ("edge_count", snapshot.edge_count, ready_status.edge_count),
        ("key_label_counts", snapshot.key_label_counts, ready_status.key_label_counts),
        ("checksum", snapshot.checksum, ready_status.checksum),
    ):
        if snapshot_value != status_value:
            mismatches.append(
                f"{field_name} artifact={snapshot_value!r} status={status_value!r}",
            )
    if mismatches:
        raise ValueError(
            "cold reload artifact metrics disagree with Neo4jGraphStatus: "
            + "; ".join(mismatches),
        )

    return ColdReloadArtifactProof(
        snapshot_ref=snapshot_ref,
        cycle_id=plan.cycle_id,
        snapshot_id=snapshot.snapshot_id,
        graph_generation_id=snapshot.graph_generation_id,
        node_count=snapshot.node_count,
        edge_count=snapshot.edge_count,
        key_label_counts=dict(snapshot.key_label_counts),
        checksum=snapshot.checksum,
    )


class _FailClosedGraphPhase1Runtime:
    def promote_graph(
        self,
        request: GraphPromotionAssetRequest,
    ) -> GraphPromotionAssetResult:
        raise RuntimeError(_FAIL_CLOSED_RUNTIME_MESSAGE)

    def compute_graph_snapshot(
        self,
        request: GraphSnapshotAssetRequest,
    ) -> GraphSnapshotAssetResult:
        raise RuntimeError(_FAIL_CLOSED_RUNTIME_MESSAGE)


_FAIL_CLOSED_RUNTIME_MESSAGE = (
    "Graph Phase 1 runtime dependencies are not configured; provide real "
    "candidate_reader, entity_reader, canonical_writer, Neo4j client/status, "
    "regime_reader, and formal artifact snapshot writer resources."
)


def _ensure_phase0_readiness(value: object) -> None:
    ready = _value_by_name(value, ("ready", "passed", "ok"))
    if ready is not None and not bool(ready):
        raise PermissionError("Phase 1 graph promotion requires Phase 0 readiness")
    status = _value_by_name(value, ("status", "graph_status"))
    if isinstance(status, str) and status.lower() in {"failed", "blocked", "rebuilding"}:
        raise PermissionError(
            f"Phase 1 graph promotion requires ready Phase 0 status; got {status!r}",
        )
    if isinstance(value, str) and value.strip().lower() in {"failed", "blocked"}:
        raise PermissionError(
            f"Phase 1 graph promotion requires ready Phase 0 status; got {value!r}",
        )


def _ensure_phase0_graph_status_ready(value: object) -> Neo4jGraphStatus | None:
    if isinstance(value, Neo4jGraphStatus):
        return require_ready_status(value)

    if isinstance(value, Mapping) or _has_any_attr(value, ("graph_status", "status")):
        status_value = _value_by_name(value, ("graph_status", "status"))
        if status_value != "ready":
            raise PermissionError(
                "Phase 1 graph promotion requires graph_status='ready'; "
                f"got {status_value!r}",
            )
        writer_lock_token = _value_by_name(value, ("writer_lock_token",))
        if writer_lock_token is not None:
            raise PermissionError("Phase 1 graph promotion requires no graph writer lock")
        try:
            return Neo4jGraphStatus.model_validate(value)
        except Exception:
            return None

    if isinstance(value, str):
        normalized = value.lower()
        if "rebuilding" in normalized or "failed" in normalized or "blocked" in normalized:
            raise PermissionError(
                "Phase 1 graph promotion requires graph_status='ready'; "
                f"got {value!r}",
            )
        if "ready" in normalized:
            return None

    raise ValueError(
        "graph_status Phase 0 dependency must expose a ready Neo4j graph status",
    )


def _validate_phase0_status_matches_runtime(
    current_status: Neo4jGraphStatus,
    phase0_status: Neo4jGraphStatus,
) -> None:
    mismatches = [
        field_name
        for field_name in (
            "graph_generation_id",
            "node_count",
            "edge_count",
            "key_label_counts",
            "checksum",
        )
        if getattr(current_status, field_name) != getattr(phase0_status, field_name)
    ]
    if mismatches:
        raise ValueError(
            "Phase 0 graph_status disagrees with runtime Neo4jGraphStatus: "
            + ", ".join(mismatches),
        )


def _cycle_binding_from_phase0(
    candidate_freeze: object,
    *,
    context: object,
) -> tuple[str, str]:
    cycle_id = _value_by_name(candidate_freeze, ("cycle_id",))
    if cycle_id is None or not str(cycle_id):
        raise ValueError(
            "candidate_freeze Phase 0 dependency must expose cycle_id",
        )

    selection_ref = _value_by_name(
        candidate_freeze,
        ("selection_ref", "candidate_selection_ref", "snapshot_ref"),
    )
    if selection_ref is None or not str(selection_ref):
        raise ValueError(
            "candidate_freeze Phase 0 dependency must expose frozen selection_ref",
        )
    return str(cycle_id), str(selection_ref)


def _world_state_ref_from_promotion(
    graph_promotion: GraphPromotionAssetResult,
    *,
    default: str,
) -> str:
    value = _value_by_name(graph_promotion, ("world_state_ref",))
    if value is None or not str(value):
        return default
    return str(value)


def _validate_world_state_ref_is_not_current_cycle(
    world_state_ref: str,
    current_cycle_id: str,
) -> None:
    """Reject world_state_ref values that point at the current cycle.

    spec L466: Layer C must read world_state(N-1), not (N). The
    canonical refs we recognise are:

      - ``world-state:latest`` — caller is letting Layer C resolve the
        latest published world state (orchestrator must ensure this is
        not the current in-flight cycle's, but it is intentionally
        opaque here);
      - ``world-state:{cycle_id}`` — caller has resolved a specific
        cycle's world_state to read.

    Refs of the second form are checked literally against the current
    cycle_id; matches raise ValueError so the orchestrator's Phase 1
    wiring fails loudly instead of silently feeding propagation its own
    output. Other shapes are accepted (defensive — we don't pretend to
    own the ref grammar; that's a contracts concern).
    """

    if not world_state_ref or not current_cycle_id:
        return
    if world_state_ref == f"world-state:{current_cycle_id}":
        raise ValueError(
            f"Layer C must read world_state(N-1) (spec L466); got "
            f"world_state_ref={world_state_ref!r} which points at the "
            f"current cycle {current_cycle_id!r}. The orchestrator's "
            "Phase 1 wiring must resolve the previous cycle's "
            "world_state ref before invoking compute_graph_snapshot."
        )


def _artifact_ref_from_snapshot_writer(
    snapshot_writer: SnapshotWriter,
    graph_snapshot: GraphSnapshot,
) -> str:
    ref_for_snapshot = getattr(snapshot_writer, "artifact_ref_for_graph_snapshot", None)
    if callable(ref_for_snapshot):
        ref = ref_for_snapshot(graph_snapshot)
        if ref:
            return str(ref)

    last_ref = getattr(snapshot_writer, "last_artifact_ref", None)
    if last_ref:
        return str(last_ref)

    raise RuntimeError(
        "snapshot_writer must expose persisted graph_snapshot artifact_ref "
        "for cold reload proof",
    )


def _runtime_from_context(context: object, resource_key: str) -> GraphPhase1Runtime:
    resources = getattr(context, "resources")
    runtime = getattr(resources, resource_key)
    return runtime


def _context_tag(context: object, key: str) -> object | None:
    run_tags = getattr(context, "run_tags", None)
    if isinstance(run_tags, Mapping) and key in run_tags:
        return run_tags[key]
    run = getattr(context, "run", None)
    tags = getattr(run, "tags", None)
    if isinstance(tags, Mapping):
        return tags.get(key)
    return None


def _value_by_name(value: object, names: Sequence[str]) -> object | None:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _has_any_attr(value: object, names: Sequence[str]) -> bool:
    return any(hasattr(value, name) for name in names)


def _require_dagster() -> Any:
    try:
        return import_module("dagster")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Dagster is required to build graph-engine Phase 1 provider assets",
        ) from exc


__all__ = [
    "GRAPH_PHASE1_RESOURCE_KEY",
    "PHASE0_CANDIDATE_FREEZE_ASSET_KEY",
    "PHASE0_GRAPH_STATUS_ASSET_KEY",
    "PHASE0_READINESS_ASSET_KEY",
    "PHASE1_GRAPH_PROMOTION_ASSET_KEY",
    "PHASE1_GRAPH_SNAPSHOT_ASSET_KEY",
    "PHASE1_GROUP_NAME",
    "ColdReloadArtifactProof",
    "GraphPhase1AssetFactoryProvider",
    "GraphPhase1Runtime",
    "GraphPhase1Service",
    "GraphPromotionAssetRequest",
    "GraphPromotionAssetResult",
    "GraphSnapshotAssetRequest",
    "GraphSnapshotAssetResult",
    "build_fail_closed_graph_phase1_provider",
    "build_graph_phase1_provider",
    "build_graph_phase1_runtime_from_env",
    "prove_cold_reload_artifact",
]
