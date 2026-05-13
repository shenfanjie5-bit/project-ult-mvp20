from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

import graph_engine.promotion.service as service_module
from graph_engine.client import Neo4jClient
from graph_engine.models import (
    CandidateGraphDelta,
    FrozenGraphDelta,
    Neo4jGraphStatus,
    PropagationResult,
    PromotionPlan,
)
from graph_engine.promotion import build_promotion_plan, promote_graph_deltas
from graph_engine.promotion.planner import validate_entity_anchors
from graph_engine.schema.definitions import NodeLabel, RelationshipType
from graph_engine.snapshots import build_graph_impact_snapshot
from graph_engine.status import GraphStatusManager
from tests.fakes import InMemoryStatusStore

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)


class FakeCandidateReader:
    def __init__(self, deltas: list[CandidateGraphDelta]) -> None:
        self.deltas = deltas
        self.calls: list[tuple[str, str]] = []

    def read_candidate_graph_deltas(
        self,
        cycle_id: str,
        selection_ref: str,
    ) -> list[CandidateGraphDelta]:
        self.calls.append((cycle_id, selection_ref))
        return self.deltas


class FakeLegacyCandidateReader:
    def __init__(self, deltas: list[FrozenGraphDelta]) -> None:
        self.deltas = deltas
        self.calls: list[tuple[str, str]] = []

    def read_candidate_graph_deltas(
        self,
        cycle_id: str,
        selection_ref: str,
    ) -> list[FrozenGraphDelta]:
        self.calls.append((cycle_id, selection_ref))
        return self.deltas


class FakeEntityReader:
    def __init__(
        self,
        existing_ids: set[str],
        node_entity_ids: dict[str, str] | None = None,
    ) -> None:
        self.existing_ids = existing_ids
        self.node_entity_ids = node_entity_ids or {}
        self.node_calls: list[set[str]] = []
        self.calls: list[set[str]] = []

    def canonical_entity_ids_for_node_ids(self, node_ids: set[str]) -> dict[str, str]:
        self.node_calls.append(node_ids)
        return {
            node_id: self.node_entity_ids[node_id]
            for node_id in node_ids
            if node_id in self.node_entity_ids
        }

    def existing_entity_ids(self, entity_ids: set[str]) -> set[str]:
        self.calls.append(entity_ids)
        return self.existing_ids


class FakeCanonicalWriter:
    def __init__(self, calls: list[str] | None = None, fail: bool = False) -> None:
        self.calls = calls if calls is not None else []
        self.fail = fail
        self.plans: list[PromotionPlan] = []

    def write_canonical_records(self, plan: PromotionPlan) -> None:
        self.calls.append("canonical")
        self.plans.append(plan)
        if self.fail:
            raise RuntimeError("canonical write failed")


class StaleBarrierStatusStore(InMemoryStatusStore):
    def compare_and_write_current_status(
        self,
        *,
        expected_status: Neo4jGraphStatus | None,
        next_status: Neo4jGraphStatus,
    ) -> bool:
        self.status = _status(graph_status="rebuilding")
        return super().compare_and_write_current_status(
            expected_status=expected_status,
            next_status=next_status,
        )


class RebuildAfterSyncAcquireStore(InMemoryStatusStore):
    def compare_and_write_current_status(
        self,
        *,
        expected_status: Neo4jGraphStatus | None,
        next_status: Neo4jGraphStatus,
    ) -> bool:
        result = super().compare_and_write_current_status(
            expected_status=expected_status,
            next_status=next_status,
        )
        if (
            result
            and expected_status is not None
            and expected_status.graph_status == "ready"
            and next_status.writer_lock_token is not None
        ):
            self.status = _status(graph_status="rebuilding")
        return result


def _status_manager_from_store(store: InMemoryStatusStore) -> GraphStatusManager:
    return GraphStatusManager(store)


def test_validate_entity_anchors_checks_all_source_entities_once() -> None:
    deltas = [
        _delta("delta-1", "node_add", {"node": _node_payload()}, ["entity-1", "entity-2"]),
        _delta("delta-2", "node_add", {"node": _node_payload("node-2")}, ["entity-2"]),
    ]
    entity_reader = FakeEntityReader({"entity-1"})

    with pytest.raises(ValueError, match="entity-2"):
        validate_entity_anchors(deltas, entity_reader)

    assert entity_reader.calls == [{"entity-1", "entity-2"}]


def test_build_promotion_plan_parses_frozen_deltas_in_stable_order() -> None:
    deltas = [
        _delta("delta-4", "assertion_add", {"assertion": _assertion_payload()}),
        _delta("delta-1", "node_add", {"node": _node_payload()}),
        _delta("delta-3", "edge_update", {"edge": _edge_payload("edge-2")}),
        _delta("delta-2", "edge_add", {"edge": _edge_payload()}),
    ]

    plan = build_promotion_plan("cycle-1", "selection-1", deltas)

    assert plan.cycle_id == "cycle-1"
    assert plan.selection_ref == "selection-1"
    assert plan.delta_ids == ["delta-1", "delta-2", "delta-3", "delta-4"]
    assert [record.node_id for record in plan.node_records] == ["node-1"]
    assert [record.edge_id for record in plan.edge_records] == ["edge-1", "edge-2"]
    assert [record.assertion_id for record in plan.assertion_records] == ["assertion-1"]
    assert plan.created_at.tzinfo is not None


def test_build_promotion_plan_maps_delta_evidence_into_edge_and_assertion_records() -> None:
    deltas = [
        _delta(
            "delta-1",
            "edge_add",
            {
                "edge": _edge_payload(properties={"source": "filing"}),
                "evidence": ["fact-edge"],
            },
        ),
        _delta(
            "delta-2",
            "assertion_add",
            {
                "assertion": _assertion_payload(evidence={"source": "contract"}),
                "evidence": ["fact-assertion"],
            },
        ),
    ]

    plan = build_promotion_plan("cycle-1", "selection-1", deltas)

    assert plan.edge_records[0].properties["evidence_refs"] == ["fact-edge"]
    assert plan.assertion_records[0].evidence == {
        "source": "contract",
        "evidence_refs": ["fact-assertion"],
    }


def test_build_promotion_plan_extracts_refs_from_evidence_mapping() -> None:
    plan = build_promotion_plan(
        "cycle-1",
        "selection-1",
        [
            _delta(
                "delta-1",
                "edge_add",
                {
                    "edge": _edge_payload(properties={"source": "filing"}),
                    "evidence": {
                        "source": "filing",
                        "evidence_ref": "fact-edge",
                    },
                },
            ),
        ],
    )

    assert plan.edge_records[0].properties["evidence_refs"] == ["fact-edge"]


def test_build_promotion_plan_rejects_evidence_objects_without_refs() -> None:
    with pytest.raises(ValueError, match="evidence_ref"):
        build_promotion_plan(
            "cycle-1",
            "selection-1",
            [
                _delta(
                    "delta-1",
                    "edge_add",
                    {
                        "edge": _edge_payload(properties={"source": "filing"}),
                        "evidence": {"source": "filing"},
                    },
                ),
            ],
        )


def test_build_promotion_plan_rejects_non_string_evidence_ref_values() -> None:
    with pytest.raises(ValueError, match="evidence refs must be non-empty strings"):
        build_promotion_plan(
            "cycle-1",
            "selection-1",
            [
                _delta(
                    "delta-1",
                    "edge_add",
                    {
                        "edge": _edge_payload(properties={"source": "filing"}),
                        "evidence_refs": [None],
                    },
                ),
            ],
        )


def test_contract_delta_edge_timestamps_are_stable_for_replayed_delta() -> None:
    contract_delta = CandidateGraphDelta(
        delta_id="contract-edge-1",
        delta_type="upsert_edge",
        source_node="node-1",
        target_node="node-2",
        relation_type=RelationshipType.SUPPLY_CHAIN.value,
        properties={"evidence_confidence": 0.9, "recency_decay": 1.0},
        evidence=["fact-contract-1"],
        subsystem_id="subsystem-news",
    )
    delta = _delta(
        "delta-1",
        "edge_add",
        contract_delta.model_dump(),
        source_entity_ids=["entity-1", "entity-2"],
    )

    first = build_promotion_plan("cycle-1", "selection-1", [delta])
    second = build_promotion_plan("cycle-1", "selection-1", [delta])

    assert first.edge_records[0].created_at == second.edge_records[0].created_at
    assert first.edge_records[0].updated_at == second.edge_records[0].updated_at
    assert first.edge_records[0].created_at == first.edge_records[0].updated_at


def test_contract_delta_upsert_relation_maps_to_edge_promotion() -> None:
    contract_delta = _contract_delta(delta_type="upsert_relation")

    plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([contract_delta]),
        entity_reader=_contract_entity_reader(),
        canonical_writer=FakeCanonicalWriter(),
        sync_to_live_graph=False,
    )

    assert [edge.edge_id for edge in plan.edge_records] == [contract_delta.delta_id]
    assert plan.edge_records[0].relationship_type == contract_delta.relation_type


def test_contract_delta_edge_upsert_maps_to_edge_promotion() -> None:
    contract_delta = _contract_delta(delta_type="edge_upsert")

    plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([contract_delta]),
        entity_reader=_contract_entity_reader(),
        canonical_writer=FakeCanonicalWriter(),
        sync_to_live_graph=False,
    )

    assert [edge.edge_id for edge in plan.edge_records] == [contract_delta.delta_id]
    assert plan.edge_records[0].relationship_type == contract_delta.relation_type


@pytest.mark.parametrize(
    "relationship_type",
    [
        RelationshipType.CO_HOLDING.value,
        RelationshipType.NORTHBOUND_HOLD.value,
    ],
)
def test_contract_delta_promotes_holdings_relationship_types(
    relationship_type: str,
) -> None:
    contract_delta = _contract_delta(
        delta_id=f"{relationship_type.lower()}-delta-1",
        relation_type=relationship_type,
    )

    plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([contract_delta]),
        entity_reader=_contract_entity_reader(),
        canonical_writer=FakeCanonicalWriter(),
        sync_to_live_graph=False,
    )

    assert plan.edge_records[0].relationship_type == relationship_type
    assert plan.edge_records[0].edge_id.startswith(f"{relationship_type.lower()}:")


@pytest.mark.parametrize(
    "relationship_type",
    [
        RelationshipType.CO_HOLDING.value,
        RelationshipType.NORTHBOUND_HOLD.value,
    ],
)
def test_frozen_holdings_edge_upsert_promotes_to_layer_a_without_live_sync(
    monkeypatch: pytest.MonkeyPatch,
    relationship_type: str,
) -> None:
    sync_live_graph = MagicMock()
    monkeypatch.setattr(service_module, "sync_live_graph", sync_live_graph)
    source_node = f"node-holder-{relationship_type.lower()}"
    target_node = f"node-security-{relationship_type.lower()}"
    source_entity = f"entity-holder-{relationship_type.lower()}"
    target_entity = f"entity-security-{relationship_type.lower()}"
    contract_delta = _contract_delta(
        delta_id=f"{relationship_type.lower()}-live-proof-1",
        delta_type="edge_upsert",
        source_node=source_node,
        target_node=target_node,
        relation_type=relationship_type,
        subsystem_id="subsystem-holdings",
    )
    contract_delta.properties = {
        "weight": 0.7,
        "edge_key": f"{relationship_type}|holder|security",
        "source_mart": "mart_deriv_holdings_proof",
    }
    contract_delta.producer_context = {
        "graph_node_upserts": [
            _node_payload(source_node, canonical_entity_id=source_entity),
            _node_payload(target_node, canonical_entity_id=target_entity),
        ],
    }
    writer = FakeCanonicalWriter()

    plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([contract_delta]),
        entity_reader=_contract_entity_reader(
            existing_ids={source_entity, target_entity},
            node_entity_ids={},
        ),
        canonical_writer=writer,
        sync_to_live_graph=False,
    )

    edge = plan.edge_records[0]
    assert writer.calls == ["canonical"]
    assert writer.plans == [plan]
    sync_live_graph.assert_not_called()
    assert sorted(node.node_id for node in plan.node_records) == [
        source_node,
        target_node,
    ]
    assert edge.relationship_type == relationship_type
    assert edge.source_node_id == source_node
    assert edge.target_node_id == target_node
    assert edge.edge_id.startswith(f"{relationship_type.lower()}:")
    assert edge.edge_id != contract_delta.delta_id

    replay_plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([contract_delta]),
        entity_reader=_contract_entity_reader(
            existing_ids={source_entity, target_entity},
            node_entity_ids={},
        ),
        canonical_writer=FakeCanonicalWriter(),
        sync_to_live_graph=False,
    )
    assert replay_plan.edge_records[0].edge_id == edge.edge_id


def test_holdings_contract_delta_can_upsert_endpoint_nodes_before_edge() -> None:
    contract_delta = _contract_delta(
        delta_id="co-holding-delta-1",
        source_node="node-fund-1",
        target_node="node-stock-1",
        relation_type=RelationshipType.CO_HOLDING.value,
    )
    contract_delta.producer_context = {
        "graph_node_upserts": [
            _node_payload(
                "node-fund-1",
                canonical_entity_id="entity-fund-1",
                properties={"fund_code": "001753.OF"},
            ),
        ],
    }
    entity_reader = _contract_entity_reader(
        existing_ids={"entity-fund-1", "entity-stock-1"},
        node_entity_ids={"node-stock-1": "entity-stock-1"},
    )

    plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([contract_delta]),
        entity_reader=entity_reader,
        canonical_writer=FakeCanonicalWriter(),
        sync_to_live_graph=False,
    )

    assert [node.node_id for node in plan.node_records] == ["node-fund-1"]
    assert plan.node_records[0].canonical_entity_id == "entity-fund-1"
    assert plan.edge_records[0].source_node_id == "node-fund-1"
    assert plan.edge_records[0].target_node_id == "node-stock-1"
    assert entity_reader.node_calls == [{"node-fund-1", "node-stock-1"}]
    assert entity_reader.calls == [{"entity-fund-1", "entity-stock-1"}]


def test_holdings_node_upsert_requires_existing_canonical_entity_anchor() -> None:
    contract_delta = _contract_delta(
        delta_id="co-holding-delta-1",
        source_node="node-fund-1",
        target_node="node-stock-1",
        relation_type=RelationshipType.CO_HOLDING.value,
    )
    contract_delta.producer_context = {
        "graph_node_upserts": [
            _node_payload(
                "node-fund-1",
                canonical_entity_id="entity-fund-1",
                properties={"fund_code": "001753.OF"},
            ),
        ],
    }
    entity_reader = _contract_entity_reader(
        existing_ids={"entity-stock-1"},
        node_entity_ids={"node-stock-1": "entity-stock-1"},
    )
    writer = FakeCanonicalWriter()

    with pytest.raises(ValueError, match="missing entity anchors: entity-fund-1"):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeCandidateReader([contract_delta]),
            entity_reader=entity_reader,
            canonical_writer=writer,
            sync_to_live_graph=False,
        )

    assert entity_reader.node_calls == [{"node-fund-1", "node-stock-1"}]
    assert entity_reader.calls == [{"entity-fund-1", "entity-stock-1"}]
    assert writer.plans == []


def test_holdings_node_upsert_rejects_non_endpoint_node() -> None:
    contract_delta = _contract_delta(
        delta_id="co-holding-delta-1",
        source_node="node-fund-1",
        target_node="node-stock-1",
        relation_type=RelationshipType.CO_HOLDING.value,
    )
    contract_delta.producer_context = {
        "graph_node_upserts": [
            _node_payload(
                "node-fund-1",
                canonical_entity_id="entity-fund-1",
                properties={"fund_code": "001753.OF"},
            ),
            _node_payload(
                "node-extra-1",
                canonical_entity_id="entity-extra-1",
            ),
        ],
    }
    entity_reader = _contract_entity_reader(
        existing_ids={"entity-fund-1", "entity-stock-1", "entity-extra-1"},
        node_entity_ids={"node-stock-1": "entity-stock-1"},
    )
    writer = FakeCanonicalWriter()

    with pytest.raises(
        ValueError,
        match="graph_node_upserts are endpoint-only.*node-extra-1",
    ):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeCandidateReader([contract_delta]),
            entity_reader=entity_reader,
            canonical_writer=writer,
            sync_to_live_graph=False,
        )

    assert entity_reader.node_calls == []
    assert entity_reader.calls == []
    assert writer.plans == []


def test_holdings_node_upsert_rejects_cross_delta_endpoint_node() -> None:
    first = _contract_delta(
        delta_id="co-holding-delta-1",
        source_node="node-fund-1",
        target_node="node-stock-1",
        relation_type=RelationshipType.CO_HOLDING.value,
    )
    first.producer_context = {
        "graph_node_upserts": [
            _node_payload(
                "node-stock-2",
                canonical_entity_id="entity-stock-2",
            ),
        ],
    }
    second = _contract_delta(
        delta_id="co-holding-delta-2",
        source_node="node-fund-2",
        target_node="node-stock-2",
        relation_type=RelationshipType.CO_HOLDING.value,
    )
    entity_reader = _contract_entity_reader(
        existing_ids={
            "entity-fund-1",
            "entity-stock-1",
            "entity-fund-2",
            "entity-stock-2",
        },
        node_entity_ids={
            "node-fund-1": "entity-fund-1",
            "node-stock-1": "entity-stock-1",
            "node-fund-2": "entity-fund-2",
        },
    )
    writer = FakeCanonicalWriter()

    with pytest.raises(
        ValueError,
        match="graph_node_upserts are endpoint-only.*node-stock-2",
    ):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeCandidateReader([first, second]),
            entity_reader=entity_reader,
            canonical_writer=writer,
            sync_to_live_graph=False,
        )

    assert entity_reader.node_calls == []
    assert entity_reader.calls == []
    assert writer.plans == []


def test_holdings_node_upsert_rejects_conflicting_endpoint_mapping() -> None:
    contract_delta = _contract_delta(
        delta_id="co-holding-delta-1",
        source_node="node-fund-1",
        target_node="node-stock-1",
        relation_type=RelationshipType.CO_HOLDING.value,
    )
    contract_delta.producer_context = {
        "graph_node_upserts": [
            _node_payload(
                "node-fund-1",
                canonical_entity_id="entity-fund-from-producer",
                properties={"fund_code": "001753.OF"},
            ),
        ],
    }
    entity_reader = _contract_entity_reader(
        existing_ids={
            "entity-fund-from-registry",
            "entity-fund-from-producer",
            "entity-stock-1",
        },
        node_entity_ids={
            "node-fund-1": "entity-fund-from-registry",
            "node-stock-1": "entity-stock-1",
        },
    )
    writer = FakeCanonicalWriter()

    with pytest.raises(
        ValueError,
        match=(
            "graph_node_upserts conflict.*node-fund-1.*"
            "entity-fund-from-producer.*entity-fund-from-registry"
        ),
    ):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeCandidateReader([contract_delta]),
            entity_reader=entity_reader,
            canonical_writer=writer,
            sync_to_live_graph=False,
        )

    assert entity_reader.node_calls == [{"node-fund-1", "node-stock-1"}]
    assert entity_reader.calls == []
    assert writer.plans == []


def test_graph_node_upserts_are_limited_to_holdings_relationships() -> None:
    contract_delta = _contract_delta(
        delta_id="supply-chain-delta-1",
        relation_type=RelationshipType.SUPPLY_CHAIN.value,
    )
    contract_delta.producer_context = {
        "graph_node_upserts": [
            _node_payload(
                "node-1",
                canonical_entity_id="entity-1",
            ),
        ],
    }
    entity_reader = _contract_entity_reader()

    with pytest.raises(
        ValueError,
        match="graph_node_upserts are only supported for CO_HOLDING and NORTHBOUND_HOLD",
    ):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeCandidateReader([contract_delta]),
            entity_reader=entity_reader,
            canonical_writer=FakeCanonicalWriter(),
            sync_to_live_graph=False,
        )

    assert entity_reader.node_calls == []
    assert entity_reader.calls == []


def test_holdings_relationships_use_pair_stable_edge_ids_for_property_upserts() -> None:
    first = _contract_delta(
        delta_id="co-holding-2026q1",
        source_node="node-fund-1",
        target_node="node-stock-1",
        relation_type=RelationshipType.CO_HOLDING.value,
    )
    second = _contract_delta(
        delta_id="co-holding-2026q2",
        source_node="node-fund-1",
        target_node="node-stock-1",
        relation_type=RelationshipType.CO_HOLDING.value,
    )
    first.properties = {"report_date": "20260331", "weight": 0.3}
    second.properties = {"report_date": "20260630", "weight": 0.4}

    plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([second, first]),
        entity_reader=_contract_entity_reader(
            existing_ids={"entity-fund-1", "entity-stock-1"},
            node_entity_ids={
                "node-fund-1": "entity-fund-1",
                "node-stock-1": "entity-stock-1",
            },
        ),
        canonical_writer=FakeCanonicalWriter(),
        sync_to_live_graph=False,
    )

    edge_ids = [edge.edge_id for edge in plan.edge_records]
    assert edge_ids[0] == edge_ids[1]
    assert edge_ids[0] not in {first.delta_id, second.delta_id}
    assert [edge.properties["report_date"] for edge in plan.edge_records] == [
        "20260331",
        "20260630",
    ]


def test_supply_chain_contract_delta_ignores_properties_edge_id_override() -> None:
    contract_delta = _contract_delta(
        delta_id="supply-chain-delta-1",
        relation_type=RelationshipType.SUPPLY_CHAIN.value,
    )
    contract_delta.properties = {
        "edge_id": "producer-edge-override",
        "weight": 0.7,
    }

    plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([contract_delta]),
        entity_reader=_contract_entity_reader(),
        canonical_writer=FakeCanonicalWriter(),
        sync_to_live_graph=False,
    )

    assert plan.edge_records[0].edge_id == contract_delta.delta_id


@pytest.mark.parametrize(
    "relationship_type",
    [
        RelationshipType.CO_HOLDING.value,
        RelationshipType.NORTHBOUND_HOLD.value,
    ],
)
def test_holdings_contract_delta_accepts_properties_edge_id_override(
    relationship_type: str,
) -> None:
    contract_delta = _contract_delta(
        delta_id=f"{relationship_type.lower()}-delta-1",
        relation_type=relationship_type,
    )
    contract_delta.properties = {
        "edge_id": f"{relationship_type.lower()}-explicit-edge",
        "weight": 0.7,
    }

    plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([contract_delta]),
        entity_reader=_contract_entity_reader(),
        canonical_writer=FakeCanonicalWriter(),
        sync_to_live_graph=False,
    )

    assert plan.edge_records[0].edge_id == f"{relationship_type.lower()}-explicit-edge"


@pytest.mark.parametrize(
    ("delta_type", "relation_type"),
    [
        ("add_edge", "supply_contract"),
        ("add", "supplier_of"),
    ],
)
def test_contract_delta_external_ex3_terms_map_to_supply_chain_edge_promotion(
    delta_type: str,
    relation_type: str,
) -> None:
    contract_delta = _contract_delta(
        delta_type=delta_type,
        relation_type=relation_type,
    )

    plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([contract_delta]),
        entity_reader=_contract_entity_reader(),
        canonical_writer=FakeCanonicalWriter(),
        sync_to_live_graph=False,
    )

    assert [edge.edge_id for edge in plan.edge_records] == [contract_delta.delta_id]
    assert plan.edge_records[0].relationship_type == RelationshipType.SUPPLY_CHAIN.value


def test_contract_delta_evidence_flows_through_promotion_to_impact_snapshot() -> None:
    contract_delta = CandidateGraphDelta(
        delta_id="contract-edge-1",
        delta_type="upsert_edge",
        source_node="node-1",
        target_node="node-2",
        relation_type=RelationshipType.SUPPLY_CHAIN.value,
        properties={
            "evidence_confidence": 0.9,
            "recency_decay": 1.0,
            "weight": 0.7,
        },
        evidence=["fact-contract-1"],
        subsystem_id="subsystem-news",
    )
    writer = FakeCanonicalWriter()
    entity_reader = _contract_entity_reader()

    plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([contract_delta]),
        entity_reader=entity_reader,
        canonical_writer=writer,
        sync_to_live_graph=False,
    )

    edge_record = plan.edge_records[0]
    assert writer.plans == [plan]
    assert entity_reader.node_calls == [{"node-1", "node-2"}]
    assert entity_reader.calls == [{"entity-1", "entity-2"}]
    assert edge_record.edge_id == contract_delta.delta_id
    assert edge_record.source_node_id == contract_delta.source_node
    assert edge_record.target_node_id == contract_delta.target_node
    assert edge_record.relationship_type == contract_delta.relation_type
    assert edge_record.properties["evidence_refs"] == ["fact-contract-1"]

    impact_snapshot = build_graph_impact_snapshot(
        "cycle-1",
        "world-state-1",
        PropagationResult(
            cycle_id="cycle-1",
            graph_generation_id=3,
            activated_paths=[
                {
                    "source_node_id": edge_record.source_node_id,
                    "source_labels": ["Entity"],
                    "target_node_id": edge_record.target_node_id,
                    "target_labels": ["Entity"],
                    "edge_id": edge_record.edge_id,
                    "relationship_type": edge_record.relationship_type,
                    "evidence_refs": edge_record.properties["evidence_refs"],
                    "score": 0.7,
                }
            ],
            impacted_entities=[
                {"node_id": edge_record.target_node_id, "labels": ["Entity"], "score": 0.7}
            ],
            channel_breakdown={"fundamental": {"path_count": 1}},
        ),
    )

    assert impact_snapshot.evidence_refs == ["fact-contract-1"]


def test_promote_graph_deltas_validates_resolved_entities_not_endpoint_nodes() -> None:
    contract_delta = _contract_delta(
        "delta-1",
        source_node="node-source",
        target_node="node-target",
    )
    writer = FakeCanonicalWriter()
    entity_reader = _contract_entity_reader(
        existing_ids={"entity-source", "entity-target"},
        node_entity_ids={
            "node-source": "entity-source",
            "node-target": "entity-target",
        },
    )

    plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([contract_delta]),
        entity_reader=entity_reader,
        canonical_writer=writer,
        sync_to_live_graph=False,
    )

    assert entity_reader.node_calls == [{"node-source", "node-target"}]
    assert entity_reader.calls == [{"entity-source", "entity-target"}]
    assert writer.plans == [plan]
    assert plan.edge_records[0].source_node_id == "node-source"
    assert plan.edge_records[0].target_node_id == "node-target"


def test_promote_graph_deltas_rejects_contract_delta_with_unresolved_endpoint_node() -> None:
    writer = FakeCanonicalWriter()
    entity_reader = _contract_entity_reader(
        existing_ids={"entity-1"},
        node_entity_ids={"node-1": "entity-1"},
    )

    with pytest.raises(
        ValueError,
        match="missing canonical entity ids for graph nodes: node-2",
    ):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeCandidateReader([_contract_delta("delta-1")]),
            entity_reader=entity_reader,
            canonical_writer=writer,
            sync_to_live_graph=False,
        )

    assert entity_reader.node_calls == [{"node-1", "node-2"}]
    assert entity_reader.calls == []
    assert writer.plans == []


def test_promote_graph_deltas_rejects_unsupported_contract_delta_type() -> None:
    writer = FakeCanonicalWriter()
    entity_reader = _contract_entity_reader()

    with pytest.raises(ValueError, match="unsupported contract delta_type 'delete_edge'"):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeCandidateReader(
                [_contract_delta("delta-1", delta_type="delete_edge")],
            ),
            entity_reader=entity_reader,
            canonical_writer=writer,
            sync_to_live_graph=False,
        )

    assert entity_reader.calls == []
    assert entity_reader.node_calls == []
    assert writer.plans == []


def test_promote_graph_deltas_rejects_legacy_frozen_delta_reader() -> None:
    writer = FakeCanonicalWriter()
    entity_reader = FakeEntityReader({"entity-1"})

    with pytest.raises(TypeError, match="CandidateDeltaReader must return"):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeLegacyCandidateReader(
                [_delta("delta-1", "edge_add", {"edge": _edge_payload()})],
            ),
            entity_reader=entity_reader,
            canonical_writer=writer,
            sync_to_live_graph=False,
        )

    assert entity_reader.calls == []
    assert writer.plans == []


@pytest.mark.parametrize(
    ("delta_factory", "match"),
    [
        (
            lambda: _delta(
                "delta-1",
                "node_add",
                {"node": _node_payload()},
                validation_status="validated",
            ),
            "not frozen",
        ),
        (
            lambda: _delta(
                "delta-1",
                "node_add",
                {"node": _node_payload()},
                cycle_id="cycle-2",
            ),
            "cycle-2",
        ),
        (
            lambda: _delta("delta-1", "node_add", {"wrong": _node_payload()}),
            "payload must include 'node'",
        ),
        (
            lambda: _delta(
                "delta-1",
                "node_add",
                {"node": _node_payload(label="Unknown")},
            ),
            "unsupported node label",
        ),
        (
            lambda: _delta(
                "delta-1",
                "edge_add",
                {"edge": _edge_payload(relationship_type="UNKNOWN")},
            ),
            "unsupported relationship type",
        ),
        (
            lambda: _delta(
                "delta-1",
                "node_add",
                {"node": _node_payload(properties={"raw_text": "not allowed"})},
            ),
            "forbidden field 'raw_text'",
        ),
    ],
)
def test_build_promotion_plan_rejects_invalid_delta_contracts(
    delta_factory: Callable[[], FrozenGraphDelta],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        build_promotion_plan("cycle-1", "selection-1", [delta_factory()])


def test_promote_graph_deltas_writes_canonical_before_live_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    store = InMemoryStatusStore(_status())

    def fake_sync_live_graph(plan: PromotionPlan, client: Neo4jClient) -> None:
        assert plan.delta_ids == ["delta-1"]
        assert client is mock_client
        calls.append("sync")

    mock_client = MagicMock(spec=Neo4jClient)
    monkeypatch.setattr(service_module, "sync_live_graph", fake_sync_live_graph)
    monkeypatch.setattr(
        service_module,
        "read_live_graph_metrics",
        lambda client: (4, 3, {"Entity": 4}, "checksum-after-sync"),
    )
    writer = FakeCanonicalWriter(calls)

    plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([_contract_delta("delta-1")]),
        entity_reader=_contract_entity_reader(),
        canonical_writer=writer,
        client=mock_client,
        status_manager=_status_manager_from_store(store),
    )

    assert calls == ["canonical", "sync"]
    assert writer.plans == [plan]
    assert len(store.compare_calls) == 2
    expected_ready, locked_status = store.compare_calls[0]
    finish_expected, finish_ready = store.compare_calls[1]
    assert expected_ready == _status()
    assert locked_status.graph_status == "ready"
    assert locked_status.writer_lock_token is not None
    assert finish_expected == locked_status
    assert finish_ready.graph_status == "ready"
    assert finish_ready.writer_lock_token is None
    assert finish_ready.graph_generation_id == _status().graph_generation_id + 1
    assert finish_ready.node_count == 4
    assert finish_ready.edge_count == 3
    assert finish_ready.key_label_counts == {"Entity": 4}
    assert finish_ready.checksum == "checksum-after-sync"
    assert finish_ready.last_verified_at is not None
    assert finish_ready.last_reload_at == _status().last_reload_at
    assert store.status == finish_ready


def test_promote_graph_deltas_does_not_sync_when_canonical_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_live_graph = MagicMock()
    monkeypatch.setattr(service_module, "sync_live_graph", sync_live_graph)

    with pytest.raises(RuntimeError, match="canonical write failed"):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeCandidateReader([_contract_delta("delta-1")]),
            entity_reader=_contract_entity_reader(),
            canonical_writer=FakeCanonicalWriter(fail=True),
            client=MagicMock(spec=Neo4jClient),
            status_manager=_status_manager(),
        )

    sync_live_graph.assert_not_called()


def test_promote_graph_deltas_requires_status_manager_for_live_sync() -> None:
    writer = FakeCanonicalWriter()
    reader = FakeCandidateReader([_contract_delta("delta-1")])

    with pytest.raises(ValueError, match="status_manager"):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=reader,
            entity_reader=_contract_entity_reader(),
            canonical_writer=writer,
            client=MagicMock(spec=Neo4jClient),
        )

    assert reader.calls == []
    assert writer.plans == []


def test_promote_graph_deltas_blocks_live_sync_when_graph_is_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_live_graph = MagicMock()
    monkeypatch.setattr(service_module, "sync_live_graph", sync_live_graph)
    writer = FakeCanonicalWriter()

    with pytest.raises(PermissionError, match="ready"):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeCandidateReader([_contract_delta("delta-1")]),
            entity_reader=_contract_entity_reader(),
            canonical_writer=writer,
            client=MagicMock(spec=Neo4jClient),
            status_manager=_status_manager(graph_status="rebuilding"),
        )

    assert writer.plans == []
    sync_live_graph.assert_not_called()


def test_promote_graph_deltas_rejects_stale_status_before_live_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_live_graph = MagicMock()
    monkeypatch.setattr(service_module, "sync_live_graph", sync_live_graph)
    writer = FakeCanonicalWriter()
    status_manager = _status_manager_from_store(StaleBarrierStatusStore(_status()))

    with pytest.raises(RuntimeError, match="stale graph_status transition"):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeCandidateReader([_contract_delta("delta-1")]),
            entity_reader=_contract_entity_reader(),
            canonical_writer=writer,
            client=MagicMock(spec=Neo4jClient),
            status_manager=status_manager,
        )

    assert len(writer.plans) == 1
    sync_live_graph.assert_not_called()


def test_promote_graph_deltas_does_not_sync_if_rebuild_starts_after_barrier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_live_graph = MagicMock()
    monkeypatch.setattr(service_module, "sync_live_graph", sync_live_graph)
    store = RebuildAfterSyncAcquireStore(_status())

    with pytest.raises(RuntimeError, match="before promotion live sync"):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeCandidateReader([_contract_delta("delta-1")]),
            entity_reader=_contract_entity_reader(),
            canonical_writer=FakeCanonicalWriter(),
            client=MagicMock(spec=Neo4jClient),
            status_manager=_status_manager_from_store(store),
        )

    assert sync_live_graph.call_count == 0
    assert store.status == _status(graph_status="rebuilding")


def test_promote_graph_deltas_detects_status_change_during_live_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    store = InMemoryStatusStore(_status())

    def fake_sync_live_graph(plan: PromotionPlan, client: Neo4jClient) -> None:
        assert plan.delta_ids == ["delta-1"]
        calls.append("sync")
        store.status = _status(graph_status="rebuilding")

    monkeypatch.setattr(service_module, "sync_live_graph", fake_sync_live_graph)
    writer = FakeCanonicalWriter()

    with pytest.raises(RuntimeError, match="after promotion live sync"):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeCandidateReader([_contract_delta("delta-1")]),
            entity_reader=_contract_entity_reader(),
            canonical_writer=writer,
            client=MagicMock(spec=Neo4jClient),
            status_manager=_status_manager_from_store(store),
        )

    assert len(writer.plans) == 1
    assert calls == ["sync"]
    assert store.status == _status(graph_status="rebuilding")


def test_promote_graph_deltas_marks_status_failed_when_live_sync_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_sync_live_graph(plan: PromotionPlan, client: Neo4jClient) -> None:
        raise RuntimeError("sync failed")

    store = InMemoryStatusStore(_status())
    monkeypatch.setattr(service_module, "sync_live_graph", fake_sync_live_graph)

    with pytest.raises(RuntimeError, match="sync failed"):
        promote_graph_deltas(
            "cycle-1",
            "selection-1",
            candidate_reader=FakeCandidateReader([_contract_delta("delta-1")]),
            entity_reader=_contract_entity_reader(),
            canonical_writer=FakeCanonicalWriter(),
            client=MagicMock(spec=Neo4jClient),
            status_manager=_status_manager_from_store(store),
        )

    assert store.status is not None
    assert store.status.graph_status == "failed"


def test_promote_graph_deltas_can_skip_live_graph_sync() -> None:
    writer = FakeCanonicalWriter()

    plan = promote_graph_deltas(
        "cycle-1",
        "selection-1",
        candidate_reader=FakeCandidateReader([_contract_delta("delta-1")]),
        entity_reader=_contract_entity_reader(),
        canonical_writer=writer,
        sync_to_live_graph=False,
    )

    assert writer.plans == [plan]


def _status_manager(
    *,
    graph_status: str = "ready",
) -> GraphStatusManager:
    return GraphStatusManager(InMemoryStatusStore(_status(graph_status=graph_status)))


def _contract_entity_reader(
    existing_ids: set[str] | None = None,
    node_entity_ids: dict[str, str] | None = None,
) -> FakeEntityReader:
    resolved_node_entity_ids = node_entity_ids or {
        "node-1": "entity-1",
        "node-2": "entity-2",
    }
    return FakeEntityReader(
        existing_ids or set(resolved_node_entity_ids.values()),
        resolved_node_entity_ids,
    )


def _status(
    *,
    graph_status: str = "ready",
    writer_lock_token: str | None = None,
) -> Neo4jGraphStatus:
    return Neo4jGraphStatus(
        graph_status=graph_status,
        graph_generation_id=3,
        node_count=2,
        edge_count=1,
        key_label_counts={"Entity": 2},
        checksum="abc123",
        last_verified_at=NOW if graph_status == "ready" else None,
        last_reload_at=None,
        writer_lock_token=writer_lock_token,
    )


def _delta(
    delta_id: str,
    delta_type: str,
    payload: dict[str, Any],
    source_entity_ids: list[str] | None = None,
    *,
    cycle_id: str = "cycle-1",
    validation_status: str = "frozen",
) -> FrozenGraphDelta:
    return FrozenGraphDelta(
        delta_id=delta_id,
        cycle_id=cycle_id,
        delta_type=delta_type,
        source_entity_ids=source_entity_ids or ["entity-1"],
        payload=payload,
        validation_status=validation_status,
    )


def _contract_delta(
    delta_id: str = "delta-1",
    *,
    delta_type: str = "upsert_edge",
    source_node: str = "node-1",
    target_node: str = "node-2",
    relation_type: str = RelationshipType.SUPPLY_CHAIN.value,
    subsystem_id: str = "subsystem-news",
) -> CandidateGraphDelta:
    return CandidateGraphDelta(
        delta_id=delta_id,
        delta_type=delta_type,
        source_node=source_node,
        target_node=target_node,
        relation_type=relation_type,
        properties={"weight": 0.7},
        evidence=[f"fact-{delta_id}"],
        subsystem_id=subsystem_id,
    )


def _node_payload(
    node_id: str = "node-1",
    *,
    canonical_entity_id: str = "entity-1",
    label: str = NodeLabel.ENTITY.value,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "canonical_entity_id": canonical_entity_id,
        "label": label,
        "properties": properties or {"ticker": "ULT"},
        "created_at": NOW,
        "updated_at": NOW,
    }


def _edge_payload(
    edge_id: str = "edge-1",
    *,
    relationship_type: str = RelationshipType.SUPPLY_CHAIN.value,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "edge_id": edge_id,
        "source_node_id": "node-1",
        "target_node_id": "node-2",
        "relationship_type": relationship_type,
        "properties": (
            {"source": "filing", "evidence_refs": [f"fact-{edge_id}"]}
            if properties is None
            else properties
        ),
        "weight": 0.7,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _assertion_payload(*, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "assertion_id": "assertion-1",
        "source_node_id": "node-1",
        "target_node_id": "node-2",
        "assertion_type": "risk",
        "evidence": {"source": "contract"} if evidence is None else evidence,
        "confidence": 0.8,
        "created_at": NOW,
    }
