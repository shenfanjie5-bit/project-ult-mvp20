from __future__ import annotations

import os
from collections.abc import Generator
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, date, datetime
from typing import Any, get_args
from uuid import uuid4

import pytest

from data_platform.cycle import (
    CYCLE_ID_PATTERN,
    CYCLE_METADATA_TABLE,
    CycleAlreadyExists,
    CycleMetadata,
    CycleNotFound,
    CycleStatus,
    InvalidCycleId,
    InvalidCycleTransition,
    create_cycle,
    get_cycle,
    list_cycles,
    publish_manifest,
    transition_cycle_status,
)


EXPECTED_CYCLE_METADATA_COLUMNS = [
    "cycle_id",
    "cycle_date",
    "status",
    "cutoff_submitted_at",
    "cutoff_ingest_seq",
    "candidate_count",
    "selection_frozen_at",
    "created_at",
    "updated_at",
]
EXPECTED_CYCLE_STATUSES = (
    "pending",
    "phase0",
    "phase1",
    "phase2",
    "phase3",
    "published",
    "failed",
)


@pytest.fixture()
def postgres_dsn() -> Generator[str]:
    admin_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DP_PG_DSN")
    if not admin_dsn:
        pytest.skip("PostgreSQL cycle metadata tests require DATABASE_URL or DP_PG_DSN")

    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL cycle metadata tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL cycle metadata tests require the migration runner",
    )
    make_url = pytest.importorskip(
        "sqlalchemy.engine",
        reason="PostgreSQL cycle metadata tests require SQLAlchemy",
    ).make_url
    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="PostgreSQL cycle metadata tests require SQLAlchemy",
    ).SQLAlchemyError

    admin_engine = _create_engine(admin_dsn, isolation_level="AUTOCOMMIT")
    database_name = f"dp_cycle_metadata_test_{uuid4().hex}"
    try:
        with admin_engine.connect() as connection:
            connection.execute(sqlalchemy.text(f'CREATE DATABASE "{database_name}"'))
    except sqlalchemy_error as exc:
        admin_engine.dispose()
        pytest.skip(
            "PostgreSQL cycle metadata tests require permission to create "
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
        reason="PostgreSQL cycle metadata tests require the migration runner",
    )
    applied_versions = runner_module.MigrationRunner().apply_pending(postgres_dsn)
    assert applied_versions == ["0001", "0002", "0003", "0004", "0005", "0006"]
    assert runner_module.MigrationRunner().apply_pending(postgres_dsn) == []
    return postgres_dsn


@pytest.fixture()
def cycle_repository_env(
    migrated_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[str]:
    monkeypatch.setenv("DP_PG_DSN", migrated_postgres_dsn)
    yield migrated_postgres_dsn


def test_cycle_models_expose_contract_types_and_constants() -> None:
    assert CYCLE_METADATA_TABLE == "data_platform.cycle_metadata"
    assert CYCLE_ID_PATTERN.fullmatch("CYCLE_20260416") is not None
    assert CYCLE_ID_PATTERN.fullmatch("cycle_20260416") is None
    assert get_args(CycleStatus) == EXPECTED_CYCLE_STATUSES

    assert is_dataclass(CycleMetadata)
    assert [field.name for field in fields(CycleMetadata)] == EXPECTED_CYCLE_METADATA_COLUMNS
    assert CycleMetadata.__slots__ == tuple(EXPECTED_CYCLE_METADATA_COLUMNS)

    metadata = _cycle_metadata()
    with pytest.raises(FrozenInstanceError):
        metadata.status = "phase0"  # type: ignore[misc]


@pytest.mark.parametrize(
    "cycle_id",
    ["20260416", "CYCLE_2026041", "CYCLE_20261301"],
)
def test_cycle_metadata_rejects_invalid_cycle_id(cycle_id: str) -> None:
    with pytest.raises(InvalidCycleId):
        _cycle_metadata(cycle_id=cycle_id)


def test_cycle_metadata_rejects_mismatched_cycle_date() -> None:
    with pytest.raises(InvalidCycleId):
        _cycle_metadata(cycle_id="CYCLE_20260416", cycle_date=date(2026, 4, 17))


def test_cycle_metadata_rejects_invalid_status() -> None:
    with pytest.raises(ValueError, match="status must be one of"):
        _cycle_metadata(status="unknown")  # type: ignore[arg-type]


@pytest.mark.parametrize("cycle_id", ["bad", "CYCLE_2026041", "CYCLE_20261301"])
def test_repository_rejects_invalid_cycle_id_before_database(cycle_id: str) -> None:
    with pytest.raises(InvalidCycleId):
        get_cycle(cycle_id)

    with pytest.raises(InvalidCycleId):
        transition_cycle_status(cycle_id, "phase0")


@pytest.mark.parametrize("limit", [0, -1, 501, True, "10"])
def test_list_cycles_rejects_invalid_limit_before_database(limit: object) -> None:
    with pytest.raises(ValueError, match="limit must be an integer"):
        list_cycles(limit=limit)  # type: ignore[arg-type]


def test_transition_rejects_invalid_target_status_before_database() -> None:
    with pytest.raises(InvalidCycleTransition):
        transition_cycle_status("CYCLE_20260416", "unknown")  # type: ignore[arg-type]


def test_migration_creates_cycle_metadata_schema(migrated_postgres_dsn: str) -> None:
    engine = _create_engine(migrated_postgres_dsn)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(
                    _text("SELECT to_regclass('data_platform.cycle_metadata')")
                ).scalar_one()
                == "data_platform.cycle_metadata"
            )
            assert _enum_labels(connection, "cycle_status") == list(EXPECTED_CYCLE_STATUSES)

            table_columns = connection.execute(
                _text(
                    """
                    SELECT column_name, data_type, udt_name, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'data_platform'
                      AND table_name = 'cycle_metadata'
                    ORDER BY ordinal_position
                    """
                )
            ).mappings()
            columns = {str(row["column_name"]): row for row in table_columns}
            assert list(columns) == EXPECTED_CYCLE_METADATA_COLUMNS
            assert columns["cycle_id"]["data_type"] == "text"
            assert columns["cycle_date"]["data_type"] == "date"
            assert columns["status"]["udt_name"] == "cycle_status"
            assert columns["status"]["column_default"] == (
                "'pending'::data_platform.cycle_status"
            )
            assert columns["cutoff_submitted_at"]["is_nullable"] == "YES"
            assert columns["cutoff_ingest_seq"]["is_nullable"] == "YES"
            assert columns["candidate_count"]["column_default"] == "0"
            assert columns["selection_frozen_at"]["is_nullable"] == "YES"
            assert columns["created_at"]["column_default"] == "now()"
            assert columns["updated_at"]["column_default"] == "now()"

            for column_name in EXPECTED_CYCLE_METADATA_COLUMNS:
                expected_nullable = (
                    "YES"
                    if column_name
                    in {
                        "cutoff_submitted_at",
                        "cutoff_ingest_seq",
                        "selection_frozen_at",
                    }
                    else "NO"
                )
                assert columns[column_name]["is_nullable"] == expected_nullable

            assert {
                str(row[0])
                for row in connection.execute(
                    _text(
                        """
                        SELECT constraint_name
                        FROM information_schema.table_constraints
                        WHERE table_schema = 'data_platform'
                          AND table_name = 'cycle_metadata'
                        """
                    )
                )
            } >= {
                "cycle_metadata_pkey",
                "cycle_metadata_cycle_date_key",
                "cycle_metadata_cycle_id_format",
                "cycle_metadata_candidate_count_nonnegative",
            }
    finally:
        engine.dispose()


def test_create_cycle_returns_pending_cycle_and_rejects_duplicate(
    cycle_repository_env: str,
) -> None:
    created = create_cycle(date(2026, 4, 16))

    assert created.cycle_id == "CYCLE_20260416"
    assert created.cycle_date == date(2026, 4, 16)
    assert created.status == "pending"
    assert created.cutoff_submitted_at is None
    assert created.cutoff_ingest_seq is None
    assert created.candidate_count == 0
    assert created.selection_frozen_at is None

    assert get_cycle("CYCLE_20260416") == created

    with pytest.raises(CycleAlreadyExists):
        create_cycle(date(2026, 4, 16))

    assert _cycle_count(cycle_repository_env) == 1


def test_get_cycle_raises_not_found_for_valid_missing_cycle(
    cycle_repository_env: str,
) -> None:
    with pytest.raises(CycleNotFound):
        get_cycle("CYCLE_20260416")


def test_list_cycles_orders_newest_first_and_filters_status(
    cycle_repository_env: str,
) -> None:
    create_cycle(date(2026, 4, 16))
    create_cycle(date(2026, 4, 17))
    transition_cycle_status("CYCLE_20260417", "phase0")

    cycles = list_cycles()

    assert [cycle.cycle_id for cycle in cycles] == [
        "CYCLE_20260417",
        "CYCLE_20260416",
    ]
    assert [cycle.cycle_id for cycle in list_cycles(limit=1)] == ["CYCLE_20260417"]
    assert [cycle.cycle_id for cycle in list_cycles(status="phase0")] == [
        "CYCLE_20260417"
    ]


def test_legal_cycle_status_transitions_pass(cycle_repository_env: str) -> None:
    create_cycle(date(2026, 4, 16))
    cycle_id = "CYCLE_20260416"

    for status in ["phase0", "phase1", "phase2", "phase3"]:
        metadata = transition_cycle_status(cycle_id, status)
        assert metadata.status == status

    assert get_cycle(cycle_id).status == "phase3"


def test_direct_pending_to_published_transition_fails(cycle_repository_env: str) -> None:
    create_cycle(date(2026, 4, 16))

    with pytest.raises(InvalidCycleTransition):
        transition_cycle_status("CYCLE_20260416", "published")

    assert get_cycle("CYCLE_20260416").status == "pending"


@pytest.mark.parametrize(
    ("cycle_date", "path"),
    [
        (date(2026, 4, 16), []),
        (date(2026, 4, 17), ["phase0"]),
        (date(2026, 4, 18), ["phase0", "phase1"]),
        (date(2026, 4, 19), ["phase0", "phase1", "phase2"]),
        (date(2026, 4, 20), ["phase0", "phase1", "phase2", "phase3"]),
    ],
)
def test_failed_status_can_be_entered_from_any_nonterminal_status(
    cycle_repository_env: str,
    cycle_date: date,
    path: list[CycleStatus],
) -> None:
    metadata = create_cycle(cycle_date)
    for status in path:
        metadata = transition_cycle_status(metadata.cycle_id, status)

    failed = transition_cycle_status(metadata.cycle_id, "failed")

    assert failed.status == "failed"


def test_published_cycle_cannot_transition_to_failed(cycle_repository_env: str) -> None:
    create_cycle(date(2026, 4, 16))
    cycle_id = "CYCLE_20260416"
    for status in ["phase0", "phase1", "phase2", "phase3"]:
        transition_cycle_status(cycle_id, status)
    publish_manifest(
        cycle_id,
        {
            "formal.world_state_snapshot": 1,
            "formal.official_alpha_pool": 2,
            "formal.alpha_result_snapshot": 3,
            "formal.recommendation_snapshot": 4,
        },
        recommendation_provenance={
            "cycle_id": cycle_id,
            "current_cycle_id": cycle_id,
            "source_layer": "L8",
            "source_kind": "current-cycle",
            "recommendation_snapshot_id": 4,
            "audit_record_ids": ["audit-cycle-metadata-published-transition"],
            "replay_record_ids": ["replay-cycle-metadata-published-transition"],
        },
    )

    with pytest.raises(InvalidCycleTransition):
        transition_cycle_status(cycle_id, "failed")

    assert get_cycle(cycle_id).status == "published"


def _cycle_metadata(
    *,
    cycle_id: str = "CYCLE_20260416",
    cycle_date: date = date(2026, 4, 16),
    status: CycleStatus = "pending",
) -> CycleMetadata:
    now = datetime.now(UTC)
    return CycleMetadata(
        cycle_id=cycle_id,
        cycle_date=cycle_date,
        status=status,
        cutoff_submitted_at=None,
        cutoff_ingest_seq=None,
        candidate_count=0,
        selection_frozen_at=None,
        created_at=now,
        updated_at=now,
    )


def _create_engine(dsn: str, **kwargs: object) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL cycle metadata tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL cycle metadata tests require the migration runner",
    )
    return sqlalchemy.create_engine(runner_module._sqlalchemy_postgres_uri(dsn), **kwargs)


def _text(sql: str) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL cycle metadata tests require SQLAlchemy",
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


def _cycle_count(dsn: str) -> int:
    engine = _create_engine(dsn)
    try:
        with engine.connect() as connection:
            return int(
                connection.execute(
                    _text("SELECT count(*) FROM data_platform.cycle_metadata")
                ).scalar_one()
            )
    finally:
        engine.dispose()
