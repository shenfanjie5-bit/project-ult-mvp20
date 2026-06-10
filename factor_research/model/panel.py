#!/usr/bin/env python3
"""Build a PIT-safe cross-sectional feature panel for forward-return modeling.

ISOLATED / READ-ONLY. Reads:
  - cached price matrices (factor_research/data/px_20230101.npz, via _datalib)
  - DockCase by-symbol CSVs directly (daily_basic / fina_indicator / income)
  - the production industry map (pit_backtest.universe.primary_industry_map)
Writes ONLY factor_research/model/panel.npz (+ panel_meta.json).

Design (honors the 6 onboarding disciplines):
  * RAW features only here; industry+size neutralization and cross-sectional
    ranking happen in harness.py so they are auditable and model-varied.
  * Strict PIT: financial features use ann_date <= base_date (no look-ahead);
    price/market features use only data up to and including the base day k.
  * Forward returns (+5/+10/+20d) are the LABEL, taken strictly after k.

Output arrays are aligned: panel[d] is the cross-section at base_dates[d].
"""
from __future__ import annotations

import bisect
import glob
import json
import os
import sys
import time

import numpy as np
import pandas as pd

os.environ.setdefault("DOCKCASE_WRITEBACK", "0")
os.environ.setdefault("DOCKCASE_CACHE", "1")
sys.path.insert(0, os.getcwd())

from factor_research._datalib import load_price_matrices, load_quarterly_earnings  # noqa: E402
from pit_backtest import universe  # noqa: E402

DC = "/Volumes/dockcase2tb/database_all/股票数据"
DBASIC = os.path.join(DC, "行情数据", "每日指标", "by_symbol")
FINA = os.path.join(DC, "财务数据", "财务指标数据", "by_symbol")
OUT = "factor_research/model"

# base-date sampling: every STEP trading days; need MOM_LONG history before and
# HMAX forward days after.
STEP = 10
MOM_LONG = 252      # 12-1 momentum lookback
HMAX = 20           # longest forward horizon
WARMUP = 130        # min history so short features (60-126d) are valid


def _file_index(folder: str) -> dict:
    idx = {}
    for p in glob.glob(os.path.join(folder, "*.csv")):
        idx[os.path.basename(p).split("+")[0]] = p
    return idx


def log(*a):
    print(*a, flush=True)


# ----------------------------------------------------------------------------
# price / volume derived features (vectorized; PIT = uses only days <= k)
# ----------------------------------------------------------------------------
def price_features(RET, TO, MV, cal, base_idx):
    n, m = RET.shape
    R = np.where(np.isfinite(RET), RET, np.nan)
    LR = np.log1p(np.nan_to_num(R, nan=0.0))
    CUM = np.cumsum(LR, axis=0)              # CUM[k] = sum_{0..k} log(1+r)
    HAS = np.isfinite(RET)
    first_valid = np.where(HAS.any(0), HAS.argmax(0), n + 1)

    def cumret(a, b):
        """simple return from day a to day b (exclusive of a, inclusive b)."""
        return np.exp(CUM[b] - CUM[a]) - 1.0

    # market daily return (MV-weighted across the universe) for beta/ivol/regime
    w = np.where(np.isfinite(MV) & (MV > 0), MV, np.nan)
    Rf = np.where(HAS, R, np.nan)
    mkt = np.full(n, np.nan)
    for i in range(n):
        wi = w[i]
        ri = Rf[i]
        ok = np.isfinite(wi) & np.isfinite(ri)
        if ok.sum() >= 30:
            mkt[i] = np.average(ri[ok], weights=wi[ok])
    mkt = np.nan_to_num(mkt, nan=0.0)

    D = len(base_idx)
    feats = {nm: np.full((D, m), np.nan, np.float64) for nm in [
        "strev", "strev_adj", "mom_6_1", "mom_12_1", "rvol_20", "rvol_60",
        "ivol_60", "beta_60", "max5", "turnover_20", "turnover_trend",
        "amihud", "ln_mv",
    ]}
    lnmv_raw = np.full((D, m), np.nan, np.float64)

    for d, k in enumerate(base_idx):
        valid_k = HAS[k] & (first_valid <= k - 60)   # need >=60d history
        # reversal (last 20d), sign flipped (oversold -> high score)
        r20 = cumret(k - 20, k)
        feats["strev"][d] = np.where(valid_k, -r20, np.nan)
        to20 = np.nanmean(np.where(HAS[k - 20:k], TO[k - 20:k], np.nan), axis=0)
        feats["turnover_20"][d] = np.where(valid_k, to20, np.nan)
        feats["strev_adj"][d] = np.where(valid_k, -r20 / np.maximum(to20, 0.5), np.nan)
        # momentum (skip last 21d)
        feats["mom_6_1"][d] = np.where(valid_k & (first_valid <= k - 126), cumret(k - 126, k - 21), np.nan)
        feats["mom_12_1"][d] = np.where(valid_k & (first_valid <= k - 252), cumret(k - 252, k - 21), np.nan)
        # realized vol
        win20 = np.where(HAS[k - 20:k], R[k - 20:k], np.nan)
        win60 = np.where(HAS[k - 60:k], R[k - 60:k], np.nan)
        feats["rvol_20"][d] = np.where(valid_k, np.nanstd(win20, axis=0), np.nan)
        feats["rvol_60"][d] = np.where(valid_k, np.nanstd(win60, axis=0), np.nan)
        # lottery: mean of top-5 daily returns last 20d
        srt = np.sort(np.where(np.isfinite(win20), win20, -np.inf), axis=0)
        top5 = srt[-5:]
        feats["max5"][d] = np.where(valid_k, np.where(np.isfinite(top5), top5, np.nan).mean(axis=0), np.nan)
        # turnover trend (attention spike)
        to60 = np.nanmean(np.where(HAS[k - 60:k], TO[k - 60:k], np.nan), axis=0)
        feats["turnover_trend"][d] = np.where(valid_k, to20 / np.where(to60 > 0, to60, np.nan) - 1.0, np.nan)
        # amihud illiquidity proxy: mean |ret| / (turnover% * mv) over 20d
        amt = np.where(HAS[k - 20:k], (TO[k - 20:k] / 100.0) * MV[k - 20:k], np.nan)
        illiq = np.nanmean(np.abs(win20) / np.where(amt > 0, amt, np.nan), axis=0)
        feats["amihud"][d] = np.where(valid_k, illiq, np.nan)
        # beta / ivol vs market over 60d
        mk = mkt[k - 60:k]
        mk_c = mk - mk.mean()
        var_m = float((mk_c * mk_c).sum())
        for j in range(m):
            if not valid_k[j]:
                continue
            y = win60[:, j]
            ok = np.isfinite(y)
            if ok.sum() < 40 or var_m <= 0:
                continue
            yc = y[ok] - y[ok].mean()
            xc = mk_c[ok]
            denom = float((xc * xc).sum())
            if denom <= 0:
                continue
            beta = float((xc * yc).sum() / denom)
            resid = yc - beta * xc
            feats["beta_60"][d, j] = beta
            feats["ivol_60"][d, j] = float(np.std(resid, ddof=1)) if resid.size > 2 else np.nan
        # size
        mvk = np.where(np.isfinite(MV[k]) & (MV[k] > 0), MV[k], np.nan)
        feats["ln_mv"][d] = np.where(valid_k, np.log(mvk), np.nan)
        lnmv_raw[d] = np.log(mvk)

    return feats, lnmv_raw, CUM, HAS, first_valid, mkt


def forward_returns(CUM, HAS, first_valid, base_idx, horizons=(5, 10, 20)):
    n = CUM.shape[0]
    out = {}
    for h in horizons:
        D = len(base_idx)
        m = CUM.shape[1]
        F = np.full((D, m), np.nan, np.float64)
        for d, k in enumerate(base_idx):
            if k + h >= n:
                continue
            fr = np.exp(CUM[k + h] - CUM[k]) - 1.0
            ok = HAS[k] & (first_valid <= k) & HAS[k + 1:k + h + 1].any(0)
            F[d] = np.where(ok, fr, np.nan)
        out[h] = F
    return out


# ----------------------------------------------------------------------------
# value features (daily_basic by-symbol, as-of base date; market PIT)
# ----------------------------------------------------------------------------
def value_features(cols, cal, base_idx):
    di = _file_index(DBASIC)
    base_dates = [cal[k] for k in base_idx]
    D, m = len(base_idx), len(cols)
    out = {nm: np.full((D, m), np.nan, np.float64) for nm in ["ep_ttm", "bp", "sp_ttm", "dy"]}
    use = ["trade_date", "pe_ttm", "pb", "ps_ttm", "dv_ttm"]
    for j, ts in enumerate(cols):
        if ts not in di:
            continue
        try:
            x = pd.read_csv(di[ts], usecols=use, dtype={"trade_date": str})
        except Exception:
            continue
        x = x.dropna(subset=["trade_date"]).sort_values("trade_date")
        td = x["trade_date"].values
        for d, bd in enumerate(base_dates):
            p = bisect.bisect_right(td, bd) - 1   # last row with trade_date <= base date
            if p < 0:
                continue
            row = x.iloc[p]
            pe, pb, ps, dv = row["pe_ttm"], row["pb"], row["ps_ttm"], row["dv_ttm"]
            if pd.notna(pe) and pe != 0:
                out["ep_ttm"][d, j] = 1.0 / float(pe)
            if pd.notna(pb) and pb != 0:
                out["bp"][d, j] = 1.0 / float(pb)
            if pd.notna(ps) and ps != 0:
                out["sp_ttm"][d, j] = 1.0 / float(ps)
            if pd.notna(dv):
                out["dy"][d, j] = float(dv)
    return out


# ----------------------------------------------------------------------------
# quality features (fina_indicator by-symbol, PIT by ann_date <= base date)
# ----------------------------------------------------------------------------
def quality_features(cols, cal, base_idx):
    di = _file_index(FINA)
    base_dates = [cal[k] for k in base_idx]
    D, m = len(base_idx), len(cols)
    fields = ["roe", "roa", "grossprofit_margin", "netprofit_margin",
              "debt_to_assets", "assets_turn", "q_roe"]
    rename = {"grossprofit_margin": "gpm", "netprofit_margin": "npm",
              "debt_to_assets": "debt_assets", "assets_turn": "asset_turn"}
    out = {rename.get(f, f): np.full((D, m), np.nan, np.float64) for f in fields}
    use = ["ann_date", "end_date"] + fields
    for j, ts in enumerate(cols):
        if ts not in di:
            continue
        try:
            x = pd.read_csv(di[ts], usecols=lambda c: c in use, dtype={"ann_date": str, "end_date": str})
        except Exception:
            continue
        if "ann_date" not in x.columns:
            continue
        x = x.dropna(subset=["ann_date"]).copy()
        # PIT: earliest announcement per end_date, then sorted by ann_date
        x = x.sort_values("ann_date").drop_duplicates(subset=["end_date"], keep="first")
        x = x.sort_values("ann_date")
        ann = x["ann_date"].values
        for d, bd in enumerate(base_dates):
            p = bisect.bisect_right(ann, bd) - 1
            if p < 0:
                continue
            row = x.iloc[p]
            for f in fields:
                if f in x.columns and pd.notna(row[f]):
                    out[rename.get(f, f)][d, j] = float(row[f])
    return out


# ----------------------------------------------------------------------------
# earnings: SUE (seasonal-RW, PIT) + single-quarter YoY profit growth
# ----------------------------------------------------------------------------
def earnings_features(cols, cal, base_idx, earn):
    D, m = len(base_idx), len(cols)
    base_dates = [cal[k] for k in base_idx]
    sue = np.full((D, m), np.nan, np.float64)
    dsa = np.full((D, m), np.nan, np.float64)   # days since announce (trading-day count)
    npq_yoy = np.full((D, m), np.nan, np.float64)
    MIN_HIST = 6

    def prev_year(ed):
        return str(int(ed[:4]) - 1) + ed[4:]

    cal_arr = cal  # list of date strings

    for j, ts in enumerate(cols):
        if ts not in earn:
            continue
        recs = earn[ts]  # [(ann_date, end_date, q_profit)] asc by end_date
        q = {ed: v for _, ed, v in recs}
        ann_of = {ed: a for a, ed, _ in recs}
        eds = sorted(q)
        # SUE series (seasonal random walk), accumulate history for stdev
        surp = []
        for ed in eds:
            py = prev_year(ed)
            if py in q:
                surp.append((ed, ann_of[ed], q[ed] - q[py], q[ed], q[py]))
        sue_series = []   # (ann_date, sue, end_date)
        yoy_series = []   # (ann_date, yoy_growth)
        svals = []
        for ed, a, s, cur, prv in surp:
            if not a:
                continue
            if len(svals) >= MIN_HIST:
                sd = float(np.std(svals, ddof=1))
                if sd > 1e-6:
                    sue_series.append((a, max(-5.0, min(5.0, s / sd))))
            svals.append(s)
            # YoY growth (guard tiny/neg base)
            if abs(prv) > 1e-6:
                g = (cur - prv) / abs(prv)
                yoy_series.append((a, max(-3.0, min(3.0, g))))
        for series, mat in ((sue_series, sue), (yoy_series, npq_yoy)):
            if not series:
                continue
            series = [(a, v) for a, v in series if a and a <= cal_arr[-1]]
            series.sort()
            anns = [a for a, _ in series]
            for d, bd in enumerate(base_dates):
                p = bisect.bisect_right(anns, bd) - 1
                if p >= 0:
                    mat[d, j] = series[p][1]
        # days since most recent SUE announce
        if sue_series:
            anns = sorted(a for a, _ in sue_series)
            for d, k in enumerate(base_idx):
                bd = base_dates[d]
                p = bisect.bisect_right(anns, bd) - 1
                if p >= 0:
                    ai = bisect.bisect_left(cal_arr, anns[p])
                    dsa[d, j] = k - ai
    return {"sue": sue, "npq_yoy": npq_yoy, "days_since_ann": dsa}


# ----------------------------------------------------------------------------
# regime tags per base date (market trend + vol) from price matrix
# ----------------------------------------------------------------------------
def regime_tags(mkt, CUM_mkt, base_idx, cal, fwd_mkt_h=10):
    # cumulative market log-return
    lm = np.log1p(mkt)
    cum = np.cumsum(lm)
    n = len(mkt)
    out = []
    trends, vols = [], []
    for k in base_idx:
        trend60 = float(np.exp(cum[k] - cum[max(0, k - 60)]) - 1.0)
        vol20 = float(np.std(mkt[max(0, k - 20):k], ddof=1)) if k > 21 else float("nan")
        fwd = float(np.exp(cum[min(n - 1, k + fwd_mkt_h)] - cum[k]) - 1.0)
        out.append({"date": cal[k], "trend60": trend60, "vol20": vol20, "mkt_fwd10": fwd})
        trends.append(trend60)
        vols.append(vol20)
    vmed = float(np.nanmedian(vols))
    for o in out:
        up = o["trend60"] >= 0
        turb = (o["vol20"] >= vmed) if np.isfinite(o["vol20"]) else False
        o["regime"] = ("up" if up else "down") + "_" + ("turbulent" if turb else "calm")
    return out


def build():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    log("loading price matrices ...")
    RET, TO, MV, cal, cols = load_price_matrices("20230101")
    n, m = RET.shape
    base_idx = [k for k in range(WARMUP, n - HMAX) if k % STEP == 0]
    log(f"universe={m} days={n} base_dates={len(base_idx)} ({cal[base_idx[0]]}..{cal[base_idx[-1]]})")

    log("price/volume features ...")
    pfeat, lnmv_raw, CUM, HAS, first_valid, mkt = price_features(RET, TO, MV, cal, base_idx)
    log(f"  done ({time.time()-t0:.0f}s)")

    log("forward returns +5/+10/+20 ...")
    fwd = forward_returns(CUM, HAS, first_valid, base_idx, (5, 10, 20))

    log("value features (daily_basic) ...")
    vfeat = value_features(cols, cal, base_idx)
    log(f"  done ({time.time()-t0:.0f}s)")

    log("quality features (fina_indicator) ...")
    qfeat = quality_features(cols, cal, base_idx)
    log(f"  done ({time.time()-t0:.0f}s)")

    log("earnings/SUE features (income) ...")
    earn = load_quarterly_earnings(cols, start="20180101")
    efeat = earnings_features(cols, cal, base_idx, earn)
    log(f"  earnings coverage {len(earn)}/{m}; done ({time.time()-t0:.0f}s)")

    # industry codes
    ind_map = universe.primary_industry_map()
    ind_names = sorted(set(ind_map.get(c, "UNKNOWN") for c in cols))
    ind_code = {nm: i for i, nm in enumerate(ind_names)}
    industry = np.array([ind_code.get(ind_map.get(c, "UNKNOWN"), -1) for c in cols], dtype=np.int32)

    regimes = regime_tags(mkt, None, base_idx, cal)

    # assemble feature tensor
    feat_order = (
        # value
        ["ep_ttm", "bp", "sp_ttm", "dy"]
        # quality
        + ["roe", "roa", "gpm", "npm", "debt_assets", "asset_turn", "q_roe"]
        # earnings / expectation
        + ["sue", "npq_yoy"]
        # momentum / reversal
        + ["mom_6_1", "mom_12_1", "strev", "strev_adj"]
        # risk / low-vol / lottery
        + ["rvol_20", "rvol_60", "ivol_60", "beta_60", "max5"]
        # liquidity / crowding / size
        + ["turnover_20", "turnover_trend", "amihud", "ln_mv"]
    )
    allf = {}
    allf.update(vfeat)
    allf.update(qfeat)
    allf.update({"sue": efeat["sue"], "npq_yoy": efeat["npq_yoy"]})
    allf.update(pfeat)
    D = len(base_idx)
    feat = np.stack([allf[nm] for nm in feat_order], axis=2).astype(np.float32)  # D x N x F

    base_dates = [cal[k] for k in base_idx]
    np.savez_compressed(
        os.path.join(OUT, "panel.npz"),
        feat=feat,
        fwd5=fwd[5].astype(np.float32),
        fwd10=fwd[10].astype(np.float32),
        fwd20=fwd[20].astype(np.float32),
        ln_mv=lnmv_raw.astype(np.float32),
        industry=industry,
        days_since_ann=efeat["days_since_ann"].astype(np.float32),
    )
    meta = {
        "feat_names": feat_order,
        "cols": cols,
        "base_dates": base_dates,
        "base_idx": [int(k) for k in base_idx],
        "industry_names": ind_names,
        "regimes": regimes,
        "n_days_total": n,
        "step": STEP,
        "warmup": WARMUP,
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    json.dump(meta, open(os.path.join(OUT, "panel_meta.json"), "w"), ensure_ascii=False, indent=1)

    # coverage report
    log("\n==== feature coverage (non-NaN fraction across all cells) ====")
    for fi, nm in enumerate(feat_order):
        cov = float(np.isfinite(feat[:, :, fi]).mean())
        log(f"  {nm:16} {cov:5.1%}")
    log("\n==== forward-return coverage ====")
    for h in (5, 10, 20):
        log(f"  fwd{h:<2} {float(np.isfinite(fwd[h]).mean()):5.1%}")
    log(f"\nwrote {OUT}/panel.npz  feat shape={feat.shape}  ({time.time()-t0:.0f}s total)")
    return feat.shape


if __name__ == "__main__":
    build()
