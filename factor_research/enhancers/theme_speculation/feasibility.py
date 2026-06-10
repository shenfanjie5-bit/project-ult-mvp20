#!/usr/bin/env python3
"""Feasibility scan for theme_speculation family (PIT check, coverage, ranges)."""
import os, json
os.environ['DOCKCASE_WRITEBACK'] = '0'
import numpy as np
import pandas as pd

BASE = "/Volumes/dockcase2tb/database_all/股票数据/打板专题数据"
PROJ = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"

meta = json.load(open(f"{PROJ}/factor_research/model/panel_meta.json"))
base_dates = [str(d) for d in meta["base_dates"]]
cols = meta["cols"]
print("panel:", len(base_dates), "dates", base_dates[0], "->", base_dates[-1], ";", len(cols), "stocks")

# 1) limit-up/down/zha file
lim = pd.read_csv(f"{BASE}/涨跌停和炸板数据/all.csv", dtype={'trade_date': str}, low_memory=False)
lim_dates = sorted(lim.trade_date.unique())
print("\n[limit] rows", len(lim), "dates", len(lim_dates), lim_dates[0], "->", lim_dates[-1])
# gaps: trading days per year
yr = pd.Series(lim_dates).str[:4].value_counts().sort_index()
print("[limit] dates per year:\n", yr.to_string())
# panel stock coverage: ever appeared before each of a few base dates
lim_u = lim[lim.limit == 'U']
print("[limit] U rows", len(lim_u), "Z rows", (lim.limit == 'Z').sum(), "D rows", (lim.limit == 'D').sum())
print("[limit] limit_times stats on U:", lim_u.limit_times.describe().loc[['min','50%','max']].to_dict())
print("[limit] open_times>0 share among U:", (lim_u.open_times > 0).mean().round(3))
cols_set = set(cols)
in_panel = lim.ts_code.isin(cols_set)
print("[limit] rows belonging to panel stocks:", in_panel.mean().round(3))
ever = lim[in_panel].groupby('ts_code').trade_date.min()
print("[limit] panel stocks ever in limit file:", len(ever), "/", len(cols))

# 2) ladder
lad = pd.read_csv(f"{BASE}/涨停股票连板天梯/all.csv", dtype={'trade_date': str})
lad_dates = sorted(lad.trade_date.unique())
print("\n[ladder] rows", len(lad), "dates", len(lad_dates), lad_dates[0], "->", lad_dates[-1])
print("[ladder] dates per year:\n", pd.Series(lad_dates).str[:4].value_counts().sort_index().to_string())
print("[ladder] nums dist:", lad.nums.value_counts().sort_index().head(8).to_dict())
# consistency vs limit_times
m = lad.merge(lim_u[['ts_code','trade_date','limit_times']], on=['ts_code','trade_date'], how='left')
print("[ladder] merge match rate:", m.limit_times.notna().mean().round(3),
      "equal rate:", (m.nums == m.limit_times).mean().round(3))

# 3) concept index OHLC
ci = pd.read_csv(f"{BASE}/同花顺概念和行业指数行情/all.csv", dtype={'trade_date': str},
                 usecols=['ts_code','trade_date','close','pct_change'])
print("\n[concept_idx] rows", len(ci), "codes", ci.ts_code.nunique(),
      "dates", ci.trade_date.min(), "->", ci.trade_date.max())
print("[concept_idx] code prefixes:", ci.ts_code.str[:3].value_counts().head(6).to_dict())

# 4) membership snapshot
mem = pd.read_csv(f"{BASE}/同花顺行业概念成分/all.csv")
blk = pd.read_csv(f"{BASE}/同花顺行业概念板块/all.csv")
print("\n[membership] rows", len(mem), "blocks", mem.ts_code.nunique())
print("[blocks] type counts:", blk.type.value_counts().to_dict())
mem2 = mem.merge(blk[['ts_code','type','name']], on='ts_code', how='left')
con = mem2[mem2.type == 'N']
print("[membership] concept(N) rows", len(con), "concepts", con.ts_code.nunique())
pstocks = con[con.con_code.isin(cols_set)]
print("[membership] panel stocks with >=1 concept:", pstocks.con_code.nunique(), "/", len(cols),
      "; concepts/stock median:", pstocks.groupby('con_code').size().median())
# concept codes overlap with index OHLC
ci_codes = set(ci.ts_code.unique())
print("[membership] concepts with OHLC history:", len(set(con.ts_code) & ci_codes), "/", con.ts_code.nunique())

# 5) strongest-sector stats + KPL theme
ss = pd.read_csv(f"{BASE}/涨停最强板块统计/all.csv", dtype={'trade_date': str})
print("\n[strong_sector] rows", len(ss), "dates", ss.trade_date.nunique(),
      ss.trade_date.min(), "->", ss.trade_date.max())
kp = pd.read_csv(f"{BASE}/题材数据（开盘啦）/all.csv", dtype={'trade_date': str})
print("[KPL theme] rows", len(kp), "dates", kp.trade_date.nunique(), kp.trade_date.min(), "->", kp.trade_date.max())

# 6) base date alignment: how many base dates beyond limit data end?
last = lim_dates[-1]
tail = [d for d in base_dates if d > last]
print("\nbase dates beyond limit-data end:", tail)
# trading calendar from concept index (dense daily) vs limit dates
cal = sorted(ci.trade_date.unique())
cal2326 = [d for d in cal if '20230101' <= d <= last]
limset = set(lim_dates)
missing = [d for d in cal2326 if d not in limset]
print("calendar days 2023+ missing from limit file:", len(missing), missing[:10])
