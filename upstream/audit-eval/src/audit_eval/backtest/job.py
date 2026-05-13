"""Backtest job request object."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Literal

from audit_eval._boundary import assert_no_forbidden_write
from audit_eval.backtest.errors import BacktestInputError
from audit_eval.backtest.schema import BacktestEngine
from audit_eval.contracts.common import JsonObject

_BACKTEST_ENGINES: frozenset[str] = frozenset({"alphalens", "backtrader"})


@dataclass(frozen=True)
class BacktestJob:
    """Offline backtest execution request."""

    job_ref: str
    feature_ref: str
    formal_snapshot_range: JsonObject
    engine: BacktestEngine = "alphalens"
    run_mode: Literal["offline_research"] = "offline_research"
    metrics_config: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        job_ref = _strip_required_string(self.job_ref, field_name="job_ref")
        feature_ref = _strip_required_string(
            self.feature_ref,
            field_name="feature_ref",
        )
        if self.engine not in _BACKTEST_ENGINES:
            raise BacktestInputError("engine must be 'alphalens' or 'backtrader'")
        if self.run_mode != "offline_research":
            raise BacktestInputError(
                "BacktestJob.run_mode must be offline_research; "
                "backtests cannot run in daily cycle or online modes"
            )
        if not isinstance(self.formal_snapshot_range, dict):
            raise BacktestInputError("formal_snapshot_range must be a JSON object")
        if not isinstance(self.metrics_config, dict):
            raise BacktestInputError("metrics_config must be a JSON object")

        formal_snapshot_range = deepcopy(self.formal_snapshot_range)
        metrics_config = deepcopy(self.metrics_config)
        assert_no_forbidden_write(
            formal_snapshot_range,
            path="$.formal_snapshot_range",
        )
        assert_no_forbidden_write(metrics_config, path="$.metrics_config")

        object.__setattr__(self, "job_ref", job_ref)
        object.__setattr__(self, "feature_ref", feature_ref)
        object.__setattr__(self, "formal_snapshot_range", formal_snapshot_range)
        object.__setattr__(self, "metrics_config", metrics_config)


def _strip_required_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise BacktestInputError(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        raise BacktestInputError(f"{field_name} must not be empty")
    return stripped


__all__ = ["BacktestJob"]
