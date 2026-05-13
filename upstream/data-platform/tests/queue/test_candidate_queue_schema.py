from __future__ import annotations

import json
import os
from collections.abc import Generator
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, datetime
from typing import Any, get_args
from uuid import uuid4

import pytest

from data_platform.queue import (
    CANDIDATE_QUEUE_TABLE,
    INGEST_METADATA_VIEW,
    CandidatePayloadType,
    CandidateQueueItem,
    IngestMetadataRecord,
    ValidationStatus,
)


EXPECTED_QUEUE_COLUMNS = [
    "id",
    "payload_type",
    "payload",
    "submitted_by",
    "submitted_at",
    "ingest_seq",
    "validation_status",
    "rejection_reason",
]
EXPECTED_INGEST_METADATA_COLUMNS = [
    "candidate_id",
    "payload_type",
    "submitted_by",
    "submitted_at",
    "ingest_seq",
    "validation_status",
    "rejection_reason",
]


@pytest.fixture()
def postgres_dsn() -> Generator[str]:
    admin_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DP_PG_DSN")
    if not admin_dsn:
        pytest.skip("PostgreSQL candidate queue schema tests require DATABASE_URL or DP_PG_DSN")

    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL candidate queue schema tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL candidate queue schema tests require the migration runner",
    )
    make_url = pytest.importorskip(
        "sqlalchemy.engine",
        reason="PostgreSQL candidate queue schema tests require SQLAlchemy",
    ).make_url
    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="PostgreSQL candidate queue schema tests require SQLAlchemy",
    ).SQLAlchemyError

    admin_engine = _create_engine(admin_dsn, isolation_level="AUTOCOMMIT")
    database_name = f"dp_candidate_queue_test_{uuid4().hex}"
    try:
        with admin_engine.connect() as connection:
            connection.execute(sqlalchemy.text(f'CREATE DATABASE "{database_name}"'))
    except sqlalchemy_error as exc:
        admin_engine.dispose()
        pytest.skip(
            "PostgreSQL candidate queue schema tests require permission to create "
            f"test databases: {exc}"
        )

    test_dsn = (
        make_url(runner_module._sqlalchemy_postgres_uri(admin_dsn))
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )
    try:
        yield test_dsn
    finally:
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
            connection.execute(sqlalchemy.text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()


@pytest.fixture()
def migrated_postgres_dsn(postgres_dsn: str) -> str:
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL candidate queue schema tests require the migration runner",
    )
    applied_versions = runner_module.MigrationRunner().apply_pending(postgres_dsn)
    assert applied_versions == ["0001", "0002", "0003", "0004", "0005", "0006"]
    assert runner_module.MigrationRunner().apply_pending(postgres_dsn) == []
    return postgres_dsn


def test_queue_models_expose_contract_types_and_constants() -> None:
    assert CANDIDATE_QUEUE_TABLE == "data_platform.candidate_queue"
    assert INGEST_METADATA_VIEW == "data_platform.ingest_metadata"
    assert get_args(CandidatePayloadType) == ("Ex-0", "Ex-1", "Ex-2", "Ex-3")
    assert get_args(ValidationStatus) == ("pending", "accepted", "rejected")

    assert is_dataclass(CandidateQueueItem)
    assert is_dataclass(IngestMetadataRecord)
    assert [field.name for field in fields(CandidateQueueItem)] == EXPECTED_QUEUE_COLUMNS
    assert [field.name for field in fields(IngestMetadataRecord)] == (
        EXPECTED_INGEST_METADATA_COLUMNS
    )
    assert CandidateQueueItem.__slots__ == tuple(EXPECTED_QUEUE_COLUMNS)
    assert IngestMetadataRecord.__slots__ == tuple(EXPECTED_INGEST_METADATA_COLUMNS)

    item = CandidateQueueItem(
        id=1,
        payload_type="Ex-1",
        payload={"candidate": "alpha"},
        submitted_by="subsystem-a",
        submitted_at=datetime.now(UTC),
        ingest_seq=1,
        validation_status="pending",
        rejection_reason=None,
    )
    with pytest.raises(FrozenInstanceError):
        item.ingest_seq = 2


@pytest.mark.parametrize("forbidden_key", ["submitted_at", "ingest_seq"])
def test_candidate_queue_item_rejects_ingest_metadata_in_payload(forbidden_key: str) -> None:
    with pytest.raises(ValueError, match="producer payload must not include"):
        CandidateQueueItem(
            id=1,
            payload_type="Ex-1",
            payload={forbidden_key: "not producer-owned"},
            submitted_by="subsystem-a",
            submitted_at=datetime.now(UTC),
            ingest_seq=1,
            validation_status="pending",
            rejection_reason=None,
        )


def test_candidate_queue_item_requires_payload_mapping() -> None:
    with pytest.raises(TypeError, match="payload must be a JSON object mapping"):
        CandidateQueueItem(
            id=1,
            payload_type="Ex-1",
            payload=["not", "an", "object"],  # type: ignore[arg-type]
            submitted_by="subsystem-a",
            submitted_at=datetime.now(UTC),
            ingest_seq=1,
            validation_status="pending",
            rejection_reason=None,
        )


def test_candidate_queue_item_payload_is_defensively_copied_and_read_only() -> None:
    producer_payload = {"candidate": "alpha"}
    item = CandidateQueueItem(
        id=1,
        payload_type="Ex-1",
        payload=producer_payload,
        submitted_by="subsystem-a",
        submitted_at=datetime.now(UTC),
        ingest_seq=1,
        validation_status="pending",
        rejection_reason=None,
    )

    producer_payload["submitted_at"] = "not producer-owned"

    assert dict(item.payload) == {"candidate": "alpha"}
    with pytest.raises(TypeError):
        item.payload["ingest_seq"] = 2  # type: ignore[index]
    assert "ingest_seq" not in item.payload


def test_migration_creates_candidate_queue_schema(migrated_postgres_dsn: str) -> None:
    engine = _create_engine(migrated_postgres_dsn)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(
                    _text("SELECT to_regclass('data_platform.candidate_queue')")
                ).scalar_one()
                == "data_platform.candidate_queue"
            )
            assert (
                connection.execute(
                    _text("SELECT to_regclass('data_platform.ingest_metadata')")
                ).scalar_one()
                == "data_platform.ingest_metadata"
            )
            assert _enum_labels(connection, "candidate_payload_type") == [
                "Ex-0",
                "Ex-1",
                "Ex-2",
                "Ex-3",
            ]
            assert _enum_labels(connection, "validation_status") == [
                "pending",
                "accepted",
                "rejected",
            ]

            table_columns = connection.execute(
                _text(
                    """
                    SELECT column_name, data_type, udt_schema, udt_name, is_nullable,
                           column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'data_platform'
                      AND table_name = 'candidate_queue'
                    ORDER BY ordinal_position
                    """
                )
            ).mappings()
            columns = {str(row["column_name"]): row for row in table_columns}
            assert list(columns) == EXPECTED_QUEUE_COLUMNS
            assert columns["payload_type"]["udt_name"] == "candidate_payload_type"
            assert columns["payload"]["data_type"] == "jsonb"
            assert columns["validation_status"]["udt_name"] == "validation_status"
            assert columns["submitted_at"]["column_default"] == "now()"
            assert str(columns["ingest_seq"]["column_default"]).startswith(
                "nextval('data_platform.candidate_queue_ingest_seq_seq'"
            )
            assert columns["validation_status"]["column_default"] == (
                "'pending'::data_platform.validation_status"
            )
            for column_name in EXPECTED_QUEUE_COLUMNS:
                expected_nullable = "YES" if column_name == "rejection_reason" else "NO"
                assert columns[column_name]["is_nullable"] == expected_nullable

            assert _view_columns(connection) == EXPECTED_INGEST_METADATA_COLUMNS
            assert {
                str(row[0])
                for row in connection.execute(
                    _text(
                        """
                        SELECT constraint_name
                        FROM information_schema.table_constraints
                        WHERE table_schema = 'data_platform'
                          AND table_name = 'candidate_queue'
                        """
                    )
                )
            } >= {
                "candidate_queue_pkey",
                "candidate_queue_ingest_seq_key",
                "candidate_queue_payload_is_object",
                "candidate_queue_payload_excludes_ingest_metadata",
            }
            assert {
                str(row[0])
                for row in connection.execute(
                    _text(
                        """
                        SELECT indexname
                        FROM pg_indexes
                        WHERE schemaname = 'data_platform'
                          AND tablename = 'candidate_queue'
                        """
                    )
                )
            } >= {
                "candidate_queue_pkey",
                "candidate_queue_ingest_seq_key",
                "candidate_queue_ex3_delta_id_key",
            }
            ex3_delta_index = connection.execute(
                _text(
                    """
                    SELECT indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'data_platform'
                      AND tablename = 'candidate_queue'
                      AND indexname = 'candidate_queue_ex3_delta_id_key'
                    """
                )
            ).scalar_one()
            assert "(payload ->> 'delta_id'::text)" in str(ex3_delta_index)
            assert "WHERE ((payload_type = 'Ex-3'::data_platform.candidate_payload_type)" in str(
                ex3_delta_index
            )
            assert "jsonb_typeof((payload -> 'delta_id'::text)) = 'string'::text" in str(
                ex3_delta_index
            )
            assert "(payload ->> 'delta_id'::text) <> ''::text" in str(ex3_delta_index)
    finally:
        engine.dispose()


def test_candidate_queue_ex3_delta_unique_index_matches_idempotency_domain(
    migrated_postgres_dsn: str,
) -> None:
    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="PostgreSQL candidate queue schema tests require SQLAlchemy",
    ).SQLAlchemyError
    engine = _create_engine(migrated_postgres_dsn)
    insert_sql = _text(
        """
        INSERT INTO data_platform.candidate_queue (
            payload_type,
            payload,
            submitted_by
        )
        VALUES ('Ex-3', CAST(:payload AS jsonb), 'subsystem-holdings')
        """
    )

    try:
        with engine.begin() as connection:
            connection.execute(
                insert_sql,
                {"payload": json.dumps({"delta_id": "holdings-delta-unique"})},
            )

        with pytest.raises(sqlalchemy_error):
            with engine.begin() as connection:
                connection.execute(
                    insert_sql,
                    {"payload": json.dumps({"delta_id": "holdings-delta-unique"})},
                )

        with engine.begin() as connection:
            for delta_id in ("", 42):
                connection.execute(insert_sql, {"payload": json.dumps({"delta_id": delta_id})})
                connection.execute(insert_sql, {"payload": json.dumps({"delta_id": delta_id})})
    finally:
        engine.dispose()


def test_candidate_queue_defaults_and_metadata_view(migrated_postgres_dsn: str) -> None:
    engine = _create_engine(migrated_postgres_dsn)
    try:
        with engine.begin() as connection:
            first = connection.execute(
                _text(
                    """
                    INSERT INTO data_platform.candidate_queue (
                        payload_type,
                        payload,
                        submitted_by
                    )
                    VALUES ('Ex-1', CAST(:payload AS jsonb), :submitted_by)
                    RETURNING id, submitted_at, ingest_seq, validation_status, rejection_reason
                    """
                ),
                {"payload": '{"candidate":"alpha"}', "submitted_by": "subsystem-a"},
            ).mappings().one()
            second = connection.execute(
                _text(
                    """
                    INSERT INTO data_platform.candidate_queue (
                        payload_type,
                        payload,
                        submitted_by
                    )
                    VALUES ('Ex-2', CAST(:payload AS jsonb), :submitted_by)
                    RETURNING id, submitted_at, ingest_seq, validation_status
                    """
                ),
                {"payload": '{"candidate":"beta"}', "submitted_by": "subsystem-b"},
            ).mappings().one()

            assert first["submitted_at"] is not None
            assert first["ingest_seq"] is not None
            assert int(second["ingest_seq"]) > int(first["ingest_seq"])
            assert first["validation_status"] == "pending"
            assert first["rejection_reason"] is None

            metadata = connection.execute(
                _text(
                    """
                    SELECT *
                    FROM data_platform.ingest_metadata
                    WHERE candidate_id = :candidate_id
                    """
                ),
                {"candidate_id": first["id"]},
            ).mappings().one()
            assert list(metadata.keys()) == EXPECTED_INGEST_METADATA_COLUMNS
            assert metadata["candidate_id"] == first["id"]
            assert metadata["payload_type"] == "Ex-1"
            assert metadata["submitted_by"] == "subsystem-a"
            assert metadata["submitted_at"] == first["submitted_at"]
            assert metadata["ingest_seq"] == first["ingest_seq"]
            assert metadata["validation_status"] == "pending"
            assert metadata["rejection_reason"] is None
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("column_name", "bad_value"),
    [("payload_type", "Ex-4"), ("validation_status", "done")],
)
def test_candidate_queue_rejects_invalid_enum_values(
    migrated_postgres_dsn: str,
    column_name: str,
    bad_value: str,
) -> None:
    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="PostgreSQL candidate queue schema tests require SQLAlchemy",
    ).SQLAlchemyError
    engine = _create_engine(migrated_postgres_dsn)
    try:
        with pytest.raises(sqlalchemy_error):
            with engine.begin() as connection:
                connection.execute(
                    _text(_invalid_enum_insert_sql(column_name)),
                    {"payload": '{"candidate":"alpha"}', "bad_value": bad_value},
                )
    finally:
        engine.dispose()


@pytest.mark.parametrize("forbidden_key", ["submitted_at", "ingest_seq"])
def test_candidate_queue_rejects_payload_ingest_metadata_keys(
    migrated_postgres_dsn: str,
    forbidden_key: str,
) -> None:
    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="PostgreSQL candidate queue schema tests require SQLAlchemy",
    ).SQLAlchemyError
    engine = _create_engine(migrated_postgres_dsn)
    try:
        with pytest.raises(sqlalchemy_error):
            with engine.begin() as connection:
                connection.execute(
                    _text(
                        """
                        INSERT INTO data_platform.candidate_queue (
                            payload_type,
                            payload,
                            submitted_by
                        )
                        VALUES ('Ex-1', CAST(:payload AS jsonb), 'subsystem-a')
                        """
                    ),
                    {"payload": f'{{"{forbidden_key}":"not producer-owned"}}'},
                )
    finally:
        engine.dispose()


def _create_engine(dsn: str, **kwargs: object) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL candidate queue schema tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL candidate queue schema tests require the migration runner",
    )
    return sqlalchemy.create_engine(runner_module._sqlalchemy_postgres_uri(dsn), **kwargs)


def _invalid_enum_insert_sql(column_name: str) -> str:
    if column_name == "payload_type":
        return """
            INSERT INTO data_platform.candidate_queue (
                payload_type,
                payload,
                submitted_by
            )
            VALUES (:bad_value, CAST(:payload AS jsonb), 'subsystem-a')
            """
    if column_name == "validation_status":
        return """
            INSERT INTO data_platform.candidate_queue (
                payload_type,
                payload,
                submitted_by,
                validation_status
            )
            VALUES ('Ex-1', CAST(:payload AS jsonb), 'subsystem-a', :bad_value)
            """
    msg = f"unsupported enum column for candidate_queue test: {column_name}"
    raise ValueError(msg)


def _text(sql: str) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL candidate queue schema tests require SQLAlchemy",
    )
    return sqlalchemy.text(sql)


def _enum_labels(connection: Any, type_name: str) -> list[str]:
    rows = connection.execute(
        _text(
            """
            SELECT pg_enum.enumlabel
            FROM pg_enum
            JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
            JOIN pg_namespace ON pg_namespace.oid = pg_type.typnamespace
            WHERE pg_namespace.nspname = 'data_platform'
              AND pg_type.typname = :type_name
            ORDER BY pg_enum.enumsortorder
            """
        ),
        {"type_name": type_name},
    ).scalars()
    return [str(row) for row in rows]


def _view_columns(connection: Any) -> list[str]:
    rows = connection.execute(
        _text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'data_platform'
              AND table_name = 'ingest_metadata'
            ORDER BY ordinal_position
            """
        )
    ).scalars()
    return [str(row) for row in rows]
