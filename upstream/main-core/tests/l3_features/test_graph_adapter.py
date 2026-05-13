"""Tests for read-only graph adapter consumption in L3."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

import pytest

from main_core.common.schemas.feature_bundle import FeatureSignalBundle
from main_core.common.types import CycleId, EntityId
from main_core.l1_l2_basis import EntityMasterRow, MarketBar
from main_core.l3_features import (
    GraphEnginePort,
    GraphImpactRecord,
    GraphRegimeContext,
    GraphSnapshotError,
    build_feature_signal_bundles,
    load_graph_features,
    merge_graph_features,
)

from .conftest import FakeDataPlatformPort


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


def test_graph_engine_port_is_runtime_checkable_and_read_only() -> None:
    port = FakeGraphEnginePort()

    protocol_methods = {
        name
        for name, value in GraphEnginePort.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert isinstance(port, GraphEnginePort)
    assert protocol_methods == {
        "read_graph_impact_snapshot",
        "read_graph_regime_context",
    }
    assert not {
        name
        for name in dir(GraphEnginePort)
        if name.startswith(("write_", "commit_", "mutate_"))
    }
    assert not {
        name
        for name in dir(port)
        if name.startswith(("write_", "commit_", "mutate_"))
    }


def test_load_graph_features_returns_empty_without_port_or_matching_record() -> None:
    cycle_id = CycleId("cycle-graph-l3")
    port = FakeGraphEnginePort(
        impact_records=(
            GraphImpactRecord(
                cycle_id=cycle_id,
                entity_id=EntityId("ENT_Z"),
                features={"centrality": 0.9},
                snapshot_id="graph-impact-001",
            ),
        )
    )

    assert load_graph_features(cycle_id, EntityId("ENT_001"), None) == {}
    assert load_graph_features(cycle_id, EntityId("ENT_001"), port) == {}


def test_load_graph_features_returns_snapshot_id_and_features() -> None:
    cycle_id = CycleId("cycle-graph-l3")
    port = FakeGraphEnginePort(
        impact_records=(
            GraphImpactRecord(
                cycle_id=cycle_id,
                entity_id=EntityId("ENT_001"),
                features={
                    "centrality": 0.72,
                    "neighbors": ("ENT_A", "ENT_B"),
                    "metadata": {"source": "previous_world_state"},
                },
                snapshot_id="graph-impact-001",
            ),
        )
    )

    graph_features = load_graph_features(cycle_id, EntityId("ENT_001"), port)

    assert graph_features == {
        "snapshot_id": "graph-impact-001",
        "features": {
            "centrality": 0.72,
            "neighbors": ["ENT_A", "ENT_B"],
            "metadata": {"source": "previous_world_state"},
        },
    }


def test_load_graph_features_rejects_cycle_mismatch() -> None:
    port = FakeGraphEnginePort(
        impact_records=(
            GraphImpactRecord(
                cycle_id=CycleId("cycle-other"),
                entity_id=EntityId("ENT_001"),
                features={"centrality": 0.72},
                snapshot_id="graph-impact-001",
            ),
        )
    )

    with pytest.raises(GraphSnapshotError, match="different cycle"):
        load_graph_features(CycleId("cycle-current"), EntityId("ENT_001"), port)


def test_merge_graph_features_returns_new_bundle_without_mutating_original() -> None:
    bundle = FeatureSignalBundle(
        cycle_id="cycle-graph-l3",
        entity_id="ENT_001",
        feature_values={"momentum": 0.4},
        signal_values={"direction": "positive"},
        graph_features={"legacy": {"score": 1}},
        feature_weight_multiplier={"momentum": 1.0},
    )
    before_json = bundle.to_json()

    merged = merge_graph_features(
        bundle,
        {"snapshot_id": "graph-impact-001", "features": {"centrality": 0.72}},
    )

    assert bundle.to_json() == before_json
    assert merged is not bundle
    assert merged.generated_at == bundle.generated_at
    assert merged.feature_values == bundle.feature_values
    assert merged.signal_values == bundle.signal_values
    assert merged.feature_weight_multiplier == bundle.feature_weight_multiplier
    assert merged.graph_features == {
        "snapshot_id": "graph-impact-001",
        "features": {"centrality": 0.72},
    }


def test_builder_enriches_existing_market_entities_and_ignores_graph_only_entity(
    cycle_id: CycleId,
) -> None:
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
    )
    data_port = FakeDataPlatformPort(
        entity_master=(entity,),
        market_bars=(market_bar,),
    )
    graph_port = FakeGraphEnginePort(
        impact_records=(
            GraphImpactRecord(
                cycle_id=cycle_id,
                entity_id=entity.entity_id,
                features={"centrality": 0.72},
                snapshot_id="graph-impact-001",
            ),
            GraphImpactRecord(
                cycle_id=cycle_id,
                entity_id=EntityId("ENT_Z"),
                features={"centrality": 0.95},
                snapshot_id="graph-impact-extra",
            ),
        )
    )

    bundles = build_feature_signal_bundles(
        cycle_id,
        data_port=data_port,
        graph_engine_port=graph_port,
    )

    assert [bundle.entity_id for bundle in bundles] == ["ENT_001"]
    assert bundles[0].graph_features == {
        "snapshot_id": "graph-impact-001",
        "features": {"centrality": 0.72},
    }
    assert graph_port.impact_calls == [cycle_id]
