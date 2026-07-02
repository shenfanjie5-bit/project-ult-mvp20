#!/usr/bin/env python3
"""20-seed null calibration for disc20/disc10/ic20 t-stats of t5a residualized."""
import os, sys, json
os.environ['DOCKCASE_WRITEBACK'] = '0'
import numpy as np

PROJ = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
sys.path.insert(0, f"{PROJ}/factor_research/model")
from harness import _winsor_z, _rank_z, _spearman, load_panel, neutralize
import caliblib

z, meta = load_panel(f"{PROJ}/factor_research/model/panel.npz")
Zn = neutralize(z, meta)
fn = meta['feat_names']
fwd20 = z['fwd20'].astype(float); fwd10 = z['fwd10'].astype(float)
lnmv = z['ln_mv'].astype(float); ind = z['industry'].astype(int)
D, N = lnmv.shape
m70 = caliblib.liquid_mask(z, 0.70)
ci = [fn.index(c) for c in ['max5','turnover_20','ivol_60','strev','mom_6_1']]
dat = np.load(f"{PROJ}/factor_research/enhancers/theme_speculation/theme_factors.npz")
F0 = dat['t5a_cptheat5'].astype(float)
ind_u = sorted(set(int(i) for i in ind if i >= 0))
Dind = np.zeros((N, len(ind_u)))
for kk, code in enumerate(ind_u): Dind[:, kk] = (ind == code)
rngj = np.random.default_rng(7)
F0 = F0 + rngj.standard_normal(F0.shape)*1e-6*(np.nanstd(F0) or 1.0)
R = np.full((D, N), np.nan)
for d in range(D):
    v = _winsor_z(F0[d]); mv = lnmv[d]
    ok = np.isfinite(v) & np.isfinite(mv)
    if ok.sum() < 20: continue
    di = Dind[ok]; di = di[:, di.sum(0) > 0]
    X = np.column_stack([np.ones(ok.sum()), mv[ok], di])
    b, *_ = np.linalg.lstsq(X, v[ok], rcond=None)
    rv = np.full(N, np.nan); rv[ok] = v[ok] - X @ b
    Fn = _rank_z(rv)
    C = Zn[d][:, ci]
    ok2 = np.isfinite(Fn) & np.all(np.isfinite(C), 1)
    X2 = np.column_stack([np.ones(ok2.sum()), C[ok2]])
    b2, *_ = np.linalg.lstsq(X2, Fn[ok2], rcond=None)
    rv2 = np.full(N, np.nan); rv2[ok2] = Fn[ok2] - X2 @ b2
    R[d] = _rank_z(rv2)

def tstat(a):
    a = a[np.isfinite(a)]
    return float(a.mean()), float(a.mean()/(a.std(ddof=1)/np.sqrt(a.size)))

def stats_for(F):
    ics, d10, d20 = [], [], []
    for d in range(D):
        okI = np.isfinite(F[d]) & np.isfinite(fwd20[d])
        ics.append(_spearman(F[d][okI], fwd20[d][okI]) if okI.sum() >= 30 else np.nan)
        for h, fw, acc in ((10, fwd10, d10), (20, fwd20, d20)):
            ok = m70[d] & np.isfinite(F[d]) & np.isfinite(fw[d])
            if ok.sum() < 50: acc.append(np.nan); continue
            s, r = F[d][ok], fw[d][ok]
            q = np.array_split(np.argsort(s, kind='stable'), 5)
            acc.append(float((r[q[-1]]>0).mean() - (r[q[0]]>0).mean()))
    return tstat(np.array(ics)), tstat(np.array(d10)), tstat(np.array(d20))

rows = []
for sd in range(101, 121):
    rng = np.random.default_rng(sd)
    Fs = np.full_like(R, np.nan)
    for d in range(D):
        okf = np.isfinite(R[d]); v = R[d][okf].copy(); rng.shuffle(v); Fs[d, okf] = v
    (icm, ict), (d10m, d10t), (d20m, d20t) = stats_for(Fs)
    rows.append({'seed': sd, 'ic20_t': round(ict,2), 'disc10_m': round(d10m,4), 'disc10_t': round(d10t,2),
                 'disc20_m': round(d20m,4), 'disc20_t': round(d20t,2)})
    print(rows[-1])

arr = lambda k: np.array([r[k] for r in rows])
print("\nNULL CALIBRATION (20 seeds):")
for k in ('ic20_t','disc10_t','disc20_t'):
    a = arr(k)
    print(f"{k}: mean={a.mean():.2f} sd={a.std(ddof=1):.2f} min={a.min():.2f} max={a.max():.2f} |t|>2: {(np.abs(a)>2).sum()}/20")
for k in ('disc10_m','disc20_m'):
    a = arr(k)
    print(f"{k}: mean={a.mean():.4f} sd={a.std(ddof=1):.4f} min={a.min():.4f} max={a.max():.4f}")
json.dump(rows, open(f"{PROJ}/factor_research/model/reports/enh_theme_speculation_null20.json","w"), indent=1)
