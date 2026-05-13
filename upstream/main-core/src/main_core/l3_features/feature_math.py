"""Pure feature derivation helpers for L3 feature bundles."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite

from main_core.l1_l2_basis.models import MarketBar
from main_core.l3_features.errors import InvalidMultiplierError


def market_bar_feature_values(market_bar: MarketBar) -> dict[str, float]:
    """Convert a validated latest market bar into base numeric feature values."""

    feature_values = {
        "close_price": market_bar.close_price,
        "volume": market_bar.volume,
    }
    if market_bar.return_1d is not None:
        feature_values["return_1d"] = market_bar.return_1d
    return feature_values


def apply_feature_weight_multiplier(
    feature_values: Mapping[str, float],
    multipliers: Mapping[str, float],
) -> tuple[dict[str, float], dict[str, float]]:
    """Apply known feature multipliers and return weighted features plus effective weights."""

    effective_multipliers = {
        feature_name: float(multipliers.get(feature_name, 1.0))
        for feature_name in feature_values
    }
    weighted_feature_values = {}
    for feature_name, feature_value in feature_values.items():
        weighted_feature_value = feature_value * effective_multipliers[feature_name]
        if not isfinite(weighted_feature_value):
            raise InvalidMultiplierError(
                "weighted feature values must be finite after applying multipliers"
            )
        weighted_feature_values[feature_name] = weighted_feature_value
    return weighted_feature_values, effective_multipliers


__all__ = ["apply_feature_weight_multiplier", "market_bar_feature_values"]
