"""Tests for the L4 reasoner boundary port."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from main_core.common.contexts import WorldStateInputs
from main_core.common.schemas import FeatureSignalBundle
from main_core.l4_world_state import StaticWorldStateReasonerPort
from main_core.l4_world_state.reasoner_port import WorldStateDeltaDecision


def _inputs(feature_bundle: FeatureSignalBundle) -> WorldStateInputs:
    return WorldStateInputs(
        cycle_id=feature_bundle.cycle_id,
        feature_bundle=feature_bundle,
        macro_context={},
        graph_impact={},
    )


def test_delta_decision_is_frozen_dataclass() -> None:
    decision = WorldStateDeltaDecision(
        raw_delta=1,
        rationale="risk appetite improved",
        actual_model_used="static",
        actual_provider="local",
        fallback_path=[],
    )

    with pytest.raises(FrozenInstanceError):
        decision.raw_delta = 0  # type: ignore[misc]


def test_static_reasoner_port_returns_configured_decision(
    feature_bundle: FeatureSignalBundle,
) -> None:
    decision = WorldStateDeltaDecision(
        raw_delta=-1,
        rationale="risk appetite worsened",
        actual_model_used="static",
        actual_provider="local",
        fallback_path=["fixture"],
    )
    port = StaticWorldStateReasonerPort(decision)

    assert port.propose_delta(_inputs(feature_bundle), "neutral") == decision
