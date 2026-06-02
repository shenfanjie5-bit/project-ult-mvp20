"""Derived-layer calculator for L6 / L7 / L8 / L10 / L11 dp_ids.

Spec v2 designates a large class of dp_ids as **derived** (not directly
available from any data source) — they are functions of other dp_ids and
short historical windows. ~124 of the 250 spec dp_ids carry
``source_status: ○ (possible_but_not_integrated)`` which means: at least
one source contributes partial info, but a derive/aggregate step is
required to produce the final value.

This module owns those derive formulas. It runs after a collector cycle:

  1. For each ``ts_code``, ``read_hot_snapshot`` pulls every available
     dp_id (per-stock + sentinels for INDUSTRY:* and MARKET:*).
  2. Each derive formula consumes a curated subset of the snapshot and
     emits a payload dict (or ``None`` if input was wholly missing).
  3. Results are UPSERTed back into ``realtime_current`` with
     ``source="derive:<formula_id>"`` so they are addressable by the
     scoring/aggregation layers like any other dp_id.

Architecture
============

Three families coexist:

  * Tier 0 (legacy): the historical Tushare-backed derives that need
    multi-day price/turnover/PE windows — ``derive_run_up``,
    ``derive_crowdedness``, ``derive_historical_quantile``,
    ``derive_overvalued``. These still run via ``derive_all``.

  * Tier 1-4 (new, this commit): snapshot-only derives that compose hard
    data already collected into ``realtime_current``. These run via the
    new ``DeriveRunner`` and emit ``source="derive:<formula>"`` rows.

  * Composite scores (``L11.short.score`` / ``L11.mid.score`` /
    ``L11.long.score``) consume Tier 2-4 outputs.

Run
===

  ``.venv/bin/python -m mvp20 derive --db runtime/hot.sqlite``
      Tier 0 history derive (Tushare).

  ``.venv/bin/python -m mvp20 derive-snapshot --db runtime/hot.sqlite``
      Tier 1-4 snapshot derive (this commit).

Confidence decay
================

Each derive function returns a ``confidence`` field. The driver decays
that by 10% per layer (``output_conf = min(input_confs) * 0.9``) so
multi-layer derives degrade gracefully.

Missing-input handling
======================

If every required input for a formula is missing, the driver emits a row
with ``data_status="Inactive"``, the governance ``neutral_value``, and
``confidence=0.3`` — that way downstream scoring can still find the
dp_id, just neutralized.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

log = logging.getLogger("mvp20.derive")

DEFAULT_TUSHARE_TIMEOUT_SECONDS = 10.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentile_rank(current: float, history: list[float]) -> float | None:
    """Return current's percentile rank within history (0..1). None if empty."""

    if not history:
        return None
    sorted_h = sorted(h for h in history if h is not None)
    if not sorted_h:
        return None
    n_below = sum(1 for h in sorted_h if h < current)
    return n_below / len(sorted_h)


def _safe_load(value_json: str | None) -> Any:
    if not value_json:
        return None
    try:
        return json.loads(value_json)
    except (ValueError, TypeError):
        return None


def _read_realtime_value(conn: sqlite3.Connection, ts_code: str, dp_id: str) -> Any:
    row = conn.execute(
        "SELECT value_json FROM realtime_current WHERE ts_code = ? AND dp_id = ?",
        (ts_code, dp_id),
    ).fetchone()
    return _safe_load(row[0]) if row else None


def _is_mock_source(source: Any) -> bool:
    """True when a realtime_current row originates from a fabricated/mock
    feed (``source`` starting ``"mock:"``). Such rows carry placeholder
    scalars and must never feed quantitative derives."""

    return isinstance(source, str) and source.startswith("mock:")


def _value_if_not_mock(value: Any, source: Any) -> Any:
    """Pure mock guard: return ``value`` unless ``source`` is a mock feed,
    in which case return ``None``. Kept tiny + side-effect free so it can be
    unit-tested offline without a Tushare client or live DB."""

    return None if _is_mock_source(source) else value


def _read_realtime_value_with_source(
    conn: sqlite3.Connection, ts_code: str, dp_id: str
) -> tuple[Any, str | None]:
    """Like :func:`_read_realtime_value` but also returns the row's ``source``
    so callers can reject mock feeds. Returns ``(value, source)``; ``value``
    is ``None`` when the row is absent or its source is ``mock:*``."""

    row = conn.execute(
        "SELECT value_json, source FROM realtime_current WHERE ts_code = ? AND dp_id = ?",
        (ts_code, dp_id),
    ).fetchone()
    if not row:
        return None, None
    source = row[1]
    return _value_if_not_mock(_safe_load(row[0]), source), source


def _coerce_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float coercion. Returns ``default`` for None/NaN/non-numeric."""

    if value is None:
        return default
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return f


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _input_conf(*inputs: Mapping[str, Any] | None, default: float = 0.5) -> float:
    """Min over input confidences, used as base for derive decay."""

    confs = []
    for inp in inputs:
        if isinstance(inp, Mapping) and inp.get("confidence") is not None:
            try:
                confs.append(float(inp["confidence"]))
            except (TypeError, ValueError):
                pass
    if not confs:
        return default
    return min(confs)


def _decay(input_conf: float, factor: float = 0.9) -> float:
    """Per-layer confidence decay: each derive multiplies by ``factor``."""

    return max(0.0, min(1.0, input_conf * factor))


# ---------------------------------------------------------------------------
# Tier 0 (legacy): historical derives — kept verbatim
# ---------------------------------------------------------------------------


def derive_run_up(daily_close: list[float]) -> dict | None:
    """L6.priced.run_up — 5/20/60-day price change percentage. Requires at
    least 6 days of closing prices (latest day first or last is fine; we
    sort by index)."""

    if not daily_close or len(daily_close) < 6:
        return None
    # Assume daily_close[0] is the most recent
    latest = daily_close[0]
    series = daily_close
    out: dict[str, float | None] = {}
    for window in (5, 20, 60):
        if len(series) > window:
            ref = series[window]
            if ref and ref != 0:
                out[f"d{window}_pct"] = (latest - ref) / ref
            else:
                out[f"d{window}_pct"] = None
        else:
            out[f"d{window}_pct"] = None
    return {**out, "latest_close": latest, "history_days": len(series)}


def derive_crowdedness(
    current_turnover_rate: float | None,
    history_turnover_rates: list[float],
) -> dict | None:
    """L6.priced.crowdedness — current turnover-rate percentile within last
    N days. Higher = more crowded."""

    if current_turnover_rate is None or not history_turnover_rates:
        return None
    pct = _percentile_rank(current_turnover_rate, history_turnover_rates)
    if pct is None:
        return None
    label = (
        "extreme" if pct > 0.9 else
        "crowded" if pct > 0.75 else
        "elevated" if pct > 0.5 else
        "neutral"
    )
    return {
        "percentile": pct,
        "label": label,
        "current_turnover_rate": current_turnover_rate,
        "history_window_days": len(history_turnover_rates),
    }


def derive_historical_quantile(
    current_pe: float | None, history_pe: list[float],
    current_pb: float | None, history_pb: list[float],
) -> dict | None:
    """L10.val.historical_quantile — current PE/PB vs N-year history."""

    out: dict[str, Any] = {}
    if current_pe is not None and history_pe:
        pe_pct = _percentile_rank(current_pe, [p for p in history_pe if p and p > 0])
        out["pe_percentile"] = pe_pct
    if current_pb is not None and history_pb:
        pb_pct = _percentile_rank(current_pb, [p for p in history_pb if p and p > 0])
        out["pb_percentile"] = pb_pct
    if not out:
        return None
    out["history_window_days"] = max(len(history_pe or []), len(history_pb or []))
    return out


def derive_overvalued(quantile_payload: dict | None) -> dict | None:
    """L8.val.overvalued — boolean + severity from PE/PB percentile."""

    if not quantile_payload:
        return None
    pe_pct = quantile_payload.get("pe_percentile")
    pb_pct = quantile_payload.get("pb_percentile")
    max_pct = max(filter(lambda x: x is not None, [pe_pct, pb_pct]), default=None)
    if max_pct is None:
        return None
    severity = (
        "extreme" if max_pct > 0.95 else
        "high" if max_pct > 0.80 else
        "elevated" if max_pct > 0.60 else
        "normal"
    )
    return {
        "is_overvalued": max_pct > 0.80,
        "severity": severity,
        "max_quantile": max_pct,
        "pe_pct": pe_pct,
        "pb_pct": pb_pct,
    }


# ---------------------------------------------------------------------------
# Tier 4 derives (L7 / L10 mirror): smallest dependency set
# ---------------------------------------------------------------------------


def derive_l7_env_risk_appetite(
    market_trend: Mapping[str, Any] | None,
    style: Mapping[str, Any] | None,
    macro_liquidity: Mapping[str, Any] | None,
    macro_rates: Mapping[str, Any] | None,
) -> dict | None:
    """L7.env.risk_appetite — market-wide risk appetite multiplier.

    Composes 4 macro inputs into a single multiplier in roughly ``[0.7, 1.3]``:

      * ``market_trend.regime`` (bull/range/bear) -> +/-
      * ``style.regime`` (growth/value) -> small tilt
      * ``macro_liquidity.m2_yoy_pct`` (M2 growth) -> liquidity tailwind
      * ``macro_rates.lpr_1y_pct`` (LPR) -> rates headwind

    Spec §27.4: risk-appetite multiplier modulates capital_sentiment.
    """

    have_any = any(x for x in (market_trend, style, macro_liquidity, macro_rates))
    if not have_any:
        return None

    multiplier = 1.0
    drivers: list[str] = []

    # Market trend
    if isinstance(market_trend, Mapping):
        regime = market_trend.get("regime") or market_trend.get("label")
        if regime in ("bull", "strong_bull"):
            multiplier *= 1.15
            drivers.append("trend↑")
        elif regime in ("bear", "strong_bear"):
            multiplier *= 0.85
            drivers.append("trend↓")
        scalar = _coerce_float(market_trend.get("scalar"), 0.0)
        if scalar:
            multiplier *= 1.0 + _clip(scalar, -0.3, 0.3) * 0.25
            drivers.append(f"trend_scalar={scalar:.2f}")

    # Style tilt
    if isinstance(style, Mapping):
        s = style.get("growth_minus_value") or style.get("scalar")
        if s is not None:
            multiplier *= 1.0 + _clip(_coerce_float(s), -0.3, 0.3) * 0.10
            drivers.append("style_tilt")

    # Liquidity (M2 vs 8% baseline)
    if isinstance(macro_liquidity, Mapping):
        m2 = _coerce_float(macro_liquidity.get("m2_yoy_pct"), 8.0)
        liq_factor = 1.0 + _clip((m2 - 8.0) / 100.0, -0.10, 0.10)
        multiplier *= liq_factor
        if abs(m2 - 8.0) > 1.0:
            drivers.append(f"M2={m2:.1f}%")

    # Rates (LPR 3% baseline; higher LPR = lower risk appetite)
    if isinstance(macro_rates, Mapping):
        lpr = _coerce_float(macro_rates.get("lpr_1y_pct"), 3.0)
        rate_factor = 1.0 - _clip((lpr - 3.0) / 10.0, -0.10, 0.10)
        multiplier *= rate_factor
        if abs(lpr - 3.0) > 0.25:
            drivers.append(f"LPR={lpr:.2f}%")

    multiplier = _clip(multiplier, 0.7, 1.3)
    label = (
        "risk_on" if multiplier > 1.08 else
        "risk_off" if multiplier < 0.92 else
        "neutral"
    )
    return {
        "multiplier": multiplier,
        "label": label,
        "drivers": drivers,
        "inputs_used": sum(1 for x in (market_trend, style, macro_liquidity, macro_rates) if x),
    }


def derive_l7_mood_fomo(
    media_social: Mapping[str, Any] | None,
    active_inflow: Mapping[str, Any] | None,
    theme: Mapping[str, Any] | None,
) -> dict | None:
    """L7.mood.fomo — overheat risk from social + flow + theme concentration.

    Score in ``[0, 1]``: higher = more FOMO / overheat risk. Spec §27.4:
    fomo is a ``discount`` against capital_sentiment.

      * ``media_social.in_top_100`` + concept_tag_count -> social heat
      * ``active_inflow.main_net`` 5-day flow surge -> capital chase
      * ``theme.concept_count`` rising concept tags -> theme inflation
    """

    if not any(x for x in (media_social, active_inflow, theme)):
        return None

    score = 0.0
    factors: list[str] = []

    if isinstance(media_social, Mapping):
        if media_social.get("in_top_100"):
            score += 0.25
            factors.append("top100_hot")
        ctc = _coerce_float(media_social.get("concept_tag_count"))
        if ctc >= 10:
            score += 0.15
            factors.append(f"concepts={ctc:.0f}")

    if isinstance(active_inflow, Mapping):
        main_net = _coerce_float(active_inflow.get("main_net"))
        if main_net > 50_000:
            score += 0.3
            factors.append(f"main_net+{main_net:.0f}万")
        elif main_net > 10_000:
            score += 0.15

    if isinstance(theme, Mapping):
        cc = _coerce_float(theme.get("concept_count"))
        if cc >= 10:
            score += 0.20
            factors.append(f"theme_concepts={cc:.0f}")
        elif cc >= 5:
            score += 0.10

    score = _clip(score, 0.0, 1.0)
    label = (
        "extreme" if score > 0.7 else
        "elevated" if score > 0.4 else
        "moderate" if score > 0.15 else
        "calm"
    )
    return {
        "score": score,
        "label": label,
        "factors": factors,
    }


def derive_l10_val_expansion_compression(
    state_expansion: Mapping[str, Any] | None,
    mult_pe: Mapping[str, Any] | None = None,
    historical_quantile: Mapping[str, Any] | None = None,
    historical_pct: Mapping[str, Any] | None = None,
) -> dict | None:
    """L10.val.expansion_compression — 10-layer verification view that mirrors
    ``L6.state.expansion_compression``.

    The 10-layer macro audit re-reports the same valuation expansion/compression
    state at the market verification layer so consumers can cross-check whether
    the stock-level state is consistent with the macro view.

    For A-share, the primary input is the Tushare-emitted
    ``L6.state.expansion_compression`` payload (PE vs 60d / 250d MA regime).

    For US/HK stocks where no upstream emits that dp_id, fall back to
    composing a regime label from FMP-driven inputs: current PE
    (``L6.mult.pe``) compared against the historical PE quantile
    (``L10.val.historical_quantile`` or ``L6.state.historical_percentile``)
    so the verification view still has something to report.
    """

    # Primary path: mirror upstream state_expansion verbatim.
    if isinstance(state_expansion, Mapping):
        out = dict(state_expansion)
        out["mirror_of"] = "L6.state.expansion_compression"
        return out

    # Fallback path: synthesise a regime label from PE + quantile inputs
    # (used when upstream L6.state.expansion_compression is unavailable, e.g.
    # US stocks without the Tushare history fetcher).
    pe_current: float | None = None
    if isinstance(mult_pe, Mapping):
        pe_current = mult_pe.get("scalar")
        if pe_current is None:
            pe_current = mult_pe.get("pe_ttm") or mult_pe.get("value")
        pe_current = _coerce_float(pe_current, 0.0) or None

    pe_pct: float | None = None
    for src in (historical_pct, historical_quantile):
        if isinstance(src, Mapping):
            cand = src.get("pe_percentile")
            if cand is not None:
                pe_pct = _coerce_float(cand)
                break

    if pe_current is None and pe_pct is None:
        return None

    if pe_pct is not None:
        if pe_pct >= 0.75:
            regime = "expanded"
        elif pe_pct <= 0.25:
            regime = "compressed"
        else:
            regime = "neutral"
    else:
        regime = "neutral"

    return {
        "pe_current": pe_current,
        "pe_percentile": pe_pct,
        "regime": regime,
        "mirror_of": "L6.state.expansion_compression",
        "fallback": "fmp_pe_quantile",
    }


def derive_l6_priced_run_up_snapshot(
    surprise_preprice: Mapping[str, Any] | None,
) -> dict | None:
    """L6.priced.run_up — snapshot fallback when Tushare history is absent.

    For A-shares, this dp_id is populated by the Tier 0 history derive
    (`derive_run_up` over Tushare daily closes). For US stocks we don't run
    that path; instead FMP's `/earnings` + `/historical-price-eod` already
    produce `L5.surprise.preprice` carrying ``run_up_5d_pct`` /
    ``run_up_10d_pct`` / ``run_up_20d_pct``. Re-shape those into the
    standard ``d5_pct``/``d20_pct``/``d60_pct`` payload so downstream
    derives (`L6.path.second_derivative`, `L8.val.priced_in`) work
    unchanged on US tickers.

    Returns ``None`` when no preprice payload is available (so the
    DeriveRunner emits Inactive). When called for an A-share that already
    has a Tier 0 emit, the runner's skip-on-existing-known guard prevents
    this fallback from clobbering the better value.
    """

    if not isinstance(surprise_preprice, Mapping):
        return None
    d5 = surprise_preprice.get("run_up_5d_pct")
    d10 = surprise_preprice.get("run_up_10d_pct")
    d20 = surprise_preprice.get("run_up_20d_pct")
    if d5 is None and d10 is None and d20 is None:
        return None
    payload: dict[str, Any] = {
        "d5_pct": _coerce_float(d5) if d5 is not None else None,
        "d10_pct": _coerce_float(d10) if d10 is not None else None,
        "d20_pct": _coerce_float(d20) if d20 is not None else None,
        "d60_pct": None,
        "source": "L5.surprise.preprice",
    }
    return payload


def derive_l8_val_overvalued_snapshot(
    historical_quantile: Mapping[str, Any] | None,
    historical_pct: Mapping[str, Any] | None,
    mult_peg: Mapping[str, Any] | None = None,
    mult_pe: Mapping[str, Any] | None = None,
) -> dict | None:
    """L8.val.overvalued — snapshot fallback when Tier 0 history is absent.

    Composes the same overvalued boolean + severity label that
    ``derive_overvalued`` produces from PE/PB percentile data — but works
    on snapshot inputs only:

      * Prefer ``L10.val.historical_quantile`` (per-stock PE/PB percentile
        within own history; populated by Tushare A-share Tier 0 OR FMP key
        metrics aggregations for US tickers).
      * Fall back to ``L6.state.historical_percentile`` (alias, same shape).
      * As a last resort, use PEG (``L6.mult.peg``) banding: PEG >= 2 =>
        high, PEG >= 1.5 => elevated, PEG < 1.0 with positive growth =>
        normal. This gives US stocks at least one severity classification
        even when no PE history is available yet.

    Returns ``None`` only when every source is missing.
    """

    pe_pct = pb_pct = None
    src_payload = historical_quantile if isinstance(historical_quantile, Mapping) else historical_pct
    if isinstance(src_payload, Mapping):
        pe_pct = src_payload.get("pe_percentile")
        pb_pct = src_payload.get("pb_percentile")

    if pe_pct is not None or pb_pct is not None:
        max_pct = max(
            (p for p in (_coerce_float(pe_pct, -1.0), _coerce_float(pb_pct, -1.0)) if p >= 0),
            default=None,
        )
        if max_pct is not None:
            severity = (
                "extreme" if max_pct > 0.95 else
                "high" if max_pct > 0.80 else
                "elevated" if max_pct > 0.60 else
                "normal"
            )
            return {
                "is_overvalued": max_pct > 0.80,
                "severity": severity,
                "max_quantile": max_pct,
                "pe_pct": _coerce_float(pe_pct, 0.0) if pe_pct is not None else None,
                "pb_pct": _coerce_float(pb_pct, 0.0) if pb_pct is not None else None,
                "source": "historical_quantile",
            }

    # PEG fallback (US stocks without PE/PB history). PEG > 2 ≈ rich, < 1 ≈ cheap.
    peg = None
    if isinstance(mult_peg, Mapping):
        peg = mult_peg.get("scalar") or mult_peg.get("value")
    if peg is not None:
        pegf = _coerce_float(peg)
        if pegf > 0:
            severity = (
                "high" if pegf >= 2.0 else
                "elevated" if pegf >= 1.5 else
                "normal" if pegf >= 1.0 else
                "normal"
            )
            return {
                "is_overvalued": pegf >= 2.0,
                "severity": severity,
                "peg": pegf,
                "source": "L6.mult.peg",
            }

    return None


# ---------------------------------------------------------------------------
# Tier 3 derives (L8 risk)
# ---------------------------------------------------------------------------


def derive_l8_industry_demand_supply(
    demand_terminal: Mapping[str, Any] | None,
    supply_capacity: Mapping[str, Any] | None,
    supply_inventory: Mapping[str, Any] | None,
    demand_replacement: Mapping[str, Any] | None,
) -> dict | None:
    """L8.industry.demand_supply — risk score from demand/supply imbalance.

    Positive risk score means supply > demand (price pressure). Returns
    score in ``[-1, 1]`` (negative => demand surplus, positive => supply glut).
    """

    inputs = [demand_terminal, supply_capacity, supply_inventory, demand_replacement]
    if not any(x for x in inputs):
        return None

    demand_score = 0.0
    supply_score = 0.0
    drivers: list[str] = []

    if isinstance(demand_terminal, Mapping):
        s = _coerce_float(demand_terminal.get("growth_pct") or demand_terminal.get("scalar"))
        demand_score += _clip(s / 20.0, -1.0, 1.0)
        if abs(s) > 5:
            drivers.append(f"terminal_demand={s:+.1f}%")
    if isinstance(demand_replacement, Mapping):
        r = _coerce_float(demand_replacement.get("cycle_position") or demand_replacement.get("scalar"))
        demand_score += _clip(r, -1.0, 1.0) * 0.5

    if isinstance(supply_capacity, Mapping):
        c = _coerce_float(supply_capacity.get("utilization_pct") or supply_capacity.get("scalar"), 75.0)
        # Utilization > 85% = tight supply (good), < 65% = oversupply (bad)
        supply_score += _clip((85.0 - c) / 20.0, -1.0, 1.0)
        if c > 90 or c < 65:
            drivers.append(f"capacity_util={c:.0f}%")
    if isinstance(supply_inventory, Mapping):
        days = _coerce_float(supply_inventory.get("days_on_hand") or supply_inventory.get("scalar"), 60.0)
        supply_score += _clip((days - 60.0) / 60.0, -0.5, 0.5)
        if days > 90 or days < 30:
            drivers.append(f"inv_days={days:.0f}")

    # Imbalance: positive => supply glut (bad), negative => demand surplus (good)
    imbalance = _clip(supply_score - demand_score, -1.0, 1.0)
    severity = (
        "severe_glut" if imbalance > 0.6 else
        "soft_demand" if imbalance > 0.3 else
        "balanced" if abs(imbalance) <= 0.3 else
        "tight_supply" if imbalance > -0.6 else
        "strong_demand"
    )
    return {
        "score": imbalance,
        "demand_score": demand_score,
        "supply_score": supply_score,
        "severity": severity,
        "drivers": drivers,
    }


def derive_l8_industry_price_war(
    price_discount: Mapping[str, Any] | None,
    compete_price_war: Mapping[str, Any] | None,
    price_pricing_power: Mapping[str, Any] | None,
) -> dict | None:
    """L8.industry.price_war — price-war intensity from discount + L0.compete proxy.

    Returns score in ``[0, 1]`` where 1 = severe price war.
    """

    inputs = [price_discount, compete_price_war, price_pricing_power]
    if not any(x for x in inputs):
        return None

    score = 0.0
    drivers: list[str] = []

    if isinstance(price_discount, Mapping):
        d = _coerce_float(price_discount.get("discount_pct") or price_discount.get("scalar"))
        if d > 10:
            score += 0.4
            drivers.append(f"discount={d:.1f}%")
        elif d > 5:
            score += 0.2

    if isinstance(compete_price_war, Mapping):
        c = _coerce_float(compete_price_war.get("intensity") or compete_price_war.get("scalar"))
        score += _clip(c, 0.0, 1.0) * 0.4
        if c > 0.5:
            drivers.append(f"compete_war={c:.2f}")

    if isinstance(price_pricing_power, Mapping):
        p = _coerce_float(price_pricing_power.get("scalar"), 0.5)
        # Low pricing power => price war
        if p < 0.4:
            score += 0.25
            drivers.append("pricing_power_weak")
        elif p < 0.6:
            score += 0.10

    score = _clip(score, 0.0, 1.0)
    severity = (
        "severe" if score > 0.7 else
        "active" if score > 0.4 else
        "muted" if score > 0.15 else
        "none"
    )
    return {
        "score": score,
        "severity": severity,
        "drivers": drivers,
    }


def derive_l8_val_priced_in(
    run_up: Mapping[str, Any] | None,
    short_score: Mapping[str, Any] | None,
    overvalued: Mapping[str, Any] | None,
) -> dict | None:
    """L8.val.priced_in — proportion of upside already priced in by recent run.

    Composes 60-day run-up, current short-horizon score, and valuation severity:

      * Run-up high + valuation severe + score positive => heavily priced in
      * Run-up flat + valuation normal + score positive => fresh story
    """

    if not any(x for x in (run_up, short_score, overvalued)):
        return None

    score = 0.0
    factors: list[str] = []

    if isinstance(run_up, Mapping):
        d60 = _coerce_float(run_up.get("d60_pct"))
        if d60 > 0.30:
            score += 0.40
            factors.append(f"60d涨幅 {d60*100:.0f}%")
        elif d60 > 0.15:
            score += 0.20

    if isinstance(overvalued, Mapping):
        sev = overvalued.get("severity")
        if sev in ("extreme", "high"):
            score += 0.35
            factors.append(f"估值{sev}")
        elif sev == "elevated":
            score += 0.15

    if isinstance(short_score, Mapping):
        s = _coerce_float(short_score.get("score"))
        if s > 0.4:
            score += 0.20
            factors.append(f"短期分 {s:+.2f}")

    score = _clip(score, 0.0, 1.0)
    label = (
        "fully_priced_in" if score >= 0.7 else
        "priced_in" if score >= 0.4 else
        "partial" if score >= 0.2 else
        "fresh"
    )
    return {
        "priced_in_score": score,
        "label": label,
        "factors": factors,
    }


# ---------------------------------------------------------------------------
# Tier 2 derives (L6 valuation)
# ---------------------------------------------------------------------------


def derive_l6_path_tag(
    mult_pe: Mapping[str, Any] | None,
    historical_pct: Mapping[str, Any] | None,
    quantile: Mapping[str, Any] | None,
    state_expansion: Mapping[str, Any] | None,
) -> dict | None:
    """L6.path.tag — valuation path classification.

    Classifies the current PE trajectory into one of:
      * 估值扩张 (expansion)   — PE rising, percentile rising
      * 估值压缩 (compression) — PE falling
      * 估值修复 (repair)      — PE rising from low base
      * 估值持平 (flat)        — small change
    """

    if not any(x for x in (mult_pe, historical_pct, quantile, state_expansion)):
        return None

    # If state_expansion has a tag already, use it
    if isinstance(state_expansion, Mapping) and state_expansion.get("path_tag"):
        tag = state_expansion["path_tag"]
        return {
            "tag": tag,
            "label": tag,
            "source": "L6.state.expansion_compression",
        }

    pe_pct = None
    if isinstance(historical_pct, Mapping):
        pe_pct = historical_pct.get("pe_percentile")
    if pe_pct is None and isinstance(quantile, Mapping):
        pe_pct = quantile.get("pe_percentile")

    pe_pct = _coerce_float(pe_pct, default=-1.0)
    if pe_pct < 0:
        # No basis for classification
        return {
            "tag": "估值持平",
            "label": "flat",
            "rationale": "insufficient historical context",
        }

    # Direction needs second-derivative-like input — fall back to percentile band
    if pe_pct > 0.75:
        tag, label = "估值扩张", "expansion"
    elif pe_pct < 0.25:
        tag, label = "估值修复", "repair"
    elif pe_pct < 0.40:
        tag, label = "估值压缩", "compression"
    else:
        tag, label = "估值持平", "flat"
    return {
        "tag": tag,
        "label": label,
        "pe_percentile": pe_pct,
    }


def derive_l6_path_second_derivative(
    historical_pct: Mapping[str, Any] | None,
    run_up: Mapping[str, Any] | None,
    surprise_preprice: Mapping[str, Any] | None = None,
) -> dict | None:
    """L6.path.second_derivative — rate-of-change of valuation expansion.

    Uses 20d vs 60d run-up as a proxy for valuation acceleration. Positive
    => accelerating expansion, negative => decelerating.

    For A-share the primary input is ``L6.priced.run_up`` (Tushare history
    derived) which carries ``d20_pct`` / ``d60_pct``. For US stocks where
    that Tier 0 derive is not run, fall back to FMP's
    ``L5.surprise.preprice`` payload which carries ``run_up_5d_pct`` /
    ``run_up_10d_pct`` / ``run_up_20d_pct`` so we still get an
    acceleration signal at the shorter horizons.
    """

    d20: float | None = None
    d60: float | None = None
    d5: float | None = None
    source = "L6.priced.run_up"

    if isinstance(run_up, Mapping):
        d20 = run_up.get("d20_pct")
        d60 = run_up.get("d60_pct")
        if d20 is None and d60 is None and "run_up_20d_pct" in run_up:
            # Tolerate caller passing a preprice-shaped payload directly.
            d20 = run_up.get("run_up_20d_pct")
            d5 = run_up.get("run_up_5d_pct")

    # Fallback: US side via L5.surprise.preprice (FMP). Only consult when
    # the primary run_up payload didn't yield numbers.
    if d20 is None and d60 is None and isinstance(surprise_preprice, Mapping):
        d20 = surprise_preprice.get("run_up_20d_pct")
        d5 = surprise_preprice.get("run_up_5d_pct")
        source = "L5.surprise.preprice"

    if d20 is None and d60 is None and d5 is None:
        return None

    d20f = _coerce_float(d20) if d20 is not None else 0.0
    d60f = _coerce_float(d60) if d60 is not None else 0.0
    d5f = _coerce_float(d5) if d5 is not None else 0.0
    d20_daily = d20f / 20.0 if d20 is not None else 0.0
    d60_daily = d60f / 60.0 if d60 is not None else 0.0
    d5_daily = d5f / 5.0 if d5 is not None else 0.0

    if d60 is not None and d20 is not None:
        second_deriv = d20_daily - d60_daily
    elif d20 is not None and d5 is not None:
        # No 60d horizon — compare 5d daily rate vs 20d daily rate. Same
        # sign convention (faster recent = accelerating).
        second_deriv = d5_daily - d20_daily
    else:
        second_deriv = d20_daily or d5_daily

    label = (
        "accelerating" if second_deriv > 0.002 else
        "decelerating" if second_deriv < -0.002 else
        "stable"
    )
    return {
        "second_derivative": second_deriv,
        "d20_daily": d20_daily,
        "d60_daily": d60_daily,
        "label": label,
        "source": source,
    }


def _l6_sens_factor(
    inputs: list[tuple[Mapping[str, Any] | None, float, float]],
    default: float = 1.0,
) -> dict | None:
    """Helper for L6.sens.* multiplicative-factor derives.

    ``inputs`` is a list of ``(payload, weight, neutral_value)``. Returns
    a multiplier in ``[0.5, 1.5]`` (or ``None`` if all inputs missing).
    """

    if not any(p for p, _w, _n in inputs):
        return None
    factor = default
    drivers: list[str] = []
    for payload, weight, neutral in inputs:
        if not isinstance(payload, Mapping):
            continue
        v = _coerce_float(
            payload.get("scalar") or payload.get("value") or payload.get("score"),
            neutral,
        )
        # Treat v as a deviation from neutral; map to multiplier
        delta = (v - neutral) / (neutral or 1.0) if neutral else v
        factor *= 1.0 + _clip(delta, -0.5, 0.5) * weight
        drivers.append(f"x={v:.3f}")
    factor = _clip(factor, 0.5, 1.5)
    return {"multiplier": factor, "drivers": drivers}


def derive_l6_sens_growth_margin(
    fina_gross_margin: Mapping[str, Any] | None,
    fina_revenue_yoy: Mapping[str, Any] | None,
    is_gross_margin: Mapping[str, Any] | None = None,
    is_revenue_growth: Mapping[str, Any] | None = None,
) -> dict | None:
    """L6.sens.growth_margin — valuation sensitivity to growth+margin.

    Higher margin and higher YoY growth => valuation supports premium
    multipliers.

    Inputs in priority order:
      * A-share (Tushare ``fina_indicator``): ``L5.fina.gross_margin``
        carries ``value`` as percent (e.g. 28.27 => 28.27%); ``L5.fina.revenue_yoy``
        likewise pct.
      * US (FMP ``income-statement`` / ``financial-growth``):
        ``L5.is.gross_margin`` carries ``scalar`` as ratio (0.71 => 71%);
        ``L5.is.revenue_growth`` carries ``yoy_pct`` as ratio (0.06 => 6%).

    We normalise both onto a percent scale (e.g. 28.27 or 71.0) before
    feeding ``_l6_sens_factor`` so the same baseline (25% margin, 10% YoY)
    is meaningful across markets.
    """

    margin_pct: float | None = None
    margin_conf: float | None = None
    if isinstance(fina_gross_margin, Mapping):
        v = fina_gross_margin.get("value")
        if v is not None:
            margin_pct = _coerce_float(v)
            margin_conf = _coerce_float(fina_gross_margin.get("confidence"), 0.5)
    if margin_pct is None and isinstance(is_gross_margin, Mapping):
        scalar = is_gross_margin.get("scalar")
        if scalar is None:
            scalar = is_gross_margin.get("value")
        if scalar is not None:
            f = _coerce_float(scalar)
            # FMP emits ratio (0..1) — convert to percent for baseline parity.
            margin_pct = f * 100.0 if abs(f) <= 1.5 else f
            margin_conf = _coerce_float(is_gross_margin.get("confidence"), 0.5)

    revenue_pct: float | None = None
    revenue_conf: float | None = None
    if isinstance(fina_revenue_yoy, Mapping):
        v = fina_revenue_yoy.get("value")
        if v is not None:
            revenue_pct = _coerce_float(v)
            revenue_conf = _coerce_float(fina_revenue_yoy.get("confidence"), 0.5)
    if revenue_pct is None and isinstance(is_revenue_growth, Mapping):
        yoy = is_revenue_growth.get("yoy_pct")
        if yoy is None:
            yoy = is_revenue_growth.get("value")
        if yoy is not None:
            f = _coerce_float(yoy)
            # FMP emits ratio (0.06 => 6%) — convert to percent.
            revenue_pct = f * 100.0 if abs(f) <= 5.0 else f
            revenue_conf = _coerce_float(is_revenue_growth.get("confidence"), 0.5)

    if margin_pct is None and revenue_pct is None:
        return None

    # Compose multiplier directly so we can record the normalised inputs.
    factor = 1.0
    drivers: list[str] = []
    if margin_pct is not None:
        delta = (margin_pct - 25.0) / 25.0
        factor *= 1.0 + _clip(delta, -0.5, 0.5) * 0.5
        drivers.append(f"gm={margin_pct:.2f}%")
    if revenue_pct is not None:
        delta = (revenue_pct - 10.0) / 10.0
        factor *= 1.0 + _clip(delta, -0.5, 0.5) * 0.5
        drivers.append(f"rev_yoy={revenue_pct:.2f}%")

    factor = _clip(factor, 0.5, 1.5)
    out: dict[str, Any] = {
        "multiplier": factor,
        "drivers": drivers,
        "gross_margin_pct": margin_pct,
        "revenue_yoy_pct": revenue_pct,
    }
    if margin_conf is not None or revenue_conf is not None:
        confs = [c for c in (margin_conf, revenue_conf) if c is not None]
        if confs:
            out["confidence"] = _decay(min(confs), 0.9)
    return out


def derive_l6_sens_cashflow(
    fina_ocf_quality: Mapping[str, Any] | None,
    cf_fcf: Mapping[str, Any] | None,
) -> dict | None:
    """L6.sens.cashflow — valuation sensitivity to cashflow quality."""

    if not isinstance(fina_ocf_quality, Mapping) and not isinstance(cf_fcf, Mapping):
        return None
    factor = 1.0
    drivers: list[str] = []
    if isinstance(fina_ocf_quality, Mapping):
        q = _coerce_float(fina_ocf_quality.get("value"), 50.0)
        factor *= 1.0 + _clip((q - 50.0) / 100.0, -0.20, 0.20)
        drivers.append(f"ocf_q={q:.0f}%")
    if isinstance(cf_fcf, Mapping):
        fcf = _coerce_float(cf_fcf.get("scalar"))
        if fcf > 0:
            factor *= 1.05
            drivers.append("FCF+")
        elif fcf < 0:
            factor *= 0.95
            drivers.append("FCF-")
    return {"multiplier": _clip(factor, 0.5, 1.5), "drivers": drivers}


def derive_l6_sens_rates(
    env_rates: Mapping[str, Any] | None,
    macro_rates: Mapping[str, Any] | None,
) -> dict | None:
    """L6.sens.rates — valuation sensitivity to interest rates.

    Higher LPR => lower valuation multiplier (long-duration discount).
    """

    rates = env_rates or macro_rates
    if not isinstance(rates, Mapping):
        return None
    lpr = _coerce_float(rates.get("lpr_1y_pct"), 3.0)
    factor = 1.0 - _clip((lpr - 3.0) / 10.0, -0.20, 0.20)
    return {
        "multiplier": _clip(factor, 0.5, 1.5),
        "drivers": [f"LPR_1Y={lpr:.2f}%"],
    }


def derive_l6_sens_risk_narrative(
    media_report: Mapping[str, Any] | None,
    company_news: Mapping[str, Any] | None,
    surprise: Mapping[str, Any] | None,
) -> dict | None:
    """L6.sens.risk_narrative — valuation sensitivity to narrative risk.

    Negative news/reports compress valuation; positive surprise expands.
    """

    inputs = [media_report, company_news, surprise]
    if not any(x for x in inputs):
        return None
    factor = 1.0
    drivers: list[str] = []
    if isinstance(media_report, Mapping):
        c = _coerce_float(media_report.get("count_24h"))
        if c > 5:
            factor *= 0.95
            drivers.append(f"media_24h={c:.0f}")
    if isinstance(company_news, Mapping):
        c = _coerce_float(company_news.get("count_24h") or company_news.get("count_recent"))
        if c > 10:
            factor *= 0.95
            drivers.append(f"news={c:.0f}")
    if isinstance(surprise, Mapping):
        ratings = surprise.get("rating_distribution") or {}
        buys = sum(int(ratings.get(k, 0)) for k in ("买入", "Buy", "增持", "强烈推荐"))
        sells = sum(int(ratings.get(k, 0)) for k in ("卖出", "Sell", "减持"))
        if buys > sells * 3 and buys > 5:
            factor *= 1.10
            drivers.append(f"buy_ratings={buys}")
        elif sells > buys:
            factor *= 0.90
    return {"multiplier": _clip(factor, 0.5, 1.5), "drivers": drivers}


# ---------------------------------------------------------------------------
# Tier 1: L11 composite scores (depend on Tier 2-4 outputs)
# ---------------------------------------------------------------------------


def derive_l11_short_score(
    event_impact: Mapping[str, Any] | None,
    flow_boost: Mapping[str, Any] | None,
    sentiment_shift: Mapping[str, Any] | None,
    technical: Mapping[str, Any] | None,
) -> dict | None:
    """L11.short.score — composite 1-5d horizon score from 4 sub-inputs.

    Spec §27.4: weighted_sum of event_impact + flow_boost + sentiment_shift
    + technical. Each sub-input contributes to short-term thesis.
    """

    sub_inputs = [event_impact, flow_boost, sentiment_shift, technical]
    if not any(x for x in sub_inputs):
        return None

    weights = {"event": 0.30, "flow": 0.30, "sentiment": 0.20, "technical": 0.20}
    score = 0.0
    used = 0
    rationale: list[str] = []

    if isinstance(event_impact, Mapping):
        s = _coerce_float(event_impact.get("score"))
        score += s * weights["event"]
        used += 1
        if abs(s) > 0.3:
            rationale.append(f"event{s:+.2f}")
    if isinstance(flow_boost, Mapping):
        s = _coerce_float(flow_boost.get("score"))
        score += s * weights["flow"]
        used += 1
        if abs(s) > 0.3:
            rationale.append(f"flow{s:+.2f}")
    if isinstance(sentiment_shift, Mapping):
        s = _coerce_float(sentiment_shift.get("score"))
        score += s * weights["sentiment"]
        used += 1
        if abs(s) > 0.3:
            rationale.append(f"sent{s:+.2f}")
    if isinstance(technical, Mapping):
        s = _coerce_float(technical.get("score"))
        score += s * weights["technical"]
        used += 1
        if abs(s) > 0.3:
            rationale.append(f"tech{s:+.2f}")

    # If only partial inputs, renormalize
    total_weight = sum(w for inp, w in zip(sub_inputs, weights.values()) if inp)
    if 0 < total_weight < sum(weights.values()):
        score = score / total_weight * sum(weights.values())

    score = _clip(score, -1.0, 1.0)
    label = (
        "bullish" if score > 0.3 else
        "neutral" if -0.3 <= score <= 0.3 else
        "bearish"
    )
    return {
        "score": score,
        "label": label,
        "horizon_days": 5,
        "factors_used": used,
        "rationale": rationale,
    }


def derive_l11_mid_score(
    orders_revenue: Mapping[str, Any] | None,
    margin_guidance: Mapping[str, Any] | None,
    eps_upward: Mapping[str, Any] | None,
) -> dict | None:
    """L11.mid.score — composite 1-2 quarter horizon score.

    Spec §27.4: weighted_sum of orders_revenue + margin_guidance + eps_upward.
    """

    sub_inputs = [orders_revenue, margin_guidance, eps_upward]
    if not any(x for x in sub_inputs):
        return None

    weights = {"orders": 0.40, "margin": 0.30, "eps": 0.30}
    score = 0.0
    used = 0
    rationale: list[str] = []

    if isinstance(orders_revenue, Mapping):
        # Prefer explicit score, else fall back to YoY growth pct normalized
        s = _coerce_float(orders_revenue.get("score"))
        if s == 0.0:
            growth = _coerce_float(orders_revenue.get("yoy_pct"))
            s = _clip(growth / 50.0, -1.0, 1.0)
        score += s * weights["orders"]
        used += 1
        if abs(s) > 0.3:
            rationale.append(f"orders{s:+.2f}")
    if isinstance(margin_guidance, Mapping):
        s = _coerce_float(margin_guidance.get("score"))
        score += s * weights["margin"]
        used += 1
    if isinstance(eps_upward, Mapping):
        s = _coerce_float(eps_upward.get("score"))
        if s == 0.0:
            # Fall back to forecast guidance change_pct
            cp = _coerce_float(eps_upward.get("change_pct_min")) + _coerce_float(eps_upward.get("change_pct_max"))
            if cp:
                s = _clip(cp / 200.0, -1.0, 1.0)
        score += s * weights["eps"]
        used += 1
        if abs(s) > 0.3:
            rationale.append(f"eps{s:+.2f}")

    total_weight = sum(w for inp, w in zip(sub_inputs, weights.values()) if inp)
    if 0 < total_weight < sum(weights.values()):
        score = score / total_weight * sum(weights.values())

    score = _clip(score, -1.0, 1.0)
    label = (
        "bullish" if score > 0.3 else
        "neutral" if -0.3 <= score <= 0.3 else
        "bearish"
    )
    return {
        "score": score,
        "label": label,
        "horizon_quarters": 1,
        "factors_used": used,
        "rationale": rationale,
    }


def derive_l11_long_score(
    industry_space: Mapping[str, Any] | None,
    compete_moat: Mapping[str, Any] | None,
    business_model: Mapping[str, Any] | None,
    margin: Mapping[str, Any] | None,
) -> dict | None:
    """L11.long.score — composite long-horizon score.

    Spec §27.4: weighted_sum of industry_space + compete_moat + business_model
    + margin. Long-term thesis is structurally weighted toward moat.
    """

    sub_inputs = [industry_space, compete_moat, business_model, margin]
    if not any(x for x in sub_inputs):
        return None

    weights = {"space": 0.25, "moat": 0.35, "model": 0.20, "margin": 0.20}
    score = 0.0
    used = 0

    for payload, key in zip(sub_inputs, weights.keys()):
        if not isinstance(payload, Mapping):
            continue
        s = _coerce_float(payload.get("score") or payload.get("scalar"))
        score += s * weights[key]
        used += 1

    total_weight = sum(w for inp, w in zip(sub_inputs, weights.values()) if inp)
    if 0 < total_weight < sum(weights.values()):
        score = score / total_weight * sum(weights.values())

    score = _clip(score, -1.0, 1.0)
    label = (
        "bullish" if score > 0.3 else
        "neutral" if -0.3 <= score <= 0.3 else
        "bearish"
    )
    return {
        "score": score,
        "label": label,
        "horizon": "long",
        "factors_used": used,
    }


# ---------------------------------------------------------------------------
# Mode classification + trade signal (depend on the three L11 horizons)
# ---------------------------------------------------------------------------


def derive_l11_mode(
    short_score: Mapping[str, Any] | None,
    mid_score: Mapping[str, Any] | None,
    long_score: Mapping[str, Any] | None,
    overvalued: Mapping[str, Any] | None,
    active_inflow: Mapping[str, Any] | None,
) -> dict | None:
    """L11.mode — classify current state into one of 7 spec §30 modes.

    Maps to: 强多头 / 温和多头 / 震荡消化 / 结构分化 / 杀估值 / 趋势反转 /
    等待验证. Threshold logic mirrors ``scoring.classify_mode`` but is
    expressed as a derive-friendly snapshot computation (no signal-pack
    plumbing required).
    """

    if not any(x for x in (short_score, mid_score, long_score)):
        return None

    s_short = _coerce_float(short_score.get("score") if isinstance(short_score, Mapping) else None)
    s_mid = _coerce_float(mid_score.get("score") if isinstance(mid_score, Mapping) else None)
    s_long = _coerce_float(long_score.get("score") if isinstance(long_score, Mapping) else None)
    central = (s_short + s_mid + s_long) / 3.0

    val_pressure = 0.0
    if isinstance(overvalued, Mapping):
        sev = overvalued.get("severity")
        val_pressure = {"extreme": 0.95, "high": 0.80, "elevated": 0.60, "normal": 0.20}.get(sev, 0.0)

    capital_flow = 0.0
    if isinstance(active_inflow, Mapping):
        mn = _coerce_float(active_inflow.get("main_net"))
        capital_flow = _clip(mn / 100_000, -1.0, 1.0)

    # --- mode selection (mirror spec §30) ---
    mode = None
    rationale = ""

    if s_long <= -0.3 and s_mid <= -0.2 and capital_flow <= -0.2:
        mode, rationale = "trend_reversal", "长/中线↓ 资金↓ (趋势反转)"
    elif val_pressure >= 0.6 and capital_flow <= -0.2 and s_mid < 0.2:
        mode, rationale = "de_rating", "估值高 + 资金撤 + 增速放缓 (杀估值)"
    elif s_long >= 0.4 and s_mid >= 0.2 and val_pressure < 0.6 and capital_flow >= 0.2:
        mode, rationale = "strong_bull", "长线↑ 中线↑ 估值合理 资金↑ (强多头)"
    elif s_long >= 0.2 and s_short < 0.2:
        mode, rationale = "structural_divergence", "长线利好但短期未跟 (结构分化)"
    elif s_short < 0.3 and abs(s_mid) < 0.2 and abs(capital_flow) < 0.3:
        mode, rationale = "digestion", "短期平淡 中线稳 资金轮动 (震荡消化)"
    elif s_long >= 0.2 and s_mid >= 0.0 and val_pressure < 0.8 and capital_flow >= 0.0:
        mode, rationale = "moderate_bull", "基本面稳 估值合理 资金稳 (温和多头)"
    elif central <= -0.20:
        mode, rationale = "trend_reversal", "整体分数偏负 (回退)"
    else:
        mode, rationale = "wait_for_confirmation", "信号不足 (等待验证)"

    # Confidence: average of available input confidences, decayed
    inps = [short_score, mid_score, long_score, overvalued, active_inflow]
    confs = [
        _coerce_float(x.get("confidence"), 0.5)
        for x in inps if isinstance(x, Mapping)
    ]
    confidence = min(confs) if confs else 0.5

    return {
        "mode": mode,
        "label": mode,
        "rationale": rationale,
        "central_score": central,
        "short": s_short, "mid": s_mid, "long": s_long,
        "valuation_pressure": val_pressure,
        "capital_flow": capital_flow,
        "confidence": confidence,
    }


def derive_l11_trade_signal(
    short_score: Mapping[str, Any] | None,
    mid_score: Mapping[str, Any] | None,
    long_score: Mapping[str, Any] | None,
    mode: Mapping[str, Any] | None,
) -> dict | None:
    """L11.trade.signal — BUY/HOLD/WATCH/AVOID label.

    Spec §27.4: derived from L11.short/mid/long.score + L11.mode.
    Thresholds mirror ``scoring._trading_signal_from_mix``.
    """

    if not any(x for x in (short_score, mid_score, long_score)):
        return None

    s = _coerce_float(short_score.get("score") if isinstance(short_score, Mapping) else None)
    m = _coerce_float(mid_score.get("score") if isinstance(mid_score, Mapping) else None)
    l_ = _coerce_float(long_score.get("score") if isinstance(long_score, Mapping) else None)
    # Spec §27.4 horizon weights: short 0.25 / medium 0.45 / long 0.30
    mix = s * 0.25 + m * 0.45 + l_ * 0.30

    # Mode can override: trend_reversal / de_rating force AVOID; strong_bull boosts
    mode_label = (mode or {}).get("mode") if isinstance(mode, Mapping) else None
    if mode_label in ("trend_reversal", "de_rating"):
        signal = "AVOID"
    elif mode_label == "wait_for_confirmation":
        signal = "WATCH"
    elif mix >= 0.45:
        signal = "BUY"
    elif mix >= 0.10:
        signal = "HOLD"
    elif mix >= -0.20:
        signal = "WATCH"
    else:
        signal = "AVOID"

    return {
        "signal": signal,
        "mix_score": mix,
        "short": s,
        "mid": m,
        "long": l_,
        "mode_label": mode_label,
    }


# ---------------------------------------------------------------------------
# Tushare history backfill — kept for Tier 0 derives
# ---------------------------------------------------------------------------


def _get_pro_api():
    import tushare as ts  # type: ignore

    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        from .sources import load_dotenv
        load_dotenv()
        token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        return None
    ts.set_token(token)
    return ts.pro_api(timeout=_tushare_timeout_seconds())


def _tushare_timeout_seconds() -> float:
    raw = os.environ.get("TUSHARE_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_TUSHARE_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError:
        log.warning(
            "[derive] invalid TUSHARE_TIMEOUT_SECONDS=%r; using %.1fs",
            raw,
            DEFAULT_TUSHARE_TIMEOUT_SECONDS,
        )
        return DEFAULT_TUSHARE_TIMEOUT_SECONDS
    if timeout <= 0:
        log.warning(
            "[derive] non-positive TUSHARE_TIMEOUT_SECONDS=%r; using %.1fs",
            raw,
            DEFAULT_TUSHARE_TIMEOUT_SECONDS,
        )
        return DEFAULT_TUSHARE_TIMEOUT_SECONDS
    return timeout


def _fetch_a_share_history(pro, ts_code: str, days: int = 90) -> dict:
    """Pull last N days of OHLCV + turnover_rate + PE + PB from Tushare.

    Returns a dict with:

    * ``close``         — desc list of close prices (latest first; used by
      legacy tier-0 derives)
    * ``turnover_rate`` — desc list (used for crowdedness)
    * ``pe_ttm`` / ``pb`` — desc lists (used for historical_quantile)
    * ``bars``          — **asc** list of full OHLCV Bar dicts ready to
      feed ``technicals.compute_all`` (oldest → latest)

    Splits the call into ``pro.daily`` (OHLCV) and ``pro.daily_basic``
    (turnover / valuation) — two calls but cheap with the existing 90-day
    cap and ``_BUCKET_A_SLEEP_S`` rate-limit.
    """

    end = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    start = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    out: dict[str, list] = {
        "close": [], "turnover_rate": [], "pe_ttm": [], "pb": [],
        "bars": [],
    }
    try:
        # pro.daily for full OHLCV — we now use high/low/vol too.
        df_p = pro.daily(
            ts_code=ts_code, start_date=start, end_date=end,
            fields="ts_code,trade_date,open,high,low,close,vol",
        )
        if df_p is not None and len(df_p) > 0:
            df_desc = df_p.sort_values("trade_date", ascending=False)
            out["close"] = [float(x) for x in df_desc["close"].dropna().tolist()]
            # technicals.compute_all expects ascending bars (oldest → latest).
            df_asc = df_p.sort_values("trade_date", ascending=True)
            bars: list[dict] = []
            for _, row in df_asc.iterrows():
                try:
                    bars.append({
                        "date": str(row.get("trade_date") or ""),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "vol": float(row["vol"]) if row.get("vol") is not None else 0.0,
                    })
                except (TypeError, ValueError, KeyError):
                    continue
            out["bars"] = bars
        # pro.daily_basic for PE/PB/turnover_rate
        df_b = pro.daily_basic(ts_code=ts_code, start_date=start, end_date=end,
                                fields="ts_code,trade_date,turnover_rate,pe_ttm,pb")
        if df_b is not None and len(df_b) > 0:
            df_b = df_b.sort_values("trade_date", ascending=False)
            out["turnover_rate"] = [float(x) for x in df_b["turnover_rate"].dropna().tolist()]
            out["pe_ttm"] = [float(x) for x in df_b["pe_ttm"].dropna().tolist()]
            out["pb"] = [float(x) for x in df_b["pb"].dropna().tolist()]
    except Exception as e:  # noqa: BLE001
        log.warning("[derive] history %s failed: %s", ts_code, e)
    return out


def _fetch_a_share_weekly_history(pro, ts_code: str, weeks: int = 120) -> list[dict]:
    """Pull ``weeks`` of weekly OHLCV bars via ``pro.weekly``.

    Returns ascending (oldest → latest) bar dicts shaped like
    ``_fetch_a_share_history``'s ``bars`` so the same technicals layer
    consumes them unchanged. Empty list on any error / missing token.

    Tushare ``pro.weekly`` schema:
        ts_code / trade_date / open / high / low / close / vol / amount
    """

    end = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    # Generous: 120 weeks ≈ 840 days; pad to 870 to absorb non-trading weeks.
    start = (datetime.now(tz=timezone.utc) - timedelta(days=weeks * 7 + 30)).strftime("%Y%m%d")
    try:
        df = pro.weekly(
            ts_code=ts_code, start_date=start, end_date=end,
            fields="ts_code,trade_date,open,high,low,close,vol",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[derive] weekly history %s failed: %s", ts_code, e)
        return []
    if df is None or len(df) == 0:
        return []
    df_asc = df.sort_values("trade_date", ascending=True)
    bars: list[dict] = []
    for _, row in df_asc.iterrows():
        try:
            bars.append({
                "date": str(row.get("trade_date") or ""),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "vol": float(row["vol"]) if row.get("vol") is not None else 0.0,
            })
        except (TypeError, ValueError, KeyError):
            continue
    return bars


def _fetch_a_share_monthly_history(pro, ts_code: str, months: int = 36) -> list[dict]:
    """Pull ``months`` of monthly OHLCV bars via ``pro.monthly``.

    Same shape as the weekly fetcher — ascending Bar dicts.
    """

    end = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    start = (datetime.now(tz=timezone.utc) - timedelta(days=months * 31 + 30)).strftime("%Y%m%d")
    try:
        df = pro.monthly(
            ts_code=ts_code, start_date=start, end_date=end,
            fields="ts_code,trade_date,open,high,low,close,vol",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[derive] monthly history %s failed: %s", ts_code, e)
        return []
    if df is None or len(df) == 0:
        return []
    df_asc = df.sort_values("trade_date", ascending=True)
    bars: list[dict] = []
    for _, row in df_asc.iterrows():
        try:
            bars.append({
                "date": str(row.get("trade_date") or ""),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "vol": float(row["vol"]) if row.get("vol") is not None else 0.0,
            })
        except (TypeError, ValueError, KeyError):
            continue
    return bars


def _derive_technicals_for_period(
    bars: list[dict],
    period_suffix: str,
    conf_factor: float = 1.0,
) -> list[tuple[str, dict, str]]:
    """Compute the 5 weekly/monthly tech sub-dicts on ``bars`` and return
    emit specs ready to UPSERT.

    ``period_suffix`` ∈ ``("_weekly", "_monthly")``. Produces ``L11.tech.{name}{suffix}``
    dp_ids for the indicators that carry useful information at lower
    frequency — **MA / MACD / RSI / KDJ / BOLL**. ATR / OBV / VOL_MA are
    intentionally skipped because their interpretation depends on the
    daily-trading frequency they were calibrated for (周线 ATR ≈ daily
    ATR×√5, but the absolute scalar loses meaning to consumers wired up
    against the daily product).

    ``conf_factor`` lets callers gently down-weight (e.g. ~0.93 for weekly
    → ~0.88 effective vs 0.95 daily) to reflect data-update latency at
    week / month closes.

    Returns a list of ``(dp_id, payload, source)``. Sub-payloads that are
    wholly-None (e.g. MACD on <35 weekly bars) are skipped. The source
    string is ``derived:technical_indicators_weekly`` or
    ``..._monthly`` depending on ``period_suffix``.
    """

    from mvp20 import technicals

    if not bars:
        return []
    tech = technicals.compute_all(bars)
    source = (
        "derived:technical_indicators_weekly"
        if period_suffix == "_weekly"
        else "derived:technical_indicators_monthly"
    )

    # Same base confidences as daily (see ``derive_all`` daily emit
    # specs), multiplied by ``conf_factor`` — weekly ≈ 0.93, monthly ≈
    # 0.84, giving roughly 0.88 / 0.80 effective on the MA/MACD tier.
    emit_specs = (
        ("ma",   0.95),
        ("macd", 0.90),
        ("rsi",  0.90),
        ("kdj",  0.85),
        ("boll", 0.90),
    )

    out: list[tuple[str, dict, str]] = []
    for key, base_conf in emit_specs:
        sub = tech.get(key) if isinstance(tech, dict) else None
        if sub is None:
            continue
        if isinstance(sub, dict) and all(v is None for v in sub.values()):
            continue
        wrapped = dict(sub) if isinstance(sub, dict) else {"scalar": sub}
        wrapped["as_of"] = tech.get("as_of") if isinstance(tech, dict) else None
        wrapped["n_bars"] = tech.get("n_bars") if isinstance(tech, dict) else None
        wrapped["confidence"] = max(0.0, min(1.0, base_conf * conf_factor))
        dp_id = f"L11.tech.{key}{period_suffix}"
        out.append((dp_id, wrapped, source))
    return out


def _fmp_rows_to_bars(rows: list[dict]) -> list[dict]:
    """Convert FMP /historical-price-eod/light rows (desc by date) into
    ascending OHLCV bars compatible with ``technicals.compute_all``.

    The light endpoint returns ``{symbol, date, price, volume}`` — no real
    OHLC. For technicals that consume only close (MA / EMA / MACD / RSI /
    OBV) this is fine; for KDJ / BOLL / ATR which read high/low we fall
    back to ``open=high=low=close=price`` so those still produce values
    (slightly degraded but non-crashing). When FMP ships full OHLC fields
    (``open`` / ``high`` / ``low`` / ``close``) we honour them.
    """

    asc = sorted(rows, key=lambda r: r.get("date") or "")
    bars: list[dict] = []
    for r in asc:
        close_v = r.get("close")
        if close_v is None:
            close_v = r.get("price")
        try:
            c = float(close_v)
        except (TypeError, ValueError):
            continue
        try:
            o = float(r["open"]) if r.get("open") is not None else c
            h = float(r["high"]) if r.get("high") is not None else c
            lo = float(r["low"]) if r.get("low") is not None else c
            v = float(r["volume"]) if r.get("volume") is not None else 0.0
        except (TypeError, ValueError):
            o = h = lo = c
            v = 0.0
        bars.append({
            "date": str(r.get("date") or ""),
            "open": o, "high": h, "low": lo, "close": c, "vol": v,
        })
    return bars


def _fetch_us_share_history(ts_code: str, days: int = 90) -> dict:
    """Pull last N days of OHLCV for a US stock via FMP's price-history
    light endpoint. ``ts_code`` is the canonical ``NVDA.US`` form; we
    strip the ``.US`` suffix before calling FMP. Returns the same shape
    as ``_fetch_a_share_history``; PE / PB / turnover_rate stay empty
    here (FMP source already emits its own snapshot derives for those).
    """

    out: dict[str, list] = {
        "close": [], "turnover_rate": [], "pe_ttm": [], "pb": [],
        "bars": [],
    }
    if not ts_code.endswith(".US"):
        return out
    symbol = ts_code[:-3]
    try:
        from mvp20.sources.fmp_source import _fetch_price_history_cached
        rows = _fetch_price_history_cached(symbol, lookback_days=max(days, 80))
    except Exception as e:  # noqa: BLE001
        log.warning("[derive] US history %s failed: %s", ts_code, e)
        return out
    if not rows:
        return out
    bars = _fmp_rows_to_bars(rows)
    out["bars"] = bars
    out["close"] = [b["close"] for b in reversed(bars)]
    return out


def _fetch_hk_share_history(ts_code: str, days: int = 90) -> dict:
    """Pull last N days of OHLCV for a HK stock via FMP. ``ts_code`` is
    the canonical ``00700.HK`` form; FMP expects ``0700.HK`` (leading
    zero stripped to four digits). Futu has no kline helper in this
    codebase, so FMP is the only option — if FMP returns nothing we
    return empty bars and the caller skips technical emits.

    TODO: switch to Futu ``request_history_kline`` once a helper is
    wired into ``mvp20/sources/futu_source.py``.
    """

    out: dict[str, list] = {
        "close": [], "turnover_rate": [], "pe_ttm": [], "pb": [],
        "bars": [],
    }
    if not ts_code.endswith(".HK"):
        return out
    base = ts_code[:-3]
    # HK tickers are stored as 5-digit zero-padded (e.g. ``00700``). FMP
    # uses 4-digit form (``0700.HK``); strip a leading zero when present.
    if base.startswith("0") and len(base) == 5:
        symbol = base[1:] + ".HK"
    else:
        symbol = base + ".HK"
    try:
        from mvp20.sources.fmp_source import _fetch_price_history_cached
        rows = _fetch_price_history_cached(symbol, lookback_days=max(days, 80))
    except Exception as e:  # noqa: BLE001
        log.warning("[derive] HK history %s failed: %s", ts_code, e)
        return out
    if not rows:
        return out
    bars = _fmp_rows_to_bars(rows)
    out["bars"] = bars
    out["close"] = [b["close"] for b in reversed(bars)]
    return out


def is_a_share(ts_code: str) -> bool:
    return ts_code.endswith((".SH", ".SZ", ".BJ"))


def is_us_share(ts_code: str) -> bool:
    return ts_code.endswith(".US")


def is_hk_share(ts_code: str) -> bool:
    return ts_code.endswith(".HK")


# ---------------------------------------------------------------------------
# Tier 0 driver (legacy)
# ---------------------------------------------------------------------------


def derive_all(
    db_path: Path,
    history_days: int = 90,
    limit_companies: int | None = None,
    a_share_only: bool = True,
    ts_codes: list[str] | None = None,
) -> dict[str, int]:
    """Iterate every (ts_code) in realtime_current, compute Tier 0 derived
    dp_ids, UPSERT them back with source ``derived:*``. Returns counters.

    This is the historical Tushare-backed derive. Snapshot-only derives
    (Tier 1-4) are run via ``DeriveRunner.run_all()``.
    """

    from .storage import upsert_realtime

    # Always try Tushare init — returns None if no token. With
    # ``a_share_only=False`` we still need it for any A-share that lives
    # in the universe alongside US / HK.
    pro = _get_pro_api()
    if pro is None and a_share_only:
        log.warning("[derive] no Tushare token — skipping A-share derives")
        return {"companies_processed": 0, "derived_rows": 0}

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        all_ts = [r[0] for r in conn.execute(
            "SELECT DISTINCT ts_code FROM realtime_current ORDER BY ts_code"
        ).fetchall()]
    finally:
        conn.close()

    if a_share_only:
        all_ts = [t for t in all_ts if is_a_share(t)]
    else:
        # Keep only ts_codes we have a fetcher for (A / US / HK). Avoids
        # wasted iterations on sentinel rows (e.g. INDUSTRY:* / MARKET:*).
        all_ts = [
            t for t in all_ts
            if is_a_share(t) or is_us_share(t) or is_hk_share(t)
        ]
    if ts_codes:
        # Single-stock / subset derive (used by onboarding one new stock so the
        # preliminary pass stays fast instead of re-deriving the whole universe).
        want = {t.upper() for t in ts_codes}
        all_ts = [t for t in all_ts if t.upper() in want]
    if limit_companies:
        all_ts = all_ts[:limit_companies]

    derived_rows: list[tuple] = []
    now = int(time.time())

    for idx, ts_code in enumerate(all_ts):
        # Pull current values for this stock
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            # Source-aware reads: a row whose ``source`` is ``mock:*`` carries
            # a fabricated scalar and must NOT flow into quantile/overvalued
            # derives. ``_read_realtime_value_with_source`` returns ``None`` for
            # such rows (defense-in-depth — the DB may still hold legacy mock
            # rows even after the collector stopped emitting them).
            current_pe_payload, _ = _read_realtime_value_with_source(conn, ts_code, "L6.mult.pe")
            current_pb_payload, _ = _read_realtime_value_with_source(conn, ts_code, "L6.mult.pb")
            volume_turnover_payload, _ = _read_realtime_value_with_source(
                conn, ts_code, "L7.trade.volume_turnover"
            )
        finally:
            conn.close()

        current_pe = (current_pe_payload or {}).get("scalar") if isinstance(current_pe_payload, dict) else None
        current_pb = (current_pb_payload or {}).get("scalar") if isinstance(current_pb_payload, dict) else None
        current_turnover_rate = (
            (volume_turnover_payload or {}).get("turnover_rate_pct")
            if isinstance(volume_turnover_payload, dict) else None
        )

        # Pull history — dispatch by market suffix so US/HK use FMP while
        # A-share continues to use Tushare. Each fetcher returns the same
        # shape (``{"bars": [...], "close": [...], ...}``) so the rest of
        # the loop is source-agnostic.
        if is_a_share(ts_code):
            hist = _fetch_a_share_history(pro, ts_code, days=history_days) if pro else {}
        elif is_us_share(ts_code):
            hist = _fetch_us_share_history(ts_code, days=history_days)
        elif is_hk_share(ts_code):
            hist = _fetch_hk_share_history(ts_code, days=history_days)
        else:
            hist = {}

        # Derive Tier 0 only
        run_up = derive_run_up(hist.get("close", []))
        crowd = derive_crowdedness(current_turnover_rate, hist.get("turnover_rate", []))
        quantile = derive_historical_quantile(
            current_pe, hist.get("pe_ttm", []),
            current_pb, hist.get("pb", []),
        )
        overvalued = derive_overvalued(quantile)

        # Technical-indicator pack — MA / EMA / MACD / RSI / KDJ / BOLL /
        # VOL_MA / ATR / OBV. Emits seven independent L11.tech.* dp_ids so
        # downstream callers (BFF / FrontEnd) can subscribe to any subset
        # without pulling the whole pack. Each sub-payload is None when
        # input is too short for that indicator (see ``compute_all``).
        from mvp20 import technicals
        bars = hist.get("bars", [])
        tech = technicals.compute_all(bars) if bars else {}

        tech_emit_specs = (
            # (output_dp_id, payload-key, confidence)
            ("L11.tech.ma",     "ma",     0.95),
            ("L11.tech.macd",   "macd",   0.90),
            ("L11.tech.rsi",    "rsi",    0.90),
            ("L11.tech.kdj",    "kdj",    0.85),
            ("L11.tech.boll",   "boll",   0.90),
            ("L11.tech.vol_ma", "vol_ma", 0.90),
            ("L11.tech.atr",    "atr14",  0.85),
            ("L11.tech.obv",    "obv",    0.80),
        )

        emit: list[tuple[str, Any, str]] = [
            ("L6.priced.run_up", run_up, "derived:price_history"),
            ("L6.priced.crowdedness", crowd, "derived:turnover_history"),
            ("L10.val.historical_quantile", quantile, "derived:pe_pb_history"),
            ("L8.val.overvalued", overvalued, "derived:from_quantile"),
        ]
        # OHLCV bar history — capped to the most recent 90 bars so the
        # ``/api/project-ult/technicals?return_series=N`` endpoint can return
        # K-line + 均线叠加 data without an extra Tushare round-trip.
        if bars:
            emit.append((
                "L11.tech.bars",
                {"bars": bars[-90:], "as_of": tech.get("as_of"), "n_bars": len(bars)},
                "derived:technical_indicators",
            ))
        for dp_id, key, conf in tech_emit_specs:
            sub = tech.get(key) if isinstance(tech, dict) else None
            if sub is None:
                continue
            if isinstance(sub, dict) and all(v is None for v in sub.values()):
                # Whole sub-dict empty (e.g. <35 bars for MACD) — skip emit.
                continue
            wrapped: dict[str, Any]
            if isinstance(sub, dict):
                wrapped = dict(sub)
            else:
                # scalar (atr / obv) → wrap so the value_json is uniform.
                wrapped = {"scalar": sub}
            wrapped["as_of"] = tech.get("as_of") if isinstance(tech, dict) else None
            wrapped["n_bars"] = tech.get("n_bars") if isinstance(tech, dict) else None
            wrapped["confidence"] = conf
            emit.append((dp_id, wrapped, "derived:technical_indicators"))

        # Pattern recognition — translate the raw indicator pack above into
        # named, structured signals (golden/death cross, MACD divergence,
        # double top/bottom, RSI/KDJ zones, BOLL breakout, volume-price).
        # Reuses ``tech`` so MA / EMA / RSI / KDJ are not recomputed. Wrapped
        # in try/except so a defect in pattern detection cannot break the
        # core technical-indicator emit pipeline above.
        try:
            from mvp20 import patterns as _patterns
            patterns_result = _patterns.detect_all(bars, indicators=tech) if bars else None
            if patterns_result and (
                patterns_result.get("patterns") or patterns_result.get("current_signals")
            ):
                patterns_payload = dict(patterns_result)
                patterns_payload.setdefault("confidence", 0.75)
                emit.append((
                    "L11.tech.patterns",
                    patterns_payload,
                    "derived:pattern_detection",
                ))
        except Exception as _pat_err:  # noqa: BLE001
            log.warning("[derive] patterns %s failed: %s", ts_code, _pat_err)

        for dp_id, payload, src in emit:
            if payload is None:
                continue
            derived_rows.append((
                ts_code, dp_id,
                json.dumps(payload, ensure_ascii=False),
                "Known", payload.get("confidence", 0.6) if isinstance(payload, dict) else 0.6,
                src, now,
            ))

        if (idx + 1) % 20 == 0:
            log.info("[derive] %d/%d processed (%d derived rows so far)",
                     idx + 1, len(all_ts), len(derived_rows))

    # Bulk UPSERT
    n = upsert_realtime(db_path, derived_rows)
    return {"companies_processed": len(all_ts), "derived_rows": n}


# ---------------------------------------------------------------------------
# Weekly / monthly periodic technical-indicator drivers
# ---------------------------------------------------------------------------
#
# These are siblings of ``derive_all`` but only compute the
# longer-timeframe ``L11.tech.*_weekly`` / ``L11.tech.*_monthly`` dp_ids.
# They reuse the same ``technicals`` library — the bars are weekly /
# monthly OHLCV rather than daily, but the formulas (MA / MACD / RSI /
# KDJ / BOLL) are identical.
#
# Only A-share is supported today because Tushare ``pro.weekly`` /
# ``pro.monthly`` cover SH / SZ / BJ. HK / US weekly+monthly is a TODO
# pending an FMP / Futu equivalent (FMP has /historical-chart/4hour and
# adjustable timeframes, but no native weekly/monthly aggregate that
# matches Tushare's calendar).


def derive_all_weekly(
    db_path: Path,
    history_weeks: int = 120,
    limit_companies: int | None = None,
    a_share_only: bool = True,
    conf_factor: float = 0.93,
) -> dict[str, int]:
    """Compute ``L11.tech.*_weekly`` for every ts_code in the snapshot.

    Pulls ``history_weeks`` of weekly OHLCV bars (Tushare ``pro.weekly``)
    per stock and writes 5 dp_ids back per stock with
    ``source="derived:technical_indicators_weekly"``.

    The default ``conf_factor=0.93`` decays the daily-equivalent base
    confidences (0.95/0.90/...) to roughly ``0.88`` on MA — a deliberate
    nudge to reflect that weekly bars only fully refresh on Friday close
    and may lag during the week.

    Returns counters identical in shape to ``derive_all``::

        {"companies_processed": N, "derived_rows": M}
    """

    from .storage import upsert_realtime

    pro = _get_pro_api() if a_share_only else None
    if pro is None and a_share_only:
        log.warning("[derive] no Tushare token — skipping A-share weekly derives")
        return {"companies_processed": 0, "derived_rows": 0}

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        all_ts = [r[0] for r in conn.execute(
            "SELECT DISTINCT ts_code FROM realtime_current ORDER BY ts_code"
        ).fetchall()]
    finally:
        conn.close()

    if a_share_only:
        all_ts = [t for t in all_ts if is_a_share(t)]
    if limit_companies:
        all_ts = all_ts[:limit_companies]

    derived_rows: list[tuple] = []
    now = int(time.time())

    for idx, ts_code in enumerate(all_ts):
        bars = _fetch_a_share_weekly_history(pro, ts_code, weeks=history_weeks)
        specs = _derive_technicals_for_period(
            bars, period_suffix="_weekly", conf_factor=conf_factor,
        )
        for dp_id, payload, src in specs:
            derived_rows.append((
                ts_code, dp_id,
                json.dumps(payload, ensure_ascii=False),
                "Known", payload.get("confidence", 0.6),
                src, now,
            ))
        if (idx + 1) % 20 == 0:
            log.info("[derive-weekly] %d/%d processed (%d rows so far)",
                     idx + 1, len(all_ts), len(derived_rows))

    n = upsert_realtime(db_path, derived_rows)
    return {"companies_processed": len(all_ts), "derived_rows": n}


def derive_all_monthly(
    db_path: Path,
    history_months: int = 36,
    limit_companies: int | None = None,
    a_share_only: bool = True,
    conf_factor: float = 0.84,
) -> dict[str, int]:
    """Compute ``L11.tech.*_monthly`` for every ts_code in the snapshot.

    Pulls ``history_months`` of monthly OHLCV bars (Tushare
    ``pro.monthly``) per stock and writes 5 dp_ids back per stock with
    ``source="derived:technical_indicators_monthly"``.

    The default ``conf_factor=0.84`` decays daily-equivalent base
    confidences to roughly ``0.80`` on MA — monthly bars refresh once
    per month and are the most stale of the three timeframes.
    """

    from .storage import upsert_realtime

    pro = _get_pro_api() if a_share_only else None
    if pro is None and a_share_only:
        log.warning("[derive] no Tushare token — skipping A-share monthly derives")
        return {"companies_processed": 0, "derived_rows": 0}

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        all_ts = [r[0] for r in conn.execute(
            "SELECT DISTINCT ts_code FROM realtime_current ORDER BY ts_code"
        ).fetchall()]
    finally:
        conn.close()

    if a_share_only:
        all_ts = [t for t in all_ts if is_a_share(t)]
    if limit_companies:
        all_ts = all_ts[:limit_companies]

    derived_rows: list[tuple] = []
    now = int(time.time())

    for idx, ts_code in enumerate(all_ts):
        bars = _fetch_a_share_monthly_history(pro, ts_code, months=history_months)
        specs = _derive_technicals_for_period(
            bars, period_suffix="_monthly", conf_factor=conf_factor,
        )
        for dp_id, payload, src in specs:
            derived_rows.append((
                ts_code, dp_id,
                json.dumps(payload, ensure_ascii=False),
                "Known", payload.get("confidence", 0.6),
                src, now,
            ))
        if (idx + 1) % 20 == 0:
            log.info("[derive-monthly] %d/%d processed (%d rows so far)",
                     idx + 1, len(all_ts), len(derived_rows))

    n = upsert_realtime(db_path, derived_rows)
    return {"companies_processed": len(all_ts), "derived_rows": n}


# ---------------------------------------------------------------------------
# DeriveRunner — Tier 1-4 snapshot derive orchestrator
# ---------------------------------------------------------------------------


# Formula registry: (output_dp_id, input_dp_ids, fn, governance_key)
#
# ``fn`` accepts the resolved input payloads in the same order as
# ``input_dp_ids``. ``governance_key`` selects the governance entry whose
# ``neutral_value`` is emitted when every input is missing (Inactive case).


_FORMULA_REGISTRY: list[tuple[str, list[str], Callable[..., dict | None]]] = [
    # ---- Tier 4: smallest dep set ----
    ("L7.env.risk_appetite", [
        "L7.env.market_trend", "L7.env.style", "L9.macro.liquidity", "L9.macro.rates",
    ], derive_l7_env_risk_appetite),
    ("L7.mood.fomo", [
        "L7.mood.media_social", "L7.flow.active_inflow", "L7.mood.theme",
    ], derive_l7_mood_fomo),
    ("L10.val.expansion_compression", [
        "L6.state.expansion_compression",
        # US fallback inputs (FMP-side): synthesise regime from PE + quantile
        # when no upstream L6.state.expansion_compression exists.
        "L6.mult.pe", "L10.val.historical_quantile",
        "L6.state.historical_percentile",
    ], derive_l10_val_expansion_compression),

    # ---- Tier 1.5: snapshot fallbacks for Tier 0 dp_ids ----
    # These re-emit `L6.priced.run_up` and `L8.val.overvalued` when the
    # legacy A-share Tier 0 derive (derive_all) didn't run for this ts_code,
    # using FMP-side inputs already in the snapshot. The runner skips emit
    # when the same dp_id is already Known from a non-derive source.
    ("L6.priced.run_up", [
        "L5.surprise.preprice",
    ], derive_l6_priced_run_up_snapshot),
    ("L8.val.overvalued", [
        "L10.val.historical_quantile", "L6.state.historical_percentile",
        "L6.mult.peg", "L6.mult.pe",
    ], derive_l8_val_overvalued_snapshot),

    # ---- Tier 3: L8 risks ----
    ("L8.industry.demand_supply", [
        "L0.demand.terminal", "L0.supply.capacity", "L0.supply.inventory",
        "L0.demand.replacement",
    ], derive_l8_industry_demand_supply),
    ("L8.industry.price_war", [
        "L0.price.discount", "L0.compete.price_war", "L0.price.pricing_power",
    ], derive_l8_industry_price_war),
    ("L8.val.priced_in", [
        "L6.priced.run_up", "L11.short.score", "L8.val.overvalued",
    ], derive_l8_val_priced_in),

    # ---- Tier 2: L6 valuation ----
    ("L6.path.tag", [
        "L6.mult.pe", "L6.state.historical_percentile",
        "L10.val.historical_quantile", "L6.state.expansion_compression",
    ], derive_l6_path_tag),
    ("L6.path.second_derivative", [
        "L6.state.historical_percentile", "L6.priced.run_up",
        # US fallback — FMP surprise.preprice carries 5/10/20d run-up.
        "L5.surprise.preprice",
    ], derive_l6_path_second_derivative),
    ("L6.sens.growth_margin", [
        "L5.fina.gross_margin", "L5.fina.revenue_yoy",
        # US fallback — FMP income-statement + financial-growth fields.
        "L5.is.gross_margin", "L5.is.revenue_growth",
    ], derive_l6_sens_growth_margin),
    ("L6.sens.cashflow", [
        "L5.fina.ocf_quality", "L5.cf.fcf",
    ], derive_l6_sens_cashflow),
    ("L6.sens.rates", [
        "L7.env.rates", "L9.macro.rates",
    ], derive_l6_sens_rates),
    ("L6.sens.risk_narrative", [
        "L9.media.report", "L9.event.intraday_news", "L5.surprise.sell_side",
    ], derive_l6_sens_risk_narrative),

    # ---- Tier 1: L11 composites (depend on Tier 2-4 outputs) ----
    ("L11.short.score", [
        "L11.short.event_impact", "L11.short.flow_boost",
        "L11.short.sentiment_shift", "L11.short.technical",
    ], derive_l11_short_score),
    ("L11.mid.score", [
        "L11.mid.orders_revenue", "L11.mid.margin_guidance",
        "L11.mid.eps_upward",
    ], derive_l11_mid_score),
    ("L11.long.score", [
        "L11.long.industry_space", "L11.long.compete_moat",
        "L11.long.business_model", "L11.long.margin",
    ], derive_l11_long_score),

    # ---- L11 mode + trade signal: depend on Tier 1 outputs ----
    ("L11.mode", [
        "L11.short.score", "L11.mid.score", "L11.long.score",
        "L8.val.overvalued", "L7.flow.active_inflow",
    ], derive_l11_mode),
    ("L11.trade.signal", [
        "L11.short.score", "L11.mid.score", "L11.long.score", "L11.mode",
    ], derive_l11_trade_signal),
]


# Bootstrap proxy inputs for L11 sub-scores (event_impact, flow_boost, etc.).
# These are placeholder "Tier 1.5" derives that feed L11.short/mid/long.score
# from upstream hard data so the composite L11 scores have inputs to work
# with. They're computed before the formula registry runs.


def _bootstrap_l11_subscores(
    inputs: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict]:
    """Build proxy ``L11.short/mid/long.<sub>`` rows from upstream hard data.

    Each returns a small payload with ``score`` in ``[-1, 1]`` so the
    composite L11.*.score derive can sum them.
    """

    out: dict[str, dict] = {}

    # ---- L11.short ----
    # event_impact: presence + sentiment of recent intraday news/announcements
    news = inputs.get("L9.event.intraday_news") or {}
    ann = inputs.get("L9.event.intraday_announcement") or {}
    news_val = news.get("value") if isinstance(news.get("value"), dict) else news
    ann_val = ann.get("value") if isinstance(ann.get("value"), dict) else ann
    news_count = _coerce_float(
        (news_val or {}).get("count_24h"), 0.0,
    ) if isinstance(news_val, Mapping) else 0.0
    ann_count = _coerce_float(
        (ann_val or {}).get("count_recent"), 0.0,
    ) if isinstance(ann_val, Mapping) else 0.0
    event_score = _clip((news_count + ann_count) / 40.0 - 0.25, -0.5, 0.8)
    out["L11.short.event_impact"] = {
        "score": event_score,
        "news_count_24h": news_count,
        "ann_count_recent": ann_count,
    }

    # flow_boost: short-term capital flow + block trade
    flow = inputs.get("L7.flow.active_inflow") or {}
    block = inputs.get("L7.flow.block_trade") or {}
    flow_val = flow.get("value") if isinstance(flow.get("value"), dict) else flow
    block_val = block.get("value") if isinstance(block.get("value"), dict) else block
    main_net = _coerce_float((flow_val or {}).get("main_net")) if isinstance(flow_val, Mapping) else 0.0
    block_amt = _coerce_float((block_val or {}).get("total_amount")) if isinstance(block_val, Mapping) else 0.0
    flow_score = _clip(main_net / 100_000.0 + block_amt / 50_000.0, -1.0, 1.0)
    out["L11.short.flow_boost"] = {
        "score": flow_score,
        "main_net": main_net,
        "block_amount": block_amt,
    }

    # sentiment_shift: media + social buzz
    media = inputs.get("L7.mood.media_social") or {}
    media_val = media.get("value") if isinstance(media.get("value"), dict) else media
    buzz = inputs.get("L9.media.social_buzz") or {}
    buzz_val = buzz.get("value") if isinstance(buzz.get("value"), dict) else buzz
    in_top = bool((media_val or {}).get("in_top_100")) if isinstance(media_val, Mapping) else False
    in_buzz = bool((buzz_val or {}).get("in_xq_top_buzz")) if isinstance(buzz_val, Mapping) else False
    sent_score = 0.3 * in_top + 0.2 * in_buzz
    out["L11.short.sentiment_shift"] = {
        "score": sent_score,
        "in_top_100": in_top,
        "in_xq_buzz": in_buzz,
    }

    # technical: run-up + crowdedness
    run_up = inputs.get("L6.priced.run_up") or {}
    run_up_val = run_up.get("value") if isinstance(run_up.get("value"), dict) else run_up
    crowd = inputs.get("L6.priced.crowdedness") or {}
    crowd_val = crowd.get("value") if isinstance(crowd.get("value"), dict) else crowd
    d20 = _coerce_float((run_up_val or {}).get("d20_pct")) if isinstance(run_up_val, Mapping) else 0.0
    pct = _coerce_float((crowd_val or {}).get("percentile")) if isinstance(crowd_val, Mapping) else 0.5
    tech_score = _clip(d20 - (pct - 0.5) * 0.3, -1.0, 1.0)
    out["L11.short.technical"] = {
        "score": tech_score,
        "d20_pct": d20,
        "crowdedness": pct,
    }

    # ---- L11.mid ----
    fina_rev = inputs.get("L5.fina.revenue_yoy") or {}
    fina_rev_val = fina_rev.get("value") if isinstance(fina_rev.get("value"), dict) else fina_rev
    rev_yoy = _coerce_float((fina_rev_val or {}).get("value")) if isinstance(fina_rev_val, Mapping) else 0.0
    out["L11.mid.orders_revenue"] = {
        "score": _clip(rev_yoy / 50.0, -1.0, 1.0),
        "yoy_pct": rev_yoy,
    }

    fina_gm = inputs.get("L5.fina.gross_margin") or {}
    fina_gm_val = fina_gm.get("value") if isinstance(fina_gm.get("value"), dict) else fina_gm
    gm = _coerce_float((fina_gm_val or {}).get("value"), 25.0) if isinstance(fina_gm_val, Mapping) else 25.0
    out["L11.mid.margin_guidance"] = {
        "score": _clip((gm - 25.0) / 25.0, -1.0, 1.0),
        "gross_margin_pct": gm,
    }

    guid = inputs.get("L9.company.earnings_guidance") or {}
    guid_val = guid.get("value") if isinstance(guid.get("value"), dict) else guid
    if isinstance(guid_val, Mapping):
        cp_min = _coerce_float(guid_val.get("change_pct_min"))
        cp_max = _coerce_float(guid_val.get("change_pct_max"))
        eps_score = _clip(((cp_min + cp_max) / 2.0) / 100.0, -1.0, 1.0)
    else:
        eps_score = 0.0
    out["L11.mid.eps_upward"] = {
        "score": eps_score,
        "guidance": guid_val if isinstance(guid_val, Mapping) else None,
    }

    # ---- L11.long ----
    # industry_space — proxy from PMI + L10.industry.fund_flow direction
    pmi = inputs.get("L10.industry.pmi") or {}
    pmi_val = pmi.get("value") if isinstance(pmi.get("value"), dict) else pmi
    mpmi = _coerce_float((pmi_val or {}).get("manufacturing_pmi"), 50.0) if isinstance(pmi_val, Mapping) else 50.0
    out["L11.long.industry_space"] = {
        "score": _clip((mpmi - 50.0) / 5.0, -1.0, 1.0),
        "pmi": mpmi,
    }

    # compete_moat — from gross margin (higher = stronger moat) + ROE
    fina_roe = inputs.get("L5.fina.roe") or {}
    fina_roe_val = fina_roe.get("value") if isinstance(fina_roe.get("value"), dict) else fina_roe
    roe = _coerce_float((fina_roe_val or {}).get("value")) if isinstance(fina_roe_val, Mapping) else 0.0
    out["L11.long.compete_moat"] = {
        "score": _clip((gm - 30.0) / 30.0 + (roe - 10.0) / 20.0, -1.0, 1.0) / 2.0,
        "gross_margin": gm, "roe": roe,
    }

    # business_model — operating CF quality
    ocf_q = inputs.get("L5.fina.ocf_quality") or {}
    ocf_q_val = ocf_q.get("value") if isinstance(ocf_q.get("value"), dict) else ocf_q
    ocfq = _coerce_float((ocf_q_val or {}).get("value")) if isinstance(ocf_q_val, Mapping) else 0.0
    out["L11.long.business_model"] = {
        "score": _clip((ocfq - 50.0) / 100.0, -1.0, 1.0),
        "ocf_quality_pct": ocfq,
    }

    # margin — net margin trajectory
    fina_nm = inputs.get("L5.fina.net_margin") or {}
    fina_nm_val = fina_nm.get("value") if isinstance(fina_nm.get("value"), dict) else fina_nm
    nm = _coerce_float((fina_nm_val or {}).get("value")) if isinstance(fina_nm_val, Mapping) else 0.0
    out["L11.long.margin"] = {
        "score": _clip((nm - 10.0) / 20.0, -1.0, 1.0),
        "net_margin_pct": nm,
    }

    return out


class DeriveRunner:
    """Snapshot-only derive driver.

    Wires:
      1. ``read_hot_snapshot(ts_code)`` -> per-stock + sentinel-merged inputs
      2. Bootstrap L11.* sub-scores from hard data
      3. Run ``_FORMULA_REGISTRY`` in registration order so dependencies
         resolve (Tier 4 -> Tier 3 -> Tier 2 -> Tier 1 -> mode/signal)
      4. ``upsert_realtime(rows)`` writes everything back with
         ``source="derive:<formula_id>"``
    """

    def __init__(
        self,
        hot_db_path: Path,
        governance_yaml_path: Path | None = None,
    ) -> None:
        self.db = Path(hot_db_path)
        self.governance_path = (
            Path(governance_yaml_path) if governance_yaml_path
            else Path("config/data_point_roles.yaml")
        )
        self._governance: Any = None  # lazy

    @property
    def governance(self):
        if self._governance is None:
            try:
                from .field_governance import load_default_governance
                self._governance = load_default_governance(strict=False)
            except Exception as exc:  # noqa: BLE001
                log.warning("[derive] governance load failed: %s", exc)
                self._governance = None
        return self._governance

    # -- helpers -----------------------------------------------------------

    def _list_ts_codes(self, ts_codes: list[str] | None) -> list[str]:
        if ts_codes:
            return [c.strip() for c in ts_codes if c and c.strip()]
        with sqlite3.connect(f"file:{self.db}?mode=ro", uri=True) as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT DISTINCT ts_code FROM overlay_manifest
                    UNION
                    SELECT DISTINCT ts_code FROM realtime_current
                     WHERE ts_code NOT LIKE 'MARKET:%' AND ts_code NOT LIKE 'INDUSTRY:%'
                    ORDER BY 1
                    """
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        return [r[0] for r in rows]

    def _load_snapshot(self, ts_code: str) -> dict[str, dict]:
        from .storage import read_hot_snapshot
        return read_hot_snapshot(self.db, ts_code)

    def _neutral_for(self, dp_id: str) -> tuple[float, str]:
        """Return ``(neutral_value, label)`` for the ``Inactive`` emit path."""

        if self.governance is None:
            return 0.0, "Inactive"
        rule = self.governance.get(dp_id)
        if rule is None:
            return 0.0, "Inactive"
        return rule.neutral_value, "Inactive"

    # -- core --------------------------------------------------------------

    def _run_one(self, ts_code: str, now: int) -> tuple[list[tuple], dict[str, str]]:
        """Run all formulas for one ts_code. Return (rows, status_per_dp)."""

        snapshot = self._load_snapshot(ts_code)
        # Filter snapshot to only Known-ish statuses for input purposes
        usable: dict[str, dict] = {}
        for dp_id, row in snapshot.items():
            status = (row.get("data_status") or "").lower()
            if status in ("unknown", "unavailable", "inactive"):
                continue
            usable[dp_id] = row

        # Bootstrap L11 sub-scores from hard data and inject as inputs
        sub_rows = _bootstrap_l11_subscores(usable)
        bootstrap_emit: dict[str, dict] = {}
        for dp_id, payload in sub_rows.items():
            usable[dp_id] = {"value": payload, "confidence": 0.5}
            bootstrap_emit[dp_id] = payload

        # Now run each formula
        emitted: dict[str, dict] = {}
        # Track dp_ids that came from a real non-derive upstream source so we
        # don't clobber them with a snapshot fallback. Mock rows are excluded:
        # they should seed downstream calculations when useful, but a concrete
        # derive formula must be allowed to replace them.
        upstream_known: dict[str, dict] = {}
        for dp_id, row in usable.items():
            src = (row.get("source") or "")
            if src and not src.startswith("derive:") and not src.startswith("mock:"):
                upstream_known[dp_id] = row

        for output_dp, input_dp_ids, fn in _FORMULA_REGISTRY:
            # If a real upstream source already wrote this dp_id (Known,
            # non-derive), preserve it rather than re-emit. This protects
            # Tier 0 A-share derives (source: derived:price_history) and
            # any future direct FMP emit for L6.priced.run_up /
            # L8.val.overvalued from being clobbered by our snapshot
            # fallback. Note: derived:* (Tier 0) is also preserved here.
            existing = upstream_known.get(output_dp)
            if existing is not None and (existing.get("data_status") or "").lower() == "known":
                # Pass the upstream value through `emitted` so downstream
                # formulas that depend on `output_dp` still see it.
                upstream_val = existing.get("value")
                if isinstance(upstream_val, Mapping):
                    emitted[output_dp] = dict(upstream_val)
                else:
                    emitted[output_dp] = {"scalar": upstream_val}
                emitted[output_dp]["_input_conf"] = float(existing.get("confidence") or 0.5)
                emitted[output_dp]["_preserved_upstream"] = True
                continue

            payloads = []
            input_confs = []
            for inp_dp in input_dp_ids:
                if inp_dp in emitted:
                    # Use freshly-derived value
                    payloads.append(emitted[inp_dp])
                    input_confs.append(emitted[inp_dp].get("_input_conf", 0.5))
                else:
                    row = usable.get(inp_dp)
                    if row is None:
                        payloads.append(None)
                    else:
                        v = row.get("value")
                        # If "value" is a dict, pass it; else wrap as scalar
                        if isinstance(v, Mapping):
                            payloads.append(v)
                        else:
                            payloads.append({"scalar": v})
                        if row.get("confidence") is not None:
                            try:
                                input_confs.append(float(row["confidence"]))
                            except (TypeError, ValueError):
                                pass

            try:
                result = fn(*payloads)
            except Exception as exc:  # noqa: BLE001
                log.warning("[derive] %s for %s failed: %s", output_dp, ts_code, exc)
                result = None

            if result is None:
                # Inactive emit
                neutral, status = self._neutral_for(output_dp)
                payload = {"value": neutral, "_inactive": True, "missing_inputs": input_dp_ids}
                confidence = 0.3
                data_status = status
            else:
                payload = dict(result)
                base_conf = min(input_confs) if input_confs else 0.5
                confidence = _decay(base_conf, 0.9)
                payload["_input_conf"] = base_conf
                if "confidence" not in payload:
                    payload["confidence"] = confidence
                data_status = "Known"

            emitted[output_dp] = payload

        # Also emit bootstrap rows (for transparency)
        rows: list[tuple] = []
        for dp_id, payload in bootstrap_emit.items():
            rows.append((
                ts_code, dp_id,
                json.dumps(payload, ensure_ascii=False),
                "Known", 0.5, f"derive:bootstrap_l11_subscore", now,
            ))
        # Strip _input_conf before persistence to keep payloads clean.
        # Skip preserved-upstream rows so we don't overwrite the original
        # row's source attribution (Tier 0 derived:* or upstream fmp:*).
        for dp_id, payload in emitted.items():
            if payload.get("_preserved_upstream"):
                continue
            persist = {k: v for k, v in payload.items()
                       if k not in ("_input_conf", "_preserved_upstream")}
            data_status = "Inactive" if payload.get("_inactive") else "Known"
            confidence = float(payload.get("confidence", 0.5))
            formula_id = dp_id.replace(".", "_").lower()
            rows.append((
                ts_code, dp_id,
                json.dumps(persist, ensure_ascii=False),
                data_status, confidence,
                f"derive:{formula_id}", now,
            ))

        status_map = {}
        for dp, payload in emitted.items():
            if payload.get("_preserved_upstream"):
                status_map[dp] = "Known"
            elif payload.get("_inactive"):
                status_map[dp] = "Inactive"
            else:
                status_map[dp] = "Known"
        return rows, status_map

    def run_all(
        self,
        ts_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run snapshot-derive for every ts_code (or a subset).

        Returns stats: ``{companies_processed, rows_emitted, dp_status_counts}``.
        """

        from .storage import upsert_realtime

        codes = self._list_ts_codes(ts_codes)
        all_rows: list[tuple] = []
        status_counts: dict[str, dict[str, int]] = {}
        now = int(time.time())

        for ts_code in codes:
            rows, status_map = self._run_one(ts_code, now)
            all_rows.extend(rows)
            for dp_id, status in status_map.items():
                status_counts.setdefault(dp_id, {"Known": 0, "Inactive": 0})
                status_counts[dp_id][status] = status_counts[dp_id].get(status, 0) + 1

        n = upsert_realtime(self.db, all_rows) if all_rows else 0
        return {
            "companies_processed": len(codes),
            "rows_emitted": n,
            "dp_status_counts": status_counts,
        }
