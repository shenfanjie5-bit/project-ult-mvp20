"""World-state policy protocol contracts for §16.2."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal, Protocol, runtime_checkable

from main_core.common.contexts import WorldStateInputs
from main_core.common.types import Regime

BoundedLlmDelta = Literal[-1, 0, 1]


@runtime_checkable
class WorldStatePolicy(Protocol):
    """L4 rule skeleton and correction constraint interface from §16.2."""

    def baseline(self, inputs: WorldStateInputs) -> Regime:
        """Derive the baseline market regime from typed world-state inputs."""

    def bound_delta(self, raw_delta: int) -> BoundedLlmDelta:
        """Clamp a raw LLM delta to the formal ``-1`` / ``0`` / ``+1`` range."""

    def compose(self, baseline: Regime, delta: BoundedLlmDelta) -> Regime:
        """Compose a baseline regime and bounded LLM delta into a final regime."""


class WorldStatePolicyBase(ABC):
    """ABC inheritance entry point for concrete §16.2 world-state policies."""

    @abstractmethod
    def baseline(self, inputs: WorldStateInputs) -> Regime:
        """Derive the baseline market regime from typed world-state inputs."""

    @abstractmethod
    def bound_delta(self, raw_delta: int) -> BoundedLlmDelta:
        """Clamp a raw LLM delta to the formal range."""

    @abstractmethod
    def compose(self, baseline: Regime, delta: BoundedLlmDelta) -> Regime:
        """Compose baseline regime and bounded delta."""


__all__ = ["BoundedLlmDelta", "WorldStatePolicy", "WorldStatePolicyBase"]
