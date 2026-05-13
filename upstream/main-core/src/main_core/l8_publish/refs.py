"""Canonical formal object keys and ref readers for L8 publish bundles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from main_core.common.errors import ManifestPublishError
from main_core.common.schemas import PublishBundle

WORLD_STATE_SNAPSHOT_KEY = "world_state_snapshot"
OFFICIAL_ALPHA_POOL_KEY = "official_alpha_pool"
ALPHA_RESULT_SNAPSHOT_KEY = "alpha_result_snapshot"
RECOMMENDATION_SNAPSHOT_KEY = "recommendation_snapshot"

CANONICAL_FORMAL_OBJECT_KEYS: tuple[str, ...] = (
    WORLD_STATE_SNAPSHOT_KEY,
    OFFICIAL_ALPHA_POOL_KEY,
    ALPHA_RESULT_SNAPSHOT_KEY,
    RECOMMENDATION_SNAPSHOT_KEY,
)


def formal_object_ref(bundle: PublishBundle, object_key: str) -> str:
    """Return the single canonical ref for a formal object entry."""

    refs = formal_object_refs(bundle, object_key)
    if len(refs) != 1:
        raise ManifestPublishError(f"{object_key} must expose exactly one formal ref")
    return refs[0]


def formal_object_refs(bundle: PublishBundle, object_key: str) -> tuple[str, ...]:
    """Return formal refs from a bundle entry using the canonical ref shape."""

    entry = _formal_object_entry(bundle, object_key)
    if "refs" in entry:
        refs = entry["refs"]
        if (
            isinstance(refs, Sequence)
            and not isinstance(refs, (str, bytes))
            and all(isinstance(ref, str) for ref in refs)
        ):
            return tuple(refs)
        raise ManifestPublishError(f"{object_key}.refs must be a sequence of strings")

    ref = entry.get("ref")
    if not isinstance(ref, str) or not ref:
        raise ManifestPublishError(f"{object_key}.ref must be a non-empty string")
    return (ref,)


def _formal_object_entry(
    bundle: PublishBundle,
    object_key: str,
) -> Mapping[str, Any]:
    try:
        entry = bundle.formal_objects[object_key]
    except KeyError as exc:
        raise ManifestPublishError(f"missing formal object entry {object_key}") from exc

    if not isinstance(entry, Mapping):
        raise ManifestPublishError(f"{object_key} formal object entry must be a mapping")
    return entry


__all__ = [
    "ALPHA_RESULT_SNAPSHOT_KEY",
    "CANONICAL_FORMAL_OBJECT_KEYS",
    "OFFICIAL_ALPHA_POOL_KEY",
    "RECOMMENDATION_SNAPSHOT_KEY",
    "WORLD_STATE_SNAPSHOT_KEY",
    "formal_object_ref",
    "formal_object_refs",
]
