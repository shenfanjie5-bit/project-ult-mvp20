#!/usr/bin/env python3
"""Adversarial skeptic attack on t5a_cptheat5 (statistics lens).

1) Reproduce headline pipeline EXACTLY as honesty_t5a.py (jitter seed 7 ->
   neutralize on [1, ln_mv, ind] -> residualize on max5/turnover_20/ivol_60/
   strev/mom_6_1 -> rank_z) and verify the claimed cells.
2) Fresh shuffle null, 5 seeds (7,11,13,17,19), covering ic20 / disc10 /
   disc20 / h20_top (the agent never published a null for disc20, its
   strongest cell).
3) Overlap correction: Newey-West t (lags 1,2) + stationary block bootstrap
   for ic20 / disc10 / disc20 (base dates ~10td apart, fwd20 overlaps 50%).
4) Year / regime concentration: drop-one re-tests.
5) Which side carries the disc (Q5 hot depressed vs Q1 cold elevated).
6) Subsumption: residualize additionally on t1_lu20 (own limit-up count).
7) MV profile of extreme deciles within liq70.
"""
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
fwd = {5: z['fwd5'].astype(float), 10: z['fwd10'].astype(float), 20: z['fwd20'].astype(float)}
lnmv = z['ln_mv'].astype(float); ind = z['industry'].astype(int)
D, N = lnmv.shape
years = np.array([str(r['date'])[:4] for r in meta['regimes']])
regs = np.array([r['regime'] for r in meta['regimes']])
m70 = caliblib.liquid_mask(z, 0.70); m50 = caliblib.liquid_mask(z, 0.50)
CTRL = ['max5', 'turnover_20', 'ivol_60', 'strev', 'mom_6_1']
ci = [fn.index(c) for c in CTRL]

dat = np.load(f"{PROJ}/factor_research/enhancers/theme_speculation/theme_factors.npz", allow_pickle=True)
F0 = dat['t5a_cptheat5'].astype(float)
T1 = dat['t1_lu20'].astype(float)

ind_u = sorted(set(int(i) for i in ind if i >= 0))
Dind = np.zeros((N, len(ind_u)))
for kk, code in enumerate(ind_u): Dind[:, kk] = (ind == code)

def neut(F, seed=7):
    rngj = np.random.default_rng(seed)
    F = F + rngj.standard_normal(F.shape) * 1e-6 * (np.nanstd(F) or 1.0)
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

def resid_ctrl(Fn, extra=None):
    R = np.full((D, N), np.nan)
    for d in range(D):
        C = Zn[d][:, ci]
        if extra is not None:
            C = np.column_stack([C, extra[d]])
        ok = np.isfinite(Fn[d]) & np.all(np.isfinite(C), 1)
        if ok.sum() < 30: continue
        X = np.column_stack([np.ones(ok.sum()), C[ok]])
        beta, *_ = np.linalg.lstsq(X, Fn[d][ok], rcond=None)
        rv = np.full(N, np.nan); rv[ok] = Fn[d][ok] - X @ beta
        R[d] = _rank_z(rv)
    return R

def tstat(a):
    a = a[np.isfinite(a)]
    if a.size < 4: return (np.nan,)*3 + (0,)
    return float(a.mean()), float(a.mean()/(a.std(ddof=1)/np.sqrt(a.size))), float((a>0).mean()), int(a.size)

def nw_t(a, lag):
    """Newey-West t for the mean of a (possibly NaN-holed) series."""
    a = a[np.isfinite(a)]
    n = a.size
    if n < 8: return np.nan
    e = a - a.mean()
    s = float(e @ e) / n
    for L in range(1, lag+1):
        w = 1.0 - L/(lag+1)
        s += 2.0 * w * float(e[L:] @ e[:-L]) / n
    se = np.sqrt(s / n)
    return float(a.mean() / se)

def autocorr(a, L):
    a = a[np.isfinite(a)]
    e = a - a.mean()
    return float((e[L:] @ e[:-L]) / (e @ e))

def block_boot(a, B=4000, blk=3, seed=99):
    a = a[np.isfinite(a)]
    n = a.size
    rng = np.random.default_rng(seed)
    means = np.empty(B)
    nb = int(np.ceil(n/blk))
    for b in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + np.arange(blk)[None, :]).ravel() % n
        means[b] = a[idx[:n]].mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    p = 2*min((means >= 0).mean(), (means <= 0).mean())  # sign-flip style: frac crossing 0
    return float(lo), float(hi), float(p)

def ic_series(F, h, mask=None):
    out = []
    for d in range(D):
        ok = np.isfinite(F[d]) & np.isfinite(fwd[h][d])
        if mask is not None: ok &= mask[d]
        out.append(_spearman(F[d][ok], fwd[h][d][ok]) if ok.sum() >= 30 else np.nan)
    return np.array(out)

def tail_disc(F, h, mask):
    tx, bx, disc, q5lev, q1lev, ulev = [], [], [], [], [], []
    for d in range(D):
        ok = mask[d] & np.isfinite(F[d]) & np.isfinite(fwd[h][d])
        if ok.sum() < 50:
            for L in (tx, bx, disc, q5lev, q1lev, ulev): L.append(np.nan)
            continue
        s, r = F[d][ok], fwd[h][d][ok]; u = r.mean()
        o = np.argsort(s, kind='stable'); g = np.array_split(o, 10); q = np.array_split(o, 5)
        tx.append(r[g[-1]].mean()-u); bx.append(r[g[0]].mean()-u)
        up_u = (r > 0).mean()
        q5 = (r[q[-1]] > 0).mean(); q1 = (r[q[0]] > 0).mean()
        disc.append(float(q5 - q1)); q5lev.append(float(q5-up_u)); q1lev.append(float(q1-up_u)); ulev.append(float(up_u))
    return map(np.array, (tx, bx, disc, q5lev, q1lev, ulev))

out = {}

# ---------- 1) reproduce ----------
R = resid_ctrl(neut(F0))
ic20 = ic_series(R, 20); ic20_70 = ic_series(R, 20, m70); ic10 = ic_series(R, 10)
tx20, bx20, disc20, q5x20, q1x20, _ = tail_disc(R, 20, m70)
tx10, bx10, disc10, q5x10, q1x10, _ = tail_disc(R, 10, m70)
_, _, disc10_50, _, _, _ = tail_disc(R, 10, m50)
rep = {
 'ic20_all': [round(x,4) for x in tstat(ic20)[:2]],
 'ic20_liq70': [round(x,4) for x in tstat(ic20_70)[:2]],
 'disc10': [round(x,4) for x in tstat(disc10)[:2]],
 'disc20': [round(x,4) for x in tstat(disc20)[:2]],
 'disc10_liq50': [round(x,4) for x in tstat(disc10_50)[:2]],
 'h20_top': [round(x,5) for x in tstat(tx20)[:2]],
 'h20_bot': [round(x,5) for x in tstat(bx20)[:2]],
}
out['reproduce'] = rep
print("REPRODUCE:", json.dumps(rep))
print(" claimed : ic20_all[-0.0321,-3.75] ic20_liq70[-0.0309,-3.01] disc10[-0.0231,-2.21] disc20[-0.0368,-3.42] disc10_liq50[-0.0303,-2.40] h20_top[-0.00298,-1.39]")

# ---------- 2) fresh shuffle null, 5 seeds ----------
nulls = []
for sd in (7, 11, 13, 17, 19):
    rng = np.random.default_rng(sd)
    Fs = np.full_like(R, np.nan)
    for d in range(D):
        okf = np.isfinite(R[d]); v = R[d][okf].copy(); rng.shuffle(v); Fs[d, okf] = v
    n_ic20 = tstat(ic_series(Fs, 20))
    ntx20, nbx20, nd20, _, _, _ = tail_disc(Fs, 20, m70)
    _, _, nd10, _, _, _ = tail_disc(Fs, 10, m70)
    nulls.append({'ic20': round(n_ic20[0],4), 'ic20_t': round(n_ic20[1],2),
                  'disc10': round(tstat(nd10)[0],4), 'disc20': round(tstat(nd20)[0],4),
                  'disc20_t': round(tstat(nd20)[1],2),
                  'top20': round(tstat(ntx20)[0],5)})
out['fresh_null_5seeds'] = nulls
print("FRESH NULL:", json.dumps(nulls))

# ---------- 3) overlap / autocorrelation ----------
ov = {}
for nm, ser in (('ic20', ic20), ('disc10', disc10), ('disc20', disc20), ('top20', tx20), ('ic10', ic10)):
    m, t_naive, _, n = tstat(ser)
    ov[nm] = {'mean': round(m,4), 't_naive': round(t_naive,2),
              'rho1': round(autocorr(ser,1),3), 'rho2': round(autocorr(ser,2),3),
              't_nw1': round(nw_t(ser,1),2), 't_nw2': round(nw_t(ser,2),2),
              'blockboot_b3': [round(x,4) for x in block_boot(ser)]}
out['overlap'] = ov
print("OVERLAP:", json.dumps(ov))

# ---------- 4) drop-one year / regime ----------
dy = {}
for y in sorted(set(years)):
    keep = years != y
    dy[f'ex{y}'] = {'ic20': [round(x,4) for x in tstat(ic20[keep])[:2]],
                    'ic20_nw1': round(nw_t(ic20[keep],1),2),
                    'disc10': [round(x,4) for x in tstat(disc10[keep])[:2]],
                    'disc20': [round(x,4) for x in tstat(disc20[keep])[:2]],
                    'disc20_nw1': round(nw_t(disc20[keep],1),2)}
dr = {}
for g in sorted(set(regs)):
    keep = regs != g
    dr[f'ex_{g}'] = {'ic20': [round(x,4) for x in tstat(ic20[keep])[:2]],
                     'disc20': [round(x,4) for x in tstat(disc20[keep])[:2]]}
out['drop_year'] = dy; out['drop_regime'] = dr
print("DROP YEAR:", json.dumps(dy))
print("DROP REGIME:", json.dumps(dr))

# ---------- 5) which side carries disc ----------
side = {'h10_q5_minus_univ': [round(x,4) for x in tstat(q5x10)[:2]],
        'h10_q1_minus_univ': [round(x,4) for x in tstat(q1x10)[:2]],
        'h20_q5_minus_univ': [round(x,4) for x in tstat(q5x20)[:2]],
        'h20_q1_minus_univ': [round(x,4) for x in tstat(q1x20)[:2]]}
out['disc_sides'] = side
print("DISC SIDES:", json.dumps(side))

# ---------- 6) additionally residualize on own limit-up count t1_lu20 ----------
T1n = neut(T1, seed=8)
R2 = resid_ctrl(neut(F0), extra=T1n)
ic20b = ic_series(R2, 20)
_, _, d20b, _, _, _ = tail_disc(R2, 20, m70)
_, _, d10b, _, _, _ = tail_disc(R2, 10, m70)
sub = {'ic20': [round(x,4) for x in tstat(ic20b)[:2]], 'ic20_nw1': round(nw_t(ic20b,1),2),
       'disc10': [round(x,4) for x in tstat(d10b)[:2]],
       'disc20': [round(x,4) for x in tstat(d20b)[:2]], 'disc20_nw1': round(nw_t(d20b,1),2)}
out['plus_t1_resid'] = sub
print("PLUS-T1 RESID:", json.dumps(sub))

# ---------- 7) MV profile of extreme deciles in liq70 ----------
prof = []
for d in range(D):
    ok = m70[d] & np.isfinite(R[d]) & np.isfinite(fwd[20][d]) & np.isfinite(lnmv[d])
    if ok.sum() < 50: continue
    s = R[d][ok]; mv = lnmv[d][ok]
    o = np.argsort(s, kind='stable'); g = np.array_split(o, 10)
    rk = np.argsort(np.argsort(mv)) / (len(mv)-1)
    prof.append([rk[g[0]].mean(), rk[g[-1]].mean()])
prof = np.array(prof)
out['mv_rank_in_liq70'] = {'bot_decile_mean_mvrank': round(float(prof[:,0].mean()),3),
                           'top_decile_mean_mvrank': round(float(prof[:,1].mean()),3)}
print("MV PROFILE:", json.dumps(out['mv_rank_in_liq70']))

json.dump(out, open(f"{PROJ}/factor_research/model/reports/enh_theme_speculation_skeptic_attack.json", "w"), indent=1)
print("saved skeptic report")
