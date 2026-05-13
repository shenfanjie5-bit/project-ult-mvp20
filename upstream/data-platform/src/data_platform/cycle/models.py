"""Types for daily cycle metadata control rows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal, TypeAlias, cast, get_args

CycleStatus: TypeAlias = Literal[
    "pending",
    "phase0",
    "phase1",
    "phase2",
    "phase3",
    "published",
    "failed",
]

CYCLE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^CYCLE_(?P<cycle_date>\d{8})$")
CYCLE_METADATA_TABLE: Final[str] = "data_platform.cycle_metadata"
CYCLE_CANDIDATE_SELECTION_TABLE: Final[str] = (
    "data_platform.cycle_candidate_selection"
)

_CYCLE_STATUSES: Final[frozenset[str]] = frozenset(get_args(CycleStatus))


class InvalidCycleId(ValueError):
    """Raised when a cycle_id is not a valid CYCLE_YYYYMMDD identifier."""


@dataclass(frozen=True, slots=True)
class CycleMetadata:
    """A row from data_platform.cycle_metadata."""

    cycle_id: str
    cycle_date: date
    status: CycleStatus
    cutoff_submitted_at: datetime | None
    cutoff_ingest_seq: int | None
    candidate_count: int
    selection_frozen_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        cycle_date = _cycle_date_from_id(self.cycle_id)
        if cycle_date != self.cycle_date:
            msg = (
                "cycle_id must match cycle_date: "
                f"{self.cycle_id!r} != CYCLE_{self.cycle_date:%Y%m%d}"
            )
            raise InvalidCycleId(msg)
        _validate_cycle_status(self.status)
        if self.candidate_count < 0:
            msg = "candidate_count must be non-negative"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class CycleCandidateSelection:
    """A row from data_platform.cycle_candidate_selection."""

    cycle_id: str
    candidate_id: int
    selected_at: datetime

    def __post_init__(self) -> None:
        _cycle_date_from_id(self.cycle_id)
        if self.candidate_id < 1:
            msg = "candidate_id must be positive"
            raise ValueError(msg)


def cycle_id_for_date(cycle_date: date) -> str:
    """Return the canonical cycle_id for a daily cycle date."""

    return f"CYCLE_{cycle_date:%Y%m%d}"


def _cycle_date_from_id(cycle_id: str) -> date:
    match = CYCLE_ID_PATTERN.fullmatch(cycle_id)
    if match is None:
        msg = f"cycle_id must match CYCLE_YYYYMMDD: {cycle_id!r}"
        raise InvalidCycleId(msg)
    try:
        return datetime.strptime(match.group("cycle_date"), "%Y%m%d").date()
    except ValueError as exc:
        msg = f"cycle_id contains an invalid calendar date: {cycle_id!r}"
        raise InvalidCycleId(msg) from exc


def _validate_cycle_status(status: str) -> CycleStatus:
    if status not in _CYCLE_STATUSES:
        msg = f"status must be one of {sorted(_CYCLE_STATUSES)}"
        raise ValueError(msg)
    return cast(CycleStatus, status)
