"""Integration coverage for read-only graph consumption across L3 and L4."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from main_core.common.contexts import WorldStateInputs
from main_core.common.protocols import GraphImpactRecord, GraphRegimeContext
from main_core.common.schemas import WorldStateSnapshot
from main_core.common.types import CycleId, EntityId, Regime
from main_core.l1_l2_basis import EntityMasterRow, MarketBar
from main_core.l3_features import build_feature_signal_bundles
from main_core.l4_world_state import StaticWorldStateReasonerPort, derive_world_state
from main_core.l4_world_state.reasoner_port import WorldStateDeltaDecision


@dataclass
class FakeDataPlatformPort:
    market_bars: Sequence[object] = field(default_factory=tuple)
    entity_master: Sequence[object] = field(default_factory=tuple)

    def read_market_bars(self, cycle_id: CycleId | str) -> Sequence[object]:
        return self.market_bars

    def read_calendar(self, cycle_id: CycleId | str) -> Sequence[object]:
        return ()

    def read_entity_master(self, cycle_id: CycleId | str) -> Sequence[object]:
        return self.entity_master


@dataclass
class FakeGraphEnginePort:
    previous_world_state: WorldStateSnapshot
    graph_only_entity_id: EntityId = EntityId("ENT_Z")
    impact_calls: list[CycleId] = field(default_factory=list)
    regime_calls: list[CycleId] = field(default_factory=list)

    def read_graph_impact_snapshot(
        self,
        cycle_id: CycleId,
    ) -> Sequence[GraphImpactRecord]:
        self.impact_calls.append(cycle_id)
        return (
            GraphImpactRecord(
                cycle_id=cycle_id,
                entity_id=EntityId("ENT_001"),
                snapshot_id=f"graph-impact-{cycle_id}",
                features={
                    "previous_cycle_id": str(self.previous_world_state.cycle_id),
                    "previous_final_regime": self.previous_world_state.final_regime,
                    "impact_score": 0.81,
                },
            ),
            GraphImpactRecord(
                cycle_id=cycle_id,
                entity_id=self.graph_only_entity_id,
                snapshot_id=f"graph-impact-extra-{cycle_id}",
                features={"impact_score": 0.99},
            ),
        )

    def read_graph_regime_context(
        self,
        cycle_id: CycleId,
    ) -> GraphRegimeContext | None:
        self.regime_calls.append(cycle_id)
        return GraphRegimeContext(
            cycle_id=cycle_id,
            snapshot_id=f"graph-snapshot-{cycle_id}",
            regime_context={
                "previous_cycle_id": str(self.previous_world_state.cycle_id),
                "previous_final_regime": self.previous_world_state.final_regime,
                "previous_llm_delta": self.previous_world_state.llm_delta,
            },
        )


@dataclass
class CapturingWorldStatePolicy:
    seen_inputs: list[WorldStateInputs] = field(default_factory=list)

    def baseline(self, inputs: WorldStateInputs) -> Regime:
        self.seen_inputs.append(inputs)
        return "neutral"

    def bound_delta(self, raw_delta: int) -> int:
        if raw_delta < 0:
            return -1
        if raw_delta > 0:
            return 1
        return 0

    def compose(self, baseline: Regime, delta: int) -> Regime:
        regimes: tuple[Regime, ...] = ("risk_off", "neutral", "risk_on")
        return regimes[regimes.index(baseline) + delta]


def test_previous_world_state_feeds_readonly_graph_context_into_l3_and_l4() -> None:
    previous_cycle_id = CycleId("cycle-previous")
    current_cycle_id = CycleId("cycle-current")
    previous_world_state = WorldStateSnapshot(
        cycle_id=previous_cycle_id,
        baseline_regime="neutral",
        llm_delta=1,
        final_regime="risk_on",
        llm_rationale="previous cycle risk appetite improved",
        actual_model_used="static",
        actual_provider="local",
        fallback_path=[],
    )
    entity = EntityMasterRow(
        entity_id=EntityId("ENT_001"),
        ticker="AAA",
        name="Alpha A",
        exchange="NASDAQ",
    )
    data_port = FakeDataPlatformPort(
        entity_master=(entity,),
        market_bars=(
            MarketBar(
                cycle_id=current_cycle_id,
                entity_id=entity.entity_id,
                as_of_date=date(2026, 4, 17),
                close_price=100.0,
                volume=1000.0,
                return_1d=0.01,
            ),
        ),
    )
    graph_port = FakeGraphEnginePort(previous_world_state=previous_world_state)

    bundles = build_feature_signal_bundles(
        current_cycle_id,
        data_port=data_port,
        graph_engine_port=graph_port,
    )

    assert [bundle.entity_id for bundle in bundles] == ["ENT_001"]
    assert bundles[0].graph_features == {
        "snapshot_id": "graph-impact-cycle-current",
        "features": {
            "previous_cycle_id": "cycle-previous",
            "previous_final_regime": "risk_on",
            "impact_score": 0.81,
        },
    }

    policy = CapturingWorldStatePolicy()
    world_state = derive_world_state(
        bundles[0],
        policy=policy,
        reasoner_port=StaticWorldStateReasonerPort(
            WorldStateDeltaDecision(
                raw_delta=0,
                rationale="static integration delta",
                actual_model_used="static",
                actual_provider="local",
                fallback_path=[],
            )
        ),
        graph_engine_port=graph_port,
    )

    assert world_state.cycle_id == current_cycle_id
    assert world_state.final_regime == "neutral"
    assert policy.seen_inputs[0].graph_impact == {
        "snapshot_id": "graph-snapshot-cycle-current",
        "regime_context": {
            "previous_cycle_id": "cycle-previous",
            "previous_final_regime": "risk_on",
            "previous_llm_delta": 1,
        },
    }
    assert graph_port.impact_calls == [current_cycle_id]
    assert graph_port.regime_calls == [current_cycle_id]
