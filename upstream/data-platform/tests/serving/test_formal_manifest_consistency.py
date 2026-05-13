from __future__ import annotations

import importlib.util
import os
from collections.abc import Generator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    import pyarrow as pa
    from pyiceberg.catalog.sql import SqlCatalog


REQUIRED_MODULES = ("pyarrow", "pyiceberg", "sqlalchemy", "pydantic_settings")
FORMAL_CONSISTENCY_DEPS_MISSING = any(
    importlib.util.find_spec(module) is None for module in REQUIRED_MODULES
)
pytestmark = pytest.mark.skipif(
    FORMAL_CONSISTENCY_DEPS_MISSING,
    reason="formal manifest consistency tests require PyArrow, PyIceberg, and SQLAlchemy",
)

OBJECT_TYPE = "recommendation_snapshot"
FORMAL_IDENTIFIER = f"formal.{OBJECT_TYPE}"


@dataclass(frozen=True, slots=True)
class FormalConsistencyContext:
    catalog: SqlCatalog
    engine: Any
    object_type: str
    identifier: str


def test_add_column_old_manifest_snapshot_keeps_old_schema(
    formal_context: FormalConsistencyContext,
    pa_module: Any,
) -> None:
    from data_platform.serving.formal import get_formal_by_id

    v1_snapshot_id = write_formal_snapshot(
        formal_context.catalog,
        formal_context.identifier,
        _formal_rows(pa_module, "v1", scores=[10, 11]),
    )
    _publish_snapshot(date(2026, 4, 16), formal_context.identifier, v1_snapshot_id)

    _add_extra_column(formal_context.catalog, formal_context.identifier)
    v2_snapshot_id = write_formal_snapshot(
        formal_context.catalog,
        formal_context.identifier,
        _formal_rows(pa_module, "v2", scores=[20], extra_values=["new"]),
    )
    _publish_snapshot(date(2026, 4, 17), formal_context.identifier, v2_snapshot_id)

    old_object = get_formal_by_id("CYCLE_20260416", formal_context.object_type)
    new_object = get_formal_by_id("CYCLE_20260417", formal_context.object_type)

    assert old_object.snapshot_id == v1_snapshot_id
    assert_formal_payload_columns(old_object, ["version", "score"])
    assert "extra" not in old_object.payload.schema.names
    assert old_object.payload.num_rows == 2
    assert old_object.payload.column("version").to_pylist() == ["v1-0", "v1-1"]

    assert new_object.snapshot_id == v2_snapshot_id
    assert_formal_payload_columns(new_object, ["version", "score", "extra"])
    assert new_object.payload.column("extra").to_pylist() == ["new"]


def test_unpublished_formal_head_is_invisible_to_latest_reader(
    formal_context: FormalConsistencyContext,
    pa_module: Any,
) -> None:
    from data_platform.serving.formal import get_formal_latest

    v1_snapshot_id = write_formal_snapshot(
        formal_context.catalog,
        formal_context.identifier,
        _formal_rows(pa_module, "v1", scores=[1]),
    )
    _publish_snapshot(date(2026, 4, 16), formal_context.identifier, v1_snapshot_id)

    _add_extra_column(formal_context.catalog, formal_context.identifier)
    v2_snapshot_id = write_formal_snapshot(
        formal_context.catalog,
        formal_context.identifier,
        _formal_rows(pa_module, "v2", scores=[2], extra_values=["published"]),
    )
    _publish_snapshot(date(2026, 4, 17), formal_context.identifier, v2_snapshot_id)

    v3_snapshot_id = write_formal_snapshot(
        formal_context.catalog,
        formal_context.identifier,
        _formal_rows(pa_module, "v3", scores=[3], extra_values=["unpublished-head"]),
    )

    latest_object = get_formal_latest(formal_context.object_type)

    assert latest_object.cycle_id == "CYCLE_20260417"
    assert latest_object.snapshot_id == v2_snapshot_id
    assert latest_object.snapshot_id != v3_snapshot_id
    assert latest_object.payload.column("version").to_pylist() == ["v2-0"]
    assert latest_object.payload.column("extra").to_pylist() == ["published"]


def test_failed_publish_does_not_advance_latest_manifest(
    formal_context: FormalConsistencyContext,
    pa_module: Any,
) -> None:
    from data_platform.cycle import (
        PublishManifestNotFound,
        get_cycle,
        get_publish_manifest,
        publish_manifest,
    )
    from data_platform.serving.formal import get_formal_latest

    v1_snapshot_id = write_formal_snapshot(
        formal_context.catalog,
        formal_context.identifier,
        _formal_rows(pa_module, "v1", scores=[1]),
    )
    _publish_snapshot(date(2026, 4, 16), formal_context.identifier, v1_snapshot_id)

    v2_snapshot_id = write_formal_snapshot(
        formal_context.catalog,
        formal_context.identifier,
        _formal_rows(pa_module, "v2", scores=[2]),
    )
    _publish_snapshot(date(2026, 4, 17), formal_context.identifier, v2_snapshot_id)

    v3_snapshot_id = write_formal_snapshot(
        formal_context.catalog,
        formal_context.identifier,
        _formal_rows(pa_module, "v3", scores=[3]),
    )
    failed_cycle_id = _create_phase3_cycle(date(2026, 4, 18))
    _install_publish_status_failure_trigger(formal_context.engine)

    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="formal manifest consistency tests require SQLAlchemy",
    ).SQLAlchemyError
    with pytest.raises(sqlalchemy_error):
        publish_manifest(
            failed_cycle_id,
            _snapshot_manifest(formal_context.identifier, v3_snapshot_id),
            recommendation_provenance=_recommendation_provenance(
                failed_cycle_id,
                v3_snapshot_id,
            ),
        )

    latest_object = get_formal_latest(formal_context.object_type)

    assert latest_object.cycle_id == "CYCLE_20260417"
    assert latest_object.snapshot_id == v2_snapshot_id
    assert latest_object.snapshot_id != v3_snapshot_id
    assert latest_object.payload.column("version").to_pylist() == ["v2-0"]
    assert get_cycle(failed_cycle_id).status == "phase3"
    with pytest.raises(PublishManifestNotFound):
        get_publish_manifest(failed_cycle_id)
    assert _manifest_count(formal_context.engine) == 2


def test_by_snapshot_requires_manifest_publication(
    formal_context: FormalConsistencyContext,
    pa_module: Any,
) -> None:
    from data_platform.serving.formal import (
        FormalSnapshotNotPublished,
        get_formal_by_snapshot,
    )

    v1_snapshot_id = write_formal_snapshot(
        formal_context.catalog,
        formal_context.identifier,
        _formal_rows(pa_module, "v1", scores=[1]),
    )
    _publish_snapshot(date(2026, 4, 16), formal_context.identifier, v1_snapshot_id)

    v2_snapshot_id = write_formal_snapshot(
        formal_context.catalog,
        formal_context.identifier,
        _formal_rows(pa_module, "v2", scores=[2]),
    )
    _publish_snapshot(date(2026, 4, 17), formal_context.identifier, v2_snapshot_id)

    v3_snapshot_id = write_formal_snapshot(
        formal_context.catalog,
        formal_context.identifier,
        _formal_rows(pa_module, "v3", scores=[3]),
    )

    published_object = get_formal_by_snapshot(v2_snapshot_id, formal_context.object_type)

    assert published_object.cycle_id == "CYCLE_20260417"
    assert published_object.snapshot_id == v2_snapshot_id
    assert published_object.payload.column("version").to_pylist() == ["v2-0"]
    with pytest.raises(FormalSnapshotNotPublished):
        get_formal_by_snapshot(v3_snapshot_id, formal_context.object_type)


def write_formal_snapshot(catalog: SqlCatalog, identifier: str, rows: pa.Table) -> int:
    table = catalog.load_table(identifier)
    table.overwrite(rows)
    snapshot = table.refresh().current_snapshot()
    if snapshot is None:
        raise AssertionError("formal table overwrite did not create a snapshot")
    return int(snapshot.snapshot_id)


def assert_formal_payload_columns(obj: Any, expected: list[str]) -> None:
    assert obj.payload.schema.names == expected


@pytest.fixture()
def pa_module() -> Any:
    return pytest.importorskip("pyarrow", reason="formal consistency tests require PyArrow")


@pytest.fixture()
def formal_test_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[str]:
    admin_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DP_PG_DSN")
    if not admin_dsn:
        pytest.skip(
            "PostgreSQL formal manifest consistency tests require DATABASE_URL or DP_PG_DSN"
        )

    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="formal manifest consistency tests require SQLAlchemy",
    )
    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="formal manifest consistency tests require SQLAlchemy",
    ).SQLAlchemyError
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="formal manifest consistency tests require the migration runner",
    )

    database_name = f"dp_formal_manifest_{uuid4().hex}"
    admin_engine = _create_engine(
        admin_dsn,
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    database_created = False
    try:
        try:
            with admin_engine.connect() as connection:
                connection.execute(sqlalchemy.text(f'CREATE DATABASE "{database_name}"'))
            database_created = True
        except sqlalchemy_error as exc:
            pytest.skip(
                "PostgreSQL formal manifest consistency tests require permission "
                f"to create test databases: {exc}"
            )

        test_dsn = _database_dsn(admin_dsn, database_name)
        runner_module.MigrationRunner().apply_pending(test_dsn)
        monkeypatch.setenv("DP_PG_DSN", test_dsn)
        monkeypatch.setenv("DP_RAW_ZONE_PATH", str(tmp_path / "raw"))
        monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", str(tmp_path / "warehouse"))
        monkeypatch.setenv("DP_DUCKDB_PATH", str(tmp_path / "formal.duckdb"))
        monkeypatch.setenv("DP_ICEBERG_CATALOG_NAME", f"manifest_{uuid4().hex}")
        _reset_settings_cache()
        yield test_dsn
    finally:
        _reset_settings_cache()
        if database_created:
            with admin_engine.connect() as connection:
                connection.execute(
                    sqlalchemy.text(
                        """
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = :database_name
                          AND pid <> pg_backend_pid()
                        """
                    ),
                    {"database_name": database_name},
                )
                connection.execute(
                    sqlalchemy.text(f'DROP DATABASE IF EXISTS "{database_name}"')
                )
        admin_engine.dispose()


@pytest.fixture()
def formal_context(
    formal_test_env: str,
    pa_module: Any,
) -> Generator[FormalConsistencyContext]:
    from data_platform.serving.catalog import load_catalog

    catalog = load_catalog()
    catalog.create_namespace_if_not_exists(("formal",))
    catalog.create_table(FORMAL_IDENTIFIER, schema=_base_schema(pa_module))

    engine = _create_engine(formal_test_env)
    try:
        yield FormalConsistencyContext(
            catalog=catalog,
            engine=engine,
            object_type=OBJECT_TYPE,
            identifier=FORMAL_IDENTIFIER,
        )
    finally:
        engine.dispose()


def _formal_rows(
    pa_module: Any,
    version_prefix: str,
    *,
    scores: list[int],
    extra_values: list[str] | None = None,
) -> Any:
    versions = [f"{version_prefix}-{index}" for index in range(len(scores))]
    if extra_values is None:
        return pa_module.table(
            {
                "version": versions,
                "score": scores,
            },
            schema=_base_schema(pa_module),
        )

    return pa_module.table(
        {
            "version": versions,
            "score": scores,
            "extra": extra_values,
        },
        schema=_extended_schema(pa_module),
    )


def _base_schema(pa_module: Any) -> Any:
    return pa_module.schema(
        [
            pa_module.field("version", pa_module.string()),
            pa_module.field("score", pa_module.int64()),
        ]
    )


def _extended_schema(pa_module: Any) -> Any:
    return pa_module.schema(
        [
            pa_module.field("version", pa_module.string()),
            pa_module.field("score", pa_module.int64()),
            pa_module.field("extra", pa_module.string()),
        ]
    )


def _add_extra_column(catalog: SqlCatalog, identifier: str) -> None:
    types = pytest.importorskip(
        "pyiceberg.types",
        reason="formal manifest consistency tests require PyIceberg",
    )
    table = catalog.load_table(identifier)
    table.update_schema().add_column("extra", types.StringType()).commit()


def _publish_snapshot(cycle_date: date, identifier: str, snapshot_id: int) -> None:
    from data_platform.cycle import publish_manifest

    cycle_id = _create_phase3_cycle(cycle_date)
    publish_manifest(
        cycle_id,
        _snapshot_manifest(identifier, snapshot_id),
        recommendation_provenance=_recommendation_provenance(cycle_id, snapshot_id),
    )


def _recommendation_provenance(cycle_id: str, snapshot_id: int) -> dict[str, object]:
    return {
        "cycle_id": cycle_id,
        "current_cycle_id": cycle_id,
        "source_layer": "L8",
        "source_kind": "current-cycle",
        "recommendation_snapshot_id": snapshot_id,
        "audit_record_ids": [f"audit-formal-consistency-{cycle_id}-{snapshot_id}"],
        "replay_record_ids": [f"replay-formal-consistency-{cycle_id}-{snapshot_id}"],
    }


def _snapshot_manifest(identifier: str, snapshot_id: int) -> dict[str, int]:
    snapshots = {
        "formal.world_state_snapshot": snapshot_id,
        "formal.official_alpha_pool": snapshot_id,
        "formal.alpha_result_snapshot": snapshot_id,
        "formal.recommendation_snapshot": snapshot_id,
    }
    snapshots[identifier] = snapshot_id
    return snapshots


def _create_phase3_cycle(cycle_date: date) -> str:
    from data_platform.cycle import create_cycle, transition_cycle_status

    cycle = create_cycle(cycle_date)
    for status in ("phase0", "phase1", "phase2", "phase3"):
        transition_cycle_status(cycle.cycle_id, status)
    return cycle.cycle_id


def _install_publish_status_failure_trigger(engine: Any) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION data_platform.raise_publish_status_update_failure()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'forced publish status update failure';
            END;
            $$;

            CREATE TRIGGER force_publish_status_update_failure
            BEFORE UPDATE OF status ON data_platform.cycle_metadata
            FOR EACH ROW
            WHEN (NEW.status = CAST('published' AS data_platform.cycle_status))
            EXECUTE FUNCTION data_platform.raise_publish_status_update_failure();
            """
        )


def _manifest_count(engine: Any) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                _text("SELECT count(*) FROM data_platform.cycle_publish_manifest")
            ).scalar_one()
        )


def _create_engine(dsn: str, **kwargs: object) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="formal manifest consistency tests require SQLAlchemy",
    )
    from data_platform.serving.catalog import _sqlalchemy_postgres_uri

    return sqlalchemy.create_engine(_sqlalchemy_postgres_uri(dsn), **kwargs)


def _database_dsn(admin_dsn: str, database_name: str) -> str:
    make_url = pytest.importorskip(
        "sqlalchemy.engine",
        reason="formal manifest consistency tests require SQLAlchemy",
    ).make_url
    return (
        make_url(_plain_postgres_uri(admin_dsn))
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )


def _plain_postgres_uri(dsn: str) -> str:
    if dsn.startswith("jdbc:postgresql://"):
        return "postgresql://" + dsn.removeprefix("jdbc:postgresql://")
    if dsn.startswith("postgresql+psycopg://"):
        return "postgresql://" + dsn.removeprefix("postgresql+psycopg://")
    if dsn.startswith("postgres://"):
        return "postgresql://" + dsn.removeprefix("postgres://")
    return dsn


def _text(sql: str) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="formal manifest consistency tests require SQLAlchemy",
    )
    return sqlalchemy.text(sql)


def _reset_settings_cache() -> None:
    from data_platform.config import reset_settings_cache

    reset_settings_cache()
