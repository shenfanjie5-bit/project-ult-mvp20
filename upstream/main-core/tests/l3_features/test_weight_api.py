"""Tests for the public L3 multiplier API."""

from __future__ import annotations

from main_core.l3_features import (
    InMemoryMultiplierStore,
    apply_weight_multiplier,
    get_feature_weight_multiplier,
)


def test_weight_api_applies_updates_to_injected_store() -> None:
    store = InMemoryMultiplierStore()

    apply_weight_multiplier("cycle-001", {"close_price": 1.2}, store=store)
    apply_weight_multiplier("cycle-001", {"volume": 0.8}, store=store)

    assert get_feature_weight_multiplier("cycle-001", store=store) == {
        "close_price": 1.2,
        "volume": 0.8,
    }


def test_weight_api_returns_defensive_copy() -> None:
    store = InMemoryMultiplierStore()
    apply_weight_multiplier("cycle-001", {"close_price": 1.2}, store=store)

    returned_multipliers = get_feature_weight_multiplier("cycle-001", store=store)
    returned_multipliers["close_price"] = 9.9

    assert get_feature_weight_multiplier("cycle-001", store=store) == {"close_price": 1.2}
