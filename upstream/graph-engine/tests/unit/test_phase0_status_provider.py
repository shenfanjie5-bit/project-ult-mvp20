"""Unit tests for graph_engine.providers.phase0 (Phase 0 status provider)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from graph_engine.models import Neo4jGraphStatus
from graph_engine.providers.phase0 import (
    Neo4jGraphStatusProvider,
    _FailClosedGraphPhase0StatusRuntime,
    build_graph_phase0_status_provider,
    build_graph_phase0_status_runtime_from_env,
)
from graph_engine.status import GraphStatusManager
from tests.fakes import InMemoryStatusStore


NOW = datetime(2026, 4, 29, 12, 30, 45, tzinfo=timezone.utc)


def _ready_status(*, generation_id: int = 7) -> Neo4jGraphStatus:
    return Neo4jGraphStatus(
        graph_status="ready",
        graph_generation_id=generation_id,
        node_count=4,
        edge_count=3,
        key_label_counts={"Entity": 2, "Sector": 2},
        checksum="ready-checksum",
        last_verified_at=NOW,
        last_reload_at=NOW,
    )


def _rebuilding_status() -> Neo4jGraphStatus:
    return Neo4jGraphStatus(
        graph_status="rebuilding",
        graph_generation_id=2,
        node_count=0,
        edge_count=0,
        key_label_counts={},
        checksum="rebuilding",
        last_verified_at=None,
        last_reload_at=NOW,
    )


EXPECTED_DICT_KEYS = frozenset(
    {
        "graph_status",
        "graph_generation_id",
        "node_count",
        "edge_count",
        "key_label_counts",
        "checksum",
        "writer_lock_token",
        "last_verified_at",
        "last_reload_at",
        "cycle_id",
    },
)


def test_neo4j_graph_status_provider_returns_ready_dict() -> None:
    store = InMemoryStatusStore(_ready_status())
    provider = Neo4jGraphStatusProvider(
        status_manager=GraphStatusManager(store, clock=lambda: NOW),
    )

    result = provider.get_graph_status(
        candidate_freeze={"cycle_id": "CYCLE_20260429"},
        cycle_id="CYCLE_20260429",
    )

    # Pin the dict shape so future refactors can't silently leak extra fields
    # into the orchestrator-facing payload.
    assert frozenset(result.keys()) == EXPECTED_DICT_KEYS

    assert result["graph_status"] == "ready"
    assert result["graph_generation_id"] == 7
    assert result["node_count"] == 4
    assert result["edge_count"] == 3
    assert result["key_label_counts"] == {"Entity": 2, "Sector": 2}
    assert result["checksum"] == "ready-checksum"
    assert result["writer_lock_token"] is None
    assert result["last_verified_at"] == NOW.isoformat()
    assert result["last_reload_at"] == NOW.isoformat()
    assert result["cycle_id"] == "CYCLE_20260429"


def test_neo4j_graph_status_provider_passes_orchestrator_ready_check() -> None:
    """The returned dict must satisfy orchestrator's _graph_status_ready check.

    See orchestrator/src/orchestrator_adapters/production_daily_cycle.py:719-724:
        def _graph_status_ready(value: object) -> bool:
            if isinstance(value, Mapping):
                return (
                    value.get("graph_status") == "ready"
                    and value.get("writer_lock_token") is None
                )
            ...
    """

    store = InMemoryStatusStore(_ready_status())
    provider = Neo4jGraphStatusProvider(
        status_manager=GraphStatusManager(store, clock=lambda: NOW),
    )

    result = provider.get_graph_status(
        candidate_freeze=None, cycle_id="CYCLE_20260429"
    )

    # Mirror the orchestrator's check inline so this test breaks loudly if the
    # provider's dict shape ever drifts away from the consumer contract.
    assert result.get("graph_status") == "ready"
    assert result.get("writer_lock_token") is None


def test_neo4j_graph_status_provider_surfaces_rebuilding_state() -> None:
    store = InMemoryStatusStore(_rebuilding_status())
    provider = Neo4jGraphStatusProvider(
        status_manager=GraphStatusManager(store),
    )

    result = provider.get_graph_status(
        candidate_freeze=None, cycle_id="CYCLE_20260429"
    )

    assert result["graph_status"] == "rebuilding"
    assert result["last_verified_at"] is None
    assert result["last_reload_at"] == NOW.isoformat()


def test_neo4j_graph_status_provider_surfaces_failed_state() -> None:
    """Non-ready 'failed' status must surface verbatim through the dict."""

    failed = Neo4jGraphStatus(
        graph_status="failed",
        graph_generation_id=5,
        node_count=0,
        edge_count=0,
        key_label_counts={},
        checksum="failed",
        last_verified_at=None,
        last_reload_at=NOW,
    )
    store = InMemoryStatusStore(failed)
    provider = Neo4jGraphStatusProvider(
        status_manager=GraphStatusManager(store),
    )

    result = provider.get_graph_status(candidate_freeze=None, cycle_id="CYCLE_X")

    # Pin shape — failed states must use the same dict envelope as ready/rebuilding.
    assert frozenset(result.keys()) == EXPECTED_DICT_KEYS
    assert result["graph_status"] == "failed"
    assert result["last_verified_at"] is None
    assert result["last_reload_at"] == NOW.isoformat()
    # Mirror orchestrator's readiness check: failed must NOT be ready.
    is_ready = (
        result.get("graph_status") == "ready"
        and result.get("writer_lock_token") is None
    )
    assert is_ready is False


def test_neo4j_graph_status_provider_returns_ready_with_writer_lock() -> None:
    """A ready status carrying a writer_lock_token must propagate the token
    so orchestrator's _graph_status_ready returns False (lock active)."""

    ready_locked = Neo4jGraphStatus(
        graph_status="ready",
        graph_generation_id=9,
        node_count=4,
        edge_count=3,
        key_label_counts={"Entity": 2, "Sector": 2},
        checksum="ready-locked-checksum",
        last_verified_at=NOW,
        last_reload_at=NOW,
        writer_lock_token="incremental-sync",
    )
    store = InMemoryStatusStore(ready_locked)
    provider = Neo4jGraphStatusProvider(
        status_manager=GraphStatusManager(store),
    )

    result = provider.get_graph_status(candidate_freeze=None, cycle_id="CYCLE_X")

    assert result["graph_status"] == "ready"
    assert result["writer_lock_token"] == "incremental-sync"
    is_ready = (
        result.get("graph_status") == "ready"
        and result.get("writer_lock_token") is None
    )
    assert is_ready is False


def test_neo4j_graph_status_provider_handles_empty_key_label_counts() -> None:
    """Empty key_label_counts (e.g. just-bootstrapped) must round-trip cleanly."""

    bootstrap = Neo4jGraphStatus(
        graph_status="rebuilding",
        graph_generation_id=0,
        node_count=0,
        edge_count=0,
        key_label_counts={},
        checksum="rebuilding",
        last_verified_at=None,
        last_reload_at=None,
    )
    store = InMemoryStatusStore(bootstrap)
    provider = Neo4jGraphStatusProvider(
        status_manager=GraphStatusManager(store),
    )

    result = provider.get_graph_status(candidate_freeze=None, cycle_id="CYCLE_X")

    assert result["key_label_counts"] == {}
    assert result["last_verified_at"] is None
    assert result["last_reload_at"] is None


def test_neo4j_graph_status_provider_propagates_lookup_error_when_uninitialised() -> None:
    store = InMemoryStatusStore()  # no status row
    provider = Neo4jGraphStatusProvider(
        status_manager=GraphStatusManager(store),
    )

    with pytest.raises(LookupError, match="not been initialized"):
        provider.get_graph_status(candidate_freeze=None, cycle_id="any")


def test_fail_closed_runtime_always_raises() -> None:
    runtime = _FailClosedGraphPhase0StatusRuntime()

    with pytest.raises(RuntimeError, match="not configured"):
        runtime.get_graph_status(candidate_freeze=None, cycle_id="CYCLE_20260429")


def test_build_from_env_raises_environment_error_when_neo4j_password_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/proj")

    with pytest.raises(EnvironmentError, match="NEO4J_URI/USER/PASSWORD"):
        # status_store override skips the DATABASE_URL lookup so the failure
        # is purely about the Neo4j config.
        build_graph_phase0_status_runtime_from_env(
            status_store=InMemoryStatusStore(_ready_status()),
        )


def test_build_from_env_raises_environment_error_when_database_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(EnvironmentError, match="DATABASE_URL"):
        build_graph_phase0_status_runtime_from_env()


def test_build_from_env_wraps_store_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A RuntimeError from PostgreSQLStatusStore (e.g. psycopg unavailable)
    must be wrapped as EnvironmentError so the orchestrator's resolver can
    fall back to fail-closed via a single ``except EnvironmentError``."""

    monkeypatch.setenv("DATABASE_URL", "postgresql://example/proj")

    def _raise_runtime_error(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("psycopg is not importable in this venv")

    monkeypatch.setattr(
        "graph_engine.providers.phase0.PostgreSQLStatusStore.from_database_url",
        _raise_runtime_error,
    )

    with pytest.raises(EnvironmentError, match="DATABASE_URL"):
        build_graph_phase0_status_runtime_from_env(
            neo4j_client=object(),  # bypass Neo4j env so the failure is store-only
        )


def test_build_from_env_neo4j_client_override_still_requires_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asymmetric override: passing only ``neo4j_client`` must still raise
    when ``DATABASE_URL`` is absent (the store factory cannot bypass env)."""

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    class _SentinelClient:
        pass

    with pytest.raises(EnvironmentError, match="DATABASE_URL"):
        build_graph_phase0_status_runtime_from_env(
            neo4j_client=_SentinelClient(),  # type: ignore[arg-type]
        )


def test_build_from_env_accepts_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both store and client overrides should bypass env lookup entirely."""

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    store = InMemoryStatusStore(_ready_status())

    class _SentinelClient:
        pass

    runtime = build_graph_phase0_status_runtime_from_env(
        status_store=store,
        neo4j_client=_SentinelClient(),  # type: ignore[arg-type]
    )

    assert isinstance(runtime, Neo4jGraphStatusProvider)
    assert isinstance(runtime.client, _SentinelClient)
    result = runtime.get_graph_status(candidate_freeze=None, cycle_id="CYCLE_20260429")
    assert result["graph_status"] == "ready"


def test_public_factory_returns_explicit_runtime_unchanged() -> None:
    runtime = _FailClosedGraphPhase0StatusRuntime()
    assert build_graph_phase0_status_provider(runtime=runtime) is runtime


def test_public_factory_falls_through_to_env_when_runtime_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(EnvironmentError):
        build_graph_phase0_status_provider()
