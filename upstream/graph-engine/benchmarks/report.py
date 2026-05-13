"""Human-readable benchmark reporting and budget checks."""

from __future__ import annotations

from benchmarks.run_benchmark import BenchmarkResult

DEFAULT_BUDGETS: dict[str, float] = {
    "propagation": 60.0,
    "consistency_check": 5.0,
    "cold_reload": 90.0,
    "cold_reload_hard": 300.0,
}


def generate_text_report(
    results: list[BenchmarkResult],
    budget: dict[str, float] | None = None,
) -> str:
    """Generate a readable PASS/FAIL report for benchmark results."""

    budget = budget or DEFAULT_BUDGETS
    lines = [
        "Graph Engine GDS Benchmark Report",
        "",
        "Budgets:",
        f"- propagation < {budget['propagation']:.1f}s",
        f"- consistency_check < {budget['consistency_check']:.1f}s",
        f"- cold_reload < {budget['cold_reload']:.1f}s",
        f"- cold_reload_hard < {budget['cold_reload_hard']:.1f}s",
        "",
        "Results:",
    ]

    for result in results:
        passed = _result_passes_budget(result, budget)
        status = "PASS" if passed else "FAIL"
        budget_label = _budget_label(result.operation, budget)
        memory_label = (
            "memory=n/a"
            if result.memory_mb is None
            else f"memory={result.memory_mb:.1f}MB"
        )
        lines.append(
            f"- {status} {result.operation}: "
            f"{result.duration_seconds:.3f}s, "
            f"nodes={result.node_count}, edges={result.edge_count}, "
            f"{memory_label}, {budget_label}"
        )

    lines.extend(["", f"Overall: {'PASS' if check_budgets(results, budget) else 'FAIL'}"])
    return "\n".join(lines)


def check_budgets(
    results: list[BenchmarkResult],
    budget: dict[str, float] | None = None,
) -> bool:
    """Return whether every benchmark result satisfies the configured budgets."""

    budget = budget or DEFAULT_BUDGETS
    return all(_result_passes_budget(result, budget) for result in results)


def _result_passes_budget(result: BenchmarkResult, budget: dict[str, float]) -> bool:
    if result.operation in {
        "pagerank",
        "path_traversal",
        "propagation",
        "query_subgraph",
        "query_propagation_paths",
        "simulate_readonly_impact",
    }:
        return result.passed and result.duration_seconds < budget["propagation"]
    if result.operation == "consistency_check":
        return result.passed and result.duration_seconds < budget["consistency_check"]
    if result.operation == "cold_reload":
        return (
            result.passed
            and result.duration_seconds < budget["cold_reload"]
            and result.duration_seconds < budget["cold_reload_hard"]
        )
    return result.passed


def _budget_label(operation: str, budget: dict[str, float]) -> str:
    if operation in {
        "pagerank",
        "path_traversal",
        "propagation",
        "query_subgraph",
        "query_propagation_paths",
        "simulate_readonly_impact",
    }:
        return f"budget=propagation<{budget['propagation']:.1f}s"
    if operation == "consistency_check":
        return f"budget=consistency_check<{budget['consistency_check']:.1f}s"
    if operation == "cold_reload":
        return (
            f"budget=cold_reload<{budget['cold_reload']:.1f}s "
            f"(hard<{budget['cold_reload_hard']:.1f}s)"
        )
    return "budget=n/a"
