"""Holdings-only propagation algorithms for graph-engine #55.

These algorithms are explicit entry points. They intentionally do not plug
into ``run_full_propagation`` so holdings signals are not double-counted by
the generic event/reflexive propagation channels.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from graph_engine.client import Neo4jClient
from graph_engine.evidence import evidence_refs_from_mapping
from graph_engine.models import PropagationContext, PropagationResult
from graph_engine.propagation.merge import merge_propagation_results
from graph_engine.propagation.scoring import build_score_explanation
from graph_engine.status import GraphStatusManager, hold_ready_read

_CO_HOLDING_CHANNEL = "reflexive"
_NORTHBOUND_CHANNEL = "event"
_CO_HOLDING_RELATIONSHIP = "CO_HOLDING"
_NORTHBOUND_RELATIONSHIP = "NORTHBOUND_HOLD"


@dataclass(frozen=True)
class HoldingsAlgorithmConfig:
    """Thresholds for holdings-only propagation algorithms."""

    min_holder_count: int = 2
    normalization_holder_count: int = 5
    crowding_threshold: float = 0.4
    northbound_z_threshold: float = 2.0

    def __post_init__(self) -> None:
        if self.min_holder_count < 1:
            raise ValueError("min_holder_count must be positive")
        if self.normalization_holder_count < 1:
            raise ValueError("normalization_holder_count must be positive")
        if not _is_finite_non_negative(self.crowding_threshold):
            raise ValueError("crowding_threshold must be finite and non-negative")
        if not _is_finite_non_negative(self.northbound_z_threshold):
            raise ValueError("northbound_z_threshold must be finite and non-negative")


def run_co_holding_crowding(
    context: PropagationContext,
    client: Neo4jClient,
    *,
    status_manager: GraphStatusManager,
    config: HoldingsAlgorithmConfig | None = None,
    result_limit: int = 100,
) -> PropagationResult:
    """Compute explicit co-holding crowding signals from ``CO_HOLDING`` edges."""

    algorithm_config = config or HoldingsAlgorithmConfig()
    if _CO_HOLDING_CHANNEL not in context.enabled_channels:
        raise PermissionError("co-holding crowding requires the reflexive channel")
    _validate_result_limit(result_limit)

    with hold_ready_read(status_manager, "holdings co-holding crowding") as ready_status:
        _validate_context_generation(context, ready_status.graph_generation_id)
        rows = _read_co_holding_rows(client, result_limit=result_limit)

    valid_paths: list[dict[str, Any]] = []
    diagnostics: dict[str, int] = {}
    for row in rows:
        path = _co_holding_path_from_row(context, row, algorithm_config, diagnostics)
        if path is not None:
            valid_paths.append(path)

    grouped_paths = _co_holding_paths_above_threshold(
        valid_paths,
        algorithm_config,
        diagnostics,
        result_limit=result_limit,
    )
    impacted_entities = _co_holding_impacted_entities(grouped_paths, result_limit=result_limit)

    return PropagationResult(
        cycle_id=context.cycle_id,
        graph_generation_id=context.graph_generation_id,
        activated_paths=grouped_paths,
        impacted_entities=impacted_entities,
        channel_breakdown={
            _CO_HOLDING_CHANNEL: {
                "co_holding_crowding": {
                    "relationship_type": _CO_HOLDING_RELATIONSHIP,
                    "path_count": len(grouped_paths),
                    "impacted_entity_count": len(impacted_entities),
                    "total_path_score": sum(float(path["score"]) for path in grouped_paths),
                    "min_holder_count": algorithm_config.min_holder_count,
                    "normalization_holder_count": algorithm_config.normalization_holder_count,
                    "crowding_threshold": algorithm_config.crowding_threshold,
                    "scanned_edge_count": len(rows),
                    "valid_edge_count": len(valid_paths),
                    "skipped_edge_count": sum(diagnostics.values()),
                    "diagnostics": dict(sorted(diagnostics.items())),
                },
            },
        },
    )


def run_northbound_anomaly(
    context: PropagationContext,
    client: Neo4jClient,
    *,
    status_manager: GraphStatusManager,
    config: HoldingsAlgorithmConfig | None = None,
    result_limit: int = 100,
) -> PropagationResult:
    """Compute explicit northbound anomaly signals from ``NORTHBOUND_HOLD`` edges."""

    algorithm_config = config or HoldingsAlgorithmConfig()
    if _NORTHBOUND_CHANNEL not in context.enabled_channels:
        raise PermissionError("northbound anomaly requires the event channel")
    _validate_result_limit(result_limit)

    with hold_ready_read(status_manager, "holdings northbound anomaly") as ready_status:
        _validate_context_generation(context, ready_status.graph_generation_id)
        rows = _read_northbound_rows(client, result_limit=result_limit)

    diagnostics: dict[str, int] = {}
    activated_paths = [
        path
        for row in rows
        if (
            path := _northbound_path_from_row(
                context,
                row,
                algorithm_config,
                diagnostics,
            )
        )
        is not None
    ]
    activated_paths.sort(key=_path_sort_key)
    activated_paths = activated_paths[:result_limit]
    impacted_entities = _impacted_entities_from_paths(
        activated_paths,
        channel=_NORTHBOUND_CHANNEL,
        result_limit=result_limit,
    )

    return PropagationResult(
        cycle_id=context.cycle_id,
        graph_generation_id=context.graph_generation_id,
        activated_paths=activated_paths,
        impacted_entities=impacted_entities,
        channel_breakdown={
            _NORTHBOUND_CHANNEL: {
                "northbound_anomaly": {
                    "relationship_type": _NORTHBOUND_RELATIONSHIP,
                    "path_count": len(activated_paths),
                    "impacted_entity_count": len(impacted_entities),
                    "total_path_score": sum(float(path["score"]) for path in activated_paths),
                    "northbound_z_threshold": algorithm_config.northbound_z_threshold,
                    "scanned_edge_count": len(rows),
                    "skipped_edge_count": sum(diagnostics.values()),
                    "diagnostics": dict(sorted(diagnostics.items())),
                },
            },
        },
    )


def run_holdings_algorithms(
    context: PropagationContext,
    client: Neo4jClient,
    *,
    status_manager: GraphStatusManager,
    config: HoldingsAlgorithmConfig | None = None,
    result_limit: int = 100,
) -> PropagationResult:
    """Run enabled holdings algorithms and merge their explicit results."""

    if (
        _CO_HOLDING_CHANNEL not in context.enabled_channels
        and _NORTHBOUND_CHANNEL not in context.enabled_channels
    ):
        raise PermissionError("holdings algorithms require event or reflexive channel")

    results: list[PropagationResult] = []
    if _CO_HOLDING_CHANNEL in context.enabled_channels:
        results.append(
            run_co_holding_crowding(
                context,
                client,
                status_manager=status_manager,
                config=config,
                result_limit=result_limit,
            )
        )
    if _NORTHBOUND_CHANNEL in context.enabled_channels:
        results.append(
            run_northbound_anomaly(
                context,
                client,
                status_manager=status_manager,
                config=config,
                result_limit=result_limit,
            )
        )

    if len(results) == 1:
        return results[0]
    return merge_propagation_results(results, result_limit=result_limit)


def _read_co_holding_rows(
    client: Neo4jClient,
    *,
    result_limit: int,
) -> list[dict[str, Any]]:
    return client.execute_read(
        """
MATCH (source)-[relationship:CO_HOLDING]->(target)
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
       relationship.properties_json AS properties_json,
       relationship.weight AS weight,
       relationship.evidence_confidence AS evidence_confidence,
       relationship.recency_decay AS recency_decay,
       relationship.co_holding_fund_count AS co_holding_fund_count,
       relationship.security_left_fund_count AS security_left_fund_count,
       relationship.security_right_fund_count AS security_right_fund_count,
       relationship.jaccard_score AS jaccard_score,
       relationship.report_date AS report_date,
       relationship.latest_announced_date AS latest_announced_date,
       source.canonical_id_rule_version AS source_canonical_id_rule_version,
       target.canonical_id_rule_version AS target_canonical_id_rule_version
ORDER BY target_node_id ASC,
         coalesce(relationship.co_holding_fund_count, 0) DESC,
         coalesce(relationship.jaccard_score, relationship.weight, 0.0) DESC,
         source_node_id ASC,
         edge_id ASC
LIMIT $scan_limit
""",
        {"scan_limit": _scan_limit(result_limit)},
    )


def _read_northbound_rows(
    client: Neo4jClient,
    *,
    result_limit: int,
) -> list[dict[str, Any]]:
    return client.execute_read(
        """
MATCH (source)-[relationship:NORTHBOUND_HOLD]->(target)
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
       relationship.properties_json AS properties_json,
       relationship.weight AS weight,
       relationship.evidence_confidence AS evidence_confidence,
       relationship.recency_decay AS recency_decay,
       relationship.metric_z_score AS metric_z_score,
       relationship.northbound_z_score AS northbound_z_score,
       relationship.z_score AS z_score,
       relationship.z_score_metric AS z_score_metric,
       relationship.lookback_observations AS lookback_observations,
       relationship.window_start_date AS window_start_date,
       relationship.window_end_date AS window_end_date,
       relationship.observation_count AS observation_count,
       relationship.metric_value AS metric_value,
       relationship.metric_mean AS metric_mean,
       relationship.metric_stddev AS metric_stddev,
       relationship.report_date AS report_date,
       source.canonical_id_rule_version AS source_canonical_id_rule_version,
       target.canonical_id_rule_version AS target_canonical_id_rule_version
ORDER BY abs(coalesce(
             relationship.metric_z_score,
             relationship.northbound_z_score,
             relationship.z_score,
             0.0
         )) DESC,
         target_node_id ASC,
         edge_id ASC
LIMIT $scan_limit
""",
        {"scan_limit": _scan_limit(result_limit)},
    )


def _co_holding_path_from_row(
    context: PropagationContext,
    row: Mapping[str, Any],
    config: HoldingsAlgorithmConfig,
    diagnostics: dict[str, int],
) -> dict[str, Any] | None:
    evidence_refs = _evidence_refs(row, diagnostics)
    if not evidence_refs:
        return None

    holder_count = _int_value(row.get("co_holding_fund_count"))
    if holder_count is None:
        _increment(diagnostics, "missing_holder_count")
        return None
    if holder_count < config.min_holder_count:
        _increment(diagnostics, "holder_count_below_minimum")
        return None

    relation_weight = _co_holding_relation_weight(row, diagnostics)
    evidence_confidence = _bounded_float(row.get("evidence_confidence"), default=1.0)
    recency_decay = _bounded_float(row.get("recency_decay"), default=1.0)
    if relation_weight is None or evidence_confidence is None or recency_decay is None:
        _increment(diagnostics, "invalid_scoring_field")
        return None

    explanation = build_score_explanation(
        relation_weight=relation_weight,
        evidence_confidence=evidence_confidence,
        channel_multiplier=_context_multiplier(context, _CO_HOLDING_CHANNEL),
        regime_multiplier=_context_regime_multiplier(context, _CO_HOLDING_CHANNEL),
        recency_decay=recency_decay,
    )

    return {
        "channel": _CO_HOLDING_CHANNEL,
        "algorithm": "co_holding_crowding",
        "source_node_id": row.get("source_node_id"),
        "source_entity_id": row.get("source_entity_id"),
        "source_labels": _string_list(row.get("source_labels")),
        "target_node_id": row.get("target_node_id"),
        "target_entity_id": row.get("target_entity_id"),
        "target_labels": _string_list(row.get("target_labels")),
        "edge_id": row.get("edge_id"),
        "relationship_type": row.get("relationship_type") or _CO_HOLDING_RELATIONSHIP,
        "evidence_refs": evidence_refs,
        "source_canonical_id_rule_version": row.get("source_canonical_id_rule_version"),
        "target_canonical_id_rule_version": row.get("target_canonical_id_rule_version"),
        "co_holding_fund_count": holder_count,
        "security_left_fund_count": _int_value(row.get("security_left_fund_count")),
        "security_right_fund_count": _int_value(row.get("security_right_fund_count")),
        "jaccard_score": _optional_float(row.get("jaccard_score")),
        "report_date": row.get("report_date"),
        "latest_announced_date": row.get("latest_announced_date"),
        "lineage": _lineage_from_row(row),
        "score": explanation["score"],
        "explanation": explanation,
    }


def _co_holding_relation_weight(
    row: Mapping[str, Any],
    diagnostics: dict[str, int],
) -> float | None:
    raw_jaccard = row.get("jaccard_score")
    if raw_jaccard is not None:
        jaccard = _optional_float(raw_jaccard)
        if jaccard is None or jaccard < 0.0:
            _increment(diagnostics, "invalid_jaccard_score")
            return None
        return min(jaccard, 1.0)

    properties = _properties_from_row(row)
    if properties is None or "weight" not in properties:
        _increment(diagnostics, "missing_explicit_weight")
        return None

    weight = _optional_float(properties.get("weight"))
    if weight is None or weight < 0.0:
        _increment(diagnostics, "invalid_explicit_weight")
        return None
    return min(weight, 1.0)


def _co_holding_paths_above_threshold(
    paths: list[dict[str, Any]],
    config: HoldingsAlgorithmConfig,
    diagnostics: dict[str, int],
    *,
    result_limit: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for path in paths:
        target_key = str(path.get("target_node_id") or "")
        if not target_key:
            _increment(diagnostics, "missing_target_node")
            continue
        grouped.setdefault(target_key, []).append(path)

    activated_paths: list[dict[str, Any]] = []
    for target_paths in grouped.values():
        total_strength = sum(float(path["score"]) for path in target_paths)
        crowding_score = min(1.0, total_strength / config.normalization_holder_count)
        if crowding_score < config.crowding_threshold:
            _increment_by(
                diagnostics,
                "crowding_score_below_threshold",
                len(target_paths),
            )
            continue

        target_holder_count = sum(
            int(path.get("co_holding_fund_count") or 0)
            for path in target_paths
        )
        for path in target_paths:
            activated = dict(path)
            activated["crowding_score"] = crowding_score
            activated["target_holder_count"] = target_holder_count
            activated_paths.append(activated)

    activated_paths.sort(key=_path_sort_key)
    return activated_paths[:result_limit]


def _co_holding_impacted_entities(
    paths: list[dict[str, Any]],
    *,
    result_limit: int,
) -> list[dict[str, Any]]:
    impacted = _impacted_entities_from_paths(
        paths,
        channel=_CO_HOLDING_CHANNEL,
        result_limit=result_limit,
        score_key="crowding_score",
    )
    for entity in impacted:
        entity_paths = [
            path
            for path in paths
            if str(path.get("target_node_id") or "") == str(entity.get("node_id") or "")
        ]
        entity["algorithm"] = "co_holding_crowding"
        entity["holder_count"] = max(
            (int(path.get("target_holder_count") or 0) for path in entity_paths),
            default=0,
        )
    return impacted


def _northbound_path_from_row(
    context: PropagationContext,
    row: Mapping[str, Any],
    config: HoldingsAlgorithmConfig,
    diagnostics: dict[str, int],
) -> dict[str, Any] | None:
    evidence_refs = _evidence_refs(row, diagnostics)
    if not evidence_refs:
        return None

    z_score = _first_float(row, ("metric_z_score", "northbound_z_score", "z_score"))
    if z_score is None:
        _increment(diagnostics, "missing_z_score")
        return None
    if abs(z_score) < config.northbound_z_threshold:
        _increment(diagnostics, "z_score_below_threshold")
        return None

    evidence_confidence = _bounded_float(row.get("evidence_confidence"), default=1.0)
    recency_decay = _bounded_float(row.get("recency_decay"), default=1.0)
    if evidence_confidence is None or recency_decay is None:
        _increment(diagnostics, "invalid_scoring_field")
        return None

    explanation = build_score_explanation(
        relation_weight=abs(z_score),
        evidence_confidence=evidence_confidence,
        channel_multiplier=_context_multiplier(context, _NORTHBOUND_CHANNEL),
        regime_multiplier=_context_regime_multiplier(context, _NORTHBOUND_CHANNEL),
        recency_decay=recency_decay,
    )

    return {
        "channel": _NORTHBOUND_CHANNEL,
        "algorithm": "northbound_anomaly",
        "source_node_id": row.get("source_node_id"),
        "source_entity_id": row.get("source_entity_id"),
        "source_labels": _string_list(row.get("source_labels")),
        "target_node_id": row.get("target_node_id"),
        "target_entity_id": row.get("target_entity_id"),
        "target_labels": _string_list(row.get("target_labels")),
        "edge_id": row.get("edge_id"),
        "relationship_type": row.get("relationship_type") or _NORTHBOUND_RELATIONSHIP,
        "evidence_refs": evidence_refs,
        "source_canonical_id_rule_version": row.get("source_canonical_id_rule_version"),
        "target_canonical_id_rule_version": row.get("target_canonical_id_rule_version"),
        "direction": "inflow" if z_score > 0 else "outflow",
        "z_score": z_score,
        "z_score_metric": row.get("z_score_metric"),
        "lookback_observations": _int_value(row.get("lookback_observations")),
        "window_start_date": row.get("window_start_date"),
        "window_end_date": row.get("window_end_date"),
        "observation_count": _int_value(row.get("observation_count")),
        "metric_value": _optional_float(row.get("metric_value")),
        "metric_mean": _optional_float(row.get("metric_mean")),
        "metric_stddev": _optional_float(row.get("metric_stddev")),
        "report_date": row.get("report_date"),
        "lineage": _lineage_from_row(row),
        "score": explanation["score"],
        "explanation": explanation,
    }


def _impacted_entities_from_paths(
    paths: list[dict[str, Any]],
    *,
    channel: str,
    result_limit: int,
    score_key: str = "score",
) -> list[dict[str, Any]]:
    impacted_by_node_id: dict[str, dict[str, Any]] = {}
    for path in paths:
        target_node_id = path.get("target_node_id")
        if target_node_id is None:
            continue
        node_id = str(target_node_id)
        impact = impacted_by_node_id.setdefault(
            node_id,
            {
                "channel": channel,
                "node_id": target_node_id,
                "canonical_entity_id": path.get("target_entity_id"),
                "labels": _string_list(path.get("target_labels")),
                "score": 0.0,
                "stable_node_id": node_id,
                "path_count": 0,
            },
        )
        impact["score"] = max(
            float(impact["score"]),
            _optional_float(path.get(score_key)) or 0.0,
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


def _lineage_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    properties = _properties_from_row(row)
    if properties is None:
        return {}
    lineage = properties.get("lineage")
    if isinstance(lineage, Mapping):
        return dict(lineage)
    return {}


def _properties_from_row(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    properties_json = row.get("properties_json")
    if not isinstance(properties_json, str) or not properties_json:
        return None
    try:
        properties = json.loads(properties_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(properties, Mapping):
        return None
    return properties


def _evidence_refs(row: Mapping[str, Any], diagnostics: dict[str, int]) -> list[str]:
    try:
        refs = evidence_refs_from_mapping(row)
    except ValueError:
        _increment(diagnostics, "invalid_evidence_refs")
        return []
    if not refs:
        _increment(diagnostics, "missing_evidence_refs")
        return []
    return refs


def _first_float(
    row: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    default: float | None = None,
) -> float | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        return _optional_float(value)
    return default


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _bounded_float(value: Any, *, default: float) -> float | None:
    number = _optional_float(value)
    if number is None:
        number = default
    if number < 0.0:
        return None
    return number


def _int_value(value: Any) -> int | None:
    number = _optional_float(value)
    if number is None:
        return None
    return int(number)


def _context_multiplier(context: PropagationContext, channel: str) -> float:
    return float(context.channel_multipliers.get(channel, 1.0))


def _context_regime_multiplier(context: PropagationContext, channel: str) -> float:
    return float(context.regime_multipliers.get(channel, 1.0))


def _path_sort_key(path: Mapping[str, Any]) -> tuple[float, str, str, str, str, str]:
    return (
        -float(path.get("score") or 0.0),
        str(path.get("channel") or ""),
        str(path.get("source_node_id") or ""),
        str(path.get("relationship_type") or ""),
        str(path.get("target_node_id") or ""),
        str(path.get("edge_id") or ""),
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(str(item) for item in value)


def _scan_limit(result_limit: int) -> int:
    return max(result_limit * 20, 100)


def _validate_result_limit(result_limit: int) -> None:
    if result_limit < 1:
        raise ValueError("result_limit must be greater than zero")


def _validate_context_generation(
    context: PropagationContext,
    graph_generation_id: int,
) -> None:
    if graph_generation_id != context.graph_generation_id:
        raise ValueError(
            "PropagationContext graph_generation_id disagrees with Neo4jGraphStatus: "
            f"context={context.graph_generation_id}, status={graph_generation_id}",
        )


def _increment(diagnostics: dict[str, int], key: str) -> None:
    diagnostics[key] = diagnostics.get(key, 0) + 1


def _increment_by(diagnostics: dict[str, int], key: str, amount: int) -> None:
    diagnostics[key] = diagnostics.get(key, 0) + amount


def _is_finite_non_negative(value: float) -> bool:
    return math.isfinite(value) and value >= 0.0
