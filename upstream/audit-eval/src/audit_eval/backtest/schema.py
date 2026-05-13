"""Runtime schema objects for point-in-time backtesting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from audit_eval._boundary import assert_no_forbidden_write
from audit_eval.contracts.common import JsonObject

BacktestEngine = Literal["alphalens", "backtrader"]


@dataclass(frozen=True)
class FeatureAvailability:
    """Point-in-time feature availability bound to a manifest snapshot."""

    feature_ref: str
    as_of: datetime
    available_at: datetime
    snapshot_ref: str
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert_no_forbidden_write(self.metadata, path="$.metadata")


@dataclass(frozen=True)
class PITCheckResult:
    """Result of point-in-time feature validation."""

    passed: bool
    violations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        assert_no_forbidden_write(
            {"passed": self.passed, "violations": self.violations},
            path="$.pit_check_result",
        )
        if self.passed and self.violations:
            raise ValueError("PITCheckResult.passed cannot be true with violations")


__all__ = [
    "BacktestEngine",
    "FeatureAvailability",
    "PITCheckResult",
]
