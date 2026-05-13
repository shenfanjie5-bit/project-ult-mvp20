"""Storage adapter interfaces for formal audit/replay writes."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
import json
from pathlib import Path
from typing import Any, Protocol

from audit_eval.contracts.audit_record import AuditRecord
from audit_eval.contracts.replay_record import ReplayRecord


_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MAX_RELATION_PARTS = 3
DEFAULT_MANAGED_AUDIT_TABLE = "audit_eval.audit_records"
DEFAULT_MANAGED_REPLAY_TABLE = "audit_eval.replay_records"
_MANAGED_AUDIT_COLUMNS = (
    "record_id",
    "cycle_id",
    "layer",
    "object_ref",
    "payload_json",
    "created_at",
)
_MANAGED_REPLAY_COLUMNS = (
    "replay_id",
    "cycle_id",
    "object_ref",
    "payload_json",
    "created_at",
)


class AuditStorageError(RuntimeError):
    """Raised when formal audit storage is not configured or cannot append."""


class AuditPersistenceError(RuntimeError):
    """Raised when a formal audit persistence operation fails."""

    def __init__(
        self,
        operation: str,
        partial_ids: Sequence[str] | None = None,
        message: str | None = None,
    ) -> None:
        self.operation = operation
        self.partial_ids = list(partial_ids or [])
        detail = (
            f"{message or f'{operation} failed'} "
            f"(operation={operation}, partial_ids={self.partial_ids!r})"
        )
        super().__init__(detail)


class FormalAuditStorageAdapter(Protocol):
    """Append-only storage boundary owned by the data-platform integration."""

    def append_audit_records(self, records: Sequence[AuditRecord]) -> list[str]:
        """Append validated formal audit records and return persisted ids."""

    def append_replay_records(self, records: Sequence[ReplayRecord]) -> list[str]:
        """Append validated formal replay records and return persisted ids."""


class BundleFormalAuditStorageAdapter(FormalAuditStorageAdapter, Protocol):
    """Retry-safe storage boundary for atomic or idempotent audit/replay bundles."""

    def append_audit_write_bundle(
        self,
        audit_records: Sequence[AuditRecord],
        replay_records: Sequence[ReplayRecord],
    ) -> tuple[list[str], list[str]]:
        """Persist one validated audit/replay bundle without split-write risk."""


class InMemoryFormalAuditStorageAdapter:
    """In-memory formal audit storage adapter for tests and Lite workflows."""

    def __init__(self) -> None:
        self.audit_rows: list[dict[str, Any]] = []
        self.replay_rows: list[dict[str, Any]] = []

    def append_audit_records(self, records: Sequence[AuditRecord]) -> list[str]:
        rows = [record.model_dump(mode="json") for record in records]
        self.audit_rows.extend(rows)
        return [record.record_id for record in records]

    def append_replay_records(self, records: Sequence[ReplayRecord]) -> list[str]:
        rows = [record.model_dump(mode="json") for record in records]
        self.replay_rows.extend(rows)
        return [record.replay_id for record in records]

    def append_audit_write_bundle(
        self,
        audit_records: Sequence[AuditRecord],
        replay_records: Sequence[ReplayRecord],
    ) -> tuple[list[str], list[str]]:
        audit_ids = self.append_audit_records(audit_records)
        replay_ids = self.append_replay_records(replay_records)
        return audit_ids, replay_ids


class ManagedDuckDBFormalAuditStorageAdapter:
    """Durable DuckDB-backed audit/replay storage with managed tables."""

    def __init__(
        self,
        duckdb_path: str | Path,
        audit_table: str = DEFAULT_MANAGED_AUDIT_TABLE,
        replay_table: str = DEFAULT_MANAGED_REPLAY_TABLE,
    ) -> None:
        if not duckdb_path:
            raise AuditStorageError("duckdb_path must be provided")
        self.duckdb_path = Path(duckdb_path).expanduser()
        self._audit_table_parts = _relation_name_parts(audit_table, "audit_table")
        self._replay_table_parts = _relation_name_parts(replay_table, "replay_table")

    def append_audit_records(self, records: Sequence[AuditRecord]) -> list[str]:
        if not records:
            return []

        rows = _audit_rows(records)

        def append(connection: Any) -> None:
            self._with_managed_tables(
                connection,
                lambda audit_table, replay_table: _append_idempotent_rows(
                    connection,
                    table=audit_table,
                    columns=_MANAGED_AUDIT_COLUMNS,
                    id_column="record_id",
                    payload_column="payload_json",
                    rows=rows,
                ),
            )

        self._with_connection(lambda connection: _run_in_transaction(connection, append))
        return [record.record_id for record in records]

    def append_replay_records(self, records: Sequence[ReplayRecord]) -> list[str]:
        if not records:
            return []

        rows = _replay_rows(records)

        def append(connection: Any) -> None:
            self._with_managed_tables(
                connection,
                lambda audit_table, replay_table: _append_idempotent_rows(
                    connection,
                    table=replay_table,
                    columns=_MANAGED_REPLAY_COLUMNS,
                    id_column="replay_id",
                    payload_column="payload_json",
                    rows=rows,
                ),
            )

        self._with_connection(lambda connection: _run_in_transaction(connection, append))
        return [record.replay_id for record in records]

    def append_audit_write_bundle(
        self,
        audit_records: Sequence[AuditRecord],
        replay_records: Sequence[ReplayRecord],
    ) -> tuple[list[str], list[str]]:
        audit_rows = _audit_rows(audit_records)
        replay_rows = _replay_rows(replay_records)

        def append(connection: Any) -> None:
            def write_rows(audit_table: str, replay_table: str) -> None:
                _append_idempotent_rows(
                    connection,
                    table=audit_table,
                    columns=_MANAGED_AUDIT_COLUMNS,
                    id_column="record_id",
                    payload_column="payload_json",
                    rows=audit_rows,
                )
                _append_idempotent_rows(
                    connection,
                    table=replay_table,
                    columns=_MANAGED_REPLAY_COLUMNS,
                    id_column="replay_id",
                    payload_column="payload_json",
                    rows=replay_rows,
                )

            self._with_managed_tables(connection, write_rows)

        self._with_connection(lambda connection: _run_in_transaction(connection, append))
        return (
            [record.record_id for record in audit_records],
            [record.replay_id for record in replay_records],
        )

    def _with_connection(self, callback: Callable[[Any], Any]) -> Any:
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise AuditStorageError("duckdb is required for managed audit storage") from exc

        connection = duckdb.connect(str(self.duckdb_path))
        try:
            return callback(connection)
        finally:
            connection.close()

    def _with_managed_tables(
        self,
        connection: Any,
        callback: Callable[[str, str], Any],
    ) -> Any:
        audit_table = _managed_relation_sql(connection, self._audit_table_parts)
        replay_table = _managed_relation_sql(connection, self._replay_table_parts)
        _ensure_managed_tables(
            connection,
            audit_table=audit_table,
            audit_table_parts=self._audit_table_parts,
            replay_table=replay_table,
            replay_table_parts=self._replay_table_parts,
        )
        return callback(audit_table, replay_table)


class DuckDBReplayRepository:
    """Replay repository reading records from managed DuckDB audit storage."""

    def __init__(
        self,
        duckdb_path: str | Path,
        audit_table: str = DEFAULT_MANAGED_AUDIT_TABLE,
        replay_table: str = DEFAULT_MANAGED_REPLAY_TABLE,
    ) -> None:
        if not duckdb_path:
            raise AuditStorageError("duckdb_path must be provided")
        self.duckdb_path = Path(duckdb_path).expanduser()
        self._audit_table_parts = _relation_name_parts(audit_table, "audit_table")
        self._replay_table_parts = _relation_name_parts(replay_table, "replay_table")

    def get_replay_record(
        self,
        cycle_id: str,
        object_ref: str,
    ) -> ReplayRecord | None:
        rows = self._fetch_all(
            lambda connection: f"""
                SELECT payload_json
                FROM {_managed_relation_sql(connection, self._replay_table_parts)}
                WHERE cycle_id = ? AND object_ref = ?
                ORDER BY created_at DESC, replay_id DESC
                """,
            [cycle_id, object_ref],
        )
        if len(rows) > 1:
            from audit_eval.audit.errors import ReplayQueryError

            raise ReplayQueryError(
                "Expected at most one replay_record for "
                f"cycle_id={cycle_id!r}, object_ref={object_ref!r}"
            )
        return _replay_record_from_payload(rows[0][0]) if rows else None

    def get_replay_record_by_id(self, replay_id: str) -> ReplayRecord | None:
        rows = self._fetch_all(
            lambda connection: f"""
                SELECT payload_json
                FROM {_managed_relation_sql(connection, self._replay_table_parts)}
                WHERE replay_id = ?
                """,
            [replay_id],
        )
        return _replay_record_from_payload(rows[0][0]) if rows else None

    def get_audit_record_by_id(self, record_id: str) -> AuditRecord | None:
        rows = self._fetch_all(
            lambda connection: f"""
                SELECT payload_json
                FROM {_managed_relation_sql(connection, self._audit_table_parts)}
                WHERE record_id = ?
                """,
            [record_id],
        )
        return _audit_record_from_payload(rows[0][0]) if rows else None

    def get_audit_records(self, record_ids: Sequence[str]) -> list[AuditRecord]:
        requested_ids = list(record_ids)
        if not requested_ids:
            return []

        placeholders = ", ".join("?" for _ in requested_ids)
        rows = self._fetch_all(
            lambda connection: f"""
                SELECT payload_json
                FROM {_managed_relation_sql(connection, self._audit_table_parts)}
                WHERE record_id IN ({placeholders})
                """,
            requested_ids,
        )
        records_by_id = {
            record.record_id: record
            for row in rows
            for record in [_audit_record_from_payload(row[0])]
        }
        return [
            records_by_id[record_id]
            for record_id in requested_ids
            if record_id in records_by_id
        ]

    def _fetch_all(
        self,
        query_factory: Callable[[Any], str],
        parameters: Sequence[object],
    ) -> list[tuple[Any, ...]]:
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise AuditStorageError("duckdb is required for replay queries") from exc

        connection = duckdb.connect(str(self.duckdb_path), read_only=True)
        try:
            sql = query_factory(connection)
            return connection.execute(sql, list(parameters)).fetchall()
        finally:
            connection.close()


class DuckDBFormalAuditStorageAdapter:
    """Append-only DuckDB adapter for existing formal audit/replay tables."""

    def __init__(
        self,
        connection: Any,
        audit_table: str,
        replay_table: str,
    ) -> None:
        if connection is None:
            raise AuditStorageError("DuckDB connection must be provided")
        if not audit_table:
            raise AuditStorageError("audit_table must be provided")
        if not replay_table:
            raise AuditStorageError("replay_table must be provided")

        self.connection = connection
        self.audit_table = _quote_relation_name(audit_table, "audit_table")
        self.replay_table = _quote_relation_name(replay_table, "replay_table")

    def append_audit_records(self, records: Sequence[AuditRecord]) -> list[str]:
        rows = [record.model_dump(mode="json") for record in records]
        self._append_rows(self.audit_table, rows)
        return [record.record_id for record in records]

    def append_replay_records(self, records: Sequence[ReplayRecord]) -> list[str]:
        rows = [record.model_dump(mode="json") for record in records]
        self._append_rows(self.replay_table, rows)
        return [record.replay_id for record in records]

    def _append_rows(self, table_name: str, rows: Sequence[dict[str, Any]]) -> None:
        if not rows:
            return

        columns = tuple(rows[0])
        column_sql = ", ".join(_quote_identifier(column) for column in columns)
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})"
        parameters = [tuple(row[column] for column in columns) for row in rows]

        try:
            self.connection.executemany(sql, parameters)
        except Exception as exc:  # pragma: no cover - exercised through writer tests
            raise AuditStorageError(f"Failed to append rows to {table_name}") from exc


def _quote_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def _quote_relation_name(relation_name: str, config_name: str) -> str:
    parts = _relation_name_parts(relation_name, config_name)
    return ".".join(_quote_identifier(part) for part in parts)


def _relation_name_parts(relation_name: str, config_name: str) -> tuple[str, ...]:
    parts = tuple(relation_name.split("."))
    if (
        not parts
        or len(parts) > _MAX_RELATION_PARTS
        or any(not _IDENTIFIER_RE.fullmatch(part) for part in parts)
    ):
        raise AuditStorageError(
            f"{config_name} must be 1-{_MAX_RELATION_PARTS} dot-separated "
            "SQL identifiers matching [A-Za-z_][A-Za-z0-9_]*"
        )
    return parts


def _ensure_managed_tables(
    connection: Any,
    *,
    audit_table: str,
    audit_table_parts: Sequence[str],
    replay_table: str,
    replay_table_parts: Sequence[str],
) -> None:
    _ensure_schema(connection, audit_table_parts)
    _ensure_schema(connection, replay_table_parts)
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {audit_table} (
            record_id TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL,
            layer TEXT NOT NULL,
            object_ref TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {replay_table} (
            replay_id TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL,
            object_ref TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )


def _ensure_schema(connection: Any, relation_parts: Sequence[str]) -> None:
    if len(relation_parts) <= 1:
        return
    schema_name = _managed_schema_sql(connection, relation_parts)
    connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")


def _managed_schema_sql(connection: Any, relation_parts: Sequence[str]) -> str:
    if len(relation_parts) == _MAX_RELATION_PARTS:
        return ".".join(_quote_identifier(part) for part in relation_parts[:-1])
    database_name = str(connection.execute("SELECT current_database()").fetchone()[0])
    return ".".join(
        (
            _quote_identifier(database_name),
            _quote_identifier(relation_parts[0]),
        )
    )


def _managed_relation_sql(connection: Any, relation_parts: Sequence[str]) -> str:
    if len(relation_parts) <= 1:
        return ".".join(_quote_identifier(part) for part in relation_parts)
    if len(relation_parts) == _MAX_RELATION_PARTS:
        return ".".join(_quote_identifier(part) for part in relation_parts)
    database_name = str(connection.execute("SELECT current_database()").fetchone()[0])
    parts = [_quote_identifier(database_name)]
    parts.extend(_quote_identifier(part) for part in relation_parts)
    return ".".join(parts)


def _audit_rows(records: Sequence[AuditRecord]) -> list[tuple[object, ...]]:
    return [
        (
            record.record_id,
            record.cycle_id,
            record.layer,
            record.object_ref,
            _record_payload_json(record),
            record.created_at,
        )
        for record in records
    ]


def _replay_rows(records: Sequence[ReplayRecord]) -> list[tuple[object, ...]]:
    return [
        (
            record.replay_id,
            record.cycle_id,
            record.object_ref,
            _record_payload_json(record),
            record.created_at,
        )
        for record in records
    ]


def _run_in_transaction(connection: Any, callback: Callable[[Any], Any]) -> Any:
    connection.execute("BEGIN TRANSACTION")
    try:
        result = callback(connection)
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")
    return result


def _append_idempotent_rows(
    connection: Any,
    *,
    table: str,
    columns: Sequence[str],
    id_column: str,
    payload_column: str,
    rows: Sequence[Sequence[object]],
) -> None:
    if not rows:
        return

    id_index = columns.index(id_column)
    payload_index = columns.index(payload_column)
    id_sql = _quote_identifier(id_column)
    payload_sql = _quote_identifier(payload_column)
    missing_rows: list[Sequence[object]] = []
    for row in rows:
        row_id = str(row[id_index])
        existing = connection.execute(
            f"SELECT {payload_sql} FROM {table} WHERE {id_sql} = ?",
            [row_id],
        ).fetchone()
        if existing is None:
            missing_rows.append(row)
            continue
        if existing[0] != row[payload_index]:
            raise AuditStorageError(
                f"managed audit storage row {row_id!r} already exists "
                "with a different payload"
            )

    if not missing_rows:
        return

    column_sql = ", ".join(_quote_identifier(column) for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
        list(missing_rows),
    )


def _record_payload_json(record: AuditRecord | ReplayRecord) -> str:
    return json.dumps(
        record.model_dump(mode="json"),
        allow_nan=False,
        sort_keys=True,
    )


def _audit_record_from_payload(payload_json: object) -> AuditRecord:
    return AuditRecord.model_validate(_payload_from_json(payload_json))


def _replay_record_from_payload(payload_json: object) -> ReplayRecord:
    return ReplayRecord.model_validate(_payload_from_json(payload_json))


def _payload_from_json(payload_json: object) -> Any:
    if not isinstance(payload_json, str):
        raise AuditStorageError("managed audit payload_json must be a string")
    return json.loads(payload_json)


__all__ = [
    "AuditPersistenceError",
    "AuditStorageError",
    "DEFAULT_MANAGED_AUDIT_TABLE",
    "DEFAULT_MANAGED_REPLAY_TABLE",
    "BundleFormalAuditStorageAdapter",
    "DuckDBReplayRepository",
    "DuckDBFormalAuditStorageAdapter",
    "FormalAuditStorageAdapter",
    "InMemoryFormalAuditStorageAdapter",
    "ManagedDuckDBFormalAuditStorageAdapter",
]
