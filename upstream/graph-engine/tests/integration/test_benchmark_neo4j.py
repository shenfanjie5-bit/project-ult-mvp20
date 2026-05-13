from __future__ import annotations

import os

import pytest

from benchmarks.generate_synthetic import (
    clear_graph,
    generate_synthetic_edges,
    generate_synthetic_nodes,
    load_synthetic_graph,
)
from benchmarks.run_benchmark import benchmark_gds_projection_create, benchmark_pagerank
from graph_engine.client import Neo4jClient
from graph_engine.config import load_config_from_env
from graph_engine.schema.definitions import NodeLabel, RelationshipType
from graph_engine.schema.manager import SchemaManager


pytestmark = pytest.mark.skipif(
    os.getenv("NEO4J_PASSWORD") is None,
    reason="NEO4J_PASSWORD is not set; Neo4j benchmark integration tests require a database.",
)


def test_small_neo4j_gds_benchmark_flow_runs() -> None:
    pytest.importorskip("neo4j")
    if os.getenv("NEO4J_PASSWORD") is None:
        pytest.skip("NEO4J_PASSWORD is not set; graph_engine.config requires it.")

    graph_name = "graph_engine_integration_benchmark"
    nodes = generate_synthetic_nodes(1000, [label.value for label in NodeLabel])
    edges = generate_synthetic_edges(
        nodes,
        5000,
        [relationship_type.value for relationship_type in RelationshipType],
    )

    with Neo4jClient(load_config_from_env()) as client:
        if not client.verify_connectivity():
            pytest.skip("Neo4j is not reachable with the configured environment.")

        try:
            clear_graph(client)
            schema_manager = SchemaManager(client)
            schema_manager.apply_schema()
            assert schema_manager.verify_schema() is True
            load_synthetic_graph(client, nodes, edges)

            try:
                projection_result = benchmark_gds_projection_create(
                    client,
                    graph_name,
                )
                pagerank_result = benchmark_pagerank(
                    client,
                    graph_name,
                    max_iterations=2,
                )
            except RuntimeError as exc:
                if str(exc) == "GDS plugin not available":
                    pytest.skip("GDS plugin is not available in the configured Neo4j instance.")
                raise
        finally:
            _drop_projection_if_present(client, graph_name)
            clear_graph(client)

    assert projection_result.node_count == 1000
    assert projection_result.edge_count == 5000
    assert projection_result.passed is True
    assert pagerank_result.node_count == 1000
    assert pagerank_result.edge_count == 5000
    assert pagerank_result.passed is True


def _drop_projection_if_present(client: Neo4jClient, graph_name: str) -> None:
    try:
        rows = client.execute_read(
            "CALL gds.graph.exists($graph_name) YIELD exists RETURN exists",
            {"graph_name": graph_name},
        )
        if rows and rows[0].get("exists") is True:
            client.execute_write(
                "CALL gds.graph.drop($graph_name) YIELD graphName RETURN graphName",
                {"graph_name": graph_name},
            )
    except Exception as exc:  # noqa: BLE001 - cleanup should not fail when GDS is absent.
        if str(exc) != "GDS plugin not available" and "gds." not in str(exc).lower():
            raise
