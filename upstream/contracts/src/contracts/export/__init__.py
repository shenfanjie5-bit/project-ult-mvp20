"""JSON Schema 自动导出 CLI 与库入口。"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from contracts.core import ContractBaseModel, VersionString, __version__
from contracts.schemas import (
    AlphaResult,
    AlphaResultSnapshot,
    AuditRecord,
    BaseExPayload,
    CandidateGraphDelta,
    CanonicalEntity,
    CycleMetadata,
    DashboardSnapshot,
    EntityAlias,
    EntityReference,
    Ex0Metadata,
    Ex1CandidateFact,
    Ex2CandidateSignal,
    Ex3CandidateGraphDelta,
    FormalObjectBase,
    GraphImpactSnapshot,
    GraphSnapshot,
    OfficialAlphaPool,
    RecommendationSnapshot,
    ReasonerErrorClassification,
    ReasonerHealth,
    ReasonerReplay,
    ReasonerRequest,
    ReasonerResult,
    ResolutionCase,
    ReplayRecord,
    Report,
    WorldStateSnapshot,
)


class SchemaArtifact(ContractBaseModel):
    """单个 JSON Schema 导出产物的清单记录。"""

    name: str
    source_model: str
    artifact_type: Literal["json_schema"] = "json_schema"
    version: VersionString = __version__
    output_path: str


SCHEMA_MODEL_REGISTRY: Mapping[str, type[ContractBaseModel]] = MappingProxyType(
    {
        "base_ex_payload": BaseExPayload,
        "ex0_metadata": Ex0Metadata,
        "ex1_candidate_fact": Ex1CandidateFact,
        "ex2_candidate_signal": Ex2CandidateSignal,
        "ex3_candidate_graph_delta": Ex3CandidateGraphDelta,
        "canonical_entity": CanonicalEntity,
        "entity_alias": EntityAlias,
        "entity_reference": EntityReference,
        "resolution_case": ResolutionCase,
        "reasoner_error_classification": ReasonerErrorClassification,
        "reasoner_request": ReasonerRequest,
        "reasoner_result": ReasonerResult,
        "reasoner_replay": ReasonerReplay,
        "reasoner_health": ReasonerHealth,
        "candidate_graph_delta": CandidateGraphDelta,
        "graph_snapshot": GraphSnapshot,
        "graph_impact_snapshot": GraphImpactSnapshot,
        "alpha_result": AlphaResult,
        "cycle_metadata": CycleMetadata,
        "formal_object_base": FormalObjectBase,
        "world_state_snapshot": WorldStateSnapshot,
        "official_alpha_pool": OfficialAlphaPool,
        "alpha_result_snapshot": AlphaResultSnapshot,
        "recommendation_snapshot": RecommendationSnapshot,
        "dashboard_snapshot": DashboardSnapshot,
        "report": Report,
        "audit_record": AuditRecord,
        "replay_record": ReplayRecord,
    }
)

_RESOLUTION_CASE_RULES: tuple[dict[str, object], ...] = (
    {
        "if": {"properties": {"decision": {"const": "matched"}}},
        "then": {
            "required": ["resolved_entity"],
            "properties": {
                "resolved_entity": {"not": {"type": "null"}},
                "candidate_entities": {"minItems": 1},
            },
        },
    },
    {
        "if": {"properties": {"decision": {"const": "ambiguous"}}},
        "then": {
            "properties": {
                "resolved_entity": {"type": "null"},
                "candidate_entities": {"minItems": 1},
            },
        },
    },
    {
        "if": {"properties": {"decision": {"const": "unresolved"}}},
        "then": {"properties": {"resolved_entity": {"type": "null"}}},
    },
)

_REASONER_RESULT_RULES: tuple[dict[str, object], ...] = (
    {
        "if": {"properties": {"status": {"const": "failed"}}},
        "then": {
            "required": ["error_classification"],
            "properties": {"error_classification": {"not": {"type": "null"}}},
        },
    },
    {
        "if": {"properties": {"status": {"enum": ["accepted", "completed"]}}},
        "then": {"properties": {"error_classification": {"type": "null"}}},
    },
)

_REASONER_HEALTH_RULES: tuple[dict[str, object], ...] = (
    {
        "if": {"properties": {"status": {"const": "failed"}}},
        "then": {
            "required": ["error_classification"],
            "properties": {"error_classification": {"not": {"type": "null"}}},
        },
    },
    {
        "if": {"properties": {"status": {"const": "ok"}}},
        "then": {"properties": {"error_classification": {"type": "null"}}},
    },
)

_REASONER_ERROR_CODE_BY_CATEGORY: Mapping[str, str] = MappingProxyType(
    {
        "input_contract": "REASONER_INPUT_CONTRACT_ERROR",
        "model_provider": "REASONER_MODEL_PROVIDER_ERROR",
        "tool_execution": "REASONER_TOOL_EXECUTION_ERROR",
        "timeout": "REASONER_TIMEOUT_ERROR",
        "internal": "REASONER_INTERNAL_ERROR",
    }
)

_REASONER_ERROR_CLASSIFICATION_RULES: tuple[dict[str, object], ...] = tuple(
    {
        "if": {"properties": {"category": {"const": category}}},
        "then": {"properties": {"code": {"const": code}}},
    }
    for category, code in _REASONER_ERROR_CODE_BY_CATEGORY.items()
)

_RUNTIME_INVARIANTS_BY_TITLE: Mapping[str, tuple[dict[str, str], ...]] = (
    MappingProxyType(
        {
            "CycleMetadata": (
                {
                    "id": "cycle_metadata.ended_at_gte_started_at",
                    "description": (
                        "ended_at must be greater than or equal to started_at; "
                        "enforced by Pydantic runtime validation."
                    ),
                },
            ),
            "GraphSnapshot": (
                {
                    "id": "graph_snapshot.counts_match_payloads",
                    "description": (
                        "node_count and edge_count must match the nodes and "
                        "edges array lengths; enforced by Pydantic runtime "
                        "validation."
                    ),
                },
                {
                    "id": "graph_snapshot.edges_reference_declared_nodes",
                    "description": (
                        "edge source_node and target_node values must reference "
                        "declared nodes; enforced by Pydantic runtime validation."
                    ),
                },
            ),
        }
    )
)


def iter_schema_models() -> Iterator[tuple[str, type[ContractBaseModel]]]:
    """按稳定 registry 顺序返回待导出的 Pydantic 模型。"""

    yield from SCHEMA_MODEL_REGISTRY.items()


def export_json_schemas(
    output_dir: str | Path,
    *,
    version: str = __version__,
) -> tuple[SchemaArtifact, ...]:
    """把 registry 中的 Pydantic 模型导出为 JSON Schema 文件。"""

    schema_dir = Path(output_dir)
    schema_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[SchemaArtifact] = []
    for name, model in iter_schema_models():
        source_model = f"{model.__module__}.{model.__qualname__}"
        schema = model.model_json_schema()
        _augment_exported_schema(schema, model)
        schema["x-contract-version"] = version
        schema["x-source-model"] = source_model

        schema_path = schema_dir / f"{name}.schema.json"
        schema_path.write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifacts.append(
            SchemaArtifact(
                name=name,
                source_model=source_model,
                version=version,
                output_path=str(schema_path),
            )
        )

    manifest = {
        "artifact_type": "json_schema",
        "version": version,
        "artifacts": [artifact.model_dump() for artifact in artifacts],
    }
    (schema_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return tuple(artifacts)


def _augment_exported_schema(
    schema: dict[str, object],
    model: type[ContractBaseModel],
) -> None:
    """Add contract validation metadata not emitted by Pydantic JSON Schema."""

    _annotate_runtime_validation(schema, model)
    for node in _walk_schema_nodes(schema):
        title = node.get("title")
        if title == "ResolutionCase":
            _add_all_of_rules(node, _RESOLUTION_CASE_RULES)
        if title == "ReasonerResult":
            _add_all_of_rules(node, _REASONER_RESULT_RULES)
        if title == "ReasonerHealth":
            _add_all_of_rules(node, _REASONER_HEALTH_RULES)
        if title == "ReasonerErrorClassification":
            _add_all_of_rules(node, _REASONER_ERROR_CLASSIFICATION_RULES)
        if isinstance(title, str) and title in _RUNTIME_INVARIANTS_BY_TITLE:
            node["x-contract-runtime-invariants"] = list(
                _RUNTIME_INVARIANTS_BY_TITLE[title]
            )


def _annotate_runtime_validation(
    schema: dict[str, object],
    model: type[ContractBaseModel],
) -> None:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return

    for field_name, field_info in model.model_fields.items():
        property_schema = properties.get(field_name)
        if not isinstance(property_schema, dict):
            continue

        runtime_validation: dict[str, object] = {}
        for metadata in field_info.metadata:
            strict = getattr(metadata, "strict", None)
            if strict is not None:
                runtime_validation["strict"] = strict

            allow_inf_nan = getattr(metadata, "allow_inf_nan", None)
            if allow_inf_nan is not None:
                runtime_validation["allow_inf_nan"] = allow_inf_nan

        if runtime_validation:
            property_schema["x-contract-runtime-validation"] = runtime_validation


def _walk_schema_nodes(schema: dict[str, object]) -> Iterator[dict[str, object]]:
    seen_ids: set[int] = set()
    stack: list[object] = [schema]

    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            value_id = id(value)
            if value_id in seen_ids:
                continue
            seen_ids.add(value_id)
            yield value
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)


def _add_all_of_rules(
    schema: dict[str, object],
    rules: tuple[dict[str, object], ...],
) -> None:
    all_of = schema.setdefault("allOf", [])
    if not isinstance(all_of, list):
        return

    for rule in rules:
        if rule not in all_of:
            all_of.append(rule)


__all__ = [
    "SchemaArtifact",
    "SCHEMA_MODEL_REGISTRY",
    "iter_schema_models",
    "export_json_schemas",
]
