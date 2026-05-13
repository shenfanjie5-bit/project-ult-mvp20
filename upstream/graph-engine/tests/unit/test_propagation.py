from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from graph_engine.models import Neo4jGraphStatus, PropagationContext
from graph_engine.propagation import (
    FUNDAMENTAL_RELATIONSHIP_TYPES,
    build_propagation_context,
    compute_path_score,
    run_fundamental_propagation,
)
from graph_engine.status import GraphStatusManager
from tests.fakes import InMemoryStatusStore

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)


class StaticRegimeReader:
    def __init__(self, regime_context: dict[str, Any]) -> None:
        self.regime_context = regime_context
        self.calls: list[str] = []

    def read_regime_context(self, world_state_ref: str) -> dict[str, Any]:
        self.calls.append(world_state_ref)
        return self.regime_context


class FakeGDSClient:
    def __init__(
        self,
        *,
        exists_results: list[bool] | None = None,
        fail_on_pagerank: bool = False,
        path_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.exists_results = exists_results or [False, True]
        self.fail_on_pagerank = fail_on_pagerank
        self.path_rows = path_rows
        self.read_calls: list[tuple[str, dict[str, Any]]] = []
        self.write_calls: list[tuple[str, dict[str, Any]]] = []

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params = parameters or {}
        self.read_calls.append((query, params))
        if "gds.graph.exists" in query:
            exists = self.exists_results.pop(0) if self.exists_results else False
            return [{"exists": exists}]
        if "gds.pageRank.stream" in query:
            if self.fail_on_pagerank:
                raise RuntimeError("pagerank failed")
            return [
                {
                    "node_id": "node-b",
                    "canonical_entity_id": "entity-b",
                    "labels": ["Entity"],
                    "stable_node_id": "node-b",
                    "score": 0.2,
                },
                {
                    "node_id": "node-a",
                    "canonical_entity_id": "entity-a",
                    "labels": ["Entity"],
                    "stable_node_id": "node-a",
                    "score": 0.9,
                },
            ]
        if "MATCH (source)-[relationship]->(target)" in query:
            rows = self._fundamental_rows()
            if "ORDER BY path_score DESC" in query:
                rows.sort(
                    key=lambda row: (
                        -_path_score(row, params),
                        str(row["source_node_id"]),
                        str(row["relationship_type"]),
                        str(row["target_node_id"]),
                        str(row["edge_id"]),
                    ),
                )
            else:
                rows.sort(
                    key=lambda row: (
                        str(row["source_node_id"]),
                        str(row["relationship_type"]),
                        str(row["target_node_id"]),
                        str(row["edge_id"]),
                    ),
                )
            return rows[: int(params.get("result_limit", len(rows)))]
        return []

    def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params = parameters or {}
        self.write_calls.append((query, params))
        if "gds.graph.project" in query:
            return [
                {
                    "graphName": params.get("graph_name"),
                    "nodeCount": 2 if self._fundamental_rows() else 0,
                    "relationshipCount": len(self._fundamental_rows()),
                }
            ]
        return []

    def _fundamental_rows(self) -> list[dict[str, Any]]:
        rows = self.path_rows if self.path_rows is not None else _default_path_rows()
        return [row for row in rows if _effective_channel(row) == "fundamental"]


def test_compute_path_score_uses_documented_multiplication() -> None:
    assert compute_path_score(
        relation_weight=0.8,
        evidence_confidence=0.5,
        channel_multiplier=1.5,
        regime_multiplier=0.75,
        recency_decay=0.9,
    ) == pytest.approx(0.405)


def test_build_propagation_context_reads_regime_context_only() -> None:
    reader = StaticRegimeReader(
        {
            "channel_multipliers": {"fundamental": 1.25},
            "regime_multipliers": {"fundamental": 0.8},
            "decay_policy": {"half_life_days": 30},
        }
    )

    context = build_propagation_context(
        "cycle-1",
        "world-state-1",
        7,
        regime_reader=reader,
    )

    assert reader.calls == ["world-state-1"]
    assert context.enabled_channels == ["fundamental"]
    assert context.channel_multipliers == {"fundamental": 1.25}
    assert context.regime_multipliers == {"fundamental": 0.8}
    assert context.decay_policy == {"half_life_days": 30}
    assert "main_core" not in sys.modules


def test_propagation_context_accepts_all_channels_and_rejects_duplicates() -> None:
    context = PropagationContext(
        cycle_id="cycle-1",
        world_state_ref="world-state-1",
        graph_generation_id=1,
        enabled_channels=["fundamental", "event", "reflexive"],
        channel_multipliers={"fundamental": 1.0, "event": 1.0, "reflexive": 1.0},
        regime_multipliers={"fundamental": 1.0, "event": 1.0, "reflexive": 1.0},
        decay_policy={},
        regime_context={},
    )

    assert context.enabled_channels == ["fundamental", "event", "reflexive"]

    with pytest.raises(ValidationError, match="duplicates"):
        PropagationContext(
            cycle_id="cycle-1",
            world_state_ref="world-state-1",
            graph_generation_id=1,
            enabled_channels=["event", "event"],
            channel_multipliers={"event": 1.0},
            regime_multipliers={"event": 1.0},
            decay_policy={},
            regime_context={},
        )


def test_build_propagation_context_reads_multipliers_for_requested_channels() -> None:
    reader = StaticRegimeReader(
        {
            "channel_multipliers": {"event": 2.5},
            "regime_multipliers": {"reflexive": 0.25},
            "decay_policy": {"half_life_days": 3},
        }
    )

    context = build_propagation_context(
        "cycle-1",
        "world-state-1",
        7,
        regime_reader=reader,
        enabled_channels=["event", "reflexive"],
    )

    assert reader.calls == ["world-state-1"]
    assert context.enabled_channels == ["event", "reflexive"]
    assert context.channel_multipliers == {"event": 2.5, "reflexive": 1.0}
    assert context.regime_multipliers == {"event": 1.0, "reflexive": 0.25}
    assert context.decay_policy == {"half_life_days": 3}


def test_build_propagation_context_rejects_explicit_empty_channels() -> None:
    reader = StaticRegimeReader({})

    with pytest.raises(ValidationError, match="at least 1"):
        build_propagation_context(
            "cycle-1",
            "world-state-1",
            7,
            regime_reader=reader,
            enabled_channels=[],
        )

    assert reader.calls == ["world-state-1"]


def test_build_propagation_context_rejects_non_ready_status_before_reading() -> None:
    reader = StaticRegimeReader({})
    graph_status = Neo4jGraphStatus(
        graph_status="rebuilding",
        graph_generation_id=1,
        node_count=0,
        edge_count=0,
        key_label_counts={},
        checksum="pending",
        last_verified_at=NOW,
        last_reload_at=None,
    )

    with pytest.raises(PermissionError, match="ready"):
        build_propagation_context(
            "cycle-1",
            "world-state-1",
            1,
            regime_reader=reader,
            graph_status=graph_status,
        )

    assert reader.calls == []


def test_run_fundamental_propagation_uses_gds_projection_and_explains_paths() -> None:
    client = FakeGDSClient(exists_results=[True, True])
    context = _context()

    result = run_fundamental_propagation(
        context,
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        graph_name="unit-fundamental",
        max_iterations=5,
        result_limit=10,
    )

    write_queries = [query for query, _ in client.write_calls]
    assert "gds.graph.drop" in write_queries[0]
    assert "gds.graph.project" in write_queries[1]
    assert "gds.graph.drop" in write_queries[2]
    assert all(" SET " not in query and " DELETE " not in query for query in write_queries)

    projection_query, projection_params = client.write_calls[1]
    assert projection_params["graph_name"] == "unit-fundamental"
    assert "MATCH (source)-[relationship]->(target)" in projection_query
    assert "coalesce(relationship.propagation_channel" in projection_query
    assert 'WHEN "OWNERSHIP" THEN "fundamental"' in projection_query
    assert '= "fundamental"' in projection_query

    pagerank_call = next(
        (query, params)
        for query, params in client.read_calls
        if "gds.pageRank.stream" in query
    )
    assert pagerank_call[1]["max_iterations"] == 5
    assert pagerank_call[1]["result_limit"] == 10

    assert [entity["node_id"] for entity in result.impacted_entities] == [
        "node-b",
        "node-c",
    ]
    assert [entity["score"] for entity in result.impacted_entities] == [
        pytest.approx(0.5),
        pytest.approx(0.2),
    ]
    assert result.impacted_entities[0]["pagerank_score"] == pytest.approx(0.2)
    assert result.activated_paths[0]["edge_id"] == "edge-1"
    assert result.activated_paths[0]["evidence_refs"] == ["fact-edge-1"]
    assert result.activated_paths[0]["score"] == pytest.approx(0.5)
    assert result.activated_paths[0]["explanation"] == {
        "relation_weight": 0.5,
        "evidence_confidence": 1.0,
        "channel_multiplier": 2.0,
        "regime_multiplier": 0.5,
        "recency_decay": 1.0,
        "score": 0.5,
    }
    assert result.channel_breakdown["fundamental"]["path_count"] == 2


def test_run_fundamental_propagation_excludes_relationships_tagged_for_other_channels() -> None:
    client = FakeGDSClient(
        path_rows=[
            _path_row(
                edge_id="edge-fundamental",
                relationship_type="SUPPLY_CHAIN",
                target_node_id="node-fundamental",
                target_entity_id="entity-fundamental",
                relation_weight=1.0,
            ),
            _path_row(
                edge_id="edge-reflexive-ownership",
                relationship_type="OWNERSHIP",
                target_node_id="node-reflexive",
                target_entity_id="entity-reflexive",
                relation_weight=100.0,
                propagation_channel="reflexive",
            ),
        ],
    )

    result = run_fundamental_propagation(
        _context(),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        graph_name="unit-fundamental",
    )

    assert [path["edge_id"] for path in result.activated_paths] == ["edge-fundamental"]
    assert result.channel_breakdown["fundamental"]["path_count"] == 1
    projection_query = next(
        query for query, _ in client.write_calls if "gds.graph.project" in query
    )
    path_query = next(
        query
        for query, _ in client.read_calls
        if "MATCH (source)-[relationship]->(target)" in query
    )
    assert 'relationship.impact_channel, CASE type(relationship)' in projection_query
    assert 'relationship.impact_channel, CASE type(relationship)' in path_query


def test_run_fundamental_propagation_blocks_non_ready_before_neo4j_reads() -> None:
    client = FakeGDSClient()

    with pytest.raises(PermissionError, match="ready"):
        run_fundamental_propagation(
            _context(),
            client,  # type: ignore[arg-type]
            status_manager=_status_manager(graph_status="rebuilding"),
            graph_name="unit-fundamental",
        )

    assert client.read_calls == []
    assert client.write_calls == []


def test_run_fundamental_propagation_blocks_active_writer_lock_before_neo4j_reads() -> None:
    client = FakeGDSClient()

    with pytest.raises(PermissionError, match="writer lock"):
        run_fundamental_propagation(
            _context(),
            client,  # type: ignore[arg-type]
            status_manager=_status_manager(writer_lock_token="incremental-sync"),
            graph_name="unit-fundamental",
        )

    assert client.read_calls == []
    assert client.write_calls == []


def test_run_fundamental_propagation_requires_status_manager_before_neo4j_reads() -> None:
    client = FakeGDSClient()

    with pytest.raises(TypeError, match="status_manager"):
        run_fundamental_propagation(
            _context(),
            client,  # type: ignore[arg-type]
            graph_name="unit-fundamental",
        )

    assert client.read_calls == []
    assert client.write_calls == []


def test_run_fundamental_propagation_generates_unique_default_projection_names() -> None:
    first_client = FakeGDSClient()
    second_client = FakeGDSClient()

    run_fundamental_propagation(  # type: ignore[arg-type]
        _context(),
        first_client,
        status_manager=_status_manager(),
    )
    run_fundamental_propagation(  # type: ignore[arg-type]
        _context(),
        second_client,
        status_manager=_status_manager(),
    )

    first_project = next(
        params["graph_name"]
        for query, params in first_client.write_calls
        if "gds.graph.project" in query
    )
    second_project = next(
        params["graph_name"]
        for query, params in second_client.write_calls
        if "gds.graph.project" in query
    )

    assert first_project.startswith("graph_engine_fundamental_cycle_1_")
    assert second_project.startswith("graph_engine_fundamental_cycle_1_")
    assert first_project != second_project


def test_impacted_entities_use_five_factor_path_scores() -> None:
    client = FakeGDSClient(
        path_rows=[
            {
                "source_node_id": "node-a",
                "source_entity_id": "entity-a",
                "source_labels": ["Entity"],
                "target_node_id": "node-zero",
                "target_entity_id": "entity-zero",
                "target_labels": ["Entity"],
                "edge_id": "edge-zero",
                "relationship_type": "SUPPLY_CHAIN",
                "relation_weight": 100.0,
                "evidence_confidence": 0.0,
                "recency_decay": 1.0,
            },
            {
                "source_node_id": "node-a",
                "source_entity_id": "entity-a",
                "source_labels": ["Entity"],
                "target_node_id": "node-small",
                "target_entity_id": "entity-small",
                "target_labels": ["Entity"],
                "edge_id": "edge-small",
                "relationship_type": "SUPPLY_CHAIN",
                "relation_weight": 0.1,
                "evidence_confidence": 1.0,
                "recency_decay": 1.0,
            },
        ],
    )

    result = run_fundamental_propagation(
        _context(),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        graph_name="unit-fundamental",
    )

    assert [entity["node_id"] for entity in result.impacted_entities] == [
        "node-small",
        "node-zero",
    ]
    assert result.impacted_entities[0]["score"] == pytest.approx(0.1)
    assert result.impacted_entities[1]["score"] == pytest.approx(0.0)


def test_activated_paths_limit_applies_after_five_factor_scoring() -> None:
    client = FakeGDSClient(
        path_rows=[
            {
                "source_node_id": "node-a",
                "source_entity_id": "entity-a",
                "source_labels": ["Entity"],
                "target_node_id": "node-low-1",
                "target_entity_id": "entity-low-1",
                "target_labels": ["Entity"],
                "edge_id": "edge-low-1",
                "relationship_type": "OWNERSHIP",
                "relation_weight": 0.1,
                "evidence_confidence": 1.0,
                "recency_decay": 1.0,
            },
            {
                "source_node_id": "node-b",
                "source_entity_id": "entity-b",
                "source_labels": ["Entity"],
                "target_node_id": "node-low-2",
                "target_entity_id": "entity-low-2",
                "target_labels": ["Entity"],
                "edge_id": "edge-low-2",
                "relationship_type": "OWNERSHIP",
                "relation_weight": 0.2,
                "evidence_confidence": 1.0,
                "recency_decay": 1.0,
            },
            {
                "source_node_id": "node-z",
                "source_entity_id": "entity-z",
                "source_labels": ["Entity"],
                "target_node_id": "node-top",
                "target_entity_id": "entity-top",
                "target_labels": ["Entity"],
                "edge_id": "edge-top",
                "relationship_type": "SUPPLY_CHAIN",
                "relation_weight": 99.0,
                "evidence_confidence": 1.0,
                "recency_decay": 1.0,
            },
        ],
    )

    result = run_fundamental_propagation(
        _context(),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        graph_name="unit-fundamental",
        result_limit=2,
    )

    activated_edge_ids = [path["edge_id"] for path in result.activated_paths]
    assert activated_edge_ids == ["edge-top", "edge-low-2"]
    assert [entity["node_id"] for entity in result.impacted_entities] == [
        "node-top",
        "node-low-2",
    ]

    path_query, path_params = next(
        (query, params)
        for query, params in client.read_calls
        if "MATCH (source)-[relationship]->(target)" in query
    )
    assert "ORDER BY path_score DESC" in path_query
    assert path_params["channel_multiplier"] == pytest.approx(2.0)
    assert path_params["regime_multiplier"] == pytest.approx(0.5)


def test_run_fundamental_propagation_cleans_up_projection_on_exception() -> None:
    client = FakeGDSClient(exists_results=[False, True], fail_on_pagerank=True)

    with pytest.raises(RuntimeError, match="pagerank failed"):
        run_fundamental_propagation(
            _context(),
            client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
            graph_name="unit-fundamental",
        )

    write_queries = [query for query, _ in client.write_calls]
    assert any("gds.graph.project" in query for query in write_queries)
    assert any("gds.graph.drop" in query for query in write_queries)


def _context() -> PropagationContext:
    return PropagationContext(
        cycle_id="cycle-1",
        world_state_ref="world-state-1",
        graph_generation_id=1,
        enabled_channels=["fundamental"],
        channel_multipliers={"fundamental": 2.0},
        regime_multipliers={"fundamental": 0.5},
        decay_policy={},
        regime_context={},
    )


def _status_manager(
    *,
    graph_status: str = "ready",
    graph_generation_id: int = 1,
    writer_lock_token: str | None = None,
) -> GraphStatusManager:
    return GraphStatusManager(
        InMemoryStatusStore(
            Neo4jGraphStatus(
                graph_status=graph_status,  # type: ignore[arg-type]
                graph_generation_id=graph_generation_id,
                node_count=2,
                edge_count=1,
                key_label_counts={"Entity": 2},
                checksum="abc123" if graph_status == "ready" else graph_status,
                last_verified_at=NOW if graph_status == "ready" else None,
                last_reload_at=None,
                writer_lock_token=writer_lock_token,
            ),
        ),
    )


def _path_row(
    *,
    edge_id: str,
    relationship_type: str,
    target_node_id: str,
    target_entity_id: str,
    relation_weight: float,
    evidence_confidence: float | None = 1.0,
    recency_decay: float | None = 1.0,
    propagation_channel: str | None = None,
    channel: str | None = None,
    impact_channel: str | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "source_node_id": "node-a",
        "source_entity_id": "entity-a",
        "source_labels": ["Entity"],
        "target_node_id": target_node_id,
        "target_entity_id": target_entity_id,
        "target_labels": ["Entity"],
        "edge_id": edge_id,
        "relationship_type": relationship_type,
        "relation_weight": relation_weight,
        "evidence_confidence": evidence_confidence,
        "recency_decay": recency_decay,
        "propagation_channel": propagation_channel,
        "channel": channel,
        "impact_channel": impact_channel,
        "evidence_refs": [f"fact-{edge_id}"] if evidence_refs is None else evidence_refs,
    }


def _default_path_rows() -> list[dict[str, Any]]:
    return [
        _path_row(
            edge_id="edge-1",
            relationship_type="SUPPLY_CHAIN",
            target_node_id="node-b",
            target_entity_id="entity-b",
            relation_weight=0.5,
            evidence_confidence=None,
            recency_decay=None,
        ),
        _path_row(
            edge_id="edge-2",
            relationship_type="OWNERSHIP",
            target_node_id="node-c",
            target_entity_id="entity-c",
            relation_weight=0.8,
            evidence_confidence=0.5,
            recency_decay=0.5,
        ),
    ]


def _effective_channel(row: dict[str, Any]) -> str | None:
    return (
        row.get("propagation_channel")
        or row.get("channel")
        or row.get("impact_channel")
        or (
            "fundamental"
            if row.get("relationship_type") in FUNDAMENTAL_RELATIONSHIP_TYPES
            else None
        )
    )


def _path_score(row: dict[str, Any], params: dict[str, Any]) -> float:
    return (
        _float_or_default(row.get("relation_weight"))
        * _float_or_default(row.get("evidence_confidence"))
        * float(params.get("channel_multiplier", 1.0))
        * float(params.get("regime_multiplier", 1.0))
        * _float_or_default(row.get("recency_decay"))
    )


def _float_or_default(value: Any, default: float = 1.0) -> float:
    if value is None:
        return default
    return float(value)
