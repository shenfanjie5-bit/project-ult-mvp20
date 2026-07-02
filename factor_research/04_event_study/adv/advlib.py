#!/usr/bin/env python3
"""Adversarial re-implementation of eventlib's abnormal-return + P&L engine,
parameterized on an arbitrary price panel (so we can swap the SURVIVOR panel for
the DE-SURVIVORED full panel and isolate selection/survivorship bias).

The math is copied line-for-line from factor_research/04_event_study/eventlib.py
(CUM/VCUM log-return cum-sum; size = MV-decile mean forward return; mkt = EW mean;
PIT entry e = last trade day <= ann_date; forward window e+1..e+h). Verified to
reproduce eventlib's numbers when fed the same 1617-name panel.

Read-only. No project writes.
"""
from __future__ import annotations
import os, glob, json, bisect, sys
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
DC = "/Volumes/dockcase2tb/database_all/股票数据"
FC_FOLDER = os.path.join(DC, "财务数据", "业绩预告", "by_symbol")

_FC_POS = {"预增", "略增", "扭亏", "续盈", "减亏"}
_FC_NEG = {"预减", "略减", "首亏", "续亏", "增亏"}
WIN_LO, WIN_HI = "20230103", "20260531"


# ───────────────────────── panel container ─────────────────────────
class Panel:
    def __init__(self, RET, MV, TO, cal, cols):
        R = np.asarray(RET, float)
        Rfill = np.where(np.isfinite(R), R, 0.0)
        LOG = np.log1p(np.clip(Rfill, -0.99, None))
        self.R = R
        self.MV = np.asarray(MV, float)
        self.TO = np.asarray(TO, float)
        self.cal = list(cal)
        self.cols = list(cols)
        self.CUM = np.cumsum(LOG, axis=0)
        self.VCUM = np.cumsum(np.isfinite(R).astype(np.int32), axis=0)
        self.colidx = {c: i for i, c in enumerate(self.cols)}
        self._xs = {}

    @classmethod
    def from_npz(cls, npz, js):
        d = np.load(npz)
        meta = json.load(open(js))
        return cls(d["RET"], d["MV"], d["TO"], meta["cal"], meta["cols"])

    @classmethod
    def survivor(cls):
        """The 1617-name panel exactly as eventlib.panel() builds it."""
        base = os.path.join(HERE, "..", "..", "data")
        return cls.from_npz(os.path.join(base, "px_20230101.npz"),
                            os.path.join(base, "px_20230101.json"))

    @classmethod
    def full(cls):
        return cls.from_npz(os.path.join(HERE, "full_panel.npz"),
                            os.path.join(HERE, "full_panel.json"))

    def xsec(self, e, h):
        key = (e, h)
        if key in self._xs:
            return self._xs[key]
        n = self.CUM.shape[0]
        if e < 0 or e + h >= n:
            self._xs[key] = None
            return None
        fwd = np.exp(self.CUM[e + h] - self.CUM[e]) - 1.0
        vdays = self.VCUM[e + h] - self.VCUM[e]
        valid = (vdays >= max(1, int(0.6 * h))) & np.isfinite(self.MV[e])
        f = np.where(valid, fwd, np.nan)
        mkt = np.nanmean(f)
        mv = np.where(valid, self.MV[e], np.nan)
        decmean = np.full(len(mv), mkt)
        order = [i for i in np.argsort(np.where(np.isfinite(mv), mv, np.inf)) if np.isfinite(mv[i])]
        m = len(order)
        if m >= 50:
            for dd in range(10):
                ids = order[int(dd * m / 10):int((dd + 1) * m / 10)]
                if ids:
                    decmean[ids] = np.nanmean(f[ids])
        self._xs[key] = (f, mkt, decmean, valid)
        return self._xs[key]


# ───────────────────────── event loading (full universe) ─────────────────────────
def _read_symbol(path):
    ts = os.path.basename(path).split("+")[0]
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception:
        return None
    if "ann_date" not in df.columns:
        return None
    df["ts_code"] = ts
    return df


def load_forecast_events(cols):
    """Normalize 业绩预告 -> [ts_code,event_date,sign,magnitude,subtype], restricted
    to `cols` (the panel universe) and the window. Mirrors eventlib._normalize."""
    colset = set(cols)
    files = [p for p in glob.glob(os.path.join(FC_FOLDER, "*.csv"))
             if os.path.basename(p).split("+")[0] in colset]
    parts = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for r in ex.map(_read_symbol, files):
            if r is not None:
                parts.append(r)
    d = pd.concat(parts, ignore_index=True)
    dt = d["first_ann_date"].fillna(d["ann_date"]) if "first_ann_date" in d else d["ann_date"]
    d = d.assign(event_date=dt.astype(str))
    typ = d["type"].astype(str)
    sign = np.where(typ.isin(_FC_POS), 1.0, np.where(typ.isin(_FC_NEG), -1.0, 0.0))
    pmin = pd.to_numeric(d.get("p_change_min"), errors="coerce")
    pmax = pd.to_numeric(d.get("p_change_max"), errors="coerce")
    mag = ((pmin + pmax) / 2.0) / 100.0
    out = pd.DataFrame({"ts_code": d["ts_code"], "event_date": d["event_date"],
                        "sign": sign, "magnitude": mag.values, "subtype": typ})
    out["_ed"] = d["end_date"].astype(str).values
    out = out.sort_values("event_date").groupby(["ts_code", "_ed"], as_index=False).first()
    out = out.drop(columns="_ed")
    out = out.dropna(subset=["event_date"])
    out = out[(out["event_date"] >= WIN_LO) & (out["event_date"] <= WIN_HI)]
    out = out[out["ts_code"].isin(colset)].reset_index(drop=True)
    return out


def attach(ev, P: Panel):
    e = np.array([bisect.bisect_right(P.cal, d) - 1 for d in ev["event_date"]])
    j = np.array([P.colidx.get(t, -1) for t in ev["ts_code"]])
    out = ev.copy()
    out["e"] = e
    out["j"] = j
    return out[(out["e"] >= 0) & (out["j"] >= 0)].reset_index(drop=True)


def abnormal(ev, h, P: Panel, method="size"):
    """Abnormal forward-h return per event. ev must have e,j and a clean RangeIndex."""
    out = np.full(len(ev), np.nan)
    for e, grp in ev.groupby("e"):
        xs = P.xsec(int(e), h)
        if xs is None:
            continue
        f, mkt, decmean, valid = xs
        for idx, j in zip(grp.index, grp["j"].values):
            if 0 <= j < len(valid) and valid[j]:
                out[idx] = f[j] - (decmean[j] if method == "size" else mkt)
    return out


def fold_of(d):
    return f"{d[:4]}{'H1' if d[4:6] <= '06' else 'H2'}"


def pnl_long_only(ev, h, P: Panel, method="size", cost_bps=25, mask=None):
    """Per-fold long-only net abnormal (sign>0). Returns (per_fold_df, summary)."""
    e = ev.copy()
    e["fold"] = [fold_of(d) for d in e["event_date"]]
    abn = abnormal(e, h, P, method=method)
    e = e.assign(abn=abn).dropna(subset=["abn"])
    if mask is not None:
        e = e[mask.loc[e.index]] if hasattr(mask, "loc") else e[mask]
    cost = cost_bps / 1e4
    rows = []
    for fold, g in e.groupby("fold"):
        longs = g[g["sign"] > 0]["abn"]
        net = longs.mean() - cost if len(longs) else np.nan
        rows.append(dict(fold=fold, n_long=len(longs), gross_bps=longs.mean() * 1e4 if len(longs) else np.nan,
                         net_bps=net * 1e4, win=bool(np.isfinite(net) and net > 0)))
    pf = pd.DataFrame(rows).sort_values("fold").reset_index(drop=True)
    nf = int(pf["net_bps"].notna().sum())
    wins = int(pf["win"].sum())
    summ = dict(folds=nf, wins=wins, mean_net_bps=float(pf["net_bps"].mean()),
                pass_majority=bool(nf and wins > nf / 2), n_events=len(e),
                n_long=int((e["sign"] > 0).sum()))
    return pf, summ
