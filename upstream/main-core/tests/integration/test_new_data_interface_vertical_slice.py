"""Vertical proof for extracted data-source signals entering graph/reasoner paths."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import pytest

from main_core.common.contexts import WorldStateInputs
from main_core.common.protocols import GraphImpactRecord, GraphRegimeContext
from main_core.common.schemas import AlphaResultSnapshot
from main_core.common.types import CycleId, EntityId, Regime
from main_core.l1_l2_basis import EntityMasterRow, MarketBar
from main_core.l3_features import CandidateSignalRecord, build_feature_signal_bundles
from main_core.l4_world_state import derive_world_state
from main_core.l4_world_state.reasoner_port import (
    WorldStateDeltaDecision,
)
from main_core.l5_universe import select_official_alpha_pool
from main_core.l7_recommendation import generate_recommendations

contracts = pytest.importorskip("contracts")
reasoner_runtime = pytest.importorskip("reasoner_runtime")

from contracts.core import Direction, HeartbeatStatus  # noqa: E402
from contracts.protocols import DataSourceBatch  # noqa: E402
from contracts.schemas import (  # noqa: E402
    Ex0Metadata,
    Ex1CandidateFact,
    Ex2CandidateSignal,
    Ex3CandidateGraphDelta,
    GraphImpactSnapshot,
    GraphSnapshot,
)
from contracts.schemas.cycle import CycleMetadata, CyclePhase  # noqa: E402
from contracts.schemas.entities import EntityReference  # noqa: E402
from contracts.schemas.graph import GraphEdge, GraphNode  # noqa: E402

CYCLE_ID = CycleId("CYCLE_20260427_VERTICAL")
ENTITY_ID = EntityId("ENT_STOCK_600519.SH")
SECTOR_ID = "SECTOR_BAIJIU"
EVENT_NODE_ID = "ENT_EVENT_earnings_notice_5b6f6d42"
EVIDENCE_REF = "evidence:earnings-notice:20260427:600519"
SNAPSHOT_ID = "graph-impact-CYCLE_20260427_VERTICAL-001"
NOW = datetime(2026, 4, 27, 9, 30, tzinfo=UTC)


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
class Ex2CandidateSignalPort:
    signals: Sequence[Ex2CandidateSignal] = field(default_factory=tuple)
    calls: list[CycleId] = field(default_factory=list)

    def read_candidate_signals(
        self,
        cycle_id: CycleId,
    ) -> Sequence[CandidateSignalRecord]:
        self.calls.append(cycle_id)
        records: list[CandidateSignalRecord] = []
        for signal in self.signals:
            if str(signal.producer_context["cycle_id"]) != str(cycle_id):
                continue
            for entity_id in signal.affected_entities:
                records.append(
                    CandidateSignalRecord(
                        cycle_id=cycle_id,
                        entity_id=EntityId(str(entity_id)),
                        signal_name=signal.signal_type,
                        value=signal.magnitude,
                        source=f"layer_b:{signal.subsystem_id}",
                        confidence=signal.confidence,
                        metadata={
                            "signal_id": signal.signal_id,
                            "direction": signal.direction.value,
                            "affected_sectors": list(signal.affected_sectors),
                            "evidence": list(signal.evidence),
                            "event_node_id": signal.producer_context["event_node_id"],
                        },
                    )
                )
        return records


@dataclass
class GraphImpactSnapshotPort:
    impact_snapshot: GraphImpactSnapshot
    calls: list[CycleId] = field(default_factory=list)

    def read_graph_impact_snapshot(
        self,
        cycle_id: CycleId,
    ) -> Sequence[GraphImpactRecord]:
        self.calls.append(cycle_id)
        snapshot = self.impact_snapshot
        if snapshot.cycle_id != str(cycle_id):
            return ()
        return tuple(
            GraphImpactRecord(
                cycle_id=cycle_id,
                entity_id=EntityId(reference.entity_id),
                snapshot_id=snapshot.impact_snapshot_id,
                features={
                    "impact_score": snapshot.impact_score,
                    "direction": snapshot.direction.value,
                    "affected_sectors": list(snapshot.affected_sectors),
                    "evidence_refs": list(snapshot.evidence_refs),
                    "target_entities": [
                        target.model_dump(mode="json")
                        for target in snapshot.target_entities
                    ],
                },
            )
            for reference in snapshot.affected_entities
        )

    def read_graph_regime_context(self, cycle_id: CycleId) -> GraphRegimeContext | None:
        if self.impact_snapshot.cycle_id != str(cycle_id):
            return None
        return GraphRegimeContext(
            cycle_id=cycle_id,
            snapshot_id=self.impact_snapshot.impact_snapshot_id,
            regime_context={
                "graph_impact_snapshot_id": self.impact_snapshot.impact_snapshot_id,
                "graph_impact_direction": self.impact_snapshot.direction.value,
            },
        )


@dataclass
class RecordingReasonerRuntimePort:
    requests: list[reasoner_runtime.ReasonerRequest] = field(default_factory=list)

    def propose_delta(
        self,
        inputs: WorldStateInputs,
        baseline_regime: Regime,
    ) -> WorldStateDeltaDecision:
        evidence_refs = _evidence_refs_from_inputs(inputs)
        request = reasoner_runtime.ReasonerRequest(
            request_id=f"reasoner-{inputs.cycle_id}",
            caller_module="main-core.l4_world_state",
            target_schema="WorldStateDeltaDecision",
            messages=[
                {
                    "role": "user",
                    "content": "Assess extracted event impact for current-cycle world state.",
                }
            ],
            configured_provider="openai-codex",
            configured_model="codex",
            max_retries=0,
            metadata={
                "cycle_id": str(inputs.cycle_id),
                "baseline_regime": baseline_regime,
                "feature_bundle": inputs.feature_bundle.model_dump(mode="json"),
                "graph_impact": inputs.graph_impact,
            },
            input_refs=evidence_refs,
        )
        self.requests.append(request)
        return WorldStateDeltaDecision(
            raw_delta=1,
            rationale="reasoner-runtime consumed event signal and graph impact",
            actual_model_used=request.configured_model,
            actual_provider=request.configured_provider,
            fallback_path=[],
        )


def test_extracted_event_flows_to_graph_reasoner_recommendation() -> None:
    batch, graph_snapshot, impact_snapshot = _new_data_interface_payloads()

    assert batch.signals[0].affected_sectors == [SECTOR_ID]
    assert graph_snapshot.nodes[0].node_id == EVENT_NODE_ID
    assert graph_snapshot.edges[0].source_node == EVENT_NODE_ID

    data_port = FakeDataPlatformPort(
        entity_master=(
            EntityMasterRow(
                entity_id=ENTITY_ID,
                ticker="600519.SH",
                name="Kweichow Moutai",
                exchange="SSE",
            ),
        ),
        market_bars=(
            MarketBar(
                cycle_id=CYCLE_ID,
                entity_id=ENTITY_ID,
                as_of_date=date(2026, 4, 27),
                close_price=1720.0,
                volume=1800000.0,
                return_1d=0.012,
            ),
        ),
    )
    graph_port = GraphImpactSnapshotPort(impact_snapshot=impact_snapshot)
    candidate_port = Ex2CandidateSignalPort(signals=batch.signals)

    bundles = build_feature_signal_bundles(
        CYCLE_ID,
        data_port=data_port,
        graph_engine_port=graph_port,
        candidate_signal_port=candidate_port,
    )

    assert [bundle.entity_id for bundle in bundles] == [ENTITY_ID]
    candidate_payload = bundles[0].signal_values["candidate_signals"][
        "event_industry_price_impact"
    ]
    assert candidate_payload["metadata"]["event_node_id"] == EVENT_NODE_ID
    assert list(candidate_payload["metadata"]["affected_sectors"]) == [SECTOR_ID]
    assert list(candidate_payload["metadata"]["evidence"]) == [EVIDENCE_REF]
    graph_features = bundles[0].model_dump(mode="json")["graph_features"]
    assert graph_features == {
        "snapshot_id": SNAPSHOT_ID,
        "features": {
            "impact_score": 0.42,
            "direction": "bullish",
            "affected_sectors": [SECTOR_ID],
            "evidence_refs": [EVIDENCE_REF],
            "target_entities": [
                {
                    "entity_id": ENTITY_ID,
                    "entity_type": "stock",
                    "canonical_id_rule_version": "ent-id-rule-v1",
                    "display_name": "Kweichow Moutai",
                }
            ],
        },
    }

    reasoner_port = RecordingReasonerRuntimePort()
    world_state = derive_world_state(
        bundles[0],
        graph_engine_port=graph_port,
        graph_impact=bundles[0].graph_features,
        reasoner_port=reasoner_port,
    )

    assert world_state.final_regime == "risk_on"
    request = reasoner_port.requests[0]
    assert request.configured_provider == "openai-codex"
    assert request.input_refs == [EVIDENCE_REF]
    assert request.context["graph_impact"]["features"]["impact_score"] == 0.42
    assert (
        request.context["feature_bundle"]["signal_values"]["candidate_signals"][
            "event_industry_price_impact"
        ]["metadata"]["event_node_id"]
        == EVENT_NODE_ID
    )

    pool = select_official_alpha_pool(world_state, bundles)
    recommendations = generate_recommendations(
        pool,
        analyses=[
            AlphaResultSnapshot(
                cycle_id=CYCLE_ID,
                entity_id=ENTITY_ID,
                analyzer_type="multi_agent_v1",
                score=0.72,
                confidence=0.86,
                rationale="L6 consumed event signal and graph impact",
                similar_cases=[],
                status="ok",
            )
        ],
        world_state=world_state,
    )

    assert recommendations[0].entity_id == ENTITY_ID
    assert recommendations[0].action_type == "buy"
    assert candidate_port.calls == [CYCLE_ID]
    assert graph_port.calls == [CYCLE_ID]


def _new_data_interface_payloads() -> tuple[
    DataSourceBatch,
    GraphSnapshot,
    GraphImpactSnapshot,
]:
    stock_ref = EntityReference(
        entity_id=ENTITY_ID,
        entity_type="stock",
        canonical_id_rule_version="ent-id-rule-v1",
        display_name="Kweichow Moutai",
    )
    event_ref = EntityReference(
        entity_id=EVENT_NODE_ID,
        entity_type="event",
        canonical_id_rule_version="ent-id-rule-v1",
        display_name="Controlled policy event",
    )
    sector_ref = EntityReference(
        entity_id=SECTOR_ID,
        entity_type="sector",
        canonical_id_rule_version="ent-id-rule-v1",
        display_name="Baijiu",
    )
    cycle = CycleMetadata(
        cycle_id=CYCLE_ID,
        phase=CyclePhase.ANALYZING,
        started_at=NOW,
    )
    metadata = Ex0Metadata(
        subsystem_id="subsystem-controlled-event",
        version="0.1.0",
        heartbeat_at=NOW,
        status=HeartbeatStatus.OK,
        last_output_at=NOW,
        pending_count=0,
    )
    fact = Ex1CandidateFact(
        subsystem_id=metadata.subsystem_id,
        fact_id="fact-event-600519-policy-20260427",
        entity_id=ENTITY_ID,
        fact_type="controlled_event_summary",
        fact_content={
            "event_node_id": EVENT_NODE_ID,
            "headline": "Controlled event expected to support baijiu demand",
        },
        confidence=0.88,
        source_reference={
            "source": "controlled_new_data_interface_fixture",
            "cycle_id": cycle.cycle_id,
        },
        extracted_at=NOW,
        evidence=[EVIDENCE_REF],
        producer_context={"cycle_id": cycle.cycle_id},
    )
    signal = Ex2CandidateSignal(
        subsystem_id=metadata.subsystem_id,
        signal_id="signal-event-600519-policy-20260427",
        signal_type="event_industry_price_impact",
        direction=Direction.BULLISH,
        magnitude=0.42,
        affected_entities=[ENTITY_ID],
        affected_sectors=[SECTOR_ID],
        time_horizon="1-3d",
        evidence=[EVIDENCE_REF],
        confidence=0.81,
        producer_context={
            "cycle_id": cycle.cycle_id,
            "event_node_id": EVENT_NODE_ID,
            "event_anchor_policy": "deterministic_layer_a_entity",
        },
    )
    delta = Ex3CandidateGraphDelta(
        subsystem_id=metadata.subsystem_id,
        delta_id="delta-event-baijiu-impact-20260427",
        delta_type="add_edge",
        source_node=EVENT_NODE_ID,
        target_node=SECTOR_ID,
        relation_type="impacts_sector",
        properties={
            "direction": Direction.BULLISH.value,
            "magnitude": 0.42,
            "time_horizon": "1-3d",
        },
        evidence=[EVIDENCE_REF],
        producer_context={
            "cycle_id": cycle.cycle_id,
            "event_anchor_policy": "deterministic_layer_a_entity",
        },
    )
    graph_snapshot = GraphSnapshot(
        graph_snapshot_id="graph-CYCLE_20260427_VERTICAL-001",
        cycle_id=CYCLE_ID,
        version="0.1.0",
        created_at=NOW,
        node_count=3,
        edge_count=1,
        nodes=[
            GraphNode(
                node_id=EVENT_NODE_ID,
                labels=["Event"],
                properties={"anchored": True, "source": "LayerA"},
                entity=event_ref,
            ),
            GraphNode(
                node_id=ENTITY_ID,
                labels=["Stock"],
                properties={"ts_code": "600519.SH"},
                entity=stock_ref,
            ),
            GraphNode(
                node_id=SECTOR_ID,
                labels=["Sector"],
                properties={},
                entity=sector_ref,
            ),
        ],
        edges=[
            GraphEdge(
                edge_id="edge-event-sector-20260427",
                source_node=EVENT_NODE_ID,
                target_node=SECTOR_ID,
                relation_type="impacts_sector",
                properties={"direction": "bullish", "magnitude": 0.42},
                evidence_refs=[EVIDENCE_REF],
            )
        ],
    )
    impact_snapshot = GraphImpactSnapshot(
        impact_snapshot_id=SNAPSHOT_ID,
        cycle_id=CYCLE_ID,
        version="0.1.0",
        created_at=NOW,
        target_entities=[stock_ref],
        affected_entities=[stock_ref],
        affected_sectors=[SECTOR_ID],
        direction=Direction.BULLISH,
        impact_score=0.42,
        evidence_refs=[EVIDENCE_REF],
    )
    return (
        DataSourceBatch(
            metadata=metadata,
            facts=[fact],
            signals=[signal],
            graph_deltas=[delta],
        ),
        graph_snapshot,
        impact_snapshot,
    )


def _evidence_refs_from_inputs(inputs: WorldStateInputs) -> list[str]:
    refs: set[str] = set()
    candidate_payload = inputs.feature_bundle.signal_values.get("candidate_signals", {})
    if isinstance(candidate_payload, dict):
        for signal in candidate_payload.values():
            if not isinstance(signal, dict):
                continue
            metadata = signal.get("metadata", {})
            if isinstance(metadata, dict):
                refs.update(str(ref) for ref in metadata.get("evidence", []))

    graph_features = inputs.graph_impact.get("features", {})
    if isinstance(graph_features, dict):
        refs.update(str(ref) for ref in graph_features.get("evidence_refs", []))
    return sorted(refs)
