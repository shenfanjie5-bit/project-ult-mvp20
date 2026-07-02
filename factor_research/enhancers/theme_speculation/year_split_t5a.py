#!/usr/bin/env python3
"""Year splits of residualized t5a IC (h10/h20) + n dates per year."""
import os, sys, json
os.environ['DOCKCASE_WRITEBACK'] = '0'
import numpy as np
PROJ = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
sys.path.insert(0, f"{PROJ}/factor_research/model")
from harness import _winsor_z, _rank_z, _spearman, load_panel, neutralize
import caliblib
z, meta = load_panel(f"{PROJ}/factor_research/model/panel.npz")
Zn = neutralize(z, meta); fn = meta['feat_names']
fwd = {10: z['fwd10'].astype(float), 20: z['fwd20'].astype(float)}
lnmv = z['ln_mv'].astype(float); ind = z['industry'].astype(int)
D, N = lnmv.shape
years = np.array([str(r['date'])[:4] for r in meta['regimes']])
ci = [fn.index(c) for c in ['max5','turnover_20','ivol_60','strev','mom_6_1']]
F0 = np.load(f"{PROJ}/factor_research/enhancers/theme_speculation/theme_factors.npz")['t5a_cptheat5'].astype(float)
ind_u = sorted(set(int(i) for i in ind if i >= 0))
Dind = np.zeros((N, len(ind_u)))
for kk, code in enumerate(ind_u): Dind[:, kk] = (ind == code)
rng = np.random.default_rng(7)
F0 = F0 + rng.standard_normal(F0.shape)*1e-6*(np.nanstd(F0) or 1.0)
R = np.full((D,N), np.nan)
for d in range(D):
    v = _winsor_z(F0[d]); mv = lnmv[d]
    ok = np.isfinite(v)&np.isfinite(mv)
    if ok.sum()<20: continue
    di = Dind[ok]; di = di[:, di.sum(0)>0]
    X = np.column_stack([np.ones(ok.sum()), mv[ok], di])
    b,*_ = np.linalg.lstsq(X, v[ok], rcond=None)
    rv = np.full(N, np.nan); rv[ok] = v[ok]-X@b
    Fn = _rank_z(rv)
    C = Zn[d][:, ci]
    ok2 = np.isfinite(Fn)&np.all(np.isfinite(C),1)
    X2 = np.column_stack([np.ones(ok2.sum()), C[ok2]])
    b2,*_ = np.linalg.lstsq(X2, Fn[ok2], rcond=None)
    rv2 = np.full(N, np.nan); rv2[ok2] = Fn[ok2]-X2@b2
    R[d] = _rank_z(rv2)
for h in (10,20):
    ics = np.array([_spearman(R[d][m], fwd[h][d][m]) if (m:=(np.isfinite(R[d])&np.isfinite(fwd[h][d]))).sum()>=30 else np.nan for d in range(D)])
    print(f"h{h} IC by year:")
    for y in sorted(set(years)):
        s = ics[(years==y)]; s = s[np.isfinite(s)]
        if len(s)<2: print(f"  {y}: n={len(s)}"); continue
        print(f"  {y}: mean={s.mean():.4f} t={s.mean()/(s.std(ddof=1)/np.sqrt(len(s))):.2f} n={len(s)} neg%={np.mean(s<0):.2f}")
