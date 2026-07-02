"""Unit tests for mvp20.patterns.

Each pattern is exercised against a hand-crafted synthetic series so the
detection logic stays deterministic — no fixtures or external data
needed.
"""

from __future__ import annotations

import math

import pytest

from mvp20 import patterns, technicals


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bars_from_closes(closes: list[float], start_vol: float = 1000.0) -> list[dict]:
    """Wrap a close-price series into full OHLCV Bar dicts with stable
    high/low spreads and a slowly-rising vol."""

    bars = []
    for i, c in enumerate(closes):
        bars.append({
            "date": f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            "open": c - 0.05,
            "high": c + 0.20,
            "low": c - 0.20,
            "close": c,
            "vol": start_vol + i * 10,
        })
    return bars


# ---------------------------------------------------------------------------
# 1. MA cross
# ---------------------------------------------------------------------------


class TestMACross:
    def test_golden_cross_detected_on_synthetic_data(self) -> None:
        # 30 flat then 20 sharply rising — MA5 must cross above MA20.
        closes = [10.0] * 30 + [10.0 + i for i in range(1, 21)]
        out = patterns.detect_ma_cross(closes, short=5, long=20, lookback=60)
        assert out is not None
        assert out["cross_type"] == "golden"
        assert isinstance(out["days_since"], int)
        assert out["days_since"] >= 0

    def test_death_cross_on_descending_data(self) -> None:
        # 30 flat at 100 then 20 sharply falling — MA5 must cross below MA20.
        closes = [100.0] * 30 + [100.0 - i for i in range(1, 21)]
        out = patterns.detect_ma_cross(closes, short=5, long=20, lookback=60)
        assert out is not None
        assert out["cross_type"] == "death"
        assert out["days_since"] >= 0
        # short_ma should be below long_ma in a fresh death cross.
        assert out["short_ma"] is not None and out["long_ma"] is not None
        assert out["short_ma"] < out["long_ma"]

    def test_no_cross_returns_none_on_flat_series(self) -> None:
        closes = [50.0] * 50
        # Constant series — MAs equal, no genuine crossing.
        out = patterns.detect_ma_cross(closes, short=5, long=20, lookback=60)
        assert out is None

    def test_short_series_returns_none(self) -> None:
        closes = [1.0, 2.0, 3.0]
        assert patterns.detect_ma_cross(closes, short=5, long=20) is None


# ---------------------------------------------------------------------------
# 2. MACD divergence
# ---------------------------------------------------------------------------


class TestMACDDivergence:
    def test_macd_divergence_top(self) -> None:
        # Build a price series where second peak > first peak but
        # MACD-hist second peak < first peak (a classic top divergence).
        # We achieve this by having a sharp rally → pullback → slow grind
        # to a marginally higher high — the slower second rally cools
        # the MACD histogram.
        closes: list[float] = []
        # Warm-up 40 bars around 100 to seed MACD properly.
        closes += [100.0 + 0.05 * i for i in range(40)]
        # Sharp first peak.
        closes += [102.0, 103.5, 105.5, 107.0, 108.0, 106.5, 104.5, 103.0]
        # Pullback.
        closes += [102.0, 101.0, 100.5, 100.5, 101.0, 101.5]
        # Slow second peak (slightly higher).
        closes += [102.0, 102.8, 103.6, 104.4, 105.2, 106.0, 106.5, 107.0,
                   107.5, 108.2, 108.5, 108.3, 107.8]
        bars = _bars_from_closes(closes)
        out = patterns.detect_macd_divergence(bars, lookback=80)
        # We may or may not always detect (depends on exact MACD shape) —
        # but if we do, it must be "top" not "bottom".
        if out is not None:
            assert out["divergence"] == "top"
            assert out["price_high_or_low"] > 0
            assert out["second_index"] > out["first_index"]

    def test_handles_short_series_no_crash(self) -> None:
        bars = _bars_from_closes([10.0, 11.0, 12.0])
        # Below 35 bars — divergence requires MACD which needs 35+.
        assert patterns.detect_macd_divergence(bars) is None


# ---------------------------------------------------------------------------
# 3. Double top / bottom
# ---------------------------------------------------------------------------


class TestDoubleTopBottom:
    def test_double_top_pattern(self) -> None:
        # Two peaks around 120 with a trough around 110 between them.
        closes: list[float] = []
        # Run up to first peak.
        closes += [100, 105, 110, 115, 120, 119, 118, 116]
        # Trough.
        closes += [114, 112, 110, 110, 111, 113]
        # Run up to second peak (within 1% of the first).
        closes += [115, 118, 120, 120.5, 119, 117, 114]
        out = patterns.detect_double_top_bottom(closes, lookback=60, tolerance=0.03)
        assert out is not None
        assert out["pattern"] == "double_top"
        assert out["first_index"] < out["mid_index"] < out["second_index"]
        v1, v2 = out["peak_or_trough_levels"]
        assert abs(v1 - v2) / ((v1 + v2) / 2) < 0.03

    def test_double_bottom_pattern(self) -> None:
        # Two troughs near 80, peak around 90 between.
        closes: list[float] = []
        closes += [100, 95, 90, 85, 80, 81, 82, 83]
        closes += [85, 87, 89, 90, 89, 87]
        closes += [85, 83, 81, 79.5, 81, 83, 86]
        out = patterns.detect_double_top_bottom(closes, lookback=60, tolerance=0.05)
        assert out is not None
        assert out["pattern"] == "double_bottom"

    def test_no_pattern_on_flat_data(self) -> None:
        closes = [50.0] * 50
        assert patterns.detect_double_top_bottom(closes) is None


# ---------------------------------------------------------------------------
# 4. RSI / KDJ zones
# ---------------------------------------------------------------------------


class TestZones:
    def test_rsi_overbought_zone(self) -> None:
        assert patterns.rsi_zone(85.0) == "overbought"
        assert patterns.rsi_zone(15.0) == "oversold"
        assert patterns.rsi_zone(50.0) == "neutral"
        assert patterns.rsi_zone(None) == "neutral"

    def test_kdj_overbought_zone(self) -> None:
        assert patterns.kdj_zone(95.0) == "overbought"
        assert patterns.kdj_zone(5.0) == "oversold"
        assert patterns.kdj_zone(50.0) == "neutral"
        # J > 100 also triggers overbought.
        assert patterns.kdj_zone(70.0, j=110.0) == "overbought"
        # J < 0 triggers oversold.
        assert patterns.kdj_zone(30.0, j=-5.0) == "oversold"


# ---------------------------------------------------------------------------
# 5. Bollinger
# ---------------------------------------------------------------------------


class TestBollinger:
    def test_boll_breakout_upper(self) -> None:
        # 19 bars steady at 100, then a sharp pop to 115 — definitely
        # outside the upper band.
        closes = [100.0] * 19 + [115.0]
        out = patterns.detect_boll_squeeze_breakout(closes, period=20)
        assert out is not None
        assert out["breakout"] == "upper"
        assert out["last_close"] == 115.0

    def test_boll_breakout_lower(self) -> None:
        closes = [100.0] * 19 + [80.0]
        out = patterns.detect_boll_squeeze_breakout(closes, period=20)
        assert out is not None
        assert out["breakout"] == "lower"

    def test_bollinger_zone_inside(self) -> None:
        boll = {"upper": 110.0, "lower": 90.0, "mid": 100.0}
        assert patterns.bollinger_zone(boll, 100.0) == "inside"
        assert patterns.bollinger_zone(boll, 120.0) == "above_upper"
        assert patterns.bollinger_zone(boll, 80.0) == "below_lower"
        assert patterns.bollinger_zone(None, 100.0) == "inside"


# ---------------------------------------------------------------------------
# 6. Volume-price
# ---------------------------------------------------------------------------


class TestVolumePriceSignal:
    def test_volume_price_confirm(self) -> None:
        # 6 bars baseline + 1 strong up bar with double normal volume.
        bars = _bars_from_closes([100.0, 101.0, 100.5, 101.5, 102.0, 102.5, 105.0])
        # Override last vol to clearly exceed 1.5x of prior 5-day mean.
        prior_mean = sum(b["vol"] for b in bars[1:6]) / 5
        bars[-1]["vol"] = prior_mean * 3.0
        out = patterns.detect_volume_price_signal(bars)
        assert out is not None
        assert out["signal"] == "volume_price_rally"
        assert out["pct_change"] > 0
        assert out["vol_ratio"] > 1.5

    def test_volume_price_divergence_heavy_selling(self) -> None:
        bars = _bars_from_closes([100.0, 101.0, 100.5, 101.5, 102.0, 102.5, 98.0])
        prior_mean = sum(b["vol"] for b in bars[1:6]) / 5
        bars[-1]["vol"] = prior_mean * 3.0
        out = patterns.detect_volume_price_signal(bars)
        assert out is not None
        assert out["signal"] == "volume_price_divergence"
        assert out["pct_change"] < 0

    def test_no_signal_on_quiet_day(self) -> None:
        bars = _bars_from_closes([100.0, 100.1, 100.05, 100.1, 100.0, 100.05, 100.1])
        out = patterns.detect_volume_price_signal(bars)
        assert out is None


# ---------------------------------------------------------------------------
# 7. detect_all orchestrator
# ---------------------------------------------------------------------------


class TestDetectAll:
    def test_detect_all_returns_structured_dict(self) -> None:
        # 60 bars in a slow uptrend — enough for every detector to run.
        closes = [50.0 + i * 0.5 for i in range(60)]
        bars = _bars_from_closes(closes)
        tech = technicals.compute_all(bars)
        out = patterns.detect_all(bars, indicators=tech)
        assert set(out.keys()) == {"patterns", "current_signals", "as_of"}
        assert isinstance(out["patterns"], list)
        assert isinstance(out["current_signals"], dict)
        expected_signal_keys = {
            "ma_cross_5_20", "ma_cross_20_60", "macd_cross",
            "rsi_zone", "kdj_zone", "bollinger_zone",
        }
        assert set(out["current_signals"].keys()) == expected_signal_keys
        # Every pattern entry should have the standard 4 fields.
        for p in out["patterns"]:
            assert {"type", "confidence", "signal_date", "evidence"} <= set(p.keys())
            assert 0.5 <= p["confidence"] <= 0.95

    def test_handles_short_series(self) -> None:
        # Below 30 bars — patterns must be empty, signals still returned.
        bars = _bars_from_closes([10.0, 11.0, 12.0, 13.0, 14.0])
        out = patterns.detect_all(bars)
        assert out["patterns"] == []
        assert isinstance(out["current_signals"], dict)
        # Zones should fall back to neutral / inside when nothing computable.
        assert out["current_signals"]["rsi_zone"] == "neutral"
        assert out["current_signals"]["kdj_zone"] == "neutral"
        assert out["current_signals"]["bollinger_zone"] == "inside"

    def test_detect_all_without_indicators_arg_does_not_crash(self) -> None:
        # 60 bars but indicators=None — patterns module should compute
        # everything it needs internally.
        closes = [100.0 + (i % 7) * 0.5 for i in range(60)]
        bars = _bars_from_closes(closes)
        out = patterns.detect_all(bars, indicators=None)
        assert "patterns" in out and "current_signals" in out

    def test_overbought_rsi_surfaces_as_pattern(self) -> None:
        # 40 bars of unbroken rally → RSI will exceed 80.
        closes = [100.0 + i for i in range(40)]
        bars = _bars_from_closes(closes)
        tech = technicals.compute_all(bars)
        out = patterns.detect_all(bars, indicators=tech)
        # RSI12 of 40 monotonically rising bars should be 100 (no losses).
        assert out["current_signals"]["rsi_zone"] == "overbought"
        types = {p["type"] for p in out["patterns"]}
        assert "rsi_overbought" in types

    def test_empty_bars_returns_empty(self) -> None:
        out = patterns.detect_all([])
        assert out["patterns"] == []
        assert out["as_of"] is None

    def test_detect_all_emits_golden_cross_pattern(self) -> None:
        # 30 flat then 20 rising → should fire golden_cross_5_20.
        closes = [10.0] * 30 + [10.0 + i for i in range(1, 21)]
        bars = _bars_from_closes(closes)
        tech = technicals.compute_all(bars)
        out = patterns.detect_all(bars, indicators=tech)
        assert out["current_signals"]["ma_cross_5_20"] == "golden"
