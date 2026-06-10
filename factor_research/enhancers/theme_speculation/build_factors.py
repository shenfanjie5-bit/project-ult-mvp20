#!/usr/bin/env python3
"""Build PIT-safe theme_speculation factor matrices aligned to the panel.

All factors at base date d use ONLY limit-file rows with trade_date <= d.
Calendar = limit-file trade dates (verified complete vs index calendar 2023+).
Base dates beyond the limit-data end (20260323) -> all NaN.

Factors (D x N, aligned to panel_meta cols):
  t1_lu20        # limit-up (U) days in past 20 td               [0 if none]
  t1b_touch20    # touch days (U or Z) in past 20 td             [0 if none]
  t2_height10    max 连板数 (limit_times) among U in past 10 td   [0 if none]
  t3_zha20       (#Z + #U with open_times>0) / #touch, past 20td [NaN if no touch]
  t4a_indheat5   industry share of all U events, past 5 td       [NaN if industry unknown]
  t4b_indrot     industry U count 5td / industry U count 60td    [NaN if ind unknown or 60td count==0]
  t5a_cptheat5   mean over stock's THS concepts of (U events among members past 5td / n_members)  [SNAPSHOT membership]
  t5b_cptrot     t5a minus same quantity for past 60td scaled to 5td rate  [SNAPSHOT membership]
"""
import os, json
os.environ['DOCKCASE_WRITEBACK'] = '0'
import numpy as np
import pandas as pd

BASE = "/Volumes/dockcase2tb/database_all/股票数据/打板专题数据"
PROJ = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
OUT = f"{PROJ}/factor_research/enhancers/theme_speculation"

meta = json.load(open(f"{PROJ}/factor_research/model/panel_meta.json"))
base_dates = [str(d) for d in meta["base_dates"]]
cols = list(meta["cols"])
N = len(cols)
D = len(base_dates)
col_idx = {c: j for j, c in enumerate(cols)}

lim = pd.read_csv(f"{BASE}/涨跌停和炸板数据/all.csv", dtype={'trade_date': str}, low_memory=False)
cal = sorted(lim.trade_date.unique())
cal_pos = {dt: i for i, dt in enumerate(cal)}
last_data = cal[-1]

# verify every usable base date is in calendar
usable = [d for d in base_dates if d <= last_data]
missing = [d for d in usable if d not in cal_pos]
assert not missing, f"base dates missing from limit calendar: {missing}"
print(f"usable base dates: {len(usable)}/{D} (dropped beyond {last_data}: {[d for d in base_dates if d > last_data]})")

lim = lim[lim.limit.isin(['U', 'Z'])].copy()   # ignore D (跌停) for these factors
lim['pos'] = lim.trade_date.map(cal_pos)
lim['j'] = lim.ts_code.map(col_idx)            # NaN for non-panel stocks (kept for industry/concept aggregates)
lim['isU'] = (lim.limit == 'U').astype(int)
lim['isZha'] = ((lim.limit == 'Z') | ((lim.limit == 'U') & (lim.open_times > 0))).astype(int)
lim['lt'] = pd.to_numeric(lim.limit_times, errors='coerce').fillna(0)

# ---- dense per-position event arrays for panel stocks ----
P = len(cal)
panel_rows = lim[lim.j.notna()].copy()
panel_rows['j'] = panel_rows.j.astype(int)
U = np.zeros((P, N), dtype=np.int16)     # limit-up day
T = np.zeros((P, N), dtype=np.int16)     # touch day (U or Z)
ZH = np.zeros((P, N), dtype=np.int16)    # zha event day
HT = np.zeros((P, N), dtype=np.int16)    # 连板数 on U days
for r in panel_rows.itertuples():
    U[r.pos, r.j] |= r.isU
    T[r.pos, r.j] = 1
    ZH[r.pos, r.j] |= r.isZha
    if r.isU:
        HT[r.pos, r.j] = max(HT[r.pos, r.j], int(r.lt))

cU = np.vstack([np.zeros((1, N), np.int32), U.cumsum(0)])    # P+1
cT = np.vstack([np.zeros((1, N), np.int32), T.cumsum(0)])
cZ = np.vstack([np.zeros((1, N), np.int32), ZH.cumsum(0)])

def wsum(c, pos, w):
    lo = max(0, pos + 1 - w)
    return c[pos + 1] - c[lo]

# ---- industry aggregates (industry field is PIT, whole market not just panel) ----
ind_codes = {v: k for k, v in enumerate(sorted(lim.industry.dropna().unique()))}
NI = len(ind_codes)
lim['ind_k'] = lim.industry.map(ind_codes)
IU = np.zeros((P, NI), dtype=np.int32)   # industry U-event count per day (whole market)
for r in lim[lim.isU == 1].itertuples():
    if r.ind_k == r.ind_k:
        IU[r.pos, int(r.ind_k)] += 1
cIU = np.vstack([np.zeros((1, NI), np.int64), IU.cumsum(0)])

# PIT stock->industry map: most recent limit-file record at or before each base date
pr = panel_rows.sort_values('pos').copy()
pr['ind_k'] = pr.industry.map(ind_codes)
stock_ind_hist = {}   # j -> list[(pos, ind_k)]
for r in pr.itertuples():
    if r.ind_k == r.ind_k:
        stock_ind_hist.setdefault(r.j, []).append((r.pos, int(r.ind_k)))

def ind_asof(j, pos):
    h = stock_ind_hist.get(j)
    if not h:
        return -1
    best = -1
    for p, k in h:
        if p <= pos:
            best = k
        else:
            break
    return best

# ---- concept aggregates (membership = CURRENT SNAPSHOT -> look-ahead caveat) ----
mem = pd.read_csv(f"{BASE}/同花顺行业概念成分/all.csv")
blk = pd.read_csv(f"{BASE}/同花顺行业概念板块/all.csv")
ncpt = set(blk[blk.type == 'N'].ts_code)
mem = mem[mem.ts_code.isin(ncpt)]
cpt_codes = {v: k for k, v in enumerate(sorted(mem.ts_code.unique()))}
NC = len(cpt_codes)
mem['ck'] = mem.ts_code.map(cpt_codes)
# concept member counts (whole-market members)
cpt_size = mem.groupby('ck').size().reindex(range(NC)).fillna(1).values.astype(float)
# stock(panel j) -> list of concept ks
mem_p = mem[mem.con_code.isin(col_idx)]
stock_cpts = {}
for r in mem_p.itertuples():
    stock_cpts.setdefault(col_idx[r.con_code], []).append(int(r.ck))
# concept U-event counts per day: map ALL limit rows (whole market) via membership con_code
all_codes = {c: i for i, c in enumerate(sorted(lim.ts_code.unique()))}
code_cpts = {}
for r in mem.itertuples():
    if r.con_code in all_codes:
        code_cpts.setdefault(r.con_code, []).append(int(r.ck))
CU = np.zeros((P, NC), dtype=np.int32)
for r in lim[lim.isU == 1].itertuples():
    for ck in code_cpts.get(r.ts_code, ()):
        CU[r.pos, ck] += 1
cCU = np.vstack([np.zeros((1, NC), np.int64), CU.cumsum(0)])

# ---- assemble factor matrices ----
names = ['t1_lu20', 't1b_touch20', 't2_height10', 't3_zha20',
         't4a_indheat5', 't4b_indrot', 't5a_cptheat5', 't5b_cptrot']
F = {n: np.full((D, N), np.nan, np.float32) for n in names}

for di, d in enumerate(base_dates):
    if d > last_data:
        continue
    pos = cal_pos[d]
    if pos < 59:   # need 60d lookback for rotation factors; all have >=60 (panel starts 2023)
        pass
    u20 = wsum(cU, pos, 20).astype(float)
    t20 = wsum(cT, pos, 20).astype(float)
    z20 = wsum(cZ, pos, 20).astype(float)
    F['t1_lu20'][di] = u20
    F['t1b_touch20'][di] = t20
    with np.errstate(invalid='ignore', divide='ignore'):
        zr = np.where(t20 > 0, z20 / np.maximum(t20, 1), np.nan)
    F['t3_zha20'][di] = zr
    # height: max limit_times in past 10 td
    lo = max(0, pos + 1 - 10)
    F['t2_height10'][di] = HT[lo:pos + 1].max(0).astype(float)
    # industry heat
    iu5 = (cIU[pos + 1] - cIU[max(0, pos + 1 - 5)]).astype(float)
    iu60 = (cIU[pos + 1] - cIU[max(0, pos + 1 - 60)]).astype(float)
    tot5 = iu5.sum()
    share5 = iu5 / max(tot5, 1)
    rot = np.where(iu60 > 0, iu5 / iu60, np.nan)
    v4a = np.full(N, np.nan); v4b = np.full(N, np.nan)
    for j in range(N):
        k = ind_asof(j, pos)
        if k >= 0:
            v4a[j] = share5[k]
            v4b[j] = rot[k]
    F['t4a_indheat5'][di] = v4a
    F['t4b_indrot'][di] = v4b
    # concept heat (snapshot membership)
    cu5 = (cCU[pos + 1] - cCU[max(0, pos + 1 - 5)]).astype(float) / cpt_size
    cu60 = (cCU[pos + 1] - cCU[max(0, pos + 1 - 60)]).astype(float) / cpt_size
    v5a = np.full(N, np.nan); v5b = np.full(N, np.nan)
    for j, cks in stock_cpts.items():
        a = np.mean(cu5[cks])
        v5a[j] = a
        v5b[j] = a - np.mean(cu60[cks]) * (5.0 / 60.0)
    F['t5a_cptheat5'][di] = v5a
    F['t5b_cptrot'][di] = v5b

np.savez_compressed(f"{OUT}/theme_factors.npz", **F,
                    names=np.array(names), base_dates=np.array(base_dates))
print("saved", f"{OUT}/theme_factors.npz")
for n in names:
    f = F[n]
    cov = np.isfinite(f).mean(1)
    nz = np.nanmean((f > 0).astype(float), axis=1)
    print(f"{n:14s} coverage/date mean={np.nanmean(cov):.3f} min={np.nanmin(cov[:len(usable)]):.3f}  "
          f">0 share mean={np.nanmean(nz):.3f}")
