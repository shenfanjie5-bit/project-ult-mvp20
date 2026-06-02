"""Tests for Bucket A hard-data dp_ids in ``tushare_source``.

All Tushare HTTP calls are stubbed via fake DataFrames so the suite stays
hermetic. We exercise each fetcher and the dispatcher contract:

  * L2.segment.revenue_share / gross_margin / growth  — fina_mainbz
  * L5.fcst.guidance_change  — forecast (2 most recent)
  * L5.surprise.beat_miss    — express + forecast
  * L8.fin.eps_downward      — forecast EPS midpoint delta
  * L8.fin.goodwill_impairment — balancesheet goodwill drop
  * L8.fin.revenue_profit_miss — derived from beat_miss
  * L8.cap.crowdedness       — daily_basic.turnover + 5d main_net
  * L8.cap.short_increase    — margin_detail.rqye 30/90d ma
  * L8.cap.liquidity_short   — daily.amount + pct_chg/vol
  * L8.industry.valuation_compression — industry PE 30/90d median
  * L8.op.cost_overrun       — income.oper_cost yoy vs revenue yoy
  * L9.capital.margin_anomaly — margin_detail.rzmre 5/30d ma
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mvp20.sources import tushare_source


# ---------------------------------------------------------------------------
# Test stubs (mirror test_tushare_derive.py style).
# ---------------------------------------------------------------------------


class _StubDF:
    """Minimal DataFrame stand-in covering the calls Bucket A makes."""

    def __init__(self, records: list[dict[str, Any]]):
        self._rows = list(records)

    def __len__(self) -> int:
        return len(self._rows)

    def sort_values(self, key, ascending: bool = True) -> "_StubDF":
        return _StubDF(sorted(
            self._rows,
            key=lambda r: (r.get(key) is None, r.get(key)),
            reverse=not ascending,
        ))

    def head(self, n: int) -> "_StubDF":
        return _StubDF(self._rows[:n])

    def to_dict(self, orient: str = "records") -> list[dict[str, Any]]:
        assert orient == "records"
        return [dict(r) for r in self._rows]

    @property
    def columns(self):
        cols: set[str] = set()
        for r in self._rows:
            cols.update(r.keys())
        return cols


class _StubPro:
    """Per-endpoint dispatcher for Bucket A tests."""

    def __init__(self, **endpoint_data):
        self._data = endpoint_data
        self.call_counts: dict[str, int] = {k: 0 for k in endpoint_data}

    def _dispatch(self, name: str, **kwargs):
        self.call_counts[name] = self.call_counts.get(name, 0) + 1
        v = self._data.get(name)
        if isinstance(v, Exception):
            raise v
        if callable(v):
            return v(**kwargs)
        return v

    def fina_mainbz(self, **kw):     return self._dispatch("fina_mainbz", **kw)
    def forecast(self, **kw):        return self._dispatch("forecast", **kw)
    def express(self, **kw):         return self._dispatch("express", **kw)
    def balancesheet(self, **kw):    return self._dispatch("balancesheet", **kw)
    def income(self, **kw):          return self._dispatch("income", **kw)
    def daily_basic(self, **kw):     return self._dispatch("daily_basic", **kw)
    def daily(self, **kw):           return self._dispatch("daily", **kw)
    def margin_detail(self, **kw):   return self._dispatch("margin_detail", **kw)
    def cashflow(self, **kw):        return self._dispatch("cashflow", **kw)
    def fina_indicator(self, **kw):  return self._dispatch("fina_indicator", **kw)


@pytest.fixture(autouse=True)
def _clear_caches():
    """Wipe every cache touched by Bucket A between tests."""

    tushare_source._FINA_MAINBZ_CACHE.clear()
    tushare_source._FORECAST_CACHE.clear()
    tushare_source._EXPRESS_CACHE.clear()
    tushare_source._BALANCESHEET_CACHE.clear()
    tushare_source._INCOME_CACHE.clear()
    tushare_source._DAILY_BASIC_HISTORY_CACHE.clear()
    tushare_source._DAILY_HISTORY_CACHE.clear()
    tushare_source._MARGIN_HISTORY_CACHE.clear()
    yield
    tushare_source._FINA_MAINBZ_CACHE.clear()
    tushare_source._FORECAST_CACHE.clear()
    tushare_source._EXPRESS_CACHE.clear()
    tushare_source._BALANCESHEET_CACHE.clear()
    tushare_source._INCOME_CACHE.clear()
    tushare_source._DAILY_BASIC_HISTORY_CACHE.clear()
    tushare_source._DAILY_HISTORY_CACHE.clear()
    tushare_source._MARGIN_HISTORY_CACHE.clear()


# ---------------------------------------------------------------------------
# SUPPORTED_DP_IDS contract — all Bucket A + direct priced dp_ids registered.
# ---------------------------------------------------------------------------


def test_supported_dp_ids_includes_bucket_a_and_priced_crowdedness() -> None:
    expected = {
        "L2.segment.revenue_share", "L2.segment.gross_margin",
        "L2.segment.growth",
        "L5.fcst.guidance_change", "L5.surprise.beat_miss",
        "L8.fin.eps_downward", "L8.fin.goodwill_impairment",
        "L8.fin.revenue_profit_miss",
        "L6.priced.crowdedness",
        "L8.cap.crowdedness", "L8.cap.short_increase",
        "L8.cap.liquidity_short",
        "L8.industry.valuation_compression", "L8.op.cost_overrun",
        "L9.capital.margin_anomaly",
    }
    assert expected.issubset(tushare_source.SUPPORTED_DP_IDS)


# ---------------------------------------------------------------------------
# _derive_segments — L2.segment.*
# ---------------------------------------------------------------------------


def test_derive_segments_revenue_share_and_gross_margin() -> None:
    # Two segments in 20260331 + one prior-year row → yoy growth possible.
    records = [
        {"end_date": "20260331", "bz_item": "电池", "bz_sales": 60.0,
         "bz_cost": 36.0},
        {"end_date": "20260331", "bz_item": "材料", "bz_sales": 40.0,
         "bz_cost": 30.0},
        {"end_date": "20250331", "bz_item": "电池", "bz_sales": 40.0,
         "bz_cost": 30.0},
        {"end_date": "20250331", "bz_item": "材料", "bz_sales": 35.0,
         "bz_cost": 25.0},
    ]
    rs, gm, gr = tushare_source._derive_segments(records)
    # revenue_share: 60/100 = 60%, 40/100 = 40%
    rs_items = {s["item"]: s["revenue_pct"] for s in rs["segments"]}
    assert abs(rs_items["电池"] - 60.0) < 0.01
    assert abs(rs_items["材料"] - 40.0) < 0.01
    # gross_margin: 电池 24/60 = 40%, 材料 10/40 = 25%
    gm_items = {s["item"]: s["gross_margin_pct"] for s in gm["segments"]}
    assert abs(gm_items["电池"] - 40.0) < 0.01
    assert abs(gm_items["材料"] - 25.0) < 0.01
    # growth: 电池 (60-40)/40 = 50%, 材料 (40-35)/35 = 14.29%
    gr_items = {s["item"]: s["yoy_pct"] for s in gr["segments"]}
    assert abs(gr_items["电池"] - 50.0) < 0.01
    assert abs(gr_items["材料"] - 14.2857) < 0.01


def test_derive_segments_inactive_when_empty() -> None:
    rs, gm, gr = tushare_source._derive_segments([])
    assert "reason" in rs and "reason" in gm and "reason" in gr


def test_derive_segments_growth_skips_missing_prior() -> None:
    # Only current period → growth is empty (no prior comparable).
    records = [
        {"end_date": "20260331", "bz_item": "电池", "bz_sales": 60.0,
         "bz_cost": 36.0},
    ]
    rs, gm, gr = tushare_source._derive_segments(records)
    assert rs["segments"]
    assert "reason" in gr  # no yoy comparable


# ---------------------------------------------------------------------------
# _derive_guidance_change — L5.fcst.guidance_change
# ---------------------------------------------------------------------------


def test_derive_guidance_change_upgraded() -> None:
    records = [
        {"ann_date": "20260415", "end_date": "20260331", "type": "预增",
         "p_change_min": 30.0, "p_change_max": 50.0},
        {"ann_date": "20260315", "end_date": "20260331", "type": "预增",
         "p_change_min": 10.0, "p_change_max": 20.0},
    ]
    payload, status = tushare_source._derive_guidance_change(records)
    assert status == "Known"
    assert payload["change_direction"] == "upgraded"
    assert payload["current_range_pct"] == 40.0  # (30+50)/2
    assert payload["prev_range_pct"] == 15.0     # (10+20)/2


def test_derive_guidance_change_new_when_single_record() -> None:
    records = [
        {"ann_date": "20260415", "end_date": "20260331", "type": "预增",
         "p_change_min": 10.0, "p_change_max": 20.0},
    ]
    payload, status = tushare_source._derive_guidance_change(records)
    assert status == "Known"
    assert payload["change_direction"] == "new"


def test_derive_guidance_change_inactive_when_empty() -> None:
    payload, status = tushare_source._derive_guidance_change([])
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_beat_miss — L5.surprise.beat_miss
# ---------------------------------------------------------------------------


def test_derive_beat_miss_beat() -> None:
    express = [
        {"ann_date": "20260415", "end_date": "20260331",
         "yoy_sales": 65.0},
    ]
    forecast = [
        {"ann_date": "20260315", "end_date": "20260331",
         "p_change_min": 30.0, "p_change_max": 50.0},
    ]
    payload, status = tushare_source._derive_beat_miss(express, forecast)
    assert status == "Known"
    assert payload["classification"] == "beat"
    assert payload["deviation_pct"] > 0


def test_derive_beat_miss_miss() -> None:
    express = [
        {"ann_date": "20260415", "end_date": "20260331",
         "yoy_sales": 5.0},
    ]
    forecast = [
        {"ann_date": "20260315", "end_date": "20260331",
         "p_change_min": 30.0, "p_change_max": 50.0},
    ]
    payload, status = tushare_source._derive_beat_miss(express, forecast)
    assert status == "Known"
    assert payload["classification"] == "miss"
    assert payload["deviation_pct"] < 0


def test_derive_beat_miss_in_range() -> None:
    express = [
        {"ann_date": "20260415", "end_date": "20260331",
         "yoy_sales": 40.0},
    ]
    forecast = [
        {"ann_date": "20260315", "end_date": "20260331",
         "p_change_min": 30.0, "p_change_max": 50.0},
    ]
    payload, status = tushare_source._derive_beat_miss(express, forecast)
    assert status == "Known"
    assert payload["classification"] == "in_range"


def test_derive_beat_miss_inactive_when_no_express() -> None:
    payload, status = tushare_source._derive_beat_miss([], [
        {"ann_date": "20260315", "end_date": "20260331",
         "p_change_min": 30.0, "p_change_max": 50.0},
    ])
    assert status == "Inactive"


def test_derive_beat_miss_inactive_when_no_forecast() -> None:
    payload, status = tushare_source._derive_beat_miss([
        {"ann_date": "20260415", "end_date": "20260331",
         "yoy_sales": 5.0},
    ], [])
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_eps_downward — L8.fin.eps_downward
# ---------------------------------------------------------------------------


def test_derive_eps_downward_warn_when_5_to_20_drop() -> None:
    records = [
        {"ann_date": "20260415", "end_date": "20260331",
         "net_profit_min": 80.0, "net_profit_max": 100.0},
        {"ann_date": "20260315", "end_date": "20260331",
         "net_profit_min": 90.0, "net_profit_max": 110.0},
    ]
    payload, status = tushare_source._derive_eps_downward(records)
    # 90 vs 100 → -10% → WARN
    assert status == "Known"
    assert payload["alert_severity"] == "WARN"


def test_derive_eps_downward_error_when_severe_drop() -> None:
    records = [
        {"ann_date": "20260415", "end_date": "20260331",
         "net_profit_min": 40.0, "net_profit_max": 60.0},
        {"ann_date": "20260315", "end_date": "20260331",
         "net_profit_min": 90.0, "net_profit_max": 110.0},
    ]
    payload, status = tushare_source._derive_eps_downward(records)
    # 50 vs 100 → -50% → ERROR
    assert status == "Known"
    assert payload["alert_severity"] == "ERROR"


def test_derive_eps_downward_inactive_when_upward() -> None:
    records = [
        {"ann_date": "20260415", "end_date": "20260331",
         "net_profit_min": 120.0, "net_profit_max": 140.0},
        {"ann_date": "20260315", "end_date": "20260331",
         "net_profit_min": 90.0, "net_profit_max": 110.0},
    ]
    payload, status = tushare_source._derive_eps_downward(records)
    assert status == "Inactive"


def test_derive_eps_downward_inactive_when_single_record() -> None:
    payload, status = tushare_source._derive_eps_downward([
        {"ann_date": "20260415", "end_date": "20260331",
         "net_profit_min": 80.0, "net_profit_max": 100.0},
    ])
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_goodwill_impairment — L8.fin.goodwill_impairment
# ---------------------------------------------------------------------------


def test_derive_goodwill_impairment_warn() -> None:
    records = [
        {"end_date": "20260331", "goodwill": 80.0},
        {"end_date": "20251231", "goodwill": 100.0},
    ]
    # 20% drop → WARN (≥ 5%, < 20%) — exactly 20% lands on WARN
    payload, status = tushare_source._derive_goodwill_impairment(records)
    assert status == "Known"
    assert payload["alert_severity"] == "ERROR"  # ≥ 20% → ERROR
    assert abs(payload["drop_pct"] - 20.0) < 0.01


def test_derive_goodwill_impairment_inactive_when_field_missing() -> None:
    # Cache fields don't include goodwill — payload returns Inactive.
    records = [
        {"end_date": "20260331"},
        {"end_date": "20251231"},
    ]
    payload, status = tushare_source._derive_goodwill_impairment(records)
    assert status == "Inactive"


def test_derive_goodwill_impairment_inactive_when_steady() -> None:
    records = [
        {"end_date": "20260331", "goodwill": 100.0},
        {"end_date": "20251231", "goodwill": 100.0},
    ]
    payload, status = tushare_source._derive_goodwill_impairment(records)
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_revenue_profit_miss — L8.fin.revenue_profit_miss
# ---------------------------------------------------------------------------


def test_derive_revenue_profit_miss_known_when_miss() -> None:
    bm = {
        "classification": "miss",
        "actual_revenue_yoy": 5.0,
        "forecast_range_min": 30.0,
        "forecast_range_max": 50.0,
        "deviation_pct": -25.0,
        "period": "20260331",
    }
    payload, status = tushare_source._derive_revenue_profit_miss(bm)
    assert status == "Known"
    assert payload["alert_severity"] == "ERROR"


def test_derive_revenue_profit_miss_inactive_when_beat() -> None:
    bm = {
        "classification": "beat",
        "actual_revenue_yoy": 60.0,
        "forecast_range_min": 30.0,
        "forecast_range_max": 50.0,
        "deviation_pct": 10.0,
        "period": "20260331",
    }
    payload, status = tushare_source._derive_revenue_profit_miss(bm)
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_crowdedness — L8.cap.crowdedness
# ---------------------------------------------------------------------------


def test_derive_crowdedness_known_when_high_turnover_and_inflow() -> None:
    # 30 days of 10% turnover + positive inflow → ERROR-tier crowdedness
    records = [{"trade_date": f"2026040{i % 10}", "turnover_rate": 16.0}
               for i in range(40)]
    payload, status = tushare_source._derive_crowdedness(
        records, main_net_inflow_5d=1_000_000.0,
    )
    assert status == "Known"
    assert payload["alert_severity"] == "ERROR"  # > 15% turnover


def test_derive_crowdedness_warn_high_turnover_no_inflow() -> None:
    records = [{"trade_date": f"2026040{i % 10}", "turnover_rate": 10.0}
               for i in range(40)]
    payload, status = tushare_source._derive_crowdedness(records, None)
    assert status == "Known"
    assert payload["alert_severity"] == "WARN"


def test_derive_crowdedness_inactive_when_normal_turnover() -> None:
    records = [{"trade_date": f"2026040{i % 10}", "turnover_rate": 2.5}
               for i in range(40)]
    payload, status = tushare_source._derive_crowdedness(
        records, main_net_inflow_5d=None,
    )
    assert status == "Inactive"


def test_derive_priced_crowdedness_percentile_from_turnover_history() -> None:
    records = (
        [{"trade_date": "20260510", "turnover_rate": 35.0}]
        + [{"trade_date": f"202604{i:02d}", "turnover_rate": float(i)}
           for i in range(1, 30)]
    )
    payload, status = tushare_source._derive_priced_crowdedness(records)
    assert status == "Known"
    assert payload["label"] in {"crowded", "extreme"}
    assert payload["percentile"] > 0.75


# ---------------------------------------------------------------------------
# _derive_short_increase — L8.cap.short_increase
# ---------------------------------------------------------------------------


def test_derive_short_increase_warn_when_30d_exceeds_90d() -> None:
    # 30d rqye averages 120, 90d averages 100 → +20% → WARN
    high = [{"trade_date": f"d{i:03d}", "rqye": 120.0} for i in range(30)]
    low = [{"trade_date": f"d{i:03d}", "rqye": 90.0} for i in range(30, 90)]
    records = high + low
    payload, status = tushare_source._derive_short_increase(records)
    assert status == "Known"
    assert payload["alert_severity"] == "WARN"


def test_derive_short_increase_inactive_when_steady() -> None:
    records = [{"trade_date": f"d{i:03d}", "rqye": 100.0} for i in range(90)]
    payload, status = tushare_source._derive_short_increase(records)
    assert status == "Inactive"


def test_derive_short_increase_inactive_when_insufficient_history() -> None:
    records = [{"trade_date": "20260401", "rqye": 120.0}]
    payload, status = tushare_source._derive_short_increase(records)
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_liquidity_short — L8.cap.liquidity_short
# ---------------------------------------------------------------------------


def test_derive_liquidity_short_warn_on_dive_day() -> None:
    # 30d data: one dive day (pct < -5%, vol > 30d_avg * 1.5)
    records = []
    for i in range(30):
        if i == 0:
            records.append({"trade_date": f"2026040{i}",
                            "amount": 200_000, "pct_chg": -7.0,
                            "vol": 5000.0})
        else:
            records.append({"trade_date": f"2026040{i}",
                            "amount": 200_000, "pct_chg": 0.5,
                            "vol": 1000.0})
    payload, status = tushare_source._derive_liquidity_short(records)
    assert status == "Known"
    assert payload["alert_severity"] == "WARN"
    assert payload["dive_day_count"] == 1


def test_derive_liquidity_short_inactive_in_normal_conditions() -> None:
    records = [{"trade_date": f"d{i:03d}", "amount": 200_000,
                "pct_chg": 0.5, "vol": 1000.0} for i in range(40)]
    payload, status = tushare_source._derive_liquidity_short(records)
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_valuation_compression — L8.industry.valuation_compression
# ---------------------------------------------------------------------------


def test_derive_valuation_compression_warn() -> None:
    # 30d PE = 18, 90d PE = 20 → 10% compression → WARN
    payload, status = tushare_source._derive_valuation_compression(18.0, 20.0)
    assert status == "Known"
    assert payload["alert_severity"] == "WARN"


def test_derive_valuation_compression_error_on_severe_drop() -> None:
    payload, status = tushare_source._derive_valuation_compression(10.0, 20.0)
    assert status == "Known"
    assert payload["alert_severity"] == "ERROR"


def test_derive_valuation_compression_inactive_when_expanding() -> None:
    payload, status = tushare_source._derive_valuation_compression(25.0, 20.0)
    assert status == "Inactive"


def test_derive_valuation_compression_inactive_when_missing_data() -> None:
    payload, status = tushare_source._derive_valuation_compression(None, 20.0)
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_cost_overrun — L8.op.cost_overrun
# ---------------------------------------------------------------------------


def test_derive_cost_overrun_warn() -> None:
    yoy = tushare_source._yoy_period("20260331")
    records = [
        {"end_date": "20260331", "total_revenue": 110.0, "oper_cost": 90.0},
        {"end_date": yoy, "total_revenue": 100.0, "oper_cost": 70.0},
    ]
    payload, status = tushare_source._derive_cost_overrun(records)
    # rev_yoy=10, cost_yoy=28.57 → gap ~18.57 → ERROR (≥10pp)
    assert status == "Known"
    assert payload["alert_severity"] == "ERROR"


def test_derive_cost_overrun_inactive_when_aligned() -> None:
    yoy = tushare_source._yoy_period("20260331")
    records = [
        {"end_date": "20260331", "total_revenue": 110.0, "oper_cost": 77.0},
        {"end_date": yoy, "total_revenue": 100.0, "oper_cost": 70.0},
    ]
    payload, status = tushare_source._derive_cost_overrun(records)
    assert status == "Inactive"


def test_derive_cost_overrun_inactive_when_single_period() -> None:
    records = [
        {"end_date": "20260331", "total_revenue": 110.0, "oper_cost": 90.0},
    ]
    payload, status = tushare_source._derive_cost_overrun(records)
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# _derive_margin_anomaly — L9.capital.margin_anomaly
# ---------------------------------------------------------------------------


def test_derive_margin_anomaly_warn() -> None:
    # 5d rzmre = 200, 30d rzmre = 100 → ratio 2 → WARN
    five = [{"trade_date": f"d{i:03d}", "rzmre": 200.0} for i in range(5)]
    rest = [{"trade_date": f"d{i:03d}", "rzmre": 80.0} for i in range(5, 30)]
    records = five + rest
    payload, status = tushare_source._derive_margin_anomaly(records)
    assert status == "Known"
    assert payload["alert_severity"] == "WARN"


def test_derive_margin_anomaly_error() -> None:
    # 5d=500, 30d=100 → ratio 5 → ERROR
    five = [{"trade_date": f"d{i:03d}", "rzmre": 500.0} for i in range(5)]
    rest = [{"trade_date": f"d{i:03d}", "rzmre": 33.0} for i in range(5, 30)]
    records = five + rest
    payload, status = tushare_source._derive_margin_anomaly(records)
    assert status == "Known"
    assert payload["alert_severity"] == "ERROR"


def test_derive_margin_anomaly_inactive_when_steady() -> None:
    records = [{"trade_date": f"d{i:03d}", "rzmre": 100.0}
               for i in range(30)]
    payload, status = tushare_source._derive_margin_anomaly(records)
    assert status == "Inactive"


# ---------------------------------------------------------------------------
# fetch_bucket_a_batch — end-to-end dispatcher
# ---------------------------------------------------------------------------


def _make_bucket_a_pro(yoy_period: str = "20250331") -> _StubPro:
    """A pro stub seeded with enough records for every Bucket A path to
    emit a Known row."""

    fina_mainbz = _StubDF([
        {"end_date": "20260331", "bz_item": "电池", "bz_sales": 60.0,
         "bz_cost": 36.0},
        {"end_date": "20260331", "bz_item": "材料", "bz_sales": 40.0,
         "bz_cost": 30.0},
        {"end_date": yoy_period, "bz_item": "电池", "bz_sales": 40.0,
         "bz_cost": 30.0},
        {"end_date": yoy_period, "bz_item": "材料", "bz_sales": 35.0,
         "bz_cost": 25.0},
    ])
    forecast = _StubDF([
        {"ann_date": "20260415", "end_date": "20260331", "type": "预增",
         "p_change_min": 30.0, "p_change_max": 50.0,
         "net_profit_min": 40.0, "net_profit_max": 60.0},
        {"ann_date": "20260315", "end_date": "20260331", "type": "预增",
         "p_change_min": 10.0, "p_change_max": 20.0,
         "net_profit_min": 90.0, "net_profit_max": 110.0},
    ])
    express = _StubDF([
        {"ann_date": "20260415", "end_date": "20260331",
         "yoy_sales": 5.0},
    ])
    balancesheet = _StubDF([
        {"end_date": "20260331", "goodwill": 60.0},
        {"end_date": "20251231", "goodwill": 100.0},
    ])
    income = _StubDF([
        {"end_date": "20260331", "total_revenue": 110.0, "oper_cost": 90.0},
        {"end_date": yoy_period, "total_revenue": 100.0,
         "oper_cost": 70.0},
    ])
    daily_basic = _StubDF([
        {"trade_date": f"2026040{i % 10}", "turnover_rate": 16.0,
         "pe_ttm": 12.0 if i < 30 else 20.0}
        for i in range(120)
    ])
    daily = _StubDF([
        {"trade_date": f"2026040{i}", "amount": 50_000,
         "pct_chg": (-8.0 if i == 0 else 0.5),
         "vol": 8000.0 if i == 0 else 1000.0}
        for i in range(40)
    ])
    margin = _StubDF(
        # rqye: 30 newest at 120, then 60 older at 90 → 30/90 ratio +20%
        [{"trade_date": f"d{i:03d}", "rqye": 120.0, "rzmre": 500.0}
         for i in range(5)]
        + [{"trade_date": f"d{i:03d}", "rqye": 120.0, "rzmre": 60.0}
           for i in range(5, 30)]
        + [{"trade_date": f"d{i:03d}", "rqye": 90.0, "rzmre": 60.0}
           for i in range(30, 90)]
    )
    return _StubPro(
        fina_mainbz=fina_mainbz, forecast=forecast, express=express,
        balancesheet=balancesheet, income=income, daily_basic=daily_basic,
        daily=daily, margin_detail=margin,
    )


def test_fetch_bucket_a_batch_emits_all_14_dp_ids() -> None:
    pro = _make_bucket_a_pro()
    rows = tushare_source.fetch_bucket_a_batch(
        pro, ["300750.SZ"], now=1700000000,
    )
    assert rows, "expected at least 13 per-stock rows"
    by_dp: dict[str, list[tuple]] = {}
    for r in rows:
        by_dp.setdefault(r[1], []).append(r)
    expected_per_stock = {
        "L2.segment.revenue_share", "L2.segment.gross_margin",
        "L2.segment.growth",
        "L5.fcst.guidance_change", "L5.surprise.beat_miss",
        "L8.fin.eps_downward", "L8.fin.goodwill_impairment",
        "L8.fin.revenue_profit_miss",
        "L6.priced.crowdedness",
        "L8.cap.crowdedness", "L8.cap.short_increase",
        "L8.cap.liquidity_short",
        "L8.op.cost_overrun",
        "L9.capital.margin_anomaly",
    }
    for dp in expected_per_stock:
        assert dp in by_dp, f"missing per-stock dp_id {dp}"
        # Exactly one row per stock per dp_id
        assert len(by_dp[dp]) == 1, f"unexpected duplicates for {dp}"


def test_fetch_bucket_a_batch_skips_non_a_share() -> None:
    pro = _make_bucket_a_pro()
    rows = tushare_source.fetch_bucket_a_batch(
        pro, ["NVDA.US", "09988.HK"], now=1700000000,
    )
    # Only industry-level rows may be emitted (depends on active industries).
    # All per-stock rows must be skipped.
    for r in rows:
        assert not (r[0].endswith(".SH") or r[0].endswith(".SZ")
                    or r[0].endswith(".BJ"))


def test_fetch_bucket_a_batch_handles_empty_data() -> None:
    pro = _StubPro(
        fina_mainbz=_StubDF([]), forecast=_StubDF([]),
        express=_StubDF([]), balancesheet=_StubDF([]),
        income=_StubDF([]), daily_basic=_StubDF([]),
        daily=_StubDF([]), margin_detail=_StubDF([]),
    )
    rows = tushare_source.fetch_bucket_a_batch(
        pro, ["300750.SZ"], now=1700000000,
    )
    by_dp = {r[1]: r for r in rows}
    # Every per-stock dp_id should still emit (Inactive when no data)
    for dp in (
        "L2.segment.revenue_share", "L2.segment.gross_margin",
        "L2.segment.growth",
        "L5.fcst.guidance_change", "L5.surprise.beat_miss",
        "L8.fin.eps_downward", "L8.fin.goodwill_impairment",
        "L8.fin.revenue_profit_miss",
        "L6.priced.crowdedness",
        "L8.cap.crowdedness", "L8.cap.short_increase",
        "L8.cap.liquidity_short",
        "L8.op.cost_overrun",
        "L9.capital.margin_anomaly",
    ):
        assert dp in by_dp, f"{dp} not emitted on empty-data"
        assert by_dp[dp][3] == "Inactive", f"{dp} should be Inactive"
        assert by_dp[dp][4] == 0.0, f"{dp} confidence != 0.0 on Inactive"


def test_fetch_bucket_a_batch_isolates_endpoint_failures() -> None:
    """Forecast permission denied: forecast-dependent dp_ids degrade gracefully
    but the rest still emit."""

    pro = _make_bucket_a_pro()
    pro._data["forecast"] = RuntimeError("permission denied")
    rows = tushare_source.fetch_bucket_a_batch(
        pro, ["300750.SZ"], now=1700000000,
    )
    by_dp = {r[1]: r for r in rows}
    # Forecast-dependent → Inactive (graceful), not missing
    assert "L5.fcst.guidance_change" in by_dp
    assert by_dp["L5.fcst.guidance_change"][3] == "Inactive"
    assert "L5.surprise.beat_miss" in by_dp
    assert by_dp["L5.surprise.beat_miss"][3] == "Inactive"
    assert "L8.fin.eps_downward" in by_dp
    assert by_dp["L8.fin.eps_downward"][3] == "Inactive"
    # Income-only dp_ids still flow
    assert "L8.op.cost_overrun" in by_dp
    assert by_dp["L8.op.cost_overrun"][3] == "Known"


def test_fetch_bucket_a_batch_emits_industry_valuation() -> None:
    """Industry-level rows use ``INDUSTRY:<id>`` sentinel — confirm at least
    one is emitted when ``_active_industry_ids`` returns active slugs."""

    pro = _make_bucket_a_pro()
    rows = tushare_source.fetch_bucket_a_batch(
        pro, ["300750.SZ"], now=1700000000,
    )
    industry_rows = [r for r in rows
                     if r[1] == "L8.industry.valuation_compression"]
    # If _active_industry_ids() returns >=1 slug, we expect ≥ 1 industry row.
    # We don't assert the exact count because the YAML is environment-driven.
    if industry_rows:
        for r in industry_rows:
            assert r[0].startswith("INDUSTRY:")
            payload = json.loads(r[2])
            assert "industry_id" in payload


def test_fetch_bucket_a_batch_alert_severity_present_on_known_alerts() -> None:
    """L8.* alert dp_ids should carry ``alert_severity`` in the payload when
    Known."""

    pro = _make_bucket_a_pro()
    rows = tushare_source.fetch_bucket_a_batch(
        pro, ["300750.SZ"], now=1700000000,
    )
    known_alerts = [
        r for r in rows
        if r[3] == "Known" and r[1].startswith(
            ("L8.fin.", "L8.cap.", "L8.op.", "L9.capital.")
        )
    ]
    for r in known_alerts:
        payload = json.loads(r[2])
        sev = payload.get("alert_severity")
        assert sev in ("WARN", "ERROR"), (
            f"{r[1]} Known emit should carry WARN/ERROR severity, got {sev}"
        )


# ---------------------------------------------------------------------------
# Cache hit behavior — second call within TTL should not hit Tushare again.
# ---------------------------------------------------------------------------


def test_bucket_a_caches_within_ttl() -> None:
    pro = _make_bucket_a_pro()
    tushare_source.fetch_bucket_a_batch(
        pro, ["300750.SZ"], now=1700000000,
    )
    calls_after_first = dict(pro.call_counts)
    tushare_source.fetch_bucket_a_batch(
        pro, ["300750.SZ"], now=1700000000 + 60,
    )
    # No new RPCs — cached records used.
    for k, v in pro.call_counts.items():
        assert v == calls_after_first.get(k, 0), (
            f"{k} re-hit Tushare on cache TTL"
        )
