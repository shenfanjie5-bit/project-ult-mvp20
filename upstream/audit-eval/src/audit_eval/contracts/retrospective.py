"""Analytical retrospective evaluation runtime contract."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from audit_eval.contracts.common import JsonObject, RetrospectiveHorizon


class RetrospectiveEvaluation(BaseModel):
    """Analytical Zone retrospective evaluation shape."""

    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    cycle_id: str
    object_ref: str
    horizon: RetrospectiveHorizon
    trend_deviation: float
    risk_deviation: float
    alert_score: float
    learning_score: float
    deviation_level: int
    hit_rate_rel: float | None
    baseline_vs_llm_breakdown: JsonObject
    evaluated_at: datetime

    @staticmethod
    def derive_alert_score(trend_deviation: float, risk_deviation: float) -> float:
        """Return the hard-coded alert score for retrospective deviations."""

        return max(trend_deviation, risk_deviation)

    @staticmethod
    def derive_learning_score(trend_deviation: float, risk_deviation: float) -> float:
        """Return the hard-coded learning score for retrospective deviations."""

        return trend_deviation * 0.6 + risk_deviation * 0.4

    @model_validator(mode="after")
    def validate_scores_and_level(self) -> Self:
        """Validate score formulas and bounded deviation metadata."""

        for field_name in (
            "trend_deviation",
            "risk_deviation",
            "alert_score",
            "learning_score",
        ):
            value = getattr(self, field_name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative finite number")

        if not 0 <= self.deviation_level <= 4:
            raise ValueError("deviation_level must be between 0 and 4")

        expected_alert_score = self.derive_alert_score(
            self.trend_deviation,
            self.risk_deviation,
        )
        if not math.isclose(
            self.alert_score,
            expected_alert_score,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "alert_score must equal max(trend_deviation, risk_deviation)"
            )

        expected_learning_score = self.derive_learning_score(
            self.trend_deviation,
            self.risk_deviation,
        )
        if not math.isclose(
            self.learning_score,
            expected_learning_score,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "learning_score must equal "
                "trend_deviation * 0.6 + risk_deviation * 0.4"
            )
        return self


__all__ = ["RetrospectiveEvaluation"]
