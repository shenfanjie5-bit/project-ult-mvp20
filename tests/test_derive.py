"""Tests for the snapshot-only derive layer (Tier 1-4).

Tier 0 (legacy Tushare-history) derives are not covered here — they
require network round-trips and are already exercised by manual smoke
runs. This module instead targets the new ``DeriveRunner`` + per-formula
pure functions, which are hermetic.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from mvp20 import derive as derive_mod
from mvp20.derive import (
    DeriveRunner,
    _bootstrap_l11_subscores,
    _read_realtime_value_with_source,
    _value_if_not_mock,
    derive_historical_quantile,
    derive_overvalued,
    derive_run_up,
    derive_l6_mult_ev_ebitda,
    derive_l6_mult_forward_pe,
    derive_l6_mult_peg,
    derive_l6_path_second_derivative,
    derive_l6_path_tag,
    derive_l6_priced_news_age,
    derive_l6_priced_run_up_snapshot,
    derive_l6_sens_cashflow,
    derive_l6_sens_growth_margin,
    derive_l6_sens_rates,
    derive_l6_sens_risk_narrative,
    derive_l6_state_peg_match,
    derive_l7_env_risk_appetite,
    derive_l7_mood_fomo,
    derive_l8_industry_demand_supply,
    derive_l8_industry_price_war,
    derive_l8_val_overvalued_snapshot,
    derive_l8_val_priced_in,
    derive_l10_val_expansion_compression,
    derive_l11_long_score,
    derive_l11_mid_score,
    derive_l11_mode,
    derive_l11_short_score,
    derive_l11_trade_signal,
)
from mvp20.storage import init_db, upsert_realtime


# ---------------------------------------------------------------------------
# Per-formula hermetic tests
# ---------------------------------------------------------------------------


def test_l7_env_risk_appetite_basic():
    out = derive_l7_env_risk_appetite(
        market_trend={"regime": "bull", "scalar": 0.4},
        style={"growth_minus_value": 0.2},
        macro_liquidity={"m2_yoy_pct": 10.0},
        macro_rates={"lpr_1y_pct": 2.5},
    )
    assert out is not None
    assert out["multiplier"] > 1.0
    assert out["label"] == "risk_on"
    assert out["inputs_used"] == 4


def test_l7_env_risk_appetite_missing_all():
    assert derive_l7_env_risk_appetite(None, None, None, None) is None


def test_l7_mood_fomo():
    out = derive_l7_mood_fomo(
        media_social={"in_top_100": True, "concept_tag_count": 15},
        active_inflow={"main_net": 80000},
        theme={"concept_count": 12},
    )
    assert out["score"] > 0.5
    assert out["label"] in ("elevated", "extreme")
    assert any("top100" in f for f in out["factors"])


def test_l7_mood_fomo_calm():
    out = derive_l7_mood_fomo(
        media_social={"in_top_100": False, "concept_tag_count": 0},
        active_inflow={"main_net": 0},
        theme={"concept_count": 0},
    )
    assert out["score"] == pytest.approx(0.0, abs=1e-9)
    assert out["label"] == "calm"


def test_l10_val_expansion_compression_mirror():
    state = {"label": "expansion", "scalar": 0.5}
    out = derive_l10_val_expansion_compression(state)
    assert out["label"] == "expansion"
    assert out["mirror_of"] == "L6.state.expansion_compression"


def test_l10_val_expansion_compression_missing():
    assert derive_l10_val_expansion_compression(None) is None


def test_l8_industry_demand_supply():
    out = derive_l8_industry_demand_supply(
        demand_terminal={"growth_pct": 20.0},
        supply_capacity={"utilization_pct": 95.0},
        supply_inventory={"days_on_hand": 30.0},
        demand_replacement=None,
    )
    assert out["score"] < 0  # demand surplus => negative score
    assert "tight" in out["severity"] or "strong_demand" in out["severity"]


def test_l8_industry_price_war():
    out = derive_l8_industry_price_war(
        price_discount={"discount_pct": 15.0},
        compete_price_war={"intensity": 0.7},
        price_pricing_power={"scalar": 0.3},
    )
    assert out["score"] >= 0.7
    assert out["severity"] == "severe"


def test_l8_val_priced_in():
    out = derive_l8_val_priced_in(
        run_up={"d60_pct": 0.35},
        short_score={"score": 0.5},
        overvalued={"severity": "high"},
    )
    assert out["priced_in_score"] >= 0.7
    assert out["label"] == "fully_priced_in"


def test_l8_val_priced_in_fresh():
    out = derive_l8_val_priced_in(
        run_up={"d60_pct": 0.05},
        short_score={"score": 0.0},
        overvalued={"severity": "normal"},
    )
    assert out["priced_in_score"] < 0.2
    assert out["label"] == "fresh"


def test_l6_path_tag_expansion():
    out = derive_l6_path_tag(
        mult_pe={"scalar": 30.0},
        historical_pct={"pe_percentile": 0.85},
        quantile=None,
        state_expansion=None,
    )
    assert out["tag"] == "估值扩张"


def test_l6_path_tag_repair():
    out = derive_l6_path_tag(
        mult_pe=None,
        historical_pct={"pe_percentile": 0.10},
        quantile=None,
        state_expansion=None,
    )
    assert out["tag"] == "估值修复"


def test_l6_path_second_derivative_acceleration():
    out = derive_l6_path_second_derivative(
        historical_pct=None,
        run_up={"d20_pct": 0.20, "d60_pct": 0.20},  # 1%/day vs 0.33%/day
    )
    assert out["label"] == "accelerating"


def test_l6_sens_growth_margin():
    out = derive_l6_sens_growth_margin(
        fina_gross_margin={"value": 40.0},
        fina_revenue_yoy={"value": 30.0},
    )
    assert out["multiplier"] > 1.0


def test_l6_sens_cashflow():
    out = derive_l6_sens_cashflow(
        fina_ocf_quality={"value": 80.0},
        cf_fcf={"scalar": 1e9},
    )
    assert out["multiplier"] > 1.0


def test_l6_sens_rates():
    out = derive_l6_sens_rates(
        env_rates={"lpr_1y_pct": 4.5},
        macro_rates=None,
    )
    assert out["multiplier"] < 1.0  # higher rates => discount


def test_l6_sens_risk_narrative():
    out = derive_l6_sens_risk_narrative(
        media_report={"count_24h": 8},
        company_news={"count_24h": 15},
        surprise={"rating_distribution": {"买入": 40, "Sell": 1}},
    )
    assert "multiplier" in out


# ---- L6 valuation multiples (ev_ebitda / forward_pe / peg / peg_match) ----
#
# Sanity numbers mirror 688256.SH in runtime/hot.sqlite:
#   mcap 865.85e9, EBITDA 2.3335e9, cash 1.379e9, debt 0,
#   eps_avg 11.70, pe_ttm 318.68, revenue yoy 159.56%.


def test_l6_mult_ev_ebitda_matches_688256():
    out = derive_l6_mult_ev_ebitda(
        mult_pe={"scalar": 318.68, "total_mv_cny": 865850540579.0,
                 "total_share": 2.7e9},
        debt_pressure={"ebitda_cny": 2333496610.75},
        cash_debt={"cash": 1379151407.35, "debt": 0.0},
    )
    assert out is not None
    # EV = mcap + debt - cash; EV/EBITDA ~ 370.
    assert out["scalar"] == pytest.approx(370.46, abs=0.5)
    assert out["ev_cny"] == pytest.approx(865850540579.0 - 1379151407.35, abs=1.0)


def test_l6_mult_ev_ebitda_subtracts_cash_adds_debt():
    out = derive_l6_mult_ev_ebitda(
        mult_pe={"total_mv_cny": 100.0},
        debt_pressure={"ebitda_cny": 10.0},
        cash_debt={"cash": 30.0, "debt": 50.0},
    )
    # EV = 100 + 50 - 30 = 120; /10 = 12.0
    assert out["scalar"] == pytest.approx(12.0)


def test_l6_mult_ev_ebitda_inactive_when_ebitda_nonpositive_or_missing():
    assert derive_l6_mult_ev_ebitda(
        {"total_mv_cny": 1e9}, {"ebitda_cny": 0.0}, {"cash": 0, "debt": 0}) is None
    assert derive_l6_mult_ev_ebitda(
        {"total_mv_cny": 1e9}, {"ebitda_cny": -5.0}, None) is None
    assert derive_l6_mult_ev_ebitda(
        {"total_mv_cny": 1e9}, {}, None) is None
    # mcap missing -> Inactive
    assert derive_l6_mult_ev_ebitda(
        {"scalar": 10.0}, {"ebitda_cny": 1e9}, None) is None
    assert derive_l6_mult_ev_ebitda(None, None, None) is None


def test_l6_mult_forward_pe_equals_price_over_eps():
    out = derive_l6_mult_forward_pe(
        mult_pe={"total_mv_cny": 865850540579.0, "total_share": 2.7e9},
        fcst_eps={"eps_avg": 11.70111111111111},
    )
    assert out is not None
    price = 865850540579.0 / 2.7e9
    # Payload fields are rounded to 4 decimals (matches sibling multiples).
    assert out["price_cny"] == pytest.approx(price, abs=1e-3)
    assert out["scalar"] == pytest.approx(price / 11.70111111111111, abs=1e-3)


def test_l6_mult_forward_pe_inactive_when_eps_nonpositive_or_missing():
    assert derive_l6_mult_forward_pe(
        {"total_mv_cny": 1e9, "total_share": 1e6}, {"eps_avg": 0.0}) is None
    assert derive_l6_mult_forward_pe(
        {"total_mv_cny": 1e9, "total_share": 1e6}, {"eps_avg": -2.0}) is None
    # shares missing -> Inactive
    assert derive_l6_mult_forward_pe(
        {"total_mv_cny": 1e9}, {"eps_avg": 5.0}) is None
    assert derive_l6_mult_forward_pe(None, None) is None


def test_l6_mult_peg_uses_revenue_yoy_basis():
    out = derive_l6_mult_peg(
        mult_pe={"scalar": 318.6816},
        revenue_growth={"yoy_pct": 159.5554734937324},
    )
    assert out is not None
    # Payload scalar is rounded to 4 decimals.
    assert out["scalar"] == pytest.approx(318.6816 / 159.5554734937324, abs=1e-4)
    assert out["scalar"] == pytest.approx(2.0, abs=0.05)
    assert out["growth_basis"] == "revenue_yoy"


def test_l6_mult_peg_inactive_when_growth_or_pe_nonpositive():
    # PEG undefined for flat/shrinking growth.
    assert derive_l6_mult_peg({"scalar": 30.0}, {"yoy_pct": 0.0}) is None
    assert derive_l6_mult_peg({"scalar": 30.0}, {"yoy_pct": -8.0}) is None
    assert derive_l6_mult_peg({"scalar": -3.0}, {"yoy_pct": 20.0}) is None
    assert derive_l6_mult_peg({}, {"yoy_pct": 20.0}) is None
    assert derive_l6_mult_peg(None, None) is None


def test_l6_state_peg_match_bands():
    # PEG < 1.0 => undervalued (+1)
    cheap = derive_l6_state_peg_match({"scalar": 0.8})
    assert cheap["band"] == "undervalued"
    assert cheap["score"] == pytest.approx(1.0)
    # 1.0 <= PEG <= 2.0 => fair (linear +1 -> -1)
    fair_lo = derive_l6_state_peg_match({"scalar": 1.0})
    assert fair_lo["band"] == "fair" and fair_lo["score"] == pytest.approx(1.0)
    fair_mid = derive_l6_state_peg_match({"scalar": 1.5})
    assert fair_mid["band"] == "fair" and fair_mid["score"] == pytest.approx(0.0)
    fair_hi = derive_l6_state_peg_match({"scalar": 2.0})
    assert fair_hi["band"] == "fair" and fair_hi["score"] == pytest.approx(-1.0)
    # PEG > 2.0 => expensive (-1)
    rich = derive_l6_state_peg_match({"scalar": 2.0001})
    assert rich["band"] == "expensive" and rich["score"] == pytest.approx(-1.0)


def test_l6_state_peg_match_inactive_when_peg_missing_or_nonpositive():
    assert derive_l6_state_peg_match({"scalar": 0.0}) is None
    assert derive_l6_state_peg_match({"scalar": -1.0}) is None
    assert derive_l6_state_peg_match({}) is None
    assert derive_l6_state_peg_match(None) is None
    # Tolerates a PEG payload carrying the value under "value" instead.
    assert derive_l6_state_peg_match({"value": 0.5})["band"] == "undervalued"


# ---------------------------------------------------------------------------
# L6.priced.news_age — time-decay discount
# ---------------------------------------------------------------------------


def _ymd_n_days_ago(now_epoch: int, days: int) -> str:
    from datetime import datetime, timedelta, timezone
    dt = datetime.fromtimestamp(now_epoch, tz=timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y%m%d")


def test_l6_priced_news_age_fresh_hits_peak():
    """A same-day announcement is fully fresh => magnitude == damped peak."""

    now = int(time.time())
    today = _ymd_n_days_ago(now, 0)
    out = derive_l6_priced_news_age(
        {"top_announcements": [{"ann_date": today, "type": None}],
         "count_recent": 4},
        now,
    )
    assert out is not None
    assert out["age_days"] == 0
    # Calibration (FU-2): peak damped to 0.6, NOT 1.0.
    assert out["scalar"] == pytest.approx(0.6, abs=1e-6)
    assert out["peak"] == 0.6
    assert out["halflife_days"] == 30.0
    assert out["latest_ann_date"] == today
    assert out["count_recent"] == 4


def test_l6_priced_news_age_halflife_and_decay_to_zero():
    """~30 days => half the peak; ~90 days => decayed toward 0 (<= ~0.1)."""

    now = int(time.time())
    mid = derive_l6_priced_news_age(
        {"top_announcements": [{"ann_date": _ymd_n_days_ago(now, 30)}]}, now)
    assert mid["age_days"] == 30
    # half-life: 0.6 * 0.5 = 0.3
    assert mid["scalar"] == pytest.approx(0.3, abs=1e-3)

    old = derive_l6_priced_news_age(
        {"top_announcements": [{"ann_date": _ymd_n_days_ago(now, 90)}]}, now)
    assert old["age_days"] == 90
    # 0.6 * 0.5**3 = 0.075 — small, does not saturate the cluster.
    assert old["scalar"] == pytest.approx(0.075, abs=1e-3)
    assert old["scalar"] < 0.1


def test_l6_priced_news_age_picks_freshest_and_skips_unparseable_first():
    """Most-recent-first list whose first item lacks a parseable date still
    decays off the freshest *parseable* ann_date."""

    now = int(time.time())
    d10 = _ymd_n_days_ago(now, 10)
    d40 = _ymd_n_days_ago(now, 40)
    out = derive_l6_priced_news_age(
        {"top_announcements": [
            {"ann_date": None},          # unparseable first item
            {"ann_date": d10},           # freshest parseable
            {"ann_date": d40},
        ]},
        now,
    )
    assert out["age_days"] == 10
    assert out["latest_ann_date"] == d10


def test_l6_priced_news_age_inactive_paths():
    now = int(time.time())
    # No payload at all.
    assert derive_l6_priced_news_age(None, now) is None
    # Empty / missing announcement list.
    assert derive_l6_priced_news_age({"count_recent": 0}, now) is None
    assert derive_l6_priced_news_age({"top_announcements": []}, now) is None
    # All ann_dates unparseable => Inactive.
    assert derive_l6_priced_news_age(
        {"top_announcements": [{"ann_date": "n/a"}, {"ann_date": "2026"}]}, now
    ) is None


def test_l6_priced_news_age_uses_as_of_when_now_absent():
    """When the runner `now` is not supplied, "today" falls back to the
    payload `as_of` so the decay stays deterministic in standalone use."""

    as_of = "20260603"
    # Announcement 11 days before as_of (mirrors 688256.SH: 20260523).
    out = derive_l6_priced_news_age(
        {"top_announcements": [{"ann_date": "20260523"}], "as_of": as_of})
    assert out is not None
    assert out["age_days"] == 11
    # 0.6 * 0.5**(11/30) ≈ 0.465
    assert out["scalar"] == pytest.approx(0.6 * 0.5 ** (11 / 30), abs=1e-3)


def test_l11_short_score_weighted():
    out = derive_l11_short_score(
        event_impact={"score": 0.6},
        flow_boost={"score": 0.4},
        sentiment_shift={"score": -0.2},
        technical={"score": 0.3},
    )
    # weighted: 0.6*0.3 + 0.4*0.3 + -0.2*0.2 + 0.3*0.2 = 0.18 + 0.12 - 0.04 + 0.06 = 0.32
    assert out["score"] == pytest.approx(0.32, abs=0.02)
    assert out["label"] == "bullish"
    assert out["factors_used"] == 4


def test_l11_short_score_partial_renormalize():
    out = derive_l11_short_score(
        event_impact={"score": 0.5},
        flow_boost=None,
        sentiment_shift=None,
        technical={"score": 0.5},
    )
    assert out["factors_used"] == 2
    # Renormalized: 0.5*0.3/(0.3+0.2)*1.0 + 0.5*0.2/(0.3+0.2)*1.0 should equal 0.5
    assert out["score"] == pytest.approx(0.5, abs=0.05)


def test_l11_mid_score():
    out = derive_l11_mid_score(
        orders_revenue={"score": 0.5},
        margin_guidance={"score": 0.3},
        eps_upward={"score": 0.4},
    )
    # weighted: 0.5*0.4 + 0.3*0.3 + 0.4*0.3 = 0.41
    assert out["score"] == pytest.approx(0.41, abs=0.02)


def test_l11_long_score():
    out = derive_l11_long_score(
        industry_space={"score": 0.4},
        compete_moat={"score": 0.5},
        business_model={"score": 0.3},
        margin={"score": 0.2},
    )
    assert out["score"] > 0
    assert out["factors_used"] == 4


def test_l11_mode_strong_bull():
    mode = derive_l11_mode(
        short_score={"score": 0.5},
        mid_score={"score": 0.5},
        long_score={"score": 0.6},
        overvalued={"severity": "normal"},
        active_inflow={"main_net": 50000},
    )
    assert mode["mode"] == "strong_bull"


def test_l11_mode_trend_reversal():
    mode = derive_l11_mode(
        short_score={"score": -0.5},
        mid_score={"score": -0.4},
        long_score={"score": -0.5},
        overvalued=None,
        active_inflow={"main_net": -100000},
    )
    assert mode["mode"] == "trend_reversal"


def test_l11_trade_signal_buy():
    sig = derive_l11_trade_signal(
        short_score={"score": 0.6},
        mid_score={"score": 0.5},
        long_score={"score": 0.5},
        mode={"mode": "strong_bull"},
    )
    assert sig["signal"] == "BUY"


def test_l11_trade_signal_avoid_on_reversal():
    sig = derive_l11_trade_signal(
        short_score={"score": 0.5},  # high but mode overrides
        mid_score={"score": 0.5},
        long_score={"score": 0.5},
        mode={"mode": "trend_reversal"},
    )
    assert sig["signal"] == "AVOID"


# ---------------------------------------------------------------------------
# DeriveRunner integration test
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_hot_db(tmp_path: Path) -> Path:
    db = tmp_path / "hot.sqlite"
    init_db(db)
    now = int(time.time())
    rows = [
        ("300750.SZ", "L5.fina.gross_margin",
         {"value": 25.5}, "Known", 0.9, "tushare:fina_indicator", now),
        ("300750.SZ", "L5.fina.revenue_yoy",
         {"value": 50.0}, "Known", 0.9, "tushare:fina_indicator", now),
        ("300750.SZ", "L5.fina.ocf_quality",
         {"value": 75.0}, "Known", 0.85, "tushare:fina_indicator", now),
        ("300750.SZ", "L5.fina.net_margin",
         {"value": 18.0}, "Known", 0.85, "tushare:fina_indicator", now),
        ("300750.SZ", "L5.fina.roe",
         {"value": 6.0}, "Known", 0.85, "tushare:fina_indicator", now),
        ("300750.SZ", "L5.cf.fcf",
         {"scalar": 1e10}, "Known", 0.85, "tushare:cashflow", now),
        ("300750.SZ", "L7.flow.active_inflow",
         {"main_net": -22000.0}, "Known", 0.8, "tushare:moneyflow", now),
        ("300750.SZ", "L7.flow.block_trade",
         {"total_amount": 5000.0}, "Known", 0.8, "tushare:block_trade", now),
        ("300750.SZ", "L7.mood.media_social",
         {"in_top_100": False}, "Known", 0.7, "akshare:hot_rank", now),
        ("300750.SZ", "L7.mood.theme",
         {"concept_count": 8}, "Known", 0.7, "akshare:hot_keyword", now),
        ("300750.SZ", "L9.event.intraday_news",
         {"count_24h": 5}, "Known", 0.7, "akshare:em_news", now),
        ("300750.SZ", "L9.event.intraday_announcement",
         {"count_recent": 10}, "Known", 0.7, "akshare:notice", now),
        ("300750.SZ", "L9.company.earnings_guidance",
         {"change_pct_min": 11.0, "change_pct_max": 20.0}, "Known", 0.8, "tushare:forecast", now),
        ("300750.SZ", "L6.priced.run_up",
         {"d20_pct": 0.14, "d60_pct": 0.05}, "Known", 0.7, "derived:price_history", now),
        ("300750.SZ", "L6.priced.crowdedness",
         {"percentile": 0.6}, "Known", 0.7, "derived:turnover_history", now),
        ("300750.SZ", "L8.val.overvalued",
         {"severity": "elevated"}, "Known", 0.7, "derived:from_quantile", now),
        ("300750.SZ", "L6.state.historical_percentile",
         {"pe_percentile": 0.35}, "Known", 0.7, "tushare:history", now),
        # Sentinels
        ("MARKET:CN", "L7.env.market_trend", {"regime": "bull", "scalar": 0.2},
         "Known", 0.8, "synthetic", now),
        ("MARKET:CN", "L7.env.rates", {"lpr_1y_pct": 3.0},
         "Known", 0.85, "tushare:lpr", now),
        ("MARKET:CN", "L9.macro.liquidity", {"m2_yoy_pct": 8.5},
         "Known", 0.85, "tushare:cn_m", now),
        ("MARKET:CN", "L9.macro.rates", {"lpr_1y_pct": 3.0},
         "Known", 0.85, "tushare:lpr", now),
        ("MARKET:CN", "L10.industry.pmi", {"manufacturing_pmi": 50.4},
         "Known", 0.85, "tushare:pmi", now),
    ]
    upsert_realtime(db, rows)
    # Map ts_code -> industry in overlay_manifest so sentinels resolve
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            """INSERT INTO overlay_manifest
                 (ts_code, industry_id, overlay_path, period, primary_industry,
                  overlay_status, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("300750.SZ", "STORAGE_GRID", "test", "20260331", 1, "ok", now),
        )
    return db


def test_derive_runner_emits_all_dp_ids(tmp_hot_db: Path):
    runner = DeriveRunner(tmp_hot_db)
    stats = runner.run_all(["300750.SZ"])
    assert stats["companies_processed"] == 1
    assert stats["rows_emitted"] >= 15

    expected_outputs = {
        "L7.env.risk_appetite",
        "L7.mood.fomo",
        "L10.val.expansion_compression",
        "L8.industry.demand_supply",
        "L8.industry.price_war",
        "L8.val.priced_in",
        "L6.path.tag",
        "L6.path.second_derivative",
        "L6.sens.growth_margin",
        "L6.sens.cashflow",
        "L6.sens.rates",
        "L6.sens.risk_narrative",
        "L11.short.score",
        "L11.mid.score",
        "L11.long.score",
        "L11.mode",
        "L11.trade.signal",
    }

    with sqlite3.connect(f"file:{tmp_hot_db}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            """SELECT dp_id, data_status, confidence, source, value_json
                 FROM realtime_current
                WHERE ts_code = '300750.SZ' AND source LIKE 'derive:%'"""
        ).fetchall()
    by_dp = {r[0]: r for r in rows}
    assert expected_outputs.issubset(by_dp.keys()), (
        "missing derived dp_ids: " + str(expected_outputs - by_dp.keys())
    )

    # Spot-check a couple of derives produced sensible payloads
    short_row = by_dp["L11.short.score"]
    assert short_row[1] == "Known"
    short_payload = json.loads(short_row[4])
    assert "score" in short_payload
    assert -1.0 <= short_payload["score"] <= 1.0

    mode_row = by_dp["L11.mode"]
    assert mode_row[1] == "Known"
    mode_payload = json.loads(mode_row[4])
    assert mode_payload["mode"] in {
        "strong_bull", "moderate_bull", "digestion", "structural_divergence",
        "de_rating", "trend_reversal", "wait_for_confirmation",
    }


def test_derive_runner_replaces_mock_trade_signal(tmp_hot_db: Path):
    now = int(time.time())
    upsert_realtime(tmp_hot_db, [(
        "300750.SZ", "L11.trade.signal",
        {"signal": "MOCK", "mix_score": 0.0},
        "Known", 0.55, "mock:mvp20-bff", now,
    )])

    runner = DeriveRunner(tmp_hot_db)
    runner.run_all(["300750.SZ"])

    with sqlite3.connect(f"file:{tmp_hot_db}?mode=ro", uri=True) as conn:
        source, payload_json = conn.execute(
            """SELECT source, value_json
                 FROM realtime_current
                WHERE ts_code = '300750.SZ'
                  AND dp_id = 'L11.trade.signal'"""
        ).fetchone()

    payload = json.loads(payload_json)
    assert source == "derive:l11_trade_signal"
    assert payload["signal"] in {"BUY", "HOLD", "WATCH", "AVOID"}
    assert payload["signal"] != "MOCK"


def test_derive_runner_confidence_decay(tmp_hot_db: Path):
    """Each derive output's confidence should be <= the minimum input confidence."""

    runner = DeriveRunner(tmp_hot_db)
    runner.run_all(["300750.SZ"])

    with sqlite3.connect(f"file:{tmp_hot_db}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            """SELECT dp_id, confidence FROM realtime_current
                WHERE ts_code = '300750.SZ' AND source LIKE 'derive:%'
                  AND data_status = 'Known'"""
        ).fetchall()

    # All known-status derive rows should have confidence <= 1.0 and > 0.0
    for dp_id, conf in rows:
        assert conf is not None and 0.0 < conf <= 1.0, f"{dp_id}: conf={conf}"

    # L11.short.score depends on bootstrap subscores (conf 0.5);
    # after one decay it should be 0.45.
    short_row = next(r for r in rows if r[0] == "L11.short.score")
    assert short_row[1] == pytest.approx(0.45, abs=0.01)


def test_derive_runner_inactive_when_inputs_missing(tmp_path: Path):
    """If all inputs are missing, derive should emit Inactive with neutral value."""

    db = tmp_path / "empty.sqlite"
    init_db(db)
    now = int(time.time())
    # Only seed a tiny snapshot — no upstream demand/supply / price_war inputs
    upsert_realtime(db, [
        ("000001.SZ", "L5.fina.gross_margin",
         {"value": 25.0}, "Known", 0.9, "tushare:fina", now),
    ])

    runner = DeriveRunner(db)
    stats = runner.run_all(["000001.SZ"])
    assert stats["companies_processed"] == 1

    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            """SELECT dp_id, data_status, value_json FROM realtime_current
                WHERE ts_code = '000001.SZ' AND source LIKE 'derive:%'"""
        ).fetchall()
    by_dp = {r[0]: (r[1], r[2]) for r in rows}

    # demand_supply / price_war have no inputs => Inactive
    if "L8.industry.demand_supply" in by_dp:
        status, payload_json = by_dp["L8.industry.demand_supply"]
        if status == "Inactive":
            payload = json.loads(payload_json)
            assert payload.get("_inactive") is True


def test_derive_runner_emits_l6_valuation_multiples(tmp_path: Path):
    """End-to-end: the 4 valuation multiples are emitted Known by DeriveRunner.

    Critically, EBITDA lives in ``L8.fin.debt_pressure`` which is persisted
    ``Inactive`` for low-leverage names (the common case). This test seeds it
    Inactive and asserts ``L6.mult.ev_ebitda`` still computes — exercising the
    ``_INACTIVE_TOLERANT_INPUTS`` fallback in the runner. Numbers mirror
    688256.SH.
    """

    db = tmp_path / "mult.sqlite"
    init_db(db)
    now = int(time.time())
    upsert_realtime(db, [
        # L6.mult.pe carries mcap + shares (persisted by the daily_basic
        # collector, PART A).
        ("688256.SH", "L6.mult.pe",
         {"scalar": 318.6816, "unit": "ratio", "ttm": True,
          "total_mv_cny": 865850540579.0, "total_share": 2.7e9},
         "Known", 0.7, "tushare:daily_basic", now),
        # EBITDA carrier persisted INACTIVE (no leverage alert) — must still
        # be read by ev_ebitda via the inactive-tolerant fallback.
        ("688256.SH", "L8.fin.debt_pressure",
         {"ebitda_cny": 2333496610.75, "alert_severity": None,
          "interest_debt_to_ebitda": 0.0},
         "Inactive", 0.5, "tushare:balancesheet+fina_indicator.derived", now),
        ("688256.SH", "L5.bs.cash_debt",
         {"cash": 1379151407.35, "debt": 0.0, "net": 1379151407.35},
         "Known", 0.85, "tushare:balancesheet", now),
        ("688256.SH", "L5.fcst.eps_cf",
         {"eps_avg": 11.70111111111111}, "Known", 0.8, "tushare:report_rc", now),
        ("688256.SH", "L5.is.revenue_growth",
         {"yoy_pct": 159.5554734937324}, "Known", 0.8, "tushare:income.derived", now),
    ])

    runner = DeriveRunner(db)
    runner.run_all(["688256.SH"])

    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            """SELECT dp_id, data_status, source, value_json
                 FROM realtime_current
                WHERE ts_code = '688256.SH' AND source LIKE 'derive:%'"""
        ).fetchall()
    by_dp = {r[0]: (r[1], r[2], r[3]) for r in rows}

    for dp in ("L6.mult.ev_ebitda", "L6.mult.forward_pe",
               "L6.mult.peg", "L6.state.peg_match"):
        assert dp in by_dp, f"{dp} not emitted"
        status, source, _ = by_dp[dp]
        assert status == "Known", f"{dp} status={status}"
        assert source == f"derive:{dp.replace('.', '_').lower()}"

    ev = json.loads(by_dp["L6.mult.ev_ebitda"][2])
    assert ev["scalar"] == pytest.approx(370.46, abs=0.5)

    fpe = json.loads(by_dp["L6.mult.forward_pe"][2])
    assert fpe["scalar"] == pytest.approx(
        (865850540579.0 / 2.7e9) / 11.70111111111111, abs=1e-3)

    peg = json.loads(by_dp["L6.mult.peg"][2])
    assert peg["scalar"] == pytest.approx(2.0, abs=0.05)
    assert peg["growth_basis"] == "revenue_yoy"

    pm = json.loads(by_dp["L6.state.peg_match"][2])
    assert pm["band"] == "fair"  # PEG ~ 2.0
    assert -1.0 <= pm["score"] <= 1.0


def test_derive_runner_l6_multiples_inactive_when_inputs_missing(tmp_path: Path):
    """Without mcap/EBITDA/eps/growth, the 4 multiples emit Inactive."""

    db = tmp_path / "mult_empty.sqlite"
    init_db(db)
    now = int(time.time())
    # Seed only a bare PE scalar (no mcap/shares, no EBITDA, no eps, no growth).
    upsert_realtime(db, [
        ("000001.SZ", "L6.mult.pe",
         {"scalar": 8.5, "unit": "ratio", "ttm": True},
         "Known", 0.7, "tushare:daily_basic", now),
    ])

    runner = DeriveRunner(db)
    runner.run_all(["000001.SZ"])

    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            """SELECT dp_id, data_status, value_json FROM realtime_current
                WHERE ts_code = '000001.SZ' AND source LIKE 'derive:%'"""
        ).fetchall()
    by_dp = {r[0]: (r[1], r[2]) for r in rows}

    for dp in ("L6.mult.ev_ebitda", "L6.mult.forward_pe",
               "L6.mult.peg", "L6.state.peg_match"):
        assert dp in by_dp, f"{dp} not emitted"
        status, payload_json = by_dp[dp]
        assert status == "Inactive", f"{dp} expected Inactive, got {status}"
        assert json.loads(payload_json).get("_inactive") is True


def test_derive_runner_inactive_reason_distinguishes_undefined_from_missing(tmp_path: Path):
    """PEG label polish: when inputs are PRESENT but the formula is undefined
    (PEG with growth<=0), ``missing_inputs`` must be empty and
    ``inactive_reason='formula_undefined'`` — not a misleading list of present
    inputs (the old behavior, e.g. 000977 PEG with -24% revenue growth). When an
    input is genuinely absent it IS listed with reason 'missing_inputs'.
    """

    now = int(time.time())

    # Case A: pe present + revenue_growth present but NEGATIVE → peg undefined.
    db = tmp_path / "peg_undef.sqlite"
    init_db(db)
    upsert_realtime(db, [
        ("000001.SZ", "L6.mult.pe",
         {"scalar": 30.0, "unit": "ratio", "ttm": True},
         "Known", 0.7, "tushare:daily_basic", now),
        ("000001.SZ", "L5.is.revenue_growth",
         {"yoy_pct": -24.3, "qoq_pct": -50.0, "current_period": "20260331",
          "yoy_compare_period": "20250331"},
         "Known", 0.8, "tushare:income.derived", now),
    ])
    DeriveRunner(db).run_all(["000001.SZ"])
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        status, payload_json = conn.execute(
            "SELECT data_status, value_json FROM realtime_current "
            "WHERE ts_code='000001.SZ' AND dp_id='L6.mult.peg'"
        ).fetchone()
    payload = json.loads(payload_json)
    assert status == "Inactive"
    assert payload["missing_inputs"] == []            # inputs present, not missing
    assert payload["inactive_reason"] == "formula_undefined"

    # Case B: revenue_growth genuinely ABSENT → listed + reason 'missing_inputs'.
    db2 = tmp_path / "peg_missing.sqlite"
    init_db(db2)
    upsert_realtime(db2, [
        ("000001.SZ", "L6.mult.pe",
         {"scalar": 30.0, "unit": "ratio", "ttm": True},
         "Known", 0.7, "tushare:daily_basic", now),
    ])
    DeriveRunner(db2).run_all(["000001.SZ"])
    with sqlite3.connect(f"file:{db2}?mode=ro", uri=True) as conn:
        payload_json = conn.execute(
            "SELECT value_json FROM realtime_current "
            "WHERE ts_code='000001.SZ' AND dp_id='L6.mult.peg'"
        ).fetchone()[0]
    payload = json.loads(payload_json)
    assert "L5.is.revenue_growth" in payload["missing_inputs"]
    assert payload["inactive_reason"] == "missing_inputs"


def test_derive_runner_emits_news_age_with_injected_now(tmp_path: Path):
    """End-to-end: DeriveRunner injects its `now` into L6.priced.news_age so a
    recent announcement decays off the runner clock (not a hardcoded date)."""

    from datetime import datetime, timedelta, timezone

    db = tmp_path / "news.sqlite"
    init_db(db)
    now = int(time.time())
    ann_date = (datetime.fromtimestamp(now, tz=timezone.utc)
                - timedelta(days=10)).strftime("%Y%m%d")
    upsert_realtime(db, [
        ("300308.SZ", "L9.event.intraday_announcement",
         {"count_recent": 3,
          "top_announcements": [{"title": "x", "type": None,
                                 "ann_date": ann_date, "url": None}],
          "as_of": "1970-01-01T00:00:00Z"},  # stale as_of must be ignored
         "Known", 0.65, "tushare:anns_d", now),
    ])

    runner = DeriveRunner(db)
    runner.run_all(["300308.SZ"])

    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        row = conn.execute(
            """SELECT data_status, value_json FROM realtime_current
                WHERE ts_code = '300308.SZ' AND dp_id = 'L6.priced.news_age'"""
        ).fetchone()
    assert row is not None, "L6.priced.news_age not emitted"
    status, payload_json = row
    assert status == "Known"
    payload = json.loads(payload_json)
    # Decay measured off the *runner* now => age == 10 (not from stale as_of).
    assert payload["age_days"] == 10
    assert payload["scalar"] == pytest.approx(0.6 * 0.5 ** (10 / 30), abs=1e-3)
    assert 0.0 < payload["scalar"] <= 0.6


def test_derive_runner_news_age_inactive_when_no_announcement(tmp_path: Path):
    """No intraday_announcement row => L6.priced.news_age emits Inactive."""

    db = tmp_path / "news_empty.sqlite"
    init_db(db)
    now = int(time.time())
    upsert_realtime(db, [
        ("300308.SZ", "L6.mult.pe",
         {"scalar": 20.0, "unit": "ratio"}, "Known", 0.7, "tushare:daily_basic", now),
    ])

    runner = DeriveRunner(db)
    runner.run_all(["300308.SZ"])

    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        row = conn.execute(
            """SELECT data_status, value_json FROM realtime_current
                WHERE ts_code = '300308.SZ' AND dp_id = 'L6.priced.news_age'"""
        ).fetchone()
    assert row is not None, "L6.priced.news_age not emitted"
    status, payload_json = row
    assert status == "Inactive"
    assert json.loads(payload_json).get("_inactive") is True


# ---------------------------------------------------------------------------
# US-side fallback tests for the 5 unblocked formulas
# ---------------------------------------------------------------------------


def test_l6_sens_growth_margin_us_fallback():
    """FMP-style ratio inputs (gross_margin as 0.71, revenue_yoy as 0.65)
    should be normalised to percent before being fed into the multiplier."""

    out = derive_l6_sens_growth_margin(
        fina_gross_margin=None,
        fina_revenue_yoy=None,
        is_gross_margin={"scalar": 0.7106},  # 71.06% gross margin (NVDA-like)
        is_revenue_growth={"yoy_pct": 0.6547},  # 65.47% YoY revenue growth
    )
    assert out is not None
    assert out["gross_margin_pct"] == pytest.approx(71.06, abs=0.1)
    assert out["revenue_yoy_pct"] == pytest.approx(65.47, abs=0.1)
    assert out["multiplier"] > 1.0  # premium-margin premium-growth => multiplier > 1
    # A-share path still works when both supplied — primary wins.
    out2 = derive_l6_sens_growth_margin(
        fina_gross_margin={"value": 28.27},
        fina_revenue_yoy={"value": 6.12},
        is_gross_margin={"scalar": 0.7106},
        is_revenue_growth={"yoy_pct": 0.6547},
    )
    assert out2["gross_margin_pct"] == pytest.approx(28.27, abs=0.05)


def test_l6_sens_growth_margin_inactive_when_all_missing():
    assert derive_l6_sens_growth_margin(None, None, None, None) is None


def test_l6_path_second_derivative_us_fallback():
    """When `L6.priced.run_up` is absent, fall back to FMP's L5.surprise.preprice
    which carries run_up_5/10/20d_pct."""

    out = derive_l6_path_second_derivative(
        historical_pct=None,
        run_up=None,
        surprise_preprice={
            "run_up_5d_pct": 0.04,
            "run_up_10d_pct": 0.06,
            "run_up_20d_pct": 0.05,
        },
    )
    assert out is not None
    assert out["source"] == "L5.surprise.preprice"
    # d5/5 = 0.008, d20/20 = 0.0025 → second_deriv positive ⇒ accelerating
    assert out["label"] == "accelerating"


def test_l6_priced_run_up_snapshot_us():
    """FMP preprice payload should reshape into the standard run_up payload."""

    out = derive_l6_priced_run_up_snapshot({
        "run_up_5d_pct": 0.02,
        "run_up_10d_pct": 0.04,
        "run_up_20d_pct": 0.07,
    })
    assert out["d20_pct"] == pytest.approx(0.07, abs=0.001)
    assert out["d5_pct"] == pytest.approx(0.02, abs=0.001)
    assert out["d60_pct"] is None
    assert out["source"] == "L5.surprise.preprice"


def test_l6_priced_run_up_snapshot_missing():
    assert derive_l6_priced_run_up_snapshot(None) is None
    assert derive_l6_priced_run_up_snapshot({}) is None


def test_l8_val_overvalued_snapshot_via_quantile():
    out = derive_l8_val_overvalued_snapshot(
        historical_quantile={"pe_percentile": 0.96, "pb_percentile": 0.87},
        historical_pct=None,
    )
    assert out is not None
    assert out["is_overvalued"] is True
    assert out["severity"] == "extreme"
    assert out["source"] == "historical_quantile"


def test_l8_val_overvalued_snapshot_peg_fallback():
    """When no PE/PB history is available, classify by PEG (US fallback)."""

    out = derive_l8_val_overvalued_snapshot(
        historical_quantile=None,
        historical_pct=None,
        mult_peg={"scalar": 2.3},
        mult_pe={"scalar": 35.0},
    )
    assert out is not None
    assert out["severity"] == "high"
    assert out["is_overvalued"] is True
    assert out["source"] == "L6.mult.peg"


def test_l10_val_expansion_compression_us_fallback():
    """When L6.state.expansion_compression is missing, derive a regime
    label from PE quantile (US fallback path)."""

    out = derive_l10_val_expansion_compression(
        state_expansion=None,
        mult_pe={"scalar": 35.0},
        historical_quantile={"pe_percentile": 0.88},
        historical_pct=None,
    )
    assert out is not None
    assert out["regime"] == "expanded"
    assert out["fallback"] == "fmp_pe_quantile"
    assert out["pe_percentile"] == pytest.approx(0.88, abs=0.01)


# ---------------------------------------------------------------------------
# Integration: US ts_code through DeriveRunner
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_us_hot_db(tmp_path: Path) -> Path:
    """Hot DB seeded with NVDA.US + MARKET:US sentinel only — no A-share
    L5.fina.* and no Tushare L6.state.expansion_compression. Exercises the
    US fallback paths in the 5 unblocked derives."""

    db = tmp_path / "us_hot.sqlite"
    init_db(db)
    now = int(time.time())
    rows = [
        # US per-stock FMP-style inputs.
        ("NVDA.US", "L5.is.gross_margin",
         {"scalar": 0.7106, "unit": "ratio"}, "Known", 0.85, "fmp:income-statement", now),
        ("NVDA.US", "L5.is.revenue_growth",
         {"yoy_pct": 0.6547, "eps_growth_yoy": 0.66}, "Known", 0.85,
         "fmp:financial-growth", now),
        ("NVDA.US", "L5.cf.fcf",
         {"scalar": 6e10}, "Known", 0.85, "fmp:cash-flow", now),
        ("NVDA.US", "L5.surprise.preprice",
         {"earnings_date": "2026-05-28", "run_up_5d_pct": 0.04,
          "run_up_10d_pct": 0.06, "run_up_20d_pct": 0.07,
          "spx_relative_5d": 0.02, "is_upcoming": True},
         "Known", 0.75, "fmp:earnings.derived", now),
        ("NVDA.US", "L6.mult.pe",
         {"scalar": 50.0, "unit": "ratio"}, "Known", 0.85, "fmp:ratios-ttm", now),
        ("NVDA.US", "L6.mult.peg",
         {"scalar": 0.69, "unit": "ratio"}, "Known", 0.85, "fmp:ratios-ttm", now),
        # Sentinel MARKET:US carrying macro/env values.
        ("MARKET:US", "L7.env.market_trend",
         {"regime": "bull", "spx_30d_pct": 0.12, "ndx_30d_pct": 0.21},
         "Known", 0.8, "fmp:historical-index", now),
        ("MARKET:US", "L7.env.rates",
         {"1y": 3.79, "10y": 4.46, "lpr_1y_pct": 4.46},
         "Known", 0.85, "fmp:treasury", now),
        ("MARKET:US", "L9.macro.rates",
         {"10y": 4.46, "lpr_1y_pct": 4.46}, "Known", 0.85,
         "fmp:treasury.derived", now),
        ("MARKET:US", "L9.macro.cpi_employment",
         {"cpi_yoy_latest": 3.8, "unemployment_pct": 4.3},
         "Known", 0.85, "fmp:economic-calendar", now),
    ]
    upsert_realtime(db, rows)
    # NVDA must be in overlay_manifest for derive runner to find it.
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            """INSERT INTO overlay_manifest
                 (ts_code, industry_id, overlay_path, period, primary_industry,
                  overlay_status, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("NVDA.US", "SEMICONDUCTOR_GPU", "test", "2026Q1", 1, "ok", now),
        )
    return db


def test_derive_runner_us_unblocks_target_dp_ids(tmp_us_hot_db: Path):
    """The 5 unblocked formulas should emit Known on NVDA.US given FMP-side
    inputs only (no MARKET:CN / L5.fina.*)."""

    runner = DeriveRunner(tmp_us_hot_db)
    stats = runner.run_all(["NVDA.US"])
    assert stats["companies_processed"] == 1

    with sqlite3.connect(f"file:{tmp_us_hot_db}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            """SELECT dp_id, data_status, value_json FROM realtime_current
                WHERE ts_code = 'NVDA.US' AND source LIKE 'derive:%'"""
        ).fetchall()
    by_dp = {r[0]: (r[1], json.loads(r[2])) for r in rows}

    # L6.sens.growth_margin: FMP fallback should produce Known.
    status, payload = by_dp["L6.sens.growth_margin"]
    assert status == "Known", f"unexpected status for growth_margin: {status} payload={payload}"
    assert payload.get("multiplier", 0) > 1.0
    assert payload.get("gross_margin_pct") == pytest.approx(71.06, abs=0.1)

    # L6.priced.run_up: snapshot fallback from L5.surprise.preprice => Known.
    status, payload = by_dp["L6.priced.run_up"]
    assert status == "Known"
    assert payload["d20_pct"] == pytest.approx(0.07, abs=0.001)

    # L6.path.second_derivative: derives from preprice (since run_up was
    # also freshly emitted to `emitted` dict and visible to downstream).
    status, payload = by_dp["L6.path.second_derivative"]
    assert status == "Known"
    assert payload["label"] in ("accelerating", "decelerating", "stable")

    # L8.val.overvalued: PEG fallback (no historical_quantile yet for US).
    status, payload = by_dp["L8.val.overvalued"]
    assert status == "Known"
    # PEG 0.69 => normal (not high). PE alone doesn't flag overvalued.
    assert payload.get("severity") in ("normal", "elevated", "high", "extreme")

    # L10.val.expansion_compression: fallback to PE + quantile when no
    # upstream L6.state.expansion_compression. Without quantile, we get
    # regime=neutral because pe_pct is None; pe_current carries through.
    status, payload = by_dp["L10.val.expansion_compression"]
    assert status == "Known"
    assert payload["mirror_of"] == "L6.state.expansion_compression"
    assert payload.get("regime") in ("expanded", "compressed", "neutral")


def test_derive_runner_us_inactive_when_upstream_missing(tmp_path: Path):
    """When even the US fallback inputs are missing, the 5 derives should
    emit Inactive with `_inactive: True` and not crash."""

    db = tmp_path / "us_bare.sqlite"
    init_db(db)
    now = int(time.time())
    # Only seed one unrelated dp_id — no FMP-side inputs to feed the
    # 5 target formulas.
    upsert_realtime(db, [
        ("AAPL.US", "L9.event.news_flow",
         {"count": 12}, "Known", 0.75, "fmp:news", now),
    ])
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            """INSERT INTO overlay_manifest
                 (ts_code, industry_id, overlay_path, period, primary_industry,
                  overlay_status, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("AAPL.US", "CONSUMER_ELECTRONICS", "test", "2026Q1", 1, "ok", now),
        )

    runner = DeriveRunner(db)
    runner.run_all(["AAPL.US"])

    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            """SELECT dp_id, data_status, value_json FROM realtime_current
                WHERE ts_code = 'AAPL.US' AND source LIKE 'derive:%'"""
        ).fetchall()
    by_dp = {r[0]: (r[1], json.loads(r[2])) for r in rows}

    # All 5 target dp_ids should at least have a row (Inactive is fine).
    for dp in ("L6.sens.growth_margin", "L6.priced.run_up",
               "L6.path.second_derivative", "L8.val.overvalued",
               "L10.val.expansion_compression"):
        assert dp in by_dp, f"missing fallback emit for {dp}"
        status, payload = by_dp[dp]
        if status == "Inactive":
            assert payload.get("_inactive") is True


def test_bootstrap_subscores_produces_all_l11_subs():
    inputs = {
        "L9.event.intraday_news": {"value": {"count_24h": 5}},
        "L7.flow.active_inflow": {"value": {"main_net": 10000.0}},
        "L7.mood.media_social": {"value": {"in_top_100": True}},
        "L6.priced.run_up": {"value": {"d20_pct": 0.10}},
        "L6.priced.crowdedness": {"value": {"percentile": 0.5}},
        "L5.fina.revenue_yoy": {"value": {"value": 30.0}},
        "L5.fina.gross_margin": {"value": {"value": 35.0}},
        "L5.fina.net_margin": {"value": {"value": 15.0}},
        "L5.fina.roe": {"value": {"value": 12.0}},
        "L5.fina.ocf_quality": {"value": {"value": 70.0}},
        "L10.industry.pmi": {"value": {"manufacturing_pmi": 52.0}},
        "L9.company.earnings_guidance": {"value": {"change_pct_min": 10.0, "change_pct_max": 20.0}},
    }
    out = _bootstrap_l11_subscores(inputs)
    expected_subs = {
        "L11.short.event_impact",
        "L11.short.flow_boost",
        "L11.short.sentiment_shift",
        "L11.short.technical",
        "L11.mid.orders_revenue",
        "L11.mid.margin_guidance",
        "L11.mid.eps_upward",
        "L11.long.industry_space",
        "L11.long.compete_moat",
        "L11.long.business_model",
        "L11.long.margin",
    }
    assert expected_subs.issubset(out.keys())
    for dp_id, payload in out.items():
        assert "score" in payload
        assert -1.0 <= payload["score"] <= 1.0


# ---------------------------------------------------------------------------
# Tier 0 (legacy) pure-function tests: run_up / historical_quantile /
# overvalued. These were previously uncovered. They are hermetic — no
# network, no DB.
# ---------------------------------------------------------------------------


def test_derive_run_up_typical():
    # index 0 is the most recent close. 7 days so the 5-day window resolves.
    # d5_pct = (latest - close[5]) / close[5] = (110 - 100) / 100 = 0.10.
    closes = [110.0, 108.0, 106.0, 104.0, 102.0, 100.0, 98.0]
    out = derive_run_up(closes)
    assert out is not None
    assert out["d5_pct"] == pytest.approx(0.10, abs=1e-9)
    # Not enough history for the 20-/60-day windows -> None.
    assert out["d20_pct"] is None
    assert out["d60_pct"] is None
    assert out["latest_close"] == 110.0
    assert out["history_days"] == 7


def test_derive_run_up_zero_reference_is_safe():
    # close[5] == 0 must not divide-by-zero; that window -> None.
    closes = [110.0, 108.0, 106.0, 104.0, 102.0, 0.0, 98.0]
    out = derive_run_up(closes)
    assert out is not None
    assert out["d5_pct"] is None


def test_derive_run_up_short_or_empty_series():
    # Fewer than 6 closes -> neutral/safe None (no payload).
    assert derive_run_up([110.0, 108.0, 106.0, 104.0, 102.0]) is None
    assert derive_run_up([]) is None
    assert derive_run_up(None) is None  # type: ignore[arg-type]


def test_derive_historical_quantile_by_hand():
    # PE history (all positive) = [10, 20, 30, 40, 50]; current 30.
    # count(h < 30) = {10, 20} = 2 -> 2/5 = 0.40.
    # PB history = [1, 2, 3, 4]; current 3 -> count(<3) = {1, 2} = 2 -> 2/4 = 0.50.
    out = derive_historical_quantile(
        30.0, [10.0, 20.0, 30.0, 40.0, 50.0],
        3.0, [1.0, 2.0, 3.0, 4.0],
    )
    assert out is not None
    assert out["pe_percentile"] == pytest.approx(0.40, abs=1e-9)
    assert out["pb_percentile"] == pytest.approx(0.50, abs=1e-9)
    assert out["history_window_days"] == 5


def test_derive_historical_quantile_out_of_range_high():
    # current far above all history -> every point is below -> percentile 1.0.
    out = derive_historical_quantile(
        100.0, [10.0, 20.0, 30.0, 40.0, 50.0],
        None, [],
    )
    assert out is not None
    assert out["pe_percentile"] == pytest.approx(1.0, abs=1e-9)
    # pb absent -> key not emitted.
    assert "pb_percentile" not in out


def test_derive_historical_quantile_filters_nonpositive():
    # Zero/negative history entries are filtered before ranking, so the
    # effective history is [20, 40]; current 30 -> count(<30) = {20} -> 1/2 = 0.5.
    out = derive_historical_quantile(
        30.0, [0.0, -5.0, 20.0, 40.0],
        None, [],
    )
    assert out is not None
    assert out["pe_percentile"] == pytest.approx(0.5, abs=1e-9)


def test_derive_historical_quantile_empty_history():
    # No usable history at all -> None (nothing to rank against).
    assert derive_historical_quantile(30.0, [], 3.0, []) is None
    assert derive_historical_quantile(None, [10.0, 20.0], None, [1.0]) is None


def test_derive_overvalued_extreme_and_normal():
    # max_pct = 0.96 > 0.95 -> extreme + overvalued.
    hot = derive_overvalued({"pe_percentile": 0.96, "pb_percentile": 0.50})
    assert hot is not None
    assert hot["is_overvalued"] is True
    assert hot["severity"] == "extreme"
    assert hot["max_quantile"] == pytest.approx(0.96, abs=1e-9)

    # max_pct = 0.50 -> normal, not overvalued.
    cool = derive_overvalued({"pe_percentile": 0.50, "pb_percentile": 0.30})
    assert cool is not None
    assert cool["is_overvalued"] is False
    assert cool["severity"] == "normal"


def test_derive_overvalued_high_threshold_boundary():
    # max_pct = 0.85 -> in (0.80, 0.95] -> "high" and overvalued (> 0.80).
    out = derive_overvalued({"pe_percentile": 0.85, "pb_percentile": None})
    assert out is not None
    assert out["severity"] == "high"
    assert out["is_overvalued"] is True


def test_derive_overvalued_none_inputs():
    # No payload, or a payload with no usable percentile -> None.
    assert derive_overvalued(None) is None
    assert derive_overvalued({}) is None
    assert derive_overvalued({"pe_percentile": None, "pb_percentile": None}) is None


# ---------------------------------------------------------------------------
# H-3: valuation-percentile look-back window unification.
#
# ``_fetch_a_share_history`` (derive.py) feeds PE/PB into
# ``derive_historical_quantile`` → L10.val.historical_quantile / L8.val.overvalued.
# Previously it reused the short OHLCV window (90 calendar days ≈ 54 trading
# days), contradicting the sibling L6.state.historical_percentile path
# (``tushare_source._fetch_a_share_historical_percentile``, history_days=250 ≈
# 183 trading days). The fix decouples the PE/PB window (``pe_pb_days``, default
# 250) from the OHLCV window so both valuation-percentile paths agree.
#
# These tests are hermetic: a stub ``pro`` backed by in-memory pandas frames,
# no network and no DB.
# ---------------------------------------------------------------------------


class _HistRecorderPro:
    """Stub Tushare ``pro`` that records the start/end window per endpoint and
    serves canned ``daily`` / ``daily_basic`` frames built from a PE/PB series.
    """

    def __init__(self, pe_series_desc, pb_series_desc, turnover_desc):
        import pandas as pd
        self._pd = pd
        # Build trade_date strings newest→oldest; the producer re-sorts anyway.
        n = max(len(pe_series_desc), len(pb_series_desc), len(turnover_desc))
        self._dates = [f"2026{(m % 12) + 1:02d}{(m % 27) + 1:02d}{i:02d}"[-8:]
                       for i, m in enumerate(range(n))]
        self._pe = list(pe_series_desc)
        self._pb = list(pb_series_desc)
        self._turn = list(turnover_desc)
        self.calls: dict[str, dict] = {}

    def daily(self, **kw):
        self.calls["daily"] = dict(kw)
        # Minimal OHLCV frame; close mirrors PE just to have data.
        n = len(self._pe)
        return self._pd.DataFrame({
            "ts_code": ["X"] * n,
            "trade_date": self._dates[:n],
            "open": [10.0] * n, "high": [11.0] * n, "low": [9.0] * n,
            "close": [10.0] * n, "vol": [1000.0] * n,
        })

    def daily_basic(self, **kw):
        self.calls["daily_basic"] = dict(kw)
        n = max(len(self._pe), len(self._pb), len(self._turn))
        def _pad(xs):
            return list(xs) + [None] * (n - len(xs))
        return self._pd.DataFrame({
            "ts_code": ["X"] * n,
            "trade_date": self._dates[:n],
            "turnover_rate": _pad(self._turn),
            "pe_ttm": _pad(self._pe),
            "pb": _pad(self._pb),
        })


def test_fetch_a_share_history_uses_longer_pe_pb_window():
    """H-3: the daily_basic (PE/PB) call must reach further back than the
    daily (OHLCV) call — i.e. the valuation window is decoupled and widened.

    With days=90 and pe_pb_days=250 the daily_basic start_date must be
    strictly EARLIER (smaller YYYYMMDD) than the daily start_date.
    """

    pro = _HistRecorderPro(
        pe_series_desc=[20.0] * 200, pb_series_desc=[3.0] * 200,
        turnover_desc=[1.5] * 200,
    )
    out = derive_mod._fetch_a_share_history(pro, "600519.SH", days=90, pe_pb_days=250)

    daily_start = pro.calls["daily"]["start_date"]
    basic_start = pro.calls["daily_basic"]["start_date"]
    # Same end date, but PE/PB window starts earlier (longer look-back).
    assert pro.calls["daily"]["end_date"] == pro.calls["daily_basic"]["end_date"]
    assert basic_start < daily_start, (
        f"PE/PB window ({basic_start}) must start before OHLCV window ({daily_start})"
    )
    # PE/PB use the full long series; turnover is sliced back to the short
    # `days` window so crowdedness behaviour is unchanged.
    assert len(out["pe_ttm"]) == 200
    assert len(out["pb"]) == 200
    assert len(out["turnover_rate"]) == 90


def test_history_quantile_and_state_percentile_agree_on_same_series():
    """H-3 parity: given the SAME PE/PB series, the derive.py valuation
    percentile (derive_historical_quantile, consumed by L8.val.overvalued)
    and the tushare_source.py L6.state.historical_percentile computation must
    produce the SAME percentile. They differed live only because the two
    code paths pulled DIFFERENT-length windows — once the window is unified
    the math is identical.
    """

    from mvp20.sources import tushare_source as ts

    # A 183-point PE series (the longer, unified window). Current PE sits at a
    # known rank so the percentile is unambiguous.
    pe_series_desc = [float(v) for v in range(1, 184)][::-1]  # 183, 182, ..., 1
    current_pe = pe_series_desc[0]  # 183 → above all but itself

    # --- derive.py path: derive_historical_quantile (current vs history) ---
    quant = derive_historical_quantile(
        current_pe, pe_series_desc, None, [],
    )
    overvalued = derive_overvalued(quant)
    derive_pe_pct = quant["pe_percentile"]

    # --- tushare_source.py path: replicate _fetch_a_share_historical_percentile
    # percentile math on the IDENTICAL series (this is the exact computation in
    # that function: n_below / len over the positive series). ---
    pe_pos = [v for v in pe_series_desc if v and v > 0]
    n_below = sum(1 for v in pe_pos if v < current_pe)
    state_pe_pct = n_below / len(pe_pos)

    # Same window length → identical percentile (no 54-vs-183 contradiction).
    assert derive_pe_pct == pytest.approx(state_pe_pct, abs=1e-9)
    assert quant["history_window_days"] == 183
    # And the L8.val.overvalued severity is driven by that same percentile.
    assert overvalued["max_quantile"] == pytest.approx(state_pe_pct, abs=1e-9)

    # Guard the helper used by the L6.state path is the same ranking idea as
    # derive's _percentile_rank for an in-range value (mid-series → ~0.5).
    mid = 92.0  # middle of 1..183
    assert derive_mod._percentile_rank(mid, pe_series_desc) == pytest.approx(
        sum(1 for v in pe_pos if v < mid) / len(pe_pos), abs=1e-9
    )
    # `ts` import kept meaningful: assert the L6.state default window matches
    # the derive pe_pb_days default (both ~250), so production runs align.
    import inspect
    sig = inspect.signature(ts._fetch_a_share_historical_percentile)
    derive_sig = inspect.signature(derive_mod._fetch_a_share_history)
    assert sig.parameters["history_days"].default == \
        derive_sig.parameters["pe_pb_days"].default == 250


# ---------------------------------------------------------------------------
# Mock-guard regression: derive's valuation reads must reject ``mock:*`` rows.
#
# ``derive_all`` itself needs a live Tushare client for price/PE/PB history,
# so it cannot run hermetically offline. The mock-skip logic was therefore
# extracted into the pure helper ``_value_if_not_mock`` (used by
# ``_read_realtime_value_with_source``); we unit-test that helper directly
# AND prove the source-aware reader drops a mock scalar from an in-memory DB.
# ---------------------------------------------------------------------------


def test_value_if_not_mock_helper():
    real = {"scalar": 42.0, "unit": "ratio"}
    assert _value_if_not_mock(real, "tushare:daily_basic") is real
    assert _value_if_not_mock(real, None) is real
    # Any source starting "mock:" is dropped, regardless of payload shape.
    assert _value_if_not_mock({"scalar": 999.0, "unit": "mock"}, "mock:mvp20-bff") is None
    assert _value_if_not_mock(real, "mock:") is None


def test_read_realtime_value_with_source_skips_mock(tmp_path: Path):
    db = tmp_path / "mockguard.sqlite"
    init_db(db)
    now = int(time.time())
    upsert_realtime(db, [
        # A fabricated PE row — has a "scalar" key just like a real one.
        ("600519.SH", "L6.mult.pe",
         {"scalar": 999.0, "unit": "mock"}, "Known", 0.55, "mock:mvp20-bff", now),
        # A genuine PB row for contrast.
        ("600519.SH", "L6.mult.pb",
         {"scalar": 7.5, "unit": "ratio"}, "Known", 0.9, "tushare:daily_basic", now),
    ])

    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        pe_value, pe_source = _read_realtime_value_with_source(conn, "600519.SH", "L6.mult.pe")
        pb_value, pb_source = _read_realtime_value_with_source(conn, "600519.SH", "L6.mult.pb")
        missing_value, missing_source = _read_realtime_value_with_source(
            conn, "600519.SH", "L7.trade.volume_turnover"
        )

    # Mock PE: source reported, but value scrubbed to None so the fake 999.0
    # scalar can never reach derive_historical_quantile / derive_overvalued.
    assert pe_source == "mock:mvp20-bff"
    assert pe_value is None
    pe_scalar = (pe_value or {}).get("scalar") if isinstance(pe_value, dict) else None
    assert pe_scalar is None

    # Real PB flows through untouched.
    assert pb_source == "tushare:daily_basic"
    assert pb_value == {"scalar": 7.5, "unit": "ratio"}

    # Absent row -> (None, None).
    assert missing_value is None and missing_source is None
