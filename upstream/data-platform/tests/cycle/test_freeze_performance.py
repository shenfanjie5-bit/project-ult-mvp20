from __future__ import annotations

import json
import os
from collections.abc import Generator, Mapping
from datetime import date
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4

import pytest

from data_platform.cycle import create_cycle, freeze_cycle_candidates, get_cycle
from data_platform.queue import CandidateQueueItem, ValidationStatus, submit_candidate
from data_platform.queue.validation import CandidateValidationError
from data_platform.queue.worker import validate_pending_candidates


EXPECTED_MIGRATIONS = ["0001", "0002", "0003", "0004", "0005", "0006"]
FREEZE_CYCLE_ID = "CYCLE_20260416"
FREEZE_CYCLE_DATE = date(2026, 4, 16)
FREEZE_PERFORMANCE_SECONDS = 3.0


class SeedCandidates(Protocol):
    def __call__(
        self,
        count: int,
        *,
        status: ValidationStatus = "accepted",
    ) -> list[CandidateQueueItem]: ...


def test_freezing_100_candidates_under_three_seconds(
    cycle_engine: Any,
    seed_candidates: SeedCandidates,
    capsys: pytest.CaptureFixture[str],
) -> None:
    accepted = seed_candidates(100)
    create_cycle(FREEZE_CYCLE_DATE)

    start = perf_counter()
    metadata = freeze_cycle_candidates(FREEZE_CYCLE_ID)
    duration_seconds = perf_counter() - start

    with capsys.disabled():
        print(
            f"\n{FREEZE_CYCLE_ID} freeze_duration_seconds={duration_seconds:.6f}",
            flush=True,
        )

    selection = _selection_snapshot(cycle_engine, FREEZE_CYCLE_ID)

    assert duration_seconds < FREEZE_PERFORMANCE_SECONDS, (
        f"freeze took {duration_seconds:.6f}s, expected "
        f"< {FREEZE_PERFORMANCE_SECONDS:.1f}s"
    )
    assert selection["candidate_count"] == 100
    assert selection["candidate_count"] == metadata.candidate_count
    assert metadata.candidate_count == _cycle_candidate_count(cycle_engine, FREEZE_CYCLE_ID)
    assert selection["candidate_ids"] == [item.id for item in accepted]
    assert metadata.cutoff_ingest_seq == selection["cutoff_ingest_seq"]
    assert metadata.cutoff_ingest_seq == max(item.ingest_seq for item in accepted)
    assert metadata.cutoff_submitted_at == selection["cutoff_submitted_at"]


def test_concurrent_candidate_insert_does_not_change_frozen_snapshot(
    cycle_engine: Any,
    seed_candidates: SeedCandidates,
) -> None:
    accepted = seed_candidates(5)
    create_cycle(FREEZE_CYCLE_DATE)

    independent_connection = cycle_engine.connect()
    independent_transaction = independent_connection.begin()
    try:
        concurrent_candidate = _insert_accepted_candidate(
            independent_connection,
            candidate="concurrent-uncommitted",
        )

        metadata = freeze_cycle_candidates(FREEZE_CYCLE_ID)
        frozen_selection = _selection_snapshot(cycle_engine, FREEZE_CYCLE_ID)

        independent_transaction.commit()
    finally:
        if independent_transaction.is_active:
            independent_transaction.rollback()
        independent_connection.close()

    after_freeze = seed_candidates(1)[0]
    final_selection = _selection_snapshot(cycle_engine, FREEZE_CYCLE_ID)
    stored_metadata = get_cycle(FREEZE_CYCLE_ID)

    assert frozen_selection == final_selection
    assert stored_metadata == metadata
    assert final_selection["candidate_ids"] == [item.id for item in accepted]
    assert int(concurrent_candidate["id"]) not in final_selection["candidate_ids"]
    assert after_freeze.id not in final_selection["candidate_ids"]
    assert metadata.candidate_count == len(accepted)
    assert metadata.cutoff_ingest_seq == max(item.ingest_seq for item in accepted)
    assert metadata.cutoff_ingest_seq == final_selection["cutoff_ingest_seq"]
    assert _cycle_candidate_count(cycle_engine, FREEZE_CYCLE_ID) == len(accepted)


def test_freeze_ignores_pending_and_rejected_candidates(
    cycle_engine: Any,
    seed_candidates: SeedCandidates,
) -> None:
    accepted = seed_candidates(4, status="accepted")
    rejected = seed_candidates(3, status="rejected")
    pending = seed_candidates(2, status="pending")
    create_cycle(FREEZE_CYCLE_DATE)

    metadata = freeze_cycle_candidates(FREEZE_CYCLE_ID)
    selection = _selection_snapshot(cycle_engine, FREEZE_CYCLE_ID)

    assert selection["candidate_ids"] == [item.id for item in accepted]
    assert not set(selection["candidate_ids"]).intersection(item.id for item in rejected)
    assert not set(selection["candidate_ids"]).intersection(item.id for item in pending)
    assert metadata.candidate_count == len(accepted)
    assert metadata.candidate_count == selection["candidate_count"]
    assert metadata.cutoff_ingest_seq == max(item.ingest_seq for item in accepted)
    assert metadata.cutoff_ingest_seq == selection["cutoff_ingest_seq"]
    assert _validation_status_counts(cycle_engine) == {
        "accepted": len(accepted),
        "pending": len(pending),
        "rejected": len(rejected),
    }


@pytest.fixture()
def seed_candidates(cycle_engine: Any, cycle_repository_env: str) -> SeedCandidates:
    assert cycle_repository_env

    def seed(
        count: int,
        *,
        status: ValidationStatus = "accepted",
    ) -> list[CandidateQueueItem]:
        if count < 0:
            msg = "count must be non-negative"
            raise ValueError(msg)
        if status not in {"accepted", "pending", "rejected"}:
            msg = "status must be accepted, pending, or rejected"
            raise ValueError(msg)

        items = [
            submit_candidate(
                {
                    "payload_type": "Ex-1",
                    "submitted_by": "freeze-performance-test",
                    "candidate": f"{status}-{uuid4().hex}",
                }
            )
            for _ in range(count)
        ]
        if status == "pending" or count == 0:
            return items

        class RejectAllValidator:
            def validate(self, item: CandidateQueueItem) -> None:
                raise CandidateValidationError("freeze performance test rejected candidate")

        summary = validate_pending_candidates(
            limit=count,
            validator=RejectAllValidator() if status == "rejected" else None,
        )
        assert summary.scanned == count
        if status == "accepted":
            assert summary.accepted == count
            assert summary.rejected == 0
        else:
            assert summary.accepted == 0
            assert summary.rejected == count

        return _fetch_candidates(cycle_engine, [item.id for item in items])

    return seed


@pytest.fixture()
def postgres_dsn() -> Generator[str]:
    admin_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DP_PG_DSN")
    if not admin_dsn:
        pytest.skip("PostgreSQL freeze performance tests require DATABASE_URL or DP_PG_DSN")

    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL freeze performance tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL freeze performance tests require the migration runner",
    )
    make_url = pytest.importorskip(
        "sqlalchemy.engine",
        reason="PostgreSQL freeze performance tests require SQLAlchemy",
    ).make_url
    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="PostgreSQL freeze performance tests require SQLAlchemy",
    ).SQLAlchemyError

    admin_engine = _create_engine(admin_dsn, isolation_level="AUTOCOMMIT")
    database_name = f"dp_freeze_performance_test_{uuid4().hex}"
    try:
        with admin_engine.connect() as connection:
            connection.execute(sqlalchemy.text(f'CREATE DATABASE "{database_name}"'))
    except sqlalchemy_error as exc:
        admin_engine.dispose()
        pytest.skip(
            "PostgreSQL freeze performance tests require permission to create "
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
        reason="PostgreSQL freeze performance tests require the migration runner",
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


def _fetch_candidates(engine: Any, candidate_ids: list[int]) -> list[CandidateQueueItem]:
    if not candidate_ids:
        return []

    with engine.connect() as connection:
        rows = (
            connection.execute(
                _text(
                    """
                    SELECT
                        id,
                        payload_type,
                        payload,
                        submitted_by,
                        submitted_at,
                        ingest_seq,
                        validation_status,
                        rejection_reason
                    FROM data_platform.candidate_queue
                    WHERE id = ANY(:candidate_ids)
                    ORDER BY ingest_seq ASC
                    """
                ),
                {"candidate_ids": candidate_ids},
            )
            .mappings()
            .all()
        )

    assert len(rows) == len(candidate_ids)
    return [
        CandidateQueueItem(
            id=int(row["id"]),
            payload_type=row["payload_type"],
            payload=row["payload"],
            submitted_by=str(row["submitted_by"]),
            submitted_at=row["submitted_at"],
            ingest_seq=int(row["ingest_seq"]),
            validation_status=row["validation_status"],
            rejection_reason=(
                None if row["rejection_reason"] is None else str(row["rejection_reason"])
            ),
        )
        for row in rows
    ]


def _insert_accepted_candidate(connection: Any, *, candidate: str) -> Mapping[str, Any]:
    payload = {
        "payload_type": "Ex-1",
        "submitted_by": "freeze-performance-test",
        "candidate": candidate,
    }
    return connection.execute(
        _text(
            """
            INSERT INTO data_platform.candidate_queue (
                payload_type,
                payload,
                submitted_by,
                validation_status
            )
            VALUES (
                'Ex-1',
                CAST(:payload AS jsonb),
                'freeze-performance-test',
                CAST('accepted' AS data_platform.validation_status)
            )
            RETURNING id, submitted_at, ingest_seq, validation_status
            """
        ),
        {"payload": json.dumps(payload, allow_nan=False)},
    ).mappings().one()


def _selection_snapshot(engine: Any, cycle_id: str) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            _text(
                """
                SELECT
                    coalesce(array_agg(selection.candidate_id ORDER BY selection.candidate_id), '{}')
                        AS candidate_ids,
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

    return {
        "candidate_ids": [int(candidate_id) for candidate_id in row["candidate_ids"]],
        "candidate_count": int(row["candidate_count"]),
        "cutoff_ingest_seq": (
            None if row["cutoff_ingest_seq"] is None else int(row["cutoff_ingest_seq"])
        ),
        "cutoff_submitted_at": row["cutoff_submitted_at"],
    }


def _cycle_candidate_count(engine: Any, cycle_id: str) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                _text(
                    """
                    SELECT candidate_count
                    FROM data_platform.cycle_metadata
                    WHERE cycle_id = :cycle_id
                    """
                ),
                {"cycle_id": cycle_id},
            ).scalar_one()
        )


def _validation_status_counts(engine: Any) -> dict[str, int]:
    with engine.connect() as connection:
        rows = connection.execute(
            _text(
                """
                SELECT validation_status, count(*)::integer AS row_count
                FROM data_platform.candidate_queue
                GROUP BY validation_status
                ORDER BY validation_status
                """
            )
        )
        return {str(row[0]): int(row[1]) for row in rows}


def _create_engine(dsn: str, **kwargs: object) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL freeze performance tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL freeze performance tests require the migration runner",
    )
    return sqlalchemy.create_engine(runner_module._sqlalchemy_postgres_uri(dsn), **kwargs)


def _text(sql: str) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL freeze performance tests require SQLAlchemy",
    )
    return sqlalchemy.text(sql)
