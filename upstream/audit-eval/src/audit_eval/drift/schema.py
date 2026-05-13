"""Runtime schema objects for drift reporting."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real
from typing import Literal

from audit_eval.contracts.common import JsonObject

RegimeWarningLevel = Literal["none", "warning", "critical"]


@dataclass(frozen=True)
class DriftedFeature:
    """One feature-level drift evidence item."""

    name: str
    score: float | None
    statistic: float | None
    threshold: float
    drifted: bool

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("DriftedFeature.name must not be empty")
        if self.score is None and self.statistic is None:
            raise ValueError("DriftedFeature requires score or statistic")
        for field_name in ("score", "statistic", "threshold"):
            value = getattr(self, field_name)
            if value is not None:
                _require_finite_number(value, field_name=field_name)

    def to_payload(self) -> JsonObject:
        """Return the JSON-compatible feature evidence payload."""

        return {
            "name": self.name,
            "score": self.score,
            "statistic": self.statistic,
            "threshold": self.threshold,
            "drifted": self.drifted,
        }


@dataclass(frozen=True, init=False)
class EvidentlyRunResult:
    """Evidently report output normalized for drift rules."""

    evidently_json: JsonObject
    features: tuple[DriftedFeature, ...]
    total_feature_count: int | None = None

    def __init__(
        self,
        evidently_json: JsonObject,
        features: Sequence[DriftedFeature] | None = None,
        total_feature_count: int | None = None,
        drifted_features: Sequence[DriftedFeature] | None = None,
    ) -> None:
        if not isinstance(evidently_json, dict):
            raise ValueError("EvidentlyRunResult.evidently_json must be a JSON object")
        if features is not None and drifted_features is not None:
            raise ValueError("Pass either features or drifted_features, not both")
        normalized_features = tuple(
            features if features is not None else drifted_features or ()
        )
        if total_feature_count is not None:
            if total_feature_count < 0:
                raise ValueError("total_feature_count must be non-negative")
            if total_feature_count < len(normalized_features):
                raise ValueError("total_feature_count cannot be smaller than features")
        object.__setattr__(self, "evidently_json", evidently_json)
        object.__setattr__(self, "features", normalized_features)
        object.__setattr__(self, "total_feature_count", total_feature_count)

    @property
    def drifted_features(self) -> tuple[DriftedFeature, ...]:
        """Return feature evidence items marked as drifted."""

        return tuple(feature for feature in self.features if feature.drifted)


@dataclass(frozen=True)
class DriftAlertPayload:
    """Third-layer structural drift warning payload."""

    report_id: str
    regime_warning_level: RegimeWarningLevel
    drifted_features: tuple[str, ...]
    evidently_json_ref: str


def _require_finite_number(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


__all__ = [
    "DriftAlertPayload",
    "DriftedFeature",
    "EvidentlyRunResult",
    "RegimeWarningLevel",
]
