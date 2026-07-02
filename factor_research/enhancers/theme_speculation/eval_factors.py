#!/usr/bin/env python3
"""Evaluate theme_speculation factors per the audited EVAL PROTOCOL.

Raw + neutralized; IC h5/10/20; liquid-70 decile curve (BOTH tails),
top/bottom-decile excess, up-rate Q5-Q1; by-year/by-regime; shuffle null
(4 seeds, within-date permutation); liquid-50 re-check.
Ties in sparse factors broken by per-date deterministic jitter << 1 count unit
applied identically to real and shuffled runs (so the null is fair).
"""
import os, sys, json
os.environ['DOCKCASE_WRITEBACK'] = '0'
import numpy as np

PROJ = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
sys.path.insert(0, PROJ)
sys.path.insert(0, f"{PROJ}/factor_research/model")
import harness
from harness import _winsor_z, _rank_z, _spearman, load_panel
import caliblib

z, meta = load_panel(f"{PROJ}/factor_research/model/panel.npz")
fwd = {5: z['fwd5'].astype(float), 10: z['fwd10'].astype(float), 20: z['fwd20'].astype(float)}
lnmv = z['ln_mv'].astype(float)
ind = z['industry'].astype(int)
D, N = lnmv.shape
years = np.array([str(r['date'])[:4] for r in meta['regimes']])
regs = np.array([r['regime'] for r in meta['regimes']])
m70 = caliblib.liquid_mask(z, 0.70)
m50 = caliblib.liquid_mask(z, 0.50)

dat = np.load(f"{PROJ}/factor_research/enhancers/theme_speculation/theme_factors.npz", allow_pickle=True)
names = [str(n) for n in dat['names']]

ind_u = sorted(set(int(i) for i in ind if i >= 0))
Dind = np.zeros((N, len(ind_u)))
for kk, code in enumerate(ind_u):
    Dind[:, kk] = (ind == code)

def neutralize_mat(F, use_industry=True):
    Z = np.full((D, N), np.nan)
    for d in range(D):
        v = _winsor_z(F[d])
        mv = lnmv[d]
        ok = np.isfinite(v) & np.isfinite(mv)
        if ok.sum() < 20:
            Z[d] = _rank_z(v); continue
        Xc = [np.ones(ok.sum()), mv[ok]]
        if use_industry:
            di = Dind[ok]; di = di[:, di.sum(0) > 0]
            X = np.column_stack(Xc + [di])
        else:
            X = np.column_stack(Xc)
        y = v[ok]
        try:
            beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            resid = y - X @ beta
        except Exception:
            resid = y - y.mean()
        rv = np.full(N, np.nan); rv[ok] = resid
        Z[d] = _rank_z(rv)
    return Z

def jitter(F, seed=7):
    """deterministic tiny jitter to break tie mass (same for real & shuffle)."""
    rng = np.random.default_rng(seed)
    eps = rng.standard_normal(F.shape) * 1e-6
    sc = np.nanstd(F)
    return F + eps * (sc if np.isfinite(sc) and sc > 0 else 1.0)

def ic_series(F, h):
    out = []
    for d in range(D):
        ok = np.isfinite(F[d]) & np.isfinite(fwd[h][d])
        out.append(_spearman(F[d][ok], fwd[h][d][ok]) if ok.sum() >= 30 else np.nan)
    return np.array(out)

def tstat(a):
    a = a[np.isfinite(a)]
    if a.size < 4: return np.nan, np.nan, np.nan, 0
    return float(a.mean()), float(a.mean() / (a.std(ddof=1) / np.sqrt(a.size))), float((a > 0).mean()), int(a.size)

def decile_stats(F, h, mask, k=10):
    """per-date decile means of fwd minus universe mean; also up-rate quintiles."""
    curves, topx, botx, disc = [], [], [], []
    for d in range(D):
        ok = mask[d] & np.isfinite(F[d]) & np.isfinite(fwd[h][d])
        if ok.sum() < k * 5:
            topx.append(np.nan); botx.append(np.nan); disc.append(np.nan); continue
        s, r = F[d][ok], fwd[h][d][ok]
        u = r.mean()
        order = np.argsort(s, kind='stable')
        groups = np.array_split(order, k)
        means = np.array([r[g].mean() for g in groups]) - u
        curves.append(means)
        topx.append(means[-1]); botx.append(means[0])
        q = np.array_split(order, 5)
        disc.append(float((r[q[-1]] > 0).mean() - (r[q[0]] > 0).mean()))
    curve = np.nanmean(np.array(curves), 0) if curves else np.full(k, np.nan)
    return curve, np.array(topx), np.array(botx), np.array(disc)

def split_stats(series, labels):
    out = {}
    for lab in sorted(set(labels)):
        s = series[labels == lab]
        m, t, p, n = tstat(s)
        out[lab] = {"mean": None if not np.isfinite(m) else round(m, 5),
                    "t": None if not np.isfinite(t) else round(t, 2), "n": n}
    return out

def shuffle_null(F, h, mask, seeds=(1, 2, 3, 4)):
    """within-date permutation of finite factor values -> top-decile excess mean."""
    outs = []
    for sd in seeds:
        rng = np.random.default_rng(1000 + sd)
        Fs = np.full_like(F, np.nan)
        for d in range(D):
            okf = np.isfinite(F[d])
            v = F[d][okf].copy()
            rng.shuffle(v)
            Fs[d, okf] = v
        _, tx, bx, _ = decile_stats(Fs, h, mask)
        outs.append({"top": tstat(tx)[0], "bot": tstat(bx)[0]})
    return outs

report = {"family": "theme_speculation", "n_dates_usable": int(np.isfinite(dat[names[0]]).any(1).sum()),
          "factors": {}}

for nm in names:
    Fraw0 = dat[nm].astype(float)
    Fraw = jitter(Fraw0)
    use_ind = True
    Fneu = neutralize_mat(Fraw, use_industry=True)
    res = {"coverage_pct": round(100 * float(np.isfinite(Fraw0[:64]).mean()), 1)}
    for tag, F in (("raw", Fraw), ("neut", Fneu)):
        block = {}
        for h in (5, 10, 20):
            ics = ic_series(F, h)
            m, t, p, n = tstat(ics)
            block[f"ic_h{h}"] = {"mean": round(m, 4) if np.isfinite(m) else None,
                                 "t": round(t, 2) if np.isfinite(t) else None,
                                 "pos": round(p, 2) if np.isfinite(p) else None, "n": n}
            curve, tx, bx, disc = decile_stats(F, h, m70)
            tm, tt, tp, tn = tstat(tx)
            bm, bt, bp, bn = tstat(bx)
            block[f"liq70_h{h}"] = {
                "top_excess": {"mean": round(tm, 5), "t": round(tt, 2), "pos": round(tp, 2), "n": tn},
                "bot_excess": {"mean": round(bm, 5), "t": round(bt, 2), "pos": round(bp, 2), "n": bn},
            }
            if h == 10:
                dm, dt, dp, dn = tstat(disc)
                block["liq70_h10_decile_curve"] = [round(float(x), 5) for x in curve]
                block["liq70_h10_uprate_disc"] = {"mean": round(dm, 4), "t": round(dt, 2), "n": dn}
                block["liq70_h10_top_by_year"] = split_stats(tx, years)
                block["liq70_h10_top_by_regime"] = split_stats(tx, regs)
                block["liq70_h10_bot_by_year"] = split_stats(bx, years)
                block["liq70_h10_bot_by_regime"] = split_stats(bx, regs)
                _, tx50, bx50, _ = decile_stats(F, h, m50)
                block["liq50_h10"] = {"top_excess_mean": round(tstat(tx50)[0], 5), "top_t": round(tstat(tx50)[1], 2),
                                      "bot_excess_mean": round(tstat(bx50)[0], 5), "bot_t": round(tstat(bx50)[1], 2)}
        res[tag] = block
    # shuffle null on the neutralized version, h10 liq70
    res["shuffle_null_neut_h10"] = shuffle_null(Fneu, 10, m70)
    report["factors"][nm] = res
    print(f"== {nm} cov={res['coverage_pct']}% "
          f"neut ic10={res['neut']['ic_h10']['mean']}(t{res['neut']['ic_h10']['t']}) "
          f"top10={res['neut']['liq70_h10']['top_excess']['mean']}(t{res['neut']['liq70_h10']['top_excess']['t']}) "
          f"bot10={res['neut']['liq70_h10']['bot_excess']['mean']}(t{res['neut']['liq70_h10']['bot_excess']['t']})")

out = f"{PROJ}/factor_research/model/reports/enh_theme_speculation.json"
json.dump(report, open(out, "w"), indent=1, ensure_ascii=False)
print("saved", out)
