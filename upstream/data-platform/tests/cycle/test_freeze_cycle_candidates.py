from __future__ import annotations

import json
import os
from collections.abc import Generator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, date, datetime
from threading import Barrier
from typing import Any
from uuid import uuid4

import pytest

from data_platform.cycle import (
    CYCLE_CANDIDATE_SELECTION_TABLE,
    CycleAlreadyFrozen,
    CycleCandidateSelection,
    CycleNotFound,
    InvalidCycleId,
    create_cycle,
    freeze_cycle_candidates,
    get_cycle,
)


EXPECTED_SELECTION_COLUMNS = ["cycle_id", "candidate_id", "selected_at"]
EXPECTED_MIGRATIONS = ["0001", "0002", "0003", "0004", "0005", "0006"]


def test_cycle_candidate_selection_model_exposes_contract() -> None:
    assert CYCLE_CANDIDATE_SELECTION_TABLE == "data_platform.cycle_candidate_selection"
    assert is_dataclass(CycleCandidateSelection)
    assert [field.name for field in fields(CycleCandidateSelection)] == (
        EXPECTED_SELECTION_COLUMNS
    )
    assert CycleCandidateSelection.__slots__ == tuple(EXPECTED_SELECTION_COLUMNS)

    selection = CycleCandidateSelection(
        cycle_id="CYCLE_20260416",
        candidate_id=1,
        selected_at=datetime.now(UTC),
    )
    with pytest.raises(FrozenInstanceError):
        selection.candidate_id = 2

    with pytest.raises(InvalidCycleId):
        CycleCandidateSelection(
            cycle_id="bad",
            candidate_id=1,
            selected_at=datetime.now(UTC),
        )
    with pytest.raises(ValueError, match="candidate_id must be positive"):
        CycleCandidateSelection(
            cycle_id="CYCLE_20260416",
            candidate_id=0,
            selected_at=datetime.now(UTC),
        )


def test_freeze_rejects_invalid_cycle_id_before_database() -> None:
    with pytest.raises(InvalidCycleId):
        freeze_cycle_candidates("bad")


def test_migration_creates_cycle_candidate_selection_schema(
    migrated_postgres_dsn: str,
) -> None:
    engine = _create_engine(migrated_postgres_dsn)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(
                    _text("SELECT to_regclass('data_platform.cycle_candidate_selection')")
                ).scalar_one()
                == "data_platform.cycle_candidate_selection"
            )

            table_columns = connection.execute(
                _text(
                    """
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'data_platform'
                      AND table_name = 'cycle_candidate_selection'
                    ORDER BY ordinal_position
                    """
                )
            ).mappings()
            columns = {str(row["column_name"]): row for row in table_columns}
            assert list(columns) == EXPECTED_SELECTION_COLUMNS
            assert columns["cycle_id"]["data_type"] == "text"
            assert columns["candidate_id"]["data_type"] == "bigint"
            assert columns["selected_at"]["data_type"] == "timestamp with time zone"
            assert columns["selected_at"]["column_default"] == "now()"
            for column_name in EXPECTED_SELECTION_COLUMNS:
                assert columns[column_name]["is_nullable"] == "NO"

            assert {
                str(row[0])
                for row in connection.execute(
                    _text(
                        """
                        SELECT constraint_name
                        FROM information_schema.table_constraints
                        WHERE table_schema = 'data_platform'
                          AND table_name = 'cycle_candidate_selection'
                        """
                    )
                )
            } >= {
                "cycle_candidate_selection_pkey",
                "cycle_candidate_selection_cycle_id_fkey",
                "cycle_candidate_selection_candidate_id_fkey",
                "cycle_candidate_selection_candidate_id_key",
            }
    finally:
        engine.dispose()


def test_freeze_allows_empty_queue_with_zero_count(
    cycle_repository_env: str,
    cycle_engine: Any,
) -> None:
    create_cycle(date(2026, 4, 16))

    metadata = freeze_cycle_candidates("CYCLE_20260416")

    assert metadata.status == "phase0"
    assert metadata.cutoff_submitted_at is None
    assert metadata.cutoff_ingest_seq is None
    assert metadata.candidate_count == 0
    assert metadata.selection_frozen_at is not None
    assert _selection_ids(cycle_engine, "CYCLE_20260416") == []


def test_freeze_selects_only_accepted_candidates_and_sets_cutoffs(
    cycle_repository_env: str,
    cycle_engine: Any,
) -> None:
    create_cycle(date(2026, 4, 16))
    accepted: list[Mapping[str, Any]] = []
    with cycle_engine.begin() as connection:
        for index in range(5):
            accepted.append(
                _insert_candidate(
                    connection,
                    validation_status="accepted",
                    candidate=f"accepted-{index}",
                )
            )
        for index in range(2):
            _insert_candidate(
                connection,
                validation_status="rejected",
                candidate=f"rejected-{index}",
            )

    metadata = freeze_cycle_candidates("CYCLE_20260416")

    assert _selection_ids(cycle_engine, "CYCLE_20260416") == [
        int(row["id"]) for row in accepted
    ]
    assert metadata.status == "phase0"
    assert metadata.candidate_count == 5
    assert metadata.cutoff_ingest_seq == max(int(row["ingest_seq"]) for row in accepted)
    selected_submitted_at = [row["submitted_at"] for row in accepted]
    assert metadata.cutoff_submitted_at == max(selected_submitted_at)
    assert all(metadata.cutoff_submitted_at >= submitted_at for submitted_at in selected_submitted_at)


def test_freeze_filter_selects_only_targeted_holdings_ex3_candidates(
    cycle_repository_env: str,
    cycle_engine: Any,
) -> None:
    create_cycle(date(2026, 4, 16))
    with cycle_engine.begin() as connection:
        selected = _insert_candidate(
            connection,
            validation_status="accepted",
            candidate="holdings-ex3",
            payload_type="Ex-3",
            submitted_by="subsystem-holdings",
            delta_id="holdings-freeze-target",
        )
        _insert_candidate(
            connection,
            validation_status="accepted",
            candidate="other-ex3",
            payload_type="Ex-3",
            submitted_by="other-subsystem",
            delta_id="other-freeze-target",
        )
        _insert_candidate(
            connection,
            validation_status="accepted",
            candidate="holdings-ex1",
            payload_type="Ex-1",
            submitted_by="subsystem-holdings",
        )

    metadata = freeze_cycle_candidates(
        "CYCLE_20260416",
        submitted_by="subsystem-holdings",
        payload_type="Ex-3",
    )

    assert metadata.status == "phase0"
    assert metadata.candidate_count == 1
    assert metadata.cutoff_ingest_seq == selected["ingest_seq"]
    assert _selection_ids(cycle_engine, "CYCLE_20260416") == [int(selected["id"])]


def test_freeze_metadata_matches_actual_selection_rows(
    cycle_repository_env: str,
    cycle_engine: Any,
) -> None:
    create_cycle(date(2026, 4, 16))
    with cycle_engine.begin() as connection:
        for index in range(3):
            _insert_candidate(
                connection,
                validation_status="accepted",
                candidate=f"accepted-{index}",
            )
        _insert_candidate(
            connection,
            validation_status="rejected",
            candidate="rejected",
        )

    metadata = freeze_cycle_candidates("CYCLE_20260416")
    stats = _selection_stats(cycle_engine, "CYCLE_20260416")

    assert stats == {
        "candidate_count": metadata.candidate_count,
        "cutoff_ingest_seq": metadata.cutoff_ingest_seq,
        "cutoff_submitted_at": metadata.cutoff_submitted_at,
    }


def test_freeze_missing_cycle_raises_not_found(
    cycle_repository_env: str,
) -> None:
    with pytest.raises(CycleNotFound):
        freeze_cycle_candidates("CYCLE_20260416")


def test_repeated_freeze_raises_and_late_candidates_are_not_selected(
    cycle_repository_env: str,
    cycle_engine: Any,
) -> None:
    create_cycle(date(2026, 4, 16))
    with cycle_engine.begin() as connection:
        first = _insert_candidate(
            connection,
            validation_status="accepted",
            candidate="before-freeze",
        )

    first_metadata = freeze_cycle_candidates("CYCLE_20260416")

    with cycle_engine.begin() as connection:
        _insert_candidate(
            connection,
            validation_status="accepted",
            candidate="after-freeze",
        )

    with pytest.raises(CycleAlreadyFrozen):
        freeze_cycle_candidates("CYCLE_20260416")

    assert _selection_ids(cycle_engine, "CYCLE_20260416") == [int(first["id"])]
    assert get_cycle("CYCLE_20260416") == first_metadata


def test_selection_insert_failure_rolls_back_whole_freeze_transaction(
    cycle_repository_env: str,
    cycle_engine: Any,
) -> None:
    create_cycle(date(2026, 4, 16))
    with cycle_engine.begin() as connection:
        _insert_candidate(
            connection,
            validation_status="accepted",
            candidate="will-roll-back",
        )
        connection.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION data_platform.raise_selection_insert_failure()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'forced selection insert failure';
            END;
            $$;

            CREATE TRIGGER force_selection_insert_failure
            BEFORE INSERT ON data_platform.cycle_candidate_selection
            FOR EACH ROW
            EXECUTE FUNCTION data_platform.raise_selection_insert_failure();
            """
        )

    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="PostgreSQL freeze tests require SQLAlchemy",
    ).SQLAlchemyError
    with pytest.raises(sqlalchemy_error):
        freeze_cycle_candidates("CYCLE_20260416")

    metadata = get_cycle("CYCLE_20260416")
    assert _selection_ids(cycle_engine, "CYCLE_20260416") == []
    assert metadata.status == "pending"
    assert metadata.cutoff_submitted_at is None
    assert metadata.cutoff_ingest_seq is None
    assert metadata.candidate_count == 0
    assert metadata.selection_frozen_at is None


def test_concurrent_freezes_do_not_select_candidate_twice(
    cycle_repository_env: str,
    cycle_engine: Any,
) -> None:
    assert cycle_repository_env
    create_cycle(date(2026, 4, 16))
    create_cycle(date(2026, 4, 17))
    with cycle_engine.begin() as connection:
        accepted_ids = [
            int(
                _insert_candidate(
                    connection,
                    validation_status="accepted",
                    candidate=f"concurrent-freeze-{index}",
                )["id"]
            )
            for index in range(8)
        ]
        connection.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION data_platform.slow_selection_insert()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                PERFORM pg_sleep(0.1);
                RETURN NEW;
            END;
            $$;

            CREATE TRIGGER slow_selection_insert
            BEFORE INSERT ON data_platform.cycle_candidate_selection
            FOR EACH ROW
            EXECUTE FUNCTION data_platform.slow_selection_insert();
            """
        )

    barrier = Barrier(2)

    def freeze(cycle_id: str) -> Any:
        barrier.wait(timeout=15)
        return freeze_cycle_candidates(cycle_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_16 = executor.submit(freeze, "CYCLE_20260416")
        future_17 = executor.submit(freeze, "CYCLE_20260417")
        metadata_16 = future_16.result(timeout=30)
        metadata_17 = future_17.result(timeout=30)

    selection_16 = _selection_ids(cycle_engine, "CYCLE_20260416")
    selection_17 = _selection_ids(cycle_engine, "CYCLE_20260417")

    assert not set(selection_16).intersection(selection_17)
    assert set(selection_16).union(selection_17).issubset(accepted_ids)
    assert metadata_16.candidate_count == len(selection_16)
    assert metadata_17.candidate_count == len(selection_17)


@pytest.fixture()
def postgres_dsn() -> Generator[str]:
    admin_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DP_PG_DSN")
    if not admin_dsn:
        pytest.skip("PostgreSQL freeze tests require DATABASE_URL or DP_PG_DSN")

    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL freeze tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL freeze tests require the migration runner",
    )
    make_url = pytest.importorskip(
        "sqlalchemy.engine",
        reason="PostgreSQL freeze tests require SQLAlchemy",
    ).make_url
    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="PostgreSQL freeze tests require SQLAlchemy",
    ).SQLAlchemyError

    admin_engine = _create_engine(admin_dsn, isolation_level="AUTOCOMMIT")
    database_name = f"dp_freeze_candidates_test_{uuid4().hex}"
    try:
        with admin_engine.connect() as connection:
            connection.execute(sqlalchemy.text(f'CREATE DATABASE "{database_name}"'))
    except sqlalchemy_error as exc:
        admin_engine.dispose()
        pytest.skip(
            "PostgreSQL freeze tests require permission to create test databases: "
            f"{exc}"
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
        reason="PostgreSQL freeze tests require the migration runner",
    )
    applied_versions = runner_module.MigrationRunner().apply_pending(postgres_dsn)
    assert applied_versions == EXPECTED_MIGRATIONS
    assert runner_module.MigrationRunner().apply_pending(postgres_dsn) == []
    return postgres_dsn


@pytest.fixture()
def cycle_repository_env(
    migrated_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[str]:
    monkeypatch.setenv("DP_PG_DSN", migrated_postgres_dsn)
    yield migrated_postgres_dsn


@pytest.fixture()
def cycle_engine(migrated_postgres_dsn: str) -> Generator[Any]:
    engine = _create_engine(migrated_postgres_dsn)
    try:
        yield engine
    finally:
        engine.dispose()


def _insert_candidate(
    connection: Any,
    *,
    validation_status: str,
    candidate: str,
    payload_type: str = "Ex-1",
    submitted_by: str = "freeze-test",
    delta_id: str | None = None,
) -> Mapping[str, Any]:
    payload = {
        "payload_type": payload_type,
        "submitted_by": submitted_by,
        "candidate": candidate,
    }
    if delta_id is not None:
        payload["delta_id"] = delta_id
    return connection.execute(
        _text(
            """
            INSERT INTO data_platform.candidate_queue (
                payload_type,
                payload,
                submitted_by,
                validation_status,
                rejection_reason
            )
            VALUES (
                :payload_type,
                CAST(:payload AS jsonb),
                :submitted_by,
                CAST(:validation_status AS data_platform.validation_status),
                :rejection_reason
            )
            RETURNING id, submitted_at, ingest_seq, validation_status
            """
        ),
        {
            "payload_type": payload_type,
            "payload": json.dumps(payload, allow_nan=False),
            "submitted_by": submitted_by,
            "validation_status": validation_status,
            "rejection_reason": (
                "rejected by freeze test" if validation_status == "rejected" else None
            ),
        },
    ).mappings().one()


def _selection_ids(engine: Any, cycle_id: str) -> list[int]:
    with engine.connect() as connection:
        rows = connection.execute(
            _text(
                """
                SELECT candidate_id
                FROM data_platform.cycle_candidate_selection
                WHERE cycle_id = :cycle_id
                ORDER BY candidate_id ASC
                """
            ),
            {"cycle_id": cycle_id},
        ).scalars()
        return [int(row) for row in rows]


def _selection_stats(engine: Any, cycle_id: str) -> dict[str, object]:
    with engine.connect() as connection:
        row = connection.execute(
            _text(
                """
                SELECT
                    count(*)::integer AS candidate_count,
                    max(candidate_queue.ingest_seq) AS cutoff_ingest_seq,
                    max(candidate_queue.submitted_at) AS cutoff_submitted_at
                FROM data_platform.cycle_candidate_selection AS selection
                JOIN data_platform.candidate_queue AS candidate_queue
                  ON candidate_queue.id = selection.candidate_id
                WHERE selection.cycle_id = :cycle_id
                """
            ),
            {"cycle_id": cycle_id},
        ).mappings().one()
    return dict(row)


def _create_engine(dsn: str, **kwargs: object) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL freeze tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL freeze tests require the migration runner",
    )
    return sqlalchemy.create_engine(runner_module._sqlalchemy_postgres_uri(dsn), **kwargs)


def _text(sql: str) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL freeze tests require SQLAlchemy",
    )
    return sqlalchemy.text(sql)
