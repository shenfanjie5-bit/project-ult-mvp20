"""Reasoner-runtime boundary for L4 world-state deltas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from main_core.common.contexts import WorldStateInputs
from main_core.common.errors import MainCoreError
from main_core.common.types import Regime


class WorldStateReasonerError(MainCoreError):
    """Raised when the L4 reasoner boundary fails."""


@dataclass(frozen=True)
class WorldStateDeltaDecision:
    """Raw reasoner decision before policy bounding and composition."""

    raw_delta: int
    rationale: str
    actual_model_used: str
    actual_provider: str
    fallback_path: list[str]


class WorldStateReasonerPort(Protocol):
    """Boundary protocol for reasoner-runtime world-state correction."""

    def propose_delta(
        self,
        inputs: WorldStateInputs,
        baseline_regime: Regime,
    ) -> WorldStateDeltaDecision:
        """Return the raw reasoner delta for the current world-state inputs."""


def _default_delta_decision() -> WorldStateDeltaDecision:
    return WorldStateDeltaDecision(
        raw_delta=0,
        rationale="static world-state delta",
        actual_model_used="static_world_state_reasoner",
        actual_provider="static",
        fallback_path=[],
    )


@dataclass(frozen=True)
class StaticWorldStateReasonerPort:
    """Deterministic reasoner fake for tests and local runs."""

    decision: WorldStateDeltaDecision = field(default_factory=_default_delta_decision)

    def propose_delta(
        self,
        inputs: WorldStateInputs,
        baseline_regime: Regime,
    ) -> WorldStateDeltaDecision:
        """Return the configured static decision."""

        return self.decision


__all__ = [
    "StaticWorldStateReasonerPort",
    "WorldStateDeltaDecision",
    "WorldStateReasonerError",
    "WorldStateReasonerPort",
]
