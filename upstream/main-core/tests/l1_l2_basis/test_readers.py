"""Tests for L1/L2 basis reader functions."""

from __future__ import annotations

from datetime import date

import pytest

from main_core.common.types import CycleId, EntityId
from main_core.l1_l2_basis import (
    CalendarDay,
    DataPlatformReadError,
    EntityMasterRow,
    MarketBar,
    read_calendar,
    read_entity_master,
    read_market_bars,
)

from .conftest import FakeDataPlatformPort


def test_read_market_bars_delegates_once_and_returns_sorted_list(cycle_id: CycleId) -> None:
    later_aapl = MarketBar(
        cycle_id=cycle_id,
        entity_id=EntityId("ENT_AAPL"),
        as_of_date=date(2026, 4, 18),
        close_price=101.0,
        volume=1100.0,
    )
    earlier_aapl = MarketBar(
        cycle_id=cycle_id,
        entity_id=EntityId("ENT_AAPL"),
        as_of_date=date(2026, 4, 17),
        close_price=100.0,
        volume=1000.0,
    )
    msft = MarketBar(
        cycle_id=cycle_id,
        entity_id=EntityId("ENT_MSFT"),
        as_of_date=date(2026, 4, 17),
        close_price=200.0,
        volume=2000.0,
    )
    port = FakeDataPlatformPort(market_bars=(msft, later_aapl, earlier_aapl))

    result = read_market_bars(cycle_id, port=port)

    assert isinstance(result, list)
    assert result == [earlier_aapl, later_aapl, msft]
    assert port.market_bar_calls == [cycle_id]


def test_read_calendar_delegates_once_and_returns_sorted_list(cycle_id: CycleId) -> None:
    later = CalendarDay(
        cycle_id=cycle_id,
        trading_date=date(2026, 4, 20),
        is_trading_day=True,
    )
    earlier = CalendarDay(
        cycle_id=cycle_id,
        trading_date=date(2026, 4, 17),
        is_trading_day=True,
    )
    port = FakeDataPlatformPort(calendar=(later, earlier))

    result = read_calendar(str(cycle_id), port=port)

    assert result == [earlier, later]
    assert port.calendar_calls == [str(cycle_id)]


def test_read_entity_master_delegates_once_and_returns_sorted_list(cycle_id: CycleId) -> None:
    msft = EntityMasterRow(
        entity_id=EntityId("ENT_MSFT"),
        ticker="MSFT",
        name="Microsoft Corp.",
        exchange="NASDAQ",
    )
    aapl = EntityMasterRow(
        entity_id=EntityId("ENT_AAPL"),
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
    )
    port = FakeDataPlatformPort(entity_master=(msft, aapl))

    result = read_entity_master(cycle_id, port=port)

    assert result == [aapl, msft]
    assert port.entity_master_calls == [cycle_id]


@pytest.mark.parametrize(
    ("reader", "payload_name"),
    [
        (read_market_bars, "market_bars"),
        (read_calendar, "calendar"),
        (read_entity_master, "entity_master"),
    ],
)
def test_readers_reject_invalid_port_payloads(
    reader: object,
    payload_name: str,
    cycle_id: CycleId,
) -> None:
    port = FakeDataPlatformPort(**{payload_name: (object(),)})

    with pytest.raises(DataPlatformReadError, match="non-"):
        reader(cycle_id, port=port)


@pytest.mark.parametrize(
    ("reader", "payload_name", "record"),
    [
        (
            read_market_bars,
            "market_bars",
            MarketBar(
                cycle_id=CycleId("cycle-other"),
                entity_id=EntityId("ENT_AAPL"),
                as_of_date=date(2026, 4, 17),
                close_price=100.0,
                volume=1000.0,
            ),
        ),
        (
            read_calendar,
            "calendar",
            CalendarDay(
                cycle_id=CycleId("cycle-other"),
                trading_date=date(2026, 4, 17),
                is_trading_day=True,
            ),
        ),
    ],
)
def test_readers_reject_cycle_mismatches(
    reader: object,
    payload_name: str,
    record: MarketBar | CalendarDay,
    cycle_id: CycleId,
) -> None:
    port = FakeDataPlatformPort(**{payload_name: (record,)})

    with pytest.raises(DataPlatformReadError, match="different cycle"):
        reader(cycle_id, port=port)


def test_reader_wraps_port_failures(cycle_id: CycleId) -> None:
    class BrokenPort(FakeDataPlatformPort):
        def read_market_bars(self, cycle_id: CycleId | str) -> object:
            raise RuntimeError("provider unavailable")

    with pytest.raises(DataPlatformReadError, match="port failed"):
        read_market_bars(cycle_id, port=BrokenPort())
