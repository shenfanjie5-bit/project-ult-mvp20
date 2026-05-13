"""Retrospective horizon helpers."""

from __future__ import annotations

from datetime import date, timedelta

from audit_eval.contracts.common import RetrospectiveHorizon
from audit_eval.retro.storage import RetrospectiveInputError

HORIZONS: tuple[RetrospectiveHorizon, ...] = ("T+1", "T+5", "T+20")


class UnsupportedRetrospectiveHorizon(RetrospectiveInputError):
    """Raised when a requested retrospective horizon is not supported."""


def horizon_to_days(horizon: RetrospectiveHorizon) -> int:
    """Return the number of days after date_ref required by a horizon."""

    if horizon == "T+1":
        return 1
    if horizon == "T+5":
        return 5
    if horizon == "T+20":
        return 20
    raise UnsupportedRetrospectiveHorizon(
        f"Unsupported retrospective horizon {horizon!r}"
    )


def resolve_evaluation_date(base: date, horizon: RetrospectiveHorizon) -> date:
    """Return the business date when a horizon's outcome becomes available."""

    return base + timedelta(days=horizon_to_days(horizon))


def is_outcome_mature(
    horizon: RetrospectiveHorizon,
    date_ref: date,
    as_of_date: date,
) -> bool:
    """Return whether the requested horizon has matured by as_of_date."""

    return resolve_evaluation_date(date_ref, horizon) <= as_of_date


def require_mature_horizon(
    horizon: RetrospectiveHorizon,
    date_ref: date,
    as_of_date: date,
) -> None:
    """Raise when a requested retrospective horizon is not yet mature."""

    evaluation_date = resolve_evaluation_date(date_ref, horizon)
    if evaluation_date > as_of_date:
        raise RetrospectiveInputError(
            f"{horizon} market outcome is not mature for "
            f"date_ref={date_ref.isoformat()} as_of_date={as_of_date.isoformat()} "
            f"maturity_date={evaluation_date.isoformat()}"
        )


__all__ = [
    "HORIZONS",
    "UnsupportedRetrospectiveHorizon",
    "horizon_to_days",
    "is_outcome_mature",
    "require_mature_horizon",
    "resolve_evaluation_date",
]
