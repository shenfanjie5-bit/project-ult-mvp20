from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa  # type: ignore[import-untyped]
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from data_platform.ddl.runner import MigrationRunner
from data_platform.formal_registry import REQUIRED_FORMAL_OBJECT_NAMES
from data_platform.serving.catalog import _sqlalchemy_postgres_uri, load_catalog


FORMAL_SCHEMA = pa.schema(
    [
        pa.field("version", pa.string()),
        pa.field("score", pa.int64()),
    ]
)


@dataclass(frozen=True, slots=True)
class PublishChainContext:
    dsn: str
    engine: Any
    warehouse_path: Path
    catalog_name: str


@pytest.mark.spike
def test_pg_catalog_formal_write_manifest_serving_atomicity(
    publish_chain_context: PublishChainContext,
) -> None:
    from data_platform.cycle import (
        PublishManifestNotFound,
        get_publish_manifest,
        publish_manifest,
    )
    from data_platform.serving.formal import (
        FormalSnapshotNotPublished,
        get_formal_by_snapshot,
        get_formal_latest,
    )

    catalog = load_catalog()
    catalog.create_namespace_if_not_exists(("formal",))
    for object_name in REQUIRED_FORMAL_OBJECT_NAMES:
        catalog.create_table(f"formal.{object_name}", schema=FORMAL_SCHEMA)

    v1_snapshots = _write_formal_set(catalog, "v1", score=1)
    _publish_snapshot_set(date(2026, 4, 16), v1_snapshots)

    v2_snapshots = _write_formal_set(catalog, "v2", score=2)
    _publish_snapshot_set(date(2026, 4, 17), v2_snapshots)

    _assert_pg_catalog_points_at_snapshot(
        publish_chain_context.engine,
        publish_chain_context.warehouse_path,
        publish_chain_context.catalog_name,
        "formal.recommendation_snapshot",
        v2_snapshots["formal.recommendation_snapshot"],
    )

    manifest = get_publish_manifest("CYCLE_20260417")
    assert set(manifest.formal_table_snapshots) == {
        f"formal.{object_name}" for object_name in REQUIRED_FORMAL_OBJECT_NAMES
    }
    assert {
        table: snapshot.snapshot_id
        for table, snapshot in manifest.formal_table_snapshots.items()
    } == v2_snapshots

    latest = get_formal_latest("recommendation_snapshot")
    assert latest.cycle_id == "CYCLE_20260417"
    assert latest.snapshot_id == v2_snapshots["formal.recommendation_snapshot"]
    assert latest.payload.to_pylist() == [{"version": "v2", "score": 2}]

    old = get_formal_by_snapshot(
        v1_snapshots["formal.recommendation_snapshot"],
        "recommendation_snapshot",
    )
    assert old.cycle_id == "CYCLE_20260416"
    assert old.payload.to_pylist() == [{"version": "v1", "score": 1}]

    v3_snapshots = _write_formal_set(catalog, "v3-unpublished", score=3)
    failed_cycle_id = _create_phase3_cycle(date(2026, 4, 18))
    _install_publish_status_failure_trigger(publish_chain_context.engine)
    with pytest.raises(SQLAlchemyError):
        publish_manifest(
            failed_cycle_id,
            v3_snapshots,
            recommendation_provenance=_recommendation_provenance(
                failed_cycle_id,
                v3_snapshots["formal.recommendation_snapshot"],
            ),
        )

    latest_after_failure = get_formal_latest("recommendation_snapshot")
    assert latest_after_failure.cycle_id == "CYCLE_20260417"
    assert latest_after_failure.snapshot_id == v2_snapshots["formal.recommendation_snapshot"]
    assert latest_after_failure.payload.to_pylist() == [{"version": "v2", "score": 2}]
    with pytest.raises(PublishManifestNotFound):
        get_publish_manifest(failed_cycle_id)
    with pytest.raises(FormalSnapshotNotPublished):
        get_formal_by_snapshot(
            v3_snapshots["formal.recommendation_snapshot"],
            "recommendation_snapshot",
        )


@pytest.fixture()
def publish_chain_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[PublishChainContext]:
    admin_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DP_PG_DSN")
    if not admin_dsn:
        pytest.skip("Iceberg publish chain spike requires DATABASE_URL or DP_PG_DSN")

    database_name = f"dp_publish_chain_{uuid4().hex}"
    admin_engine = create_engine(
        _sqlalchemy_postgres_uri(admin_dsn),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    database_created = False
    try:
        try:
            with admin_engine.connect() as connection:
                connection.execute(text(f'CREATE DATABASE "{database_name}"'))
            database_created = True
        except SQLAlchemyError as exc:
            pytest.skip(
                "Iceberg publish chain spike requires permission to create "
                f"test databases: {exc}"
            )

        test_dsn = (
            make_url(_plain_postgres_uri(admin_dsn))
            .set(database=database_name)
            .render_as_string(hide_password=False)
        )
        MigrationRunner().apply_pending(test_dsn)
        warehouse_path = tmp_path / "warehouse"
        monkeypatch.setenv("DP_PG_DSN", test_dsn)
        monkeypatch.setenv("DP_RAW_ZONE_PATH", str(tmp_path / "raw"))
        monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", str(warehouse_path))
        monkeypatch.setenv("DP_DUCKDB_PATH", str(tmp_path / "serving.duckdb"))
        monkeypatch.setenv("DP_ICEBERG_CATALOG_NAME", f"publish_chain_{uuid4().hex}")
        _reset_settings_cache()

        engine = create_engine(_sqlalchemy_postgres_uri(test_dsn), pool_pre_ping=True)
        try:
            yield PublishChainContext(
                dsn=test_dsn,
                engine=engine,
                warehouse_path=warehouse_path,
                catalog_name=os.environ["DP_ICEBERG_CATALOG_NAME"],
            )
        finally:
            engine.dispose()
    finally:
        _reset_settings_cache()
        if database_created:
            with admin_engine.connect() as connection:
                connection.execute(
                    text(
                        """
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = :database_name
                          AND pid <> pg_backend_pid()
                        """
                    ),
                    {"database_name": database_name},
                )
                connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()


def _write_formal_set(catalog: Any, version: str, *, score: int) -> dict[str, int]:
    snapshots: dict[str, int] = {}
    for object_name in REQUIRED_FORMAL_OBJECT_NAMES:
        identifier = f"formal.{object_name}"
        table = catalog.load_table(identifier)
        table.overwrite(
            pa.table(
                {"version": [version], "score": [score]},
                schema=FORMAL_SCHEMA,
            )
        )
        snapshot = table.refresh().current_snapshot()
        if snapshot is None:
            raise AssertionError(f"{identifier} overwrite did not create a snapshot")
        snapshots[identifier] = int(snapshot.snapshot_id)
    return snapshots


def _publish_snapshot_set(cycle_date: date, snapshots: dict[str, int]) -> None:
    from data_platform.cycle import publish_manifest

    cycle_id = _create_phase3_cycle(cycle_date)
    publish_manifest(
        cycle_id,
        snapshots,
        recommendation_provenance=_recommendation_provenance(
            cycle_id,
            snapshots["formal.recommendation_snapshot"],
        ),
    )


def _recommendation_provenance(cycle_id: str, snapshot_id: int) -> dict[str, object]:
    return {
        "cycle_id": cycle_id,
        "current_cycle_id": cycle_id,
        "source_layer": "L8",
        "source_kind": "current-cycle",
        "recommendation_snapshot_id": snapshot_id,
        "audit_record_ids": [f"audit-publish-chain-{cycle_id}-{snapshot_id}"],
        "replay_record_ids": [f"replay-publish-chain-{cycle_id}-{snapshot_id}"],
    }


def _create_phase3_cycle(cycle_date: date) -> str:
    from data_platform.cycle import create_cycle, transition_cycle_status

    cycle = create_cycle(cycle_date)
    for status in ("phase0", "phase1", "phase2", "phase3"):
        transition_cycle_status(cycle.cycle_id, status)
    return cycle.cycle_id


def _assert_pg_catalog_points_at_snapshot(
    engine: Any,
    warehouse_path: Path,
    catalog_name: str,
    table_identifier: str,
    expected_snapshot_id: int,
) -> None:
    namespace, table_name = table_identifier.split(".", maxsplit=1)
    with engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    """
                    SELECT metadata_location
                    FROM iceberg_tables
                    WHERE catalog_name = :catalog_name
                      AND table_namespace = :namespace
                      AND table_name = :table_name
                    """
                ),
                {
                    "catalog_name": catalog_name,
                    "namespace": namespace,
                    "table_name": table_name,
                },
            )
            .mappings()
            .one()
        )

    metadata_location = _metadata_path(warehouse_path, str(row["metadata_location"]))
    metadata = json.loads(metadata_location.read_text(encoding="utf-8"))
    assert int(metadata["current-snapshot-id"]) == expected_snapshot_id


def _metadata_path(warehouse_path: Path, metadata_location: str) -> Path:
    if metadata_location.startswith("file:"):
        from urllib.parse import unquote, urlparse

        return Path(unquote(urlparse(metadata_location).path))
    path = Path(metadata_location)
    if path.is_absolute():
        return path
    return warehouse_path / path


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


def _plain_postgres_uri(dsn: str) -> str:
    if dsn.startswith("jdbc:postgresql://"):
        return "postgresql://" + dsn.removeprefix("jdbc:postgresql://")
    if dsn.startswith("postgresql+psycopg://"):
        return "postgresql://" + dsn.removeprefix("postgresql+psycopg://")
    if dsn.startswith("postgres://"):
        return "postgresql://" + dsn.removeprefix("postgres://")
    return dsn


def _reset_settings_cache() -> None:
    from data_platform.config import reset_settings_cache
    import data_platform.serving.reader as serving_reader

    reset_settings_cache()
    serving_reader._duckdb_connection.cache_clear()
