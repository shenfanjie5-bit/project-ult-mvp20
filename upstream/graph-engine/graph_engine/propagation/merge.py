"""Merge explainable propagation results across channels."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from graph_engine.models import PropagationResult

_ALLOWED_CHANNELS = frozenset({"fundamental", "event", "reflexive"})
_REQUIRED_EXPLANATION_KEYS = frozenset(
    {
        "relation_weight",
        "evidence_confidence",
        "channel_multiplier",
        "regime_multiplier",
        "recency_decay",
        "score",
    }
)


def merge_propagation_results(
    results: Sequence[PropagationResult],
    *,
    result_limit: int = 100,
) -> PropagationResult:
    """Return one deterministic, auditable result from channel-specific results."""

    if not results:
        raise ValueError("results must not be empty")
    if result_limit < 1:
        raise ValueError("result_limit must be greater than zero")

    cycle_id = results[0].cycle_id
    graph_generation_id = results[0].graph_generation_id
    for result in results:
        if result.cycle_id != cycle_id:
            raise ValueError("cannot merge propagation results from different cycle_id values")
        if result.graph_generation_id != graph_generation_id:
            raise ValueError(
                "cannot merge propagation results from different graph_generation_id values"
            )

    all_paths: list[dict[str, Any]] = []
    channel_breakdown: dict[str, Any] = {}
    enabled_channels: set[str] = set()
    entity_path_counts = _entity_path_counts(results)

    for result in results:
        result_channels = _result_channels(result)
        enabled_channels.update(result_channels)
        for channel in result_channels:
            if channel not in result.channel_breakdown:
                raise ValueError(f"channel_breakdown is missing channel {channel!r}")
            channel_breakdown[channel] = result.channel_breakdown[channel]

        for path in result.activated_paths:
            _validate_path(path)
            all_paths.append(dict(path))

    activated_paths = sorted(all_paths, key=_path_sort_key)[:result_limit]
    impacted_entities = _merge_impacted_entities(
        results,
        entity_path_counts=entity_path_counts,
        result_limit=result_limit,
    )

    channel_breakdown["merged"] = {
        "enabled_channels": sorted(enabled_channels),
        "path_count": len(activated_paths),
        "impacted_entity_count": len(impacted_entities),
        "total_path_score": sum(_float_value(path.get("score")) for path in activated_paths),
        "result_limit": result_limit,
    }

    return PropagationResult(
        cycle_id=cycle_id,
        graph_generation_id=graph_generation_id,
        activated_paths=activated_paths,
        impacted_entities=impacted_entities,
        channel_breakdown=channel_breakdown,
    )


def _result_channels(result: PropagationResult) -> set[str]:
    channels: set[str] = set()
    for path in result.activated_paths:
        channels.add(_payload_channel(path, "activated path"))
    for entity in result.impacted_entities:
        channels.add(_payload_channel(entity, "impacted entity"))

    channels.update(
        str(channel)
        for channel in result.channel_breakdown
        if channel in _ALLOWED_CHANNELS
    )
    if not channels:
        raise ValueError("cannot determine propagation channel for result")
    return channels


def _validate_path(path: dict[str, Any]) -> None:
    _payload_channel(path, "activated path")
    explanation = path.get("explanation")
    if not isinstance(explanation, dict):
        raise ValueError("activated path explanation must be a mapping")
    missing_keys = sorted(_REQUIRED_EXPLANATION_KEYS - set(explanation))
    if missing_keys:
        raise ValueError(f"activated path explanation is missing keys: {missing_keys}")


def _payload_channel(payload: dict[str, Any], payload_name: str) -> str:
    channel = payload.get("channel")
    if not isinstance(channel, str) or not channel:
        raise ValueError(f"{payload_name} payload is missing channel")
    if channel not in _ALLOWED_CHANNELS:
        raise ValueError(f"{payload_name} payload has unknown channel {channel!r}")
    return channel


def _path_sort_key(path: dict[str, Any]) -> tuple[float, str, str, str, str, str]:
    return (
        -_float_value(path.get("score")),
        str(path.get("channel") or ""),
        str(path.get("source_node_id") or ""),
        str(path.get("relationship_type") or ""),
        str(path.get("target_node_id") or ""),
        str(path.get("edge_id") or ""),
    )


def _merge_impacted_entities(
    results: Sequence[PropagationResult],
    *,
    entity_path_counts: dict[tuple[str, str], int],
    result_limit: int,
) -> list[dict[str, Any]]:
    merged_by_key: dict[str, dict[str, Any]] = {}
    for result in results:
        for entity in result.impacted_entities:
            channel = _payload_channel(entity, "impacted entity")
            entity_key = _entity_key(
                canonical_entity_id=entity.get("canonical_entity_id"),
                node_id=entity.get("node_id"),
            )
            merged = merged_by_key.setdefault(
                entity_key,
                {
                    "canonical_entity_id": entity.get("canonical_entity_id"),
                    "node_id": entity.get("node_id"),
                    "labels": [],
                    "score": 0.0,
                    "channel_scores": {},
                    "channels": [],
                    "path_count": 0,
                },
            )
            _merge_identity(merged, entity)
            merged["labels"] = sorted(
                set(_string_list(merged.get("labels"))) | set(_string_list(entity.get("labels")))
            )

            channel_scores = dict(merged["channel_scores"])
            channel_scores[channel] = channel_scores.get(channel, 0.0) + _float_value(
                entity.get("score")
            )
            merged["channel_scores"] = channel_scores
            merged["channels"] = sorted(channel_scores)
            merged["score"] = sum(float(score) for score in channel_scores.values())
            merged["path_count"] = int(merged["path_count"]) + _entity_path_count(
                entity,
                entity_key=entity_key,
                channel=channel,
                entity_path_counts=entity_path_counts,
            )

    impacted_entities = list(merged_by_key.values())
    impacted_entities.sort(key=_entity_sort_key)
    return impacted_entities[:result_limit]


def _entity_path_counts(
    results: Sequence[PropagationResult],
) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for result in results:
        for path in result.activated_paths:
            channel = _payload_channel(path, "activated path")
            entity_key = _path_entity_key(
                canonical_entity_id=path.get("target_entity_id"),
                node_id=path.get("target_node_id"),
            )
            if entity_key is None:
                continue
            counts[(entity_key, channel)] = counts.get((entity_key, channel), 0) + 1
    return counts


def _entity_path_count(
    entity: dict[str, Any],
    *,
    entity_key: str,
    channel: str,
    entity_path_counts: dict[tuple[str, str], int],
) -> int:
    raw_path_count = entity.get("path_count")
    if raw_path_count is not None:
        return int(raw_path_count)
    return entity_path_counts.get((entity_key, channel), 0)


def _entity_key(*, canonical_entity_id: Any, node_id: Any) -> str:
    if canonical_entity_id is not None:
        canonical = str(canonical_entity_id)
        if canonical:
            return f"canonical:{canonical}"
    if node_id is not None:
        node = str(node_id)
        if node:
            return f"node:{node}"
    raise ValueError("impacted entity payload is missing canonical_entity_id and node_id")


def _path_entity_key(*, canonical_entity_id: Any, node_id: Any) -> str | None:
    if canonical_entity_id is None and node_id is None:
        return None
    return _entity_key(canonical_entity_id=canonical_entity_id, node_id=node_id)


def _merge_identity(merged: dict[str, Any], entity: dict[str, Any]) -> None:
    canonical_entity_id = entity.get("canonical_entity_id")
    if merged.get("canonical_entity_id") is None and canonical_entity_id is not None:
        merged["canonical_entity_id"] = canonical_entity_id

    node_id = entity.get("node_id")
    current_node_id = merged.get("node_id")
    if current_node_id is None:
        merged["node_id"] = node_id
    elif node_id is not None and str(node_id) < str(current_node_id):
        merged["node_id"] = node_id


def _entity_sort_key(entity: dict[str, Any]) -> tuple[float, str, str]:
    return (
        -_float_value(entity.get("score")),
        str(entity.get("canonical_entity_id") or ""),
        str(entity.get("node_id") or ""),
    )


def _float_value(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(str(item) for item in value)
