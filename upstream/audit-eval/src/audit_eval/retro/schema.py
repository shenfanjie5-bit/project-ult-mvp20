"""Runtime schema objects for retrospective computation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from audit_eval.contracts.common import JsonObject, RetrospectiveHorizon
from audit_eval.retro.alert import AlertState


@dataclass(frozen=True)
class RetrospectiveTarget:
    """One cycle/object binding eligible for retrospective evaluation."""

    cycle_id: str
    object_ref: str


@dataclass(frozen=True)
class RetrospectiveSeed:
    """Historical prediction seed extracted from manifest-bound replay records."""

    cycle_id: str
    object_ref: str
    expected_trend_score: float
    expected_risk_score: float
    baseline_vs_llm_breakdown: JsonObject


@dataclass(frozen=True)
class MarketOutcome:
    """Realized market outcome for a retrospective target and horizon."""

    cycle_id: str
    object_ref: str
    horizon: RetrospectiveHorizon
    realized_trend_score: float
    realized_risk_score: float
    hit_rate_rel: float | None
    baseline_vs_llm_breakdown: JsonObject


@dataclass(frozen=True)
class DeviationResult:
    """Deviation values produced from a seed/outcome pair."""

    trend_deviation: float
    risk_deviation: float
    hit_rate_rel: float | None
    baseline_vs_llm_breakdown: JsonObject


@dataclass(frozen=True)
class RetroWindow:
    """Stable retrospective evaluation query boundary."""

    start: date
    end: date
    horizon: RetrospectiveHorizon = "T+1"
    object_ref: str | None = None

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError("RetroWindow.start must be on or before end")


@dataclass(frozen=True)
class RetrospectiveSummary:
    """Aggregated retrospective current-view summary."""

    date_window: str
    window_start: date
    window_end: date
    horizon: RetrospectiveHorizon
    evaluation_count: int
    composite_learning_score_mean: float
    trend: float
    baseline_vs_llm_breakdown: JsonObject
    l7_hit_rate_rel_trend: float | None
    alert_state: AlertState
    generated_at: datetime
    object_ref: str | None = None


__all__ = [
    "DeviationResult",
    "MarketOutcome",
    "RetroWindow",
    "RetrospectiveSeed",
    "RetrospectiveSummary",
    "RetrospectiveTarget",
]
