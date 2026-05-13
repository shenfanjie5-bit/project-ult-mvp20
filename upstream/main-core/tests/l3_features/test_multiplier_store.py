"""Tests for L3 multiplier storage."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from main_core.common.types import CycleId
from main_core.l3_features import InMemoryMultiplierStore, InvalidMultiplierError


def test_in_memory_multiplier_store_is_cycle_scoped() -> None:
    store = InMemoryMultiplierStore()

    store.put_multipliers(CycleId("cycle-001"), {"close_price": 1.2})

    assert store.get_multipliers("cycle-001") == {"close_price": 1.2}
    assert store.get_multipliers("cycle-002") == {}


def test_in_memory_multiplier_store_returns_defensive_copy() -> None:
    store = InMemoryMultiplierStore()
    store.put_multipliers("cycle-001", {"close_price": 1.2})

    returned_multipliers = store.get_multipliers("cycle-001")
    returned_multipliers["close_price"] = 9.9

    assert store.get_multipliers("cycle-001") == {"close_price": 1.2}


def test_in_memory_multiplier_store_defensively_copies_updates() -> None:
    store = InMemoryMultiplierStore()
    updates = {"close_price": 1.2}

    store.put_multipliers("cycle-001", updates)
    updates["close_price"] = 9.9

    assert store.get_multipliers("cycle-001") == {"close_price": 1.2}


def test_in_memory_multiplier_store_merges_concurrent_same_cycle_updates_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryMultiplierStore()
    original_get_multipliers = store.get_multipliers
    read_barrier = Barrier(2)

    def synchronized_get_multipliers(cycle_id: CycleId | str) -> dict[str, float]:
        multipliers = original_get_multipliers(cycle_id)
        read_barrier.wait(timeout=5)
        return multipliers

    monkeypatch.setattr(store, "get_multipliers", synchronized_get_multipliers)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(store.put_multipliers, "cycle-001", {"close_price": 1.2}),
            executor.submit(store.put_multipliers, "cycle-001", {"volume": 0.5}),
        ]
        for future in futures:
            future.result(timeout=5)
    monkeypatch.undo()

    assert store.get_multipliers("cycle-001") == {
        "close_price": 1.2,
        "volume": 0.5,
    }


@pytest.mark.parametrize("invalid_multiplier", [0.0, -0.1, float("nan"), float("inf")])
def test_in_memory_multiplier_store_rejects_invalid_values(
    invalid_multiplier: float,
) -> None:
    store = InMemoryMultiplierStore()

    with pytest.raises(InvalidMultiplierError, match="finite and > 0"):
        store.put_multipliers("cycle-001", {"close_price": invalid_multiplier})

    assert store.get_multipliers("cycle-001") == {}
