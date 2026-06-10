#!/usr/bin/env python3
"""Fusion study: mag score (ew sue,npq_yoy) x prob score (ew rvol/ivol/max5/turn/ep).

Per-date rank-average fusion with weight w_mag; for each w report
  (a) liquid-70 top-decile excess fwd return (h10, h20)  [magnitude edge]
  (b) within-date up-rate discrimination via the caliblib calibrated pipeline
      (h10, target abs & rel)                            [P(up) edge]

All scores come from harness.walk_forward (walk-forward, PIT-safe). Fusion is a
fixed per-date rank transform of two walk-forward scores -> no extra leak path.
Null test: within-date shuffle of the FUSED score (scores carry no info ->
both metrics must ~0).

Usage:
  fusion_product.py sweep
  fusion_product.py honesty --w 0.5
  fusion_product.py realbase
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

ROOT = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from factor_research.model import harness as H            # noqa: E402
from factor_research.model import caliblib as C           # noqa: E402

MAG_CFG = {"name": "mag", "method": "ew_signed",
           "features": ["sue", "npq_yoy"],
           "params": {"min_cov": 0.5}, "min_train_dates": 12}
PROB_CFG = {"name": "prob", "method": "ew_signed",
            "features": ["rvol_20", "ivol_60", "max5", "turnover_20", "ep_ttm"],
            "params": {"min_cov": 0.5}, "min_train_dates": 12}
WEIGHTS = [1.0, 0.7, 0.5, 0.3, 0.0]


# ----------------------------------------------------------------------------
# score building
# ----------------------------------------------------------------------------
def _rank01(v, ok):
    """rank in (0,1) over ok entries; NaN elsewhere."""
    out = np.full(v.shape, np.nan)
    idx = np.where(ok)[0]
    if idx.size < 10:
        return out
    r = np.argsort(np.argsort(v[idx]))
    out[idx] = (r + 1.0) / (idx.size + 1.0)
    return out


def fuse(mag, prob, w):
    """per-date rank-average; requires BOTH scores finite (fair across w)."""
    D, N = mag.shape
    out = np.full((D, N), np.nan)
    for d in range(D):
        ok = np.isfinite(mag[d]) & np.isfinite(prob[d])
        if ok.sum() < 30:
            continue
        rm = _rank01(mag[d], ok)
        rp = _rank01(prob[d], ok)
        out[d] = w * rm + (1.0 - w) * rp
    return out


def build_scores():
    z, meta = H.load_panel()
    Z = H.neutralize(z, meta)
    fwd10 = z["fwd10"].astype(np.float64)
    mag = H.walk_forward(Z, fwd10, meta, MAG_CFG)    # ew_signed: fwd unused in fit
    prob = H.walk_forward(Z, fwd10, meta, PROB_CFG)
    return z, meta, mag, prob


# ----------------------------------------------------------------------------
# metric (a): liquid top-decile excess, harness-style
# ----------------------------------------------------------------------------
def mag_metric(scores, z, meta, horizon, liquid=0.70, drop_regime=None,
               drop_year=None, shuffle=None):
    fwd = z[f"fwd{horizon}"].astype(np.float64)
    sc = scores.copy()
    if shuffle is not None:
        rng = np.random.default_rng(int(shuffle))
        for d in range(sc.shape[0]):
            ok = np.where(np.isfinite(sc[d]))[0]
            if ok.size > 1:
                sc[d, ok] = sc[d, ok][rng.permutation(ok.size)]
    mask = C.liquid_mask(z, liquid)
    rep = H.evaluate(sc, fwd, meta, horizon, eval_mask=mask,
                     drop_regime=drop_regime, drop_year=drop_year)
    te = rep.get("top_excess_uni") or {}
    return {"mean": te.get("mean"), "t": te.get("t"), "n_dates": te.get("n_dates"),
            "pct_pos": te.get("pct_pos"), "d10_d1": (rep.get("d10_d1") or {}).get("mean")}


# ----------------------------------------------------------------------------
# metric (b): caliblib calibrated pipeline with INJECTED scores
# (mirrors caliblib.walk_forward_calibrated after the score step)
# ----------------------------------------------------------------------------
def calib_recs(scores, z, meta, horizon=10, liquid=0.70, variant="empirical",
               min_train=12, shrink=0.5, shuffle=None, target="abs"):
    fwd = z[f"fwd{horizon}"].astype(np.float64)
    sc = scores.copy()
    if target == "rel":
        mask0 = C.liquid_mask(z, liquid)
        fwd = fwd.copy()
        for d in range(fwd.shape[0]):
            ok = np.isfinite(fwd[d]) & mask0[d]
            if ok.sum() > 50:
                fwd[d] = fwd[d] - np.median(fwd[d][ok])
    if shuffle is not None:
        rng = np.random.default_rng(int(shuffle))
        for d in range(sc.shape[0]):
            ok = np.where(np.isfinite(sc[d]))[0]
            if ok.size > 1:
                sc[d, ok] = sc[d, ok][rng.permutation(ok.size)]
    mask = C.liquid_mask(z, liquid)
    regimes = [r["regime"] for r in meta["regimes"]]
    dates = meta["base_dates"]
    D = sc.shape[0]
    recs = []
    for t in range(D):
        if t < min_train or not np.isfinite(sc[t]).any():
            continue
        train_idx = [d for d in range(t) if np.isfinite(sc[d]).any()]
        if len(train_idx) < min_train:
            continue
        reg = regimes[t] if variant == "empirical_regime" else None
        bins_stats, used_reg = C.fit_bins(
            sc, fwd, mask, train_idx,
            regimes=regimes if variant == "empirical_regime" else None,
            test_regime=reg, shrink=shrink)
        b = C.score_bins(sc[t], mask[t])
        r = fwd[t]
        sel = (b >= 0) & np.isfinite(r)
        if sel.sum() < 50:
            continue
        idx = np.where(sel)[0]
        pred = [bins_stats[b[j]] for j in idx]
        keep = [i for i, p in enumerate(pred) if p is not None]
        idx = idx[keep]
        pred = [pred[i] for i in keep]
        recs.append({
            "date": dates[t], "regime": regimes[t], "used_regime_pool": used_reg,
            "bin": b[idx], "ret": r[idx],
            "p_up": np.array([p["p_up"] for p in pred]),
            "exp": np.array([p["mean"] for p in pred]),
            "q10": np.array([p["q10"] for p in pred]),
            "q90": np.array([p["q90"] for p in pred]),
            "mean_up": np.array([p["mean_up"] for p in pred]),
            "train_base_rate": float(np.mean([
                s["p_up"] for s in
                (C.fit_bins(sc, fwd, mask, train_idx)[0]) if s])),
        })
    return recs


def disc_metric(scores, z, meta, horizon=10, liquid=0.70, target="abs",
                shuffle=None, drop_regime=None, drop_year=None):
    recs = calib_recs(scores, z, meta, horizon=horizon, liquid=liquid,
                      shuffle=shuffle, target=target)
    if drop_regime:
        recs = [r for r in recs if r["regime"] != drop_regime]
    if drop_year:
        recs = [r for r in recs if r["date"][:4] != str(drop_year)]
    rep = C.evaluate(recs)
    d = rep.get("discrimination_up_rate_top_minus_bottom", {})
    return {"mean": d.get("mean"), "t": d.get("t"), "n": d.get("n"),
            "pos_pct": d.get("pos_pct"),
            "brier_skill": rep.get("brier_skill"),
            "coverage": rep.get("interval_coverage_q10_q90")}


# ----------------------------------------------------------------------------
# commands
# ----------------------------------------------------------------------------
def cmd_sweep(args):
    z, meta, mag, prob = build_scores()
    out = {}
    for w in WEIGHTS:
        f = fuse(mag, prob, w)
        row = {
            "top_excess_h10": mag_metric(f, z, meta, 10),
            "top_excess_h20": mag_metric(f, z, meta, 20),
            "disc_h10_abs": disc_metric(f, z, meta, 10, target="abs"),
            "disc_h10_rel": disc_metric(f, z, meta, 10, target="rel"),
        }
        out[f"w_mag={w}"] = row
        print(f"w={w}: te20={row['top_excess_h20']['mean']:+.4f} "
              f"(t{row['top_excess_h20']['t']:.2f}) "
              f"te10={row['top_excess_h10']['mean']:+.4f} "
              f"(t{row['top_excess_h10']['t']:.2f}) "
              f"disc_abs={row['disc_h10_abs']['mean']*100:+.2f}pp "
              f"(t{row['disc_h10_abs']['t']:.2f}) "
              f"disc_rel={row['disc_h10_rel']['mean']*100:+.2f}pp "
              f"(t{row['disc_h10_rel']['t']:.2f})", flush=True)
    json.dump(out, open(args.out, "w"), indent=1, default=float)
    print("saved", args.out)


def cmd_honesty(args):
    z, meta, mag, prob = build_scores()
    f = fuse(mag, prob, args.w)
    out = {"w_mag": args.w}
    out["base_l70"] = {
        "top_excess_h20": mag_metric(f, z, meta, 20),
        "top_excess_h10": mag_metric(f, z, meta, 10),
        "disc_h10_abs": disc_metric(f, z, meta, 10, target="abs"),
        "disc_h10_rel": disc_metric(f, z, meta, 10, target="rel"),
    }
    out["liquid_50"] = {
        "top_excess_h20": mag_metric(f, z, meta, 20, liquid=0.50),
        "disc_h10_abs": disc_metric(f, z, meta, 10, liquid=0.50, target="abs"),
        "disc_h10_rel": disc_metric(f, z, meta, 10, liquid=0.50, target="rel"),
    }
    out["shuffle"] = {}
    for seed in [1, 2, 3, 4, 5, 6]:
        out["shuffle"][seed] = {
            "top_excess_h20": mag_metric(f, z, meta, 20, shuffle=seed),
            "disc_h10_abs": disc_metric(f, z, meta, 10, target="abs", shuffle=seed),
            "disc_h10_rel": disc_metric(f, z, meta, 10, target="rel", shuffle=seed),
        }
        print("shuffle", seed, "done", flush=True)
    out["drop_year"] = {}
    for y in ["2024", "2025", "2026"]:
        out["drop_year"][y] = {
            "top_excess_h20": mag_metric(f, z, meta, 20, drop_year=y),
            "disc_h10_abs": disc_metric(f, z, meta, 10, target="abs", drop_year=y),
            "disc_h10_rel": disc_metric(f, z, meta, 10, target="rel", drop_year=y),
        }
    out["drop_regime"] = {}
    for g in ["up_calm", "up_turbulent", "down_calm", "down_turbulent"]:
        out["drop_regime"][g] = {
            "top_excess_h20": mag_metric(f, z, meta, 20, drop_regime=g),
            "disc_h10_abs": disc_metric(f, z, meta, 10, target="abs", drop_regime=g),
            "disc_h10_rel": disc_metric(f, z, meta, 10, target="rel", drop_regime=g),
        }
    json.dump(out, open(args.out, "w"), indent=1, default=float)
    print("saved", args.out)


# ----------------------------------------------------------------------------
# realbase head-to-head: base_score vs prob/mag/fused as P(up) predictors
# ----------------------------------------------------------------------------
def cmd_realbase(args):
    import sqlite3
    zr = np.load(os.path.join(ROOT, "factor_research/model/panel_realbase.npz"),
                 allow_pickle=True)
    cols = list(zr["cols"])
    dates = list(zr["base_dates"])
    regimes = list(zr["regimes"])
    col_idx = {c: i for i, c in enumerate(cols)}
    zdict = {"feat": zr["feat"], "ln_mv": zr["ln_mv"], "industry": zr["industry"]}
    Z = H.neutralize(zdict, None, cache=False)          # per-date cross-sectional
    names = json.load(open(os.path.join(
        ROOT, "factor_research/model/panel_meta.json")))["feat_names"]

    def ew(feats):
        idx = [names.index(f) for f in feats]
        signs = np.array([H.SIGN_PRIOR[f] for f in feats], float)
        D = Z.shape[0]
        out = np.full((D, Z.shape[1]), np.nan)
        for d in range(D):
            Xi, keep = H._impute0_coverage(Z[d][:, idx], 0.5)
            s = Xi @ signs
            s[~keep] = np.nan
            out[d] = s
        return out

    mag = ew(MAG_CFG["features"])
    prob = ew(PROB_CFG["features"])

    con = sqlite3.connect(
        "file:" + os.path.join(ROOT, "factor_research/pit_extra/realbase.sqlite")
        + "?mode=ro", uri=True)
    rows = con.execute(
        "SELECT ts_code, base_date, base_score FROM scores").fetchall()
    bs = {}
    for c, d, v in rows:
        bs.setdefault(d, {})[c] = v

    fwd10 = zr["fwd10"].astype(np.float64)
    fwd20 = zr["fwd20"].astype(np.float64)

    per_date = []
    for di, d in enumerate(dates):
        cell = bs.get(str(d), {})
        ids = [col_idx[c] for c in cell if c in col_idx]
        codes = [c for c in cell if c in col_idx]
        if len(ids) < 100:
            continue
        ids = np.array(ids)
        b = np.array([cell[c] for c in codes], float)
        r10 = fwd10[di, ids]
        r20 = fwd20[di, ids]
        m = mag[di, ids]
        p = prob[di, ids]
        # fused candidates within the cell
        okf = np.isfinite(m) & np.isfinite(p)
        fus = {}
        for w in [0.7, 0.5, 0.3]:
            rm = _rank01(m, okf)
            rp = _rank01(p, okf)
            fus[w] = w * rm + (1 - w) * rp
        ok = np.isfinite(b) & np.isfinite(r10)
        if ok.sum() < 100:
            continue
        med = np.median(r10[ok])
        y_up = (r10 > 0).astype(float)
        y_beat = (r10 > med).astype(float)
        y_up20 = (r20 > 0).astype(float)

        def ic(s, y, okx):
            o = okx & np.isfinite(s) & np.isfinite(y)
            return H._spearman(s[o], y[o]) if o.sum() >= 50 else np.nan

        def disc(s, y, okx):
            o = okx & np.isfinite(s) & np.isfinite(y)
            if o.sum() < 50:
                return np.nan
            sv, yv = s[o], y[o]
            lo, hi = np.percentile(sv, [20, 80])
            a, bm = sv <= lo, sv >= hi
            return float(yv[bm].mean() - yv[a].mean())

        rec = {"date": str(d), "regime": str(regimes[di]), "n": int(ok.sum()),
               "ic_base_up": ic(b, y_up, ok), "ic_base_beat": ic(b, y_beat, ok),
               "ic_prob_up": ic(p, y_up, ok), "ic_prob_beat": ic(p, y_beat, ok),
               "ic_mag_up": ic(m, y_up, ok), "ic_mag_beat": ic(m, y_beat, ok),
               "ic_base_up20": ic(b, y_up20, np.isfinite(b) & np.isfinite(r20)),
               "ic_prob_up20": ic(p, y_up20, np.isfinite(p) & np.isfinite(r20)),
               "ic_base_ret10": ic(b, r10, ok), "ic_prob_ret10": ic(p, r10, ok),
               "disc_base_up": disc(b, y_up, ok), "disc_prob_up": disc(p, y_up, ok),
               "disc_base_beat": disc(b, y_beat, ok),
               "disc_prob_beat": disc(p, y_beat, ok)}
        for w, fv in fus.items():
            rec[f"ic_fused{w}_up"] = ic(fv, y_up, ok)
            rec[f"ic_fused{w}_beat"] = ic(fv, y_beat, ok)
        per_date.append(rec)

    def agg(key):
        v = np.array([r[key] for r in per_date if np.isfinite(r.get(key, np.nan))])
        if v.size < 3:
            return None
        t = float(v.mean() / (v.std(ddof=1) / np.sqrt(v.size)))
        return {"mean": float(v.mean()), "t": t, "n": int(v.size),
                "pos_pct": float((v > 0).mean()),
                "min": float(v.min()), "max": float(v.max())}

    keys = [k for k in per_date[0] if k not in ("date", "regime", "n")]
    out = {"n_dates": len(per_date), "aggregate": {k: agg(k) for k in keys}}
    # regime split for the headline comparison
    out["by_regime"] = {}
    for g in sorted(set(r["regime"] for r in per_date)):
        sub = [r for r in per_date if r["regime"] == g]
        out["by_regime"][g] = {
            "n": len(sub),
            "ic_base_up": float(np.nanmean([r["ic_base_up"] for r in sub])),
            "ic_prob_up": float(np.nanmean([r["ic_prob_up"] for r in sub])),
            "ic_base_beat": float(np.nanmean([r["ic_base_beat"] for r in sub])),
            "ic_prob_beat": float(np.nanmean([r["ic_prob_beat"] for r in sub])),
        }
    out["per_date"] = per_date
    json.dump(out, open(args.out, "w"), indent=1, default=float)
    for k in keys:
        a = out["aggregate"][k]
        if a:
            print(f"{k:22s} mean={a['mean']:+.4f} t={a['t']:+.2f} "
                  f"pos={a['pos_pct']:.2f}")
    print("saved", args.out)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("sweep")
    s1.add_argument("--out", default="/tmp/fusion_sweep.json")
    s2 = sub.add_parser("honesty")
    s2.add_argument("--w", type=float, required=True)
    s2.add_argument("--out", default="/tmp/fusion_honesty.json")
    s3 = sub.add_parser("realbase")
    s3.add_argument("--out", default="/tmp/fusion_realbase.json")
    a = ap.parse_args()
    {"sweep": cmd_sweep, "honesty": cmd_honesty, "realbase": cmd_realbase}[a.cmd](a)


if __name__ == "__main__":
    main()
