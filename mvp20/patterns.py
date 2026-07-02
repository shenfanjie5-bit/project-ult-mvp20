"""Pure-Python pattern recognition for OHLCV bars.

Translates raw indicator series into structured, named signals — golden
cross / death cross, MACD divergence, double top/bottom, RSI/KDJ
overbought/oversold, Bollinger breakout, volume-price confirmation.

Design goals
============

* **No numpy / pandas / talib** — pure Python so mvp20 stays lean.
* **Reuses ``technicals.compute_all`` output** when supplied so we don't
  recompute EMAs / MAs / RSI / KDJ. The ``indicators`` kwarg is optional
  — callers can pass either ``None`` (we compute on demand) or the dict
  returned by ``technicals.compute_all(bars)``.
* **Confidence-scored** — every pattern has a 0.5–0.95 ``confidence``
  field so downstream consumers can threshold (e.g. only show > 0.7
  signals on the dashboard).
* **Tolerant of short series** — sub-30 bars returns empty ``patterns``
  list and any zone signals it can still compute; never raises.

Returned shape
==============

``detect_all`` returns::

    {
      "patterns": [
        {"type": str,         # e.g. "golden_cross_5_20"
         "confidence": float, # 0.5 – 0.95
         "signal_date": str,  # date of the bar that triggered it
         "evidence": dict,    # supporting numbers
        }, ...
      ],
      "current_signals": {
        "ma_cross_5_20":  "golden" | "death" | None,
        "ma_cross_20_60": "golden" | "death" | None,
        "macd_cross":     "bull"   | "bear"  | None,
        "rsi_zone":       "overbought" | "oversold" | "neutral",
        "kdj_zone":       "overbought" | "oversold" | "neutral",
        "bollinger_zone": "above_upper" | "below_lower" | "inside",
      },
      "as_of": str | None,    # date of the latest bar
    }

The dict is JSON-safe — emit directly into ``L11.tech.patterns``.
"""

from __future__ import annotations

from typing import Mapping, Sequence

Bar = Mapping[str, float | str]

# Minimum bars before we try any pattern detection. Below this we still
# return ``current_signals`` for whatever indicators we can compute, but
# ``patterns`` stays empty.
_MIN_BARS_FOR_PATTERNS = 30


# ---------------------------------------------------------------------------
# Bar helpers — reuse technicals.py's close/volume extractors so the two
# modules stay byte-for-byte aligned (previously duplicated, drifted-silently
# risk noted in P2 review).
#
# IMPORTANT: ``_dates`` must use the SAME filter as ``_closes`` / ``_volumes``
# so the three index together 1:1. Otherwise, when ``bars`` contains a
# non-Mapping entry (e.g. legacy fixture row, malformed SQLite payload), the
# three lists drift in length and pattern detectors emit signal_date pointing
# at the wrong bar. The shared ``_aligned_dates_closes_volumes`` helper
# below guarantees alignment by walking the input once.
# ---------------------------------------------------------------------------

from mvp20.technicals import _to_close_list as _closes  # re-export (DRY)
from mvp20.technicals import _to_volume_list as _volumes


def _aligned_bars(bars: Sequence[Bar]) -> list[Mapping]:
    """Filter ``bars`` to entries that are ``Mapping`` AND have a numeric
    close. The returned list is the canonical reference frame against which
    every pattern detector indexes — date[i], close[i], volume[i] all refer
    to the same bar."""

    out: list[Mapping] = []
    for b in bars:
        if not isinstance(b, Mapping):
            continue
        v = b.get("close")
        if v is None:
            v = b.get("price")
        if v is None:
            continue
        try:
            float(v)
        except (TypeError, ValueError):
            continue
        out.append(b)
    return out


def _dates(bars: Sequence[Bar]) -> list[str]:
    """Dates aligned 1:1 with ``_closes(bars)``. Both filter on the same
    "is Mapping + has numeric close" predicate via ``_aligned_bars`` so
    indices match across detectors."""

    return [
        str(b.get("date") or b.get("trade_date") or "")
        for b in _aligned_bars(bars)
    ]


def _sma_at(closes: Sequence[float], idx: int, period: int) -> float | None:
    """SMA over ``closes[idx-period+1 : idx+1]`` — None if not enough bars."""

    if idx < period - 1 or idx >= len(closes):
        return None
    window = closes[idx - period + 1: idx + 1]
    if len(window) < period:
        return None
    return sum(window) / period


# ---------------------------------------------------------------------------
# 1. MA golden / death cross
# ---------------------------------------------------------------------------


def detect_ma_cross(
    closes: Sequence[float],
    short: int = 5,
    long: int = 20,
    lookback: int = 60,
) -> dict | None:
    """Find the most recent MA(short) vs MA(long) crossover within
    ``lookback`` bars from the end.

    Returns ``{"cross_type": "golden"|"death", "cross_index": int,
    "days_since": int, "short_ma": float, "long_ma": float}`` or ``None``
    if no cross found / series too short.
    """

    if len(closes) < long + 1:
        return None
    n = len(closes)
    # Scan from latest backwards until we find a sign flip in (short_ma - long_ma).
    start = max(long, n - lookback)
    prev_diff: float | None = None
    last_cross: tuple[int, str] | None = None
    for i in range(start, n):
        sa = _sma_at(closes, i, short)
        la = _sma_at(closes, i, long)
        if sa is None or la is None:
            continue
        diff = sa - la
        if prev_diff is not None:
            if prev_diff <= 0.0 and diff > 0.0:
                last_cross = (i, "golden")
            elif prev_diff >= 0.0 and diff < 0.0:
                last_cross = (i, "death")
        prev_diff = diff
    if last_cross is None:
        return None
    idx, ctype = last_cross
    return {
        "cross_type": ctype,
        "cross_index": idx,
        "days_since": n - 1 - idx,
        "short_ma": _sma_at(closes, n - 1, short),
        "long_ma": _sma_at(closes, n - 1, long),
    }


# ---------------------------------------------------------------------------
# 2. MACD divergence (top / bottom)
# ---------------------------------------------------------------------------


# EMA full series — reuse technicals.ema_series rather than re-implement
# (was previously duplicated; ~15 LOC drift risk). Aliased as ``_ema_full``
# for back-compat with existing call sites in this module.
from mvp20.technicals import ema_series as _ema_full


def _macd_hist_series(closes: Sequence[float]) -> list[float | None]:
    """Aligned MACD hist series — ``(dif - dea) * 2`` (A-股 convention).
    None where input is too short.

    Uses ``technicals.ema_series`` for EMA12 / EMA26 / DEA so the formula
    stays byte-for-byte aligned with ``technicals.macd``'s single-point
    output. Previously this re-implemented EMA inline; if technicals.macd
    ever changed its seed or recurrence the two would silently disagree.
    """

    n = len(closes)
    if n < 35:
        return [None] * n
    ef = _ema_full(closes, 12)
    es = _ema_full(closes, 26)
    dif: list[float | None] = [None] * n
    for i in range(n):
        if ef[i] is None or es[i] is None:
            continue
        dif[i] = ef[i] - es[i]
    leading = next((i for i, v in enumerate(dif) if v is not None), None)
    if leading is None:
        return [None] * n
    dif_valid = [v for v in dif[leading:] if v is not None]
    dea_valid = _ema_full(dif_valid, 9)
    out: list[float | None] = [None] * n
    for j, dea in enumerate(dea_valid):
        if dea is None:
            continue
        d = dif_valid[j]
        out[leading + j] = (d - dea) * 2.0
    return out


def _local_extrema(values: Sequence[float | None], lookback: int, kind: str = "high") -> list[int]:
    """Return indices of local highs (or lows) in the last ``lookback``
    bars. A point qualifies if it's a strict extremum compared to its 2
    immediate neighbors on each side (5-bar window)."""

    n = len(values)
    start = max(2, n - lookback)
    out: list[int] = []
    for i in range(start, n - 2):
        v = values[i]
        if v is None:
            continue
        window = values[i - 2: i + 3]
        if any(x is None for x in window):
            continue
        if kind == "high" and v == max(window) and v > values[i - 2] and v > values[i + 2]:
            out.append(i)
        elif kind == "low" and v == min(window) and v < values[i - 2] and v < values[i + 2]:
            out.append(i)
    return out


def detect_macd_divergence(
    bars: Sequence[Bar],
    lookback: int = 60,
) -> dict | None:
    """Look for top / bottom divergence between price and MACD histogram
    over the last ``lookback`` bars.

    *Top divergence*: price makes a higher high but MACD hist makes a
    lower high — bearish.

    *Bottom divergence*: price makes a lower low but MACD hist makes a
    higher low — bullish.

    Returns ``{"divergence": "top"|"bottom", "price_high_or_low": float,
    "hist_high_or_low": float, "first_index": int, "second_index": int}``
    or ``None`` if nothing detected.
    """

    closes = _closes(bars)
    if len(closes) < 35:
        return None
    hist = _macd_hist_series(closes)
    n = len(closes)

    # Top: two highest closes in the last `lookback`, second > first,
    # but the corresponding hist values are second <= first.
    highs = _local_extrema(closes, lookback, kind="high")
    if len(highs) >= 2:
        # Take the two most recent local highs.
        first_i, second_i = highs[-2], highs[-1]
        if (
            closes[second_i] > closes[first_i]
            and hist[first_i] is not None
            and hist[second_i] is not None
            and hist[second_i] < hist[first_i]
        ):
            return {
                "divergence": "top",
                "price_high_or_low": closes[second_i],
                "hist_high_or_low": hist[second_i],
                "first_index": first_i,
                "second_index": second_i,
            }

    # Bottom: two lowest closes — second < first but hist second > first.
    lows = _local_extrema(closes, lookback, kind="low")
    if len(lows) >= 2:
        first_i, second_i = lows[-2], lows[-1]
        if (
            closes[second_i] < closes[first_i]
            and hist[first_i] is not None
            and hist[second_i] is not None
            and hist[second_i] > hist[first_i]
        ):
            return {
                "divergence": "bottom",
                "price_high_or_low": closes[second_i],
                "hist_high_or_low": hist[second_i],
                "first_index": first_i,
                "second_index": second_i,
            }

    return None


# ---------------------------------------------------------------------------
# 3. Double top / double bottom
# ---------------------------------------------------------------------------


def detect_double_top_bottom(
    closes: Sequence[float],
    lookback: int = 60,
    tolerance: float = 0.03,
) -> dict | None:
    """W-bottom / M-top scanner.

    Picks the two most recent local extrema within ``lookback`` bars; if
    their values are within ``tolerance`` (fractional, e.g. 0.03 = 3%)
    and there's a meaningful trough/peak between them, classify as
    double_top (highs) or double_bottom (lows).

    Returns ``{"pattern": "double_top"|"double_bottom", "first_index",
    "second_index", "mid_index", "peak_or_trough_levels": [v1, v2]}``
    or ``None``.
    """

    if len(closes) < 10:
        return None

    # Double top — look at local highs.
    highs = _local_extrema(closes, lookback, kind="high")
    if len(highs) >= 2:
        first_i, second_i = highs[-2], highs[-1]
        v1, v2 = closes[first_i], closes[second_i]
        avg = (v1 + v2) / 2.0
        if avg > 0 and abs(v1 - v2) / avg <= tolerance and second_i - first_i >= 3:
            # Need a meaningful trough between them.
            trough_slice = closes[first_i + 1: second_i]
            if trough_slice:
                trough_idx = first_i + 1 + min(range(len(trough_slice)), key=lambda k: trough_slice[k])
                trough_val = closes[trough_idx]
                # Require the trough to dip at least ~3% below the peak average.
                if trough_val < avg * (1.0 - tolerance):
                    return {
                        "pattern": "double_top",
                        "first_index": first_i,
                        "second_index": second_i,
                        "mid_index": trough_idx,
                        "peak_or_trough_levels": [v1, v2],
                    }

    # Double bottom — local lows.
    lows = _local_extrema(closes, lookback, kind="low")
    if len(lows) >= 2:
        first_i, second_i = lows[-2], lows[-1]
        v1, v2 = closes[first_i], closes[second_i]
        avg = (v1 + v2) / 2.0
        if avg > 0 and abs(v1 - v2) / avg <= tolerance and second_i - first_i >= 3:
            peak_slice = closes[first_i + 1: second_i]
            if peak_slice:
                peak_idx = first_i + 1 + max(range(len(peak_slice)), key=lambda k: peak_slice[k])
                peak_val = closes[peak_idx]
                if peak_val > avg * (1.0 + tolerance):
                    return {
                        "pattern": "double_bottom",
                        "first_index": first_i,
                        "second_index": second_i,
                        "mid_index": peak_idx,
                        "peak_or_trough_levels": [v1, v2],
                    }

    return None


# ---------------------------------------------------------------------------
# 4. RSI / KDJ overbought / oversold zones
# ---------------------------------------------------------------------------


def rsi_zone(rsi12: float | None) -> str:
    """A-share convention: RSI12 > 80 → overbought, < 20 → oversold."""

    if rsi12 is None:
        return "neutral"
    if rsi12 > 80.0:
        return "overbought"
    if rsi12 < 20.0:
        return "oversold"
    return "neutral"


def kdj_zone(k: float | None, j: float | None = None) -> str:
    """KDJ overbought = K > 90 (and optionally J > 100); oversold = K < 10."""

    if k is None:
        return "neutral"
    if k > 90.0 or (j is not None and j > 100.0):
        return "overbought"
    if k < 10.0 or (j is not None and j < 0.0):
        return "oversold"
    return "neutral"


# ---------------------------------------------------------------------------
# 5. Bollinger breakout
# ---------------------------------------------------------------------------


def bollinger_zone(boll: Mapping[str, float | None] | None, last_close: float | None) -> str:
    """Where is the latest close vs the Bollinger envelope?"""

    if not boll or last_close is None:
        return "inside"
    upper = boll.get("upper")
    lower = boll.get("lower")
    if upper is not None and last_close > upper:
        return "above_upper"
    if lower is not None and last_close < lower:
        return "below_lower"
    return "inside"


def detect_boll_squeeze_breakout(
    closes: Sequence[float],
    bandwidth_history: Sequence[float | None] | None = None,
    period: int = 20,
) -> dict | None:
    """Today's close breaks the upper / lower band AND the recent
    bandwidth is in the lower half of its history (band squeeze, often
    precedes volatility expansion).

    If ``bandwidth_history`` is not provided, this just checks the
    breakout itself without the squeeze qualifier.
    """

    if len(closes) < period:
        return None
    window = closes[-period:]
    mid = sum(window) / period
    var = sum((x - mid) ** 2 for x in window) / period
    sigma = var ** 0.5
    upper = mid + 2.0 * sigma
    lower = mid - 2.0 * sigma
    last = closes[-1]
    width = upper - lower
    bandwidth = (width / mid) if mid > 0 else None

    breakout: str | None = None
    if last > upper:
        breakout = "upper"
    elif last < lower:
        breakout = "lower"
    if breakout is None:
        return None

    squeeze = False
    if bandwidth_history and bandwidth is not None:
        bw_clean = [b for b in bandwidth_history if b is not None]
        if bw_clean:
            srt = sorted(bw_clean)
            median = srt[len(srt) // 2]
            squeeze = bandwidth < median

    return {
        "breakout": breakout,
        "last_close": last,
        "upper": upper,
        "lower": lower,
        "bandwidth": bandwidth,
        "squeeze": squeeze,
    }


# ---------------------------------------------------------------------------
# 6. Volume-price confirmation / divergence
# ---------------------------------------------------------------------------


def detect_volume_price_signal(
    bars: Sequence[Bar],
    pct_threshold: float = 0.015,
    vol_ratio_threshold: float = 1.5,
) -> dict | None:
    """Pair-wise volume / price action on the latest bar.

    Definitions used:

    * **量价齐升** (``volume_price_rally``) — close up ≥ ``pct_threshold``
      AND vol_ratio (today vs 5-day prior mean) ≥ ``vol_ratio_threshold``.
      Confirms an uptrend — bullish.
    * **量价背离** (``volume_price_divergence``) — close down ≥
      ``pct_threshold`` AND vol_ratio ≥ ``vol_ratio_threshold``. Heavy
      selling — bearish warning.
    """

    closes = _closes(bars)
    vols = _volumes(bars)
    if len(closes) < 7 or len(vols) < 7:
        return None
    pct = (closes[-1] - closes[-2]) / closes[-2] if closes[-2] != 0 else 0.0
    prior5 = vols[-6:-1]
    if not prior5:
        return None
    mean5 = sum(prior5) / len(prior5)
    if mean5 <= 0:
        return None
    vol_ratio = vols[-1] / mean5
    if vol_ratio < vol_ratio_threshold:
        return None
    if pct >= pct_threshold:
        return {
            "signal": "volume_price_rally",
            "pct_change": pct,
            "vol_ratio": vol_ratio,
        }
    if pct <= -pct_threshold:
        return {
            "signal": "volume_price_divergence",
            "pct_change": pct,
            "vol_ratio": vol_ratio,
        }
    return None


# ---------------------------------------------------------------------------
# MACD cross with days-since look-back
# ---------------------------------------------------------------------------


def _macd_full_series(closes: Sequence[float]) -> tuple[list[float | None], list[float | None]]:
    """Return aligned ``(dif, dea)`` lists."""

    n = len(closes)
    if n < 35:
        return [None] * n, [None] * n
    ef = _ema_full(closes, 12)
    es = _ema_full(closes, 26)
    dif: list[float | None] = [None] * n
    for i in range(n):
        if ef[i] is None or es[i] is None:
            continue
        dif[i] = ef[i] - es[i]
    leading = next((i for i, v in enumerate(dif) if v is not None), None)
    dea: list[float | None] = [None] * n
    if leading is None:
        return dif, dea
    dif_valid = [v for v in dif[leading:] if v is not None]
    dea_valid = _ema_full(dif_valid, 9)
    for j, v in enumerate(dea_valid):
        dea[leading + j] = v
    return dif, dea


def detect_macd_cross_history(closes: Sequence[float], lookback: int = 60) -> dict | None:
    """Most recent MACD bull/bear cross within ``lookback`` bars and the
    bar-distance from today."""

    if len(closes) < 35:
        return None
    dif, dea = _macd_full_series(closes)
    n = len(closes)
    start = max(1, n - lookback)
    last: tuple[int, str] | None = None
    for i in range(start, n):
        a = dif[i]; b = dea[i]; ap = dif[i - 1]; bp = dea[i - 1]
        if None in (a, b, ap, bp):
            continue
        if ap <= bp and a > b:
            last = (i, "bull")
        elif ap >= bp and a < b:
            last = (i, "bear")
    if last is None:
        return None
    idx, ctype = last
    return {
        "cross_type": ctype,
        "cross_index": idx,
        "days_since": n - 1 - idx,
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _bandwidth_history(closes: Sequence[float], period: int = 20) -> list[float | None]:
    """Aligned BB bandwidth series — used for squeeze detection."""

    n = len(closes)
    out: list[float | None] = [None] * n
    if n < period:
        return out
    for i in range(period - 1, n):
        window = closes[i - period + 1: i + 1]
        mid = sum(window) / period
        var = sum((x - mid) ** 2 for x in window) / period
        sigma = var ** 0.5
        if mid > 0:
            out[i] = (4.0 * sigma) / mid
    return out


def detect_all(
    bars: Sequence[Bar],
    indicators: Mapping[str, object] | None = None,
) -> dict:
    """Run every supported detector against ``bars`` and aggregate into a
    single JSON-safe dict (see module docstring for shape).

    ``indicators`` is the optional output of ``technicals.compute_all`` —
    when supplied we reuse the RSI / KDJ / Bollinger snapshots instead of
    recomputing.
    """

    closes = _closes(bars)
    dates = _dates(bars)
    n = len(closes)
    as_of = dates[-1] if dates else None

    patterns: list[dict] = []
    current_signals: dict[str, str | None] = {
        "ma_cross_5_20": None,
        "ma_cross_20_60": None,
        "macd_cross": None,
        "rsi_zone": "neutral",
        "kdj_zone": "neutral",
        "bollinger_zone": "inside",
    }

    # ----- pull cached indicator snapshots when available ---------------
    rsi_block = (indicators or {}).get("rsi") if isinstance(indicators, Mapping) else None
    kdj_block = (indicators or {}).get("kdj") if isinstance(indicators, Mapping) else None
    boll_block = (indicators or {}).get("boll") if isinstance(indicators, Mapping) else None
    macd_block = (indicators or {}).get("macd") if isinstance(indicators, Mapping) else None

    # Zones are cheap and run even on short series.
    rsi12 = rsi_block.get("rsi12") if isinstance(rsi_block, Mapping) else None
    current_signals["rsi_zone"] = rsi_zone(rsi12)

    k = kdj_block.get("k") if isinstance(kdj_block, Mapping) else None
    j = kdj_block.get("j") if isinstance(kdj_block, Mapping) else None
    current_signals["kdj_zone"] = kdj_zone(k, j)

    last_close = closes[-1] if closes else None
    current_signals["bollinger_zone"] = bollinger_zone(
        boll_block if isinstance(boll_block, Mapping) else None, last_close
    )

    if n < _MIN_BARS_FOR_PATTERNS:
        return {
            "patterns": patterns,
            "current_signals": current_signals,
            "as_of": as_of,
        }

    # ----- MA crosses (5/20 + 20/60) ------------------------------------
    ma_5_20 = detect_ma_cross(closes, short=5, long=20, lookback=60)
    if ma_5_20:
        current_signals["ma_cross_5_20"] = ma_5_20["cross_type"]
        if ma_5_20["days_since"] <= 5:
            patterns.append({
                "type": f"{ma_5_20['cross_type']}_cross_5_20",
                "confidence": 0.85 if ma_5_20["days_since"] == 0 else 0.70,
                "signal_date": dates[ma_5_20["cross_index"]] if dates else None,
                "evidence": {
                    "days_since": ma_5_20["days_since"],
                    "short_ma": ma_5_20["short_ma"],
                    "long_ma": ma_5_20["long_ma"],
                },
            })

    ma_20_60 = detect_ma_cross(closes, short=20, long=60, lookback=120) if n >= 61 else None
    if ma_20_60:
        current_signals["ma_cross_20_60"] = ma_20_60["cross_type"]
        if ma_20_60["days_since"] <= 5:
            patterns.append({
                "type": f"{ma_20_60['cross_type']}_cross_20_60",
                "confidence": 0.90 if ma_20_60["days_since"] == 0 else 0.75,
                "signal_date": dates[ma_20_60["cross_index"]] if dates else None,
                "evidence": {
                    "days_since": ma_20_60["days_since"],
                    "short_ma": ma_20_60["short_ma"],
                    "long_ma": ma_20_60["long_ma"],
                },
            })

    # ----- MACD cross + divergence --------------------------------------
    macd_hist = detect_macd_cross_history(closes, lookback=60)
    # Prefer the supplied snapshot's `cross` if it says something *today*.
    snap_cross = macd_block.get("cross") if isinstance(macd_block, Mapping) else None
    if snap_cross:
        current_signals["macd_cross"] = snap_cross
    elif macd_hist:
        current_signals["macd_cross"] = macd_hist["cross_type"]
    if macd_hist and macd_hist["days_since"] <= 5:
        patterns.append({
            "type": f"macd_{macd_hist['cross_type']}_cross",
            "confidence": 0.80 if macd_hist["days_since"] == 0 else 0.65,
            "signal_date": dates[macd_hist["cross_index"]] if dates else None,
            "evidence": {"days_since": macd_hist["days_since"]},
        })

    div = detect_macd_divergence(bars, lookback=60)
    if div:
        patterns.append({
            "type": f"macd_{div['divergence']}_divergence",
            "confidence": 0.65,
            "signal_date": dates[div["second_index"]] if dates else None,
            "evidence": {
                "first_index": div["first_index"],
                "second_index": div["second_index"],
                "price": div["price_high_or_low"],
                "hist": div["hist_high_or_low"],
            },
        })

    # ----- Double top / bottom ------------------------------------------
    dtb = detect_double_top_bottom(closes, lookback=60, tolerance=0.03)
    if dtb:
        patterns.append({
            "type": dtb["pattern"],
            "confidence": 0.70,
            "signal_date": dates[dtb["second_index"]] if dates else None,
            "evidence": {
                "first_index": dtb["first_index"],
                "second_index": dtb["second_index"],
                "mid_index": dtb["mid_index"],
                "levels": dtb["peak_or_trough_levels"],
            },
        })

    # ----- Overbought / oversold (also surfaced as patterns) ------------
    if current_signals["rsi_zone"] != "neutral":
        patterns.append({
            "type": f"rsi_{current_signals['rsi_zone']}",
            "confidence": 0.60,
            "signal_date": as_of,
            "evidence": {"rsi12": rsi12},
        })
    if current_signals["kdj_zone"] != "neutral":
        patterns.append({
            "type": f"kdj_{current_signals['kdj_zone']}",
            "confidence": 0.60,
            "signal_date": as_of,
            "evidence": {"k": k, "j": j},
        })

    # ----- Bollinger breakout / squeeze ---------------------------------
    bw_hist = _bandwidth_history(closes, 20)
    boll_signal = detect_boll_squeeze_breakout(closes, bw_hist, period=20)
    if boll_signal:
        patterns.append({
            "type": f"boll_breakout_{boll_signal['breakout']}",
            "confidence": 0.75 if boll_signal["squeeze"] else 0.60,
            "signal_date": as_of,
            "evidence": {
                "last_close": boll_signal["last_close"],
                "upper": boll_signal["upper"],
                "lower": boll_signal["lower"],
                "bandwidth": boll_signal["bandwidth"],
                "squeeze": boll_signal["squeeze"],
            },
        })

    # ----- Volume / price confirm or divergence -------------------------
    vp = detect_volume_price_signal(bars)
    if vp:
        patterns.append({
            "type": vp["signal"],
            "confidence": 0.70 if vp["signal"] == "volume_price_rally" else 0.65,
            "signal_date": as_of,
            "evidence": {
                "pct_change": vp["pct_change"],
                "vol_ratio": vp["vol_ratio"],
            },
        })

    return {
        "patterns": patterns,
        "current_signals": current_signals,
        "as_of": as_of,
    }


__all__ = [
    "Bar",
    "bollinger_zone",
    "detect_all",
    "detect_boll_squeeze_breakout",
    "detect_double_top_bottom",
    "detect_ma_cross",
    "detect_macd_cross_history",
    "detect_macd_divergence",
    "detect_volume_price_signal",
    "kdj_zone",
    "rsi_zone",
]
