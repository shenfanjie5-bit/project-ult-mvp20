from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any, Literal
from unittest.mock import MagicMock

import pytest

import graph_engine.snapshots.generator as snapshot_generator
from graph_engine.live_metrics import LiveGraphMetrics
from graph_engine.models import (
    CandidateGraphDelta,
    FrozenGraphDelta,
    GraphImpactSnapshot,
    GraphSnapshot,
    Neo4jGraphStatus,
    PropagationContext,
    PropagationResult,
)
from graph_engine.promotion import build_promotion_plan
from graph_engine.propagation import run_fundamental_propagation
from graph_engine.snapshots import (
    build_graph_impact_snapshot,
    build_graph_snapshot,
    compute_graph_snapshots,
)
from graph_engine.status import GraphStatusManager

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)


class FakeSnapshotClient:
    def __init__(
        self,
        *,
        nodes: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> None:
        self.nodes = nodes
        self.relationships = relationships
        self.read_calls: list[str] = []

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.read_calls.append(query)
        if "RETURN node_count, edge_count, label_counts, nodes, relationships" in query:
            counts: dict[str, int] = {}
            for node in self.nodes:
                for label in node["labels"]:
                    counts[label] = counts.get(label, 0) + 1
            return [
                {
                    "node_count": len(self.nodes),
                    "edge_count": len(self.relationships),
                    "label_counts": [
                        {"label": label, "count": count}
                        for label, count in sorted(counts.items())
                    ],
                    "nodes": list(self.nodes),
                    "relationships": list(self.relationships),
                }
            ]
        return []


class FakePropagationReaderClient:
    def __init__(self) -> None:
        self.read_calls: list[str] = []
        self.write_calls: list[str] = []

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.read_calls.append(query)
        if "gds.graph.exists" in query:
            return [{"exists": False}]
        if "gds.pageRank.stream" in query:
            return [
                {
                    "node_id": "node-2",
                    "canonical_entity_id": "entity-2",
                    "labels": ["Entity"],
                    "stable_node_id": "node-2",
                    "score": 0.4,
                }
            ]
        if "MATCH (source)-[relationship]->(target)" in query:
            return [
                {
                    "source_node_id": "node-1",
                    "source_entity_id": "entity-1",
                    "source_labels": ["Entity"],
                    "target_node_id": "node-2",
                    "target_entity_id": "entity-2",
                    "target_labels": ["Entity"],
                    "edge_id": "edge-1",
                    "relationship_type": "SUPPLY_CHAIN",
                    "evidence_refs": ["fact-synced-1"],
                    "evidence_ref": None,
                    "relation_weight": 0.7,
                    "evidence_confidence": 1.0,
                    "recency_decay": 1.0,
                    "path_score": 0.7,
                }
            ]
        return []

    def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.write_calls.append(query)
        if "gds.graph.project" in query:
            return [{"relationshipCount": 1}]
        return []


class StaticRegimeReader:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def read_regime_context(self, world_state_ref: str) -> dict[str, Any]:
        self.calls.append(world_state_ref)
        return {}


class RecordingSnapshotWriter:
    def __init__(self, events: list[str] | None = None) -> None:
        self.events = events
        self.calls: list[tuple[GraphSnapshot, GraphImpactSnapshot]] = []

    def write_snapshots(
        self,
        graph_snapshot: GraphSnapshot,
        impact_snapshot: GraphImpactSnapshot,
    ) -> None:
        if self.events is not None:
            self.events.append("write")
        self.calls.append((graph_snapshot, impact_snapshot))


class RaisingSnapshotWriter:
    def write_snapshots(
        self,
        graph_snapshot: GraphSnapshot,
        impact_snapshot: GraphImpactSnapshot,
    ) -> None:
        raise RuntimeError("writer failed")


class SequentialStatusStore:
    def __init__(
        self,
        graph_status: Neo4jGraphStatus | list[Neo4jGraphStatus],
    ) -> None:
        if isinstance(graph_status, list):
            self.graph_statuses = graph_status
        else:
            self.graph_statuses = [graph_status]
        self.calls = 0

    def read_current_status(self) -> Neo4jGraphStatus:
        self.calls += 1
        index = min(self.calls - 1, len(self.graph_statuses) - 1)
        return self.graph_statuses[index]

    def ready_read_lock(self) -> nullcontext[None]:
        return nullcontext()

    def write_current_status(self, status: Neo4jGraphStatus) -> None:
        self.graph_statuses = [status]

    def compare_and_write_current_status(
        self,
        *,
        expected_status: Neo4jGraphStatus | None,
        next_status: Neo4jGraphStatus,
    ) -> bool:
        if self.graph_statuses[-1] != expected_status:
            return False
        self.write_current_status(next_status)
        return True


def test_build_graph_snapshot_reads_metrics_and_stable_checksum() -> None:
    client = FakeSnapshotClient(
        nodes=[
            {
                "labels": ["Entity"],
                "node_id": "node-b",
                "canonical_entity_id": "entity-b",
                "properties": {"node_id": "node-b", "ticker": "BBB"},
            },
            {
                "labels": ["Entity", "Sector"],
                "node_id": "node-a",
                "canonical_entity_id": "entity-a",
                "properties": {"node_id": "node-a", "ticker": "AAA"},
            },
        ],
        relationships=[
            {
                "source_node_id": "node-a",
                "target_node_id": "node-b",
                "relationship_type": "SUPPLY_CHAIN",
                "edge_id": "edge-1",
                "properties": {"weight": 0.7},
            }
        ],
    )
    status_manager, _ = _status_manager(_ready_status(graph_generation_id=3))

    first = build_graph_snapshot(  # type: ignore[arg-type]
        "cycle-1",
        3,
        client,
        status_manager=status_manager,
    )
    second = build_graph_snapshot(  # type: ignore[arg-type]
        "cycle-1",
        3,
        client,
        status_manager=status_manager,
    )

    assert first.node_count == 2
    assert first.edge_count == 1
    assert [node.node_id for node in first.nodes] == ["node-b", "node-a"]
    assert first.nodes[0].entity is not None
    assert first.nodes[0].entity.entity_id == "entity-b"
    assert first.edges[0].relation_type == "SUPPLY_CHAIN"
    assert first.graph_snapshot_id == second.graph_snapshot_id
    assert len(client.read_calls) == 2

    client.relationships[0] = {
        **client.relationships[0],
        "properties": {"weight": 0.9},
    }
    changed = build_graph_snapshot(  # type: ignore[arg-type]
        "cycle-1",
        3,
        client,
        status_manager=status_manager,
    )
    assert changed.graph_snapshot_id != first.graph_snapshot_id
    assert len(client.read_calls) == 3


def test_build_graph_snapshot_blocks_non_ready_before_reading() -> None:
    client = MagicMock()
    status_manager, _ = _status_manager(_ready_status(graph_status="failed"))

    with pytest.raises(PermissionError, match="ready"):
        build_graph_snapshot(
            "cycle-1",
            1,
            client,
            status_manager=status_manager,
        )

    client.execute_read.assert_not_called()


def test_build_graph_snapshot_blocks_active_writer_lock_before_reading() -> None:
    client = MagicMock()
    status_manager, _ = _status_manager(
        _ready_status(writer_lock_token="incremental-sync"),
    )

    with pytest.raises(PermissionError, match="writer lock"):
        build_graph_snapshot(
            "cycle-1",
            1,
            client,
            status_manager=status_manager,
        )

    client.execute_read.assert_not_called()


def test_build_graph_impact_snapshot_returns_contract_payload() -> None:
    propagation_result = _propagation_result()

    impact_snapshot = build_graph_impact_snapshot(
        "cycle-1",
        "world-state-1",
        propagation_result,
    )

    # Snapshot version stamps the live contracts version
    # (graph_engine.snapshots.generator imports
    # ``contracts.core.__version__`` as CONTRACT_VERSION). Avoid
    # hardcoding the literal so the test doesn't drift on each
    # contracts bump (Stage 2.10 follow-up: contracts went 0.1.0 →
    # 0.1.3).
    from contracts.core import __version__ as _CONTRACT_VERSION

    assert impact_snapshot.version == _CONTRACT_VERSION
    assert [entity.entity_id for entity in impact_snapshot.target_entities] == ["node-2"]
    assert [entity.entity_id for entity in impact_snapshot.affected_entities] == ["node-2"]
    assert impact_snapshot.direction == "bullish"
    assert impact_snapshot.impact_score == pytest.approx(0.4)
    assert impact_snapshot.evidence_refs == ["fact-1"]


def test_build_graph_impact_snapshot_rejects_edge_id_as_evidence_fallback() -> None:
    propagation_result = _propagation_result()
    propagation_result.activated_paths[0].pop("evidence_refs")

    with pytest.raises(
        ValueError,
        match=r"real evidence references.*paths_without_evidence=\['edge-1'\]",
    ):
        build_graph_impact_snapshot(
            "cycle-1",
            "world-state-1",
            propagation_result,
        )


def test_build_graph_impact_snapshot_rejects_forged_evidence_refs() -> None:
    propagation_result = _propagation_result()
    propagation_result.activated_paths[0]["evidence_refs"] = [{"source": "filing"}]

    with pytest.raises(ValueError, match="evidence refs must be non-empty strings"):
        build_graph_impact_snapshot(
            "cycle-1",
            "world-state-1",
            propagation_result,
        )


def test_build_graph_impact_snapshot_extracts_refs_from_evidence_mapping() -> None:
    propagation_result = _propagation_result()
    propagation_result.activated_paths[0].pop("evidence_refs")
    propagation_result.activated_paths[0]["evidence"] = {
        "source": "filing",
        "evidence_refs": ["fact-1"],
    }

    impact_snapshot = build_graph_impact_snapshot(
        "cycle-1",
        "world-state-1",
        propagation_result,
    )

    assert impact_snapshot.evidence_refs == ["fact-1"]


def test_build_graph_impact_snapshot_empty_impact_error_has_context() -> None:
    propagation_result = PropagationResult(
        cycle_id="cycle-1",
        graph_generation_id=1,
        activated_paths=[],
        impacted_entities=[],
        channel_breakdown={"fundamental": {"path_count": 0}},
    )

    with pytest.raises(
        ValueError,
        match=(
            "target entity.*cycle_id='cycle-1'.*world_state_ref='world-state-1'.*"
            "graph_generation_id=1"
        ),
    ):
        build_graph_impact_snapshot(
            "cycle-1",
            "world-state-1",
            propagation_result,
        )


def test_build_graph_impact_snapshot_id_tracks_full_propagation_payload() -> None:
    baseline = build_graph_impact_snapshot(
        "cycle-1",
        "world-state-1",
        _propagation_result(),
    )
    repeated = build_graph_impact_snapshot(
        "cycle-1",
        "world-state-1",
        _propagation_result(),
    )
    changed_breakdown = _propagation_result()
    changed_breakdown.channel_breakdown["event"] = {"path_count": 1}
    changed = build_graph_impact_snapshot(
        "cycle-1",
        "world-state-1",
        changed_breakdown,
    )

    assert repeated.impact_snapshot_id == baseline.impact_snapshot_id
    assert changed.impact_snapshot_id != baseline.impact_snapshot_id


def test_compute_graph_snapshots_requires_status_source_without_side_effects() -> None:
    client = MagicMock()
    reader = StaticRegimeReader()
    writer = RecordingSnapshotWriter()

    with pytest.raises(TypeError, match="status_manager"):
        compute_graph_snapshots(
            "cycle-1",
            "world-state-1",
            client=client,
            graph_generation_id=1,
            regime_reader=reader,
            snapshot_writer=writer,
        )

    assert reader.calls == []
    assert writer.calls == []
    client.execute_read.assert_not_called()
    client.execute_write.assert_not_called()


def test_compute_graph_snapshots_rejects_graph_status_without_status_manager() -> None:
    client = MagicMock()
    reader = StaticRegimeReader()
    writer = RecordingSnapshotWriter()

    with pytest.raises(TypeError, match="status_manager"):
        compute_graph_snapshots(
            "cycle-1",
            "world-state-1",
            client=client,
            graph_generation_id=1,
            regime_reader=reader,
            snapshot_writer=writer,
            graph_status=_ready_status(),
        )

    assert reader.calls == []
    assert writer.calls == []
    client.execute_read.assert_not_called()
    client.execute_write.assert_not_called()


def test_compute_graph_snapshots_rejects_non_ready_status_without_side_effects() -> None:
    client = MagicMock()
    reader = StaticRegimeReader()
    writer = RecordingSnapshotWriter()
    status_manager, _ = _status_manager(
        _ready_status(
            graph_status="failed",
            node_count=0,
            edge_count=0,
            key_label_counts={},
            checksum="failed",
        ),
    )

    with pytest.raises(PermissionError, match="ready"):
        compute_graph_snapshots(
            "cycle-1",
            "world-state-1",
            client=client,
            graph_generation_id=1,
            regime_reader=reader,
            snapshot_writer=writer,
            status_manager=status_manager,
        )

    assert reader.calls == []
    assert writer.calls == []
    client.execute_read.assert_not_called()
    client.execute_write.assert_not_called()


def test_compute_graph_snapshots_rejects_active_writer_lock_without_side_effects() -> None:
    client = MagicMock()
    reader = StaticRegimeReader()
    writer = RecordingSnapshotWriter()
    status_manager, _ = _status_manager(
        _ready_status(writer_lock_token="incremental-sync"),
    )

    with pytest.raises(PermissionError, match="writer lock"):
        compute_graph_snapshots(
            "cycle-1",
            "world-state-1",
            client=client,
            graph_generation_id=1,
            regime_reader=reader,
            snapshot_writer=writer,
            status_manager=status_manager,
        )

    assert reader.calls == []
    assert writer.calls == []
    client.execute_read.assert_not_called()
    client.execute_write.assert_not_called()


def test_compute_graph_snapshots_uses_status_manager_and_derives_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    status_manager, status_store = _status_manager(_ready_status(graph_generation_id=7))
    writer = RecordingSnapshotWriter(events)

    _patch_metrics(monkeypatch, events)

    def build_context(
        cycle_id: str,
        world_state_ref: str,
        graph_generation_id: int,
        **kwargs: Any,
    ) -> PropagationContext:
        events.append(f"context:{graph_generation_id}")
        assert kwargs["enabled_channels"] == ["fundamental", "event", "reflexive"]
        return _context(graph_generation_id=graph_generation_id)

    def run_propagation(
        context: PropagationContext,
        *args: Any,
        **kwargs: Any,
    ) -> PropagationResult:
        events.append(f"propagation:{context.graph_generation_id}")
        return _propagation_result(graph_generation_id=context.graph_generation_id)

    monkeypatch.setattr(snapshot_generator, "build_propagation_context", build_context)
    monkeypatch.setattr(snapshot_generator, "run_full_propagation", run_propagation)

    graph_snapshot, impact_snapshot = compute_graph_snapshots(
        "cycle-1",
        "world-state-1",
        client=MagicMock(),
        regime_reader=StaticRegimeReader(),
        snapshot_writer=writer,
        status_manager=status_manager,
    )

    assert status_store.calls == 3
    assert graph_snapshot.graph_snapshot_id.startswith("graph-snapshot-cycle-1-7-")
    assert graph_snapshot.node_count == 2
    assert graph_snapshot.edge_count == 1
    assert impact_snapshot.cycle_id == "cycle-1"
    assert events == [
        "metrics",
        "context:7",
        "propagation:7",
        "metrics",
        "metrics",
        "write",
    ]
    assert writer.calls == [(graph_snapshot, impact_snapshot)]


@pytest.mark.parametrize(
    ("field_name", "graph_generation_id", "status_updates", "expected_events"),
    [
        ("graph_generation_id", 2, {}, []),
        ("node_count", 1, {"node_count": 999}, ["metrics"]),
        ("edge_count", 1, {"edge_count": 999}, ["metrics"]),
        (
            "key_label_counts",
            1,
            {"key_label_counts": {"Entity": 999}},
            ["metrics"],
        ),
        ("checksum", 1, {"checksum": "stale"}, ["metrics"]),
    ],
)
def test_compute_graph_snapshots_rejects_status_disagreements_before_write(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    graph_generation_id: int,
    status_updates: dict[str, Any],
    expected_events: list[str],
) -> None:
    events: list[str] = []
    reader = StaticRegimeReader()
    writer = RecordingSnapshotWriter()
    graph_status = _ready_status(**status_updates)
    status_manager, _ = _status_manager(graph_status)

    _patch_metrics(monkeypatch, events)

    def run_propagation(*args: Any, **kwargs: Any) -> PropagationResult:
        events.append("propagation")
        return _propagation_result()

    monkeypatch.setattr(snapshot_generator, "run_full_propagation", run_propagation)

    with pytest.raises(ValueError, match=field_name):
        compute_graph_snapshots(
            "cycle-1",
            "world-state-1",
            client=MagicMock(),
            graph_generation_id=graph_generation_id,
            regime_reader=reader,
            snapshot_writer=writer,
            status_manager=status_manager,
        )

    assert events == expected_events
    assert reader.calls == []
    assert writer.calls == []


def test_compute_graph_snapshots_writes_once_after_both_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    impact_snapshot = _impact_snapshot()

    _patch_metrics(monkeypatch, events)
    monkeypatch.setattr(
        snapshot_generator,
        "build_propagation_context",
        lambda *args, **kwargs: events.append("context") or _context(),
    )
    monkeypatch.setattr(
        snapshot_generator,
        "run_full_propagation",
        lambda *args, **kwargs: events.append("propagation") or _propagation_result(),
    )
    monkeypatch.setattr(
        snapshot_generator,
        "build_graph_impact_snapshot",
        lambda *args, **kwargs: events.append("impact") or impact_snapshot,
    )
    writer = RecordingSnapshotWriter(events)
    status_manager, _ = _status_manager(_ready_status())

    result = compute_graph_snapshots(
        "cycle-1",
        "world-state-1",
        client=MagicMock(),
        graph_generation_id=1,
        regime_reader=StaticRegimeReader(),
        snapshot_writer=writer,
        status_manager=status_manager,
    )

    graph_snapshot = result[0]
    assert result == (graph_snapshot, impact_snapshot)
    assert graph_snapshot.node_count == 2
    assert graph_snapshot.edge_count == 1
    assert events == [
        "metrics",
        "context",
        "propagation",
        "metrics",
        "impact",
        "metrics",
        "write",
    ]
    assert writer.calls == [(graph_snapshot, impact_snapshot)]


def test_compute_graph_snapshots_accepts_single_channel_regression_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_channels: list[str] = []

    _patch_metrics(monkeypatch)

    def build_context(*args: Any, **kwargs: Any) -> PropagationContext:
        requested_channels.extend(kwargs["enabled_channels"])
        return _context()

    monkeypatch.setattr(snapshot_generator, "build_propagation_context", build_context)
    monkeypatch.setattr(
        snapshot_generator,
        "run_full_propagation",
        lambda *args, **kwargs: _propagation_result(),
    )
    status_manager, _ = _status_manager(_ready_status())

    compute_graph_snapshots(
        "cycle-1",
        "world-state-1",
        client=MagicMock(),
        graph_generation_id=1,
        regime_reader=StaticRegimeReader(),
        snapshot_writer=RecordingSnapshotWriter(),
        status_manager=status_manager,
        enabled_channels=["fundamental"],
    )

    assert requested_channels == ["fundamental"]


def test_compute_graph_snapshots_publishes_promoted_contract_delta_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract_delta = CandidateGraphDelta(
        delta_id="contract-edge-1",
        delta_type="upsert_edge",
        source_node="node-1",
        target_node="node-2",
        relation_type="SUPPLY_CHAIN",
        properties={
            "evidence_confidence": 0.9,
            "recency_decay": 1.0,
            "weight": 0.7,
        },
        evidence=["fact-contract-1"],
        subsystem_id="subsystem-news",
    )
    plan = build_promotion_plan(
        "cycle-1",
        "selection-1",
        [
            FrozenGraphDelta(
                delta_id="delta-1",
                cycle_id="cycle-1",
                delta_type="edge_add",
                source_entity_ids=["entity-1", "entity-2"],
                payload=contract_delta.model_dump(),
                validation_status="frozen",
            ),
        ],
    )
    edge_record = plan.edge_records[0]
    client = FakeSnapshotClient(
        nodes=[
            {
                "labels": ["Entity"],
                "node_id": edge_record.source_node_id,
                "canonical_entity_id": "entity-1",
                "properties": {"node_id": edge_record.source_node_id},
            },
            {
                "labels": ["Entity"],
                "node_id": edge_record.target_node_id,
                "canonical_entity_id": "entity-2",
                "properties": {"node_id": edge_record.target_node_id},
            },
        ],
        relationships=[
            {
                "source_node_id": edge_record.source_node_id,
                "target_node_id": edge_record.target_node_id,
                "relationship_type": edge_record.relationship_type,
                "edge_id": edge_record.edge_id,
                "properties": {
                    "edge_id": edge_record.edge_id,
                    **edge_record.properties,
                },
            },
        ],
    )
    node_count, edge_count, key_label_counts, checksum = snapshot_generator._read_graph_metrics(
        client,
    )
    client.read_calls.clear()
    status_manager, _ = _status_manager(
        _ready_status(
            node_count=node_count,
            edge_count=edge_count,
            key_label_counts=key_label_counts,
            checksum=checksum,
        ),
    )

    def run_propagation(
        context: PropagationContext,
        passed_client: Any,
        **kwargs: Any,
    ) -> PropagationResult:
        assert context.graph_generation_id == 1
        assert passed_client is client
        return PropagationResult(
            cycle_id="cycle-1",
            graph_generation_id=context.graph_generation_id,
            activated_paths=[
                {
                    "source_node_id": edge_record.source_node_id,
                    "source_labels": ["Entity"],
                    "target_node_id": edge_record.target_node_id,
                    "target_labels": ["Entity"],
                    "edge_id": edge_record.edge_id,
                    "relationship_type": edge_record.relationship_type,
                    "evidence_refs": edge_record.properties["evidence_refs"],
                    "score": 0.7,
                }
            ],
            impacted_entities=[
                {
                    "node_id": edge_record.target_node_id,
                    "labels": ["Entity"],
                    "score": 0.7,
                }
            ],
            channel_breakdown={"fundamental": {"path_count": 1}},
        )

    monkeypatch.setattr(snapshot_generator, "run_full_propagation", run_propagation)
    writer = RecordingSnapshotWriter()

    graph_snapshot, impact_snapshot = compute_graph_snapshots(
        "cycle-1",
        "world-state-1",
        client=client,
        graph_generation_id=1,
        regime_reader=StaticRegimeReader(),
        snapshot_writer=writer,
        status_manager=status_manager,
        enabled_channels=["fundamental"],
    )

    assert graph_snapshot.edges[0].evidence_refs == ["fact-contract-1"]
    assert impact_snapshot.evidence_refs == ["fact-contract-1"]
    assert writer.calls == [(graph_snapshot, impact_snapshot)]


def test_real_channel_reader_preserves_synced_relationship_evidence_refs() -> None:
    client = FakePropagationReaderClient()
    status_manager, _ = _status_manager(_ready_status())

    propagation_result = run_fundamental_propagation(
        _context(),
        client,  # type: ignore[arg-type]
        status_manager=status_manager,
        graph_name="unit-snapshot-fundamental",
        result_limit=10,
    )
    impact_snapshot = build_graph_impact_snapshot(
        "cycle-1",
        "world-state-1",
        propagation_result,
    )

    assert propagation_result.activated_paths[0]["evidence_refs"] == ["fact-synced-1"]
    assert impact_snapshot.evidence_refs == ["fact-synced-1"]
    assert any("relationship.evidence_refs AS evidence_refs" in query for query in client.read_calls)


def test_compute_graph_snapshots_rechecks_status_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    ready_status = _ready_status()
    rebuilding_status = _ready_status(graph_status="rebuilding")
    status_manager, status_store = _status_manager([ready_status, ready_status, rebuilding_status])
    writer = RecordingSnapshotWriter(events)

    _patch_metrics(monkeypatch, events)
    monkeypatch.setattr(
        snapshot_generator,
        "build_propagation_context",
        lambda *args, **kwargs: events.append("context") or _context(),
    )
    monkeypatch.setattr(
        snapshot_generator,
        "run_full_propagation",
        lambda *args, **kwargs: events.append("propagation") or _propagation_result(),
    )
    monkeypatch.setattr(
        snapshot_generator,
        "build_graph_impact_snapshot",
        lambda *args, **kwargs: events.append("impact") or _impact_snapshot(),
    )

    with pytest.raises(RuntimeError, match="changed before snapshot publication"):
        compute_graph_snapshots(
            "cycle-1",
            "world-state-1",
            client=MagicMock(),
            graph_generation_id=1,
            regime_reader=StaticRegimeReader(),
            snapshot_writer=writer,
            status_manager=status_manager,
        )

    assert status_store.calls == 3
    assert events == ["metrics", "context", "propagation", "metrics", "impact"]
    assert writer.calls == []


def test_compute_graph_snapshots_rechecks_live_metrics_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    writer = RecordingSnapshotWriter(events)

    _patch_metrics(
        monkeypatch,
        events,
        metrics_sequence=[
            (2, 1, {"Entity": 2}, "abc123"),
            (2, 1, {"Entity": 2}, "abc123"),
            (3, 1, {"Entity": 3}, "changed"),
        ],
    )
    monkeypatch.setattr(
        snapshot_generator,
        "build_propagation_context",
        lambda *args, **kwargs: events.append("context") or _context(),
    )
    monkeypatch.setattr(
        snapshot_generator,
        "run_full_propagation",
        lambda *args, **kwargs: events.append("propagation") or _propagation_result(),
    )
    monkeypatch.setattr(
        snapshot_generator,
        "build_graph_impact_snapshot",
        lambda *args, **kwargs: events.append("impact") or _impact_snapshot(),
    )
    status_manager, _ = _status_manager(_ready_status())

    with pytest.raises(ValueError, match="live graph metrics disagree"):
        compute_graph_snapshots(
            "cycle-1",
            "world-state-1",
            client=MagicMock(),
            graph_generation_id=1,
            regime_reader=StaticRegimeReader(),
            snapshot_writer=writer,
            status_manager=status_manager,
        )

    assert events == ["metrics", "context", "propagation", "metrics", "impact", "metrics"]
    assert writer.calls == []


def test_compute_graph_snapshots_does_not_write_if_snapshot_build_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = RecordingSnapshotWriter()

    _patch_metrics(monkeypatch)
    monkeypatch.setattr(
        snapshot_generator,
        "build_propagation_context",
        lambda *args, **kwargs: _context(),
    )
    monkeypatch.setattr(
        snapshot_generator,
        "run_full_propagation",
        lambda *args, **kwargs: _propagation_result(),
    )

    def raise_impact_error(*args: Any, **kwargs: Any) -> GraphImpactSnapshot:
        raise ValueError("impact failed")

    monkeypatch.setattr(
        snapshot_generator,
        "build_graph_impact_snapshot",
        raise_impact_error,
    )
    status_manager, _ = _status_manager(_ready_status())

    with pytest.raises(ValueError, match="impact failed"):
        compute_graph_snapshots(
            "cycle-1",
            "world-state-1",
            client=MagicMock(),
            graph_generation_id=1,
            regime_reader=StaticRegimeReader(),
            snapshot_writer=writer,
            status_manager=status_manager,
        )

    assert writer.calls == []


def test_compute_graph_snapshots_surfaces_writer_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_metrics(monkeypatch)
    monkeypatch.setattr(
        snapshot_generator,
        "build_propagation_context",
        lambda *args, **kwargs: _context(),
    )
    monkeypatch.setattr(
        snapshot_generator,
        "run_full_propagation",
        lambda *args, **kwargs: _propagation_result(),
    )
    monkeypatch.setattr(
        snapshot_generator,
        "build_graph_impact_snapshot",
        lambda *args, **kwargs: _impact_snapshot(),
    )
    status_manager, _ = _status_manager(_ready_status())

    with pytest.raises(RuntimeError, match="writer failed"):
        compute_graph_snapshots(
            "cycle-1",
            "world-state-1",
            client=MagicMock(),
            graph_generation_id=1,
            regime_reader=StaticRegimeReader(),
            snapshot_writer=RaisingSnapshotWriter(),
            status_manager=status_manager,
        )


def _patch_metrics(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str] | None = None,
    metrics_sequence: list[tuple[int, int, dict[str, int], str]] | None = None,
) -> None:
    metrics = metrics_sequence or [(2, 1, {"Entity": 2}, "abc123")]
    calls = 0

    def read_metrics(client: Any) -> tuple[int, int, dict[str, int], str]:
        nonlocal calls
        if events is not None:
            events.append("metrics")
        index = min(calls, len(metrics) - 1)
        calls += 1
        return metrics[index]

    def read_metric_payload(client: Any) -> LiveGraphMetrics:
        node_count, edge_count, key_label_counts, checksum = read_metrics(client)
        nodes = [
            {
                "labels": ["Entity"],
                "node_id": f"node-{index}",
                "canonical_entity_id": f"entity-{index}",
                "properties": {"node_id": f"node-{index}"},
            }
            for index in range(1, node_count + 1)
        ]
        relationships = [
            {
                "source_node_id": "node-1",
                "target_node_id": "node-2",
                "relationship_type": "SUPPLY_CHAIN",
                "edge_id": f"edge-{index}",
                "properties": {"edge_id": f"edge-{index}"},
            }
            for index in range(1, edge_count + 1)
        ]
        return LiveGraphMetrics(
            node_count=node_count,
            edge_count=edge_count,
            key_label_counts=key_label_counts,
            checksum=checksum,
            nodes=nodes,
            relationships=relationships,
        )

    monkeypatch.setattr(snapshot_generator, "_read_graph_metrics", read_metrics)
    monkeypatch.setattr(snapshot_generator, "_read_graph_metric_payload", read_metric_payload)


def _status_manager(
    graph_status: Neo4jGraphStatus | list[Neo4jGraphStatus],
) -> tuple[GraphStatusManager, SequentialStatusStore]:
    store = SequentialStatusStore(graph_status)
    return GraphStatusManager(store), store


def _ready_status(
    *,
    graph_status: Literal["ready", "rebuilding", "failed"] = "ready",
    graph_generation_id: int = 1,
    node_count: int = 2,
    edge_count: int = 1,
    key_label_counts: dict[str, int] | None = None,
    checksum: str = "abc123",
    writer_lock_token: str | None = None,
) -> Neo4jGraphStatus:
    return Neo4jGraphStatus(
        graph_status=graph_status,
        graph_generation_id=graph_generation_id,
        node_count=node_count,
        edge_count=edge_count,
        key_label_counts={"Entity": 2} if key_label_counts is None else key_label_counts,
        checksum=checksum,
        last_verified_at=NOW,
        last_reload_at=None,
        writer_lock_token=writer_lock_token,
    )


def _context(graph_generation_id: int = 1) -> PropagationContext:
    return PropagationContext(
        cycle_id="cycle-1",
        world_state_ref="world-state-1",
        graph_generation_id=graph_generation_id,
        enabled_channels=["fundamental"],
        channel_multipliers={"fundamental": 1.0},
        regime_multipliers={"fundamental": 1.0},
        decay_policy={},
        regime_context={},
    )


def _propagation_result(graph_generation_id: int = 1) -> PropagationResult:
    return PropagationResult(
        cycle_id="cycle-1",
        graph_generation_id=graph_generation_id,
        activated_paths=[
            {
                "source_node_id": "node-1",
                "source_labels": ["Entity"],
                "target_node_id": "node-2",
                "target_labels": ["Entity"],
                "edge_id": "edge-1",
                "evidence_refs": ["fact-1"],
                "score": 0.7,
            }
        ],
        impacted_entities=[{"node_id": "node-2", "labels": ["Entity"], "score": 0.4}],
        channel_breakdown={"fundamental": {"path_count": 1}},
    )


def _impact_snapshot() -> GraphImpactSnapshot:
    return GraphImpactSnapshot(
        cycle_id="cycle-1",
        impact_snapshot_id="impact-1",
        version="0.1.0",
        created_at=NOW,
        target_entities=[
            {
                "entity_id": "node-2",
                "entity_type": "entity",
                "canonical_id_rule_version": "0.1.0",
            }
        ],
        affected_entities=[],
        affected_sectors=[],
        direction="neutral",
        impact_score=0.0,
        evidence_refs=["fact-1"],
    )
