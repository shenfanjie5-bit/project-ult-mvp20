"""Repository helpers for PostgreSQL-backed cycle metadata."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import date
from typing import Any, Final, get_args

from data_platform.cycle.models import (
    CYCLE_CANDIDATE_SELECTION_TABLE,
    CYCLE_METADATA_TABLE,
    CycleMetadata,
    CycleStatus,
    InvalidCycleId,
    _cycle_date_from_id,
    _validate_cycle_status,
    cycle_id_for_date,
)
from data_platform.queue.models import CANDIDATE_QUEUE_TABLE, CandidatePayloadType

_FORWARD_TRANSITIONS: Final[dict[CycleStatus, CycleStatus]] = {
    "pending": "phase0",
    "phase0": "phase1",
    "phase1": "phase2",
    "phase2": "phase3",
}
_FAILED_SOURCES: Final[frozenset[CycleStatus]] = frozenset(
    ("pending", "phase0", "phase1", "phase2", "phase3")
)
_CANDIDATE_PAYLOAD_TYPES: Final[frozenset[str]] = frozenset(
    get_args(CandidatePayloadType)
)


class CycleAlreadyExists(RuntimeError):
    """Raised when a cycle row already exists for a cycle_id or cycle_date."""

    def __init__(self, cycle_id: str) -> None:
        self.cycle_id = cycle_id
        super().__init__(f"cycle already exists: {cycle_id}")


class CycleNotFound(LookupError):
    """Raised when no cycle_metadata row exists for a valid cycle_id."""

    def __init__(self, cycle_id: str) -> None:
        self.cycle_id = cycle_id
        super().__init__(f"cycle not found: {cycle_id}")


class CycleAlreadyFrozen(RuntimeError):
    """Raised when candidate selection for a cycle has already been frozen."""

    def __init__(self, cycle_id: str, current_status: str) -> None:
        self.cycle_id = cycle_id
        self.current_status = current_status
        super().__init__(
            f"cycle candidate selection already frozen: {cycle_id} "
            f"status={current_status!r}"
        )


class NoAcceptedCandidates(RuntimeError):
    """Available for strict callers; the default freeze path allows empty selection."""

    def __init__(self, cycle_id: str) -> None:
        self.cycle_id = cycle_id
        super().__init__(f"cycle has no accepted candidates to freeze: {cycle_id}")


class InvalidCycleTransition(ValueError):
    """Raised when a requested cycle status transition is not allowed."""

    def __init__(self, cycle_id: str, current_status: str, target_status: str) -> None:
        self.cycle_id = cycle_id
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(
            "invalid cycle status transition: "
            f"{cycle_id} {current_status!r} -> {target_status!r}"
        )


class CycleRepository:
    """Repository for PostgreSQL-backed cycle operations."""

    def __init__(self, dsn: str | None = None, *, engine: Any | None = None) -> None:
        if dsn is not None and engine is not None:
            msg = "provide either dsn or engine, not both"
            raise ValueError(msg)

        self._owns_engine = engine is None
        self._engine = engine if engine is not None else _create_engine(dsn or _resolve_dsn())

    def begin(self) -> Any:
        """Begin a PostgreSQL transaction for cycle operations."""

        return self._engine.begin()

    def freeze_selection(
        self,
        cycle_id: str,
        connection: Any,
        *,
        submitted_by: str | None = None,
        payload_type: str | None = None,
    ) -> CycleMetadata:
        """Freeze accepted queue candidates for one cycle in the caller transaction.

        Under PostgreSQL READ COMMITTED, the freeze boundary is the
        INSERT...SELECT statement start. Candidates accepted before that statement's
        snapshot are eligible; candidates accepted later wait for a future cycle.
        Eligible candidate rows are locked with SKIP LOCKED so concurrent freezes
        cannot select the same candidate into multiple cycles.
        Metadata is derived from the same inserted CTE so cutoffs and counts always
        describe the actual selected rows.
        """

        _cycle_date_from_id(cycle_id)
        params: dict[str, Any] = {"cycle_id": cycle_id}
        filter_clause = _freeze_filter_clause(
            submitted_by=submitted_by,
            payload_type=payload_type,
            params=params,
        )
        current = connection.execute(
            _text(
                f"""
                SELECT
                    cycle_id,
                    status,
                    selection_frozen_at
                FROM {CYCLE_METADATA_TABLE}
                WHERE cycle_id = :cycle_id
                FOR UPDATE
                """
            ),
            {"cycle_id": cycle_id},
        ).mappings().one_or_none()
        if current is None:
            raise CycleNotFound(cycle_id)

        current_status = _validate_cycle_status(str(current["status"]))
        if current_status != "pending" or current["selection_frozen_at"] is not None:
            raise CycleAlreadyFrozen(cycle_id, current_status)

        row = connection.execute(
            _text(
                f"""
                WITH locked_candidates AS (
                    SELECT candidate_queue.id AS candidate_id
                    FROM {CANDIDATE_QUEUE_TABLE} AS candidate_queue
                    WHERE candidate_queue.validation_status = 'accepted'
                      {filter_clause}
                      AND NOT EXISTS (
                          SELECT 1
                          FROM {CYCLE_CANDIDATE_SELECTION_TABLE} AS selection
                          WHERE selection.candidate_id = candidate_queue.id
                      )
                    ORDER BY candidate_queue.ingest_seq ASC
                    FOR UPDATE OF candidate_queue SKIP LOCKED
                ),
                inserted AS (
                    INSERT INTO {CYCLE_CANDIDATE_SELECTION_TABLE} (
                        cycle_id,
                        candidate_id
                    )
                    SELECT
                        :cycle_id,
                        locked_candidates.candidate_id
                    FROM locked_candidates
                    RETURNING candidate_id
                ),
                stats AS (
                    SELECT
                        max(candidate_queue.submitted_at) AS cutoff_submitted_at,
                        max(candidate_queue.ingest_seq) AS cutoff_ingest_seq,
                        count(*) AS candidate_count
                    FROM inserted
                    JOIN {CANDIDATE_QUEUE_TABLE} AS candidate_queue
                      ON candidate_queue.id = inserted.candidate_id
                )
                UPDATE {CYCLE_METADATA_TABLE} AS cycle_metadata
                SET
                    cutoff_submitted_at = stats.cutoff_submitted_at,
                    cutoff_ingest_seq = stats.cutoff_ingest_seq,
                    candidate_count = CAST(stats.candidate_count AS integer),
                    selection_frozen_at = now(),
                    status = CAST('phase0' AS data_platform.cycle_status),
                    updated_at = now()
                FROM stats
                WHERE cycle_metadata.cycle_id = :cycle_id
                RETURNING
                    cycle_metadata.cycle_id,
                    cycle_metadata.cycle_date,
                    cycle_metadata.status,
                    cycle_metadata.cutoff_submitted_at,
                    cycle_metadata.cutoff_ingest_seq,
                    cycle_metadata.candidate_count,
                    cycle_metadata.selection_frozen_at,
                    cycle_metadata.created_at,
                    cycle_metadata.updated_at
                """
            ),
            params,
        ).mappings().one()
        return _metadata_from_row(row)

    def close(self) -> None:
        """Dispose an owned SQLAlchemy engine."""

        if self._owns_engine:
            self._engine.dispose()


def create_cycle(cycle_date: date) -> CycleMetadata:
    """Create a pending cycle_metadata row for cycle_date."""

    if not isinstance(cycle_date, date):
        msg = "cycle_date must be a datetime.date"
        raise TypeError(msg)

    from sqlalchemy.exc import IntegrityError

    cycle_id = cycle_id_for_date(cycle_date)
    engine = _create_engine()
    try:
        with engine.begin() as connection:
            row = connection.execute(
                _text(
                    f"""
                    INSERT INTO {CYCLE_METADATA_TABLE} (
                        cycle_id,
                        cycle_date
                    )
                    VALUES (:cycle_id, :cycle_date)
                    RETURNING
                        cycle_id,
                        cycle_date,
                        status,
                        cutoff_submitted_at,
                        cutoff_ingest_seq,
                        candidate_count,
                        selection_frozen_at,
                        created_at,
                        updated_at
                    """
                ),
                {"cycle_id": cycle_id, "cycle_date": cycle_date},
            ).mappings().one()
            return _metadata_from_row(row)
    except IntegrityError as exc:
        raise CycleAlreadyExists(cycle_id) from exc
    finally:
        engine.dispose()


def get_cycle(cycle_id: str) -> CycleMetadata:
    """Return one cycle_metadata row by cycle_id."""

    _cycle_date_from_id(cycle_id)
    engine = _create_engine()
    try:
        with engine.connect() as connection:
            row = connection.execute(
                _text(
                    f"""
                    SELECT
                        cycle_id,
                        cycle_date,
                        status,
                        cutoff_submitted_at,
                        cutoff_ingest_seq,
                        candidate_count,
                        selection_frozen_at,
                        created_at,
                        updated_at
                    FROM {CYCLE_METADATA_TABLE}
                    WHERE cycle_id = :cycle_id
                    """
                ),
                {"cycle_id": cycle_id},
            ).mappings().one_or_none()
            if row is None:
                raise CycleNotFound(cycle_id)
            return _metadata_from_row(row)
    finally:
        engine.dispose()


def list_cycles(
    *,
    limit: int = 100,
    status: CycleStatus | None = None,
) -> tuple[CycleMetadata, ...]:
    """Return recent cycle_metadata rows ordered newest first."""

    validated_limit = _validate_cycle_limit(limit)
    params: dict[str, Any] = {"limit": validated_limit}
    where_clause = ""
    if status is not None:
        params["status"] = _validate_cycle_status(status)
        where_clause = "WHERE status = CAST(:status AS data_platform.cycle_status)"

    engine = _create_engine()
    try:
        with engine.connect() as connection:
            rows = (
                connection.execute(
                    _text(
                        f"""
                    SELECT
                        cycle_id,
                        cycle_date,
                        status,
                        cutoff_submitted_at,
                        cutoff_ingest_seq,
                        candidate_count,
                        selection_frozen_at,
                        created_at,
                        updated_at
                    FROM {CYCLE_METADATA_TABLE}
                    {where_clause}
                    ORDER BY cycle_date DESC, cycle_id DESC
                    LIMIT :limit
                    """
                    ),
                    params,
                )
                .mappings()
                .all()
            )
            return tuple(_metadata_from_row(row) for row in rows)
    finally:
        engine.dispose()


def transition_cycle_status(cycle_id: str, status: CycleStatus) -> CycleMetadata:
    """Transition a cycle to the next allowed status."""

    _cycle_date_from_id(cycle_id)
    target_status = _transition_target(cycle_id, status)
    engine = _create_engine()
    try:
        with engine.begin() as connection:
            current = connection.execute(
                _text(
                    f"""
                    SELECT status
                    FROM {CYCLE_METADATA_TABLE}
                    WHERE cycle_id = :cycle_id
                    FOR UPDATE
                    """
                ),
                {"cycle_id": cycle_id},
            ).mappings().one_or_none()
            if current is None:
                raise CycleNotFound(cycle_id)

            current_status = _validate_cycle_status(str(current["status"]))
            _validate_transition(cycle_id, current_status, target_status)

            row = connection.execute(
                _text(
                    f"""
                    UPDATE {CYCLE_METADATA_TABLE}
                    SET status = CAST(:status AS data_platform.cycle_status),
                        updated_at = now()
                    WHERE cycle_id = :cycle_id
                    RETURNING
                        cycle_id,
                        cycle_date,
                        status,
                        cutoff_submitted_at,
                        cutoff_ingest_seq,
                        candidate_count,
                        selection_frozen_at,
                        created_at,
                        updated_at
                    """
                ),
                {"cycle_id": cycle_id, "status": target_status},
            ).mappings().one()
            return _metadata_from_row(row)
    finally:
        engine.dispose()


def _create_engine(dsn: str | None = None) -> Any:
    from sqlalchemy import create_engine

    return create_engine(_sqlalchemy_postgres_uri(dsn or _resolve_dsn()))


def _text(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


def _resolve_dsn() -> str:
    raw_dsn = os.environ.get("DP_PG_DSN")
    if raw_dsn:
        return raw_dsn
    from data_platform.config import get_settings

    return str(get_settings().pg_dsn)


def _sqlalchemy_postgres_uri(dsn: str) -> str:
    if dsn.startswith("postgresql://"):
        return "postgresql+psycopg://" + dsn.removeprefix("postgresql://")
    if dsn.startswith("postgres://"):
        return "postgresql+psycopg://" + dsn.removeprefix("postgres://")
    return dsn


def _freeze_filter_clause(
    *,
    submitted_by: str | None,
    payload_type: str | None,
    params: dict[str, Any],
) -> str:
    clauses: list[str] = []
    if submitted_by is not None:
        if not submitted_by.strip():
            msg = "submitted_by filter must be a non-empty string"
            raise ValueError(msg)
        params["filter_submitted_by"] = submitted_by
        clauses.append("AND candidate_queue.submitted_by = :filter_submitted_by")
    if payload_type is not None:
        if payload_type not in _CANDIDATE_PAYLOAD_TYPES:
            msg = f"payload_type filter must be one of {sorted(_CANDIDATE_PAYLOAD_TYPES)}"
            raise ValueError(msg)
        params["filter_payload_type"] = payload_type
        clauses.append(
            "AND candidate_queue.payload_type = "
            "CAST(:filter_payload_type AS data_platform.candidate_payload_type)"
        )
    return "\n                      ".join(clauses)


def _transition_target(cycle_id: str, status: str) -> CycleStatus:
    try:
        return _validate_cycle_status(status)
    except ValueError as exc:
        raise InvalidCycleTransition(cycle_id, "unknown", status) from exc


def _validate_transition(
    cycle_id: str,
    current_status: CycleStatus,
    target_status: CycleStatus,
) -> None:
    if target_status == "failed" and current_status in _FAILED_SOURCES:
        return
    if _FORWARD_TRANSITIONS.get(current_status) == target_status:
        return
    raise InvalidCycleTransition(cycle_id, current_status, target_status)


def _validate_cycle_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        msg = f"limit must be an integer between 1 and 500: {limit!r}"
        raise ValueError(msg)
    if limit < 1 or limit > 500:
        msg = f"limit must be an integer between 1 and 500: {limit!r}"
        raise ValueError(msg)
    return limit


def _metadata_from_row(row: Mapping[str, Any]) -> CycleMetadata:
    return CycleMetadata(
        cycle_id=str(row["cycle_id"]),
        cycle_date=row["cycle_date"],
        status=_validate_cycle_status(str(row["status"])),
        cutoff_submitted_at=row["cutoff_submitted_at"],
        cutoff_ingest_seq=row["cutoff_ingest_seq"],
        candidate_count=int(row["candidate_count"]),
        selection_frozen_at=row["selection_frozen_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


__all__ = [
    "CycleAlreadyFrozen",
    "CycleAlreadyExists",
    "CycleRepository",
    "CycleNotFound",
    "InvalidCycleId",
    "InvalidCycleTransition",
    "NoAcceptedCandidates",
    "create_cycle",
    "get_cycle",
    "list_cycles",
    "transition_cycle_status",
]
