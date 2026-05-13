"""Reader functions for L1/L2 basis data."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

from main_core.common.types import CycleId
from main_core.l1_l2_basis.errors import DataPlatformReadError
from main_core.l1_l2_basis.models import CalendarDay, EntityMasterRow, MarketBar
from main_core.l1_l2_basis.ports import DataPlatformPort

BasisDTO = TypeVar("BasisDTO", MarketBar, CalendarDay, EntityMasterRow)


def read_market_bars(cycle_id: CycleId | str, *, port: DataPlatformPort) -> list[MarketBar]:
    """Read and validate market bars from the injected data-platform port."""

    records = _read_from_port(cycle_id, port.read_market_bars, MarketBar)
    _validate_cycle_ids(cycle_id, records, "market bars")
    return sorted(records, key=lambda record: (record.entity_id, record.as_of_date))


def read_calendar(cycle_id: CycleId | str, *, port: DataPlatformPort) -> list[CalendarDay]:
    """Read and validate trading calendar rows from the injected data-platform port."""

    records = _read_from_port(cycle_id, port.read_calendar, CalendarDay)
    _validate_cycle_ids(cycle_id, records, "calendar")
    return sorted(records, key=lambda record: record.trading_date)


def read_entity_master(
    cycle_id: CycleId | str,
    *,
    port: DataPlatformPort,
) -> list[EntityMasterRow]:
    """Read and validate entity master rows from the injected data-platform port."""

    records = _read_from_port(cycle_id, port.read_entity_master, EntityMasterRow)
    return sorted(records, key=lambda record: record.entity_id)


def _read_from_port(
    cycle_id: CycleId | str,
    read: Callable[[CycleId | str], Sequence[BasisDTO]],
    expected_type: type[BasisDTO],
) -> list[BasisDTO]:
    try:
        records = read(cycle_id)
    except DataPlatformReadError:
        raise
    except Exception as exc:
        raise DataPlatformReadError("data-platform port failed while reading basis data") from exc

    try:
        normalized_records = list(records)
    except TypeError as exc:
        raise DataPlatformReadError(
            "data-platform port returned a non-sequence basis payload"
        ) from exc

    invalid_records = [
        index
        for index, record in enumerate(normalized_records)
        if not isinstance(record, expected_type)
    ]
    if invalid_records:
        raise DataPlatformReadError(
            f"data-platform port returned non-{expected_type.__name__} records "
            f"at indexes {invalid_records}"
        )
    return normalized_records


def _validate_cycle_ids(
    requested_cycle_id: CycleId | str,
    records: Sequence[MarketBar] | Sequence[CalendarDay],
    dataset_name: str,
) -> None:
    requested = str(requested_cycle_id)
    mismatched_records = [
        index
        for index, record in enumerate(records)
        if str(record.cycle_id) != requested
    ]
    if mismatched_records:
        raise DataPlatformReadError(
            f"{dataset_name} contain records from a different cycle at indexes "
            f"{mismatched_records}"
        )


__all__ = ["read_calendar", "read_entity_master", "read_market_bars"]
