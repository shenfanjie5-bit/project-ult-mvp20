from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from benchmarks.generate_synthetic import (
    clear_graph,
    generate_synthetic_edges,
    generate_synthetic_nodes,
    load_synthetic_graph,
)
from benchmarks.report import DEFAULT_BUDGETS, check_budgets, generate_text_report
from benchmarks.run_benchmark import (
    BenchmarkResult,
    benchmark_consistency_check,
    benchmark_gds_projection_create,
    benchmark_read_api_queries,
    main,
    run_full_benchmark_suite,
    validate_benchmark_artifact,
    write_benchmark_artifacts,
)
from graph_engine.schema.definitions import NodeLabel, RelationshipType


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _lite_target_results(*, pagerank_seconds: float = 23.5) -> list[BenchmarkResult]:
    return [
        BenchmarkResult("consistency_check", 100_000, 800_000, 0.4, None, True),
        BenchmarkResult("gds_projection_create", 100_000, 800_000, 7.8, None, True),
        BenchmarkResult("pagerank", 100_000, 800_000, pagerank_seconds, None, True),
        BenchmarkResult("path_traversal", 100_000, 800_000, 1.7, None, True),
        BenchmarkResult("cold_reload", 100_000, 800_000, 74.9, None, True),
    ]


def test_generate_synthetic_nodes_returns_expected_shape() -> None:
    nodes = generate_synthetic_nodes(3, [NodeLabel.ENTITY.value, NodeLabel.SECTOR.value])

    assert len(nodes) == 3
    assert nodes[0]["node_id"] == "synthetic-node-00000000"
    assert nodes[0]["canonical_entity_id"] == "synthetic-entity-00000000"
    assert nodes[0]["label"] in {NodeLabel.ENTITY.value, NodeLabel.SECTOR.value}
    assert nodes[0]["properties"]["synthetic_benchmark"] is True


def test_generate_synthetic_nodes_distributes_labels() -> None:
    labels = [NodeLabel.ENTITY.value, NodeLabel.SECTOR.value, NodeLabel.INDUSTRY.value]

    nodes = generate_synthetic_nodes(300, labels)
    observed_labels = {node["label"] for node in nodes}

    assert observed_labels == set(labels)


def test_generate_synthetic_nodes_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="count"):
        generate_synthetic_nodes(-1, [NodeLabel.ENTITY.value])

    with pytest.raises(ValueError, match="labels"):
        generate_synthetic_nodes(1, [])


def test_generate_synthetic_edges_returns_valid_references_and_weights() -> None:
    nodes = generate_synthetic_nodes(10, [NodeLabel.ENTITY.value])
    relationship_types = [
        RelationshipType.SUPPLY_CHAIN.value,
        RelationshipType.EVENT_IMPACT.value,
    ]

    edges = generate_synthetic_edges(nodes, 50, relationship_types)
    node_labels_by_id = {node["node_id"]: node["label"] for node in nodes}

    assert len(edges) == 50
    assert all(edge["source_node_id"] in node_labels_by_id for edge in edges)
    assert all(edge["target_node_id"] in node_labels_by_id for edge in edges)
    assert all(
        edge["source_label"] == node_labels_by_id[edge["source_node_id"]]
        for edge in edges
    )
    assert all(
        edge["target_label"] == node_labels_by_id[edge["target_node_id"]]
        for edge in edges
    )
    assert all(edge["relationship_type"] in relationship_types for edge in edges)
    assert all(0.1 <= edge["weight"] <= 1.0 for edge in edges)


def test_generate_synthetic_edges_rejects_positive_count_without_nodes() -> None:
    with pytest.raises(ValueError, match="nodes"):
        generate_synthetic_edges([], 1, [RelationshipType.SUPPLY_CHAIN.value])


def test_generate_synthetic_edges_allows_empty_edges_without_relationship_types() -> None:
    nodes = generate_synthetic_nodes(2, [NodeLabel.ENTITY.value])

    assert generate_synthetic_edges(nodes, 0, []) == []


def test_load_synthetic_graph_batches_nodes_and_edges_by_type() -> None:
    client = MagicMock()
    nodes = [
        {
            "node_id": "n1",
            "canonical_entity_id": "e1",
            "label": NodeLabel.ENTITY.value,
            "properties": {},
        },
        {
            "node_id": "n2",
            "canonical_entity_id": "e2",
            "label": NodeLabel.SECTOR.value,
            "properties": {},
        },
    ]
    edges = [
        {
            "edge_id": "r1",
            "source_node_id": "n1",
            "target_node_id": "n2",
            "relationship_type": RelationshipType.SUPPLY_CHAIN.value,
            "weight": 0.5,
            "properties": {},
        }
    ]

    load_synthetic_graph(client, nodes, edges, batch_size=1)

    queries = [call.args[0] for call in client.execute_write.call_args_list]
    assert len(queries) == 3
    assert any("MERGE (n:`Entity`" in query for query in queries)
    assert any("MERGE (n:`Sector`" in query for query in queries)
    edge_queries = [query for query in queries if "[r:`SUPPLY_CHAIN`" in query]
    assert len(edge_queries) == 1
    assert "MATCH (source:`Entity`" in edge_queries[0]
    assert "MATCH (target:`Sector`" in edge_queries[0]


def test_load_synthetic_graph_rejects_invalid_batch_size() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        load_synthetic_graph(MagicMock(), [], [], batch_size=0)


def test_clear_graph_deletes_only_synthetic_benchmark_data_in_batches() -> None:
    client = MagicMock()
    client.execute_write.side_effect = [
        [{"deleted": 10_000}],
        [{"deleted": 3}],
        [{"deleted": 2}],
    ]

    clear_graph(client, batch_size=10_000)

    queries = [call.args[0] for call in client.execute_write.call_args_list]
    parameters = [call.args[1] for call in client.execute_write.call_args_list]

    assert len(queries) == 3
    assert all("synthetic_benchmark = true" in query for query in queries)
    assert all("LIMIT $batch_size" in query for query in queries)
    assert all("MATCH (n) DETACH DELETE n" not in query for query in queries)
    assert parameters == [
        {"batch_size": 10_000},
        {"batch_size": 10_000},
        {"batch_size": 10_000},
    ]


def test_clear_graph_rejects_invalid_batch_size() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        clear_graph(MagicMock(), batch_size=0)


def test_generate_text_report_includes_status_and_operation_names() -> None:
    results = [
        BenchmarkResult("pagerank", 100, 500, 1.2, None, True),
        BenchmarkResult("cold_reload", 100, 500, 120.0, None, False),
    ]

    report = generate_text_report(results, DEFAULT_BUDGETS)

    assert "PASS pagerank" in report
    assert "FAIL cold_reload" in report
    assert "Overall: FAIL" in report


def test_check_budgets_returns_true_only_when_all_budgeted_results_pass() -> None:
    passing_results = [
        BenchmarkResult("pagerank", 100, 500, 1.0, None, True),
        BenchmarkResult("consistency_check", 100, 500, 0.1, None, True),
        BenchmarkResult("cold_reload", 100, 500, 2.0, None, True),
    ]
    failing_results = [
        BenchmarkResult("pagerank", 100, 500, 61.0, None, True),
    ]

    assert check_budgets(passing_results, DEFAULT_BUDGETS) is True
    assert check_budgets(failing_results, DEFAULT_BUDGETS) is False


def test_benchmark_read_api_queries_times_status_gated_read_apis() -> None:
    client = MagicMock()

    def execute_read(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if "node_count" in query and "edge_count" in query:
            return [{"node_count": 100, "edge_count": 200}]
        return []

    client.execute_read.side_effect = execute_read

    results = benchmark_read_api_queries(
        client,
        "missing-entity",
        graph_generation_id=7,
        depth=2,
        result_limit=5,
    )

    assert [result.operation for result in results] == [
        "query_subgraph",
        "query_propagation_paths",
        "simulate_readonly_impact",
    ]
    assert all(result.node_count == 100 for result in results)
    assert all(result.edge_count == 200 for result in results)
    assert all(result.passed for result in results)
    assert client.execute_write.call_args_list == []


def test_write_benchmark_artifacts_records_json_and_text_report(tmp_path: Path) -> None:
    json_path = tmp_path / "lite_target.json"
    text_path = tmp_path / "lite_target.txt"

    write_benchmark_artifacts(
        _lite_target_results(),
        json_path,
        text_path,
        target_nodes=100_000,
        target_edge_factor=8,
        command="python -m benchmarks.run_benchmark --target-nodes 100000",
    )

    record = json.loads(json_path.read_text(encoding="utf-8"))
    assert record["target"] == {
        "node_count": 100_000,
        "edge_count": 800_000,
        "edge_factor": 8,
    }
    assert record["overall_passed"] is True
    assert record["environment"] == {
        "graph_store": "Neo4j 5.x with GDS",
        "record_scope": "milestone-0 Lite target budget gate",
    }
    assert record["notes"] == [
        "Small integration tests cover Neo4j/GDS connectivity only.",
        "This committed run record is the target-scale budget gate artifact.",
    ]
    assert validate_benchmark_artifact(json_path) is True
    assert "Overall: PASS" in text_path.read_text(encoding="utf-8")


def test_validate_benchmark_artifact_rejects_budget_failure(tmp_path: Path) -> None:
    json_path = tmp_path / "lite_target_failure.json"
    text_path = tmp_path / "lite_target_failure.txt"

    write_benchmark_artifacts(
        _lite_target_results(pagerank_seconds=61.0),
        json_path,
        text_path,
        target_nodes=100_000,
        target_edge_factor=8,
        command="python -m benchmarks.run_benchmark --target-nodes 100000",
    )

    assert validate_benchmark_artifact(json_path) is False
    assert main(["--validate-artifact", str(json_path)]) == 1


def test_validate_benchmark_artifact_rejects_non_lite_target(tmp_path: Path) -> None:
    json_path = tmp_path / "small_target.json"
    text_path = tmp_path / "small_target.txt"

    write_benchmark_artifacts(
        [
            BenchmarkResult("consistency_check", 1_000, 5_000, 0.1, None, True),
            BenchmarkResult("gds_projection_create", 1_000, 5_000, 0.1, None, True),
            BenchmarkResult("pagerank", 1_000, 5_000, 0.1, None, True),
            BenchmarkResult("path_traversal", 1_000, 5_000, 0.1, None, True),
            BenchmarkResult("cold_reload", 1_000, 5_000, 0.1, None, True),
        ],
        json_path,
        text_path,
        target_nodes=1_000,
        target_edge_factor=5,
        command="python -m benchmarks.run_benchmark --target-nodes 1000",
    )

    assert validate_benchmark_artifact(json_path) is False


def test_committed_lite_target_artifact_passes_budget_gate() -> None:
    artifact_path = _REPO_ROOT / "benchmarks/artifacts/lite_target_100k_800k.json"

    assert validate_benchmark_artifact(artifact_path) is True
    assert main(["--validate-artifact", str(artifact_path)]) == 0


def test_benchmark_gds_projection_create_reports_missing_gds_plugin() -> None:
    client = MagicMock()
    client.execute_write.side_effect = RuntimeError(
        "There is no procedure with the name gds.graph.exists registered"
    )

    with pytest.raises(RuntimeError, match="GDS plugin not available"):
        benchmark_gds_projection_create(client, "missing_gds")


def test_benchmark_gds_projection_create_does_not_hide_gds_runtime_errors() -> None:
    client = MagicMock()
    client.execute_write.side_effect = RuntimeError("gds PageRank execution failed")

    with pytest.raises(RuntimeError, match="PageRank execution failed"):
        benchmark_gds_projection_create(client, "runtime_failure")


def test_benchmark_consistency_check_normalizes_connection_failures() -> None:
    client = MagicMock()
    client.execute_read.side_effect = RuntimeError("connection refused")

    with pytest.raises(ConnectionError, match="Neo4j connection failed"):
        benchmark_consistency_check(client, 1, 1)


def test_run_full_benchmark_suite_normalizes_initial_connection_failures() -> None:
    client = MagicMock()
    client.execute_write.side_effect = RuntimeError("service unavailable")

    with pytest.raises(ConnectionError, match="Neo4j connection failed"):
        run_full_benchmark_suite(client, target_nodes=1, target_edge_factor=1)
