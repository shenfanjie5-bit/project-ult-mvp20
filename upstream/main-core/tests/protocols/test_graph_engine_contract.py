"""Tests for the shared graph-engine protocol contract."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from main_core import l3_features
from main_core.common.protocols import (
    GraphEnginePort,
    GraphImpactRecord,
    GraphRegimeContext,
    GraphSnapshotError,
)
from main_core.common.types import CycleId, EntityId
from main_core.l3_features import graph_adapter as l3_graph_adapter


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


def test_graph_contract_is_owned_by_common_protocols() -> None:
    assert GraphEnginePort.__module__ == "main_core.common.protocols.graph"
    assert GraphImpactRecord.__module__ == "main_core.common.protocols.graph"
    assert GraphRegimeContext.__module__ == "main_core.common.protocols.graph"
    assert GraphSnapshotError.__module__ == "main_core.common.protocols.graph"


def test_l3_graph_exports_are_compatibility_aliases() -> None:
    assert l3_features.GraphEnginePort is GraphEnginePort
    assert l3_features.GraphImpactRecord is GraphImpactRecord
    assert l3_features.GraphRegimeContext is GraphRegimeContext
    assert l3_features.GraphSnapshotError is GraphSnapshotError


def test_l3_adapter_only_exports_adapter_helpers() -> None:
    assert set(l3_graph_adapter.__all__) == {
        "load_graph_features",
        "merge_graph_features",
    }


def test_graph_engine_port_is_runtime_checkable_and_read_only() -> None:
    cycle_id = CycleId("cycle-graph-contract")
    port = FakeGraphEnginePort(
        impact_records=(
            GraphImpactRecord(
                cycle_id=cycle_id,
                entity_id=EntityId("ENT_001"),
                features={"centrality": 0.72},
                snapshot_id="graph-impact-001",
            ),
        ),
        regime_context=GraphRegimeContext(
            cycle_id=cycle_id,
            snapshot_id="graph-regime-001",
            regime_context={"previous_final_regime": "neutral"},
        ),
    )

    assert isinstance(port, GraphEnginePort)
    assert port.read_graph_impact_snapshot(cycle_id)[0].entity_id == "ENT_001"
    assert port.read_graph_regime_context(cycle_id) == port.regime_context
    assert not {
        name
        for name in dir(GraphEnginePort)
        if name.startswith(("write_", "commit_", "mutate_"))
    }
