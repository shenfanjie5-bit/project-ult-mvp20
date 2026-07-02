#!/usr/bin/env python3
"""Adversarial PIT/tradeability attack on t5a_cptheat5 (THS concept limit-up heat).

0) Reproduce headline (control-residualized) numbers exactly per honesty_t5a.py.
1) Newey-West overlap-corrected t for ic20/disc20 (biweekly dates, 20td horizon
   -> ~50% window overlap; iid t is inflated).
2) Drop-each-year ic20 / disc tests.
3) Fresh within-date shuffle null, 5 seeds (7,11,13,17,19): ic20, disc10, disc20.
4) Tradeability: hot-decile composition (own limit-up at base date close = price
   unbuyable; own touch in 5d/20d window); re-test with those stocks EXCLUDED.
5) Leave-own-events-out rebuild of concept heat (subtract stock's own U events
   from its concepts' counts) -> does the 'theme' signal survive without
   self-contamination?
6) MV percentile of hot/cold deciles within liq70 (microcap tilt check).
7) Survivorship: panel stocks absent from snapshot membership.
"""
import os, sys, json
os.environ['DOCKCASE_WRITEBACK'] = '0'
import numpy as np
import pandas as pd

PROJ = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
BASE = "/Volumes/dockcase2tb/database_all/股票数据/打板专题数据"
sys.path.insert(0, f"{PROJ}/factor_research/model")
from harness import _winsor_z, _rank_z, _spearman, load_panel, neutralize
import caliblib

z, meta = load_panel(f"{PROJ}/factor_research/model/panel.npz")
Zn = neutralize(z, meta)
fn = meta['feat_names']
fwd = {5: z['fwd5'].astype(float), 10: z['fwd10'].astype(float), 20: z['fwd20'].astype(float)}
lnmv = z['ln_mv'].astype(float); ind = z['industry'].astype(int)
D, N = lnmv.shape
cols = list(meta['cols']); col_idx = {c: j for j, c in enumerate(cols)}
base_dates = [str(d) for d in meta['base_dates']]
years = np.array([str(r['date'])[:4] for r in meta['regimes']])
regs = np.array([r['regime'] for r in meta['regimes']])
m70 = caliblib.liquid_mask(z, 0.70); m50 = caliblib.liquid_mask(z, 0.50)
CTRL = ['max5', 'turnover_20', 'ivol_60', 'strev', 'mom_6_1']
ci = [fn.index(c) for c in CTRL]

# ---------------- limit data + own-event masks ----------------
lim_all = pd.read_csv(f"{BASE}/涨跌停和炸板数据/all.csv", dtype={'trade_date': str}, low_memory=False)
cal = sorted(lim_all.trade_date.unique()); cal_pos = {dt: i for i, dt in enumerate(cal)}
last_data = cal[-1]; P = len(cal)
limUZ = lim_all[lim_all.limit.isin(['U', 'Z'])].copy()
limU = limUZ[limUZ.limit == 'U']

U = np.zeros((P, N), np.int8); TCH = np.zeros((P, N), np.int8)
pr = limUZ[limUZ.ts_code.isin(col_idx)]
for r in pr.itertuples():
    j = col_idx[r.ts_code]; pos = cal_pos[r.trade_date]
    TCH[pos, j] = 1
    if r.limit == 'U':
        U[pos, j] = 1
cU = np.vstack([np.zeros((1, N), np.int32), U.cumsum(0)])
cT = np.vstack([np.zeros((1, N), np.int32), TCH.cumsum(0)])

ownU_day = np.zeros((D, N), bool)     # closed at limit-up on base date
ownT5 = np.zeros((D, N), bool)        # touched limit (U/Z) in past 5 td
ownT20 = np.zeros((D, N), bool)       # touched in past 20 td
usable = np.zeros(D, bool)
for di, d in enumerate(base_dates):
    if d > last_data:
        continue
    usable[di] = True
    pos = cal_pos[d]
    ownU_day[di] = U[pos] > 0
    ownT5[di] = (cT[pos + 1] - cT[max(0, pos + 1 - 5)]) > 0
    ownT20[di] = (cT[pos + 1] - cT[max(0, pos + 1 - 20)]) > 0

# ---------------- pipeline (exact replication of honesty_t5a.py) ----------------
ind_u = sorted(set(int(i) for i in ind if i >= 0))
Dind = np.zeros((N, len(ind_u)))
for kk, code in enumerate(ind_u):
    Dind[:, kk] = (ind == code)

def neut(F, rngj):
    F = F + rngj.standard_normal(F.shape) * 1e-6 * (np.nanstd(F) or 1.0)
    Z = np.full((D, N), np.nan)
    for d in range(D):
        v = _winsor_z(F[d]); mv = lnmv[d]
        ok = np.isfinite(v) & np.isfinite(mv)
        if ok.sum() < 20:
            Z[d] = _rank_z(v); continue
        di = Dind[ok]; di = di[:, di.sum(0) > 0]
        X = np.column_stack([np.ones(ok.sum()), mv[ok], di])
        beta, *_ = np.linalg.lstsq(X, v[ok], rcond=None)
        rv = np.full(N, np.nan); rv[ok] = v[ok] - X @ beta
        Z[d] = _rank_z(rv)
    return Z

def resid_ctrl(Fn):
    R = np.full((D, N), np.nan)
    for d in range(D):
        C = Zn[d][:, ci]
        ok = np.isfinite(Fn[d]) & np.all(np.isfinite(C), 1)
        if ok.sum() < 30:
            continue
        X = np.column_stack([np.ones(ok.sum()), C[ok]])
        beta, *_ = np.linalg.lstsq(X, Fn[d][ok], rcond=None)
        rv = np.full(N, np.nan); rv[ok] = Fn[d][ok] - X @ beta
        R[d] = _rank_z(rv)
    return R

def tstat(a):
    a = a[np.isfinite(a)]
    if a.size < 4:
        return (np.nan,) * 3 + (0,)
    return float(a.mean()), float(a.mean() / (a.std(ddof=1) / np.sqrt(a.size))), float((a > 0).mean()), int(a.size)

def nw_t(a, L=2):
    """HAC (Bartlett) t-stat of the mean for an overlapping series."""
    a = a[np.isfinite(a)]
    n = a.size
    if n < 8:
        return np.nan
    x = a - a.mean()
    g0 = float(x @ x) / n
    S = g0
    for l in range(1, L + 1):
        gl = float(x[l:] @ x[:-l]) / n
        S += 2.0 * (1 - l / (L + 1)) * gl
    return float(a.mean() / np.sqrt(S / n))

def ic_in_mask(F, h, mask=None, excl=None):
    ics = []
    for d in range(D):
        ok = np.isfinite(F[d]) & np.isfinite(fwd[h][d])
        if mask is not None: ok &= mask[d]
        if excl is not None: ok &= ~excl[d]
        ics.append(_spearman(F[d][ok], fwd[h][d][ok]) if ok.sum() >= 30 else np.nan)
    return np.array(ics)

def tail_disc(F, h, mask, excl=None):
    tx, bx, disc = [], [], []
    for d in range(D):
        ok = mask[d] & np.isfinite(F[d]) & np.isfinite(fwd[h][d])
        if excl is not None: ok &= ~excl[d]
        if ok.sum() < 50:
            tx.append(np.nan); bx.append(np.nan); disc.append(np.nan); continue
        s, r = F[d][ok], fwd[h][d][ok]; u = r.mean()
        o = np.argsort(s, kind='stable'); g = np.array_split(o, 10); q = np.array_split(o, 5)
        tx.append(r[g[-1]].mean() - u); bx.append(r[g[0]].mean() - u)
        disc.append(float((r[q[-1]] > 0).mean() - (r[q[0]] > 0).mean()))
    return np.array(tx), np.array(bx), np.array(disc)

F0 = np.load(f"{PROJ}/factor_research/enhancers/theme_speculation/theme_factors.npz")['t5a_cptheat5'].astype(float)
R = resid_ctrl(neut(F0, np.random.default_rng(7)))

out = {}

# ---- 0) reproduce headline ----
rep = {}
ic20 = ic_in_mask(R, 20); ic20_70 = ic_in_mask(R, 20, m70)
ic10 = ic_in_mask(R, 10); ic5 = ic_in_mask(R, 5)
tx20, bx20, disc20 = tail_disc(R, 20, m70)
tx10, bx10, disc10 = tail_disc(R, 10, m70)
rep['ic20_all'] = [round(x, 4) for x in tstat(ic20)[:2]]
rep['ic20_liq70'] = [round(x, 4) for x in tstat(ic20_70)[:2]]
rep['ic10_all'] = [round(x, 4) for x in tstat(ic10)[:2]]
rep['ic5_all'] = [round(x, 4) for x in tstat(ic5)[:2]]
rep['disc20_liq70'] = [round(x, 4) for x in tstat(disc20)[:2]]
rep['disc10_liq70'] = [round(x, 4) for x in tstat(disc10)[:2]]
rep['h20_top_liq70'] = [round(x, 5) for x in tstat(tx20)[:2]]
out['reproduce'] = rep
print("REPRODUCE:", json.dumps(rep))

# ---- 1) NW overlap-corrected t ----
out['nw'] = {
    'ic20_all_t_nw2': round(nw_t(ic20, 2), 2), 'ic20_all_t_nw1': round(nw_t(ic20, 1), 2),
    'ic20_liq70_t_nw2': round(nw_t(ic20_70, 2), 2),
    'disc20_t_nw2': round(nw_t(disc20, 2), 2), 'disc10_t_nw1': round(nw_t(disc10, 1), 2),
    'ic10_all_t_nw1': round(nw_t(ic10, 1), 2),
    'lag1_autocorr_ic20': round(float(np.corrcoef(ic20[np.isfinite(ic20)][:-1], ic20[np.isfinite(ic20)][1:])[0, 1]), 3),
}
print("NW:", json.dumps(out['nw']))

# ---- 2) drop-year ----
dy = {}
for y in sorted(set(years)):
    keep = years != y
    dy[f'ex{y}'] = {'ic20': [round(x, 4) for x in tstat(ic20[keep])[:2]],
                    'disc20': [round(x, 4) for x in tstat(disc20[keep])[:2]],
                    'disc10': [round(x, 4) for x in tstat(disc10[keep])[:2]]}
out['drop_year'] = dy
print("DROP-YEAR:", json.dumps(dy))

# ---- 3) fresh shuffle null, 5 seeds ----
nulls = []
for sd in (7, 11, 13, 17, 19):
    rng = np.random.default_rng(sd)
    Fs = np.full_like(R, np.nan)
    for d in range(D):
        okf = np.isfinite(R[d]); v = R[d][okf].copy(); rng.shuffle(v); Fs[d, okf] = v
    icn = tstat(ic_in_mask(Fs, 20))[0]
    txs, bxs, ds10 = tail_disc(Fs, 10, m70)
    _, _, ds20 = tail_disc(Fs, 20, m70)
    nulls.append({'ic20': round(icn, 4), 'disc10': round(tstat(ds10)[0], 4),
                  'disc20': round(tstat(ds20)[0], 4), 'top10': round(tstat(txs)[0], 5)})
out['shuffle_null_5seeds'] = nulls
print("NULL:", json.dumps(nulls))

# ---- 4) tradeability: hot-decile composition + exclusion re-tests ----
compU, compT5, compT20, baseU, baseT5 = [], [], [], [], []
for d in range(D):
    ok = m70[d] & np.isfinite(R[d]) & np.isfinite(fwd[10][d])
    if ok.sum() < 50:
        continue
    idx = np.where(ok)[0]
    o = idx[np.argsort(R[d][idx], kind='stable')]
    top = o[-len(o) // 10:]
    compU.append(ownU_day[d][top].mean()); compT5.append(ownT5[d][top].mean())
    compT20.append(ownT20[d][top].mean())
    baseU.append(ownU_day[d][idx].mean()); baseT5.append(ownT5[d][idx].mean())
comp = {'hot_decile_ownU_day': round(float(np.mean(compU)), 3),
        'hot_decile_ownTouch5': round(float(np.mean(compT5)), 3),
        'hot_decile_ownTouch20': round(float(np.mean(compT20)), 3),
        'universe_ownU_day': round(float(np.mean(baseU)), 3),
        'universe_ownTouch5': round(float(np.mean(baseT5)), 3)}
out['composition'] = comp
print("COMPOSITION:", json.dumps(comp))

excl_tests = {}
for lab, ex in (('excl_ownU_day', ownU_day), ('excl_ownTouch5', ownT5), ('excl_ownTouch20', ownT20)):
    blk = {}
    e20 = ic_in_mask(R, 20, excl=ex); e10 = ic_in_mask(R, 10, excl=ex); e5 = ic_in_mask(R, 5, excl=ex)
    blk['ic20_all'] = [round(x, 4) for x in tstat(e20)[:2]] + [round(nw_t(e20, 2), 2)]
    blk['ic10_all'] = [round(x, 4) for x in tstat(e10)[:2]]
    blk['ic5_all'] = [round(x, 4) for x in tstat(e5)[:2]]
    blk['ic20_liq70'] = [round(x, 4) for x in tstat(ic_in_mask(R, 20, m70, excl=ex))[:2]]
    txe, bxe, d20e = tail_disc(R, 20, m70, excl=ex)
    _, _, d10e = tail_disc(R, 10, m70, excl=ex)
    blk['disc20_liq70'] = [round(x, 4) for x in tstat(d20e)[:2]] + [round(nw_t(d20e, 2), 2)]
    blk['disc10_liq70'] = [round(x, 4) for x in tstat(d10e)[:2]]
    blk['h20_top_liq70'] = [round(x, 5) for x in tstat(txe)[:2]]
    excl_tests[lab] = blk
    print(f"EXCL {lab}:", json.dumps(blk))
out['exclusion'] = excl_tests

# ---- 5) leave-own-events-out rebuild ----
mem = pd.read_csv(f"{BASE}/同花顺行业概念成分/all.csv")
blkdf = pd.read_csv(f"{BASE}/同花顺行业概念板块/all.csv")
ncpt = set(blkdf[blkdf.type == 'N'].ts_code)
mem = mem[mem.ts_code.isin(ncpt)]
cpt_codes = {v: k for k, v in enumerate(sorted(mem.ts_code.unique()))}
NC = len(cpt_codes)
mem['ck'] = mem.ts_code.map(cpt_codes)
cpt_size = mem.groupby('ck').size().reindex(range(NC)).fillna(1).values.astype(float)
code_cpts = {}
for r in mem.itertuples():
    code_cpts.setdefault(r.con_code, []).append(int(r.ck))
stock_cpts = {}
for r in mem[mem.con_code.isin(col_idx)].itertuples():
    stock_cpts.setdefault(col_idx[r.con_code], []).append(int(r.ck))
limUp = limU.copy(); limUp['pos'] = limUp.trade_date.map(cal_pos)
CU = np.zeros((P, NC), np.int32)
for r in limUp.itertuples():
    for ck in code_cpts.get(r.ts_code, ()):
        CU[r.pos, ck] += 1
cCU = np.vstack([np.zeros((1, NC), np.int64), CU.cumsum(0)])
F_loo = np.full((D, N), np.nan)
for di, d in enumerate(base_dates):
    if d > last_data:
        continue
    pos = cal_pos[d]
    cu5 = (cCU[pos + 1] - cCU[max(0, pos + 1 - 5)]).astype(float)
    own5 = (cU[pos + 1] - cU[max(0, pos + 1 - 5)]).astype(float)  # panel stock own U count, past 5td
    for j, cks in stock_cpts.items():
        num = cu5[cks] - own5[j]
        den = np.maximum(cpt_size[cks] - 1.0, 1.0)
        F_loo[di, j] = float(np.mean(num / den))
R_loo = resid_ctrl(neut(F_loo, np.random.default_rng(7)))
loo = {}
l20 = ic_in_mask(R_loo, 20); l10 = ic_in_mask(R_loo, 10); l5 = ic_in_mask(R_loo, 5)
loo['ic20_all'] = [round(x, 4) for x in tstat(l20)[:2]] + [round(nw_t(l20, 2), 2)]
loo['ic10_all'] = [round(x, 4) for x in tstat(l10)[:2]]
loo['ic5_all'] = [round(x, 4) for x in tstat(l5)[:2]]
loo['ic20_liq70'] = [round(x, 4) for x in tstat(ic_in_mask(R_loo, 20, m70))[:2]]
txl, bxl, d20l = tail_disc(R_loo, 20, m70); _, _, d10l = tail_disc(R_loo, 10, m70)
loo['disc20_liq70'] = [round(x, 4) for x in tstat(d20l)[:2]] + [round(nw_t(d20l, 2), 2)]
loo['disc10_liq70'] = [round(x, 4) for x in tstat(d10l)[:2]]
loo['h20_top_liq70'] = [round(x, 5) for x in tstat(txl)[:2]]
# LOO + exclusion combined (hardest test)
le20 = ic_in_mask(R_loo, 20, excl=ownT5)
loo['ic20_all_exclT5'] = [round(x, 4) for x in tstat(le20)[:2]] + [round(nw_t(le20, 2), 2)]
_, _, d20le = tail_disc(R_loo, 20, m70, excl=ownT5)
loo['disc20_liq70_exclT5'] = [round(x, 4) for x in tstat(d20le)[:2]]
out['leave_own_out'] = loo
print("LOO:", json.dumps(loo))

# ---- 6) MV percentile of hot/cold deciles within liq70 ----
hp, cp = [], []
for d in range(D):
    ok = m70[d] & np.isfinite(R[d]) & np.isfinite(fwd[10][d]) & np.isfinite(lnmv[d])
    if ok.sum() < 50:
        continue
    idx = np.where(ok)[0]
    o = idx[np.argsort(R[d][idx], kind='stable')]
    k = len(o) // 10
    ranks = pd.Series(lnmv[d][idx]).rank(pct=True).values
    rmap = dict(zip(idx, ranks))
    hp.append(np.mean([rmap[i] for i in o[-k:]])); cp.append(np.mean([rmap[i] for i in o[:k]]))
out['mv_percentile'] = {'hot_decile': round(float(np.mean(hp)), 3), 'cold_decile': round(float(np.mean(cp)), 3)}
print("MV:", json.dumps(out['mv_percentile']))

# ---- 7) survivorship ----
ever = np.isfinite(F0[usable]).any(0)
miss = [cols[j] for j in range(N) if not ever[j]]
out['survivorship'] = {'panel_stocks_no_concept': len(miss), 'examples': miss[:10]}
print("SURVIVORSHIP:", json.dumps(out['survivorship']))

json.dump(out, open(f"{PROJ}/factor_research/model/reports/skeptic_t5a_pit.json", 'w'), indent=1)
print("saved", f"{PROJ}/factor_research/model/reports/skeptic_t5a_pit.json")
