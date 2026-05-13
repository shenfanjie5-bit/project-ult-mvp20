"""Canonical business-date helpers for retrospective evaluations."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

from audit_eval.contracts.retrospective import RetrospectiveEvaluation

if TYPE_CHECKING:
    from audit_eval.retro.schema import RetroWindow

_CYCLE_DATE_RE = re.compile(r"(?:^|_)cycle_(\d{8})(?:$|[_:/-])")


def evaluation_business_date(evaluation: RetrospectiveEvaluation) -> date:
    """Return the canonical business date for retrospective windows.

    The analytical contract does not yet expose a dedicated date_ref field, so the
    project convention is to derive it from cycle_id values like cycle_20260418.
    Rows with non-conforming cycle IDs fall back to evaluated_at.date().
    """

    match = _CYCLE_DATE_RE.search(f"{evaluation.cycle_id}_")
    if match is None:
        return evaluation.evaluated_at.date()
    try:
        return date.fromisoformat(
            f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}"
        )
    except ValueError:
        return evaluation.evaluated_at.date()


def filter_evaluations_for_window(
    evaluations: Sequence[RetrospectiveEvaluation],
    window: RetroWindow,
) -> list[RetrospectiveEvaluation]:
    """Filter evaluations using canonical business date, horizon, and object_ref."""

    return [
        evaluation
        for evaluation in evaluations
        if evaluation.horizon == window.horizon
        and window.start <= evaluation_business_date(evaluation) <= window.end
        and (
            window.object_ref is None
            or evaluation.object_ref == window.object_ref
        )
    ]


__all__ = [
    "evaluation_business_date",
    "filter_evaluations_for_window",
]
