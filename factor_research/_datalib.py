#!/usr/bin/env python3
"""Shared data loaders for Phase-3b (ISOLATED, read-only on project + DockCase).
Caches price matrices to factor_research/data/ so repeated analyses are fast."""
from __future__ import annotations
import os, glob, json, sqlite3
import numpy as np, pandas as pd

DC = "/Volumes/dockcase2tb/database_all/股票数据"
DAILY = os.path.join(DC, "行情数据", "历史日线", "by_symbol")
DBASIC = os.path.join(DC, "行情数据", "每日指标", "by_symbol")
INCOME = os.path.join(DC, "财务数据", "利润表", "by_symbol")
BT = "runtime/backtest/backtest.sqlite"
DATADIR = "factor_research/data"

def universe():
    c = sqlite3.connect(f"file:{BT}?mode=ro", uri=True)
    u = [r[0] for r in c.execute("SELECT DISTINCT ts_code FROM scores WHERE base_date='20260116'")]
    c.close(); return u

def _file_index(folder):
    idx = {}
    for p in glob.glob(os.path.join(folder, "*.csv")):
        idx[os.path.basename(p).split("+")[0]] = (p, os.path.basename(p))
    return idx

def load_price_matrices(start="20230101"):
    """Returns (RET, TO, MV, cal, cols) — numpy n_days x n_stocks (NaN where missing).
    RET=simple daily return (pct_chg/100). Cached to npz+json keyed on start."""
    npz = os.path.join(DATADIR, f"px_{start}.npz"); js = os.path.join(DATADIR, f"px_{start}.json")
    if os.path.exists(npz) and os.path.exists(js):
        d = np.load(npz); meta = json.load(open(js))
        return d["RET"], d["TO"], d["MV"], meta["cal"], meta["cols"]
    di, bi = _file_index(DAILY), _file_index(DBASIC)
    rets, tos, mvs = {}, {}, {}
    for ts in universe():
        if ts not in di: continue
        path, fname = di[ts]
        if any(t in fname.upper() for t in ("ST", "PT", "退")): continue
        try:
            x = pd.read_csv(path, usecols=["trade_date", "pct_chg"], dtype={"trade_date": str})
        except Exception: continue
        x = x[x["trade_date"] >= start]
        if len(x) < 30: continue
        rets[ts] = x.set_index("trade_date")["pct_chg"].astype(float) / 100.0
        if ts in bi:
            try:
                b = pd.read_csv(bi[ts][0], usecols=["trade_date", "turnover_rate", "total_mv"], dtype={"trade_date": str})
                b = b[b["trade_date"] >= start].set_index("trade_date")
                tos[ts] = b["turnover_rate"].astype(float); mvs[ts] = b["total_mv"].astype(float)
            except Exception: pass
    R = pd.DataFrame(rets).sort_index()
    TO = pd.DataFrame(tos).reindex(index=R.index, columns=R.columns)
    MV = pd.DataFrame(mvs).reindex(index=R.index, columns=R.columns)
    cal, cols = list(R.index), list(R.columns)
    os.makedirs(DATADIR, exist_ok=True)
    np.savez(npz, RET=R.values, TO=TO.values, MV=MV.values)
    json.dump({"cal": cal, "cols": cols}, open(js, "w"))
    return R.values, TO.values, MV.values, cal, cols

def load_quarterly_earnings(cols, start="20180101"):
    """Per-stock single-quarter 归母净利润 with first-announce date (PIT).
    Returns {ts_code: [(ann_date, end_date, q_profit)]} ascending by end_date.
    Single quarter derived by differencing YTD n_income_attr_p within a fiscal year."""
    di = _file_index(INCOME); out = {}
    colset = set(cols)
    for ts in colset:
        if ts not in di: continue
        try:
            x = pd.read_csv(di[ts][0], usecols=["ann_date", "f_ann_date", "end_date", "report_type", "n_income_attr_p"],
                            dtype={"ann_date": str, "f_ann_date": str, "end_date": str, "report_type": str})
        except Exception: continue
        x = x[(x["report_type"] == "1") & (x["end_date"] >= start)]
        if len(x) == 0: continue
        x["ann"] = x["f_ann_date"].fillna(x["ann_date"])
        x = x.dropna(subset=["ann", "n_income_attr_p"])
        # PIT: earliest announcement per end_date (original report, not restatement)
        x = x.sort_values("ann").groupby("end_date", as_index=False).first()
        x = x.sort_values("end_date")
        ytd = {r["end_date"]: float(r["n_income_attr_p"]) for _, r in x.iterrows()}
        annmap = {r["end_date"]: str(r["ann"]) for _, r in x.iterrows()}
        recs = []
        for ed in sorted(ytd):
            y, mm = ed[:4], ed[4:8]
            if mm == "0331": q = ytd[ed]
            else:
                prev = {"0630": "0331", "0930": "0630", "1231": "0930"}.get(mm)
                ped = y + prev + ed[8:] if prev else None
                if ped is None or ped not in ytd: continue
                q = ytd[ed] - ytd[ped]
            recs.append((annmap[ed], ed, q))
        if recs: out[ts] = recs
    return out
