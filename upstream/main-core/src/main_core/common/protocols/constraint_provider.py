"""Recommendation constraint protocol contracts for §16.2."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from main_core.common.contexts import RecommendationConstraintInputs
from main_core.common.schemas import RecommendationSnapshot


@runtime_checkable
class RecommendationConstraintProvider(Protocol):
    """L7 regime and risk constraint interface from §16.2.

    Per §12.3, constraint gates take precedence over override handling.
    """

    def gate(
        self,
        inputs: RecommendationConstraintInputs,
        candidate: RecommendationSnapshot,
    ) -> RecommendationSnapshot:
        """Apply gate constraints to a typed recommendation candidate."""


class RecommendationConstraintProviderBase(ABC):
    """ABC inheritance entry point for concrete §16.2 constraint providers."""

    @abstractmethod
    def gate(
        self,
        inputs: RecommendationConstraintInputs,
        candidate: RecommendationSnapshot,
    ) -> RecommendationSnapshot:
        """Apply gate constraints to a typed recommendation candidate."""


__all__ = ["RecommendationConstraintProvider", "RecommendationConstraintProviderBase"]
