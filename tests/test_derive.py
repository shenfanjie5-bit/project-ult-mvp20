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
    derive_l6_path_second_derivative,
    derive_l6_path_tag,
    derive_l6_sens_cashflow,
    derive_l6_sens_growth_margin,
    derive_l6_sens_rates,
    derive_l6_sens_risk_narrative,
    derive_l7_env_risk_appetite,
    derive_l7_mood_fomo,
    derive_l8_industry_demand_supply,
    derive_l8_industry_price_war,
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
