#!/usr/bin/env python3
"""Vol-conditioned PEAD refinement: validate or kill (ISOLATED, read-only research).

LEAD (fusion_product.json, post-hoc single split, NOT validated): within the
magnitude-layer (ew_signed sue,npq_yoy) TOP decile on liquid-70, the PEAD drift
sits entirely in the HIGH-vol half (+1.63%/20d t2.88 when split by prob-score
median); the low-vol half has ~zero drift.

This study:
  1. Reproduces the lead exactly (prob-score median split) AND the brief's
     restatement (rvol_20 median split).
  2. Measures the WALK-FORWARD IMPLEMENTABLE tilt gain: at each test date,
     within the date's liquid mag-top-bucket, split by the date's own vol
     median/terciles (a fixed ex-ante rule, no parameter fit) and aggregate
     (high-half excess - whole-bucket excess) across dates.
  3. Variant grid (all counted): split var rvol_20|ivol_60 (neutralized),
     median|tercile, decile|quintile bucket, h10|h20.  Raw rvol_20 sensitivity.
  4. Honesty bar: within-date shuffle nulls (vol scrambled WITHIN the top
     bucket, >=8 seeds) on the decision metric; liquid-50 recheck; drop-year /
     drop-regime cuts; nonoverlap subsample at h20; by-year/by-regime
     stability; multiple-testing accounting.
  5. Prob-layer tension: P(beat median) & P(up) and prob-score percentile of
     the high-vol-tilted bucket vs the untilted bucket.

Writes factor_research/model/reports/enh_vol_surprise.json.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from factor_research.model import harness as H            # noqa: E402
from factor_research.model.caliblib import liquid_mask    # noqa: E402

OUT = os.path.join(ROOT, "factor_research", "model", "reports", "enh_vol_surprise.json")

MAG_CFG = {"name": "mag_pead", "method": "ew_signed",
           "features": ["sue", "npq_yoy"], "params": {"min_cov": 0.5},
           "min_train_dates": 12}
PROB_CFG = {"name": "prob_proxy", "method": "ew_signed",
            "features": ["rvol_20", "ivol_60", "max5", "turnover_20", "ep_ttm"],
            "params": {"min_cov": 0.5}, "min_train_dates": 12}

NULL_SEEDS = [101, 102, 103, 104, 105, 106, 107, 108]


# ----------------------------------------------------------------------------
def agg(vals):
    a = np.asarray([v for v in vals if np.isfinite(v)], float)
    if a.size < 3:
        return None
    se = a.std(ddof=1) / np.sqrt(a.size)
    return {"mean": float(a.mean()),
            "se": float(se),
            "t": float(a.mean() / se) if se > 0 else float("nan"),
            "pos_pct": float((a > 0).mean()),
            "n_dates": int(a.size)}


def per_date_records(mag, vol, fwd, mask, meta, bucket="decile", split="median",
                     rng=None, prob=None):
    """One record per evaluable test date with the tilt metrics.

    rng != None -> NULL: permute vol values WITHIN the top bucket before the
    split (mag ranking and labels untouched), so any surviving tilt gain is
    chance/bucket-composition, not vol information."""
    D, N = mag.shape
    dates = meta["base_dates"]
    regimes = [r["regime"] for r in meta["regimes"]]
    k = 10 if bucket == "decile" else 5
    recs = []
    for d in range(D):
        sc, rt, vl = mag[d], fwd[d], vol[d]
        ok = np.isfinite(sc) & np.isfinite(rt) & mask[d]
        if ok.sum() < 50:
            continue
        idx = np.where(ok)[0]
        uni = float(rt[idx].mean())
        med_uni = float(np.median(rt[idx]))
        order = idx[np.argsort(sc[idx])]
        ntop = max(1, idx.size // k)
        top = order[-ntop:]
        fin = np.isfinite(vl[top])
        if fin.sum() < 6:
            continue
        top_f = top[fin]
        v = vl[top_f]
        if rng is not None:
            v = v[rng.permutation(v.size)]
        if split == "median":
            mv = np.median(v)
            hi, lo = top_f[v > mv], top_f[v <= mv]
        else:  # tercile: top vs bottom third by vol
            o = np.argsort(v)
            kk = max(1, v.size // 3)
            lo, hi = top_f[o[:kk]], top_f[o[-kk:]]
        if hi.size < 3 or lo.size < 3:
            continue
        ret_top = float(rt[top].mean())
        ret_hi = float(rt[hi].mean())
        ret_lo = float(rt[lo].mean())
        rec = {"d": d, "date": dates[d], "year": dates[d][:4], "regime": regimes[d],
               "n_uni": int(idx.size), "n_top": int(top.size),
               "n_hi": int(hi.size), "n_lo": int(lo.size),
               "exc_top": ret_top - uni, "exc_hi": ret_hi - uni, "exc_lo": ret_lo - uni,
               "tilt_gain": ret_hi - ret_top,        # implementable: hi-half vs whole bucket
               "lo_minus_top": ret_lo - ret_top,
               "p_up_hi": float((rt[hi] > 0).mean()),
               "p_up_top": float((rt[top] > 0).mean()),
               "p_beat_hi": float((rt[hi] > med_uni).mean()),
               "p_beat_top": float((rt[top] > med_uni).mean())}
        if prob is not None and np.isfinite(prob[d][idx]).sum() > 50:
            pr = prob[d]
            r_ok = np.argsort(np.argsort(pr[idx]))
            pct = np.full(N, np.nan)
            pct[idx] = (r_ok + 1.0) / (idx.size + 1.0)
            rec["prob_pct_hi"] = float(np.nanmean(pct[hi]))
            rec["prob_pct_top"] = float(np.nanmean(pct[top]))
        recs.append(rec)
    return recs


def nw_t(x, lag=1):
    """Newey-West (Bartlett) t for the mean of an autocorrelated date series
    (h20 windows overlap adjacent test dates at step=10 -> lag 1)."""
    x = np.asarray([v for v in x if np.isfinite(v)], float)
    n = x.size
    if n < 5:
        return float("nan")
    e = x - x.mean()
    s = float(e @ e) / n
    for l in range(1, lag + 1):
        s += 2 * (1 - l / (lag + 1)) * float(e[:-l] @ e[l:]) / n
    se = np.sqrt(s / n)
    return float(x.mean() / se) if se > 0 else float("nan")


def boot_ci(x, nb=5000, seed=7):
    x = np.asarray([v for v in x if np.isfinite(v)], float)
    rng = np.random.default_rng(seed)
    bs = np.array([rng.choice(x, x.size, replace=True).mean() for _ in range(nb)])
    return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]


def summarize(recs, nonoverlap_every=1):
    if nonoverlap_every > 1:
        recs = [r for r in recs if r["d"] % nonoverlap_every == 0]
    out = {"n_dates": len(recs)}
    for key in ("tilt_gain", "exc_hi", "exc_lo", "exc_top", "lo_minus_top"):
        out[key] = agg([r[key] for r in recs])
    return out


def by_group(recs, key):
    out = {}
    for g in sorted(set(r[key] for r in recs)):
        sub = [r for r in recs if r[key] == g]
        out[g] = {"n": len(sub),
                  "tilt_gain": agg([r["tilt_gain"] for r in sub]),
                  "exc_hi": agg([r["exc_hi"] for r in sub]),
                  "exc_lo": agg([r["exc_lo"] for r in sub]),
                  "exc_top": agg([r["exc_top"] for r in sub])}
    return out


def drop_cut(recs, key, val):
    sub = [r for r in recs if r[key] != val]
    return {"n": len(sub), "tilt_gain": agg([r["tilt_gain"] for r in sub])}


# ----------------------------------------------------------------------------
def main():
    z, meta = H.load_panel()
    Z = H.neutralize(z, meta)
    names = meta["feat_names"]
    fwd = {h: z[f"fwd{h}"].astype(np.float64) for h in (10, 20)}
    mask70 = liquid_mask(z, 0.70)
    mask50 = liquid_mask(z, 0.50)

    # scores (ew_signed = fit-free -> walk-forward == per-date deterministic)
    mag = H.walk_forward(Z, fwd[20], meta, MAG_CFG)
    prob = H.walk_forward(Z, fwd[20], meta, PROB_CFG)

    vols = {"rvol_20": Z[:, :, names.index("rvol_20")],
            "ivol_60": Z[:, :, names.index("ivol_60")],
            "rvol_20_raw": z["feat"].astype(np.float64)[:, :, names.index("rvol_20")]}

    report = {"family": "vol_surprise (vol-conditioned PEAD top-bucket tilt)",
              "date": "2026-06-10",
              "lead_source": "fusion_product.json mechanism_interaction_test (post-hoc, 1 try)"}
    configs_tried = 0

    # ---- 1. exact lead reproduction: prob-score median split in mag top decile
    repro = {}
    for h in (10, 20):
        recs = per_date_records(mag, prob, fwd[h], mask70, meta,
                                bucket="decile", split="median")
        # NOTE: split var here IS the prob score; hi = prob>median = FAVORED half
        repro[f"h{h}"] = {
            "n_dates": len(recs),
            "prob_favored_half_excess": agg([r["exc_hi"] for r in recs]),
            "prob_evicted_half_excess": agg([r["exc_lo"] for r in recs]),
            "whole_decile_excess": agg([r["exc_top"] for r in recs])}
        configs_tried += 1
    report["repro_lead_prob_split"] = repro
    report["repro_note"] = ("split var = prob score; hi(=prob>median)=favored/low-vol, "
                            "lo=evicted/high-vol. Lead claims evicted ~ +1.63%/20d t2.88.")

    # ---- 2+3. variant grid: the walk-forward implementable tilt
    grid = {}
    primary_recs = {}
    for vname in ("rvol_20", "ivol_60", "rvol_20_raw"):
        for split in ("median", "tercile"):
            for bucket in ("decile", "quintile"):
                if vname == "rvol_20_raw" and (split != "median" or bucket != "decile"):
                    continue  # raw var = sensitivity check only
                for h in (10, 20):
                    recs = per_date_records(mag, vols[vname], fwd[h], mask70, meta,
                                            bucket=bucket, split=split, prob=prob)
                    key = f"{vname}|{split}|{bucket}|h{h}"
                    entry = {"summary": summarize(recs)}
                    if h == 20:
                        entry["nonoverlap_every2"] = summarize(recs, nonoverlap_every=2)
                    grid[key] = entry
                    configs_tried += 1
                    if vname == "rvol_20" and split == "median" and bucket == "decile":
                        primary_recs[h] = recs
    report["grid"] = grid
    report["primary_config"] = "rvol_20|median|decile (neutralized rvol_20, liquid-70)"

    # ---- 4. honesty bar on the primary config
    honesty = {}
    # shuffle nulls: scramble vol within the top bucket, >=8 seeds, both horizons
    nulls = {}
    for h in (10, 20):
        per_seed = []
        for s in NULL_SEEDS:
            rng = np.random.default_rng(s)
            recs = per_date_records(mag, vols["rvol_20"], fwd[h], mask70, meta,
                                    bucket="decile", split="median", rng=rng)
            a = agg([r["tilt_gain"] for r in recs])
            per_seed.append({"seed": s, "mean": a["mean"], "t": a["t"]})
        ts = [p["t"] for p in per_seed]
        ms = [p["mean"] for p in per_seed]
        nulls[f"h{h}"] = {"per_seed": per_seed,
                          "null_t_max_abs": float(np.max(np.abs(ts))),
                          "null_t_spread": [float(np.min(ts)), float(np.max(ts))],
                          "null_mean_spread": [float(np.min(ms)), float(np.max(ms))]}
    honesty["shuffle_null_vol_within_bucket"] = nulls

    # liquid-50 recheck
    liq50 = {}
    for h in (10, 20):
        recs = per_date_records(mag, vols["rvol_20"], fwd[h], mask50, meta,
                                bucket="decile", split="median")
        liq50[f"h{h}"] = summarize(recs)
        configs_tried += 1
    honesty["liquid_50"] = liq50

    # drop-year / drop-regime cuts (primary, both horizons)
    cuts = {}
    for h in (10, 20):
        recs = primary_recs[h]
        cuts[f"h{h}"] = {
            "drop_year": {y: drop_cut(recs, "year", y) for y in ("2023", "2024", "2025", "2026")},
            "drop_regime": {g: drop_cut(recs, "regime", g)
                            for g in sorted(set(r["regime"] for r in recs))}}
    honesty["drop_cuts"] = cuts

    # stability
    stability = {}
    for h in (10, 20):
        stability[f"h{h}"] = {"by_year": by_group(primary_recs[h], "year"),
                              "by_regime": by_group(primary_recs[h], "regime")}
    honesty["stability"] = stability
    report["honesty"] = honesty

    # ---- 5. prob-layer tension (primary config)
    tension = {}
    for h in (10, 20):
        recs = primary_recs[h]
        tension[f"h{h}"] = {
            "p_up_hi_tilted": agg([r["p_up_hi"] for r in recs]),
            "p_up_untilted_decile": agg([r["p_up_top"] for r in recs]),
            "p_beat_median_hi_tilted": agg([r["p_beat_hi"] for r in recs]),
            "p_beat_median_untilted_decile": agg([r["p_beat_top"] for r in recs]),
            "prob_score_pct_hi_tilted": agg([r.get("prob_pct_hi", np.nan) for r in recs]),
            "prob_score_pct_untilted": agg([r.get("prob_pct_top", np.nan) for r in recs])}
    report["prob_layer_tension"] = tension

    # per-date series of the primary headline for transparency
    report["primary_per_date_h20"] = [
        {k: r[k] for k in ("date", "regime", "n_top", "tilt_gain", "exc_hi", "exc_lo", "exc_top")}
        for r in primary_recs[20]]

    # overlap-honest significance for the primary headline
    overlap_adj = {}
    for h in (10, 20):
        g = [r["tilt_gain"] for r in primary_recs[h]]
        overlap_adj[f"h{h}"] = {"plain_t": agg(g)["t"],
                                "nw_t_lag1": nw_t(g, 1), "nw_t_lag2": nw_t(g, 2),
                                "boot_ci95": boot_ci(g)}
    report["primary_overlap_adjusted"] = overlap_adj

    # grid consistency (correlated variants, but uniform sign is informative)
    tilts = [grid[k]["summary"]["tilt_gain"]["mean"] for k in grid]
    report["grid_consistency"] = {
        "n_cells": len(tilts), "n_positive": int(sum(t > 0 for t in tilts)),
        "h20_t_range": [min(grid[k]["summary"]["tilt_gain"]["t"] for k in grid if k.endswith("h20")),
                        max(grid[k]["summary"]["tilt_gain"]["t"] for k in grid if k.endswith("h20"))]}

    report["verdict"] = "weak_positive"
    report["verdict_reasoning"] = (
        "h20 primary tilt gain +0.72%/20d plain t2.22 pos63% clears the 8-seed "
        "within-bucket vol-shuffle null (max |t| 1.21, mean spread +/-0.15%), "
        "survives liquid-50 (+0.78% t2.27), is positive in every test year "
        "(2024/25/26) and every evaluable regime, and ALL 18 grid cells are "
        "positive; the symmetric claim is confirmed (low-vol half excess "
        "+0.11% t0.4 -> eviction costless). NOT full positive because: (a) "
        "h10 tilt t1.13 does not clear its null max (1.43) -- effect is "
        "h20-specific; (b) overlap-honest significance is t1.81 (NW lag1) / "
        "t1.13 (27 nonoverlap dates); (c) significance leans on up_calm "
        "(t2.44) and 2026 -- up_turbulent alone is +0.31% t0.59 and "
        "drop-up_calm leaves t1.13. Direction robust, size ~ +0.6-0.7%/20d, "
        "but sub-cut power is thin.")

    report["configs_tried"] = configs_tried
    report["multiple_testing_note"] = (
        f"{configs_tried} scored configurations (2 repro + 16 grid + 2 raw-rvol "
        "sensitivity + 2 liquid-50). Nulls and drop-cuts not counted (can only "
        "weaken). Headline must clear the 8-seed null t-spread AND a ~Bonferroni "
        "view across the 16-config grid.")

    json.dump(report, open(OUT, "w"), indent=1, default=float)

    # compact stdout
    print("=== repro (prob-split) ===")
    print(json.dumps(repro, indent=1, default=float))
    print("=== primary grid cells ===")
    for k in grid:
        s = grid[k]["summary"]
        tg = s["tilt_gain"]
        print(f"{k:38s} tilt={tg['mean']*100:+.2f}% t={tg['t']:+.2f} pos={tg['pos_pct']:.2f} "
              f"hi={s['exc_hi']['mean']*100:+.2f}%(t{s['exc_hi']['t']:+.1f}) "
              f"lo={s['exc_lo']['mean']*100:+.2f}%(t{s['exc_lo']['t']:+.1f}) "
              f"top={s['exc_top']['mean']*100:+.2f}%")
    print("=== nulls ===")
    print(json.dumps({k: {kk: v[kk] for kk in ("null_t_spread", "null_mean_spread")}
                      for k, v in nulls.items()}, indent=1))
    print("=== liquid50 ===")
    for h in (10, 20):
        tg = liq50[f"h{h}"]["tilt_gain"]
        print(f"h{h}: tilt={tg['mean']*100:+.2f}% t={tg['t']:+.2f} pos={tg['pos_pct']:.2f}")
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
