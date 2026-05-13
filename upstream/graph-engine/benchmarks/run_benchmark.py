"""Manual Neo4j GDS benchmark runner for graph-engine scale budgets."""

from __future__ import annotations

import argparse
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from benchmarks.generate_synthetic import (
    clear_graph,
    generate_synthetic_edges,
    generate_synthetic_nodes,
    load_synthetic_graph,
)
from graph_engine.client import Neo4jClient
from graph_engine.config import load_config_from_env
from graph_engine.models import Neo4jGraphStatus, ReadonlySimulationRequest
from graph_engine.query import query_propagation_paths, query_subgraph, simulate_readonly_impact
from graph_engine.schema.definitions import NodeLabel, RelationshipType
from graph_engine.schema.manager import SchemaManager
from graph_engine.status import GraphStatusManager

_DEFAULT_GRAPH_NAME = "graph_engine_benchmark"
_LITE_TARGET_NODE_COUNT = 100_000
_LITE_TARGET_MIN_EDGE_COUNT = 500_000
_LITE_TARGET_MAX_EDGE_COUNT = 1_000_000
_REQUIRED_LITE_TARGET_OPERATIONS = frozenset(
    {
        "consistency_check",
        "gds_projection_create",
        "pagerank",
        "path_traversal",
        "cold_reload",
    }
)
_CONNECTION_FAILURE_MARKERS = (
    "connection",
    "connect",
    "service unavailable",
    "failed to obtain",
    "unable to retrieve routing",
    "authentication",
)
_GDS_UNAVAILABLE_MARKERS = (
    "no procedure",
    "not found",
    "not available",
    "procedure not found",
    "procedurenotfound",
    "unknown procedure",
    "unknown function",
)


@dataclass(frozen=True)
class BenchmarkResult:
    """Standard result emitted by every benchmark operation."""

    operation: str
    node_count: int
    edge_count: int
    duration_seconds: float
    memory_mb: float | None
    passed: bool


def write_benchmark_artifacts(
    results: list[BenchmarkResult],
    json_path: Path | str,
    text_report_path: Path | str,
    *,
    target_nodes: int,
    target_edge_factor: int,
    command: str,
) -> None:
    """Persist machine-readable and human-readable benchmark run artifacts."""

    from benchmarks.report import DEFAULT_BUDGETS, generate_text_report

    record = build_benchmark_run_record(
        results,
        target_nodes=target_nodes,
        target_edge_factor=target_edge_factor,
        command=command,
    )

    json_output_path = Path(json_path)
    text_output_path = Path(text_report_path)
    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    text_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    text_output_path.write_text(
        generate_text_report(results, DEFAULT_BUDGETS) + "\n",
        encoding="utf-8",
    )


def build_benchmark_run_record(
    results: list[BenchmarkResult],
    *,
    target_nodes: int,
    target_edge_factor: int,
    command: str,
) -> dict[str, Any]:
    """Build the committed JSON shape for a Lite target benchmark run."""

    from benchmarks.report import DEFAULT_BUDGETS, check_budgets

    target_edge_count = target_nodes * target_edge_factor
    return {
        "schema_version": 1,
        "suite": "graph_engine_lite_target_budget",
        "record_type": "target_scale_budget_validation",
        "recorded_at": datetime.now(UTC).isoformat(),
        "command": command,
        "environment": {
            "graph_store": "Neo4j 5.x with GDS",
            "record_scope": "milestone-0 Lite target budget gate",
        },
        "notes": [
            "Small integration tests cover Neo4j/GDS connectivity only.",
            "This committed run record is the target-scale budget gate artifact.",
        ],
        "validation_command": (
            "python -m benchmarks.run_benchmark "
            "--validate-artifact benchmarks/artifacts/lite_target_100k_800k.json"
        ),
        "target": {
            "node_count": target_nodes,
            "edge_count": target_edge_count,
            "edge_factor": target_edge_factor,
        },
        "budget_seconds": DEFAULT_BUDGETS,
        "results": [_benchmark_result_to_dict(result) for result in results],
        "overall_passed": check_budgets(results, DEFAULT_BUDGETS),
    }


def load_benchmark_run_record(path: Path | str) -> dict[str, Any]:
    """Load a machine-readable benchmark run record from disk."""

    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("benchmark run record must be a JSON object")
    return loaded


def validate_benchmark_artifact(path: Path | str) -> bool:
    """Return whether a committed Lite target artifact satisfies the budget gate."""

    try:
        record = load_benchmark_run_record(path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    return validate_benchmark_run_record(record)


def validate_benchmark_run_record(record: dict[str, Any]) -> bool:
    """Validate a Lite target run record without opening a Neo4j connection."""

    from benchmarks.report import DEFAULT_BUDGETS, check_budgets

    if record.get("schema_version") != 1:
        return False
    if record.get("record_type") != "target_scale_budget_validation":
        return False

    target = record.get("target")
    if not isinstance(target, dict):
        return False

    try:
        target_node_count = _target_int(target, "node_count")
        target_edge_count = _target_int(target, "edge_count")
    except (TypeError, ValueError):
        return False
    if target_node_count != _LITE_TARGET_NODE_COUNT:
        return False
    if not _LITE_TARGET_MIN_EDGE_COUNT <= target_edge_count <= _LITE_TARGET_MAX_EDGE_COUNT:
        return False

    try:
        results = _benchmark_results_from_record(record)
    except (KeyError, TypeError, ValueError):
        return False

    operations = {result.operation for result in results}
    if not _REQUIRED_LITE_TARGET_OPERATIONS.issubset(operations):
        return False
    if record.get("overall_passed") is not True:
        return False
    if not _recorded_counts_match_target(results, target_node_count, target_edge_count):
        return False
    return check_budgets(results, DEFAULT_BUDGETS)


def benchmark_gds_projection_create(client: Neo4jClient, graph_name: str) -> BenchmarkResult:
    """Create a GDS named projection and return wall-clock timing."""

    try:
        _drop_gds_projection_if_exists(client, graph_name)
        start = time.perf_counter()
        rows = _execute_write(
            client,
            """
            CALL gds.graph.project($graph_name, $node_labels, $relationship_projection)
            YIELD graphName, nodeCount, relationshipCount
            RETURN graphName, nodeCount, relationshipCount
            """,
            {
                "graph_name": graph_name,
                "node_labels": [label.value for label in NodeLabel],
                "relationship_projection": _relationship_projection(),
            },
        )
        duration_seconds = time.perf_counter() - start
    except Exception as exc:
        _raise_if_connection_failure(exc)
        if _is_gds_unavailable(exc):
            raise RuntimeError("GDS plugin not available") from exc
        raise

    row = rows[0] if rows else {}
    return BenchmarkResult(
        operation="gds_projection_create",
        node_count=_int_field(row, "nodeCount"),
        edge_count=_int_field(row, "relationshipCount"),
        duration_seconds=duration_seconds,
        memory_mb=None,
        passed=True,
    )


def benchmark_pagerank(
    client: Neo4jClient,
    graph_name: str,
    max_iterations: int = 20,
) -> BenchmarkResult:
    """Run GDS PageRank against an existing named projection."""

    if max_iterations <= 0:
        raise ValueError("max_iterations must be positive")

    node_count, edge_count = _projected_graph_counts(client, graph_name)
    start = time.perf_counter()
    _execute_write(
        client,
        """
        CALL gds.pageRank.stats(
            $graph_name,
            {
                maxIterations: $max_iterations,
                relationshipWeightProperty: 'weight'
            }
        )
        YIELD ranIterations, didConverge
        RETURN ranIterations, didConverge
        """,
        {"graph_name": graph_name, "max_iterations": max_iterations},
    )
    duration_seconds = time.perf_counter() - start

    return BenchmarkResult(
        operation="pagerank",
        node_count=node_count,
        edge_count=edge_count,
        duration_seconds=duration_seconds,
        memory_mb=None,
        passed=duration_seconds < _default_budget("propagation"),
    )


def benchmark_path_traversal(
    client: Neo4jClient,
    seed_node_id: str,
    max_depth: int = 5,
) -> BenchmarkResult:
    """Run a bounded breadth-first traversal from one synthetic seed node."""

    if not seed_node_id:
        raise ValueError("seed_node_id must be non-empty")
    if max_depth <= 0:
        raise ValueError("max_depth must be positive")

    node_count, edge_count = _live_graph_counts(client)
    visited = {seed_node_id}
    frontier = {seed_node_id}

    start = time.perf_counter()
    for _depth in range(max_depth):
        if not frontier:
            break
        rows = _execute_read(
            client,
            """
            MATCH (source)
            WHERE source.node_id IN $frontier
            MATCH (source)-[]->(target)
            WHERE target.node_id IS NOT NULL
            RETURN collect(DISTINCT target.node_id) AS target_node_ids
            """,
            {"frontier": list(frontier)},
        )
        target_node_ids = set(rows[0].get("target_node_ids", [])) if rows else set()
        frontier = {node_id for node_id in target_node_ids if node_id not in visited}
        visited.update(frontier)

    duration_seconds = time.perf_counter() - start
    return BenchmarkResult(
        operation="path_traversal",
        node_count=node_count,
        edge_count=edge_count,
        duration_seconds=duration_seconds,
        memory_mb=None,
        passed=duration_seconds < _default_budget("propagation"),
    )


def benchmark_read_api_queries(
    client: Neo4jClient,
    seed_entity_id: str,
    *,
    graph_generation_id: int = 1,
    depth: int = 4,
    result_limit: int = 100,
) -> list[BenchmarkResult]:
    """Run the public bounded read APIs against one seed entity."""

    if not seed_entity_id:
        raise ValueError("seed_entity_id must be non-empty")
    if depth <= 0:
        raise ValueError("depth must be positive")
    if result_limit <= 0:
        raise ValueError("result_limit must be positive")

    node_count, edge_count = _live_graph_counts(client)
    status_manager = GraphStatusManager(
        _StaticBenchmarkStatusStore(
            Neo4jGraphStatus(
                graph_status="ready",
                graph_generation_id=graph_generation_id,
                node_count=node_count,
                edge_count=edge_count,
                key_label_counts={},
                checksum="benchmark",
                last_verified_at=datetime.now(UTC),
                last_reload_at=None,
            ),
        ),
    )
    simulation_request = ReadonlySimulationRequest(
        cycle_id="benchmark",
        world_state_ref="benchmark",
        graph_generation_id=graph_generation_id,
        depth=min(depth, 6),
        enabled_channels=["fundamental", "event", "reflexive"],
        channel_multipliers={"fundamental": 1.0, "event": 1.0, "reflexive": 1.0},
        regime_multipliers={"fundamental": 1.0, "event": 1.0, "reflexive": 1.0},
        decay_policy={"default": 1.0},
        regime_context={"benchmark": True},
        result_limit=result_limit,
        max_iterations=20,
        projection_name="graph_engine_benchmark_readonly_sim",
    )

    return [
        _time_read_api_operation(
            "query_subgraph",
            node_count,
            edge_count,
            lambda: query_subgraph(
                [seed_entity_id],
                min(depth, 4),
                client=client,
                status_manager=status_manager,
                result_limit=result_limit,
            ),
        ),
        _time_read_api_operation(
            "query_propagation_paths",
            node_count,
            edge_count,
            lambda: query_propagation_paths(
                [seed_entity_id],
                min(depth, 4),
                client=client,
                status_manager=status_manager,
                result_limit=result_limit,
            ),
        ),
        _time_read_api_operation(
            "simulate_readonly_impact",
            node_count,
            edge_count,
            lambda: simulate_readonly_impact(
                [seed_entity_id],
                simulation_request,
                client=client,
                status_manager=status_manager,
            ),
        ),
    ]


def benchmark_cold_reload_simulation(
    client: Neo4jClient,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> BenchmarkResult:
    """Measure clear, full reload, and schema rebuild timing."""

    try:
        start = time.perf_counter()
        clear_graph(client)
        load_synthetic_graph(client, nodes, edges)
        SchemaManager(client).apply_schema()
        duration_seconds = time.perf_counter() - start
    except Exception as exc:
        _raise_if_connection_failure(exc)
        raise

    return BenchmarkResult(
        operation="cold_reload",
        node_count=len(nodes),
        edge_count=len(edges),
        duration_seconds=duration_seconds,
        memory_mb=None,
        passed=duration_seconds < _default_budget("cold_reload"),
    )


def benchmark_consistency_check(
    client: Neo4jClient,
    expected_node_count: int,
    expected_edge_count: int,
) -> BenchmarkResult:
    """Measure live graph node and relationship count verification."""

    start = time.perf_counter()
    node_count, edge_count = _live_graph_counts(client)
    duration_seconds = time.perf_counter() - start
    counts_match = node_count == expected_node_count and edge_count == expected_edge_count

    return BenchmarkResult(
        operation="consistency_check",
        node_count=node_count,
        edge_count=edge_count,
        duration_seconds=duration_seconds,
        memory_mb=None,
        passed=counts_match and duration_seconds < _default_budget("consistency_check"),
    )


def run_full_benchmark_suite(
    client: Neo4jClient,
    target_nodes: int = 100_000,
    target_edge_factor: int = 8,
) -> list[BenchmarkResult]:
    """Generate, load, and benchmark the full Lite-scale synthetic graph."""

    if target_nodes <= 0:
        raise ValueError("target_nodes must be positive")
    if target_edge_factor <= 0:
        raise ValueError("target_edge_factor must be positive")

    node_labels = [label.value for label in NodeLabel]
    relationship_types = [relationship_type.value for relationship_type in RelationshipType]
    nodes = generate_synthetic_nodes(target_nodes, node_labels)
    edges = generate_synthetic_edges(nodes, target_nodes * target_edge_factor, relationship_types)

    try:
        clear_graph(client)
        SchemaManager(client).apply_schema()
        load_synthetic_graph(client, nodes, edges)
    except Exception as exc:
        _raise_if_connection_failure(exc)
        raise

    results = [
        benchmark_consistency_check(client, len(nodes), len(edges)),
        benchmark_gds_projection_create(client, _DEFAULT_GRAPH_NAME),
        benchmark_pagerank(client, _DEFAULT_GRAPH_NAME),
        benchmark_path_traversal(client, nodes[0]["node_id"]),
        *benchmark_read_api_queries(client, nodes[0]["canonical_entity_id"]),
        benchmark_cold_reload_simulation(client, nodes, edges),
    ]
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-nodes", type=int, default=100_000)
    parser.add_argument("--target-edge-factor", type=int, default=8)
    parser.add_argument(
        "--record-json",
        type=Path,
        help="Write a machine-readable benchmark run record to this JSON path.",
    )
    parser.add_argument(
        "--record-report",
        type=Path,
        help="Write the generated human-readable benchmark report to this text path.",
    )
    parser.add_argument(
        "--validate-artifact",
        type=Path,
        help="Validate a committed Lite target JSON artifact without connecting to Neo4j.",
    )
    args = parser.parse_args(argv)

    if (args.record_json is None) != (args.record_report is None):
        parser.error("--record-json and --record-report must be provided together")

    from benchmarks.report import DEFAULT_BUDGETS, check_budgets, generate_text_report

    if args.validate_artifact is not None:
        passed = validate_benchmark_artifact(args.validate_artifact)
        status = "PASS" if passed else "FAIL"
        print(f"Benchmark artifact budget gate: {status} ({args.validate_artifact})")
        return 0 if passed else 1

    with Neo4jClient(load_config_from_env()) as client:
        results = run_full_benchmark_suite(
            client,
            target_nodes=args.target_nodes,
            target_edge_factor=args.target_edge_factor,
        )

    report = generate_text_report(results, DEFAULT_BUDGETS)
    if args.record_json is not None and args.record_report is not None:
        write_benchmark_artifacts(
            results,
            args.record_json,
            args.record_report,
            target_nodes=args.target_nodes,
            target_edge_factor=args.target_edge_factor,
            command=_benchmark_command(args),
        )

    print(report)
    return 0 if check_budgets(results, DEFAULT_BUDGETS) else 1


def _benchmark_command(args: argparse.Namespace) -> str:
    parts = [
        "python -m benchmarks.run_benchmark",
        f"--target-nodes {args.target_nodes}",
        f"--target-edge-factor {args.target_edge_factor}",
    ]
    if args.record_json is not None:
        parts.append(f"--record-json {args.record_json}")
    if args.record_report is not None:
        parts.append(f"--record-report {args.record_report}")
    return " ".join(parts)


class _StaticBenchmarkStatusStore:
    def __init__(self, status: Neo4jGraphStatus) -> None:
        self.status = status

    @contextmanager
    def ready_read_lock(self) -> Iterator[None]:
        yield

    def read_current_status(self) -> Neo4jGraphStatus | None:
        return self.status

    def write_current_status(self, status: Neo4jGraphStatus) -> None:
        self.status = status

    def compare_and_write_current_status(
        self,
        *,
        expected_status: Neo4jGraphStatus | None,
        next_status: Neo4jGraphStatus,
    ) -> bool:
        if self.status != expected_status:
            return False
        self.status = next_status
        return True


def _time_read_api_operation(
    operation: str,
    node_count: int,
    edge_count: int,
    callback: Any,
) -> BenchmarkResult:
    start = time.perf_counter()
    callback()
    duration_seconds = time.perf_counter() - start
    return BenchmarkResult(
        operation=operation,
        node_count=node_count,
        edge_count=edge_count,
        duration_seconds=duration_seconds,
        memory_mb=None,
        passed=duration_seconds < _default_budget("propagation"),
    )


def _benchmark_result_to_dict(result: BenchmarkResult) -> dict[str, Any]:
    return {
        "operation": result.operation,
        "node_count": result.node_count,
        "edge_count": result.edge_count,
        "duration_seconds": result.duration_seconds,
        "memory_mb": result.memory_mb,
        "passed": result.passed,
    }


def _benchmark_results_from_record(record: dict[str, Any]) -> list[BenchmarkResult]:
    rows = record.get("results")
    if not isinstance(rows, list):
        raise ValueError("benchmark run record results must be a list")
    return [_benchmark_result_from_dict(row) for row in rows]


def _benchmark_result_from_dict(row: Any) -> BenchmarkResult:
    if not isinstance(row, dict):
        raise ValueError("benchmark result must be a JSON object")

    passed = row.get("passed")
    if not isinstance(passed, bool):
        raise ValueError("benchmark result passed field must be a boolean")

    memory_value = row.get("memory_mb")
    memory_mb = None if memory_value is None else float(memory_value)
    return BenchmarkResult(
        operation=str(row["operation"]),
        node_count=int(row["node_count"]),
        edge_count=int(row["edge_count"]),
        duration_seconds=float(row["duration_seconds"]),
        memory_mb=memory_mb,
        passed=passed,
    )


def _recorded_counts_match_target(
    results: list[BenchmarkResult],
    target_node_count: int,
    target_edge_count: int,
) -> bool:
    return all(
        result.node_count == target_node_count and result.edge_count == target_edge_count
        for result in results
        if result.operation in _REQUIRED_LITE_TARGET_OPERATIONS
    )


def _target_int(target: dict[str, Any], field_name: str) -> int:
    value = target.get(field_name)
    return value if isinstance(value, int) else int(value)


def _relationship_projection() -> dict[str, dict[str, Any]]:
    return {
        relationship_type.value: {
            "type": relationship_type.value,
            "orientation": "NATURAL",
            "properties": ["weight"],
        }
        for relationship_type in RelationshipType
    }


def _drop_gds_projection_if_exists(client: Neo4jClient, graph_name: str) -> None:
    rows = _execute_write(
        client,
        "CALL gds.graph.exists($graph_name) YIELD exists RETURN exists",
        {"graph_name": graph_name},
    )
    if rows and rows[0].get("exists") is True:
        _execute_write(
            client,
            "CALL gds.graph.drop($graph_name, false) YIELD graphName RETURN graphName",
            {"graph_name": graph_name},
        )


def _projected_graph_counts(client: Neo4jClient, graph_name: str) -> tuple[int, int]:
    rows = _execute_write(
        client,
        """
        CALL gds.graph.list($graph_name)
        YIELD nodeCount, relationshipCount
        RETURN nodeCount, relationshipCount
        """,
        {"graph_name": graph_name},
    )
    row = rows[0] if rows else {}
    return _int_field(row, "nodeCount"), _int_field(row, "relationshipCount")


def _live_graph_counts(client: Neo4jClient) -> tuple[int, int]:
    rows = _execute_read(
        client,
        """
        MATCH (n)
        WITH count(n) AS node_count
        OPTIONAL MATCH ()-[r]->()
        RETURN node_count, count(r) AS edge_count
        """,
    )
    row = rows[0] if rows else {}
    return _int_field(row, "node_count"), _int_field(row, "edge_count")


def _execute_read(
    client: Neo4jClient,
    query: str,
    parameters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    try:
        return client.execute_read(query, parameters)
    except Exception as exc:
        _raise_if_connection_failure(exc)
        raise


def _execute_write(
    client: Neo4jClient,
    query: str,
    parameters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    try:
        return client.execute_write(query, parameters)
    except Exception as exc:
        _raise_if_connection_failure(exc)
        raise


def _raise_if_connection_failure(exc: Exception) -> None:
    if isinstance(exc, ConnectionError):
        raise exc

    message = str(exc).lower()
    if any(marker in message for marker in _CONNECTION_FAILURE_MARKERS):
        raise ConnectionError(f"Neo4j connection failed: {exc}") from exc


def _is_gds_unavailable(exc: Exception) -> bool:
    message = str(exc).lower()
    return "gds" in message and any(marker in message for marker in _GDS_UNAVAILABLE_MARKERS)


def _int_field(row: dict[str, Any], field_name: str) -> int:
    value = row.get(field_name, 0)
    return value if isinstance(value, int) else int(value)


def _default_budget(name: str) -> float:
    from benchmarks.report import DEFAULT_BUDGETS

    return DEFAULT_BUDGETS[name]


if __name__ == "__main__":
    raise SystemExit(main())
