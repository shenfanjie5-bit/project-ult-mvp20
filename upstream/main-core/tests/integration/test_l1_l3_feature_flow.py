"""Minimal pure-market L1 to L3 integration flow."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from main_core.common.types import CycleId, EntityId
from main_core.l1_l2_basis import CalendarDay, EntityMasterRow, MarketBar
from main_core.l3_features import build_feature_signal_bundles


@dataclass
class FakeDataPlatformPort:
    market_bars: Sequence[object] = field(default_factory=tuple)
    calendar: Sequence[object] = field(default_factory=tuple)
    entity_master: Sequence[object] = field(default_factory=tuple)

    def read_market_bars(self, cycle_id: CycleId | str) -> Sequence[object]:
        return self.market_bars

    def read_calendar(self, cycle_id: CycleId | str) -> Sequence[object]:
        return self.calendar

    def read_entity_master(self, cycle_id: CycleId | str) -> Sequence[object]:
        return self.entity_master


def test_pure_market_l1_to_l3_flow_without_graph_or_candidate_signals() -> None:
    cycle_id = CycleId("cycle-integration-001")
    entity = EntityMasterRow(
        entity_id=EntityId("ENT_AAPL"),
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
    )
    port = FakeDataPlatformPort(
        entity_master=(entity,),
        market_bars=(
            MarketBar(
                cycle_id=cycle_id,
                entity_id=entity.entity_id,
                as_of_date=date(2026, 4, 17),
                close_price=100.0,
                volume=1000.0,
                return_1d=0.01,
            ),
        ),
        calendar=(
            CalendarDay(
                cycle_id=cycle_id,
                trading_date=date(2026, 4, 17),
                is_trading_day=True,
            ),
        ),
    )

    bundles = build_feature_signal_bundles(cycle_id, data_port=port)

    assert len(bundles) == 1
    assert bundles[0].cycle_id == cycle_id
    assert bundles[0].entity_id == "ENT_AAPL"
    assert bundles[0].feature_values == {
        "close_price": 100.0,
        "volume": 1000.0,
        "return_1d": 0.01,
    }
    assert bundles[0].signal_values == {}
    assert bundles[0].graph_features == {}
    assert bundles[0].feature_weight_multiplier == {
        "close_price": 1.0,
        "volume": 1.0,
        "return_1d": 1.0,
    }
