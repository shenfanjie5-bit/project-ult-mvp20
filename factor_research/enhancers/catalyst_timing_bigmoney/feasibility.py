#!/usr/bin/env python3
"""Feasibility scan for catalyst_timing_bigmoney family.

PART 1 sources: 业绩预告 (forecast), 业绩快报 (express)
PART 2 sources: 龙虎榜每日统计单/机构交易单, 大宗交易, 机构调研, 券商月度金股, 每日筹码及胜率

Outputs coverage numbers vs the 1617-stock panel universe and the 67 base dates.
Also empirically checks the semantics of express `yoy_net_profit` (percent vs
last-year-absolute-profit) before it is used as a surprise.
"""
import os, json, glob, bisect
import numpy as np
import pandas as pd

os.environ["DOCKCASE_WRITEBACK"] = "0"

ROOT = "/Volumes/dockcase2tb/database_all/股票数据"
HERE = os.path.dirname(os.path.abspath(__file__))
META = json.load(open("/Users/fanjie/Desktop/Cowork/project-ult-mvp20/factor_research/model/panel_meta.json"))
COLS = META["cols"]; BASE = META["base_dates"]
UNIV = set(COLS)

def file_map(d):
    out = {}
    for p in glob.glob(os.path.join(d, "*.csv")):
        ts = os.path.basename(p).split("+")[0]
        out[ts] = p
    return out

res = {}

# ---------------- PART 2 quick kills ----------------
for name, sub in [
    ("lhb_daily_stats", "打板专题数据/龙虎榜每日统计单"),
    ("lhb_inst_trades", "打板专题数据/龙虎榜机构交易单"),
    ("broker_gold_picks", "特色数据/券商月度金股"),
]:
    d = os.path.join(ROOT, sub)
    n = len(glob.glob(os.path.join(d, "*"))) if os.path.isdir(d) else -1
    res[name] = {"path": sub, "n_entries": n, "verdict": "EMPTY dir -> infeasible" if n == 0 else str(n)}

for name, sub in [
    ("block_trades", "参考数据/大宗交易/by_symbol"),
    ("inst_surveys", "特色数据/机构调研数据/by_symbol"),
    ("chips_winrate", "特色数据/每日筹码及胜率/by_symbol"),
]:
    fm = file_map(os.path.join(ROOT, sub))
    inter = len(UNIV & set(fm))
    res[name] = {"path": sub, "n_files": len(fm), "in_universe": inter,
                 "universe_cov_pct": round(100.0 * inter / len(UNIV), 1)}

# chip date range from a few sample files
samp = []
fm_chip = file_map(os.path.join(ROOT, "特色数据/每日筹码及胜率/by_symbol"))
for ts in COLS[::400]:
    p = fm_chip.get(ts)
    if not p: continue
    df = pd.read_csv(p, usecols=["trade_date"], dtype=str)
    samp.append((ts, df["trade_date"].min(), df["trade_date"].max(), len(df)))
res["chips_winrate"]["sample_ranges"] = samp

# ---------------- PART 1 forecast/express ----------------
fm_fc = file_map(os.path.join(ROOT, "财务数据/业绩预告/by_symbol"))
fm_ex = file_map(os.path.join(ROOT, "财务数据/业绩快报/by_symbol"))
res["forecast"] = {"n_files": len(fm_fc), "in_universe": len(UNIV & set(fm_fc)),
                   "universe_cov_pct": round(100.0 * len(UNIV & set(fm_fc)) / len(UNIV), 1)}
res["express"] = {"n_files": len(fm_ex), "in_universe": len(UNIV & set(fm_ex)),
                  "universe_cov_pct": round(100.0 * len(UNIV & set(fm_ex)) / len(UNIV), 1)}

# fresh-event coverage per base date: % of universe with a forecast/express
# announced in the past 60 calendar days (PIT min(first_ann,ann))
def dt(s):
    return pd.to_datetime(s, format="%Y%m%d", errors="coerce")

base_dt = pd.to_datetime(BASE, format="%Y%m%d")
fc_cnt = np.zeros(len(BASE)); ex_cnt = np.zeros(len(BASE))
n_read = 0
yoy_checks = []  # (n_income, yoy_col, end_date) for semantic check via 1y-lag self-join
ex_store = {}
for ts in COLS:
    p = fm_fc.get(ts)
    if p:
        df = pd.read_csv(p, dtype={"ann_date": str, "first_ann_date": str, "end_date": str})
        if len(df):
            pit = df[["ann_date", "first_ann_date"]].apply(dt).min(axis=1)
            pit = pit.dropna().sort_values().values
            for i, b in enumerate(base_dt):
                lo, hi = b - pd.Timedelta(days=60), b
                k = np.searchsorted(pit, np.datetime64(hi), side="right") - np.searchsorted(pit, np.datetime64(lo), side="left")
                if k > 0: fc_cnt[i] += 1
    q = fm_ex.get(ts)
    if q:
        dfe = pd.read_csv(q, dtype={"ann_date": str, "end_date": str})
        if len(dfe):
            ex_store[ts] = dfe
            pit = dt(dfe["ann_date"]).dropna().sort_values().values
            for i, b in enumerate(base_dt):
                lo, hi = b - pd.Timedelta(days=60), b
                k = np.searchsorted(pit, np.datetime64(hi), side="right") - np.searchsorted(pit, np.datetime64(lo), side="left")
                if k > 0: ex_cnt[i] += 1
    n_read += 1

res["forecast"]["fresh60_cov_pct_by_date"] = {BASE[i]: round(100*fc_cnt[i]/len(COLS),1) for i in range(len(BASE))}
res["express"]["fresh60_cov_pct_by_date"] = {BASE[i]: round(100*ex_cnt[i]/len(COLS),1) for i in range(len(BASE))}
res["forecast"]["fresh60_cov_pct_mean"] = round(100*fc_cnt.mean()/len(COLS),1)
res["express"]["fresh60_cov_pct_mean"] = round(100*ex_cnt.mean()/len(COLS),1)

# semantic check of yoy_net_profit: is it percent or last-year absolute profit?
# test A: |value| > 1e6 share (absolute amounts) vs small (percent)
# test B: match value[t] against n_income at end_date one year earlier
mag_large = 0; mag_small = 0; match = 0; tot = 0
for ts, dfe in ex_store.items():
    dfe = dfe.dropna(subset=["yoy_net_profit"])
    if not len(dfe): continue
    v = dfe["yoy_net_profit"].astype(float)
    mag_large += int((v.abs() > 1e6).sum()); mag_small += int((v.abs() <= 1e4).sum())
    ni = {str(e): float(x) for e, x in zip(dfe["end_date"], dfe["n_income"]) if np.isfinite(x)}
    for e, val in zip(dfe["end_date"], v):
        e = str(e); prev = str(int(e[:4]) - 1) + e[4:]
        if prev in ni and abs(ni[prev]) > 1:
            tot += 1
            if abs(val - ni[prev]) / abs(ni[prev]) < 0.05:
                match += 1
res["express"]["yoy_semantic"] = {
    "n_abs_gt_1e6": mag_large, "n_abs_le_1e4": mag_small,
    "match_lastyear_n_income": match, "checkable": tot,
    "match_rate": round(match / tot, 3) if tot else None}

json.dump(res, open(os.path.join(HERE, "feasibility.json"), "w"), ensure_ascii=False, indent=1, default=str)
print(json.dumps({k: {kk: vv for kk, vv in v.items() if not isinstance(vv, dict)} for k, v in res.items()},
                 ensure_ascii=False, indent=1, default=str))
print("forecast fresh60 mean cov%:", res["forecast"]["fresh60_cov_pct_mean"])
print("express  fresh60 mean cov%:", res["express"]["fresh60_cov_pct_mean"])
print("yoy_semantic:", res["express"]["yoy_semantic"])
