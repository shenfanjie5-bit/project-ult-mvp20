#!/usr/bin/env python3
"""Freeze the validated two-layer model into production calibration params.

Produces ``config/quant_score_params.json`` — the ONLY interface between the
research stack (this directory, research venv) and production
(``mvp20/quant_score.py``). Production never re-trains; it computes today's
features, neutralizes cross-sectionally, and maps through these FROZEN tables.

What gets frozen (all from the audited panel, walk-forward conventions):
  * magnitude layer (REPORT.md): ew(sue, npq_yoy) score -> decile bins ->
    pooled absolute fwd20 distributions (exp/q10/q90/mean_up) + uni_mean
    baseline, fitted on ALL panel dates with matured fwd20.
  * probability layer (REPORT_PROB.md / workflow prob_features): per-feature
    IC weights for ic_weighted(ivol_60, max5, turnover_20, ep_ttm) against
    median-demeaned fwd10 (rel target), plus score-decile -> P(beat median)
    bins and the bin-average base rate.
  * honesty contract constants: liquid fraction 0.70, horizon labels,
    OOS performance summary + caveats (ride along to the UI), top-bin shrink
    (the verified reliability flaw: the extreme high-P bin under-delivers ->
    shrink predicted tilt of the top bin by 50% toward base rate).

Refresh cadence: monthly, or after a panel rebuild —
  factor_research/.venv_research/bin/python factor_research/model/panel.py
  factor_research/.venv_research/bin/python factor_research/model/export_params.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.getcwd())
from factor_research.model import harness as H  # noqa: E402
from factor_research.model.caliblib import (  # noqa: E402
    K_BINS, fit_bins, liquid_mask, score_bins)

OUT = "config/quant_score_params.json"

MAG_CFG = json.load(open("factor_research/model/final_model.json"))
PROB_FEATURES = ["ivol_60", "max5", "turnover_20", "ep_ttm"]
LIQUID_FRAC = 0.70
MAG_HORIZON = 20
PROB_HORIZON = 10
#: verified reliability flaw: extreme predicted-P bin under-delivers at both
#: horizons -> shrink its tilt toward base rate by this factor.
TOP_BIN_SHRINK = 0.5


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    z, meta = H.load_panel()
    Z = H.neutralize(z, meta)
    mask = liquid_mask(z, LIQUID_FRAC)
    names = meta["feat_names"]

    # ---- magnitude layer: bins over ALL dates with matured fwd20 ----
    fwd20 = z[f"fwd{MAG_HORIZON}"].astype(np.float64)
    mag_scores = H.walk_forward(Z, fwd20, meta, MAG_CFG)
    # use every date that has BOTH scores and matured labels as "train"
    train_idx = [d for d in range(mag_scores.shape[0])
                 if np.isfinite(mag_scores[d]).any() and np.isfinite(fwd20[d]).any()]
    mag_stats, _ = fit_bins(mag_scores, fwd20, mask, train_idx)
    if any(s is None for s in mag_stats):
        raise RuntimeError("magnitude bins incomplete — panel too thin?")
    uni_mean = float(np.nanmean([s["mean"] for s in mag_stats]))

    # ---- probability layer: rel target on fwd10 ----
    fwd10 = z[f"fwd{PROB_HORIZON}"].astype(np.float64).copy()
    for d in range(fwd10.shape[0]):
        ok = np.isfinite(fwd10[d]) & mask[d]
        if ok.sum() > 50:
            fwd10[d] = fwd10[d] - np.median(fwd10[d][ok])
    prob_cfg = {"name": "prob_layer_v2", "method": "ic_weighted",
                "features": PROB_FEATURES, "params": {"min_cov": 0.5},
                "min_train_dates": 12}
    prob_scores = H.walk_forward(Z, fwd10, meta, prob_cfg)
    train_idx_p = [d for d in range(prob_scores.shape[0])
                   if np.isfinite(prob_scores[d]).any()]
    prob_stats, _ = fit_bins(prob_scores, fwd10, mask, train_idx_p)
    if any(s is None for s in prob_stats):
        raise RuntimeError("probability bins incomplete")
    base_rate = float(np.nanmean([s["p_up"] for s in prob_stats]))

    # frozen per-feature IC weights = full-sample trailing weights (what the
    # last walk-forward step would use). Recompute explicitly for transparency.
    fsel = [names.index(f) for f in PROB_FEATURES]
    w = H._ic_weights(Z[:, :, fsel][np.array(train_idx_p)],
                      fwd10[np.array(train_idx_p)], None)
    prob_weights = {f: float(w[i]) for i, f in enumerate(PROB_FEATURES)}

    params = {
        "version": 1,
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_sha": _git_sha(),
        "panel": {"base_dates": [meta["base_dates"][0], meta["base_dates"][-1]],
                  "n_dates": len(meta["base_dates"]), "n_stocks": len(meta["cols"])},
        "liquid_frac": LIQUID_FRAC,
        "k_bins": K_BINS,
        "neutralization": "per-date cross-section: winsor->z->residualize[1,ln_mv,industry]->rank-z; NaN->0 post-rank; min feature coverage 0.5",
        "magnitude": {
            "features": MAG_CFG["features"],
            "method": "ew_signed",
            "signs": {f: H.SIGN_PRIOR[f] for f in MAG_CFG["features"]},
            "horizon_days": MAG_HORIZON,
            "uni_mean": uni_mean,
            "bins": [{k: s[k] for k in
                      ("n", "p_up", "mean", "mean_up", "mean_down",
                       "q10", "q25", "q50", "q75", "q90")} for s in mag_stats],
            "oos": {"top_excess_20d": 0.0083, "t": 2.9,
                    "note": "liquid-70 top-decile excess vs universe, walk-forward (REPORT.md §6)"},
        },
        "probability": {
            "features": PROB_FEATURES,
            "method": "ic_weighted_frozen",
            "weights": prob_weights,
            "horizon_days": PROB_HORIZON,
            "target": "P(beat same-day liquid median)",
            "base_rate": base_rate,
            "top_bin_shrink": TOP_BIN_SHRINK,
            "bins": [{k: s[k] for k in ("n", "p_up", "mean")} for s in prob_stats],
            "oos": {"disc_top_bottom_pp": 5.5, "t": 2.0,
                    "note": "honest fwd expectation 5-7pp after multiple-testing haircut (REPORT_PROB.md §5.1)"},
        },
        "caveats": [
            "validated ONLY on the liquid top-70% by market cap; outside -> validated:false",
            "absolute P(up) is market-dominated (OOS date base rate 0.12-0.97) and intentionally NOT emitted",
            "magnitude and probability are tail-anti-aligned; NEVER fuse into one score",
            "down_turbulent regime was untested in the OOS window — de-rate probability there",
            "survivorship: universe frozen from a recent snapshot; reported edges are upper bounds",
            "net-of-cost positive only at ~monthly rebalance on the magnitude layer",
        ],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(params, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"wrote {OUT}")
    print(f"  mag bins exp range: {mag_stats[0]['mean']:+.4f} .. {mag_stats[-1]['mean']:+.4f} (uni {uni_mean:+.4f})")
    print(f"  prob bins P(beat) range: {prob_stats[0]['p_up']:.3f} .. {prob_stats[-1]['p_up']:.3f} (base {base_rate:.3f})")
    print(f"  prob weights: {prob_weights}")


if __name__ == "__main__":
    main()
