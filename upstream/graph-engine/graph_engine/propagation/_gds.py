"""Shared GDS projection helpers for propagation runners."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from graph_engine.client import Neo4jClient


@dataclass(frozen=True, slots=True)
class GDSAvailability:
    """Observed availability of required Neo4j GDS procedures."""

    gds_version: str
    graph_exists_procedure_available: bool


def probe_gds_availability(client: Neo4jClient) -> GDSAvailability:
    """Verify required GDS procedures and return evidence runner facts."""

    version_rows = execute_gds_read(
        client,
        "CALL gds.version() YIELD gdsVersion RETURN gdsVersion",
        {},
    )
    gds_version = _required_string_field(version_rows, "gdsVersion", "gds.version")

    exists_rows = execute_gds_read(
        client,
        "CALL gds.graph.exists($graph_name) YIELD exists RETURN exists",
        {"graph_name": "__graph_engine_gds_probe__"},
    )
    _required_bool_field(exists_rows, "exists", "gds.graph.exists")

    return GDSAvailability(
        gds_version=gds_version,
        graph_exists_procedure_available=True,
    )


def drop_projection_if_exists(client: Neo4jClient, graph_name: str) -> None:
    rows = execute_gds_read(
        client,
        "CALL gds.graph.exists($graph_name) YIELD exists RETURN exists",
        {"graph_name": graph_name},
    )
    if rows and rows[0].get("exists") is True:
        execute_gds_write(
            client,
            "CALL gds.graph.drop($graph_name) YIELD graphName RETURN graphName",
            {"graph_name": graph_name},
        )


def execute_gds_read(
    client: Neo4jClient,
    query: str,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        return client.execute_read(query, parameters)
    except Exception as exc:
        if _is_missing_gds_error(exc):
            raise RuntimeError("GDS plugin not available") from exc
        raise


def execute_gds_write(
    client: Neo4jClient,
    query: str,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        return client.execute_write(query, parameters)
    except Exception as exc:
        if _is_missing_gds_error(exc):
            raise RuntimeError("GDS plugin not available") from exc
        raise


def _is_missing_gds_error(exc: Exception) -> bool:
    message = str(exc).lower()
    missing_markers = (
        "no procedure",
        "no function",
        "not registered",
        "unknown procedure",
        "unknown function",
        "procedure not found",
        "function not found",
    )
    return "gds." in message and any(marker in message for marker in missing_markers)


def _required_string_field(rows: list[dict[str, Any]], field: str, probe: str) -> str:
    value = rows[0].get(field) if rows else None
    if isinstance(value, str) and value:
        return value
    raise RuntimeError(f"GDS probe {probe} returned no {field}")


def _required_bool_field(rows: list[dict[str, Any]], field: str, probe: str) -> bool:
    value = rows[0].get(field) if rows else None
    if isinstance(value, bool):
        return value
    raise RuntimeError(f"GDS probe {probe} returned no {field}")
