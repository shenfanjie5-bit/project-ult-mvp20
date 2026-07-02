#!/usr/bin/env python3
"""Synthesis-phase self-verification (do it myself, not just trust agents).

Quantifies the two things that decide the honest ceiling:
  1. The covered-universe-vs-REAL-market benchmark gap (how much of any reported
     top_excess_uni is a benchmark artifact).
  2. Whether ANY candidate keeps a positive top-decile edge in the INVESTABLE
     (liquid, large-enough) universe -- dropping the smallest names that the
     audit showed drive the amihud/illiquidity artifact.

Evaluates: long-only top-decile ABSOLUTE return vs the real MV-weighted market,
on the full universe AND on the liquid top-{70,50}% by ln_mv, at +10/+20d,
walk-forward.
"""
from __future__ import annotations
import json, os, sys
import numpy as np
sys.path.insert(0, os.getcwd())
from factor_research.model import harness as H

CANDIDATES = {
    "amihud(artifact)":      {"name": "ami", "method": "ic_weighted", "features": ["amihud"], "params": {"min_cov": 0.5}, "min_train_dates": 12},
    "earnings_surprise":     {"name": "es", "method": "ew_signed", "features": ["sue", "npq_yoy"], "params": {"min_cov": 0.5}, "min_train_dates": 12},
    "value_quality_surprise":{"name": "vqs", "method": "ic_weighted", "features": ["ep_ttm", "bp", "dy", "roe", "gpm", "q_roe", "sue", "npq_yoy", "debt_assets"], "params": {"halflife": 12, "min_cov": 0.5}, "min_train_dates": 12},
    "gbdt_blend":            {"name": "gb", "method": "gbdt", "features": ["amihud", "npq_yoy", "sue", "debt_assets", "turnover_20", "turnover_trend", "q_roe", "asset_turn"], "regime_feature": True, "params": {"n_estimators": 300, "num_leaves": 7, "max_depth": 3, "min_child": 300, "reg_lambda": 7.0, "lr": 0.03}, "lookback_dates": 40, "min_train_dates": 20},
}


def market_fwd(z, horizon):
    """real MV-weighted market forward return per base date (all valid stocks)."""
    fwd = z[f"fwd{horizon}"].astype(np.float64)
    mv = np.exp(z["ln_mv"].astype(np.float64))
    D = fwd.shape[0]
    out = np.full(D, np.nan)
    cov = np.full(D, np.nan)
    for d in range(D):
        ok = np.isfinite(fwd[d]) & np.isfinite(mv[d]) & (mv[d] > 0)
        if ok.sum() > 50:
            out[d] = np.average(fwd[d][ok], weights=mv[d][ok])
            cov[d] = float(np.nanmean(fwd[d][ok]))   # covered-universe EQUAL-weight mean (the benchmark used in top_excess_uni)
    return out, cov


def liquid_mask(z, frac):
    """per-date mask keeping the largest `frac` by ln_mv (drop smallest)."""
    lnmv = z["ln_mv"].astype(np.float64)
    D, N = lnmv.shape
    m = np.zeros((D, N), bool)
    for d in range(D):
        v = lnmv[d]; ok = np.isfinite(v)
        if ok.sum() < 50:
            continue
        thr = np.percentile(v[ok], 100 * (1 - frac))
        m[d] = ok & (v >= thr)
    return m


def eval_topbucket(scores, fwd, mask, mkt):
    """long-only top-decile abs return, excess vs covered-universe EW mean, and
    excess vs REAL MV-weighted market; mean across dates + t."""
    D = scores.shape[0]
    top_abs, exc_uni, exc_mkt = [], [], []
    for d in range(D):
        sc = np.where(mask[d], scores[d], np.nan)
        rt = fwd[d]
        ok = np.isfinite(sc) & np.isfinite(rt)
        if ok.sum() < 50 or not np.isfinite(mkt[d]):
            continue
        uni = float(np.nanmean(rt[ok]))
        order = np.argsort(np.where(np.isfinite(sc), sc, -np.inf))
        ntop = max(5, int(ok.sum() // 10))
        top = order[-ntop:]
        tr = rt[top]; tr = tr[np.isfinite(tr)]
        if tr.size < 3:
            continue
        ta = float(tr.mean())
        top_abs.append(ta); exc_uni.append(ta - uni); exc_mkt.append(ta - mkt[d])
    def stat(a):
        a = np.array(a)
        if a.size < 3:
            return None
        return {"mean": float(a.mean()),
                "t": float(a.mean() / (a.std(ddof=1) / np.sqrt(a.size))),
                "pos%": float((a > 0).mean()), "n": int(a.size)}
    return {"top_abs": stat(top_abs), "excess_vs_universe": stat(exc_uni), "excess_vs_REAL_market": stat(exc_mkt)}


def main():
    z, meta = H.load_panel()
    Z = H.neutralize(z, meta)
    for horizon in (10, 20):
        mkt, cov = market_fwd(z, horizon)
        gap = np.nanmean(cov - mkt)
        print(f"\n{'='*92}\nHORIZON +{horizon}d  | covered-universe EW mean vs REAL MV-weighted market: avg gap = {gap:+.4f} ({gap*100:+.2f}pp)")
        print(f"  (positive gap => top_excess_uni is inflated by this much vs a real-market benchmark)\n")
        fwd = z[f"fwd{horizon}"].astype(np.float64)
        masks = {"FULL": np.isfinite(z["ln_mv"]) & True, "liquid_top70": liquid_mask(z, 0.70), "liquid_top50": liquid_mask(z, 0.50)}
        # FULL mask: all finite-lnmv
        masks["FULL"] = np.isfinite(z["ln_mv"].astype(np.float64))
        print(f"  {'candidate':24} {'universe':13} {'topAbs':>9} {'vsUniv(t)':>14} {'vsMKT(t)':>14}")
        for cname, cfg in CANDIDATES.items():
            scores = H.walk_forward(Z, fwd, meta, cfg)
            for mname, mask in masks.items():
                r = eval_topbucket(scores, fwd, mask, mkt)
                eu = r["excess_vs_universe"]; em = r["excess_vs_REAL_market"]; ta = r["top_abs"]
                if eu is None:
                    continue
                print(f"  {cname:24} {mname:13} {ta['mean']:+8.4f} {eu['mean']:+8.4f}({eu['t']:+4.1f}) {em['mean']:+8.4f}({em['t']:+4.1f})")
            print()


if __name__ == "__main__":
    main()
