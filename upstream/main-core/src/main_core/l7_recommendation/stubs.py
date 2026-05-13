"""Compatibility exports for implemented L7 recommendation constraints."""

from __future__ import annotations

from main_core.l7_recommendation.constraints import DefaultConstraintProvider


class NullConstraintProviderStub(DefaultConstraintProvider):
    """Backward-compatible name for the real default L7 constraint provider."""


__all__ = ["NullConstraintProviderStub"]
