"""Default L4 world-state policy rules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from main_core.common.contexts import WorldStateInputs
from main_core.common.errors import MainCoreError
from main_core.common.protocols import BoundedLlmDelta, WorldStatePolicyBase
from main_core.common.schemas.world_state import REGIME_SEQUENCE
from main_core.common.types import Regime


class WorldStatePolicyError(MainCoreError):
    """Raised when L4 policy rules cannot produce a valid regime."""


class DefaultWorldStatePolicy(WorldStatePolicyBase):
    """Deterministic L4 rule skeleton for deriving shared world state."""

    def baseline(self, inputs: WorldStateInputs) -> Regime:
        """Derive baseline regime from explicit hints, else fall back to neutral."""

        signal_baseline = _explicit_baseline(
            inputs.feature_bundle.signal_values,
            "signal_values",
        )
        if signal_baseline is not None:
            return signal_baseline

        macro_baseline = _explicit_baseline(inputs.macro_context, "macro_context")
        if macro_baseline is not None:
            return macro_baseline

        return "neutral"

    def bound_delta(self, raw_delta: int) -> BoundedLlmDelta:
        """Clamp raw LLM deltas to the formal ``-1`` / ``0`` / ``+1`` range."""

        if raw_delta < 0:
            return -1
        if raw_delta > 0:
            return 1
        return 0

    def compose(self, baseline: Regime, delta: BoundedLlmDelta) -> Regime:
        """Compose baseline regime and bounded LLM delta into a final regime."""

        try:
            baseline_index = REGIME_SEQUENCE.index(baseline)
        except ValueError as exc:
            raise WorldStatePolicyError(
                f"unknown baseline_regime {baseline!r}",
            ) from exc

        final_index = baseline_index + delta
        if final_index < 0 or final_index >= len(REGIME_SEQUENCE):
            raise WorldStatePolicyError(
                "baseline_regime + llm_delta is outside the regime sequence",
            )

        return REGIME_SEQUENCE[final_index]


def _explicit_baseline(
    values: Mapping[str, Any],
    source_name: str,
) -> Regime | None:
    if "baseline_regime" not in values:
        return None

    regime = values["baseline_regime"]
    if regime not in REGIME_SEQUENCE:
        raise WorldStatePolicyError(
            f"{source_name}.baseline_regime must be one of {REGIME_SEQUENCE}",
        )
    return cast(Regime, regime)


__all__ = ["DefaultWorldStatePolicy", "WorldStatePolicyError"]
