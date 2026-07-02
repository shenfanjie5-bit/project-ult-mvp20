#!/usr/bin/env python3
"""Phase-3b empirical IC harness (ISOLATED, read-only on project + data).

Tests Wave-1 price/volume factors (STREV raw + turnover-adj, RVOL20≈IVOL proxy)
against forward returns on the A-share universe, reusing pit_backtest.metrics for
the exact IC methodology. Returns are compounded daily pct_chg (tushare pre_close
is ex-rights adjusted → correct price return; no adj_factor needed).

Reads: DockCase daily/daily_basic CSVs (read-only) + runtime/backtest/backtest.sqlite
(read-only, for orthogonality vs cached base_score). Writes: factor_research/ only.
"""
from __future__ import annotations
import os, glob, json, sqlite3, math, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.getcwd())
from pit_backtest.metrics import rank_ic, quantile_groups, fisher_ci, aggregate_ic_across_windows

DC = "/Volumes/dockcase2tb/database_all/股票数据/行情数据"
DAILY = os.path.join(DC, "历史日线", "by_symbol")
DBASIC = os.path.join(DC, "每日指标", "by_symbol")
BT = "runtime/backtest/backtest.sqlite"
OUT = "factor_research"
START = "20230101"           # multi-year, multi-regime window (DockCase has data back to 2001)
SYS_BASE = ["20260116", "20260309", "20260421"]  # system backtest base dates (orthogonality)
HORIZONS = [10, 15, 20]      # trading-day forward horizons (~2-4 weeks)
LOOKBACK = 21                # 1-month reversal window
VOLWIN = 20                  # realized-vol / turnover window

def log(*a): print(*a, flush=True)

def universe():
    c = sqlite3.connect(f"file:{BT}?mode=ro", uri=True)
    u = [r[0] for r in c.execute("SELECT DISTINCT ts_code FROM scores WHERE base_date='20260116'")]
    c.close(); return u

def file_index(folder):
    idx = {}
    for p in glob.glob(os.path.join(folder, "*.csv")):
        base = os.path.basename(p)
        code = base.split("+")[0]
        idx[code] = (p, base)
    return idx

def load_series(univ):
    di, bi = file_index(DAILY), file_index(DBASIC)
    rets, tos, mvs = {}, {}, {}
    skipped_st = 0; used = []
    for ts in univ:
        if ts not in di: continue
        path, fname = di[ts]
        if any(tag in fname.upper() for tag in ("ST", "PT", "退")):  # exclude ST/退市
            skipped_st += 1; continue
        try:
            d = pd.read_csv(path, usecols=["trade_date", "pct_chg"], dtype={"trade_date": str})
        except Exception: continue
        d = d[d["trade_date"] >= START]
        if len(d) < LOOKBACK + 5: continue
        rets[ts] = d.set_index("trade_date")["pct_chg"].astype(float) / 100.0
        if ts in bi:
            try:
                b = pd.read_csv(bi[ts][0], usecols=["trade_date", "turnover_rate", "total_mv"], dtype={"trade_date": str})
                b = b[b["trade_date"] >= START].set_index("trade_date")
                tos[ts] = b["turnover_rate"].astype(float)
                mvs[ts] = b["total_mv"].astype(float)
            except Exception: pass
        used.append(ts)
    log(f"loaded {len(used)} stocks (skipped ST/退={skipped_st})")
    R = pd.DataFrame(rets).sort_index()
    TO = pd.DataFrame(tos).reindex(index=R.index, columns=R.columns)
    MV = pd.DataFrame(mvs).reindex(index=R.index, columns=R.columns)
    return R, TO, MV

def main():
    univ = universe(); log("universe:", len(univ))
    R, TO, MV = load_series(univ)
    cal = list(R.index); n = len(cal)
    log("calendar:", n, cal[0], "->", cal[-1])
    # cumulative log return on calendar; suspended (NaN) -> 0 daily return
    LR = np.log1p(R.fillna(0.0).values)         # n x m
    CUM = np.vstack([np.zeros((1, LR.shape[1])), np.cumsum(LR, axis=0)])[:-1]  # CUM[k] = sum up to k-1; use diffs
    CUMc = np.cumsum(LR, axis=0)                 # CUMc[k] inclusive of day k
    HAS = R.notna().values                        # listed/traded mask
    first_valid = np.where(HAS.any(axis=0), HAS.argmax(axis=0), n + 1)
    cols = list(R.columns)
    TOv = TO.values; MVv = MV.values

    def fwd_ret(k, h):
        if k + h >= n: return None
        fr = np.exp(CUMc[k + h] - CUMc[k]) - 1.0
        valid = HAS[k] & (np.arange(len(cols)) >= 0) & (first_valid <= k)
        # require the stock traded at least once in (k, k+h]
        traded_fwd = HAS[k + 1:k + h + 1].any(axis=0)
        fr = np.where(valid & traded_fwd, fr, np.nan)
        return fr

    def factors(k):
        if k - LOOKBACK < 0: return None
        past = np.exp(CUMc[k] - CUMc[k - LOOKBACK]) - 1.0           # 1M return
        strev_raw = -past
        avg_to = np.nanmean(TOv[k - VOLWIN + 1:k + 1], axis=0)
        strev_adj = strev_raw / np.maximum(avg_to, 0.5)
        rvol = np.nanstd(R.values[k - VOLWIN + 1:k + 1], axis=0, ddof=1) * math.sqrt(252)
        size = np.log(MVv[k])
        listed = (first_valid <= k - LOOKBACK) & HAS[k]
        out = {}
        for name, v in [("STREV_raw", strev_raw), ("STREV_adj", strev_adj), ("RVOL20", rvol)]:
            vv = np.where(listed, v, np.nan)
            out[name] = vv
        out["_size"] = np.where(listed, size, np.nan)
        return out

    def size_neutralize(f, size):
        m = np.isfinite(f) & np.isfinite(size)
        if m.sum() < 30: return np.full_like(f, np.nan)
        x = size[m]; y = f[m]
        b1 = np.cov(x, y, ddof=0)[0, 1] / np.var(x); b0 = y.mean() - b1 * x.mean()
        res = np.full_like(f, np.nan); res[m] = y - (b0 + b1 * x)
        return res

    # base-date grid: every 10 td, need LOOKBACK lookback and max horizon forward
    base_idx = [k for k in range(LOOKBACK + 1, n - max(HORIZONS)) if k % 10 == 0]
    log("base dates:", len(base_idx), [cal[k] for k in base_idx[:3]], "...", [cal[k] for k in base_idx[-2:]])

    FNAMES = ["STREV_raw", "STREV_adj", "RVOL20"]
    ic = {f: {h: [] for h in HORIZONS} for f in FNAMES}
    ic_sn = {f: {h: [] for h in HORIZONS} for f in FNAMES}
    pooled = {f: {h: {"x": [], "y": []} for h in HORIZONS} for f in FNAMES}
    for k in base_idx:
        ff = factors(k)
        if ff is None: continue
        size = ff["_size"]
        for h in HORIZONS:
            fr = fwd_ret(k, h)
            if fr is None: continue
            yr = cal[k][:4]
            for f in FNAMES:
                r = rank_ic(ff[f], fr)
                if np.isfinite(r["ic"]): ic[f][h].append((yr, r["ic"])); pooled[f][h]["x"].extend(ff[f].tolist()); pooled[f][h]["y"].extend(fr.tolist())
                rsn = rank_ic(size_neutralize(ff[f], size), fr)
                if np.isfinite(rsn["ic"]): ic_sn[f][h].append((yr, rsn["ic"]))

    # aggregate
    res = {"meta": {"universe": len(cols), "calendar": [cal[0], cal[-1]], "n_base_dates": len(base_idx),
                    "horizons": HORIZONS, "lookback": LOOKBACK, "note": "overlapping windows (10td spacing) → ICs autocorrelated; mean±std is a sanity/ordering read, not alpha proof"},
           "factors": {}}
    for f in FNAMES:
        res["factors"][f] = {}
        for h in HORIZONS:
            ics = [v for _, v in ic[f][h]]
            agg = aggregate_ic_across_windows(ics)
            aggsn = aggregate_ic_across_windows([v for _, v in ic_sn[f][h]])
            years = sorted(set(y for y, _ in ic[f][h]))
            per_year = {y: round(float(np.mean([v for yy, v in ic[f][h] if yy == y])), 4) for y in years}
            pos_frac = round(float(np.mean([1.0 if v > 0 else 0.0 for v in ics])), 2) if ics else None
            px, py = np.array(pooled[f][h]["x"]), np.array(pooled[f][h]["y"])
            q = quantile_groups(px, py, k=10) if len(px) > 100 else {"top_minus_bottom": None, "monotone": None}
            res["factors"][f][f"h{h}"] = {
                "mean_ic": round(agg["mean_ic"], 4), "std_ic": round(agg["std_ic"], 4) if np.isfinite(agg["std_ic"]) else None,
                "n_windows": agg["n_windows"], "pct_windows_positive": pos_frac,
                "mean_ic_size_neut": round(aggsn["mean_ic"], 4) if np.isfinite(aggsn["mean_ic"]) else None,
                "decile_top_minus_bottom": round(q["top_minus_bottom"], 4) if q.get("top_minus_bottom") is not None else None,
                "decile_monotone": q.get("monotone"),
                "per_year_ic": per_year,
                "pooled_n": int(len(px)),
            }

    # orthogonality vs cached base_score / short_total at system base dates
    c = sqlite3.connect(f"file:{BT}?mode=ro", uri=True)
    ortho = {}
    for bd in SYS_BASE:
        if bd not in cal:
            # nearest
            cand = [d for d in cal if d <= bd]
            if not cand: continue
            kbd = cal.index(cand[-1])
        else:
            kbd = cal.index(bd)
        ff = factors(kbd)
        if ff is None: continue
        rows = {r[0]: (r[1], r[2]) for r in c.execute("SELECT ts_code, base_score, short_total FROM scores WHERE base_date=?", (bd,))}
        bs = np.array([rows.get(ts, (np.nan, np.nan))[0] for ts in cols], float)
        st = np.array([rows.get(ts, (np.nan, np.nan))[1] for ts in cols], float)
        ortho[bd] = {}
        for f in FNAMES:
            ortho[bd][f] = {"vs_base_score": round(rank_ic(ff[f], bs)["ic"], 3), "vs_short_total": round(rank_ic(ff[f], st)["ic"], 3)}
    c.close()
    res["orthogonality_vs_cached_score"] = ortho

    os.makedirs(f"{OUT}/03_impact_studies/3b_empirical", exist_ok=True)
    json.dump(res, open(f"{OUT}/data/ic_results.json", "w"), ensure_ascii=False, indent=1)
    log("\n==== IC SUMMARY (mean rank-IC across windows) ====")
    for f in FNAMES:
        for h in HORIZONS:
            d = res["factors"][f][f"h{h}"]
            log(f"  {f:10} +{h:2}d  IC={d['mean_ic']:+.4f} (±{d['std_ic']} n={d['n_windows']} pos%={d['pct_windows_positive']})  size-neut={d['mean_ic_size_neut']}  decileTMB={d['decile_top_minus_bottom']}")
    log("\n==== PER-YEAR IC (+20d, tests regime-dependence) ====")
    for f in FNAMES:
        log(f"  {f:10} " + "  ".join(f"{y}:{v:+.3f}" for y, v in res["factors"][f]["h20"]["per_year_ic"].items()))
    log("\n==== ORTHOGONALITY (rank-corr factor vs cached score) ====")
    for bd, dd in ortho.items():
        for f in FNAMES:
            log(f"  {bd} {f:10} vs base_score={dd[f]['vs_base_score']:+.3f} vs short_total={dd[f]['vs_short_total']:+.3f}")
    log("\nwrote factor_research/data/ic_results.json")

if __name__ == "__main__":
    main()
