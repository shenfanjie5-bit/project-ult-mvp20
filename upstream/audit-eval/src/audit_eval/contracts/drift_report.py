"""Analytical drift report runtime contract."""

from __future__ import annotations

import math
from datetime import datetime
from numbers import Real
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from audit_eval._boundary import assert_no_forbidden_write

NonBlankString = Annotated[str, Field(min_length=1)]


class DriftedFeatureEvidence(BaseModel):
    """Structured evidence for one drifted feature."""

    model_config = ConfigDict(extra="forbid")

    name: NonBlankString
    score: float | None = None
    statistic: float | None = None
    threshold: float
    drifted: bool

    @field_validator("name", mode="after")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Normalize feature names and reject whitespace-only values."""

        return _strip_non_blank_string(value, field_name="drifted feature name")

    @field_validator("score", "statistic", "threshold", mode="before")
    @classmethod
    def reject_bool_or_non_real_numeric_evidence(cls, value: object) -> object:
        """Reject bool and non-real values before Pydantic float coercion."""

        if value is None:
            return value
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError("drift evidence numeric fields must be real numbers")
        return value

    @model_validator(mode="after")
    def validate_feature_evidence(self) -> Self:
        """Require complete, finite feature drift evidence."""

        if self.score is None and self.statistic is None:
            raise ValueError("drifted feature requires score or statistic")
        for field_name in ("score", "statistic", "threshold"):
            value = getattr(self, field_name)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{field_name} must be finite")
        return self


class DriftedFeaturesPayload(BaseModel):
    """Validated drifted feature evidence payload."""

    model_config = ConfigDict(extra="forbid")

    features: list[DriftedFeatureEvidence]


class DriftReport(BaseModel):
    """Analytical Zone drift report shape."""

    model_config = ConfigDict(extra="forbid")

    report_id: NonBlankString
    cycle_id: NonBlankString | None
    baseline_ref: NonBlankString
    target_ref: NonBlankString
    evidently_json_ref: NonBlankString
    drifted_features: DriftedFeaturesPayload
    regime_warning_level: Literal["none", "warning", "critical"]
    alert_rules_version: NonBlankString
    created_at: datetime

    @field_validator(
        "report_id",
        "cycle_id",
        "baseline_ref",
        "target_ref",
        "evidently_json_ref",
        "alert_rules_version",
        mode="after",
    )
    @classmethod
    def normalize_non_blank_string(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        """Normalize identifier/ref/version strings and reject whitespace-only values."""

        if value is None:
            return value
        return _strip_non_blank_string(value, field_name=info.field_name or "")

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_raw_payload(cls, payload: object) -> object:
        """Reject forbidden write fields before nested validation normalizes input."""

        assert_no_forbidden_write(payload)
        return payload

    @model_validator(mode="after")
    def validate_drift_report(self) -> Self:
        """Validate boundary safety and structural warning evidence."""

        drifted_features = self.drifted_features.features
        if self.regime_warning_level in {"warning", "critical"}:
            if not drifted_features:
                raise ValueError(
                    "warning and critical drift reports require feature evidence"
                )
            if not any(feature.drifted for feature in drifted_features):
                raise ValueError(
                    "warning and critical drift reports require drifted evidence"
                )

        assert_no_forbidden_write(
            self.drifted_features.model_dump(mode="python"),
            path="$.drifted_features",
        )
        assert_no_forbidden_write(self.model_dump(mode="python"))
        return self


def _strip_non_blank_string(value: str, *, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be empty")
    return stripped


__all__ = [
    "DriftReport",
    "DriftedFeatureEvidence",
    "DriftedFeaturesPayload",
]
