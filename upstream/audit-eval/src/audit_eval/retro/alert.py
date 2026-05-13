"""Cumulative retrospective alert evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from audit_eval.contracts.common import JsonObject
from audit_eval.contracts.retrospective import RetrospectiveEvaluation
from audit_eval.retro.dates import evaluation_business_date

AlertLevel = Literal["NONE", "WARNING", "CRITICAL", "EMERGENCY"]

_REASON_WARNING_3D_GE2 = "CONSECUTIVE_3_DAYS_ALERT_SCORE_GE_2"
_REASON_CRITICAL_3D_GE3 = "CONSECUTIVE_3_DAYS_ALERT_SCORE_GE_3"
_REASON_CRITICAL_5D_4_GE2 = "ROLLING_5_DAYS_4_DAYS_ALERT_SCORE_GE_2"
_REASON_EMERGENCY_5D_GE2 = "CONSECUTIVE_5_DAYS_ALERT_SCORE_GE_2"
_REASON_EMERGENCY_3D_GE3_L7_LOW = (
    "CONSECUTIVE_3_DAYS_ALERT_SCORE_GE_3_AND_L7_HIT_RATE_REL_LT_0_35"
)


@dataclass(frozen=True)
class AlertState:
    """Current cumulative retrospective alert state."""

    level: AlertLevel
    reason_codes: tuple[str, ...]
    window_start: date
    window_end: date
    evaluated_at: datetime
    metrics: JsonObject


def evaluate_cumulative_alert(
    history: Sequence[RetrospectiveEvaluation],
    *,
    evaluated_at: datetime | None = None,
) -> AlertState:
    """Evaluate cumulative alert thresholds from T+1 retrospective history."""

    effective_evaluated_at = evaluated_at or datetime.now(timezone.utc)
    t_plus_1_history = [
        evaluation for evaluation in history if evaluation.horizon == "T+1"
    ]
    if not t_plus_1_history:
        empty_date = effective_evaluated_at.date()
        return AlertState(
            level="NONE",
            reason_codes=(),
            window_start=empty_date,
            window_end=empty_date,
            evaluated_at=effective_evaluated_at,
            metrics={
                "daily_alert_score_max": {},
                "last_3_days_alert_score_ge_2": False,
                "last_3_days_alert_score_ge_3": False,
                "last_5_days_alert_score_ge_2_count": 0,
                "last_5_days_alert_score_ge_2_all": False,
                "l7_hit_rate_rel_mean": None,
                "l7_hit_rate_rel_count": 0,
            },
        )

    daily_scores = _daily_max_alert_scores(t_plus_1_history)
    ordered_dates = sorted(daily_scores)
    window_start = ordered_dates[0]
    window_end = ordered_dates[-1]
    recent_3_dates = _dates_for_recent_days(window_end, days=3)
    recent_3_scores = _scores_for_recent_days(daily_scores, window_end, days=3)
    recent_5_scores = _scores_for_recent_days(daily_scores, window_end, days=5)
    l7_hit_rates = _l7_hit_rates(t_plus_1_history, recent_3_dates)
    l7_hit_rate_mean = _mean(l7_hit_rates)

    warning_3d_ge2 = _all_at_or_above(recent_3_scores, threshold=2.0)
    critical_3d_ge3 = _all_at_or_above(recent_3_scores, threshold=3.0)
    critical_5d_4_ge2_count = sum(score >= 2.0 for score in recent_5_scores)
    critical_5d_4_ge2 = critical_5d_4_ge2_count >= 4
    emergency_5d_ge2 = _all_at_or_above(recent_5_scores, threshold=2.0)
    emergency_3d_ge3_l7_low = (
        critical_3d_ge3
        and l7_hit_rate_mean is not None
        and _strictly_less_than(l7_hit_rate_mean, threshold=0.35)
    )

    reason_codes: list[str] = []
    if warning_3d_ge2:
        reason_codes.append(_REASON_WARNING_3D_GE2)
    if critical_3d_ge3:
        reason_codes.append(_REASON_CRITICAL_3D_GE3)
    if critical_5d_4_ge2:
        reason_codes.append(_REASON_CRITICAL_5D_4_GE2)
    if emergency_5d_ge2:
        reason_codes.append(_REASON_EMERGENCY_5D_GE2)
    if emergency_3d_ge3_l7_low:
        reason_codes.append(_REASON_EMERGENCY_3D_GE3_L7_LOW)

    level: AlertLevel = "NONE"
    if emergency_5d_ge2 or emergency_3d_ge3_l7_low:
        level = "EMERGENCY"
    elif critical_3d_ge3 or critical_5d_4_ge2:
        level = "CRITICAL"
    elif warning_3d_ge2:
        level = "WARNING"

    return AlertState(
        level=level,
        reason_codes=tuple(reason_codes),
        window_start=window_start,
        window_end=window_end,
        evaluated_at=effective_evaluated_at,
        metrics={
            "daily_alert_score_max": {
                day.isoformat(): daily_scores[day] for day in ordered_dates
            },
            "last_3_days_alert_score_ge_2": warning_3d_ge2,
            "last_3_days_alert_score_ge_3": critical_3d_ge3,
            "last_5_days_alert_score_ge_2_count": critical_5d_4_ge2_count,
            "last_5_days_alert_score_ge_2_all": emergency_5d_ge2,
            "l7_hit_rate_rel_mean": l7_hit_rate_mean,
            "l7_hit_rate_rel_count": len(l7_hit_rates),
        },
    )


def _daily_max_alert_scores(
    history: Sequence[RetrospectiveEvaluation],
) -> dict[date, float]:
    daily_scores: dict[date, float] = {}
    for evaluation in history:
        evaluated_day = evaluation_business_date(evaluation)
        current_score = daily_scores.get(evaluated_day)
        if current_score is None or evaluation.alert_score > current_score:
            daily_scores[evaluated_day] = evaluation.alert_score
    return daily_scores


def _scores_for_recent_days(
    daily_scores: dict[date, float],
    window_end: date,
    *,
    days: int,
) -> tuple[float, ...]:
    return tuple(
        daily_scores.get(day, float("-inf"))
        for day in _dates_for_recent_days(window_end, days=days)
    )


def _dates_for_recent_days(window_end: date, *, days: int) -> tuple[date, ...]:
    return tuple(
        window_end - timedelta(days=offset)
        for offset in reversed(range(days))
    )


def _all_at_or_above(scores: Sequence[float], *, threshold: float) -> bool:
    return bool(scores) and all(score >= threshold for score in scores)


def _l7_hit_rates(
    history: Sequence[RetrospectiveEvaluation],
    included_dates: Sequence[date],
) -> list[float]:
    included_date_set = set(included_dates)
    return [
        evaluation.hit_rate_rel
        for evaluation in history
        if evaluation_business_date(evaluation) in included_date_set
        and evaluation.baseline_vs_llm_breakdown.get("layer") == "L7"
        and evaluation.hit_rate_rel is not None
    ]


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    total = sum(Decimal(str(value)) for value in values)
    return float(total / Decimal(len(values)))


def _strictly_less_than(value: float, *, threshold: float) -> bool:
    return Decimal(str(value)) < Decimal(str(threshold))


__all__ = [
    "AlertLevel",
    "AlertState",
    "evaluate_cumulative_alert",
]
