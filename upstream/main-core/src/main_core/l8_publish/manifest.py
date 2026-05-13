"""Manifest-backed formal object commit helpers for L8 publication."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from main_core.common.errors import ManifestPublishError
from main_core.common.schemas import FormalObjectBase
from main_core.common.types import CycleId
from main_core.l8_publish.publish_port import (
    CommittedFormalObject,
    DataPlatformPublishPort,
    FormalObjectValue,
    ManifestWriteResult,
)
from main_core.l8_publish.refs import CANONICAL_FORMAL_OBJECT_KEYS


def commit_formal_objects(
    cycle_id: CycleId,
    formal_objects: Mapping[str, FormalObjectValue],
    publish_port: DataPlatformPublishPort,
) -> tuple[CommittedFormalObject, ...]:
    """Commit formal object classes in stable order before manifest publication."""

    committed_objects: list[CommittedFormalObject] = []
    for object_key in _ordered_object_keys(formal_objects):
        formal_object = formal_objects[object_key]
        payload = _commit_payload(formal_object)
        expected_row_count = _expected_row_count(formal_object)
        try:
            committed_object = publish_port.commit_formal_object(
                cycle_id=cycle_id,
                object_key=object_key,
                payload=payload,
            )
        except ManifestPublishError:
            raise
        except Exception as exc:
            raise ManifestPublishError(
                f"failed to commit formal object {object_key}",
            ) from exc

        _validate_committed_formal_object(
            committed_object,
            object_key,
            expected_row_count,
        )
        committed_objects.append(committed_object)

    return tuple(committed_objects)


def write_manifest_after_commits(
    cycle_id: CycleId,
    committed_objects: Sequence[CommittedFormalObject],
    publish_port: DataPlatformPublishPort,
    *,
    expected_manifest_ref: str | None = None,
) -> ManifestWriteResult:
    """Write the cycle manifest only after all formal object commits succeed."""

    committed_tuple = tuple(committed_objects)
    try:
        manifest = publish_port.write_cycle_manifest(
            cycle_id=cycle_id,
            committed_objects=committed_tuple,
            expected_manifest_ref=expected_manifest_ref,
        )
    except ManifestPublishError:
        raise
    except Exception as exc:
        raise ManifestPublishError("failed to write cycle publish manifest") from exc
    _validate_manifest_write_result(manifest, committed_tuple)
    if (
        expected_manifest_ref is not None
        and manifest.manifest_ref != expected_manifest_ref
    ):
        raise ManifestPublishError(
            "manifest write result must match expected manifest_ref",
        )
    return manifest


def build_manifest_candidate(
    cycle_id: CycleId,
    committed_objects: Sequence[CommittedFormalObject],
    manifest: ManifestWriteResult | None = None,
) -> dict[str, Any]:
    """Build the manifest candidate embedded in the returned publish bundle."""

    candidate: dict[str, Any] = {
        "cycle_id": str(cycle_id),
        "object_refs": {
            committed.object_key: committed.ref
            for committed in committed_objects
        },
        "committed_objects": [
            {
                "object_key": committed.object_key,
                "ref": committed.ref,
                "snapshot_id": committed.snapshot_id,
                "payload_hash": committed.payload_hash,
                "row_count": committed.row_count,
            }
            for committed in committed_objects
        ],
    }
    if manifest is not None:
        candidate.update(
            {
                "manifest_ref": manifest.manifest_ref,
                "manifest_version": manifest.manifest_version,
                "table_snapshots": dict(manifest.table_snapshots),
            }
        )
    return candidate


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


def _commit_payload(value: FormalObjectValue) -> Mapping[str, Any]:
    if isinstance(value, FormalObjectBase):
        return value.model_dump(mode="json")

    payload_items = [
        item.model_dump(mode="json")
        for item in value
    ]
    return {"items": payload_items, "count": len(payload_items)}


def _expected_row_count(value: FormalObjectValue) -> int:
    if isinstance(value, FormalObjectBase):
        return 1
    return len(value)


def _validate_committed_formal_object(
    committed_object: CommittedFormalObject,
    object_key: str,
    expected_row_count: int,
) -> None:
    if not isinstance(committed_object, CommittedFormalObject):
        raise ManifestPublishError(
            f"commit result for {object_key} must be CommittedFormalObject",
        )
    if committed_object.object_key != object_key:
        raise ManifestPublishError(
            f"commit result object_key mismatch for {object_key}",
        )
    for field_name in ("ref", "snapshot_id", "payload_hash"):
        field_value = getattr(committed_object, field_name)
        if not _non_empty_string(field_value):
            raise ManifestPublishError(
                f"commit result {field_name} must be non-empty for {object_key}",
            )
    if (
        not isinstance(committed_object.row_count, int)
        or isinstance(committed_object.row_count, bool)
        or committed_object.row_count < 0
    ):
        raise ManifestPublishError(
            f"commit result row_count must be non-negative for {object_key}",
        )
    if committed_object.row_count != expected_row_count:
        raise ManifestPublishError(
            f"commit result row_count mismatch for {object_key}",
        )


def _validate_manifest_write_result(
    manifest: ManifestWriteResult,
    committed_objects: Sequence[CommittedFormalObject],
) -> None:
    if not isinstance(manifest, ManifestWriteResult):
        raise ManifestPublishError("manifest result must be ManifestWriteResult")
    if not _non_empty_string(manifest.manifest_ref):
        raise ManifestPublishError("manifest_ref must be non-empty")
    if not _non_empty_string(manifest.manifest_version):
        raise ManifestPublishError("manifest_version must be non-empty")
    if not isinstance(manifest.table_snapshots, Mapping):
        raise ManifestPublishError("manifest table_snapshots must be a mapping")

    expected_snapshots = {
        committed.object_key: committed.snapshot_id
        for committed in committed_objects
    }
    committed_object_keys = set(expected_snapshots)
    table_snapshot_keys = set(manifest.table_snapshots)
    missing_object_keys = committed_object_keys - table_snapshot_keys
    if missing_object_keys:
        missing = ", ".join(sorted(missing_object_keys))
        raise ManifestPublishError(
            f"manifest table_snapshots missing committed object keys: {missing}",
        )
    unexpected_object_keys = table_snapshot_keys - committed_object_keys
    if unexpected_object_keys:
        unexpected = ", ".join(sorted(unexpected_object_keys))
        raise ManifestPublishError(
            f"manifest table_snapshots contains unexpected object keys: {unexpected}",
        )
    for object_key, expected_snapshot_id in expected_snapshots.items():
        table_snapshot = manifest.table_snapshots[object_key]
        if table_snapshot is None or (
            isinstance(table_snapshot, str) and not table_snapshot.strip()
        ):
            raise ManifestPublishError(
                f"manifest table_snapshots entry must be non-empty for {object_key}",
            )
        if table_snapshot != expected_snapshot_id:
            raise ManifestPublishError(
                f"manifest table_snapshots snapshot_id mismatch for {object_key}",
            )


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


__all__ = [
    "build_manifest_candidate",
    "commit_formal_objects",
    "write_manifest_after_commits",
]
