#!/usr/bin/env python3
"""Adversarial economics skeptic for the magnitude_band claim.

Attacks:
 1. fresh vol-shuffle null seeds (7,11,13,17,19) x h10/h20 -> c_vs_a must die
 2. keep-only regime cuts (not just drop-one): is the gain concentrated?
 3. liquid 0.50 re-run (independent of the report)
 4. economic size: within-date predicted-width differentiation (c vs a),
    does predicted width track realized dispersion, pinball gain by
    predicted-width tercile, per-date coverage dispersion of c_cf,
    date-vs-stock variance decomposition of |ret - q50| (signal-to-date-noise)
Writes factor_research/model/reports/skeptic_band_econ.json
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from factor_research.model import harness as H            # noqa: E402
from factor_research.model.prob_variants import band as B  # noqa: E402

OUT = os.path.join(ROOT, "factor_research", "model", "reports",
                   "skeptic_band_econ.json")


def cva(res):
    p = res["c_vs_a"]
    return {"dpin_pct": round(p["pinball_improve_pct"], 2),
            "t": round(p["pinball_improve_t"], 2),
            "pos_dates": round(p["pinball_pos_dates_pct"], 2)}


def main():
    t0 = time.time()
    z, meta = H.load_panel()
    Z = H.neutralize(z, meta)
    cfg = json.load(open(B.FINAL_CFG))
    scores = {}
    for h in (10, 20):
        fwd = z[f"fwd{h}"].astype(np.float64)
        scores[h] = H.walk_forward(Z, fwd, meta, cfg)
    print(f"[{time.time()-t0:.1f}s] scores ready", flush=True)

    def run(h, **kw):
        return B.run_variants(horizon=h, panel=(z, meta), scores=scores[h], **kw)

    rep = {}

    # ---- main recs reused everywhere -----------------------------------
    recs = {h: run(h, liquid=0.70) for h in (10, 20)}

    # ---- 1. fresh vol-shuffle nulls ------------------------------------
    rep["fresh_vol_shuffle"] = {}
    for h in (10, 20):
        rows = []
        for seed in (7, 11, 13, 17, 19):
            res, _ = B.evaluate_all(run(h, liquid=0.70, shuffle_vol=seed))
            rows.append({"seed": seed, **cva(res)})
            print(f"[{time.time()-t0:.1f}s] vshuf h{h} s{seed}", flush=True)
        rep["fresh_vol_shuffle"][f"h{h}"] = rows

    # ---- 2. keep-only regime cuts --------------------------------------
    rep["keep_only_regime"] = {}
    for h in (10, 20):
        out = {}
        regs = sorted({r["regime"] for r in recs[h]})
        for rg in regs:
            sub = [r for r in recs[h] if r["regime"] == rg]
            if len(sub) < 5:
                out[rg] = {"n_dates": len(sub), "skipped": True}
                continue
            res, _ = B.evaluate_all(sub)
            out[rg] = {"n_dates": len(sub), **cva(res)}
        rep["keep_only_regime"][f"h{h}"] = out

    # keep-only year
    rep["keep_only_year"] = {}
    for h in (10, 20):
        out = {}
        for y in sorted({r["date"][:4] for r in recs[h]}):
            sub = [r for r in recs[h] if r["date"][:4] == y]
            if len(sub) < 5:
                out[y] = {"n_dates": len(sub), "skipped": True}
                continue
            res, _ = B.evaluate_all(sub)
            out[y] = {"n_dates": len(sub), **cva(res)}
        rep["keep_only_year"][f"h{h}"] = out

    # ---- 3. liquid 0.50 -------------------------------------------------
    rep["liquid_50"] = {}
    for h in (10, 20):
        res, _ = B.evaluate_all(run(h, liquid=0.50))
        cf = res["conformal"]
        rep["liquid_50"][f"h{h}"] = {
            **cva(res),
            "c_cf_cov": round(cf["c_cf"]["coverage_q10_q90"], 4),
            "c_cf_vs_a_cf": {
                "dpin_pct": round(cf["c_cf_vs_a_cf"]["pinball_improve_pct"], 2),
                "t": round(cf["c_cf_vs_a_cf"]["pinball_improve_t"], 2)}}
        print(f"[{time.time()-t0:.1f}s] liquid50 h{h}", flush=True)

    # ---- 4. economic size ------------------------------------------------
    rep["econ_size"] = {}
    for h in (10, 20):
        R = recs[h]
        # 4a. within-date predicted width spread, c vs a
        wsp = {"a": [], "c": []}
        wratio = []          # within-date P90/P10 of c width
        for r in R:
            for p in ("a", "c"):
                w = r[f"{p}_q90"] - r[f"{p}_q10"]
                wsp[p].append(float(np.std(w)) / max(float(np.mean(w)), 1e-9))
            wc = r["c_q90"] - r["c_q10"]
            wratio.append(float(np.percentile(wc, 90) /
                                max(np.percentile(wc, 10), 1e-9)))
        # 4b. predicted width tercile -> realized dispersion + pinball gain
        # within each date, sort by c predicted width, tercile split
        realized_disp = [[], [], []]       # realized std of ret per tercile
        realized_cov = [[], [], []]        # realized coverage by c band
        pin_gain = [[], [], []]            # per-date pinball gain c vs a
        widths = [[], [], []]
        for r in R:
            wc = r["c_q90"] - r["c_q10"]
            y = r["ret"]
            n = len(y)
            order = np.argsort(np.argsort(wc))
            ter = np.minimum(order * 3 // n, 2)
            for g in range(3):
                m = ter == g
                if m.sum() < 30:
                    continue
                realized_disp[g].append(float(np.std(y[m])))
                realized_cov[g].append(float(np.mean(
                    (y[m] >= r["c_q10"][m]) & (y[m] <= r["c_q90"][m]))))
                pa = (B.pinball(y[m], r["a_q10"][m], .1)
                      + B.pinball(y[m], r["a_q90"][m], .9)).mean()
                pc = (B.pinball(y[m], r["c_q10"][m], .1)
                      + B.pinball(y[m], r["c_q90"][m], .9)).mean()
                pin_gain[g].append(float((pa - pc) / pa * 100))
                widths[g].append(float(np.mean(wc[m])))
        # 4c. per-date coverage dispersion of c_cf (conformal-ready dates)
        cfr = [r for r in R if r.get("conformal_ready")]
        cov_d = [float(np.mean((r["ret"] >= r["c_cf_q10"])
                               & (r["ret"] <= r["c_cf_q90"]))) for r in cfr]
        cov_d_a = [float(np.mean((r["ret"] >= r["a_cf_q10"])
                                 & (r["ret"] <= r["a_cf_q90"]))) for r in cfr]
        # 4d. date vs stock variance decomposition of |ret - c_q50|
        resid = [np.abs(r["ret"] - r["c_q50"]) for r in R]
        dmeans = np.array([float(x.mean()) for x in resid])
        allr = np.concatenate(resid)
        grand = allr.mean()
        ssb = sum(len(x) * (m - grand) ** 2
                  for x, m in zip(resid, dmeans))
        sst = float(((allr - grand) ** 2).sum())
        rep["econ_size"][f"h{h}"] = {
            "within_date_width_cv": {p: round(float(np.mean(wsp[p])), 4)
                                     for p in ("a", "c")},
            "within_date_c_width_p90_over_p10":
                round(float(np.mean(wratio)), 3),
            "by_pred_width_tercile": {
                f"t{g}": {
                    "mean_pred_width": round(float(np.mean(widths[g])), 4),
                    "realized_ret_std": round(float(np.mean(realized_disp[g])), 4),
                    "realized_cov_c": round(float(np.mean(realized_cov[g])), 4),
                    "pinball_gain_c_vs_a_pct":
                        round(float(np.mean(pin_gain[g])), 2),
                    "pinball_gain_t": round(float(
                        np.mean(pin_gain[g]) /
                        (np.std(pin_gain[g], ddof=1) /
                         np.sqrt(len(pin_gain[g])))), 2)}
                for g in range(3)},
            "c_cf_per_date_coverage": {
                "mean": round(float(np.mean(cov_d)), 4),
                "std": round(float(np.std(cov_d)), 4),
                "min": round(float(np.min(cov_d)), 4),
                "max": round(float(np.max(cov_d)), 4),
                "frac_in_70_90": round(float(np.mean(
                    [(0.70 <= c <= 0.90) for c in cov_d])), 3)},
            "a_cf_per_date_coverage_std": round(float(np.std(cov_d_a)), 4),
            "date_share_of_absresid_var": round(ssb / sst, 4)}
        print(f"[{time.time()-t0:.1f}s] econ h{h}", flush=True)

    rep["runtime_sec"] = round(time.time() - t0, 1)
    json.dump(rep, open(OUT, "w"), indent=1, default=float)
    print(json.dumps(rep, indent=1, default=float))


if __name__ == "__main__":
    main()
