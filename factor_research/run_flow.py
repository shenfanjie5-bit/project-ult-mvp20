#!/usr/bin/env python3
"""Phase-3b: institutional-FLOW factor IC test (ISOLATED, read-only) — the
original thesis. CNIR (moneyflow main net inflow), CYQ chip (winner_rate +
concentration), northbound hk_hold change. margin skipped (only 80 stocks cached)."""
from __future__ import annotations
import os, sys, math, json, glob, csv, bisect
import numpy as np
sys.path.insert(0, os.getcwd())
from pit_backtest.metrics import rank_ic, aggregate_ic_across_windows
from factor_research._datalib import load_price_matrices

def log(*a): print(*a, flush=True)
MF = "/Volumes/dockcase2tb/database_all/股票数据/资金流向数据/个股资金流向/by_symbol"
CYQ = "/Volumes/dockcase2tb/database_all/股票数据/特色数据/每日筹码及胜率/by_symbol"
HK = "/Volumes/dockcase2tb/database_all/股票数据/特色数据/沪深股通持股明细/all.csv"
HORIZONS = [10, 20]

def fidx(folder):
    return {os.path.basename(p).split("+")[0]: p for p in glob.glob(os.path.join(folder, "*.csv"))}

def align(series_by_ts, cal, cols):
    """dict ts->(dates_list, vals_list) → matrix n x m aligned to cal (NaN missing)."""
    n, m = len(cal), len(cols); M = np.full((n, m), np.nan)
    calpos = {d: i for i, d in enumerate(cal)}
    for j, ts in enumerate(cols):
        sv = series_by_ts.get(ts)
        if not sv: continue
        for d, v in zip(*sv):
            i = calpos.get(d)
            if i is not None and v is not None: M[i, j] = v
    return M

def main():
    RET, TO, MV, cal, cols = load_price_matrices("20230101")
    n, m = RET.shape
    LR = np.log1p(np.nan_to_num(RET, nan=0.0)); CUM = np.cumsum(LR, axis=0)
    HAS = ~np.isnan(RET); first_valid = np.where(HAS.any(0), HAS.argmax(0), n + 1)
    mkt = np.nanmean(RET, axis=1); mkt_lr = np.log1p(np.nan_to_num(mkt, 0.0)); mkt_cum = np.cumsum(mkt_lr)
    colset = set(cols); cal0 = cal[0]

    def fwd(k, h):
        if k + h >= n: return None
        fr = np.exp(CUM[k + h] - CUM[k]) - 1.0
        ok = HAS[k] & (first_valid <= k) & HAS[k + 1:k + h + 1].any(0)
        return np.where(ok, fr, np.nan)

    # ---- load moneyflow main_net + total ----
    di = fidx(MF); mn_by, tot_by = {}, {}
    for ts in colset:
        if ts not in di: continue
        try:
            x = list(csv.DictReader(open(di[ts], encoding="utf-8")))
        except Exception: continue
        ds, mns, tots = [], [], []
        for r in x:
            if r["trade_date"] < cal0: continue
            try:
                bl, be = float(r["buy_lg_amount"]), float(r["buy_elg_amount"])
                sl, se = float(r["sell_lg_amount"]), float(r["sell_elg_amount"])
                tot = sum(float(r[c]) for c in ("buy_sm_amount","sell_sm_amount","buy_md_amount","sell_md_amount","buy_lg_amount","sell_lg_amount","buy_elg_amount","sell_elg_amount"))
            except Exception: continue
            ds.append(r["trade_date"]); mns.append((bl+be)-(sl+se)); tots.append(tot)
        if ds: mn_by[ts] = (ds, mns); tot_by[ts] = (ds, tots)
    MAIN = align(mn_by, cal, cols); TOT = align(tot_by, cal, cols)
    MAIN0 = np.nan_to_num(MAIN, nan=0.0); TOT0 = np.nan_to_num(TOT, nan=0.0)
    cMAIN = np.cumsum(MAIN0, axis=0); cTOT = np.cumsum(TOT0, axis=0)
    log(f"moneyflow loaded: {len(mn_by)} stocks")

    # ---- load CYQ winner_rate + concentration ----
    di = fidx(CYQ); wr_by, cc_by = {}, {}
    for ts in colset:
        if ts not in di: continue
        try: x = list(csv.DictReader(open(di[ts], encoding="utf-8")))
        except Exception: continue
        dsw, wr, dsc, cc = [], [], [], []
        for r in x:
            if r["trade_date"] < cal0: continue
            try:
                w = float(r["winner_rate"]); dsw.append(r["trade_date"]); wr.append(w)
                c5, c50, c85, c15 = float(r["cost_5pct"]), float(r["cost_50pct"]), float(r["cost_85pct"]), float(r["cost_15pct"])
                if c50 > 0: dsc.append(r["trade_date"]); cc.append(-(c85 - c15) / c50)  # high = concentrated
            except Exception: continue
        if dsw: wr_by[ts] = (dsw, wr)
        if dsc: cc_by[ts] = (dsc, cc)
    WINNER = align(wr_by, cal, cols); CHIPC = align(cc_by, cal, cols)
    log(f"cyq loaded: winner {len(wr_by)}, conc {len(cc_by)}")

    # ---- load hk_hold (northbound) ratio, build change between snapshots ----
    hk = {}
    for r in csv.DictReader(open(HK, encoding="utf-8")):
        ts = r.get("ts_code") or ""
        if ts in colset and r["trade_date"] >= cal0:
            try: hk.setdefault(ts, []).append((r["trade_date"], float(r["ratio"])))
            except Exception: pass
    hk_dates = sorted({d for v in hk.values() for d, _ in v})
    HKCHG = np.full((n, m), np.nan); calpos = {d: i for i, d in enumerate(cal)}
    # map each snapshot date to nearest cal idx <= date
    for j, ts in enumerate(cols):
        v = sorted(hk.get(ts, []))
        for a in range(1, len(v)):
            d, rat = v[a]; rprev = v[a-1][1]
            cand = [c for c in cal if c <= d]
            if not cand: continue
            HKCHG[calpos[cand[-1]], j] = rat - rprev
    log(f"hk_hold loaded: {len(hk)} stocks, {len(hk_dates)} snapshot dates")

    def cnir(k, N):
        if k - N < 0: return np.full(m, np.nan)
        num = cMAIN[k] - cMAIN[k - N]; den = cTOT[k] - cTOT[k - N]
        v = np.where(den > 0, num / den, np.nan)
        listed = HAS[k] & (first_valid <= k)
        return np.where(listed, v, np.nan)

    FACTORS = {
        "CNIR_10": lambda k: cnir(k, 10),
        "WINNER_RATE": lambda k: np.where(HAS[k], WINNER[k], np.nan),
        "CHIP_CONC": lambda k: np.where(HAS[k], CHIPC[k], np.nan),
        "HKHOLD_CHG": lambda k: HKCHG[k],
    }
    base_idx = [k for k in range(25, n - max(HORIZONS)) if k % 10 == 0]
    res = {"meta": {"universe": m, "n_base": len(base_idx), "horizons": HORIZONS,
                    "data_notes": {"moneyflow_cov": len(mn_by), "cyq_cov": len(wr_by), "hk_snapshots": len(hk_dates),
                                   "margin": "SKIPPED — only 80 stocks cached in DockCase"}}, "factors": {}}
    vols = []
    for k in base_idx:
        vols.append((k, float(np.std(mkt[k-19:k+1], ddof=1)*math.sqrt(252)), math.exp(mkt_cum[k]-mkt_cum[k-60])-1.0))
    vmed = float(np.median([v for _, v, _ in vols]))

    for fname, fn in FACTORS.items():
        res["factors"][fname] = {}
        for h in HORIZONS:
            recs = []  # (year, ic, regime_vol_hi, regime_trend_up, n_valid)
            for k in base_idx:
                f = fn(k); fr = fwd(k, h)
                if fr is None: continue
                nv = int(np.sum(np.isfinite(f) & np.isfinite(fr)))
                if nv < 30: continue
                r = rank_ic(f, fr)
                if np.isfinite(r["ic"]):
                    vol = float(np.std(mkt[k-19:k+1], ddof=1)*math.sqrt(252)); tr = math.exp(mkt_cum[k]-mkt_cum[k-60])-1.0
                    recs.append((cal[k][:4], r["ic"], vol > vmed, tr > 0, nv))
            ics = [r[1] for r in recs]; agg = aggregate_ic_across_windows(ics)
            years = sorted(set(r[0] for r in recs))
            per_year = {y: round(float(np.mean([r[1] for r in recs if r[0]==y])), 4) for y in years}
            def bmean(vh, tu):
                s=[r[1] for r in recs if r[2]==vh and r[3]==tu]; return round(float(np.mean(s)),4) if s else None
            res["factors"][fname][f"h{h}"] = {
                "mean_ic": round(agg["mean_ic"],4), "std_ic": round(agg["std_ic"],4) if np.isfinite(agg["std_ic"]) else None,
                "n_windows": agg["n_windows"], "pct_pos": round(float(np.mean([1.0 if v>0 else 0.0 for v in ics])),2) if ics else None,
                "avg_valid_n": int(np.mean([r[4] for r in recs])) if recs else 0,
                "per_year_ic": per_year,
                "regime": {"trendDN_volHI": bmean(True, False), "trendUP_volLO": bmean(False, True)},
            }
    # orthogonality vs cached score (at system base dates)
    import sqlite3
    c = sqlite3.connect("file:runtime/backtest/backtest.sqlite?mode=ro", uri=True); ortho={}
    for bd in ["20260116","20260309","20260421"]:
        cand=[d for d in cal if d<=bd]
        if not cand: continue
        k=cal.index(cand[-1]); rows={r[0]:(r[1],r[2]) for r in c.execute("SELECT ts_code,base_score,short_total FROM scores WHERE base_date=?",(bd,))}
        bs=np.array([rows.get(ts,(np.nan,np.nan))[0] for ts in cols]); st=np.array([rows.get(ts,(np.nan,np.nan))[1] for ts in cols])
        ortho[bd]={fn:{"vs_base":round(rank_ic(FACTORS[fn](k),bs)["ic"],3),"vs_short":round(rank_ic(FACTORS[fn](k),st)["ic"],3)} for fn in FACTORS}
    c.close(); res["orthogonality"]=ortho
    json.dump(res, open("factor_research/data/flow_results.json","w"), ensure_ascii=False, indent=1)

    log("\n==== FLOW factor IC ====")
    for fn in FACTORS:
        for h in HORIZONS:
            d=res["factors"][fn][f"h{h}"]
            log(f"  {fn:12} +{h:2}d IC={d['mean_ic']:+.4f} (±{d['std_ic']} n={d['n_windows']} pos%={d['pct_pos']} validN~{d['avg_valid_n']}) regime[DN/HI={d['regime']['trendDN_volHI']} UP/LO={d['regime']['trendUP_volLO']}]")
    log("\n==== FLOW per-year IC (+20d) ====")
    for fn in FACTORS:
        log(f"  {fn:12} " + "  ".join(f"{y}:{v:+.3f}" for y,v in res["factors"][fn]["h20"]["per_year_ic"].items()))
    log("\n==== FLOW orthogonality vs cached short_total ====")
    for bd,d in ortho.items():
        log(f"  {bd} " + "  ".join(f"{fn}:{d[fn]['vs_short']:+.2f}" for fn in FACTORS))
    log("\nwrote factor_research/data/flow_results.json")

if __name__ == "__main__":
    main()
