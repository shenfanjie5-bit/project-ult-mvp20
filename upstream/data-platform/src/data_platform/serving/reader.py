"""Canonical read APIs backed by DuckDB Iceberg scans."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from functools import lru_cache
import json
from pathlib import Path
import re
from threading import RLock
from typing import Any

import duckdb
import pyarrow as pa  # type: ignore[import-untyped]

from data_platform.config import get_settings
from data_platform.serving.canonical_datasets import (
    CANONICAL_DATASET_TABLE_MAPPINGS,
    CANONICAL_DATASET_TABLE_MAPPINGS_V2,
    canonical_table_identifier_for_dataset,
    canonical_table_mapping_for_dataset,
    use_canonical_v2,
)


CANONICAL_NAMESPACE = "canonical"
CANONICAL_V2_NAMESPACE = "canonical_v2"
TABLE_STOCK_BASIC = "stock_basic"
CANONICAL_MART_SNAPSHOT_SET_FILE = "_mart_snapshot_set.json"
_CANONICAL_MART_TABLES_BY_NAMESPACE = {
    CANONICAL_NAMESPACE: frozenset(
        mapping.table_name for mapping in CANONICAL_DATASET_TABLE_MAPPINGS
    ),
    CANONICAL_V2_NAMESPACE: frozenset(
        {TABLE_STOCK_BASIC}
        | {mapping.table_name for mapping in CANONICAL_DATASET_TABLE_MAPPINGS_V2}
    ),
}
CANONICAL_MART_TABLES = _CANONICAL_MART_TABLES_BY_NAMESPACE[CANONICAL_NAMESPACE]
_CANONICAL_MART_MANIFEST_KEY_BY_NAMESPACE = {
    CANONICAL_NAMESPACE: "tables",
    CANONICAL_V2_NAMESPACE: "canonical_v2_tables",
}
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CONNECTION_LOCK = RLock()


class CanonicalTableNotFound(LookupError):
    """Raised when a canonical Iceberg table cannot be read."""

    def __init__(self, table: str) -> None:
        self.table = table
        super().__init__(f"canonical table not found: {table}")


class UnsupportedFilter(ValueError):
    """Raised when a read_canonical filter is outside the supported contract."""

    def __init__(self, filter_spec: object) -> None:
        self.filter_spec = filter_spec
        super().__init__(f"unsupported canonical filter: {filter_spec!r}")


def read_canonical(
    table: str,
    columns: list[str] | None = None,
    filters: list[tuple[str, str, Any]] | None = None,
) -> pa.Table:
    """Read one canonical Iceberg table as a PyArrow table."""

    _validate_identifier(table)
    return _read_table_expression(
        table,
        _canonical_table_expression(table),
        columns=columns,
        filters=filters,
    )


def _read_table_expression(
    table: str,
    table_expression: str,
    *,
    columns: list[str] | None = None,
    filters: list[tuple[str, str, Any]] | None = None,
) -> pa.Table:
    """Read from an already-resolved DuckDB table expression."""

    select_list = _compile_select_list(columns)
    where_clause, parameters = _compile_filters(filters)
    sql = f"""
SELECT {select_list}
FROM {table_expression}
{where_clause}
"""

    with with_duckdb_connection() as connection:
        try:
            return connection.execute(sql, parameters).to_arrow_table()
        except duckdb.Error as exc:
            if _is_missing_table_error(exc, table):
                raise CanonicalTableNotFound(table) from exc
            raise


def read_iceberg_snapshot(table_identifier: str, snapshot_id: int) -> pa.Table:
    """Read one Iceberg table snapshot through DuckDB time travel."""

    validated_snapshot_id = _validate_snapshot_id(snapshot_id)
    sql = f"""
SELECT *
FROM {_iceberg_snapshot_expression(table_identifier, validated_snapshot_id)}
"""

    with with_duckdb_connection() as connection:
        return connection.execute(sql).to_arrow_table()


def read_canonical_dataset(
    dataset_id: str,
    columns: list[str] | None = None,
    filters: list[tuple[str, str, Any]] | None = None,
) -> pa.Table:
    """Read one provider-neutral canonical dataset through its mapped table."""

    mapping = canonical_table_mapping_for_dataset(dataset_id)
    if mapping.namespace == CANONICAL_NAMESPACE:
        return read_canonical(mapping.table_name, columns=columns, filters=filters)
    return _read_table_expression(
        mapping.table_identifier,
        _canonical_table_identifier_expression(mapping.table_identifier),
        columns=columns,
        filters=filters,
    )


def read_canonical_dataset_snapshot(dataset_id: str, snapshot_id: int) -> pa.Table:
    """Read one provider-neutral canonical dataset at an explicit Iceberg snapshot."""

    return read_iceberg_snapshot(
        canonical_table_identifier_for_dataset(dataset_id),
        snapshot_id,
    )


def canonical_snapshot_id(table: str) -> int:
    """Return the pinned canonical snapshot id for a physical canonical table."""

    _validate_identifier(table)
    snapshot_entry = _canonical_mart_snapshot_entry(table)
    if snapshot_entry is not None:
        return int(snapshot_entry["snapshot_id"])
    if table in CANONICAL_MART_TABLES:
        raise CanonicalTableNotFound(table)

    metadata_location = _latest_metadata_location(table)
    metadata = json.loads(metadata_location.read_text(encoding="utf-8"))
    snapshot_id = metadata.get("current-snapshot-id")
    if isinstance(snapshot_id, int):
        return snapshot_id
    raise CanonicalTableNotFound(table)


def canonical_snapshot_id_for_dataset(dataset_id: str) -> int:
    """Return the pinned snapshot id for one provider-neutral canonical dataset."""

    mapping = canonical_table_mapping_for_dataset(dataset_id)
    if mapping.namespace == CANONICAL_NAMESPACE:
        return canonical_snapshot_id(mapping.table_name)
    return _canonical_snapshot_id_for_identifier(mapping.table_identifier)


def get_canonical_stock_basic(active_only: bool = True) -> pa.Table:
    """Read stock_basic in the legacy helper shape, filtering active rows by default."""

    filters = [("is_active", "=", True)] if active_only else None
    if use_canonical_v2():
        table_identifier = f"{CANONICAL_V2_NAMESPACE}.{TABLE_STOCK_BASIC}"
        table = _read_table_expression(
            table_identifier,
            _canonical_table_identifier_expression(table_identifier),
            columns=[
                "security_id",
                "symbol",
                "display_name",
                "area",
                "industry",
                "market",
                "list_date",
                "is_active",
                "canonical_loaded_at",
            ],
            filters=filters,
        )
        return _canonical_stock_basic_v2_to_legacy_shape(table)
    return read_canonical(TABLE_STOCK_BASIC, filters=filters)


def _canonical_stock_basic_v2_to_legacy_shape(table: pa.Table) -> pa.Table:
    column_names = [
        "ts_code" if name == "security_id" else "name" if name == "display_name" else name
        for name in table.schema.names
    ]
    return table.rename_columns(column_names)


@contextmanager
def with_duckdb_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    """Yield the process-global DuckDB connection for canonical reads."""

    connection = _duckdb_connection()
    with _CONNECTION_LOCK:
        yield connection


@lru_cache(maxsize=1)
def _duckdb_connection() -> duckdb.DuckDBPyConnection:
    settings = get_settings()
    connection = duckdb.connect(str(settings.duckdb_path))
    _load_iceberg_extension(connection)
    return connection


def _load_iceberg_extension(connection: duckdb.DuckDBPyConnection) -> None:
    try:
        connection.execute("LOAD iceberg")
    except duckdb.Error:
        connection.execute("INSTALL iceberg")
        connection.execute("LOAD iceberg")


def _compile_select_list(columns: list[str] | None) -> str:
    if columns is None:
        return "*"
    if not columns:
        msg = "columns must not be empty"
        raise ValueError(msg)
    return ", ".join(_quote_identifier(column) for column in columns)


def _compile_filters(
    filters: list[tuple[str, str, Any]] | None,
) -> tuple[str, list[Any]]:
    if not filters:
        return "", []

    clauses: list[str] = []
    parameters: list[Any] = []
    for filter_spec in filters:
        if len(filter_spec) != 3:
            raise UnsupportedFilter(filter_spec)

        column, operator, value = filter_spec
        quoted_column = _quote_identifier(column)
        normalized_operator = operator.strip().lower()
        if normalized_operator == "=":
            clauses.append(f"{quoted_column} = ?")
            parameters.append(value)
        elif normalized_operator == "in":
            values = _filter_values(filter_spec, value)
            if values:
                placeholders = ", ".join("?" for _ in values)
                clauses.append(f"{quoted_column} IN ({placeholders})")
                parameters.extend(values)
            else:
                clauses.append("FALSE")
        else:
            raise UnsupportedFilter(filter_spec)

    return "WHERE " + " AND ".join(clauses), parameters


def _filter_values(filter_spec: object, value: object) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise UnsupportedFilter(filter_spec)
    return list(value)


def _canonical_table_expression(table: str) -> str:
    try:
        return _canonical_table_identifier_expression(f"{CANONICAL_NAMESPACE}.{table}")
    except CanonicalTableNotFound as exc:
        raise CanonicalTableNotFound(table) from exc


def _canonical_table_identifier_expression(table_identifier: str) -> str:
    parts = _validate_table_identifier(table_identifier)
    namespace = parts[0]
    table = parts[-1]
    snapshot_entry = _canonical_mart_snapshot_entry(table, namespace=namespace)
    if snapshot_entry is not None:
        metadata_location = str(snapshot_entry["metadata_location"])
        snapshot_id = int(snapshot_entry["snapshot_id"])
        return (
            f"iceberg_scan({_sql_string_literal(metadata_location)}, "
            f"snapshot_from_id = {snapshot_id})"
        )
    if _is_canonical_mart_table(table, namespace):
        raise CanonicalTableNotFound(table_identifier)

    try:
        latest_metadata_location = _latest_metadata_location_for_identifier(table_identifier)
    except FileNotFoundError as exc:
        raise CanonicalTableNotFound(table_identifier) from exc
    return f"iceberg_scan({_sql_string_literal(str(latest_metadata_location))})"


def _canonical_snapshot_id_for_identifier(table_identifier: str) -> int:
    parts = _validate_table_identifier(table_identifier)
    namespace = parts[0]
    table = parts[-1]
    snapshot_entry = _canonical_mart_snapshot_entry(table, namespace=namespace)
    if snapshot_entry is not None:
        return int(snapshot_entry["snapshot_id"])
    if _is_canonical_mart_table(table, namespace):
        raise CanonicalTableNotFound(table_identifier)

    try:
        metadata_location = _latest_metadata_location_for_identifier(table_identifier)
    except FileNotFoundError as exc:
        raise CanonicalTableNotFound(table_identifier) from exc
    metadata = json.loads(metadata_location.read_text(encoding="utf-8"))
    snapshot_id = metadata.get("current-snapshot-id")
    if isinstance(snapshot_id, int):
        return snapshot_id
    raise CanonicalTableNotFound(table_identifier)


def _iceberg_snapshot_expression(table_identifier: str, snapshot_id: int) -> str:
    metadata_location = _latest_metadata_location_for_identifier(table_identifier)
    return (
        f"iceberg_scan({_sql_string_literal(str(metadata_location))}, "
        f"snapshot_from_id = {snapshot_id})"
    )


def _canonical_table_location(table: str) -> Path:
    return _iceberg_table_location(f"{CANONICAL_NAMESPACE}.{table}")


def _latest_metadata_location(table: str) -> Path:
    metadata_dir = _canonical_table_location(table) / "metadata"
    metadata_files = sorted(metadata_dir.glob("*.metadata.json"))
    if metadata_files:
        return metadata_files[-1]
    raise CanonicalTableNotFound(table)


def _latest_metadata_location_for_identifier(table_identifier: str) -> Path:
    metadata_dir = _iceberg_table_location(table_identifier) / "metadata"
    metadata_files = sorted(metadata_dir.glob("*.metadata.json"))
    if metadata_files:
        return metadata_files[-1]
    msg = f"Iceberg table metadata not found: {table_identifier}"
    raise FileNotFoundError(msg)


def _iceberg_table_location(table_identifier: str) -> Path:
    parts = _validate_table_identifier(table_identifier)
    warehouse_path = get_settings().iceberg_warehouse_path.expanduser()
    return warehouse_path.joinpath(*parts)


def _canonical_mart_snapshot_entry(
    table: str,
    *,
    namespace: str = CANONICAL_NAMESPACE,
) -> dict[str, str | int] | None:
    manifest_path = _canonical_mart_snapshot_manifest_path(namespace)
    if not manifest_path.exists():
        return None

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_key = _CANONICAL_MART_MANIFEST_KEY_BY_NAMESPACE.get(namespace)
    if manifest_key is None:
        return None
    tables = payload.get(manifest_key, {})
    if not isinstance(tables, dict):
        return None
    entry = tables.get(table)
    if not isinstance(entry, dict):
        return None
    metadata_location = entry.get("metadata_location")
    snapshot_id = entry.get("snapshot_id")
    if isinstance(metadata_location, str) and isinstance(snapshot_id, (int, str)):
        return {"metadata_location": metadata_location, "snapshot_id": snapshot_id}
    return None


def _canonical_mart_snapshot_manifest_path(
    namespace: str = CANONICAL_NAMESPACE,
) -> Path:
    _validate_identifier(namespace)
    warehouse_path = get_settings().iceberg_warehouse_path.expanduser()
    return warehouse_path / namespace / CANONICAL_MART_SNAPSHOT_SET_FILE


def _is_canonical_mart_table(table: str, namespace: str) -> bool:
    return table in _CANONICAL_MART_TABLES_BY_NAMESPACE.get(namespace, frozenset())


def _quote_identifier(identifier: str) -> str:
    _validate_identifier(identifier)
    return f'"{identifier}"'


def _validate_identifier(identifier: str) -> None:
    if _IDENTIFIER_PATTERN.fullmatch(identifier):
        return
    msg = f"invalid SQL identifier: {identifier!r}"
    raise ValueError(msg)


def _validate_table_identifier(table_identifier: str) -> tuple[str, ...]:
    if not isinstance(table_identifier, str):
        msg = f"table_identifier must be a string: {table_identifier!r}"
        raise TypeError(msg)
    if table_identifier != table_identifier.strip():
        msg = f"table_identifier must not include surrounding whitespace: {table_identifier!r}"
        raise ValueError(msg)
    parts = tuple(table_identifier.split("."))
    if len(parts) < 2:
        msg = f"table_identifier must include a namespace and table: {table_identifier!r}"
        raise ValueError(msg)
    for part in parts:
        _validate_identifier(part)
    return parts


def _validate_snapshot_id(snapshot_id: int) -> int:
    if isinstance(snapshot_id, bool) or not isinstance(snapshot_id, int):
        msg = f"snapshot_id must be a positive integer: {snapshot_id!r}"
        raise ValueError(msg)
    if snapshot_id < 1:
        msg = f"snapshot_id must be a positive integer: {snapshot_id!r}"
        raise ValueError(msg)
    return snapshot_id


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _is_missing_table_error(exc: duckdb.Error, table: str) -> bool:
    detail = str(exc).lower()
    if "." in table:
        expected_location = str(_iceberg_table_location(table)).lower()
    else:
        expected_location = str(_canonical_table_location(table)).lower()
    missing_markers = ("does not exist", "no such file", "not found", "cannot open")
    return (
        table.lower() in detail or expected_location in detail
    ) and any(marker in detail for marker in missing_markers)


__all__ = [
    "CanonicalTableNotFound",
    "UnsupportedFilter",
    "canonical_snapshot_id",
    "canonical_snapshot_id_for_dataset",
    "get_canonical_stock_basic",
    "read_canonical",
    "read_canonical_dataset",
    "read_canonical_dataset_snapshot",
    "read_iceberg_snapshot",
    "with_duckdb_connection",
]
