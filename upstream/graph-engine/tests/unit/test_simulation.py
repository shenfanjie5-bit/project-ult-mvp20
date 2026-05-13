from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

import pytest
from pydantic import ValidationError

import graph_engine.query.simulation as simulation_module
from graph_engine.models import Neo4jGraphStatus, PropagationContext, PropagationResult
from graph_engine.models import ReadonlySimulationRequest
from graph_engine.query import simulate_readonly_impact
from graph_engine.status import GraphStatusManager
from tests.fakes import InMemoryStatusStore

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)
_LIVE_MUTATION_PATTERN = re.compile(r"\b(MERGE|SET|CREATE|DELETE)\b", re.IGNORECASE)


class FakeSimulationClient:
    def __init__(
        self,
        *,
        nodes: list[dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
        live_edges: list[dict[str, Any]] | None = None,
        missing_gds: bool = False,
        raise_on_pagerank: bool = False,
    ) -> None:
        self.nodes = _nodes() if nodes is None else nodes
        self.edges = _edges() if edges is None else edges
        self.live_edges = list(self.edges if live_edges is None else live_edges)
        self.missing_gds = missing_gds
        self.raise_on_pagerank = raise_on_pagerank
        self.projections: dict[str, bool] = {}
        self.read_calls: list[tuple[str, dict[str, Any]]] = []
        self.write_calls: list[tuple[str, dict[str, Any]]] = []

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params = parameters or {}
        self.read_calls.append((query, params))
        assert _LIVE_MUTATION_PATTERN.search(query) is None
        assert "[*" not in query
        assert "collect(path)" not in query
        if self.missing_gds and "gds." in query:
            raise RuntimeError("There is no procedure with name `gds.graph.exists` registered")
        if "RETURN node_key," in query:
            return self._seed_rows(params)
        if "RETURN relationship_key," in query:
            return self._frontier_rows(params)
        if "gds.graph.exists" in query:
            return [{"exists": self.projections.get(str(params.get("graph_name")), False)}]
        if "gds.pageRank.stream" in query:
            if self.raise_on_pagerank:
                raise RuntimeError("pagerank failed")
            return self._pagerank_rows(str(params.get("graph_name") or ""))
        if "MATCH (source)-[relationship]->(target)" in query and "path_score" in query:
            return self._path_rows(query, params)
        return []

    def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params = parameters or {}
        self.write_calls.append((query, params))
        if self.missing_gds and "gds." in query:
            raise RuntimeError("There is no procedure with name `gds.graph.project` registered")
        allowed_gds_write = "gds.graph.project" in query or "gds.graph.drop" in query
        assert allowed_gds_write
        assert _LIVE_MUTATION_PATTERN.search(query) is None

        graph_name = str(params.get("graph_name") or "")
        if "gds.graph.project" in query:
            relationship_count = len(params.get("edge_ids", []))
            if relationship_count:
                self.projections[graph_name] = True
            return [
                {
                    "graphName": graph_name,
                    "nodeCount": len(params.get("node_ids", [])),
                    "relationshipCount": relationship_count,
                }
            ]
        self.projections[graph_name] = False
        return [{"graphName": graph_name}]

    def _pagerank_rows(self, graph_name: str) -> list[dict[str, Any]]:
        channel = _channel_from_graph_name(graph_name)
        rows = [
            edge
            for edge in self.live_edges
            if channel is None or channel in _edge_channels(edge)
        ]
        return [
            {
                "node_id": edge["target_node_id"],
                "canonical_entity_id": f"{edge['target_node_id']}-entity",
                "labels": ["Entity"],
                "stable_node_id": edge["target_node_id"],
                "score": edge.get("weight", 1.0),
            }
            for edge in rows
        ]

    def _seed_rows(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        seed_entities = set(params.get("seed_entities", []))
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
        return rows[: int(params.get("per_depth_limit", len(rows)))]

    def _frontier_rows(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        frontier = set(params.get("frontier_node_keys", []))
        visited_relationships = set(params.get("visited_relationship_keys", []))
        nodes_by_id = {_node_key(node): node for node in self.nodes}
        rows: list[dict[str, Any]] = []
        for edge in self.edges:
            edge_key = str(edge["edge_id"])
            if edge_key in visited_relationships:
                continue
            source_key = str(edge["source_node_id"])
            target_key = str(edge["target_node_id"])
            if source_key not in frontier and target_key not in frontier:
                continue
            source = nodes_by_id[source_key]
            target = nodes_by_id[target_key]
            neighbor = target if source_key in frontier else source
            rows.append(
                {
                    "relationship_key": edge_key,
                    "source_key": source_key,
                    "target_key": target_key,
                    "neighbor_key": _node_key(neighbor),
                    "channel": _edge_channel(edge),
                    "source": source,
                    "target": target,
                    "neighbor": neighbor,
                    "relationship": edge,
                },
            )
        rows.sort(
            key=lambda row: (
                str(row["relationship_key"]),
                str(row["source_key"]),
                str(row["target_key"]),
            ),
        )
        return rows[: int(params.get("per_depth_limit", len(rows)))]

    def _path_rows(
        self,
        query: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        edge_ids = set(params.get("edge_ids", []))
        channel = _channel_from_query(query)
        rows = [
            edge
            for edge in self.live_edges
            if edge["edge_id"] in edge_ids and (channel is None or channel in _edge_channels(edge))
        ]
        return [
            {
                "source_node_id": edge["source_node_id"],
                "source_entity_id": f"{edge['source_node_id']}-entity",
                "source_labels": ["Entity"],
                "target_node_id": edge["target_node_id"],
                "target_entity_id": f"{edge['target_node_id']}-entity",
                "target_labels": ["Entity"],
                "edge_id": edge["edge_id"],
                "relationship_type": edge["relationship_type"],
                "relation_weight": edge.get("weight", 1.0),
                "evidence_confidence": 1.0,
                "recency_decay": 1.0,
            }
            for edge in rows
        ]


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


def test_simulate_readonly_impact_returns_interim_propagation_envelope() -> None:
    client = FakeSimulationClient()

    result = simulate_readonly_impact(
        [" entity-a ", "entity-a"],
        _request(projection_name="unsafe `projection`; DROP GRAPH"),
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
    )

    assert result["status"] == "ready"
    assert result["interim"] is True
    assert result["graph_generation_id"] == 1
    assert result["seed_entities"] == ["entity-a"]
    assert result["depth"] == 2
    assert re.fullmatch(r"unsafe_projection_DROP_GRAPH_[0-9a-f]{12}", result["projection_name"])
    assert "snapshot_id" not in result
    assert "impact_snapshot_id" not in result
    assert [path["edge_id"] for path in result["activated_paths"]] == ["edge-fundamental"]
    assert result["channel_breakdown"]["merged"]["enabled_channels"] == ["fundamental"]
    assert result["subgraph"]["relationships"][0]["edge_id"] == "edge-fundamental"


@pytest.mark.parametrize("graph_status", ["rebuilding", "failed"])
def test_simulation_blocks_non_ready_before_neo4j_reads(
    graph_status: Literal["rebuilding", "failed"],
) -> None:
    client = FakeSimulationClient()

    with pytest.raises(PermissionError, match="ready"):
        simulate_readonly_impact(
            ["entity-a"],
            _request(),
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(graph_status=graph_status),
        )

    assert client.read_calls == []
    assert client.write_calls == []


def test_simulation_blocks_active_writer_lock_before_neo4j_reads() -> None:
    client = FakeSimulationClient()

    with pytest.raises(PermissionError, match="writer lock"):
        simulate_readonly_impact(
            ["entity-a"],
            _request(),
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(writer_lock_token="incremental-sync"),
        )

    assert client.read_calls == []
    assert client.write_calls == []


def test_simulation_rejects_generation_mismatch_before_neo4j_reads() -> None:
    client = FakeSimulationClient()

    with pytest.raises(ValueError, match="graph_generation_id"):
        simulate_readonly_impact(
            ["entity-a"],
            _request(graph_generation_id=1),
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(graph_generation_id=2),
        )

    assert client.read_calls == []
    assert client.write_calls == []


def test_ready_read_barrier_covers_subgraph_projection_and_propagation() -> None:
    events: list[str] = []
    client = FakeSimulationClient()

    simulate_readonly_impact(
        ["entity-a"],
        _request(),
        client=client,  # type: ignore[arg-type]
        status_manager=RecordingStatusManager(_ready_status(), events),  # type: ignore[arg-type]
    )

    assert events == ["enter", "exit"]
    assert client.read_calls
    assert client.write_calls


def test_projection_is_dropped_after_success() -> None:
    client = FakeSimulationClient()

    result = simulate_readonly_impact(
        ["entity-a"],
        _request(projection_name="unit-projection"),
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
    )

    assert re.fullmatch(r"unit-projection_[0-9a-f]{12}", result["projection_name"])
    assert client.projections[result["projection_name"]] is False
    write_queries = [query for query, _ in client.write_calls]
    assert any("gds.graph.project" in query for query in write_queries)
    assert write_queries[-1].strip().startswith("CALL gds.graph.drop")


def test_projection_is_dropped_after_propagation_error() -> None:
    client = FakeSimulationClient(raise_on_pagerank=True)

    with pytest.raises(RuntimeError, match="pagerank failed"):
        simulate_readonly_impact(
            ["entity-a"],
            _request(projection_name="unit-projection"),
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
        )

    dropped_projection_names = [
        parameters["graph_name"]
        for query, parameters in client.write_calls
        if "gds.graph.drop" in query
    ]
    assert len(dropped_projection_names) == 1
    assert re.fullmatch(r"unit-projection_[0-9a-f]{12}", dropped_projection_names[0])
    assert client.projections[dropped_projection_names[0]] is False


def test_caller_projection_name_is_prefix_and_does_not_drop_existing_exact_name() -> None:
    client = FakeSimulationClient()
    client.projections["unit-projection"] = True

    result = simulate_readonly_impact(
        ["entity-a"],
        _request(projection_name="unit-projection"),
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
    )

    assert result["projection_name"] != "unit-projection"
    assert re.fullmatch(r"unit-projection_[0-9a-f]{12}", result["projection_name"])
    assert client.projections["unit-projection"] is True
    dropped_projection_names = [
        parameters["graph_name"]
        for query, parameters in client.write_calls
        if "gds.graph.drop" in query
    ]
    assert "unit-projection" not in dropped_projection_names


def test_projection_name_collision_rejects_without_dropping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FixedUUID:
        hex = "0123456789abcdef0123456789abcdef"

    monkeypatch.setattr(simulation_module, "uuid4", lambda: FixedUUID())
    client = FakeSimulationClient()
    client.projections["unit-projection_0123456789ab"] = True

    with pytest.raises(ValueError, match="already exists"):
        simulate_readonly_impact(
            ["entity-a"],
            _request(projection_name="unit-projection"),
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
        )

    assert client.projections["unit-projection_0123456789ab"] is True
    assert not any("gds.graph.drop" in query for query, _ in client.write_calls)


def test_gds_missing_errors_are_normalized() -> None:
    client = FakeSimulationClient(missing_gds=True)

    with pytest.raises(RuntimeError, match="GDS plugin not available"):
        simulate_readonly_impact(
            ["entity-a"],
            _request(),
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
        )


def test_empty_subgraph_returns_empty_interim_without_running_propagation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeSimulationClient(nodes=[], edges=[])

    def fail_run_full(*args: Any, **kwargs: Any) -> PropagationResult:
        raise AssertionError("empty subgraphs must not run GDS propagation")

    monkeypatch.setattr(simulation_module, "run_full_propagation", fail_run_full)

    result = simulate_readonly_impact(
        ["missing-entity"],
        _request(),
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
    )

    assert result["interim"] is True
    assert result["activated_paths"] == []
    assert result["impacted_entities"] == []
    assert result["channel_breakdown"]["fundamental"]["status"] == "empty"
    assert result["channel_breakdown"]["fundamental"]["reason"] == "empty_subgraph"
    assert result["channel_breakdown"]["fundamental"]["path_count"] == 0
    assert client.write_calls == []


def test_run_full_propagation_receives_request_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeSimulationClient()
    calls: list[dict[str, Any]] = []

    def run_full(
        context: PropagationContext,
        run_client: Any,
        *,
        status_manager: Any,
        graph_name: str | None = None,
        max_iterations: int = 20,
        result_limit: int = 100,
    ) -> PropagationResult:
        calls.append(
            {
                "context": context,
                "graph_name": graph_name,
                "max_iterations": max_iterations,
                "result_limit": result_limit,
                "run_client": run_client,
                "status_manager": status_manager,
            }
        )
        return PropagationResult(
            cycle_id=context.cycle_id,
            graph_generation_id=context.graph_generation_id,
            activated_paths=[{"edge_id": "from-runner", "channel": "fundamental"}],
            impacted_entities=[{"node_id": "node-b", "channel": "fundamental"}],
            channel_breakdown={"fundamental": {"path_count": 1}},
        )

    monkeypatch.setattr(simulation_module, "run_full_propagation", run_full)

    result = simulate_readonly_impact(
        ["entity-a"],
        _request(max_iterations=3, result_limit=7, projection_name="unit-projection"),
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
    )

    assert re.fullmatch(r"unit-projection_[0-9a-f]{12}", calls[0]["graph_name"])
    assert calls[0]["max_iterations"] == 3
    assert calls[0]["result_limit"] == 7
    assert calls[0]["context"].enabled_channels == ["fundamental"]
    assert result["activated_paths"] == [{"edge_id": "from-runner", "channel": "fundamental"}]
    assert result["impacted_entities"] == [{"node_id": "node-b", "channel": "fundamental"}]


def test_activated_path_read_requires_resolvable_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeSimulationClient()

    def run_full(
        context: PropagationContext,
        run_client: Any,
        *,
        status_manager: Any,
        graph_name: str | None = None,
        max_iterations: int = 20,
        result_limit: int = 100,
    ) -> PropagationResult:
        run_client.execute_read(
            """
MATCH (source)-[relationship]->(target)
WITH source, relationship, target, 1.0 AS path_score
RETURN path_score
""",
            {"result_limit": result_limit},
        )
        return PropagationResult(
            cycle_id=context.cycle_id,
            graph_generation_id=context.graph_generation_id,
            activated_paths=[],
            impacted_entities=[],
            channel_breakdown={"fundamental": {"path_count": 0}},
        )

    monkeypatch.setattr(simulation_module, "run_full_propagation", run_full)

    with pytest.raises(PermissionError, match="resolvable channel"):
        simulate_readonly_impact(
            ["entity-a"],
            _request(),
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
        )


def test_readonly_simulation_blocks_propagation_mutation_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeSimulationClient()

    def run_full(
        context: PropagationContext,
        run_client: Any,
        *,
        status_manager: Any,
        graph_name: str | None = None,
        max_iterations: int = 20,
        result_limit: int = 100,
    ) -> PropagationResult:
        run_client.execute_write(
            "MATCH (n:Entity) SET n.readonly_escape = true RETURN n",
            {},
        )
        raise AssertionError("readonly mutation candidate should be blocked")

    monkeypatch.setattr(simulation_module, "run_full_propagation", run_full)

    with pytest.raises(PermissionError, match="GDS projection writes"):
        simulate_readonly_impact(
            ["entity-a"],
            _request(),
            client=client,  # type: ignore[arg-type]
            status_manager=_status_manager(),
        )

    assert not any("readonly_escape" in query for query, _ in client.write_calls)


def test_simulation_module_has_no_snapshot_writer_runtime_dependency() -> None:
    source = Path(simulation_module.__file__).read_text()

    assert "SnapshotWriter" not in source
    assert "snapshots.writer" not in source
    assert "write_snapshots" not in source


@pytest.mark.parametrize(
    ("request_update", "match"),
    [
        ({"channel_multipliers": {"fundamental": -1.0}}, "finite non-negative"),
        ({"channel_multipliers": {"fundamental": float("nan")}}, "finite non-negative"),
        ({"regime_multipliers": {"fundamental": float("inf")}}, "finite non-negative"),
        ({"channel_multipliers": {}}, "must include every enabled channel"),
        ({"regime_multipliers": {}}, "must include every enabled channel"),
    ],
)
def test_readonly_request_rejects_invalid_runtime_multipliers(
    request_update: dict[str, Any],
    match: str,
) -> None:
    payload = {
        "cycle_id": "cycle-1",
        "world_state_ref": "world-state-1",
        "graph_generation_id": 1,
        "depth": 2,
        "enabled_channels": ["fundamental"],
        "channel_multipliers": {"fundamental": 1.0},
        "regime_multipliers": {"fundamental": 1.0},
        "decay_policy": {"default": 1.0},
        "regime_context": {"risk_regime": "baseline"},
    }
    payload.update(request_update)

    with pytest.raises(ValidationError, match=match):
        ReadonlySimulationRequest(**payload)


def test_readonly_projection_scopes_paths_to_seed_subgraph() -> None:
    client = FakeSimulationClient(
        live_edges=[
            *_edges(),
            {
                "edge_id": "outside-edge",
                "source_node_id": "outside-a",
                "target_node_id": "outside-b",
                "relationship_type": "SUPPLY_CHAIN",
                "properties": {},
                "weight": 10.0,
            },
        ]
    )

    result = simulate_readonly_impact(
        ["entity-a"],
        _request(),
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
    )

    assert [path["edge_id"] for path in result["activated_paths"]] == ["edge-fundamental"]
    project_parameters = [
        parameters
        for query, parameters in client.write_calls
        if "gds.graph.project" in query
    ]
    assert project_parameters[0]["edge_ids"] == ["edge-fundamental"]


def test_readonly_simulation_uses_bounded_subgraph_traversal_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nodes, edges = _dense_cyclic_graph(node_count=12)
    client = FakeSimulationClient(nodes=nodes, edges=edges)

    def run_scoped(
        request: ReadonlySimulationRequest,
        *,
        projection_name: str,
        client: Any,
        ready_status: Neo4jGraphStatus,
    ) -> PropagationResult:
        return PropagationResult(
            cycle_id=request.cycle_id,
            graph_generation_id=ready_status.graph_generation_id,
            activated_paths=[],
            impacted_entities=[],
            channel_breakdown={"fundamental": {"path_count": 0}},
        )

    monkeypatch.setattr(simulation_module, "_run_scoped_propagation", run_scoped)

    result = simulate_readonly_impact(
        ["dense-entity-0"],
        _request(result_limit=5),
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
    )

    assert result["result_limit"] == 5
    assert result["truncated"] is True
    assert result["truncation"]["frontier_limit_reached"] is True
    assert result["subgraph"]["truncated"] is True
    assert len(result["subgraph"]["nodes"]) <= 5
    assert len(result["subgraph"]["relationships"]) <= 5
    assert all("[*" not in query and "collect(path)" not in query for query, _ in client.read_calls)


def test_reflexive_tagged_ownership_is_not_counted_as_fundamental() -> None:
    client = FakeSimulationClient()

    result = simulate_readonly_impact(
        ["entity-a"],
        _request(enabled_channels=["fundamental", "reflexive"]),
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
    )

    channels_by_edge_id: dict[str, set[str]] = {}
    for path in result["activated_paths"]:
        channels_by_edge_id.setdefault(str(path["edge_id"]), set()).add(str(path["channel"]))

    assert channels_by_edge_id["edge-fundamental"] == {"fundamental"}
    assert channels_by_edge_id["edge-reflexive"] == {"reflexive"}


def test_northbound_hold_participates_in_event_and_reflexive_simulation() -> None:
    client = FakeSimulationClient()

    result = simulate_readonly_impact(
        ["entity-a"],
        _request(enabled_channels=["event", "reflexive"]),
        client=client,  # type: ignore[arg-type]
        status_manager=_status_manager(),
    )

    channels_by_edge_id: dict[str, set[str]] = {}
    for path in result["activated_paths"]:
        channels_by_edge_id.setdefault(str(path["edge_id"]), set()).add(str(path["channel"]))

    assert channels_by_edge_id["edge-northbound"] == {"event", "reflexive"}


def test_examples_do_not_import_business_modules() -> None:
    examples_dir = Path(__file__).resolve().parents[2] / "examples"
    for filename in ("consumer_main_core.py", "consumer_stream_layer.py"):
        path = examples_dir / filename
        if not path.exists():
            continue
        source = path.read_text()
        assert "import main_core" not in source
        assert "import stream_layer" not in source


def _nodes() -> list[dict[str, Any]]:
    return [
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
            "properties": {"name": "Beta"},
        },
        {
            "node_id": "node-c",
            "canonical_entity_id": "entity-c",
            "labels": ["Entity"],
            "properties": {"name": "Gamma"},
        },
    ]


def _edges() -> list[dict[str, Any]]:
    return [
        {
            "edge_id": "edge-fundamental",
            "source_node_id": "node-a",
            "target_node_id": "node-b",
            "relationship_type": "SUPPLY_CHAIN",
            "properties": {},
            "weight": 2.0,
        },
        {
            "edge_id": "edge-reflexive",
            "source_node_id": "node-a",
            "target_node_id": "node-c",
            "relationship_type": "OWNERSHIP",
            "properties": {"propagation_channel": "reflexive"},
            "weight": 3.0,
        },
        {
            "edge_id": "edge-northbound",
            "source_node_id": "node-a",
            "target_node_id": "node-b",
            "relationship_type": "NORTHBOUND_HOLD",
            "properties": {},
            "weight": 4.0,
        },
    ]


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


def _request(
    *,
    graph_generation_id: int = 1,
    enabled_channels: list[Literal["fundamental", "event", "reflexive"]] | None = None,
    max_iterations: int = 20,
    projection_name: str | None = None,
    result_limit: int = 100,
) -> ReadonlySimulationRequest:
    channels = ["fundamental"] if enabled_channels is None else enabled_channels
    return ReadonlySimulationRequest(
        cycle_id="cycle-1",
        world_state_ref="world-state-1",
        graph_generation_id=graph_generation_id,
        depth=2,
        enabled_channels=channels,
        channel_multipliers={channel: 1.0 for channel in channels},
        regime_multipliers={channel: 1.0 for channel in channels},
        decay_policy={"default": 1.0},
        regime_context={"risk_regime": "baseline"},
        max_iterations=max_iterations,
        projection_name=projection_name,
        result_limit=result_limit,
    )


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


def _node_key(node: dict[str, Any]) -> str:
    return str(node["node_id"])


def _edge_channel(edge: dict[str, Any]) -> str:
    channels = _edge_channels(edge)
    return channels[0] if channels else "fundamental"


def _edge_channels(edge: dict[str, Any]) -> tuple[str, ...]:
    properties = edge.get("properties", {})
    if properties.get("propagation_channel") is not None:
        return (str(properties["propagation_channel"]),)
    if edge["relationship_type"] == "EVENT_IMPACT":
        return ("event",)
    if edge["relationship_type"] == "CO_HOLDING":
        return ("reflexive",)
    if edge["relationship_type"] == "NORTHBOUND_HOLD":
        return ("event", "reflexive")
    return ("fundamental",)


def _channel_from_query(query: str) -> str | None:
    for channel in ("fundamental", "event", "reflexive"):
        if f'= "{channel}"' in query:
            return channel
    return None


def _channel_from_graph_name(graph_name: str) -> str | None:
    for channel in ("fundamental", "event", "reflexive"):
        if graph_name.endswith(f"-{channel}"):
            return channel
    return None
