"""Reflexive propagation over reflexive-tagged relationships."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from graph_engine.client import Neo4jClient
from graph_engine.evidence import evidence_refs_from_mapping
from graph_engine.models import PropagationContext, PropagationResult
from graph_engine.propagation._gds import (
    drop_projection_if_exists,
    execute_gds_read,
    execute_gds_write,
)
from graph_engine.propagation.channels import (
    effective_channel_selector,
    relationship_types_for_channel,
)
from graph_engine.propagation.scoring import build_score_explanation
from graph_engine.status import GraphStatusManager, hold_ready_read

_REFLEXIVE_CHANNEL = "reflexive"
REFLEXIVE_RELATIONSHIP_TYPES = relationship_types_for_channel(_REFLEXIVE_CHANNEL)
_REFLEXIVE_PATH_SELECTOR = effective_channel_selector(_REFLEXIVE_CHANNEL)


def run_reflexive_propagation(
    context: PropagationContext,
    client: Neo4jClient,
    *,
    status_manager: GraphStatusManager,
    graph_name: str | None = None,
    max_iterations: int = 20,
    result_limit: int = 100,
) -> PropagationResult:
    """Run weighted PageRank for reflexive-tagged relationships."""

    if _REFLEXIVE_CHANNEL not in context.enabled_channels:
        raise PermissionError("reflexive propagation requires the reflexive channel")
    if max_iterations < 1:
        raise ValueError("max_iterations must be greater than zero")
    if result_limit < 1:
        raise ValueError("result_limit must be greater than zero")

    with hold_ready_read(status_manager, "reflexive propagation") as ready_status:
        if ready_status.graph_generation_id != context.graph_generation_id:
            raise ValueError(
                "PropagationContext graph_generation_id disagrees with Neo4jGraphStatus: "
                f"context={context.graph_generation_id}, "
                f"status={ready_status.graph_generation_id}",
            )

        projection_name = graph_name or _default_projection_name(context)
        drop_projection_if_exists(client, projection_name)
        try:
            relationship_count = _create_projection(client, projection_name)
            if relationship_count == 0:
                pagerank_entities: list[dict[str, Any]] = []
                activated_paths: list[dict[str, Any]] = []
            else:
                pagerank_entities = _stream_pagerank(
                    client,
                    projection_name,
                    max_iterations=max_iterations,
                    result_limit=result_limit,
                )
                activated_paths = _read_activated_paths(
                    context,
                    client,
                    result_limit=result_limit,
                )
        finally:
            drop_projection_if_exists(client, projection_name)

    impacted_entities = _impacted_entities_from_paths(
        activated_paths,
        pagerank_entities,
        result_limit=result_limit,
    )
    channel_breakdown: dict[str, Any] = {
        _REFLEXIVE_CHANNEL: {
            "relationship_types": list(REFLEXIVE_RELATIONSHIP_TYPES),
            "path_selector": _REFLEXIVE_PATH_SELECTOR,
            "path_count": len(activated_paths),
            "impacted_entity_count": len(impacted_entities),
            "total_path_score": sum(float(path["score"]) for path in activated_paths),
            "channel_multiplier": _context_multiplier(context.channel_multipliers),
            "regime_multiplier": _context_multiplier(context.regime_multipliers),
        },
    }
    return PropagationResult(
        cycle_id=context.cycle_id,
        graph_generation_id=context.graph_generation_id,
        activated_paths=activated_paths,
        impacted_entities=impacted_entities,
        channel_breakdown=channel_breakdown,
    )


def _default_projection_name(context: PropagationContext) -> str:
    cycle_component = re.sub(r"[^A-Za-z0-9_]", "_", context.cycle_id).strip("_")
    cycle_component = (cycle_component or "cycle")[:64]
    return f"graph_engine_reflexive_{cycle_component}_{uuid4().hex[:8]}"


def _create_projection(client: Neo4jClient, graph_name: str) -> int:
    rows = execute_gds_write(
        client,
        f"""
MATCH (source)-[relationship]->(target)
WHERE {_REFLEXIVE_PATH_SELECTOR}
WITH gds.graph.project(
    $graph_name,
    source,
    target,
    {{
        relationshipType: type(relationship),
        relationshipProperties: {{
            weight: coalesce(relationship.weight, 1.0)
        }}
    }}
) AS projection
RETURN projection.graphName AS graphName,
       projection.nodeCount AS nodeCount,
       projection.relationshipCount AS relationshipCount
""",
        {"graph_name": graph_name},
    )
    if not rows:
        return 0
    return int(rows[0].get("relationshipCount") or 0)


def _stream_pagerank(
    client: Neo4jClient,
    graph_name: str,
    *,
    max_iterations: int,
    result_limit: int,
) -> list[dict[str, Any]]:
    rows = execute_gds_read(
        client,
        """
CALL gds.pageRank.stream($graph_name, {
    maxIterations: $max_iterations,
    relationshipWeightProperty: "weight"
})
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS node, score
WITH node,
     score,
     coalesce(node.node_id, elementId(node)) AS stable_node_id
RETURN node.node_id AS node_id,
       node.canonical_entity_id AS canonical_entity_id,
       labels(node) AS labels,
       stable_node_id,
       score
ORDER BY score DESC, stable_node_id ASC
LIMIT $result_limit
""",
        {
            "graph_name": graph_name,
            "max_iterations": max_iterations,
            "result_limit": result_limit,
        },
    )
    impacted_entities = [_pagerank_entity(row) for row in rows]
    impacted_entities.sort(
        key=lambda entity: (-float(entity["score"]), str(entity["stable_node_id"])),
    )
    return impacted_entities[:result_limit]


def _read_activated_paths(
    context: PropagationContext,
    client: Neo4jClient,
    *,
    result_limit: int,
) -> list[dict[str, Any]]:
    channel_multiplier = _context_multiplier(context.channel_multipliers)
    regime_multiplier = _context_multiplier(context.regime_multipliers)
    rows = client.execute_read(
        f"""
MATCH (source)-[relationship]->(target)
WHERE {_REFLEXIVE_PATH_SELECTOR}
WITH source,
     relationship,
     target,
     coalesce(relationship.weight, 1.0) AS relation_weight,
     coalesce(relationship.evidence_confidence, 1.0) AS evidence_confidence,
     coalesce(relationship.recency_decay, 1.0) AS recency_decay
WITH source,
     relationship,
     target,
     relation_weight,
     evidence_confidence,
     recency_decay,
     relation_weight
         * evidence_confidence
         * $channel_multiplier
         * $regime_multiplier
         * recency_decay AS path_score
RETURN source.node_id AS source_node_id,
       source.canonical_entity_id AS source_entity_id,
       labels(source) AS source_labels,
       target.node_id AS target_node_id,
       target.canonical_entity_id AS target_entity_id,
       labels(target) AS target_labels,
       relationship.edge_id AS edge_id,
       type(relationship) AS relationship_type,
       relationship.evidence_refs AS evidence_refs,
       relationship.evidence_ref AS evidence_ref,
       source.canonical_id_rule_version AS source_canonical_id_rule_version,
       target.canonical_id_rule_version AS target_canonical_id_rule_version,
       relation_weight,
       evidence_confidence,
       recency_decay,
       path_score
ORDER BY path_score DESC,
         source_node_id ASC,
         relationship_type ASC,
         target_node_id ASC,
         edge_id ASC
LIMIT $result_limit
""",
        {
            "result_limit": result_limit,
            "channel_multiplier": channel_multiplier,
            "regime_multiplier": regime_multiplier,
        },
    )

    activated_paths = [
        _activated_path(row, channel_multiplier, regime_multiplier)
        for row in rows
    ]
    activated_paths.sort(
        key=lambda path: (
            -float(path["score"]),
            str(path["source_node_id"]),
            str(path["relationship_type"]),
            str(path["target_node_id"]),
            str(path["edge_id"]),
        ),
    )
    return activated_paths[:result_limit]


def _activated_path(
    row: dict[str, Any],
    channel_multiplier: float,
    regime_multiplier: float,
) -> dict[str, Any]:
    relation_weight = _float_value(row.get("relation_weight"), default=1.0)
    evidence_confidence = _float_value(row.get("evidence_confidence"), default=1.0)
    recency_decay = _float_value(row.get("recency_decay"), default=1.0)
    explanation = build_score_explanation(
        relation_weight=relation_weight,
        evidence_confidence=evidence_confidence,
        channel_multiplier=channel_multiplier,
        regime_multiplier=regime_multiplier,
        recency_decay=recency_decay,
    )

    return {
        "channel": _REFLEXIVE_CHANNEL,
        "source_node_id": row.get("source_node_id"),
        "source_entity_id": row.get("source_entity_id"),
        "source_labels": _string_list(row.get("source_labels")),
        "target_node_id": row.get("target_node_id"),
        "target_entity_id": row.get("target_entity_id"),
        "target_labels": _string_list(row.get("target_labels")),
        "edge_id": row.get("edge_id"),
        "relationship_type": row.get("relationship_type"),
        "evidence_refs": evidence_refs_from_mapping(row),
        "source_canonical_id_rule_version": row.get("source_canonical_id_rule_version"),
        "target_canonical_id_rule_version": row.get("target_canonical_id_rule_version"),
        "score": explanation["score"],
        "explanation": explanation,
    }


def _pagerank_entity(row: dict[str, Any]) -> dict[str, Any]:
    stable_node_id = str(row.get("stable_node_id") or row.get("node_id") or "")
    return {
        "channel": _REFLEXIVE_CHANNEL,
        "node_id": row.get("node_id"),
        "canonical_entity_id": row.get("canonical_entity_id"),
        "labels": _string_list(row.get("labels")),
        "score": _float_value(row.get("score"), default=0.0),
        "stable_node_id": stable_node_id,
    }


def _impacted_entities_from_paths(
    activated_paths: list[dict[str, Any]],
    pagerank_entities: list[dict[str, Any]],
    *,
    result_limit: int,
) -> list[dict[str, Any]]:
    pagerank_by_node_id = {
        str(entity.get("node_id")): _float_value(entity.get("score"), default=0.0)
        for entity in pagerank_entities
        if entity.get("node_id") is not None
    }
    impacted_by_node_id: dict[str, dict[str, Any]] = {}
    for path in activated_paths:
        target_node_id = path.get("target_node_id")
        if target_node_id is None:
            continue

        node_id = str(target_node_id)
        impact = impacted_by_node_id.setdefault(
            node_id,
            {
                "channel": _REFLEXIVE_CHANNEL,
                "node_id": target_node_id,
                "canonical_entity_id": path.get("target_entity_id"),
                "labels": _string_list(path.get("target_labels")),
                "score": 0.0,
                "stable_node_id": node_id,
                "pagerank_score": pagerank_by_node_id.get(node_id, 0.0),
                "path_count": 0,
            },
        )
        impact["score"] = float(impact["score"]) + _float_value(
            path.get("score"),
            default=0.0,
        )
        impact["path_count"] = int(impact["path_count"]) + 1

    impacted_entities = list(impacted_by_node_id.values())
    impacted_entities.sort(
        key=lambda entity: (
            -float(entity["score"]),
            str(entity["stable_node_id"]),
        ),
    )
    return impacted_entities[:result_limit]


def _context_multiplier(multipliers: dict[str, float]) -> float:
    return float(multipliers.get(_REFLEXIVE_CHANNEL, 1.0))


def _float_value(value: Any, *, default: float) -> float:
    if value is None:
        return default
    return float(value)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(str(item) for item in value)
