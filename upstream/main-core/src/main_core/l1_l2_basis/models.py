"""Pydantic DTOs for L1/L2 basis data reads."""

from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from main_core.common.types import CycleId, EntityId


class _L1L2BasisDTO(BaseModel):
    """Frozen strict DTO base local to the L1/L2 basis layer."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MarketBar(_L1L2BasisDTO):
    """Market OHLCV row returned by the injected data-platform port."""

    cycle_id: CycleId
    entity_id: EntityId
    as_of_date: date
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    close_price: float
    volume: float
    return_1d: float | None = None

    @field_validator(
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
        "return_1d",
    )
    @classmethod
    def validate_finite_numeric_value(cls, value: float | None) -> float | None:
        """Reject non-finite numeric payloads before L3 derives features."""

        if value is not None and not isfinite(value):
            raise ValueError("numeric market bar values must be finite")
        return value

    @model_validator(mode="after")
    def validate_non_negative_close_and_volume(self) -> Self:
        """Reject impossible price and volume payloads."""

        if self.close_price < 0:
            raise ValueError("close_price must be non-negative")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        return self


class CalendarDay(_L1L2BasisDTO):
    """Trading calendar metadata for one cycle."""

    cycle_id: CycleId
    trading_date: date
    is_trading_day: bool
    previous_trading_date: date | None = None
    next_trading_date: date | None = None


class EntityMasterRow(_L1L2BasisDTO):
    """Minimal entity master row required by P2a L3 feature reads."""

    entity_id: EntityId
    ticker: str
    name: str
    exchange: str
    is_active: bool = True
    sector: str | None = None


__all__ = ["CalendarDay", "EntityMasterRow", "MarketBar"]
