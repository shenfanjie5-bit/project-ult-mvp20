#!/usr/bin/env python3
"""Build a DE-SURVIVORED price panel over the FULL DockCase daily universe.

Mirrors factor_research/_datalib.load_price_matrices EXACTLY (same columns, same
return convention pct_chg/100, same >=30-row filter, same MV/TO from daily_basic),
EXCEPT:
  * iterates the WHOLE 历史日线/by_symbol folder (~5800 symbols) instead of
    _datalib.universe() (the 1617 scored survivors);
  * does NOT drop files whose name contains ST/PT/退 -> delisted & ST names kept.

Output: factor_research/04_event_study/adv/full_panel.npz + .json
  RET, TO, MV  (n_days x n_stocks, NaN where missing)
  cal, cols
Read-only on DockCase. Run from REPO ROOT with the research venv.
"""
from __future__ import annotations
import os, glob, json, sys
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor

DC = "/Volumes/dockcase2tb/database_all/股票数据"
DAILY = os.path.join(DC, "行情数据", "历史日线", "by_symbol")
DBASIC = os.path.join(DC, "行情数据", "每日指标", "by_symbol")
OUT = os.path.dirname(os.path.abspath(__file__))
START = "20230101"


def _index(folder):
    idx = {}
    for p in glob.glob(os.path.join(folder, "*.csv")):
        idx[os.path.basename(p).split("+")[0]] = p
    return idx


def _read_daily(args):
    ts, path = args
    try:
        x = pd.read_csv(path, usecols=["trade_date", "pct_chg"], dtype={"trade_date": str})
    except Exception:
        return None
    x = x[x["trade_date"] >= START]
    if len(x) < 30:
        return None
    s = x.set_index("trade_date")["pct_chg"].astype(float) / 100.0
    s = s[~s.index.duplicated(keep="last")]
    return ts, s


def _read_basic(args):
    ts, path = args
    try:
        b = pd.read_csv(path, usecols=["trade_date", "turnover_rate", "total_mv"],
                        dtype={"trade_date": str})
    except Exception:
        return None
    b = b[b["trade_date"] >= START].set_index("trade_date")
    b = b[~b.index.duplicated(keep="last")]
    return ts, b["turnover_rate"].astype(float), b["total_mv"].astype(float)


def main():
    di, bi = _index(DAILY), _index(DBASIC)
    print(f"[full_panel] daily files={len(di)}  daily_basic files={len(bi)}")
    rets = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        for r in ex.map(_read_daily, list(di.items())):
            if r is not None:
                rets[r[0]] = r[1]
    print(f"[full_panel] symbols with >=30 daily rows since {START}: {len(rets)}")
    R = pd.DataFrame(rets).sort_index()
    cols = list(R.columns)
    tos, mvs = {}, {}
    todo = [(ts, bi[ts]) for ts in cols if ts in bi]
    with ThreadPoolExecutor(max_workers=12) as ex:
        for r in ex.map(_read_basic, todo):
            if r is not None:
                tos[r[0]] = r[1]
                mvs[r[0]] = r[2]
    TO = pd.DataFrame(tos).reindex(index=R.index, columns=R.columns)
    MV = pd.DataFrame(mvs).reindex(index=R.index, columns=R.columns)
    cal = list(R.index)
    print(f"[full_panel] final matrix: {len(cal)} days x {len(cols)} stocks "
          f"({cal[0]}..{cal[-1]});  MV coverage cols={MV.notna().any().sum()}")
    np.savez(os.path.join(OUT, "full_panel.npz"),
             RET=R.values, TO=TO.values, MV=MV.values)
    json.dump({"cal": cal, "cols": cols}, open(os.path.join(OUT, "full_panel.json"), "w"))
    print(f"[full_panel] wrote full_panel.npz + .json to {OUT}")


if __name__ == "__main__":
    main()
