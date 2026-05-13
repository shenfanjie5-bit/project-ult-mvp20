"""Fixtures for L4 world-state tests."""

from __future__ import annotations

import pytest

from main_core.common.schemas import FeatureSignalBundle


@pytest.fixture
def feature_bundle() -> FeatureSignalBundle:
    return FeatureSignalBundle(
        cycle_id="cycle_001",
        entity_id="ENT_001",
        feature_values={"momentum": 0.42, "volatility": 0.2},
        signal_values={},
        graph_features={"centrality": 0.5},
        feature_weight_multiplier={"momentum": 1.2, "volatility": 1.0},
    )
