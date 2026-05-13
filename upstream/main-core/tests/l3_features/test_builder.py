"""Tests for L3 feature bundle assembly."""

from __future__ import annotations

import sys
from datetime import date
from sys import float_info
from types import ModuleType

import pytest

from main_core.common.schemas.feature_bundle import FeatureSignalBundle
from main_core.common.types import CycleId, EntityId
from main_core.l1_l2_basis import EntityMasterRow, MarketBar
from main_core.l3_features import (
    CandidateSignalRecord,
    InMemoryMultiplierStore,
    InvalidMultiplierError,
    L3FeatureError,
    apply_weight_multiplier,
    build_feature_signal_bundle,
    build_feature_signal_bundles,
)
from main_core.l3_features.feature_math import (
    apply_feature_weight_multiplier,
    market_bar_feature_values,
)

from .conftest import FakeDataPlatformPort

UPDATED_CLOSE_PRICE = 120.0
UPDATED_CLOSE_MULTIPLIER = 1.2


class FakeCandidateSignalPort:
    def __init__(self, records: tuple[CandidateSignalRecord, ...]) -> None:
        self.records = records
        self.calls: list[CycleId] = []

    def read_candidate_signals(
        self,
        cycle_id: CycleId,
    ) -> tuple[CandidateSignalRecord, ...]:
        self.calls.append(cycle_id)
        return self.records


def test_feature_math_derives_market_features_and_applies_known_multipliers(
    cycle_id: CycleId,
) -> None:
    market_bar = MarketBar(
        cycle_id=cycle_id,
        entity_id=EntityId("ENT_AAPL"),
        as_of_date=date(2026, 4, 17),
        close_price=100.0,
        volume=1000.0,
        return_1d=0.02,
    )

    base_features = market_bar_feature_values(market_bar)
    weighted_features, effective_multipliers = apply_feature_weight_multiplier(
        base_features,
        {"close_price": 1.2, "unknown_feature": 9.0},
    )

    assert base_features == {
        "close_price": 100.0,
        "volume": 1000.0,
        "return_1d": 0.02,
    }
    assert weighted_features == {
        "close_price": 120.0,
        "volume": 1000.0,
        "return_1d": 0.02,
    }
    assert effective_multipliers == {
        "close_price": 1.2,
        "volume": 1.0,
        "return_1d": 1.0,
    }


def test_feature_math_omits_missing_return_1d(cycle_id: CycleId) -> None:
    market_bar = MarketBar(
        cycle_id=cycle_id,
        entity_id=EntityId("ENT_AAPL"),
        as_of_date=date(2026, 4, 17),
        close_price=100.0,
        volume=1000.0,
    )

    assert market_bar_feature_values(market_bar) == {
        "close_price": 100.0,
        "volume": 1000.0,
    }


def test_feature_math_rejects_weighted_feature_overflow() -> None:
    with pytest.raises(InvalidMultiplierError, match="weighted feature values"):
        apply_feature_weight_multiplier(
            {"close_price": float_info.max},
            {"close_price": 2.0},
        )


def test_build_feature_signal_bundle_uses_latest_market_bar_and_sorts_by_entity(
    cycle_id: CycleId,
) -> None:
    aapl = EntityMasterRow(
        entity_id=EntityId("ENT_AAPL"),
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
    )
    msft = EntityMasterRow(
        entity_id=EntityId("ENT_MSFT"),
        ticker="MSFT",
        name="Microsoft Corp.",
        exchange="NASDAQ",
    )
    inactive = EntityMasterRow(
        entity_id=EntityId("ENT_IBM"),
        ticker="IBM",
        name="International Business Machines",
        exchange="NYSE",
        is_active=False,
    )
    earlier_aapl = MarketBar(
        cycle_id=cycle_id,
        entity_id=aapl.entity_id,
        as_of_date=date(2026, 4, 16),
        close_price=90.0,
        volume=900.0,
    )
    latest_aapl = MarketBar(
        cycle_id=cycle_id,
        entity_id=aapl.entity_id,
        as_of_date=date(2026, 4, 17),
        close_price=100.0,
        volume=1000.0,
        return_1d=0.03,
    )
    msft_bar = MarketBar(
        cycle_id=cycle_id,
        entity_id=msft.entity_id,
        as_of_date=date(2026, 4, 17),
        close_price=200.0,
        volume=2000.0,
    )
    inactive_bar = MarketBar(
        cycle_id=cycle_id,
        entity_id=inactive.entity_id,
        as_of_date=date(2026, 4, 17),
        close_price=50.0,
        volume=500.0,
    )
    store = InMemoryMultiplierStore()
    apply_weight_multiplier(cycle_id, {"close_price": 1.2, "volume": 0.5}, store=store)
    port = FakeDataPlatformPort(
        market_bars=(msft_bar, inactive_bar, latest_aapl, earlier_aapl),
        entity_master=(msft, inactive, aapl),
    )

    bundles = build_feature_signal_bundles(
        cycle_id,
        data_port=port,
        multiplier_store=store,
        graph_impact={"ENT_AAPL": {"centrality": 0.7}},
        candidate_signals={"ENT_AAPL": {"direction": "positive"}},
    )

    assert all(isinstance(bundle, FeatureSignalBundle) for bundle in bundles)
    assert [bundle.entity_id for bundle in bundles] == ["ENT_AAPL", "ENT_MSFT"]
    assert bundles[0].feature_values == {
        "close_price": 120.0,
        "volume": 500.0,
        "return_1d": 0.03,
    }
    assert bundles[0].feature_weight_multiplier == {
        "close_price": 1.2,
        "volume": 0.5,
        "return_1d": 1.0,
    }
    assert bundles[0].signal_values == {
        "candidate_signals": {
            "direction": {
                "raw_value": "positive",
                "adjusted_value": "positive",
                "source": "layer_b",
                "confidence": None,
                "metadata": {},
            },
        },
    }
    assert bundles[0].graph_features == {"centrality": 0.7}
    assert bundles[1].feature_values == {
        "close_price": 240.0,
        "volume": 1000.0,
    }
    assert bundles[1].signal_values == {}
    assert bundles[1].graph_features == {}
    assert port.entity_master_calls == [cycle_id]
    assert port.market_bar_calls == [cycle_id]


def test_build_feature_signal_bundle_defaults_optional_inputs_to_empty_dicts(
    cycle_id: CycleId,
    active_entity: EntityMasterRow,
    market_bar: MarketBar,
) -> None:
    port = FakeDataPlatformPort(
        market_bars=(market_bar,),
        entity_master=(active_entity,),
    )

    bundles = build_feature_signal_bundles(cycle_id, data_port=port)

    assert len(bundles) == 1
    assert bundles[0].cycle_id == cycle_id
    assert bundles[0].entity_id == active_entity.entity_id
    assert bundles[0].signal_values == {}
    assert bundles[0].graph_features == {}
    assert bundles[0].feature_weight_multiplier == {
        "close_price": 1.0,
        "volume": 1.0,
        "return_1d": 1.0,
    }


def test_build_feature_signal_bundle_normalizes_all_candidate_signal_inputs(
    cycle_id: CycleId,
    active_entity: EntityMasterRow,
    market_bar: MarketBar,
) -> None:
    port = FakeDataPlatformPort(
        market_bars=(market_bar,),
        entity_master=(active_entity,),
    )
    candidate_port = FakeCandidateSignalPort(
        (
            CandidateSignalRecord(
                cycle_id=cycle_id,
                entity_id=active_entity.entity_id,
                signal_name="port_score",
                value=2.0,
                confidence=0.7,
                metadata={"source_table": "candidate_signal_port"},
            ),
        )
    )

    bundle = build_feature_signal_bundle(
        cycle_id,
        data_port=port,
        candidate_signals={
            str(active_entity.entity_id): {
                "legacy_direction": "positive",
            },
        },
        candidate_signal_port=candidate_port,
    )

    assert bundle.signal_values == {
        "candidate_signals": {
            "legacy_direction": {
                "raw_value": "positive",
                "adjusted_value": "positive",
                "source": "layer_b",
                "confidence": None,
                "metadata": {},
            },
            "port_score": {
                "raw_value": 2.0,
                "adjusted_value": 2.0,
                "source": "layer_b",
                "confidence": 0.7,
                "metadata": {"source_table": "candidate_signal_port"},
            },
        },
    }
    assert candidate_port.calls == [cycle_id]


def test_default_multiplier_store_update_is_visible_to_same_cycle_build() -> None:
    cycle_id = CycleId("cycle-default-online-update")
    entity = EntityMasterRow(
        entity_id=EntityId("ENT_AAPL"),
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
    )
    market_bar = MarketBar(
        cycle_id=cycle_id,
        entity_id=entity.entity_id,
        as_of_date=date(2026, 4, 17),
        close_price=100.0,
        volume=1000.0,
    )
    port = FakeDataPlatformPort(
        market_bars=(market_bar,),
        entity_master=(entity,),
    )

    apply_weight_multiplier(cycle_id, {"close_price": UPDATED_CLOSE_MULTIPLIER})

    bundles = build_feature_signal_bundles(cycle_id, data_port=port)

    assert bundles[0].feature_values["close_price"] == UPDATED_CLOSE_PRICE
    assert bundles[0].feature_weight_multiplier["close_price"] == UPDATED_CLOSE_MULTIPLIER


def test_build_feature_signal_bundle_resolves_default_port_and_returns_single_bundle(
    cycle_id: CycleId,
    active_entity: EntityMasterRow,
    market_bar: MarketBar,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = FakeDataPlatformPort(
        market_bars=(market_bar,),
        entity_master=(active_entity,),
    )
    module = ModuleType("fake_l3_data_platform")
    module.build_port = lambda: port
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setenv("MAIN_CORE_DATA_PLATFORM_PORT", f"{module.__name__}:build_port")

    bundle = build_feature_signal_bundle(cycle_id)

    assert isinstance(bundle, FeatureSignalBundle)
    assert bundle.cycle_id == cycle_id
    assert bundle.entity_id == active_entity.entity_id
    assert port.entity_master_calls == [cycle_id]
    assert port.market_bar_calls == [cycle_id]


def test_build_feature_signal_bundle_rejects_ambiguous_multi_entity_cycle(
    cycle_id: CycleId,
) -> None:
    aapl = EntityMasterRow(
        entity_id=EntityId("ENT_AAPL"),
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
    )
    msft = EntityMasterRow(
        entity_id=EntityId("ENT_MSFT"),
        ticker="MSFT",
        name="Microsoft Corp.",
        exchange="NASDAQ",
    )
    port = FakeDataPlatformPort(
        entity_master=(aapl, msft),
        market_bars=(
            MarketBar(
                cycle_id=cycle_id,
                entity_id=aapl.entity_id,
                as_of_date=date(2026, 4, 17),
                close_price=100.0,
                volume=1000.0,
            ),
            MarketBar(
                cycle_id=cycle_id,
                entity_id=msft.entity_id,
                as_of_date=date(2026, 4, 17),
                close_price=200.0,
                volume=2000.0,
            ),
        ),
    )

    with pytest.raises(L3FeatureError, match="multiple FeatureSignalBundle"):
        build_feature_signal_bundle(cycle_id, data_port=port)

    bundles = build_feature_signal_bundles(cycle_id, data_port=port)
    assert [bundle.entity_id for bundle in bundles] == ["ENT_AAPL", "ENT_MSFT"]
