"""PIT visibility filter + payload-replication tests (offline, no network)."""

import pandas as pd
import pytest

from pit_backtest import collector as C


def test_visible_records_drops_future_filings():
    df = pd.DataFrame([
        {"end_date": "20250930", "f_ann_date": "20251031", "ann_date": "20251031", "total_revenue": 100},
        {"end_date": "20251231", "f_ann_date": "20260411", "ann_date": "20260411", "total_revenue": 200},
        {"end_date": "20260331", "f_ann_date": "20260430", "ann_date": "20260430", "total_revenue": 300},
    ])
    vis = C._visible_records(df, "20260116")
    assert {r["end_date"] for r in vis} == {"20250930"}  # Q3 only; annual+Q1 not yet filed


def test_visible_records_at_t30_includes_annual_not_q1():
    df = pd.DataFrame([
        {"end_date": "20251231", "f_ann_date": "20260411", "ann_date": "20260411", "total_revenue": 200},
        {"end_date": "20260331", "f_ann_date": "20260430", "ann_date": "20260430", "total_revenue": 300},
    ])
    vis = C._visible_records(df, "20260421")  # T-30
    assert {r["end_date"] for r in vis} == {"20251231"}  # annual visible, Q1 not


def test_visible_records_requires_a_date():
    df = pd.DataFrame([{"end_date": "20250930", "total_revenue": 100}])  # no ann/f_ann
    assert C._visible_records(df, "20260116") == []  # dropped — cannot prove knowable


def test_dedup_prefers_update_flag_and_latest_visible():
    recs = [
        {"end_date": "20250930", "f_ann_date": "20251031", "total_revenue": 100, "update_flag": "0"},
        {"end_date": "20250930", "f_ann_date": "20251101", "total_revenue": 105, "update_flag": "1"},
        {"end_date": "20250630", "f_ann_date": "20250827", "total_revenue": 80, "update_flag": "1"},
    ]
    ordered, by_period = C._dedup_by_period(recs, "total_revenue")
    assert ordered[0]["end_date"] == "20250930"
    assert by_period["20250930"]["update_flag"] == "1"  # restatement preferred


def test_emit_income_payloads_and_growth():
    inc = [
        {"end_date": "20250930", "total_revenue": 1000.0, "oper_cost": 900.0,
         "operate_profit": 50.0, "n_income": 40.0, "basic_eps": 0.4,
         "sell_exp": 10, "admin_exp": 20, "rd_exp": 30},
        {"end_date": "20240930", "total_revenue": 800.0},  # yoy compare
    ]
    rows = {dp: p for dp, p, *_ in C.emit_income(inc)}
    assert rows["L5.is.revenue"]["scalar"] == 1000.0
    assert rows["L5.is.revenue"]["period"] == "20250930"
    assert abs(rows["L5.is.gross_margin"]["scalar"] - 0.1) < 1e-9
    assert abs(rows["L5.is.revenue_growth"]["yoy_pct"] - 25.0) < 1e-9  # (1000-800)/800*100


def test_emit_fina_indicator_maps_columns():
    fina = [{"end_date": "20250930", "ann_date": "20251031", "roe": 7.2, "debt_to_assets": 73.0,
             "assets_turn": 0.42}]
    rows = {dp: p for dp, p, *_ in C.emit_fina_indicator(fina)}
    assert rows["L5.fina.roe"] == {"value": 7.2, "period": "20250930", "currency": "CNY", "unit": "ratio_pct"}
    assert rows["L5.fina.asset_turnover"]["unit"] == "ratio"


def test_assert_pit_rows_raises_on_future_observation():
    rows = [("X", "L6.mult.pe", {"trade_date": "20260606"}, "Known", 0.7, "src", 0)]
    with pytest.raises(AssertionError):
        C.assert_pit_rows(rows, "20260605")


def test_assert_pit_rows_allows_future_forecast_period():
    # forecast target period in the future is OK (not an observation date)
    rows = [("X", "L5.fcst.eps_cf", {"period": "2026Q4", "ann_date": "20260101"},
             "Known", 0.8, "src", 0)]
    C.assert_pit_rows(rows, "20260605")  # must not raise
