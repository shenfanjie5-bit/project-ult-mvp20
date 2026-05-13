"""Market adapter layer for CN_A / US / HK scoring adjustments.

The adapter consumes already-routed role components from ``scoring``. It does
not re-run the graph formula or mutate overlay nodes; it only applies local
market multipliers, local additive scores, and local discounts around the core
final score.
"""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
from typing import Any, Mapping

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MARKET_ADAPTER_PATH = ROOT_DIR / "config/market_adapters.yaml"
HORIZON_KEYS = ("short_total", "medium_total", "long_total", "base_score")
HORIZON_KEY_MAP = {
    "short_total": "short",
    "medium_total": "mid",
    "long_total": "long",
}
FACTOR_NAMES = (
    "microstructure",
    "participant",
    "liquidity",
    "theme",
    "policy",
    "derivatives_shorting",
    "crossborder_fx",
    "market_regime",
)
BETA_KEYS = {
    "microstructure": ("microstructure_beta",),
    "participant": ("participant_beta", "retail_beta", "institutional_beta"),
    "liquidity": ("liquidity_beta",),
    "theme": ("theme_beta",),
    "policy": ("policy_beta",),
    "derivatives_shorting": (
        "derivatives_shorting_beta",
        "derivatives_beta",
        "shorting_beta",
    ),
    "crossborder_fx": (
        "crossborder_beta",
        "crossborder_fx_beta",
        "northbound_beta",
        "southbound_beta",
    ),
    "market_regime": ("market_regime_beta", "valuation_beta"),
}


def infer_market_code(stock_overlay: Mapping[str, Any] | None, ts_code: str | None = None) -> str:
    overlay = stock_overlay or {}
    adapter = overlay.get("market_adapter") or {}
    if not isinstance(adapter, Mapping):
        adapter = {}
    explicit = overlay.get("market_code") or adapter.get("market_code")
    if explicit:
        return _normalize_market_code(str(explicit))
    ticker = str(ts_code or overlay.get("ts_code") or overlay.get("ticker") or "")
    if ticker.endswith((".SZ", ".SH", ".BJ")):
        return "CN_A"
    if ticker.endswith(".HK"):
        return "HK"
    return "US"


def load_market_adapter_config(
    path: Path = DEFAULT_MARKET_ADAPTER_PATH,
) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def apply_market_adapter(
    *,
    final_score: Mapping[str, Any],
    role_components: Mapping[str, float] | None,
    stock_overlay: Mapping[str, Any] | None,
    ts_code: str | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = dict(config or load_market_adapter_config())
    market_code = infer_market_code(stock_overlay, ts_code)
    market_rules = ((cfg.get("market_rules") or {}).get(market_code) or {})
    if not isinstance(market_rules, Mapping):
        market_rules = {}
    bounds = cfg.get("multiplier_bounds") or {}
    min_multiplier = _optional_float(bounds.get("min"), 0.2)
    max_multiplier = _optional_float(bounds.get("max"), None)
    components = dict(role_components or {})
    factors = _factor_names(cfg)
    base_horizon = _normalize_horizon(str(cfg.get("base_horizon") or "mid"))

    target_map = market_rules.get("target_map") or {}
    stock_betas = _stock_local_betas(stock_overlay, cfg, factors)
    raw_factor_signals = {}
    factor_scores = {}
    adjusted_factor_scores = {}
    for name in factors:
        raw_signal = _target_signal(components, _factor_targets(target_map, name))
        factor_score = _normalize_factor_score(raw_signal, cfg)
        raw_factor_signals[name] = raw_signal
        factor_scores[name] = factor_score
        adjusted_factor_scores[name] = factor_score * stock_betas.get(name, 1.0)

    horizon_multipliers = {}
    weighted_sums = {}
    for horizon in ("short", "mid", "long"):
        weights = _factor_weights(cfg, market_rules, market_code, horizon, factors)
        weighted_sum = sum(
            _coerce_float(weights.get(name), 0.0) * adjusted_factor_scores.get(name, 0.0)
            for name in factors
        )
        weighted_sums[horizon] = weighted_sum
        horizon_multipliers[horizon] = _bound_multiplier(
            math.exp(_horizon_kappa(market_rules, horizon) * weighted_sum),
            min_multiplier,
            max_multiplier,
        )

    base_weights = _factor_weights(cfg, market_rules, market_code, base_horizon, factors)
    base_kappa = _horizon_kappa(market_rules, base_horizon)
    multipliers = {
        name: _bound_multiplier(
            math.exp(
                base_kappa
                * _coerce_float(base_weights.get(name), 0.0)
                * adjusted_factor_scores.get(name, 0.0)
            ),
            min_multiplier,
            max_multiplier,
        )
        for name in factors
    }
    market_multiplier = horizon_multipliers.get(base_horizon, 1.0)

    local_scores = {
        name: _target_signal(components, targets)
        for name, targets in (market_rules.get("local_scores") or {}).items()
    }
    discounts = {
        name: abs(_target_signal(components, targets))
        for name, targets in (market_rules.get("discounts") or {}).items()
    }
    local_score_total = sum(local_scores.values())
    local_discount_total = sum(discounts.values())

    adjusted = deepcopy(dict(final_score))
    for key in HORIZON_KEYS:
        base_value = _coerce_float(final_score.get(key), 0.0)
        horizon = HORIZON_KEY_MAP.get(key, base_horizon)
        multiplier = horizon_multipliers.get(horizon, market_multiplier)
        adjusted[key] = base_value * multiplier + local_score_total - local_discount_total
    adjusted["components"] = dict(adjusted.get("components") or {})
    adjusted["components"].update({
        "market_adapter_multiplier": market_multiplier,
        "market_adapter_multiplier_short": horizon_multipliers.get("short", 1.0),
        "market_adapter_multiplier_mid": horizon_multipliers.get("mid", 1.0),
        "market_adapter_multiplier_long": horizon_multipliers.get("long", 1.0),
        "market_factor_weighted_sum_short": weighted_sums.get("short", 0.0),
        "market_factor_weighted_sum_mid": weighted_sums.get("mid", 0.0),
        "market_factor_weighted_sum_long": weighted_sums.get("long", 0.0),
        "market_local_scores": local_score_total,
        "market_local_discounts": local_discount_total,
    })

    return {
        "market_code": market_code,
        "listing_board": _listing_board(stock_overlay),
        "multiplier": market_multiplier,
        "horizon_multipliers": horizon_multipliers,
        "multipliers": multipliers,
        "raw_factor_signals": raw_factor_signals,
        "factor_scores": factor_scores,
        "adjusted_factor_scores": adjusted_factor_scores,
        "stock_betas": stock_betas,
        "weighted_sums": weighted_sums,
        "local_scores": local_scores,
        "discounts": discounts,
        "adjusted_final_score": adjusted,
        "source_notes": list(market_rules.get("source_notes") or []),
    }


def _factor_names(cfg: Mapping[str, Any]) -> tuple[str, ...]:
    configured = cfg.get("factors") or FACTOR_NAMES
    out: list[str] = []
    for raw in configured:
        name = _canonical_factor_name(str(raw))
        if name not in out:
            out.append(name)
    return tuple(out or FACTOR_NAMES)


def _canonical_factor_name(name: str) -> str:
    if name == "connect_fx":
        return "crossborder_fx"
    return name


def _factor_targets(target_map: Mapping[str, Any], factor: str) -> list[str]:
    targets = target_map.get(factor)
    if targets is None and factor == "crossborder_fx":
        targets = target_map.get("connect_fx")
    if targets is None:
        return []
    return [str(target) for target in targets]


def _factor_weights(
    cfg: Mapping[str, Any],
    market_rules: Mapping[str, Any],
    market_code: str,
    horizon: str,
    factors: tuple[str, ...],
) -> dict[str, float]:
    by_horizon = market_rules.get("factor_weights") or {}
    weights = by_horizon.get(horizon)
    if isinstance(weights, Mapping):
        return {
            _canonical_factor_name(str(name)): _coerce_float(value, 0.0)
            for name, value in weights.items()
        }

    # Backward-compatible fallback for the old single-weight config.
    legacy = _component_weights(cfg, market_code)
    return {name: _coerce_float(legacy.get(name), 0.0) for name in factors}


def _component_weights(cfg: Mapping[str, Any], market_code: str) -> Mapping[str, Any]:
    weights = cfg.get("component_weights") or {}
    base = dict(weights.get("default") or {})
    base.update(weights.get(market_code) or {})
    if "connect_fx" in base and "crossborder_fx" not in base:
        base["crossborder_fx"] = base["connect_fx"]
    return base


def _horizon_kappa(market_rules: Mapping[str, Any], horizon: str) -> float:
    kappa = market_rules.get("kappa") or {}
    if isinstance(kappa, Mapping):
        return _coerce_float(kappa.get(horizon), 1.0)
    return _coerce_float(kappa, 1.0)


def _normalize_horizon(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"short", "s"}:
        return "short"
    if normalized in {"medium", "mid", "m"}:
        return "mid"
    if normalized in {"long", "l"}:
        return "long"
    return "mid"


def _normalize_factor_score(raw_signal: float, cfg: Mapping[str, Any]) -> float:
    lo, hi = _factor_range(cfg)
    method = str(cfg.get("factor_score_method") or "tanh").lower()
    if method == "clip":
        score = raw_signal
    else:
        scale = max(_coerce_float(cfg.get("factor_score_scale"), 2.0), 1e-9)
        score = math.tanh(raw_signal / scale)
    return _clip(score, lo, hi)


def _factor_range(cfg: Mapping[str, Any]) -> tuple[float, float]:
    raw = cfg.get("factor_range") or [-1.0, 1.0]
    if not isinstance(raw, list | tuple) or len(raw) != 2:
        return (-1.0, 1.0)
    lo = _coerce_float(raw[0], -1.0)
    hi = _coerce_float(raw[1], 1.0)
    if lo > hi:
        return (hi, lo)
    return (lo, hi)


def _stock_local_betas(
    stock_overlay: Mapping[str, Any] | None,
    cfg: Mapping[str, Any],
    factors: tuple[str, ...],
) -> dict[str, float]:
    overlay = stock_overlay or {}
    adapter = overlay.get("market_adapter") or {}
    if not isinstance(adapter, Mapping):
        adapter = {}
    profile = (
        overlay.get("stock_local_profile")
        or adapter.get("stock_local_profile")
        or overlay.get("local_profile")
        or {}
    )
    if not isinstance(profile, Mapping):
        profile = {}
    beta_bounds = cfg.get("stock_beta_bounds") or {}
    min_beta = _coerce_float(beta_bounds.get("min"), 0.0)
    max_beta = _coerce_float(beta_bounds.get("max"), 2.0)
    out = {}
    for factor in factors:
        out[factor] = _clip(
            _profile_beta(profile, overlay, BETA_KEYS.get(factor, (f"{factor}_beta",))),
            min_beta,
            max_beta,
        )
    return out


def _profile_beta(
    profile: Mapping[str, Any],
    overlay: Mapping[str, Any],
    keys: tuple[str, ...],
) -> float:
    values = []
    for key in keys:
        if key in profile:
            values.append(_coerce_float(profile.get(key), 1.0))
        elif key in overlay:
            values.append(_coerce_float(overlay.get(key), 1.0))
    if not values:
        return 1.0
    return sum(values) / len(values)


def _target_signal(components: Mapping[str, float], targets: list[str]) -> float:
    total = 0.0
    for target in targets:
        if target in components:
            total += _component_signal(target, components[target])
    return total


def _component_signal(target: str, value: Any) -> float:
    f = _coerce_float(value, 0.0)
    if target.endswith("_multiplier") or target in {"multiplier_stack"}:
        return f - 1.0
    return f


def _listing_board(stock_overlay: Mapping[str, Any] | None) -> str | None:
    overlay = stock_overlay or {}
    adapter = overlay.get("market_adapter") or {}
    if not isinstance(adapter, Mapping):
        adapter = {}
    value = overlay.get("listing_board") or adapter.get("listing_board")
    return str(value) if value else None


def _normalize_market_code(value: str) -> str:
    normalized = value.strip().upper()
    if normalized in {"A", "A_SHARE", "CN", "CHINA_A", "CN_A"}:
        return "CN_A"
    if normalized in {"HK", "HKG", "HONG_KONG"}:
        return "HK"
    return "US"


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _bound_multiplier(
    value: float,
    min_multiplier: float | None,
    max_multiplier: float | None,
) -> float:
    if min_multiplier is not None:
        value = max(min_multiplier, value)
    if max_multiplier is not None:
        value = min(max_multiplier, value)
    return value


__all__ = [
    "apply_market_adapter",
    "infer_market_code",
    "load_market_adapter_config",
]
