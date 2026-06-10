"""Top-level scoring module for MVP20 graph engine.

This module implements **path / company / final score** computations
plus the **7-mode classifier** described in ``图谱设计.md`` §27 and §30.

The module is intentionally side-effect free: each scoring function
accepts plain dicts / scalars and returns a dict, so callers in
``cli.py`` / ``server.py`` can wire it on top of:

  * ``mvp20.aggregator`` — aggregates the company graph (A1)
  * ``mvp20.coverage``   — computes data-coverage / confidence (A2)
  * ``mvp20.storage.read_hot_snapshot`` — current realtime values

…without scoring needing to know how those upstreams compute things.

Spec references (file: ``图谱设计.md``):

  §27.1 ``路径分``   ─ ``compute_path_score``
  §27.3 ``公司分``   ─ ``compute_company_score``
  §27.4 ``股价结果分`` ─ ``compute_final_score``
  §28   ``时间周期`` ─ ``HORIZON_DEFAULT_WEIGHTS``
  §30   ``当前模式`` ─ ``classify_mode``

The orchestrator function ``score_company()`` ties everything together
into the contract documented in the task brief.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from mvp20.field_governance import NON_SCORING_ROLES
from mvp20.market_adapter import apply_market_adapter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Spec §30 mode identifiers (English keys, Chinese display names).
MODE_STRONG_BULL = "strong_bull"
MODE_MODERATE_BULL = "moderate_bull"
MODE_DIGESTION = "digestion"
MODE_STRUCTURAL_DIVERGENCE = "structural_divergence"
MODE_DE_RATING = "de_rating"
MODE_TREND_REVERSAL = "trend_reversal"
MODE_WAIT_FOR_CONFIRMATION = "wait_for_confirmation"

MODE_DISPLAY = {
    MODE_STRONG_BULL: "强多头",
    MODE_MODERATE_BULL: "温和多头",
    MODE_DIGESTION: "震荡消化",
    MODE_STRUCTURAL_DIVERGENCE: "结构分化",
    MODE_DE_RATING: "杀估值",
    MODE_TREND_REVERSAL: "趋势反转",
    MODE_WAIT_FOR_CONFIRMATION: "等待验证",
}

#: Spec §28 default horizon-mix weights — the cross-horizon roll-up used
#: when ``score_company`` produces a single blended number from the three
#: per-horizon totals. Each entry weights the *horizon itself* (short /
#: medium / long); the components inside one horizon are mixed via
#: :data:`SPEC28_DEFAULT_HORIZON_MIX` below.
HORIZON_DEFAULT_WEIGHTS = {
    "short": 0.30,
    "medium": 0.45,
    "long": 0.25,
}


#: Spec §28 per-horizon component mix — feeds ``compute_final_score``'s
#: ``horizons`` parameter. The structure matches the example in
#: :func:`compute_final_score`'s docstring:
#:
#:   * **short** emphasises events + capital flow — ``capital_sentiment``
#:     dominates because intraday-to-week price action is driven by news +
#:     money flow, not fundamentals.
#:   * **medium** rebalances toward fundamentals while keeping expectation-
#:     gap weight high — 1-3 month moves rotate as the market digests
#:     earnings revisions.
#:   * **long** is fundamentals + structural rerating heavy; short-term
#:     event noise basically vanishes.
#:
#: Risk + priced_in are full subtractions at every horizon (the time
#: dimension does not make them more or less relevant). This is wired
#: as the default in :func:`score_company` so the BFF / CLI no longer
#: render 短=中=长 when the caller forgets to pass an explicit mix.
SPEC28_DEFAULT_HORIZON_MIX: dict[str, dict[str, float]] = {
    "short":  {
        "fundamental": 0.20,
        "expectation_gap": 0.30,
        "valuation_rerating": 0.10,
        "capital_sentiment": 0.40,
    },
    "medium": {
        "fundamental": 0.50,
        "expectation_gap": 0.30,
        "valuation_rerating": 0.10,
        "capital_sentiment": 0.10,
    },
    "long":   {
        "fundamental": 0.60,
        "expectation_gap": 0.05,
        "valuation_rerating": 0.30,
        "capital_sentiment": 0.05,
    },
}

#: F7 — saturating scale for the industry-fundamental block in the company
#: score. ``compute_company_score`` sums an *unbounded* product chain over the
#: industry variables (one term per participating node), so the raw
#: ``industry_total`` grows with node count and dominates the other final-score
#: channels (event / capital / risk / valuation_pressure / priced_in), which
#: are damped into roughly ``[-1, 1]``. To put fundamental on the *same* scale
#: — and stop it from inflating merely because an industry overlay has more
#: filled nodes — the value that feeds ``total`` is squashed through
#: ``tanh(industry_total / _INDUSTRY_TOTAL_SCALE)``. The raw sum is still
#: surfaced as ``components["industry_contrib"]`` for transparency.
#:
#: K is the fundamental-vs-valuation DIAL. SMALLER K = less squashing = a strong
#: industry/fundamental keeps more weight (growth-tilt: a great company can stay
#: BUY despite a rich valuation). LARGER K = more squashing = fundamental matters
#: less, so the valuation_rerating / priced-in drag dominates (valuation-aware:
#: expensive run-ups → HOLD even with strong fundamentals).
#:
#: Calibrated on the post-L0-wiring A-share distribution (the filled-L0 AI_COMPUTE
#: cohort is the only one where the bound bites — industry_total p75 ≈ 2.70; every
#: other name sits near 0 where tanh is ~linear regardless of K). At K=2.0 the
#: strongest fundamental names (e.g. 688256: industry_total ≈ 3.48 → bounded 0.79,
#: base_score 0.327) clear the ~31%-BUY cutoff; K=2.70 squashed them to HOLD. The
#: 31%-BUY threshold ≈ 0.30 holds across K≈2.0–2.7.
#:
#: TODO (market-regime adaptive — design pending, see calib discussion): K should
#: NOT stay a fixed constant. It should shift with the broad-market regime —
#: smaller K (growth-tilt) in a risk-on / bull tape, larger K (valuation-prudent)
#: in a risk-off / bear tape — driven by the existing regime signal
#: (L7.env.market_trend / market_regime_multiplier). Until that is wired, 2.0 is
#: the fixed default.
_INDUSTRY_TOTAL_SCALE = 2.0


def _bound_industry_total(industry_total: float) -> float:
    """F7 — squash the raw industry Σ onto ~[-1, 1] via
    ``tanh(industry_total / _INDUSTRY_TOTAL_SCALE)``.

    Single seam for the bound so both ``compute_company_score`` and the
    final-score ``fundamental`` derivation share one definition (and tests /
    calibration can exercise it directly).
    """

    return math.tanh(industry_total / _INDUSTRY_TOTAL_SCALE)

#: Trading signal thresholds applied to the **market-adjusted** ``base_score``
#: (the value ``score_company`` thresholds for ``trading_signal`` — i.e.
#: ``market_adjusted_final_score["base_score"]``).
#:
#: T2 re-calibration (post sentiment de-bias) set 0.20 / −0.10 / −0.45 on a
#: pre-L0-wiring, pre-F7 distribution.
#:
#: T3 re-calibration (post L0-wiring + F7 bound): wiring the industry overlay
#: (Part 1) and bounding the fundamental block via tanh (F7) shifted the
#: ``base_score`` basis. Across the 121-stock A-share universe it now
#: distributes as min −1.10 / p25 −0.25 / median +0.08 / p75 +0.33 /
#: p90 +0.44 / max +1.40. Under the OLD BUY=0.20 this labelled 51/121 (42%)
#: as BUY — too rich. BUY is re-anchored to 0.30 (≈ the cohort's p70), which
#: lands 37/121 (31%) BUY — inside the 25–35% target — while the
#: meaningfully-negative tail (16/121 ≈ 13% AVOID) is preserved. HOLD/WATCH
#: stay at −0.10 / −0.45: −0.10 sits just below the new median so the broad
#: middle reads HOLD, and −0.45 keeps the AVOID tail at the bottom ~13%.
#: Resulting mix: BUY 31% / HOLD 36% / WATCH 20% / AVOID 13%. These remain
#: calibration constants to revisit if the field set / data distribution
#: changes.
#: R-5 (2026-06-05) SUPERSEDES the T2/T3 calibration above. R-2c removed the
#: confidence_multiplier from base (a ~0.65x haircut → field decompressed ~1.54x)
#: and the market adapter is empirically ≈ identity for A-shares (multiplier
#: median 1.007), so base ≈ direct (merit + valuation + flow − risk − priced_in)
#: and base = 0 is a clean ABSOLUTE neutral. Per user policy these thresholds
#: carry ABSOLUTE meaning and are NOT pegged to a target BUY% (a weak tape may
#: legitimately have no BUYs). The participates_in_score governance fix (R-6
#: follow-up: data_point_roles.yaml is authoritative at runtime, so the 55 dead
#: qualitative dp_ids finally EXIT the damped denominators instead of inflating
#: them ~40% with unreadable fake-zeros) un-diluted risk/expectation_gap and
#: dropped base ~0.16 to its honest scale: 116-stock base p10/p25/median/p75/p90
#: = −1.07/−0.73/−0.41/−0.08/+0.13. Anchored absolutely: BUY ≥ +0.20 (positives
#: clearly beat risk — conviction, not merely base>0) / HOLD ≥ −0.15 (roughly
#: balanced middle) / WATCH ≥ −0.50 (net-negative, monitor) / AVOID < −0.50
#: (clearly net-negative). Honest weak-tape mix: BUY 10 (9%) / HOLD 30 / WATCH
#: 28 / AVOID 48 (41%) — few BUYs / many AVOIDs is the TRUTH once risk is counted
#: without dead-node dilution, not a threshold artifact. Dynamic macro-regime amplification (lifting the
#: whole field in a bull regime via the currently-dormant market_regime
#: multiplier, median 1.007) is deferred to R-7 — to be validated by the
#: point-in-time backtest rather than hand-tuned.
SIGNAL_BUY_THRESHOLD = 0.20
SIGNAL_HOLD_THRESHOLD = -0.15
SIGNAL_WATCH_THRESHOLD = -0.50
# anything strictly below WATCH threshold => AVOID


# ── RD-A dual-axis signal (PARALLEL v2 — headline stays v1 until the P&L loop
# promotes it; see docs/audit/rda_dual_axis_design_2026-06-10.md) ────────────
#
# The single-axis base lets timing variance dominate: a high-merit company in
# an expensive/overheated tape gets pushed to AVOID ("好公司但贵" failure mode,
# redesign item RD-A). v2 decomposes the SAME six components into
#   merit  M = fundamental + expectation_gap − risk_discount     (公司质量)
#   timing T = valuation_rerating + capital_sentiment − priced_in (入场时机)
# (so M + T == the core unweighted base, exactly) and reads the signal off a
# 2-D matrix where strong merit with poor timing degrades to HOLD/WATCH — never
# AVOID. Bands are provisional absolute cuts on the core scale; the promotion
# decision (and any re-anchoring) comes from the P&L loop's v1-vs-v2 matured
# comparison, NOT from hand-tuning.
MERIT_BAND = 0.15
TIMING_BAND = 0.15
#: a deeply negative timing axis (crowding + rich valuation together) degrades
#: even a strong-merit name from HOLD to WATCH (still never AVOID).
TIMING_DEEP_NEGATIVE = -0.50


def dual_axis_signal(merit: float, timing: float) -> str:
    """BUY/HOLD/WATCH/AVOID from the (merit, timing) 2-D matrix."""

    if merit > MERIT_BAND:
        if timing > TIMING_BAND:
            return "BUY"
        if timing < TIMING_DEEP_NEGATIVE:
            return "WATCH"
        return "HOLD"          # 好公司但时机差 → 持有/等待, 不是回避
    if merit >= -MERIT_BAND:
        if timing < -TIMING_BAND:
            return "WATCH"
        return "HOLD"
    # weak merit
    if timing < -TIMING_BAND:
        return "AVOID"
    return "WATCH"             # 差公司好时机 → 最多观察, 不追


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clip(value: float, lo: float, hi: float) -> float:
    """Clamp ``value`` into ``[lo, hi]`` (safe for None via caller)."""

    if value is None:
        return lo
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _coerce_float(value: Any, default: float = 0.0) -> float:
    """Best-effort cast to float; falls back to ``default`` for None/garbage."""

    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_direction(value: Any) -> float:
    """Normalize a direction signal to ``-1 / 0 / +1``.

    Accepts numeric (clipped to sign) or the literal strings
    ``positive``/``negative``/``neutral`` used in the overlay YAMLs.
    """

    if isinstance(value, str):
        v = value.strip().lower()
        if v == "positive":
            return 1.0
        if v == "negative":
            return -1.0
        if v in ("neutral", "", "none"):
            return 0.0
        try:
            value = float(v)
        except ValueError:
            return 0.0
    f = _coerce_float(value, 0.0)
    if f > 0:
        return 1.0
    if f < 0:
        return -1.0
    return 0.0


# ---------------------------------------------------------------------------
# Spec §27.1 — Path score
# ---------------------------------------------------------------------------


def compute_path_score(
    direction: float,
    event_strength: float,
    transmission_strength: float,
    company_exposure: float,
    revenue_share: float,
    profit_elasticity: float,
    confidence: float,
    time_factor: float,
    expectation_gap: float,
    capital_amplification: float,
    priced_in_discount: float,
    risk_discount: float,
) -> float:
    """Compute one causal path's contribution to the stock score.

    Implements spec §27.1 verbatim:

    ``Path Score = direction × event_strength × transmission_strength
                 × company_exposure × revenue_share × profit_elasticity
                 × confidence × time_factor × expectation_gap
                 × capital_amplification
                 - priced_in_discount - risk_discount``

    All multiplicative inputs are coerced to floats (None ⇒ 0). The
    direction is normalised to ``-1/0/+1`` so a single negative leg
    flips the whole product, as the spec intends.

    Parameter ranges (per task brief):

      direction              : -1 / 0 / +1
      event_strength         : 0..1
      transmission_strength  : 0..1
      company_exposure       : 0..1
      revenue_share          : 0..1
      profit_elasticity      : 0..2 (1 = neutral)
      confidence             : 0..1
      time_factor            : 0..1 (1 = short-term salient)
      expectation_gap        : -1..+1
      capital_amplification  : 0..2
      priced_in_discount     : 0..1
      risk_discount          : 0..1
    """

    d = _coerce_direction(direction)
    es = _coerce_float(event_strength)
    ts = _coerce_float(transmission_strength)
    ce = _coerce_float(company_exposure)
    rs = _coerce_float(revenue_share)
    pe = _coerce_float(profit_elasticity)
    cf = _coerce_float(confidence)
    tf = _coerce_float(time_factor)
    eg = _coerce_float(expectation_gap)
    ca = _coerce_float(capital_amplification)
    pid = _coerce_float(priced_in_discount)
    rd = _coerce_float(risk_discount)

    multiplicative = d * es * ts * ce * rs * pe * cf * tf * eg * ca
    return multiplicative - pid - rd


# ---------------------------------------------------------------------------
# Spec §27.2 — Node score (helper, used by aggregator + final)
# ---------------------------------------------------------------------------


def compute_node_score(
    direction: float | None = None,
    strength: float | None = None,
    confidence: float | None = None,
    children: Sequence[Mapping[str, Any]] | None = None,
) -> float:
    """Spec §27.2 node score.

    With children:  ``Σ child.score × child.weight × child.confidence``
    Leaf node:      ``direction × strength × confidence``

    Each child mapping should expose ``score``, ``weight``, ``confidence``;
    missing fields fall back to neutral defaults (1.0 for weight/confidence,
    0.0 for score).
    """

    if children:
        total = 0.0
        for c in children:
            s = _coerce_float(c.get("score"))
            w = _coerce_float(c.get("weight"), 1.0)
            cf = _coerce_float(c.get("confidence"), 1.0)
            total += s * w * cf
        return total

    d = _coerce_direction(direction)
    st = _coerce_float(strength)
    cf = _coerce_float(confidence, 1.0)
    return d * st * cf


# ---------------------------------------------------------------------------
# Spec §27.3 — Company score
# ---------------------------------------------------------------------------


def compute_company_score(
    industry_variables: Iterable[Mapping[str, Any]],
    company_event_score: float,
    capital_sentiment_score: float,
    risk_discount: float,
    valuation_pressure: float,
    priced_in_discount: float,
) -> dict[str, Any]:
    """Spec §27.3 company score.

    ``Company Score = Σ [industry_var.score × exposure × revenue_share
                        × profit_elasticity × financial_sensitivity
                        × valuation_sensitivity]
                     + company_event_score + capital_sentiment_score
                     - risk_discount - valuation_pressure
                     - priced_in_discount``

    ``industry_variables`` items expose:

        {
          "score": <industry-variable score, output of node aggregation>,
          "exposure": 0..1,
          "revenue_share": 0..1,
          "profit_elasticity": 0..2,
          "financial_sensitivity": 0..2,
          "valuation_sensitivity": 0..2,
          # optional metadata used downstream by classify_mode / top_paths:
          "name": str, "direction": -1/0/+1, "confidence": 0..1
        }

    Returns:
        {
          "score": float,                       # full company score
          "components": {
              "industry_contrib": float,        # the RAW Σ industry block
              "industry_contrib_bounded": float,# F7: tanh-bounded Σ → into score
              "event": float,
              "capital": float,
              "risk": float,
              "valuation_pressure": float,
              "priced_in": float,
          },
          "industry_contributions": [           # per-variable contribution
              {"name": str, "value": float, "direction": -1/0/+1}
          ],
        }
    """

    # R-2b: coverage-normalized weighted MEAN (was a plain Σ then tanh-bounded).
    # The sum made ``fundamental`` a coverage proxy — |industry_total| correlated
    # ~0.95 with the non-zero node count (more covered nodes → bigger sum → tanh
    # saturated), so it measured "how much data" not "how good". A confidence-
    # weighted MEAN is already in [-1, 1] (mean of [-1, 1] scores), so node count
    # no longer inflates it and the F7 tanh / _INDUSTRY_TOTAL_SCALE bound is moot.
    weighted_sum = 0.0   # Σ(score × weight)
    weight_sum = 0.0     # Σ weight  (the mean denominator)
    contribs: list[dict[str, Any]] = []
    for v in industry_variables or []:
        score = _coerce_float(v.get("score"))
        # R-2b follow-up: skip zero-score nodes (the neutral_value default for
        # unfilled L0/L1 fields = "no signal / abstain"). Averaging them in pulled
        # the real financial signal toward 0 — empirically 60+ zeros took 74-96%
        # of the mean denominator, compressing merit ~22× (fund sd 0.018). Letting
        # only the OPINIONATED signals (financials + non-neutral L0) set the mean
        # restores merit's magnitude without re-introducing the node-count proxy.
        if abs(score) < 1e-9:
            continue
        exposure = _coerce_float(v.get("exposure"), 1.0)
        rev_share = _coerce_float(v.get("revenue_share"), 1.0)
        prof_e = _coerce_float(v.get("profit_elasticity"), 1.0)
        fin_s = _coerce_float(v.get("financial_sensitivity"), 1.0)
        val_s = _coerce_float(v.get("valuation_sensitivity"), 1.0)
        conf = _coerce_float(v.get("confidence"), 1.0)

        contrib = score * exposure * rev_share * prof_e * fin_s * val_s
        weight = exposure * rev_share * prof_e * fin_s * val_s * conf
        weighted_sum += score * weight
        weight_sum += weight

        contribs.append({
            "name": v.get("name") or v.get("node_id") or "",
            "value": contrib,
            "direction": _coerce_direction(v.get("direction") or contrib),
            "confidence": _coerce_float(v.get("confidence"), 1.0),
        })

    event = _coerce_float(company_event_score)
    capital = _coerce_float(capital_sentiment_score)
    risk = _coerce_float(risk_discount)
    val_pressure = _coerce_float(valuation_pressure)
    priced_in = _coerce_float(priced_in_discount)

    # F7 — bound the fundamental block onto the same ~[-1, 1] scale as the
    # other final-score channels before summing. ``industry_total`` is the raw
    # (unbounded) Σ; ``industry_bounded`` is what actually enters ``total`` so
    # fundamental can't dominate / grow merely with node count. The raw sum is
    # still reported in components["industry_contrib"] for transparency.
    # Raw weighted sum kept for transparency; the MEAN is what enters the score.
    industry_total = weighted_sum
    industry_bounded = weighted_sum / weight_sum if weight_sum > 1e-9 else 0.0

    total = industry_bounded + event + capital - risk - val_pressure - priced_in

    return {
        "score": total,
        "components": {
            "industry_contrib": industry_total,
            "industry_contrib_bounded": industry_bounded,
            "event": event,
            "capital": capital,
            "risk": risk,
            "valuation_pressure": val_pressure,
            "priced_in": priced_in,
        },
        "industry_contributions": contribs,
    }


# ---------------------------------------------------------------------------
# Spec §27.4 — Stock final score (with horizon mix)
# ---------------------------------------------------------------------------


def compute_final_score(
    fundamental_score: float,
    expectation_gap_score: float,
    valuation_rerating_score: float,
    capital_sentiment_score: float,
    risk_discount: float,
    priced_in_discount: float,
    horizons: Mapping[str, Mapping[str, float]] | None = None,
    primary_positive_path: Sequence[Mapping[str, Any]] | None = None,
    primary_negative_path: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Spec §27.4 stock final score.

    Base formula:

      ``Stock Final = fundamental + expectation_gap + valuation_rerating
                     + capital_sentiment - risk - priced_in``

    The ``horizons`` argument lets callers re-weight the inputs per
    spec §28. It expects a mapping of horizon → component weights, e.g.::

        {
          "short":  {"fundamental": 0.2, "expectation_gap": 0.3,
                     "valuation_rerating": 0.1, "capital_sentiment": 0.4},
          "medium": {"fundamental": 0.5, "expectation_gap": 0.3,
                     "valuation_rerating": 0.1, "capital_sentiment": 0.1},
          "long":   {"fundamental": 0.6, "expectation_gap": 0.05,
                     "valuation_rerating": 0.30, "capital_sentiment": 0.05},
        }

    When omitted, each horizon evaluates the unweighted base formula
    (i.e. short = medium = long until callers customise the mix).

    Returns:
        {
          "short_total":   float,
          "medium_total":  float,
          "long_total":    float,
          "base_score":    float,                # unweighted sum
          "components":    {...},                # input echo for audit
          "primary_positive_path": [...],
          "primary_negative_path": [...],
          "trading_meaning": str,
        }
    """

    f = _coerce_float(fundamental_score)
    e = _coerce_float(expectation_gap_score)
    vr = _coerce_float(valuation_rerating_score)
    cs = _coerce_float(capital_sentiment_score)
    r = _coerce_float(risk_discount)
    p = _coerce_float(priced_in_discount)

    base = f + e + vr + cs - r - p

    def horizon_total(weights: Mapping[str, float] | None) -> float:
        if not weights:
            return base
        wf = _coerce_float(weights.get("fundamental"), 1.0)
        we = _coerce_float(weights.get("expectation_gap"), 1.0)
        wv = _coerce_float(weights.get("valuation_rerating"), 1.0)
        wc = _coerce_float(weights.get("capital_sentiment"), 1.0)
        # risk + priced_in are full subtractions at every horizon — they
        # do not become more or less relevant with time.
        return f * wf + e * we + vr * wv + cs * wc - r - p

    horizons = horizons or {}
    short_total = horizon_total(horizons.get("short"))
    medium_total = horizon_total(horizons.get("medium"))
    long_total = horizon_total(horizons.get("long"))

    pos = list(primary_positive_path or [])
    neg = list(primary_negative_path or [])

    return {
        "short_total": short_total,
        "medium_total": medium_total,
        "long_total": long_total,
        "base_score": base,
        "components": {
            "fundamental": f,
            "expectation_gap": e,
            "valuation_rerating": vr,
            "capital_sentiment": cs,
            "risk": r,
            "priced_in": p,
        },
        "primary_positive_path": pos,
        "primary_negative_path": neg,
        "trading_meaning": _describe_trading_meaning(
            short_total, medium_total, long_total, base_score=base,
        ),
    }


def _describe_trading_meaning(
    short_t: float,
    medium_t: float,
    long_t: float,
    base_score: float | None = None,
) -> str:
    """One-line trading-narrative string derived from the three horizons.

    Format: ``短:<short>/中:<medium>/长:<long> => <verb>``. The verb is the
    plain-Chinese version of the trading-signal bucket and is intentionally
    kept short — UI may use this directly in a tooltip.

    The verb is keyed off ``base_score`` (the unweighted sum) when supplied
    so it stays aligned with ``_trading_signal_from_mix`` (which also runs
    on the unweighted scale to preserve threshold calibration). When
    ``base_score`` is None we fall back to the average of the three
    horizons — kept for back-compat with callers that pre-date the split.
    """

    pivot = base_score if base_score is not None else (
        (short_t + medium_t + long_t) / 3.0
    )
    if pivot >= SIGNAL_BUY_THRESHOLD:
        verb = "积极介入"
    elif pivot >= SIGNAL_HOLD_THRESHOLD:
        verb = "维持仓位"
    elif pivot >= SIGNAL_WATCH_THRESHOLD:
        verb = "观察等待"
    else:
        verb = "回避"
    return f"短:{short_t:.3f}/中:{medium_t:.3f}/长:{long_t:.3f} => {verb}"


# ---------------------------------------------------------------------------
# Spec §30 — Mode classifier (7 modes)
# ---------------------------------------------------------------------------


def classify_mode(
    final_score: Mapping[str, Any],
    signals: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify the current "mode" of the stock per spec §30.

    Spec §30 ranks **7 modes** by their qualitative cause-pattern. We translate
    the prose pattern table into thresholds that operate on the signal pack:

        signals = {
          "industry_trend":      float in [-1, 1],   # 行业变量增强/恶化
          "exposure":            float in [0,  1],   # 公司暴露度
          "financial_revision":  float in [-1, 1],   # 财务预期上修/下修
          "valuation_pressure":  float in [0,  1],   # 估值过度定价
          "capital_flow":        float in [-1, 1],   # 资金流入/流出
          "expectation_gap":     float in [-1, 1],   # 预期差
          "priced_in":           float in [0,  1],   # 已定价折扣
          "new_catalyst":        float in [0,  1],   # 新催化力度
          "competition":         float in [-1, 1],   # 竞争格局变化 (+ better, - worse)
          "event_present":       float in [0,  1],   # 事件出现 0=无, 1=有
          "operating_confirmed": float in [0,  1],   # 经营数据已确认
        }

    Threshold derivation (cross-reference spec §30):

      * 强多头   (strong_bull):
            industry_trend >= 0.4  AND exposure >= 0.5
            AND financial_revision >= 0.2 AND valuation_pressure < 0.6
            AND capital_flow >= 0.2
            Reason: "行业↑ + 暴露度高 + 财务预期↑ + 估值未过度 + 资金↑"
      * 温和多头 (moderate_bull):
            industry_trend >= 0.2 AND financial_revision >= 0.0
            AND valuation_pressure < 0.8 AND capital_flow >= 0.0
            AND expectation_gap < 0.4   # gap has narrowed
            Reason: "基本面强 但预期差缩 估值合理 资金稳"
      * 震荡消化 (digestion):
            priced_in >= 0.5 AND new_catalyst < 0.3
            AND abs(financial_revision) < 0.2   # earnings stable
            AND abs(capital_flow) < 0.3         # rotational, not directional
            Reason: "利好部分定价 新催化不足 财务稳 资金轮动"
      * 结构分化 (structural_divergence):
            industry_trend >= 0.2 AND exposure < 0.5
            Reason: "行业利好 但暴露不同 龙头强"
      * 杀估值   (de_rating):
            valuation_pressure >= 0.6 AND capital_flow < -0.2
            AND financial_revision < 0.2  # but slowing growth, not crashing
            Reason: "业绩稳但增速降 估值高 资金撤"
      * 趋势反转 (trend_reversal):
            industry_trend <= -0.3 AND financial_revision <= -0.2
            AND capital_flow <= -0.2
            (competition is allowed to amplify but isn't gating)
            Reason: "行业↓ 财务↓ 竞争↓ 资金↓"
      * 等待验证 (wait_for_confirmation):
            event_present >= 0.5 AND operating_confirmed < 0.4
            AND abs(expectation_gap) < 0.4
            Reason: "事件出现 但经营未确认"

    Evaluation order: most-specific / most-negative first. A net-negative
    `final_score` short-circuits to trend_reversal if no other negative
    rule fires — this protects the API consumer from "mode says
    strong_bull but score is -0.5".
    """

    s = dict(signals or {})
    industry_trend = _coerce_float(s.get("industry_trend"))
    exposure = _coerce_float(s.get("exposure"))
    financial_revision = _coerce_float(s.get("financial_revision"))
    valuation_pressure = _coerce_float(s.get("valuation_pressure"))
    capital_flow = _coerce_float(s.get("capital_flow"))
    expectation_gap = _coerce_float(s.get("expectation_gap"))
    priced_in = _coerce_float(s.get("priced_in"))
    new_catalyst = _coerce_float(s.get("new_catalyst"))
    event_present = _coerce_float(s.get("event_present"))
    operating_confirmed = _coerce_float(s.get("operating_confirmed"))

    # Use the medium horizon as the "central" score for confidence weighting.
    medium = _coerce_float(final_score.get("medium_total") if final_score else None)
    short = _coerce_float(final_score.get("short_total") if final_score else None)
    long_ = _coerce_float(final_score.get("long_total") if final_score else None)
    central = (short + medium + long_) / 3.0

    # ---- evaluate negative-leaning modes first (safety) -------------------
    if (
        industry_trend <= -0.3
        and financial_revision <= -0.2
        and capital_flow <= -0.2
    ):
        return _mode_result(
            MODE_TREND_REVERSAL,
            confidence=_mode_confidence([
                -industry_trend, -financial_revision, -capital_flow,
            ], magnitude=central),
            drivers=["industry_trend↓", "financial_revision↓", "capital_flow↓"],
            rationale="行业变量恶化、财务预期下修、资金持续流出 (spec §30 趋势反转)",
        )

    if (
        valuation_pressure >= 0.6
        and capital_flow <= -0.2
        and financial_revision < 0.2
    ):
        return _mode_result(
            MODE_DE_RATING,
            confidence=_mode_confidence([
                valuation_pressure, -capital_flow,
            ], magnitude=abs(central)),
            drivers=["valuation_pressure↑", "capital_flow↓"],
            rationale="估值偏高 + 资金撤出 + 增速放缓 (spec §30 杀估值)",
        )

    if (
        event_present >= 0.5
        and operating_confirmed < 0.4
        and abs(expectation_gap) < 0.4
    ):
        # Wait-for-confirmation: event signal present but operating data not
        # yet confirmed. Catch this before bull modes so an unverified rumour
        # doesn't masquerade as strong_bull.
        return _mode_result(
            MODE_WAIT_FOR_CONFIRMATION,
            confidence=_mode_confidence([
                event_present, 1.0 - operating_confirmed,
            ], magnitude=abs(central)),
            drivers=["event_present", "operating_data_pending"],
            rationale="事件出现但经营数据未确认 (spec §30 等待验证)",
        )

    # ---- bull / divergent modes ------------------------------------------
    if (
        industry_trend >= 0.4
        and exposure >= 0.5
        and financial_revision >= 0.2
        and valuation_pressure < 0.6
        and capital_flow >= 0.2
    ):
        return _mode_result(
            MODE_STRONG_BULL,
            confidence=_mode_confidence([
                industry_trend, exposure, financial_revision, capital_flow,
                1.0 - valuation_pressure,
            ], magnitude=central),
            drivers=[
                "industry_trend↑", "exposure↑", "financial_revision↑",
                "capital_flow↑",
            ],
            rationale="行业↑ 暴露↑ 财务↑ 估值未过度 资金↑ (spec §30 强多头)",
        )

    if (
        industry_trend >= 0.2
        and exposure < 0.5
    ):
        # Industry-wide tailwind but this name has limited exposure → the
        # spec calls this "structural_divergence" (龙头 vs 二线 dispersion).
        return _mode_result(
            MODE_STRUCTURAL_DIVERGENCE,
            confidence=_mode_confidence([
                industry_trend, 1.0 - exposure,
            ], magnitude=abs(central)),
            drivers=["industry_trend↑", "exposure_low"],
            rationale="行业利好但公司暴露度不足，龙头>二线 (spec §30 结构分化)",
        )

    if (
        priced_in >= 0.5
        and new_catalyst < 0.3
        and abs(financial_revision) < 0.2
        and abs(capital_flow) < 0.3
    ):
        return _mode_result(
            MODE_DIGESTION,
            confidence=_mode_confidence([
                priced_in, 1.0 - new_catalyst,
            ], magnitude=abs(central)),
            drivers=["priced_in↑", "new_catalyst_low"],
            rationale="利好部分定价 + 新催化不足 + 财务稳 + 资金轮动 (spec §30 震荡消化)",
        )

    if (
        industry_trend >= 0.2
        and financial_revision >= 0.0
        and valuation_pressure < 0.8
        and capital_flow >= 0.0
        and expectation_gap < 0.4
    ):
        return _mode_result(
            MODE_MODERATE_BULL,
            confidence=_mode_confidence([
                industry_trend, max(0.0, financial_revision),
                max(0.0, capital_flow), 1.0 - valuation_pressure,
            ], magnitude=central),
            drivers=["industry_trend↑", "valuation_acceptable"],
            rationale="基本面强 但预期差缩 估值合理 资金稳 (spec §30 温和多头)",
        )

    # ---- catch-all: fall back to wait_for_confirmation, but if the central
    # score is meaningfully negative, default to trend_reversal so the
    # caller never sees a contradictory (strong_bull, score=-0.5) result.
    if central <= -0.20:
        return _mode_result(
            MODE_TREND_REVERSAL,
            confidence=min(1.0, abs(central)),
            drivers=["score_net_negative"],
            rationale="多个负向因素叠加 (fallback, score<-0.2)",
        )

    return _mode_result(
        MODE_WAIT_FOR_CONFIRMATION,
        confidence=0.3,
        drivers=["signals_insufficient"],
        rationale="信号不足以触发任何 spec §30 明确模式，等待数据补充",
    )


def _mode_confidence(positives: Iterable[float], magnitude: float = 0.0) -> float:
    """Combine the rule's gating signals into a confidence in ``[0, 1]``.

    The average of the positive gating signals is multiplied by a mild
    magnitude factor so a barely-passing rule on a near-zero score
    doesn't claim 1.0 confidence.
    """

    vals = [_clip(_coerce_float(v), 0.0, 1.5) for v in positives]
    if not vals:
        return 0.5
    base = sum(vals) / len(vals)
    base = _clip(base, 0.0, 1.0)
    # Magnitude penalty: if |central| < 0.05, scale the confidence by 0.5.
    if abs(magnitude) < 0.05:
        base *= 0.5
    return _clip(base, 0.0, 1.0)


def _mode_result(
    mode: str,
    *,
    confidence: float,
    drivers: list[str],
    rationale: str,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "mode_display": MODE_DISPLAY.get(mode, mode),
        "confidence": _clip(confidence, 0.0, 1.0),
        "primary_drivers": list(drivers),
        "rationale": rationale,
    }


# ---------------------------------------------------------------------------
# Trading signal
# ---------------------------------------------------------------------------


def _trading_signal_from_mix(short_t: float, medium_t: float, long_t: float,
                             horizon_weights: Mapping[str, float] | None = None) -> str:
    """Translate the weighted final-score mix into a BUY/HOLD/WATCH/AVOID label.

    Default horizon weighting is per ``HORIZON_DEFAULT_WEIGHTS``. The
    thresholds are spec-derived (§27.4 maps the final score to the
    trading-meaning column): a clean bull (multi-driver positive) crosses
    BUY at ~0.5; a flat picture sits in HOLD/WATCH; net-negative goes
    to AVOID.
    """

    w = horizon_weights or HORIZON_DEFAULT_WEIGHTS
    ws = _coerce_float(w.get("short"), 0.0)
    wm = _coerce_float(w.get("medium"), 0.0)
    wl = _coerce_float(w.get("long"), 0.0)
    if ws + wm + wl <= 0:
        ws, wm, wl = 1.0, 1.0, 1.0
    total = ws + wm + wl
    mix = (short_t * ws + medium_t * wm + long_t * wl) / total

    if mix >= SIGNAL_BUY_THRESHOLD:
        return "BUY"
    if mix >= SIGNAL_HOLD_THRESHOLD:
        return "HOLD"
    if mix >= SIGNAL_WATCH_THRESHOLD:
        return "WATCH"
    return "AVOID"


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


#: ``score_target`` values whose magnitude is SUBTRACTED from the final
#: score (see :func:`_role_components_from_flat`, where every one of these is
#: rolled up with ``absolute=True`` and then fed to ``compute_*_score`` as a
#: ``- risk_discount`` / ``- valuation_pressure`` / ``- priced_in_discount``
#: term). A node tagged with one of these stores a POSITIVE magnitude but is
#: an *effective negative* contributor, so ``_top_paths`` must never surface it
#: as a "top positive" driver. Kept in sync with the target sets above.
_SUBTRACTIVE_SCORE_TARGETS: frozenset[str] = frozenset({
    # risk_discount group
    "risk_discount", "uncertainty_discount", "volatility_risk", "overheat_risk",
    # valuation_pressure
    "valuation_pressure",
    # priced_in_discount group
    "priced_in_discount", "option_priced_in", "time_decay",
})


@dataclass(frozen=True)
class _PathInfo:
    """Lightweight handle to a path's score + metadata, for ranking."""

    node_id: str
    score: float
    direction: float
    rationale: str
    score_target: str | None = None

    @property
    def effective_score(self) -> float:
        """Signed contribution to the FINAL score.

        Most nodes contribute their raw ``score``. Nodes whose
        ``score_target`` is a discount/risk target (see
        :data:`_SUBTRACTIVE_SCORE_TARGETS`) store a positive magnitude that the
        scorer SUBTRACTS, so their effective contribution is ``-abs(score)``.
        Ranking on this value keeps penalties out of the "top positive" list
        and lets them rank in the "top negative" list — without touching the
        numeric final score (which is computed separately upstream)."""

        if self.score_target in _SUBTRACTIVE_SCORE_TARGETS:
            return -abs(self.score)
        return self.score


def _is_flat_aggregator_output(payload: Mapping[str, Any]) -> bool:
    """Heuristic: A1's ``aggregate_company_graph`` returns a flat
    ``{node_id: {score, short_score, medium_score, long_score, ...}}``
    dict. Detect that shape so we can read both the flat form and the
    "envelope" form ``{"nodes": {...}, "industry_variables": [...], ...}``
    that callers can use to inject signals directly."""

    if not isinstance(payload, Mapping) or not payload:
        return False
    for k, v in payload.items():
        if not isinstance(v, Mapping):
            continue
        if {"score", "short_score", "medium_score", "long_score"} <= set(v.keys()) or "score" in v:
            # Avoid mis-classifying an envelope where one key happens to be
            # called e.g. "nodes" → its value is dict-of-list not dict-of-dict.
            if isinstance(k, str) and k not in {"nodes", "industry_variables"}:
                return True
    return False


def _collect_path_infos(
    aggregated_nodes: Mapping[str, Any],
) -> list[_PathInfo]:
    """Pull per-node path scores out of the aggregator output.

    Supports two shapes:

      * **Envelope form** (used by ``score_company`` mock tests and by
        callers that want to pre-compute paths): the aggregator output is
        ``{"nodes": {node_id: {path_score, direction, name}}, ...}``.

      * **Flat form** (the real ``aggregate_company_graph`` output):
        ``{node_id: {score, short_score, ..., confidence}}``. We treat
        ``score`` as the path score, ``direction`` derived from sign.

    We tolerate missing fields by skipping them so a partially-populated
    aggregator output never crashes scoring.
    """

    paths: list[_PathInfo] = []
    flat = _is_flat_aggregator_output(aggregated_nodes)

    if flat:
        items: Iterable[tuple[str, Mapping[str, Any]]] = (
            (k, v) for k, v in aggregated_nodes.items() if isinstance(v, Mapping)
            and {"score", "short_score", "medium_score", "long_score"} <= set(v.keys())
        )
    else:
        nodes = (aggregated_nodes or {}).get("nodes") or {}
        if isinstance(nodes, list):
            items = (
                (str(n.get("node_id") or ""), n)
                for n in nodes if isinstance(n, Mapping)
            )
        elif isinstance(nodes, dict):
            items = ((k, v) for k, v in nodes.items() if isinstance(v, Mapping))
        else:
            items = ()

    for node_id, node in items:
        if not isinstance(node, Mapping):
            continue
        score = _coerce_float(node.get("path_score") or node.get("score"))
        if score == 0.0 and not node.get("direction"):
            continue
        direction = _coerce_direction(node.get("direction") or score)
        rationale = str(
            node.get("rationale") or node.get("name") or node_id or ""
        )
        raw_target = node.get("score_target")
        paths.append(_PathInfo(
            node_id=str(node_id),
            score=score,
            direction=direction,
            rationale=rationale,
            score_target=str(raw_target) if raw_target is not None else None,
        ))
    return paths


def _top_paths(paths: Sequence[_PathInfo], n: int = 3) -> dict[str, list[dict[str, Any]]]:
    """Pick top ``n`` positive paths and top ``n`` negative paths, ranked by
    each path's EFFECTIVE contribution to the final score. Returns lists of
    plain dicts (JSON-friendly).

    Ranking uses :attr:`_PathInfo.effective_score` rather than the raw score so
    that discount/risk nodes (``score_target`` in
    :data:`_SUBTRACTIVE_SCORE_TARGETS`) — which store a positive magnitude but
    are SUBTRACTED from the score — are correctly treated as negative
    contributors. This keeps penalties (e.g. ``priced.run_up``, ``overvalued``)
    out of the "top positive" headline list. The reported ``score`` is the
    effective (signed) contribution so the magnitude reads honestly. This is a
    display-only ordering — the numeric final score is computed upstream and is
    unaffected."""

    positive = sorted(
        (p for p in paths if p.effective_score > 0),
        key=lambda p: -p.effective_score,
    )[:n]
    negative = sorted(
        (p for p in paths if p.effective_score < 0),
        key=lambda p: p.effective_score,
    )[:n]
    return {
        "positive": [
            {"node_id": p.node_id, "score": p.effective_score, "rationale": p.rationale}
            for p in positive
        ],
        "negative": [
            {"node_id": p.node_id, "score": p.effective_score, "rationale": p.rationale}
            for p in negative
        ],
    }


def _signals_from_inputs(
    company_score: Mapping[str, Any],
    aggregated_nodes: Mapping[str, Any] | None,
    coverage_report: Mapping[str, Any] | None,
    realtime_data: Mapping[str, Any] | None,
) -> dict[str, float]:
    """Build the spec §30 signal pack from the upstream inputs.

    Aggregator / coverage / realtime payloads are all dict-shaped contracts;
    we fall back to neutral values if a field is missing so scoring stays
    robust to partial data."""

    aggregated_nodes = aggregated_nodes or {}
    coverage_report = coverage_report or {}
    realtime_data = realtime_data or {}

    # Industry trend: aggregator may surface this on the company-level node
    # (the L0 industry block). Fall back to the sign of industry_contrib.
    industry_trend = _coerce_float(
        aggregated_nodes.get("industry_trend"),
        default=_clip_to_unit_signed(
            company_score.get("components", {}).get("industry_contrib", 0.0)
        ),
    )

    # Coverage report may be either the legacy ``{data_coverage: ...}``
    # shape or A2's nested ``{overall: {data_coverage: ...}}``.
    cov_overall: Mapping[str, Any] = {}
    if isinstance(coverage_report.get("overall"), Mapping):
        cov_overall = coverage_report["overall"]
    cov_data = _coerce_float(
        cov_overall.get("data_coverage")
        if cov_overall else coverage_report.get("data_coverage"),
        0.5,
    )

    exposure = _coerce_float(
        aggregated_nodes.get("company_exposure_overall"),
        default=cov_data,
    )

    # Pull additional signals from aggregator if available; otherwise
    # synthesise from company-score components.
    components = company_score.get("components") or {}
    capital_flow = _coerce_float(
        aggregated_nodes.get("capital_flow"),
        default=_clip_to_unit_signed(_coerce_float(components.get("capital"))),
    )
    expectation_gap = _coerce_float(
        aggregated_nodes.get("expectation_gap"),
        default=0.0,
    )
    valuation_pressure = _coerce_float(
        aggregated_nodes.get("valuation_pressure"),
        default=_clip(_coerce_float(components.get("valuation_pressure")), 0.0, 1.0),
    )
    priced_in = _coerce_float(
        aggregated_nodes.get("priced_in"),
        default=_clip(_coerce_float(components.get("priced_in")), 0.0, 1.0),
    )
    financial_revision = _coerce_float(
        aggregated_nodes.get("financial_revision"),
        default=0.0,
    )
    event_present = _coerce_float(
        aggregated_nodes.get("event_present"),
        default=1.0 if _coerce_float(components.get("event")) != 0.0 else 0.0,
    )
    new_catalyst = _coerce_float(
        aggregated_nodes.get("new_catalyst"),
        default=event_present,
    )
    operating_confirmed = _coerce_float(
        aggregated_nodes.get("operating_confirmed"),
        default=cov_data,
    )

    return {
        "industry_trend": industry_trend,
        "exposure": _clip(exposure, 0.0, 1.0),
        "financial_revision": _clip(financial_revision, -1.0, 1.0),
        "valuation_pressure": _clip(valuation_pressure, 0.0, 1.0),
        "capital_flow": _clip(capital_flow, -1.0, 1.0),
        "expectation_gap": _clip(expectation_gap, -1.0, 1.0),
        "priced_in": _clip(priced_in, 0.0, 1.0),
        "new_catalyst": _clip(new_catalyst, 0.0, 1.0),
        "competition": _clip(
            _coerce_float(aggregated_nodes.get("competition")), -1.0, 1.0,
        ),
        "event_present": _clip(event_present, 0.0, 1.0),
        "operating_confirmed": _clip(operating_confirmed, 0.0, 1.0),
    }


def _clip_to_unit_signed(value: Any) -> float:
    """Squash an arbitrary float to ``[-1, 1]`` via simple tanh-like clip."""

    f = _coerce_float(value)
    if f > 1.0:
        return 1.0
    if f < -1.0:
        return -1.0
    return f


def _company_aggregate_from_flat(
    aggregated_nodes: Mapping[str, Any], ts_code: str,
) -> Mapping[str, Any] | None:
    """Return the company-level node's aggregate from the flat shape.

    A1's overlays use ``<ts_code>:company`` for the root node. Fall back
    to the first node whose id ends in ``:company`` if the exact match
    isn't found.
    """

    if not isinstance(aggregated_nodes, Mapping):
        return None
    if ts_code:
        cid = f"{ts_code}:company"
        node = aggregated_nodes.get(cid)
        if isinstance(node, Mapping):
            return node
    for k, v in aggregated_nodes.items():
        if isinstance(k, str) and k.endswith(":company") and isinstance(v, Mapping):
            return v
    return None


def _has_role_governance(
    aggregated_nodes: Mapping[str, Any],
    stock_overlay: Mapping[str, Any],
) -> bool:
    for node in stock_overlay.get("nodes") or []:
        if isinstance(node, Mapping) and (node.get("field_role") or node.get("score_target")):
            return True
    for value in aggregated_nodes.values():
        if isinstance(value, Mapping) and (value.get("field_role") or value.get("score_target")):
            return True
    return False


def _role_participates(node: Mapping[str, Any]) -> bool:
    participates = node.get("participates_in_score")
    if participates is not None and not bool(participates):
        return False
    if node.get("score_enabled") is not None and not bool(node.get("score_enabled")):
        return False
    role = node.get("field_role")
    if role and str(role) in NON_SCORING_ROLES:
        return False
    return True


def _sum_role_target(
    aggregated_nodes: Mapping[str, Any],
    target: str,
    *,
    absolute: bool = False,
    damp: bool = False,
) -> float:
    """Roll up ``Σ(score × confidence)`` over nodes tagged ``score_target == target``.

    When ``damp=True`` the raw confidence-weighted sum is divided by
    ``max(1.0, Σconfidence)``. The ``max(1.0, …)`` floor means a sparse /
    single low-confidence node (total confidence ≤ 1) is returned unchanged
    (identical to the non-damped sum, preserving the confidence discount and
    existing test expectations), while stacked signals (Σconf > 1) are
    averaged so components no longer inflate. ``damp=False`` (default) keeps
    every existing caller's raw-sum behaviour.
    """

    total = 0.0
    conf_sum = 0.0
    matched = False
    for value in aggregated_nodes.values():
        if not isinstance(value, Mapping):
            continue
        if value.get("score_target") != target:
            continue
        if not _role_participates(value):
            continue
        matched = True
        score = _coerce_float(value.get("score"), 0.0)
        if absolute:
            score = abs(score)
        confidence = _coerce_float(value.get("confidence"), 1.0)
        total += score * confidence
        conf_sum += confidence
    if damp:
        if not matched:
            return 0.0
        return total / max(1.0, conf_sum)
    return total


def _sum_role_targets(
    aggregated_nodes: Mapping[str, Any],
    targets: set[str],
    *,
    absolute: bool = False,
    damp: bool = False,
) -> float:
    """Roll up a SET of ``score_target`` values into one component.

    With ``damp=True`` the damping is applied ONCE over the COMBINED group:
    we accumulate ``Σ(score × conf)`` and ``Σconf`` across every node matching
    any target in the set, then divide a single time by ``max(1.0, Σconf)``
    (NOT per-target). ``damp=False`` (default) is the plain sum-of-sums.
    """

    if not damp:
        return sum(
            _sum_role_target(aggregated_nodes, target, absolute=absolute)
            for target in targets
        )

    total = 0.0
    conf_sum = 0.0
    matched = False
    for value in aggregated_nodes.values():
        if not isinstance(value, Mapping):
            continue
        if value.get("score_target") not in targets:
            continue
        if not _role_participates(value):
            continue
        matched = True
        score = _coerce_float(value.get("score"), 0.0)
        if absolute:
            score = abs(score)
        confidence = _coerce_float(value.get("confidence"), 1.0)
        total += score * confidence
        conf_sum += confidence
    if not matched:
        return 0.0
    return total / max(1.0, conf_sum)


def _multiplier_factor_from_targets(
    aggregated_nodes: Mapping[str, Any],
    targets: set[str],
) -> float:
    signal = _sum_role_targets(aggregated_nodes, targets)
    return 1.0 + _clip(signal, -0.5, 1.0)


def _confidence_multiplier_from_flat(aggregated_nodes: Mapping[str, Any]) -> float:
    factors: list[float] = []
    for value in aggregated_nodes.values():
        if not isinstance(value, Mapping):
            continue
        if value.get("score_target") != "confidence_multiplier":
            continue
        if not _role_participates(value):
            continue
        confidence = _clip(_coerce_float(value.get("confidence"), 1.0), 0.0, 1.0)
        coverage = value.get("data_coverage")
        if coverage is not None:
            confidence *= _clip(_coerce_float(coverage, 1.0), 0.0, 1.0)
        factors.append(confidence)
    if not factors:
        return 1.0
    return sum(factors) / len(factors)


def _role_components_from_flat(aggregated_nodes: Mapping[str, Any]) -> dict[str, float]:
    multiplier_targets = {
        "multiplier_stack",
        "funding_multiplier",
        "theme_multiplier",
        "sentiment_multiplier",
        "policy_sensitivity_multiplier",
        "market_regime_multiplier",
        "reflexivity_multiplier",
        "liquidity_multiplier",
        "options_momentum_multiplier",
        "gamma_multiplier",
        "valuation_sensitivity_multiplier",
        "rate_sensitivity_multiplier",
        "narrative_sensitivity_multiplier",
    }
    multiplier_stack = _multiplier_factor_from_targets(
        aggregated_nodes, multiplier_targets,
    )
    return {
        # Additive + discount components use a damped denominator
        # (max(1.0, Σconf)) so stacked realtime signals average instead of
        # summing. Sparse / single low-conf nodes (Σconf ≤ 1) are unchanged.
        "expectation_gap": _sum_role_target(
            aggregated_nodes, "expectation_gap", damp=True,
        ),
        "valuation_rerating": _sum_role_target(
            aggregated_nodes, "valuation_rerating", damp=True,
        ),
        "funding_score": _sum_role_target(
            aggregated_nodes, "funding_score", damp=True,
        ),
        "sentiment_score": _sum_role_target(
            aggregated_nodes, "sentiment_score", damp=True,
        ),
        "capital_sentiment": _sum_role_targets(
            aggregated_nodes,
            {"capital_sentiment", "funding_score", "sentiment_score"},
            damp=True,
        ),
        "risk_discount": _sum_role_targets(
            aggregated_nodes,
            {"risk_discount", "uncertainty_discount", "volatility_risk", "overheat_risk"},
            absolute=True,
            damp=True,
        ),
        "valuation_pressure": _sum_role_target(
            aggregated_nodes, "valuation_pressure", absolute=True, damp=True,
        ),
        "priced_in_discount": _sum_role_targets(
            aggregated_nodes,
            {"priced_in_discount", "option_priced_in", "time_decay"},
            absolute=True,
            damp=True,
        ),
        "funding_multiplier": _multiplier_factor_from_targets(
            aggregated_nodes, {"funding_multiplier"},
        ),
        "theme_multiplier": _multiplier_factor_from_targets(
            aggregated_nodes, {"theme_multiplier"},
        ),
        "policy_sensitivity_multiplier": _multiplier_factor_from_targets(
            aggregated_nodes, {"policy_sensitivity_multiplier"},
        ),
        "market_regime_multiplier": _multiplier_factor_from_targets(
            aggregated_nodes, {"market_regime_multiplier"},
        ),
        "reflexivity_multiplier": _multiplier_factor_from_targets(
            aggregated_nodes, {"reflexivity_multiplier"},
        ),
        "valuation_sensitivity_multiplier": _multiplier_factor_from_targets(
            aggregated_nodes,
            {
                "valuation_sensitivity_multiplier",
                "rate_sensitivity_multiplier",
                "narrative_sensitivity_multiplier",
            },
        ),
        "multiplier_stack": multiplier_stack,
        "confidence_multiplier": _confidence_multiplier_from_flat(aggregated_nodes),
    }


def _industry_variables_from_flat(
    aggregated_nodes: Mapping[str, Any],
    stock_overlay: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Synthesize an industry-variable list from the flat aggregator output.

    For every node in the overlay whose layer is industry-*, look up the
    aggregator's score for that node and produce the dict shape that
    ``compute_company_score`` expects (score + exposure + share + …).

    The overlay's ``materiality`` / ``exposure`` slots are used as the
    multiplicative inputs; when a slot is null we fall back to 1.0 so
    the variable still participates with its raw score.
    """

    nodes_yaml = stock_overlay.get("nodes") or []
    out: list[dict[str, Any]] = []
    use_governance = _has_role_governance(aggregated_nodes, stock_overlay)
    for n in nodes_yaml:
        if not isinstance(n, Mapping):
            continue
        node_id = n.get("node_id")
        agg = aggregated_nodes.get(node_id) if isinstance(node_id, str) else None
        if not isinstance(agg, Mapping):
            continue
        if use_governance:
            merged_role = agg.get("field_role") or n.get("field_role")
            merged_target = agg.get("score_target") or n.get("score_target")
            role_node = {
                "field_role": merged_role,
                "score_target": merged_target,
                "participates_in_score": (
                    agg.get("participates_in_score")
                    if agg.get("participates_in_score") is not None
                    else n.get("participates_in_score")
                ),
                "score_enabled": agg.get("score_enabled"),
            }
            if not _role_participates(role_node):
                continue
            if merged_target not in {
                "fundamental_score",
                "base_score",
                "node_score",
                "parent_score",
                "optionality_score",
            }:
                continue
            if merged_role not in {"score_component", "derived_metric", "gate", "aggregation"}:
                continue
        else:
            layer = str(n.get("layer") or "")
            if not (layer.startswith("industry") or layer.startswith("company_position")):
                continue
        out.append({
            "name": n.get("node_name") or n.get("dp_id") or node_id,
            "node_id": node_id,
            "score": _coerce_float(agg.get("score"), 0.0),
            "exposure": _coerce_float(n.get("exposure"), 1.0),
            "revenue_share": _coerce_float(
                n.get("revenue_share") or n.get("materiality"), 1.0,
            ),
            "profit_elasticity": _coerce_float(
                n.get("profit_elasticity"), 1.0,
            ),
            "financial_sensitivity": _coerce_float(
                n.get("financial_sensitivity"), 1.0,
            ),
            "valuation_sensitivity": _coerce_float(
                n.get("valuation_sensitivity"), 1.0,
            ),
            "direction": n.get("direction") or "neutral",
            "confidence": _coerce_float(agg.get("confidence"), 0.0),
            "materiality": _coerce_float(n.get("materiality"), 1.0),
        })

    # ---- Realtime-bridge dead-sink rescue ----------------------------------
    # The overlay loop above only sees authored YAML nodes, so synthetic
    # realtime leaves (node_id ``<ts>:<dp_id>:rt``) never reach the company
    # score this way. Two score-targets have a sink HERE (industry_contrib →
    # the §27.4 `fundamental` term) but NO flat sink in
    # ``_role_components_from_flat``: ``fundamental_score`` and
    # ``optionality_score``. Without this, ~96/250 participating spec fields
    # that target fundamental_score are a dead sink via the bridge.
    #
    # ⚠️ Restrict STRICTLY to {fundamental_score, optionality_score}. Every
    # other live target (valuation_rerating, expectation_gap, risk_discount,
    # funding/sentiment_score, priced_in_discount, *_multiplier,
    # confidence_multiplier) already counts once via _role_components_from_flat
    # path #1 — routing them here too would double-count them.
    if use_governance:
        _DEAD_SINK_TARGETS = {"fundamental_score", "optionality_score"}
        emitted_ids = {v.get("node_id") for v in out}
        # Accumulate ALL synthetic dead-sink nodes into a single damped-mean
        # variable instead of emitting one industry-variable per node. Each
        # synthetic node defaults every weight to 1.0, so N of them would SUM
        # in compute_company_score → inflation as more realtime fields wire in.
        # We collapse them to ONE var whose score is
        # ``Σ(node_score × conf) / max(1.0, Σconf)`` (the same damping the
        # additive components use), confidence = mean conf, direction = sign.
        synth_total = 0.0          # Σ(node_score × conf)
        synth_conf_sum = 0.0       # Σ conf (damping denominator)
        synth_conf_count = 0       # for the mean confidence
        synth_matched = False
        for node_id, agg in aggregated_nodes.items():
            if not isinstance(agg, Mapping):
                continue
            # Prefer the explicit flag (propagated through aggregation); fall
            # back to the ``:rt`` node_id suffix so detection stays reliable
            # even if a future refactor drops the flag.
            is_synthetic = bool(agg.get("synthetic_realtime")) or (
                isinstance(node_id, str) and node_id.endswith(":rt")
            )
            if not is_synthetic:
                continue
            if node_id in emitted_ids:
                continue
            if agg.get("score_target") not in _DEAD_SINK_TARGETS:
                continue
            if not _role_participates(agg):
                continue
            score = _coerce_float(agg.get("score"), 0.0)
            confidence = _coerce_float(agg.get("confidence"), 0.0)
            synth_total += score * confidence
            synth_conf_sum += confidence
            synth_conf_count += 1
            synth_matched = True

        if synth_matched:
            # Damped mean — identical to a single node when Σconf ≤ 1 (the
            # max(1.0, …) floor preserves the lone-node confidence discount),
            # averaging when signals stack so industry_contrib does not scale
            # linearly with the node count.
            collapsed_score = synth_total / max(1.0, synth_conf_sum)
            mean_conf = (
                synth_conf_sum / synth_conf_count if synth_conf_count else 0.0
            )
            direction = (
                "positive" if collapsed_score > 0
                else "negative" if collapsed_score < 0 else "neutral"
            )
            # Synthetic nodes have no overlay weights; default every
            # multiplicative factor to 1.0 so the damped-mean score flows
            # through compute_company_score unchanged. A future B-calibration
            # pass can tune these per dp_id / score_target.
            out.append({
                "name": "realtime_fundamental",
                "node_id": "realtime_fundamental",
                "score": collapsed_score,
                "exposure": 1.0,
                "revenue_share": 1.0,
                "profit_elasticity": 1.0,
                "financial_sensitivity": 1.0,
                "valuation_sensitivity": 1.0,
                "direction": direction,
                "confidence": mean_conf,
                "materiality": 1.0,
            })
    return out


def score_company(
    stock_overlay: Mapping[str, Any],
    aggregated_nodes: Mapping[str, Any] | None = None,
    coverage_report: Mapping[str, Any] | None = None,
    realtime_data: Mapping[str, Any] | None = None,
    horizons: Mapping[str, Mapping[str, float]] | None = None,
    horizon_weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Top-level scoring driver.

    Combines:
      1. ``compute_company_score`` from the aggregator's industry-variable
         scores plus the company-level event/capital/risk slots.
      2. ``compute_final_score`` from the company score + expectation_gap +
         valuation_rerating + capital_sentiment, with per-horizon mixing.
      3. ``classify_mode`` (spec §30) using a signal pack derived from
         aggregator + coverage + realtime data.
      4. Top-3 positive / negative paths surfaced by the aggregator.

    All upstream payloads are **dict-shaped contracts** so this module
    stays decoupled from A1/A2's implementation details.
    """

    aggregated_nodes = aggregated_nodes or {}
    coverage_report = coverage_report or {}
    realtime_data = realtime_data or {}

    ts_code = str(stock_overlay.get("ts_code") or "")
    industry_id = str(stock_overlay.get("industry_id") or "")

    # Detect whether the caller passed the **flat** aggregator output
    # (real ``aggregate_company_graph`` result) or the **envelope** form
    # (used by tests that want to inject industry_variables directly).
    flat = _is_flat_aggregator_output(aggregated_nodes)
    role_components: dict[str, float] = {}

    if flat:
        # Re-shape: pull the company-level node's aggregate as the
        # `fundamental` proxy, and surface industry-layer leaves/parents
        # as the industry_variables block.
        industry_variables = _industry_variables_from_flat(
            aggregated_nodes, stock_overlay
        )
        # Look up company node aggregate so risk/priced-in/discount hooks
        # populated by the aggregator are propagated.
        company_aggregate = _company_aggregate_from_flat(
            aggregated_nodes, ts_code
        )
        role_components = (
            _role_components_from_flat(aggregated_nodes)
            if _has_role_governance(aggregated_nodes, stock_overlay)
            else {}
        )
        company_event_score = _coerce_float(
            aggregated_nodes.get("company_event_score"), 0.0,
        )  # not yet computed by A1; default to 0
        capital_sentiment = _coerce_float(
            aggregated_nodes.get("capital_sentiment_score"),
            role_components.get("capital_sentiment", 0.0),
        )
        risk_discount = _coerce_float(
            company_aggregate.get("risk_discount") if company_aggregate else None,
            role_components.get("risk_discount", 0.0),
        )
        valuation_pressure = _coerce_float(
            aggregated_nodes.get("valuation_pressure"),
            role_components.get("valuation_pressure", 0.0),
        )
        priced_in_discount = _coerce_float(
            company_aggregate.get("priced_in_discount") if company_aggregate else None,
            role_components.get("priced_in_discount", 0.0),
        )
        if role_components:
            if capital_sentiment == 0.0:
                capital_sentiment = role_components.get("capital_sentiment", 0.0)
            if risk_discount == 0.0:
                risk_discount = role_components.get("risk_discount", 0.0)
            if priced_in_discount == 0.0:
                priced_in_discount = role_components.get("priced_in_discount", 0.0)
            if valuation_pressure == 0.0:
                valuation_pressure = role_components.get("valuation_pressure", 0.0)
    else:
        industry_variables = aggregated_nodes.get("industry_variables") or []
        company_event_score = _coerce_float(
            aggregated_nodes.get("company_event_score"), 0.0,
        )
        capital_sentiment = _coerce_float(
            aggregated_nodes.get("capital_sentiment_score"), 0.0,
        )
        risk_discount = _coerce_float(aggregated_nodes.get("risk_discount"), 0.0)
        valuation_pressure = _coerce_float(
            aggregated_nodes.get("valuation_pressure"), 0.0,
        )
        priced_in_discount = _coerce_float(
            aggregated_nodes.get("priced_in_discount"), 0.0,
        )

    company_score = compute_company_score(
        industry_variables=industry_variables,
        company_event_score=company_event_score,
        capital_sentiment_score=capital_sentiment,
        risk_discount=risk_discount,
        valuation_pressure=valuation_pressure,
        priced_in_discount=priced_in_discount,
    )

    # Spec §27.4 decomposes the stock final score as
    # ``fundamental + expectation_gap + valuation_rerating + capital_sentiment
    #  - risk - priced_in``. To avoid double-counting capital sentiment +
    # risk + priced_in (which §27.3's company score also subtracts), we feed
    # the **industry-driven business fundamentals** as the fundamental
    # input, and the event signal as part of the fundamental too (since
    # company-specific events are operational, not market-driven). Capital
    # sentiment / risk / priced-in are then injected once at the §27.4 level.
    #
    # F7 — use the *bounded* industry block (tanh-squashed, see
    # _INDUSTRY_TOTAL_SCALE) so the fundamental that drives the final score /
    # base_score / trading_signal sits on the same ~[-1, 1] scale as the other
    # channels and can't grow merely with industry-node count. The raw Σ is
    # still surfaced as components["industry_contrib"] for transparency.
    industry_contrib = company_score["components"]["industry_contrib_bounded"]
    # R-2b: ``industry_contrib_bounded`` is now the coverage-normalized industry
    # MEAN (no longer tanh(Σ)). The post-tanh ``*= multiplier_stack`` is removed:
    # multiplying a SIGNED fundamental by a >=1 tailwind made 41% of names
    # (negative fundamental) MORE negative (inflows worsening weak names) and
    # pushed every stock past the F7 bound. Tailwind multipliers belong in a
    # timing/sentiment channel, not multiplied onto company quality.
    fundamental = industry_contrib + company_event_score
    expectation_gap_score = _coerce_float(
        aggregated_nodes.get("expectation_gap_score"),
        role_components.get("expectation_gap", 0.0),
    )
    valuation_rerating_score = _coerce_float(
        aggregated_nodes.get("valuation_rerating_score"),
        role_components.get("valuation_rerating", 0.0),
    )
    if role_components:
        if expectation_gap_score == 0.0:
            expectation_gap_score = role_components.get("expectation_gap", 0.0)
        if valuation_rerating_score == 0.0:
            valuation_rerating_score = role_components.get("valuation_rerating", 0.0)

    path_infos = _collect_path_infos(aggregated_nodes)
    top = _top_paths(path_infos, n=3)

    # Apply spec §28 default per-horizon component mix when the caller
    # didn't supply one. ``compute_final_score`` itself stays back-compat
    # (None → unweighted base for all three horizons) so low-level math
    # callers + the existing test_unweighted_base assertion are unchanged;
    # the high-level orchestrator is the right place to enforce the
    # default since this is where "produce a stock view" intent lives.
    effective_horizons = (
        horizons if horizons is not None else SPEC28_DEFAULT_HORIZON_MIX
    )
    final = compute_final_score(
        fundamental_score=fundamental,
        expectation_gap_score=expectation_gap_score,
        valuation_rerating_score=valuation_rerating_score,
        capital_sentiment_score=capital_sentiment,
        risk_discount=risk_discount,
        priced_in_discount=priced_in_discount,
        horizons=effective_horizons,
        primary_positive_path=top["positive"],
        primary_negative_path=top["negative"],
    )
    # R-2c: confidence is a CONVICTION band, not a magnitude. Record it alongside
    # the score but do NOT multiply it into base/totals. Multiplying conflated
    # "how sure are we" (coverage / evidence quality) with "how strong is the
    # signal", and crushed genuinely high-merit but low-coverage names — a
    # ~0.65× haircut compressed base ~1.54× for every low-confidence stock,
    # which is why BUY% collapsed. The band is surfaced for display / mode; the
    # point estimate stays on the signal's own scale. BUY/HOLD/WATCH thresholds
    # were re-anchored to this (un-compressed) scale in R-5.
    confidence_multiplier = role_components.get("confidence_multiplier", 1.0)
    if role_components:
        final["components"]["confidence_multiplier"] = confidence_multiplier
    core_final = dict(final)
    market_adapter = apply_market_adapter(
        final_score=core_final,
        role_components=role_components,
        stock_overlay=stock_overlay,
        ts_code=ts_code,
    )
    market_final = market_adapter["adjusted_final_score"]

    # Align the RETURNED trading_meaning verb with the trading_signal basis.
    # ``apply_market_adapter`` deep-copies ``core_final`` (including its
    # ``trading_meaning``, which was computed on the core / pre-market-adapter
    # base_score whose scale is ~0.5 lower than the market-adjusted base the
    # signal thresholds). Under the higher T1 thresholds that stale verb would
    # read 回避/观察 even when ``trading_signal`` is BUY — a visible
    # contradiction. Recompute the verb on the market-adjusted short/medium/
    # long totals + market-adjusted base so verb and signal agree. The returned
    # ``final_score`` and ``market_adjusted_final_score`` are this same object,
    # so the single override fixes both; ``core_final_score["trading_meaning"]``
    # is left as-is (it documents the pre-adapter view). The displayed
    # short/medium/long totals are not changed.
    market_final["trading_meaning"] = _describe_trading_meaning(
        _coerce_float(market_final.get("short_total"), 0.0),
        _coerce_float(market_final.get("medium_total"), 0.0),
        _coerce_float(market_final.get("long_total"), 0.0),
        base_score=_coerce_float(market_final.get("base_score"), 0.0),
    )

    signals = _signals_from_inputs(
        company_score=company_score,
        aggregated_nodes=aggregated_nodes,
        coverage_report=coverage_report,
        realtime_data=realtime_data,
    )
    mode = classify_mode(final_score=market_final, signals=signals)

    # Trading signal is computed off the **unweighted base** so the
    # BUY/HOLD/WATCH/AVOID thresholds remain on the same scale they were
    # calibrated for. The per-horizon totals stay weighted (spec §28) for
    # the UI time-profile view (短/中/长), but signal is the "overall
    # bullishness" answer — orthogonal to "when does it show up". Pre-fix
    # this happened to coincide because horizons defaulted to None and
    # short=medium=long=base; we now make the contract explicit.
    base_score = _coerce_float(market_final.get("base_score"), 0.0)
    signal = _trading_signal_from_mix(
        base_score, base_score, base_score,
        horizon_weights=horizon_weights,
    )

    # RD-A v2 (parallel): merit/timing decomposition of the SAME six core
    # components (M + T == core unweighted base). Computed on the CORE scale
    # (pre-market-adapter; regime modulation is R-7's job, not v2's).
    merit = fundamental + expectation_gap_score - risk_discount
    timing = (valuation_rerating_score + capital_sentiment
              - priced_in_discount)
    signal_v2 = dual_axis_signal(merit, timing)

    return {
        "ts_code": ts_code,
        "industry_id": industry_id,
        "short_total": market_final["short_total"],
        "medium_total": market_final["medium_total"],
        "long_total": market_final["long_total"],
        "mode": mode["mode"],
        "mode_display": mode["mode_display"],
        "mode_confidence": mode["confidence"],
        "mode_rationale": mode["rationale"],
        "mode_drivers": mode["primary_drivers"],
        "company_score": company_score,
        "core_final_score": core_final,
        "final_score": market_final,
        "market_adjusted_final_score": market_final,
        "market_adapter": market_adapter,
        "top_paths": top,
        "trading_signal": signal,
        "merit": merit,
        "timing": timing,
        "trading_signal_v2": signal_v2,
        "signals": signals,
        "role_components": role_components,
    }


__all__ = [
    "HORIZON_DEFAULT_WEIGHTS",
    "SPEC28_DEFAULT_HORIZON_MIX",
    "MODE_DE_RATING",
    "MODE_DIGESTION",
    "MODE_DISPLAY",
    "MODE_MODERATE_BULL",
    "MODE_STRONG_BULL",
    "MODE_STRUCTURAL_DIVERGENCE",
    "MODE_TREND_REVERSAL",
    "MODE_WAIT_FOR_CONFIRMATION",
    "SIGNAL_BUY_THRESHOLD",
    "SIGNAL_HOLD_THRESHOLD",
    "SIGNAL_WATCH_THRESHOLD",
    "classify_mode",
    "compute_company_score",
    "compute_final_score",
    "compute_node_score",
    "compute_path_score",
    "dual_axis_signal",
    "score_company",
]
