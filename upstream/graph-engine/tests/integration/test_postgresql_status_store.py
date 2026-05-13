from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier, Event
from typing import Any
from uuid import uuid4

import pytest

from graph_engine.models import Neo4jGraphStatus
from graph_engine.status import GraphStatusManager
from graph_engine.status.store import PostgreSQLStatusStore

pytestmark = pytest.mark.skipif(
    os.getenv("DATABASE_URL") is None,
    reason="DATABASE_URL is not set; PostgreSQL status store tests require a database.",
)

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)


class BarrierStatusStore(PostgreSQLStatusStore):
    def __init__(self, *args: Any, barrier: Barrier, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._barrier = barrier

    def read_current_status(self) -> Neo4jGraphStatus | None:
        status = super().read_current_status()
        if (
            status is not None
            and status.graph_status == "ready"
            and status.writer_lock_token is None
        ):
            self._barrier.wait(timeout=10)
        return status


def test_postgresql_status_store_bootstraps_empty_row_and_persists_transitions() -> None:
    pytest.importorskip("psycopg")

    database_url = _database_url()
    table_name = _table_name()
    store = PostgreSQLStatusStore(database_url, table_name=table_name)

    try:
        assert store.read_current_status() is None

        rebuilding = GraphStatusManager(store, clock=lambda: NOW).mark_rebuilding()
        assert rebuilding.graph_status == "rebuilding"
        assert store.read_current_status() == rebuilding

        ready = GraphStatusManager(store, clock=lambda: NOW).mark_ready(
            node_count=3,
            edge_count=2,
            key_label_counts={"Entity": 2, "Sector": 1},
            checksum="ready-checksum",
            reload_completed=True,
        )

        assert store.read_current_status() == ready
        assert ready.graph_status == "ready"
        assert ready.graph_generation_id == 1
        assert ready.last_verified_at == NOW
        assert ready.last_reload_at == NOW
    finally:
        _drop_table(database_url, table_name)


def test_postgresql_status_store_rejects_competing_reload_and_sync_transitions() -> None:
    pytest.importorskip("psycopg")

    database_url = _database_url()
    table_name = _table_name()
    store = PostgreSQLStatusStore(database_url, table_name=table_name)
    store.write_current_status(_status())
    barrier = Barrier(2)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(_begin_sync, database_url, table_name, barrier),
                executor.submit(_mark_rebuilding, database_url, table_name, barrier),
            ]
            outcomes = [future.result(timeout=20) for future in futures]

        assert outcomes.count("stale") == 1
        assert outcomes.count("locked") + outcomes.count("rebuilding") == 1
        final_status = store.read_current_status()
        assert final_status is not None
        assert final_status.graph_status == "rebuilding" or (
            final_status.graph_status == "ready"
            and final_status.writer_lock_token is not None
        )
    finally:
        _drop_table(database_url, table_name)


def test_postgresql_ready_read_lock_blocks_competing_store_writer() -> None:
    pytest.importorskip("psycopg")

    database_url = _database_url()
    table_name = _table_name()
    store = PostgreSQLStatusStore(database_url, table_name=table_name)
    store.write_current_status(_status())

    reader_entered = Event()
    release_reader = Event()
    writer_started = Event()

    class ObservedWriterStore(PostgreSQLStatusStore):
        def compare_and_write_current_status(
            self,
            *,
            expected_status: Neo4jGraphStatus | None,
            next_status: Neo4jGraphStatus,
        ) -> bool:
            writer_started.set()
            return super().compare_and_write_current_status(
                expected_status=expected_status,
                next_status=next_status,
            )

    def hold_reader() -> Neo4jGraphStatus:
        reader_store = PostgreSQLStatusStore(database_url, table_name=table_name)
        with GraphStatusManager(reader_store, clock=lambda: NOW).ready_read() as status:
            reader_entered.set()
            release_reader.wait(timeout=10)
            return status

    def begin_sync() -> tuple[Neo4jGraphStatus, Neo4jGraphStatus]:
        writer_store = ObservedWriterStore(database_url, table_name=table_name)
        return GraphStatusManager(writer_store, clock=lambda: NOW).begin_sync()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            reader_future = executor.submit(hold_reader)
            assert reader_entered.wait(timeout=10)

            writer_future = executor.submit(begin_sync)
            assert writer_started.wait(timeout=10)
            assert not writer_future.done()

            release_reader.set()
            ready_status, locked_status = writer_future.result(timeout=20)
            assert reader_future.result(timeout=20) == _status()

        assert ready_status == _status()
        assert locked_status.graph_status == "ready"
        assert locked_status.writer_lock_token is not None
    finally:
        release_reader.set()
        _drop_table(database_url, table_name)


def test_postgresql_ready_read_lock_uses_resolved_relation_for_schema_qualified_store() -> None:
    pytest.importorskip("psycopg")

    database_url = _database_url()
    table_name = _table_name()
    qualified_table_name = f"public.{table_name}"
    store = PostgreSQLStatusStore(database_url, table_name=qualified_table_name)
    store.write_current_status(_status())

    reader_entered = Event()
    release_reader = Event()
    writer_started = Event()

    class ObservedWriterStore(PostgreSQLStatusStore):
        def compare_and_write_current_status(
            self,
            *,
            expected_status: Neo4jGraphStatus | None,
            next_status: Neo4jGraphStatus,
        ) -> bool:
            writer_started.set()
            return super().compare_and_write_current_status(
                expected_status=expected_status,
                next_status=next_status,
            )

    def hold_reader() -> Neo4jGraphStatus:
        reader_store = PostgreSQLStatusStore(database_url, table_name=table_name)
        with GraphStatusManager(reader_store, clock=lambda: NOW).ready_read() as status:
            reader_entered.set()
            release_reader.wait(timeout=10)
            return status

    def begin_sync() -> tuple[Neo4jGraphStatus, Neo4jGraphStatus]:
        writer_store = ObservedWriterStore(database_url, table_name=qualified_table_name)
        return GraphStatusManager(writer_store, clock=lambda: NOW).begin_sync()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            reader_future = executor.submit(hold_reader)
            assert reader_entered.wait(timeout=10)

            writer_future = executor.submit(begin_sync)
            assert writer_started.wait(timeout=10)
            assert not writer_future.done()

            release_reader.set()
            ready_status, locked_status = writer_future.result(timeout=20)
            assert reader_future.result(timeout=20) == _status()

        assert ready_status == _status()
        assert locked_status.graph_status == "ready"
        assert locked_status.writer_lock_token is not None
    finally:
        release_reader.set()
        _drop_public_table(database_url, table_name)


def test_postgresql_status_store_bootstrap_migrates_legacy_syncing_status() -> None:
    psycopg = pytest.importorskip("psycopg")

    database_url = _database_url()
    table_name = _table_name()
    _create_legacy_syncing_status_row(psycopg, database_url, table_name)
    store = PostgreSQLStatusStore(database_url, table_name=table_name)

    try:
        store.bootstrap()

        status = store.read_current_status()
        assert status is not None
        assert status.graph_status == "failed"
        assert status.writer_lock_token is None
        assert status.last_verified_at is None

        with pytest.raises(Exception):
            with psycopg.connect(database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
UPDATE "{table_name}"
SET graph_status = 'syncing'
WHERE status_key = 'current'
""",
                    )
    finally:
        _drop_table(database_url, table_name)


def _begin_sync(database_url: str, table_name: str, barrier: Barrier) -> str:
    store = BarrierStatusStore(database_url, table_name=table_name, barrier=barrier)
    manager = GraphStatusManager(store, clock=lambda: NOW)
    try:
        _, status = manager.begin_sync()
    except RuntimeError as exc:
        assert "stale graph_status transition" in str(exc)
        return "stale"
    assert status.graph_status == "ready"
    assert status.writer_lock_token is not None
    return "locked"


def _mark_rebuilding(database_url: str, table_name: str, barrier: Barrier) -> str:
    store = BarrierStatusStore(database_url, table_name=table_name, barrier=barrier)
    manager = GraphStatusManager(store, clock=lambda: NOW)
    try:
        status = manager.mark_rebuilding()
    except RuntimeError as exc:
        assert "stale graph_status transition" in str(exc)
        return "stale"
    return status.graph_status


def _status() -> Neo4jGraphStatus:
    return Neo4jGraphStatus(
        graph_status="ready",
        graph_generation_id=8,
        node_count=2,
        edge_count=1,
        key_label_counts={"Entity": 2},
        checksum="ready-checksum",
        last_verified_at=NOW,
        last_reload_at=None,
    )


def _database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    assert database_url is not None
    return database_url


def _table_name() -> str:
    return f"neo4j_graph_status_test_{uuid4().hex}"


def _drop_table(database_url: str, table_name: str) -> None:
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')


def _drop_public_table(database_url: str, table_name: str) -> None:
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS public."{table_name}"')


def _create_legacy_syncing_status_row(
    psycopg: Any,
    database_url: str,
    table_name: str,
) -> None:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            cursor.execute(
                f"""
CREATE TABLE "{table_name}" (
    status_key text PRIMARY KEY,
    graph_status text NOT NULL CHECK (
        graph_status IN ('ready', 'rebuilding', 'failed', 'syncing')
    ),
    graph_generation_id bigint NOT NULL CHECK (graph_generation_id >= 0),
    node_count bigint NOT NULL CHECK (node_count >= 0),
    edge_count bigint NOT NULL CHECK (edge_count >= 0),
    key_label_counts jsonb NOT NULL CHECK (jsonb_typeof(key_label_counts) = 'object'),
    checksum text NOT NULL CHECK (checksum <> ''),
    last_verified_at timestamptz NULL,
    last_reload_at timestamptz NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
)
""",
            )
            cursor.execute(
                f"""
INSERT INTO "{table_name}" (
    status_key,
    graph_status,
    graph_generation_id,
    node_count,
    edge_count,
    key_label_counts,
    checksum,
    last_verified_at,
    last_reload_at
)
VALUES (
    'current',
    'syncing',
    8,
    2,
    1,
    '{{"Entity": 2}}'::jsonb,
    'legacy-syncing',
    %s,
    NULL
)
""",
                (NOW,),
            )
