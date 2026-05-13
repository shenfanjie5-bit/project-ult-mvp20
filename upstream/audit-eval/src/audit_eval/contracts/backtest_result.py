"""Analytical backtest result runtime contract."""

from __future__ import annotations

from datetime import datetime
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
from audit_eval.contracts.common import JsonObject

NonBlankString = Annotated[str, Field(min_length=1)]


class BacktestResult(BaseModel):
    """Analytical Zone backtest result shape."""

    model_config = ConfigDict(extra="forbid")

    backtest_id: NonBlankString
    job_ref: NonBlankString
    engine: Literal["alphalens", "backtrader"]
    feature_ref: NonBlankString
    formal_snapshot_range: JsonObject
    metrics: JsonObject
    pit_check_passed: Annotated[bool, Field(strict=True)]
    created_at: datetime

    @field_validator("backtest_id", "job_ref", "feature_ref", mode="after")
    @classmethod
    def normalize_non_blank_string(
        cls,
        value: str,
        info: ValidationInfo,
    ) -> str:
        """Normalize identifiers and reject whitespace-only values."""

        return _strip_non_blank_string(value, field_name=info.field_name or "")

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_raw_payload(cls, payload: object) -> object:
        """Reject forbidden write fields before nested validation normalizes input."""

        assert_no_forbidden_write(payload)
        return payload

    @model_validator(mode="after")
    def validate_backtest_result(self) -> Self:
        """Enforce PIT publication gate and analytical boundary safety."""

        if self.pit_check_passed is not True:
            raise ValueError("pit_check_passed must be True for BacktestResult")
        assert_no_forbidden_write(
            self.formal_snapshot_range,
            path="$.formal_snapshot_range",
        )
        assert_no_forbidden_write(self.metrics, path="$.metrics")
        assert_no_forbidden_write(self.model_dump(mode="python"))
        return self


def _strip_non_blank_string(value: str, *, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be empty")
    return stripped


__all__ = ["BacktestResult"]
