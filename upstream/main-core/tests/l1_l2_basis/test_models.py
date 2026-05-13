"""Tests for L1/L2 basis DTO validation."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from main_core.common.types import CycleId, EntityId
from main_core.l1_l2_basis import CalendarDay, EntityMasterRow, MarketBar


def _market_bar_payload() -> dict[str, object]:
    return {
        "cycle_id": CycleId("cycle-001"),
        "entity_id": EntityId("ENT_AAPL"),
        "as_of_date": date(2026, 4, 17),
        "open_price": 99.0,
        "high_price": 101.0,
        "low_price": 98.0,
        "close_price": 100.0,
        "volume": 1000.0,
        "return_1d": 0.01,
    }


def test_l1_dtos_are_frozen_strict_and_forbid_extra_fields() -> None:
    for model in (MarketBar, CalendarDay, EntityMasterRow):
        assert model.model_config["extra"] == "forbid"
        assert model.model_config["frozen"] is True
        assert model.model_config["strict"] is True

    bar = MarketBar(**_market_bar_payload())

    with pytest.raises(ValidationError):
        MarketBar(**(_market_bar_payload() | {"unexpected": "field"}))
    with pytest.raises(ValidationError):
        bar.close_price = 101.0


@pytest.mark.parametrize(
    ("field_name", "value", "match"),
    [
        ("open_price", float("nan"), "finite"),
        ("high_price", float("inf"), "finite"),
        ("low_price", float("-inf"), "finite"),
        ("close_price", float("nan"), "finite"),
        ("volume", float("inf"), "finite"),
        ("return_1d", float("-inf"), "finite"),
        ("close_price", -0.01, "close_price"),
        ("volume", -1.0, "volume"),
    ],
)
def test_market_bar_rejects_invalid_numeric_values(
    field_name: str,
    value: float,
    match: str,
) -> None:
    payload = _market_bar_payload()
    payload[field_name] = value

    with pytest.raises(ValidationError, match=match):
        MarketBar(**payload)


def test_market_bar_requires_strict_field_types() -> None:
    payload = _market_bar_payload()
    payload["close_price"] = "100.0"

    with pytest.raises(ValidationError):
        MarketBar(**payload)


def test_calendar_day_and_entity_master_happy_paths() -> None:
    calendar_day = CalendarDay(
        cycle_id=CycleId("cycle-001"),
        trading_date=date(2026, 4, 17),
        is_trading_day=True,
    )
    entity = EntityMasterRow(
        entity_id=EntityId("ENT_AAPL"),
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
    )

    assert calendar_day.previous_trading_date is None
    assert entity.is_active is True
    assert entity.sector is None
