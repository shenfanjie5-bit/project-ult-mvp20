#!/usr/bin/env python3
"""Honesty battery for t5a_cptheat5 (concept heat, negative attention signal).

1) Rebuild heat using ONLY concepts with list_date <= 20221231 (pre-sample
   concept definitions -> removes 'concept created after the mania' channel
   of the snapshot look-ahead; member-addition channel remains).
2) IC within liquid-70 / liquid-50 universes.
3) Up-rate disc by year and by regime (h10, h20).
4) 4-seed within-date shuffle null for disc and top/bot excess.
All on the control-residualized version (incremental to max5/turnover_20/
ivol_60/strev/mom_6_1)."""
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

# ---------- rebuild concept heat with pre-2023 concepts only ----------
lim = pd.read_csv(f"{BASE}/涨跌停和炸板数据/all.csv", dtype={'trade_date': str}, low_memory=False)
cal = sorted(lim.trade_date.unique()); cal_pos = {dt: i for i, dt in enumerate(cal)}
last_data = cal[-1]
lim = lim[lim.limit == 'U']
lim['pos'] = lim.trade_date.map(cal_pos)
P = len(cal)

mem = pd.read_csv(f"{BASE}/同花顺行业概念成分/all.csv")
blk = pd.read_csv(f"{BASE}/同花顺行业概念板块/all.csv", dtype={'list_date': str})
blkN = blk[blk.type == 'N']
print("concept list_date dist:", blkN.list_date.str[:4].value_counts().sort_index().to_dict())
old = set(blkN[blkN.list_date <= '20221231'].ts_code)
print(f"concepts with list_date<=20221231: {len(old)}/{len(blkN)}")

def build_heat(concept_set):
    m = mem[mem.ts_code.isin(concept_set)]
    cpt_codes = {v: k for k, v in enumerate(sorted(m.ts_code.unique()))}
    NC = len(cpt_codes)
    csize = m.groupby(m.ts_code.map(cpt_codes)).size().reindex(range(NC)).fillna(1).values.astype(float)
    code_cpts = {}
    for r in m.itertuples():
        code_cpts.setdefault(r.con_code, []).append(cpt_codes[r.ts_code])
    CU = np.zeros((P, NC), np.int32)
    for r in lim.itertuples():
        for ck in code_cpts.get(r.ts_code, ()):
            CU[r.pos, ck] += 1
    cCU = np.vstack([np.zeros((1, NC), np.int64), CU.cumsum(0)])
    stock_cpts = {}
    mp = m[m.con_code.isin(col_idx)]
    for r in mp.itertuples():
        stock_cpts.setdefault(col_idx[r.con_code], []).append(cpt_codes[r.ts_code])
    F = np.full((D, N), np.nan, float)
    for di, d in enumerate(base_dates):
        if d > last_data: continue
        pos = cal_pos[d]
        cu5 = (cCU[pos+1] - cCU[max(0, pos+1-5)]).astype(float) / csize
        for j, cks in stock_cpts.items():
            F[di, j] = float(np.mean(cu5[cks]))
    return F

F_old = build_heat(old)
print("pre-2023-concept heat coverage:", round(float(np.isfinite(F_old[:64]).mean()), 3))

# ---------- pipeline: neutralize -> residualize on controls ----------
ind_u = sorted(set(int(i) for i in ind if i >= 0))
Dind = np.zeros((N, len(ind_u)))
for kk, code in enumerate(ind_u): Dind[:, kk] = (ind == code)
rngj = np.random.default_rng(7)

def neut(F):
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

def resid_ctrl(Fn):
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
    if a.size < 4: return (np.nan,)*3 + (0,)
    return float(a.mean()), float(a.mean()/(a.std(ddof=1)/np.sqrt(a.size))), float((a>0).mean()), int(a.size)

def ic_in_mask(F, h, mask=None):
    ics = []
    for d in range(D):
        ok = np.isfinite(F[d]) & np.isfinite(fwd[h][d])
        if mask is not None: ok &= mask[d]
        ics.append(_spearman(F[d][ok], fwd[h][d][ok]) if ok.sum() >= 30 else np.nan)
    return np.array(ics)

def tail_disc(F, h, mask):
    tx, bx, disc = [], [], []
    for d in range(D):
        ok = mask[d] & np.isfinite(F[d]) & np.isfinite(fwd[h][d])
        if ok.sum() < 50: tx.append(np.nan); bx.append(np.nan); disc.append(np.nan); continue
        s, r = F[d][ok], fwd[h][d][ok]; u = r.mean()
        o = np.argsort(s, kind='stable'); g = np.array_split(o, 10); q = np.array_split(o, 5)
        tx.append(r[g[-1]].mean()-u); bx.append(r[g[0]].mean()-u)
        disc.append(float((r[q[-1]]>0).mean()-(r[q[0]]>0).mean()))
    return np.array(tx), np.array(bx), np.array(disc)

out = {}
for label, F0 in (("full_snapshot", np.load(f"{PROJ}/factor_research/enhancers/theme_speculation/theme_factors.npz")['t5a_cptheat5'].astype(float)),
                  ("pre2023_concepts", F_old)):
    R = resid_ctrl(neut(F0))
    blockx = {}
    for h in (5, 10, 20):
        m, t, p, n = tstat(ic_in_mask(R, h))
        blockx[f'ic_h{h}_all'] = (round(m,4), round(t,2), round(p,2))
        m, t, p, n = tstat(ic_in_mask(R, h, m70))
        blockx[f'ic_h{h}_liq70'] = (round(m,4), round(t,2), round(p,2))
    m, t, p, n = tstat(ic_in_mask(R, 10, m50))
    blockx['ic_h10_liq50'] = (round(m,4), round(t,2), round(p,2))
    for h in (10, 20):
        tx, bx, disc = tail_disc(R, h, m70)
        blockx[f'h{h}_top'] = tuple(round(x,5) for x in tstat(tx)[:2])
        blockx[f'h{h}_bot'] = tuple(round(x,5) for x in tstat(bx)[:2])
        blockx[f'h{h}_disc'] = tuple(round(x,4) for x in tstat(disc)[:2])
        if h == 10:
            blockx['disc_by_year'] = {y: (round(tstat(disc[years==y])[0],4), round(tstat(disc[years==y])[1],2)) for y in sorted(set(years))}
            blockx['disc_by_regime'] = {g: (round(tstat(disc[regs==g])[0],4), round(tstat(disc[regs==g])[1],2)) for g in sorted(set(regs))}
            _, _, d50 = tail_disc(R, h, m50)
            blockx['h10_disc_liq50'] = tuple(round(x,4) for x in tstat(d50)[:2])
    # shuffle null (within-date permute residualized values), 4 seeds
    nulls = []
    for sd in (11, 22, 33, 44):
        rng = np.random.default_rng(sd)
        Fs = np.full_like(R, np.nan)
        for d in range(D):
            okf = np.isfinite(R[d]); v = R[d][okf].copy(); rng.shuffle(v); Fs[d, okf] = v
        icm = tstat(ic_in_mask(Fs, 20))[0]
        txs, bxs, ds = tail_disc(Fs, 10, m70)
        nulls.append({"ic20": round(icm,4), "disc10": round(tstat(ds)[0],4),
                      "top10": round(tstat(txs)[0],5), "bot10": round(tstat(bxs)[0],5)})
    blockx['shuffle_null'] = nulls
    out[label] = blockx
    print(f"\n== {label}:")
    print(json.dumps(blockx, indent=1, default=str))

json.dump(out, open(f"{PROJ}/factor_research/model/reports/enh_theme_speculation_honesty_t5a.json","w"), indent=1)
print("saved honesty report")
