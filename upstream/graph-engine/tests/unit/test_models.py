from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from graph_engine.models import (
    CandidateGraphDelta,
    ColdReloadPlan,
    FrozenGraphDelta,
    GraphAssertionRecord,
    GraphEdgeRecord,
    GraphImpactSnapshot,
    GraphMetricsSnapshot,
    GraphNodeRecord,
    GraphSnapshot,
    Neo4jGraphStatus,
    PropagationContext,
    PropagationResult,
    PromotionPlan,
    ReadonlySimulationRequest,
)

NOW = datetime(2026, 4, 17, 1, 2, 3, tzinfo=timezone.utc)


def _model_payloads() -> list[tuple[type[BaseModel], dict[str, Any]]]:
    return [
        (
            GraphNodeRecord,
            {
                "node_id": "node-1",
                "canonical_entity_id": "entity-1",
                "label": "Entity",
                "properties": {"ticker": "ULT"},
                "created_at": NOW,
                "updated_at": NOW,
            },
        ),
        (
            GraphEdgeRecord,
            {
                "edge_id": "edge-1",
                "source_node_id": "node-1",
                "target_node_id": "node-2",
                "relationship_type": "SUPPLY_CHAIN",
                "properties": {"source": "filing", "evidence_refs": ["fact-1"]},
                "weight": 0.7,
                "created_at": NOW,
                "updated_at": NOW,
            },
        ),
        (
            GraphAssertionRecord,
            {
                "assertion_id": "assertion-1",
                "source_node_id": "node-1",
                "target_node_id": None,
                "assertion_type": "risk",
                "evidence": {"source": "contract"},
                "confidence": 0.8,
                "created_at": NOW,
            },
        ),
        (
            CandidateGraphDelta,
            {
                "delta_id": "delta-1",
                "delta_type": "upsert_edge",
                "source_node": "node-1",
                "target_node": "node-2",
                "relation_type": "SUPPLY_CHAIN",
                "properties": {"weight": 1.0},
                "evidence": ["fact-1"],
                "subsystem_id": "subsystem-news",
            },
        ),
        (
            FrozenGraphDelta,
            {
                "delta_id": "delta-1",
                "cycle_id": "cycle-1",
                "delta_type": "node_add",
                "source_entity_ids": ["entity-1"],
                "payload": {"node_id": "node-1"},
                "validation_status": "frozen",
            },
        ),
        (
            GraphSnapshot,
            {
                "cycle_id": "cycle-1",
                "graph_snapshot_id": "snapshot-1",
                "version": "0.1.0",
                "node_count": 2,
                "edge_count": 1,
                "nodes": [
                    {"node_id": "node-1", "labels": ["Entity"]},
                    {"node_id": "node-2", "labels": ["Entity"]},
                ],
                "edges": [
                    {
                        "edge_id": "edge-1",
                        "source_node": "node-1",
                        "target_node": "node-2",
                        "relation_type": "SUPPLY_CHAIN",
                    }
                ],
                "created_at": NOW,
            },
        ),
        (
            GraphMetricsSnapshot,
            {
                "cycle_id": "cycle-1",
                "snapshot_id": "snapshot-1",
                "graph_generation_id": 1,
                "node_count": 10,
                "edge_count": 12,
                "key_label_counts": {"Entity": 10},
                "checksum": "abc123",
                "created_at": NOW,
            },
        ),
        (
            PropagationContext,
            {
                "cycle_id": "cycle-1",
                "world_state_ref": "world-state-1",
                "graph_generation_id": 1,
                "enabled_channels": ["fundamental"],
                "channel_multipliers": {"fundamental": 1.0},
                "regime_multipliers": {"fundamental": 1.0},
                "decay_policy": {"default": 1.0},
                "regime_context": {"risk_regime": "baseline"},
            },
        ),
        (
            PropagationResult,
            {
                "cycle_id": "cycle-1",
                "graph_generation_id": 1,
                "activated_paths": [{"path": ["node-1", "node-2"]}],
                "impacted_entities": [{"entity_id": "entity-2", "score": 0.5}],
                "channel_breakdown": {"fundamental": {"score": 0.5}},
            },
        ),
        (
            ReadonlySimulationRequest,
            {
                "cycle_id": "cycle-1",
                "world_state_ref": "world-state-1",
                "graph_generation_id": 1,
                "depth": 2,
                "enabled_channels": ["fundamental", "event", "reflexive"],
                "channel_multipliers": {
                    "fundamental": 1.0,
                    "event": 1.0,
                    "reflexive": 1.0,
                },
                "regime_multipliers": {
                    "fundamental": 1.0,
                    "event": 1.0,
                    "reflexive": 1.0,
                },
                "decay_policy": {"default": 1.0},
                "regime_context": {"risk_regime": "baseline"},
                "result_limit": 100,
                "max_iterations": 20,
                "projection_name": "graph_engine_readonly_sim_cycle_1",
            },
        ),
        (
            GraphImpactSnapshot,
            {
                "cycle_id": "cycle-1",
                "impact_snapshot_id": "impact-1",
                "version": "0.1.0",
                "created_at": NOW,
                "target_entities": [
                    {
                        "entity_id": "entity-1",
                        "entity_type": "equity",
                        "canonical_id_rule_version": "0.1.0",
                    }
                ],
                "affected_entities": [
                    {
                        "entity_id": "entity-2",
                        "entity_type": "equity",
                        "canonical_id_rule_version": "0.1.0",
                    }
                ],
                "affected_sectors": ["technology"],
                "direction": "bullish",
                "impact_score": 0.5,
                "evidence_refs": ["fact-1"],
            },
        ),
        (
            ColdReloadPlan,
            {
                "snapshot_ref": "snapshot-ref-1",
                "cycle_id": "cycle-1",
                "expected_snapshot": {
                    "cycle_id": "cycle-1",
                    "snapshot_id": "snapshot-1",
                    "graph_generation_id": 1,
                    "node_count": 1,
                    "edge_count": 0,
                    "key_label_counts": {"Entity": 1},
                    "checksum": "abc123",
                    "created_at": NOW,
                },
                "node_records": [
                    {
                        "node_id": "node-1",
                        "canonical_entity_id": "entity-1",
                        "label": "Entity",
                        "properties": {"ticker": "ULT"},
                        "created_at": NOW,
                        "updated_at": NOW,
                    }
                ],
                "edge_records": [],
                "assertion_records": [],
                "projection_name": "graph_engine_reload_cycle_1",
                "created_at": NOW,
            },
        ),
        (
            Neo4jGraphStatus,
            {
                "graph_status": "ready",
                "graph_generation_id": 1,
                "node_count": 10,
                "edge_count": 12,
                "key_label_counts": {"Entity": 10},
                "checksum": "abc123",
                "last_verified_at": NOW,
                "last_reload_at": None,
            },
        ),
        (
            PromotionPlan,
            {
                "cycle_id": "cycle-1",
                "selection_ref": "selection-1",
                "delta_ids": ["delta-1"],
                "node_records": [
                    {
                        "node_id": "node-1",
                        "canonical_entity_id": "entity-1",
                        "label": "Entity",
                        "properties": {"ticker": "ULT"},
                        "created_at": NOW,
                        "updated_at": NOW,
                    }
                ],
                "edge_records": [],
                "assertion_records": [],
                "created_at": NOW,
            },
        ),
    ]


@pytest.mark.parametrize(("model_type", "payload"), _model_payloads())
def test_models_round_trip_json(model_type: type[BaseModel], payload: dict[str, Any]) -> None:
    model = model_type.model_validate(payload)

    restored = model_type.model_validate_json(model.model_dump_json())

    assert restored == model


def test_edge_weight_defaults_to_one() -> None:
    edge = GraphEdgeRecord(
        edge_id="edge-1",
        source_node_id="node-1",
        target_node_id="node-2",
        relationship_type="OWNERSHIP",
        properties={"evidence_ref": "fact-1"},
        created_at=NOW,
        updated_at=NOW,
    )

    assert edge.weight == 1.0
    assert edge.properties["evidence_refs"] == ["fact-1"]


def test_propagatable_edge_requires_evidence_refs() -> None:
    with pytest.raises(ValidationError, match="evidence_ref"):
        GraphEdgeRecord(
            edge_id="edge-1",
            source_node_id="node-1",
            target_node_id="node-2",
            relationship_type="SUPPLY_CHAIN",
            properties={"source": "filing"},
            created_at=NOW,
            updated_at=NOW,
        )


@pytest.mark.parametrize(
    "properties",
    [
        {"evidence_ref": ""},
        {"evidence_ref": 123},
        {"evidence_ref": {"source": "filing"}},
        {"evidence_refs": ["fact-1", ""]},
        {"evidence_refs": [None]},
        {"evidence_refs": [{"source": "filing"}]},
        {"evidence_refs": {"source": "filing"}},
    ],
)
def test_propagatable_edge_rejects_forged_evidence_refs(
    properties: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError, match="evidence refs must be non-empty strings"):
        GraphEdgeRecord(
            edge_id="edge-1",
            source_node_id="node-1",
            target_node_id="node-2",
            relationship_type="SUPPLY_CHAIN",
            properties=properties,
            created_at=NOW,
            updated_at=NOW,
        )


def test_non_propagatable_edge_can_omit_evidence_refs() -> None:
    edge = GraphEdgeRecord(
        edge_id="edge-1",
        source_node_id="node-1",
        target_node_id="assertion-1",
        relationship_type="ASSERTION_LINK",
        properties={"role": "source"},
        created_at=NOW,
        updated_at=NOW,
    )

    assert edge.properties == {"role": "source"}


def test_candidate_delta_rejects_invalid_validation_status() -> None:
    with pytest.raises(ValidationError):
        FrozenGraphDelta(
            delta_id="delta-1",
            cycle_id="cycle-1",
            delta_type="node_add",
            source_entity_ids=["entity-1"],
            payload={},
            validation_status="invalid",
        )


def test_candidate_delta_rejects_invalid_delta_type() -> None:
    with pytest.raises(ValidationError):
        FrozenGraphDelta(
            delta_id="delta-1",
            cycle_id="cycle-1",
            delta_type="node_delete",
            source_entity_ids=["entity-1"],
            payload={},
            validation_status="validated",
        )


def test_neo4j_graph_status_rejects_syncing_public_state() -> None:
    with pytest.raises(ValidationError):
        Neo4jGraphStatus(
            graph_status="syncing",
            graph_generation_id=1,
            node_count=10,
            edge_count=12,
            key_label_counts={"Entity": 10},
            checksum="abc123",
            last_verified_at=NOW,
            last_reload_at=None,
        )


def test_neo4j_graph_status_writer_lock_requires_ready_state() -> None:
    with pytest.raises(ValidationError, match="writer_lock_token"):
        Neo4jGraphStatus(
            graph_status="rebuilding",
            graph_generation_id=1,
            node_count=10,
            edge_count=12,
            key_label_counts={"Entity": 10},
            checksum="abc123",
            last_verified_at=None,
            last_reload_at=None,
            writer_lock_token="incremental-sync",
        )


def test_assertion_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        GraphAssertionRecord(
            assertion_id="assertion-1",
            source_node_id="node-1",
            target_node_id="node-2",
            assertion_type="risk",
            evidence={},
            confidence=1.5,
            created_at=NOW,
        )


def test_graph_snapshot_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        GraphSnapshot(
            cycle_id="cycle-1",
            graph_snapshot_id="snapshot-1",
            version="0.1.0",
            node_count=-1,
            edge_count=0,
            nodes=[],
            edges=[],
            created_at=NOW,
        )


def test_propagation_context_requires_fundamental_channel() -> None:
    with pytest.raises(ValidationError):
        PropagationContext(
            cycle_id="cycle-1",
            world_state_ref="world-state-1",
            graph_generation_id=1,
            enabled_channels=[],
            channel_multipliers={"fundamental": 1.0},
            regime_multipliers={"fundamental": 1.0},
            decay_policy={},
            regime_context={},
        )


@pytest.mark.parametrize(
    ("payload_update", "match"),
    [
        ({"depth": 7}, "less than or equal"),
        ({"result_limit": 0}, "greater than or equal"),
        ({"result_limit": 1001}, "less than or equal"),
        ({"max_iterations": 0}, "greater than or equal"),
        ({"enabled_channels": ["fundamental", "fundamental"]}, "duplicates"),
        ({"enabled_channels": []}, "too_short"),
        ({"channel_multipliers": {"unknown": 1.0}}, "unknown"),
    ],
)
def test_readonly_simulation_request_validates_runtime_bounds(
    payload_update: dict[str, Any],
    match: str,
) -> None:
    payload = {
        "cycle_id": "cycle-1",
        "world_state_ref": "world-state-1",
        "graph_generation_id": 1,
        "enabled_channels": ["fundamental"],
        "channel_multipliers": {"fundamental": 1.0},
        "regime_multipliers": {"fundamental": 1.0},
        "decay_policy": {},
        "regime_context": {},
    }
    payload.update(payload_update)

    with pytest.raises(ValidationError, match=match):
        ReadonlySimulationRequest(**payload)


def test_models_forbid_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        GraphNodeRecord(
            node_id="node-1",
            canonical_entity_id="entity-1",
            label="Entity",
            properties={},
            created_at=NOW,
            updated_at=NOW,
            raw_text="not allowed",
        )
