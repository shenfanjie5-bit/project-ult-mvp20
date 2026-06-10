#!/usr/bin/env python3
"""Paired per-date comparison: logistic P(beat-median) vs empirical-bin layer.

Both models are evaluated on the IDENTICAL test dates (same panel, same liquid
mask, same rel target), so the per-date discrimination difference
(logistic - empirical) with a paired t-test is far more powerful than
comparing the two aggregate t-stats.

  .../python factor_research/model/prob_variants/compare_paired.py --horizon 10
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
from factor_research.model.prob_variants import logistic as L  # noqa: E402

PROB_CFG = {"name": "prob_composite", "method": "ew_signed",
            "features": ["rvol_20", "ivol_60", "max5", "turnover_20", "ep_ttm"],
            "params": {"min_cov": 0.5}}


def per_date_disc(recs):
    """same definition as caliblib.evaluate: within-date top-20% minus
    bottom-20% (by predicted P) realized up-rate."""
    out = {}
    for r in recs:
        p, y = r["p_up"], (r["ret"] > 0).astype(float)
        if p.size < 50 or np.unique(p).size < 3:
            continue
        lo_thr, hi_thr = np.percentile(p, [20, 80])
        lo, hi = p <= lo_thr, p >= hi_thr
        if lo.sum() > 10 and hi.sum() > 10:
            out[r["date"]] = float(y[hi].mean() - y[lo].mean())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--liquid", type=float, default=0.70)
    ap.add_argument("--features", default="base5")
    ap.add_argument("--C", type=float, default=1.0, dest="Creg")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    emp_recs = C.walk_forward_calibrated(PROB_CFG, a.horizon, a.liquid,
                                         "empirical", target="rel")
    z, meta = L.H.load_panel()
    Z = L.H.neutralize(z, meta)
    fwd = z[f"fwd{a.horizon}"].astype(np.float64)
    mask = C.liquid_mask(z, a.liquid)
    fwd_rel = L.rel_demean(fwd, mask)
    X, feats = L.build_design(Z, meta, a.features)
    P, _ = L.prob_matrix(X, fwd_rel, mask, Creg=a.Creg)
    log_recs = L.build_recs(P, fwd_rel, mask, meta, pcal="raw")

    de = per_date_disc(emp_recs)
    dl = per_date_disc(log_recs)
    common = sorted(set(de) & set(dl))
    diff = np.array([dl[d] - de[d] for d in common])
    t = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(diff.size))) if diff.size > 2 else float("nan")
    rep = {
        "horizon": a.horizon, "liquid": a.liquid,
        "logistic": {"feature_set": a.features, "C": a.Creg,
                     "disc_mean": float(np.mean(list(dl.values()))), "n_dates": len(dl)},
        "empirical": {"disc_mean": float(np.mean(list(de.values()))), "n_dates": len(de)},
        "paired_n_dates": len(common),
        "paired_diff_logistic_minus_empirical": {
            "mean": float(diff.mean()), "t": t,
            "pos_pct": float((diff > 0).mean()),
            "per_date_corr": float(np.corrcoef(
                [dl[d] for d in common], [de[d] for d in common])[0, 1]),
        },
    }
    if a.out:
        json.dump(rep, open(a.out, "w"), indent=1, default=float)
    print(json.dumps(rep, indent=1, default=float))


if __name__ == "__main__":
    main()
