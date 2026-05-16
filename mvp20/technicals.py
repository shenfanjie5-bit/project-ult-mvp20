"""Pure-Python technical-indicator library.

Used by the derive layer to compute per-stock technicals from OHLCV bars
and emit them as ``L11.tech.*`` dp_ids in the SQLite hot snapshot.

Design goals
============

* **Source-agnostic** — all functions take plain ``list[float]`` (or list of
  ``Bar`` dicts) so callers can feed Tushare / FMP / Futu equally.
* **No numpy / pandas dependency** — keeps mvp20 deps lean (`click /
  pydantic / pyyaml` only). For a 250d series the pure-Python cost is
  microseconds and computed once per daily cycle.
* **Returns plain dicts** — caller can JSON-serialize directly into
  ``realtime_current.value_json``.
* **Tolerates short series** — every function returns ``None`` when input
  is below the indicator's minimum length, so the derive layer can branch
  on it cleanly without raising.

Bar input convention
====================

``Bar = {"date": str, "open": float, "high": float, "low": float,
         "close": float, "vol": float}``

Functions accept either:

* ``bars: list[Bar]`` (ordered **ascending** by date — oldest first), or
* ``closes: list[float]`` (ascending) when only closes matter.

Indicators implemented
======================

==================  ==============================================
Name                Output keys (single latest value, or list)
==================  ==============================================
moving_averages      ma5 / ma10 / ma20 / ma60 / ma120 / ma250
ema_series           ema12 / ema26
macd                 dif / dea / hist / cross (bull|bear|None)
rsi                  rsi6 / rsi12 / rsi24
kdj                  k / d / j  (KDJ(9,3,3))
boll                 mid / upper / lower / percent_b / bandwidth
volume_ma            vol5 / vol10 / vol_ratio_today
atr                  atr14
obv                  obv (cumulative, latest value)
==================  ==============================================

Each "single-snapshot" function returns ``{... latest values ...}``;
``series_*`` variants return the full history aligned to the input bars
so the frontend can render line overlays.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

Bar = Mapping[str, float | str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_close_list(bars_or_closes: Sequence[float | Bar]) -> list[float]:
    """Accept either a list of floats or a list of ``Bar`` dicts; return
    a list of close prices. Drops rows where ``close`` is missing /
    non-numeric so downstream math stays clean."""

    out: list[float] = []
    for item in bars_or_closes:
        if isinstance(item, (int, float)):
            out.append(float(item))
            continue
        if isinstance(item, Mapping):
            v = item.get("close")
            if v is None:
                v = item.get("price")
            if v is None:
                continue
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                continue
    return out


def _to_volume_list(bars: Sequence[Bar]) -> list[float]:
    out: list[float] = []
    for b in bars:
        if not isinstance(b, Mapping):
            continue
        v = b.get("vol")
        if v is None:
            v = b.get("volume")
        if v is None:
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out


def _safe_mean(xs: Sequence[float]) -> float | None:
    if not xs:
        return None
    return sum(xs) / len(xs)


# ---------------------------------------------------------------------------
# Moving averages
# ---------------------------------------------------------------------------


#: Default windows used by ``moving_averages`` — 大家都会看的 4-tier 视角.
DEFAULT_MA_WINDOWS = (5, 10, 20, 60, 120, 250)


def sma_series(closes: Sequence[float], period: int) -> list[float | None]:
    """Simple moving average for every index. Bars [0, period-2] return
    ``None`` so the output list aligns 1:1 with the input."""

    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period:
        return out
    rolling = sum(closes[:period])
    out[period - 1] = rolling / period
    for i in range(period, len(closes)):
        rolling += closes[i] - closes[i - period]
        out[i] = rolling / period
    return out


def moving_averages(
    bars_or_closes: Sequence[float | Bar],
    windows: Sequence[int] = DEFAULT_MA_WINDOWS,
) -> dict[str, float | None]:
    """Latest SMA snapshot. Returns ``{f"ma{w}": value | None}`` for each
    requested window."""

    closes = _to_close_list(bars_or_closes)
    out: dict[str, float | None] = {}
    for w in windows:
        series = sma_series(closes, w)
        out[f"ma{w}"] = series[-1] if series else None
    return out


# ---------------------------------------------------------------------------
# Exponential moving averages
# ---------------------------------------------------------------------------


def ema_series(closes: Sequence[float], period: int) -> list[float | None]:
    """EMA aligned to input length. First ``period-1`` entries are
    ``None``; entry ``period-1`` seeds with SMA(period); the rest use the
    standard EMA recurrence ``ema = close*k + ema_prev*(1-k)`` with
    ``k = 2/(period+1)``."""

    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period:
        return out
    k = 2.0 / (period + 1.0)
    seed = sum(closes[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(closes)):
        cur = closes[i] * k + prev * (1.0 - k)
        out[i] = cur
        prev = cur
    return out


# ---------------------------------------------------------------------------
# MACD (12, 26, 9)  — A 股惯例: DIF / DEA / MACD柱
# ---------------------------------------------------------------------------


def macd(
    bars_or_closes: Sequence[float | Bar],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, float | None | str]:
    """Latest MACD snapshot.

    Returns ``{dif, dea, hist, cross}`` where:

    * ``dif`` = EMA(fast) - EMA(slow)
    * ``dea`` = EMA(dif, signal)
    * ``hist`` = (dif - dea) * 2  — A 股惯例 ×2 让柱体更醒目
    * ``cross`` = ``"bull"`` if today's dif crosses up through dea,
                  ``"bear"`` if it crosses down, otherwise ``None``.

    All values ``None`` if input length < slow + signal.
    """

    closes = _to_close_list(bars_or_closes)
    if len(closes) < slow + signal:
        return {"dif": None, "dea": None, "hist": None, "cross": None}

    ef = ema_series(closes, fast)
    es = ema_series(closes, slow)
    if not ef or not es:
        return {"dif": None, "dea": None, "hist": None, "cross": None}

    # Build dif aligned to indices where both EMAs are non-None.
    n = len(closes)
    dif: list[float | None] = [None] * n
    for i in range(n):
        a = ef[i]
        b = es[i]
        if a is None or b is None:
            continue
        dif[i] = a - b

    # DEA = EMA(dif, signal). Strip leading Nones first.
    leading = next((i for i, v in enumerate(dif) if v is not None), None)
    if leading is None:
        return {"dif": None, "dea": None, "hist": None, "cross": None}
    dif_valid = [v for v in dif[leading:] if v is not None]
    dea_valid = ema_series(dif_valid, signal)
    if not dea_valid or dea_valid[-1] is None:
        return {"dif": dif_valid[-1] if dif_valid else None,
                "dea": None, "hist": None, "cross": None}

    dif_now = dif_valid[-1]
    dea_now = dea_valid[-1]
    hist_now = (dif_now - dea_now) * 2.0

    # Detect today's cross by comparing prev bar.
    cross: str | None = None
    if len(dif_valid) >= 2 and len(dea_valid) >= 2:
        dif_prev = dif_valid[-2]
        dea_prev = dea_valid[-2]
        if dif_prev is not None and dea_prev is not None:
            if dif_prev <= dea_prev and dif_now > dea_now:
                cross = "bull"
            elif dif_prev >= dea_prev and dif_now < dea_now:
                cross = "bear"

    return {"dif": dif_now, "dea": dea_now, "hist": hist_now, "cross": cross}


# ---------------------------------------------------------------------------
# RSI (6 / 12 / 24)  — Wilder smoothing
# ---------------------------------------------------------------------------


def _rsi_single(closes: Sequence[float], period: int) -> float | None:
    """Wilder-smoothed RSI for the latest bar."""

    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    # Seed: simple mean of first `period`.
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    # Wilder recurrence for the rest.
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def rsi(
    bars_or_closes: Sequence[float | Bar],
    periods: Sequence[int] = (6, 12, 24),
) -> dict[str, float | None]:
    """Latest RSI for 6 / 12 / 24 day windows (A 股 default).

    Returns ``{f"rsi{p}": value}``. Each entry is ``None`` when input is
    shorter than ``period + 1`` bars.
    """

    closes = _to_close_list(bars_or_closes)
    return {f"rsi{p}": _rsi_single(closes, p) for p in periods}


# ---------------------------------------------------------------------------
# KDJ (9, 3, 3)  — A 股 default
# ---------------------------------------------------------------------------


def kdj(
    bars: Sequence[Bar],
    period: int = 9,
    k_smooth: int = 3,
    d_smooth: int = 3,
) -> dict[str, float | None]:
    """Latest KDJ snapshot. Requires high/low/close bars (not just closes)."""

    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for b in bars:
        if not isinstance(b, Mapping):
            continue
        try:
            h = float(b["high"]) if b.get("high") is not None else None
            l = float(b["low"]) if b.get("low") is not None else None
            c = float(b["close"]) if b.get("close") is not None else None
        except (TypeError, ValueError, KeyError):
            continue
        if h is None or l is None or c is None:
            continue
        highs.append(h)
        lows.append(l)
        closes.append(c)

    if len(closes) < period:
        return {"k": None, "d": None, "j": None}

    # Compute %K raw RSV series, then smooth via simple recurrence:
    #   K = (2/3)*K_prev + (1/3)*RSV    (A 股 惯例)
    #   D = (2/3)*D_prev + (1/3)*K
    #   J = 3*K - 2*D
    k_prev = 50.0
    d_prev = 50.0
    k_cur = k_prev
    d_cur = d_prev
    for i in range(period - 1, len(closes)):
        window_h = max(highs[i - period + 1: i + 1])
        window_l = min(lows[i - period + 1: i + 1])
        denom = window_h - window_l
        rsv = 50.0 if denom == 0 else (closes[i] - window_l) / denom * 100.0
        k_cur = (k_smooth - 1) / k_smooth * k_prev + 1.0 / k_smooth * rsv
        d_cur = (d_smooth - 1) / d_smooth * d_prev + 1.0 / d_smooth * k_cur
        k_prev, d_prev = k_cur, d_cur

    j_cur = 3.0 * k_cur - 2.0 * d_cur
    return {"k": k_cur, "d": d_cur, "j": j_cur}


# ---------------------------------------------------------------------------
# Bollinger Bands (20, 2σ)
# ---------------------------------------------------------------------------


def boll(
    bars_or_closes: Sequence[float | Bar],
    period: int = 20,
    num_std: float = 2.0,
) -> dict[str, float | None]:
    """Latest Bollinger snapshot: mid (SMA20), upper, lower, %B, bandwidth."""

    closes = _to_close_list(bars_or_closes)
    if len(closes) < period:
        return {
            "mid": None, "upper": None, "lower": None,
            "percent_b": None, "bandwidth": None,
        }
    window = closes[-period:]
    mid = sum(window) / period
    var = sum((x - mid) ** 2 for x in window) / period
    sigma = var ** 0.5
    upper = mid + num_std * sigma
    lower = mid - num_std * sigma
    last = closes[-1]
    width = upper - lower
    percent_b = None if width == 0 else (last - lower) / width
    bandwidth = None if mid == 0 else width / mid
    return {
        "mid": mid, "upper": upper, "lower": lower,
        "percent_b": percent_b, "bandwidth": bandwidth,
    }


# ---------------------------------------------------------------------------
# Volume MA + volume ratio
# ---------------------------------------------------------------------------


def volume_ma(bars: Sequence[Bar]) -> dict[str, float | None]:
    """Latest VOL_MA5 / VOL_MA10 + today's volume ratio vs 5-day mean.

    A 股 ``vol_ratio_today`` defined as ``today_vol / vol_ma5_yesterday``
    — anything ≥ 2.0 is "明显放量"; ≤ 0.5 is "明显缩量".
    """

    vols = _to_volume_list(bars)
    if not vols:
        return {"vol5": None, "vol10": None, "vol_ratio_today": None}
    v5 = _safe_mean(vols[-5:]) if len(vols) >= 5 else None
    v10 = _safe_mean(vols[-10:]) if len(vols) >= 10 else None
    ratio = None
    if len(vols) >= 6:
        vol_ma5_yesterday = _safe_mean(vols[-6:-1])
        if vol_ma5_yesterday and vol_ma5_yesterday > 0:
            ratio = vols[-1] / vol_ma5_yesterday
    return {"vol5": v5, "vol10": v10, "vol_ratio_today": ratio}


# ---------------------------------------------------------------------------
# ATR (Wilder, 14)
# ---------------------------------------------------------------------------


def atr(bars: Sequence[Bar], period: int = 14) -> float | None:
    """Average true range over the latest ``period`` bars."""

    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    prev_close: float | None = None
    for b in bars:
        if not isinstance(b, Mapping):
            continue
        try:
            h = float(b["high"]); l = float(b["low"]); c = float(b["close"])
        except (TypeError, ValueError, KeyError):
            continue
        if prev_close is None:
            tr = h - l
        else:
            tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
        prev_close = c
    if len(trs) < period + 1:
        return None
    # Wilder smoothing
    cur = sum(trs[1:period + 1]) / period
    for i in range(period + 1, len(trs)):
        cur = (cur * (period - 1) + trs[i]) / period
    return cur


# ---------------------------------------------------------------------------
# OBV
# ---------------------------------------------------------------------------


def obv(bars: Sequence[Bar]) -> float | None:
    """On-balance volume (cumulative, latest value).

    OBV[t] = OBV[t-1] + sign(close[t] - close[t-1]) * vol[t]
    """

    closes = _to_close_list(bars)
    vols = _to_volume_list(bars)
    if len(closes) < 2 or len(closes) != len(vols):
        return None
    total = 0.0
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            total += vols[i]
        elif closes[i] < closes[i - 1]:
            total -= vols[i]
    return total


# ---------------------------------------------------------------------------
# All-in-one snapshot (single call from derive layer)
# ---------------------------------------------------------------------------


def compute_all(
    bars: Sequence[Bar],
    ma_windows: Sequence[int] = DEFAULT_MA_WINDOWS,
) -> dict[str, dict | None]:
    """Compute the standard battery of technicals from a single bar series.

    Returns a dict shaped for direct emission as multiple SQLite dp_ids::

        {
          "ma":        {ma5, ma10, ma20, ma60, ma120, ma250},
          "macd":      {dif, dea, hist, cross},
          "rsi":       {rsi6, rsi12, rsi24},
          "kdj":       {k, d, j},
          "boll":      {mid, upper, lower, percent_b, bandwidth},
          "vol_ma":    {vol5, vol10, vol_ratio_today},
          "atr14":     float | None,
          "obv":       float | None,
          "as_of":     str | None,   # date of the latest bar, if present
          "n_bars":    int,
        }

    ``bars`` should be ascending by date (oldest → latest).
    """

    return {
        "ma": moving_averages(bars, ma_windows),
        "macd": macd(bars),
        "rsi": rsi(bars),
        "kdj": kdj(bars),
        "boll": boll(bars),
        "vol_ma": volume_ma(bars),
        "atr14": atr(bars, 14),
        "obv": obv(bars),
        "as_of": _latest_date(bars),
        "n_bars": len(bars),
    }


def _latest_date(bars: Sequence[Bar]) -> str | None:
    if not bars:
        return None
    last = bars[-1]
    if isinstance(last, Mapping):
        d = last.get("date") or last.get("trade_date")
        if d is not None:
            return str(d)
    return None


# ---------------------------------------------------------------------------
# Series helper — bars + per-bar SMA overlays for FrontEnd K-line chart
# ---------------------------------------------------------------------------


def compute_series_with_ma(
    bars: Sequence[Bar],
    periods: Sequence[int] = (5, 10, 20, 60),
) -> list[dict[str, float | str | None]]:
    """Return a flat list of per-bar dicts with OHLCV + MAs for each requested
    period, aligned 1:1 with ``bars`` (ascending by date).

    Each entry is shaped::

        {"date": "20260301", "open": 10.1, "high": 10.5, "low": 9.8,
         "close": 10.3, "vol": 12345,
         "ma5": null | float, "ma10": null | float,
         "ma20": null | float, "ma60": null | float}

    ``ma{p}`` keys mirror ``periods`` — extend by passing e.g.
    ``periods=(5, 10, 20, 60, 120)``. Entries before index ``p - 1`` carry
    ``ma{p} = None`` because SMA needs a full window of closes. This shape is
    what the FrontEnd K-line + 均线叠加图 consumes directly.
    """

    closes = _to_close_list(bars)
    ma_lookup: dict[int, list[float | None]] = {
        p: sma_series(closes, p) for p in periods
    }

    out: list[dict[str, float | str | None]] = []
    for i, bar in enumerate(bars):
        if not isinstance(bar, Mapping):
            continue
        date_v = bar.get("date") or bar.get("trade_date")
        row: dict[str, float | str | None] = {
            "date": str(date_v) if date_v is not None else None,
            "open": _coerce_float(bar.get("open")),
            "high": _coerce_float(bar.get("high")),
            "low": _coerce_float(bar.get("low")),
            "close": _coerce_float(bar.get("close")),
            "vol": _coerce_float(bar.get("vol") if bar.get("vol") is not None
                                  else bar.get("volume")),
        }
        for p in periods:
            series = ma_lookup[p]
            row[f"ma{p}"] = series[i] if i < len(series) else None
        out.append(row)
    return out


def _coerce_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


__all__ = [
    "DEFAULT_MA_WINDOWS",
    "Bar",
    "atr",
    "boll",
    "compute_all",
    "compute_series_with_ma",
    "ema_series",
    "kdj",
    "macd",
    "moving_averages",
    "obv",
    "rsi",
    "sma_series",
    "volume_ma",
]
