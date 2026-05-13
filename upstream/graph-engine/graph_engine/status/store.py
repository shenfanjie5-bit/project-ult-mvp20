"""Status storage boundary for the current Neo4j live graph state."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from threading import Lock
from typing import Any, Protocol

from graph_engine.models import Neo4jGraphStatus

_GRAPH_STATUS_CHECK_CONSTRAINT = "neo4j_graph_status_graph_status_check"


class StatusStore(Protocol):
    """Persistence boundary for the singleton Neo4j graph status row."""

    def ready_read_lock(self) -> AbstractContextManager[None]:
        """Hold a shared persistence lock for a ready live-graph read."""

    def read_current_status(self) -> Neo4jGraphStatus | None:
        """Return the current status row, or None before bootstrap."""

    def write_current_status(self, status: Neo4jGraphStatus) -> None:
        """Persist the current status row."""

    def compare_and_write_current_status(
        self,
        *,
        expected_status: Neo4jGraphStatus | None,
        next_status: Neo4jGraphStatus,
    ) -> bool:
        """Atomically persist next_status only if the current row still matches."""


class PostgreSQLStatusStore:
    """PostgreSQL-backed singleton status store.

    The store keeps one row in ``neo4j_graph_status`` by default.  It expects
    PostgreSQL ``READ COMMITTED`` isolation or stronger: compare-and-set writes
    are a single ``UPDATE ... WHERE`` statement, so PostgreSQL locks the row and
    rechecks the expected fields after any competing transaction commits.  Ready
    reads hold a shared advisory lock on a dedicated connection for the duration
    of the read body, and status writes take the matching exclusive advisory lock
    so distinct store instances backed by the same row share the same read/write
    barrier.  Empty store bootstrap uses the singleton primary key with
    ``ON CONFLICT DO NOTHING`` so only one process can create the first status
    row.
    """

    def __init__(
        self,
        database_url: str | None = None,
        *,
        connection_factory: Callable[[], Any] | None = None,
        table_name: str = "neo4j_graph_status",
        status_key: str = "current",
        auto_bootstrap: bool = True,
        connect_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        if connection_factory is None:
            resolved_database_url = database_url or os.getenv("DATABASE_URL")
            if resolved_database_url is None:
                raise ValueError(
                    "database_url or DATABASE_URL is required for PostgreSQLStatusStore",
                )
            connection_factory = _build_psycopg_connection_factory(
                resolved_database_url,
                connect_kwargs=dict(connect_kwargs or {}),
            )

        if not status_key:
            raise ValueError("status_key must be non-empty")

        self._connection_factory = connection_factory
        self._table_name = _quote_qualified_identifier(table_name)
        self._status_key = status_key
        self._auto_bootstrap = auto_bootstrap
        self._bootstrapped = False
        self._bootstrap_lock = Lock()

    @classmethod
    def from_database_url(
        cls,
        database_url: str | None = None,
        *,
        table_name: str = "neo4j_graph_status",
        status_key: str = "current",
        auto_bootstrap: bool = True,
        connect_kwargs: Mapping[str, Any] | None = None,
    ) -> PostgreSQLStatusStore:
        """Build a store from a PostgreSQL URL, defaulting to ``DATABASE_URL``."""

        return cls(
            database_url,
            table_name=table_name,
            status_key=status_key,
            auto_bootstrap=auto_bootstrap,
            connect_kwargs=connect_kwargs,
        )

    def bootstrap(self) -> None:
        """Create the status table if assembly has not already provisioned it."""

        with self._bootstrap_lock:
            if self._bootstrapped:
                return
            with self._transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
CREATE TABLE IF NOT EXISTS {self._table_name} (
    status_key text PRIMARY KEY,
    graph_status text NOT NULL CHECK (
        graph_status IN ('ready', 'rebuilding', 'failed')
    ),
    graph_generation_id bigint NOT NULL CHECK (graph_generation_id >= 0),
    node_count bigint NOT NULL CHECK (node_count >= 0),
    edge_count bigint NOT NULL CHECK (edge_count >= 0),
    key_label_counts jsonb NOT NULL CHECK (jsonb_typeof(key_label_counts) = 'object'),
    checksum text NOT NULL CHECK (checksum <> ''),
    last_verified_at timestamptz NULL,
    last_reload_at timestamptz NULL,
    writer_lock_token text NULL CHECK (
        writer_lock_token IS NULL OR writer_lock_token <> ''
    ),
    updated_at timestamptz NOT NULL DEFAULT now()
)
""",
                    )
                    cursor.execute(
                        f"""
ALTER TABLE {self._table_name}
ADD COLUMN IF NOT EXISTS writer_lock_token text NULL CHECK (
    writer_lock_token IS NULL OR writer_lock_token <> ''
)
""",
                    )
                    self._normalize_legacy_syncing_status(cursor)
                    self._recreate_graph_status_check_constraint(cursor)
            self._bootstrapped = True

    def ensure_schema(self) -> None:
        """Alias for callers that name bootstrap as schema provisioning."""

        self.bootstrap()

    def read_current_status(self) -> Neo4jGraphStatus | None:
        """Return the current status row, or None before row bootstrap."""

        self._ensure_bootstrap()
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
SELECT graph_status,
       graph_generation_id,
       node_count,
       edge_count,
       key_label_counts,
       checksum,
       last_verified_at,
       last_reload_at,
       writer_lock_token
FROM {self._table_name}
WHERE status_key = %s
""",
                    (self._status_key,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return _status_from_row(row)

    @contextmanager
    def ready_read_lock(self) -> Iterator[None]:
        """Hold a shared PostgreSQL advisory lock for a live-graph read."""

        self._ensure_bootstrap()
        connection = self._connection_factory()
        locked = False
        lock_key: int | None = None
        try:
            with connection.cursor() as cursor:
                lock_key = self._resolve_advisory_lock_key(cursor)
                cursor.execute(
                    "SELECT pg_advisory_lock_shared(%s)",
                    (lock_key,),
                )
                locked = True
            connection.commit()
            yield
        except Exception:
            connection.rollback()
            raise
        finally:
            if locked:
                if lock_key is None:
                    # Invariant: lock_key is set inside the cursor block above
                    # before `locked` becomes True, so it cannot be None when
                    # entering this branch. Retained as explicit raise so
                    # the invariant survives `python -O`. Critical because
                    # this sits inside a PG-backed locking flow where None
                    # would corrupt the unlock SQL.
                    raise AssertionError(
                        "invariant: lock_key must be non-None when locked=True"
                    )
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_advisory_unlock_shared(%s)",
                            (lock_key,),
                        )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    connection.close()
            else:
                connection.close()

    def write_current_status(self, status: Neo4jGraphStatus) -> None:
        """Persist the current status row without comparing the previous value."""

        self._ensure_bootstrap()
        values = _status_write_values(status)
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                self._acquire_exclusive_status_lock(cursor)
                cursor.execute(
                    f"""
INSERT INTO {self._table_name} (
    status_key,
    graph_status,
    graph_generation_id,
    node_count,
    edge_count,
    key_label_counts,
    checksum,
    last_verified_at,
    last_reload_at,
    writer_lock_token
)
VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
ON CONFLICT (status_key) DO UPDATE SET
    graph_status = EXCLUDED.graph_status,
    graph_generation_id = EXCLUDED.graph_generation_id,
    node_count = EXCLUDED.node_count,
    edge_count = EXCLUDED.edge_count,
    key_label_counts = EXCLUDED.key_label_counts,
    checksum = EXCLUDED.checksum,
    last_verified_at = EXCLUDED.last_verified_at,
    last_reload_at = EXCLUDED.last_reload_at,
    writer_lock_token = EXCLUDED.writer_lock_token,
    updated_at = now()
""",
                    (self._status_key, *values),
                )

    def compare_and_write_current_status(
        self,
        *,
        expected_status: Neo4jGraphStatus | None,
        next_status: Neo4jGraphStatus,
    ) -> bool:
        """Atomically persist next_status only if the current row still matches."""

        self._ensure_bootstrap()
        next_values = _status_write_values(next_status)
        if expected_status is None:
            return self._insert_if_missing(next_values)

        expected_values = _status_write_values(expected_status)
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                self._acquire_exclusive_status_lock(cursor)
                cursor.execute(
                    f"""
UPDATE {self._table_name}
SET graph_status = %s,
    graph_generation_id = %s,
    node_count = %s,
    edge_count = %s,
    key_label_counts = %s::jsonb,
    checksum = %s,
    last_verified_at = %s,
    last_reload_at = %s,
    writer_lock_token = %s,
    updated_at = now()
WHERE status_key = %s
  AND graph_status = %s
  AND graph_generation_id = %s
  AND node_count = %s
  AND edge_count = %s
  AND key_label_counts = %s::jsonb
  AND checksum = %s
  AND last_verified_at IS NOT DISTINCT FROM %s
  AND last_reload_at IS NOT DISTINCT FROM %s
  AND writer_lock_token IS NOT DISTINCT FROM %s
RETURNING status_key
""",
                    (*next_values, self._status_key, *expected_values),
                )
                return cursor.fetchone() is not None

    def _insert_if_missing(self, next_values: tuple[Any, ...]) -> bool:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                self._acquire_exclusive_status_lock(cursor)
                cursor.execute(
                    f"""
INSERT INTO {self._table_name} (
    status_key,
    graph_status,
    graph_generation_id,
    node_count,
    edge_count,
    key_label_counts,
    checksum,
    last_verified_at,
    last_reload_at,
    writer_lock_token
)
VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
ON CONFLICT (status_key) DO NOTHING
RETURNING status_key
""",
                    (self._status_key, *next_values),
                )
                return cursor.fetchone() is not None

    def _acquire_exclusive_status_lock(self, cursor: Any) -> None:
        lock_key = self._resolve_advisory_lock_key(cursor)
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (lock_key,),
        )

    def _resolve_advisory_lock_key(self, cursor: Any) -> int:
        cursor.execute("SELECT %s::regclass::oid", (self._table_name,))
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL did not return a status table OID")
        return _advisory_lock_key(int(row[0]), self._status_key)

    def _ensure_bootstrap(self) -> None:
        if self._auto_bootstrap and not self._bootstrapped:
            self.bootstrap()

    def _normalize_legacy_syncing_status(self, cursor: Any) -> None:
        cursor.execute(
            f"""
UPDATE {self._table_name}
SET graph_status = 'failed',
    writer_lock_token = NULL,
    last_verified_at = NULL,
    checksum = CASE WHEN checksum = '' THEN 'failed' ELSE checksum END,
    updated_at = now()
WHERE graph_status = 'syncing'
""",
        )

    def _recreate_graph_status_check_constraint(self, cursor: Any) -> None:
        cursor.execute(
            """
SELECT conname
FROM pg_constraint
WHERE conrelid = %s::regclass
  AND contype = 'c'
  AND pg_get_constraintdef(oid) ILIKE '%%graph_status%%'
""",
            (self._table_name,),
        )
        constraint_names = [str(row[0]) for row in cursor.fetchall()]
        for constraint_name in constraint_names:
            cursor.execute(
                f"""
ALTER TABLE {self._table_name}
DROP CONSTRAINT IF EXISTS {_quote_identifier(constraint_name)}
""",
            )

        cursor.execute(
            f"""
ALTER TABLE {self._table_name}
ADD CONSTRAINT {_quote_identifier(_GRAPH_STATUS_CHECK_CONSTRAINT)}
CHECK (graph_status IN ('ready', 'rebuilding', 'failed'))
""",
        )

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        connection = self._connection_factory()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


PostgresStatusStore = PostgreSQLStatusStore


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _build_psycopg_connection_factory(
    database_url: str,
    *,
    connect_kwargs: dict[str, Any],
) -> Callable[[], Any]:
    try:
        psycopg = importlib.import_module("psycopg")
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised by integration envs.
        raise RuntimeError(
            "PostgreSQLStatusStore requires the optional 'psycopg' package",
        ) from exc

    psycopg_database_url = _normalize_psycopg_database_url(database_url)
    return lambda: psycopg.connect(psycopg_database_url, **connect_kwargs)


def _normalize_psycopg_database_url(database_url: str) -> str:
    sqlalchemy_psycopg_scheme = "postgresql+psycopg://"
    if database_url.startswith(sqlalchemy_psycopg_scheme):
        return "postgresql://" + database_url.removeprefix(sqlalchemy_psycopg_scheme)
    return database_url


def _quote_qualified_identifier(identifier: str) -> str:
    parts = identifier.split(".")
    if not parts or any(_IDENTIFIER_RE.fullmatch(part) is None for part in parts):
        raise ValueError(f"invalid PostgreSQL identifier: {identifier!r}")
    return ".".join(f'"{part}"' for part in parts)


def _quote_identifier(identifier: str) -> str:
    if _IDENTIFIER_RE.fullmatch(identifier) is None:
        raise ValueError(f"invalid PostgreSQL identifier: {identifier!r}")
    return f'"{identifier}"'


def _advisory_lock_key(relation_oid: int, status_key: str) -> int:
    lock_name = f"{relation_oid}\0{status_key}".encode()
    digest = hashlib.blake2b(
        lock_name,
        digest_size=8,
        person=b"ge-status",
    ).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


def _status_write_values(status: Neo4jGraphStatus) -> tuple[Any, ...]:
    return (
        status.graph_status,
        status.graph_generation_id,
        status.node_count,
        status.edge_count,
        json.dumps(status.key_label_counts, sort_keys=True, separators=(",", ":")),
        status.checksum,
        status.last_verified_at,
        status.last_reload_at,
        status.writer_lock_token,
    )


def _status_from_row(row: Any) -> Neo4jGraphStatus:
    (
        graph_status,
        graph_generation_id,
        node_count,
        edge_count,
        key_label_counts,
        checksum,
        last_verified_at,
        last_reload_at,
        writer_lock_token,
    ) = row
    if isinstance(key_label_counts, str):
        key_label_counts = json.loads(key_label_counts)

    return Neo4jGraphStatus(
        graph_status=graph_status,
        graph_generation_id=graph_generation_id,
        node_count=node_count,
        edge_count=edge_count,
        key_label_counts=dict(key_label_counts),
        checksum=checksum,
        last_verified_at=last_verified_at,
        last_reload_at=last_reload_at,
        writer_lock_token=writer_lock_token,
    )
