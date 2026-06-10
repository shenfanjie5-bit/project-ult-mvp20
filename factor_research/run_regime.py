#!/usr/bin/env python3
"""Phase-3b: regime-conditioning test (ISOLATED, read-only).
Tests whether STREV(reversal)/RVOL(low-vol) IC sign depends on market regime
(trend + vol). If IC is reliably signed WITHIN a regime, that validates R-7
(regime-conditioning) as the fix for the sign-flips found in RESULTS.md."""
from __future__ import annotations
import os, sys, math, json
import numpy as np
sys.path.insert(0, os.getcwd())
from pit_backtest.metrics import rank_ic
from factor_research._datalib import load_price_matrices

def log(*a): print(*a, flush=True)
LOOKBACK, VOLWIN = 21, 20
HORIZONS = [10, 20]

def main():
    RET, TO, MV, cal, cols = load_price_matrices("20230101")
    n, m = RET.shape
    log(f"matrices: {n} days x {m} stocks  {cal[0]}->{cal[-1]}")
    LR = np.log1p(np.nan_to_num(RET, nan=0.0))
    CUM = np.cumsum(LR, axis=0)
    HAS = ~np.isnan(RET)
    first_valid = np.where(HAS.any(0), HAS.argmax(0), n + 1)
    mkt = np.nanmean(RET, axis=1)                      # equal-weight market daily return
    mkt_lr = np.log1p(np.nan_to_num(mkt, nan=0.0)); mkt_cum = np.cumsum(mkt_lr)

    def fwd(k, h):
        if k + h >= n: return None
        fr = np.exp(CUM[k + h] - CUM[k]) - 1.0
        ok = HAS[k] & (first_valid <= k) & HAS[k + 1:k + h + 1].any(0)
        return np.where(ok, fr, np.nan)

    def facts(k):
        past = np.exp(CUM[k] - CUM[k - LOOKBACK]) - 1.0
        strev = -past
        rvol = np.nanstd(RET[k - VOLWIN + 1:k + 1], axis=0, ddof=1) * math.sqrt(252)
        listed = (first_valid <= k - LOOKBACK) & HAS[k]
        return np.where(listed, strev, np.nan), np.where(listed, rvol, np.nan)

    rows = []  # (date, mkt_ret60, mkt_vol20, h, ic_strev, ic_rvol)
    for k in range(max(LOOKBACK, 60) + 1, n - max(HORIZONS)):
        if k % 5: continue
        mret60 = math.exp(mkt_cum[k] - mkt_cum[k - 60]) - 1.0
        mvol20 = float(np.std(mkt[k - VOLWIN + 1:k + 1], ddof=1) * math.sqrt(252))
        strev, rvol = facts(k)
        for h in HORIZONS:
            fr = fwd(k, h)
            if fr is None: continue
            ics = rank_ic(strev, fr)["ic"]; icr = rank_ic(rvol, fr)["ic"]
            if np.isfinite(ics) and np.isfinite(icr):
                rows.append((cal[k], mret60, mvol20, h, ics, icr))

    arr = rows
    def bucket(h, trend_up, vol_hi, vol_med):
        sel = [r for r in arr if r[3] == h and (r[1] > 0) == trend_up and (r[2] > vol_med) == vol_hi]
        if not sel: return None
        return (round(float(np.mean([r[4] for r in sel])), 4),  # STREV mean IC
                round(float(np.mean([r[5] for r in sel])), 4),  # RVOL  mean IC
                len(sel))

    out = {"meta": {"n_windows_per_h": {h: sum(1 for r in arr if r[3] == h) for h in HORIZONS},
                    "note": "overlapping 5td windows; regime buckets show IC sign conditional on market trend/vol"}, "buckets": {}, "corr": {}}
    log("\n==== IC by REGIME bucket (mean rank-IC; STREV=reversal, RVOL=low-vol) ====")
    for h in HORIZONS:
        vols = [r[2] for r in arr if r[3] == h]; vmed = float(np.median(vols)) if vols else 0.0
        log(f"\n  horizon +{h}d  (vol median={vmed:.2f})")
        out["buckets"][f"h{h}"] = {}
        for tu in (True, False):
            for vh in (True, False):
                b = bucket(h, tu, vh, vmed)
                tag = f"{'trendUP' if tu else 'trendDN'}/{'volHI' if vh else 'volLO'}"
                if b:
                    log(f"    {tag:18} STREV_IC={b[0]:+.4f}  RVOL_IC={b[1]:+.4f}  (n={b[2]})")
                    out["buckets"][f"h{h}"][tag] = {"strev_ic": b[0], "rvol_ic": b[1], "n": b[2]}
        # continuous: corr(regime feature, per-window IC)
        sub = [r for r in arr if r[3] == h]
        if len(sub) > 10:
            mr = np.array([r[1] for r in sub]); mv = np.array([r[2] for r in sub])
            si = np.array([r[4] for r in sub]); ri = np.array([r[5] for r in sub])
            def pc(a, b):
                a, b = a - a.mean(), b - b.mean()
                d = math.sqrt((a*a).sum()*(b*b).sum()); return round(float((a*b).sum()/d), 3) if d else None
            out["corr"][f"h{h}"] = {"trend_vs_STREV_ic": pc(mr, si), "trend_vs_RVOL_ic": pc(mr, ri),
                                     "vol_vs_STREV_ic": pc(mv, si), "vol_vs_RVOL_ic": pc(mv, ri)}
            log(f"    corr(mkt_trend, STREV_IC)={out['corr'][f'h{h}']['trend_vs_STREV_ic']:+.3f}  corr(mkt_trend, RVOL_IC)={out['corr'][f'h{h}']['trend_vs_RVOL_ic']:+.3f}")
            log(f"    corr(mkt_vol,   STREV_IC)={out['corr'][f'h{h}']['vol_vs_STREV_ic']:+.3f}  corr(mkt_vol,   RVOL_IC)={out['corr'][f'h{h}']['vol_vs_RVOL_ic']:+.3f}")

    json.dump(out, open("factor_research/data/regime_results.json", "w"), ensure_ascii=False, indent=1)
    log("\nwrote factor_research/data/regime_results.json")

if __name__ == "__main__":
    main()
