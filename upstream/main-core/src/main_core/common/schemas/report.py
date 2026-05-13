"""L8 formal report schema."""

from __future__ import annotations

from typing import Any

from main_core.common.schemas.base import FormalObjectBase
from main_core.common.types import CycleId


class FormalReport(FormalObjectBase):
    """Formal L8 human-facing report described in §9.3."""

    cycle_id: CycleId
    report_type: str
    recommendation_ref: str
    narrative_sections: dict[str, Any]
    appendix_refs: dict[str, Any]


__all__ = ["FormalReport"]
