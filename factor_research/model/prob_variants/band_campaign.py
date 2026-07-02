#!/usr/bin/env python3
"""magnitude_band campaign: main grid + hyperparameter probes + honesty bar.

Writes factor_research/model/reports/magnitude_band.json.
Panel loaded once; ranking scores computed once per horizon and reused
(vol-shuffle does not touch scores; score-shuffle perturbs a copy inside
run_variants)."""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from factor_research.model import harness as H                     # noqa: E402
from factor_research.model.prob_variants import band as B          # noqa: E402

OUT = os.path.join(ROOT, "factor_research", "model", "reports",
                   "magnitude_band.json")


def compact(res, keep_cal=False):
    """compress evaluate_all output for the report."""
    def row(m):
        r = {"cov": round(m["coverage_q10_q90"], 4),
             "width": round(m["mean_width"], 4),
             "pin": round(m["pinball_total"], 5),
             "mu_slope": (round(m["mean_up_calibration"]["slope"], 2)
                          if np.isfinite(m["mean_up_calibration"]["slope"]) else None),
             "mu_mae": (round(m["mean_up_calibration"]["mae"], 4)
                        if np.isfinite(m["mean_up_calibration"]["mae"]) else None)}
        if keep_cal:
            r["mu_octiles"] = m["mean_up_calibration"]["octiles"]
        return r

    def pr(p):
        return {"dpin_pct": round(p["pinball_improve_pct"], 2),
                "t": round(p["pinball_improve_t"], 2),
                "pos_dates": round(p["pinball_pos_dates_pct"], 2)}

    out = {"n_dates": res["a"]["n_dates"], "n_obs": res["a"]["n_obs"]}
    for p in B.VARIANTS:
        out[p] = row(res[p])
    for k in ("aw_vs_a", "b_vs_a", "c_vs_a", "d_vs_a", "b_vs_aw",
              "d_vs_b", "d_vs_c"):
        out[k] = pr(res[k])
    if "conformal" in res:
        cf = res["conformal"]
        o = {"n_dates": cf["n_dates"],
             "lambdas": {p: round(cf[f"mean_lambda_{p}"], 3)
                         for p in ("a", "b", "c", "d")}}
        for p in ("a_cf", "b_cf", "c_cf", "d_cf", "a_on_subset"):
            o[p] = row(cf[p])
        for k in ("b_cf_vs_a_cf", "c_cf_vs_a_cf", "d_cf_vs_a_cf", "d_cf_vs_d"):
            o[k] = pr(cf[k])
        out["conformal"] = o
    return out


def main():
    t0 = time.time()
    z, meta = H.load_panel()
    Z = H.neutralize(z, meta)
    cfg = json.load(open(B.FINAL_CFG))
    scores = {}
    for h in (10, 20):
        fwd = z[f"fwd{h}"].astype(np.float64)
        scores[h] = H.walk_forward(Z, fwd, meta, cfg)
        print(f"[{time.time()-t0:6.1f}s] scores h{h} ready", flush=True)

    report = {"family": "magnitude_band",
              "score_config": "factor_research/model/final_model.json "
                              "(ew_signed sue,npq_yoy)",
              "vol_feature": "rvol_20 (raw panel feature, observed at t)",
              "main": {}, "probes": {}, "honesty": {}}
    n_configs = 0

    def run(h, **kw):
        return B.run_variants(horizon=h, panel=(z, meta), scores=scores[h], **kw)

    # ---------------- main grid (defaults: clip .5-2, alpha 1, ng 3) -------
    recs_main = {}
    for h in (10, 20):
        recs = run(h, liquid=0.70)
        recs_main[h] = recs
        res, _ = B.evaluate_all(recs)
        report["main"][f"h{h}"] = compact(res, keep_cal=True)
        n_configs += 5   # a, aw, b, c, d
        print(f"[{time.time()-t0:6.1f}s] main h{h} done", flush=True)

    # ---------------- hyperparameter probes --------------------------------
    for tag, kw in (("alpha_0.7", dict(alpha=0.7)),
                    ("clip_0.33_3", dict(clip_lo=1 / 3, clip_hi=3.0)),
                    ("ng_5", dict(ng=5))):
        report["probes"][tag] = {}
        for h in (10, 20):
            res, _ = B.evaluate_all(run(h, liquid=0.70, **kw))
            report["probes"][tag][f"h{h}"] = compact(res)
            n_configs += 3   # affects b/c/d
            print(f"[{time.time()-t0:6.1f}s] probe {tag} h{h} done", flush=True)

    # ---------------- honesty bar -------------------------------------------
    hon = report["honesty"]

    # (1) vol-shuffle null, 5 seeds per horizon: c/d/b improvements must die
    hon["vol_shuffle"] = {}
    for h in (10, 20):
        rows = []
        for seed in range(1, 6):
            res, _ = B.evaluate_all(run(h, liquid=0.70, shuffle_vol=seed))
            cf = res["conformal"]
            rows.append({
                "seed": seed,
                "c_vs_a_pct": round(res["c_vs_a"]["pinball_improve_pct"], 2),
                "c_vs_a_t": round(res["c_vs_a"]["pinball_improve_t"], 2),
                "d_vs_a_pct": round(res["d_vs_a"]["pinball_improve_pct"], 2),
                "b_vs_aw_pct": round(res["b_vs_aw"]["pinball_improve_pct"], 2),
                "c_cf_vs_a_cf_pct": round(
                    cf["c_cf_vs_a_cf"]["pinball_improve_pct"], 2),
                "c_cf_vs_a_cf_t": round(
                    cf["c_cf_vs_a_cf"]["pinball_improve_t"], 2)})
            print(f"[{time.time()-t0:6.1f}s] vol-shuffle h{h} seed{seed}",
                  flush=True)
        hon["vol_shuffle"][f"h{h}"] = rows

    # (2) score-shuffle (leak check on the pipeline): score bins carry no
    # info -> mean_up slope must die; vol effect (c/d/b vs a) may legitimately
    # persist because vol is real even when score is noise.
    hon["score_shuffle"] = {}
    for h in (10, 20):
        rows = []
        for seed in (1, 2, 3, 4):
            res, _ = B.evaluate_all(run(h, liquid=0.70, shuffle_score=seed))
            rows.append({
                "seed": seed,
                "a_mu_slope": (round(res["a"]["mean_up_calibration"]["slope"], 2)
                               if np.isfinite(res["a"]["mean_up_calibration"]["slope"])
                               else None),
                "d_mu_slope": (round(res["d"]["mean_up_calibration"]["slope"], 2)
                               if np.isfinite(res["d"]["mean_up_calibration"]["slope"])
                               else None),
                "a_cov": round(res["a"]["coverage_q10_q90"], 4),
                "c_vs_a_pct": round(res["c_vs_a"]["pinball_improve_pct"], 2)})
            print(f"[{time.time()-t0:6.1f}s] score-shuffle h{h} seed{seed}",
                  flush=True)
        hon["score_shuffle"][f"h{h}"] = rows

    # (3) liquid 0.50
    hon["liquid_50"] = {}
    for h in (10, 20):
        res, _ = B.evaluate_all(run(h, liquid=0.50))
        hon["liquid_50"][f"h{h}"] = compact(res)
        print(f"[{time.time()-t0:6.1f}s] liquid50 h{h} done", flush=True)

    # (4) drop-year / drop-regime: filter TEST recs of the main run
    hon["drop_year"] = {}
    hon["drop_regime"] = {}
    for h in (10, 20):
        years = sorted({r["date"][:4] for r in recs_main[h]})
        hon["drop_year"][f"h{h}"] = {}
        for y in years:
            sub = B.filter_recs(recs_main[h], drop_year=y)
            if len(sub) < 8:
                continue
            res, _ = B.evaluate_all(sub)
            hon["drop_year"][f"h{h}"][y] = compact(res)
        regs = sorted({r["regime"] for r in recs_main[h]})
        hon["drop_regime"][f"h{h}"] = {}
        for rg in regs:
            sub = B.filter_recs(recs_main[h], drop_regime=rg)
            if len(sub) < 8:
                continue
            res, _ = B.evaluate_all(sub)
            hon["drop_regime"][f"h{h}"][rg] = compact(res)
        print(f"[{time.time()-t0:6.1f}s] subset cuts h{h} done", flush=True)

    report["configs_tried"] = n_configs
    report["runtime_sec"] = round(time.time() - t0, 1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=1, default=float)
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
