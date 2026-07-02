#!/usr/bin/env python3
"""Evaluate catalyst-timing + big-money-residual factors per the audited protocol.

Per factor (raw + neutralized):
  - per-date spearman IC vs fwd{5,10,20}: mean, t, pos%
  - liquid-70 top-bucket excess vs universe mean (decision metric), bottom tail,
    full bucket curve, h5/h10/h20
  - up-rate Q5-Q1 disc (h10)
  - by-year / by-regime splits (h10 top excess)
  - liquid-50 recheck (h10)
  - within-date shuffle null, 4 seeds (h10 top excess)
  - rank-corr with panel sue / npq_yoy / mom_6_1 / strev / turnover_20

KEY QUESTION (Part 1): incremental value of fresh forecast surprise over the
validated PEAD layer -> paired per-date diff of liquid-70 top-decile excess:
  blend(rz_sue, rz_f1_fc60) vs rz_sue alone (and vs ew(sue,npq_yoy)).

Bucketing: k=10 when every usable date has >=100 covered liquid names,
else k=5 (sparse event factors); dates with <30 covered names are skipped
(count reported). Sparse factors stay NaN where unknown — never filled with 0.
"""
import os, sys, json
import numpy as np

PROJ = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
sys.path.insert(0, os.path.join(PROJ, "factor_research/model"))
os.environ["DOCKCASE_WRITEBACK"] = "0"

from harness import load_panel, _winsor_z, _rank_z   # noqa: E402
from caliblib import liquid_mask                      # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
z, meta = load_panel(os.path.join(PROJ, "factor_research/model/panel.npz"))
BASE = meta["base_dates"]; COLS = meta["cols"]
D, N = len(BASE), len(COLS)
FWD = {5: z["fwd5"].astype(np.float64), 10: z["fwd10"].astype(np.float64), 20: z["fwd20"].astype(np.float64)}
LNMV = z["ln_mv"].astype(np.float64)
IND = z["industry"].astype(int)
FEAT = z["feat"].astype(np.float64)
FN = meta["feat_names"]
SUE = FEAT[:, :, FN.index("sue")]
NPQ = FEAT[:, :, FN.index("npq_yoy")]
REF = {"sue": SUE, "npq_yoy": NPQ, "mom_6_1": FEAT[:, :, FN.index("mom_6_1")],
       "strev": FEAT[:, :, FN.index("strev")], "turnover_20": FEAT[:, :, FN.index("turnover_20")],
       "ln_mv": LNMV}
REG = {r["date"]: r["regime"] for r in meta["regimes"]}
L70 = liquid_mask(z, 0.70)
L50 = liquid_mask(z, 0.50)

FX = np.load(os.path.join(HERE, "factors.npz"))
rng0 = np.random.default_rng(20260610)


def spearman(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 10:
        return np.nan
    ra = np.argsort(np.argsort(a[ok])).astype(float)
    rb = np.argsort(np.argsort(b[ok])).astype(float)
    sa, sb = ra.std(), rb.std()
    if sa <= 0 or sb <= 0:
        return np.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def neut_one(F):
    """mirror harness.neutralize for a single factor matrix [D,N]."""
    ind_u = sorted(set(int(i) for i in IND if i >= 0))
    Dind = np.zeros((N, len(ind_u)))
    for kk, c in enumerate(ind_u):
        Dind[:, kk] = (IND == c).astype(float)
    out = np.full((D, N), np.nan)
    for d in range(D):
        v = _winsor_z(F[d])
        mv = LNMV[d]
        ok = np.isfinite(v) & np.isfinite(mv)
        if ok.sum() < 20:
            out[d] = _rank_z(v)
            continue
        di = Dind[ok]
        di = di[:, di.sum(0) > 0]
        X = np.column_stack([np.ones(ok.sum()), mv[ok], di])
        try:
            beta, *_ = np.linalg.lstsq(X, v[ok], rcond=None)
            resid = v[ok] - X @ beta
        except Exception:
            resid = v[ok] - v[ok].mean()
        rv = np.full(N, np.nan)
        rv[ok] = resid
        out[d] = _rank_z(rv)
    return out


def agg(vals):
    v = np.array([x for x in vals if np.isfinite(x)])
    if len(v) < 4:
        return {"mean": None, "t": None, "pos_pct": None, "n_dates": int(len(v))}
    t = float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))) if v.std(ddof=1) > 0 else None
    return {"mean": round(float(v.mean()), 5), "t": round(t, 2) if t is not None else None,
            "pos_pct": round(100.0 * float((v > 0).mean()), 1), "n_dates": int(len(v))}


def bucket_stats(F, h, mask, k, min_cov=30):
    """per-date top/bottom bucket excess vs masked-universe mean + curve."""
    r = FWD[h]
    top_u, top_c, bot_u, curves, ns = [], [], [], [], []
    dates_used = []
    for d in range(D):
        m = mask[d] & np.isfinite(r[d])
        cov = m & np.isfinite(F[d])
        n = int(cov.sum())
        if n < min_cov or m.sum() < 100:
            continue
        f = F[d][cov]; rr = r[d][cov]
        order = np.argsort(np.argsort(f))
        b = np.minimum((order * k) // n, k - 1)
        umean = float(r[d][m].mean()); cmean = float(rr.mean())
        tmean = float(rr[b == k - 1].mean()); bmean = float(rr[b == 0].mean())
        top_u.append(tmean - umean); top_c.append(tmean - cmean); bot_u.append(bmean - umean)
        curves.append([float(rr[b == q].mean()) - umean if (b == q).any() else np.nan for q in range(k)])
        ns.append(n); dates_used.append(d)
    out = {"k": k, "n_dates_used": len(dates_used), "median_covered_n": int(np.median(ns)) if ns else 0,
           "top_excess_vs_universe": agg(top_u), "top_excess_vs_covered": agg(top_c),
           "bottom_excess_vs_universe": agg(bot_u)}
    if curves:
        C = np.array(curves, dtype=float)
        out["bucket_curve_excess"] = [round(float(np.nanmean(C[:, q])), 5) for q in range(k)]
    return out, dict(zip(dates_used, top_u))


def updisc(F, h, mask, min_cov=30):
    r = FWD[h]; vals = []
    for d in range(D):
        m = mask[d] & np.isfinite(r[d])
        cov = m & np.isfinite(F[d])
        n = int(cov.sum())
        if n < min_cov:
            continue
        f = F[d][cov]; rr = r[d][cov]
        order = np.argsort(np.argsort(f))
        b = np.minimum((order * 5) // n, 4)
        vals.append(float((rr[b == 4] > 0).mean() - (rr[b == 0] > 0).mean()))
    return agg(vals)


def splits(per_date_top):
    by_year, by_reg = {}, {}
    for d, v in per_date_top.items():
        y = BASE[d][:4]; g = REG.get(BASE[d], "?")
        by_year.setdefault(y, []).append(v)
        by_reg.setdefault(g, []).append(v)
    return ({y: agg(v) for y, v in sorted(by_year.items())},
            {g: agg(v) for g, v in sorted(by_reg.items())})


def shuffle_null(F, h, mask, k, seeds=(1, 2, 3, 4), min_cov=30):
    outs = []
    for s in seeds:
        rng = np.random.default_rng(20260610 + s)
        Fs = np.full_like(F, np.nan)
        for d in range(D):
            cov = mask[d] & np.isfinite(F[d]) & np.isfinite(FWD[h][d])
            idx = np.where(cov)[0]
            if len(idx) < min_cov:
                continue
            Fs[d, idx] = F[d, idx][rng.permutation(len(idx))]
        st, _ = bucket_stats(Fs, h, mask, k, min_cov)
        outs.append(st["top_excess_vs_universe"]["mean"])
    outs = [o for o in outs if o is not None]
    return {"seeds": len(outs), "means": outs,
            "null_max_abs": round(max(abs(x) for x in outs), 5) if outs else None}


def pick_k(F, mask):
    ns = []
    for d in range(D):
        cov = mask[d] & np.isfinite(F[d]) & np.isfinite(FWD[10][d])
        n = int(cov.sum())
        if n >= 30:
            ns.append(n)
    return (10 if (ns and min(ns) >= 100) else 5), ns


def coverage(F):
    per = np.isfinite(F).mean(1) * 100
    l70 = np.array([np.isfinite(F[d])[L70[d]].mean() * 100 if L70[d].sum() else np.nan for d in range(D)])
    return {"mean_pct": round(float(per.mean()), 1), "min_pct": round(float(per.min()), 1),
            "max_pct": round(float(per.max()), 1), "liquid70_mean_pct": round(float(np.nanmean(l70)), 1)}


def eval_factor(name, F, do_null=True):
    rep = {"name": name, "coverage": coverage(F)}
    rep["rank_corr_with"] = {rn: round(float(np.nanmean([spearman(F[d], RM[d]) for d in range(D)])), 3)
                             for rn, RM in REF.items()}
    Fn = neut_one(F)
    k, ns = pick_k(F, L70)
    rep["bucket_k"] = k
    for tag, M in (("raw", F), ("neut", Fn)):
        rep[tag] = {}
        rep[tag]["ic"] = {f"h{h}": agg([spearman(M[d], FWD[h][d]) for d in range(D)]) for h in (5, 10, 20)}
        for h in (5, 10, 20):
            st, per_top = bucket_stats(M, h, L70, k)
            rep[tag][f"l70_h{h}"] = st
            if h == 10:
                rep[tag]["updisc_h10"] = updisc(M, 10, L70)
                by, br = splits(per_top)
                rep[tag]["by_year_h10"] = by
                rep[tag]["by_regime_h10"] = br
                st50, _ = bucket_stats(M, 10, L50, k)
                rep[tag]["l50_h10"] = {kk: st50[kk] for kk in
                                       ("top_excess_vs_universe", "bottom_excess_vs_universe", "n_dates_used")}
        if do_null:
            rep[tag]["shuffle_null_h10"] = shuffle_null(M, 10, L70, k)
    return rep, Fn


def rz_mat(F):
    return np.vstack([_rank_z(F[d])[None, :] for d in range(D)])


def blend(mats):
    S = np.full((D, N), np.nan)
    for d in range(D):
        col = np.vstack([m[d] for m in mats])
        cnt = np.isfinite(col).sum(0)
        s = np.nansum(np.where(np.isfinite(col), col, 0.0), axis=0)
        S[d] = np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)
    return S


def paired_diff(stA, stB):
    """per-date diff of top excess (A - B) over common dates."""
    common = sorted(set(stA) & set(stB))
    return agg([stA[d] - stB[d] for d in common])


def main():
    report = {"family": "catalyst_timing_bigmoney", "built": "2026-06-10",
              "protocol": {"decision_metric": "liquid70 top-bucket excess vs universe mean, h10",
                           "min_covered_per_date": 30, "shuffle_seeds": 4},
              "factors": {}, "composites": {}, "n_configs_examined": 0}

    facs = {"f1_fc30": FX["f1_fc30"], "f1_fc60": FX["f1_fc60"], "f2_ex60": FX["f2_ex60"],
            "f3_speed60": FX["f3_speed60"], "chip_winner": FX["chip_winner"], "chip_conc": FX["chip_conc"]}
    neuts = {}
    for nm, F in facs.items():
        print("eval", nm, flush=True)
        rep, Fn = eval_factor(nm, F)
        report["factors"][nm] = rep
        neuts[nm] = Fn
        report["n_configs_examined"] += 2 * 3  # raw/neut x h5/10/20

    # ---------------- composites / KEY incremental test ----------------
    rz_sue = rz_mat(SUE); rz_npq = rz_mat(NPQ)
    rz_f1 = rz_mat(FX["f1_fc60"]); rz_f3 = rz_mat(FX["f3_speed60"])
    comps = {
        "sue_alone": rz_sue,
        "blend_sue_f1": blend([rz_sue, rz_f1]),
        "f3_or_sue": np.where(np.isfinite(rz_f3), rz_f3, rz_sue),
        "pead2_sue_npq": blend([rz_sue, rz_npq]),
        "pead2_plus_f1": blend([rz_sue, rz_npq, rz_f1]),
    }
    tops = {}
    for nm, S in comps.items():
        print("eval composite", nm, flush=True)
        c = {"coverage": coverage(S)}
        c["ic"] = {f"h{h}": agg([spearman(S[d], FWD[h][d]) for d in range(D)]) for h in (10, 20)}
        tops[nm] = {}
        for h in (5, 10, 20):
            st, per_top = bucket_stats(S, h, L70, 10)
            c[f"l70_h{h}"] = st
            tops[nm][h] = per_top
            if h == 10:
                by, br = splits(per_top)
                c["by_year_h10"] = by; c["by_regime_h10"] = br
                st50, _ = bucket_stats(S, 10, L50, 10)
                c["l50_h10_top_excess"] = st50["top_excess_vs_universe"]
        c["shuffle_null_h10"] = shuffle_null(S, 10, L70, 10)
        report["composites"][nm] = c
        report["n_configs_examined"] += 3

    report["incremental_tests"] = {}
    for a, b in [("blend_sue_f1", "sue_alone"), ("f3_or_sue", "sue_alone"),
                 ("pead2_plus_f1", "pead2_sue_npq")]:
        report["incremental_tests"][f"{a}_minus_{b}"] = {
            f"h{h}": paired_diff(tops[a][h], tops[b][h]) for h in (5, 10, 20)}

    out = os.path.join(PROJ, "factor_research/model/reports/enh_catalyst_timing_bigmoney.json")
    json.dump(report, open(out, "w"), indent=1)
    print("wrote", out)

    # console summary
    for nm, rep in report["factors"].items():
        r = rep["raw"]
        print(f"{nm:12s} cov={rep['coverage']['mean_pct']:5.1f}% k={rep['bucket_k']} "
              f"IC10={r['ic']['h10']['mean']} t={r['ic']['h10']['t']} "
              f"topexc10={r['l70_h10']['top_excess_vs_universe']['mean']} t={r['l70_h10']['top_excess_vs_universe']['t']} "
              f"botexc10={r['l70_h10']['bottom_excess_vs_universe']['mean']} "
              f"null|max|={r['shuffle_null_h10']['null_max_abs']}")
    for nm, c in report["composites"].items():
        print(f"comp {nm:16s} topexc10={c['l70_h10']['top_excess_vs_universe']['mean']} "
              f"t={c['l70_h10']['top_excess_vs_universe']['t']} "
              f"topexc20={c['l70_h20']['top_excess_vs_universe']['mean']}")
    print(json.dumps(report["incremental_tests"], indent=1))


if __name__ == "__main__":
    main()
