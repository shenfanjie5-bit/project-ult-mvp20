#!/usr/bin/env python3
"""industry_chain family — full eval per the audited harness conventions.

Variants per factor:
  raw       factor as-is (deterministic tie-break jitter, seed=7)
  sizeneut  winsor-z -> residualize on [1, ln_mv] -> rank-z  (NO industry dummies:
            these are industry-level signals; industry dummies span broadcast
            factors and annihilate them by construction)
  indneut   full harness-style neutralization incl. industry dummies (sanity
            check only — expected ~0 for broadcast factors)

Metrics: harness.evaluate (per-date spearman IC, decile curve, liquid-70
top-decile excess vs universe mean = decision metric, by-year, by-regime),
up-rate Q5-Q1 disc, liquid-50 re-check, shuffle nulls (stock-level and
industry-label-level, 4 seeds each), industry-level IC supplement (N=12).
"""
import os, sys, json
import numpy as np

os.environ["DOCKCASE_WRITEBACK"] = "0"
ROOT = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "factor_research", "model"))

import harness
from harness import _winsor_z, _rank_z, _deciles, _spearman, evaluate, load_panel
import caliblib

REPORT = os.path.join(ROOT, "factor_research", "model", "reports", "enh_industry_chain.json")
FNPZ = os.path.join(ROOT, "factor_research", "enhancers", "industry_chain", "factors_industry_chain.npz")

z, meta = load_panel()
F = np.load(FNPZ)
fnames = [str(x) for x in F["fnames"]]
fwd = {5: z["fwd5"].astype(np.float64), 10: z["fwd10"].astype(np.float64), 20: z["fwd20"].astype(np.float64)}
lnmv = z["ln_mv"].astype(np.float64)
ind = z["industry"].astype(int)
D, N = lnmv.shape
K = len(meta["industry_names"])
liq70 = caliblib.liquid_mask(z, 0.70)
liq50 = caliblib.liquid_mask(z, 0.50)
RNG = np.random.default_rng(7)
JIT = RNG.standard_normal((D, N))  # one fixed jitter field reused everywhere


def jitter(Fm):
    out = Fm.copy()
    for d in range(D):
        row = out[d]
        ok = np.isfinite(row)
        if ok.sum() < 10:
            continue
        sd = np.nanstd(row)
        eps = (sd if sd > 0 else 1.0) * 1e-7
        out[d, ok] = row[ok] + eps * JIT[d, ok]
    return out


def sizeneut(Fm):
    out = np.full((D, N), np.nan)
    for d in range(D):
        v = _winsor_z(Fm[d])
        mv = lnmv[d]
        ok = np.isfinite(v) & np.isfinite(mv)
        if ok.sum() < 20:
            out[d] = _rank_z(v)
            continue
        X = np.column_stack([np.ones(ok.sum()), mv[ok]])
        beta, *_ = np.linalg.lstsq(X, v[ok], rcond=None)
        rv = np.full(N, np.nan)
        rv[ok] = v[ok] - X @ beta
        out[d] = _rank_z(rv)
    return out


def indneut(Fm):
    """harness-style: winsor-z -> residualize [1, ln_mv, industry dummies] -> rank-z"""
    Dind = np.zeros((N, K))
    for k in range(K):
        Dind[:, k] = (ind == k).astype(float)
    out = np.full((D, N), np.nan)
    for d in range(D):
        v = _winsor_z(Fm[d])
        mv = lnmv[d]
        ok = np.isfinite(v) & np.isfinite(mv)
        if ok.sum() < 20:
            continue
        di = Dind[ok]
        di = di[:, di.sum(0) > 0]
        X = np.column_stack([np.ones(ok.sum()), mv[ok], di])
        beta, *_ = np.linalg.lstsq(X, v[ok], rcond=None)
        rv = np.full(N, np.nan)
        rv[ok] = v[ok] - X @ beta
        out[d] = _rank_z(rv)
    return out


def up_disc(scores, h, mask):
    """per-date up-rate(Q5) - up-rate(Q1), quintiles among masked; mean, t."""
    vals = []
    rt_all = fwd[h]
    for d in range(D):
        sc = np.where(mask[d], scores[d], np.nan)
        rt = rt_all[d]
        ok = np.isfinite(sc) & np.isfinite(rt)
        if ok.sum() < 50:
            continue
        s, r = sc[ok], rt[ok]
        order = np.argsort(s)
        gs = np.array_split(order, 5)
        u5 = (r[gs[-1]] > 0).mean()
        u1 = (r[gs[0]] > 0).mean()
        vals.append(u5 - u1)
    a = np.array(vals)
    if a.size < 3:
        return {"mean": None, "t": None, "n": int(a.size)}
    se = a.std(ddof=1) / np.sqrt(a.size)
    return {"mean": round(float(a.mean()), 5), "t": round(float(a.mean() / se), 2), "n": int(a.size)}


def top_excess_series(scores, h, mask):
    rt_all = fwd[h]
    vals = []
    for d in range(D):
        sc = np.where(mask[d], scores[d], np.nan)
        rt = rt_all[d]
        ok = np.isfinite(sc) & np.isfinite(rt)
        if ok.sum() < 50:
            continue
        dec = _deciles(sc, rt, 10)
        if dec is None:
            continue
        vals.append(dec[-1] - float(np.nanmean(rt[ok])))
    return np.array(vals)


def mt(a):
    if a.size < 3:
        return (None, None)
    se = a.std(ddof=1) / np.sqrt(a.size)
    return (round(float(a.mean()), 5), round(float(a.mean() / se), 2))


def shuffle_stock(scores, seed):
    rng = np.random.default_rng(seed)
    out = scores.copy()
    for d in range(D):
        ok = np.isfinite(out[d])
        v = out[d, ok]
        rng.shuffle(v)
        out[d, ok] = v
    return out


def shuffle_industry(Fm, seed):
    """permute which industry gets which industry-level signal value, per date.
    Uses the industry mean of the factor as the signal (exact for broadcast
    factors; close approximation for LOO c1)."""
    rng = np.random.default_rng(seed)
    out = np.full((D, N), np.nan)
    for d in range(D):
        sig = np.full(K, np.nan)
        for k in range(K):
            v = Fm[d, ind == k]
            if np.isfinite(v).sum() >= 5:
                sig[k] = np.nanmean(v)
        kk = np.where(np.isfinite(sig))[0]
        if kk.size < 4:
            continue
        perm = rng.permutation(kk)
        for a, b in zip(kk, perm):
            out[d, ind == a] = sig[b]
    return jitter(out)


def slim(ev):
    """compact the harness.evaluate output"""
    if "error" in ev:
        return ev
    o = {}
    for k in ("ic", "top_excess_uni", "d10_d1", "top_hit"):
        b = ev.get(k)
        o[k] = None if not b else {kk: (round(b[kk], 5) if isinstance(b[kk], float) else b[kk])
                                   for kk in ("mean", "t", "pct_pos", "n_dates")}
    o["decile_curve"] = [round(x, 5) for x in ev.get("decile_curve", [])]
    o["by_year"] = {y: {"top_excess": (round(v["top_excess_uni"]["mean"], 5), round(v["top_excess_uni"]["t"], 2))
                        if v.get("top_excess_uni") else None, "n": v["n"]}
                    for y, v in ev.get("by_year", {}).items()}
    o["by_regime"] = {g: {"top_excess": (round(v["top_excess_uni"]["mean"], 5), round(v["top_excess_uni"]["t"], 2))
                          if v.get("top_excess_uni") else None, "n": v["n"]}
                      for g, v in ev.get("by_regime", {}).items()}
    return o


def main():
    indlevel = np.load(FNPZ.replace(".npz", "_indlevel.npz"))
    M20, M60 = indlevel["M20"], indlevel["M60"]

    # industry EW fwd returns for industry-level IC
    indfwd = {}
    for h in (10, 20):
        Mf = np.full((D, K), np.nan)
        for k in range(K):
            sub = fwd[h][:, ind == k]
            n = np.isfinite(sub).sum(1)
            with np.errstate(invalid="ignore"):
                Mf[:, k] = np.where(n >= 5, np.nanmean(sub, 1), np.nan)
        indfwd[h] = Mf

    report = {"family": "industry_chain", "n_factors": len(fnames),
              "variants": ["raw", "sizeneut", "indneut(sanity)"],
              "factors": {}}

    for nme in fnames:
        Fm = F[nme].astype(np.float64)
        cov = np.isfinite(Fm).mean(1)
        raw = jitter(Fm)
        sn = sizeneut(jitter(Fm))
        inn = indneut(jitter(Fm))
        ent = {"coverage_mean": round(float(cov.mean()), 4)}
        for vname, S in (("raw", raw), ("sizeneut", sn), ("indneut", inn)):
            vent = {}
            for h in (5, 10, 20):
                ev = evaluate(S, fwd[h], meta, h, eval_mask=liq70)
                vent[f"h{h}"] = slim(ev)
            vent["h10_updisc"] = up_disc(S, 10, liq70)
            # liquid-50 re-check (top excess only)
            te50_10 = top_excess_series(S, 10, liq50)
            te50_20 = top_excess_series(S, 20, liq50)
            vent["liq50_top_excess"] = {"h10": mt(te50_10), "h20": mt(te50_20)}
            ent[vname] = vent
        # shuffle nulls on raw, h10, liq70 decision metric
        nulls_stock, nulls_indlbl = [], []
        for seed in (11, 12, 13, 14):
            te = top_excess_series(shuffle_stock(raw, seed), 10, liq70)
            nulls_stock.append(mt(te))
            te = top_excess_series(shuffle_industry(Fm, seed), 10, liq70)
            nulls_indlbl.append(mt(te))
        ent["shuffle_null_h10"] = {"stock": nulls_stock, "industry_label": nulls_indlbl}
        report["factors"][nme] = ent
        print(f"== {nme} done")

    # industry-level IC supplement (N=12 cross-section)
    indic = {}
    for sig_name, M in (("indmom20", M20), ("indmom60", M60)):
        for h in (10, 20):
            ics = []
            for d in range(D):
                ok = np.isfinite(M[d]) & np.isfinite(indfwd[h][d])
                if ok.sum() < 8:
                    continue
                ics.append(_spearman(M[d, ok], indfwd[h][d, ok]))
            a = np.array([x for x in ics if np.isfinite(x)])
            indic[f"{sig_name}_h{h}"] = {"mean_ic": round(float(a.mean()), 4),
                                         "t": round(float(a.mean() / (a.std(ddof=1) / np.sqrt(a.size))), 2),
                                         "n_dates": int(a.size)}
    report["industry_level_ic_N12"] = indic

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    json.dump(report, open(REPORT, "w"), indent=1)
    print("saved", REPORT)


if __name__ == "__main__":
    main()
