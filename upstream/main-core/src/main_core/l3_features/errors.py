"""Local exception types for L3 feature assembly."""

from __future__ import annotations

from main_core.common.errors import MainCoreError


class L3FeatureError(MainCoreError):
    """Base exception for L3 feature and signal bundle failures."""


class InvalidMultiplierError(L3FeatureError):
    """Raised when a feature weight multiplier is non-positive or non-finite."""


__all__ = ["InvalidMultiplierError", "L3FeatureError"]
