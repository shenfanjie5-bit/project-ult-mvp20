"""Canonical Iceberg schema evolution planning and backfill helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

import duckdb
import pyarrow as pa  # type: ignore[import-untyped]
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.table import Table
from pyiceberg.types import (
    BooleanType,
    DateType,
    DecimalType,
    DoubleType,
    FloatType,
    IcebergType,
    IntegerType,
    LongType,
    StringType,
    TimestampType,
    TimestamptzType,
)

from data_platform.ddl.iceberg_tables import CANONICAL_NAMESPACE, DEFAULT_TABLE_SPECS
from data_platform.serving.canonical_writer import (
    CANONICAL_LOADED_AT_COLUMN,
    CanonicalLoadSpec,
    WriteResult,
    load_canonical_table,
)

DECLARED_CANONICAL_TABLE_IDENTIFIERS = frozenset(
    f"{spec.namespace}.{spec.name}"
    for spec in DEFAULT_TABLE_SPECS
    if spec.namespace == CANONICAL_NAMESPACE
)


@dataclass(frozen=True, slots=True)
class SchemaChange:
    """One allowed canonical schema evolution step."""

    kind: Literal["add_column", "widen_type"]
    field_name: str
    from_type: str | None
    to_type: str


@dataclass(frozen=True, slots=True)
class SchemaEvolutionPlan:
    """Stable dry-run/apply output for a canonical Iceberg table schema change."""

    table_identifier: str
    changes: list[SchemaChange]
    rejections: list[str]
    requires_backfill: bool


def plan_schema_evolution(
    table_identifier: str,
    current_schema: pa.Schema,
    target_schema: pa.Schema,
) -> SchemaEvolutionPlan:
    """Compare an Iceberg table schema to a target PyArrow schema."""

    table_identifier = _require_declared_canonical_identifier(table_identifier)
    changes: list[SchemaChange] = []
    rejections: list[str] = []
    current_fields = {field.name: field for field in current_schema}
    target_fields = {field.name: field for field in target_schema}
    current_names = list(current_schema.names)
    target_names = list(target_schema.names)
    removed_names = [name for name in current_names if name not in target_fields]
    added_names = [name for name in target_names if name not in current_fields]

    if removed_names:
        rejections.extend(
            f"drop column is not supported for {table_identifier}: {name}"
            for name in removed_names
        )
    if removed_names and added_names:
        rejections.append(
            f"rename column is not supported for {table_identifier}: "
            f"removed={', '.join(removed_names)} added={', '.join(added_names)}"
        )

    shared_target_order = [name for name in target_names if name in current_fields]
    if shared_target_order != current_names:
        rejections.append(
            f"column reorder is not supported for {table_identifier}; "
            "existing columns must keep their relative order"
        )

    if added_names:
        first_added_index = min(target_names.index(name) for name in added_names)
        if any(name in current_fields for name in target_names[first_added_index:]):
            rejections.append(
                f"add column is only supported at the end of {table_identifier}"
            )

    for name in current_names:
        if name not in target_fields:
            continue
        current_field = current_fields[name]
        target_field = target_fields[name]
        current_type = _normalize_arrow_type(current_field.type)
        target_type = _normalize_arrow_type(target_field.type)

        if current_field.nullable != target_field.nullable:
            rejections.append(
                f"nullability change is not supported for {table_identifier}.{name}: "
                f"{'nullable' if current_field.nullable else 'required'} -> "
                f"{'nullable' if target_field.nullable else 'required'}"
            )

        if current_type.equals(target_type):
            continue
        if _is_safe_type_widening(current_type, target_type):
            changes.append(
                SchemaChange(
                    kind="widen_type",
                    field_name=name,
                    from_type=_format_arrow_type(current_type),
                    to_type=_format_arrow_type(target_type),
                )
            )
            continue

        rejections.append(
            f"type change is not allowed for {table_identifier}.{name}: "
            f"{_format_arrow_type(current_type)} -> {_format_arrow_type(target_type)}"
        )

    for name in added_names:
        target_field = target_fields[name]
        if not target_field.nullable:
            rejections.append(
                f"add required column is not supported for {table_identifier}.{name}"
            )
            continue
        try:
            _pyarrow_type_to_iceberg(target_field.type)
        except TypeError as exc:
            rejections.append(f"{table_identifier}.{name}: {exc}")
            continue
        changes.append(
            SchemaChange(
                kind="add_column",
                field_name=name,
                from_type=None,
                to_type=_format_arrow_type(_normalize_arrow_type(target_field.type)),
            )
        )

    return SchemaEvolutionPlan(
        table_identifier=table_identifier,
        changes=changes,
        rejections=rejections,
        requires_backfill=any(change.kind == "add_column" for change in changes),
    )


def apply_schema_evolution(
    catalog: SqlCatalog,
    table_identifier: str,
    target_schema: pa.Schema,
    *,
    dry_run: bool = True,
) -> SchemaEvolutionPlan:
    """Plan and optionally commit allowed Iceberg schema updates."""

    table_identifier = _require_declared_canonical_identifier(table_identifier)
    table = catalog.load_table(table_identifier)
    current_schema = _table_schema_as_pyarrow(table)
    plan = plan_schema_evolution(table_identifier, current_schema, target_schema)
    if dry_run or plan.rejections or not plan.changes:
        return plan

    target_fields = {field.name: field for field in target_schema}
    update = table.update_schema()
    for change in plan.changes:
        target_field = target_fields[change.field_name]
        iceberg_type = _pyarrow_type_to_iceberg(target_field.type)
        if change.kind == "add_column":
            update.add_column(change.field_name, iceberg_type, required=False)
        elif change.kind == "widen_type":
            update.update_column(change.field_name, iceberg_type)
    update.commit()
    return plan


def run_canonical_backfill(
    catalog: SqlCatalog,
    duckdb_path: Path,
    table_identifier: str,
    select_sql: str,
    *,
    dry_run: bool = False,
) -> WriteResult | None:
    """Backfill a canonical table from an explicit DuckDB SELECT."""

    table_identifier = _require_declared_canonical_identifier(table_identifier)
    cleaned_sql = _clean_select_sql(select_sql)
    table = catalog.load_table(table_identifier)
    target_schema = _table_schema_as_pyarrow(table)
    required_columns = tuple(
        name for name in target_schema.names if name != CANONICAL_LOADED_AT_COLUMN
    )
    if not required_columns:
        msg = f"{table_identifier} has no backfillable columns"
        raise ValueError(msg)

    relation = f"canonical_backfill_{uuid4().hex}"
    spec = CanonicalLoadSpec(
        identifier=table_identifier,
        duckdb_relation=relation,
        required_columns=required_columns,
    )
    try:
        if dry_run:
            _validate_backfill_select(duckdb_path, spec, cleaned_sql)
            return None
        _create_backfill_view(duckdb_path, relation, cleaned_sql)
        return load_canonical_table(catalog, duckdb_path, spec)
    finally:
        if not dry_run:
            _drop_backfill_view(duckdb_path, relation)


def _table_schema_as_pyarrow(table: Table) -> pa.Schema:
    table_schema = table.schema
    schema = table_schema() if callable(table_schema) else table_schema
    if isinstance(schema, pa.Schema):
        return schema

    as_arrow = getattr(schema, "as_arrow", None)
    if callable(as_arrow):
        arrow_schema = as_arrow()
        if isinstance(arrow_schema, pa.Schema):
            return arrow_schema

    msg = "Iceberg table schema cannot be converted to a PyArrow schema"
    raise TypeError(msg)


def _normalize_arrow_type(data_type: pa.DataType) -> pa.DataType:
    if pa.types.is_string(data_type) or pa.types.is_large_string(data_type):
        return pa.string()
    if pa.types.is_float32(data_type):
        return pa.float32()
    if pa.types.is_float64(data_type):
        return pa.float64()
    return data_type


def _is_safe_type_widening(
    current_type: pa.DataType,
    target_type: pa.DataType,
) -> bool:
    if pa.types.is_int32(current_type) and pa.types.is_int64(target_type):
        return True
    if pa.types.is_float32(current_type) and pa.types.is_float64(target_type):
        return True
    return False


def _format_arrow_type(data_type: pa.DataType) -> str:
    if pa.types.is_int32(data_type):
        return "int32"
    if pa.types.is_int64(data_type):
        return "int64"
    if pa.types.is_float32(data_type):
        return "float32"
    if pa.types.is_float64(data_type):
        return "float64"
    if pa.types.is_string(data_type) or pa.types.is_large_string(data_type):
        return "string"
    if pa.types.is_boolean(data_type):
        return "bool"
    if pa.types.is_date32(data_type):
        return "date32"
    return str(data_type)


def _pyarrow_type_to_iceberg(data_type: pa.DataType) -> IcebergType:
    normalized_type = _normalize_arrow_type(data_type)
    if pa.types.is_string(normalized_type):
        return StringType()
    if pa.types.is_boolean(normalized_type):
        return BooleanType()
    if pa.types.is_int32(normalized_type):
        return IntegerType()
    if pa.types.is_int64(normalized_type):
        return LongType()
    if pa.types.is_float32(normalized_type):
        return FloatType()
    if pa.types.is_float64(normalized_type):
        return DoubleType()
    if pa.types.is_date32(normalized_type):
        return DateType()
    if pa.types.is_timestamp(normalized_type):
        if normalized_type.tz is None:
            return TimestampType()
        return TimestamptzType()
    if pa.types.is_decimal(normalized_type):
        return DecimalType(normalized_type.precision, normalized_type.scale)

    msg = f"unsupported PyArrow type for Iceberg schema evolution: {data_type}"
    raise TypeError(msg)


def _clean_select_sql(select_sql: str) -> str:
    cleaned_sql = select_sql.strip()
    if not cleaned_sql:
        msg = "backfill SELECT SQL must not be empty"
        raise ValueError(msg)
    if ";" in cleaned_sql:
        msg = "backfill SQL must contain exactly one SELECT statement without semicolons"
        raise ValueError(msg)

    try:
        statements = duckdb.extract_statements(cleaned_sql)
    except duckdb.Error as exc:
        msg = "backfill SQL must parse as exactly one read-only SELECT statement"
        raise ValueError(msg) from exc
    if len(statements) != 1:
        msg = "backfill SQL must contain exactly one SELECT statement"
        raise ValueError(msg)

    statement = statements[0]
    if statement.type != duckdb.StatementType.SELECT:
        msg = "backfill SQL must be a read-only SELECT statement"
        raise ValueError(msg)
    return statement.query.strip()


def _require_declared_canonical_identifier(table_identifier: str) -> str:
    normalized_identifier = table_identifier.strip()
    namespace, separator, _table_name = normalized_identifier.partition(".")
    if (
        not separator
        or namespace != CANONICAL_NAMESPACE
        or normalized_identifier not in DECLARED_CANONICAL_TABLE_IDENTIFIERS
    ):
        allowed = ", ".join(sorted(DECLARED_CANONICAL_TABLE_IDENTIFIERS))
        msg = (
            "schema evolution and backfill only support declared canonical tables; "
            f"got {table_identifier!r}. allowed={allowed}"
        )
        raise ValueError(msg)
    return normalized_identifier


def _create_backfill_view(duckdb_path: Path, relation: str, select_sql: str) -> None:
    connection = duckdb.connect(str(duckdb_path))
    try:
        connection.execute(
            f'CREATE OR REPLACE VIEW "{relation}" AS {select_sql}'
        )
    finally:
        connection.close()


def _validate_backfill_select(
    duckdb_path: Path,
    spec: CanonicalLoadSpec,
    select_sql: str,
) -> None:
    quoted_columns = ", ".join(f'"{column}"' for column in spec.required_columns)
    connection = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        connection.execute(
            f"SELECT {quoted_columns} FROM ({select_sql}) AS backfill_source LIMIT 0"
        ).fetchall()
    finally:
        connection.close()


def _drop_backfill_view(duckdb_path: Path, relation: str) -> None:
    connection = duckdb.connect(str(duckdb_path))
    try:
        connection.execute(f'DROP VIEW IF EXISTS "{relation}"')
    finally:
        connection.close()


__all__ = [
    "SchemaChange",
    "SchemaEvolutionPlan",
    "apply_schema_evolution",
    "plan_schema_evolution",
    "run_canonical_backfill",
]
