from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

import contracts.schemas as schemas
from contracts.compat import compare_schema_sets, load_schema_directory
from contracts.core import ContractBaseModel, __version__
from contracts.errors import ErrorCode
from contracts.export import SCHEMA_MODEL_REGISTRY, export_json_schemas


NOW = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)

ENTITY_CONTRACTS = {
    "canonical_entity": schemas.CanonicalEntity,
    "entity_alias": schemas.EntityAlias,
    "entity_reference": schemas.EntityReference,
    "resolution_case": schemas.ResolutionCase,
}
REASONER_CONTRACTS = {
    "reasoner_error_classification": schemas.ReasonerErrorClassification,
    "reasoner_request": schemas.ReasonerRequest,
    "reasoner_result": schemas.ReasonerResult,
    "reasoner_replay": schemas.ReasonerReplay,
    "reasoner_health": schemas.ReasonerHealth,
}
GRAPH_CONTRACTS = {
    "candidate_graph_delta": schemas.CandidateGraphDelta,
    "graph_snapshot": schemas.GraphSnapshot,
    "graph_impact_snapshot": schemas.GraphImpactSnapshot,
}
DOWNSTREAM_CONTRACTS = {
    **ENTITY_CONTRACTS,
    **REASONER_CONTRACTS,
    **GRAPH_CONTRACTS,
}


def entity_reference_payload() -> dict[str, object]:
    return {
        "entity_id": "AAPL",
        "entity_type": "equity",
        "canonical_id_rule_version": "0.1.0",
        "display_name": "Apple Inc.",
    }


def graph_delta_payload() -> dict[str, object]:
    return {
        "delta_id": "delta-1",
        "delta_type": "upsert_edge",
        "source_node": "AAPL",
        "target_node": "technology",
        "relation_type": "belongs_to_sector",
        "properties": {"weight": 1.0},
        "evidence": ["fact-1"],
        "subsystem_id": "subsystem-news",
    }


def reasoner_error_payload() -> dict[str, object]:
    return {
        "code": "REASONER_TOOL_EXECUTION_ERROR",
        "category": "tool_execution",
        "severity": "error",
        "retryable": True,
        "message": "tool call failed",
        "details": {"tool": "search"},
    }


def reasoner_request_payload() -> dict[str, object]:
    return {
        "request_id": "reasoner-request-1",
        "cycle_id": "cycle-20260415-001",
        "reasoner_name": "fixture-reasoner",
        "reasoner_version": "0.1.0",
        "prompt": "Summarize the evidence.",
        "context": {"entity_id": "AAPL"},
        "requested_at": NOW,
        "input_refs": ["fact-1"],
    }


def reasoner_result_payload() -> dict[str, object]:
    return {
        "result_id": "reasoner-result-1",
        "request_id": "reasoner-request-1",
        "status": "completed",
        "reasoner_name": "fixture-reasoner",
        "reasoner_version": "0.1.0",
        "output": {"summary": "positive earnings signal"},
        "evidence_refs": ["fact-1"],
        "completed_at": NOW,
        "confidence": 0.8,
    }


def valid_payloads() -> dict[str, dict[str, object]]:
    return {
        "canonical_entity": {
            "canonical_entity_id": "AAPL",
            "entity_type": "equity",
            "display_name": "Apple Inc.",
            "canonical_id_rule_version": "0.1.0",
            "created_at": NOW,
            "attributes": {"ticker": "AAPL"},
        },
        "entity_alias": {
            "alias_id": "alias-aapl",
            "canonical_entity_id": "AAPL",
            "alias": "Apple",
            "alias_type": "common_name",
            "source_reference": {"source": "fixture"},
            "confidence": 0.9,
            "observed_at": NOW,
            "canonical_id_rule_version": "0.1.0",
        },
        "entity_reference": entity_reference_payload(),
        "resolution_case": {
            "resolution_case_id": "resolution-1",
            "input_alias": "Apple",
            "decision": "matched",
            "confidence": 0.9,
            "candidate_entities": [entity_reference_payload()],
            "evidence_refs": ["fact-1"],
            "resolved_at": NOW,
            "canonical_id_rule_version": "0.1.0",
            "resolved_entity": entity_reference_payload(),
        },
        "reasoner_error_classification": reasoner_error_payload(),
        "reasoner_request": reasoner_request_payload(),
        "reasoner_result": reasoner_result_payload(),
        "reasoner_replay": {
            "replay_id": "reasoner-replay-1",
            "request": reasoner_request_payload(),
            "result": reasoner_result_payload(),
            "recorded_at": NOW,
            "replay_version": "0.1.0",
        },
        "reasoner_health": {
            "subsystem_id": "reasoner-runtime",
            "version": "0.1.0",
            "checked_at": NOW,
            "status": "ok",
            "last_success_at": NOW,
            "pending_count": 0,
        },
        "candidate_graph_delta": graph_delta_payload(),
        "graph_snapshot": {
            "graph_snapshot_id": "graph-snapshot-1",
            "cycle_id": "cycle-20260415-001",
            "version": "0.1.0",
            "created_at": NOW,
            "node_count": 2,
            "edge_count": 1,
            "nodes": [
                {
                    "node_id": "AAPL",
                    "labels": ["entity"],
                    "entity": entity_reference_payload(),
                },
                {
                    "node_id": "technology",
                    "labels": ["sector"],
                },
            ],
            "edges": [
                {
                    "edge_id": "edge-1",
                    "source_node": "AAPL",
                    "target_node": "technology",
                    "relation_type": "belongs_to_sector",
                    "evidence_refs": ["fact-1"],
                }
            ],
        },
        "graph_impact_snapshot": {
            "impact_snapshot_id": "impact-snapshot-1",
            "cycle_id": "cycle-20260415-001",
            "version": "0.1.0",
            "created_at": NOW,
            "target_entities": [entity_reference_payload()],
            "affected_entities": [entity_reference_payload()],
            "affected_sectors": ["technology"],
            "direction": "bullish",
            "impact_score": 0.7,
            "evidence_refs": ["fact-1"],
        },
    }


def test_downstream_contract_names_are_public_and_registered() -> None:
    public_models = {
        getattr(schemas, model.__name__) for model in DOWNSTREAM_CONTRACTS.values()
    }

    assert public_models == set(DOWNSTREAM_CONTRACTS.values())
    for contract_name, model in DOWNSTREAM_CONTRACTS.items():
        assert contract_name in SCHEMA_MODEL_REGISTRY
        assert SCHEMA_MODEL_REGISTRY[contract_name] is model
        assert model.__name__ in schemas.__all__

    assert schemas.CandidateGraphDelta is schemas.Ex3CandidateGraphDelta
    assert "CandidateGraphDelta" in schemas.__all__


def test_entity_registry_required_entity_exports_are_public() -> None:
    from contracts.schemas import (
        CANONICAL_ID_RULE_VERSION,
        CanonicalEntity,
        EntityAlias,
        EntityReference,
        ResolutionCase,
    )

    assert CANONICAL_ID_RULE_VERSION == schemas.CANONICAL_ID_RULE_VERSION
    assert isinstance(CANONICAL_ID_RULE_VERSION, str)
    assert CANONICAL_ID_RULE_VERSION
    assert CANONICAL_ID_RULE_VERSION != __version__
    assert "CANONICAL_ID_RULE_VERSION" in schemas.__all__
    assert CanonicalEntity is schemas.CanonicalEntity
    assert EntityAlias is schemas.EntityAlias
    assert EntityReference is schemas.EntityReference
    assert ResolutionCase is schemas.ResolutionCase


@pytest.mark.parametrize("contract_name,model", sorted(DOWNSTREAM_CONTRACTS.items()))
def test_downstream_contract_payloads_validate(
    contract_name: str,
    model: type[ContractBaseModel],
) -> None:
    instance = model.model_validate(valid_payloads()[contract_name])

    assert isinstance(instance, model)


@pytest.mark.parametrize(
    "contract_name,field_name",
    [
        ("canonical_entity", "canonical_id_rule_version"),
        ("entity_alias", "canonical_id_rule_version"),
        ("entity_reference", "canonical_id_rule_version"),
        ("resolution_case", "canonical_id_rule_version"),
        ("reasoner_request", "requested_at"),
        ("reasoner_result", "completed_at"),
        ("reasoner_replay", "recorded_at"),
        ("reasoner_health", "checked_at"),
        ("graph_snapshot", "created_at"),
        ("graph_impact_snapshot", "created_at"),
    ],
)
def test_downstream_contract_required_fields_are_enforced(
    contract_name: str,
    field_name: str,
) -> None:
    payload = valid_payloads()[contract_name]
    payload.pop(field_name)

    with pytest.raises(ValidationError):
        DOWNSTREAM_CONTRACTS[contract_name].model_validate(payload)


def test_graph_snapshot_counts_must_match_payload_lengths() -> None:
    payload = {**valid_payloads()["graph_snapshot"], "node_count": 3}

    with pytest.raises(ValidationError, match="node_count"):
        schemas.GraphSnapshot.model_validate(payload)


def test_resolution_case_matched_requires_resolved_entity() -> None:
    payload = valid_payloads()["resolution_case"]
    payload.pop("resolved_entity")

    with pytest.raises(ValidationError, match="resolved_entity"):
        schemas.ResolutionCase.model_validate(payload)


@pytest.mark.parametrize("decision", ["ambiguous", "unresolved"])
def test_resolution_case_unmatched_decision_rejects_resolved_entity(
    decision: str,
) -> None:
    payload = {**valid_payloads()["resolution_case"], "decision": decision}

    with pytest.raises(ValidationError, match="resolved_entity"):
        schemas.ResolutionCase.model_validate(payload)


def test_resolution_case_unresolved_allows_no_candidate_entities() -> None:
    payload = {
        **valid_payloads()["resolution_case"],
        "decision": "unresolved",
        "candidate_entities": [],
        "confidence": 0.0,
        "resolved_entity": None,
    }

    case = schemas.ResolutionCase.model_validate(payload)

    assert case.decision is schemas.EntityResolutionDecision.UNRESOLVED
    assert case.candidate_entities == []
    assert case.resolved_entity is None


@pytest.mark.parametrize("decision", ["matched", "ambiguous"])
def test_resolution_case_candidate_entities_required_unless_unresolved(
    decision: str,
) -> None:
    payload = {
        **valid_payloads()["resolution_case"],
        "decision": decision,
        "candidate_entities": [],
    }
    if decision == "ambiguous":
        payload["resolved_entity"] = None

    with pytest.raises(ValidationError, match="candidate_entities"):
        schemas.ResolutionCase.model_validate(payload)


def test_failed_reasoner_result_requires_error_classification() -> None:
    payload = {**reasoner_result_payload(), "status": "failed"}

    with pytest.raises(ValidationError, match="error_classification"):
        schemas.ReasonerResult.model_validate(payload)


@pytest.mark.parametrize("status", ["accepted", "completed"])
def test_non_failed_reasoner_result_rejects_error_classification(
    status: str,
) -> None:
    payload = {
        **reasoner_result_payload(),
        "status": status,
        "error_classification": reasoner_error_payload(),
    }

    with pytest.raises(ValidationError, match="error_classification"):
        schemas.ReasonerResult.model_validate(payload)


def test_failed_reasoner_health_requires_error_classification() -> None:
    payload = {**valid_payloads()["reasoner_health"], "status": "failed"}

    with pytest.raises(ValidationError, match="error_classification"):
        schemas.ReasonerHealth.model_validate(payload)


def test_ok_reasoner_health_rejects_error_classification() -> None:
    payload = {
        **valid_payloads()["reasoner_health"],
        "error_classification": reasoner_error_payload(),
    }

    with pytest.raises(ValidationError, match="error_classification"):
        schemas.ReasonerHealth.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "missing_node"),
    [
        ("source_node", "missing-source"),
        ("target_node", "missing-target"),
    ],
)
def test_graph_snapshot_edges_must_reference_declared_nodes(
    field_name: str,
    missing_node: str,
) -> None:
    payload = valid_payloads()["graph_snapshot"]
    edges = payload["edges"]
    assert isinstance(edges, list)
    edge = edges[0]
    assert isinstance(edge, dict)
    edge[field_name] = missing_node

    with pytest.raises(ValidationError, match=field_name):
        schemas.GraphSnapshot.model_validate(payload)


def test_reasoner_error_classification_rejects_unknown_category() -> None:
    payload = {**reasoner_error_payload(), "category": "unknown"}

    with pytest.raises(ValidationError):
        schemas.ReasonerErrorClassification.model_validate(payload)


def test_reasoner_error_classification_requires_registered_code() -> None:
    payload = reasoner_error_payload()
    payload.pop("code")

    with pytest.raises(ValidationError):
        schemas.ReasonerErrorClassification.model_validate(payload)


def test_reasoner_error_classification_uses_error_code_registry() -> None:
    classification = schemas.ReasonerErrorClassification.model_validate(
        reasoner_error_payload()
    )

    assert classification.code is ErrorCode.REASONER_TOOL_EXECUTION_ERROR


def test_reasoner_error_classification_rejects_mismatched_code() -> None:
    payload = {
        **reasoner_error_payload(),
        "code": "REASONER_TIMEOUT_ERROR",
    }

    with pytest.raises(ValidationError, match="expected REASONER_TOOL_EXECUTION_ERROR"):
        schemas.ReasonerErrorClassification.model_validate(payload)


def test_export_manifest_includes_downstream_shared_contracts(tmp_path: Path) -> None:
    export_json_schemas(tmp_path, version="0.1.0")
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    artifact_names = {
        artifact["name"]
        for artifact in manifest["artifacts"]
        if isinstance(artifact, dict)
    }

    assert set(DOWNSTREAM_CONTRACTS) <= artifact_names
    for contract_name in DOWNSTREAM_CONTRACTS:
        assert (tmp_path / f"{contract_name}.schema.json").is_file()


def test_new_downstream_contract_breaking_change_is_detected(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline"
    current = tmp_path / "current"
    export_json_schemas(baseline, version="0.1.0")
    shutil.copytree(baseline, current)

    schema_path = current / "graph_impact_snapshot.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    properties = schema["properties"]
    assert isinstance(properties, dict)
    impact_score = properties["impact_score"]
    assert isinstance(impact_score, dict)
    impact_score["type"] = "string"
    schema_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = compare_schema_sets(
        load_schema_directory(baseline),
        load_schema_directory(current),
    )

    assert not result.is_compatible
    assert any(
        event.schema_name == "graph_impact_snapshot"
        and event.change_type == "field_type_changed"
        and event.breaking
        for event in result.events
    )
