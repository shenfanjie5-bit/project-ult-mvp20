from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Literal

import pytest
from pydantic import ValidationError

from graph_engine.models import (
    GraphPropagationPathQueryResult,
    GraphQueryResult,
    Neo4jGraphStatus,
)
from graph_engine.query import (
    MAX_QUERY_DEPTH,
    MVP20_GRAPH_DEPTH,
    query_propagation_paths,
    query_mvp20_context_subgraph,
    query_subgraph,
    validate_mvp20_decision_targets,
)
from graph_engine.status import GraphStatusManager
from tests.fakes import InMemoryStatusStore

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)
_MUTATION_PATTERN = re.compile(r"\b(MERGE|SET|DELETE|CREATE)\b", re.IGNORECASE)


class FakeQueryClient:
    def __init__(
        self,
        *,
        nodes: list[dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
    ) -> None:
        self.nodes = _node_rows() if nodes is None else nodes
        self.edges = _edge_rows() if edges is None else edges
        self.read_calls: list[tuple[str, dict[str, Any]]] = []
        self.write_calls: list[tuple[str, dict[str, Any]]] = []
        self.expansion_row_counts: list[int] = []

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        call_parameters = parameters or {}
        self.read_calls.append((query, call_parameters))
        assert _MUTATION_PATTERN.search(query) is None
        assert "[*" not in query
        assert "collect(path)" not in query
        if "RETURN node_key," in query:
            return self._seed_rows(call_parameters)
        if "RETURN relationship_key," in query:
            return self._frontier_rows(query, call_parameters)
        return []

    def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.write_calls.append((query, parameters or {}))
        raise AssertionError("query APIs must not call execute_write")

    def _seed_rows(self, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        seed_entities = set(parameters.get("seed_entities", []))
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for node in self.nodes:
            node_key = _node_key(node)
            if node_key in seen:
                continue
            if node.get("canonical_entity_id") in seed_entities or node.get("node_id") in seed_entities:
                seen.add(node_key)
                rows.append({"node_key": node_key, "node": node})
        rows.sort(key=lambda row: str(row["node_key"]))
        return rows[: int(parameters.get("per_depth_limit", len(rows)))]

    def _frontier_rows(
        self,
        query: str,
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        frontier = set(parameters.get("frontier_node_keys", []))
        visited_relationships = set(parameters.get("visited_relationship_keys", []))
        channel_filter = parameters.get("channel_filter")
        channel_set = set(channel_filter) if isinstance(channel_filter, list) else None
        include_channel = "UNWIND channels AS channel" in query
        nodes_by_id = {_node_key(node): node for node in self.nodes}
        rows: list[dict[str, Any]] = []
        for edge in self.edges:
            edge_key = _edge_key(edge)
            if edge_key in visited_relationships:
                continue
            source_key = str(edge["source_node_id"])
            target_key = str(edge["target_node_id"])
            if source_key not in frontier and target_key not in frontier:
                continue
            source = nodes_by_id[source_key]
            target = nodes_by_id[target_key]
            neighbor = target if source_key in frontier else source
            channels: tuple[str | None, ...] = (None,)
            if include_channel:
                channels = _edge_channels(edge)
                if channel_set is not None:
                    channels = tuple(channel for channel in channels if channel in channel_set)
            if include_channel and not channels:
                continue
            for channel in channels:
                row = {
                    "relationship_key": edge_key,
                    "source_key": source_key,
                    "target_key": target_key,
                    "neighbor_key": _node_key(neighbor),
                    "channel": channel,
                    "source": source,
                    "target": target,
                    "neighbor": neighbor,
                    "relationship": edge,
                }
                rows.append(row)
        rows.sort(
            key=lambda row: (
                str(row["relationship_key"]),
                str(row["channel"]),
                str(row["source_key"]),
                str(row["target_key"]),
            ),
        )
        limited_rows = rows[: int(parameters.get("per_depth_limit", len(rows)))]
        self.expansion_row_counts.append(len(limited_rows))
        return limited_rows


class GateAwareClient(FakeQueryClient):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        assert self.events == ["enter"]
        return super().execute_read(query, parameters)


class RecordingStatusManager:
    def __init__(self, status: Neo4jGraphStatus, events: list[str]) -> None:
        self.status = status
        self.events = events

    @contextmanager
    def ready_read(self) -> Iterator[Neo4jGraphStatus]:
        self.events.append("enter")
        try:
            yield self.status
        finally:
            self.events.append("exit")


def test_graph_query_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        GraphQueryResult(
            graph_generation_id=1,
            subgraph_nodes=[],
            subgraph_edges=[],
            status="ready",
            extra_field=True,
        )


def test_graph_propagation_path_query_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        GraphPropagationPathQueryResult(
            graph_generation_id=1,
            paths=[],
            status="ready",
            extra_field=True,
        )


@pytest.mark.parametrize(
    ("seed_entities", "match"),
    [
        ([], "seed_entities"),
        (["entity-a", " "], "non-empty"),
        (["entity-a", 42], "strings"),
    ],
)
def test_query_subgraph_validates_seed_entities_before_reading(
    seed_entities: list[Any],
    match: str,
) -> None:
    client = FakeQueryClient()

    with pytest.raises(ValueError, match=match):
        query_subgraph(
            seed_entities,  # type: ignore[arg-type]
            1,
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
        )

    assert client.read_calls == []
    assert client.write_calls == []


@pytest.mark.parametrize(
    ("depth", "max_depth", "match"),
    [
        (-1, MAX_QUERY_DEPTH, "greater than or equal"),
        (MAX_QUERY_DEPTH + 1, MAX_QUERY_DEPTH, "less than or equal"),
        (True, MAX_QUERY_DEPTH, "integer"),
        (1, -1, "max_depth"),
    ],
)
def test_query_subgraph_validates_depth_before_reading(
    depth: Any,
    max_depth: Any,
    match: str,
) -> None:
    client = FakeQueryClient()

    with pytest.raises(ValueError, match=match):
        query_subgraph(
            ["entity-a"],
            depth,  # type: ignore[arg-type]
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
            max_depth=max_depth,  # type: ignore[arg-type]
        )

    assert client.read_calls == []


def test_query_subgraph_validates_result_limit_before_reading() -> None:
    client = FakeQueryClient()

    with pytest.raises(ValueError, match="result_limit"):
        query_subgraph(
            ["entity-a"],
            1,
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
            result_limit=0,
        )

    assert client.read_calls == []


@pytest.mark.parametrize("graph_status", ["rebuilding", "failed"])
def test_query_subgraph_blocks_non_ready_before_neo4j_reads(
    graph_status: Literal["rebuilding", "failed"],
) -> None:
    client = FakeQueryClient()

    with pytest.raises(PermissionError, match="ready"):
        query_subgraph(
            ["entity-a"],
            1,
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(graph_status=graph_status),
        )

    assert client.read_calls == []


def test_query_subgraph_blocks_active_writer_lock_before_neo4j_reads() -> None:
    client = FakeQueryClient()

    with pytest.raises(PermissionError, match="writer lock"):
        query_subgraph(
            ["entity-a"],
            1,
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(writer_lock_token="incremental-sync"),
        )

    assert client.read_calls == []


def test_query_subgraph_reads_inside_ready_gate_and_normalizes_result() -> None:
    events: list[str] = []
    client = GateAwareClient(events)
    status = _ready_status(graph_generation_id=42)

    result = query_subgraph(
        [" entity-b ", "entity-b", "node-a"],
        2,
        client=client,  # type: ignore[arg-type]
        status_manager=RecordingStatusManager(status, events),  # type: ignore[arg-type]
        result_limit=10,
    )

    assert events == ["enter", "exit"]
    assert result.graph_generation_id == 42
    assert result.status == "ready"
    assert result.seed_entities == ["entity-b", "node-a"]
    assert result.depth == 2
    assert result.result_limit == 10
    assert result.truncated is False
    assert [node["node_id"] for node in result.subgraph_nodes] == [
        "node-a",
        "node-b",
        "node-c",
    ]
    assert result.subgraph_nodes[1]["properties"] == {"name": "Beta", "rank": 2}
    assert [edge["edge_id"] for edge in result.subgraph_edges] == ["edge-1", "edge-2"]
    assert result.subgraph_edges[0]["weight"] == 0.7
    assert len(client.read_calls) == 3
    assert all("[*" not in query for query, _ in client.read_calls)
    assert client.read_calls[0][1] == {
        "per_depth_limit": 11,
        "seed_entities": ["entity-b", "node-a"],
    }


def test_query_subgraph_uses_generation_from_status_not_neo4j_rows() -> None:
    client = FakeQueryClient()

    result = query_subgraph(
        ["entity-a"],
        1,
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(graph_generation_id=77),
    )

    assert result.graph_generation_id == 77


@pytest.mark.parametrize("graph_status", ["rebuilding", "failed"])
def test_query_propagation_paths_blocks_non_ready_before_neo4j_reads(
    graph_status: Literal["rebuilding", "failed"],
) -> None:
    client = FakeQueryClient()

    with pytest.raises(PermissionError, match="ready"):
        query_propagation_paths(
            ["entity-a"],
            1,
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(graph_status=graph_status),
        )

    assert client.read_calls == []


def test_query_propagation_paths_blocks_active_writer_lock_before_neo4j_reads() -> None:
    client = FakeQueryClient()

    with pytest.raises(PermissionError, match="writer lock"):
        query_propagation_paths(
            ["entity-a"],
            1,
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(writer_lock_token="incremental-sync"),
        )

    assert client.read_calls == []


@pytest.mark.parametrize(
    ("channels", "match"),
    [
        ([], "channels"),
        ([""], "non-empty"),
        (["unknown"], "unknown"),
        ([1], "strings"),
    ],
)
def test_query_propagation_paths_validates_channels_before_reading(
    channels: list[Any],
    match: str,
) -> None:
    client = FakeQueryClient()

    with pytest.raises(ValueError, match=match):
        query_propagation_paths(
            ["entity-a"],
            1,
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
            channels=channels,  # type: ignore[arg-type]
        )

    assert client.read_calls == []


def test_query_propagation_paths_filters_channels_and_normalizes_paths() -> None:
    client = FakeQueryClient()

    result = query_propagation_paths(
        ["entity-a"],
        2,
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        channels=["event", "event"],
        result_limit=5,
    )

    assert result.graph_generation_id == 1
    assert result.status == "ready"
    assert result.seed_entities == ["entity-a"]
    assert result.depth == 2
    assert result.result_limit == 5
    assert result.truncated is False
    assert result.paths == [
        {
            "channel": "event",
            "edge_id": "edge-2",
            "source_node_id": "node-b",
            "target_node_id": "node-c",
            "relationship_type": "EVENT_IMPACT",
            "score": 0.2,
            "path_length": 2,
            "properties": {"kind": "news"},
        }
    ]
    query, parameters = client.read_calls[0]
    assert "MATCH (seed)" in query
    assert all("[*" not in read_query for read_query, _ in client.read_calls)
    assert any("propagation_channel" in read_query for read_query, _ in client.read_calls)
    assert parameters == {"per_depth_limit": 6, "seed_entities": ["entity-a"]}
    assert any(
        read_parameters.get("channel_filter") == ["event"]
        for _, read_parameters in client.read_calls
    )
    assert any(
        "WHERE $channel_filter IS NULL OR channel IN $channel_filter" in read_query
        for read_query, _ in client.read_calls
    )


@pytest.mark.parametrize("channels", [None, ["event", "reflexive"]])
def test_query_propagation_paths_expands_northbound_hold_multi_channel(
    channels: list[str] | None,
) -> None:
    client = FakeQueryClient(
        edges=[
            {
                "edge_id": "edge-northbound",
                "source_node_id": "node-a",
                "target_node_id": "node-b",
                "relationship_type": "NORTHBOUND_HOLD",
                "properties": {},
                "weight": 0.8,
            }
        ],
    )

    result = query_propagation_paths(
        ["entity-a"],
        1,
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        channels=channels,
        result_limit=5,
    )

    assert result.paths == [
        {
            "channel": "event",
            "edge_id": "edge-northbound",
            "source_node_id": "node-a",
            "target_node_id": "node-b",
            "relationship_type": "NORTHBOUND_HOLD",
            "score": 0.8,
            "path_length": 1,
            "properties": {},
        },
        {
            "channel": "reflexive",
            "edge_id": "edge-northbound",
            "source_node_id": "node-a",
            "target_node_id": "node-b",
            "relationship_type": "NORTHBOUND_HOLD",
            "score": 0.8,
            "path_length": 1,
            "properties": {},
        },
    ]
    assert any("UNWIND channels AS channel" in query for query, _ in client.read_calls)
    assert any('"NORTHBOUND_HOLD" THEN ["event", "reflexive"]' in query for query, _ in client.read_calls)
    if channels is not None:
        assert any(
            read_parameters.get("channel_filter") == ["event", "reflexive"]
            for _, read_parameters in client.read_calls
        )


def test_query_propagation_paths_can_filter_northbound_hold_as_reflexive() -> None:
    client = FakeQueryClient(
        edges=[
            {
                "edge_id": "edge-northbound",
                "source_node_id": "node-a",
                "target_node_id": "node-b",
                "relationship_type": "NORTHBOUND_HOLD",
                "properties": {},
                "weight": 0.8,
            }
        ]
    )

    result = query_propagation_paths(
        ["entity-a"],
        1,
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        channels=["reflexive"],
        result_limit=5,
    )

    assert result.paths == [
        {
            "channel": "reflexive",
            "edge_id": "edge-northbound",
            "source_node_id": "node-a",
            "target_node_id": "node-b",
            "relationship_type": "NORTHBOUND_HOLD",
            "score": 0.8,
            "path_length": 1,
            "properties": {},
        }
    ]
    assert any('"NORTHBOUND_HOLD"' in query for query, _ in client.read_calls)


def test_query_propagation_paths_can_filter_co_holding_as_reflexive() -> None:
    client = FakeQueryClient(
        edges=[
            {
                "edge_id": "edge-co-holding",
                "source_node_id": "node-a",
                "target_node_id": "node-b",
                "relationship_type": "CO_HOLDING",
                "properties": {},
                "weight": 0.8,
            }
        ]
    )

    result = query_propagation_paths(
        ["entity-a"],
        1,
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        channels=["reflexive"],
        result_limit=5,
    )

    assert result.paths == [
        {
            "channel": "reflexive",
            "edge_id": "edge-co-holding",
            "source_node_id": "node-a",
            "target_node_id": "node-b",
            "relationship_type": "CO_HOLDING",
            "score": 0.8,
            "path_length": 1,
            "properties": {},
        }
    ]
    assert any(
        '"CO_HOLDING" THEN ["reflexive"]' in query
        for query, _ in client.read_calls
    )
    assert any(
        read_parameters.get("channel_filter") == ["reflexive"]
        for _, read_parameters in client.read_calls
    )


def test_query_propagation_paths_depth_zero_returns_empty_path_summary() -> None:
    client = FakeQueryClient()

    result = query_propagation_paths(
        ["entity-a"],
        0,
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
    )

    assert result.paths == []
    assert result.truncated is False
    assert result.truncation["path_count"] == 0
    assert client.read_calls == []


def test_query_subgraph_caps_dense_cyclic_frontiers_and_reports_truncation() -> None:
    nodes, edges = _dense_cyclic_graph(node_count=12)
    client = FakeQueryClient(nodes=nodes, edges=edges)

    result = query_subgraph(
        ["dense-entity-0"],
        4,
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        result_limit=5,
    )

    assert result.truncated is True
    assert result.truncation["frontier_limit_reached"] is True
    assert 1 in result.truncation["truncated_depths"]
    assert len(result.subgraph_nodes) <= 5
    assert len(result.subgraph_edges) <= 5
    returned_node_ids = {node["node_id"] for node in result.subgraph_nodes}
    assert all(
        edge["source_node_id"] in returned_node_ids and edge["target_node_id"] in returned_node_ids
        for edge in result.subgraph_edges
    )
    assert max(client.expansion_row_counts) <= 6
    assert all("[*" not in query and "collect(path)" not in query for query, _ in client.read_calls)


def test_query_propagation_paths_caps_dense_cyclic_frontiers() -> None:
    nodes, edges = _dense_cyclic_graph(node_count=12)
    client = FakeQueryClient(nodes=nodes, edges=edges)

    result = query_propagation_paths(
        ["dense-entity-0"],
        4,
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        result_limit=3,
    )

    assert len(result.paths) <= 3
    assert result.truncated is True
    assert result.truncation["frontier_limit_reached"] is True
    assert max(client.expansion_row_counts) <= 4
    assert all("[*" not in query and "collect(path)" not in query for query, _ in client.read_calls)


def test_query_apis_do_not_call_execute_write() -> None:
    client = FakeQueryClient()

    query_subgraph(
        ["entity-a"],
        1,
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
    )
    query_propagation_paths(
        ["entity-a"],
        1,
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
    )

    assert client.write_calls == []


def test_validate_mvp20_decision_targets_requires_exact_unique_universe() -> None:
    assert validate_mvp20_decision_targets(_mvp20_targets()) == tuple(_mvp20_targets())

    with pytest.raises(ValueError, match="exactly 20"):
        validate_mvp20_decision_targets(_mvp20_targets()[:-1])
    with pytest.raises(ValueError, match="unique"):
        validate_mvp20_decision_targets([*_mvp20_targets()[:-1], "entity-a"])


def test_query_mvp20_context_subgraph_locks_depth_two_and_marks_context_only() -> None:
    client = FakeQueryClient()

    result = query_mvp20_context_subgraph(
        ["entity-a"],
        decision_target_entities=_mvp20_targets(),
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
        result_limit=10,
    )

    roles = {
        node["canonical_entity_id"]: node["entity_role"]
        for node in result.subgraph_nodes
    }
    assert result.depth == MVP20_GRAPH_DEPTH
    assert result.result_limit == 10
    assert roles == {
        "entity-a": "decision_target",
        "entity-b": "decision_target",
        "entity-c": "context_only",
    }
    assert all(
        node["metadata"]["mvp20_entity_role"] == node["entity_role"]
        for node in result.subgraph_nodes
    )
    assert {
        edge["target_entity_role"] for edge in result.subgraph_edges
    } == {"decision_target", "context_only"}
    assert client.write_calls == []
    assert all("run_full_propagation" not in query for query, _ in client.read_calls)


def test_query_mvp20_context_subgraph_validates_targets_before_reading() -> None:
    client = FakeQueryClient()

    with pytest.raises(ValueError, match="exactly 20"):
        query_mvp20_context_subgraph(
            ["entity-a"],
            decision_target_entities=_mvp20_targets()[:-1],
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
        )

    assert client.read_calls == []
    assert client.write_calls == []


def _node_rows() -> list[dict[str, Any]]:
    return [
        {
            "node_id": "node-b",
            "canonical_entity_id": "entity-b",
            "labels": ["Entity"],
            "properties": {
                "canonical_entity_id": "entity-b",
                "node_id": "node-b",
                "properties_json": '{"name": "Beta"}',
                "rank": 2,
            },
        },
        {
            "node_id": "node-a",
            "canonical_entity_id": "entity-a",
            "labels": ["Entity"],
            "properties": {"name": "Alpha"},
        },
        {
            "node_id": "node-b",
            "canonical_entity_id": "entity-b",
            "labels": ["Entity"],
            "properties": {
                "canonical_entity_id": "entity-b",
                "node_id": "node-b",
                "properties_json": '{"name": "Beta"}',
                "rank": 2,
            },
        },
        {
            "node_id": "node-c",
            "canonical_entity_id": "entity-c",
            "labels": ["Entity"],
            "properties": {"name": "Gamma"},
        },
    ]


def _edge_rows() -> list[dict[str, Any]]:
    return [
        {
            "edge_id": "edge-2",
            "source_node_id": "node-b",
            "target_node_id": "node-c",
            "relationship_type": "EVENT_IMPACT",
            "properties": {"properties_json": '{"kind": "news"}', "weight": 0.2},
        },
        {
            "edge_id": "edge-1",
            "source_node_id": "node-a",
            "target_node_id": "node-b",
            "relationship_type": "SUPPLY_CHAIN",
            "properties": {"properties_json": '{"kind": "supply"}'},
            "weight": 0.7,
        },
        {
            "edge_id": "edge-1",
            "source_node_id": "node-a",
            "target_node_id": "node-b",
            "relationship_type": "SUPPLY_CHAIN",
            "properties": {"properties_json": '{"kind": "supply"}'},
            "weight": 0.7,
        },
    ]


def _path_rows(channels: list[str] | None) -> list[dict[str, Any]]:
    paths = [
        {
            "channel": "event",
            "edge_id": "edge-2",
            "source_node_id": "node-b",
            "target_node_id": "node-c",
            "relationship_type": "EVENT_IMPACT",
            "score": 0.2,
            "path_length": 2,
            "properties": {"properties_json": '{"kind": "news"}'},
        },
        {
            "channel": "fundamental",
            "edge_id": "edge-1",
            "source_node_id": "node-a",
            "target_node_id": "node-b",
            "relationship_type": "SUPPLY_CHAIN",
            "score": 0.7,
            "path_length": 1,
            "properties": {"properties_json": '{"kind": "supply"}'},
        },
        {
            "channel": "fundamental",
            "edge_id": "edge-1",
            "source_node_id": "node-a",
            "target_node_id": "node-b",
            "relationship_type": "SUPPLY_CHAIN",
            "score": 0.7,
            "path_length": 1,
            "properties": {"properties_json": '{"kind": "supply"}'},
        },
    ]
    if channels is None:
        return paths
    return [path for path in paths if path["channel"] in channels]


def _dense_cyclic_graph(node_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = [
        {
            "node_id": f"dense-node-{index}",
            "canonical_entity_id": f"dense-entity-{index}",
            "labels": ["Entity"],
            "properties": {"index": index},
        }
        for index in range(node_count)
    ]
    edges: list[dict[str, Any]] = []
    for index in range(1, node_count):
        edges.append(
            {
                "edge_id": f"dense-star-{index:02d}",
                "source_node_id": "dense-node-0",
                "target_node_id": f"dense-node-{index}",
                "relationship_type": "SUPPLY_CHAIN",
                "properties": {},
                "weight": 1.0,
            },
        )
    for index in range(node_count):
        edges.append(
            {
                "edge_id": f"dense-cycle-{index:02d}",
                "source_node_id": f"dense-node-{index}",
                "target_node_id": f"dense-node-{(index + 1) % node_count}",
                "relationship_type": "EVENT_IMPACT",
                "properties": {"propagation_channel": "event"},
                "weight": 0.5,
            },
        )
    return nodes, edges


def _node_key(node: dict[str, Any]) -> str:
    return str(node["node_id"])


def _edge_key(edge: dict[str, Any]) -> str:
    return str(edge["edge_id"])


def _edge_channels(edge: dict[str, Any]) -> tuple[str, ...]:
    properties = edge.get("properties", {})
    for property_name in ("propagation_channel", "channel", "impact_channel"):
        if properties.get(property_name) is not None:
            return (str(properties[property_name]),)
    if edge["relationship_type"] == "EVENT_IMPACT":
        return ("event",)
    if edge["relationship_type"] == "CO_HOLDING":
        return ("reflexive",)
    if edge["relationship_type"] == "NORTHBOUND_HOLD":
        return ("event", "reflexive")
    return ("fundamental",)


def _mvp20_targets() -> list[str]:
    return [
        "entity-a",
        "entity-b",
        *[f"entity-target-{index:02d}" for index in range(18)],
    ]


def _status_manager(
    *,
    graph_status: Literal["ready", "rebuilding", "failed"] = "ready",
    graph_generation_id: int = 1,
    writer_lock_token: str | None = None,
) -> GraphStatusManager:
    return GraphStatusManager(
        InMemoryStatusStore(
            _ready_status(
                graph_status=graph_status,
                graph_generation_id=graph_generation_id,
                writer_lock_token=writer_lock_token,
            ),
        ),
    )


def _ready_status(
    *,
    graph_status: Literal["ready", "rebuilding", "failed"] = "ready",
    graph_generation_id: int = 1,
    writer_lock_token: str | None = None,
) -> Neo4jGraphStatus:
    return Neo4jGraphStatus(
        graph_status=graph_status,
        graph_generation_id=graph_generation_id,
        node_count=3,
        edge_count=2,
        key_label_counts={"Entity": 3},
        checksum="abc123" if graph_status == "ready" else graph_status,
        last_verified_at=NOW if graph_status == "ready" else None,
        last_reload_at=None,
        writer_lock_token=writer_lock_token,
    )
