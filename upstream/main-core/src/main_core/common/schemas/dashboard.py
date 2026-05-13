"""L8 formal dashboard snapshot schema."""

from __future__ import annotations

from typing import Any

from main_core.common.schemas.base import FormalObjectBase
from main_core.common.types import CycleId


class DashboardSnapshot(FormalObjectBase):
    """Formal L8 dashboard snapshot described in §9.3."""

    cycle_id: CycleId
    world_state_ref: str
    pool_ref: str
    recommendation_ref: str
    summary_cards: dict[str, Any]


__all__ = ["DashboardSnapshot"]
