"""L4 formal world state schema."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from main_core.common.schemas.base import FormalObjectBase
from main_core.common.types import CycleId, Regime

REGIME_SEQUENCE: tuple[Regime, ...] = ("risk_off", "neutral", "risk_on")


class WorldStateSnapshot(FormalObjectBase):
    """Formal L4 shared world state snapshot described in §9.3."""

    cycle_id: CycleId
    baseline_regime: Regime
    llm_delta: Literal[-1, 0, 1]
    final_regime: Regime
    llm_rationale: str
    actual_model_used: str
    actual_provider: str
    fallback_path: list[str]

    @model_validator(mode="after")
    def validate_final_regime(self) -> WorldStateSnapshot:
        """Require final_regime to match baseline_regime shifted by llm_delta."""

        baseline_index = REGIME_SEQUENCE.index(self.baseline_regime)
        final_index = baseline_index + self.llm_delta
        if final_index < 0 or final_index >= len(REGIME_SEQUENCE):
            raise ValueError("baseline_regime + llm_delta is outside the regime sequence")

        expected_final_regime = REGIME_SEQUENCE[final_index]
        if self.final_regime != expected_final_regime:
            raise ValueError("final_regime must equal baseline_regime shifted by llm_delta")

        return self


__all__ = ["REGIME_SEQUENCE", "WorldStateSnapshot"]
