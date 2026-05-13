"""Gateway protocols for manifest-bound formal snapshot reads."""

from __future__ import annotations

from typing import Any, Protocol

from audit_eval.contracts.manifest_draft import CyclePublishManifestDraft


class ManifestGateway(Protocol):
    """Read the published formal snapshot set for one cycle."""

    def load(self, cycle_id: str) -> CyclePublishManifestDraft:
        """Load the cycle_publish_manifest row for cycle_id."""


class FormalSnapshotGateway(Protocol):
    """Read formal objects only through manifest snapshot/time-travel refs."""

    def load_snapshot(self, snapshot_ref: str) -> dict[str, Any]:
        """Load one historical formal object by manifest snapshot ref."""


__all__ = ["FormalSnapshotGateway", "ManifestGateway"]
