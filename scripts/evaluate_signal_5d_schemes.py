#!/usr/bin/env python3
"""Compare per-stock A-share 5d relative probability schemes.

The existing serving layer maps the cross-sectional score into 10 calibrated
bins.  This evaluator tests more granular/aggressive alternatives under the
same no-leakage rule: each tested as-of date trains/calibrates only on earlier
panel dates.

No sklearn/lightgbm dependency is required; logistic variants use a small
numpy-only ridge logistic fitter.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from factor_research.model import harness as H  # noqa: E402
from factor_research.model.caliblib import fit_bins, liquid_mask, score_bins  # noqa: E402
from mvp20 import signal_5d  # noqa: E402


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


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _relative_returns(fwd: np.ndarray, liquid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rel = fwd.copy()
    med = np.full(fwd.shape[0], np.nan)
    for d in range(fwd.shape[0]):
        ok = np.isfinite(fwd[d]) & liquid[d]
        if ok.sum() > 50:
            med[d] = float(np.median(fwd[d][ok]))
            rel[d] = fwd[d] - med[d]
    return rel, med


def _score_percentiles(scores: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = np.full(scores.shape, np.nan)
    for d in range(scores.shape[0]):
        ok = np.isfinite(scores[d]) & mask[d]
        if ok.sum() < 10:
            continue
        ranks = np.argsort(np.argsort(scores[d][ok]))
        out[d, ok] = 100.0 * ranks / max(int(ok.sum()) - 1, 1)
    return out


def _score_matrix(z: Any, meta: dict[str, Any], params: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    z_neutral = H.neutralize(z, meta)
    names = meta["feat_names"]
    legacy = params.get("legacy_bin_calibration") or params
    features = [str(f) for f in legacy["features"]]
    idx = [names.index(f) for f in features]
    sub = z_neutral[:, :, idx]
    signs = legacy.get("signs") or {}
    w = np.array([float(signs[f]) for f in features], dtype=float)
    cov = np.isfinite(sub).mean(axis=2)
    score = np.where(np.isfinite(sub), sub, 0.0) @ w
    score[cov < float(params.get("min_feature_coverage") or signal_5d.MIN_FEATURE_COV)] = np.nan
    return score, z_neutral


def _fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0, max_iter: int = 35) -> np.ndarray:
    """Small ridge logistic fitter with Newton steps."""
    Xd = np.column_stack([np.ones(X.shape[0]), X])
    beta = np.zeros(Xd.shape[1], dtype=float)
    reg = np.eye(Xd.shape[1], dtype=float) * float(l2)
    reg[0, 0] = 0.0
    for _ in range(max_iter):
        eta = np.clip(Xd @ beta, -30.0, 30.0)
        p = 1.0 / (1.0 + np.exp(-eta))
        w = np.clip(p * (1.0 - p), 1e-5, None)
        grad = Xd.T @ (p - y) + reg @ beta
        hess = (Xd.T * w) @ Xd + reg
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(hess, grad, rcond=None)[0]
        beta -= step
        if float(np.max(np.abs(step))) < 1e-5:
            break
    return beta


def _predict_logistic(beta: np.ndarray, X: np.ndarray) -> np.ndarray:
    Xd = np.column_stack([np.ones(X.shape[0]), X])
    eta = np.clip(Xd @ beta, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-eta))


def _train_feature_frame(
    z_neutral: np.ndarray,
    meta: dict[str, Any],
    features: list[str],
) -> np.ndarray:
    idx = [meta["feat_names"].index(f) for f in features]
    return z_neutral[:, :, idx].astype(float)


def _safe_standardize_train_test(Xtr: np.ndarray, Xte: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mu = np.nanmean(Xtr, axis=0)
    sd = np.nanstd(Xtr, axis=0)
    sd = np.where(np.isfinite(sd) & (sd > 1e-8), sd, 1.0)
    mu = np.where(np.isfinite(mu), mu, 0.0)
    return (
        np.nan_to_num((Xtr - mu) / sd, nan=0.0),
        np.nan_to_num((Xte - mu) / sd, nan=0.0),
    )


def _calibrate_bins(
    scores: np.ndarray,
    fwd_rel: np.ndarray,
    liquid: np.ndarray,
    train_idx: list[int],
    test_idx: int,
    k: int,
    shrink: float,
) -> np.ndarray:
    stats_raw, _ = fit_bins(scores, fwd_rel, liquid, train_idx, k=k)
    if any(s is None for s in stats_raw):
        return np.full(scores.shape[1], np.nan)
    stats = signal_5d.apply_isotonic_p_up(stats_raw)
    base = float(np.nanmean([s["p_up"] for s in stats]))
    b = score_bins(scores[test_idx], liquid[test_idx], k=k)
    out = np.full(scores.shape[1], np.nan)
    for bi in range(k):
        sel = b == bi
        out[sel] = base + shrink * (float(stats[bi]["p_up"]) - base)
    return out


def _calibrate_pct_curve(
    pct: np.ndarray,
    fwd_rel: np.ndarray,
    liquid: np.ndarray,
    train_idx: list[int],
    test_idx: int,
    n_knots: int,
) -> np.ndarray:
    bins = np.linspace(0.0, 100.0, n_knots + 1)
    centers = (bins[:-1] + bins[1:]) / 2.0
    probs: list[float] = []
    weights: list[int] = []
    for lo, hi in zip(bins[:-1], bins[1:], strict=True):
        vals = []
        for d in train_idx:
            sel = liquid[d] & np.isfinite(pct[d]) & np.isfinite(fwd_rel[d]) & (pct[d] >= lo)
            sel &= pct[d] <= hi if hi == 100.0 else pct[d] < hi
            if sel.any():
                vals.extend((fwd_rel[d][sel] > 0).astype(float).tolist())
        if vals:
            probs.append(float(np.mean(vals)))
            weights.append(len(vals))
        else:
            probs.append(float("nan"))
            weights.append(0)
    if not any(weights):
        return np.full(pct.shape[1], np.nan)
    finite = np.isfinite(probs)
    if not finite.all():
        fill = float(np.average(np.array(probs)[finite], weights=np.array(weights)[finite]))
        probs = [fill if not np.isfinite(p) else p for p in probs]
    smooth = signal_5d.isotonic_non_decreasing(probs, weights)
    return np.interp(pct[test_idx], centers, smooth, left=smooth[0], right=smooth[-1])


def _date_metrics(
    date: str,
    p: np.ndarray,
    score: np.ndarray,
    fwd_rel: np.ndarray,
    valid: np.ndarray,
    train_base: float,
    top_n: int,
) -> dict[str, Any] | None:
    ok = valid & np.isfinite(p) & np.isfinite(fwd_rel)
    if ok.sum() < 50:
        return None
    pp = np.clip(p[ok].astype(float), 1e-4, 1 - 1e-4)
    y = (fwd_rel[ok] > 0).astype(float)
    rr = fwd_rel[ok].astype(float)
    sc = score[ok].astype(float)
    order = np.lexsort((sc, pp))
    top = order[-min(top_n, order.size):]
    brier = float(np.mean((pp - y) ** 2))
    base = float(np.mean((np.full_like(y, train_base) - y) ** 2))
    return {
        "date": date,
        "n": int(ok.sum()),
        "p_min": float(np.min(pp)),
        "p10": float(np.percentile(pp, 10)),
        "p50": float(np.percentile(pp, 50)),
        "p90": float(np.percentile(pp, 90)),
        "p_max": float(np.max(pp)),
        "p_std": float(np.std(pp)),
        "unique_1dp": int(len(set(np.round(pp * 100, 1).tolist()))),
        "brier": brier,
        "brier_base": base,
        "brier_skill": float(1.0 - brier / base) if base > 0 else None,
        "calibration_error": float(abs(np.mean(pp) - np.mean(y))),
        "rank_ic": float(H._spearman(pp, rr)),
        "score_ic": float(H._spearman(sc, rr)),
        "top_hit": float(np.mean(y[top])),
        "top_excess": float(np.mean(rr[top])),
    }


def _aggregate(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    def mean(key: str) -> float | None:
        vals = np.array([r[key] for r in rows if r.get(key) is not None and np.isfinite(r[key])], dtype=float)
        return float(vals.mean()) if vals.size else None
    return {
        "scheme": name,
        "n_dates": len(rows),
        "avg_brier": mean("brier"),
        "avg_brier_skill": mean("brier_skill"),
        "avg_calibration_error": mean("calibration_error"),
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
        "failure_dates": [
            {"date": r["date"], "rank_ic": r["rank_ic"], "top_excess": r["top_excess"]}
            for r in rows if r["rank_ic"] < 0 or r["top_excess"] < 0
        ],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    params = signal_5d.load_params()
    if not params:
        raise SystemExit("config/signal_5d_params.json missing")
    z, meta = H.load_panel()
    scores, z_neutral = _score_matrix(z, meta, params)
    liquid = liquid_mask(z, float(params.get("liquid_frac") or 0.70))
    pct = _score_percentiles(scores, liquid)
    fwd_abs = z[f"fwd{int(params.get('horizon_days') or 5)}"].astype(float)
    fwd_rel, median_ret = _relative_returns(fwd_abs, liquid)
    y_rel = fwd_rel > 0

    features_aggressive = [
        f for f in ("ivol_60", "ep_ttm", "strev", "max5", "turnover_20", "rvol_20", "mom_6_1")
        if f in meta["feat_names"]
    ]
    Xfeat = _train_feature_frame(z_neutral, meta, features_aggressive)

    candidates: list[int] = []
    for t, date in enumerate(meta["base_dates"]):
        train_idx = [d for d in range(t) if np.isfinite(scores[d]).any() and np.isfinite(fwd_rel[d]).any()]
        valid = liquid[t] & np.isfinite(scores[t]) & np.isfinite(fwd_rel[t])
        if len(train_idx) >= args.min_train_dates and valid.sum() >= 50:
            candidates.append(t)
    if args.dates:
        wanted = set(x.strip() for x in args.dates.split(",") if x.strip())
        selected = [t for t in candidates if meta["base_dates"][t] in wanted]
        missing = sorted(wanted - {meta["base_dates"][t] for t in selected})
        if missing:
            raise SystemExit(f"dates not evaluable: {missing}")
    else:
        idx = sorted(set(int(round(x)) for x in np.linspace(0, len(candidates) - 1, args.n_dates)))
        while len(idx) < args.n_dates:
            idx.append(len(idx))
        selected = [candidates[i] for i in idx[:args.n_dates]]

    schemes: dict[str, list[dict[str, Any]]] = {
        "baseline_10bin_shrink05": [],
        "aggressive_50bin_no_shrink": [],
        "continuous_pct_curve_50knots": [],
        "logistic_score_pct": [],
        "logistic_multifeature_7f": [],
    }

    per_date_details: list[dict[str, Any]] = []
    for t in selected:
        date = meta["base_dates"][t]
        train_idx = [d for d in range(t) if np.isfinite(scores[d]).any() and np.isfinite(fwd_rel[d]).any()]
        train_sel = np.zeros_like(scores, dtype=bool)
        for d in train_idx:
            train_sel[d] = liquid[d] & np.isfinite(scores[d]) & np.isfinite(fwd_rel[d])
        train_base = float(np.mean(y_rel[train_sel]))
        valid = liquid[t] & np.isfinite(scores[t]) & np.isfinite(fwd_rel[t])

        predictions: dict[str, np.ndarray] = {
            "baseline_10bin_shrink05": _calibrate_bins(scores, fwd_rel, liquid, train_idx, t, 10, 0.5),
            "aggressive_50bin_no_shrink": _calibrate_bins(scores, fwd_rel, liquid, train_idx, t, 50, 1.0),
            "continuous_pct_curve_50knots": _calibrate_pct_curve(pct, fwd_rel, liquid, train_idx, t, 50),
        }

        # Logistic on score percentile.
        Xtr = pct[train_sel].reshape(-1, 1) / 100.0
        ytr = y_rel[train_sel].astype(float)
        Xte = (pct[t].reshape(-1, 1) / 100.0)
        Xtr_s, Xte_s = _safe_standardize_train_test(Xtr, Xte)
        beta = _fit_logistic(Xtr_s, ytr, l2=args.logistic_l2)
        predictions["logistic_score_pct"] = _predict_logistic(beta, Xte_s)

        # Logistic on a wider feature set.
        Xtr2 = Xfeat[train_sel]
        Xte2 = Xfeat[t]
        Xtr2_s, Xte2_s = _safe_standardize_train_test(Xtr2, Xte2)
        beta2 = _fit_logistic(Xtr2_s, ytr, l2=args.logistic_l2)
        predictions["logistic_multifeature_7f"] = _predict_logistic(beta2, Xte2_s)

        date_row = {"date": date, "train_dates": len(train_idx), "median_5d_return": float(median_ret[t])}
        for name, pred in predictions.items():
            m = _date_metrics(date, pred, scores[t], fwd_rel[t], valid, train_base, args.top_n)
            if m:
                schemes[name].append(m)
                date_row[name] = {
                    "p10": m["p10"],
                    "p50": m["p50"],
                    "p90": m["p90"],
                    "unique_1dp": m["unique_1dp"],
                    "rank_ic": m["rank_ic"],
                    "top_excess": m["top_excess"],
                    "brier_skill": m["brier_skill"],
                }
        per_date_details.append(date_row)

    summary = [_aggregate(name, rows) for name, rows in schemes.items()]
    summary.sort(key=lambda r: (
        r["avg_rank_ic"] if r["avg_rank_ic"] is not None else -999,
        r["avg_p_std"] if r["avg_p_std"] is not None else -999,
    ), reverse=True)
    best = next((r for r in summary if r["scheme"] == "logistic_multifeature_7f"), {})
    fallback = next((r for r in summary if r["scheme"] == "continuous_pct_curve_50knots"), {})
    legacy = next((r for r in summary if r["scheme"] == "baseline_10bin_shrink05"), {})
    gates = {
        "avg_unique_1dp_ge_50": (best.get("avg_unique_1dp") or 0.0) >= 50.0,
        "avg_brier_skill_gt_0": (best.get("avg_brier_skill") or -999.0) > 0.0,
        "avg_rank_ic_gt_legacy_bin": (
            (best.get("avg_rank_ic") or -999.0)
            > (legacy.get("avg_rank_ic") or -999.0)
        ),
        "avg_top_excess_gt_legacy_bin": (
            (best.get("avg_top_excess") or -999.0)
            > (legacy.get("avg_top_excess") or -999.0)
        ),
    }
    return {
        "audit": "a_share_signal_5d_model_backtest",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "methodology": {
            "target": signal_5d.TARGET_LABEL,
            "not_absolute_p_up": True,
            "walk_forward": True,
            "rule": "each test asof uses only prior panel dates for calibration/training",
            "dependencies": "numpy only; sklearn/lightgbm unavailable in current .venv",
            "selected_dates": [meta["base_dates"][t] for t in selected],
            "features_aggressive": features_aggressive,
            "top_n": args.top_n,
        },
        "summary": summary,
        "validation_gates": gates,
        "primary_model_passed": all(gates.values()),
        "recommended_probability_source": (
            "logistic_multifeature_7f" if all(gates.values()) else "score_pct_linear_bin10"
        ),
        "fallback_reference": fallback,
        "per_date": per_date_details,
        "interpretation": {
            "baseline_10bin_shrink05": "current conservative bucketed contract; low dispersion",
            "aggressive_50bin_no_shrink": "more buckets, no tilt shrink; more dispersion but still bucketed",
            "continuous_pct_curve_50knots": "per-stock continuous interpolation over score percentile; easiest production upgrade",
            "logistic_score_pct": "per-stock continuous logistic probability from current score percentile",
            "logistic_multifeature_7f": "more aggressive direct classifier over seven neutralized features",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--out", default=None)
    ap.add_argument("--n-dates", type=int, default=12)
    ap.add_argument("--dates", default=None)
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--min-train-dates", type=int, default=12)
    ap.add_argument("--logistic-l2", type=float, default=0.2)
    args = ap.parse_args()
    payload = run(args)
    out = Path(args.out) if args.out else ROOT / "docs" / "audit" / f"{args.date}_a_share_signal_5d_model_backtest.json"
    _write(out, payload)
    print(out)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    t0 = time.time()
    rc = main()
    print(f"elapsed_s={time.time() - t0:.1f}")
    raise SystemExit(rc)
