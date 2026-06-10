#!/usr/bin/env python3
"""Phase-3b: SUE/PEAD empirical test (ISOLATED, read-only).
Is the fundamental factor SUE (the only Phase-3a POSITIVE) more regime-stable
than the price/vol factors that flipped sign? Seasonal-random-walk SUE from
income n_income_attr_p (YTD→single-quarter), PIT-aligned by announce date."""
from __future__ import annotations
import os, sys, math, json, bisect
import numpy as np
sys.path.insert(0, os.getcwd())
from pit_backtest.metrics import rank_ic, quantile_groups, aggregate_ic_across_windows
from factor_research._datalib import load_price_matrices, load_quarterly_earnings

def log(*a): print(*a, flush=True)
HORIZONS = [10, 15, 20]; MIN_HIST = 6

def prev_year(ed): return str(int(ed[:4]) - 1) + ed[4:]

def _sue_series(recs):
    q = {ed: v for _, ed, v in recs}
    ann_of = {ed: a for a, ed, _ in recs}
    eds = sorted(q)
    surp = []  # (end, ann, s)
    for ed in eds:
        py = prev_year(ed)
        if py in q:
            surp.append((ed, ann_of[ed], q[ed] - q[py]))
    out = []
    svals = []
    for ed, ann, s in surp:
        if len(svals) >= MIN_HIST:
            sd = float(np.std(svals, ddof=1))
            if sd > 1e-6:
                out.append((ann, max(-5.0, min(5.0, s / sd))))
        svals.append(s)
    return out  # [(ann_date, sue)] in surprise order (~asc by end/ann)

def main():
    RET, TO, MV, cal, cols = load_price_matrices("20230101")
    n, m = RET.shape
    LR = np.log1p(np.nan_to_num(RET, nan=0.0)); CUM = np.cumsum(LR, axis=0)
    HAS = ~np.isnan(RET); first_valid = np.where(HAS.any(0), HAS.argmax(0), n + 1)
    earn = load_quarterly_earnings(cols, start="20180101")
    log(f"earnings coverage: {len(earn)}/{m} stocks")

    # build SUE matrix (n x m) + days-since-announce matrix, PIT forward-filled
    SUE = np.full((n, m), np.nan); DSA = np.full((n, m), np.nan)
    for j, ts in enumerate(cols):
        if ts not in earn: continue
        ser = _sue_series(earn[ts])
        ser = [(a, v) for a, v in ser if a and a <= cal[-1]]
        ser.sort()
        if not ser: continue
        anns = [a for a, _ in ser]
        for i, d in enumerate(cal):
            p = bisect.bisect_right(anns, d) - 1
            if p >= 0:
                SUE[i, j] = ser[p][1]
                # days since announce (calendar idx diff approx via trading days)
                ai = bisect.bisect_left(cal, anns[p])
                DSA[i, j] = i - ai
    log("SUE matrix filled")

    def fwd(k, h):
        if k + h >= n: return None
        fr = np.exp(CUM[k + h] - CUM[k]) - 1.0
        ok = HAS[k] & (first_valid <= k) & HAS[k + 1:k + h + 1].any(0)
        return np.where(ok, fr, np.nan)

    base_idx = [k for k in range(25, n - max(HORIZONS)) if k % 10 == 0]
    res = {"meta": {"universe": m, "earnings_cov": len(earn), "n_base": len(base_idx), "horizons": HORIZONS,
                    "note": "seasonal-RW SUE, PIT by announce date; overlapping windows → low power"}, "factors": {}}
    for label, fresh in [("SUE_all", None), ("SUE_fresh60", 60)]:
        ic = {h: [] for h in HORIZONS}; pooled = {h: {"x": [], "y": []} for h in HORIZONS}
        for k in base_idx:
            s = SUE[k].copy()
            if fresh is not None:
                s = np.where(DSA[k] <= fresh, s, np.nan)
            for h in HORIZONS:
                fr = fwd(k, h)
                if fr is None: continue
                r = rank_ic(s, fr)
                if np.isfinite(r["ic"]):
                    ic[h].append((cal[k][:4], r["ic"]))
                    pooled[h]["x"].extend(s.tolist()); pooled[h]["y"].extend(fr.tolist())
        res["factors"][label] = {}
        for h in HORIZONS:
            ics = [v for _, v in ic[h]]; agg = aggregate_ic_across_windows(ics)
            years = sorted(set(y for y, _ in ic[h]))
            per_year = {y: round(float(np.mean([v for yy, v in ic[h] if yy == y])), 4) for y in years}
            px, py = np.array(pooled[h]["x"]), np.array(pooled[h]["y"])
            q = quantile_groups(px, py, 10) if len(px) > 200 else {"top_minus_bottom": None}
            res["factors"][label][f"h{h}"] = {
                "mean_ic": round(agg["mean_ic"], 4), "std_ic": round(agg["std_ic"], 4) if np.isfinite(agg["std_ic"]) else None,
                "n_windows": agg["n_windows"], "pct_pos": round(float(np.mean([1.0 if v > 0 else 0.0 for v in ics])), 2) if ics else None,
                "per_year_ic": per_year, "decile_tmb": round(q["top_minus_bottom"], 4) if q.get("top_minus_bottom") is not None else None,
                "pooled_n": int(len(px)),
            }

    # orthogonality vs cached score
    import sqlite3
    c = sqlite3.connect("file:runtime/backtest/backtest.sqlite?mode=ro", uri=True)
    ortho = {}
    for bd in ["20260116", "20260309", "20260421"]:
        cand = [d for d in cal if d <= bd]
        if not cand: continue
        k = cal.index(cand[-1])
        rows = {r[0]: (r[1], r[2]) for r in c.execute("SELECT ts_code, base_score, short_total FROM scores WHERE base_date=?", (bd,))}
        bs = np.array([rows.get(ts, (np.nan, np.nan))[0] for ts in cols]); st = np.array([rows.get(ts, (np.nan, np.nan))[1] for ts in cols])
        ortho[bd] = {"vs_base_score": round(rank_ic(SUE[k], bs)["ic"], 3), "vs_short_total": round(rank_ic(SUE[k], st)["ic"], 3)}
    c.close(); res["orthogonality_vs_cached_score"] = ortho

    json.dump(res, open("factor_research/data/sue_results.json", "w"), ensure_ascii=False, indent=1)
    log("\n==== SUE IC ====")
    for label in res["factors"]:
        for h in HORIZONS:
            d = res["factors"][label][f"h{h}"]
            log(f"  {label:12} +{h:2}d IC={d['mean_ic']:+.4f} (±{d['std_ic']} n={d['n_windows']} pos%={d['pct_pos']}) decileTMB={d['decile_tmb']} poolN={d['pooled_n']}")
    log("\n==== SUE per-year IC (+20d) ====")
    for label in res["factors"]:
        log(f"  {label:12} " + "  ".join(f"{y}:{v:+.3f}" for y, v in res["factors"][label]["h20"]["per_year_ic"].items()))
    log("\n==== SUE orthogonality vs cached score ====")
    for bd, d in ortho.items(): log(f"  {bd} vs_base={d['vs_base_score']:+.3f} vs_short={d['vs_short_total']:+.3f}")
    log("\nwrote factor_research/data/sue_results.json")

if __name__ == "__main__":
    main()
