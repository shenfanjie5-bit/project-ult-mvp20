"""A-share 5 trading-day relative signal artifact.

This module is the request-path half of the "today key signals" feature.  It
mirrors ``mvp20.quant_score``: research/export scripts freeze calibration
parameters, an offline builder writes a per-symbol artifact, and the BFF only
does cheap lookup + honesty flags.

Contract:
* A-share only.
* Target is P(5d return beats the same-day liquid-universe median), not
  absolute P(up).
* ``validated`` is false outside the liquid gate, on stale artifacts, or when
  feature coverage is insufficient.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from mvp20 import quant_score


REPO_ROOT = Path(__file__).resolve().parent.parent
PARAMS_PATH = REPO_ROOT / "config" / "signal_5d_params.json"
ARTIFACT_DIR = REPO_ROOT / "runtime" / "signal_5d"
STALE_AFTER_DAYS = 10
MIN_FEATURE_COV = 0.5

TARGET_LABEL = "P(5d beat same-day liquid median)"
TARGET_DISPLAY = "5日跑赢同日流动性股票中位数概率"

_params_cache: dict[str, tuple[int, dict[str, Any]]] = {}
_artifact_cache: dict[str, tuple[int, dict[str, Any]]] = {}

_FEATURE_LABELS = {
    "ivol_60": "低特质波动",
    "ep_ttm": "估值收益率",
    "strev": "短期反转",
    "max5": "彩票型冲高约束",
    "turnover_20": "换手拥挤约束",
    "rvol_20": "低波动",
    "mom_6_1": "中期动量",
}

LOGISTIC_METHOD = "logistic_multifeature_7f"
FALLBACK_METHOD = "score_pct_linear_bin10"


def load_params(path: Path | None = None) -> dict[str, Any] | None:
    p = Path(path or PARAMS_PATH)
    if not p.exists():
        return None
    key = str(p)
    mtime = p.stat().st_mtime_ns
    hit = _params_cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    data = json.loads(p.read_text(encoding="utf-8"))
    _params_cache[key] = (mtime, data)
    return data


def artifact_path(market: str = "A_share", root: Path | None = None) -> Path:
    return Path(root or ARTIFACT_DIR) / f"{market}.json"


def load_artifact(market: str = "A_share", root: Path | None = None) -> dict[str, Any] | None:
    p = artifact_path(market, root)
    if not p.exists():
        return None
    key = str(p)
    mtime = p.stat().st_mtime_ns
    hit = _artifact_cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    data = json.loads(p.read_text(encoding="utf-8"))
    _artifact_cache[key] = (mtime, data)
    return data


def is_stale(artifact: Mapping[str, Any], today: str | None = None) -> bool:
    asof = str(artifact.get("asof") or "")
    if len(asof) != 8:
        return True
    today = today or datetime.now().strftime("%Y%m%d")
    try:
        d0 = datetime.strptime(asof, "%Y%m%d")
        d1 = datetime.strptime(today, "%Y%m%d")
    except ValueError:
        return True
    return (d1 - d0).days > STALE_AFTER_DAYS


def _feature_label(feature: str) -> str:
    return _FEATURE_LABELS.get(feature, feature)


def direction_from_probability(probability: float, base_rate: float) -> str:
    tilt_pp = 100.0 * (probability - base_rate)
    if tilt_pp >= 1.5:
        return "上涨"
    if tilt_pp <= -1.5:
        return "下跌"
    return "震荡"


def strength_from_probability(probability: float, base_rate: float) -> str:
    tilt_pp = abs(100.0 * (probability - base_rate))
    if tilt_pp >= 3.5:
        return "强"
    if tilt_pp >= 1.0:
        return "中"
    return "弱"


def grade_from_probability(probability: float, base_rate: float) -> str:
    tilt_pp = 100.0 * (probability - base_rate)
    if tilt_pp >= 4.0:
        return "S"
    if tilt_pp >= 2.5:
        return "A"
    if tilt_pp >= 1.0:
        return "B"
    if tilt_pp >= -1.0:
        return "C"
    return "D"


def isotonic_non_decreasing(
    values: Sequence[float],
    weights: Sequence[float] | None = None,
) -> list[float]:
    """Weighted PAVA smoothing for score-bin probabilities.

    The signal score is ordinal: higher bins should not emit a lower calibrated
    P(beat median).  This only smooths the calibration layer; it does not change
    the cross-sectional score or any realized backtest label.
    """
    if not values:
        return []
    xs = [float(v) for v in values]
    ws = [1.0] * len(xs) if weights is None else [max(float(w), 1e-12) for w in weights]
    blocks: list[dict[str, float | int]] = []
    for i, (x, w) in enumerate(zip(xs, ws, strict=True)):
        blocks.append({"start": i, "end": i, "sum_w": w, "sum_xw": x * w})
        while len(blocks) >= 2:
            left = blocks[-2]
            right = blocks[-1]
            left_mean = float(left["sum_xw"]) / float(left["sum_w"])
            right_mean = float(right["sum_xw"]) / float(right["sum_w"])
            if left_mean <= right_mean:
                break
            merged = {
                "start": int(left["start"]),
                "end": int(right["end"]),
                "sum_w": float(left["sum_w"]) + float(right["sum_w"]),
                "sum_xw": float(left["sum_xw"]) + float(right["sum_xw"]),
            }
            blocks[-2:] = [merged]
    out = [0.0] * len(xs)
    for block in blocks:
        mean = float(block["sum_xw"]) / float(block["sum_w"])
        for i in range(int(block["start"]), int(block["end"]) + 1):
            out[i] = mean
    return out


def apply_isotonic_p_up(bin_stats: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return bin stats with monotone ``p_up`` and preserved ``p_up_raw``."""
    values = [float(s["p_up"]) for s in bin_stats]
    weights = [float(s.get("n", 1.0)) for s in bin_stats]
    smooth = isotonic_non_decreasing(values, weights)
    out: list[dict[str, Any]] = []
    for stat, p_smooth in zip(bin_stats, smooth, strict=True):
        row = dict(stat)
        row.setdefault("p_up_raw", float(row["p_up"]))
        row["p_up"] = float(p_smooth)
        out.append(row)
    return out


def _bin_of(score: "Any", eligible: "Any", k: int) -> "Any":
    return quant_score._bin_of(score, eligible, k)  # tested parity in quant_score


def _weights(params: Mapping[str, Any]) -> dict[str, float]:
    method = str(params.get("method") or "ew_signed")
    if method == "ew_signed":
        return {str(k): float(v) for k, v in (params.get("signs") or {}).items()}
    if method == "ic_weighted":
        return {str(k): float(v) for k, v in (params.get("weights") or {}).items()}
    raise ValueError(f"unsupported signal_5d method: {method}")


def sigmoid(value: float) -> float:
    x = max(-30.0, min(30.0, float(value)))
    return 1.0 / (1.0 + math.exp(-x))


def fit_ridge_logistic(
    X: "Any",
    y: "Any",
    l2: float = 0.2,
    max_iter: int = 35,
) -> list[float]:
    """Small numpy-only ridge logistic fitter used by export/backtest.

    Returns ``[intercept, beta_1, ...]``. Callers own PIT train/test slicing;
    this helper is intentionally stateless.
    """
    import numpy as np

    Xd = np.column_stack([np.ones(X.shape[0]), X.astype(float)])
    yy = y.astype(float)
    beta = np.zeros(Xd.shape[1], dtype=float)
    reg = np.eye(Xd.shape[1], dtype=float) * float(l2)
    reg[0, 0] = 0.0
    for _ in range(max_iter):
        eta = np.clip(Xd @ beta, -30.0, 30.0)
        p = 1.0 / (1.0 + np.exp(-eta))
        w = np.clip(p * (1.0 - p), 1e-5, None)
        grad = Xd.T @ (p - yy) + reg @ beta
        hess = (Xd.T * w) @ Xd + reg
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(hess, grad, rcond=None)[0]
        beta -= step
        if float(np.max(np.abs(step))) < 1e-5:
            break
    return [float(x) for x in beta]


def standardize_matrix(
    X: "Any",
    means: Sequence[float],
    stds: Sequence[float],
) -> "Any":
    import numpy as np

    mu = np.array([float(x) for x in means], dtype=float)
    sd = np.array([float(x) if float(x) > 1e-8 else 1.0 for x in stds], dtype=float)
    out = (X.astype(float) - mu) / sd
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)


def predict_ridge_logistic(
    X: "Any",
    model: Mapping[str, Any],
) -> "Any":
    import numpy as np

    beta = np.array([float(x) for x in model.get("coefficients", [])], dtype=float)
    intercept = float(model.get("intercept", beta[0] if beta.size else 0.0))
    if beta.size == X.shape[1] + 1:
        intercept = float(beta[0])
        beta = beta[1:]
    if beta.size != X.shape[1]:
        raise ValueError(
            f"logistic coefficient count {beta.size} does not match features {X.shape[1]}"
        )
    Xs = standardize_matrix(
        X,
        model.get("feature_means") or [0.0] * X.shape[1],
        model.get("feature_stds") or [1.0] * X.shape[1],
    )
    eta = np.clip(intercept + Xs @ beta, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-eta))


def _legacy_calibration(params: Mapping[str, Any]) -> Mapping[str, Any]:
    legacy = params.get("legacy_bin_calibration")
    return legacy if isinstance(legacy, Mapping) else params


def _score_percentiles(score: "Any", eligible: "Any") -> "Any":
    import numpy as np

    out = np.full(score.shape, np.nan, dtype=float)
    ok = np.isfinite(score) & eligible
    if int(ok.sum()) > 10:
        ranks = np.argsort(np.argsort(score[ok]))
        out[ok] = 100.0 * ranks / max(int(ok.sum()) - 1, 1)
    return out


def _composite_score(
    z_all: "Any",
    name_idx: Mapping[str, int],
    features: Sequence[str],
    weights: Mapping[str, float],
    min_cov: float,
) -> tuple["Any", "Any"]:
    import numpy as np

    idx = [name_idx[f] for f in features]
    z = z_all[:, idx]
    cov = np.isfinite(z).mean(axis=1)
    xi = np.where(np.isfinite(z), z, 0.0)
    w = np.array([float(weights[f]) for f in features], dtype=float)
    score = xi @ w
    score[cov < min_cov] = np.nan
    return score, cov


def _legacy_probability_arrays(
    score: "Any",
    eligible: "Any",
    params: Mapping[str, Any],
) -> tuple["Any", "Any", "Any", "Any", "Any"]:
    import numpy as np

    k = int(params.get("k_bins") or 10)
    bins = _bin_of(score, eligible, k)
    score_pct = _score_percentiles(score, eligible)
    base_rate = float(params["base_rate"])
    tilt_shrink = float(params.get("tilt_shrink", 1.0))
    bin_stats = list(params["bins"])
    legacy_bin = np.full(score.shape, np.nan, dtype=float)
    raw_bin = np.full(score.shape, np.nan, dtype=float)
    for bi in range(k):
        sel = bins == bi
        if not sel.any():
            continue
        p_bin = float(bin_stats[bi]["p_up"])
        raw_bin[sel] = float(bin_stats[bi].get("p_up_raw", p_bin))
        legacy_bin[sel] = base_rate + tilt_shrink * (p_bin - base_rate)

    centers = (np.arange(k, dtype=float) + 0.5) * (100.0 / k)
    p_by_center = np.array([
        base_rate + tilt_shrink * (float(stat["p_up"]) - base_rate)
        for stat in bin_stats
    ], dtype=float)
    fallback = np.interp(score_pct, centers, p_by_center, left=p_by_center[0], right=p_by_center[-1])
    fallback[~np.isfinite(score_pct)] = np.nan
    return legacy_bin, raw_bin, fallback, bins, score_pct


def _model_primary_enabled(params: Mapping[str, Any]) -> bool:
    model = params.get("model")
    if not isinstance(model, Mapping):
        return False
    if model.get("primary_enabled") is False:
        return False
    validation = model.get("validation") or {}
    gates = validation.get("gates") if isinstance(validation, Mapping) else None
    if isinstance(gates, Mapping) and gates:
        return all(bool(v) for v in gates.values())
    return True


def _logistic_feature_arrays(
    z_all: "Any",
    name_idx: Mapping[str, int],
    params: Mapping[str, Any],
) -> tuple["Any", "Any"] | None:
    import numpy as np

    if str(params.get("method") or "") != LOGISTIC_METHOD:
        return None
    model = params.get("model")
    if not isinstance(model, Mapping):
        return None
    features = [str(f) for f in params.get("features") or []]
    idx = [name_idx[f] for f in features]
    X = z_all[:, idx]
    cov = np.isfinite(X).mean(axis=1)
    p = predict_ridge_logistic(X, model)
    return p, cov


def _logistic_contributions(
    z_row: "Any",
    features: Sequence[str],
    model: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    import numpy as np

    Xs = standardize_matrix(
        np.array([z_row], dtype=float),
        model.get("feature_means") or [0.0] * len(features),
        model.get("feature_stds") or [1.0] * len(features),
    )[0]
    coeffs = list(model.get("coefficients") or [])
    if len(coeffs) == len(features) + 1:
        coeffs = coeffs[1:]
    rows = []
    for feature, value, coef in zip(features, Xs, coeffs, strict=True):
        contribution = float(value) * float(coef)
        rows.append({
            "factor_id": feature,
            "factor_label": _feature_label(feature),
            "contribution": round(contribution, 3),
            "source_node_id": f"signal_5d.{feature}",
        })
    rows.sort(key=lambda r: abs(float(r["contribution"])), reverse=True)
    return [r for r in rows if r["contribution"] > 0][:5], [r for r in rows if r["contribution"] < 0][:5]


def _feature_contributions(
    z_row: "Any",
    features: Sequence[str],
    weights: Mapping[str, float],
    base_norm: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    import numpy as np

    rows: list[dict[str, Any]] = []
    for i, feature in enumerate(features):
        v = float(z_row[i]) if np.isfinite(z_row[i]) else 0.0
        signed = v * float(weights[feature])
        contribution = signed / base_norm if base_norm > 0 else signed
        rows.append({
            "factor_id": feature,
            "factor_label": _feature_label(feature),
            "contribution": round(float(contribution), 3),
            "source_node_id": f"signal_5d.{feature}",
        })
    rows.sort(key=lambda r: abs(float(r["contribution"])), reverse=True)
    drivers = [r for r in rows if float(r["contribution"]) > 0][:5]
    risks = [r for r in rows if float(r["contribution"]) < 0][:5]
    return drivers, risks


def build_rows(
    codes: Sequence[str],
    feat: "Any",
    feat_names: Sequence[str],
    lnmv: "Any",
    industry: "Any",
    params: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Score one current A-share cross-section through frozen 5d params."""
    import numpy as np

    method = str(params.get("method") or "ew_signed")
    legacy_params = _legacy_calibration(params)
    k = int(legacy_params.get("k_bins") or params.get("k_bins") or 10)
    liquid_frac = float(params.get("liquid_frac") or 0.7)
    min_cov = float(params.get("min_feature_coverage") or MIN_FEATURE_COV)
    legacy_features = [str(f) for f in legacy_params["features"]]
    legacy_weights = _weights(legacy_params)
    model_features = [str(f) for f in params.get("features") or legacy_features]
    all_features = list(dict.fromkeys([*legacy_features, *model_features]))
    name_idx = {f: i for i, f in enumerate(feat_names)}
    missing = [f for f in all_features if f not in name_idx]
    if missing:
        raise ValueError(f"signal_5d feature(s) missing from builder output: {missing}")
    for f in legacy_features:
        if f not in legacy_weights:
            raise ValueError(f"signal_5d legacy weight/sign missing for feature: {f}")

    z_all = quant_score.neutralize_cross_section(feat, lnmv, industry)
    legacy_score, legacy_cov = _composite_score(
        z_all, name_idx, legacy_features, legacy_weights, min_cov,
    )

    ok_mv = np.isfinite(lnmv)
    eligible = np.zeros(len(codes), bool)
    if ok_mv.sum() >= 50:
        threshold = np.percentile(lnmv[ok_mv], 100 * (1 - liquid_frac))
        eligible = ok_mv & (lnmv >= threshold)

    legacy_bin_probability, raw_bin_probability, fallback_probability, bins, score_pct = (
        _legacy_probability_arrays(legacy_score, eligible, legacy_params)
    )
    base_rate = float(legacy_params["base_rate"])
    target = str(params.get("target") or TARGET_LABEL)
    horizon = int(params.get("horizon_days") or 5)
    base_norm = math.sqrt(max(len(legacy_features), 1))

    model_probability = np.full(len(codes), np.nan, dtype=float)
    model_cov = np.full(len(codes), np.nan, dtype=float)
    model_enabled = method == LOGISTIC_METHOD
    model_primary = model_enabled and _model_primary_enabled(params)
    model = params.get("model") if isinstance(params.get("model"), Mapping) else {}
    model_arrays = _logistic_feature_arrays(z_all, name_idx, params)
    if model_arrays is not None:
        model_probability, model_cov = model_arrays
    probability_source = LOGISTIC_METHOD if model_primary else FALLBACK_METHOD
    probability_semantics = (
        "P(5d return beats same-day liquid-universe median); not absolute P(up)"
    )

    rows: dict[str, dict[str, Any]] = {}
    for j, ts in enumerate(codes):
        feature_coverage = (
            float(model_cov[j]) if model_enabled and np.isfinite(model_cov[j])
            else float(legacy_cov[j]) if np.isfinite(legacy_cov[j])
            else None
        )
        if not bool(ok_mv[j]):
            rows[ts] = {
                "available": False,
                "validated": False,
                "reason": "missing market-cap feature; cannot apply liquid gate",
                "model_method": method,
                "probability_semantics": probability_semantics,
                "probability_source": probability_source,
                "feature_coverage": feature_coverage,
            }
            continue
        if not bool(eligible[j]):
            rows[ts] = {
                "available": True,
                "validated": False,
                "reason": "outside liquid top-%d%% gate (5d signal unvalidated there)"
                          % round(liquid_frac * 100),
                "model_method": method,
                "probability_semantics": probability_semantics,
                "probability_source": probability_source,
                "feature_coverage": feature_coverage,
            }
            continue
        if int(bins[j]) < 0 or not np.isfinite(legacy_score[j]) or feature_coverage is None or feature_coverage < min_cov:
            rows[ts] = {
                "available": True,
                "validated": False,
                "reason": "insufficient feature coverage",
                "model_method": method,
                "probability_semantics": probability_semantics,
                "probability_source": probability_source,
                "feature_coverage": feature_coverage,
            }
            continue

        fallback_p = float(fallback_probability[j])
        legacy_bin_p = float(legacy_bin_probability[j])
        raw_p = float(raw_bin_probability[j])
        model_p = float(model_probability[j]) if np.isfinite(model_probability[j]) else None
        if model_primary and model_p is not None:
            probability = model_p
        else:
            probability = fallback_p if np.isfinite(fallback_p) else legacy_bin_p

        if model_enabled:
            model_idx = [name_idx[f] for f in model_features]
            drivers, risks = _logistic_contributions(z_all[j, model_idx], model_features, model)
        else:
            legacy_idx = [name_idx[f] for f in legacy_features]
            drivers, risks = _feature_contributions(
                z_all[j, legacy_idx], legacy_features, legacy_weights, base_norm,
            )

        rows[ts] = {
            "available": True,
            "validated": True,
            "reason": "validated",
            "market": "A_share",
            "horizon_days": horizon,
            "target": target,
            "target_display": TARGET_DISPLAY,
            "target_kind": params.get("target_kind") or "relative_cross_section_median",
            "model_method": method,
            "probability_semantics": probability_semantics,
            "probability_source": probability_source,
            "feature_coverage": round(float(feature_coverage), 3),
            "probability": round(probability, 4),
            "p_beat_median": round(probability, 4),
            "model_probability": round(model_p, 4) if model_p is not None else None,
            "model_probability_shadow": (
                round(model_p, 4)
                if model_enabled and not model_primary and model_p is not None
                else None
            ),
            "legacy_bin_probability": round(legacy_bin_p, 4),
            "fallback_probability": round(fallback_p, 4) if np.isfinite(fallback_p) else None,
            "raw_bin_probability": round(raw_p, 4),
            "base_rate": round(base_rate, 4),
            "tilt_pp": round(100.0 * (probability - base_rate), 2),
            "direction": direction_from_probability(probability, base_rate),
            "signal_strength": strength_from_probability(probability, base_rate),
            "signal_grade": grade_from_probability(probability, base_rate),
            "score_pct": round(float(score_pct[j]), 2) if np.isfinite(score_pct[j]) else None,
            "score": round(float(legacy_score[j]), 4),
            "bin": int(bins[j]),
            "drivers": drivers,
            "risks": risks,
        }
    return rows


def build_artifact(
    asof: str,
    codes: Sequence[str],
    feat: "Any",
    feat_names: Sequence[str],
    lnmv: "Any",
    industry: "Any",
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    params = params or load_params()
    if params is None:
        raise RuntimeError(f"frozen signal_5d params missing: {PARAMS_PATH}")
    rows = build_rows(codes, feat, feat_names, lnmv, industry, params)
    n_valid = sum(1 for r in rows.values() if r.get("validated"))
    n_available = sum(1 for r in rows.values() if r.get("available"))
    return {
        "market": "A_share",
        "asof": asof,
        "built_at": int(time.time()),
        "source": "DockCase daily/daily_basic + factor_research panel calibration",
        "params_version": params.get("version"),
        "params_built_at": params.get("built_at"),
        "params_git_sha": params.get("git_sha"),
        "model_method": params.get("method"),
        "probability_source": (
            LOGISTIC_METHOD
            if str(params.get("method") or "") == LOGISTIC_METHOD and _model_primary_enabled(params)
            else FALLBACK_METHOD
        ),
        "probability_semantics": (
            "P(5d return beats same-day liquid-universe median); not absolute P(up)"
        ),
        "horizon_days": int(params.get("horizon_days") or 5),
        "target": params.get("target") or TARGET_LABEL,
        "target_display": TARGET_DISPLAY,
        "n_rows": len(rows),
        "n_available": n_available,
        "n_validated": n_valid,
        "coverage": {
            "row_count": len(rows),
            "available_count": n_available,
            "validated_count": n_valid,
            "validated_ratio": round(n_valid / len(rows), 4) if rows else 0.0,
            "liquid_frac": params.get("liquid_frac"),
            "min_feature_coverage": params.get("min_feature_coverage"),
        },
        "calibration": params.get("calibration") or {},
        "model": {
            "type": (params.get("model") or {}).get("type") if isinstance(params.get("model"), Mapping) else None,
            "primary_enabled": _model_primary_enabled(params),
            "validation": (params.get("model") or {}).get("validation") if isinstance(params.get("model"), Mapping) else None,
            "fallback_method": FALLBACK_METHOD,
        },
        "caveats": params.get("caveats") or [],
        "rows": rows,
    }


def save_artifact(
    artifact: Mapping[str, Any],
    market: str = "A_share",
    root: Path | None = None,
) -> Path:
    p = artifact_path(market, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
    return p


def lookup(
    ts_code: str,
    market: str = "A_share",
    root: Path | None = None,
    today: str | None = None,
) -> dict[str, Any]:
    try:
        artifact = load_artifact(market, root)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"signal_5d artifact unreadable: {exc}"}
    if not artifact:
        return {
            "available": False,
            "reason": "signal_5d artifact not built (scripts/build_signal_5d.py)",
        }
    row = (artifact.get("rows") or {}).get(ts_code)
    if row is None:
        return {
            "available": False,
            "asof": artifact.get("asof"),
            "horizon_days": artifact.get("horizon_days", 5),
            "target": artifact.get("target") or TARGET_LABEL,
            "target_display": artifact.get("target_display") or TARGET_DISPLAY,
            "reason": "ts_code not in signal_5d scored cross-section",
        }
    out = json.loads(json.dumps(row))
    out["asof"] = artifact.get("asof")
    out["horizon_days"] = artifact.get("horizon_days", out.get("horizon_days", 5))
    out["target"] = artifact.get("target") or out.get("target") or TARGET_LABEL
    out["target_display"] = artifact.get("target_display") or out.get("target_display") or TARGET_DISPLAY
    path = artifact_path(market, root)
    if root is None:
        try:
            out["source_artifact"] = str(path.relative_to(REPO_ROOT))
        except ValueError:
            out["source_artifact"] = str(path)
    else:
        out["source_artifact"] = str(path)
    out["params_version"] = artifact.get("params_version")
    out["params_built_at"] = artifact.get("params_built_at")
    out["model_method"] = out.get("model_method") or artifact.get("model_method")
    out["probability_source"] = out.get("probability_source") or artifact.get("probability_source")
    out["probability_semantics"] = (
        out.get("probability_semantics") or artifact.get("probability_semantics")
    )
    out["stale"] = is_stale(artifact, today)
    if out["stale"]:
        out["validated"] = False
        out["reason"] = f"artifact asof {artifact.get('asof')} older than {STALE_AFTER_DAYS}d"
    out["caveats"] = list(artifact.get("caveats") or [])
    return out
