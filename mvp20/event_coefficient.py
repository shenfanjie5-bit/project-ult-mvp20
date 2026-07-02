"""Signed event-impact coefficient for the real-time event stream.

Maps a structured corporate-event payload to a bounded ``[-1, 1]`` coefficient =
the expected SIZE-ADJUSTED abnormal return (entry t+1, horizon h=1 day). This is
the ONLY event signal that passed the pre-registered kill criteria in the
2026-06 event study (业绩预告 / forecast). See
``docs/audit/event_impact_FINAL_2026-06-09.md`` and
``factor_research/04_event_study/`` for the evidence.

Honesty contract (enforced by callers):
  * ONLY forecast (``L9.company.earnings_guidance``) returns ``validated=True``.
    Free-text news (Track B) has NO historical validation yet → no coefficient
    (``news_coefficient_meta`` → ``validated=False``); it must not be shown as a
    predictive signal until forward-collection validates it.
  * The forecast coefficient is a market/size-NEUTRAL (hedged) alpha: ~+30bps/
    event hedged vs only ~+9bps unhedged; the negative (short) leg is fragile
    (survivorship); events cluster in the Jan/Jul preannouncement windows. These
    caveats ride along in ``coefficient_meta`` so the UI never overstates it.

Pure functions, no I/O — trivially unit-testable.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

# Forecast type vocab — mirrors scripts/script_fill.py:_FORECAST_{POS,NEG}_TYPES
# (kept in sync deliberately; mvp20 must not import from scripts/).
_POS_TYPES = ("预增", "略增", "扭亏", "续盈", "首盈", "减亏")
_NEG_TYPES = ("预减", "略减", "首亏", "续亏", "增亏", "预亏")

# Calibrated expected h=1 size-adjusted abnormal return (return units) per type,
# from the validated quintile curve (FINAL §2): positive guidance ranges
# +0.2%~+1.1% with announced growth, negative -0.6%~0, weak/categorical types sit
# near a small baseline. 略增/略减 are intentionally ~0 (no edge in the study).
_BASE_ABN = {
    "预增": 0.004, "略增": 0.001, "扭亏": 0.004, "续盈": 0.002, "首盈": 0.003, "减亏": 0.002,
    "预减": -0.004, "略减": -0.001, "首亏": -0.005, "续亏": -0.003, "增亏": -0.005, "预亏": -0.004,
}
# Only 预增/预减 carry a meaningful growth magnitude; scale up to ±_MAG_GAIN by
# |announced growth| (capped). 扭亏/首亏 etc. are loss-base ratios → categorical only.
_MAG_SIGN = {"预增": 1.0, "预减": -1.0}
_MAG_CAP = 1.2            # |growth| beyond +120% adds nothing more
_MAG_GAIN = 0.008
_ABN_CAP = 0.012         # cap |E[abn]| at 1.2%
_K = 200.0               # tanh gain: +0.5% -> 0.76, +1.1% -> 0.98

_SEASONAL = "jan_jul_seasonal"
_SHORT_LEG_SOFT = "short_leg_survivorship_fragile"


def _forecast_sign(typ: str) -> int:
    if any(t in typ for t in _POS_TYPES):
        return 1
    if any(t in typ for t in _NEG_TYPES):
        return -1
    return 0


def _expected_abnormal(typ: str, growth: float | None) -> float:
    """Expected h=1 size-adjusted abnormal return for a forecast type + |growth|."""
    base = next((v for k, v in _BASE_ABN.items() if k in typ), 0.0)
    if growth is not None:
        ms = next((s for k, s in _MAG_SIGN.items() if k in typ), 0.0)
        if ms:
            base += ms * _MAG_GAIN * min(abs(growth), _MAG_CAP) / _MAG_CAP
    return max(-_ABN_CAP, min(_ABN_CAP, base))


def forecast_coefficient(payload: Mapping[str, Any]) -> dict | None:
    """Validated signed coefficient for a 业绩预告 (``L9.company.earnings_guidance``)
    payload (see tushare_source._fetch_a_share_forecast for its shape).

    Returns ``{coefficient, validated, model, direction, horizon_days, basis,
    caveats}`` or ``None`` when the payload carries no clear directional forecast
    (e.g. 不确定 / missing type) — callers SKIP such events rather than show 0.
    """
    if not isinstance(payload, Mapping):
        return None
    typ = str(payload.get("type") or "").strip()
    sign = _forecast_sign(typ)
    if sign == 0:
        return None
    vals = [float(v) for v in (payload.get("change_pct_min"), payload.get("change_pct_max"))
            if isinstance(v, (int, float))]
    growth = (sum(vals) / len(vals) / 100.0) if vals else None
    coef = math.tanh(_K * _expected_abnormal(typ, growth))
    caveats = [_SEASONAL] + ([_SHORT_LEG_SOFT] if sign < 0 else [])
    return {
        "coefficient": round(coef, 4),
        "validated": True,
        "model": "forecast_v1",
        "direction": "positive" if sign > 0 else "negative",
        "horizon_days": 1,
        "basis": "size-adjusted abnormal CAR",
        "caveats": caveats,
    }


def news_coefficient_meta() -> dict:
    """Track B (free-text news) carries NO validated coefficient yet. Callers emit
    ``coefficient: null`` + this meta so the UI shows it as unknown, not a signal."""
    return {"validated": False, "reason": "track_b_forward_only"}
