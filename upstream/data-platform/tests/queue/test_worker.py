from __future__ import annotations

from collections.abc import Generator, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import json
import logging
import os
import threading
from typing import Any, NoReturn
from uuid import uuid4

import pytest

from data_platform.queue.models import CandidateQueueItem
from data_platform.queue.validation import (
    CandidateValidationError,
    EnvelopeCandidateValidator,
)
from data_platform.queue import worker as worker_module
from data_platform.queue.worker import (
    QueueValidationSummary,
    main,
    validate_pending_candidates,
)


def test_envelope_candidate_validator_accepts_ex_payload_envelope() -> None:
    item = _candidate_item(
        payload_type="Ex-1",
        submitted_by="worker-test",
        payload={
            "payload_type": "Ex-1",
            "submitted_by": "worker-test",
            "candidate": {"id": "alpha"},
        },
    )

    EnvelopeCandidateValidator().validate(item)


def test_envelope_candidate_validator_rejects_payload_type_drift() -> None:
    item = _candidate_item(
        payload_type="Ex-1",
        submitted_by="worker-test",
        payload={
            "payload_type": "Ex-2",
            "submitted_by": "worker-test",
            "candidate": {"id": "alpha"},
        },
    )

    with pytest.raises(CandidateValidationError, match="payload_type does not match"):
        EnvelopeCandidateValidator().validate(item)


def test_cli_prints_json_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_validate_pending_candidates(
        limit: int = 100,
        *,
        validator: object | None = None,
    ) -> QueueValidationSummary:
        assert limit == 5
        assert validator is None
        return QueueValidationSummary(scanned=0, accepted=0, rejected=0, duration_ms=1)

    monkeypatch.setattr(
        worker_module,
        "validate_pending_candidates",
        fake_validate_pending_candidates,
    )

    assert main(["--once", "--limit", "5"]) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "accepted": 0,
        "duration_ms": 1,
        "rejection_counts": {},
        "rejections_by_reason_type": {},
        "rejected": 0,
        "scanned": 0,
    }
    assert captured.err == ""


def test_worker_accepts_and_rejects_pending_candidates(
    queue_worker_env: str,
    queue_engine: Any,
) -> None:
    with queue_engine.begin() as connection:
        accepted_first = _insert_candidate(connection, "Ex-1", _payload("Ex-1", "alpha"))
        rejected = _insert_candidate(connection, "Ex-2", _payload("Ex-2", "reject"))
        accepted_second = _insert_candidate(connection, "Ex-3", _payload("Ex-3", "beta"))

    class FakeValidator:
        def validate(self, item: CandidateQueueItem) -> None:
            if item.payload["candidate"] == "reject":
                raise CandidateValidationError("fake validator rejected candidate")

    summary = validate_pending_candidates(validator=FakeValidator())

    assert summary.scanned == 3
    assert summary.accepted == 2
    assert summary.rejected == 1
    assert summary.rejection_counts == {"fake validator rejected candidate": 1}
    assert summary.rejections_by_reason_type == {"CandidateValidationError": 1}

    rows = _queue_rows(queue_engine)
    assert rows[accepted_first]["validation_status"] == "accepted"
    assert rows[accepted_first]["rejection_reason"] is None
    assert rows[rejected]["validation_status"] == "rejected"
    assert rows[rejected]["rejection_reason"] == "fake validator rejected candidate"
    assert rows[accepted_second]["validation_status"] == "accepted"
    assert rows[accepted_second]["rejection_reason"] is None
    assert "submitted_at" not in rows[accepted_first]["payload"]
    assert "ingest_seq" not in rows[accepted_first]["payload"]

    second_summary = validate_pending_candidates(validator=FakeValidator())
    assert second_summary.scanned == 0
    assert second_summary.accepted == 0
    assert second_summary.rejected == 0


def test_worker_respects_limit(
    queue_worker_env: str,
    queue_engine: Any,
) -> None:
    with queue_engine.begin() as connection:
        for index in range(12):
            _insert_candidate(connection, "Ex-1", _payload("Ex-1", f"candidate-{index}"))

    summary = validate_pending_candidates(limit=10)

    assert summary.scanned == 10
    assert summary.accepted == 10
    assert summary.rejected == 0
    assert summary.rejection_counts == {}
    assert summary.rejections_by_reason_type == {}
    assert _status_counts(queue_engine) == {"accepted": 10, "pending": 2}


def test_worker_rolls_back_unexpected_validator_exceptions(
    queue_worker_env: str,
    queue_engine: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with queue_engine.begin() as connection:
        first = _insert_candidate(connection, "Ex-1", _payload("Ex-1", "first"))
        second = _insert_candidate(connection, "Ex-1", _payload("Ex-1", "crash"))

    class CrashingValidator:
        def validate(self, item: CandidateQueueItem) -> None:
            if item.payload["candidate"] == "crash":
                raise RuntimeError("validator backend unavailable")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match="validator backend unavailable"):
            validate_pending_candidates(validator=CrashingValidator())

    rows = _queue_rows(queue_engine)

    assert rows[first]["validation_status"] == "pending"
    assert rows[first]["rejection_reason"] is None
    assert rows[second]["validation_status"] == "pending"
    assert rows[second]["rejection_reason"] is None
    assert _status_counts(queue_engine) == {"pending": 2}
    assert any(
        "unexpected candidate validator failure" in record.message
        for record in caplog.records
    )


def test_concurrent_workers_do_not_process_same_candidate_twice(
    queue_worker_env: str,
    queue_engine: Any,
) -> None:
    with queue_engine.begin() as connection:
        for index in range(20):
            _insert_candidate(connection, "Ex-1", _payload("Ex-1", f"candidate-{index}"))

    validator = _BarrierValidator(threading.Barrier(2))
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(validate_pending_candidates, 10, validator=validator),
            executor.submit(validate_pending_candidates, 10, validator=validator),
        ]
        summaries = [future.result(timeout=20) for future in futures]

    assert sum(summary.scanned for summary in summaries) == 20
    assert sum(summary.accepted for summary in summaries) == 20
    assert sum(summary.rejected for summary in summaries) == 0
    assert len(validator.seen_candidate_ids) == 20
    assert len(set(validator.seen_candidate_ids)) == 20
    assert _status_counts(queue_engine) == {"accepted": 20}


def test_cli_succeeds_on_empty_queue(
    queue_worker_env: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--once", "--limit", "5"]) == 0

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["accepted"] == 0
    assert summary["rejected"] == 0
    assert summary["scanned"] == 0
    assert summary["rejection_counts"] == {}
    assert summary["rejections_by_reason_type"] == {}
    assert isinstance(summary["duration_ms"], int)
    assert summary["duration_ms"] >= 0
    assert captured.err == ""


@pytest.fixture()
def queue_worker_env(
    migrated_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[str]:
    monkeypatch.setenv("DP_PG_DSN", migrated_postgres_dsn)
    yield migrated_postgres_dsn


@pytest.fixture()
def queue_engine(migrated_postgres_dsn: str) -> Generator[Any]:
    engine = _create_engine(migrated_postgres_dsn)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def migrated_postgres_dsn() -> Generator[str]:
    admin_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DP_PG_DSN")
    if not admin_dsn:
        _skip_or_fail_worker_db(
            "PostgreSQL queue worker tests require DATABASE_URL or DP_PG_DSN",
        )

    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL queue worker tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL queue worker tests require the migration runner",
    )
    make_url = pytest.importorskip(
        "sqlalchemy.engine",
        reason="PostgreSQL queue worker tests require SQLAlchemy",
    ).make_url
    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="PostgreSQL queue worker tests require SQLAlchemy",
    ).SQLAlchemyError

    admin_engine = _create_engine(admin_dsn, isolation_level="AUTOCOMMIT")
    database_name = f"dp_queue_worker_test_{uuid4().hex}"
    try:
        with admin_engine.connect() as connection:
            connection.execute(sqlalchemy.text(f'CREATE DATABASE "{database_name}"'))
    except sqlalchemy_error as exc:
        admin_engine.dispose()
        _skip_or_fail_worker_db(
            "PostgreSQL queue worker tests require permission to create "
            f"test databases: {exc}"
        )

    test_dsn = (
        make_url(runner_module._sqlalchemy_postgres_uri(admin_dsn))
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )
    try:
        runner_module.MigrationRunner().apply_pending(test_dsn)
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
            connection.execute(
                sqlalchemy.text(f'DROP DATABASE IF EXISTS "{database_name}"')
            )
        admin_engine.dispose()


def _skip_or_fail_worker_db(message: str) -> NoReturn:
    if os.environ.get("CI", "").strip().lower() in {"1", "true", "yes", "on"}:
        pytest.fail(message)
    pytest.skip(message)


class _BarrierValidator:
    def __init__(self, barrier: threading.Barrier) -> None:
        self._barrier = barrier
        self._local = threading.local()
        self._lock = threading.Lock()
        self.seen_candidate_ids: list[int] = []

    def validate(self, item: CandidateQueueItem) -> None:
        with self._lock:
            self.seen_candidate_ids.append(item.id)
        if getattr(self._local, "waited", False):
            return

        self._local.waited = True
        self._barrier.wait(timeout=10)


def _candidate_item(
    *,
    payload_type: str,
    submitted_by: str,
    payload: Mapping[str, Any],
) -> CandidateQueueItem:
    return CandidateQueueItem(
        id=1,
        payload_type=payload_type,  # type: ignore[arg-type]
        payload=payload,
        submitted_by=submitted_by,
        submitted_at=datetime.now(UTC),
        ingest_seq=1,
        validation_status="pending",
        rejection_reason=None,
    )


def _payload(payload_type: str, candidate: str) -> dict[str, Any]:
    return {
        "payload_type": payload_type,
        "submitted_by": "worker-test",
        "candidate": candidate,
    }


def _insert_candidate(
    connection: Any,
    payload_type: str,
    payload: Mapping[str, Any],
) -> int:
    return int(
        connection.execute(
            _text(
                """
                INSERT INTO data_platform.candidate_queue (
                    payload_type,
                    payload,
                    submitted_by
                )
                VALUES (:payload_type, CAST(:payload AS jsonb), :submitted_by)
                RETURNING id
                """
            ),
            {
                "payload_type": payload_type,
                "payload": json.dumps(dict(payload), allow_nan=False),
                "submitted_by": payload["submitted_by"],
            },
        ).scalar_one()
    )


def _queue_rows(queue_engine: Any) -> dict[int, Mapping[str, Any]]:
    with queue_engine.connect() as connection:
        rows = (
            connection.execute(
                _text(
                    """
                    SELECT id, payload, validation_status, rejection_reason
                    FROM data_platform.candidate_queue
                    ORDER BY ingest_seq ASC
                    """
                )
            )
            .mappings()
            .all()
        )
    return {int(row["id"]): row for row in rows}


def _status_counts(queue_engine: Any) -> dict[str, int]:
    with queue_engine.connect() as connection:
        rows = connection.execute(
            _text(
                """
                SELECT validation_status, count(*) AS row_count
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
        reason="PostgreSQL queue worker tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL queue worker tests require the migration runner",
    )
    return sqlalchemy.create_engine(runner_module._sqlalchemy_postgres_uri(dsn), **kwargs)


def _text(sql: str) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL queue worker tests require SQLAlchemy",
    )
    return sqlalchemy.text(sql)
