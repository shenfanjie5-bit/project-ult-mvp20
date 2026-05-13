"""Tests for default L4 world-state policy rules."""

from __future__ import annotations

import pytest

from main_core.common.contexts import WorldStateInputs
from main_core.common.errors import MainCoreError
from main_core.common.protocols import WorldStatePolicy
from main_core.common.schemas import FeatureSignalBundle
from main_core.common.schemas.world_state import REGIME_SEQUENCE
from main_core.l4_world_state import DefaultWorldStatePolicy


def _inputs(
    feature_bundle: FeatureSignalBundle,
    *,
    signal_values: dict[str, object] | None = None,
    macro_context: dict[str, object] | None = None,
    graph_impact: dict[str, object] | None = None,
) -> WorldStateInputs:
    return WorldStateInputs(
        cycle_id=feature_bundle.cycle_id,
        feature_bundle=feature_bundle.model_copy(
            update={"signal_values": signal_values or {}},
        ),
        macro_context=macro_context or {},
        graph_impact=graph_impact or {},
    )


def test_default_world_state_policy_matches_runtime_protocol() -> None:
    policy = DefaultWorldStatePolicy()

    assert isinstance(policy, WorldStatePolicy)


def test_baseline_uses_signal_value_before_macro_context(
    feature_bundle: FeatureSignalBundle,
) -> None:
    policy = DefaultWorldStatePolicy()
    inputs = _inputs(
        feature_bundle,
        signal_values={"baseline_regime": "risk_off"},
        macro_context={"baseline_regime": "risk_on"},
    )

    assert policy.baseline(inputs) == "risk_off"


def test_baseline_uses_macro_context_when_signal_value_is_absent(
    feature_bundle: FeatureSignalBundle,
) -> None:
    policy = DefaultWorldStatePolicy()
    inputs = _inputs(feature_bundle, macro_context={"baseline_regime": "risk_on"})

    assert policy.baseline(inputs) == "risk_on"


def test_baseline_falls_back_to_neutral_without_explicit_hint(
    feature_bundle: FeatureSignalBundle,
) -> None:
    policy = DefaultWorldStatePolicy()
    inputs = _inputs(
        feature_bundle,
        graph_impact={"systemic_pressure": 0.7},
    )

    assert policy.baseline(inputs) == "neutral"


def test_baseline_rejects_unknown_explicit_regime(
    feature_bundle: FeatureSignalBundle,
) -> None:
    policy = DefaultWorldStatePolicy()
    inputs = _inputs(feature_bundle, signal_values={"baseline_regime": "euphoric"})

    with pytest.raises(MainCoreError, match="baseline_regime"):
        policy.baseline(inputs)


@pytest.mark.parametrize(
    ("raw_delta", "expected_delta"),
    [
        (-5, -1),
        (0, 0),
        (5, 1),
    ],
)
def test_bound_delta_clamps_to_formal_range(
    raw_delta: int,
    expected_delta: int,
) -> None:
    policy = DefaultWorldStatePolicy()

    assert policy.bound_delta(raw_delta) == expected_delta


def test_compose_uses_shared_regime_sequence() -> None:
    policy = DefaultWorldStatePolicy()

    assert policy.compose(REGIME_SEQUENCE[1], 1) == REGIME_SEQUENCE[2]
    assert policy.compose(REGIME_SEQUENCE[1], -1) == REGIME_SEQUENCE[0]


@pytest.mark.parametrize(
    ("baseline", "delta"),
    [
        ("risk_on", 1),
        ("risk_off", -1),
    ],
)
def test_compose_rejects_regime_sequence_overflow(
    baseline: str,
    delta: int,
) -> None:
    policy = DefaultWorldStatePolicy()

    with pytest.raises(MainCoreError, match="outside the regime sequence"):
        policy.compose(baseline, delta)  # type: ignore[arg-type]
