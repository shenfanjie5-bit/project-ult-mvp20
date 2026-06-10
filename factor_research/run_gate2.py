#!/usr/bin/env python3
"""Tier-1 regime decision-gate v2 — DUAL-condition down-weight.

Improves RESULTS5 run_gate.py (single hard binary skip "is_bad -> cash", which
saved 2026 but hurt 2024/2025 → net -0.27pp). Here the gate fires ONLY when BOTH:
  (1) bad_regime  = up-trend AND high-vol (meltup; same economic def as v1), AND
  (2) ic_decay    = the proxy's TRAILING realized IC (matured windows only, PIT-safe
                    'model is currently failing' proxy) has gone negative.
Down-weight only (w in [w_min,1]), NEVER sign-flip. Zero tuned params → no overfit;
every gate decision uses only past data (causal/walk-forward by construction).
Validated on BUY-cohort forward P&L + worst-window tail + per-year, NOT on IC.
read-only; writes only factor_research/data/gate2_results.json.
"""
from __future__ import annotations
import os, sys, math, json, warnings
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
from pit_backtest.metrics import rank_ic
from factor_research._datalib import load_price_matrices

def log(*a): print(*a, flush=True)
LOOKBACK, VOLWIN, TRENDWIN = 21, 20, 60
HORIZONS = [10, 20]
DECILE = 0.1
IC_HZ = 10          # horizon used to measure the model's realized IC (decay signal)
DECAY_M = int(sys.argv[2]) if len(sys.argv) > 2 else 6   # trailing window count for decay avg
STEP = 10           # window stride (trading days)

# ── helpers (copied from run_gate.py, self-contained) ────────────────────────
def zscore(v):
    m = np.isfinite(v)
    if m.sum() < 30: return np.full_like(v, np.nan)
    mu, sd = np.nanmean(v[m]), np.nanstd(v[m])
    if sd < 1e-9: return np.full_like(v, np.nan)
    return np.clip((v - mu) / sd, -3, 3)

def fwd_ret_vec(k, h, CUM, HAS, first_valid, n):
    if k + h >= n: return None
    fr = np.exp(CUM[k + h] - CUM[k]) - 1.0
    ok = HAS[k] & (first_valid <= k) & HAS[k + 1:k + h + 1].any(0)
    return np.where(ok, fr, np.nan)

def regime(k, mkt_cum, mvol_series):
    trend60 = math.exp(mkt_cum[k] - mkt_cum[k - TRENDWIN]) - 1.0
    vol20 = mvol_series[k]
    past = mvol_series[max(0, k - 250):k]; past = past[np.isfinite(past)]
    vmed = float(np.median(past)) if len(past) > 20 else 0.22
    is_bad = (trend60 > 0) and (np.isfinite(vol20) and vol20 > vmed)
    return trend60, (float(vol20) if np.isfinite(vol20) else float("nan")), vmed, is_bad

def components(k, CUM, HAS, first_valid, RET):
    past = np.exp(CUM[k] - CUM[k - LOOKBACK]) - 1.0
    strev = -past
    rvol = np.nanstd(RET[k - VOLWIN + 1:k + 1], axis=0, ddof=1) * math.sqrt(252)
    listed = (first_valid <= k - LOOKBACK) & HAS[k]
    return zscore(np.where(listed, strev, np.nan)), zscore(np.where(listed, rvol, np.nan))

def cohort_mean(factor, fwd, top_frac=DECILE):
    m = np.isfinite(factor) & np.isfinite(fwd)
    if m.sum() < 20: return float("nan")
    f, r = factor[m], fwd[m]
    top = r[f >= np.percentile(f, (1 - top_frac) * 100)]
    return float(np.mean(top)) if len(top) else float("nan")

def real_ic(factor, fwd):
    m = np.isfinite(factor) & np.isfinite(fwd)
    if m.sum() < 30: return float("nan")
    return rank_ic(list(factor[m]), list(fwd[m]))["ic"]

# ── main ─────────────────────────────────────────────────────────────────────
def main():
    log("loading price matrices…")
    RET, TO, MV, cal, cols = load_price_matrices("20230101")
    n, m = RET.shape
    CUM = np.cumsum(np.log1p(np.nan_to_num(RET, nan=0.0)), axis=0)
    HAS = ~np.isnan(RET)
    first_valid = np.where(HAS.any(0), HAS.argmax(0), n + 1)
    mkt = np.nanmean(RET, axis=1)
    mkt_cum = np.cumsum(np.log1p(np.nan_to_num(mkt, 0.0)))
    mvol = np.array([np.std(mkt[max(0, k - VOLWIN + 1):k + 1], ddof=1) * math.sqrt(252)
                     if k >= VOLWIN else np.nan for k in range(n)])

    start = TRENDWIN + 260
    windows = list(range(start, n - max(HORIZONS) - 1, STEP))
    rows = []
    for k in windows:
        tr60, vol20, vmed, is_bad = regime(k, mkt_cum, mvol)
        sz, rz = components(k, CUM, HAS, first_valid, RET)
        L = sz - rz
        rec = {"k": k, "date": str(cal[k]), "year": str(cal[k])[:4], "is_bad": bool(is_bad)}
        for h in HORIZONS:
            fwd = fwd_ret_vec(k, h, CUM, HAS, first_valid, n)
            rec[f"ung{h}"] = cohort_mean(L, fwd) if fwd is not None else float("nan")
        fic = fwd_ret_vec(k, IC_HZ, CUM, HAS, first_valid, n)
        rec["ric"] = real_ic(L, fic) if fic is not None else float("nan")  # realized proxy IC at this window
        rows.append(rec)

    # trailing realized IC — matured windows only (window j matured if j.k + IC_HZ <= k)
    for i, r in enumerate(rows):
        hist = [rows[j]["ric"] for j in range(i)
                if np.isfinite(rows[j]["ric"]) and rows[j]["k"] + IC_HZ <= r["k"]]
        r["trail_ic"] = float(np.mean(hist[-DECAY_M:])) if len(hist) >= 3 else float("nan")

    # ── apply gates ──
    W_MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    def stats(vals):
        a = np.array([v for v in vals if np.isfinite(v)])
        return (float(a.mean()) if len(a) else float("nan"),
                float(np.percentile(a, 5)) if len(a) else float("nan"))
    out = {"meta": {"design": "dual gate = is_bad AND trailing_realized_IC<0 → w_min; "
                    "down-weight only, causal/zero-tuned. Proxy L=z(STREV)-z(RVOL).",
                    "IC_HZ": IC_HZ, "DECAY_M": DECAY_M, "W_MIN": W_MIN,
                    "n_windows": len(rows), "span": f"{rows[0]['date']}..{rows[-1]['date']}"}}
    for h in HORIZONS:
        ung, sing, dual = [], [], []
        fire_s = fire_d = tot = 0
        per_year = {}
        for r in rows:
            c = r[f"ung{h}"]
            if not np.isfinite(c): continue
            tot += 1
            s = 0.0 if r["is_bad"] else c
            fire = r["is_bad"] and np.isfinite(r["trail_ic"]) and r["trail_ic"] < 0
            d = (W_MIN * c) if fire else c
            ung.append(c); sing.append(s); dual.append(d)
            fire_s += int(r["is_bad"]); fire_d += int(fire)
            py = per_year.setdefault(r["year"], {"u": [], "s": [], "d": []})
            py["u"].append(c); py["s"].append(s); py["d"].append(d)
        um, ut = stats(ung); sm, st = stats(sing); dm, dt = stats(dual)
        log(f"\n═══ +{h}d cohort return (n_windows={tot}) ═══")
        log(f"  {'variant':16}{'mean':>9}{'worst(5pct)':>13}{'%gated':>9}")
        log(f"  {'ungated':16}{um*100:>+8.2f}%{ut*100:>+12.2f}%{'—':>9}")
        log(f"  {'single-gate(v1)':16}{sm*100:>+8.2f}%{st*100:>+12.2f}%{100*fire_s/tot:>8.0f}%")
        log(f"  {'DUAL-gate(v2)':16}{dm*100:>+8.2f}%{dt*100:>+12.2f}%{100*fire_d/tot:>8.0f}%")
        log(f"  per-year mean (ungated → single → dual):")
        for yr in sorted(per_year):
            p = per_year[yr]
            log(f"    {yr}: {np.mean(p['u'])*100:>+6.2f}% → {np.mean(p['s'])*100:>+6.2f}% → {np.mean(p['d'])*100:>+6.2f}%")
        out[f"h{h}"] = {"ungated_mean": um, "single_mean": sm, "dual_mean": dm,
                        "ungated_worst": ut, "single_worst": st, "dual_worst": dt,
                        "pct_gated_single": fire_s/tot, "pct_gated_dual": fire_d/tot,
                        "per_year": {yr: {k2: float(np.mean(v2)) for k2, v2 in p.items()}
                                     for yr, p in per_year.items()}}
    op = "factor_research/data/gate2_results.json"
    json.dump(out, open(op, "w"), indent=2)
    log(f"\nwrote {op}")

if __name__ == "__main__":
    main()
