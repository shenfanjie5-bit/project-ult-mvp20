from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from graph_engine.models import Neo4jGraphStatus, PropagationContext
from graph_engine.propagation import run_reflexive_propagation
from graph_engine.status import GraphStatusManager
from tests.fakes import InMemoryStatusStore

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)


class FakeReflexiveGDSClient:
    def __init__(
        self,
        *,
        exists_results: list[bool] | None = None,
        fail_on_pagerank: bool = False,
        path_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.exists_results = exists_results or [False, True]
        self.fail_on_pagerank = fail_on_pagerank
        self.path_rows = path_rows or []
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
                    "node_id": "node-c",
                    "canonical_entity_id": "entity-c",
                    "labels": ["Entity"],
                    "stable_node_id": "node-c",
                    "score": 0.8,
                },
                {
                    "node_id": "node-b",
                    "canonical_entity_id": "entity-b",
                    "labels": ["Entity"],
                    "stable_node_id": "node-b",
                    "score": 0.4,
                },
            ]
        if "MATCH (source)-[relationship]->(target)" in query:
            rows = self._reflexive_rows()
            rows.sort(
                key=lambda row: (
                    -_path_score(row, params),
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
        self.write_calls.append((query, parameters or {}))
        if "gds.graph.project" in query:
            return [
                {
                    "graphName": (parameters or {}).get("graph_name"),
                    "nodeCount": 2 if self._reflexive_rows() else 0,
                    "relationshipCount": len(self._reflexive_rows()),
                }
            ]
        return []

    def _reflexive_rows(self) -> list[dict[str, Any]]:
        return [
            row
            for row in self.path_rows
            if _effective_channel(row) == "reflexive"
        ]


def test_run_reflexive_propagation_requires_reflexive_channel_before_neo4j_reads() -> None:
    client = FakeReflexiveGDSClient()

    with pytest.raises(PermissionError, match="reflexive channel"):
        run_reflexive_propagation(
            _context(enabled_channels=["event"]),
            client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
            graph_name="unit-reflexive",
        )

    assert client.read_calls == []
    assert client.write_calls == []


@pytest.mark.parametrize("graph_status", ["rebuilding", "failed"])
def test_run_reflexive_propagation_blocks_non_ready_before_neo4j_reads(
    graph_status: str,
) -> None:
    client = FakeReflexiveGDSClient()

    with pytest.raises(PermissionError, match="ready"):
        run_reflexive_propagation(
            _context(),
            client,  # type: ignore[arg-type]
            status_manager=_status_manager(graph_status=graph_status),
            graph_name="unit-reflexive",
        )

    assert client.read_calls == []
    assert client.write_calls == []


def test_run_reflexive_propagation_blocks_generation_mismatch_before_neo4j_reads() -> None:
    client = FakeReflexiveGDSClient()

    with pytest.raises(ValueError, match="graph_generation_id"):
        run_reflexive_propagation(
            _context(),
            client,  # type: ignore[arg-type]
            status_manager=_status_manager(graph_generation_id=2),
            graph_name="unit-reflexive",
        )

    assert client.read_calls == []
    assert client.write_calls == []


def test_run_reflexive_propagation_filters_tagged_paths_and_explains_scores() -> None:
    client = FakeReflexiveGDSClient(
        exists_results=[True, True],
        path_rows=[
            _path_row(
                edge_id="edge-untagged",
                target_node_id="node-untagged",
                target_entity_id="entity-untagged",
                relation_weight=100.0,
                evidence_confidence=1.0,
                recency_decay=1.0,
            ),
            _path_row(
                edge_id="edge-mid",
                target_node_id="node-b",
                target_entity_id="entity-b",
                relation_weight=1.0,
                evidence_confidence=0.5,
                recency_decay=1.0,
                channel="reflexive",
            ),
            _path_row(
                edge_id="edge-top",
                target_node_id="node-c",
                target_entity_id="entity-c",
                relation_weight=2.0,
                evidence_confidence=1.0,
                recency_decay=1.0,
                impact_channel="reflexive",
            ),
        ],
    )

    result = run_reflexive_propagation(
        _context(),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        graph_name="unit-reflexive",
        max_iterations=8,
        result_limit=10,
    )

    write_queries = [query for query, _ in client.write_calls]
    assert "gds.graph.drop" in write_queries[0]
    assert "gds.graph.project" in write_queries[1]
    assert "gds.graph.drop" in write_queries[2]
    assert all(" SET " not in query and " DELETE " not in query for query in write_queries)
    assert client.write_calls[1][1]["graph_name"] == "unit-reflexive"
    assert "relationship.propagation_channel" in write_queries[1]
    assert 'relationship.impact_channel, CASE type(relationship)' in write_queries[1]
    assert '= "reflexive"' in write_queries[1]

    path_query = next(
        query
        for query, _ in client.read_calls
        if "MATCH (source)-[relationship]->(target)" in query
    )
    assert "coalesce(relationship.propagation_channel" in path_query
    assert 'relationship.impact_channel, CASE type(relationship)' in path_query
    assert '= "reflexive"' in path_query

    pagerank_call = next(
        (query, params)
        for query, params in client.read_calls
        if "gds.pageRank.stream" in query
    )
    assert pagerank_call[1]["max_iterations"] == 8

    assert [path["edge_id"] for path in result.activated_paths] == ["edge-top", "edge-mid"]
    assert {path["edge_id"] for path in result.activated_paths}.isdisjoint({"edge-untagged"})
    assert result.activated_paths[0]["channel"] == "reflexive"
    assert result.activated_paths[0]["evidence_refs"] == ["fact-edge-top"]
    assert result.activated_paths[0]["explanation"] == {
        "relation_weight": 2.0,
        "evidence_confidence": 1.0,
        "channel_multiplier": 2.0,
        "regime_multiplier": 0.5,
        "recency_decay": 1.0,
        "score": 2.0,
    }
    assert [entity["node_id"] for entity in result.impacted_entities] == ["node-c", "node-b"]
    assert result.impacted_entities[0]["pagerank_score"] == pytest.approx(0.8)
    assert result.channel_breakdown["reflexive"]["path_count"] == 2
    assert result.channel_breakdown["reflexive"]["impacted_entity_count"] == 2
    assert result.channel_breakdown["reflexive"]["total_path_score"] == pytest.approx(2.5)
    assert "path_selector" in result.channel_breakdown["reflexive"]


def test_run_reflexive_propagation_returns_empty_result_for_empty_projection() -> None:
    client = FakeReflexiveGDSClient(exists_results=[False, False], path_rows=[])

    result = run_reflexive_propagation(
        _context(),
        client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        graph_name="unit-reflexive",
    )

    assert result.activated_paths == []
    assert result.impacted_entities == []
    assert result.channel_breakdown["reflexive"]["path_count"] == 0
    assert result.channel_breakdown["reflexive"]["impacted_entity_count"] == 0
    assert result.channel_breakdown["reflexive"]["total_path_score"] == 0
    assert not any("gds.pageRank.stream" in query for query, _ in client.read_calls)
    assert any("gds.graph.project" in query for query, _ in client.write_calls)
    assert not any("RETURN count(relationship)" in query for query, _ in client.read_calls)


def test_run_reflexive_propagation_cleans_up_projection_on_exception() -> None:
    client = FakeReflexiveGDSClient(
        exists_results=[False, True],
        fail_on_pagerank=True,
        path_rows=[
            _path_row(
                edge_id="edge-1",
                target_node_id="node-b",
                target_entity_id="entity-b",
                relation_weight=1.0,
                evidence_confidence=1.0,
                recency_decay=1.0,
                propagation_channel="reflexive",
            ),
        ],
    )

    with pytest.raises(RuntimeError, match="pagerank failed"):
        run_reflexive_propagation(
            _context(),
            client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
            graph_name="unit-reflexive",
        )

    write_queries = [query for query, _ in client.write_calls]
    assert any("gds.graph.project" in query for query in write_queries)
    assert any("gds.graph.drop" in query for query in write_queries)


def _context(*, enabled_channels: list[str] | None = None) -> PropagationContext:
    return PropagationContext(
        cycle_id="cycle-1",
        world_state_ref="world-state-1",
        graph_generation_id=1,
        enabled_channels=enabled_channels or ["reflexive"],  # type: ignore[arg-type]
        channel_multipliers={"reflexive": 2.0},
        regime_multipliers={"reflexive": 0.5},
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
    target_node_id: str,
    target_entity_id: str,
    relation_weight: float,
    evidence_confidence: float,
    recency_decay: float,
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
        "relationship_type": "REFLEXIVE_SIGNAL",
        "relation_weight": relation_weight,
        "evidence_confidence": evidence_confidence,
        "recency_decay": recency_decay,
        "propagation_channel": propagation_channel,
        "channel": channel,
        "impact_channel": impact_channel,
        "evidence_refs": [f"fact-{edge_id}"] if evidence_refs is None else evidence_refs,
    }


def _effective_channel(row: dict[str, Any]) -> str | None:
    return row.get("propagation_channel") or row.get("channel") or row.get("impact_channel")


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
