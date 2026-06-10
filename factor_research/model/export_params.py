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
#: v3: + t5a THS concept limit-up heat (sign carried by its frozen IC weight,
#: which is NEGATIVE — hot themes -> lower P(beat median)). Verified by the
#: enhancer workflow: incremental disc −2.5pp on TOP of the 4-feature
#: composite after full controls (REPORT_FRAMEWORK_ENHANCERS.md §3.1).
THEME_FEATURE = "cpt_heat5"
THEME_NPZ = "factor_research/enhancers/theme_speculation/theme_factors.npz"
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


def _neutralized_theme(z, meta) -> "np.ndarray":
    """t5a concept-heat [D,N,1], neutralized per date exactly like the panel
    features (winsor->z->residualize[1,ln_mv,industry]->rank-z). Loaded from
    the enhancer-workflow matrix (panel-aligned); dates beyond the 打板 data
    end (2026-03-23) stay NaN."""

    th = np.load(THEME_NPZ, allow_pickle=True)
    t5a = th["t5a_cptheat5"].astype(np.float64)
    assert t5a.shape == (len(meta["base_dates"]), len(meta["cols"])), \
        "theme matrix not panel-aligned"
    zin = {"feat": t5a[:, :, None], "ln_mv": z["ln_mv"], "industry": z["industry"]}
    return H.neutralize(zin, None, cache=False)


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

    # ---- probability layer v3: rel target on fwd10, 4 panel features +
    # external t5a concept-heat (neutralized identically) ----
    fwd10 = z[f"fwd{PROB_HORIZON}"].astype(np.float64).copy()
    for d in range(fwd10.shape[0]):
        ok = np.isfinite(fwd10[d]) & mask[d]
        if ok.sum() > 50:
            fwd10[d] = fwd10[d] - np.median(fwd10[d][ok])

    fsel = [names.index(f) for f in PROB_FEATURES]
    Z5 = np.concatenate([Z[:, :, fsel], _neutralized_theme(z, meta)], axis=2)
    feat5 = PROB_FEATURES + [THEME_FEATURE]

    # frozen per-feature IC weights = full-sample mean per-date rank-IC; the
    # SAME frozen weights are then used for the bin fit below (a prior export
    # mixed walk-forward scores into the bins while freezing full-sample
    # weights — the parity skeptic flagged the inconsistency; now both sides
    # of the frozen artifact use one weight set).
    valid_d = np.array([d for d in range(Z5.shape[0]) if np.isfinite(fwd10[d]).any()])
    w = H._ic_weights(Z5[valid_d], fwd10[valid_d], None)
    prob_weights = {f: float(w[i]) for i, f in enumerate(feat5)}
    if prob_weights[THEME_FEATURE] >= 0:
        raise RuntimeError(
            f"theme heat weight came out non-negative ({prob_weights[THEME_FEATURE]:.4f}) "
            "— contradicts the verified negative signal; refusing to freeze")

    cov5 = np.isfinite(Z5).mean(axis=2)
    Xi = np.where(np.isfinite(Z5), Z5, 0.0)
    prob_scores = Xi @ w
    prob_scores[cov5 < 0.5] = np.nan
    train_idx_p = [int(d) for d in valid_d]
    prob_stats, _ = fit_bins(prob_scores, fwd10, mask, train_idx_p)
    if any(s is None for s in prob_stats):
        raise RuntimeError("probability bins incomplete")
    base_rate = float(np.nanmean([s["p_up"] for s in prob_stats]))

    params = {
        "version": 2,
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
            "features": PROB_FEATURES + [THEME_FEATURE],
            "method": "ic_weighted_frozen",
            "weights": prob_weights,
            "horizon_days": PROB_HORIZON,
            "target": "P(beat same-day liquid median)",
            "base_rate": base_rate,
            "top_bin_shrink": TOP_BIN_SHRINK,
            "bins": [{k: s[k] for k in ("n", "p_up", "mean")} for s in prob_stats],
            "theme_feature": {
                "name": THEME_FEATURE,
                "definition": ("mean over stock's THS N-type concepts of "
                               "(member limit-up closes past 5 trading days / concept size)"),
                "verified": "incremental disc −2.5pp on top of the 4-feature composite (REPORT_FRAMEWORK_ENHANCERS §3.1)",
                "membership_snapshot_caveat": "concept membership is a current snapshot (look-ahead in backfill, mitigated pre-2023-concepts check)",
            },
            "oos": {"disc_top_bottom_pp": 5.5, "t": 2.0,
                    "note": "honest fwd expectation 5-7pp (4-feature, REPORT_PROB.md §5.1) + theme −2.5pp incremental"},
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
