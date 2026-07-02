#!/usr/bin/env python3
"""A2: rescue report_rc via rating-CHANGE / target-price-revision; confirm-or-overturn
dividend and stk_holdertrade.

READ-ONLY on mvp20/ and DockCase (DOCKCASE_WRITEBACK=0). Run from REPO ROOT:
  DOCKCASE_WRITEBACK=0 DOCKCASE_CACHE=1 \
    factor_research/.venv_research/bin/python factor_research/04_event_study/run_A2_other.py

Writes nothing except optional artifacts under factor_research/04_event_study/.
All custom event DataFrames go through eventlib.attach_alignment -> event_study so the
PIT contract (entry = close of last trading day <= event_date; forward = e+1..e+h) and
the placebo-validated abnormal-return machinery are reused verbatim.
"""
from __future__ import annotations

import glob
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eventlib as E  # noqa: E402

pd.set_option("display.width", 230)
pd.set_option("display.max_columns", 60)
pd.set_option("display.max_rows", 200)

# Extend the tier map with the English / variant labels seen in the raw data so that
# rating CHANGES are real sentiment moves, not encoding artefacts (e.g. 买入 -> BUY).
TIER = dict(E._RATING_TIER)
TIER.update({
    "BUY": 2, "Buy": 2, "买进": 2, "强力买入": 2, "强烈买入": 2,
    "OVERWEIGHT": 1, "Overweight": 1, "增持": 1, "审慎增持": 1, "谨慎增持": 1,
    "OUTPERFORM": 1, "Outperform": 1, "强于大市": 1, "强推": 2, "审慎推荐": 1,
    "Neutral": 0, "NEUTRAL": 0, "HOLD": 0, "Hold": 0, "持有": 0, "观望": 0,
    "Equal weight": 0, "Equal Weight": 0, "Equalweight": 0,
    "Sell": -2, "SELL": -2, "Underweight": -1, "Underperform": -1, "Reduce": -1,
})

H_LIST = (1, 3, 5, 10)
SEP = "=" * 96


def banner(s):
    print("\n" + SEP + "\n" + s + "\n" + SEP)


def study_and_kills(ev, label, by="sign", horizons=H_LIST, h_pick=1,
                    long_short=True, also_h=3):
    """Run event_study + the 3 pre-registered kills on a signed event DF. h_pick is the
    a-priori announcement-reaction horizon (h=1); also report also_h (h=3)."""
    ev = ev.copy()
    if "e" not in ev.columns:
        ev = E.attach_alignment(ev)
    else:
        # already aligned upstream; ensure a contiguous 0..n-1 index because
        # eventlib.abnormal_series writes out[idx] positionally (a sliced frame
        # would carry stale labels and IndexError).
        ev = ev.reset_index(drop=True)
    print(f"\n--- {label}: {len(ev)} priceable events; "
          f"sign dist {ev['sign'].value_counts().to_dict()} ---")
    if len(ev) < 30:
        print("   (too few events; skipping)")
        return None
    st = E.event_study(ev, horizons=horizons, by=by)
    print(st.to_string(index=False))
    out = {"label": label, "n": len(ev), "study": st}
    for h in sorted(set([h_pick, also_h])):
        k1 = E.kill1_monotonic_significant(st, horizon=h)
        k2 = E.kill2_oos_sign(ev, h=h)
        # long-only and long-short portfolio at 25bps (+ 15/40 sensitivity at h_pick)
        k3_lo, _ = E.kill3_portfolio_majority(ev, h=h, cost_bps=25, long_short=False)
        k3_ls, pf_ls = E.kill3_portfolio_majority(ev, h=h, cost_bps=25, long_short=long_short)
        print(f"\n  [h={h}] KILL1 monotonic+sig: pass={k1.get('pass')} "
              f"pos={k1.get('pos_mean')} neg={k1.get('neg_mean')} spread={k1.get('spread')}")
        print(f"  [h={h}] KILL2 OOS sign-acc: pass={k2.get('pass')} acc={k2.get('acc')} "
              f"ci_lo={k2.get('ci_lo')} n={k2.get('n')}")
        print(f"  [h={h}] KILL3 long-only 25bps: pass={k3_lo['pass']} "
              f"wins={k3_lo['wins']}/{k3_lo['folds']} mean_net={k3_lo['mean_net']:.5f}")
        print(f"  [h={h}] KILL3 long-short 25bps: pass={k3_ls['pass']} "
              f"wins={k3_ls['wins']}/{k3_ls['folds']} mean_net={k3_ls['mean_net']:.5f}")
        if h == h_pick:
            print(pf_ls.to_string(index=False))
            for cb in (15, 40):
                s_lo, _ = E.kill3_portfolio_majority(ev, h=h, cost_bps=cb, long_short=False)
                s_ls, _ = E.kill3_portfolio_majority(ev, h=h, cost_bps=cb, long_short=long_short)
                print(f"    cost={cb}bps  long-only {s_lo['wins']}/{s_lo['folds']} "
                      f"(net {s_lo['mean_net']:.5f}) | long-short {s_ls['wins']}/{s_ls['folds']} "
                      f"(net {s_ls['mean_net']:.5f})")
            out[f"k1_h{h}"], out[f"k2_h{h}"] = k1, k2
            out[f"k3lo_h{h}"], out[f"k3ls_h{h}"] = k3_lo, k3_ls
    return out


# ───────────────────────── raw readers (custom, read-only) ─────────────────────────
def _read_raw(endpoint):
    """Concat all by_symbol CSVs (str dtype) restricted to the price-panel universe +
    event window. Mirrors eventlib.load_events but keeps ALL raw columns."""
    cols = set(E.panel()["cols"])
    folder = os.path.join(E.DC, E.FOLDERS[endpoint][0])
    datecol = E.FOLDERS[endpoint][1]
    files = [p for p in glob.glob(os.path.join(folder, "*.csv"))
             if os.path.basename(p).split("+")[0] in cols]

    def rd(p):
        ts = os.path.basename(p).split("+")[0]
        try:
            df = pd.read_csv(p, dtype=str)
        except Exception:
            return None
        if datecol not in df.columns:
            return None
        df["ts_code"] = ts
        return df

    parts = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(rd, files):
            if r is not None:
                parts.append(r)
    raw = pd.concat(parts, ignore_index=True)
    raw = raw[(raw[datecol] >= E.WIN_LO) & (raw[datecol] <= E.WIN_HI)]
    return raw.reset_index(drop=True)


# close price lookup (for dividend yield & target-price upside) -----------------
_CLOSE = None


def close_panel():
    """ndarray CLOSE[i,j] aligned to panel cal/cols (NaN where missing)."""
    global _CLOSE
    if _CLOSE is not None:
        return _CLOSE
    P = E.panel()
    cal, colidx = P["cal"], P["colidx"]
    calidx = {d: i for i, d in enumerate(cal)}
    CLOSE = np.full((len(cal), len(P["cols"])), np.nan)
    folder = os.path.join(E.DC, "行情数据/历史日线/by_symbol")
    files = [p for p in glob.glob(os.path.join(folder, "*.csv"))
             if os.path.basename(p).split("+")[0] in colidx]

    def rd(p):
        ts = os.path.basename(p).split("+")[0]
        try:
            df = pd.read_csv(p, usecols=["trade_date", "close"], dtype=str)
        except Exception:
            return None
        return ts, df

    with ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(rd, files):
            if res is None:
                continue
            ts, df = res
            j = colidx[ts]
            td = df["trade_date"].values
            cl = pd.to_numeric(df["close"], errors="coerce").values
            for d, c in zip(td, cl):
                i = calidx.get(d)
                if i is not None and np.isfinite(c):
                    CLOSE[i, j] = c
    _CLOSE = CLOSE
    return _CLOSE


def close_on_or_before(ts_code, event_date):
    """Close of the last trading day <= event_date for ts_code (entry-day price)."""
    import bisect
    P = E.panel()
    j = P["colidx"].get(ts_code)
    if j is None:
        return np.nan
    e = bisect.bisect_right(P["cal"], event_date) - 1
    CL = close_panel()
    while e >= 0:
        if np.isfinite(CL[e, j]):
            return CL[e, j]
        e -= 1
    return np.nan


# ══════════════════════════════ TASK 1: report_rc RESCUE ══════════════════════════════
def task_report_rc():
    banner("TASK 1 — report_rc RESCUE: rating CHANGES & target-price revisions")
    raw = _read_raw("report_rc")
    raw = raw.assign(
        tier=raw["rating"].astype(str).map(TIER),
        tp=pd.to_numeric(raw["tp"], errors="coerce"),
        rd=raw["report_date"].astype(str),
        org=raw["org_name"].astype(str),
    )
    print(f"raw in-window rows: {len(raw)}; tier-mapped frac: {raw['tier'].notna().mean():.3f}")

    # ---------- (A) per-ORG rating change: compare each report's tier to the SAME org's
    # previous report on that stock. UPGRADE tier increases, DOWNGRADE tier decreases.
    r = raw.dropna(subset=["tier"]).sort_values(["ts_code", "org", "rd"]).copy()
    r["prev_tier"] = r.groupby(["ts_code", "org"])["tier"].shift(1)
    r["prev_rd"] = r.groupby(["ts_code", "org"])["rd"].shift(1)
    r["dtier"] = r["tier"] - r["prev_tier"]
    chg = r.dropna(subset=["prev_tier"])
    # gap in calendar days between consecutive same-org reports (stale-rating guard)
    gap = (pd.to_datetime(chg["rd"]) - pd.to_datetime(chg["prev_rd"])).dt.days
    chg = chg.assign(gap=gap.values)
    print(f"\nper-org consecutive report pairs: {len(chg)}  "
          f"(median gap {np.median(chg['gap']):.0f}d)")
    print("dtier distribution:", chg["dtier"].value_counts().sort_index().to_dict())

    # Collapse to one event per (stock, report_date): net tier change across orgs that day,
    # to avoid double-counting and to mirror the level-study's same-day collapse.
    def build_change_ev(df, label, max_gap=None):
        d = df
        if max_gap is not None:
            d = d[d["gap"] <= max_gap]
        g = d.groupby(["ts_code", "rd"], as_index=False).agg(
            net_dtier=("dtier", "sum"), n_org=("dtier", "size"),
            subtype=("rating", "first"))
        g = g[g["net_dtier"] != 0]
        sign = np.sign(g["net_dtier"]).astype(float)
        ev = pd.DataFrame({"ts_code": g["ts_code"], "event_date": g["rd"],
                           "sign": sign.values, "magnitude": g["net_dtier"].abs().values,
                           "subtype": label})
        return ev

    ev_chg = build_change_ev(chg, "rc_change_all")
    study_and_kills(ev_chg, "report_rc CHANGES (per-org net, any gap)", h_pick=1)

    ev_chg_fresh = build_change_ev(chg, "rc_change_90d", max_gap=90)
    study_and_kills(ev_chg_fresh, "report_rc CHANGES (per-org net, <=90d gap)", h_pick=1)

    # ---------- (B) DOWNGRADE-only vs UPGRADE-only as separate one-sided event sets,
    # so a downgrade's negative reaction is not diluted by same-day upgrades.
    up = chg[chg["dtier"] > 0]
    dn = chg[chg["dtier"] < 0]
    for name, sub, sgn in [("UPGRADE-only", up, 1.0), ("DOWNGRADE-only", dn, -1.0)]:
        g = sub.groupby(["ts_code", "rd"], as_index=False).agg(mag=("dtier", "sum"))
        ev = pd.DataFrame({"ts_code": g["ts_code"], "event_date": g["rd"],
                           "sign": sgn, "magnitude": g["mag"].abs().values,
                           "subtype": name})
        ev = E.attach_alignment(ev)
        print(f"\n--- report_rc {name}: {len(ev)} priceable events ---")
        if len(ev) >= 30:
            st = E.event_study(ev, horizons=H_LIST, by="subtype")
            print(st.to_string(index=False))

    # ---------- (C) initiation INTO buy from below (tier crosses 0 -> >=1 upgrade), and
    # crossing down into sell/reduce (tier -> <=-1). The sharpest directional changes.
    cross_up = chg[(chg["prev_tier"] <= 0) & (chg["tier"] >= 1)]
    cross_dn = chg[(chg["prev_tier"] >= 1) & (chg["tier"] <= 0)]
    parts = []
    for sub, sgn, lab in [(cross_up, 1.0, "cross_up"), (cross_dn, -1.0, "cross_dn")]:
        g = sub.groupby(["ts_code", "rd"], as_index=False).size()
        parts.append(pd.DataFrame({"ts_code": g["ts_code"], "event_date": g["rd"],
                                   "sign": sgn, "magnitude": 1.0, "subtype": lab}))
    ev_cross = pd.concat(parts, ignore_index=True)
    # if a stock-day appears in both, drop it (ambiguous)
    ev_cross = ev_cross.drop_duplicates(subset=["ts_code", "event_date"], keep=False)
    study_and_kills(ev_cross, "report_rc CROSS (tier crosses neutral line)", h_pick=1)

    # ---------- (D) ESTIMATE revision vs the SAME org's previous report on that stock.
    # NB: the `tp` column is NOT a per-share target price (median tp/max_price ratio ~6500x;
    # it is a target net-profit / aggregate figure). But the RATIO tp_t / tp_{t-1} from the
    # SAME org on the SAME stock is scale-invariant, so it is a valid broker
    # earnings-ESTIMATE revision proxy. Per-share target price lives in min_price/max_price
    # (used in section E). Treat this as estimate-revision, not literal target-price-revision.
    rtp = raw.dropna(subset=["tp"])
    rtp = rtp[rtp["tp"] > 0].sort_values(["ts_code", "org", "rd"]).copy()
    rtp["prev_tp"] = rtp.groupby(["ts_code", "org"])["tp"].shift(1)
    rtp["prev_rd"] = rtp.groupby(["ts_code", "org"])["rd"].shift(1)
    rtp = rtp.dropna(subset=["prev_tp"])
    rtp = rtp[rtp["prev_tp"] > 0]
    rtp["tp_rev"] = rtp["tp"] / rtp["prev_tp"] - 1.0
    rtp = rtp[np.abs(rtp["tp_rev"]) < 1.0]  # drop >100% jumps (splits / data glitches)
    print(f"\nper-org ESTIMATE(tp) revisions: {len(rtp)}  "
          f"(median |rev| {np.median(np.abs(rtp['tp_rev'])):.3f})")
    g = rtp.groupby(["ts_code", "rd"], as_index=False).agg(rev=("tp_rev", "mean"))
    # require a material revision (>2%) to be an "event"
    gm = g[np.abs(g["rev"]) >= 0.02]
    ev_tp = pd.DataFrame({"ts_code": gm["ts_code"], "event_date": gm["rd"],
                          "sign": np.sign(gm["rev"]).astype(float),
                          "magnitude": gm["rev"].abs().values, "subtype": "est_rev"})
    study_and_kills(ev_tp, "report_rc ESTIMATE-REVISION (>=2% vs same org prev)", h_pick=1)
    # magnitude buckets on estimate revision (does a big cut hurt?)
    ev_tp2 = E.attach_alignment(ev_tp)
    if len(ev_tp2) >= 60:
        q = pd.qcut(ev_tp2["magnitude"] * ev_tp2["sign"], 5, labels=False, duplicates="drop")
        ev_tp2 = ev_tp2.assign(qbkt=q)
        st = E.event_study(ev_tp2, horizons=(1, 3, 5), by="qbkt")
        print("\nEstimate-revision signed-magnitude quintiles (0=biggest cut .. 4=biggest raise):")
        print(st.to_string(index=False))

    # ---------- (E) target-price UPSIDE buckets: per-share target / close - 1 at announcement.
    # Use min_price (29% coverage) / max_price (0.4%) which ARE per-share target prices.
    for tpcol in ["min_price", "max_price"]:
        raw[tpcol] = pd.to_numeric(raw[tpcol], errors="coerce")
    rtp_all = raw.dropna(subset=["min_price"]).copy()
    rtp_all = rtp_all[rtp_all["min_price"] > 0]
    # one report per stock-day: median per-share target that day
    gd = rtp_all.groupby(["ts_code", "rd"], as_index=False).agg(tp=("min_price", "median"))
    cl = np.array([close_on_or_before(t, d) for t, d in zip(gd["ts_code"], gd["rd"])])
    gd = gd.assign(close=cl)
    gd = gd[np.isfinite(gd["close"]) & (gd["close"] > 0)]
    gd["upside"] = gd["tp"] / gd["close"] - 1.0
    gd = gd[(gd["upside"] > -0.5) & (gd["upside"] < 3.0)]
    print(f"\nper-share-target UPSIDE events (min_price): {len(gd)}  "
          f"median upside {np.median(gd['upside']):.3f}")
    ev_up = pd.DataFrame({"ts_code": gd["ts_code"], "event_date": gd["rd"],
                          "sign": 1.0, "magnitude": gd["upside"].values, "subtype": "upside"})
    ev_up = E.attach_alignment(ev_up)
    if len(ev_up) >= 100:
        q = pd.qcut(ev_up["magnitude"], 5, labels=False, duplicates="drop")
        ev_up = ev_up.assign(qbkt=q)
        st = E.event_study(ev_up, horizons=(1, 3, 5, 10), by="qbkt")
        print("\nTP-UPSIDE quintiles (0=lowest upside .. 4=highest upside) CAR:")
        print(st.to_string(index=False))
        # long-short top-vs-bottom upside quintile portfolio
        topq, botq = ev_up["qbkt"].max(), ev_up["qbkt"].min()
        ls = ev_up[ev_up["qbkt"].isin([topq, botq])].reset_index(drop=True).copy()
        ls["sign"] = np.where(ls["qbkt"] == topq, 1.0, -1.0)
        for h in (1, 3, 5, 10):
            s, _ = E.kill3_portfolio_majority(ls, h=h, cost_bps=25, long_short=True)
            print(f"  upside Q5-Q1 L/S h={h} 25bps: wins {s['wins']}/{s['folds']} "
                  f"net {s['mean_net']:.5f} pass={s['pass']}")
        # Q5 upside LONG-ONLY portfolio (the cleanest tradeable form of the one
        # significant CAR signal in report_rc) — does it survive cost on its own?
        q5 = ev_up[ev_up["qbkt"] == topq].reset_index(drop=True).copy()
        q5["sign"] = 1.0
        print(f"  [Q5 upside long-only n={len(q5)}]")
        for h in (1, 3, 5, 10):
            for cb in (25, 40):
                s, pf = E.kill3_portfolio_majority(q5, h=h, cost_bps=cb, long_short=False)
                tag = "  -> per-fold:" if (h == 3 and cb == 25) else ""
                print(f"    Q5-long h={h} {cb}bps: wins {s['wins']}/{s['folds']} "
                      f"net {s['mean_net']:.5f} pass={s['pass']}{tag}")
                if h == 3 and cb == 25:
                    print(pf[["fold", "n_long", "gross", "net", "win"]].to_string(index=False))


# ══════════════════════════════ TASK 2: dividend ══════════════════════════════
def task_dividend():
    banner("TASK 2 — dividend: yield buckets & 高送转 (confirm-or-overturn)")
    raw = _read_raw("dividend")
    d = raw[raw["div_proc"].astype(str).isin(["预案", "董事会预案"])].copy()
    d["event_date"] = d["ann_date"].astype(str)
    d["cash"] = pd.to_numeric(d["cash_div_tax"], errors="coerce").fillna(0.0)
    d["stk"] = pd.to_numeric(d["stk_div"], errors="coerce").fillna(0.0)
    # collapse to one proposal per stock-day (sum cash, max stk)
    g = d.groupby(["ts_code", "event_date"], as_index=False).agg(
        cash=("cash", "sum"), stk=("stk", "max"))
    cl = np.array([close_on_or_before(t, dt) for t, dt in zip(g["ts_code"], g["event_date"])])
    g = g.assign(close=cl)
    g = g[np.isfinite(g["close"]) & (g["close"] > 0)]
    g["yield"] = g["cash"] / g["close"]            # cash_div_tax per share / price
    g = g[(g["yield"] >= 0) & (g["yield"] < 0.5)]
    print(f"dividend proposals priced: {len(g)}; with cash>0: {(g['cash']>0).sum()}; "
          f"with stk>0: {(g['stk']>0).sum()}")
    print(f"median yield among cash>0: {np.median(g['yield'][g['cash']>0]):.4f}")

    # ---------- yield quintiles among cash-dividend proposals; do high-yield beat low?
    gy = g[g["cash"] > 0].copy()
    ev = pd.DataFrame({"ts_code": gy["ts_code"], "event_date": gy["event_date"],
                       "sign": 1.0, "magnitude": gy["yield"].values, "subtype": "div"})
    ev = E.attach_alignment(ev)
    q = pd.qcut(ev["magnitude"], 5, labels=False, duplicates="drop")
    ev = ev.assign(qbkt=q)
    st = E.event_study(ev, horizons=H_LIST, by="qbkt")
    print("\nDividend YIELD quintiles (0=lowest yield .. 4=highest) CAR:")
    print(st.to_string(index=False))
    # high-yield (Q4) vs zero-dividend control as a signed long-short
    g0 = g[g["cash"] == 0]
    topq = ev["magnitude"].quantile(0.8)
    hi = gy[gy["yield"] >= topq]
    ls = pd.concat([
        pd.DataFrame({"ts_code": hi["ts_code"], "event_date": hi["event_date"],
                      "sign": 1.0, "magnitude": hi["yield"].values, "subtype": "hiyield"}),
        pd.DataFrame({"ts_code": g0["ts_code"], "event_date": g0["event_date"],
                      "sign": -1.0, "magnitude": 0.0, "subtype": "nodiv"}),
    ], ignore_index=True)
    study_and_kills(ls, "dividend HIGH-YIELD(Q5) long vs NO-DIV short", h_pick=3, also_h=1)

    # also: high-yield quintile as a standalone long (vs market/size baseline already in abn)
    hi_only = pd.DataFrame({"ts_code": hi["ts_code"], "event_date": hi["event_date"],
                            "sign": 1.0, "magnitude": hi["yield"].values, "subtype": "hiyield"})
    study_and_kills(hi_only, "dividend HIGH-YIELD(Q5) long-only", h_pick=3, also_h=5,
                    long_short=False)

    # ---------- 高送转: large stock dividend (stk_div >= 0.5, i.e. >=5 送/转 per 10).
    gz = g[g["stk"] >= 0.5].copy()
    ev_z = pd.DataFrame({"ts_code": gz["ts_code"], "event_date": gz["event_date"],
                         "sign": 1.0, "magnitude": gz["stk"].values, "subtype": "gaosongzhuan"})
    study_and_kills(ev_z, "dividend 高送转 (stk_div>=0.5) long-only", h_pick=1, also_h=3,
                    long_short=False)
    # bigger threshold
    gz2 = g[g["stk"] >= 1.0].copy()
    ev_z2 = pd.DataFrame({"ts_code": gz2["ts_code"], "event_date": gz2["event_date"],
                          "sign": 1.0, "magnitude": gz2["stk"].values, "subtype": "gsz10"})
    study_and_kills(ev_z2, "dividend 高送转 (stk_div>=1.0, >=10转) long-only",
                    h_pick=1, also_h=3, long_short=False)


# ══════════════════════════════ TASK 3: stk_holdertrade ══════════════════════════════
def task_holdertrade():
    banner("TASK 3 — stk_holdertrade: IN magnitude buckets, holder_type, large-ratio, longer h")
    raw = _read_raw("stk_holdertrade")
    d = raw.copy()
    d["event_date"] = d["ann_date"].astype(str)
    d["in_de"] = d["in_de"].astype(str)
    d["ratio"] = pd.to_numeric(d["change_ratio"], errors="coerce").fillna(0.0)
    d["htype"] = d["holder_type"].astype(str)
    s = np.where(d["in_de"] == "IN", 1.0, np.where(d["in_de"] == "DE", -1.0, 0.0))
    d = d.assign(signed=s * d["ratio"].values)

    # net across all holders that stock-day (same as level study)
    g = d.groupby(["ts_code", "event_date"], as_index=False).agg(
        net=("signed", "sum"), gross_in=("signed", lambda x: x[x > 0].sum()),
        gross_de=("signed", lambda x: -x[x < 0].sum()))
    P = E.panel()

    # ---------- IN-only by change_ratio magnitude buckets (does a BIG buy predict?)
    gin = g[g["gross_in"] > 0].copy()
    ev_in = pd.DataFrame({"ts_code": gin["ts_code"], "event_date": gin["event_date"],
                          "sign": 1.0, "magnitude": gin["gross_in"].values, "subtype": "in"})
    ev_in = E.attach_alignment(ev_in)
    q = pd.qcut(ev_in["magnitude"], 5, labels=False, duplicates="drop")
    ev_in = ev_in.assign(qbkt=q)
    st = E.event_study(ev_in, horizons=(1, 3, 5, 10, 20), by="qbkt")
    print("\nINCREASE(IN) change_ratio quintiles (0=smallest .. 4=largest) CAR:")
    print(st.to_string(index=False))

    # large-IN only (top quintile by ratio) as long-only, h=1/3/5/10/20
    thr = ev_in["magnitude"].quantile(0.8)
    big_in = ev_in[ev_in["magnitude"] >= thr].copy()
    big_in["sign"] = 1.0
    study_and_kills(big_in.drop(columns=["qbkt"]), "holdertrade BIG-IN (top-quintile ratio) long-only",
                    horizons=(1, 3, 5, 10, 20), h_pick=1, also_h=5, long_short=False)

    # ---------- DE-only by magnitude (does a BIG sell predict NEGATIVE?)
    gde = g[g["gross_de"] > 0].copy()
    ev_de = pd.DataFrame({"ts_code": gde["ts_code"], "event_date": gde["event_date"],
                          "sign": -1.0, "magnitude": gde["gross_de"].values, "subtype": "de"})
    ev_de = E.attach_alignment(ev_de)
    qd = pd.qcut(ev_de["magnitude"], 5, labels=False, duplicates="drop")
    ev_de = ev_de.assign(qbkt=qd)
    st = E.event_study(ev_de, horizons=(1, 3, 5, 10, 20), by="qbkt")
    print("\nDECREASE(DE) change_ratio quintiles (0=smallest .. 4=largest) CAR (sign=-1):")
    print(st.to_string(index=False))
    thr_d = ev_de["magnitude"].quantile(0.8)
    big_de = ev_de[ev_de["magnitude"] >= thr_d].copy()
    # DE-only is a one-sided SHORT set: long_short=True evaluates the short leg (shorting
    # the sell-disclosure). long-only would be empty (no +sign events) -> 0/0 folds.
    study_and_kills(big_de.drop(columns=["qbkt"]), "holdertrade BIG-DE (top-quintile ratio) SHORT",
                    horizons=(1, 3, 5, 10, 20), h_pick=1, also_h=5, long_short=True)

    # ---------- restrict to specific holder types (个人/高管/公司). Per-row, then re-net.
    for ht_label, ht_vals in [("个人/自然人", {"P"}), ("公司/法人", {"C", "G"})]:
        sub = d[d["htype"].isin(ht_vals)]
        gg = sub.groupby(["ts_code", "event_date"], as_index=False).agg(net=("signed", "sum"))
        gg = gg[gg["net"] != 0]
        ev = pd.DataFrame({"ts_code": gg["ts_code"], "event_date": gg["event_date"],
                           "sign": np.sign(gg["net"]).astype(float),
                           "magnitude": gg["net"].abs().values, "subtype": ht_label})
        study_and_kills(ev, f"holdertrade holder_type={ht_label} (net signed)",
                        horizons=(1, 3, 5, 10, 20), h_pick=1, also_h=5)

    # ---------- IN-only large-ratio, longer horizons standalone L/S vs DE-large
    big_in_ls = big_in.drop(columns=["qbkt"]).copy()
    big_de_ls = big_de.drop(columns=["qbkt"]).copy()
    ls = pd.concat([big_in_ls.assign(sign=1.0), big_de_ls.assign(sign=-1.0)],
                   ignore_index=True)
    ls = E.attach_alignment(ls.drop(columns=[c for c in ("e", "j") if c in ls.columns]))
    for h in (1, 3, 5, 10, 20):
        s, _ = E.kill3_portfolio_majority(ls, h=h, cost_bps=25, long_short=True)
        print(f"  BIG-IN(+)/BIG-DE(-) L/S h={h} 25bps: wins {s['wins']}/{s['folds']} "
              f"net {s['mean_net']:.5f} pass={s['pass']}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    P = E.panel()
    print(f"[panel] {P['cal'][0]}..{P['cal'][-1]} {len(P['cal'])}d x {len(P['cols'])} stk")
    if which in ("all", "rc"):
        task_report_rc()
    if which in ("all", "div"):
        task_dividend()
    if which in ("all", "ht"):
        task_holdertrade()
    print("\n[done]")
