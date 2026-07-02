#!/usr/bin/env python3
"""Analyze REAL base_score forward IC by regime + OOS regime-overlay test (ISOLATED, read-only).

Date set = 3 cached real dates (read-only from runtime/backtest/backtest.sqlite)
           + new dates recomputed into factor_research/pit_extra/realbase.sqlite.
For each date: +10/+20d forward rank-IC of REAL base_score (price matrices from
factor_research/_datalib) and regime classification (reused run_prototype.regime()).
Then a SIMPLE time-split OOS test of a regime overlay on the REAL base_score.

All scores subset to the SAME 250-stock cap-stratified sample universe for
comparability across dates (the 3 cached dates were scored on the full 1641 but
we restrict to the sample so every date uses an identical cross-section).
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import sys

import numpy as np

os.environ.setdefault("DOCKCASE_CACHE", "1")
sys.path.insert(0, os.getcwd())

from pit_backtest.metrics import rank_ic  # noqa: E402
from factor_research._datalib import load_price_matrices  # noqa: E402

ROOT = "factor_research/pit_extra"
EXTRA_DB = f"{ROOT}/realbase.sqlite"
CACHED_DB = "runtime/backtest/backtest.sqlite"
CACHED_DATES = ["20260116", "20260309", "20260421"]
HORIZONS = [10, 20]
VOLWIN, TREND = 20, 60


def read_scores(db: str, base_date: str) -> dict[str, float]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT ts_code, base_score FROM scores WHERE base_date=?", (base_date,)
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()
    return {r[0]: r[1] for r in rows if r[1] is not None}


def main():
    universe = json.loads(open(f"{ROOT}/universe_sample.json").read())
    uset = set(universe)

    RET, TO, MV, cal, cols = load_price_matrices("20230101")
    n, m = RET.shape
    LR = np.log1p(np.nan_to_num(RET, nan=0.0))
    CUM = np.cumsum(LR, axis=0)
    HAS = ~np.isnan(RET)
    first_valid = np.where(HAS.any(0), HAS.argmax(0), n + 1)
    mkt = np.nanmean(RET, axis=1)
    mkt_lr = np.log1p(np.nan_to_num(mkt, 0.0))
    mkt_cum = np.cumsum(mkt_lr)
    mvol = np.array([np.std(mkt[max(0, k - VOLWIN + 1):k + 1], ddof=1) * math.sqrt(252)
                     if k >= VOLWIN else np.nan for k in range(n)])
    col_idx = {c: i for i, c in enumerate(cols)}

    def fwd(k, h):
        if k + h >= n:
            return None
        fr = np.exp(CUM[k + h] - CUM[k]) - 1.0
        ok = HAS[k] & (first_valid <= k) & HAS[k + 1:k + h + 1].any(0)
        return np.where(ok, fr, np.nan)

    def regime(k):
        trend = math.exp(mkt_cum[k] - mkt_cum[k - TREND]) - 1.0
        vol = mvol[k]
        pv = mvol[max(0, k - 250):k]
        pv = pv[np.isfinite(pv)]
        vmed = float(np.median(pv)) if len(pv) > 20 else 0.22
        return trend, vol, vmed

    def k_of(bd):
        le = [d for d in cal if d <= bd]
        return cal.index(le[-1]) if le else None

    # ---- assemble all dates: (date, source_db) ----
    extra_dates = []
    if os.path.exists(EXTRA_DB):
        con = sqlite3.connect(f"file:{EXTRA_DB}?mode=ro", uri=True)
        try:
            extra_dates = [r[0] for r in con.execute(
                "SELECT base_date, COUNT(*) FROM scores GROUP BY base_date HAVING COUNT(*)>=100"
            ).fetchall()]
        finally:
            con.close()
    all_dates = sorted(set(CACHED_DATES) | set(extra_dates))

    # build the score vector ALIGNED to `cols` (price-matrix order), subset to sample
    def score_vec(bd):
        db = EXTRA_DB if bd in extra_dates else CACHED_DB
        sc = read_scores(db, bd)
        return np.array([sc.get(ts, np.nan) if ts in uset else np.nan for ts in cols]), len(sc)

    table = []
    for bd in all_dates:
        k = k_of(bd)
        if k is None or k < TREND + 1:
            continue
        tr, vol, vmed = regime(k)
        bs, n_scored = score_vec(bd)
        n_overlap = int(np.sum(np.isfinite(bs)))
        row = {"date": bd, "source": "extra" if bd in extra_dates else "cached",
               "k": k, "trend60": round(tr, 3), "vol20": round(float(vol), 3),
               "vmed": round(vmed, 3),
               "regime_trend": "down" if tr < 0 else "up",
               "regime_vol": "hi" if vol > vmed else "lo",
               "n_scored": n_scored, "n_overlap": n_overlap}
        for h in HORIZONS:
            fr = fwd(k, h)
            row[f"ic{h}"] = round(rank_ic(bs, fr)["ic"], 4) if fr is not None else None
            row[f"n{h}"] = rank_ic(bs, fr)["n"] if fr is not None else 0
        table.append(row)

    table.sort(key=lambda r: r["date"])

    # ---------------- OOS regime overlay test ----------------
    # Overlay hypothesis (from RESULTS4): real base_score IC flips sign with regime.
    # Rule family tested OOS: derive a per-regime SIGN map on TRAIN dates, then on
    # TEST dates apply base_score' = sign(regime) * base_score (i.e. flip the score
    # in regimes where TRAIN showed base_score IC<0). Compare IC of overlaid vs raw.
    # Low-power (few dates) — reported honestly.
    def regime_key(r):
        return f"{r['regime_trend']}/{r['regime_vol']}"

    # time-ordered split: earliest 60% train, latest 40% test (>=1 test date)
    dts = [r for r in table if r["n20"] >= 30 or r["n10"] >= 30]
    dts.sort(key=lambda r: r["date"])
    oos = {}
    if len(dts) >= 4:
        split = max(2, int(round(len(dts) * 0.6)))
        train, test = dts[:split], dts[split:]
        for h in HORIZONS:
            # TRAIN: mean IC per regime bucket; also global mean
            buckets = {}
            for r in train:
                if r.get(f"ic{h}") is None:
                    continue
                buckets.setdefault(regime_key(r), []).append(r[f"ic{h}"])
            sign_map = {kk: (1.0 if np.mean(v) >= 0 else -1.0) for kk, v in buckets.items()}
            glob_sign = 1.0  # raw model default = trust score as-is
            # TEST: compare raw IC vs overlaid IC (flip per train sign_map)
            raw_ics, ovl_ics, detail = [], [], []
            for r in test:
                if r.get(f"ic{h}") is None:
                    continue
                rk = regime_key(r)
                s = sign_map.get(rk, glob_sign)
                raw = r[f"ic{h}"]
                ovl = s * raw  # flipping the score flips the IC sign
                raw_ics.append(raw)
                ovl_ics.append(ovl)
                detail.append({"date": r["date"], "regime": rk,
                               "train_sign": s, "raw_ic": raw, "overlaid_ic": round(ovl, 4),
                               "train_seen": rk in sign_map})
            oos[f"h{h}"] = {
                "train_dates": [r["date"] for r in train],
                "test_dates": [r["date"] for r in test],
                "train_sign_map": {kk: round(float(np.mean(v)), 4) for kk, v in buckets.items()},
                "mean_raw_ic_test": round(float(np.mean(raw_ics)), 4) if raw_ics else None,
                "mean_overlaid_ic_test": round(float(np.mean(ovl_ics)), 4) if ovl_ics else None,
                "mean_abs_raw_test": round(float(np.mean(np.abs(raw_ics))), 4) if raw_ics else None,
                "delta": round(float(np.mean(ovl_ics) - np.mean(raw_ics)), 4) if raw_ics else None,
                "detail": detail,
            }

    out = {"dates": table, "oos_overlay": oos,
           "meta": {"universe_n": len(universe), "n_dates": len(table),
                    "cached": CACHED_DATES, "extra": extra_dates,
                    "horizons": HORIZONS,
                    "note": "real base_score subset to 250-stock cap-stratified sample; "
                            "IC = Spearman rank-IC vs forward hfq return; regime via "
                            "run_prototype logic (trend60 sign + vol20 vs expanding 250d median)."}}
    os.makedirs(f"{ROOT}", exist_ok=True)
    json.dump(out, open(f"{ROOT}/realbase_analysis.json", "w"), ensure_ascii=False, indent=1)

    # ---- console summary ----
    print("\n==== REAL base_score IC by date & regime (250-stock sample) ====")
    print(f"{'date':>10} {'src':>6} {'regime':>9} {'trend60':>8} {'vol20':>6} "
          f"{'n':>4} {'+10d IC':>8} {'+20d IC':>8}")
    for r in table:
        reg = f"{r['regime_trend']}/{r['regime_vol']}"
        print(f"{r['date']:>10} {r['source']:>6} {reg:>9} {r['trend60']:>+8.3f} "
              f"{r['vol20']:>6.3f} {r['n_overlap']:>4} "
              f"{str(r['ic10']):>8} {str(r['ic20']):>8}")
    print("\n==== OOS regime-overlay (sign-flip) test ====")
    for h in HORIZONS:
        o = oos.get(f"h{h}")
        if not o:
            continue
        print(f"\n +{h}d  train={o['train_dates']}  test={o['test_dates']}")
        print(f"      train sign_map (regime->mean train IC): {o['train_sign_map']}")
        print(f"      TEST mean raw IC      = {o['mean_raw_ic_test']}")
        print(f"      TEST mean overlaid IC = {o['mean_overlaid_ic_test']}  (delta {o['delta']})")
        print(f"      TEST mean |raw IC|    = {o['mean_abs_raw_test']}  (ceiling if every flip correct)")
        for d in o["detail"]:
            print(f"        {d['date']} [{d['regime']}] train_seen={d['train_seen']} "
                  f"sign={d['train_sign']:+.0f} raw={d['raw_ic']:+.4f} -> overlaid={d['overlaid_ic']:+.4f}")
    print(f"\nwrote {ROOT}/realbase_analysis.json")


if __name__ == "__main__":
    main()
