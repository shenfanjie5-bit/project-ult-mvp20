#!/usr/bin/env python3
"""涨幅预测分数 calibration layer (ISOLATED, read-only research).

Turns the validated cross-sectional *ranking* score into per-stock ABSOLUTE
forecasts: P(up over h days), expected return, quantile band, and
E[gain | up] — all walk-forward (a date's mapping is fit ONLY on earlier
dates), so the calibration itself cannot leak.

Architecture
  rank layer  : harness.walk_forward(config)  -> score[D,N]   (already audited)
  calib layer : per train date, bin the liquid cross-section into K score-rank
                bins; pool each bin's realized fwd returns across train dates
                (optionally regime-matched with shrinkage); a test stock in
                bin b gets the pooled bin distribution as its forecast.
  eval layer  : reliability / Brier skill vs unconditional base rate,
                within-date discrimination (top-vs-bottom predicted-P bins),
                quantile interval coverage, date-vs-stock variance split.

Honesty notes baked into the design:
  * Absolute P(up) at +h is dominated by the MARKET move over [t, t+h], which
    is unknowable at t. The calibrated level can only reflect the train-period
    base rate (optionally regime-conditional); the per-stock DIFFERENTIATION
    around that level is what the rank layer adds. eval reports both.
  * Pooling raw returns across train dates is intentional: the band must carry
    market uncertainty, not just idiosyncratic spread.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.getcwd())
from factor_research.model import harness as H  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
K_BINS = 10
QS = (10, 25, 50, 75, 90)


# ----------------------------------------------------------------------------
# masks / bins
# ----------------------------------------------------------------------------
def liquid_mask(z, frac=0.70):
    """per-date mask keeping the largest `frac` by ln_mv (investable universe;
    the prior study showed the sub-30% microcap tail is an uninvestable trap)."""
    lnmv = z["ln_mv"].astype(np.float64)
    D, N = lnmv.shape
    m = np.zeros((D, N), bool)
    for d in range(D):
        v = lnmv[d]
        ok = np.isfinite(v)
        if ok.sum() < 50:
            continue
        thr = np.percentile(v[ok], 100 * (1 - frac))
        m[d] = ok & (v >= thr)
    return m


def score_bins(score_row, mask_row, k=K_BINS):
    """per-date equal-count score-rank bins over the masked cross-section.
    Returns int bin 0..k-1 (or -1 where unscored/unmasked)."""
    out = np.full(score_row.shape, -1, np.int32)
    ok = np.isfinite(score_row) & mask_row
    n = int(ok.sum())
    if n < k * 3:
        return out
    r = np.argsort(np.argsort(score_row[ok]))          # 0..n-1
    out[ok] = np.minimum((r * k) // n, k - 1)
    return out


# ----------------------------------------------------------------------------
# fit: pooled per-bin distributions from train dates
# ----------------------------------------------------------------------------
def _bin_stats(rets):
    r = np.asarray(rets, float)
    r = r[np.isfinite(r)]
    if r.size < 30:
        return None
    up = r > 0
    st = {
        "n": int(r.size),
        "p_up": float(up.mean()),
        "mean": float(r.mean()),
        "mean_up": float(r[up].mean()) if up.sum() >= 5 else float("nan"),
        "mean_down": float(r[~up].mean()) if (~up).sum() >= 5 else float("nan"),
    }
    for q in QS:
        st[f"q{q}"] = float(np.percentile(r, q))
    return st


def fit_bins(scores, fwd, mask, train_idx, regimes=None, test_regime=None,
             min_regime_dates=6, shrink=0.5, k=K_BINS):
    """Pool per-bin forward returns over train dates.

    If `regimes`/`test_regime` given and enough same-regime train dates exist,
    each bin's stats are a shrink-blend of regime-matched and all-date pools
    (blend on the STATS, sample-size-aware via the shrink weight)."""
    pool_all = [[] for _ in range(k)]
    pool_reg = [[] for _ in range(k)]
    n_reg_dates = 0
    for d in train_idx:
        b = score_bins(scores[d], mask[d], k)
        r = fwd[d]
        same = regimes is not None and test_regime is not None and regimes[d] == test_regime
        if same:
            n_reg_dates += 1
        for bi in range(k):
            sel = (b == bi) & np.isfinite(r)
            if sel.any():
                vals = r[sel].tolist()
                pool_all[bi].extend(vals)
                if same:
                    pool_reg[bi].extend(vals)
    use_reg = regimes is not None and n_reg_dates >= min_regime_dates
    out = []
    for bi in range(k):
        sa = _bin_stats(pool_all[bi])
        if sa is None:
            out.append(None)
            continue
        if use_reg:
            sr = _bin_stats(pool_reg[bi])
            if sr is not None:
                blended = {kk: (shrink * sr[kk] + (1 - shrink) * sa[kk])
                           if isinstance(sa[kk], float) and np.isfinite(sr[kk]) else sa[kk]
                           for kk in sa}
                blended["n"] = sa["n"]
                blended["n_regime"] = sr["n"]
                out.append(blended)
                continue
        out.append(sa)
    return out, use_reg


# ----------------------------------------------------------------------------
# walk-forward predict + evaluate
# ----------------------------------------------------------------------------
def walk_forward_calibrated(config, horizon=10, liquid=0.70, variant="empirical",
                            min_train=12, shrink=0.5, shuffle=None, target="abs"):
    """Returns per-test-date arrays of predictions + realized returns.

    variant: 'empirical' (all train dates pooled) or 'empirical_regime'
             (regime-matched shrink-blend).
    target : 'abs' = raw forward return (P(up) absolute; level is dominated by
             the unknowable market move) or 'rel' = per-date median-demeaned
             return (P(beat the cross-section median); level IS calibratable
             because the market component cancels).
    shuffle: if set, permute scores WITHIN each date before binning (null test:
             bins then carry no info; Brier skill and discrimination must ~0).
    """
    z, meta = H.load_panel()
    Z = H.neutralize(z, meta)
    fwd = z[f"fwd{horizon}"].astype(np.float64)
    scores = H.walk_forward(Z, fwd, meta, config)
    if target == "rel":
        mask0 = liquid_mask(z, liquid)
        fwd = fwd.copy()
        for d in range(fwd.shape[0]):
            ok = np.isfinite(fwd[d]) & mask0[d]
            if ok.sum() > 50:
                fwd[d] = fwd[d] - np.median(fwd[d][ok])
    if shuffle is not None:
        rng = np.random.default_rng(int(shuffle))
        for d in range(scores.shape[0]):
            ok = np.where(np.isfinite(scores[d]))[0]
            if ok.size > 1:
                scores[d, ok] = scores[d, ok][rng.permutation(ok.size)]
    mask = liquid_mask(z, liquid)
    regimes = [r["regime"] for r in meta["regimes"]]
    dates = meta["base_dates"]
    D = scores.shape[0]
    recs = []
    for t in range(D):
        if t < min_train or not np.isfinite(scores[t]).any():
            continue
        train_idx = [d for d in range(t) if np.isfinite(scores[d]).any()]
        if len(train_idx) < min_train:
            continue
        reg = regimes[t] if variant == "empirical_regime" else None
        bins_stats, used_reg = fit_bins(
            scores, fwd, mask, train_idx,
            regimes=regimes if variant == "empirical_regime" else None,
            test_regime=reg, shrink=shrink)
        b = score_bins(scores[t], mask[t])
        r = fwd[t]
        sel = (b >= 0) & np.isfinite(r)
        if sel.sum() < 50:
            continue
        idx = np.where(sel)[0]
        pred = [bins_stats[b[j]] for j in idx]
        keep = [i for i, p in enumerate(pred) if p is not None]
        idx = idx[keep]
        pred = [pred[i] for i in keep]
        recs.append({
            "date": dates[t], "regime": regimes[t], "used_regime_pool": used_reg,
            "bin": b[idx], "ret": r[idx],
            "p_up": np.array([p["p_up"] for p in pred]),
            "exp": np.array([p["mean"] for p in pred]),
            "q10": np.array([p["q10"] for p in pred]),
            "q90": np.array([p["q90"] for p in pred]),
            "mean_up": np.array([p["mean_up"] for p in pred]),
            "train_base_rate": float(np.mean([
                s["p_up"] for s in
                (fit_bins(scores, fwd, mask, train_idx)[0]) if s])),  # bin-avg base
        })
    return recs


def evaluate(recs):
    """calibration + discrimination + coverage metrics across test dates."""
    if not recs:
        return {"error": "no test dates"}
    # ---- pooled stock-date level ----
    P = np.concatenate([r["p_up"] for r in recs])
    Y = np.concatenate([(r["ret"] > 0).astype(float) for r in recs])
    R = np.concatenate([r["ret"] for r in recs])
    EXP = np.concatenate([r["exp"] for r in recs])
    Q10 = np.concatenate([r["q10"] for r in recs])
    Q90 = np.concatenate([r["q90"] for r in recs])
    base = np.concatenate([np.full(r["ret"].shape, r["train_base_rate"]) for r in recs])
    brier = float(np.mean((P - Y) ** 2))
    brier_base = float(np.mean((base - Y) ** 2))
    skill = 1 - brier / brier_base if brier_base > 0 else float("nan")
    # reliability: bin by predicted P
    edges = np.percentile(P, np.linspace(0, 100, 9))
    rel = []
    for i in range(8):
        m = (P >= edges[i]) & (P <= edges[i + 1] if i == 7 else P < edges[i + 1])
        if m.sum() > 200:
            rel.append({"p_pred": float(P[m].mean()), "p_real": float(Y[m].mean()),
                        "n": int(m.sum())})
    coverage = float(np.mean((R >= Q10) & (R <= Q90)))
    mae_exp = float(np.mean(np.abs(EXP - R)))
    # ---- within-date discrimination (the part the stock layer truly adds) ----
    disc_p, disc_r = [], []
    for r in recs:
        p, y, rr = r["p_up"], (r["ret"] > 0).astype(float), r["ret"]
        if p.size < 50 or np.unique(p).size < 3:
            continue
        lo_thr, hi_thr = np.percentile(p, [20, 80])
        lo, hi = p <= lo_thr, p >= hi_thr
        if lo.sum() > 10 and hi.sum() > 10:
            disc_p.append(float(y[hi].mean() - y[lo].mean()))
            disc_r.append(float(rr[hi].mean() - rr[lo].mean()))
    def _t(a):
        a = np.asarray(a)
        return float(a.mean() / (a.std(ddof=1) / np.sqrt(a.size))) if a.size > 2 else float("nan")
    # ---- variance split: date vs within-date (how much of P(up) is market) ----
    date_up = np.array([float((r["ret"] > 0).mean()) for r in recs])
    within_var = float(np.mean([np.var((r["ret"] > 0).astype(float)) for r in recs]))
    between_var = float(np.var(date_up))
    return {
        "n_test_dates": len(recs), "n_obs": int(P.size),
        "brier": brier, "brier_base_rate": brier_base, "brier_skill": skill,
        "reliability": rel,
        "interval_coverage_q10_q90": coverage,
        "mae_exp_ret": mae_exp,
        "discrimination_up_rate_top_minus_bottom": {
            "mean": float(np.mean(disc_p)), "t": _t(disc_p),
            "pos_pct": float(np.mean(np.array(disc_p) > 0)), "n": len(disc_p)},
        "discrimination_ret_top_minus_bottom": {
            "mean": float(np.mean(disc_r)), "t": _t(disc_r),
            "pos_pct": float(np.mean(np.array(disc_r) > 0)), "n": len(disc_r)},
        "variance_split": {
            "between_date_var_of_up_rate": between_var,
            "within_date_var": within_var,
            "date_share": between_var / (between_var + within_var)
            if (between_var + within_var) > 0 else float("nan"),
            "date_up_rate_min": float(date_up.min()), "date_up_rate_max": float(date_up.max()),
        },
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "final_model.json"))
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--variant", default="empirical",
                    choices=["empirical", "empirical_regime"])
    ap.add_argument("--liquid", type=float, default=0.70)
    ap.add_argument("--shrink", type=float, default=0.5)
    ap.add_argument("--shuffle", type=int, default=None)
    ap.add_argument("--target", default="abs", choices=["abs", "rel"])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    cfg = json.load(open(a.config)) if os.path.exists(a.config) else json.loads(a.config)
    recs = walk_forward_calibrated(cfg, a.horizon, a.liquid, a.variant,
                                   shrink=a.shrink, shuffle=a.shuffle, target=a.target)
    rep = evaluate(recs)
    rep["variant"] = a.variant
    rep["horizon"] = a.horizon
    rep["liquid"] = a.liquid
    rep["shuffle"] = a.shuffle
    rep["target"] = a.target
    if a.out:
        json.dump(rep, open(a.out, "w"), indent=1, default=float)
    print(json.dumps(rep, indent=1, default=float))


if __name__ == "__main__":
    main()
