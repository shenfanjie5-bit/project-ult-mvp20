#!/usr/bin/env python3
"""Freeze A-share 5d relative signal params.

Output: ``config/signal_5d_params.json``.

The production target is relative and calibratable:
    P(fwd5 return beats the same-day liquid-universe median)

It is NOT absolute P(up), which REPORT_PROB.md identifies as market-dominated.
Version 2 freezes a 7-feature ridge-logistic candidate plus the legacy 10-bin
calibration used as fallback and audit comparator.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, os.getcwd())
from factor_research.model import harness as H  # noqa: E402
from factor_research.model.caliblib import K_BINS, fit_bins, liquid_mask, score_bins  # noqa: E402
from mvp20 import signal_5d  # noqa: E402


OUT = Path("config/signal_5d_params.json")
SWEEP_REPORT = Path("factor_research/model/reports/prob_sweep_stage3.json")
HORIZON_DAYS = 5
LIQUID_FRAC = 0.70
LEGACY_FEATURES = ["ivol_60", "ep_ttm", "strev"]
MODEL_FEATURES = ["ivol_60", "ep_ttm", "strev", "max5", "turnover_20", "rvol_20", "mom_6_1"]
LEGACY_METHOD = "ew_signed"
MODEL_METHOD = signal_5d.LOGISTIC_METHOD
TARGET = signal_5d.TARGET_LABEL
TILT_SHRINK = 0.5
MODEL_L2 = 0.2
MIN_FEATURE_COV = 0.5
VALIDATION_DATES = 42
TOP_N = 20
MIN_TRAIN_DATES = 12


def _jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, np.ndarray):
        return _jsonable(v.tolist())
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v) if np.isfinite(v) else None
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except Exception:  # noqa: BLE001
        return None


def _stage3_summary() -> dict:
    if not SWEEP_REPORT.exists():
        return {"warning": f"{SWEEP_REPORT} missing"}
    rows = json.loads(SWEEP_REPORT.read_text(encoding="utf-8"))
    candidates = [
        r for r in rows
        if r.get("horizon") == HORIZON_DAYS
        and r.get("target") == "rel"
        and r.get("name") == "min_pair_strev__ew_signed"
    ]
    if not candidates:
        return {"warning": "stage3 h5 rel min_pair_strev__ew_signed not found"}
    r = candidates[0]
    return {
        "report": str(SWEEP_REPORT),
        "selected_name": r.get("name"),
        "features": r.get("features"),
        "method": r.get("method"),
        "variant": r.get("variant"),
        "n_test_dates": r.get("n_test_dates"),
        "n_obs": r.get("n_obs"),
        "disc_up_pp": r.get("disc_up_pp"),
        "disc_ret_pp": r.get("disc_ret_pp"),
        "brier_skill": r.get("brier_skill"),
        "coverage_q10_q90": r.get("coverage_q10_q90"),
        "reliability": r.get("reliability"),
        "note": (
            "Legacy H5 edge is marginal; v2 serves a 7-feature candidate only "
            "when walk-forward gates pass, otherwise continuous legacy fallback."
        ),
    }


def _relative_returns(fwd: np.ndarray, liquid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rel = fwd.astype(float).copy()
    med = np.full(fwd.shape[0], np.nan, dtype=float)
    for d in range(fwd.shape[0]):
        ok = np.isfinite(fwd[d]) & liquid[d]
        if ok.sum() > 50:
            med[d] = float(np.median(fwd[d][ok]))
            rel[d] = fwd[d] - med[d]
    return rel, med


def _legacy_score(Z: np.ndarray, meta: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    names = meta["feat_names"]
    idx = [names.index(f) for f in LEGACY_FEATURES]
    signs = {f: float(H.SIGN_PRIOR[f]) for f in LEGACY_FEATURES}
    sub = Z[:, :, idx]
    cov = np.isfinite(sub).mean(axis=2)
    w = np.array([signs[f] for f in LEGACY_FEATURES], dtype=float)
    score = np.where(np.isfinite(sub), sub, 0.0) @ w
    score[cov < MIN_FEATURE_COV] = np.nan
    return score, cov, signs


def _model_frame(Z: np.ndarray, meta: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    names = meta["feat_names"]
    missing = [f for f in MODEL_FEATURES if f not in names]
    if missing:
        raise RuntimeError(f"model feature(s) missing from panel: {missing}")
    idx = [names.index(f) for f in MODEL_FEATURES]
    X = Z[:, :, idx].astype(float)
    cov = np.isfinite(X).mean(axis=2)
    return X, cov


def _fit_model_payload(
    X: np.ndarray,
    y: np.ndarray,
    l2: float = MODEL_L2,
) -> dict[str, Any]:
    means = np.nanmean(X, axis=0)
    stds = np.nanstd(X, axis=0)
    means = np.where(np.isfinite(means), means, 0.0)
    stds = np.where(np.isfinite(stds) & (stds > 1e-8), stds, 1.0)
    Xs = signal_5d.standardize_matrix(X, means.tolist(), stds.tolist())
    beta = signal_5d.fit_ridge_logistic(Xs, y.astype(float), l2=l2)
    return {
        "intercept": float(beta[0]),
        "coefficients": [float(x) for x in beta[1:]],
        "feature_means": [float(x) for x in means],
        "feature_stds": [float(x) for x in stds],
    }


def _predict_model_payload(X: np.ndarray, payload: dict[str, Any]) -> np.ndarray:
    return signal_5d.predict_ridge_logistic(X, payload)


def _score_percentiles(scores: np.ndarray, valid: np.ndarray) -> np.ndarray:
    out = np.full(scores.shape, np.nan, dtype=float)
    for d in range(scores.shape[0]):
        ok = np.isfinite(scores[d]) & valid[d]
        if ok.sum() < 10:
            continue
        ranks = np.argsort(np.argsort(scores[d][ok]))
        out[d, ok] = 100.0 * ranks / max(int(ok.sum()) - 1, 1)
    return out


def _continuous_legacy_probability(
    pct: np.ndarray,
    stats: list[dict[str, Any]],
    base_rate: float,
) -> np.ndarray:
    k = len(stats)
    centers = (np.arange(k, dtype=float) + 0.5) * (100.0 / k)
    probs = np.array([
        base_rate + TILT_SHRINK * (float(s["p_up"]) - base_rate)
        for s in stats
    ], dtype=float)
    out = np.interp(pct, centers, probs, left=probs[0], right=probs[-1])
    out[~np.isfinite(pct)] = np.nan
    return out


def _date_metrics(
    name: str,
    date: str,
    p: np.ndarray,
    rank_score: np.ndarray,
    fwd_rel: np.ndarray,
    valid: np.ndarray,
    train_base: float,
) -> dict[str, Any] | None:
    ok = valid & np.isfinite(p) & np.isfinite(fwd_rel)
    if ok.sum() < 50:
        return None
    pp = np.clip(p[ok].astype(float), 1e-4, 1 - 1e-4)
    y = (fwd_rel[ok] > 0).astype(float)
    rr = fwd_rel[ok].astype(float)
    sc = rank_score[ok].astype(float)
    order = np.lexsort((sc, pp))
    top = order[-min(TOP_N, order.size):]
    brier = float(np.mean((pp - y) ** 2))
    base = float(np.mean((np.full_like(y, train_base) - y) ** 2))
    return {
        "scheme": name,
        "date": date,
        "n": int(ok.sum()),
        "p10": float(np.percentile(pp, 10)),
        "p50": float(np.percentile(pp, 50)),
        "p90": float(np.percentile(pp, 90)),
        "p_std": float(np.std(pp)),
        "unique_1dp": int(len(set(np.round(pp * 100, 1).tolist()))),
        "brier": brier,
        "brier_base": base,
        "brier_skill": float(1.0 - brier / base) if base > 0 else None,
        "rank_ic": float(H._spearman(pp, rr)),
        "score_ic": float(H._spearman(sc, rr)),
        "top_hit": float(np.mean(y[top])),
        "top_excess": float(np.mean(rr[top])),
    }


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def mean(key: str) -> float | None:
        vals = np.array([
            float(r[key]) for r in rows
            if r.get(key) is not None and np.isfinite(float(r[key]))
        ], dtype=float)
        return float(vals.mean()) if vals.size else None
    return {
        "n_dates": len(rows),
        "avg_brier": mean("brier"),
        "avg_brier_skill": mean("brier_skill"),
        "avg_rank_ic": mean("rank_ic"),
        "avg_score_ic": mean("score_ic"),
        "avg_top_hit": mean("top_hit"),
        "avg_top_excess": mean("top_excess"),
        "avg_p_std": mean("p_std"),
        "avg_unique_1dp": mean("unique_1dp"),
        "p10_mean": mean("p10"),
        "p90_mean": mean("p90"),
        "positive_rank_ic_pct": float(np.mean([r["rank_ic"] > 0 for r in rows])) if rows else None,
        "positive_top_excess_pct": float(np.mean([r["top_excess"] > 0 for r in rows])) if rows else None,
    }


def _walk_forward_validation(
    Xfeat: np.ndarray,
    model_cov: np.ndarray,
    legacy_score: np.ndarray,
    liquid: np.ndarray,
    fwd_rel: np.ndarray,
    meta: dict[str, Any],
    full_stats: list[dict[str, Any]],
    base_rate: float,
) -> dict[str, Any]:
    y_rel = fwd_rel > 0
    pct = _score_percentiles(legacy_score, liquid)
    candidates: list[int] = []
    for t in range(len(meta["base_dates"])):
        train_idx = [
            d for d in range(t)
            if np.isfinite(legacy_score[d]).any() and np.isfinite(fwd_rel[d]).any()
        ]
        valid = liquid[t] & np.isfinite(fwd_rel[t]) & (model_cov[t] >= MIN_FEATURE_COV)
        if len(train_idx) >= MIN_TRAIN_DATES and valid.sum() >= 50:
            candidates.append(t)
    if len(candidates) <= VALIDATION_DATES:
        selected = candidates
    else:
        idx = sorted(set(int(round(x)) for x in np.linspace(0, len(candidates) - 1, VALIDATION_DATES)))
        j = 0
        while len(idx) < VALIDATION_DATES:
            if j not in idx:
                idx.append(j)
            j += 1
        selected = [candidates[i] for i in sorted(idx[:VALIDATION_DATES])]

    logistic_rows: list[dict[str, Any]] = []
    fallback_rows: list[dict[str, Any]] = []
    per_date: list[dict[str, Any]] = []
    for t in selected:
        train_idx = [
            d for d in range(t)
            if np.isfinite(legacy_score[d]).any() and np.isfinite(fwd_rel[d]).any()
        ]
        train_sel = np.zeros_like(legacy_score, dtype=bool)
        for d in train_idx:
            train_sel[d] = (
                liquid[d]
                & np.isfinite(fwd_rel[d])
                & (model_cov[d] >= MIN_FEATURE_COV)
            )
        ytr = y_rel[train_sel].astype(float)
        train_base = float(np.mean(ytr))
        model_payload = _fit_model_payload(Xfeat[train_sel], ytr, l2=MODEL_L2)
        p_model = _predict_model_payload(Xfeat[t], model_payload)

        # Fallback uses only prior dates for bin calibration.
        stats_raw, _ = fit_bins(legacy_score, fwd_rel, liquid, train_idx, k=K_BINS)
        if any(s is None for s in stats_raw):
            stats = full_stats
        else:
            stats = signal_5d.apply_isotonic_p_up(stats_raw)
        date_base = float(np.nanmean([s["p_up"] for s in stats]))
        p_fallback = _continuous_legacy_probability(pct[t], stats, date_base)

        valid = liquid[t] & np.isfinite(fwd_rel[t]) & (model_cov[t] >= MIN_FEATURE_COV)
        m_model = _date_metrics(
            MODEL_METHOD, meta["base_dates"][t], p_model, legacy_score[t],
            fwd_rel[t], valid, train_base,
        )
        m_fallback = _date_metrics(
            signal_5d.FALLBACK_METHOD, meta["base_dates"][t], p_fallback,
            legacy_score[t], fwd_rel[t], valid, train_base,
        )
        row = {"date": meta["base_dates"][t], "train_dates": len(train_idx)}
        if m_model:
            logistic_rows.append(m_model)
            row["model"] = {
                "rank_ic": m_model["rank_ic"],
                "top_excess": m_model["top_excess"],
                "brier_skill": m_model["brier_skill"],
                "unique_1dp": m_model["unique_1dp"],
            }
        if m_fallback:
            fallback_rows.append(m_fallback)
            row["fallback"] = {
                "rank_ic": m_fallback["rank_ic"],
                "top_excess": m_fallback["top_excess"],
                "brier_skill": m_fallback["brier_skill"],
                "unique_1dp": m_fallback["unique_1dp"],
            }
        per_date.append(row)

    model_summary = _aggregate(logistic_rows)
    fallback_summary = _aggregate(fallback_rows)
    gates = {
        "avg_unique_1dp_ge_50": (model_summary.get("avg_unique_1dp") or 0.0) >= 50.0,
        "avg_brier_skill_gt_0": (model_summary.get("avg_brier_skill") or -999.0) > 0.0,
        "avg_rank_ic_gt_fallback": (
            (model_summary.get("avg_rank_ic") or -999.0)
            > (fallback_summary.get("avg_rank_ic") or -999.0)
        ),
        "avg_top_excess_gt_fallback": (
            (model_summary.get("avg_top_excess") or -999.0)
            > (fallback_summary.get("avg_top_excess") or -999.0)
        ),
    }
    return {
        "n_requested_dates": VALIDATION_DATES,
        "selected_dates": [meta["base_dates"][t] for t in selected],
        "rule": "each test asof fits on strictly earlier panel dates",
        "model_summary": model_summary,
        "fallback_summary": fallback_summary,
        "gates": gates,
        "primary_enabled": all(gates.values()),
        "per_date": per_date,
    }


def main() -> int:
    z, meta = H.load_panel()
    Z = H.neutralize(z, meta)
    fwd = z[f"fwd{HORIZON_DAYS}"].astype(np.float64)
    liquid = liquid_mask(z, LIQUID_FRAC)
    fwd_rel, _median_ret = _relative_returns(fwd, liquid)

    legacy_score, legacy_cov, signs = _legacy_score(Z, meta)
    train_idx = [
        d for d in range(legacy_score.shape[0])
        if np.isfinite(legacy_score[d]).any() and np.isfinite(fwd_rel[d]).any()
    ]
    raw_stats, _ = fit_bins(legacy_score, fwd_rel, liquid, train_idx, k=K_BINS)
    if any(s is None for s in raw_stats):
        raise RuntimeError("signal_5d legacy bins incomplete")
    stats = signal_5d.apply_isotonic_p_up(raw_stats)
    base_rate = float(np.nanmean([s["p_up"] for s in stats]))

    Xfeat, model_cov = _model_frame(Z, meta)
    train_sel = liquid & np.isfinite(fwd_rel) & (model_cov >= MIN_FEATURE_COV)
    model_fit = _fit_model_payload(Xfeat[train_sel], (fwd_rel[train_sel] > 0).astype(float), l2=MODEL_L2)
    validation = _walk_forward_validation(
        Xfeat, model_cov, legacy_score, liquid, fwd_rel, meta, stats, base_rate,
    )

    model = {
        "type": "ridge_logistic",
        "l2": MODEL_L2,
        "features": MODEL_FEATURES,
        "intercept": model_fit["intercept"],
        "coefficients": model_fit["coefficients"],
        "feature_means": model_fit["feature_means"],
        "feature_stds": model_fit["feature_stds"],
        "train_window": {
            "base_dates": [meta["base_dates"][train_idx[0]], meta["base_dates"][train_idx[-1]]],
            "n_dates": len(train_idx),
            "n_observations": int(train_sel.sum()),
            "rule": "full matured panel for serving params; historical validation is walk-forward",
        },
        "validation": validation,
        "primary_enabled": bool(validation["primary_enabled"]),
        "fallback_method": signal_5d.FALLBACK_METHOD,
    }
    legacy = {
        "method": LEGACY_METHOD,
        "features": LEGACY_FEATURES,
        "signs": signs,
        "base_rate": base_rate,
        "tilt_shrink": TILT_SHRINK,
        "k_bins": K_BINS,
        "bins": [{k: s[k] for k in (
            "n", "p_up", "p_up_raw", "mean", "q10", "q50", "q90"
        )} for s in stats],
        "feature_coverage_mean": float(np.nanmean(legacy_cov)),
        "calibration": {
            "fit": "full-panel frozen bins over matured fwd5 relative returns",
            "p_up_isotonic": True,
            "p_up_isotonic_method": "weighted_pool_adjacent_violators",
            "tilt_shrink": TILT_SHRINK,
        },
    }
    params = {
        "version": 2,
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_sha": _git_sha(),
        "panel": {
            "base_dates": [meta["base_dates"][0], meta["base_dates"][-1]],
            "n_dates": len(meta["base_dates"]),
            "n_stocks": len(meta["cols"]),
        },
        "horizon_days": HORIZON_DAYS,
        "target": TARGET,
        "target_kind": "relative_cross_section_median",
        "probability_semantics": (
            "P(5d return beats same-day liquid-universe median); not absolute P(up)"
        ),
        "liquid_frac": LIQUID_FRAC,
        "k_bins": K_BINS,
        "min_feature_coverage": MIN_FEATURE_COV,
        "neutralization": (
            "per-date cross-section: winsor->z->residualize[1,ln_mv,industry]"
            "->rank-z; NaN->0 post-rank; min feature coverage 0.5"
        ),
        "features": MODEL_FEATURES,
        "method": MODEL_METHOD,
        "model": model,
        "legacy_bin_calibration": legacy,
        # Keep these top-level keys for legacy audits/tests and old readers.
        "base_rate": base_rate,
        "tilt_shrink": TILT_SHRINK,
        "bins": legacy["bins"],
        "calibration": {
            "fit": "v2 logistic candidate with legacy continuous fallback",
            "p_up_isotonic": True,
            "p_up_isotonic_method": "weighted_pool_adjacent_violators",
            "stage3_oos": _stage3_summary(),
            "model_validation": validation,
            "primary_probability_source": MODEL_METHOD if model["primary_enabled"] else signal_5d.FALLBACK_METHOD,
            "fallback_method": signal_5d.FALLBACK_METHOD,
        },
        "caveats": [
            "validated ONLY on the liquid top-70% by market cap with enough feature coverage; outside -> validated:false",
            "target is P(5d beat same-day liquid median), not absolute P(up)",
            "absolute P(up) is market-dominated and intentionally NOT emitted",
            "v2 logistic is production-primary only when walk-forward gates pass",
            "if model gates fail, probability uses score_pct_linear_bin10 and logistic is emitted as shadow",
            "survivorship: universe frozen from a recent snapshot; reported edges are upper bounds",
            "A-share only; HK/US require separate history, feature, and calibration artifacts",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(_jsonable(params), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")
    print(
        "  legacy bins P(beat median) range: "
        f"{stats[0]['p_up']:.3f} .. {stats[-1]['p_up']:.3f} "
        f"(base {base_rate:.3f}, shrink {TILT_SHRINK})"
    )
    print(
        f"  logistic primary_enabled={model['primary_enabled']} "
        f"gates={json.dumps(validation['gates'], ensure_ascii=False)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
