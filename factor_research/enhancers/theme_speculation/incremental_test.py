#!/usr/bin/env python3
"""Incremental value test: residualize theme factors on the panel's existing
price-vol attention features (max5, turnover_20, ivol_60, strev, mom_6_1)
per date, then re-run IC / up-rate disc / tails. If the signal dies, it is
subsumed by factors the model already owns."""
import os, sys, json
os.environ['DOCKCASE_WRITEBACK'] = '0'
import numpy as np

PROJ = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
sys.path.insert(0, f"{PROJ}/factor_research/model")
from harness import _winsor_z, _rank_z, _spearman, load_panel, neutralize
import caliblib

z, meta = load_panel(f"{PROJ}/factor_research/model/panel.npz")
Zn = neutralize(z, meta)            # cached neutral.npz (D,N,F)
fn = meta['feat_names']
fwd = {5: z['fwd5'].astype(float), 10: z['fwd10'].astype(float), 20: z['fwd20'].astype(float)}
D, N = z['ln_mv'].shape
years = np.array([str(r['date'])[:4] for r in meta['regimes']])
regs = np.array([r['regime'] for r in meta['regimes']])
m70 = caliblib.liquid_mask(z, 0.70)
m50 = caliblib.liquid_mask(z, 0.50)

CTRL = ['max5', 'turnover_20', 'ivol_60', 'strev', 'mom_6_1']
ci = [fn.index(c) for c in CTRL]

dat = np.load(f"{PROJ}/factor_research/enhancers/theme_speculation/theme_factors.npz", allow_pickle=True)

# rebuild neutralized theme factors (same as eval) quickly via saved logic
lnmv = z['ln_mv'].astype(float); ind = z['industry'].astype(int)
ind_u = sorted(set(int(i) for i in ind if i >= 0))
Dind = np.zeros((N, len(ind_u)))
for kk, code in enumerate(ind_u): Dind[:, kk] = (ind == code)
rng = np.random.default_rng(7)

def neutralize_mat(F):
    eps = rng.standard_normal(F.shape) * 1e-6 * (np.nanstd(F) or 1.0)
    F = F + eps
    Z = np.full((D, N), np.nan)
    for d in range(D):
        v = _winsor_z(F[d]); mv = lnmv[d]
        ok = np.isfinite(v) & np.isfinite(mv)
        if ok.sum() < 20: Z[d] = _rank_z(v); continue
        di = Dind[ok]; di = di[:, di.sum(0) > 0]
        X = np.column_stack([np.ones(ok.sum()), mv[ok], di])
        beta, *_ = np.linalg.lstsq(X, v[ok], rcond=None)
        rv = np.full(N, np.nan); rv[ok] = v[ok] - X @ beta
        Z[d] = _rank_z(rv)
    return Z

def residualize_on_controls(Fn):
    R = np.full((D, N), np.nan)
    for d in range(D):
        C = Zn[d][:, ci]
        ok = np.isfinite(Fn[d]) & np.all(np.isfinite(C), 1)
        if ok.sum() < 30: continue
        X = np.column_stack([np.ones(ok.sum()), C[ok]])
        beta, *_ = np.linalg.lstsq(X, Fn[d][ok], rcond=None)
        rv = np.full(N, np.nan); rv[ok] = Fn[d][ok] - X @ beta
        R[d] = _rank_z(rv)
    return R

def tstat(a):
    a = a[np.isfinite(a)]
    if a.size < 4: return np.nan, np.nan, np.nan, 0
    return float(a.mean()), float(a.mean()/(a.std(ddof=1)/np.sqrt(a.size))), float((a>0).mean()), int(a.size)

def metrics(F, label):
    out = {}
    for h in (5, 10, 20):
        ics = []
        for d in range(D):
            ok = np.isfinite(F[d]) & np.isfinite(fwd[h][d])
            ics.append(_spearman(F[d][ok], fwd[h][d][ok]) if ok.sum() >= 30 else np.nan)
        m, t, p, n = tstat(np.array(ics))
        out[f'ic_h{h}'] = (round(m,4), round(t,2))
    # liq70 tails + disc at h10 and h20
    for h in (10, 20):
        tx, bx, disc = [], [], []
        for d in range(D):
            ok = m70[d] & np.isfinite(F[d]) & np.isfinite(fwd[h][d])
            if ok.sum() < 50: tx.append(np.nan); bx.append(np.nan); disc.append(np.nan); continue
            s, r = F[d][ok], fwd[h][d][ok]; u = r.mean()
            order = np.argsort(s, kind='stable'); g = np.array_split(order, 10)
            tx.append(r[g[-1]].mean()-u); bx.append(r[g[0]].mean()-u)
            q = np.array_split(order, 5)
            disc.append(float((r[q[-1]]>0).mean()-(r[q[0]]>0).mean()))
        tx, bx, disc = map(np.array, (tx, bx, disc))
        out[f'liq70_h{h}_top'] = tuple(round(x,5) if np.isfinite(x) else None for x in tstat(tx)[:2])
        out[f'liq70_h{h}_bot'] = tuple(round(x,5) if np.isfinite(x) else None for x in tstat(bx)[:2])
        out[f'liq70_h{h}_disc'] = tuple(round(x,4) if np.isfinite(x) else None for x in tstat(disc)[:2])
        if h == 10:
            out['top_by_year'] = {y: round(tstat(tx[years==y])[0],5) for y in sorted(set(years))}
    print(label, json.dumps(out, default=str))
    return out

res = {}
for nm in ['t1_lu20', 't1b_touch20', 't5a_cptheat5', 't4b_indrot', 't3_zha20']:
    Fn = neutralize_mat(dat[nm].astype(float))
    # correlation with controls (mean per-date spearman)
    cors = {}
    for c, cidx in zip(CTRL, ci):
        cs = []
        for d in range(D):
            ok = np.isfinite(Fn[d]) & np.isfinite(Zn[d][:, cidx])
            if ok.sum() >= 30: cs.append(_spearman(Fn[d][ok], Zn[d][ok, cidx]))
        cors[c] = round(float(np.nanmean(cs)), 3)
    print(f"\n== {nm} corr-with-controls:", cors)
    R = residualize_on_controls(Fn)
    res[nm] = {"corr_controls": cors, "after_resid": metrics(R, f"  {nm}|resid:")}

json.dump(res, open(f"{PROJ}/factor_research/model/reports/enh_theme_speculation_incremental.json","w"), indent=1)
print("\nsaved incremental report")
