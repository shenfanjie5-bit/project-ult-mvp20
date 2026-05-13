"""Tests for deriving formal L4 world-state snapshots."""

from __future__ import annotations

import pytest

from main_core.common.contexts import WorldStateInputs
from main_core.common.errors import MainCoreError
from main_core.common.schemas import FeatureSignalBundle, WorldStateSnapshot
from main_core.common.types import Regime
from main_core.l4_world_state import (
    StaticWorldStateReasonerPort,
    derive_world_state,
)
from main_core.l4_world_state.reasoner_port import (
    WorldStateDeltaDecision,
    WorldStateReasonerError,
)


def _decision(
    *,
    raw_delta: int = 0,
    rationale: str = "static world-state delta",
    actual_model_used: str = "static",
    actual_provider: str = "local",
    fallback_path: list[str] | None = None,
) -> WorldStateDeltaDecision:
    return WorldStateDeltaDecision(
        raw_delta=raw_delta,
        rationale=rationale,
        actual_model_used=actual_model_used,
        actual_provider=actual_provider,
        fallback_path=list(fallback_path or []),
    )


def test_derive_world_state_happy_path_returns_snapshot(
    feature_bundle: FeatureSignalBundle,
) -> None:
    snapshot = derive_world_state(
        feature_bundle,
        reasoner_port=StaticWorldStateReasonerPort(
            _decision(
                raw_delta=1,
                rationale="risk appetite improved",
                fallback_path=["static"],
            ),
        ),
    )

    assert isinstance(snapshot, WorldStateSnapshot)
    assert snapshot.baseline_regime == "neutral"
    assert snapshot.llm_delta == 1
    assert snapshot.final_regime == "risk_on"
    assert snapshot.llm_rationale == "risk appetite improved"
    assert snapshot.fallback_path == ("static",)


@pytest.mark.parametrize(
    ("raw_delta", "expected_delta", "expected_final"),
    [
        (3, 1, "risk_on"),
        (-3, -1, "risk_off"),
    ],
)
def test_derive_world_state_bounds_raw_reasoner_delta(
    feature_bundle: FeatureSignalBundle,
    raw_delta: int,
    expected_delta: int,
    expected_final: Regime,
) -> None:
    snapshot = derive_world_state(
        feature_bundle,
        reasoner_port=StaticWorldStateReasonerPort(_decision(raw_delta=raw_delta)),
    )

    assert snapshot.llm_delta == expected_delta
    assert snapshot.final_regime == expected_final


def test_derive_world_state_uses_feature_values_without_reapplying_multiplier() -> None:
    bundle = FeatureSignalBundle(
        cycle_id="cycle_weighted",
        entity_id="ENT_001",
        feature_values={"momentum": 9.0},
        signal_values={},
        graph_features={},
        feature_weight_multiplier={"momentum": 3.0},
    )

    snapshot = derive_world_state(bundle)

    assert snapshot.baseline_regime == "neutral"
    assert snapshot.llm_delta == 0
    assert snapshot.final_regime == "neutral"


@pytest.mark.parametrize(
    ("baseline_regime", "raw_delta"),
    [
        ("risk_on", 1),
        ("risk_off", -1),
    ],
)
def test_derive_world_state_rejects_regime_sequence_overflow(
    feature_bundle: FeatureSignalBundle,
    baseline_regime: Regime,
    raw_delta: int,
) -> None:
    with pytest.raises(MainCoreError, match="outside the regime sequence"):
        derive_world_state(
            feature_bundle,
            reasoner_port=StaticWorldStateReasonerPort(_decision(raw_delta=raw_delta)),
            macro_context={"baseline_regime": baseline_regime},
        )


def test_derive_world_state_propagates_main_core_reasoner_errors(
    feature_bundle: FeatureSignalBundle,
) -> None:
    class FailingReasoner:
        def propose_delta(
            self,
            inputs: WorldStateInputs,
            baseline_regime: Regime,
        ) -> WorldStateDeltaDecision:
            raise WorldStateReasonerError("reasoner unavailable")

    with pytest.raises(WorldStateReasonerError, match="reasoner unavailable"):
        derive_world_state(feature_bundle, reasoner_port=FailingReasoner())


def test_derive_world_state_wraps_unknown_reasoner_errors(
    feature_bundle: FeatureSignalBundle,
) -> None:
    class BrokenReasoner:
        def propose_delta(
            self,
            inputs: WorldStateInputs,
            baseline_regime: Regime,
        ) -> WorldStateDeltaDecision:
            raise RuntimeError("provider exploded")

    with pytest.raises(WorldStateReasonerError, match="world-state reasoner failed"):
        derive_world_state(feature_bundle, reasoner_port=BrokenReasoner())
