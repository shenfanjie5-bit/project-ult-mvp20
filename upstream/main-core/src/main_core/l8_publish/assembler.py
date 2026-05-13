"""L8 publish bundle assembly boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from main_core.common.errors import ManifestPublishError
from main_core.common.schemas import (
    AlphaResultSnapshot,
    FormalObjectBase,
    OfficialAlphaPool,
    PublishBundle,
    RecommendationSnapshot,
)
from main_core.common.types import CycleId
from main_core.l8_publish.audit_payload import (
    build_audit_payload,
    build_retrospective_seed,
)
from main_core.l8_publish.manifest import (
    build_manifest_candidate,
    commit_formal_objects,
    write_manifest_after_commits,
)
from main_core.l8_publish.publish_port import (
    CommittedFormalObject,
    DataPlatformPublishPort,
    DerivedFormalObjectBuilder,
    FormalObjectSource,
    FormalObjectValue,
)
from main_core.l8_publish.refs import (
    ALPHA_RESULT_SNAPSHOT_KEY,
    CANONICAL_FORMAL_OBJECT_KEYS,
    OFFICIAL_ALPHA_POOL_KEY,
    RECOMMENDATION_SNAPSHOT_KEY,
    WORLD_STATE_SNAPSHOT_KEY,
)
from main_core.l8_publish.report import build_dashboard_and_report

DEFAULT_DERIVED_BUILDERS: tuple[DerivedFormalObjectBuilder, ...] = (
    build_dashboard_and_report,
)


def collect_formal_objects(
    cycle_id: CycleId,
    source: FormalObjectSource,
) -> dict[str, FormalObjectValue]:
    """Load and validate formal objects already produced by L4-L7."""

    requested_cycle_id = CycleId(str(cycle_id))
    try:
        world_state = source.load_world_state(requested_cycle_id)
        pool = source.load_official_alpha_pool(requested_cycle_id)
        alpha_results = tuple(source.load_alpha_results(requested_cycle_id))
        recommendations = tuple(source.load_recommendations(requested_cycle_id))
    except ManifestPublishError:
        raise
    except Exception as exc:
        raise ManifestPublishError("failed to load formal objects for publish") from exc

    formal_objects: dict[str, FormalObjectValue] = {
        WORLD_STATE_SNAPSHOT_KEY: world_state,
        OFFICIAL_ALPHA_POOL_KEY: pool,
        ALPHA_RESULT_SNAPSHOT_KEY: alpha_results,
        RECOMMENDATION_SNAPSHOT_KEY: recommendations,
    }
    _validate_formal_object_cycles(requested_cycle_id, formal_objects)
    _validate_publish_consistency(
        pool=pool,
        alpha_results=alpha_results,
        recommendations=recommendations,
    )
    return formal_objects


def prepare_publish_bundle(
    cycle_id: CycleId,
    *,
    source: FormalObjectSource,
    publish_port: DataPlatformPublishPort,
    derived_builders: Sequence[DerivedFormalObjectBuilder] = DEFAULT_DERIVED_BUILDERS,
) -> PublishBundle:
    """Prepare, commit, manifest, and return the formal L8 publish bundle."""

    requested_cycle_id = CycleId(str(cycle_id))
    formal_objects = collect_formal_objects(requested_cycle_id, source)
    reserved_manifest_ref = (
        _reserve_cycle_manifest_ref(requested_cycle_id, publish_port)
        if derived_builders
        else None
    )
    formal_objects, committed_objects = _commit_with_derived_builders(
        cycle_id=requested_cycle_id,
        formal_objects=formal_objects,
        publish_port=publish_port,
        derived_builders=derived_builders,
        reserved_manifest_ref=reserved_manifest_ref,
    )

    manifest = write_manifest_after_commits(
        requested_cycle_id,
        committed_objects,
        publish_port,
        expected_manifest_ref=reserved_manifest_ref,
    )
    bundle_formal_objects = _build_bundle_formal_objects(
        formal_objects,
        committed_objects,
    )

    return PublishBundle(
        cycle_id=requested_cycle_id,
        formal_objects=bundle_formal_objects,
        manifest_candidate=build_manifest_candidate(
            requested_cycle_id,
            committed_objects,
            manifest,
        ),
        audit_payload=build_audit_payload(
            requested_cycle_id,
            bundle_formal_objects,
            committed_objects,
            manifest,
        ),
        retrospective_seed=build_retrospective_seed(
            requested_cycle_id,
            bundle_formal_objects,
            committed_objects,
        ),
    )


def _commit_with_derived_builders(
    *,
    cycle_id: CycleId,
    formal_objects: Mapping[str, FormalObjectValue],
    publish_port: DataPlatformPublishPort,
    derived_builders: Sequence[DerivedFormalObjectBuilder],
    reserved_manifest_ref: str | None,
) -> tuple[dict[str, FormalObjectValue], tuple[CommittedFormalObject, ...]]:
    active_formal_objects = dict(formal_objects)
    if not derived_builders:
        committed_objects = commit_formal_objects(
            cycle_id,
            active_formal_objects,
            publish_port,
        )
        return active_formal_objects, committed_objects

    committed_objects = list(
        commit_formal_objects(
            cycle_id,
            active_formal_objects,
            publish_port,
        )
    )
    for builder in derived_builders:
        bundle_formal_objects = _build_bundle_formal_objects(
            active_formal_objects,
            committed_objects,
        )
        manifest_candidate = build_manifest_candidate(cycle_id, committed_objects)
        if reserved_manifest_ref is not None:
            manifest_candidate["manifest_ref"] = reserved_manifest_ref
        draft_bundle = PublishBundle(
            cycle_id=cycle_id,
            formal_objects=bundle_formal_objects,
            manifest_candidate=manifest_candidate,
            audit_payload={
                "cycle_id": str(cycle_id),
                "audit_payload_ref": f"audit_payload/{cycle_id}",
            },
            retrospective_seed=build_retrospective_seed(
                cycle_id,
                bundle_formal_objects,
                committed_objects,
            ),
        )
        try:
            derived_objects = builder(cycle_id, draft_bundle)
        except ManifestPublishError:
            raise
        except Exception as exc:
            raise ManifestPublishError("failed to build derived formal objects") from exc

        for object_key, formal_object in derived_objects.items():
            if object_key in active_formal_objects:
                raise ManifestPublishError(
                    f"derived formal object duplicates key {object_key}",
                )
            if not isinstance(formal_object, FormalObjectBase):
                raise ManifestPublishError(
                    f"derived formal object {object_key} must be FormalObjectBase",
                )
            _ensure_cycle_id(object_key, formal_object, cycle_id)
            active_formal_objects[object_key] = formal_object

        committed_objects.extend(
            commit_formal_objects(cycle_id, derived_objects, publish_port)
        )

    return active_formal_objects, tuple(committed_objects)


def _reserve_cycle_manifest_ref(
    cycle_id: CycleId,
    publish_port: DataPlatformPublishPort,
) -> str:
    try:
        reserve_manifest_ref = publish_port.reserve_cycle_manifest_ref
    except AttributeError as exc:
        raise ManifestPublishError(
            "publish port must reserve manifest_ref before derived formal objects",
        ) from exc

    try:
        manifest_ref = reserve_manifest_ref(cycle_id=cycle_id)
    except ManifestPublishError:
        raise
    except Exception as exc:
        raise ManifestPublishError("failed to reserve cycle manifest_ref") from exc

    if not isinstance(manifest_ref, str) or not manifest_ref.strip():
        raise ManifestPublishError("reserved manifest_ref must be non-empty")
    return manifest_ref


def _validate_formal_object_cycles(
    cycle_id: CycleId,
    formal_objects: Mapping[str, FormalObjectValue],
) -> None:
    for object_key, value in formal_objects.items():
        if isinstance(value, FormalObjectBase):
            _ensure_cycle_id(object_key, value, cycle_id)
            continue
        for item in value:
            _ensure_cycle_id(object_key, item, cycle_id)


def _ensure_cycle_id(
    object_key: str,
    formal_object: FormalObjectBase,
    cycle_id: CycleId,
) -> None:
    object_cycle_id = getattr(formal_object, "cycle_id", None)
    if object_cycle_id != cycle_id:
        raise ManifestPublishError(
            f"{object_key}.cycle_id must match requested cycle_id",
        )


def _validate_publish_consistency(
    *,
    pool: OfficialAlphaPool,
    alpha_results: Sequence[AlphaResultSnapshot],
    recommendations: Sequence[RecommendationSnapshot],
) -> None:
    selected_entity_ids = {str(entity_id) for entity_id in pool.selected_entities}
    alpha_entity_ids = _unique_entity_ids(
        ALPHA_RESULT_SNAPSHOT_KEY,
        alpha_results,
    )
    missing_alpha_entity_ids = selected_entity_ids - alpha_entity_ids
    if missing_alpha_entity_ids:
        missing = ", ".join(sorted(missing_alpha_entity_ids))
        raise ManifestPublishError(
            f"missing alpha result for selected pool entities: {missing}",
        )
    extra_alpha_entity_ids = alpha_entity_ids - selected_entity_ids
    if extra_alpha_entity_ids:
        extra = ", ".join(sorted(extra_alpha_entity_ids))
        raise ManifestPublishError(
            "alpha result entity_id must belong to pool.selected_entities: "
            f"{extra}",
        )

    recommendation_entity_ids = _unique_entity_ids(
        RECOMMENDATION_SNAPSHOT_KEY,
        recommendations,
    )
    extra_recommendation_entity_ids = recommendation_entity_ids - selected_entity_ids
    if extra_recommendation_entity_ids:
        extra = ", ".join(sorted(extra_recommendation_entity_ids))
        raise ManifestPublishError(
            "recommendation entity_id must belong to pool.selected_entities: "
            f"{extra}",
        )

    missing_recommendation_entity_ids = selected_entity_ids - recommendation_entity_ids
    if missing_recommendation_entity_ids:
        missing = ", ".join(sorted(missing_recommendation_entity_ids))
        raise ManifestPublishError(
            "missing recommendation for selected pool entities: "
            f"{missing}",
        )


def _unique_entity_ids(
    object_key: str,
    formal_objects: Sequence[AlphaResultSnapshot | RecommendationSnapshot],
) -> set[str]:
    entity_ids: set[str] = set()
    for formal_object in formal_objects:
        entity_id = str(formal_object.entity_id)
        if entity_id in entity_ids:
            raise ManifestPublishError(f"duplicate {object_key} entity_id")
        entity_ids.add(entity_id)
    return entity_ids


def _build_bundle_formal_objects(
    formal_objects: Mapping[str, FormalObjectValue],
    committed_objects: Sequence[CommittedFormalObject],
) -> dict[str, dict[str, Any]]:
    committed_by_key = {
        committed.object_key: committed
        for committed in committed_objects
    }
    bundle_formal_objects: dict[str, dict[str, Any]] = {}
    for object_key in _ordered_object_keys(formal_objects):
        committed_object = committed_by_key.get(object_key)
        if committed_object is None:
            raise ManifestPublishError(f"missing commit result for {object_key}")
        bundle_formal_objects[object_key] = _bundle_formal_object_entry(
            formal_objects[object_key],
            committed_object.ref,
        )
    return bundle_formal_objects


def _bundle_formal_object_entry(
    value: FormalObjectValue,
    ref: str,
) -> dict[str, Any]:
    payload = _bundle_payload(value)
    return {
        "ref": ref,
        "payload": payload,
        "count": len(payload) if isinstance(payload, list) else 1,
    }


def _bundle_payload(value: FormalObjectValue) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(value, FormalObjectBase):
        return value.model_dump(mode="json")
    return [
        item.model_dump(mode="json")
        for item in value
    ]


def _ordered_object_keys(formal_objects: Mapping[str, FormalObjectValue]) -> tuple[str, ...]:
    canonical_keys = [
        object_key
        for object_key in CANONICAL_FORMAL_OBJECT_KEYS
        if object_key in formal_objects
    ]
    derived_keys = [
        object_key
        for object_key in formal_objects
        if object_key not in CANONICAL_FORMAL_OBJECT_KEYS
    ]
    return (*canonical_keys, *derived_keys)


__all__ = ["collect_formal_objects", "prepare_publish_bundle"]
