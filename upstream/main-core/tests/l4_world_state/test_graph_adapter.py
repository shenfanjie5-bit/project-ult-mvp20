"""Tests for graph regime context consumption in L4."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from main_core.common.contexts import WorldStateInputs
from main_core.common.protocols import (
    GraphEnginePort,
    GraphImpactRecord,
    GraphRegimeContext,
    GraphSnapshotError,
)
from main_core.common.schemas import FeatureSignalBundle, WorldStateSnapshot
from main_core.common.types import CycleId, Regime
from main_core.l4_world_state import (
    StaticWorldStateReasonerPort,
    derive_world_state,
    load_graph_regime_context,
    with_graph_impact,
)
from main_core.l4_world_state.reasoner_port import WorldStateDeltaDecision


@dataclass
class FakeGraphEnginePort:
    impact_records: Sequence[GraphImpactRecord] = field(default_factory=tuple)
    regime_context: GraphRegimeContext | None = None
    impact_calls: list[CycleId] = field(default_factory=list)
    regime_calls: list[CycleId] = field(default_factory=list)

    def read_graph_impact_snapshot(
        self,
        cycle_id: CycleId,
    ) -> Sequence[GraphImpactRecord]:
        self.impact_calls.append(cycle_id)
        return self.impact_records

    def read_graph_regime_context(
        self,
        cycle_id: CycleId,
    ) -> GraphRegimeContext | None:
        self.regime_calls.append(cycle_id)
        return self.regime_context


@dataclass
class SpyWorldStatePolicy:
    baseline_regime: Regime = "neutral"
    seen_inputs: list[WorldStateInputs] = field(default_factory=list)

    def baseline(self, inputs: WorldStateInputs) -> Regime:
        self.seen_inputs.append(inputs)
        return self.baseline_regime

    def bound_delta(self, raw_delta: int) -> int:
        if raw_delta < 0:
            return -1
        if raw_delta > 0:
            return 1
        return 0

    def compose(self, baseline: Regime, delta: int) -> Regime:
        regimes: tuple[Regime, ...] = ("risk_off", "neutral", "risk_on")
        return regimes[regimes.index(baseline) + delta]


def _decision(raw_delta: int = 0) -> WorldStateDeltaDecision:
    return WorldStateDeltaDecision(
        raw_delta=raw_delta,
        rationale="static graph test delta",
        actual_model_used="static",
        actual_provider="local",
        fallback_path=[],
    )


def test_load_graph_regime_context_returns_empty_without_port_or_context() -> None:
    cycle_id = CycleId("cycle-graph-l4")
    port = FakeGraphEnginePort()

    assert load_graph_regime_context(cycle_id, None) == {}
    assert load_graph_regime_context(cycle_id, port) == {}


def test_load_graph_regime_context_returns_world_state_input_shape() -> None:
    cycle_id = CycleId("cycle-graph-l4")
    port = FakeGraphEnginePort(
        regime_context=GraphRegimeContext(
            cycle_id=cycle_id,
            snapshot_id="graph-snapshot-001",
            regime_context={
                "previous_final_regime": "risk_on",
                "contributors": ("ENT_001", "ENT_002"),
            },
        )
    )

    graph_impact = load_graph_regime_context(cycle_id, port)

    assert graph_impact == {
        "snapshot_id": "graph-snapshot-001",
        "regime_context": {
            "previous_final_regime": "risk_on",
            "contributors": ["ENT_001", "ENT_002"],
        },
    }
    assert port.regime_calls == [cycle_id]


def test_load_graph_regime_context_rejects_cycle_mismatch() -> None:
    port = FakeGraphEnginePort(
        regime_context=GraphRegimeContext(
            cycle_id=CycleId("cycle-other"),
            snapshot_id="graph-snapshot-001",
            regime_context={"previous_final_regime": "risk_on"},
        )
    )

    with pytest.raises(GraphSnapshotError, match="different cycle"):
        load_graph_regime_context(CycleId("cycle-current"), port)


def test_with_graph_impact_returns_validated_copy(
    feature_bundle: FeatureSignalBundle,
) -> None:
    inputs = WorldStateInputs(
        cycle_id=feature_bundle.cycle_id,
        feature_bundle=feature_bundle,
        macro_context={"baseline_regime": "neutral"},
        graph_impact={"legacy": True},
    )

    updated = with_graph_impact(
        inputs,
        {"snapshot_id": "graph-snapshot-001", "regime_context": {"stress": "low"}},
    )

    assert updated is not inputs
    assert inputs.graph_impact == {"legacy": True}
    assert updated.graph_impact == {
        "snapshot_id": "graph-snapshot-001",
        "regime_context": {"stress": "low"},
    }
    assert updated.macro_context == inputs.macro_context
    assert updated.feature_bundle == inputs.feature_bundle


def test_derive_world_state_passes_graph_impact_to_policy(
    feature_bundle: FeatureSignalBundle,
) -> None:
    port = FakeGraphEnginePort(
        regime_context=GraphRegimeContext(
            cycle_id=feature_bundle.cycle_id,
            snapshot_id="graph-snapshot-001",
            regime_context={"previous_final_regime": "risk_on"},
        )
    )
    policy = SpyWorldStatePolicy()

    snapshot = derive_world_state(
        feature_bundle,
        policy=policy,
        reasoner_port=StaticWorldStateReasonerPort(_decision()),
        graph_engine_port=port,
    )

    assert isinstance(snapshot, WorldStateSnapshot)
    assert policy.seen_inputs[0].graph_impact == {
        "snapshot_id": "graph-snapshot-001",
        "regime_context": {"previous_final_regime": "risk_on"},
    }
    assert port.regime_calls == [feature_bundle.cycle_id]


def test_derive_world_state_keeps_pure_market_fallback_without_graph(
    feature_bundle: FeatureSignalBundle,
) -> None:
    policy = SpyWorldStatePolicy()

    snapshot = derive_world_state(
        feature_bundle,
        policy=policy,
        reasoner_port=StaticWorldStateReasonerPort(_decision(raw_delta=1)),
    )

    assert snapshot.baseline_regime == "neutral"
    assert snapshot.llm_delta == 1
    assert snapshot.final_regime == "risk_on"
    assert policy.seen_inputs[0].graph_impact == {}


def test_fake_graph_port_only_exposes_read_methods() -> None:
    port = FakeGraphEnginePort()

    assert isinstance(port, GraphEnginePort)
    assert not {
        name
        for name in dir(port)
        if name.startswith(("write_", "commit_", "mutate_"))
    }
