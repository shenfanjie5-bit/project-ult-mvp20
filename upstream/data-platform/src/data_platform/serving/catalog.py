"""PyIceberg SQL catalog wiring for Canonical/Formal/Analytical zones."""

from __future__ import annotations

from collections.abc import Iterable
import os
from pathlib import Path
from typing import Final

from pydantic import ValidationError
from pyiceberg.catalog import Catalog
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.typedef import Identifier
from sqlalchemy.exc import SQLAlchemyError

from data_platform.config import Settings, get_settings


DEFAULT_NAMESPACES: Final[tuple[str, ...]] = (
    "canonical",
    "formal",
    "analytical",
    "canonical_v2",
    "canonical_lineage",
)
DEFAULT_NAMESPACE_IDENTIFIERS: Final[tuple[Identifier, ...]] = tuple(
    (namespace,) for namespace in DEFAULT_NAMESPACES
)
CATALOG_TABLE_PREFIX: Final[str] = "iceberg_"
RAW_NAMESPACE: Final[str] = "raw"


class CatalogConnectError(RuntimeError):
    """Raised when the configured Iceberg SQL catalog cannot be reached."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"failed to connect to Iceberg SQL catalog: {detail}")


class DataPlatformSqlCatalog(SqlCatalog):
    """Project catalog with stable namespace ordering for runbook checks."""

    def list_namespaces(self, namespace: str | Identifier = ()) -> list[Identifier]:
        namespaces = super().list_namespaces(namespace)
        return sorted(namespaces, key=_namespace_sort_key)


SQL_CATALOG_CLASS: type[SqlCatalog] = DataPlatformSqlCatalog


def load_catalog(
    name: str | None = None,
    *,
    settings: Settings | None = None,
) -> SqlCatalog:
    """Load the project PG-backed PyIceberg SQL catalog."""

    pg_dsn, configured_catalog_name, warehouse_path = _catalog_config(settings)
    catalog_name = name or configured_catalog_name
    properties = {
        "uri": _sqlalchemy_postgres_uri(pg_dsn),
        "warehouse": _warehouse_location(warehouse_path),
        "pool_pre_ping": "true",
        "init_catalog_tables": "true",
    }

    try:
        return SQL_CATALOG_CLASS(catalog_name, **properties)
    except SQLAlchemyError as exc:
        raise CatalogConnectError(str(exc)) from exc


def ensure_namespaces(catalog: SqlCatalog, names: Iterable[str | Identifier]) -> None:
    """Create Iceberg namespaces idempotently, excluding Raw Zone by contract."""

    for namespace in names:
        normalized_namespace = _normalize_namespace_identifier(namespace)
        if normalized_namespace[0].lower() == RAW_NAMESPACE:
            msg = "raw namespace must not be created in the Iceberg catalog"
            raise ValueError(msg)
        try:
            catalog.create_namespace_if_not_exists(normalized_namespace)
        except SQLAlchemyError as exc:
            if _namespace_exists_after_create_error(catalog, normalized_namespace, exc):
                continue
            raise


def _catalog_config(settings: Settings | None = None) -> tuple[str, str, Path]:
    if settings is not None:
        return (
            str(settings.pg_dsn),
            settings.iceberg_catalog_name,
            settings.iceberg_warehouse_path,
        )

    try:
        resolved_settings = get_settings()
    except ValidationError as exc:
        jdbc_config = _jdbc_catalog_config_from_env(exc)
        if jdbc_config is None:
            raise
        return jdbc_config

    return (
        str(resolved_settings.pg_dsn),
        resolved_settings.iceberg_catalog_name,
        resolved_settings.iceberg_warehouse_path,
    )


def _jdbc_catalog_config_from_env(
    validation_error: ValidationError,
) -> tuple[str, str, Path] | None:
    raw_pg_dsn = os.environ.get("DP_PG_DSN")
    warehouse_path = os.environ.get("DP_ICEBERG_WAREHOUSE_PATH")
    if not raw_pg_dsn or not raw_pg_dsn.startswith("jdbc:postgresql://"):
        return None
    if not warehouse_path:
        return None
    if not _validation_error_includes_field(validation_error, "pg_dsn"):
        return None

    catalog_name = os.environ.get("DP_ICEBERG_CATALOG_NAME", "data_platform")
    return raw_pg_dsn, catalog_name, Path(warehouse_path)


def _validation_error_includes_field(error: ValidationError, field_name: str) -> bool:
    return any(
        error_detail.get("loc") == (field_name,) for error_detail in error.errors()
    )


def _normalize_namespace_identifier(namespace: str | Identifier) -> Identifier:
    try:
        namespace_string = Catalog.namespace_to_string(namespace)
    except ValueError as exc:
        msg = f"invalid Iceberg namespace identifier: {namespace!r}"
        raise ValueError(msg) from exc
    parts = tuple(part.strip() for part in namespace_string.split("."))
    if not parts or any(not part for part in parts):
        msg = f"invalid Iceberg namespace identifier: {namespace!r}"
        raise ValueError(msg)
    return parts


def _namespace_exists_after_create_error(
    catalog: SqlCatalog,
    namespace: Identifier,
    create_error: SQLAlchemyError,
) -> bool:
    try:
        return catalog.namespace_exists(namespace)
    except SQLAlchemyError as lookup_error:
        raise create_error from lookup_error


def _sqlalchemy_postgres_uri(dsn: str) -> str:
    if dsn.startswith("jdbc:postgresql://"):
        return "postgresql+psycopg://" + dsn.removeprefix("jdbc:postgresql://")
    if dsn.startswith("postgresql://"):
        return "postgresql+psycopg://" + dsn.removeprefix("postgresql://")
    if dsn.startswith("postgres://"):
        return "postgresql+psycopg://" + dsn.removeprefix("postgres://")
    return dsn


def _warehouse_location(path: Path) -> str:
    return str(path.expanduser())


def _namespace_sort_key(namespace: Identifier) -> tuple[int, str]:
    try:
        default_index = DEFAULT_NAMESPACE_IDENTIFIERS.index(namespace)
    except ValueError:
        default_index = len(DEFAULT_NAMESPACE_IDENTIFIERS)
    return (default_index, ".".join(namespace))
