"""Fixtures for L1/L2 basis reader tests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

import pytest

from main_core.common.types import CycleId, EntityId
from main_core.l1_l2_basis import CalendarDay, EntityMasterRow, MarketBar


@dataclass
class FakeDataPlatformPort:
    market_bars: Sequence[object] = field(default_factory=tuple)
    calendar: Sequence[object] = field(default_factory=tuple)
    entity_master: Sequence[object] = field(default_factory=tuple)
    market_bar_calls: list[CycleId | str] = field(default_factory=list)
    calendar_calls: list[CycleId | str] = field(default_factory=list)
    entity_master_calls: list[CycleId | str] = field(default_factory=list)

    def read_market_bars(self, cycle_id: CycleId | str) -> Sequence[object]:
        self.market_bar_calls.append(cycle_id)
        return self.market_bars

    def read_calendar(self, cycle_id: CycleId | str) -> Sequence[object]:
        self.calendar_calls.append(cycle_id)
        return self.calendar

    def read_entity_master(self, cycle_id: CycleId | str) -> Sequence[object]:
        self.entity_master_calls.append(cycle_id)
        return self.entity_master


@pytest.fixture
def cycle_id() -> CycleId:
    return CycleId("cycle-001")


@pytest.fixture
def active_entity() -> EntityMasterRow:
    return EntityMasterRow(
        entity_id=EntityId("ENT_AAPL"),
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        sector="technology",
    )


@pytest.fixture
def market_bar(cycle_id: CycleId, active_entity: EntityMasterRow) -> MarketBar:
    return MarketBar(
        cycle_id=cycle_id,
        entity_id=active_entity.entity_id,
        as_of_date=date(2026, 4, 17),
        close_price=100.0,
        volume=1000.0,
    )


@pytest.fixture
def calendar_day(cycle_id: CycleId) -> CalendarDay:
    return CalendarDay(
        cycle_id=cycle_id,
        trading_date=date(2026, 4, 17),
        is_trading_day=True,
        previous_trading_date=date(2026, 4, 16),
        next_trading_date=date(2026, 4, 20),
    )
