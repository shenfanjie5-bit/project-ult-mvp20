#!/usr/bin/env python3
"""Emit the per-stock 涨幅预测分数 payload for one as-of date (ISOLATED demo).

This is the PRODUCT-SHAPED artifact: for the chosen panel base date (default =
the latest), fit both layers walk-forward on strictly earlier dates and emit
one JSON row per liquid stock:

  {
    ts_code, asof, regime,
    mag_score_pct,            # 幅度层分数百分位 0..100 (盈余惊喜, 排序已验证)
    exp_excess_h, q10, q90,   # 幅度: 期望超额收益 + 80% 经验区间 (horizon h)
    mean_if_up,               # E[涨幅 | 上涨] from the stock's score bin
    p_beat_median,            # 概率层: 校准的"跑赢当日中位数"概率 (rel target)
    p_up_tilt,                # 概率层: 相对当期基准率的倾斜 (pp), NOT absolute P(up)
    confidence                # 特征覆盖率 x 样本充足度
  }

Honesty by construction (see REPORT_PROB.md §3): no absolute "73% 会涨" —
the date-level market move dominates absolute P(up); we ship the calibratable
relative probability + tilt, and the band carries market uncertainty.

Usage: emit_score.py [--asof YYYYMMDD] [--horizon 20] [--out emit.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.getcwd())
from factor_research.model import harness as H  # noqa: E402
from factor_research.model.caliblib import (  # noqa: E402
    liquid_mask, score_bins, fit_bins, K_BINS)

HERE = os.path.dirname(os.path.abspath(__file__))

MAG_CFG = json.load(open(os.path.join(HERE, "final_model.json")))
# Verified best prob layer (workflow prob_features, survived statistics +
# economics skeptics): rvol_20 was pure dilution and is dropped; ivol_60 +
# ep_ttm carry the discrimination. h20/rel disc +7.06pp (t2.83), 8.6 sigma
# beyond a 14-seed shuffle null, clears a 120-config Bonferroni by ~2.5x.
PROB_CFG = {
    "name": "prob_layer_v2",
    "method": "ic_weighted",
    "features": ["ivol_60", "max5", "turnover_20", "ep_ttm"],
    "params": {"min_cov": 0.5},
    "min_train_dates": 12,
}
# Band upgrade (verified, magnitude_band family): score-bin x rvol-tercile
# pooling + walk-forward conformal width factor (prob_variants/band.py,
# variant c_cf) improves q10/q90 pinball ~4.3% (t~10) and hits 0.80 coverage;
# this demo emitter still uses plain bin pooling for simplicity.


def emit(asof=None, horizon=20, liquid=0.70):
    z, meta = H.load_panel()
    Z = H.neutralize(z, meta)
    dates = meta["base_dates"]
    regimes = [r["regime"] for r in meta["regimes"]]
    cols = meta["cols"]
    t = len(dates) - 1 if asof is None else dates.index(asof)
    fwd = z[f"fwd{horizon}"].astype(np.float64)
    fwd_rel = fwd.copy()
    mask = liquid_mask(z, liquid)
    for d in range(fwd.shape[0]):
        ok = np.isfinite(fwd[d]) & mask[d]
        if ok.sum() > 50:
            fwd_rel[d] = fwd[d] - np.median(fwd[d][ok])

    mag_scores = H.walk_forward(Z, fwd, meta, MAG_CFG)
    prob_scores = H.walk_forward(Z, fwd_rel, meta, PROB_CFG)
    train_idx = [d for d in range(t) if np.isfinite(mag_scores[d]).any()]

    # magnitude layer: bins on mag score -> absolute fwd distribution
    mag_stats, _ = fit_bins(mag_scores, fwd, mask, train_idx)
    # probability layer: bins on prob score -> relative beat-median distribution
    prob_stats, _ = fit_bins(prob_scores, fwd_rel, mask, train_idx)
    base_rate = float(np.nanmean([s["p_up"] for s in prob_stats if s]))
    # cross-sectional expectation baseline: pooled mean across mag bins (so the
    # emitted exp_excess is the bin's edge vs the liquid universe, NOT the raw
    # train-period absolute drift, which belongs only in the band).
    uni_mean = float(np.nanmean([s["mean"] for s in mag_stats if s]))

    mb = score_bins(mag_scores[t], mask[t])
    pb = score_bins(prob_scores[t], mask[t])
    # percentile of mag score within the liquid cross-section
    ms = mag_scores[t]
    okm = np.isfinite(ms) & mask[t]
    pct = np.full(ms.shape, np.nan)
    if okm.sum() > 10:
        r = np.argsort(np.argsort(ms[okm]))
        pct[okm] = 100.0 * r / (okm.sum() - 1)

    # feature coverage for confidence
    feat_cov = np.isfinite(Z[t]).mean(axis=1)

    rows = []
    for j in range(len(cols)):
        if mb[j] < 0 or pb[j] < 0:
            continue
        m = mag_stats[mb[j]]
        p = prob_stats[pb[j]]
        if m is None or p is None:
            continue
        rows.append({
            "ts_code": cols[j],
            "asof": dates[t],
            "horizon_days": horizon,
            "regime": regimes[t],
            "mag_score_pct": round(float(pct[j]), 1),
            "exp_excess": round(m["mean"] - uni_mean, 4),
            "exp_ret_train_abs": round(m["mean"], 4),
            "q10": round(m["q10"], 4),
            "q90": round(m["q90"], 4),
            "mean_if_up": round(m["mean_up"], 4),
            "p_beat_median": round(p["p_up"], 3),
            "p_up_tilt_pp": round(100 * (p["p_up"] - base_rate), 1),
            "confidence": round(float(feat_cov[j]), 2),
        })
    return {
        "asof": dates[t], "horizon_days": horizon, "regime": regimes[t],
        "n_train_dates": len(train_idx), "n_stocks": len(rows),
        "liquid_frac": liquid,
        "note": ("p_beat_median is the calibrated P(beat the same-day liquid median); "
                 "absolute P(up) is market-dominated (date base rate ranged 0.12-0.97 OOS) "
                 "and intentionally NOT emitted as a per-stock absolute."),
        "rows": rows,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=None)
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    payload = emit(a.asof, a.horizon)
    if a.out:
        json.dump(payload, open(a.out, "w"), ensure_ascii=False, indent=1)
    head = {k: v for k, v in payload.items() if k != "rows"}
    print(json.dumps(head, ensure_ascii=False, indent=1))
    rows = sorted(payload["rows"], key=lambda r: -r["mag_score_pct"])
    print("\nTOP-10 by mag_score_pct:")
    for r in rows[:10]:
        print(f"  {r['ts_code']}  mag%={r['mag_score_pct']:5.1f}  expExc={r['exp_excess']:+.4f} "
              f"[{r['q10']:+.3f},{r['q90']:+.3f}]  E[ret|up]={r['mean_if_up']:+.4f}  "
              f"P(beat)={r['p_beat_median']:.3f} tilt={r['p_up_tilt_pp']:+.1f}pp  conf={r['confidence']}")
    print("\nBOTTOM-3:")
    for r in rows[-3:]:
        print(f"  {r['ts_code']}  mag%={r['mag_score_pct']:5.1f}  expExc={r['exp_excess']:+.4f} "
              f"[{r['q10']:+.3f},{r['q90']:+.3f}]  P(beat)={r['p_beat_median']:.3f} tilt={r['p_up_tilt_pp']:+.1f}pp")
