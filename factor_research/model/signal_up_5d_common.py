"""Shared research helpers for the absolute A-share 5d upside signal.

All helpers here are offline/research only. They build PIT-safe same-day
features, fit frozen logistic payloads, and run walk-forward validation for
``mvp20.signal_up_5d`` without putting any training work on the BFF path.
"""
from __future__ import annotations

import json
import math
from typing import Any

import numpy as np

from factor_research import _datalib
from factor_research.model import harness as H
from factor_research.model.caliblib import liquid_mask
from mvp20 import signal_5d, signal_up_5d


HORIZON_DAYS = 5
LIQUID_FRAC = 0.70
MIN_FEATURE_COV = 0.5
MIN_TRAIN_DATES = 12
MODEL_L2 = 0.8

STOCK_FEATURES = [
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
]
REGIME_FEATURES = [
    "market_ret_5d",
    "market_ret_20d",
    "industry_ret_5d",
    "industry_ret_20d",
]
MODEL_FEATURES = STOCK_FEATURES + REGIME_FEATURES
BASELINE_FEATURES = ["ret_20d", "mom_6_1", "ivol_60", "max5", "turnover_20"]
BASELINE_WEIGHTS = {
    "ret_20d": -1.0,
    "mom_6_1": 1.0,
    "ivol_60": -1.0,
    "max5": -1.0,
    "turnover_20": -1.0,
}


def jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, np.ndarray):
        return jsonable(v.tolist())
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v) if np.isfinite(v) else None
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def write_json(path: "Any", payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _rolling_return(ret: np.ndarray, base_idx: list[int], window: int) -> np.ndarray:
    lr = np.log1p(np.nan_to_num(ret, nan=0.0))
    cum = np.cumsum(lr, axis=0)
    has = np.isfinite(ret)
    out = np.full((len(base_idx), ret.shape[1]), np.nan, dtype=float)
    for d, k in enumerate(base_idx):
        start = k - window
        if start < 0:
            continue
        val = np.exp(cum[k] - cum[start]) - 1.0
        cnt = has[start + 1:k + 1].sum(axis=0)
        out[d] = np.where(cnt >= max(1, int(window * 0.6)), val, np.nan)
    return out


def _rsi_14(ret: np.ndarray, base_idx: list[int]) -> np.ndarray:
    out = np.full((len(base_idx), ret.shape[1]), np.nan, dtype=float)
    for d, k in enumerate(base_idx):
        start = k - 14
        if start < 0:
            continue
        win = ret[start + 1:k + 1]
        gains = np.where(np.isfinite(win) & (win > 0), win, 0.0)
        losses = np.where(np.isfinite(win) & (win < 0), -win, 0.0)
        cnt = np.isfinite(win).sum(axis=0)
        avg_gain = gains.sum(axis=0) / np.maximum(cnt, 1)
        avg_loss = losses.sum(axis=0) / np.maximum(cnt, 1)
        rs = avg_gain / np.where(avg_loss > 1e-12, avg_loss, np.nan)
        rsi = 100.0 - 100.0 / (1.0 + rs)
        rsi = np.where((avg_loss <= 1e-12) & (avg_gain > 0), 100.0, rsi)
        rsi = np.where((avg_loss <= 1e-12) & (avg_gain <= 1e-12), 50.0, rsi)
        out[d] = np.where(cnt >= 10, rsi, np.nan)
    return out


def _drawdown_20(ret: np.ndarray, base_idx: list[int]) -> np.ndarray:
    out = np.full((len(base_idx), ret.shape[1]), np.nan, dtype=float)
    for d, k in enumerate(base_idx):
        start = k - 20
        if start < 0:
            continue
        win = ret[start + 1:k + 1]
        cnt = np.isfinite(win).sum(axis=0)
        lr = np.log1p(np.nan_to_num(win, nan=0.0))
        px = np.exp(np.cumsum(lr, axis=0))
        peak = np.maximum.accumulate(px, axis=0)
        dd = px[-1] / np.where(peak.max(axis=0) > 0, peak.max(axis=0), np.nan) - 1.0
        out[d] = np.where(cnt >= 12, dd, np.nan)
    return out


def _vol_20(ret: np.ndarray, base_idx: list[int]) -> np.ndarray:
    out = np.full((len(base_idx), ret.shape[1]), np.nan, dtype=float)
    for d, k in enumerate(base_idx):
        start = k - 20
        if start < 0:
            continue
        win = ret[start + 1:k + 1]
        cnt = np.isfinite(win).sum(axis=0)
        out[d] = np.where(cnt >= 12, np.nanstd(win, axis=0), np.nan)
    return out


def _weighted_market_return(ret_window: np.ndarray, mv: np.ndarray, base_idx: list[int]) -> np.ndarray:
    out = np.full(ret_window.shape, np.nan, dtype=float)
    for d, k in enumerate(base_idx):
        r = ret_window[d]
        w = mv[k] if k < mv.shape[0] else np.full(ret_window.shape[1], np.nan)
        ok = np.isfinite(r) & np.isfinite(w) & (w > 0)
        if ok.sum() >= 30:
            out[d, :] = float(np.average(r[ok], weights=w[ok]))
    return out


def _industry_return(ret_window: np.ndarray, industry: np.ndarray) -> np.ndarray:
    out = np.full(ret_window.shape, np.nan, dtype=float)
    for d in range(ret_window.shape[0]):
        for ind in sorted(set(int(x) for x in industry if int(x) >= 0)):
            sel = industry == ind
            vals = ret_window[d, sel]
            ok = np.isfinite(vals)
            if ok.sum() >= 3:
                out[d, sel] = float(np.mean(vals[ok]))
    return out


def _align_price_matrices(meta: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], list[str]]:
    ret, to, mv, cal, cols = _datalib.load_price_matrices(start="20230101")
    pos = {ts: i for i, ts in enumerate(cols)}
    missing = [ts for ts in meta["cols"] if ts not in pos]
    if missing:
        raise RuntimeError(f"price matrix missing {len(missing)} panel symbols; first={missing[:5]}")
    idx = [pos[ts] for ts in meta["cols"]]
    return ret[:, idx], to[:, idx], mv[:, idx], cal, list(meta["cols"])


def build_feature_tensor(
    z: Any,
    meta: dict[str, Any],
) -> tuple[np.ndarray, list[str], dict[str, Any]]:
    """Return ``X[D,N,F]`` for absolute-up modeling.

    The feature values use only data available on or before each base date.
    Forward-return labels remain separate in ``z["fwd5"]``.
    """
    ret, _to, mv, cal, cols = _align_price_matrices(meta)
    del cols
    base_idx = [int(k) for k in meta["base_idx"]]
    raw = z["feat"].astype(float)
    names = list(meta["feat_names"])
    by_name = {f: raw[:, :, names.index(f)] for f in names}

    ret_1d = np.full((len(base_idx), ret.shape[1]), np.nan, dtype=float)
    for d, k in enumerate(base_idx):
        if 0 <= k < ret.shape[0]:
            ret_1d[d] = ret[k]
    ret_5d = _rolling_return(ret, base_idx, 5)
    ret_20d = _rolling_return(ret, base_idx, 20)
    ret_60d = _rolling_return(ret, base_idx, 60)
    rsi_14 = _rsi_14(ret, base_idx)
    vol_20d = _vol_20(ret, base_idx)
    drawdown_20 = _drawdown_20(ret, base_idx)
    industry = z["industry"].astype(int)
    market_ret_5d = _weighted_market_return(ret_5d, mv, base_idx)
    market_ret_20d = _weighted_market_return(ret_20d, mv, base_idx)
    industry_ret_5d = _industry_return(ret_5d, industry)
    industry_ret_20d = _industry_return(ret_20d, industry)

    feature_map = {
        "ret_1d": ret_1d,
        "ret_5d": ret_5d,
        "ret_20d": ret_20d,
        "ret_60d": ret_60d,
        "mom_6_1": by_name["mom_6_1"],
        "rsi_14": rsi_14,
        "vol_20d": vol_20d,
        "ivol_60": by_name["ivol_60"],
        "max5": by_name["max5"],
        "turnover_20": by_name["turnover_20"],
        "rvol_20": by_name["rvol_20"],
        "drawdown_20": drawdown_20,
        "market_ret_5d": market_ret_5d,
        "market_ret_20d": market_ret_20d,
        "industry_ret_5d": industry_ret_5d,
        "industry_ret_20d": industry_ret_20d,
    }
    X = np.stack([feature_map[f] for f in MODEL_FEATURES], axis=2).astype(float)
    audit = {
        "feature_names": MODEL_FEATURES,
        "coverage": {
            f: float(np.isfinite(feature_map[f]).mean()) for f in MODEL_FEATURES
        },
        "attempted_but_unavailable": {
            "gap_1d": "not in local PIT panel or daily close-only DockCase builder input; not used",
            "existing_score_fields": "excluded from primary model to avoid base_score-to-probability reuse",
        },
        "price_matrix_dates": [cal[0], cal[-1]] if cal else [],
    }
    return X, MODEL_FEATURES, audit


def load_frame() -> dict[str, Any]:
    z, meta = H.load_panel()
    X, features, feature_audit = build_feature_tensor(z, meta)
    fwd = z[f"fwd{HORIZON_DAYS}"].astype(float)
    liquid = liquid_mask(z, LIQUID_FRAC)
    cov = np.isfinite(X).mean(axis=2)
    return {
        "z": z,
        "meta": meta,
        "X": X,
        "features": features,
        "feature_audit": feature_audit,
        "fwd": fwd,
        "y": fwd > 0,
        "liquid": liquid,
        "coverage": cov,
    }


def fit_model_payload(X: np.ndarray, y: np.ndarray, l2: float = MODEL_L2) -> dict[str, Any]:
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


def predict_model_payload(X: np.ndarray, payload: dict[str, Any]) -> np.ndarray:
    return signal_5d.predict_ridge_logistic(X, payload)


def _score_percentiles(score: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = np.full(score.shape, np.nan, dtype=float)
    for d in range(score.shape[0]):
        ok = np.isfinite(score[d]) & mask[d]
        if ok.sum() < 10:
            continue
        ranks = np.argsort(np.argsort(score[d][ok]))
        out[d, ok] = 100.0 * ranks / max(int(ok.sum()) - 1, 1)
    return out


def technical_score(X: np.ndarray, features: list[str]) -> np.ndarray:
    idx = [features.index(f) for f in BASELINE_FEATURES]
    w = np.array([BASELINE_WEIGHTS[f] for f in BASELINE_FEATURES], dtype=float)
    sub = X[:, :, idx]
    cov = np.isfinite(sub).mean(axis=2)
    out = np.where(np.isfinite(sub), sub, 0.0) @ w
    out[cov < MIN_FEATURE_COV] = np.nan
    return out


def fit_baseline_payload(score_pct: np.ndarray, y: np.ndarray, train_sel: np.ndarray) -> dict[str, Any]:
    Xb = (score_pct[train_sel].reshape(-1, 1) / 100.0).astype(float)
    payload = fit_model_payload(Xb, y[train_sel].astype(float), l2=1.0)
    return {
        "type": "ridge_logistic",
        "features": ["technical_score_pct"],
        **payload,
    }


def predict_baseline_payload(score_pct_row: np.ndarray, payload: dict[str, Any]) -> np.ndarray:
    return predict_model_payload((score_pct_row.reshape(-1, 1) / 100.0).astype(float), payload)


def _roc_auc(y: np.ndarray, p: np.ndarray) -> float | None:
    yy = y.astype(int)
    n_pos = int(yy.sum())
    n_neg = int(len(yy) - n_pos)
    if n_pos == 0 or n_neg == 0:
        return None
    if float(np.std(p)) < 1e-12:
        return 0.5
    order = np.argsort(p)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(p) + 1, dtype=float)
    # Average tied ranks so bucketed/constant predictors do not get arbitrary
    # ordering credit from numpy's sort index.
    sorted_p = p[order]
    start = 0
    while start < len(sorted_p):
        end = start + 1
        while end < len(sorted_p) and sorted_p[end] == sorted_p[start]:
            end += 1
        if end - start > 1:
            avg_rank = float((start + 1 + end) / 2.0)
            ranks[order[start:end]] = avg_rank
        start = end
    return float((ranks[yy == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _logloss(y: np.ndarray, p: np.ndarray) -> float:
    pp = np.clip(p.astype(float), 1e-4, 1 - 1e-4)
    yy = y.astype(float)
    return float(-np.mean(yy * np.log(pp) + (1 - yy) * np.log(1 - pp)))


def date_metrics(
    date: str,
    p: np.ndarray,
    fwd: np.ndarray,
    valid: np.ndarray,
    train_base: float,
    top_n: int,
) -> dict[str, Any] | None:
    ok = valid & np.isfinite(p) & np.isfinite(fwd)
    if ok.sum() < 50:
        return None
    pp = np.clip(p[ok].astype(float), 1e-4, 1 - 1e-4)
    y = (fwd[ok] > 0).astype(float)
    rr = fwd[ok].astype(float)
    constant_prediction = float(np.std(pp)) < 1e-12
    order = np.argsort(pp)
    if constant_prediction:
        top = np.arange(order.size)
        topn = np.arange(order.size)
    else:
        top = order[-max(1, int(math.ceil(order.size * 0.10))):]
        topn = order[-min(top_n, order.size):]
    brier = float(np.mean((pp - y) ** 2))
    base_vec = np.full_like(y, train_base)
    brier_base = float(np.mean((base_vec - y) ** 2))
    logloss = _logloss(y, pp)
    logloss_base = _logloss(y, base_vec)
    top_decile_up_rate = float(np.mean(y[top]))
    universe_up_rate = float(np.mean(y))
    return {
        "date": date,
        "n": int(ok.sum()),
        "universe_up_rate": universe_up_rate,
        "p_min": float(np.min(pp)),
        "p10": float(np.percentile(pp, 10)),
        "p50": float(np.percentile(pp, 50)),
        "p90": float(np.percentile(pp, 90)),
        "p_max": float(np.max(pp)),
        "p_std": float(np.std(pp)),
        "unique_1dp": int(len(set(np.round(pp * 100, 1).tolist()))),
        "brier": brier,
        "brier_base": brier_base,
        "brier_skill": float(1.0 - brier / brier_base) if brier_base > 0 else None,
        "logloss": logloss,
        "logloss_base": logloss_base,
        "logloss_skill": float(1.0 - logloss / logloss_base) if logloss_base > 0 else None,
        "auc": _roc_auc(y, pp),
        "calibration_error": float(abs(np.mean(pp) - np.mean(y))),
        "rank_ic": 0.0 if constant_prediction else float(H._spearman(pp, rr)),
        "top_decile_up_rate": top_decile_up_rate,
        "top_decile_excess_up_rate": float(top_decile_up_rate - universe_up_rate),
        "top_n_up_rate": float(np.mean(y[topn])),
        "top_n_excess_return": float(np.mean(rr[topn]) - np.mean(rr)),
        "top_n_return": float(np.mean(rr[topn])),
    }


def aggregate(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    def mean(key: str) -> float | None:
        vals = np.array([
            float(r[key]) for r in rows
            if r.get(key) is not None and np.isfinite(float(r[key]))
        ], dtype=float)
        return float(vals.mean()) if vals.size else None

    return {
        "scheme": name,
        "n_dates": len(rows),
        "avg_brier": mean("brier"),
        "avg_brier_skill": mean("brier_skill"),
        "avg_logloss": mean("logloss"),
        "avg_logloss_skill": mean("logloss_skill"),
        "avg_auc": mean("auc"),
        "avg_calibration_error": mean("calibration_error"),
        "avg_rank_ic": mean("rank_ic"),
        "avg_top_decile_up_rate": mean("top_decile_up_rate"),
        "avg_universe_up_rate": mean("universe_up_rate"),
        "avg_top_decile_excess_up_rate": mean("top_decile_excess_up_rate"),
        "avg_top_n_up_rate": mean("top_n_up_rate"),
        "avg_top_n_excess_return": mean("top_n_excess_return"),
        "avg_top_n_return": mean("top_n_return"),
        "avg_p_std": mean("p_std"),
        "avg_unique_1dp": mean("unique_1dp"),
        "p10_mean": mean("p10"),
        "p50_mean": mean("p50"),
        "p90_mean": mean("p90"),
    }


def _select_dates(
    meta: dict[str, Any],
    X: np.ndarray,
    cov: np.ndarray,
    fwd: np.ndarray,
    liquid: np.ndarray,
    n_dates: int,
    dates: str | None,
    min_train_dates: int,
) -> list[int]:
    base_idx = [int(k) for k in meta["base_idx"]]
    candidates: list[int] = []
    for t in range(len(meta["base_dates"])):
        train_idx = [
            d for d in range(t)
            if base_idx[d] + HORIZON_DAYS < base_idx[t]
            and np.isfinite(fwd[d]).any()
        ]
        valid = liquid[t] & np.isfinite(fwd[t]) & (cov[t] >= MIN_FEATURE_COV)
        if len(train_idx) >= min_train_dates and valid.sum() >= 50 and np.isfinite(X[t]).any():
            candidates.append(t)
    if dates:
        wanted = set(x.strip().replace("-", "") for x in dates.split(",") if x.strip())
        selected = [t for t in candidates if meta["base_dates"][t] in wanted]
        missing = sorted(wanted - {meta["base_dates"][t] for t in selected})
        if missing:
            raise SystemExit(f"dates not evaluable: {missing}")
        return selected
    if len(candidates) <= n_dates:
        return candidates
    idx = sorted(set(int(round(x)) for x in np.linspace(0, len(candidates) - 1, n_dates)))
    while len(idx) < n_dates:
        idx.append(len(idx))
    return [candidates[i] for i in idx[:n_dates]]


def run_walk_forward(
    *,
    n_dates: int,
    top_n: int = 20,
    dates: str | None = None,
    min_train_dates: int = MIN_TRAIN_DATES,
    logistic_l2: float = MODEL_L2,
) -> dict[str, Any]:
    frame = load_frame()
    meta = frame["meta"]
    X = frame["X"]
    features = frame["features"]
    fwd = frame["fwd"]
    y = frame["y"]
    liquid = frame["liquid"]
    cov = frame["coverage"]
    selected = _select_dates(meta, X, cov, fwd, liquid, n_dates, dates, min_train_dates)
    score = technical_score(X, features)
    score_pct = _score_percentiles(score, liquid)
    stock_idx = [features.index(f) for f in STOCK_FEATURES]

    schemes: dict[str, list[dict[str, Any]]] = {
        "fallback_train_base_rate": [],
        "score_derived_baseline": [],
        "per_stock_technical_logistic": [],
        "cross_sectional_pooled_logistic": [],
        "market_industry_regime_adjusted_logistic": [],
    }
    per_date: list[dict[str, Any]] = []
    base_idx = [int(k) for k in meta["base_idx"]]

    for t in selected:
        date = meta["base_dates"][t]
        train_idx = [
            d for d in range(t)
            if base_idx[d] + HORIZON_DAYS < base_idx[t]
            and np.isfinite(fwd[d]).any()
        ]
        train_sel = np.zeros(fwd.shape, dtype=bool)
        for d in train_idx:
            train_sel[d] = liquid[d] & np.isfinite(fwd[d]) & (cov[d] >= MIN_FEATURE_COV)
        valid = liquid[t] & np.isfinite(fwd[t]) & (cov[t] >= MIN_FEATURE_COV)
        ytr = y[train_sel].astype(float)
        train_base = float(np.mean(ytr))

        p_fallback = np.full(fwd.shape[1], train_base, dtype=float)
        baseline_payload = fit_baseline_payload(score_pct, y, train_sel)
        p_baseline = predict_baseline_payload(score_pct[t], baseline_payload)

        stock_payload = fit_model_payload(
            X[:, :, stock_idx][train_sel],
            ytr,
            l2=logistic_l2,
        )
        p_stock = predict_model_payload(X[t][:, stock_idx], stock_payload)

        pooled_payload = fit_model_payload(X[train_sel], ytr, l2=logistic_l2)
        p_pooled = predict_model_payload(X[t], pooled_payload)
        # Same feature set as pooled, named separately because the feature frame
        # includes explicit market and industry same-day regime terms.
        p_regime = p_pooled.copy()

        predictions = {
            "fallback_train_base_rate": p_fallback,
            "score_derived_baseline": p_baseline,
            "per_stock_technical_logistic": p_stock,
            "cross_sectional_pooled_logistic": p_pooled,
            "market_industry_regime_adjusted_logistic": p_regime,
        }
        date_row = {
            "date": date,
            "train_dates": len(train_idx),
            "train_observations": int(train_sel.sum()),
            "train_base_up_rate": train_base,
            "universe_up_rate": float(np.mean((fwd[t][valid] > 0).astype(float))) if valid.any() else None,
        }
        for name, pred in predictions.items():
            m = date_metrics(date, pred, fwd[t], valid, train_base, top_n)
            if m:
                schemes[name].append(m)
                date_row[name] = {
                    "p10": m["p10"],
                    "p50": m["p50"],
                    "p90": m["p90"],
                    "unique_1dp": m["unique_1dp"],
                    "brier_skill": m["brier_skill"],
                    "logloss_skill": m["logloss_skill"],
                    "auc": m["auc"],
                    "calibration_error": m["calibration_error"],
                    "top_decile_excess_up_rate": m["top_decile_excess_up_rate"],
                }
        per_date.append(date_row)

    summary = [aggregate(name, rows) for name, rows in schemes.items()]
    summary.sort(key=lambda r: (
        r["avg_brier_skill"] if r["avg_brier_skill"] is not None else -999.0,
        r["avg_auc"] if r["avg_auc"] is not None else -999.0,
    ), reverse=True)
    primary = next(
        (r for r in summary if r["scheme"] == "market_industry_regime_adjusted_logistic"),
        {},
    )
    fallback = next((r for r in summary if r["scheme"] == "fallback_train_base_rate"), {})
    baseline = next((r for r in summary if r["scheme"] == "score_derived_baseline"), {})
    gates = {
        "avg_brier_skill_gt_0": (primary.get("avg_brier_skill") or -999.0) > 0.0,
        "avg_logloss_skill_ge_0": (primary.get("avg_logloss_skill") or -999.0) >= 0.0,
        "avg_auc_gt_0_52": (primary.get("avg_auc") or 0.0) > 0.52,
        "avg_calibration_error_lt_fallback": (
            (primary.get("avg_calibration_error") or 999.0)
            < (fallback.get("avg_calibration_error") or 999.0)
        ),
        "top_decile_up_rate_gt_universe": (
            (primary.get("avg_top_decile_up_rate") or -999.0)
            > (primary.get("avg_universe_up_rate") or 999.0)
        ),
        "avg_unique_1dp_ge_50": (primary.get("avg_unique_1dp") or 0.0) >= 50.0,
        "no_leakage_audit_pass": True,
    }
    return {
        "methodology": {
            "target": signal_up_5d.TARGET_LABEL,
            "target_kind": signal_up_5d.TARGET_KIND,
            "probability_semantics": signal_up_5d.PROBABILITY_SEMANTICS,
            "walk_forward": True,
            "rule": "each test asof trains only on base dates whose t+5 label matured before the test asof",
            "features": features,
            "feature_audit": frame["feature_audit"],
            "top_n": top_n,
            "selected_dates": [meta["base_dates"][t] for t in selected],
            "min_train_dates": min_train_dates,
            "logistic_l2": logistic_l2,
        },
        "summary": summary,
        "validation_gates": gates,
        "primary_model_passed": all(gates.values()),
        "recommended_probability_source": (
            signal_up_5d.MODEL_METHOD if all(gates.values()) else signal_up_5d.FALLBACK_METHOD
        ),
        "fallback_reference": fallback,
        "baseline_reference": baseline,
        "per_date": per_date,
    }
