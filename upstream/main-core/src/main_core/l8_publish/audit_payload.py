"""Audit and retrospective payload builders for L8 publication."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from main_core.common.types import CycleId
from main_core.l8_publish.publish_port import (
    CommittedFormalObject,
    ManifestWriteResult,
)
from main_core.l8_publish.refs import (
    ALPHA_RESULT_SNAPSHOT_KEY,
    OFFICIAL_ALPHA_POOL_KEY,
    RECOMMENDATION_SNAPSHOT_KEY,
    WORLD_STATE_SNAPSHOT_KEY,
)


def build_audit_payload(
    cycle_id: CycleId,
    formal_objects: Mapping[str, Any],
    committed_objects: Sequence[CommittedFormalObject],
    manifest: ManifestWriteResult,
) -> dict[str, Any]:
    """Build the publication audit payload from committed formal objects."""

    alpha_results = _payload_list(formal_objects, ALPHA_RESULT_SNAPSHOT_KEY)
    recommendations = _payload_list(formal_objects, RECOMMENDATION_SNAPSHOT_KEY)

    alpha_inconclusive_count = sum(
        1
        for alpha_result in alpha_results
        if alpha_result.get("status") == "inconclusive"
    )
    recommendation_inconclusive_count = sum(
        1
        for recommendation in recommendations
        if recommendation.get("action_type") == "inconclusive"
    )
    return {
        "cycle_id": str(cycle_id),
        "object_counts": _object_counts(formal_objects),
        "commit_refs": _commit_refs(committed_objects),
        "manifest_ref": manifest.manifest_ref,
        "manifest_version": manifest.manifest_version,
        # Backwards-compatible field: equal to alpha_inconclusive_count.
        "inconclusive_count": alpha_inconclusive_count,
        "alpha_inconclusive_count": alpha_inconclusive_count,
        "recommendation_inconclusive_count": recommendation_inconclusive_count,
        "override_applied_count": sum(
            1
            for recommendation in recommendations
            if recommendation.get("override_applied") is True
        ),
        "selected_entity_ids": _selected_entity_ids(formal_objects),
        "recommendation_entity_ids": _recommendation_entity_ids(formal_objects),
    }


def build_retrospective_seed(
    cycle_id: CycleId,
    formal_objects: Mapping[str, Any],
    committed_objects: Sequence[CommittedFormalObject],
) -> dict[str, Any]:
    """Build the retrospective seed carried by the publish bundle."""

    commit_refs = _commit_refs(committed_objects)
    return {
        "cycle_id": str(cycle_id),
        "world_state_ref": commit_refs.get(WORLD_STATE_SNAPSHOT_KEY),
        "pool_ref": commit_refs.get(OFFICIAL_ALPHA_POOL_KEY),
        "recommendation_ref": commit_refs.get(RECOMMENDATION_SNAPSHOT_KEY),
        "selected_entity_ids": _selected_entity_ids(formal_objects),
        "recommendation_entity_ids": _recommendation_entity_ids(formal_objects),
    }


def _object_counts(formal_objects: Mapping[str, Any]) -> dict[str, int]:
    return {
        object_key: _entry_count(entry)
        for object_key, entry in formal_objects.items()
    }


def _commit_refs(committed_objects: Sequence[CommittedFormalObject]) -> dict[str, str]:
    return {
        committed.object_key: committed.ref
        for committed in committed_objects
    }


def _selected_entity_ids(formal_objects: Mapping[str, Any]) -> list[str]:
    payload = _payload_mapping(formal_objects, OFFICIAL_ALPHA_POOL_KEY)
    selected_entities = payload.get("selected_entities", [])
    if not isinstance(selected_entities, Sequence) or isinstance(
        selected_entities,
        (str, bytes),
    ):
        return []
    return [str(entity_id) for entity_id in selected_entities]


def _recommendation_entity_ids(formal_objects: Mapping[str, Any]) -> list[str]:
    return [
        str(recommendation["entity_id"])
        for recommendation in _payload_list(formal_objects, RECOMMENDATION_SNAPSHOT_KEY)
        if "entity_id" in recommendation
    ]


def _payload_mapping(formal_objects: Mapping[str, Any], object_key: str) -> Mapping[str, Any]:
    entry = formal_objects.get(object_key, {})
    if not isinstance(entry, Mapping):
        return {}
    payload = entry.get("payload", {})
    if isinstance(payload, Mapping):
        return payload
    return {}


def _payload_list(formal_objects: Mapping[str, Any], object_key: str) -> list[Mapping[str, Any]]:
    entry = formal_objects.get(object_key, {})
    if not isinstance(entry, Mapping):
        return []
    payload = entry.get("payload", [])
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        return []
    return [
        item
        for item in payload
        if isinstance(item, Mapping)
    ]


def _entry_count(entry: Any) -> int:
    if isinstance(entry, Mapping) and isinstance(entry.get("count"), int):
        return entry["count"]
    return 0


__all__ = ["build_audit_payload", "build_retrospective_seed"]
