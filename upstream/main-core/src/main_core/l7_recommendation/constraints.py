"""Default deterministic constraint gates for L7 recommendations."""

from __future__ import annotations

from typing import Any

from main_core.common.contexts import RecommendationConstraintInputs
from main_core.common.protocols import RecommendationConstraintProviderBase
from main_core.common.schemas import RecommendationSnapshot


class DefaultConstraintProvider(RecommendationConstraintProviderBase):
    """Apply the default regime and risk gates required by L7."""

    def gate(
        self,
        inputs: RecommendationConstraintInputs,
        candidate: RecommendationSnapshot,
    ) -> RecommendationSnapshot:
        """Apply deterministic gates after candidate and override handling."""

        if inputs.risk_context.get("force_inconclusive") is True:
            return _with_constraint(
                candidate,
                "risk_gate",
                "force_inconclusive",
                action_type="inconclusive",
                rating=None,
                confidence=None,
            )

        if inputs.world_state.final_regime == "risk_off" and candidate.action_type == "buy":
            return _with_constraint(
                candidate,
                "regime_gate",
                "risk_off_buy_to_hold",
                action_type="hold",
                rating="B",
            )

        return candidate


def _with_constraint(
    candidate: RecommendationSnapshot,
    key: str,
    value: Any,
    **updates: Any,
) -> RecommendationSnapshot:
    constraints_applied = dict(candidate.constraints_applied)
    constraints_applied[key] = value
    return candidate.model_copy(
        update={
            **updates,
            "constraints_applied": constraints_applied,
        },
    )


__all__ = ["DefaultConstraintProvider"]
