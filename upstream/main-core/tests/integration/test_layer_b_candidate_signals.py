"""Integration coverage for Layer B candidate signals in L3."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from main_core.common.protocols import GraphImpactRecord
from main_core.common.types import CycleId, EntityId
from main_core.l1_l2_basis import EntityMasterRow, MarketBar
from main_core.l3_features import (
    CandidateSignalRecord,
    InMemoryMultiplierStore,
    apply_weight_multiplier,
    build_feature_signal_bundles,
)
from main_core.l4_world_state import derive_world_state
from main_core.l5_universe import select_official_alpha_pool


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
    impact_records: Sequence[GraphImpactRecord] = field(default_factory=tuple)
    impact_calls: list[CycleId] = field(default_factory=list)
    regime_calls: list[CycleId] = field(default_factory=list)

    def read_graph_impact_snapshot(
        self,
        cycle_id: CycleId,
    ) -> Sequence[GraphImpactRecord]:
        self.impact_calls.append(cycle_id)
        return self.impact_records

    def read_graph_regime_context(self, cycle_id: CycleId) -> None:
        self.regime_calls.append(cycle_id)


@dataclass
class FakeCandidateSignalPort:
    records: Sequence[CandidateSignalRecord] = field(default_factory=tuple)
    calls: list[CycleId] = field(default_factory=list)

    def read_candidate_signals(
        self,
        cycle_id: CycleId,
    ) -> Sequence[CandidateSignalRecord]:
        self.calls.append(cycle_id)
        return self.records


def test_empty_layer_b_port_matches_market_only_fallback() -> None:
    cycle_id = CycleId("cycle-layer-b-fallback")
    entity = EntityMasterRow(
        entity_id=EntityId("ENT_001"),
        ticker="AAA",
        name="Alpha A",
        exchange="NASDAQ",
    )
    market_bar = MarketBar(
        cycle_id=cycle_id,
        entity_id=entity.entity_id,
        as_of_date=date(2026, 4, 17),
        close_price=100.0,
        volume=1000.0,
        return_1d=0.01,
    )
    empty_candidate_port = FakeCandidateSignalPort()

    market_only = build_feature_signal_bundles(
        cycle_id,
        data_port=FakeDataPlatformPort(entity_master=(entity,), market_bars=(market_bar,)),
    )
    with_empty_layer_b = build_feature_signal_bundles(
        cycle_id,
        data_port=FakeDataPlatformPort(entity_master=(entity,), market_bars=(market_bar,)),
        candidate_signal_port=empty_candidate_port,
    )

    assert _stable_bundle_payload(with_empty_layer_b[0]) == _stable_bundle_payload(
        market_only[0]
    )
    assert empty_candidate_port.calls == [cycle_id]


def test_graph_and_layer_b_candidate_signals_coexist_and_flow_to_l4_l5() -> None:
    cycle_id = CycleId("cycle-layer-b-integration")
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
                cycle_id=cycle_id,
                entity_id=entity.entity_id,
                as_of_date=date(2026, 4, 17),
                close_price=100.0,
                volume=1000.0,
                return_1d=0.01,
            ),
        ),
    )
    graph_port = FakeGraphEnginePort(
        impact_records=(
            GraphImpactRecord(
                cycle_id=cycle_id,
                entity_id=entity.entity_id,
                features={"impact_score": 0.81},
                snapshot_id="graph-impact-001",
            ),
            GraphImpactRecord(
                cycle_id=cycle_id,
                entity_id=EntityId("ENT_Z"),
                features={"impact_score": 0.99},
                snapshot_id="graph-impact-extra",
            ),
        )
    )
    candidate_port = FakeCandidateSignalPort(
        records=(
            CandidateSignalRecord(
                cycle_id=cycle_id,
                entity_id=entity.entity_id,
                signal_name="layer_b_score",
                value=2.0,
                confidence=0.9,
                metadata={"source_table": "candidate_facts"},
            ),
            CandidateSignalRecord(
                cycle_id=cycle_id,
                entity_id=entity.entity_id,
                signal_name="sentiment_label",
                value="positive",
            ),
            CandidateSignalRecord(
                cycle_id=cycle_id,
                entity_id=EntityId("ENT_Z"),
                signal_name="layer_b_score",
                value=99.0,
            ),
        )
    )
    multiplier_store = InMemoryMultiplierStore()
    apply_weight_multiplier(
        cycle_id,
        {"candidate_signals.layer_b_score": 1.5},
        store=multiplier_store,
    )

    bundles = build_feature_signal_bundles(
        cycle_id,
        data_port=data_port,
        multiplier_store=multiplier_store,
        graph_engine_port=graph_port,
        candidate_signal_port=candidate_port,
    )

    assert [bundle.entity_id for bundle in bundles] == ["ENT_001"]
    assert bundles[0].graph_features == {
        "snapshot_id": "graph-impact-001",
        "features": {"impact_score": 0.81},
    }
    assert bundles[0].signal_values["candidate_signals"] == {
        "layer_b_score": {
            "raw_value": 2.0,
            "adjusted_value": 3.0,
            "source": "layer_b",
            "confidence": 0.9,
            "metadata": {"source_table": "candidate_facts"},
        },
        "sentiment_label": {
            "raw_value": "positive",
            "adjusted_value": "positive",
            "source": "layer_b",
            "confidence": None,
            "metadata": {},
        },
    }

    world_state = derive_world_state(bundles[0])
    pool = select_official_alpha_pool(world_state, bundles)

    assert world_state.cycle_id == cycle_id
    assert list(pool.selected_entities) == ["ENT_001"]
    assert graph_port.impact_calls == [cycle_id]
    assert candidate_port.calls == [cycle_id]


def _stable_bundle_payload(bundle) -> dict:
    payload = bundle.model_dump(mode="python")
    payload.pop("generated_at")
    return payload
