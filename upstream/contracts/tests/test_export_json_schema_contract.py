from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from pydantic import BaseModel

import contracts.schemas as schemas
from contracts.core import ContractBaseModel, __version__
from contracts.export import (
    SCHEMA_MODEL_REGISTRY,
    SchemaArtifact,
    export_json_schemas,
    iter_schema_models,
)
from contracts.schemas import (
    FORBIDDEN_INGEST_METADATA_FIELDS,
    FORMAL_OBJECT_REGISTRY,
    Ex0Metadata,
    Ex1CandidateFact,
    Ex2CandidateSignal,
    Ex3CandidateGraphDelta,
    FormalObjectName,
)


EX_PAYLOAD_REQUIRED_FIELDS = {
    "ex0_metadata": {
        "subsystem_id",
        "version",
        "heartbeat_at",
        "status",
        "last_output_at",
        "pending_count",
    },
    "ex1_candidate_fact": {
        "fact_id",
        "entity_id",
        "fact_type",
        "fact_content",
        "confidence",
        "source_reference",
        "extracted_at",
        "subsystem_id",
    },
    "ex2_candidate_signal": {
        # v0.1.3: affected_sectors STAYS required; only list min_length=1
        # was relaxed. Positive coverage in test_ex_payloads.py.
        "signal_id",
        "signal_type",
        "direction",
        "magnitude",
        "affected_entities",
        "affected_sectors",
        "time_horizon",
        "evidence",
        "confidence",
        "subsystem_id",
    },
    "ex3_candidate_graph_delta": {
        "delta_id",
        "delta_type",
        "source_node",
        "target_node",
        "relation_type",
        "properties",
        "evidence",
        "subsystem_id",
    },
}

NOW = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def conditional_rule_rejects(
    rule: dict[str, object],
    payload: dict[str, object],
) -> bool:
    condition = rule.get("if")
    consequence = rule.get("then")
    if not isinstance(condition, dict) or not isinstance(consequence, dict):
        return False

    return _condition_matches(condition, payload) and not _schema_fragment_matches(
        consequence,
        payload,
    )


def _condition_matches(
    schema: dict[str, object],
    payload: dict[str, object],
) -> bool:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return True

    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, dict):
            continue

        value = payload.get(field_name)
        if "const" in field_schema and value != field_schema["const"]:
            return False

        enum_values = field_schema.get("enum")
        if isinstance(enum_values, list) and value not in enum_values:
            return False

    return True


def _schema_fragment_matches(
    schema: dict[str, object],
    payload: dict[str, object],
) -> bool:
    required = schema.get("required")
    if isinstance(required, list):
        for field_name in required:
            if isinstance(field_name, str) and field_name not in payload:
                return False

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return True

    for field_name, field_schema in properties.items():
        if field_name not in payload or not isinstance(field_schema, dict):
            continue

        value = payload[field_name]
        expected_type = field_schema.get("type")
        if expected_type == "null" and value is not None:
            return False

        negated_schema = field_schema.get("not")
        if (
            isinstance(negated_schema, dict)
            and negated_schema.get("type") == "null"
            and value is None
        ):
            return False

        if "const" in field_schema and value != field_schema["const"]:
            return False

        min_items = field_schema.get("minItems")
        if isinstance(min_items, int) and isinstance(value, list):
            if len(value) < min_items:
                return False

    return True


def assert_exported_schema_rejects_with_conditional_rule(
    schema: dict[str, object],
    payload: dict[str, object],
) -> None:
    rules = schema.get("allOf")
    assert isinstance(rules, list)
    assert any(
        isinstance(rule, dict) and conditional_rule_rejects(rule, payload)
        for rule in rules
    )


def assert_exported_schema_allows_conditional_rules(
    schema: dict[str, object],
    payload: dict[str, object],
) -> None:
    rules = schema.get("allOf")
    assert isinstance(rules, list)
    assert not any(
        isinstance(rule, dict) and conditional_rule_rejects(rule, payload)
        for rule in rules
    )


def test_schema_artifact_is_a_valid_contract_model() -> None:
    artifact = SchemaArtifact(
        name="ex0_metadata",
        source_model="contracts.schemas.ex_payloads.Ex0Metadata",
        output_path="ex0_metadata.schema.json",
    )

    assert artifact.artifact_type == "json_schema"
    assert artifact.version == __version__ == "0.1.3"


def test_iter_schema_models_returns_stable_registry_order() -> None:
    assert tuple(iter_schema_models()) == tuple(SCHEMA_MODEL_REGISTRY.items())


def test_every_public_schema_pydantic_model_is_registered() -> None:
    public_schema_models = {
        name: exported
        for name in schemas.__all__
        if isinstance((exported := getattr(schemas, name)), type)
        and issubclass(exported, BaseModel)
    }

    registered_models = set(SCHEMA_MODEL_REGISTRY.values())
    missing_names = {
        name
        for name, model in public_schema_models.items()
        if model not in registered_models
    }

    assert not missing_names


def test_registry_contains_expected_schema_models_only_from_public_schemas() -> None:
    expected_models = {
        schemas.BaseExPayload,
        Ex0Metadata,
        Ex1CandidateFact,
        Ex2CandidateSignal,
        Ex3CandidateGraphDelta,
        schemas.CanonicalEntity,
        schemas.EntityAlias,
        schemas.EntityReference,
        schemas.ResolutionCase,
        schemas.ReasonerErrorClassification,
        schemas.ReasonerRequest,
        schemas.ReasonerResult,
        schemas.ReasonerReplay,
        schemas.ReasonerHealth,
        schemas.GraphSnapshot,
        schemas.GraphImpactSnapshot,
        schemas.AlphaResult,
        schemas.CycleMetadata,
        schemas.FormalObjectBase,
        *FORMAL_OBJECT_REGISTRY.values(),
    }

    assert set(SCHEMA_MODEL_REGISTRY.values()) == expected_models
    assert "backtest_result" not in SCHEMA_MODEL_REGISTRY


def test_export_writes_manifest_and_schema_files(tmp_path: Path) -> None:
    artifacts = export_json_schemas(tmp_path, version="0.1.0")
    manifest = load_json(tmp_path / "manifest.json")

    assert len(artifacts) == len(SCHEMA_MODEL_REGISTRY)
    assert manifest["artifact_type"] == "json_schema"
    assert manifest["version"] == "0.1.0"
    assert [artifact["name"] for artifact in manifest["artifacts"]] == list(
        SCHEMA_MODEL_REGISTRY
    )
    assert {path.name for path in tmp_path.glob("*.schema.json")} == {
        f"{name}.schema.json" for name in SCHEMA_MODEL_REGISTRY
    }


def test_exported_json_schemas_include_contract_metadata(tmp_path: Path) -> None:
    export_json_schemas(tmp_path, version="0.1.0")

    for name, model in iter_schema_models():
        schema = load_json(tmp_path / f"{name}.schema.json")

        assert schema["x-contract-version"] == "0.1.0"
        assert schema["x-source-model"] == (
            f"{model.__module__}.{model.__qualname__}"
        )


def test_default_export_metadata_matches_package_version(tmp_path: Path) -> None:
    export_json_schemas(tmp_path)
    manifest = load_json(tmp_path / "manifest.json")

    assert manifest["version"] == __version__
    for artifact in manifest["artifacts"]:
        assert artifact["version"] == __version__
        schema = load_json(tmp_path / f"{artifact['name']}.schema.json")
        assert schema["x-contract-version"] == __version__


def test_exported_ex_payload_required_fields_match_contracts(tmp_path: Path) -> None:
    export_json_schemas(tmp_path, version="0.1.0")

    for schema_name, expected_required_fields in EX_PAYLOAD_REQUIRED_FIELDS.items():
        schema = load_json(tmp_path / f"{schema_name}.schema.json")

        assert set(schema["required"]) == expected_required_fields
        assert FORBIDDEN_INGEST_METADATA_FIELDS.isdisjoint(schema["properties"])


def test_exported_formal_object_set_is_closed(tmp_path: Path) -> None:
    export_json_schemas(tmp_path, version="0.1.0")

    concrete_formal_keys = {
        key
        for key, model in SCHEMA_MODEL_REGISTRY.items()
        if model in set(FORMAL_OBJECT_REGISTRY.values())
    }
    exported_text = "\n".join(
        path.name + "\n" + path.read_text(encoding="utf-8")
        for path in sorted(tmp_path.glob("*.json"))
    )

    assert concrete_formal_keys == {name.value for name in FormalObjectName}
    assert "backtest_result" not in exported_text


def test_exported_json_schema_encodes_resolution_case_invariants(
    tmp_path: Path,
) -> None:
    export_json_schemas(tmp_path, version="0.1.0")
    schema = load_json(tmp_path / "resolution_case.schema.json")
    base_payload = {
        "resolution_case_id": "resolution-1",
        "input_alias": "Apple",
        "decision": "matched",
        "confidence": 0.9,
        "candidate_entities": [
            {
                "entity_id": "AAPL",
                "entity_type": "equity",
                "canonical_id_rule_version": "0.1.0",
            }
        ],
        "evidence_refs": ["fact-1"],
        "resolved_at": NOW,
        "canonical_id_rule_version": "0.1.0",
    }

    assert_exported_schema_rejects_with_conditional_rule(schema, base_payload)
    assert_exported_schema_rejects_with_conditional_rule(
        schema,
        {
            **base_payload,
            "decision": "ambiguous",
            "resolved_entity": {
                "entity_id": "AAPL",
                "entity_type": "equity",
                "canonical_id_rule_version": "0.1.0",
            },
        },
    )
    assert_exported_schema_rejects_with_conditional_rule(
        schema,
        {
            **base_payload,
            "resolved_entity": {
                "entity_id": "AAPL",
                "entity_type": "equity",
                "canonical_id_rule_version": "0.1.0",
            },
            "candidate_entities": [],
        },
    )
    assert_exported_schema_rejects_with_conditional_rule(
        schema,
        {
            **base_payload,
            "decision": "ambiguous",
            "resolved_entity": None,
            "candidate_entities": [],
        },
    )
    assert_exported_schema_allows_conditional_rules(
        schema,
        {
            **base_payload,
            "decision": "unresolved",
            "confidence": 0.0,
            "resolved_entity": None,
            "candidate_entities": [],
        },
    )


def test_exported_json_schema_encodes_reasoner_status_invariants(
    tmp_path: Path,
) -> None:
    export_json_schemas(tmp_path, version="0.1.0")
    result_schema = load_json(tmp_path / "reasoner_result.schema.json")
    health_schema = load_json(tmp_path / "reasoner_health.schema.json")

    assert_exported_schema_rejects_with_conditional_rule(
        result_schema,
        {
            "result_id": "result-1",
            "request_id": "request-1",
            "status": "failed",
            "reasoner_name": "fixture",
            "reasoner_version": "0.1.0",
            "output": {},
            "completed_at": NOW,
        },
    )
    assert_exported_schema_rejects_with_conditional_rule(
        result_schema,
        {
            "result_id": "result-1",
            "request_id": "request-1",
            "status": "completed",
            "reasoner_name": "fixture",
            "reasoner_version": "0.1.0",
            "output": {},
            "completed_at": NOW,
            "error_classification": {
                "code": "REASONER_TOOL_EXECUTION_ERROR",
                "category": "tool_execution",
                "severity": "error",
                "retryable": True,
                "message": "tool call failed",
            },
        },
    )
    assert_exported_schema_rejects_with_conditional_rule(
        health_schema,
        {
            "subsystem_id": "reasoner-runtime",
            "version": "0.1.0",
            "checked_at": NOW,
            "status": "ok",
            "last_success_at": NOW,
            "pending_count": 0,
            "error_classification": {
                "code": "REASONER_TOOL_EXECUTION_ERROR",
                "category": "tool_execution",
                "severity": "error",
                "retryable": True,
                "message": "tool call failed",
            },
        },
    )


def test_exported_json_schema_encodes_reasoner_error_code_invariant(
    tmp_path: Path,
) -> None:
    export_json_schemas(tmp_path, version="0.1.0")
    schema = load_json(tmp_path / "reasoner_error_classification.schema.json")

    assert_exported_schema_rejects_with_conditional_rule(
        schema,
        {
            "code": "REASONER_TIMEOUT_ERROR",
            "category": "tool_execution",
            "severity": "error",
            "retryable": True,
            "message": "tool call failed",
        },
    )


def test_exported_json_schema_marks_runtime_only_invariants(
    tmp_path: Path,
) -> None:
    export_json_schemas(tmp_path, version="0.1.0")

    cycle_schema = load_json(tmp_path / "cycle_metadata.schema.json")
    graph_schema = load_json(tmp_path / "graph_snapshot.schema.json")

    assert {
        invariant["id"]
        for invariant in cycle_schema["x-contract-runtime-invariants"]
    } == {"cycle_metadata.ended_at_gte_started_at"}
    assert {
        invariant["id"]
        for invariant in graph_schema["x-contract-runtime-invariants"]
    } == {
        "graph_snapshot.counts_match_payloads",
        "graph_snapshot.edges_reference_declared_nodes",
    }


def test_exported_alpha_result_score_carries_runtime_strictness(
    tmp_path: Path,
) -> None:
    export_json_schemas(tmp_path, version="0.1.0")
    schema = load_json(tmp_path / "alpha_result.schema.json")
    properties = schema["properties"]
    assert isinstance(properties, dict)
    score = properties["score"]
    assert isinstance(score, dict)

    assert score["x-contract-runtime-validation"] == {
        "allow_inf_nan": False,
        "strict": True,
    }
