"""Unit tests for ``build_graph_phase1_runtime_from_env``.

The factory composes graph-engine-owned env dependencies plus injected
Protocol adapters for cross-module reads/writes. These tests exercise that
override pattern and the EnvironmentError fail-paths.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from graph_engine.client import Neo4jClient
from graph_engine.providers import (
    GraphPhase1Service,
    build_graph_phase1_runtime_from_env,
)
from graph_engine.snapshots import FormalArtifactSnapshotWriter
from graph_engine.status import GraphStatusManager


NOW = datetime(2026, 4, 29, 12, 30, 45, tzinfo=timezone.utc)


def _live_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "changeme123")
    monkeypatch.setenv("NEO4J_DATABASE", "neo4j")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres:changeme@localhost:5432/proj",
    )
    monkeypatch.setenv(
        "GRAPH_PHASE1_SNAPSHOT_ARTIFACT_ROOT", str(tmp_path / "phase1_artifacts")
    )


class _StaticCandidateReader:
    def read_candidate_graph_deltas(self, cycle_id: str, selection_ref: str) -> list[Any]:
        return []


class _StaticEntityReader:
    def canonical_entity_ids_for_node_ids(self, node_ids: set[str]) -> dict[str, str]:
        return {}

    def existing_entity_ids(self, entity_ids: set[str]) -> set[str]:
        return set()


class _CapturingCanonicalWriter:
    def __init__(self) -> None:
        self.plans: list[Any] = []

    def write_canonical_records(self, plan: Any) -> None:
        self.plans.append(plan)


class _StaticRegimeReader:
    def read_regime_context(self, world_state_ref: str) -> dict[str, Any]:
        return {
            "world_state_ref": world_state_ref,
            "channel_multipliers": {"fundamental": 1.0},
            "regime_multipliers": {"fundamental": 1.0},
            "decay_policy": {"default": 1.0},
        }


def test_build_runtime_from_env_returns_real_service_with_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Full override path: env supplies graph-engine internals (Neo4j +
    PostgreSQL + snapshot artifact root); cross-module adapters are passed
    explicitly. This is the test recipe production-runtime composition
    helpers are expected to follow when they want isolated unit coverage."""

    _live_env(monkeypatch, tmp_path)

    runtime = build_graph_phase1_runtime_from_env(
        candidate_reader=_StaticCandidateReader(),
        entity_reader=_StaticEntityReader(),
        canonical_writer=_CapturingCanonicalWriter(),
        regime_reader=_StaticRegimeReader(),
    )

    assert isinstance(runtime, GraphPhase1Service)
    assert isinstance(runtime.client, Neo4jClient)
    assert isinstance(runtime.status_manager, GraphStatusManager)
    assert isinstance(runtime.snapshot_writer, FormalArtifactSnapshotWriter)


def test_build_runtime_raises_when_neo4j_password_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _live_env(monkeypatch, tmp_path)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    with pytest.raises(EnvironmentError, match="NEO4J_URI/USER/PASSWORD"):
        build_graph_phase1_runtime_from_env(
            candidate_reader=_StaticCandidateReader(),
            entity_reader=_StaticEntityReader(),
            canonical_writer=_CapturingCanonicalWriter(),
            regime_reader=_StaticRegimeReader(),
        )


def test_build_runtime_raises_when_database_url_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _live_env(monkeypatch, tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(EnvironmentError, match="DATABASE_URL"):
        build_graph_phase1_runtime_from_env(
            candidate_reader=_StaticCandidateReader(),
            entity_reader=_StaticEntityReader(),
            canonical_writer=_CapturingCanonicalWriter(),
            regime_reader=_StaticRegimeReader(),
        )


def test_build_runtime_raises_when_snapshot_artifact_root_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _live_env(monkeypatch, tmp_path)
    monkeypatch.delenv("GRAPH_PHASE1_SNAPSHOT_ARTIFACT_ROOT", raising=False)

    with pytest.raises(EnvironmentError, match="SNAPSHOT_ARTIFACT_ROOT"):
        build_graph_phase1_runtime_from_env(
            candidate_reader=_StaticCandidateReader(),
            entity_reader=_StaticEntityReader(),
            canonical_writer=_CapturingCanonicalWriter(),
            regime_reader=_StaticRegimeReader(),
        )


def test_build_runtime_accepts_explicit_snapshot_writer_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``snapshot_writer=`` override bypasses GRAPH_PHASE1_SNAPSHOT_ARTIFACT_ROOT
    so tests can supply an in-process writer."""

    _live_env(monkeypatch, tmp_path)
    monkeypatch.delenv("GRAPH_PHASE1_SNAPSHOT_ARTIFACT_ROOT", raising=False)

    snapshot_writer = FormalArtifactSnapshotWriter(tmp_path / "explicit")
    runtime = build_graph_phase1_runtime_from_env(
        candidate_reader=_StaticCandidateReader(),
        entity_reader=_StaticEntityReader(),
        canonical_writer=_CapturingCanonicalWriter(),
        regime_reader=_StaticRegimeReader(),
        snapshot_writer=snapshot_writer,
    )

    assert runtime.snapshot_writer is snapshot_writer


def test_phase1_provider_get_resources_raises_when_runtime_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 0 pattern: get_resources must raise rather than silently
    substitute a fail-closed runtime (M2.3a-2 architectural drift fix)."""

    from graph_engine.providers.phase1 import GraphPhase1AssetFactoryProvider

    provider = GraphPhase1AssetFactoryProvider(runtime=None)
    with pytest.raises(RuntimeError, match="not configured"):
        provider.get_resources()


def test_build_runtime_requires_injected_cross_module_protocols(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _live_env(monkeypatch, tmp_path)

    with pytest.raises(EnvironmentError, match="candidate_reader"):
        build_graph_phase1_runtime_from_env()


def test_build_runtime_requires_injected_regime_reader(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _live_env(monkeypatch, tmp_path)

    with pytest.raises(EnvironmentError, match="regime_reader"):
        build_graph_phase1_runtime_from_env(
            candidate_reader=_StaticCandidateReader(),
            entity_reader=_StaticEntityReader(),
            canonical_writer=_CapturingCanonicalWriter(),
        )


def test_phase1_provider_source_has_no_reverse_imports() -> None:
    import ast

    from graph_engine.providers import phase1

    source_path = Path(phase1.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)

    forbidden_imports = {
        module_name
        for module_name in imported_modules
        if module_name == "data_platform"
        or module_name.startswith("data_platform.")
        or module_name == "main_core"
        or module_name.startswith("main_core.")
    }
    assert forbidden_imports == set()


def test_build_fail_closed_graph_phase1_provider_returns_typed_provider() -> None:
    """Public factory replaces the M2.3a-2 private import workaround in
    orchestrator's _build_fail_closed_graph_phase1_provider helper."""

    from graph_engine.providers import build_fail_closed_graph_phase1_provider

    provider = build_fail_closed_graph_phase1_provider()

    # The factory returns a provider whose runtime is the fail-closed stub;
    # asset-evaluation will raise rather than silently no-op.
    assert provider.__class__.__name__ == "GraphPhase1AssetFactoryProvider"
    assert provider.runtime.__class__.__name__ == "_FailClosedGraphPhase1Runtime"


def test_phase1_module_all_exports_runtime_factories() -> None:
    from graph_engine.providers import phase1

    assert "build_fail_closed_graph_phase1_provider" in phase1.__all__
    assert "build_graph_phase1_runtime_from_env" in phase1.__all__
