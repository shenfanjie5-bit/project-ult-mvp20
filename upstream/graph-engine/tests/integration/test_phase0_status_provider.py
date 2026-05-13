"""Live integration tests for graph_engine.providers.phase0.

Verifies that ``build_graph_phase0_status_runtime_from_env`` constructs a
real ``Neo4jGraphStatusProvider`` against the lite-local compose stack
(PostgreSQL on ``DATABASE_URL`` + Neo4j on ``NEO4J_*``) and that the
provider's ``get_graph_status`` returns a Mapping that satisfies the
orchestrator's Phase 0 readiness check.

These tests skip when either ``DATABASE_URL`` or ``NEO4J_PASSWORD`` is
absent so the suite stays runnable on developer machines without compose
services up.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from graph_engine.client import Neo4jClient
from graph_engine.models import Neo4jGraphStatus
from graph_engine.providers.phase0 import (
    Neo4jGraphStatusProvider,
    build_graph_phase0_status_runtime_from_env,
)
from graph_engine.status.store import PostgreSQLStatusStore

pytestmark = pytest.mark.skipif(
    os.getenv("DATABASE_URL") is None or os.getenv("NEO4J_PASSWORD") is None,
    reason=(
        "Phase 0 status provider integration tests require both "
        "DATABASE_URL and NEO4J_PASSWORD."
    ),
)

NOW = datetime(2026, 4, 29, 12, 30, 45, tzinfo=timezone.utc)


def _ready_status(*, generation_id: int = 11) -> Neo4jGraphStatus:
    return Neo4jGraphStatus(
        graph_status="ready",
        graph_generation_id=generation_id,
        node_count=4,
        edge_count=3,
        key_label_counts={"Entity": 2, "Sector": 2},
        checksum=f"ready-{generation_id}",
        last_verified_at=NOW,
        last_reload_at=NOW,
    )


def _database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    assert database_url is not None
    return database_url


def _table_name() -> str:
    return f"neo4j_graph_status_phase0_test_{uuid4().hex}"


def _drop_table(database_url: str, table_name: str) -> None:
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')


def test_phase0_provider_reads_ready_status_from_live_pg() -> None:
    """Real PostgreSQL store + live env construction = ready dict round-trip."""

    pytest.importorskip("psycopg")

    database_url = _database_url()
    table_name = _table_name()

    store = PostgreSQLStatusStore(database_url, table_name=table_name)
    try:
        store.write_current_status(_ready_status(generation_id=11))

        provider = build_graph_phase0_status_runtime_from_env(status_store=store)

        result = provider.get_graph_status(
            candidate_freeze={"cycle_id": "CYCLE_20260429"},
            cycle_id="CYCLE_20260429",
        )

        assert isinstance(provider, Neo4jGraphStatusProvider)
        assert result["graph_status"] == "ready"
        assert result["graph_generation_id"] == 11
        assert result["writer_lock_token"] is None
        # Mirror orchestrator's _graph_status_ready check:
        assert result.get("graph_status") == "ready"
        assert result.get("writer_lock_token") is None
        assert result["cycle_id"] == "CYCLE_20260429"
    finally:
        _drop_table(database_url, table_name)


def test_phase0_provider_constructs_neo4j_client_from_env() -> None:
    """When env vars are set, factory builds a real Neo4jClient."""

    pytest.importorskip("psycopg")
    pytest.importorskip("neo4j")

    database_url = _database_url()
    table_name = _table_name()
    store = PostgreSQLStatusStore(database_url, table_name=table_name)

    try:
        store.write_current_status(_ready_status(generation_id=12))

        provider = build_graph_phase0_status_runtime_from_env(status_store=store)

        assert isinstance(provider, Neo4jGraphStatusProvider)
        assert isinstance(provider.client, Neo4jClient)
        # We do not call verify_connectivity here — the provider's contract is
        # to read persisted status, not probe live graph. Phase 1 owns the
        # liveness probe via build_graph_snapshot.
    finally:
        _drop_table(database_url, table_name)


def test_phase0_provider_surfaces_rebuilding_status_from_live_pg() -> None:
    """Non-ready status surfaces verbatim through the dict shape."""

    pytest.importorskip("psycopg")

    database_url = _database_url()
    table_name = _table_name()

    store = PostgreSQLStatusStore(database_url, table_name=table_name)
    try:
        store.write_current_status(
            Neo4jGraphStatus(
                graph_status="rebuilding",
                graph_generation_id=4,
                node_count=0,
                edge_count=0,
                key_label_counts={},
                checksum="rebuilding",
                last_verified_at=None,
                last_reload_at=NOW,
            ),
        )

        provider = build_graph_phase0_status_runtime_from_env(status_store=store)
        result = provider.get_graph_status(candidate_freeze=None, cycle_id="any")

        assert result["graph_status"] == "rebuilding"
        # Orchestrator's readiness check should see this as NOT ready.
        ready = (
            result.get("graph_status") == "ready"
            and result.get("writer_lock_token") is None
        )
        assert ready is False
    finally:
        _drop_table(database_url, table_name)


def test_phase0_provider_constructs_store_and_client_from_env_only() -> None:
    """End-to-end env-driven path: no overrides at all.

    The other integration tests pass ``status_store=`` and ``neo4j_client=``
    overrides to test the dict shape against a uuid-isolated table. This
    test instead exercises the full ``DATABASE_URL`` →
    ``PostgreSQLStatusStore.from_database_url()`` →
    ``GraphStatusManager`` → ``Neo4jGraphStatusProvider`` chain plus the
    parallel ``NEO4J_*`` → ``Neo4jClient`` chain, so we verify the env
    mapping itself, not just the wiring around it. We do not write or read
    a status row here (the default table may be shared); type assertions
    are sufficient to prove the env path works.
    """

    pytest.importorskip("psycopg")
    pytest.importorskip("neo4j")

    # Both env vars must already be set by the suite harness; if either is
    # missing, the module-level skipif marker would have skipped this test.

    provider = build_graph_phase0_status_runtime_from_env()

    assert isinstance(provider, Neo4jGraphStatusProvider)
    # The provider's status_manager must wrap a real PostgreSQLStatusStore
    # constructed from DATABASE_URL (not InMemory or anything else).
    assert isinstance(provider.status_manager.store, PostgreSQLStatusStore)
    # The Neo4j client must be a real Neo4jClient (lazy-connect; no network call).
    assert provider.client is not None
    assert provider.client.__class__.__name__ == "Neo4jClient"
