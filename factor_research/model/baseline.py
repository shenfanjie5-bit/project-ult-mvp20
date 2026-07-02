#!/usr/bin/env python3
"""Baseline: evaluate the PRODUCTION base_score as a forward-return predictor,
on the cells where it exists, using the SAME P&L metrics as the model harness.

base_score lives in factor_research/pit_extra/realbase.sqlite (14 monthly dates x
250-stock sample, 2024-01..2025-12). Forward returns are taken from the cached
price matrix. This establishes the bar the new model must beat:
  the task's premise is base_score is ANTI-correlated with fwd return
  (high score -> lower fwd return). We quantify the decile curve + top-excess.
"""
from __future__ import annotations
import json, os, sqlite3, sys
import numpy as np
sys.path.insert(0, os.getcwd())
from factor_research._datalib import load_price_matrices
from factor_research.model.harness import _spearman, _deciles, _boot_ci

DB = "factor_research/pit_extra/realbase.sqlite"

def fwd_at(cal, CUM, HAS, first_valid, k, h):
    n = CUM.shape[0]
    if k + h >= n:
        return None
    fr = np.exp(CUM[k + h] - CUM[k]) - 1.0
    ok = HAS[k] & (first_valid <= k) & HAS[k + 1:k + h + 1].any(0)
    return np.where(ok, fr, np.nan)

def main(h=10):
    RET, TO, MV, cal, cols = load_price_matrices("20230101")
    LR = np.log1p(np.nan_to_num(np.where(np.isfinite(RET), RET, np.nan), nan=0.0))
    CUM = np.cumsum(LR, axis=0); HAS = np.isfinite(RET)
    first_valid = np.where(HAS.any(0), HAS.argmax(0), len(cal) + 1)
    colidx = {c: j for j, c in enumerate(cols)}

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    dates = [r[0] for r in con.execute("SELECT DISTINCT base_date FROM scores ORDER BY base_date")]
    per_date = []
    for bd in dates:
        # align base date to the price calendar (last trading day <= bd)
        cand = [d for d in cal if d <= bd]
        if not cand:
            continue
        k = cal.index(cand[-1])
        fr = fwd_at(cal, CUM, HAS, first_valid, k, h)
        if fr is None:
            continue
        rows = con.execute("SELECT ts_code, base_score FROM scores WHERE base_date=?", (bd,)).fetchall()
        sc = np.full(len(cols), np.nan); rt = np.full(len(cols), np.nan)
        for ts, bs in rows:
            if ts in colidx and bs is not None:
                sc[colidx[ts]] = bs; rt[colidx[ts]] = fr[colidx[ts]]
        ok = np.isfinite(sc) & np.isfinite(rt)
        if ok.sum() < 50:
            continue
        ic = _spearman(sc[ok], rt[ok])
        dec = _deciles(sc, rt, 5)  # 250 stocks -> quintiles
        uni = float(np.nanmean(rt[ok]))
        rec = {"date": bd, "n": int(ok.sum()), "ic": ic, "uni_mean": uni}
        if dec is not None:
            rec["quint"] = dec.tolist()
            rec["q5_q1"] = float(dec[-1] - dec[0])
            rec["top_excess"] = float(dec[-1] - uni)
        per_date.append(rec)
    con.close()

    ics = [r["ic"] for r in per_date if np.isfinite(r["ic"])]
    q5q1 = [r["q5_q1"] for r in per_date if "q5_q1" in r]
    topx = [r["top_excess"] for r in per_date if "top_excess" in r]
    quints = np.array([r["quint"] for r in per_date if "quint" in r])
    summary = {
        "horizon": h, "n_dates": len(per_date),
        "ic_mean": float(np.mean(ics)), "ic_pos_pct": float(np.mean([1.0 if x>0 else 0.0 for x in ics])),
        "ic_t": float(np.mean(ics)/(np.std(ics, ddof=1)/np.sqrt(len(ics)))) if len(ics)>1 else None,
        "q5_q1_mean": float(np.mean(q5q1)), "q5_q1_ci": _boot_ci(q5q1),
        "q5_q1_pos_pct": float(np.mean([1.0 if x>0 else 0.0 for x in q5q1])),
        "top_excess_mean": float(np.mean(topx)), "top_excess_ci": _boot_ci(topx),
        "top_excess_pos_pct": float(np.mean([1.0 if x>0 else 0.0 for x in topx])),
        "quint_curve": quints.mean(0).tolist() if quints.size else None,
        "per_date": per_date,
    }
    json.dump(summary, open("factor_research/model/baseline_basescore.json","w"), indent=1)
    print(json.dumps({k:v for k,v in summary.items() if k!="per_date"}, indent=1))
    print("\nPER-DATE base_score IC (should be ~0 or NEGATIVE per the task premise):")
    for r in per_date:
        print(f"  {r['date']}  IC={r['ic']:+.3f}  Q5-Q1={r.get('q5_q1',float('nan')):+.4f}  topExc={r.get('top_excess',float('nan')):+.4f}  uni={r['uni_mean']:+.4f} n={r['n']}")

if __name__=="__main__":
    main(int(sys.argv[1]) if len(sys.argv)>1 else 10)
