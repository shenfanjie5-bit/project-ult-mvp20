"""Shared fixtures for manual benchmark tests."""

from __future__ import annotations

import pytest

from benchmarks.generate_synthetic import generate_synthetic_edges, generate_synthetic_nodes
from graph_engine.schema.definitions import NodeLabel, RelationshipType


@pytest.fixture
def benchmark_node_labels() -> list[str]:
    return [label.value for label in NodeLabel]


@pytest.fixture
def benchmark_relationship_types() -> list[str]:
    return [relationship_type.value for relationship_type in RelationshipType]


@pytest.fixture
def small_synthetic_graph(
    benchmark_node_labels: list[str],
    benchmark_relationship_types: list[str],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    nodes = generate_synthetic_nodes(100, benchmark_node_labels)
    edges = generate_synthetic_edges(nodes, 500, benchmark_relationship_types)
    return nodes, edges

