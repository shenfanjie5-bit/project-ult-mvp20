"""A-share absolute 5 trading-day upside probability artifact.

This module is intentionally parallel to ``mvp20.signal_5d`` and does not
change the existing relative signal contract.

Contract:
* A-share only.
* Target is absolute ``P(close[t+5] / close[t] - 1 > 0)``.
* ``validated`` is true only when the frozen walk-forward gates pass, the row
  is inside the liquid gate, feature coverage is sufficient, and the artifact
  is not stale.
* The request path only does lookup and frozen-model inference output already
  materialized by ``scripts/build_signal_up_5d.py``.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from mvp20 import signal_5d


REPO_ROOT = Path(__file__).resolve().parent.parent
PARAMS_PATH = REPO_ROOT / "config" / "signal_up_5d_params.json"
ARTIFACT_DIR = REPO_ROOT / "runtime" / "signal_up_5d"
STALE_AFTER_DAYS = 10
MIN_FEATURE_COV = 0.5

TARGET_LABEL = "P(5d return > 0)"
TARGET_DISPLAY = "5日上涨概率"
TARGET_KIND = "absolute_up_5d"
PROBABILITY_SEMANTICS = "P(5d return > 0); absolute, not relative"
MODEL_METHOD = "ridge_logistic_absolute_5d"
FALLBACK_METHOD = "train_base_rate_unvalidated"
BASELINE_METHOD = "score_pct_logistic_shadow"

MODEL_FEATURES = [
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "ret_60d",
    "mom_6_1",
    "rsi_14",
    "vol_20d",
    "ivol_60",
    "max5",
    "turnover_20",
    "rvol_20",
    "drawdown_20",
    "market_ret_5d",
    "market_ret_20d",
    "industry_ret_5d",
    "industry_ret_20d",
]

_FEATURE_LABELS = {
    "ret_1d": "1日收益",
    "ret_5d": "5日收益",
    "ret_20d": "20日收益",
    "ret_60d": "60日收益",
    "mom_6_1": "中期动量",
    "rsi_14": "14日RSI",
    "vol_20d": "20日波动",
    "ivol_60": "60日特质波动",
    "max5": "彩票型冲高",
    "turnover_20": "20日换手",
    "rvol_20": "20日实现波动",
    "drawdown_20": "20日回撤",
    "market_ret_5d": "市场5日收益",
    "market_ret_20d": "市场20日收益",
    "industry_ret_5d": "行业5日收益",
    "industry_ret_20d": "行业20日收益",
}

_params_cache: dict[str, tuple[int, dict[str, Any]]] = {}
_artifact_cache: dict[str, tuple[int, dict[str, Any]]] = {}


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


def _clip_probability(p: float) -> float:
    return max(0.0001, min(0.9999, float(p)))


def _feature_label(feature: str) -> str:
    return _FEATURE_LABELS.get(feature, feature)


def direction_from_probability(probability: float) -> str:
    if probability >= 0.53:
        return "上涨"
    if probability <= 0.47:
        return "下跌"
    return "震荡"


def strength_from_probability(probability: float) -> str:
    tilt_pp = abs(100.0 * (probability - 0.5))
    if tilt_pp >= 7.0:
        return "强"
    if tilt_pp >= 3.0:
        return "中"
    return "弱"


def grade_from_probability(probability: float) -> str:
    if probability >= 0.60:
        return "S"
    if probability >= 0.56:
        return "A"
    if probability >= 0.52:
        return "B"
    if probability >= 0.48:
        return "C"
    return "D"


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


def _liquid_eligible(lnmv: "Any", liquid_frac: float) -> "Any":
    import numpy as np

    ok_mv = np.isfinite(lnmv)
    eligible = np.zeros(len(lnmv), bool)
    if ok_mv.sum() >= 50:
        threshold = np.percentile(lnmv[ok_mv], 100 * (1 - liquid_frac))
        eligible = ok_mv & (lnmv >= threshold)
    return eligible


def _predict_model(X: "Any", model: Mapping[str, Any]) -> "Any":
    return signal_5d.predict_ridge_logistic(X, model)


def _logistic_contributions(
    z_row: "Any",
    features: Sequence[str],
    model: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    import numpy as np

    Xs = signal_5d.standardize_matrix(
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
            "source_node_id": f"signal_up_5d.{feature}",
        })
    rows.sort(key=lambda r: abs(float(r["contribution"])), reverse=True)
    return [r for r in rows if r["contribution"] > 0][:5], [r for r in rows if r["contribution"] < 0][:5]


def build_rows(
    codes: Sequence[str],
    feat: "Any",
    feat_names: Sequence[str],
    lnmv: "Any",
    industry: "Any",
    params: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Score one current A-share cross-section through frozen up-5d params."""
    import numpy as np

    del industry  # reserved for future per-industry serving diagnostics
    method = str(params.get("method") or MODEL_METHOD)
    liquid_frac = float(params.get("liquid_frac") or 0.70)
    min_cov = float(params.get("min_feature_coverage") or MIN_FEATURE_COV)
    model = params.get("model") if isinstance(params.get("model"), Mapping) else {}
    model_features = [str(f) for f in params.get("features") or MODEL_FEATURES]
    name_idx = {f: i for i, f in enumerate(feat_names)}
    missing = [f for f in model_features if f not in name_idx]
    if missing:
        raise ValueError(f"signal_up_5d feature(s) missing from builder output: {missing}")

    X = feat[:, [name_idx[f] for f in model_features]].astype(float)
    feature_cov = np.isfinite(X).mean(axis=1)
    model_probability = _predict_model(X, model) if model else np.full(len(codes), np.nan)
    fallback_probability = float(
        (params.get("fallback") or {}).get("probability")
        if isinstance(params.get("fallback"), Mapping)
        else params.get("base_rate", 0.5)
    )
    baseline_probability = np.full(len(codes), fallback_probability, dtype=float)
    baseline = params.get("baseline")
    if isinstance(baseline, Mapping) and isinstance(baseline.get("model"), Mapping):
        baseline_features = [str(f) for f in baseline.get("features") or model_features]
        if all(f in name_idx for f in baseline_features):
            Xb = feat[:, [name_idx[f] for f in baseline_features]].astype(float)
            baseline_probability = _predict_model(Xb, baseline["model"])

    ok_mv = np.isfinite(lnmv)
    eligible = _liquid_eligible(lnmv, liquid_frac)
    model_primary = method == MODEL_METHOD and _model_primary_enabled(params)
    probability_source = MODEL_METHOD if model_primary else FALLBACK_METHOD
    caveats = list(params.get("caveats") or [])
    rows: dict[str, dict[str, Any]] = {}

    for j, ts in enumerate(codes):
        cov = float(feature_cov[j]) if np.isfinite(feature_cov[j]) else None
        model_p = float(model_probability[j]) if np.isfinite(model_probability[j]) else None
        baseline_p = float(baseline_probability[j]) if np.isfinite(baseline_probability[j]) else None
        fallback_p = _clip_probability(fallback_probability)
        chosen = (
            _clip_probability(model_p)
            if model_primary and model_p is not None
            else fallback_p
        )
        common = {
            "market": "A_share",
            "horizon_days": int(params.get("horizon_days") or 5),
            "target": params.get("target") or TARGET_LABEL,
            "target_display": TARGET_DISPLAY,
            "target_kind": params.get("target_kind") or TARGET_KIND,
            "probability_semantics": PROBABILITY_SEMANTICS,
            "model_method": method,
            "probability_source": probability_source,
            "feature_coverage": round(cov, 3) if cov is not None else None,
            "probability": round(chosen, 4),
            "p_up_5d": round(chosen, 4),
            "model_probability": round(_clip_probability(model_p), 4) if model_p is not None else None,
            "model_probability_shadow": (
                round(_clip_probability(model_p), 4)
                if not model_primary and model_p is not None
                else None
            ),
            "fallback_probability": round(fallback_p, 4),
            "baseline_probability": round(_clip_probability(baseline_p), 4) if baseline_p is not None else None,
            "base_rate": round(float(params.get("base_rate", fallback_p)), 4),
            "direction": direction_from_probability(chosen),
            "signal_strength": strength_from_probability(chosen),
            "signal_grade": grade_from_probability(chosen),
            "caveats": caveats,
        }
        if not bool(ok_mv[j]):
            rows[ts] = {
                "available": False,
                "validated": False,
                "reason": "missing market-cap feature; cannot apply liquid gate",
                **common,
                "drivers": [],
                "risks": [],
            }
            continue
        if not bool(eligible[j]):
            rows[ts] = {
                "available": True,
                "validated": False,
                "reason": "outside liquid top-%d%% gate (absolute up model unvalidated there)"
                          % round(liquid_frac * 100),
                **common,
                "drivers": [],
                "risks": [],
            }
            continue
        if cov is None or cov < min_cov or model_p is None:
            rows[ts] = {
                "available": True,
                "validated": False,
                "reason": "insufficient feature coverage",
                **common,
                "drivers": [],
                "risks": [],
            }
            continue

        drivers, risks = _logistic_contributions(X[j], model_features, model)
        if not model_primary:
            reason = (
                "absolute up model failed production gates; fallback/shadow only"
            )
        else:
            reason = "validated"
        rows[ts] = {
            "available": True,
            "validated": bool(model_primary),
            "reason": reason,
            **common,
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
        raise RuntimeError(f"frozen signal_up_5d params missing: {PARAMS_PATH}")
    rows = build_rows(codes, feat, feat_names, lnmv, industry, params)
    n_valid = sum(1 for r in rows.values() if r.get("validated"))
    n_available = sum(1 for r in rows.values() if r.get("available"))
    return {
        "market": "A_share",
        "asof": asof,
        "built_at": int(time.time()),
        "source": "DockCase daily/daily_basic + factor_research absolute-up calibration",
        "params_version": params.get("version"),
        "params_built_at": params.get("built_at"),
        "params_git_sha": params.get("git_sha"),
        "model_method": params.get("method"),
        "probability_source": MODEL_METHOD if _model_primary_enabled(params) else FALLBACK_METHOD,
        "probability_semantics": PROBABILITY_SEMANTICS,
        "horizon_days": int(params.get("horizon_days") or 5),
        "target": params.get("target") or TARGET_LABEL,
        "target_display": TARGET_DISPLAY,
        "target_kind": params.get("target_kind") or TARGET_KIND,
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
        "baseline": params.get("baseline") or {},
        "fallback": params.get("fallback") or {},
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
        return {"available": False, "reason": f"signal_up_5d artifact unreadable: {exc}"}
    if not artifact:
        return {
            "available": False,
            "reason": "signal_up_5d artifact not built (scripts/build_signal_up_5d.py)",
        }
    row = (artifact.get("rows") or {}).get(ts_code)
    if row is None:
        return {
            "available": False,
            "asof": artifact.get("asof"),
            "horizon_days": artifact.get("horizon_days", 5),
            "target": artifact.get("target") or TARGET_LABEL,
            "target_display": artifact.get("target_display") or TARGET_DISPLAY,
            "target_kind": artifact.get("target_kind") or TARGET_KIND,
            "probability_semantics": PROBABILITY_SEMANTICS,
            "reason": "ts_code not in signal_up_5d scored cross-section",
        }
    out = json.loads(json.dumps(row))
    out["asof"] = artifact.get("asof")
    out["horizon_days"] = artifact.get("horizon_days", out.get("horizon_days", 5))
    out["target"] = artifact.get("target") or out.get("target") or TARGET_LABEL
    out["target_display"] = artifact.get("target_display") or out.get("target_display") or TARGET_DISPLAY
    out["target_kind"] = artifact.get("target_kind") or out.get("target_kind") or TARGET_KIND
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
        out.get("probability_semantics") or artifact.get("probability_semantics") or PROBABILITY_SEMANTICS
    )
    out["stale"] = is_stale(artifact, today)
    if out["stale"]:
        out["validated"] = False
        out["reason"] = f"artifact asof {artifact.get('asof')} older than {STALE_AFTER_DAYS}d"
    out["caveats"] = list(artifact.get("caveats") or out.get("caveats") or [])
    return out
