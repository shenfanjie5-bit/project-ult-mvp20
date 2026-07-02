#!/usr/bin/env python3
"""Walk-forward LOGISTIC P(beat-median) layer (ISOLATED research; read-only deps).

Alternative to caliblib's empirical score-rank-bin calibration: for each test
base date t, fit sklearn LogisticRegression on POOLED earlier base dates
(< t only — same walk-forward discipline as harness/caliblib), per-date liquid
mask, X = neutralized features (NaN->0 impute, coverage>=0.5 row filter),
y = 1{fwd_ret > per-date liquid median}  (target=rel; the only level-
calibratable target per the prior study).

Output recs are shaped exactly like caliblib.walk_forward_calibrated recs so
caliblib.evaluate() runs unmodified:
  p_up  = RAW logistic probability (--pcal raw)  -> tests logistic calibration
          or empirical-bin-recalibrated P (--pcal binned)
  exp/q10/q90/mean_up = pooled train fwd-return distributions per within-date
          decile of the logistic score (caliblib.fit_bins on the P matrix), so
          the magnitude band stays empirical/honest.

Null test (--shuffle SEED): permute the walk-forward P matrix WITHIN each base
date (train + test rows) before rec building — identical protocol to
caliblib's --shuffle: discrimination and Brier skill must collapse to ~0.

Subset cuts (--drop-year / --drop-regime) filter TEST recs before evaluate()
(the accepted protocol for caliblib-layer robustness cuts).

Run from anywhere:
  factor_research/.venv_research/bin/python factor_research/model/prob_variants/logistic.py \
      --horizon 10 --features base5 --C 1.0 --pcal raw --liquid 0.70
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from factor_research.model import caliblib as C  # noqa: E402
from factor_research.model import harness as H   # noqa: E402

BASE5 = ["rvol_20", "ivol_60", "max5", "turnover_20", "ep_ttm"]
FEATURE_SETS = {
    "base5": BASE5,
    "base5_strev": BASE5 + ["strev"],
    "base5_beta": BASE5 + ["beta_60"],
    "base5_strev_beta": BASE5 + ["strev", "beta_60"],
    "base5_surprise": BASE5 + ["sue", "npq_yoy"],   # raw surprise features
    "base5_mag": BASE5 + ["__mag__"],               # combined magnitude score
    "surprise_only": ["sue", "npq_yoy"],            # control: surprise alone
}
MIN_COV = 0.5


def magnitude_score_matrix(Z, meta):
    """final_model ranking score = ew_signed(sue, npq_yoy): signed sum of the
    neutralized features, own coverage>=0.5 else NaN, then per-date rank-z so
    it lives on the same scale as the other logistic inputs."""
    names = meta["feat_names"]
    sel = [names.index("sue"), names.index("npq_yoy")]
    X = Z[:, :, sel]
    cov = np.isfinite(X).mean(2)
    s = np.where(np.isfinite(X), X, 0.0).sum(2)
    s[cov < MIN_COV] = np.nan
    D = Z.shape[0]
    out = np.full_like(s, np.nan)
    for d in range(D):
        out[d] = H._rank_z(s[d])
    return out


def build_design(Z, meta, feature_set):
    feats = FEATURE_SETS[feature_set]
    names = meta["feat_names"]
    cols = []
    for f in feats:
        if f == "__mag__":
            cols.append(magnitude_score_matrix(Z, meta))
        else:
            cols.append(Z[:, :, names.index(f)])
    return np.stack(cols, axis=2), feats  # D,N,F


def rel_demean(fwd, mask):
    """per-date liquid-median demeaning (identical to caliblib target=rel)."""
    out = fwd.copy()
    for d in range(out.shape[0]):
        ok = np.isfinite(out[d]) & mask[d]
        if ok.sum() > 50:
            out[d] = out[d] - np.median(out[d][ok])
    return out


def prob_matrix(X, fwd_rel, mask, Creg=1.0, min_train=12):
    """walk-forward logistic P matrix [D,N]; date t fit ONLY on dates < t."""
    from sklearn.linear_model import LogisticRegression
    D, N, F = X.shape
    P = np.full((D, N), np.nan)
    coef_log = []
    for t in range(min_train, D):
        Xs, ys = [], []
        for d in range(t):
            rows = mask[d] & np.isfinite(fwd_rel[d])
            if rows.sum() < 50:
                continue
            Xd = X[d][rows]
            cov = np.isfinite(Xd).mean(1)
            keep = cov >= MIN_COV
            if keep.sum() < 50:
                continue
            Xs.append(np.where(np.isfinite(Xd[keep]), Xd[keep], 0.0))
            ys.append((fwd_rel[d][rows][keep] > 0).astype(int))
        if not Xs:
            continue
        Xtr = np.vstack(Xs)
        ytr = np.concatenate(ys)
        if len(np.unique(ytr)) < 2 or len(ytr) < 500:
            continue
        mdl = LogisticRegression(C=Creg, solver="lbfgs", max_iter=2000)
        mdl.fit(Xtr, ytr)
        rows = mask[t]
        Xt = X[t]
        cov = np.isfinite(Xt).mean(1)
        ok = rows & (cov >= MIN_COV)
        if ok.sum() < 50:
            continue
        P[t, ok] = mdl.predict_proba(np.where(np.isfinite(Xt[ok]), Xt[ok], 0.0))[:, 1]
        coef_log.append({"t": t, "coef": mdl.coef_[0].tolist(),
                         "intercept": float(mdl.intercept_[0]), "n_train": int(len(ytr))})
    return P, coef_log


def build_recs(Pmat, fwd_rel, mask, meta, pcal="raw", first_test=24, min_bin_train=12):
    """caliblib-shaped recs; magnitude band always from empirical decile pools."""
    regimes = [r["regime"] for r in meta["regimes"]]
    dates = meta["base_dates"]
    D = Pmat.shape[0]
    recs = []
    for t in range(first_test, D):
        if not np.isfinite(Pmat[t]).any():
            continue
        train_idx = [d for d in range(t) if np.isfinite(Pmat[d]).any()]
        if len(train_idx) < min_bin_train:
            continue
        bins_stats, _ = C.fit_bins(Pmat, fwd_rel, mask, train_idx)
        b = C.score_bins(Pmat[t], mask[t])
        r = fwd_rel[t]
        sel = (b >= 0) & np.isfinite(r)
        if sel.sum() < 50:
            continue
        idx = np.where(sel)[0]
        pred = [bins_stats[b[j]] for j in idx]
        keep = [i for i, p in enumerate(pred) if p is not None]
        idx = idx[keep]
        pred = [pred[i] for i in keep]
        ys = []
        for d in train_idx:
            okd = mask[d] & np.isfinite(fwd_rel[d])
            ys.append((fwd_rel[d][okd] > 0).astype(float))
        tbr = float(np.concatenate(ys).mean())
        if pcal == "raw":
            p_up = Pmat[t][idx]
        else:  # binned recalibration of the logistic score
            p_up = np.array([p["p_up"] for p in pred])
        recs.append({
            "date": dates[t], "regime": regimes[t], "used_regime_pool": False,
            "bin": b[idx], "ret": r[idx], "p_up": p_up,
            "exp": np.array([p["mean"] for p in pred]),
            "q10": np.array([p["q10"] for p in pred]),
            "q90": np.array([p["q90"] for p in pred]),
            "mean_up": np.array([p["mean_up"] for p in pred]),
            "train_base_rate": tbr,
        })
    return recs


def run(horizon=10, liquid=0.70, feature_set="base5", Creg=1.0, pcal="raw",
        target="rel", shuffle=None, drop_year=None, drop_regime=None,
        first_test=24, min_train=12):
    z, meta = H.load_panel()
    Z = H.neutralize(z, meta)
    fwd = z[f"fwd{horizon}"].astype(np.float64)
    mask = C.liquid_mask(z, liquid)
    fwd_t = rel_demean(fwd, mask) if target == "rel" else fwd.copy()
    X, feats = build_design(Z, meta, feature_set)
    P, coef_log = prob_matrix(X, fwd_t, mask, Creg=Creg, min_train=min_train)
    if shuffle is not None:
        rng = np.random.default_rng(int(shuffle))
        for d in range(P.shape[0]):
            ok = np.where(np.isfinite(P[d]))[0]
            if ok.size > 1:
                P[d, ok] = P[d, ok][rng.permutation(ok.size)]
    recs = build_recs(P, fwd_t, mask, meta, pcal=pcal, first_test=first_test)
    if drop_year:
        recs = [r for r in recs if r["date"][:4] != str(drop_year)]
    if drop_regime:
        recs = [r for r in recs if r["regime"] != drop_regime]
    rep = C.evaluate(recs)
    rep.update({
        "family": "prob_logistic", "feature_set": feature_set, "features": feats,
        "C": Creg, "pcal": pcal, "target": target, "horizon": horizon,
        "liquid": liquid, "shuffle": shuffle,
        "drop_year": drop_year, "drop_regime": drop_regime,
        "first_test": first_test,
    })
    if coef_log:
        cm = np.array([c["coef"] for c in coef_log])
        rep["coef_mean"] = dict(zip(feats, np.round(cm.mean(0), 4).tolist()))
        rep["coef_last"] = dict(zip(feats, np.round(cm[-1], 4).tolist()))
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--liquid", type=float, default=0.70)
    ap.add_argument("--features", default="base5", choices=sorted(FEATURE_SETS))
    ap.add_argument("--C", type=float, default=1.0, dest="Creg")
    ap.add_argument("--pcal", default="raw", choices=["raw", "binned"])
    ap.add_argument("--target", default="rel", choices=["rel", "abs"])
    ap.add_argument("--shuffle", type=int, default=None)
    ap.add_argument("--drop-year", default=None)
    ap.add_argument("--drop-regime", default=None)
    ap.add_argument("--first-test", type=int, default=24)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rep = run(a.horizon, a.liquid, a.features, a.Creg, a.pcal, a.target,
              a.shuffle, a.drop_year, a.drop_regime, a.first_test)
    if a.out:
        json.dump(rep, open(a.out, "w"), indent=1, default=float)
    print(json.dumps(rep, indent=1, default=float))


if __name__ == "__main__":
    main()
