"""Retrospective summary aggregation."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date, datetime, timezone
from numbers import Real
from typing import Any, cast, get_args

from audit_eval._boundary import assert_no_forbidden_write
from audit_eval.contracts.common import JsonObject, RetrospectiveHorizon
from audit_eval.contracts.retrospective import RetrospectiveEvaluation
from audit_eval.retro.dates import (
    evaluation_business_date,
    filter_evaluations_for_window,
)
from audit_eval.retro.alert import evaluate_cumulative_alert
from audit_eval.retro.schema import RetroWindow, RetrospectiveSummary
from audit_eval.retro.storage import (
    RetrospectiveCurrentViewStorage,
    RetrospectiveEvaluationReader,
    RetrospectiveStorageError,
    get_default_current_view_storage,
    get_default_evaluation_reader,
)


class RetrospectiveSummaryError(RuntimeError):
    """Raised when retrospective summary construction cannot produce output."""


_DATE_WINDOW_SEPARATOR = ".."
_DATE_WINDOW_FORMAT = "YYYY-MM-DD..YYYY-MM-DD"
_VALID_HORIZONS = set(get_args(RetrospectiveHorizon))


def build_retrospective_summary(
    window: str,
    *,
    horizon: RetrospectiveHorizon = "T+1",
    object_ref: str | None = None,
    reader: RetrospectiveEvaluationReader | None = None,
    current_view: RetrospectiveCurrentViewStorage | None = None,
    generated_at: datetime | None = None,
) -> RetrospectiveSummary:
    """Build and upsert a retrospective summary for a public date window."""

    retro_window = _parse_public_window(
        window,
        horizon=horizon,
        object_ref=object_ref,
    )
    return _build_retrospective_summary(
        retro_window,
        reader=reader,
        current_view=current_view,
        generated_at=generated_at,
    )


def _build_retrospective_summary(
    window: RetroWindow,
    *,
    reader: RetrospectiveEvaluationReader | None = None,
    current_view: RetrospectiveCurrentViewStorage | None = None,
    generated_at: datetime | None = None,
) -> RetrospectiveSummary:
    """Build and upsert a retrospective summary for a bounded window."""

    evaluation_reader = reader or get_default_evaluation_reader()
    current_view_storage = current_view or get_default_current_view_storage()
    effective_generated_at = generated_at or datetime.now(timezone.utc)
    evaluations = filter_evaluations_for_window(
        evaluation_reader.load_evaluations(window),
        window,
    )
    for index, evaluation in enumerate(evaluations):
        assert_no_forbidden_write(
            evaluation.model_dump(mode="python"),
            path=f"$.evaluations[{index}]",
        )
    if not evaluations:
        raise RetrospectiveSummaryError(
            "Retrospective summary window contains no evaluations"
        )

    alert_state = evaluate_cumulative_alert(
        evaluations,
        evaluated_at=effective_generated_at,
    )
    trend = _ordered_value_trend(
        evaluations,
        [evaluation.learning_score for evaluation in evaluations],
        insufficient_value=0.0,
    )
    summary = RetrospectiveSummary(
        date_window=_date_window(window),
        window_start=window.start,
        window_end=window.end,
        horizon=window.horizon,
        evaluation_count=len(evaluations),
        composite_learning_score_mean=_mean(
            [evaluation.learning_score for evaluation in evaluations]
        ),
        trend=0.0 if trend is None else trend,
        baseline_vs_llm_breakdown=_aggregate_breakdown(evaluations),
        l7_hit_rate_rel_trend=_l7_hit_rate_rel_trend(evaluations),
        alert_state=alert_state,
        generated_at=effective_generated_at,
        object_ref=window.object_ref,
    )

    assert_no_forbidden_write(asdict(summary), path="$.summary")
    assert_no_forbidden_write(asdict(alert_state), path="$.alert_state")

    try:
        current_view_storage.upsert_summary_and_alert_state(summary, alert_state)
    except RetrospectiveStorageError:
        raise
    except Exception as exc:
        raise RetrospectiveStorageError(f"upsert current view failed: {exc}") from exc
    return summary


def _parse_public_window(
    window: str,
    *,
    horizon: RetrospectiveHorizon,
    object_ref: str | None,
) -> RetroWindow:
    if not isinstance(window, str):
        raise TypeError(f"window must be a string in {_DATE_WINDOW_FORMAT} format")
    if horizon not in _VALID_HORIZONS:
        raise ValueError("horizon must be one of T+1, T+5, T+20")
    if object_ref is not None and not object_ref.strip():
        raise ValueError("object_ref must be a non-empty string when provided")

    parts = window.split(_DATE_WINDOW_SEPARATOR)
    if len(parts) != 2:
        raise ValueError(f"window must use {_DATE_WINDOW_FORMAT} format")

    start_text, end_text = (part.strip() for part in parts)
    start = _parse_window_date(start_text, field_name="window start")
    end = _parse_window_date(end_text, field_name="window end")
    return RetroWindow(
        start=start,
        end=end,
        horizon=cast(RetrospectiveHorizon, horizon),
        object_ref=object_ref,
    )


def _parse_window_date(value: str, *, field_name: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must use YYYY-MM-DD date format within {_DATE_WINDOW_FORMAT}"
        ) from exc
    if parsed.isoformat() != value:
        raise ValueError(
            f"{field_name} must use YYYY-MM-DD date format within {_DATE_WINDOW_FORMAT}"
        )
    return parsed


def _date_window(window: RetroWindow) -> str:
    return f"{window.start.isoformat()}..{window.end.isoformat()}"


def _aggregate_breakdown(
    evaluations: Sequence[RetrospectiveEvaluation],
) -> JsonObject:
    values_by_key: dict[str, list[Any]] = defaultdict(list)
    for evaluation in evaluations:
        for key, value in evaluation.baseline_vs_llm_breakdown.items():
            values_by_key[key].append(value)

    aggregate: JsonObject = {}
    for key in sorted(values_by_key):
        values = values_by_key[key]
        if values and all(_is_finite_number(value) for value in values):
            aggregate[key] = _mean([float(value) for value in values])
        else:
            aggregate[key] = dict(
                sorted(Counter(_count_key(value) for value in values).items())
            )
    return aggregate


def _l7_hit_rate_rel_trend(
    evaluations: Sequence[RetrospectiveEvaluation],
) -> float | None:
    l7_evaluations: list[RetrospectiveEvaluation] = []
    values: list[float] = []
    for evaluation in evaluations:
        if (
            evaluation.baseline_vs_llm_breakdown.get("layer") == "L7"
            and evaluation.hit_rate_rel is not None
        ):
            l7_evaluations.append(evaluation)
            values.append(evaluation.hit_rate_rel)
    return _ordered_value_trend(
        l7_evaluations,
        values,
        insufficient_value=None,
    )


def _ordered_value_trend(
    evaluations: Sequence[RetrospectiveEvaluation],
    values: Sequence[float],
    *,
    insufficient_value: float | None,
) -> float | None:
    if len(values) < 2:
        return insufficient_value

    ordered_pairs = sorted(
        zip(evaluations, values, strict=True),
        key=lambda pair: (evaluation_business_date(pair[0]), pair[0].evaluation_id),
    )
    ordered_values = [float(value) for _evaluation, value in ordered_pairs]
    midpoint = len(ordered_values) // 2
    first_half = ordered_values[:midpoint]
    second_half = ordered_values[midpoint:]
    return _mean(second_half) - _mean(first_half)


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise RetrospectiveSummaryError("Cannot compute mean for empty values")
    return math.fsum(values) / len(values)


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    return math.isfinite(float(value))


def _count_key(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


__all__ = [
    "RetrospectiveSummaryError",
    "build_retrospective_summary",
]
