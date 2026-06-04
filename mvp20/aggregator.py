"""Parent-node aggregation + three-horizon scoring for stock overlays.

Implements mvp20 spec §27 (父节点得分公式) + §29 (三周期分) + §23 (缺失
节点处理) on top of the static YAML overlay produced by ``mvp20.overlays``.

Pipeline
--------
1. Parse the stock overlay's ``nodes`` list into a (node_id → node) map plus
   a parent → children adjacency map.
2. Walk the tree bottom-up (topological order, leaves first).
3. For each non-leaf parent, aggregate its visible children using:

       Parent Score =
         Σ (Direction × Strength × Weight × Confidence × Recency)
         - Risk Discount - Priced-in Discount

   - Weight  = base_weight × active_weight × materiality (renormalized over
     **applicable** siblings — N/A and Inactive children drop out, the rest
     re-share the 1.0 budget).
   - Strength comes from the value payload via ``_to_scalar`` — strong/moderate/
     weak qualitative cues, ``yoy_pct``-driven magnitudes, or explicit
     ``score``/``intensity`` numbers.
   - Direction is read from ``direction`` (positive=+1, negative=-1,
     neutral/bidirectional=0).
   - Recency uses an exponential half-life from ``last_updated`` (no
     ``last_updated`` → recency=1.0; details in ``_recency``).
   - Risk Discount + Priced-in Discount currently stub to 0; richer modules
     plug them in later (see TODO at the bottom).

4. For each node also emit short/medium/long composite scores. Each node's
   raw score is mixed across the three horizons using a weight vector
   classified by ``_classify_horizon`` based on dp_id / node_name keywords
   (spec §29 tables).

5. Returns ``{node_id: {score, short_score, medium_score, long_score,
   confidence, data_coverage, n_children_*}}``.

Status / missing-state handling (spec §23)
-----------------------------------------
- Known       → contributes via direction × strength × weight.
- Unknown     → kept for confidence accounting (lowers data_coverage), but
                its strength defaults to 0 so it can't fake a direction.
- Inactive    → active_weight forced to 0, drops out entirely.
- N/A         → dropped, siblings renormalize over the surviving weight pool.
- Optionality → split into ``current_contribution`` (counts as a normal
                Known child) and ``future_option_value`` (added separately to
                the long-horizon score only).
- Low Materiality → no special handling here; the materiality factor in the
                renormalized weight handles it naturally.
"""

from __future__ import annotations

import bisect
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from mvp20.field_governance import (
    FieldGovernanceRegistry,
    NON_SCORING_ROLES,
    load_default_governance,
)


# ---------------------------------------------------------------------------
# Direction / strength helpers
# ---------------------------------------------------------------------------

_DIRECTION_SIGN = {
    "positive": 1.0,
    "negative": -1.0,
    "neutral": 0.0,
    "bidirectional": 0.0,
    None: 0.0,
}

_MAGNITUDE_TABLE = {
    "strong": 0.8,
    "moderate": 0.5,
    "weak": 0.3,
    "none": 0.0,
    "low": 0.3,
    "medium": 0.5,
    "high": 0.8,
}

_QUALITY_FACTOR_TABLE = {
    "very_low": 0.2,
    "low": 0.4,
    "medium": 0.7,
    "moderate": 0.7,
    "high": 0.9,
    "very_high": 1.0,
    "strong": 0.9,
    "weak": 0.4,
}

_TREND_SIGN = {
    "up": 1.0,
    "up_moderate": 0.6,
    "up_strong": 1.0,
    "mixed": 0.3,
    "flat": 0.0,
    "stable": 0.0,
    "down": -1.0,
    "down_strong": -1.0,
    "down_moderate": -0.6,
}

# C-2 fix — a *qualitative* ``trend`` tag (``up``/``down``) is a weak cue, not a
# saturated signal. Historically a bare ``trend: up`` returned ``abs(sign) =
# 1.0``, letting a content-free directional tag (no rank / share / strength,
# e.g. an analyst who wrote "不填具体排名和份额") pin a fundamental leaf at full
# magnitude. A trend with no real numeric backing must stay SMALL: the trend's
# direction-intensity (up_strong/up vs up_moderate vs mixed) scales WITHIN this
# cap. Confidence gating happens downstream — ``_aggregate_parent`` already
# multiplies every leaf score by its confidence, so we deliberately do NOT
# re-apply confidence here (that would double-count it). Bare ``flat``/``stable``
# (sign 0) still maps to 0.
_BARE_TREND_MAGNITUDE_CAP = 0.2


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _factor(value: Any, default: float = 1.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    key = str(value).strip().lower().replace(" ", "_")
    return _QUALITY_FACTOR_TABLE.get(key, default)


def _to_scalar(value: Any, node: dict | None = None) -> float:
    """Reduce a node's ``value`` payload to a representative magnitude in
    [0, 1]. Direction is handled separately via ``direction`` on the node —
    here we just want how strong the signal is.

    Resolution order:
    1. Explicit ``score`` / ``intensity`` / ``strength`` keys (passed through,
       clipped) — an explicit numeric strength earns FULL magnitude.
    2. ``yoy_pct``: tanh(yoy/50) magnitude (50% YoY ≈ 0.76).
    3. ``magnitude``: strong/moderate/weak/none table.
    4. ``trend``: a *qualitative* directional tag with no numeric strength →
       a SMALL magnitude capped at ``_BARE_TREND_MAGNITUDE_CAP`` (×0.2),
       scaled by the trend's own intensity. Never saturates to ±1.0 (C-2 fix).
    5. Numeric scalar at top level → clipped.
    6. Anything else → 0.
    """

    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return abs(_clip(float(value)))

    if not isinstance(value, dict):
        return 0.0

    # 1. Explicit score / intensity
    for key in ("score", "intensity", "strength"):
        if key in value and value[key] is not None:
            try:
                return abs(_clip(float(value[key])))
            except (TypeError, ValueError):
                pass

    # 2. yoy_pct via tanh
    yoy = value.get("yoy_pct")
    if yoy is not None:
        try:
            return abs(_clip(math.tanh(float(yoy) / 50.0)))
        except (TypeError, ValueError):
            pass

    # 3. magnitude qualitative
    mag = value.get("magnitude")
    if isinstance(mag, str):
        if mag.lower() in _MAGNITUDE_TABLE:
            return _MAGNITUDE_TABLE[mag.lower()]

    # 4. trend — a QUALITATIVE directional tag. We only reach here when steps
    # 1-3 found no explicit numeric strength/score/intensity, no yoy_pct, and no
    # ``magnitude`` word, i.e. the node has NO real numeric backing for its
    # magnitude. Such a bare ``trend: up``/``down`` must NOT saturate to ±1.0
    # (C-2). Cap it small and let the trend's direction-intensity scale within
    # the cap: ``up``/``up_strong`` (sign ±1.0) → 0.2, ``up_moderate`` (±0.6) →
    # 0.12, ``mixed`` (0.3) → 0.06, ``flat``/``stable`` (0.0) → 0.0. Sign is
    # owned by the node's ``direction``; here we only emit the magnitude.
    trend = value.get("trend")
    if isinstance(trend, str):
        sign = _TREND_SIGN.get(trend.lower())
        if sign is not None:
            return _BARE_TREND_MAGNITUDE_CAP * abs(sign)

    # 5. Some Optionality nodes carry split values — fall back to the future
    # piece's magnitude if no other signal present.
    if "future_option_value" in value or "current_contribution" in value:
        future = value.get("future_option_value")
        current = value.get("current_contribution")
        if isinstance(future, (int, float)):
            return abs(_clip(float(future)))
        if isinstance(current, (int, float)):
            return abs(_clip(float(current)))

    return 0.0


def _direction_sign(direction: Any) -> float:
    if isinstance(direction, str):
        return _DIRECTION_SIGN.get(direction.lower(), 0.0)
    return _DIRECTION_SIGN.get(direction, 0.0)


# ---------------------------------------------------------------------------
# Recency
# ---------------------------------------------------------------------------

# Spec is vague on the exact half-life. Default to 90d exponential decay
# (matches §29's "短线 1-5 个交易日 / 中线 1-2 个季度" framing — one quarter
# halflife gives short-term news weight ~1.0 while month-old data still
# carries ~0.7). Override via ``recency_halflife_days`` if you need a
# different shape.
_RECENCY_HALFLIFE_DAYS = 90.0


def _recency(last_updated: str | None, *,
             ref_now: datetime | None = None,
             halflife_days: float = _RECENCY_HALFLIFE_DAYS) -> float:
    """Exponential decay vs ``last_updated``. Missing → 1.0 (don't penalize
    static / quarterly nodes for being mid-quarter)."""

    if not last_updated:
        return 1.0
    try:
        # Handle naive / +08:00 / Z / etc.
        ts = str(last_updated).replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = ref_now or datetime.now(tz=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        delta_days = max(0.0, (now - dt).total_seconds() / 86400.0)
    except (ValueError, TypeError):
        return 1.0
    if halflife_days <= 0:
        return 1.0
    # f(0)=1, f(halflife)=0.5
    return math.exp(-math.log(2.0) * delta_days / halflife_days)


# ---------------------------------------------------------------------------
# Horizon classification (spec §29)
# ---------------------------------------------------------------------------

# Keyword tables — match against dp_id (case-insensitive) and node_name.
_SHORT_KEYWORDS = (
    # Chinese names
    "事件", "资金", "情绪", "成交量", "拥挤", "已定价", "买盘", "卖盘",
    "净流入", "换手", "期权", "大盘", "whisper", "预期差",
    # dp_id tokens
    "L5.", "L6.", "L7.", "L8.priced", "L8.val", "flow", "trade",
    "crowd", "surprise", "priced", "netbuy",
)

_MEDIUM_KEYWORDS = (
    # Chinese names
    "订单", "销量", "价格", "毛利率", "收入", "指引", "EPS", "景气",
    "客户结构", "渠道", "产品", "交付", "转化率", "留存率", "客流",
    "复购", "份额", "招标",
    # dp_id tokens
    "L3.", "L4.", "L9.", "earnings", "revenue", "margin", "guidance",
    "product", "channel", "customer", "delivery", "volume", "share",
)

_LONG_KEYWORDS = (
    # Chinese names
    "空间", "竞争格局", "商业模式", "技术壁垒", "品牌壁垒", "长期利润",
    "替代", "护城河", "新业务", "潜在", "可选", "渗透率", "TAM",
    "替换周期",
    # dp_id tokens
    "L0.", "L1.", "L2.", "L10.", "L11.long", "tam", "moat", "newbiz",
    "lifecycle", "penetration",
)

_DEFAULT_MIX = (0.33, 0.34, 0.33)
_SHORT_MIX = (0.5, 0.3, 0.2)
_MEDIUM_MIX = (0.2, 0.5, 0.3)
_LONG_MIX = (0.1, 0.3, 0.6)


def _classify_horizon(dp_id: str | None, node_name: str | None) -> tuple[float, float, float]:
    """Return (short, medium, long) mix weights. Keyword match priority
    is short > long > medium > default. Short is checked first because
    L8.val.priced_in / L7.* / L5.surprise are explicitly short-skewed in
    the spec, even though their layer ID lives outside the L0-L2 ``long``
    range."""

    haystack = f"{dp_id or ''} {node_name or ''}".lower()

    for kw in _SHORT_KEYWORDS:
        if kw.lower() in haystack:
            return _SHORT_MIX
    for kw in _LONG_KEYWORDS:
        if kw.lower() in haystack:
            return _LONG_MIX
    for kw in _MEDIUM_KEYWORDS:
        if kw.lower() in haystack:
            return _MEDIUM_MIX
    return _DEFAULT_MIX


# ---------------------------------------------------------------------------
# Node bookkeeping
# ---------------------------------------------------------------------------

# Possible top-level status values (data_status / status are sometimes
# inconsistently filled; we read both).
_STATUS_INACTIVE = {"inactive"}
_STATUS_NA = {"n/a", "na", "not_applicable", "not applicable"}
_STATUS_UNKNOWN = {"unknown"}
_STATUS_UNAVAILABLE = {"unavailable"}
_STATUS_PROXY = {"proxy"}
_STATUS_OPTIONALITY = {"optionality"}
_STATUS_KNOWN = {"known"}
_STATUS_LOW_MAT = {"low materiality", "low_materiality"}

_MULTIPLIER_TARGETS = {
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


def _node_status(node: dict) -> str:
    """Normalize node status to one of:
    {"Known", "Unknown", "Unavailable", "Proxy", "Inactive", "N/A",
    "Optionality", "LowMateriality"}.
    Reads ``data_status`` first, then falls back to ``status``."""

    raw = (node.get("data_status") or node.get("status") or "").strip().lower()
    if raw in _STATUS_INACTIVE:
        return "Inactive"
    if raw in _STATUS_NA:
        return "N/A"
    if raw in _STATUS_UNKNOWN:
        return "Unknown"
    if raw in _STATUS_UNAVAILABLE:
        return "Unavailable"
    if raw in _STATUS_PROXY:
        return "Proxy"
    if raw in _STATUS_OPTIONALITY:
        return "Optionality"
    if raw in _STATUS_LOW_MAT:
        return "LowMateriality"
    if raw in _STATUS_KNOWN:
        return "Known"
    # Default: treat as Unknown so we don't fabricate signal.
    return "Unknown"


def _node_score_enabled(node: Mapping[str, Any]) -> bool:
    participates = node.get("participates_in_score")
    if participates is not None:
        return bool(participates)
    field_role = node.get("field_role")
    if field_role:
        return str(field_role) not in NON_SCORING_ROLES
    return True


def _is_multiplier_node(node: Mapping[str, Any]) -> bool:
    return (
        node.get("field_role") == "multiplier"
        or node.get("score_target") in _MULTIPLIER_TARGETS
    )


def _governance_payload(node: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "field_role": node.get("field_role"),
        "score_target": node.get("score_target"),
        "participates_in_score": _node_score_enabled(node),
        "fallback_policy": node.get("fallback_policy"),
        "proxy_candidates": list(node.get("proxy_candidates") or []),
        "min_required_coverage": float(node.get("min_required_coverage") or 0.5),
        "neutral_value": float(node.get("neutral_value") or 0.0),
        "confidence_penalty": float(node.get("confidence_penalty") or 1.0),
    }


def _has_usable_value(value: Any) -> bool:
    return value not in (None, {})


def _apply_proxy_candidates(nodes_by_id: Mapping[str, dict]) -> None:
    """Promote Unavailable nodes to Proxy when a configured candidate exists."""

    nodes_by_dp: dict[str, list[dict]] = defaultdict(list)
    for node in nodes_by_id.values():
        dp_id = node.get("dp_id")
        if dp_id:
            nodes_by_dp[str(dp_id)].append(node)

    for node in nodes_by_id.values():
        if _node_status(node) != "Unavailable":
            continue
        for candidate_dp in node.get("proxy_candidates") or []:
            for candidate in nodes_by_dp.get(str(candidate_dp), []):
                if candidate is node:
                    continue
                if _node_status(candidate) not in {"Known", "Proxy"}:
                    continue
                if not _has_usable_value(candidate.get("value")):
                    continue
                node["value"] = candidate.get("value")
                node["data_status"] = "Proxy"
                node["status"] = "Proxy"
                node["proxy_used"] = {
                    "dp_id": candidate.get("dp_id"),
                    "node_id": candidate.get("node_id"),
                }
                current_penalty = float(node.get("confidence_penalty") or 1.0)
                node["confidence_penalty"] = min(current_penalty, 0.75)
                break
            if _node_status(node) == "Proxy":
                break


# ---------------------------------------------------------------------------
# Realtime → leaf-node bridge
# ---------------------------------------------------------------------------
#
# ``realtime_current`` (SQLite hot snapshot) holds the *current* value of every
# governance-participating real data point. Those values never reach the score
# unless the authored overlay happens to carry the same dp_id. ``synthesize_
# realtime_nodes`` closes that gap: it turns each unmapped, participating,
# non-mock snapshot entry into an overlay-leaf-shaped node so the existing
# post-order aggregation scores it as a standalone leaf.
#
# The sign convention lives entirely in ``_realtime_signal``: it returns a
# *signed* signal in [-1, 1] only for value shapes whose direction is
# unambiguous. Everything else returns ``None`` and is skipped — we never
# fabricate a direction for a bespoke financial dict.

# Score-targets where a *high* reading (rich valuation / hot crowd / overheat)
# is a drag on the score, so a positive raw percentile must flip negative.
_REALTIME_INVERTED_TARGETS = {
    "valuation_rerating",
    "risk_discount",
    "overheat_risk",
    "priced_in_discount",
}

# Curated single-field signed-percent shapes. Each maps to a divisor K used in
# ``tanh(x / K)``; ``flip`` inverts the sign (premium = expensive = negative).
_REALTIME_SIGNED_PCT_FIELDS: dict[str, tuple[float, bool]] = {
    "consensus_eps_revision_30d_pct": (20.0, False),
    "premium_vs_industry_pct": (30.0, True),
    "second_derivative": (1.0, False),
}

# L8 risk-alert cluster (R2 dead-sink fix). These dp_ids all target
# ``risk_discount`` and carry a producer-fired ``alert_severity`` (WARN/ERROR)
# plus a heterogeneous bad-direction numeric (ocf_to_ni<0, gap_pp>0, delta_pct,
# interest_debt_to_ebitda, inventory_yoy_pct, main_net_5d, …). The generic
# fallbacks read none of those keys, so every one returned None and contributed
# ZERO risk_discount — a WARN/ERROR alert that the producer already classified
# as a real risk silently fell out of the score. Confirmed against hot.sqlite
# (mode=ro): each carries ``alert_severity`` in 100% of participating
# (Known/Proxy, non-mock) rows; vocab is exactly {WARN, ERROR}.
#
# We drive the magnitude off ``alert_severity`` (uniform + always-present) rather
# than per-dp_id numeric maps: the alert ITSELF encodes the bad direction (the
# producer fired it), risk_discount takes ``abs()`` of the magnitude downstream
# (only magnitude is numeric; the sign is for top-path ranking), and two of these
# (crowdedness / liquidity_short) carry no single clean bad-direction scalar at
# all — so a severity tier is the robust common primitive. WARN → 0.5, ERROR →
# 1.0. Emitted NEGATIVE so the synthesized node's direction is "negative" (a
# risk), consistent with how the other risk_discount fields read.
_RISK_ALERT_DP_IDS: frozenset[str] = frozenset({
    "L8.cap.crowdedness",
    "L8.cap.liquidity_short",
    "L8.cap.outflow_cut",
    "L8.cap.short_increase",
    "L8.fin.cash_ar",
    "L8.fin.debt_pressure",
    "L8.fin.eps_downward",
    "L8.op.cost_overrun",
    "L8.op.inventory_glut",
})
_RISK_ALERT_SEVERITY_MAGNITUDE: dict[str, float] = {
    "WARN": 0.5,
    "ERROR": 1.0,
}


def _num(value: Any) -> float | None:
    """Coerce ``value`` to ``float`` for the realtime field rules, rejecting
    ``None``/``bool``/non-numeric so a missing key returns ``None`` upstream."""

    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# R-3a — cross-sectional reference ("peer context") for de-common-mode
# ---------------------------------------------------------------------------
# Some priced_in signals (``L6.priced.run_up``, ``L6.priced.crowdedness``) are
# computed on an ABSOLUTE / own-history scale: a broadly-up market dings every
# stock with a run-up discount, and a generally-elevated-turnover market reads
# every stock as "crowded". That common-mode level subtracts a near-constant
# ~0.33 from EVERY A-share base_score (measured: priced_in mean -0.332 / 100%
# of names) — it depresses the whole universe instead of discriminating. R-3a
# re-centers these signals CROSS-SECTIONALLY: rank each stock's raw input within
# the universe and penalize only the bad (high) tail, floored at 0, so the
# median stock gets ZERO discount and only names genuinely more priced-in than
# their peers are penalized. ``build_peer_context`` collects the universe
# distributions; the normalizers in ``_realtime_field_signal`` consume them.
# When peer_context is absent (None / dp_id missing) the normalizers fall back
# to their original absolute behaviour (bit-for-bit back-compat).

#: dp_id → the raw payload field whose universe distribution we rank against.
_PEER_CONTEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "L6.priced.run_up": ("d20_pct", "d5_pct"),       # 20d (fallback 5d) price move
    "L6.priced.crowdedness": ("percentile",),          # own-history turnover percentile
}


def _peer_raw_value(dp_id: str, value: Mapping[str, Any]) -> float | None:
    """Extract the single raw scalar that ``dp_id``'s cross-sectional rank is
    computed over (see ``_PEER_CONTEXT_FIELDS``). ``crowdedness`` carries its
    figure under a bare ``percentile`` key (or any ``*_percentile``); take the
    max. Returns None when the payload doesn't carry the field."""

    if not isinstance(value, Mapping):
        return None
    if dp_id == "L6.priced.crowdedness":
        cands = [
            _num(value[k])
            for k in value
            if isinstance(k, str)
            and (k == "percentile" or k.endswith("_percentile"))
            and _num(value[k]) is not None
        ]
        return max(cands) if cands else None
    for field in _PEER_CONTEXT_FIELDS.get(dp_id, ()):  # ordered fallback
        v = _num(value.get(field))
        if v is not None:
            return v
    return None


def build_peer_context(
    snapshots: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[float]]:
    """R-3a cross-sectional reference: given ``{ts_code: realtime_snapshot}`` for
    a scoring universe (e.g. all A-shares), collect the sorted universe
    distribution of each de-common-mode input. Returns
    ``{dp_id: sorted([raw values])}`` — consumed as ``peer_context`` by
    ``aggregate_company_graph`` / ``_realtime_field_signal``.

    A snapshot's per-dp_id entry is the ``read_hot_snapshot`` shape
    (``{dp_id: {value, ...}}``); we read ``entry["value"]`` (falling back to the
    entry itself). dp_ids with no usable values are omitted, so the normalizer
    falls back to absolute. This is shared infra: R-3b extends it to per-
    sub-track pools.
    """

    pops: dict[str, list[float]] = {dp: [] for dp in _PEER_CONTEXT_FIELDS}
    for snap in snapshots.values():
        if not isinstance(snap, Mapping):
            continue
        for dp_id in _PEER_CONTEXT_FIELDS:
            entry = snap.get(dp_id)
            if not isinstance(entry, Mapping):
                continue
            payload = entry.get("value") if "value" in entry else entry
            raw = _peer_raw_value(dp_id, payload)
            if raw is not None:
                pops[dp_id].append(raw)
    return {dp: sorted(vals) for dp, vals in pops.items() if vals}


def _xs_percentile(x: float, sorted_pop: Sequence[float]) -> float | None:
    """Cross-sectional percentile (0..1) of ``x`` within ``sorted_pop`` (a
    pre-sorted population). Midpoint rank (average of bisect_left/right) so ties
    map to the centre of their run rather than the top — keeps a uniform input
    centred at ~0.5. None when the population is empty."""

    n = len(sorted_pop)
    if n == 0:
        return None
    lo = bisect.bisect_left(sorted_pop, x)
    hi = bisect.bisect_right(sorted_pop, x)
    return ((lo + hi) / 2.0) / n


def _xs_bad_tail(x: float | None, sorted_pop: Sequence[float] | None) -> float | None:
    """De-common-mode magnitude in [0, 1]: rank ``x`` cross-sectionally and emit
    only the bad (above-median) tail, ``max(0, (pct - 0.5) * 2)``. The median
    stock → 0 (no common-mode); the universe-max → 1. Returns None when no rank
    can be computed (empty/missing population, or ``x`` is None) OR when the
    stock is at/below the cross-sectional median (not a signal vs peers — skip
    the node rather than dilute the discount mean with a zero)."""

    if x is None or not sorted_pop:
        return None
    pct = _xs_percentile(x, sorted_pop)
    if pct is None:
        return None
    mag = max(0.0, (pct - 0.5) * 2.0)
    return mag if mag > 0.0 else None


# Per-field ``change_direction`` vocabularies seen across sources. Tushare +
# FMP both emit ``upgraded``/``downgraded``/``unchanged``/``new``; the spec
# also lists up/raised/down/cut, so accept all of them.
_GUIDANCE_UP_DIRECTIONS = {"up", "raised", "upgraded", "increase", "increased"}
_GUIDANCE_DOWN_DIRECTIONS = {"down", "cut", "downgraded", "decrease", "decreased"}
_GUIDANCE_FLAT_DIRECTIONS = {"unchanged", "flat", "stable", "maintained"}

# Minimum magnitude for a *real* (nonzero) guidance revision so a tiny
# ``current_range_pct`` doesn't collapse a genuine up/down call to ~0.
_GUIDANCE_DIRECTION_FLOOR = 0.1

# Analyst-rating cross-sectional re-center (L7.mood.analyst_rating → sentiment_
# score). A-share sell-side ratings are uniformly bullish, so the textbook
# "3.0 out of 1–5 is neutral" map yields a near-uniform +0.81 for every stock
# (no discriminating power). Instead we re-center on the *universe consensus*
# so the signal measures ABOVE/BELOW peers, not absolute bullishness.
#
# CALIBRATION constants — measured across n=115 A-shares: avg_rating_score
# mean 4.63 / std 0.23 / range [3.6, 5.0] (histogram ≈ {4.0:9, 4.5:69, 5.0:36}).
# RECOMPUTE these if the rating distribution shifts / on data refresh.
_ANALYST_RATING_NEUTRAL = 4.63  # universe mean → consensus is neutral (signal 0)
_ANALYST_RATING_SCALE = 0.46    # ≈ 2× std → ±2σ saturates the signal to ±1

# Company-fundamental-QUALITY cross-sectional re-center (→ fundamental_score).
# Margins / efficiency / cash-cycle metrics are read ABOVE/BELOW the A-share
# universe via clip((value - MEDIAN) / SCALE, -1, 1): MEDIAN is the skew-robust
# universe median, SCALE ≈ the inter-quartile spread so a name ~1 IQR off peers
# saturates the signal to ±1.
#
# CALIBRATION constants — MEASURED across the current A-share universe (skew-
# robust median + ~IQR). RECOMPUTE these on every data refresh; the snapshot
# they were fit on will drift.
#
# CAVEAT — universe-relative is a FIRST APPROXIMATION. Margins and efficiency
# are strongly industry-dependent (a healthy software gross margin and a healthy
# steel gross margin are nowhere near each other), so a single universe-wide
# median mixes industries and will mis-rank names in atypical sectors. An
# industry-relative re-center (median/IQR within the peer group) is the intended
# future refinement; until then read these as "vs the broad market", not "vs
# peers". The gross-margin field below additionally carries an asymmetric lower
# tail (M-2) so structurally thin-margin assemblers aren't floored at -1.0; the
# net-margin / efficiency / cycle fields still use a symmetric universe scale.
_GROSS_MARGIN_MEDIAN = 0.29   # gross-margin fraction
_GROSS_MARGIN_SCALE = 0.22    # ≈ IQR; +1 IQR above median saturates to +1
# M-2 fix — ASYMMETRIC lower tail for gross margin. Single-digit gross margin is
# STRUCTURALLY NORMAL for servers / EMS / 代工 (assemblers pass through component
# cost), so the symmetric universe scale floored thin-margin-but-profitable names
# at -1.0 (000977 gm 6.6% → -1.0; 601138 gm 7.4% → -0.98), overstating
# fundamental weakness. The negative side now uses a WIDER scale so a thin
# structural margin reads MODERATELY negative (~-0.6) instead of saturating,
# while a genuinely collapsed/negative margin still approaches -1.0 (direction
# stays negative — never over-corrected to positive). The POSITIVE side keeps the
# original scale, so healthy-margin names are bit-for-bit unchanged.
#
# Why not a per-industry median keyed on ``industry_id``? The repo's only
# industry tag (e.g. ``AI_COMPUTE``) is too coarse: it bundles thin-margin EMS
# (浪潮 6.6% / 工业富联 7.4%) with high-margin chip & cloud names (NVDA 71% / Meta
# 82%), so the bucket median (~0.55) sits ABOVE the universe and re-centering the
# EMS names on it makes them MORE negative, not less — the opposite of the goal.
# An asymmetric tail fixes the structural-floor problem without that backfire and
# without needing a finer (currently absent) business-model tag. A genuine
# per-business-model median is the right future refinement once such a tag exists.
_GROSS_MARGIN_SCALE_NEG = 0.35  # wider negative-side scale (structural thin-margin floor)
_NET_MARGIN_MEDIAN = 0.12     # net-margin fraction
_NET_MARGIN_SCALE = 0.16      # ≈ IQR
_CCC_DAYS_MEDIAN = 36.0       # cash-conversion-cycle days (lower = better)
_CCC_DAYS_SCALE = 100.0       # ≈ IQR of CCC days
_INVENTORY_TURNOVER_DAYS_MEDIAN = 96.0  # inventory days outstanding (lower = better)
_INVENTORY_TURNOVER_DAYS_SCALE = 120.0  # ≈ IQR of inventory days
# Labor-cost yoy is self-contained (cost UP = bad): tanh(yoy% / 5.0) saturates a
# ±5% swing toward ±1, so no universe median/scale is needed for this field.
_LABOR_COST_YOY_SCALE = 5.0   # % yoy per ~1 tanh unit

# R-2a: company financial-QUALITY ratios (L5.fina.*) → fundamental_score. These
# benchmarks are the A-share UNIVERSE cross-section (median/spread of the
# realtime_current snapshot, mode=ro): ROE/ROA/debt/ocf/growth/turnover all
# re-centered on "vs the broad market". R-3 upgrades these to a finer细分赛道
# (peer-group) cross-section once an industry-relative percentile sink lands —
# until then read them as universe-relative, NOT peer-relative. Each field is a
# tanh(...) de-saturation so extreme tails don't pin every name at ±1.
_ROE_BENCH = 3.1              # quarterly ROE %, universe median (≈3.11 observed)
_ROE_SCALE = 2.0             # ROE % per ~1 tanh unit (higher ROE = better)
_ROA_BENCH = 1.8             # quarterly ROA %, universe median (≈1.82 observed)
_ROA_SCALE = 1.2             # ROA % per ~1 tanh unit (higher = better)
_DEBT_RATIO_BENCH = 47.0     # debt/assets %, universe median (≈47.3 observed)
_DEBT_RATIO_SCALE = 20.0     # debt % per ~1 tanh unit (higher debt = WORSE → inverse)
_OCF_QUALITY_BENCH = 10.0    # OCF-quality, universe median (≈9.9 observed)
_OCF_QUALITY_SCALE = 30.0    # OCF-quality per ~1 tanh unit (higher = better)
_OCF_QUALITY_CLIP_LO = -50.0  # winsorize floor (raw min ≈ -73)
_OCF_QUALITY_CLIP_HI = 150.0  # winsorize cap before tanh (raw max ≈ 2863 — extreme tail)
_NET_PROFIT_YOY_BENCH = 20.0  # net-profit yoy %, universe median (≈20.4 observed)
_NET_PROFIT_YOY_SCALE = 50.0  # yoy % per ~1 tanh unit (growth → positive)
_ASSET_TURNOVER_BENCH = 0.13  # asset turnover, universe median (≈0.129 observed)
_ASSET_TURNOVER_SCALE = 0.08  # turnover per ~1 tanh unit (higher = better)

# Valuation-MULTIPLE → valuation_rerating re-center (F1 fix). ``L6.mult.ev_ebitda``
# and ``L6.mult.forward_pe`` are DISTINCT expensive-vs-cheap multiples (NOT a
# re-count of PE/PB — those drive valuation_rerating via the percentile sink, and
# PEG is scored separately via L6.state.peg_match), so they are NEW valuation
# evidence. A HIGH multiple = expensive = mean-reversion / de-rating expectation =
# NEGATIVE for valuation_rerating; a CHEAP multiple (below the reference) is mildly
# POSITIVE. There is NO cross-sectional / peer percentile sink for these two
# multiples (unlike PE/PB), so we re-center each on its OWN bounded monotonic map.
#
# Map: ``-tanh( ln(multiple / REF) / SCALE )``. A LOG-ratio (not a raw difference)
# is used because both ratios are heavily right-skewed across the AI-compute cohort
# (observed forward_pe spans ~45→118; ev_ebitda spans ~69→370) — a linear
# ``-tanh((m-REF)/SCALE)`` would floor the whole expensive sector at -1.0 with no
# discrimination, whereas the log map keeps the cohort separable (688256 fwd_pe 118
# / ev 370 stays strictly more negative than 300502 fwd_pe 45 / ev 69) without ever
# pinning at the bound. REF is the "neutral growth" multiple (signal 0); SCALE sets
# how fast a richer multiple saturates.
#
# CALIBRATION — defensible anchors for a growth-stock universe (AI-compute trades
# rich, so the cohort SHOULD read negative; the goal is relative discrimination):
#   * forward_pe REF=22  (a market-ish forward P/E for a profitable grower),
#                 SCALE=1.1 → fwd_pe 22→0, 30→-0.27, 45→-0.58, 50→-0.63, 118→-0.91.
#   * ev_ebitda  REF=13  (a neutral EV/EBITDA), SCALE=1.4 → ev 13→0, 20→-0.30,
#                 40→-0.67, 69→-0.83, 98→-0.89, 370→-0.98.
# RECOMPUTE these if the universe's multiple distribution shifts. The same
# universe-mixing caveat as the fundamental-quality block applies (a single
# reference mixes industries); a peer-relative percentile is the future refinement
# once an ev_ebitda/forward_pe percentile sink exists.
_FORWARD_PE_REF = 22.0
_FORWARD_PE_SCALE = 1.1
_EV_EBITDA_REF = 13.0
_EV_EBITDA_SCALE = 1.4

# P/S multiple → valuation_rerating (R2 dead-sink fix). ``L6.mult.ps`` emits a
# clean ``scalar`` (price/sales TTM) that NO _realtime_signal shape read, so it
# was dropped → ZERO valuation evidence. Unlike PE/PB it has NO percentile sink
# (``L6.state.historical_percentile`` carries only pe/pb), so — exactly like
# ev_ebitda / forward_pe — we re-center it on its OWN bounded log-ratio map:
# ``-tanh(ln(ps / REF) / SCALE)``. A LOG ratio (not linear) because P/S is
# heavily right-skewed across the A-share universe. RICH P/S = expensive =
# de-rating expectation → NEGATIVE; below the reference → mildly POSITIVE.
# Confirmed against hot.sqlite (mode=ro): 231 participating rows, ALL strictly
# positive (P/S is never negative — sales > 0), median ≈ 4.0, ~IQR [1.8, 8.4].
#   REF=4.0 (universe-median P/S, the "neutral" multiple → signal 0),
#   SCALE=1.0 → ps 4→0, 8→-0.60, 17→-0.83, 1.8→+0.62, 0.9→+0.83.
# RECOMPUTE on a data refresh (same single-reference industry-mixing caveat as
# the ev_ebitda / forward_pe block; a peer-relative percentile is the future
# refinement once a P/S percentile sink exists).
_PS_REF = 4.0
_PS_SCALE = 1.0

# News-age "still being priced-in" discount (F1 fix). ``L6.priced.news_age``
# targets priced_in_discount (a MAGNITUDE in [0, 1]; sign ignored downstream — the
# discount roll-up only subtracts the magnitude). The producer already computes a
# time-decayed ``magnitude`` ∈ [0, _NEWS_AGE_PEAK=0.6] (fresh catalyst → larger
# discount, decaying with a ~30d half-life), so the rule just surfaces that bounded
# magnitude. The generic fallbacks can't read it because the payload carries it
# under a ``magnitude`` / ``scalar`` key (no score/percentile/yoy), so it was
# dropped → contributed ZERO. Reading ``magnitude`` makes a fresh announcement
# reach the priced_in_discount cluster.

# Same-disclosure dedup: ``{secondary_dp_id: primary_dp_id}``. Both fields in a
# pair are derived from the SAME company 业绩预告 (earnings pre-announcement) and
# target ``expectation_gap``, so emitting both double-counts the disclosure. The
# REVISION field (``L5.fcst.guidance_change``) subsumes the LEVEL field
# (``L9.company.earnings_guidance``): when the primary is present in the snapshot
# AND passes every synthesis gate (participating + Known/Proxy + non-mock +
# ``_realtime_signal`` not None), the secondary is SKIPPED. When the primary is
# absent or yields no clean signal (e.g. change_direction ``new``/``type_change``,
# or it's mock/Unknown/non-participating), the secondary is KEPT as a fallback.
_REALTIME_DEDUP_PRIMARY: dict[str, str] = {
    "L9.company.earnings_guidance": "L5.fcst.guidance_change",
}

# C-3 fix — freshness gate for the price-run-up / priced-in path. ``L6.priced.
# run_up`` turns a 20-day price move into a ``priced_in_discount``. When that
# row is a stale snapshot (its ``updated_at`` lags the freshest data in the
# snapshot by more than a few trading days) it can drive a full priced-in
# penalty off a move that has already reversed (observed: a run_up frozen ~3
# weeks behind the live price feed). These dp_ids' magnitude is multiplied by a
# freshness weight derived from ``updated_at`` vs the snapshot's freshest
# ``updated_at`` (the most robust, always-present asof signal at this layer —
# the run_up value payload itself carries no observation date). The weight is
# 1.0 up to ``_RUN_UP_FRESH_TRADING_DAYS`` of lag, then ramps linearly to 0.0
# at ``_RUN_UP_STALE_TRADING_DAYS`` (a ~3-week-stale row is fully zeroed). Trading
# days are approximated from calendar days via ``_TRADING_DAYS_PER_CALENDAR_DAY``.
_FRESHNESS_GATED_DP_IDS: frozenset[str] = frozenset({"L6.priced.run_up"})
_RUN_UP_FRESH_TRADING_DAYS = 5.0    # ≤ this lag → full weight
_RUN_UP_STALE_TRADING_DAYS = 15.0   # ≥ this lag → fully zeroed
_TRADING_DAYS_PER_CALENDAR_DAY = 5.0 / 7.0


def _freshness_weight(
    entry_updated_at: Any,
    ref_updated_at: Any,
) -> float:
    """Down-weight a stale realtime row. ``entry_updated_at`` / ``ref_updated_at``
    are unix epoch seconds (the ``updated_at`` on the entry and the freshest
    ``updated_at`` in the snapshot). Returns a multiplier in [0, 1]: 1.0 when the
    row lags the reference by ≤ ``_RUN_UP_FRESH_TRADING_DAYS``, ramping linearly
    to 0.0 at ``_RUN_UP_STALE_TRADING_DAYS``. Missing / unparseable timestamps →
    1.0 (fail-open: never invent staleness we can't measure)."""

    entry_ts = _num(entry_updated_at)
    ref_ts = _num(ref_updated_at)
    if entry_ts is None or ref_ts is None:
        return 1.0
    lag_calendar_days = max(0.0, (ref_ts - entry_ts) / 86400.0)
    lag_trading_days = lag_calendar_days * _TRADING_DAYS_PER_CALENDAR_DAY
    if lag_trading_days <= _RUN_UP_FRESH_TRADING_DAYS:
        return 1.0
    if lag_trading_days >= _RUN_UP_STALE_TRADING_DAYS:
        return 0.0
    span = _RUN_UP_STALE_TRADING_DAYS - _RUN_UP_FRESH_TRADING_DAYS
    return 1.0 - (lag_trading_days - _RUN_UP_FRESH_TRADING_DAYS) / span


# ─── F6-tag: business-model archetype gross-margin re-center ──────────────────
# The coarse theme tag (AI_COMPUTE, …) mixes 7%-margin EMS / 代工 with 80%-margin
# software (see the _GROSS_MARGIN_MEDIAN comment above), so universe-centering
# FLOORS structurally thin-margin names (浪潮 6.6% / 工业富联 7.4% → ~-0.64). We
# re-center L5.is.gross_margin on the stock's BUSINESS-MODEL archetype median
# instead. Assignments live in config/business_model_archetypes.yaml (per-stock,
# classified by what the business DOES — never by margin number, to avoid
# circularity). Medians below are frozen from the 2026-06-04 universe (n>=3
# archetypes only — see the tightness gate in the dict below); recompute on a
# material data refresh. Unclassified ts_codes, <3-member, and wide archetypes
# fall back to the universe median; FINANCIAL_DIVIDEND skips gross-margin entirely
# (GM is meaningless for banks/insurers — that group's GM range is 0.73).
_ARCHETYPE_GM_MEDIAN: dict[str, float] = {
    # Tightness-gated: only archetypes with n>=3 AND range<=0.30 AND no member
    # >0.35 (the neg scale) below the median — so re-centering can NEVER floor a
    # member the way a geography-mixed group would. Wide / mixed archetypes are
    # intentionally ABSENT and fall back to the universe median (status quo, no
    # regression): e.g. COMM_NETWORK_EQUIP bundles 中兴 28% with Cisco/Arista 64%
    # (median 0.64 → 中兴 would floor at -1.0), and SEMICONDUCTOR_IC / SOFTWARE /
    # COMMODITY / PHARMA carry real intra-model (US-vs-CN, cyclical) spread a single
    # median can't represent. A future per-archetype SCALE could re-admit them.
    "ASSEMBLER_EMS": 0.0997,
    "BATTERY_CELL_ESS": 0.1355,
    "BRANDED_CONSUMER_APPLIANCE": 0.2559,
    "CXO_PHARMA_SERVICES": 0.325,
    "HEAVY_MACHINERY_EQUIPMENT": 0.3007,
    "MEDICAL_DEVICE_GENERIC": 0.6187,
    "OPTICAL_MODULE": 0.4916,
    "PCB_SUBSTRATE": 0.281,
    "SEMI_EQUIP_MATERIAL": 0.4336,
    "SEMI_PACKAGING_TEST": 0.1399,
}
_GM_SKIP_ARCHETYPES: frozenset[str] = frozenset({"FINANCIAL_DIVIDEND"})
_ARCHETYPE_BY_TS_CACHE: dict[str, str] | None = None


def _archetype_by_ts() -> dict[str, str]:
    """``{ts_code: archetype}`` from config/business_model_archetypes.yaml (cached;
    missing / unreadable file → empty map → everything falls back to the universe
    median, i.e. F6-tag becomes a no-op rather than breaking scoring)."""
    global _ARCHETYPE_BY_TS_CACHE
    if _ARCHETYPE_BY_TS_CACHE is None:
        import yaml
        from pathlib import Path

        out: dict[str, str] = {}
        path = (
            Path(__file__).resolve().parent.parent
            / "config"
            / "business_model_archetypes.yaml"
        )
        if path.exists():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:  # noqa: BLE001 — a bad config must never break scoring
                data = {}
            for ts, info in (data.get("assignments") or {}).items():
                arch = info.get("archetype") if isinstance(info, Mapping) else info
                if arch:
                    out[str(ts)] = str(arch)
        _ARCHETYPE_BY_TS_CACHE = out
    return _ARCHETYPE_BY_TS_CACHE


def _resolve_gross_margin_median(ts_code: str | None) -> float | None:
    """Re-center median for L5.is.gross_margin. ``None`` → SKIP gross-margin
    scoring (FINANCIAL_DIVIDEND). Else the stock's business-model archetype median
    (n>=3) or the universe fallback for unclassified / small archetypes."""
    if not ts_code:
        return _GROSS_MARGIN_MEDIAN
    archetype = _archetype_by_ts().get(ts_code)
    if archetype in _GM_SKIP_ARCHETYPES:
        return None
    if archetype is not None and archetype in _ARCHETYPE_GM_MEDIAN:
        return _ARCHETYPE_GM_MEDIAN[archetype]
    return _GROSS_MARGIN_MEDIAN


def _realtime_field_signal(dp_id: str, value: Mapping[str, Any], score_target: str | None, ts_code: str | None = None, peer_context: Mapping[str, Sequence[float]] | None = None) -> float | None:
    """Per-dp_id signed/magnitude rules for the 8 governance realtime fields
    that the generic fallbacks in ``_realtime_signal`` can't read.

    Returns a signal in [-1, 1] (additive targets: sign matters) or a
    magnitude in [0, 1] (discount targets: ``synthesize_realtime_nodes`` stores
    ``abs(signal)`` and the discount roll-up in ``scoring`` ignores the sign and
    only subtracts the magnitude). ``None`` → unknown payload, caller skips.

    Robust to missing/None keys: any required key absent → ``None`` (never
    raises). Direction handled downstream via the node's ``direction``.
    """

    # --- Additive targets (sign preserved + added to the final score) ---

    if dp_id == "L6.priced.analyst_revision":
        # expectation_gap. Already-signed net revision in ~[-1, 1].
        net = _num(value.get("net_revision_score"))
        if net is None:
            return None
        return _clip(net, -1.0, 1.0)

    if dp_id == "L9.company.earnings_guidance":
        # expectation_gap. change_pct_{min,max} are percentage points (预增 →
        # large positive). De-saturate with tanh(avg/100) so a strong forecast
        # (+100%) lands at ~0.76 instead of pinning at 1.0. Either bound
        # missing → None.
        cp_min = _num(value.get("change_pct_min"))
        cp_max = _num(value.get("change_pct_max"))
        if cp_min is None or cp_max is None:
            return None
        return _clip(math.tanh(((cp_min + cp_max) / 2.0) / 100.0), -1.0, 1.0)

    if dp_id == "L5.fcst.guidance_change":
        # expectation_gap. Direction word sets the sign; current_range_pct
        # scales the magnitude via tanh (de-saturated so +100% → tanh(1.0)≈0.76
        # rather than pinning at 1.0), floored so a real revision isn't ~0.
        raw_dir = value.get("change_direction")
        if not isinstance(raw_dir, str):
            return None
        direction = raw_dir.strip().lower()
        if direction in _GUIDANCE_UP_DIRECTIONS:
            sign = 1.0
        elif direction in _GUIDANCE_DOWN_DIRECTIONS:
            sign = -1.0
        elif direction in _GUIDANCE_FLAT_DIRECTIONS:
            return 0.0
        else:
            # "new" / "type_change" / anything unknown → no clean direction.
            return None
        rng = _num(value.get("current_range_pct"))
        scale = math.tanh(abs(rng) / 100.0) if rng is not None else 0.0
        magnitude = max(scale, _GUIDANCE_DIRECTION_FLOOR)
        return _clip(sign * magnitude, -1.0, 1.0)

    if dp_id == "L7.mood.analyst_rating":
        # sentiment_score. avg_rating_score on a 1..5 scale (5 = strong_buy).
        # A-share sell-side ratings cluster near the top (mean 4.63), so an
        # absolute 3.0-neutral map gives every stock the same ~+0.81 (no signal).
        # Cross-sectional re-center on the universe consensus instead: the
        # signal measures how far ABOVE/BELOW peers a name is rated, centered
        # ~0. 5.0 → +0.80, 4.63 → 0.0, 4.5 → ≈-0.28, ≤4.0 → clip -1.0.
        avg = _num(value.get("avg_rating_score"))
        if avg is None:
            return None
        return _clip(
            (avg - _ANALYST_RATING_NEUTRAL) / _ANALYST_RATING_SCALE, -1.0, 1.0
        )

    if dp_id == "L6.state.expansion_compression":
        # valuation_rerating. EXPANDED/EXPENSIVE must be NEGATIVE.
        ratio = _num(value.get("ratio_vs_250d"))
        if ratio is not None:
            return -_clip(math.tanh((ratio - 1.0) * 2.0), -1.0, 1.0)
        regime = value.get("regime")
        if isinstance(regime, str):
            r = regime.strip().lower()
            if r == "expanded":
                return -0.5
            if r == "compressed":
                return 0.5
            return 0.0
        return None

    # NOTE on ``L6.mult.peg`` (valuation_rerating): deliberately NOT scored here.
    # The raw PEG ratio is already banded into a signed valuation_rerating score
    # by ``L6.state.peg_match`` (derive.derive_l6_state_peg_match reads
    # peg.scalar → score ∈ [-1, 1]: PEG<1 undervalued +1, 1..2 linear, >2
    # expensive -1), which DOES reach the score. Scoring raw peg again would
    # double-count the SAME PEG into valuation_rerating, so peg is left
    # data-only (its bare ``scalar`` falls through every generic shape → None).
    # peg_match is the scored form (see test_peg_match_carries_peg_signal).

    if dp_id == "L6.mult.ev_ebitda":
        # valuation_rerating. ``scalar`` is EV/EBITDA. HIGH = expensive =
        # de-rating expectation → NEGATIVE; below the reference → mildly
        # POSITIVE. Distinct multiple (NOT a re-count of PE/PB — see the
        # constants block). Log-ratio re-center so the right-skewed AI-compute
        # cohort stays separable without flooring. EBITDA-positive only (the
        # producer returns None for non-positive EBITDA), so ``scalar`` > 0.
        ev = _num(value.get("scalar"))
        if ev is None or ev <= 0:
            return None
        return -_clip(
            math.tanh(math.log(ev / _EV_EBITDA_REF) / _EV_EBITDA_SCALE),
            -1.0, 1.0,
        )

    if dp_id == "L6.mult.forward_pe":
        # valuation_rerating. ``scalar`` is forward P/E. HIGH = expensive →
        # NEGATIVE; below the reference → mildly POSITIVE. Distinct multiple
        # (forward earnings, NOT trailing PE/PB). Log-ratio re-center (same
        # rationale as ev_ebitda). The producer returns None for non-positive
        # forward EPS, so ``scalar`` > 0.
        fpe = _num(value.get("scalar"))
        if fpe is None or fpe <= 0:
            return None
        return -_clip(
            math.tanh(math.log(fpe / _FORWARD_PE_REF) / _FORWARD_PE_SCALE),
            -1.0, 1.0,
        )

    if dp_id == "L6.mult.ps":
        # valuation_rerating. ``scalar`` is price/sales (TTM). HIGH = expensive →
        # NEGATIVE; below the reference → mildly POSITIVE. Distinct multiple (NO
        # pe/pb percentile sink covers it). Log-ratio re-center (same rationale as
        # ev_ebitda / forward_pe). P/S is bounded > 0 (sales > 0), so a
        # non-positive / missing / non-numeric scalar → None (no fabricated
        # signal). See the _PS_REF / _PS_SCALE constants block.
        ps = _num(value.get("scalar"))
        if ps is None or ps <= 0:
            return None
        return -_clip(
            math.tanh(math.log(ps / _PS_REF) / _PS_SCALE),
            -1.0, 1.0,
        )

    # NOTE on ``L6.mult.mcap_fcf`` (valuation_rerating): deliberately DATA-ONLY
    # (no rule → falls through to None). Unlike P/S, mcap/FCF is NEGATIVE for ~30%
    # of the universe (67/223 in hot.sqlite, mode=ro) because trailing FCF is
    # negative — and a negative mcap/FCF is a FUNDAMENTALLY DIFFERENT state (cash
    # burn), not a "cheap" multiple, so its magnitude (e.g. -223) is meaningless as
    # cheap-vs-expensive. A log-ratio map can't take a negative argument, and
    # scoring only the positive 70% would (a) discard the negative-FCF names and
    # (b) create a perverse discontinuity (a +2894 multiple reads ≈ -1 "expensive"
    # while a -118 burner would read positive/None). The positive side is also
    # extreme-tailed (max ≈ 2894). Mapping this single-sided would MIS-RANK
    # negative-FCF names, so mcap_fcf is left data-only; P/S already supplies clean
    # new valuation evidence here. (Revisit if a sign-aware FCF-yield producer or a
    # peer percentile sink lands.)

    if dp_id == "L5.bs.leverage":
        # fundamental_score. ``leverage_ratio`` is debt/assets (e.g. 0.66).
        # Higher leverage = weaker balance sheet = NEGATIVE. 0.5 is neutral:
        # 1.0 → -0.75, 0.2 → +0.45. Missing → None.
        lev = _num(value.get("leverage_ratio"))
        if lev is None:
            return None
        return -_clip((lev - 0.5) * 1.5, -1.0, 1.0)

    if dp_id == "L5.bs.goodwill_ppe":
        # fundamental_score. ``goodwill_to_assets`` in 0..1. Higher goodwill =
        # impairment risk = weaker → NEGATIVE. 0.4 → -1.0 (strong), 0.0 → 0.
        # Missing → None.
        gw = _num(value.get("goodwill_to_assets"))
        if gw is None:
            return None
        return -_clip(gw * 2.5, -1.0, 1.0)

    if dp_id == "L5.is.gross_margin":
        # fundamental_score. ``scalar`` is the gross-margin fraction. Higher =
        # better → POSITIVE. Universe-relative re-center, with an ASYMMETRIC
        # lower tail (M-2): the negative side uses a wider scale so a
        # structurally thin (single-digit) margin reads moderately negative
        # instead of flooring at -1.0, while genuinely collapsed margins still
        # approach -1.0. 0.51 → +1.0, 0.29 → 0.0, 0.074 → ≈-0.62, ≤-0.06 → -1.0.
        gm = _num(value.get("scalar"))
        if gm is None:
            return None
        median = _resolve_gross_margin_median(ts_code)
        if median is None:  # F6-tag: FINANCIAL_DIVIDEND — GM not a meaningful signal
            return None
        delta = gm - median
        scale = _GROSS_MARGIN_SCALE if delta >= 0 else _GROSS_MARGIN_SCALE_NEG
        return _clip(delta / scale, -1.0, 1.0)

    if dp_id == "L5.is.margins":
        # fundamental_score. ``net`` is the net-margin fraction (NOT operating).
        # Higher = better → POSITIVE. Universe-relative re-center (caveat
        # applies). 0.28 → +1.0, 0.12 → 0.0, -0.04 → -1.0.
        nm = _num(value.get("net"))
        if nm is None:
            return None
        return _clip((nm - _NET_MARGIN_MEDIAN) / _NET_MARGIN_SCALE, -1.0, 1.0)

    if dp_id == "L4.eff.cycle":
        # fundamental_score. ``ccc_days`` is the cash-conversion cycle in days.
        # LOWER = better → INVERSE (negate). Universe-relative (caveat applies).
        # 136 days → -1.0 (slow cycle drags), 36 → 0.0, -64 → +1.0.
        ccc = _num(value.get("ccc_days"))
        if ccc is None:
            return None
        return -_clip((ccc - _CCC_DAYS_MEDIAN) / _CCC_DAYS_SCALE, -1.0, 1.0)

    if dp_id == "L4.eff.turnover":
        # fundamental_score. ``inventory_turnover_days`` is days inventory
        # outstanding. LOWER = better → INVERSE (negate). Universe-relative
        # (caveat applies). 216 days → -1.0, 96 → 0.0, -24 → +1.0.
        td = _num(value.get("inventory_turnover_days"))
        if td is None:
            return None
        return -_clip(
            (td - _INVENTORY_TURNOVER_DAYS_MEDIAN) / _INVENTORY_TURNOVER_DAYS_SCALE,
            -1.0,
            1.0,
        )

    if dp_id == "L4.cost.labor":
        # fundamental_score. ``labor_cost_yoy_pct`` is the yoy % change in labor
        # cost. Cost UP = bad → NEGATIVE (negate). Self-contained (tanh, no
        # universe median): +5% → ≈-0.76, 0% → 0.0, -5% → ≈+0.76.
        yoy = _num(value.get("labor_cost_yoy_pct"))
        if yoy is None:
            return None
        return -_clip(math.tanh(yoy / _LABOR_COST_YOY_SCALE), -1.0, 1.0)

    # --- R-2a: company financial-QUALITY ratios (L5.fina.*) → fundamental_score.
    # Each reads the snapshot's ``value`` field; None / non-numeric → None (no
    # node). Universe benchmark re-center (R-2; R-3 upgrades to a细分赛道
    # cross-section), de-saturated with tanh so extreme tails don't pin at ±1. ---

    if dp_id == "L5.fina.roe":
        # fundamental_score. Quarterly ROE %. Higher = better → POSITIVE.
        # tanh((v - 3.1)/2.0): 3.1 → 0.0 (median), 7.1 → ≈+0.96, -0.9 → ≈-0.96.
        v = _num(value.get("value"))
        if v is None:
            return None
        return _clip(math.tanh((v - _ROE_BENCH) / _ROE_SCALE), -1.0, 1.0)

    if dp_id == "L5.fina.roa":
        # fundamental_score. Quarterly ROA %. Higher = better → POSITIVE.
        # tanh((v - 1.8)/1.2): 1.8 → 0.0, 4.2 → ≈+0.96, -0.6 → ≈-0.96.
        v = _num(value.get("value"))
        if v is None:
            return None
        return _clip(math.tanh((v - _ROA_BENCH) / _ROA_SCALE), -1.0, 1.0)

    if dp_id == "L5.fina.debt_ratio":
        # fundamental_score. Debt/assets %. Higher leverage = WORSE → INVERSE.
        # -tanh((v - 47.0)/20.0): 47.0 → 0.0, 87.0 → ≈-0.96, 7.0 → ≈+0.96.
        v = _num(value.get("value"))
        if v is None:
            return None
        return -_clip(math.tanh((v - _DEBT_RATIO_BENCH) / _DEBT_RATIO_SCALE), -1.0, 1.0)

    if dp_id == "L5.fina.ocf_quality":
        # fundamental_score. Operating-cash-flow quality. Higher = better →
        # POSITIVE. Winsorize the extreme upper tail (raw max ≈2863) into
        # [-50, 150] FIRST, then tanh((c - 10.0)/30.0): 10.0 → 0.0, 70.0 →
        # ≈+0.96, -50.0 → ≈-0.90 (clipped tail).
        v = _num(value.get("value"))
        if v is None:
            return None
        c = _clip(v, _OCF_QUALITY_CLIP_LO, _OCF_QUALITY_CLIP_HI)
        return _clip(math.tanh((c - _OCF_QUALITY_BENCH) / _OCF_QUALITY_SCALE), -1.0, 1.0)

    if dp_id == "L5.fina.net_profit_yoy":
        # fundamental_score. Net-profit yoy % (growth). Higher = better →
        # POSITIVE. tanh((v - 20.0)/50.0): 20.0 → 0.0, 120.0 → ≈+0.96, -80.0 →
        # ≈-0.96.
        v = _num(value.get("value"))
        if v is None:
            return None
        return _clip(math.tanh((v - _NET_PROFIT_YOY_BENCH) / _NET_PROFIT_YOY_SCALE), -1.0, 1.0)

    if dp_id == "L5.fina.asset_turnover":
        # fundamental_score. Asset turnover. Higher = better → POSITIVE.
        # tanh((v - 0.13)/0.08): 0.13 → 0.0, 0.29 → ≈+0.96, -0.03 → ≈-0.96.
        v = _num(value.get("value"))
        if v is None:
            return None
        return _clip(math.tanh((v - _ASSET_TURNOVER_BENCH) / _ASSET_TURNOVER_SCALE), -1.0, 1.0)

    # --- Discount targets (sign ignored downstream; return [0, 1] magnitude) ---

    if dp_id == "L8.val.overvalued":
        # risk_discount. Higher overvaluation quantile → bigger risk. FU-1 (A):
        # the SAME PE/PB percentile (max_quantile) already drives valuation_rerating
        # via L6.state.historical_percentile / the L6.mult.* multiples, so the
        # risk-side hit is largely redundant — scale it to HALF (0.5) rather than
        # counting the valuation penalty at full weight through two channels.
        mq = _num(value.get("max_quantile"))
        if mq is None:
            return None
        return 0.5 * _clip(mq, 0.0, 1.0)

    if dp_id == "L8.val.priced_in":
        # risk_discount. priced_in_score already in 0..1.
        pis = _num(value.get("priced_in_score"))
        if pis is None:
            return None
        return _clip(pis, 0.0, 1.0)

    if dp_id in _RISK_ALERT_DP_IDS:
        # risk_discount. Producer-fired ``alert_severity`` (WARN/ERROR) drives the
        # magnitude (WARN → 0.5, ERROR → 1.0); the alert itself encodes the bad
        # direction so we emit NEGATIVE → the synthesized node reads as a "negative"
        # (risk) contributor. risk_discount takes abs(magnitude) downstream, so only
        # the magnitude is numeric. Missing / unknown severity → None (no node):
        # without the producer's classification we don't fabricate a risk. See the
        # _RISK_ALERT_DP_IDS constants block (payload shapes verified vs hot.sqlite).
        sev = value.get("alert_severity")
        if not isinstance(sev, str):
            return None
        magnitude = _RISK_ALERT_SEVERITY_MAGNITUDE.get(sev.strip().upper())
        if magnitude is None:
            return None
        return -magnitude

    if dp_id == "L6.priced.run_up":
        # priced_in_discount. d20_pct is a DECIMAL ratio (0.0245 = +2.45%).
        d20 = _num(value.get("d20_pct"))
        if d20 is None:
            d20 = _num(value.get("d5_pct"))
        if d20 is None:
            return None
        # R-3a de-common-mode: with a cross-sectional reference, penalize only a
        # run-up ABOVE the universe median (de-beta the market's broad move) —
        # bad-tail only, so the median stock gets ZERO discount instead of the
        # ~0.44 absolute common-mode that depressed every name. Without a
        # reference (peer_context absent / dp_id missing), fall back to the
        # original absolute 20%-saturating magnitude (bit-for-bit back-compat).
        pop = peer_context.get(dp_id) if peer_context else None
        if pop:
            return _xs_bad_tail(d20, pop)
        # Only a run-UP counts; a decline → 0. 20% run-up saturates.
        return _clip(max(d20, 0.0) / 0.20, 0.0, 1.0)

    if dp_id == "L6.priced.crowdedness":
        # priced_in_discount. The producer fires an own-history turnover
        # percentile (high = unusually heavily traded = crowded). Routed here it
        # would otherwise flow through the generic percentile path → inverted →
        # abs()'d downstream, which penalizes UNCROWDED (low-percentile) names
        # just as hard (a sign bug specific to the abs on a signed percentile)
        # AND adds a universe common-mode (most A-shares sit at elevated turnover
        # vs their own norm). R-3a: with a cross-sectional reference, rank the
        # crowding figure across the universe and penalize only the bad tail
        # (more crowded than peers), floored at 0 — uncrowded names get no
        # spurious discount and the median stock gets zero. Emit a NEGATIVE
        # magnitude to preserve the existing "negative" direction label (the
        # priced_in rollup abs()'s it regardless). Without a reference, return
        # None so the original generic percentile path still handles it (back-
        # compat).
        pop = peer_context.get(dp_id) if peer_context else None
        if not pop:
            return None
        raw = _peer_raw_value(dp_id, value)
        mag = _xs_bad_tail(raw, pop)
        return None if mag is None else -mag

    if dp_id == "L6.priced.news_age":
        # priced_in_discount (magnitude; sign ignored downstream). The producer
        # already computes a time-decayed ``magnitude`` ∈ [0, _NEWS_AGE_PEAK]
        # (fresh catalyst → larger discount, ~30d half-life). Surface it as the
        # magnitude. Prefer ``magnitude``; fall back to ``scalar`` (same value).
        mag = _num(value.get("magnitude"))
        if mag is None:
            mag = _num(value.get("scalar"))
        if mag is None:
            return None
        return _clip(mag, 0.0, 1.0)

    return None


def _realtime_signal(dp_id: str, value: Any, score_target: str | None, ts_code: str | None = None, peer_context: Mapping[str, Sequence[float]] | None = None) -> float | None:
    """Reduce a realtime value payload to a *signed* signal in [-1, 1].

    Only shapes whose sign is unambiguous are mapped; everything else returns
    ``None`` so the caller skips that dp_id rather than inventing a direction.

    Resolution order (first match wins):

    0. Per-dp_id rules for the 8 governance realtime fields (see
       ``_realtime_field_signal``) — bespoke payloads (net_revision_score,
       ratio_vs_250d, max_quantile, d20_pct, …) whose direction/magnitude the
       generic fallbacks below can't read.
    1. dict ``score`` / ``intensity`` / ``strength`` — a derived sub-score that
       is already normalized and signed; passthrough clipped to [-1, 1].
    2. dict with any ``*_percentile`` key — take the max percentile (0..1),
       map to ``(pct - 0.5) * 2``; invert for valuation/risk targets where a
       high percentile means "expensive / crowded".
    3. dict ``yoy_pct`` — ``tanh(yoy / 50)``.
    4. dict with exactly one curated signed-percent field (see
       ``_REALTIME_SIGNED_PCT_FIELDS``) — ``tanh(x / K)``, optional sign flip.
    5. top-level numeric already in [-1, 1] — passthrough.
    6. anything else — ``None``.
    """

    # 0. Per-dp_id field rules take precedence — these payloads carry bespoke
    # keys (not score/percentile/yoy) so they'd otherwise fall through to None.
    if isinstance(value, dict):
        field_signal = _realtime_field_signal(dp_id, value, score_target, ts_code, peer_context)
        if field_signal is not None:
            return field_signal
        # R-3a: when a cross-sectional reference governs this dp_id, the field
        # rule is AUTHORITATIVE — a None means "no signal vs peers" (at/below the
        # cross-sectional median → skip the node), NOT "fall through to the
        # legacy absolute / generic-percentile path". Without this guard a
        # below-median crowdedness would re-acquire its old abs'd percentile
        # discount via path #2 and the de-common-mode would be undone.
        if peer_context and dp_id in _PEER_CONTEXT_FIELDS and dp_id in peer_context:
            return None

    # 5 (handled early for the non-dict case): bare numeric in [-1, 1].
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        x = float(value)
        if -1.0 <= x <= 1.0:
            return x
        return None

    if not isinstance(value, dict):
        return None

    # 1. Explicit signed sub-score.
    for key in ("score", "intensity", "strength"):
        if value.get(key) is not None:
            try:
                return _clip(float(value[key]), -1.0, 1.0)
            except (TypeError, ValueError):
                return None

    # 2. Percentile shapes → signed, inverted for valuation/risk targets.
    # Accept the bare ``percentile`` key in addition to the ``*_percentile``
    # suffix: ``L6.priced.crowdedness`` (priced_in_discount, an INVERTED target)
    # emits its crowding rank under a bare ``percentile`` key, so the suffix-only
    # match dropped every high-crowding name (percentile ≈ 0.97 → ZERO discount).
    # Scoped to the exact key ``"percentile"`` so we don't over-match unrelated
    # numeric fields that merely contain the substring.
    pct_values = [
        value[k]
        for k in value
        if isinstance(k, str)
        and (k == "percentile" or k.endswith("_percentile"))
        and isinstance(value[k], (int, float))
        and not isinstance(value[k], bool)
    ]
    if pct_values:
        pct = max(float(p) for p in pct_values)
        signal = (pct - 0.5) * 2.0
        if score_target in _REALTIME_INVERTED_TARGETS:
            signal = -signal
        return _clip(signal, -1.0, 1.0)

    # 3. yoy_pct via tanh.
    yoy = value.get("yoy_pct")
    if yoy is not None:
        try:
            return _clip(math.tanh(float(yoy) / 50.0), -1.0, 1.0)
        except (TypeError, ValueError):
            return None

    # 4. Curated single signed-percent fields.
    for field, (divisor, flip) in _REALTIME_SIGNED_PCT_FIELDS.items():
        raw = value.get(field)
        if raw is None:
            continue
        try:
            signal = math.tanh(float(raw) / divisor)
        except (TypeError, ValueError):
            return None
        if flip:
            signal = -signal
        return _clip(signal, -1.0, 1.0)

    return None


def _realtime_entry_signals(
    dp_id: str,
    realtime_snapshot: Mapping[str, Mapping[str, Any]],
    role_registry: FieldGovernanceRegistry,
    *,
    existing_dp_ids: set[str] | frozenset[str],
) -> bool:
    """True iff ``dp_id``'s snapshot entry would itself be synthesized into a
    scoring node — i.e. it passes every gate in ``synthesize_realtime_nodes``
    (present + participating + Known/Proxy + non-mock + ``_realtime_signal`` not
    None) and isn't already authored in the overlay. Used to decide whether a
    dedup *primary* is strong enough to suppress its *secondary*."""

    entry = realtime_snapshot.get(dp_id)
    if not isinstance(entry, Mapping):
        return False
    if dp_id in existing_dp_ids:
        return False
    rule = role_registry.get(dp_id)
    if rule is None or not rule.participates_in_score:
        return False
    if str(entry.get("data_status") or "") not in ("Known", "Proxy"):
        return False
    if str(entry.get("source") or "").startswith("mock:"):
        return False
    return _realtime_signal(dp_id, entry.get("value"), rule.score_target) is not None


def synthesize_realtime_nodes(
    realtime_snapshot: Mapping[str, Mapping[str, Any]],
    role_registry: FieldGovernanceRegistry | None,
    *,
    existing_dp_ids: set[str] | frozenset[str],
    ts_code: str | None,
    peer_context: Mapping[str, Sequence[float]] | None = None,
) -> list[dict]:
    """Turn participating realtime snapshot entries into overlay-leaf nodes.

    For each ``(dp_id, entry)`` where ALL of the following hold, emit one
    standalone-leaf node dict (``parent_node=None``):

    - governance ``participates_in_score`` is True,
    - ``entry["data_status"]`` is ``Known`` or ``Proxy``,
    - the source does NOT start with ``"mock:"``,
    - ``dp_id`` is not already authored in the overlay (``existing_dp_ids``),
    - ``_realtime_signal`` maps the value to a signed signal (else skip),
    - ``dp_id`` is not a dedup *secondary* whose *primary* (see
      ``_REALTIME_DEDUP_PRIMARY``) is itself a scoring entry in this snapshot.

    The emitted node carries ``value={"score": abs(signal)}`` plus a
    ``direction`` so the sign survives ``_leaf_score``'s ``direction ×
    _to_scalar`` product. ``synthetic_realtime`` flags the origin for audit.

    Freshness gate (C-3): dp_ids in ``_FRESHNESS_GATED_DP_IDS`` (the price-run-up
    / priced-in path) have their magnitude scaled by ``_freshness_weight`` —
    their ``updated_at`` vs the snapshot's freshest ``updated_at`` — so a stale
    run_up row can't drive a full priced-in penalty off an already-reversed move.
    """

    if role_registry is None:
        return []

    # Reference freshness = the freshest ``updated_at`` across the whole snapshot
    # (the most robust asof signal available at this layer — individual run_up
    # payloads carry no observation date). Used by the C-3 freshness gate below.
    ref_updated_at = None
    for _e in realtime_snapshot.values():
        if isinstance(_e, Mapping):
            _u = _num(_e.get("updated_at"))
            if _u is not None and (ref_updated_at is None or _u > ref_updated_at):
                ref_updated_at = _u

    out: list[dict] = []
    for dp_id, entry in realtime_snapshot.items():
        if not isinstance(entry, Mapping):
            continue
        if dp_id in existing_dp_ids:
            continue

        # Same-disclosure dedup: skip this secondary field when its primary is
        # present AND passes every synthesis gate (so it will emit its own
        # node). A mock / Unknown / non-participating / None-signal primary does
        # NOT suppress — the secondary is kept as the fallback.
        primary_dp = _REALTIME_DEDUP_PRIMARY.get(dp_id)
        if primary_dp is not None and _realtime_entry_signals(
            primary_dp, realtime_snapshot, role_registry,
            existing_dp_ids=existing_dp_ids,
        ):
            continue

        rule = role_registry.get(dp_id)
        if rule is None or not rule.participates_in_score:
            continue

        status = str(entry.get("data_status") or "")
        if status not in ("Known", "Proxy"):
            continue

        source = str(entry.get("source") or "")
        if source.startswith("mock:"):
            continue

        signal = _realtime_signal(dp_id, entry.get("value"), rule.score_target, ts_code=ts_code, peer_context=peer_context)
        if signal is None:
            continue

        # C-3 freshness gate: down-weight a stale price-run-up / priced-in row so
        # a snapshot frozen weeks behind the live price can't drive a full
        # priced-in penalty off an already-reversed move. Scoped to
        # ``_FRESHNESS_GATED_DP_IDS`` so no other field's behaviour changes.
        if dp_id in _FRESHNESS_GATED_DP_IDS:
            signal *= _freshness_weight(entry.get("updated_at"), ref_updated_at)

        confidence = entry.get("confidence")
        try:
            confidence = float(confidence) if confidence is not None else 0.5
        except (TypeError, ValueError):
            confidence = 0.5

        # ``confidence_multiplier`` nodes are consumed via their confidence /
        # data_coverage (scoring._confidence_multiplier_from_flat), NOT via a
        # directional score. Emitting a signed magnitude for them is inert for
        # the multiplier yet would pollute the top-path explanation ranking, so
        # zero the directional signal while keeping the node (and its
        # confidence) in the set.
        if rule.score_target == "confidence_multiplier":
            node_value: dict = {"score": 0.0}
            node_direction = "neutral"
        else:
            node_value = {"score": abs(signal)}
            node_direction = "positive" if signal >= 0 else "negative"

        out.append({
            "node_id": f"{ts_code}:{dp_id}:rt",
            "dp_id": dp_id,
            "node_name": dp_id,
            "parent_node": None,
            "value": node_value,
            "direction": node_direction,
            "data_status": "Known",
            "confidence": confidence,
            "last_updated": entry.get("updated_at") or entry.get("last_updated"),
            "synthetic_realtime": True,
        })
    return out


# ---------------------------------------------------------------------------
# Leaf-node intrinsic score
# ---------------------------------------------------------------------------


def _leaf_score(node: dict) -> dict:
    """Compute a leaf node's own (direction × strength × confidence × recency)
    intrinsic score, plus the three-horizon mix."""

    status = _node_status(node)
    direction = _direction_sign(node.get("direction"))
    confidence = node.get("confidence")
    confidence = float(confidence) if confidence is not None else 0.5
    base_confidence = confidence
    recency = _recency(node.get("last_updated"))
    score_enabled = _node_score_enabled(node)
    confidence_penalty = float(node.get("confidence_penalty") or 1.0)
    missing_balance = "known"

    if not score_enabled:
        intrinsic = 0.0
        missing_balance = "non_scoring_role"
    elif status == "Inactive":
        # No current event → score 0, but confidence preserved for caller
        intrinsic = 0.0
        missing_balance = "inactive"
    elif status == "N/A":
        intrinsic = 0.0
        missing_balance = "not_applicable_remove"
    elif status == "Unknown":
        # No data → contribute 0 magnitude but lower confidence externally.
        intrinsic = 0.0
        confidence = min(confidence, 0.3)
        missing_balance = "unknown_zero_score"
    elif status == "Unavailable":
        # Cost/permission/engineering unavailable: keep the formula position
        # using a neutral value, then lower confidence according to governance.
        neutral_value = float(node.get("neutral_value") or 0.0)
        if _is_multiplier_node(node):
            # Multiplier neutral is a factor of 1.0, which maps to a score
            # signal of 0.0 because scoring later converts signal → 1+signal.
            intrinsic = _clip(neutral_value - 1.0) * recency
        else:
            intrinsic = direction * abs(neutral_value) * recency
        confidence *= confidence_penalty
        missing_balance = "neutral_with_penalty"
    elif status == "Proxy":
        magnitude = _to_scalar(node.get("value"), node)
        intrinsic = direction * magnitude * recency
        confidence *= confidence_penalty
        missing_balance = "proxy"
    else:
        # Known or Optionality (current_contribution part) — magnitude from
        # value payload.
        magnitude = _to_scalar(node.get("value"), node)
        intrinsic = direction * magnitude * recency

    # Optionality nodes contribute an additional long-horizon term from
    # ``future_option_value`` (spec §23.5).
    future_option = 0.0
    if status == "Optionality" and isinstance(node.get("value"), dict):
        fov = node["value"].get("future_option_value")
        if isinstance(fov, (int, float)):
            future_option = direction * abs(_clip(float(fov))) * recency

    sw, mw, lw = _classify_horizon(node.get("dp_id"), node.get("node_name"))
    return {
        "score": intrinsic,
        "short_score": intrinsic * sw,
        "medium_score": intrinsic * mw,
        # Optionality's expected upside lives in the long bucket only.
        "long_score": intrinsic * lw + future_option,
        "confidence": confidence,
        "base_confidence": base_confidence,
        "status": status,
        "score_enabled": score_enabled,
        "missing_balance": missing_balance,
        "confidence_penalty": confidence_penalty,
        "proxy_used": node.get("proxy_used"),
        # Carry the realtime-bridge origin flag through aggregation so scoring's
        # _industry_variables_from_flat can route dead-sink synthetic nodes
        # (fundamental_score / optionality_score) into industry_contrib.
        "synthetic_realtime": node.get("synthetic_realtime"),
        **_governance_payload(node),
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _effective_weight(node: dict) -> float:
    """base_weight × active_weight × materiality, falling back to 1.0 when
    components are missing."""

    base = node.get("base_weight")
    active = node.get("active_weight")
    materiality = node.get("materiality")
    b = float(base) if base is not None else 1.0
    a = float(active) if active is not None else 1.0
    m = float(materiality) if materiality is not None else 1.0
    return b * a * m


def _aggregate_parent(parent: dict, child_results: list[dict]) -> dict:
    """Aggregate a parent's children using the spec §27 formula.

    ``child_results`` items each carry: status, weight (raw, pre-renorm),
    score (intrinsic), short_score, medium_score, long_score, confidence,
    direction_sign, recency.

    Returns the parent's score dict (same shape as ``_leaf_score`` plus
    the children counters).
    """

    # Counters
    n_active = 0
    n_inactive = 0
    n_na = 0
    n_unknown = 0
    n_optionality = 0
    n_unavailable = 0
    n_proxy = 0
    n_non_scoring = 0

    # Pools for renormalization. N/A drops out entirely; Inactive contributes
    # a 0 score (and is excluded from the *denominator* per spec §23.1 since
    # spec treats inactive as "active_weight=0" rather than "value=0").
    applicable: list[dict] = []  # used both for weighted sum + data-coverage
    usable_weight = 0.0         # for data_coverage numerator
    total_weight = 0.0          # for data_coverage denominator (applicable)
    missing_penalty_weight = 0.0
    penalty_weight = 0.0

    for c in child_results:
        if not c.get("score_enabled", True):
            n_non_scoring += 1
            continue
        st = c["status"]
        if st == "N/A":
            n_na += 1
            continue
        if st == "Inactive":
            n_inactive += 1
            # Inactive nodes carry base_weight in spec but active_weight=0,
            # so effective_weight should already be ~0 and they contribute
            # nothing to either numerator or denominator. Skip cleanly.
            continue
        if st == "Unknown":
            n_unknown += 1
            # Counts towards total_weight (it's *applicable*, just missing
            # data) but not known_weight.
            total_weight += c["weight"]
            applicable.append(c)
            continue
        if st == "Unavailable":
            n_unavailable += 1
        elif st == "Proxy":
            n_proxy += 1
        if st == "Optionality":
            n_optionality += 1
        else:
            n_active += 1
        usable_weight += c["weight"]
        total_weight += c["weight"]
        missing_penalty_weight += c["weight"] * float(c.get("confidence_penalty") or 1.0)
        penalty_weight += c["weight"]
        applicable.append(c)

    # Renormalize: if the applicable pool has positive weight, each child's
    # share is weight / total_weight. Otherwise parent reports 0 score.
    if total_weight <= 0 or not applicable:
        parent_intrinsic = 0.0
        parent_short = 0.0
        parent_medium = 0.0
        parent_long = 0.0
    else:
        parent_intrinsic = sum(
            c["score"] * (c["weight"] / total_weight) * c["confidence"]
            for c in applicable
        )
        parent_short = sum(
            c["short_score"] * (c["weight"] / total_weight) * c["confidence"]
            for c in applicable
        )
        parent_medium = sum(
            c["medium_score"] * (c["weight"] / total_weight) * c["confidence"]
            for c in applicable
        )
        parent_long = sum(
            c["long_score"] * (c["weight"] / total_weight) * c["confidence"]
            for c in applicable
        )

    # Apply Risk Discount / Priced-in Discount (currently zero — leave hooks
    # for future modules; spec §27 explicitly subtracts these).
    risk_discount = 0.0
    priced_in_discount = 0.0
    parent_intrinsic -= risk_discount + priced_in_discount
    parent_short -= risk_discount + priced_in_discount
    parent_medium -= risk_discount + priced_in_discount
    parent_long -= risk_discount + priced_in_discount

    # Parent's own confidence (spec §23.2):
    # Parent Confidence = mean(child confidence) × Data Coverage × evidence
    # quality. We approximate evidence_quality as 1.0 (the per-node field
    # is sparsely populated in current overlays) so it doesn't suppress
    # everything; future modules can lift this.
    base_conf = (
        sum(c.get("base_confidence", c["confidence"]) for c in applicable) / len(applicable)
        if applicable else parent.get("confidence") or 0.5
    )
    data_coverage = (usable_weight / total_weight) if total_weight > 0 else 0.0
    missing_penalty = (
        (missing_penalty_weight / penalty_weight)
        if penalty_weight > 0 else 1.0
    )
    evidence_quality = _factor(parent.get("evidence_quality"), 1.0)
    parent_confidence = base_conf * data_coverage * evidence_quality * missing_penalty
    min_required_coverage = float(parent.get("min_required_coverage") or 0.5)
    warning_level = "low_confidence" if data_coverage < min_required_coverage else "normal"

    return {
        "score": parent_intrinsic,
        "short_score": parent_short,
        "medium_score": parent_medium,
        "long_score": parent_long,
        "confidence": parent_confidence,
        "data_coverage": data_coverage,
        "missing_penalty": missing_penalty,
        "evidence_quality": evidence_quality,
        "min_required_coverage": min_required_coverage,
        "warning_level": warning_level,
        "n_children_active": n_active + n_optionality,
        "n_children_inactive": n_inactive,
        "n_children_na": n_na,
        "n_children_unknown": n_unknown,
        "n_children_unavailable": n_unavailable,
        "n_children_proxy": n_proxy,
        "n_children_non_scoring": n_non_scoring,
        # Pre-discount audit hooks (so future modules can subtract on top of
        # the same intermediate values without re-running aggregation):
        "risk_discount": risk_discount,
        "priced_in_discount": priced_in_discount,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def aggregate_company_graph(
    stock_overlay: dict,
    industry_overlay: dict | None = None,
    role_registry: FieldGovernanceRegistry | None = None,
    *,
    realtime_snapshot: dict | None = None,
    peer_context: Mapping[str, Sequence[float]] | None = None,
) -> dict[str, dict]:
    """Compute parent-node scores + three-horizon mix for every node in a
    stock overlay. Returns ``{node_id: {...}}``.

    ``industry_overlay`` is accepted for symmetry / future use (e.g. inherit
    industry-level ``value`` payloads when ``inherit_from_industry: true``);
    current implementation reads inheritance directly from the stock overlay
    if the value is null and ``inherit_from_industry`` is true.

    ``realtime_snapshot`` (the ``mvp20.storage.read_hot_snapshot`` shape:
    ``{dp_id: {value, data_status, confidence, source, ...}}``) is the bridge
    from minute-level realtime data into the score. When provided, every
    participating, non-mock, unmapped (vs. authored overlay) entry whose value
    shape is unambiguous is synthesized into a standalone leaf node (see
    ``synthesize_realtime_nodes``) and folded into the same aggregation. When
    ``None`` (default), behaviour is identical to before — pure back-compat.
    """

    # Synthetic realtime nodes need governance (score_target / participates_in
    # _score) to reach the score. Authored overlay nodes already carry those
    # fields baked in, so callers historically pass no registry. When a
    # realtime_snapshot is supplied without one, load the default governance so
    # the synthetic leaves can be classified. Authored nodes are unaffected
    # (apply_to_node only fills missing fields).
    if realtime_snapshot and role_registry is None:
        role_registry = load_default_governance(strict=False)

    nodes_list = stock_overlay.get("nodes") or []
    nodes_by_id: dict[str, dict] = {}
    for n in nodes_list:
        nid = n.get("node_id")
        if not nid:
            continue
        node = dict(n)  # shallow copy so we can patch inherited values
        if role_registry is not None:
            node = role_registry.apply_to_node(node)
        nodes_by_id[nid] = node

    # Bridge realtime snapshot values into synthetic standalone-leaf nodes.
    # Dedupe against the authored overlay's dp_ids so a value is never counted
    # twice. Synthetic nodes get the same governance enrichment as authored
    # ones, then flow through the existing post-order aggregation unchanged.
    if realtime_snapshot:
        existing_dp_ids = {
            n.get("dp_id") for n in nodes_by_id.values() if n.get("dp_id")
        }
        synthetic = synthesize_realtime_nodes(
            realtime_snapshot,
            role_registry,
            existing_dp_ids=existing_dp_ids,
            ts_code=stock_overlay.get("ts_code"),
            peer_context=peer_context,
        )
        for node in synthetic:
            if role_registry is not None:
                node = role_registry.apply_to_node(node)
            nid = node.get("node_id")
            if nid and nid not in nodes_by_id:
                nodes_by_id[nid] = node

    if not nodes_by_id:
        return {}

    # Optional industry-overlay inheritance for value / confidence /
    # last_updated when ``inherit_from_industry`` is true and the stock
    # overlay's value is null. Industry-overlay nodes are keyed by dp_id.
    industry_by_dp: dict[str, dict] = {}
    if industry_overlay:
        for n in industry_overlay.get("nodes") or []:
            dp = n.get("dp_id")
            if dp:
                industry_by_dp[dp] = n
    if industry_by_dp:
        for nid, n in nodes_by_id.items():
            if n.get("inherit_from_industry") and (n.get("value") in (None, {})):
                src = industry_by_dp.get(n.get("dp_id"))
                if not src:
                    continue
                # Patch in industry value / confidence / last_updated.
                if n.get("value") in (None, {}):
                    n["value"] = src.get("value")
                if n.get("confidence") is None:
                    n["confidence"] = src.get("confidence")
                if not n.get("last_updated"):
                    n["last_updated"] = src.get("last_updated")
                # Promote status when industry knows the value but the stock
                # overlay still reads Unknown.
                if _node_status(n) == "Unknown" and src.get("value") is not None:
                    n["data_status"] = "Known"

    _apply_proxy_candidates(nodes_by_id)

    # Build parent → children adjacency.
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for nid, n in nodes_by_id.items():
        parent_id = n.get("parent_node")
        if parent_id and parent_id in nodes_by_id:
            children_by_parent[parent_id].append(nid)

    # Topological order — leaves first via reverse BFS from each root.
    # A node's depth = max(child depth) + 1. We compute via post-order.
    order: list[str] = []
    visited: set[str] = set()

    def _post_order(nid: str) -> None:
        if nid in visited:
            return
        visited.add(nid)
        for child_id in children_by_parent.get(nid, []):
            _post_order(child_id)
        order.append(nid)

    # Walk from every node so disconnected pieces still land in order.
    for nid in nodes_by_id:
        _post_order(nid)

    # Compute leaf intrinsics first, then aggregate up the tree.
    results: dict[str, dict] = {}
    # Cache the "as-child contribution" payload separately so a parent can
    # collect them without re-deriving direction / weight at aggregation time.
    child_payload: dict[str, dict] = {}

    for nid in order:
        node = nodes_by_id[nid]
        kids = children_by_parent.get(nid, [])
        if kids:
            # Parent — aggregate over children
            child_results = []
            for cid in kids:
                if cid not in child_payload:
                    # Defensive: child not yet computed (shouldn't happen
                    # given post-order). Skip to avoid recursion bombs.
                    continue
                child_results.append(child_payload[cid])
            agg = _aggregate_parent(node, child_results)
            agg.update(_governance_payload(node))
            agg["score_enabled"] = _node_score_enabled(node)
            results[nid] = agg
            # When this parent itself is a child of an even higher parent,
            # build the as-child payload from the aggregate.
            weight = _effective_weight(node)
            status = _node_status(node)
            # A parent inherits status logic from its children. If all
            # children are N/A → treat parent as N/A as well; if all
            # Inactive → Inactive.
            if agg["n_children_active"] + agg["n_children_unknown"] == 0:
                if agg["n_children_na"] > 0 and agg["n_children_inactive"] == 0:
                    status = "N/A"
                elif agg["n_children_inactive"] > 0:
                    status = "Inactive"
            child_payload[nid] = {
                "status": status,
                "weight": weight,
                "score": agg["score"],
                "short_score": agg["short_score"],
                "medium_score": agg["medium_score"],
                "long_score": agg["long_score"],
                "confidence": agg["confidence"] or 0.5,
                "base_confidence": float(node.get("confidence") or 0.5),
                "score_enabled": agg.get("score_enabled", True),
                "confidence_penalty": float(node.get("confidence_penalty") or 1.0),
            }
        else:
            # Leaf
            leaf = _leaf_score(node)
            weight = _effective_weight(node)
            # Stand-alone leaves also get reported in the result map so the
            # caller can inspect single-node scores.
            results[nid] = {
                "score": leaf["score"],
                "short_score": leaf["short_score"],
                "medium_score": leaf["medium_score"],
                "long_score": leaf["long_score"],
                "confidence": leaf["confidence"],
                "data_coverage": 1.0 if leaf["status"] in ("Known", "Proxy", "Unavailable", "Optionality") else (
                    0.0 if leaf["status"] in ("Unknown", "N/A") else 1.0
                ),
                "missing_penalty": leaf["confidence_penalty"],
                "evidence_quality": _factor(node.get("evidence_quality"), 1.0),
                "min_required_coverage": leaf["min_required_coverage"],
                "warning_level": (
                    "low_confidence"
                    if leaf["status"] == "Unknown" and leaf["min_required_coverage"] > 0
                    else "normal"
                ),
                "n_children_active": 0,
                "n_children_inactive": 0,
                "n_children_na": 0,
                "n_children_unknown": 0,
                "n_children_unavailable": 0,
                "n_children_proxy": 0,
                "n_children_non_scoring": 0,
                "risk_discount": 0.0,
                "priced_in_discount": 0.0,
                # Copy the node's dp_id into the standalone-leaf result so
                # synthetic realtime nodes carry it through to scoring for
                # later per-field calibration (was dropped → None before).
                "dp_id": node.get("dp_id"),
                "field_role": leaf.get("field_role"),
                "score_target": leaf.get("score_target"),
                "participates_in_score": leaf.get("participates_in_score"),
                "fallback_policy": leaf.get("fallback_policy"),
                "proxy_candidates": leaf.get("proxy_candidates"),
                "neutral_value": leaf.get("neutral_value"),
                "confidence_penalty": leaf.get("confidence_penalty"),
                "score_enabled": leaf.get("score_enabled"),
                "missing_balance": leaf.get("missing_balance"),
                "proxy_used": leaf.get("proxy_used"),
                "synthetic_realtime": leaf.get("synthetic_realtime"),
            }
            child_payload[nid] = {
                "status": leaf["status"],
                "weight": weight,
                "score": leaf["score"],
                "short_score": leaf["short_score"],
                "medium_score": leaf["medium_score"],
                "long_score": leaf["long_score"],
                "confidence": leaf["confidence"],
                "base_confidence": leaf["base_confidence"],
                "score_enabled": leaf["score_enabled"],
                "confidence_penalty": leaf["confidence_penalty"],
            }

    return results


# ---------------------------------------------------------------------------
# Convenience: load + aggregate from filesystem paths
# ---------------------------------------------------------------------------


def aggregate_from_paths(
    stock_overlay_path,
    industry_overlay_path=None,
) -> dict[str, dict]:
    """Helper used by the CLI. Reads YAML from disk and dispatches to
    ``aggregate_company_graph``."""

    import yaml  # local import — keeps test imports cheap

    def _load(p) -> dict:
        from pathlib import Path
        path = Path(p)
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    stock = _load(stock_overlay_path)
    industry = _load(industry_overlay_path) if industry_overlay_path else None
    return aggregate_company_graph(stock, industry, role_registry=load_default_governance(strict=False))


__all__ = [
    "aggregate_company_graph",
    "aggregate_from_paths",
    "synthesize_realtime_nodes",
    "build_peer_context",
    # Exposed helpers for tests / downstream tooling:
    "_to_scalar",
    "_classify_horizon",
    "_recency",
    "_realtime_signal",
    "_xs_percentile",
    "_xs_bad_tail",
]
