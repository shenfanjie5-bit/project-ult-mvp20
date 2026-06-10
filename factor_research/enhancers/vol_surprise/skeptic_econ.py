#!/usr/bin/env python3
"""Adversarial ECONOMICS skeptic attack on the vol-conditioned PEAD tilt claim.

Attacks (fresh, not reusing the claimant's saved numbers):
 1. exact reproduction of primary config (rvol_20|median|decile, liquid-70)
 2. fresh shuffle nulls seeds 7,11,13,17,19 (vol scrambled within top bucket)
 3. h20 overlap parity halves (even-d vs odd-d test dates)
 4. GENERIC VOL FACTOR: same hi-vol-half-minus-group tilt in (a) whole liquid
    universe, (b) mag deciles 4-6 (mid), (c) mag bottom decile. If positive
    everywhere, the "interaction" is just long-vol beta in this sample.
    Plus per-date OLS: top_tilt = a + b*uni_volfac -> is intercept ~ 0?
 5. SIZE: raw ln_mv of hi vs lo halves; drop-smallest-30% recheck (liq70 & liq50)
 6. LOTTERY/IVOL LOADING: split top bucket by rvol_20 residualized on
    ivol_60+max5; also pure max5 split. If residual split dies, rvol adds nothing.
 7. TURNOVER/COST: per-rebalance name turnover of hi-half vs whole decile;
    portfolio breadth (n_hi).
 8. multiple-testing haircut: Bonferroni t for 22 configs.

Writes factor_research/model/reports/enh_vol_surprise_skeptic_econ.json
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from factor_research.model import harness as H            # noqa: E402
from factor_research.model.caliblib import liquid_mask    # noqa: E402
from vol_surprise import (per_date_records, agg, nw_t, MAG_CFG, PROB_CFG)  # noqa: E402

OUT = os.path.join(ROOT, "factor_research", "model", "reports",
                   "enh_vol_surprise_skeptic_econ.json")

FRESH_SEEDS = [7, 11, 13, 17, 19]


def group_tilt(mag, vol, fwd, mask, meta, lo_q, hi_q):
    """Per date: take stocks with mag rank in [lo_q, hi_q) of liquid universe,
    split that group by its own vol median, return hi-half minus group mean."""
    D, N = mag.shape
    out = []
    for d in range(D):
        sc, rt, vl = mag[d], fwd[d], vol[d]
        ok = np.isfinite(sc) & np.isfinite(rt) & mask[d]
        if ok.sum() < 50:
            continue
        idx = np.where(ok)[0]
        order = idx[np.argsort(sc[idx])]
        n = idx.size
        grp = order[int(np.floor(lo_q * n)):int(np.ceil(hi_q * n))]
        fin = np.isfinite(vl[grp])
        if fin.sum() < 6:
            continue
        g = grp[fin]
        v = vl[g]
        mv = np.median(v)
        hi = g[v > mv]
        if hi.size < 3 or (g.size - hi.size) < 3:
            continue
        out.append({"d": d, "tilt": float(rt[hi].mean() - rt[grp].mean())})
    return out


def main():
    z, meta = H.load_panel()
    Z = H.neutralize(z, meta)
    names = meta["feat_names"]
    fwd = {h: z[f"fwd{h}"].astype(np.float64) for h in (10, 20)}
    mask70 = liquid_mask(z, 0.70)
    mask50 = liquid_mask(z, 0.50)

    mag = H.walk_forward(Z, fwd[20], meta, MAG_CFG)
    vol = Z[:, :, names.index("rvol_20")]
    ivol = Z[:, :, names.index("ivol_60")]
    max5 = Z[:, :, names.index("max5")]
    lnmv_raw = z["feat"].astype(np.float64)[:, :, names.index("ln_mv")]

    rep = {"study": "skeptic_econ attack on vol_surprise tilt", "date": "2026-06-10"}

    # ---- 1. reproduce primary
    recs20 = per_date_records(mag, vol, fwd[20], mask70, meta, bucket="decile", split="median")
    recs10 = per_date_records(mag, vol, fwd[10], mask70, meta, bucket="decile", split="median")
    g20 = [r["tilt_gain"] for r in recs20]
    rep["repro_primary"] = {"h20": agg(g20), "h10": agg([r["tilt_gain"] for r in recs10]),
                            "h20_nw_lag1": nw_t(g20, 1)}

    # ---- 2. fresh shuffle nulls
    nulls = {}
    for h, base in ((20, recs20), (10, recs10)):
        per_seed = []
        for s in FRESH_SEEDS:
            rng = np.random.default_rng(s)
            recs = per_date_records(mag, vol, fwd[h], mask70, meta,
                                    bucket="decile", split="median", rng=rng)
            a = agg([r["tilt_gain"] for r in recs])
            per_seed.append({"seed": s, "mean": a["mean"], "t": a["t"]})
        ts = [p["t"] for p in per_seed]
        nulls[f"h{h}"] = {"per_seed": per_seed,
                          "null_t_spread": [float(min(ts)), float(max(ts))],
                          "observed_t": agg([r["tilt_gain"] for r in base])["t"]}
    rep["fresh_nulls"] = nulls

    # ---- 3. parity halves h20
    even = [r["tilt_gain"] for r in recs20 if r["d"] % 2 == 0]
    odd = [r["tilt_gain"] for r in recs20 if r["d"] % 2 == 1]
    rep["parity_h20"] = {"even": agg(even), "odd": agg(odd)}

    # ---- 4. generic vol factor
    gen = {}
    for h in (10, 20):
        uni = group_tilt(mag, vol, fwd[h], mask70, meta, 0.0, 1.0)
        mid = group_tilt(mag, vol, fwd[h], mask70, meta, 0.3, 0.6)
        bot = group_tilt(mag, vol, fwd[h], mask70, meta, 0.0, 0.1)
        top = group_tilt(mag, vol, fwd[h], mask70, meta, 0.9, 1.0)
        gen[f"h{h}"] = {"universe": agg([r["tilt"] for r in uni]),
                        "mid_d4_d6": agg([r["tilt"] for r in mid]),
                        "bottom_decile": agg([r["tilt"] for r in bot]),
                        "top_decile_check": agg([r["tilt"] for r in top])}
        # interaction: top tilt minus universe tilt, matched by date
        um = {r["d"]: r["tilt"] for r in uni}
        diff = [r["tilt"] - um[r["d"]] for r in top if r["d"] in um]
        gen[f"h{h}"]["top_minus_universe_matched"] = agg(diff)
        # OLS: top_tilt = a + b * uni_tilt
        x = np.array([um[r["d"]] for r in top if r["d"] in um])
        y = np.array([r["tilt"] for r in top if r["d"] in um])
        if x.size > 10:
            X = np.column_stack([np.ones_like(x), x])
            beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            resid = y - X @ beta
            dof = x.size - 2
            s2 = float(resid @ resid) / dof
            cov = s2 * np.linalg.inv(X.T @ X)
            gen[f"h{h}"]["ols_top_on_universe"] = {
                "alpha": float(beta[0]), "alpha_t": float(beta[0] / np.sqrt(cov[0, 0])),
                "beta": float(beta[1]), "beta_t": float(beta[1] / np.sqrt(cov[1, 1])),
                "n": int(x.size)}
    rep["generic_vol_factor"] = gen

    # ---- 5. size composition + drop-smallest-30%
    size = {}
    dmv = []
    for r in recs20:
        pass  # need hi/lo indices -> recompute below
    # recompute hi/lo lnmv per date (mirror per_date_records logic)
    D, N = mag.shape
    diffs, hi_mv, lo_mv = [], [], []
    for d in range(D):
        sc, rt, vl = mag[d], fwd[20][d], vol[d]
        ok = np.isfinite(sc) & np.isfinite(rt) & mask70[d]
        if ok.sum() < 50:
            continue
        idx = np.where(ok)[0]
        order = idx[np.argsort(sc[idx])]
        ntop = max(1, idx.size // 10)
        top = order[-ntop:]
        fin = np.isfinite(vl[top])
        if fin.sum() < 6:
            continue
        tf = top[fin]
        v = vl[tf]
        mv = np.median(v)
        hi, lo = tf[v > mv], tf[v <= mv]
        if hi.size < 3 or lo.size < 3:
            continue
        h_mv = np.nanmean(lnmv_raw[d][hi]); l_mv = np.nanmean(lnmv_raw[d][lo])
        hi_mv.append(h_mv); lo_mv.append(l_mv); diffs.append(h_mv - l_mv)
    size["lnmv_hi_minus_lo"] = agg(diffs)
    size["lnmv_hi_mean"] = float(np.mean(hi_mv))
    size["lnmv_lo_mean"] = float(np.mean(lo_mv))

    # drop-smallest-30% by raw ln_mv within each date's liquid mask
    def drop_small(mask, frac=0.30):
        m2 = mask.copy()
        for d in range(D):
            idx = np.where(mask[d] & np.isfinite(lnmv_raw[d]))[0]
            if idx.size < 50:
                continue
            cut = np.quantile(lnmv_raw[d][idx], frac)
            kill = idx[lnmv_raw[d][idx] < cut]
            m2[d, kill] = False
        return m2

    m70big = drop_small(mask70)
    m50big = drop_small(mask50)
    for lbl, m in (("liq70_dropsmall30", m70big), ("liq50_dropsmall30", m50big)):
        rcs = per_date_records(mag, vol, fwd[20], m, meta, bucket="decile", split="median")
        size[lbl + "_h20"] = agg([r["tilt_gain"] for r in rcs])
        rcs10 = per_date_records(mag, vol, fwd[10], m, meta, bucket="decile", split="median")
        size[lbl + "_h10"] = agg([r["tilt_gain"] for r in rcs10])
    rep["size_attack"] = size

    # ---- 6. residualized vol split + max5 split
    resid_tilts, max5_tilts = [], []
    for d in range(D):
        sc, rt = mag[d], fwd[20][d]
        ok = np.isfinite(sc) & np.isfinite(rt) & mask70[d]
        if ok.sum() < 50:
            continue
        idx = np.where(ok)[0]
        order = idx[np.argsort(sc[idx])]
        ntop = max(1, idx.size // 10)
        top = order[-ntop:]
        v, iv, m5 = vol[d][top], ivol[d][top], max5[d][top]
        fin = np.isfinite(v) & np.isfinite(iv) & np.isfinite(m5)
        if fin.sum() < 8:
            continue
        tf = top[fin]
        vv, ivv, m5v = v[fin], iv[fin], m5[fin]
        X = np.column_stack([np.ones(tf.size), ivv, m5v])
        beta, _, _, _ = np.linalg.lstsq(X, vv, rcond=None)
        res = vv - X @ beta
        mr = np.median(res)
        hi = tf[res > mr]
        if hi.size >= 3 and (tf.size - hi.size) >= 3:
            resid_tilts.append(float(rt[hi].mean() - rt[top].mean()))
        mm = np.median(m5v)
        hi5 = tf[m5v > mm]
        if hi5.size >= 3 and (tf.size - hi5.size) >= 3:
            max5_tilts.append(float(rt[hi5].mean() - rt[top].mean()))
    rep["residual_vol_split_h20"] = agg(resid_tilts)
    rep["max5_split_h20"] = agg(max5_tilts)

    # ---- 7. turnover / breadth
    seq = []
    for d in range(D):
        sc, rt, vl = mag[d], fwd[20][d], vol[d]
        ok = np.isfinite(sc) & np.isfinite(rt) & mask70[d]
        if ok.sum() < 50:
            continue
        idx = np.where(ok)[0]
        order = idx[np.argsort(sc[idx])]
        ntop = max(1, idx.size // 10)
        top = order[-ntop:]
        fin = np.isfinite(vl[top])
        if fin.sum() < 6:
            continue
        tf = top[fin]
        v = vl[tf]
        mv = np.median(v)
        hi = tf[v > mv]
        seq.append({"d": d, "top": set(map(int, top)), "hi": set(map(int, hi)),
                    "n_top": int(top.size), "n_hi": int(hi.size)})
    to_top, to_hi = [], []
    for a, b in zip(seq, seq[1:]):
        if b["d"] - a["d"] != 1:
            continue
        to_top.append(1.0 - len(a["top"] & b["top"]) / max(1, len(b["top"])))
        to_hi.append(1.0 - len(a["hi"] & b["hi"]) / max(1, len(b["hi"])))
    rep["turnover"] = {
        "per_rebalance_10d_top": float(np.mean(to_top)),
        "per_rebalance_10d_hi": float(np.mean(to_hi)),
        "n_hi_median": float(np.median([s["n_hi"] for s in seq])),
        "n_top_median": float(np.median([s["n_top"] for s in seq])),
        "note": "one-way turnover fraction per 10d rebalance; A-share roundtrip "
                "cost assumption 25-35bp (commission+stamp+impact)"}

    # ---- 8. multiple-testing haircut
    from scipy import stats
    t_obs = rep["repro_primary"]["h20"]["t"]
    n = rep["repro_primary"]["h20"]["n_dates"]
    p_plain = 2 * (1 - stats.t.cdf(abs(t_obs), n - 1))
    t_nw = rep["repro_primary"]["h20_nw_lag1"]
    p_nw = 2 * (1 - stats.t.cdf(abs(t_nw), n - 1))
    rep["multiple_testing"] = {
        "configs": 22, "p_plain_h20": float(p_plain), "p_plain_x22": float(min(1, p_plain * 22)),
        "p_nw_lag1_h20": float(p_nw), "p_nw_x22": float(min(1, p_nw * 22)),
        "bonferroni_t_needed_(p05/22)": float(stats.t.ppf(1 - 0.05 / 22 / 2, n - 1))}

    json.dump(rep, open(OUT, "w"), indent=1, default=float)
    print(json.dumps(rep, indent=1, default=float))
    print("saved ->", OUT)


if __name__ == "__main__":
    main()
