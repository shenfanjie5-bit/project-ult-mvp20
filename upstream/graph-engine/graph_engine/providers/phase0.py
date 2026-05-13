"""Dagster Phase 0 asset factory for the live-graph status snapshot.

Phase 0 publishes the current ``Neo4jGraphStatus`` to the orchestrator so the
daily cycle can gate Phase 1 promotion on a readable, ready live graph. The
``GraphStatusProvider`` Protocol on the orchestrator side
(`orchestrator_adapters.production_daily_cycle.GraphStatusProvider`) calls
``get_graph_status(*, candidate_freeze, cycle_id)`` and expects a value whose
``graph_status`` field equals ``"ready"`` and whose ``writer_lock_token`` is
``None`` (cf. orchestrator's ``_graph_status_ready`` consistency check, which
duck-types both ``Mapping`` and attribute-bearing objects).

This module exposes:

* ``GraphPhase0StatusRuntime`` — Protocol matching the orchestrator boundary.
* ``Neo4jGraphStatusProvider`` — real adapter wrapping ``GraphStatusManager``.
* ``_FailClosedGraphPhase0StatusRuntime`` — explicit fail-closed used by
  callers that want a typed runtime when env vars are absent.
* ``build_graph_phase0_status_runtime_from_env`` — env-driven factory.
* ``build_graph_phase0_status_provider`` — public factory; raises
  ``EnvironmentError`` when env-driven construction is impossible.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from pydantic import ValidationError

from graph_engine.client import Neo4jClient
from graph_engine.config import load_config_from_env
from graph_engine.status import GraphStatusManager, PostgreSQLStatusStore, StatusStore


class GraphPhase0StatusRuntime(Protocol):
    """Runtime boundary for the orchestrator's Phase 0 graph status asset."""

    def get_graph_status(
        self,
        *,
        candidate_freeze: object,
        cycle_id: str,
    ) -> object:
        """Return a ready graph status object/Mapping or raise fail-closed."""


class Neo4jGraphStatusProvider:
    """Real adapter that exposes the current Neo4j graph status row.

    The provider wraps :class:`graph_engine.status.GraphStatusManager` and
    returns a serialisable ``Mapping`` so the orchestrator can persist the
    Phase 0 asset materialisation without coupling to graph-engine's Pydantic
    models.

    The optional ``client`` is reserved for future Phase 0 enhancements (live
    consistency probes); the current implementation only reads the persisted
    status row.
    """

    def __init__(
        self,
        *,
        status_manager: GraphStatusManager,
        client: Neo4jClient | None = None,
    ) -> None:
        self._status_manager = status_manager
        self._client = client

    @property
    def status_manager(self) -> GraphStatusManager:
        return self._status_manager

    @property
    def client(self) -> Neo4jClient | None:
        return self._client

    def get_graph_status(
        self,
        *,
        candidate_freeze: object,
        cycle_id: str,
    ) -> Mapping[str, object]:
        """Return the current Neo4j graph status as a JSON-friendly dict.

        ``candidate_freeze`` is accepted for Protocol compatibility but is
        not consulted: Phase 0 only publishes the global graph status, which
        is independent of the per-cycle candidate set.

        The returned dict echoes ``cycle_id`` so the asset materialisation
        carries cycle traceability, mirroring how the orchestrator's
        ``candidate_freeze`` asset emits its own ``cycle_id``.
        """

        del candidate_freeze  # signal the orchestrator-side parameter is
        # accepted for Protocol compatibility but not consulted; live status
        # is global, not per-cycle.

        status = self._status_manager.get_status()
        return {
            "graph_status": status.graph_status,
            "graph_generation_id": status.graph_generation_id,
            "node_count": status.node_count,
            "edge_count": status.edge_count,
            "key_label_counts": dict(status.key_label_counts),
            "checksum": status.checksum,
            "writer_lock_token": status.writer_lock_token,
            "last_verified_at": (
                status.last_verified_at.isoformat()
                if status.last_verified_at is not None
                else None
            ),
            "last_reload_at": (
                status.last_reload_at.isoformat()
                if status.last_reload_at is not None
                else None
            ),
            "cycle_id": cycle_id,
        }


class _FailClosedGraphPhase0StatusRuntime:
    """Explicit fail-closed runtime; raises on every status request.

    Callers wire this in environments without Neo4j or DATABASE_URL set, so
    the daily cycle fails closed at Phase 0 rather than silently degrading.
    """

    def get_graph_status(
        self,
        *,
        candidate_freeze: object,
        cycle_id: str,
    ) -> object:
        raise RuntimeError(
            "Graph Phase 0 status runtime is not configured; provide a "
            "Neo4j-backed runtime via build_graph_phase0_status_provider() "
            "with NEO4J_URI/USER/PASSWORD/DATABASE and DATABASE_URL set, or "
            "pass an explicit runtime to the orchestrator's "
            "ProductionPhase0Provider.",
        )


def build_graph_phase0_status_runtime_from_env(
    *,
    status_store: StatusStore | None = None,
    neo4j_client: Neo4jClient | None = None,
) -> Neo4jGraphStatusProvider:
    """Construct a Neo4j-backed status runtime from environment variables.

    Reads ``NEO4J_URI`` / ``NEO4J_USER`` / ``NEO4J_PASSWORD`` /
    ``NEO4J_DATABASE`` for the optional Neo4j client, and ``DATABASE_URL``
    for the PostgreSQL-backed status store. ``status_store`` and
    ``neo4j_client`` overrides exist primarily for tests.

    Raises:
        EnvironmentError: when required env vars are missing or the Neo4j
            config fails validation.
    """

    if status_store is None:
        try:
            status_store = PostgreSQLStatusStore.from_database_url()
        except (RuntimeError, ValueError) as exc:
            # ValueError covers DATABASE_URL absent / malformed connection
            # string; RuntimeError covers psycopg import failure inside
            # ``_build_psycopg_connection_factory``.
            raise EnvironmentError(
                "Phase 0 graph status requires DATABASE_URL pointing at the "
                "PostgreSQL instance hosting neo4j_graph_status",
            ) from exc

    if neo4j_client is None:
        try:
            neo4j_client = Neo4jClient(load_config_from_env())
        except (ValidationError, RuntimeError, ValueError) as exc:
            raise EnvironmentError(
                "Phase 0 graph status requires NEO4J_URI/USER/PASSWORD/"
                "DATABASE for the live-graph client",
            ) from exc

    return Neo4jGraphStatusProvider(
        status_manager=GraphStatusManager(status_store),
        client=neo4j_client,
    )


def build_graph_phase0_status_provider(
    runtime: GraphPhase0StatusRuntime | None = None,
) -> GraphPhase0StatusRuntime:
    """Public Phase 0 status provider factory.

    If ``runtime`` is explicit, it is returned unchanged. Otherwise the
    factory constructs a real :class:`Neo4jGraphStatusProvider` from
    environment variables. Callers that want fail-closed semantics on env
    misconfiguration should catch :class:`EnvironmentError` and wire
    ``_FailClosedGraphPhase0StatusRuntime`` explicitly.
    """

    if runtime is not None:
        return runtime
    return build_graph_phase0_status_runtime_from_env()


__all__ = [
    "GraphPhase0StatusRuntime",
    "Neo4jGraphStatusProvider",
    "build_graph_phase0_status_provider",
    "build_graph_phase0_status_runtime_from_env",
]
# ``_FailClosedGraphPhase0StatusRuntime`` is intentionally excluded from
# ``__all__`` — the orchestrator owns its own ``_FailClosedGraphStatusProvider``
# and consumers outside this package should not import the graph-engine
# variant. The class remains importable via its fully-qualified path for
# unit tests that need to instantiate the typed fail-closed runtime.
