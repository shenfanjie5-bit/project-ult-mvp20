"""Draft manifest contracts for offline replay spikes."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CyclePublishManifestDraft(BaseModel):
    """Published formal snapshot set for one cycle."""

    model_config = ConfigDict(extra="forbid")

    published_cycle_id: str
    snapshot_refs: dict[str, str]
    published_at: datetime


__all__ = ["CyclePublishManifestDraft"]

