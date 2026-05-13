"""MVP20 read-side helpers for bounded context graph reads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from graph_engine.client import Neo4jClient
from graph_engine.models import GraphQueryResult
from graph_engine.query.service import query_subgraph
from graph_engine.status import GraphStatusManager

MVP20_GRAPH_DEPTH = 2
MVP20_DECISION_TARGET_COUNT = 20
MVP20_DECISION_TARGET_ROLE = "decision_target"
MVP20_CONTEXT_ONLY_ROLE = "context_only"
MVP20EntityRole = Literal["decision_target", "context_only"]


def query_mvp20_context_subgraph(
    seed_entities: list[str],
    *,
    decision_target_entities: Sequence[str],
    client: Neo4jClient,
    status_manager: GraphStatusManager,
    result_limit: int = 500,
) -> GraphQueryResult:
    """Return the MVP20 depth-2 read graph with context-only role annotations.

    This is a read helper over ``query_subgraph`` only. It does not enable
    default propagation, full propagation, writes, or relationship expansion
    beyond the bounded two-hop context read.
    """

    decision_targets = validate_mvp20_decision_targets(decision_target_entities)
    result = query_subgraph(
        seed_entities,
        MVP20_GRAPH_DEPTH,
        client=client,
        status_manager=status_manager,
        result_limit=result_limit,
        max_depth=MVP20_GRAPH_DEPTH,
    )
    annotated_nodes = annotate_mvp20_context_nodes(
        result.subgraph_nodes,
        decision_targets,
    )
    annotated_edges = annotate_mvp20_context_edges(
        result.subgraph_edges,
        decision_targets,
        node_roles_by_id=_node_roles_by_id(annotated_nodes),
    )
    return result.model_copy(
        update={
            "subgraph_nodes": annotated_nodes,
            "subgraph_edges": annotated_edges,
        }
    )


def validate_mvp20_decision_targets(
    decision_target_entities: Sequence[str],
) -> tuple[str, ...]:
    """Validate the MVP20 decision target universe as exactly 20 unique ids."""

    if isinstance(decision_target_entities, (str, bytes)) or not isinstance(
        decision_target_entities,
        Sequence,
    ):
        raise ValueError("decision_target_entities must be a sequence of strings")

    seen: set[str] = set()
    normalized: list[str] = []
    for entity in decision_target_entities:
        if not isinstance(entity, str):
            raise ValueError("decision_target_entities must contain strings")
        stripped = entity.strip()
        if not stripped:
            raise ValueError("decision_target_entities must contain non-empty ids")
        if stripped in seen:
            raise ValueError("decision_target_entities must contain unique ids")
        seen.add(stripped)
        normalized.append(stripped)

    if len(normalized) != MVP20_DECISION_TARGET_COUNT:
        raise ValueError(
            "MVP20 decision target universe must contain exactly "
            f"{MVP20_DECISION_TARGET_COUNT} unique ids",
        )
    return tuple(normalized)


def annotate_mvp20_context_nodes(
    nodes: Sequence[Mapping[str, Any]],
    decision_target_entities: Sequence[str],
) -> list[dict[str, Any]]:
    """Annotate query nodes as decision targets or context-only related entities."""

    decision_targets = frozenset(decision_target_entities)
    annotated: list[dict[str, Any]] = []
    for node in nodes:
        payload = dict(node)
        role = mvp20_entity_role(_entity_id_from_node(payload), decision_targets)
        payload["entity_role"] = role
        payload["metadata"] = _metadata_with_role(payload.get("metadata"), role)
        annotated.append(payload)
    return annotated


def annotate_mvp20_context_edges(
    edges: Sequence[Mapping[str, Any]],
    decision_target_entities: Sequence[str],
    *,
    node_roles_by_id: Mapping[str, MVP20EntityRole] | None = None,
) -> list[dict[str, Any]]:
    """Annotate edge endpoint roles without changing relationship semantics."""

    decision_targets = frozenset(decision_target_entities)
    node_roles = dict(node_roles_by_id or {})
    annotated: list[dict[str, Any]] = []
    for edge in edges:
        payload = dict(edge)
        source_id = _text_or_none(payload.get("source_node_id"))
        target_id = _text_or_none(payload.get("target_node_id"))
        source_role = node_roles.get(source_id or "") or mvp20_entity_role(
            source_id,
            decision_targets,
        )
        target_role = node_roles.get(target_id or "") or mvp20_entity_role(
            target_id,
            decision_targets,
        )
        payload["source_entity_role"] = source_role
        payload["target_entity_role"] = target_role
        metadata = payload.get("metadata")
        if not isinstance(metadata, Mapping):
            metadata = {}
        payload["metadata"] = {
            **dict(metadata),
            "mvp20_source_entity_role": source_role,
            "mvp20_target_entity_role": target_role,
        }
        annotated.append(payload)
    return annotated


def mvp20_entity_role(
    entity_id: str | None,
    decision_target_entities: Sequence[str],
) -> MVP20EntityRole:
    """Classify an entity id against the MVP20 decision target universe."""

    if entity_id is not None and entity_id in decision_target_entities:
        return MVP20_DECISION_TARGET_ROLE
    return MVP20_CONTEXT_ONLY_ROLE


def _entity_id_from_node(node: Mapping[str, Any]) -> str | None:
    for key in ("canonical_entity_id", "entity_id", "node_id"):
        text = _text_or_none(node.get(key))
        if text:
            return text
    return None


def _metadata_with_role(metadata: Any, role: MVP20EntityRole) -> dict[str, Any]:
    payload = dict(metadata) if isinstance(metadata, Mapping) else {}
    payload["mvp20_entity_role"] = role
    return payload


def _node_roles_by_id(nodes: Sequence[Mapping[str, Any]]) -> dict[str, MVP20EntityRole]:
    roles: dict[str, MVP20EntityRole] = {}
    for node in nodes:
        raw_role = node.get("entity_role")
        if raw_role == MVP20_DECISION_TARGET_ROLE:
            role: MVP20EntityRole = MVP20_DECISION_TARGET_ROLE
        elif raw_role == MVP20_CONTEXT_ONLY_ROLE:
            role = MVP20_CONTEXT_ONLY_ROLE
        else:
            continue
        for key in ("node_id", "canonical_entity_id", "entity_id"):
            node_id = _text_or_none(node.get(key))
            if node_id:
                roles[node_id] = role
    return roles


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
