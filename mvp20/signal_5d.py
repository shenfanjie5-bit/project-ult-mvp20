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
}


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


def _bin_of(score: "Any", eligible: "Any", k: int) -> "Any":
    return quant_score._bin_of(score, eligible, k)  # tested parity in quant_score


def _weights(params: Mapping[str, Any]) -> dict[str, float]:
    method = str(params.get("method") or "ew_signed")
    if method == "ew_signed":
        return {str(k): float(v) for k, v in (params.get("signs") or {}).items()}
    if method == "ic_weighted":
        return {str(k): float(v) for k, v in (params.get("weights") or {}).items()}
    raise ValueError(f"unsupported signal_5d method: {method}")


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

    k = int(params.get("k_bins") or 10)
    liquid_frac = float(params.get("liquid_frac") or 0.7)
    min_cov = float(params.get("min_feature_coverage") or MIN_FEATURE_COV)
    features = [str(f) for f in params["features"]]
    weights = _weights(params)
    name_idx = {f: i for i, f in enumerate(feat_names)}
    missing = [f for f in features if f not in name_idx]
    if missing:
        raise ValueError(f"signal_5d feature(s) missing from builder output: {missing}")
    for f in features:
        if f not in weights:
            raise ValueError(f"signal_5d weight/sign missing for feature: {f}")

    z_all = quant_score.neutralize_cross_section(feat, lnmv, industry)
    idx = [name_idx[f] for f in features]
    z = z_all[:, idx]
    cov = np.isfinite(z).mean(axis=1)
    xi = np.where(np.isfinite(z), z, 0.0)
    w = np.array([weights[f] for f in features], dtype=float)
    score = xi @ w
    score[cov < min_cov] = np.nan

    ok_mv = np.isfinite(lnmv)
    eligible = np.zeros(len(codes), bool)
    if ok_mv.sum() >= 50:
        threshold = np.percentile(lnmv[ok_mv], 100 * (1 - liquid_frac))
        eligible = ok_mv & (lnmv >= threshold)

    bins = _bin_of(score, eligible, k)
    score_pct = np.full(len(codes), np.nan)
    oks = np.isfinite(score) & eligible
    if oks.sum() > 10:
        ranks = np.argsort(np.argsort(score[oks]))
        score_pct[oks] = 100.0 * ranks / max(int(oks.sum()) - 1, 1)

    base_rate = float(params["base_rate"])
    tilt_shrink = float(params.get("tilt_shrink", 1.0))
    target = str(params.get("target") or TARGET_LABEL)
    horizon = int(params.get("horizon_days") or 5)
    bin_stats = list(params["bins"])
    base_norm = math.sqrt(max(len(features), 1))

    rows: dict[str, dict[str, Any]] = {}
    for j, ts in enumerate(codes):
        if not bool(ok_mv[j]):
            rows[ts] = {
                "available": False,
                "validated": False,
                "reason": "missing market-cap feature; cannot apply liquid gate",
            }
            continue
        if not bool(eligible[j]):
            rows[ts] = {
                "available": True,
                "validated": False,
                "reason": "outside liquid top-%d%% gate (5d signal unvalidated there)"
                          % round(liquid_frac * 100),
            }
            continue
        if int(bins[j]) < 0 or not np.isfinite(score[j]):
            rows[ts] = {
                "available": True,
                "validated": False,
                "reason": "insufficient feature coverage",
            }
            continue

        stat = bin_stats[int(bins[j])]
        raw_p = float(stat["p_up"])
        probability = base_rate + tilt_shrink * (raw_p - base_rate)
        drivers, risks = _feature_contributions(z[j], features, weights, base_norm)
        rows[ts] = {
            "available": True,
            "validated": True,
            "reason": "validated",
            "market": "A_share",
            "horizon_days": horizon,
            "target": target,
            "target_display": TARGET_DISPLAY,
            "probability": round(probability, 3),
            "p_beat_median": round(probability, 3),
            "raw_bin_probability": round(raw_p, 3),
            "base_rate": round(base_rate, 3),
            "tilt_pp": round(100.0 * (probability - base_rate), 1),
            "direction": direction_from_probability(probability, base_rate),
            "signal_strength": strength_from_probability(probability, base_rate),
            "signal_grade": grade_from_probability(probability, base_rate),
            "score_pct": round(float(score_pct[j]), 1) if np.isfinite(score_pct[j]) else None,
            "score": round(float(score[j]), 4),
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
    out["stale"] = is_stale(artifact, today)
    if out["stale"]:
        out["validated"] = False
        out["reason"] = f"artifact asof {artifact.get('asof')} older than {STALE_AFTER_DAYS}d"
    out["caveats"] = list(artifact.get("caveats") or [])
    return out
