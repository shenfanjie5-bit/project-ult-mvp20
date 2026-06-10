#!/usr/bin/env python3
"""Walk-forward fit + portfolio-P&L evaluation harness (ISOLATED, read-only).

This module owns ALL leakage-critical logic so that model experiments can only
vary the *hypothesis*, never the PIT discipline:

  * Neutralization is per-date cross-sectional: winsorize -> z -> regress out
    [intercept, ln_mv, industry dummies] -> rank-z.  (no time leak)
  * Walk-forward: a model predicting date t is fit ONLY on base dates < t.
  * Labels are forward returns taken strictly after the base day.
  * Headline significance is reported on a NON-overlapping date subsample for
    the horizon (step >= horizon) AND via a date-level block bootstrap, because
    overlapping windows reuse the same universe and fake independence.

Evaluation is portfolio P&L, NOT just IC:
  decile means + D10-D1 spread, TOP-decile absolute fwd return and its excess
  over the universe / market, monotonicity, by-year & by-regime splits, tails,
  all with bootstrap CIs across dates.

CLI:
  harness.py --config cfg.json --horizon 10 --out report.json
A config is {"name":..., "method": ew_signed|ic_weighted|ridge|enet|gbdt,
             "features": [...], "params": {...}, "min_train_dates": 12,
             "lookback_dates": null|int, "regime_gate": null|{...}}
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.getcwd())
HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20260609
rng_global = np.random.default_rng(SEED)

# economic sign priors (for ew_signed and IC sanity). + = higher feature -> higher fwd ret
SIGN_PRIOR = {
    "ep_ttm": +1, "bp": +1, "sp_ttm": +1, "dy": +1,
    "roe": +1, "roa": +1, "gpm": +1, "npm": +1, "debt_assets": -1, "asset_turn": +1, "q_roe": +1,
    "sue": +1, "npq_yoy": +1,
    "mom_6_1": +1, "mom_12_1": +1, "strev": +1, "strev_adj": +1,
    "rvol_20": -1, "rvol_60": -1, "ivol_60": -1, "beta_60": -1, "max5": -1,
    "turnover_20": -1, "turnover_trend": -1, "amihud": +1, "ln_mv": -1,
}


# ----------------------------------------------------------------------------
# load + neutralize
# ----------------------------------------------------------------------------
def load_panel(path=None):
    path = path or os.path.join(HERE, "panel.npz")
    z = np.load(path)
    meta = json.load(open(os.path.join(os.path.dirname(path), "panel_meta.json")))
    return z, meta


def _winsor_z(v, lo=1, hi=99):
    """cross-sectional winsorize to [lo,hi] pct then z-score; NaN preserved."""
    out = np.full_like(v, np.nan, dtype=np.float64)
    ok = np.isfinite(v)
    if ok.sum() < 10:
        return out
    x = v[ok].astype(np.float64)
    a, b = np.percentile(x, [lo, hi])
    x = np.clip(x, a, b)
    mu, sd = x.mean(), x.std(ddof=1)
    if sd <= 0:
        return out
    out[ok] = (x - mu) / sd
    return out


def _rank_z(v):
    """cross-sectional rank -> standard-normal-ish z (NaN preserved)."""
    out = np.full_like(v, np.nan, dtype=np.float64)
    ok = np.isfinite(v)
    nz = int(ok.sum())
    if nz < 10:
        return out
    x = v[ok]
    order = np.argsort(np.argsort(x))            # 0..nz-1 ranks
    u = (order + 1.0) / (nz + 1.0)               # (0,1)
    out[ok] = u
    # to centered z-ish
    out[ok] = (u - 0.5) * np.sqrt(12.0)          # uniform var->1
    return out


def neutralize(z, meta, cache=True):
    """Return Z [D,N,F]: each raw feature winsor-z, residualized on
    [1, ln_mv, industry dummies], then rank-z. Cached to neutral.npz."""
    cpath = os.path.join(HERE, "neutral.npz")
    if cache and os.path.exists(cpath):
        c = np.load(cpath, allow_pickle=False)
        if c["feat"].shape == z["feat"].shape:
            return c["feat"]
    feat = z["feat"].astype(np.float64)          # D,N,F
    lnmv = z["ln_mv"].astype(np.float64)         # D,N
    ind = z["industry"].astype(int)              # N
    D, N, F = feat.shape
    ind_u = sorted(set(int(i) for i in ind if i >= 0))
    # industry dummy matrix (N x K), drop-one handled by intercept
    Dind = np.zeros((N, len(ind_u)), dtype=np.float64)
    for kk, code in enumerate(ind_u):
        Dind[:, kk] = (ind == code).astype(float)
    Z = np.full((D, N, F), np.nan, np.float64)
    for d in range(D):
        mv = lnmv[d]
        for fi in range(F):
            v = _winsor_z(feat[d, :, fi])
            ok = np.isfinite(v) & np.isfinite(mv)
            if ok.sum() < 20:
                Z[d, :, fi] = _rank_z(v)
                continue
            # design: intercept, ln_mv, industry dummies (only present rows)
            Xcols = [np.ones(ok.sum()), mv[ok]]
            di = Dind[ok]
            # keep industries present
            keep = di.sum(0) > 0
            di = di[:, keep]
            X = np.column_stack(Xcols + [di])
            y = v[ok]
            try:
                beta, *_ = np.linalg.lstsq(X, y, rcond=None)
                resid = y - X @ beta
            except Exception:
                resid = y - y.mean()
            rv = np.full(N, np.nan)
            rv[ok] = resid
            Z[d, :, fi] = _rank_z(rv)
    if cache:
        np.savez_compressed(cpath, feat=Z.astype(np.float32))
    return Z


# ----------------------------------------------------------------------------
# model fitters (each returns a score vector for the test cross-section)
# ----------------------------------------------------------------------------
def _select(meta, features):
    names = meta["feat_names"]
    idx = [names.index(f) for f in features]
    return idx


def _impute0_coverage(Xtest, min_cov=0.5):
    """impute NaN->0 (neutral) but drop rows below min feature coverage."""
    cov = np.isfinite(Xtest).mean(1)
    keep = cov >= min_cov
    Xi = np.where(np.isfinite(Xtest), Xtest, 0.0)
    return Xi, keep


def fit_ew_signed(Ztr, ytr, Zte, feats, params, ctx=None):
    signs = np.array([SIGN_PRIOR.get(f, +1) for f in feats], dtype=float)
    Xi, keep = _impute0_coverage(Zte, params.get("min_cov", 0.5))
    score = Xi @ signs
    score[~keep] = np.nan
    return score


def _ic_weights(Ztr, ytr, hl=None, sign_only=False, dates_mask=None):
    """per-feature trailing mean rank-IC over (optionally masked) train dates."""
    Dtr = Ztr.shape[0]
    w = np.zeros(Ztr.shape[2])
    for fi in range(Ztr.shape[2]):
        ics, wts = [], []
        for d in range(Dtr):
            if dates_mask is not None and not dates_mask[d]:
                continue
            x = Ztr[d, :, fi]; y = ytr[d]
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() < 30:
                continue
            ic = _spearman(x[ok], y[ok])
            if np.isfinite(ic):
                decay = 1.0 if hl is None else 0.5 ** ((Dtr - 1 - d) / hl)
                ics.append(ic * decay); wts.append(decay)
        if wts:
            w[fi] = sum(ics) / sum(wts)
    if sign_only:
        w = np.sign(w)
    return w


def fit_ic_weighted(Ztr, ytr, Zte, feats, params, ctx=None):
    """weights = trailing mean per-date rank-IC over train dates (optional decay)."""
    w = _ic_weights(Ztr, ytr, params.get("halflife"), params.get("sign_only", False))
    Xi, keep = _impute0_coverage(Zte, params.get("min_cov", 0.5))
    score = Xi @ w
    score[~keep] = np.nan
    return score


def fit_ic_weighted_regime(Ztr, ytr, Zte, feats, params, ctx=None):
    """regime-conditioned IC weighting: weights estimated on train dates matching
    the TEST date's regime; blended with all-date weights to avoid tiny-sample
    overfit (shrinkage). Walk-forward safe (only train dates < test)."""
    if ctx is None:
        return fit_ic_weighted(Ztr, ytr, Zte, feats, params)
    tr_reg = np.array(ctx["train_reg"]); test_reg = ctx["test_reg"]
    mask = (tr_reg == test_reg)
    w_all = _ic_weights(Ztr, ytr, params.get("halflife"))
    shrink = params.get("shrink", 0.5)
    if mask.sum() >= params.get("min_regime_dates", 6):
        w_reg = _ic_weights(Ztr, ytr, params.get("halflife"), dates_mask=mask)
        w = shrink * w_reg + (1 - shrink) * w_all
    else:
        w = w_all
    Xi, keep = _impute0_coverage(Zte, params.get("min_cov", 0.5))
    score = Xi @ w
    score[~keep] = np.nan
    return score


def _pool(Ztr, ytr):
    """stack train dates: per-date rank target y in [-0.5,0.5]; NaN rows dropped."""
    Xs, ys = [], []
    for d in range(Ztr.shape[0]):
        y = ytr[d]
        oky = np.isfinite(y)
        if oky.sum() < 30:
            continue
        yy = y[oky]
        r = np.argsort(np.argsort(yy)) / (len(yy) - 1) - 0.5  # per-date centered rank
        X = Ztr[d][oky]
        Xs.append(X)
        ys.append(r)
    if not Xs:
        return None, None
    return np.vstack(Xs), np.concatenate(ys)


def fit_linear(Ztr, ytr, Zte, feats, params, ctx=None, kind="ridge"):
    from sklearn.linear_model import Ridge, ElasticNet
    Xtr, rtr = _pool(Ztr, ytr)
    if Xtr is None:
        return np.full(Zte.shape[0], np.nan)
    Xtr = np.where(np.isfinite(Xtr), Xtr, 0.0)
    if kind == "ridge":
        mdl = Ridge(alpha=params.get("alpha", 10.0))
    else:
        mdl = ElasticNet(alpha=params.get("alpha", 0.01), l1_ratio=params.get("l1_ratio", 0.3), max_iter=5000)
    mdl.fit(Xtr, rtr)
    Xi, keep = _impute0_coverage(Zte, params.get("min_cov", 0.5))
    score = mdl.predict(Xi)
    score[~keep] = np.nan
    return score


def fit_gbdt(Ztr, ytr, Zte, feats, params, ctx=None):
    import lightgbm as lgb
    Xtr, rtr = _pool(Ztr, ytr)
    if Xtr is None or len(rtr) < 500:
        return np.full(Zte.shape[0], np.nan)
    # early-stop on the LAST 20% of train dates (still strictly < test date)
    cut = int(Ztr.shape[0] * 0.8)
    Xv, rv = _pool(Ztr[cut:], ytr[cut:])
    Xt, rt = _pool(Ztr[:cut], ytr[:cut])
    if Xt is None or Xv is None or len(rt) < 300:
        Xt, rt, Xv, rv = Xtr, rtr, None, None
    mdl = lgb.LGBMRegressor(
        n_estimators=params.get("n_estimators", 400),
        num_leaves=params.get("num_leaves", 15),
        max_depth=params.get("max_depth", 4),
        learning_rate=params.get("lr", 0.03),
        min_child_samples=params.get("min_child", 200),
        subsample=params.get("subsample", 0.7), subsample_freq=1,
        colsample_bytree=params.get("colsample", 0.7),
        reg_lambda=params.get("reg_lambda", 5.0),
        random_state=SEED, n_jobs=2, verbose=-1,
    )
    if Xv is not None:
        mdl.fit(Xt, rt, eval_set=[(Xv, rv)],
                callbacks=[lgb.early_stopping(40, verbose=False), lgb.log_evaluation(0)])
    else:
        mdl.fit(Xtr, rtr)
    score = mdl.predict(np.where(np.isfinite(Zte), Zte, np.nan))  # lgb handles NaN
    cov = np.isfinite(Zte).mean(1)
    score[cov < params.get("min_cov", 0.5)] = np.nan
    return np.asarray(score)


FITTERS = {
    "ew_signed": fit_ew_signed,
    "ic_weighted": fit_ic_weighted,
    "ic_weighted_regime": fit_ic_weighted_regime,
    "ridge": lambda *a: fit_linear(*a, kind="ridge"),
    "enet": lambda *a: fit_linear(*a, kind="enet"),
    "gbdt": fit_gbdt,
}


# ----------------------------------------------------------------------------
# metrics
# ----------------------------------------------------------------------------
def _spearman(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    if x.size < 5:
        return np.nan
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    rx -= rx.mean(); ry -= ry.mean()
    den = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float((rx * ry).sum() / den) if den > 0 else np.nan


def _deciles(score, ret, k=10):
    ok = np.isfinite(score) & np.isfinite(ret)
    s, r = score[ok], ret[ok]
    if s.size < k * 3:
        return None
    order = np.argsort(s)
    groups = np.array_split(order, k)
    means = np.array([r[g].mean() for g in groups])
    return means  # D1..Dk


def walk_forward(Z, fwd, meta, config):
    feats = list(config["features"])
    idx = _select(meta, feats)
    Zf = Z[:, :, idx]                            # D,N,Fsel
    D, N = Zf.shape[0], Z.shape[1]
    regs = [r["regime"] for r in meta["regimes"]]
    # optional: append market trend/vol as constant-per-date columns so tree/
    # linear models can learn regime-conditional factor use (cross-sectionally
    # constant -> harmless to IC methods).
    if config.get("regime_feature"):
        tr = np.array([r["trend60"] for r in meta["regimes"]], float)
        vo = np.array([r["vol20"] for r in meta["regimes"]], float)
        tr = (tr - np.nanmean(tr)) / (np.nanstd(tr) + 1e-9)
        vo = (vo - np.nanmean(vo)) / (np.nanstd(vo) + 1e-9)
        ext = np.stack([np.repeat(tr[:, None], N, 1), np.repeat(vo[:, None], N, 1)], axis=2)
        Zf = np.concatenate([Zf, ext], axis=2)
        feats = feats + ["_mkt_trend", "_mkt_vol"]
    min_train = config.get("min_train_dates", 12)
    lookback = config.get("lookback_dates", None)
    method = config["method"]
    fitter = FITTERS[method]
    params = config.get("params", {})
    scores = np.full((D, N), np.nan)
    for t in range(D):
        if t < min_train:
            continue
        lo = 0 if not lookback else max(0, t - lookback)
        Ztr = Zf[lo:t]; ytr = fwd[lo:t]; Zte = Zf[t]
        ctx = {"train_reg": regs[lo:t], "test_reg": regs[t], "test_idx": t}
        try:
            sc = fitter(Ztr, ytr, Zte, feats, params, ctx)
        except Exception as e:
            sc = np.full(N, np.nan)
            if t == min_train:
                print(f"  [warn] fitter {method} failed: {e}", file=sys.stderr)
        scores[t] = sc
    return scores


def evaluate(scores, fwd, meta, horizon, mkt_fwd=None, eval_mask=None,
             drop_regime=None, drop_year=None):
    """portfolio P&L report across test dates (those with finite scores)."""
    D, N = scores.shape
    regimes = meta["regimes"]
    base_dates = meta["base_dates"]
    per_date = []
    for d in range(D):
        if drop_regime and regimes[d]["regime"] == drop_regime:
            continue
        if drop_year and base_dates[d][:4] == str(drop_year):
            continue
        sc = scores[d]
        rt = fwd[d]
        if eval_mask is not None:
            m = eval_mask[d]
            sc = np.where(m, sc, np.nan)
        ok = np.isfinite(sc) & np.isfinite(rt)
        if ok.sum() < 50:
            continue
        ic = _spearman(sc[ok], rt[ok])
        dec = _deciles(sc, rt, 10)
        uni_mean = float(np.nanmean(rt[ok]))
        rec = {"date": base_dates[d], "n": int(ok.sum()), "ic": ic,
               "uni_mean": uni_mean, "regime": regimes[d]["regime"],
               "year": base_dates[d][:4], "mkt_fwd": regimes[d].get("mkt_fwd10")}
        if dec is not None:
            rec["deciles"] = dec.tolist()
            rec["d10_d1"] = float(dec[-1] - dec[0])
            rec["top"] = float(dec[-1])
            rec["top_excess_uni"] = float(dec[-1] - uni_mean)
            # top-decile hit rate
            order = np.argsort(np.where(np.isfinite(sc), sc, -np.inf))
            top = order[-max(1, ok.sum() // 10):]
            tr = rt[top]; tr = tr[np.isfinite(tr)]
            rec["top_hit"] = float((tr > 0).mean()) if tr.size else np.nan
            rec["top_abs"] = float(tr.mean()) if tr.size else np.nan
        per_date.append(rec)
    return _aggregate(per_date, horizon)


def _boot_ci(vals, nb=5000, z=95):
    v = np.asarray([x for x in vals if np.isfinite(x)], float)
    if v.size < 3:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(SEED)
    bs = np.array([rng.choice(v, v.size, replace=True).mean() for _ in range(nb)])
    lo, hi = (100 - z) / 2, 100 - (100 - z) / 2
    return (float(np.percentile(bs, lo)), float(np.percentile(bs, hi)))


def _agg_block(per_date, key):
    vals = [r[key] for r in per_date if key in r and np.isfinite(r.get(key, np.nan))]
    if not vals:
        return None
    arr = np.array(vals, float)
    mean = float(arr.mean())
    se = float(arr.std(ddof=1) / np.sqrt(arr.size)) if arr.size > 1 else float("nan")
    t = mean / se if (se and np.isfinite(se) and se > 0) else float("nan")
    return {"mean": mean, "se": se, "t": t, "n_dates": int(arr.size),
            "pct_pos": float((arr > 0).mean()), "ci": _boot_ci(vals),
            "worst": float(arr.min()), "best": float(arr.max())}


def _aggregate(per_date, horizon):
    if not per_date:
        return {"error": "no evaluable dates"}
    out = {"horizon": horizon, "n_test_dates": len(per_date)}
    out["ic"] = _agg_block(per_date, "ic")
    out["d10_d1"] = _agg_block(per_date, "d10_d1")
    out["top_excess_uni"] = _agg_block(per_date, "top_excess_uni")
    out["top_abs"] = _agg_block(per_date, "top_abs")
    out["top_hit"] = _agg_block(per_date, "top_hit")
    # mean decile curve + monotonicity
    decs = np.array([r["deciles"] for r in per_date if "deciles" in r])
    if decs.size:
        mc = decs.mean(0)
        out["decile_curve"] = mc.tolist()
        out["decile_monotone_pairs"] = int(np.sum(np.diff(mc) > 0))
        out["decile_spearman"] = _spearman(np.arange(len(mc)), mc)
    # by year
    out["by_year"] = {}
    for y in sorted(set(r["year"] for r in per_date)):
        sub = [r for r in per_date if r["year"] == y]
        out["by_year"][y] = {"n": len(sub),
                             "d10_d1": _agg_block(sub, "d10_d1"),
                             "top_excess_uni": _agg_block(sub, "top_excess_uni"),
                             "ic": _agg_block(sub, "ic")}
    # by regime
    out["by_regime"] = {}
    for g in sorted(set(r["regime"] for r in per_date)):
        sub = [r for r in per_date if r["regime"] == g]
        out["by_regime"][g] = {"n": len(sub),
                               "d10_d1": _agg_block(sub, "d10_d1"),
                               "top_excess_uni": _agg_block(sub, "top_excess_uni"),
                               "ic": _agg_block(sub, "ic")}
    # tails
    worst = sorted([r for r in per_date if "d10_d1" in r], key=lambda r: r["d10_d1"])[:3]
    out["worst_dates_d10_d1"] = [{"date": r["date"], "d10_d1": r["d10_d1"],
                                  "regime": r["regime"], "ic": r["ic"]} for r in worst]
    worst_top = sorted([r for r in per_date if "top_excess_uni" in r], key=lambda r: r["top_excess_uni"])[:3]
    out["worst_dates_top_excess"] = [{"date": r["date"], "top_excess_uni": r["top_excess_uni"],
                                      "regime": r["regime"]} for r in worst_top]
    out["per_date"] = per_date
    return out


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def run_config(config, horizon=10, nonoverlap=False, shuffle=None,
               drop_regime=None, drop_year=None):
    z, meta = load_panel()
    Z = neutralize(z, meta)
    fwd = z[f"fwd{horizon}"].astype(np.float64).copy()
    if shuffle is not None:
        # NULL test: permute labels WITHIN each date (train+eval) -> any surviving
        # OOS edge implies leakage / overfit-to-noise, not real signal.
        rng = np.random.default_rng(int(shuffle))
        for d in range(fwd.shape[0]):
            ok = np.where(np.isfinite(fwd[d]))[0]
            if ok.size > 1:
                fwd[d, ok] = fwd[d, ok][rng.permutation(ok.size)]
    scores = walk_forward(Z, fwd, meta, config)
    rep_all = evaluate(scores, fwd, meta, horizon, drop_regime=drop_regime, drop_year=drop_year)
    out = {"config": config, "horizon": horizon, "full": rep_all,
           "shuffle": shuffle, "drop_regime": drop_regime, "drop_year": drop_year}
    if nonoverlap:
        # non-overlapping subsample for headline significance: keep every
        # ceil(horizon/step) th test date
        step = meta["step"]
        every = max(1, int(np.ceil(horizon / step)))
        D = scores.shape[0]
        keep = np.zeros(D, bool)
        keep[::every] = True
        sc2 = np.where(keep[:, None], scores, np.nan)
        out["nonoverlap"] = evaluate(sc2, fwd, meta, horizon)
        out["nonoverlap"]["subsample_every"] = every
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--out", default=None)
    ap.add_argument("--nonoverlap", action="store_true")
    ap.add_argument("--shuffle", type=int, default=None)
    ap.add_argument("--drop-regime", default=None)
    ap.add_argument("--drop-year", default=None)
    a = ap.parse_args()
    cfg = json.load(open(a.config)) if os.path.exists(a.config) else json.loads(a.config)
    res = run_config(cfg, a.horizon, a.nonoverlap, shuffle=a.shuffle,
                     drop_regime=a.drop_regime, drop_year=a.drop_year)
    # drop the verbose per_date for stdout brevity
    summ = {k: v for k, v in res.items()}
    if a.out:
        json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1)
    f = res["full"]
    print(json.dumps({
        "name": cfg.get("name"), "method": cfg["method"], "horizon": a.horizon,
        "n_test_dates": f.get("n_test_dates"),
        "ic": f.get("ic", {}).get("mean") if f.get("ic") else None,
        "d10_d1": f.get("d10_d1"),
        "top_excess_uni": f.get("top_excess_uni"),
        "decile_monotone_pairs": f.get("decile_monotone_pairs"),
        "decile_curve": [round(x, 4) for x in f.get("decile_curve", [])],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
