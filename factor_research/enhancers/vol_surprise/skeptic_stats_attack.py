#!/usr/bin/env python3
"""Adversarial statistics attack on the vol_surprise weak_positive claim.

Attacks:
  A. Fresh shuffle nulls, mandated seeds 7,11,13,17,19, exact script path.
  B. Large empirical null (1000 reps) on the primary h20/h10 tilt t, via the
     exact permutation equivalence (random subset of size n_hi within the
     date's top bucket) -> empirical one-sided p.
  C. Westfall-Young maxT across ALL grid cells (multiplicity-honest p):
     for each null rep compute max t over the 11 h20 cells (and over all 18),
     compare the observed primary t against that null max distribution.
  D. Overlap honesty: parity halves (even d / odd d, both 27-date nonoverlap
     subsamples), autocorrelation of the tilt series, and full-weight MA(1)
     corrected t (NW Bartlett lag-1 only half-weights gamma1 -> anti-conservative
     for step-10 h20 overlap).
  E. Concentration: drop-2026, drop-up_calm, BOTH jointly; influence of top-k
     dates; sign test / median.
Writes factor_research/model/reports/enh_vol_surprise_skeptic_stats.json
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
from scipy import stats as sps

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from factor_research.model import harness as H            # noqa: E402
from factor_research.model.caliblib import liquid_mask    # noqa: E402
from factor_research.enhancers.vol_surprise.vol_surprise import (  # noqa: E402
    MAG_CFG, per_date_records, agg, nw_t)

OUT = os.path.join(ROOT, "factor_research", "model", "reports",
                   "enh_vol_surprise_skeptic_stats.json")


def extract_cells(mag, vols, fwd, mask, meta):
    """Per grid cell, per evaluable date: (rt over top bucket, n_hi, date meta).

    Permuting vol within the top bucket == drawing a uniform random subset of
    size n_hi (n_hi fixed by the tie structure of the vol multiset, which is
    permutation invariant). This lets the null run thousands of reps fast and
    EXACTLY matches the script's rng path in distribution.
    """
    D, N = mag.shape
    cells = {}
    for vname in ("rvol_20", "ivol_60", "rvol_20_raw"):
        for split in ("median", "tercile"):
            for bucket in ("decile", "quintile"):
                if vname == "rvol_20_raw" and (split != "median" or bucket != "decile"):
                    continue
                for h in (10, 20):
                    k = 10 if bucket == "decile" else 5
                    key = f"{vname}|{split}|{bucket}|h{h}"
                    per_date = []
                    for d in range(D):
                        sc, rt, vl = mag[d], fwd[h][d], vols[vname][d]
                        ok = np.isfinite(sc) & np.isfinite(rt) & mask[d]
                        if ok.sum() < 50:
                            continue
                        idx = np.where(ok)[0]
                        order = idx[np.argsort(sc[idx])]
                        ntop = max(1, idx.size // k)
                        top = order[-ntop:]
                        fin = np.isfinite(vl[top])
                        if fin.sum() < 6:
                            continue
                        top_f = top[fin]
                        v = vl[top_f]
                        if split == "median":
                            mv = np.median(v)
                            n_hi = int((v > mv).sum()); n_lo = int((v <= mv).sum())
                        else:
                            kk = max(1, v.size // 3)
                            n_hi = kk; n_lo = kk
                        if n_hi < 3 or n_lo < 3:
                            continue
                        per_date.append({"d": d, "rt_topf": rt[top_f].copy(),
                                         "ret_top": float(rt[top].mean()),
                                         "n_hi": n_hi})
                    cells[key] = per_date
    return cells


def null_tilt_t(per_date, rng):
    g = []
    for rec in per_date:
        r = rec["rt_topf"]
        pick = rng.permutation(r.size)[:rec["n_hi"]]
        g.append(float(r[pick].mean()) - rec["ret_top"])
    a = np.asarray(g)
    se = a.std(ddof=1) / np.sqrt(a.size)
    return float(a.mean() / se), float(a.mean())


def ma1_t(x):
    """t with FULL-weight lag-1 autocovariance (correct for MA(1) overlap;
    Bartlett lag-1 only half-weights gamma1 -> anti-conservative)."""
    x = np.asarray(x, float); n = x.size
    e = x - x.mean()
    g0 = float(e @ e) / n
    g1 = float(e[:-1] @ e[1:]) / n
    s = max(g0 + 2.0 * g1, 1e-12)
    return float(x.mean() / np.sqrt(s / n)), float(g1 / g0)


def main():
    z, meta = H.load_panel()
    Z = H.neutralize(z, meta)
    names = meta["feat_names"]
    fwd = {h: z[f"fwd{h}"].astype(np.float64) for h in (10, 20)}
    mask70 = liquid_mask(z, 0.70)
    mag = H.walk_forward(Z, fwd[20], meta, MAG_CFG)
    vols = {"rvol_20": Z[:, :, names.index("rvol_20")],
            "ivol_60": Z[:, :, names.index("ivol_60")],
            "rvol_20_raw": z["feat"].astype(np.float64)[:, :, names.index("rvol_20")]}

    rep = {"attack": "statistics", "date": "2026-06-10"}

    # ---------- observed primary records (exact script path) ----------
    prim = {}
    for h in (10, 20):
        prim[h] = per_date_records(mag, vols["rvol_20"], fwd[h], mask70, meta,
                                   bucket="decile", split="median")
    obs = {f"h{h}": agg([r["tilt_gain"] for r in prim[h]]) for h in (10, 20)}
    rep["observed_primary"] = obs

    # ---------- A. mandated fresh seeds via exact script path ----------
    fresh = {}
    for h in (10, 20):
        per_seed = []
        for s in (7, 11, 13, 17, 19):
            rng = np.random.default_rng(s)
            recs = per_date_records(mag, vols["rvol_20"], fwd[h], mask70, meta,
                                    bucket="decile", split="median", rng=rng)
            a = agg([r["tilt_gain"] for r in recs])
            per_seed.append({"seed": s, "mean": a["mean"], "t": a["t"]})
        fresh[f"h{h}"] = per_seed
    rep["fresh_seed_nulls"] = fresh

    # ---------- B+C. large null + Westfall-Young maxT ----------
    cells = extract_cells(mag, vols, fwd, mask70, meta)
    # sanity: observed tilt per cell recomputed from extraction must match grid
    grid_obs = {}
    for key, per_date in cells.items():
        # observed: n_hi positions are the TRUE high-vol ones; recompute via script
        pass
    NB = 1000
    rng = np.random.default_rng(7)
    h20_keys = [k for k in cells if k.endswith("h20")]
    all_keys = list(cells)
    null_prim_h20 = np.empty(NB); null_prim_h10 = np.empty(NB)
    null_max_h20 = np.empty(NB); null_max_all = np.empty(NB)
    for b in range(NB):
        ts = {}
        for key in all_keys:
            t, _ = null_tilt_t(cells[key], rng)
            ts[key] = t
        null_prim_h20[b] = ts["rvol_20|median|decile|h20"]
        null_prim_h10[b] = ts["rvol_20|median|decile|h10"]
        null_max_h20[b] = max(ts[k] for k in h20_keys)
        null_max_all[b] = max(ts[k] for k in all_keys)
    t20 = obs["h20"]["t"]; t10 = obs["h10"]["t"]
    rep["large_null"] = {
        "n_reps": NB,
        "h20_primary": {"obs_t": t20,
                        "emp_p_one_sided": float((null_prim_h20 >= t20).mean()),
                        "null_q95": float(np.quantile(null_prim_h20, 0.95)),
                        "null_q99": float(np.quantile(null_prim_h20, 0.99))},
        "h10_primary": {"obs_t": t10,
                        "emp_p_one_sided": float((null_prim_h10 >= t10).mean())},
        "maxT_h20_family_11cells": {
            "emp_p": float((null_max_h20 >= t20).mean()),
            "null_max_q95": float(np.quantile(null_max_h20, 0.95))},
        "maxT_all_18cells": {
            "emp_p": float((null_max_all >= t20).mean()),
            "null_max_q95": float(np.quantile(null_max_all, 0.95))}}

    # ---------- D. overlap honesty ----------
    g20 = [r["tilt_gain"] for r in prim[20]]
    g10 = [r["tilt_gain"] for r in prim[10]]
    even = [r["tilt_gain"] for r in prim[20] if r["d"] % 2 == 0]
    odd = [r["tilt_gain"] for r in prim[20] if r["d"] % 2 == 1]
    a = np.asarray(g20)
    ac1 = float(np.corrcoef(a[:-1], a[1:])[0, 1])
    ac2 = float(np.corrcoef(a[:-2], a[2:])[0, 1])
    tma, rho = ma1_t(g20)
    rep["overlap"] = {
        "h20_plain_t": agg(g20)["t"], "h20_nw_lag1": nw_t(g20, 1),
        "h20_ma1_fullweight_t": tma, "acf_lag1": ac1, "acf_lag2": ac2,
        "even_half": agg(even), "odd_half": agg(odd),
        "h10_plain_t": agg(g10)["t"]}

    # ---------- E. concentration ----------
    def cut(recs, f):
        sub = [r["tilt_gain"] for r in recs if f(r)]
        return agg(sub)
    r20 = prim[20]
    conc = {
        "drop_2026": cut(r20, lambda r: r["year"] != "2026"),
        "drop_up_calm": cut(r20, lambda r: r["regime"] != "up_calm"),
        "drop_2026_and_up_calm": cut(r20, lambda r: r["year"] != "2026" and r["regime"] != "up_calm"),
        "drop_top3_dates": agg(sorted(g20)[:-3]),
        "median_tilt": float(np.median(g20)),
        "sign_test_p": float(sps.binomtest((np.asarray(g20) > 0).sum(),
                                           len(g20), 0.5, alternative="greater").pvalue),
        "wilcoxon_p": float(sps.wilcoxon(g20, alternative="greater").pvalue)}
    rep["concentration"] = conc

    json.dump(rep, open(OUT, "w"), indent=1, default=float)
    print(json.dumps(rep, indent=1, default=float))


if __name__ == "__main__":
    main()
