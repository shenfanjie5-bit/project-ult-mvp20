#!/usr/bin/env python3
"""Phase-3b prototype: does REGIME-CONDITIONING beat the STATIC tilt? (ISOLATED, read-only)

The live base_score is only cached at 3 (2026) dates → can't recompute across history
without the slow PIT pipeline. So we test a transparent PROXY of the model's short-horizon
tilt: L_static = z(STREV) - z(RVOL) (reversal + low-vol; empirically corr +0.5/-0.5 with the
real short_total). We compare its forward IC to a regime-conditioned version R_regime.
All standardization is cross-sectional (no lookahead); the vol threshold is an EXPANDING
median (past-only). Also sanity-checks the 3 real base_score dates.
"""
from __future__ import annotations
import os, sys, math, json, sqlite3
import numpy as np
sys.path.insert(0, os.getcwd())
from pit_backtest.metrics import rank_ic, aggregate_ic_across_windows
from factor_research._datalib import load_price_matrices

def log(*a): print(*a, flush=True)
LOOKBACK, VOLWIN, HORIZONS = 21, 20, [10, 20]

def zscore(v):
    m = np.isfinite(v)
    if m.sum() < 30: return np.full_like(v, np.nan)
    mu, sd = np.nanmean(v[m]), np.nanstd(v[m])
    if sd < 1e-9: return np.full_like(v, np.nan)
    z = (v - mu) / sd
    return np.clip(z, -3, 3)

def main():
    RET, TO, MV, cal, cols = load_price_matrices("20230101")
    n, m = RET.shape
    LR = np.log1p(np.nan_to_num(RET, nan=0.0)); CUM = np.cumsum(LR, axis=0)
    HAS = ~np.isnan(RET); first_valid = np.where(HAS.any(0), HAS.argmax(0), n + 1)
    mkt = np.nanmean(RET, axis=1); mkt_lr = np.log1p(np.nan_to_num(mkt, 0.0)); mkt_cum = np.cumsum(mkt_lr)
    mvol_series = np.array([np.std(mkt[max(0,k-VOLWIN+1):k+1], ddof=1)*math.sqrt(252) if k>=VOLWIN else np.nan for k in range(n)])

    def fwd(k, h):
        if k + h >= n: return None
        fr = np.exp(CUM[k + h] - CUM[k]) - 1.0
        ok = HAS[k] & (first_valid <= k) & HAS[k + 1:k + h + 1].any(0)
        return np.where(ok, fr, np.nan)

    def components(k):
        past = np.exp(CUM[k] - CUM[k - LOOKBACK]) - 1.0
        strev = -past
        rvol = np.nanstd(RET[k - VOLWIN + 1:k + 1], axis=0, ddof=1) * math.sqrt(252)
        listed = (first_valid <= k - LOOKBACK) & HAS[k]
        sz = zscore(np.where(listed, strev, np.nan)); rz = zscore(np.where(listed, rvol, np.nan))
        return sz, rz

    def regime(k):
        trend60 = math.exp(mkt_cum[k] - mkt_cum[k - 60]) - 1.0
        vol20 = mvol_series[k]
        past_vols = mvol_series[max(0, k-250):k]; past_vols = past_vols[np.isfinite(past_vols)]
        vmed = float(np.median(past_vols)) if len(past_vols) > 20 else 0.22  # expanding/rolling median (past-only)
        return trend60, vol20, vmed

    base_idx = [k for k in range(max(LOOKBACK, 60) + 1, n - max(HORIZONS)) if k % 10 == 0]
    res = {"meta": {"universe": m, "n_base": len(base_idx), "horizons": HORIZONS,
                    "design": "L_static = z(STREV) - z(RVOL) [proxy of live short tilt]; "
                              "R_regime: reversal weight 1.0 if mkt trend<0 else 0.5; low-vol penalty only if mkt vol<=expanding median (else dropped). PIT-clean.",
                    "caveat": "proxy of base_score (live score cached at 3 dates only); IC is ordering evidence not alpha proof; overlapping windows"},
           "variants": {}}
    ic = {"L_static": {h: [] for h in HORIZONS}, "R_regime": {h: [] for h in HORIZONS}}
    paired = {h: [] for h in HORIZONS}
    for k in base_idx:
        sz, rz = components(k)
        tr, vol, vmed = regime(k)
        w_rev = 1.0 if tr < 0 else 0.5
        w_lv = 1.0 if (np.isfinite(vol) and vol <= vmed) else 0.0
        L = sz - rz
        R = w_rev * sz - w_lv * rz
        yr = cal[k][:4]
        for h in HORIZONS:
            fr = fwd(k, h)
            if fr is None: continue
            il = rank_ic(L, fr)["ic"]; ir = rank_ic(R, fr)["ic"]
            if np.isfinite(il) and np.isfinite(ir):
                ic["L_static"][h].append((yr, il)); ic["R_regime"][h].append((yr, ir))
                paired[h].append((yr, ir - il))
    for v in ("L_static", "R_regime"):
        res["variants"][v] = {}
        for h in HORIZONS:
            ics = [x for _, x in ic[v][h]]; agg = aggregate_ic_across_windows(ics)
            years = sorted(set(y for y, _ in ic[v][h]))
            py = {y: round(float(np.mean([x for yy, x in ic[v][h] if yy == y])), 4) for y in years}
            res["variants"][v][f"h{h}"] = {"mean_ic": round(agg["mean_ic"], 4),
                "std_ic": round(agg["std_ic"], 4) if np.isfinite(agg["std_ic"]) else None,
                "pct_pos": round(float(np.mean([1.0 if x > 0 else 0 for x in ics])), 2), "per_year": py}
    res["paired_improvement"] = {}
    for h in HORIZONS:
        d = [x for _, x in paired[h]]
        years = sorted(set(y for y, _ in paired[h]))
        res["paired_improvement"][f"h{h}"] = {"mean_delta_ic": round(float(np.mean(d)), 4),
            "pct_windows_R_gt_L": round(float(np.mean([1.0 if x > 0 else 0 for x in d])), 2),
            "per_year_delta": {y: round(float(np.mean([x for yy, x in paired[h] if yy == y])), 4) for y in years}}

    # sanity on the 3 REAL base_score dates
    c = sqlite3.connect("file:runtime/backtest/backtest.sqlite?mode=ro", uri=True); real = {}
    for bd in ["20260116", "20260309", "20260421"]:
        cand = [d for d in cal if d <= bd]
        if not cand: continue
        k = cal.index(cand[-1]); tr, vol, vmed = regime(k)
        rows = {r[0]: r[1] for r in c.execute("SELECT ts_code, base_score FROM scores WHERE base_date=?", (bd,))}
        bs = np.array([rows.get(ts, np.nan) for ts in cols])
        rr = {}
        for h in HORIZONS:
            fr = fwd(k, h)
            rr[f"h{h}_ic_base_score"] = round(rank_ic(bs, fr)["ic"], 3) if fr is not None else None
        rr["regime"] = {"trend60": round(tr, 3), "vol20": round(float(vol), 3), "vol_median": round(vmed, 3),
                        "classified": ("down" if tr < 0 else "up") + "/" + ("highvol" if vol > vmed else "lowvol")}
        real[bd] = rr
    c.close(); res["real_base_score_3dates"] = real

    json.dump(res, open("factor_research/data/prototype_results.json", "w"), ensure_ascii=False, indent=1)
    log("\n==== STATIC vs REGIME-CONDITIONED (proxy of live short tilt) ====")
    for h in HORIZONS:
        L = res["variants"]["L_static"][f"h{h}"]; R = res["variants"]["R_regime"][f"h{h}"]
        log(f"\n  +{h}d  L_static mean_IC={L['mean_ic']:+.4f} (pos%={L['pct_pos']})   R_regime mean_IC={R['mean_ic']:+.4f} (pos%={R['pct_pos']})")
        log(f"        per-year L: " + " ".join(f"{y}:{v:+.3f}" for y, v in L['per_year'].items()))
        log(f"        per-year R: " + " ".join(f"{y}:{v:+.3f}" for y, v in R['per_year'].items()))
        pi = res["paired_improvement"][f"h{h}"]
        log(f"        Δ(R−L) mean={pi['mean_delta_ic']:+.4f}  R>L in {pi['pct_windows_R_gt_L']*100:.0f}% windows  per-year Δ: " + " ".join(f"{y}:{v:+.3f}" for y, v in pi['per_year_delta'].items()))
    log("\n==== REAL base_score IC at 3 cached dates (sanity) ====")
    for bd, d in real.items():
        log(f"  {bd} [{d['regime']['classified']}] +10d IC={d.get('h10_ic_base_score')} +20d IC={d.get('h20_ic_base_score')}")
    log("\nwrote factor_research/data/prototype_results.json")

if __name__ == "__main__":
    main()
