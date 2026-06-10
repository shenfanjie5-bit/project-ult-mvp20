#!/usr/bin/env python3
"""magnitude_band: per-stock quantile band + E[gain|up] refinement.

Variants (all walk-forward; a date t forecast uses ONLY pooled train data from
base dates < t; per-stock vol used for scaling is rvol_20 OBSERVED AT t, a
panel feature, hence PIT-safe):

  a) bin-pooled  : baseline = caliblib behaviour. Stock in score-rank bin b
                   gets the pooled train distribution of bin b (q10/q50/q90,
                   mean_up). Ignores per-stock vol.
  b) vol-scaled  : same bin stats, but each stock's quantiles are scaled
                   around the bin q50 by s = clip((rvol_20_stock /
                   bin-median rvol_20)**alpha, lo, hi). mean_up scaled the
                   same way around q50.
  c) bin x vol-tercile : train returns pooled by (score-bin, per-date
                   vol-tercile); test stock gets its (bin, tercile) cell
                   distribution; falls back to plain bin pool when the cell
                   has < min_cell observations.
  aw) widen-control : variant a scaled uniformly (same factor for ALL stocks
                   on the date = per-date mean of b's stock scales). Separates
                   "b just inflates mean width because the clip is asymmetric"
                   from genuine cross-sectional reallocation.
  d) hybrid       : cell-pooled stats (as c) THEN per-stock scaling within the
                   cell by clip((vol_stock / cell-median vol)**alpha, lo, hi).
  *_cf) conformal : any base variant + walk-forward conformal width fix:
                   lambda_t = 80th pct of past OUT-OF-SAMPLE normalized band
                   residuals w (w<=1 <=> covered), past = test dates whose
                   forward window is fully realized before t (lag-aware, i.e.
                   STRICTER than caliblib's d<t convention). Past coverage
                   deficit (the temporal piece per-stock pooling cannot see)
                   is corrected by scaling both half-bands by lambda_t.

Metrics: q10-q90 coverage (target 0.80), mean band width, pinball loss at
q10/q90, E[ret|up] calibration (predicted vs realized mean_up by predicted
octile). Paired per-date t-stats variant-vs-baseline.

Nulls: --shuffle-vol permutes rvol_20 within each date everywhere it is used
(train tercile pools + test scaling/terciles) -> any b/c improvement must die.
--shuffle-score permutes scores within date (caliblib-style leak check).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from factor_research.model import harness as H            # noqa: E402
from factor_research.model import caliblib as C           # noqa: E402

MODEL_DIR = os.path.join(ROOT, "factor_research", "model")
FINAL_CFG = os.path.join(MODEL_DIR, "final_model.json")
K = 10          # score bins (caliblib default)
QS = (10, 25, 50, 75, 90)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def group_ranks(vrow, mask_row, ng):
    """per-date equal-count groups (e.g. vol terciles) over masked finite vals."""
    out = np.full(vrow.shape, -1, np.int32)
    ok = np.isfinite(vrow) & mask_row
    n = int(ok.sum())
    if n < ng * 10:
        return out
    r = np.argsort(np.argsort(vrow[ok]))
    out[ok] = np.minimum((r * ng) // n, ng - 1)
    return out


def _stats(arr):
    r = np.asarray(arr, float)
    r = r[np.isfinite(r)]
    if r.size < 30:
        return None
    up = r > 0
    st = {"n": int(r.size),
          "p_up": float(up.mean()),
          "mean": float(r.mean()),
          "mean_up": float(r[up].mean()) if up.sum() >= 5 else float("nan")}
    for q in QS:
        st[f"q{q}"] = float(np.percentile(r, q))
    return st


def pinball(y, q, tau):
    d = y - q
    return np.where(d >= 0, tau * d, (tau - 1) * d)


# ---------------------------------------------------------------------------
# walk-forward over all 3 variants in a single pass
# ---------------------------------------------------------------------------
def run_variants(horizon=10, liquid=0.70, clip_lo=0.5, clip_hi=2.0, alpha=1.0,
                 ng=3, min_cell=60, min_train=12,
                 shuffle_vol=None, shuffle_score=None,
                 scores=None, panel=None):
    """Returns list of per-test-date recs with predictions for variants a/b/c."""
    if panel is None:
        z, meta = H.load_panel()
    else:
        z, meta = panel
    fwd = z[f"fwd{horizon}"].astype(np.float64)
    if scores is None:
        Z = H.neutralize(z, meta)
        cfg = json.load(open(FINAL_CFG))
        scores = H.walk_forward(Z, fwd, meta, cfg)
    scores = scores.copy()
    vol = z["feat"][:, :, meta["feat_names"].index("rvol_20")].astype(np.float64)
    vol = vol.copy()
    if shuffle_score is not None:
        rng = np.random.default_rng(int(shuffle_score))
        for d in range(scores.shape[0]):
            ok = np.where(np.isfinite(scores[d]))[0]
            if ok.size > 1:
                scores[d, ok] = scores[d, ok][rng.permutation(ok.size)]
    if shuffle_vol is not None:
        rng = np.random.default_rng(10_000 + int(shuffle_vol))
        for d in range(vol.shape[0]):
            ok = np.where(np.isfinite(vol[d]))[0]
            if ok.size > 1:
                vol[d, ok] = vol[d, ok][rng.permutation(ok.size)]
    mask = C.liquid_mask(z, liquid)
    regimes = [r["regime"] for r in meta["regimes"]]
    dates = meta["base_dates"]
    D = scores.shape[0]

    # incremental train pools: equivalent to refitting on all d < t each time
    pool_bin = [[] for _ in range(K)]
    pool_cell = [[[] for _ in range(ng)] for _ in range(K)]
    n_train = 0
    recs = []
    # conformal machinery: past OOS normalized residuals per base variant,
    # matured only when the forward window is fully realized before t
    base_vars = ("a", "b", "c", "d")
    step = int(meta.get("step", 10))
    lag = int(np.ceil(horizon / step))
    pool_w = {p: [] for p in base_vars}
    wbuf = []                                # (t_idx, {p: [w...]})
    MIN_W = 1500
    for t in range(D):
        has_score = np.isfinite(scores[t]).any()
        if has_score and n_train >= min_train:
            bin_stats = [_stats(pool_bin[bi]) for bi in range(K)]
            cell_stats = [[(_stats(pool_cell[bi][gi])
                            if len(pool_cell[bi][gi]) >= min_cell else None)
                           for gi in range(ng)] for bi in range(K)]
            b = C.score_bins(scores[t], mask[t], K)
            g = group_ranks(vol[t], mask[t], ng)
            r = fwd[t]
            v = vol[t]
            sel = (b >= 0) & np.isfinite(r)
            if sel.sum() >= 50:
                idx = np.where(sel)[0]
                idx = np.array([j for j in idx if bin_stats[b[j]] is not None])
                if idx.size >= 50:
                    binmed = np.full(K, np.nan)
                    for bi in range(K):
                        vv = v[(b == bi) & np.isfinite(v)]
                        if vv.size >= 10:
                            binmed[bi] = np.median(vv)
                    cellmed = np.full((K, ng), np.nan)
                    for bi in range(K):
                        for gi in range(ng):
                            vv = v[(b == bi) & (g == gi) & np.isfinite(v)]
                            if vv.size >= 5:
                                cellmed[bi, gi] = np.median(vv)
                    rec = {"date": dates[t], "regime": regimes[t],
                           "ret": r[idx], "bin": b[idx]}
                    n = idx.size
                    out = {p: {k: np.empty(n) for k in
                               ("q10", "q50", "q90", "mean_up")}
                           for p in ("a", "aw", "b", "c", "d")}
                    scales_b = np.empty(n)
                    for i, j in enumerate(idx):
                        bs = bin_stats[b[j]]
                        a10, a50, a90, amu = (bs["q10"], bs["q50"],
                                              bs["q90"], bs["mean_up"])
                        out["a"]["q10"][i] = a10
                        out["a"]["q50"][i] = a50
                        out["a"]["q90"][i] = a90
                        out["a"]["mean_up"][i] = amu
                        # variant b: vol-scaled around bin q50
                        s = 1.0
                        if np.isfinite(v[j]) and np.isfinite(binmed[b[j]]) \
                                and binmed[b[j]] > 0 and v[j] > 0:
                            s = float(np.clip((v[j] / binmed[b[j]]) ** alpha,
                                              clip_lo, clip_hi))
                        out["b"]["q10"][i] = a50 + (a10 - a50) * s
                        out["b"]["q50"][i] = a50
                        out["b"]["q90"][i] = a50 + (a90 - a50) * s
                        out["b"]["mean_up"][i] = a50 + (amu - a50) * s
                        scales_b[i] = s
                        # variant c: bin x vol-tercile cell, fallback to bin
                        cs = cell_stats[b[j]][g[j]] if g[j] >= 0 else None
                        if cs is None:
                            c10, c50, c90, cmu = a10, a50, a90, amu
                        else:
                            c10, c50, c90 = cs["q10"], cs["q50"], cs["q90"]
                            cmu = (cs["mean_up"] if np.isfinite(cs["mean_up"])
                                   else amu)
                        out["c"]["q10"][i] = c10
                        out["c"]["q50"][i] = c50
                        out["c"]["q90"][i] = c90
                        out["c"]["mean_up"][i] = cmu
                        # variant d: cell stats + within-cell vol scaling
                        sd = 1.0
                        if g[j] >= 0 and np.isfinite(v[j]) and v[j] > 0 \
                                and np.isfinite(cellmed[b[j], g[j]]) \
                                and cellmed[b[j], g[j]] > 0:
                            sd = float(np.clip(
                                (v[j] / cellmed[b[j], g[j]]) ** alpha,
                                clip_lo, clip_hi))
                        out["d"]["q10"][i] = c50 + (c10 - c50) * sd
                        out["d"]["q50"][i] = c50
                        out["d"]["q90"][i] = c50 + (c90 - c50) * sd
                        out["d"]["mean_up"][i] = c50 + (cmu - c50) * sd
                    # control aw: uniform widen of a by per-date mean b-scale
                    sbar = float(np.mean(scales_b))
                    out["aw"]["q10"] = (out["a"]["q50"]
                                        + (out["a"]["q10"] - out["a"]["q50"]) * sbar)
                    out["aw"]["q50"] = out["a"]["q50"].copy()
                    out["aw"]["q90"] = (out["a"]["q50"]
                                        + (out["a"]["q90"] - out["a"]["q50"]) * sbar)
                    out["aw"]["mean_up"] = (out["a"]["q50"]
                                            + (out["a"]["mean_up"] - out["a"]["q50"]) * sbar)
                    rec["sbar"] = sbar
                    for p in ("a", "aw", "b", "c", "d"):
                        for k in ("q10", "q50", "q90", "mean_up"):
                            rec[f"{p}_{k}"] = out[p][k]
                    # --- conformal: mature past residuals, then apply lambda
                    while wbuf and wbuf[0][0] <= t - lag:
                        _, wd = wbuf.pop(0)
                        for p in base_vars:
                            pool_w[p].extend(wd[p])
                    ready = all(len(pool_w[p]) >= MIN_W for p in base_vars)
                    rec["conformal_ready"] = ready
                    if ready:
                        for p in base_vars:
                            lam = float(np.clip(
                                np.percentile(pool_w[p], 80), 0.6, 1.6))
                            q50p = rec[f"{p}_q50"]
                            for k in ("q10", "q90", "mean_up"):
                                rec[f"{p}_cf_{k}"] = (
                                    q50p + (rec[f"{p}_{k}"] - q50p) * lam)
                            rec[f"{p}_cf_q50"] = q50p
                            rec[f"{p}_cf_lambda"] = lam
                    # this date's normalized residuals -> buffer (used later)
                    wd = {}
                    y = rec["ret"]
                    for p in base_vars:
                        q10p, q50p, q90p = (rec[f"{p}_q10"], rec[f"{p}_q50"],
                                            rec[f"{p}_q90"])
                        hi = np.maximum(q90p - q50p, 1e-9)
                        lo = np.maximum(q50p - q10p, 1e-9)
                        w = np.where(y >= q50p, (y - q50p) / hi,
                                     (q50p - y) / lo)
                        wd[p] = w.tolist()
                    wbuf.append((t, wd))
                    recs.append(rec)
        # accumulate date t into train pools (mirrors caliblib fit_bins logic)
        if has_score:
            b = C.score_bins(scores[t], mask[t], K)
            g = group_ranks(vol[t], mask[t], ng)
            r = fwd[t]
            fin = np.isfinite(r)
            for bi in range(K):
                s2 = (b == bi) & fin
                if s2.any():
                    pool_bin[bi].extend(r[s2].tolist())
                    for gi in range(ng):
                        s3 = s2 & (g == gi)
                        if s3.any():
                            pool_cell[bi][gi].extend(r[s3].tolist())
            n_train += 1
    return recs


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------
def metrics(recs, p):
    """pooled + per-date metrics for variant prefix p in {a,b,c}."""
    if not recs:
        return {"error": "no recs"}
    R = np.concatenate([r["ret"] for r in recs])
    Q10 = np.concatenate([r[f"{p}_q10"] for r in recs])
    Q90 = np.concatenate([r[f"{p}_q90"] for r in recs])
    MU = np.concatenate([r[f"{p}_mean_up"] for r in recs])
    cov = float(np.mean((R >= Q10) & (R <= Q90)))
    width = float(np.mean(Q90 - Q10))
    pin10 = float(np.mean(pinball(R, Q10, 0.10)))
    pin90 = float(np.mean(pinball(R, Q90, 0.90)))
    # per-date series (for paired tests)
    cov_d, pin_d, wid_d = [], [], []
    for r in recs:
        y = r["ret"]
        q10, q90 = r[f"{p}_q10"], r[f"{p}_q90"]
        cov_d.append(float(np.mean((y >= q10) & (y <= q90))))
        pin_d.append(float(np.mean(pinball(y, q10, 0.10) +
                                   pinball(y, q90, 0.90))))
        wid_d.append(float(np.mean(q90 - q10)))
    # E[ret|up] calibration: octiles of predicted mean_up, realized mean of
    # ret | ret>0 within each octile
    upsel = R > 0
    cal = []
    if upsel.sum() > 400 and np.unique(MU).size > 8:
        mu_up, r_up = MU[upsel], R[upsel]
        edges = np.percentile(mu_up, np.linspace(0, 100, 9))
        for i in range(8):
            m = (mu_up >= edges[i]) & (mu_up <= edges[i + 1] if i == 7
                                       else mu_up < edges[i + 1])
            if m.sum() > 100:
                cal.append({"pred": float(mu_up[m].mean()),
                            "real": float(r_up[m].mean()), "n": int(m.sum())})
    cal_mae = (float(np.mean([abs(c["pred"] - c["real"]) for c in cal]))
               if cal else float("nan"))
    cal_slope = float("nan")
    if len(cal) >= 4:
        x = np.array([c["pred"] for c in cal])
        y = np.array([c["real"] for c in cal])
        if x.std() > 0:
            cal_slope = float(np.polyfit(x, y, 1)[0])
    return {"coverage_q10_q90": cov, "mean_width": width,
            "pinball_q10": pin10, "pinball_q90": pin90,
            "pinball_total": pin10 + pin90,
            "mean_up_calibration": {"octiles": cal, "mae": cal_mae,
                                    "slope": cal_slope},
            "_cov_d": cov_d, "_pin_d": pin_d, "_wid_d": wid_d,
            "n_obs": int(R.size), "n_dates": len(recs)}


def _t(a):
    a = np.asarray(a, float)
    if a.size < 3 or a.std(ddof=1) == 0:
        return float("nan")
    return float(a.mean() / (a.std(ddof=1) / np.sqrt(a.size)))


def paired(m_base, m_var):
    """per-date paired comparison variant vs baseline (positive = variant better
    on pinball; coverage compared by distance to 0.80)."""
    pb = np.array(m_base["_pin_d"]) - np.array(m_var["_pin_d"])      # >0 good
    cb = (np.abs(np.array(m_base["_cov_d"]) - 0.80)
          - np.abs(np.array(m_var["_cov_d"]) - 0.80))                # >0 good
    return {"pinball_improve_mean": float(pb.mean()),
            "pinball_improve_t": _t(pb),
            "pinball_improve_pct": float(pb.mean() / np.mean(m_base["_pin_d"]) * 100),
            "pinball_pos_dates_pct": float(np.mean(pb > 0)),
            "cov_err_improve_mean": float(cb.mean()),
            "cov_err_improve_t": _t(cb)}


def strip_private(m):
    return {k: v for k, v in m.items() if not k.startswith("_")}


def filter_recs(recs, drop_year=None, drop_regime=None):
    out = recs
    if drop_year:
        out = [r for r in out if r["date"][:4] != str(drop_year)]
    if drop_regime:
        out = [r for r in out if r["regime"] != drop_regime]
    return out


VARIANTS = ("a", "aw", "b", "c", "d")
CF_VARIANTS = ("a_cf", "b_cf", "c_cf", "d_cf")


def evaluate_all(recs):
    res = {}
    ms = {p: metrics(recs, p) for p in VARIANTS}
    for p in VARIANTS:
        res[p] = strip_private(ms[p])
    for p in ("aw", "b", "c", "d"):
        res[f"{p}_vs_a"] = paired(ms["a"], ms[p])
    res["b_vs_aw"] = paired(ms["aw"], ms["b"])
    res["d_vs_b"] = paired(ms["b"], ms["d"])
    res["d_vs_c"] = paired(ms["c"], ms["d"])
    res["mean_sbar"] = float(np.mean([r["sbar"] for r in recs]))
    # conformal group: only dates where lambda was available
    cf_recs = [r for r in recs if r.get("conformal_ready")]
    if cf_recs:
        cf = {"n_dates": len(cf_recs)}
        msc = {p: metrics(cf_recs, p) for p in CF_VARIANTS + ("a", "d")}
        for p in CF_VARIANTS:
            cf[p] = strip_private(msc[p])
        cf["a_on_subset"] = strip_private(msc["a"])
        for p in ("b_cf", "c_cf", "d_cf"):
            cf[f"{p}_vs_a_cf"] = paired(msc["a_cf"], msc[p])
        cf["d_cf_vs_d"] = paired(msc["d"], msc["d_cf"])
        for p in ("a", "b", "c", "d"):
            cf[f"mean_lambda_{p}"] = float(np.mean(
                [r[f"{p}_cf_lambda"] for r in cf_recs]))
        res["conformal"] = cf
    return res, ms


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--liquid", type=float, default=0.70)
    ap.add_argument("--clip-lo", type=float, default=0.5)
    ap.add_argument("--clip-hi", type=float, default=2.0)
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--ng", type=int, default=3)
    ap.add_argument("--min-cell", type=int, default=60)
    ap.add_argument("--shuffle-vol", type=int, default=None)
    ap.add_argument("--shuffle-score", type=int, default=None)
    ap.add_argument("--drop-year", type=str, default=None)
    ap.add_argument("--drop-regime", type=str, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    recs = run_variants(a.horizon, a.liquid, a.clip_lo, a.clip_hi, a.alpha,
                        a.ng, a.min_cell,
                        shuffle_vol=a.shuffle_vol, shuffle_score=a.shuffle_score)
    recs = filter_recs(recs, a.drop_year, a.drop_regime)
    res, _ = evaluate_all(recs)
    res["spec"] = vars(a)
    if a.out:
        json.dump(res, open(a.out, "w"), indent=1, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
