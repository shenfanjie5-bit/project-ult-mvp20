#!/usr/bin/env python3
"""Freeze A-share 5d relative signal calibration params.

Output: ``config/signal_5d_params.json``.

This is intentionally separate from ``export_params.py`` because the workbench
"today key signals" card needs a 5 trading-day probability layer, while the
existing production quant shadow emits 10d P(beat median) + 20d magnitude.

The target is relative and calibratable:
    P(fwd5 return beats the same-day liquid-universe median)

It is NOT absolute P(up), which REPORT_PROB.md identifies as market-dominated.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, os.getcwd())
from factor_research.model import harness as H  # noqa: E402
from factor_research.model.caliblib import K_BINS, fit_bins, liquid_mask  # noqa: E402
from mvp20 import signal_5d  # noqa: E402


OUT = Path("config/signal_5d_params.json")
SWEEP_REPORT = Path("factor_research/model/reports/prob_sweep_stage3.json")
HORIZON_DAYS = 5
LIQUID_FRAC = 0.70
FEATURES = ["ivol_60", "ep_ttm", "strev"]
METHOD = "ew_signed"
TARGET = "P(5d beat same-day liquid median)"
TILT_SHRINK = 0.5


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except Exception:  # noqa: BLE001
        return None


def _stage3_summary() -> dict:
    if not SWEEP_REPORT.exists():
        return {"warning": f"{SWEEP_REPORT} missing"}
    rows = json.loads(SWEEP_REPORT.read_text(encoding="utf-8"))
    candidates = [
        r for r in rows
        if r.get("horizon") == HORIZON_DAYS
        and r.get("target") == "rel"
        and r.get("name") == "min_pair_strev__ew_signed"
    ]
    if not candidates:
        return {"warning": "stage3 h5 rel min_pair_strev__ew_signed not found"}
    r = candidates[0]
    return {
        "report": str(SWEEP_REPORT),
        "selected_name": r.get("name"),
        "features": r.get("features"),
        "method": r.get("method"),
        "variant": r.get("variant"),
        "n_test_dates": r.get("n_test_dates"),
        "n_obs": r.get("n_obs"),
        "disc_up_pp": r.get("disc_up_pp"),
        "disc_ret_pp": r.get("disc_ret_pp"),
        "brier_skill": r.get("brier_skill"),
        "coverage_q10_q90": r.get("coverage_q10_q90"),
        "reliability": r.get("reliability"),
        "note": (
            "H5 edge is real but marginal; production shrinks bin tilt by 50% "
            "and surfaces validated/stale flags instead of an absolute P(up)."
        ),
    }


def main() -> int:
    z, meta = H.load_panel()
    Z = H.neutralize(z, meta)
    names = meta["feat_names"]
    fwd = z[f"fwd{HORIZON_DAYS}"].astype(np.float64).copy()
    mask = liquid_mask(z, LIQUID_FRAC)

    # Relative target: remove the same-day liquid-universe median return.
    for d in range(fwd.shape[0]):
        ok = np.isfinite(fwd[d]) & mask[d]
        if ok.sum() > 50:
            fwd[d] = fwd[d] - np.median(fwd[d][ok])

    idx = [names.index(f) for f in FEATURES]
    signs = {f: float(H.SIGN_PRIOR[f]) for f in FEATURES}
    w = np.array([signs[f] for f in FEATURES], dtype=float)
    sub = Z[:, :, idx]
    cov = np.isfinite(sub).mean(axis=2)
    score = np.where(np.isfinite(sub), sub, 0.0) @ w
    score[cov < 0.5] = np.nan

    train_idx = [
        d for d in range(score.shape[0])
        if np.isfinite(score[d]).any() and np.isfinite(fwd[d]).any()
    ]
    raw_stats, _ = fit_bins(score, fwd, mask, train_idx)
    if any(s is None for s in raw_stats):
        raise RuntimeError("signal_5d bins incomplete")
    stats = signal_5d.apply_isotonic_p_up(raw_stats)

    base_rate = float(np.nanmean([s["p_up"] for s in stats]))
    params = {
        "version": 1,
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_sha": _git_sha(),
        "panel": {
            "base_dates": [meta["base_dates"][0], meta["base_dates"][-1]],
            "n_dates": len(meta["base_dates"]),
            "n_stocks": len(meta["cols"]),
        },
        "horizon_days": HORIZON_DAYS,
        "target": TARGET,
        "target_kind": "relative_cross_section_median",
        "liquid_frac": LIQUID_FRAC,
        "k_bins": K_BINS,
        "min_feature_coverage": 0.5,
        "neutralization": (
            "per-date cross-section: winsor->z->residualize[1,ln_mv,industry]"
            "->rank-z; NaN->0 post-rank; min feature coverage 0.5"
        ),
        "features": FEATURES,
        "method": METHOD,
        "signs": signs,
        "base_rate": base_rate,
        "tilt_shrink": TILT_SHRINK,
        "bins": [{k: s[k] for k in (
            "n", "p_up", "p_up_raw", "mean", "q10", "q50", "q90"
        )} for s in stats],
        "calibration": {
            "fit": "full-panel frozen bins over matured fwd5 relative returns",
            "p_up_isotonic": True,
            "p_up_isotonic_method": "weighted_pool_adjacent_violators",
            "stage3_oos": _stage3_summary(),
            "tilt_shrink": TILT_SHRINK,
        },
        "caveats": [
            "validated ONLY on the liquid top-70% by market cap; outside -> validated:false",
            "target is P(5d beat same-day liquid median), not absolute P(up)",
            "absolute P(up) is market-dominated and intentionally NOT emitted",
            "h5 research edge is marginal versus h10/h20; probability tilt is shrunk by 50%",
            "survivorship: universe frozen from a recent snapshot; reported edges are upper bounds",
            "A-share only; HK/US require separate history, feature, and calibration artifacts",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(params, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")
    print(
        "  bins P(beat median) range: "
        f"{stats[0]['p_up']:.3f} .. {stats[-1]['p_up']:.3f} "
        f"(base {base_rate:.3f}, shrink {TILT_SHRINK})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
