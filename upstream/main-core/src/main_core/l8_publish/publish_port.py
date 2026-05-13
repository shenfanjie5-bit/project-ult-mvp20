"""L8 publish source and data-platform boundary protocols."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from main_core.common.schemas import (
    AlphaResultSnapshot,
    FormalObjectBase,
    OfficialAlphaPool,
    PublishBundle,
    RecommendationSnapshot,
    WorldStateSnapshot,
)
from main_core.common.types import CycleId

FormalObjectValue = FormalObjectBase | Sequence[FormalObjectBase]


@dataclass(frozen=True)
class CommittedFormalObject:
    """Reference returned after one formal object class is committed."""

    object_key: str
    ref: str
    snapshot_id: str
    payload_hash: str
    row_count: int


@dataclass(frozen=True)
class ManifestWriteResult:
    """Reference returned after the cycle manifest becomes visible."""

    manifest_ref: str
    manifest_version: str
    table_snapshots: Mapping[str, Any]


class FormalObjectSource(Protocol):
    """Read already-built formal objects from upstream L4-L7 boundaries."""

    def load_world_state(self, cycle_id: CycleId) -> WorldStateSnapshot:
        """Load the formal L4 world-state snapshot for a cycle."""

    def load_official_alpha_pool(self, cycle_id: CycleId) -> OfficialAlphaPool:
        """Load the formal L5 official alpha pool for a cycle."""

    def load_alpha_results(self, cycle_id: CycleId) -> Sequence[AlphaResultSnapshot]:
        """Load formal L6 alpha result snapshots for a cycle."""

    def load_recommendations(self, cycle_id: CycleId) -> Sequence[RecommendationSnapshot]:
        """Load formal L7 recommendation snapshots for a cycle."""


class DataPlatformPublishPort(Protocol):
    """Manifest-backed formal object publication boundary."""

    def reserve_cycle_manifest_ref(
        self,
        *,
        cycle_id: CycleId,
    ) -> str:
        """Reserve the exact manifest ref that write_cycle_manifest will publish."""

    def commit_formal_object(
        self,
        *,
        cycle_id: CycleId,
        object_key: str,
        payload: Mapping[str, Any],
    ) -> CommittedFormalObject:
        """Commit one formal object class before the manifest is written."""

    def write_cycle_manifest(
        self,
        *,
        cycle_id: CycleId,
        committed_objects: Sequence[CommittedFormalObject],
        expected_manifest_ref: str | None = None,
    ) -> ManifestWriteResult:
        """Write the cycle manifest after all formal object commits succeed.

        When ``expected_manifest_ref`` is provided, the port must either publish
        the manifest at exactly that ref or fail before the manifest is visible.
        """


class DerivedFormalObjectBuilder(Protocol):
    """Future hook for derived L8 formal objects such as reports."""

    def __call__(
        self,
        cycle_id: CycleId,
        bundle: PublishBundle,
    ) -> Mapping[str, FormalObjectBase]:
        """Build derived formal objects from a pre-publish bundle draft."""


__all__ = [
    "CommittedFormalObject",
    "DataPlatformPublishPort",
    "DerivedFormalObjectBuilder",
    "FormalObjectSource",
    "FormalObjectValue",
    "ManifestWriteResult",
]
