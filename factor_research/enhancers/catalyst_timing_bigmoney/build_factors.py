#!/usr/bin/env python3
"""Build PIT-safe factor matrices [67 x 1617] aligned to panel base_dates/cols.

PART 1 (catalyst timing):
  f1_fc30 / f1_fc60 : fresh forecast (业绩预告) surprise announced within the
                      past 30/60 calendar days of the base date, NaN otherwise.
                      PIT date = min(first_ann_date, ann_date).
                      surprise = midpoint(p_change_min,p_change_max)/100,
                      fallback (midpoint(net_profit_min,max)-last_parent_net)/|last_parent_net|,
                      clipped to [-3,3] (same clip as panel npq_yoy).
  f2_ex60           : fresh express (业绩快报) surprise within 60d. The CSV's
                      `yoy_net_profit` column was empirically verified to hold
                      LAST YEAR'S absolute net profit (92.3% exact match with
                      n_income one year prior), NOT a percent. So
                      surprise = (n_income - yoy_col)/|yoy_col|, clip [-3,3].
  f3_speed60        : freshest-of(forecast, express) surprise within 60d
                      (same yoy-growth scale, so directly comparable);
                      forecast wins ties (earlier in disclosure chain but here
                      tie = same pit date, rare).

PART 2 (big-money remainder, only feasible source):
  chip_winner : winner_rate (获利盘 %) from 每日筹码及胜率, latest trade_date
                <= base date within 10 calendar days.
  chip_conc   : (cost_85pct - cost_15pct) / cost_50pct  (chip dispersion;
                low = concentrated holder cost).

All lookups are strict PIT: only rows dated <= base_date are used.
"""
import os, json, glob, bisect
import numpy as np
import pandas as pd

os.environ["DOCKCASE_WRITEBACK"] = "0"

ROOT = "/Volumes/dockcase2tb/database_all/股票数据"
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
META = json.load(open(os.path.join(PROJ, "factor_research/model/panel_meta.json")))
COLS = META["cols"]; BASE = META["base_dates"]
D, N = len(BASE), len(COLS)
BASE_DT = pd.to_datetime(BASE, format="%Y%m%d")
BASE_NP = BASE_DT.values  # datetime64[ns]


def file_map(d):
    out = {}
    for p in glob.glob(os.path.join(d, "*.csv")):
        out[os.path.basename(p).split("+")[0]] = p
    return out


fm_fc = file_map(os.path.join(ROOT, "财务数据/业绩预告/by_symbol"))
fm_ex = file_map(os.path.join(ROOT, "财务数据/业绩快报/by_symbol"))
fm_ch = file_map(os.path.join(ROOT, "特色数据/每日筹码及胜率/by_symbol"))

f1_30 = np.full((D, N), np.nan); f1_60 = np.full((D, N), np.nan)
f2_60 = np.full((D, N), np.nan)
f3_60 = np.full((D, N), np.nan)
chip_win = np.full((D, N), np.nan); chip_conc = np.full((D, N), np.nan)

CLIP = 3.0

def fc_events(path):
    df = pd.read_csv(path, dtype={"ann_date": str, "first_ann_date": str, "end_date": str})
    if not len(df):
        return []
    pit = df[["ann_date", "first_ann_date"]].apply(
        lambda c: pd.to_datetime(c, format="%Y%m%d", errors="coerce")).min(axis=1)
    ev = []
    for i, row in df.iterrows():
        p = pit.iloc[i]
        if pd.isna(p):
            continue
        s = np.nan
        pcs = [row.get("p_change_min"), row.get("p_change_max")]
        pcs = [float(x) for x in pcs if pd.notna(x)]
        if pcs:
            s = float(np.mean(pcs)) / 100.0
        else:
            nps = [row.get("net_profit_min"), row.get("net_profit_max")]
            nps = [float(x) for x in nps if pd.notna(x)]
            last = row.get("last_parent_net")
            if nps and pd.notna(last) and abs(float(last)) > 1.0:
                s = (float(np.mean(nps)) - float(last)) / abs(float(last))
        if np.isfinite(s):
            ev.append((p.to_datetime64(), str(row.get("end_date")), float(np.clip(s, -CLIP, CLIP))))
    ev.sort(key=lambda x: (x[0], x[1]))
    return ev


def ex_events(path):
    df = pd.read_csv(path, dtype={"ann_date": str, "end_date": str})
    if not len(df):
        return []
    ev = []
    for _, row in df.iterrows():
        a = pd.to_datetime(str(row.get("ann_date")), format="%Y%m%d", errors="coerce")
        if pd.isna(a):
            continue
        ni, last = row.get("n_income"), row.get("yoy_net_profit")
        if pd.isna(ni) or pd.isna(last) or abs(float(last)) <= 1.0:
            continue
        s = (float(ni) - float(last)) / abs(float(last))
        ev.append((a.to_datetime64(), str(row.get("end_date")), float(np.clip(s, -CLIP, CLIP))))
    ev.sort(key=lambda x: (x[0], x[1]))
    return ev


def fill_fresh(mat, j, events, window_days):
    """events sorted by pit; mat[d,j] = surprise of the event with the max pit
    in (base-window, base]."""
    if not events:
        return
    pits = np.array([e[0] for e in events])
    for d in range(D):
        hi = np.searchsorted(pits, BASE_NP[d], side="right")
        if hi == 0:
            continue
        k = hi - 1
        age = (BASE_NP[d] - pits[k]) / np.timedelta64(1, "D")
        if age <= window_days:
            mat[d, j] = events[k][2]


def freshest_of(j, ev_a, ev_b, window_days):
    """f3: among the latest fresh event from each source, take the one with the
    more recent pit (tie -> forecast=ev_a)."""
    pits_a = np.array([e[0] for e in ev_a]) if ev_a else None
    pits_b = np.array([e[0] for e in ev_b]) if ev_b else None
    for d in range(D):
        best = None  # (pit, prio, val)
        for pits, ev, prio in ((pits_a, ev_a, 1), (pits_b, ev_b, 0)):
            if pits is None:
                continue
            hi = np.searchsorted(pits, BASE_NP[d], side="right")
            if hi == 0:
                continue
            k = hi - 1
            age = (BASE_NP[d] - pits[k]) / np.timedelta64(1, "D")
            if age <= window_days:
                cand = (pits[k], prio, ev[k][2])
                if best is None or cand[:2] > best[:2]:
                    best = cand
        if best is not None:
            f3_60[d, j] = best[2]


n_fc = n_ex = n_ch = 0
for j, ts in enumerate(COLS):
    pa = fm_fc.get(ts)
    ev_a = fc_events(pa) if pa else []
    if ev_a:
        n_fc += 1
        fill_fresh(f1_30, j, ev_a, 30)
        fill_fresh(f1_60, j, ev_a, 60)
    pb = fm_ex.get(ts)
    ev_b = ex_events(pb) if pb else []
    if ev_b:
        n_ex += 1
        fill_fresh(f2_60, j, ev_b, 60)
    if ev_a or ev_b:
        freshest_of(j, ev_a, ev_b, 60)

    pc = fm_ch.get(ts)
    if pc:
        try:
            dc = pd.read_csv(pc, usecols=["trade_date", "cost_15pct", "cost_50pct",
                                          "cost_85pct", "winner_rate"], dtype={"trade_date": str})
        except Exception:
            dc = None
        if dc is not None and len(dc):
            n_ch += 1
            dc = dc.sort_values("trade_date")
            td = pd.to_datetime(dc["trade_date"], format="%Y%m%d", errors="coerce").values
            wr = dc["winner_rate"].astype(float).values
            c15 = dc["cost_15pct"].astype(float).values
            c50 = dc["cost_50pct"].astype(float).values
            c85 = dc["cost_85pct"].astype(float).values
            for d in range(D):
                hi = np.searchsorted(td, BASE_NP[d], side="right")
                if hi == 0:
                    continue
                k = hi - 1
                age = (BASE_NP[d] - td[k]) / np.timedelta64(1, "D")
                if age <= 10:
                    chip_win[d, j] = wr[k]
                    if np.isfinite(c50[k]) and c50[k] > 0:
                        chip_conc[d, j] = (c85[k] - c15[k]) / c50[k]
    if (j + 1) % 400 == 0:
        print(f"{j+1}/{N} symbols", flush=True)

np.savez_compressed(os.path.join(HERE, "factors.npz"),
                    f1_fc30=f1_30, f1_fc60=f1_60, f2_ex60=f2_60, f3_speed60=f3_60,
                    chip_winner=chip_win, chip_conc=chip_conc)

cov = {}
for nm, m in [("f1_fc30", f1_30), ("f1_fc60", f1_60), ("f2_ex60", f2_60),
              ("f3_speed60", f3_60), ("chip_winner", chip_win), ("chip_conc", chip_conc)]:
    per_date = np.isfinite(m).mean(axis=1) * 100
    cov[nm] = {"mean_pct": round(float(per_date.mean()), 1),
               "min_pct": round(float(per_date.min()), 1),
               "max_pct": round(float(per_date.max()), 1),
               "by_date": {BASE[d]: round(float(per_date[d]), 1) for d in range(D)}}
json.dump(cov, open(os.path.join(HERE, "factor_coverage.json"), "w"), indent=1)
print("symbols with events: fc", n_fc, "ex", n_ex, "chip", n_ch)
for nm in cov:
    print(nm, "cov mean/min/max %:", cov[nm]["mean_pct"], cov[nm]["min_pct"], cov[nm]["max_pct"])
