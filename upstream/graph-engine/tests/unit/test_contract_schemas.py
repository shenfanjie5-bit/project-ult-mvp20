from __future__ import annotations

from typing import get_args, get_origin, get_type_hints

import contracts.schemas as contract_schemas

import graph_engine
from graph_engine import models
from graph_engine.promotion import CandidateDeltaReader


def test_public_graph_contracts_are_reexported_from_contracts() -> None:
    assert models.CandidateGraphDelta is contract_schemas.CandidateGraphDelta
    assert models.GraphSnapshot is contract_schemas.GraphSnapshot
    assert models.GraphImpactSnapshot is contract_schemas.GraphImpactSnapshot
    assert graph_engine.CandidateGraphDelta is contract_schemas.CandidateGraphDelta
    assert graph_engine.GraphSnapshot is contract_schemas.GraphSnapshot
    assert graph_engine.GraphImpactSnapshot is contract_schemas.GraphImpactSnapshot


def test_public_graph_contract_json_schemas_match_contracts() -> None:
    assert (
        models.CandidateGraphDelta.model_json_schema()
        == contract_schemas.CandidateGraphDelta.model_json_schema()
    )
    assert models.GraphSnapshot.model_json_schema() == contract_schemas.GraphSnapshot.model_json_schema()
    assert (
        models.GraphImpactSnapshot.model_json_schema()
        == contract_schemas.GraphImpactSnapshot.model_json_schema()
    )


def test_public_graph_contract_field_sets_are_pinned() -> None:
    assert set(models.CandidateGraphDelta.model_fields) == {
        "delta_id",
        "delta_type",
        "source_node",
        "target_node",
        "relation_type",
        "properties",
        "evidence",
        "subsystem_id",
        # contracts v0.1.3 added the `producer_context` extension slot
        # (Stage 2.8 follow-up #3 Op1 — backward-compatible nullable
        # field for cross-subsystem provenance attached to canonical
        # Ex-1/2/3 wire payloads). graph-engine just re-exports;
        # consumers may inspect `producer_context` for upstream
        # subsystem trace info but graph-engine doesn't depend on it.
        "producer_context",
    }
    assert set(models.GraphSnapshot.model_fields) == {
        "graph_snapshot_id",
        "cycle_id",
        "version",
        "created_at",
        "node_count",
        "edge_count",
        "nodes",
        "edges",
    }
    assert set(models.GraphImpactSnapshot.model_fields) == {
        "impact_snapshot_id",
        "cycle_id",
        "version",
        "created_at",
        "target_entities",
        "affected_entities",
        "affected_sectors",
        "direction",
        "impact_score",
        "evidence_refs",
    }


def test_candidate_delta_reader_exposes_contract_delta_shape() -> None:
    hints = get_type_hints(CandidateDeltaReader.read_candidate_graph_deltas)
    return_type = hints["return"]

    assert get_origin(return_type) is list
    assert get_args(return_type) == (contract_schemas.CandidateGraphDelta,)


def test_internal_metric_and_frozen_delta_models_are_not_public_contracts() -> None:
    assert models.FrozenGraphDelta is not contract_schemas.CandidateGraphDelta
    assert models.GraphMetricsSnapshot is not contract_schemas.GraphSnapshot
    assert "FrozenGraphDelta" not in graph_engine.__all__
    assert "GraphMetricsSnapshot" not in graph_engine.__all__
