#!/usr/bin/env python3
"""Event-study spine for Track A (structured corporate events -> signed impact).

ISOLATED research code. Read-only on project + DockCase (DOCKCASE_WRITEBACK=0).
Run from the REPO ROOT (paths in factor_research/_datalib are CWD-relative).

What this module guarantees (the leakage-critical contract every downstream
agent relies on):

  * PIT alignment: an event announced on calendar date D enters at the CLOSE of
    the last trading day <= D (index e). The forward window uses returns on days
    e+1 .. e+h ONLY -- the announcement-day return RET[e] is never counted, and
    no future info touches the entry. (A-share announcements post after close, so
    the first tradeable reaction is e+1; weekend/holiday filings roll to e+1.)
  * Abnormal return: raw forward return minus a same-day benchmark. Default
    'size' = mean forward return of the stock's MV-decile on day e (neutralises
    the dominant A-share small-cap factor); 'mkt' = equal-weight cross-section.
  * Survivorship caveat: the price panel universe is the ~1617 stocks scored as
    of 2026-01 -> delisted names are absent -> abnormal returns are upward-biased.
    This is a KNOWN ceiling, flagged here and to be quantified in Phase 3.

Public API:
  load_events(endpoint)                  -> normalized DataFrame (cached .pkl)
  attach_alignment(ev)                   -> + columns e (entry idx), j (col idx)
  abnormal_series(ev, h, method)         -> np.array of abnormal h-day returns
  event_study(ev, horizons, by)          -> per-bucket CAR table + significance
  walk_forward_folds(ev)                 -> + column 'fold' (half-year)
  portfolio_pnl(ev, h, ...)              -> per-fold net abnormal P&L after cost
  kill1 / kill2 / kill3                  -> pre-registered gate checks
"""
from __future__ import annotations

import bisect
import glob
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

os.environ.setdefault("DOCKCASE_WRITEBACK", "0")

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
DC = "/Volumes/dockcase2tb/database_all/股票数据"

# endpoint -> (by_symbol folder relative to DC, publish-date column)
FOLDERS = {
    "forecast":        ("财务数据/业绩预告/by_symbol", "ann_date"),
    "express":         ("财务数据/业绩快报/by_symbol", "ann_date"),
    "dividend":        ("财务数据/分红送股数据/by_symbol", "ann_date"),
    "report_rc":       ("特色数据/券商盈利预测数据/by_symbol", "report_date"),
    "stk_holdertrade": ("参考数据/股东增减持/by_symbol", "ann_date"),
}

WIN_LO, WIN_HI = "20230103", "20260531"   # inside price panel; leaves lookahead

# forecast type -> sign of the surprise
_FC_POS = {"预增", "略增", "扭亏", "续盈", "减亏"}
_FC_NEG = {"预减", "略减", "首亏", "续亏", "增亏"}
# report_rc rating -> ordinal sentiment tier
_RATING_TIER = {
    "买入": 2, "强烈推荐": 2, "强推": 2, "强烈买入": 2, "区间操作": 0,
    "增持": 1, "推荐": 1, "优于大市": 1, "跑赢行业": 1, "谨慎推荐": 1,
    "审慎增持": 1, "持有": 0, "中性": 0, "无": 0, "同步大市": 0, "维持": 0,
    "减持": -1, "卖出": -2, "回避": -2, "弱于大市": -1, "跑输行业": -1,
}

# ────────────────────────── price panel (lazy) ──────────────────────────
_PANEL = None


def panel():
    global _PANEL
    if _PANEL is not None:
        return _PANEL
    sys.path.insert(0, os.path.join(os.getcwd(), "factor_research"))
    import _datalib  # noqa: E402
    RET, TO, MV, cal, cols = _datalib.load_price_matrices("20230101")
    R = np.asarray(RET, float)
    Rfill = np.where(np.isfinite(R), R, 0.0)
    LOG = np.log1p(np.clip(Rfill, -0.99, None))
    CUM = np.cumsum(LOG, axis=0)                 # CUM[i,j] = sum_{k<=i} log(1+r)
    VCUM = np.cumsum(np.isfinite(R).astype(np.int32), axis=0)
    _PANEL = dict(
        R=R, MV=np.asarray(MV, float), cal=list(cal), cols=list(cols),
        CUM=CUM, VCUM=VCUM, colidx={c: i for i, c in enumerate(cols)},
    )
    return _PANEL


# ────────────────────────── event loaders ──────────────────────────
def _read_symbol(args):
    endpoint, path = args
    ts = os.path.basename(path).split("+")[0]
    datecol = FOLDERS[endpoint][1]
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception:
        return None
    if datecol not in df.columns:
        return None
    df["ts_code"] = ts
    return df


def _normalize(endpoint, raw):
    """raw (all-symbol concat, str dtypes) -> [ts_code, event_date, sign, magnitude, subtype]."""
    d = raw
    if endpoint == "forecast":
        dt = d["first_ann_date"].fillna(d["ann_date"]) if "first_ann_date" in d else d["ann_date"]
        d = d.assign(event_date=dt.astype(str))
        typ = d["type"].astype(str)
        sign = np.where(typ.isin(_FC_POS), 1.0, np.where(typ.isin(_FC_NEG), -1.0, 0.0))
        pmin = pd.to_numeric(d.get("p_change_min"), errors="coerce")
        pmax = pd.to_numeric(d.get("p_change_max"), errors="coerce")
        mag = ((pmin + pmax) / 2.0) / 100.0
        out = pd.DataFrame({"ts_code": d["ts_code"], "event_date": d["event_date"],
                            "sign": sign, "magnitude": mag.values, "subtype": typ})
        # earliest announcement per (stock, end_date) -> drop forecast revisions
        out["_ed"] = d["end_date"].astype(str).values
        out = out.sort_values("event_date").groupby(["ts_code", "_ed"], as_index=False).first()
        return out.drop(columns="_ed")
    if endpoint == "express":
        d = d.assign(event_date=d["ann_date"].astype(str))
        yoy = pd.to_numeric(d.get("yoy_net_profit"), errors="coerce")
        sign = np.sign(yoy).fillna(0.0)
        return pd.DataFrame({"ts_code": d["ts_code"], "event_date": d["event_date"],
                             "sign": sign.values, "magnitude": (yoy / 100.0).values,
                             "subtype": "express"})
    if endpoint == "dividend":
        d = d[d["div_proc"].astype(str).isin(["预案", "董事会预案"])].copy()  # first proposal = the news
        d = d.assign(event_date=d["ann_date"].astype(str))
        # cash_div (post-tax) is 0 at the 预案 stage; the announced dividend is in
        # cash_div_tax (pre-tax). Use it for both sign and magnitude.
        cash = pd.to_numeric(d.get("cash_div_tax"), errors="coerce").fillna(0.0)
        stk = pd.to_numeric(d.get("stk_div"), errors="coerce").fillna(0.0)
        sign = np.where((cash > 0) | (stk > 0), 1.0, 0.0)
        return pd.DataFrame({"ts_code": d["ts_code"], "event_date": d["event_date"],
                             "sign": sign, "magnitude": cash.values, "subtype": d["div_proc"].astype(str)})
    if endpoint == "report_rc":
        d = d.assign(event_date=d["report_date"].astype(str))
        tier = d["rating"].astype(str).map(_RATING_TIER).fillna(0.0)
        d = d.assign(tier=tier)
        # collapse same-day multi-broker reports into one stock-day event (mean tier)
        g = d.groupby(["ts_code", "event_date"], as_index=False).agg(
            tier=("tier", "mean"), rating=("rating", "first"))
        sign = np.where(g["tier"] >= 1, 1.0, np.where(g["tier"] <= -1, -1.0, 0.0))
        return pd.DataFrame({"ts_code": g["ts_code"], "event_date": g["event_date"],
                             "sign": sign, "magnitude": g["tier"].values,
                             "subtype": g["rating"].astype(str)})
    if endpoint == "stk_holdertrade":
        d = d.assign(event_date=d["ann_date"].astype(str))
        s = np.where(d["in_de"].astype(str) == "IN", 1.0,
                     np.where(d["in_de"].astype(str) == "DE", -1.0, 0.0))
        ratio = pd.to_numeric(d.get("change_ratio"), errors="coerce").fillna(0.0)
        d = d.assign(signed=s * ratio.values)
        # net across all holders disclosed that stock-day
        g = d.groupby(["ts_code", "event_date"], as_index=False).agg(net=("signed", "sum"))
        sign = np.sign(g["net"]).astype(float)
        return pd.DataFrame({"ts_code": g["ts_code"], "event_date": g["event_date"],
                             "sign": sign.values, "magnitude": g["net"].abs().values,
                             "subtype": "holdertrade"})
    raise ValueError(endpoint)


def load_events(endpoint, rebuild=False):
    """Normalized events restricted to the price-panel universe + window. Cached."""
    pkl = os.path.join(CACHE, f"events_{endpoint}.pkl")
    if os.path.exists(pkl) and not rebuild:
        return pd.read_pickle(pkl)
    cols = set(panel()["cols"])
    folder = os.path.join(DC, FOLDERS[endpoint][0])
    files = [p for p in glob.glob(os.path.join(folder, "*.csv"))
             if os.path.basename(p).split("+")[0] in cols]
    parts = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(_read_symbol, [(endpoint, p) for p in files]):
            if r is not None:
                parts.append(r)
    raw = pd.concat(parts, ignore_index=True)
    ev = _normalize(endpoint, raw)
    ev = ev.dropna(subset=["event_date"])
    ev = ev[(ev["event_date"] >= WIN_LO) & (ev["event_date"] <= WIN_HI)]
    ev = ev[ev["ts_code"].isin(cols)].reset_index(drop=True)
    os.makedirs(CACHE, exist_ok=True)
    ev.to_pickle(pkl)
    return ev


# ────────────────────────── alignment + abnormal returns ──────────────────────────
def attach_alignment(ev):
    P = panel()
    cal, colidx = P["cal"], P["colidx"]
    e = np.array([bisect.bisect_right(cal, d) - 1 for d in ev["event_date"]])
    j = np.array([colidx.get(t, -1) for t in ev["ts_code"]])
    out = ev.copy()
    out["e"] = e
    out["j"] = j
    return out[(out["e"] >= 0) & (out["j"] >= 0)].reset_index(drop=True)


_XS = {}


def _xsec(e, h):
    """Cross-section of forward-h returns on entry day e: (fwd, mkt_mean, decile_mean, valid)."""
    key = (e, h)
    if key in _XS:
        return _XS[key]
    P = panel()
    CUM, VCUM, MV = P["CUM"], P["VCUM"], P["MV"]
    n = CUM.shape[0]
    if e < 0 or e + h >= n:
        _XS[key] = None
        return None
    fwd = np.exp(CUM[e + h] - CUM[e]) - 1.0
    vdays = VCUM[e + h] - VCUM[e]
    valid = (vdays >= max(1, int(0.6 * h))) & np.isfinite(MV[e])
    f = np.where(valid, fwd, np.nan)
    mkt = np.nanmean(f)
    mv = np.where(valid, MV[e], np.nan)
    decmean = np.full(len(mv), mkt)
    order = [i for i in np.argsort(np.where(np.isfinite(mv), mv, np.inf)) if np.isfinite(mv[i])]
    m = len(order)
    if m >= 50:
        for dd in range(10):
            ids = order[int(dd * m / 10):int((dd + 1) * m / 10)]
            if ids:
                dm = np.nanmean(f[ids])
                decmean[ids] = dm
    _XS[key] = (f, mkt, decmean, valid)
    return _XS[key]


def abnormal_series(ev, h, method="size"):
    """Abnormal forward-h return per event (NaN if unpriceable). ev must have e,j."""
    out = np.full(len(ev), np.nan)
    for e, grp in ev.groupby("e"):
        xs = _xsec(int(e), h)
        if xs is None:
            continue
        f, mkt, decmean, valid = xs
        for idx, j in zip(grp.index, grp["j"].values):
            if 0 <= j < len(valid) and valid[j]:
                out[idx] = f[j] - (decmean[j] if method == "size" else mkt)
    return out


# ────────────────────────── statistics ──────────────────────────
def _boot_ci(x, n=2000, seed=0):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 10:
        return (np.nan, np.nan, np.nan, len(x))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    bs = x[idx].mean(axis=1)
    return (float(x.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)), len(x))


def _tstat(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return np.nan
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def event_study(ev, horizons=(1, 3, 5, 10), by="sign", method="size"):
    """Mean abnormal CAR per bucket per horizon, with bootstrap CI + t-stat.
    Returns a tidy DataFrame. ev must already have alignment (e,j)."""
    rows = []
    for h in horizons:
        abn = abnormal_series(ev, h, method=method)
        e2 = ev.assign(abn=abn)
        for bucket, grp in e2.groupby(by):
            mean, lo, hi, n = _boot_ci(grp["abn"].values)
            rows.append({"horizon": h, "bucket": bucket, "n": n,
                         "mean_abn": mean, "ci_lo": lo, "ci_hi": hi,
                         "t": _tstat(grp["abn"].values),
                         "sig": bool(np.isfinite(lo) and (lo > 0 or hi < 0))})
    return pd.DataFrame(rows)


# ────────────────────────── walk-forward + portfolio ──────────────────────────
def walk_forward_folds(ev):
    def fold(d):
        return f"{d[:4]}{'H1' if d[4:6] <= '06' else 'H2'}"
    out = ev.copy()
    out["fold"] = [fold(d) for d in out["event_date"]]
    return out


def portfolio_pnl(ev, h=5, method="size", cost_bps=25, long_short=False):
    """Per-fold mean abnormal return of the signed strategy, net of round-trip cost.
    Long = positive-sign events; if long_short, also short negative-sign events.
    'win' = net > 0 in that fold. Returns (per_fold_df, summary_dict)."""
    ev = walk_forward_folds(ev)
    abn = abnormal_series(ev, h, method=method)
    e2 = ev.assign(abn=abn).dropna(subset=["abn"])
    cost = cost_bps / 1e4
    rows = []
    for fold, g in e2.groupby("fold"):
        longs = g[g["sign"] > 0]["abn"]
        shorts = g[g["sign"] < 0]["abn"]
        if long_short:
            legs = pd.concat([longs, -shorts])
            net = legs.mean() - cost if len(legs) else np.nan
            nlong, nshort = len(longs), len(shorts)
        else:
            net = longs.mean() - cost if len(longs) else np.nan
            nlong, nshort = len(longs), 0
        rows.append({"fold": fold, "n_long": nlong, "n_short": nshort,
                     "gross": (legs.mean() if long_short and len(legs) else
                               (longs.mean() if len(longs) else np.nan)),
                     "net": net, "win": bool(np.isfinite(net) and net > 0)})
    pf = pd.DataFrame(rows).sort_values("fold").reset_index(drop=True)
    wins = int(pf["win"].sum())
    nf = int(pf["net"].notna().sum())
    summary = {"folds": nf, "wins": wins, "win_rate": wins / nf if nf else np.nan,
               "mean_net": float(pf["net"].mean()), "cost_bps": cost_bps,
               "h": h, "method": method, "long_short": long_short}
    return pf, summary


# ────────────────────────── pre-registered KILL checks ──────────────────────────
def kill1_monotonic_significant(study, horizon=5):
    """KILL #1: at the given horizon, +sign bucket mean>0 & −sign bucket mean<0,
    and both buckets' CI exclude 0 (significant top-vs-bottom spread)."""
    s = study[study["horizon"] == horizon].set_index("bucket")
    try:
        pos, neg = s.loc[1.0], s.loc[-1.0]
    except KeyError:
        return {"pass": False, "reason": "missing +/- bucket at h=5"}
    ok = (pos["mean_abn"] > 0 and neg["mean_abn"] < 0 and pos["sig"] and neg["sig"])
    return {"pass": bool(ok), "horizon": horizon, "pos_mean": pos["mean_abn"], "neg_mean": neg["mean_abn"],
            "pos_sig": bool(pos["sig"]), "neg_sig": bool(neg["sig"]),
            "spread": pos["mean_abn"] - neg["mean_abn"]}


def kill2_oos_sign(ev, h=5, method="size"):
    """KILL #2: out-of-sample sign-accuracy > 50% with 95% binomial CI lower
    bound also > 50%. Rule (no fitting): predict sign(event.sign)."""
    ev = walk_forward_folds(ev)
    abn = abnormal_series(ev, h, method=method)
    e2 = ev.assign(abn=abn).dropna(subset=["abn"])
    e2 = e2[e2["sign"] != 0]
    hit = (np.sign(e2["abn"]) == np.sign(e2["sign"])).astype(int)
    n, k = len(hit), int(hit.sum())
    if n < 30:
        return {"pass": False, "reason": "n<30", "n": n}
    p = k / n
    se = np.sqrt(p * (1 - p) / n)
    lo = p - 1.96 * se
    per_fold = e2.assign(hit=hit).groupby("fold")["hit"].mean().to_dict()
    return {"pass": bool(lo > 0.5), "acc": p, "ci_lo": lo, "n": n,
            "per_fold": {k2: round(v, 3) for k2, v in per_fold.items()}}


def kill3_portfolio_majority(ev, h=5, method="size", cost_bps=25, long_short=False):
    """KILL #3: net-of-cost strategy wins in a MAJORITY of non-overlapping folds."""
    pf, summ = portfolio_pnl(ev, h=h, method=method, cost_bps=cost_bps, long_short=long_short)
    summ["pass"] = bool(summ["folds"] and summ["wins"] > summ["folds"] / 2)
    return summ, pf


# ────────────────────────── self-test ──────────────────────────
if __name__ == "__main__":
    ep = sys.argv[1] if len(sys.argv) > 1 else "forecast"
    print(f"[panel] loading price matrices…")
    P = panel()
    print(f"[panel] {P['cal'][0]}..{P['cal'][-1]}  {len(P['cal'])}d x {len(P['cols'])} stk")
    print(f"[events] building {ep} (reads USB; cached after first run)…")
    ev = attach_alignment(load_events(ep))
    print(f"[events] {len(ev)} priceable events; sign dist: "
          f"{ev['sign'].value_counts().to_dict()}")
    study = event_study(ev, by="sign")
    print("\n=== event study: mean abnormal CAR by sign (size-decile adj) ===")
    print(study.to_string(index=False))
    print("\n=== KILL #1 (monotonic+significant @h=5) ===")
    print(kill1_monotonic_significant(study))
    print("\n=== KILL #2 (OOS sign accuracy) ===")
    print(kill2_oos_sign(ev))
    print("\n=== KILL #3 (portfolio, long-only, 25bps) ===")
    summ, pf = kill3_portfolio_majority(ev)
    print(summ)
    print(pf.to_string(index=False))
    # PLACEBO: shuffle event dates -> abnormal CAR must collapse to ~0
    rng = np.random.default_rng(7)
    fake = ev.copy()
    fake["event_date"] = rng.permutation(P["cal"])[: len(fake)] if len(fake) <= len(P["cal"]) \
        else [P["cal"][i] for i in rng.integers(0, len(P["cal"]), len(fake))]
    fake = attach_alignment(fake.drop(columns=["e", "j"]))
    ps = event_study(fake, horizons=(5,), by="sign")
    print("\n=== PLACEBO (random dates, same signs) — expect ~0, non-sig ===")
    print(ps.to_string(index=False))
