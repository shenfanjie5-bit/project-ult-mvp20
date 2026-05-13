"""Ports for external L1/L2 data providers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from main_core.common.types import CycleId
from main_core.l1_l2_basis.models import CalendarDay, EntityMasterRow, MarketBar


@runtime_checkable
class DataPlatformPort(Protocol):
    """Read-only boundary for data-platform basis data access."""

    def read_market_bars(self, cycle_id: CycleId | str) -> Sequence[MarketBar]:
        """Return market bars for the requested cycle."""

    def read_calendar(self, cycle_id: CycleId | str) -> Sequence[CalendarDay]:
        """Return trading calendar rows for the requested cycle."""

    def read_entity_master(self, cycle_id: CycleId | str) -> Sequence[EntityMasterRow]:
        """Return entity master rows visible to the requested cycle."""


__all__ = ["DataPlatformPort"]
