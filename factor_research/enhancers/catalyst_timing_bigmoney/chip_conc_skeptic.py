#!/usr/bin/env python3
"""Skeptic battery for the chip_conc AVOID-gate candidate (bottom decile =
tightly concentrated holder cost -> underperformance).

1. bottom-tail shuffle null (4 seeds), raw + neut, h10/h20
2. bottom-tail by-year / by-regime cuts
3. residualize on turnover_20 (and ln_mv+industry) -> does the tail survive?
4. liquid-50 bottom tail at h20
5. regime date counts
Appends results to the family report JSON.
"""
import os, sys, json
import numpy as np

PROJ = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
sys.path.insert(0, os.path.join(PROJ, "factor_research/model"))
os.environ["DOCKCASE_WRITEBACK"] = "0"
from harness import load_panel, _winsor_z, _rank_z  # noqa: E402
from caliblib import liquid_mask                     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
z, meta = load_panel(os.path.join(PROJ, "factor_research/model/panel.npz"))
BASE = meta["base_dates"]; D = len(BASE); N = len(meta["cols"])
FWD = {10: z["fwd10"].astype(np.float64), 20: z["fwd20"].astype(np.float64)}
LNMV = z["ln_mv"].astype(np.float64); IND = z["industry"].astype(int)
FN = meta["feat_names"]
TURN = z["feat"].astype(np.float64)[:, :, FN.index("turnover_20")]
REG = {r["date"]: r["regime"] for r in meta["regimes"]}
L70 = liquid_mask(z, 0.70); L50 = liquid_mask(z, 0.50)
FX = np.load(os.path.join(HERE, "factors.npz"))
F = FX["chip_conc"]


def agg(vals):
    v = np.array([x for x in vals if np.isfinite(x)])
    if len(v) < 4:
        return {"mean": None, "t": None, "pos_pct": None, "n_dates": int(len(v))}
    t = float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))) if v.std(ddof=1) > 0 else None
    return {"mean": round(float(v.mean()), 5), "t": round(t, 2) if t is not None else None,
            "pos_pct": round(100.0 * float((v > 0).mean()), 1), "n_dates": int(len(v))}


def bot_per_date(M, h, mask, k=10, min_cov=30):
    r = FWD[h]; out = {}
    for d in range(D):
        m = mask[d] & np.isfinite(r[d])
        cov = m & np.isfinite(M[d])
        n = int(cov.sum())
        if n < min_cov or m.sum() < 100:
            continue
        f = M[d][cov]; rr = r[d][cov]
        order = np.argsort(np.argsort(f))
        b = np.minimum((order * k) // n, k - 1)
        out[d] = float(rr[b == 0].mean()) - float(r[d][m].mean())
    return out


def residualize(extra_cols):
    """winsor-z chip_conc, residualize on [1, ln_mv, industry, extras], rank-z."""
    ind_u = sorted(set(int(i) for i in IND if i >= 0))
    Dind = np.zeros((N, len(ind_u)))
    for kk, c in enumerate(ind_u):
        Dind[:, kk] = (IND == c).astype(float)
    out = np.full((D, N), np.nan)
    for d in range(D):
        v = _winsor_z(F[d]); mv = LNMV[d]
        ex = [_winsor_z(E[d]) for E in extra_cols]
        ok = np.isfinite(v) & np.isfinite(mv)
        for e in ex:
            ok &= np.isfinite(e)
        if ok.sum() < 20:
            continue
        di = Dind[ok]; di = di[:, di.sum(0) > 0]
        X = np.column_stack([np.ones(ok.sum()), mv[ok]] + [e[ok] for e in ex] + [di])
        beta, *_ = np.linalg.lstsq(X, v[ok], rcond=None)
        rv = np.full(N, np.nan); rv[ok] = v[ok] - X @ beta
        out[d] = _rank_z(rv)
    return out


def neut_plain():
    return residualize([])


def shuffle_bot(M, h, mask, k=10, seeds=(1, 2, 3, 4)):
    outs = []
    for s in seeds:
        rng = np.random.default_rng(20260610 + s)
        Ms = np.full_like(M, np.nan)
        for d in range(D):
            cov = mask[d] & np.isfinite(M[d]) & np.isfinite(FWD[h][d])
            idx = np.where(cov)[0]
            if len(idx) < 30:
                continue
            Ms[d, idx] = M[d, idx][rng.permutation(len(idx))]
        outs.append(agg(list(bot_per_date(Ms, h, mask, k).values()))["mean"])
    outs = [o for o in outs if o is not None]
    return {"means": outs, "null_max_abs": round(max(abs(x) for x in outs), 5) if outs else None}


res = {"regime_date_counts": {}}
for b in BASE:
    g = REG.get(b, "?")
    res["regime_date_counts"][g] = res["regime_date_counts"].get(g, 0) + 1

Fn = neut_plain()
Ft = residualize([TURN])

for tag, M in (("raw", F), ("neut", Fn), ("neut_plus_turnover", Ft)):
    res[tag] = {}
    for h in (10, 20):
        per = bot_per_date(M, h, L70)
        res[tag][f"bot_l70_h{h}"] = agg(list(per.values()))
        res[tag][f"bot_l70_h{h}_null"] = shuffle_bot(M, h, L70)
        if h == 10:
            by_y, by_r = {}, {}
            for d, v in per.items():
                by_y.setdefault(BASE[d][:4], []).append(v)
                by_r.setdefault(REG.get(BASE[d], "?"), []).append(v)
            res[tag]["bot_by_year_h10"] = {y: agg(v) for y, v in sorted(by_y.items())}
            res[tag]["bot_by_regime_h10"] = {g: agg(v) for g, v in sorted(by_r.items())}
        res[tag][f"bot_l50_h{h}"] = agg(list(bot_per_date(M, h, L50).values()))

rep_path = os.path.join(PROJ, "factor_research/model/reports/enh_catalyst_timing_bigmoney.json")
rep = json.load(open(rep_path))
rep["chip_conc_skeptic"] = res
rep["n_configs_examined"] = rep.get("n_configs_examined", 0) + 6
json.dump(rep, open(rep_path, "w"), indent=1)
print(json.dumps(res, indent=1))
