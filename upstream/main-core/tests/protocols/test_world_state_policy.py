"""Tests for the L4 world-state policy protocol contract."""

from __future__ import annotations

import pytest

from main_core.common.contexts import WorldStateInputs
from main_core.common.protocols import BoundedLlmDelta, WorldStatePolicy
from main_core.common.schemas import FeatureSignalBundle
from main_core.l4_world_state import DefaultWorldStatePolicy

CYCLE_ID = "cycle_001"
ENTITY_ID = "ENT_001"
EXPECTED_NEGATIVE_DELTA = -1
EXPECTED_NEUTRAL_DELTA = 0
EXPECTED_POSITIVE_DELTA = 1


def _world_state_inputs() -> WorldStateInputs:
    return WorldStateInputs(
        cycle_id=CYCLE_ID,
        feature_bundle=FeatureSignalBundle(
            cycle_id=CYCLE_ID,
            entity_id=ENTITY_ID,
            feature_values={"volatility": 0.2},
            signal_values={},
            graph_features={},
            feature_weight_multiplier={"volatility": 1.0},
        ),
        macro_context={},
        graph_impact={},
    )


def test_world_state_policy_protocol_imports() -> None:
    assert WorldStatePolicy is not None
    assert BoundedLlmDelta is not None


def test_default_world_state_policy_matches_runtime_protocol() -> None:
    policy = DefaultWorldStatePolicy()

    assert isinstance(policy, WorldStatePolicy)


@pytest.mark.parametrize(
    ("raw_delta", "expected_delta"),
    [
        (-5, EXPECTED_NEGATIVE_DELTA),
        (-2, EXPECTED_NEGATIVE_DELTA),
        (-1, EXPECTED_NEGATIVE_DELTA),
        (0, EXPECTED_NEUTRAL_DELTA),
        (1, EXPECTED_POSITIVE_DELTA),
        (2, EXPECTED_POSITIVE_DELTA),
        (5, EXPECTED_POSITIVE_DELTA),
    ],
)
def test_bound_delta_clamps_to_formal_range(raw_delta: int, expected_delta: int) -> None:
    policy = DefaultWorldStatePolicy()

    assert policy.bound_delta(raw_delta) == expected_delta


def test_default_world_state_policy_derives_neutral_baseline() -> None:
    policy = DefaultWorldStatePolicy()

    assert policy.baseline(_world_state_inputs()) == "neutral"


def test_default_world_state_policy_composes_final_regime() -> None:
    policy = DefaultWorldStatePolicy()

    assert policy.compose("neutral", 1) == "risk_on"
