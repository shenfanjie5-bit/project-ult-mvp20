"""L8 runtime publish bundle schema."""

from __future__ import annotations

from typing import Any

from main_core.common.schemas.base import FormalObjectBase
from main_core.common.types import CycleId


class PublishBundle(FormalObjectBase):
    """Runtime Phase 3 publish bundle described in §9.3."""

    cycle_id: CycleId
    formal_objects: dict[str, Any]
    manifest_candidate: dict[str, Any]
    audit_payload: dict[str, Any]
    retrospective_seed: dict[str, Any]


__all__ = ["PublishBundle"]
