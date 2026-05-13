"""Cycle-scoped feature multiplier storage."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from threading import Lock
from typing import Protocol, runtime_checkable

from main_core.common.types import CycleId
from main_core.l3_features.errors import InvalidMultiplierError


@runtime_checkable
class MultiplierStore(Protocol):
    """Storage contract for online feature weight multiplier updates."""

    def get_multipliers(self, cycle_id: CycleId | str) -> Mapping[str, float]:
        """Return multipliers currently visible for a cycle."""

    def put_multipliers(
        self,
        cycle_id: CycleId | str,
        updates: Mapping[str, float],
    ) -> None:
        """Persist multiplier updates for a cycle."""


class InMemoryMultiplierStore:
    """In-process multiplier store with per-cycle isolation."""

    def __init__(self) -> None:
        self._multipliers_by_cycle: dict[str, dict[str, float]] = {}
        self._lock = Lock()

    def get_multipliers(self, cycle_id: CycleId | str) -> dict[str, float]:
        """Return a defensive copy of the multipliers for the requested cycle."""

        with self._lock:
            return dict(self._multipliers_by_cycle.get(str(cycle_id), {}))

    def put_multipliers(
        self,
        cycle_id: CycleId | str,
        updates: Mapping[str, float],
    ) -> None:
        """Validate and store multiplier updates for the requested cycle."""

        validated_updates = _validated_multiplier_copy(updates)
        cycle_key = str(cycle_id)
        with self._lock:
            current_multipliers = dict(self._multipliers_by_cycle.get(cycle_key, {}))
            current_multipliers.update(validated_updates)
            self._multipliers_by_cycle[cycle_key] = current_multipliers


def _validated_multiplier_copy(updates: Mapping[str, float]) -> dict[str, float]:
    invalid_keys = [
        feature_name
        for feature_name, multiplier in updates.items()
        if not isinstance(multiplier, int | float)
        or isinstance(multiplier, bool)
        or not isfinite(multiplier)
        or multiplier <= 0
    ]
    if invalid_keys:
        raise InvalidMultiplierError("feature weight multipliers must be finite and > 0")
    return {feature_name: float(multiplier) for feature_name, multiplier in updates.items()}


__all__ = ["InMemoryMultiplierStore", "MultiplierStore"]
