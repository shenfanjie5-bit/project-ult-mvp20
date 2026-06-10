#!/usr/bin/env python3
"""ADVERSARIAL ATTACK on c2cu_20 (customer-industry momentum -> supplier stocks).

Parts:
  A  independent rebuild of c2cu_20 from raw RET (own code path) vs stored npz
  B  reproduce headline: jitter(seed7) raw + sizeneut, harness.evaluate liq70 h10/h20
  C  drop-one year and drop-one regime on the per-date top-excess series (h10,h20)
  D  fresh shuffle nulls seeds (7,11,13,17,19): stock-level + industry-label,
     h10 AND h20; plus 20-seed industry-label null spread characterization
  E  overlap correction at h20: lag-1 autocorr, Newey-West t, non-overlap subsample
  F  multiple-testing haircut: 54 family cells, analytic p-values
  G  capturability: winner-industry concentration, limit-up fraction in top decile
     at base date, skip-day1 entry re-test; MV percentile profile of top decile
"""
import os, sys, json
import numpy as np

os.environ["DOCKCASE_WRITEBACK"] = "0"
ROOT = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "factor_research", "model"))

import harness
from harness import _winsor_z, _rank_z, _deciles, evaluate, load_panel
import caliblib
from scipy import stats as sps

OUT = os.path.join(ROOT, "factor_research", "model", "reports", "skeptic_industry_chain_c2cu.json")
FNPZ = os.path.join(ROOT, "factor_research", "enhancers", "industry_chain", "factors_industry_chain.npz")

z, meta = load_panel()
F = np.load(FNPZ)
fwd = {5: z["fwd5"].astype(np.float64), 10: z["fwd10"].astype(np.float64), 20: z["fwd20"].astype(np.float64)}
lnmv = z["ln_mv"].astype(np.float64)
ind = z["industry"].astype(int)
D, N = lnmv.shape
K = len(meta["industry_names"])
names = meta["industry_names"]
name2k = {n: i for i, n in enumerate(names)}
liq70 = caliblib.liquid_mask(z, 0.70)
liq50 = caliblib.liquid_mask(z, 0.50)
base_idx = meta["base_idx"]
base_dates = meta["base_dates"]
regs = [r["regime"] for r in meta["regimes"]]
years = [d[:4] for d in base_dates]
cols = meta["cols"]

px = np.load("factor_research/data/px_20230101.npz")
RET = px["RET"].astype(np.float64)
nT = RET.shape[0]

EDGES = {
    "NONFERROUS_METALS": ["STORAGE_GRID", "CONSUMER_ELECTRONICS", "ROBOTICS", "EXPORT_MFG"],
    "ANTI_INVOLUTION_CYCLICAL": ["EXPORT_MFG", "ROBOTICS"],
    "SEMI_EQUIPMENT": ["AI_COMPUTE", "CONSUMER_ELECTRONICS"],
    "STORAGE_GRID": ["AI_COMPUTE"],
    "AI_COMPUTE": ["HK_CN_INTERNET"],
}

report = {}

# ---------------- A: independent rebuild ----------------
L1 = np.log1p(RET)
C20 = np.full((D, N), np.nan)
for d, t in enumerate(base_idx):
    win = L1[t - 19: t + 1]
    nok = np.isfinite(win).sum(0)
    s = np.nansum(win, 0)
    C20[d] = np.where(nok >= 16, np.expm1(s), np.nan)
M20 = np.full((D, K), np.nan)
for k in range(K):
    sub = C20[:, ind == k]
    n = np.isfinite(sub).sum(1)
    with np.errstate(invalid="ignore"):
        M20[:, k] = np.where(n >= 5, np.nanmean(sub, 1), np.nan)
c2cu = np.full((D, N), np.nan)
for sup, custs in EDGES.items():
    ks = name2k[sup]
    kc = [name2k[c] for c in custs]
    vals = np.nanmean(M20[:, kc], 1)
    c2cu[:, ind == ks] = vals[:, None]
stored = F["c2cu_20"].astype(np.float64)
both = np.isfinite(c2cu) & np.isfinite(stored)
md = float(np.max(np.abs(c2cu[both] - stored[both]))) if both.any() else np.nan
report["A_rebuild"] = {
    "max_abs_diff": md,
    "n_finite_mine": int(np.isfinite(c2cu).sum()), "n_finite_stored": int(np.isfinite(stored).sum()),
    "match": bool(md < 1e-6 and np.isfinite(c2cu).sum() == np.isfinite(stored).sum())}
print("A rebuild:", report["A_rebuild"])

# ---------------- jitter convention (copied from eval script) ----------------
RNG = np.random.default_rng(7)
JIT = RNG.standard_normal((D, N))

def jitter(Fm, jfield=None):
    jf = JIT if jfield is None else jfield
    out = Fm.copy()
    for d in range(D):
        row = out[d]
        ok = np.isfinite(row)
        if ok.sum() < 10:
            continue
        sd = np.nanstd(row)
        eps = (sd if sd > 0 else 1.0) * 1e-7
        out[d, ok] = row[ok] + eps * jf[d, ok]
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

Fm = stored  # use stored matrix from here (verified identical)
raw = jitter(Fm)
sn = sizeneut(jitter(Fm))

# ---------------- B: reproduce headline ----------------
def slim_te(ev):
    b = ev.get("top_excess_uni")
    return None if not b else {"mean": round(b["mean"], 5), "t": round(b["t"], 2), "n": b["n_dates"]}

B = {}
for vn, S in (("raw", raw), ("sizeneut", sn)):
    for h in (10, 20):
        B[f"{vn}_h{h}"] = slim_te(evaluate(S, fwd[h], meta, h, eval_mask=liq70))
report["B_reproduce"] = B
print("B reproduce:", B)

# ---------------- per-date top-excess series helper ----------------
def te_series(scores, h, mask, fwd_override=None):
    rt_all = fwd[h] if fwd_override is None else fwd_override
    vals, idxs = [], []
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
        idxs.append(d)
    return np.array(vals), np.array(idxs)

def mt(a):
    if a.size < 3:
        return (None, None, int(a.size))
    se = a.std(ddof=1) / np.sqrt(a.size)
    return (round(float(a.mean()), 5), round(float(a.mean() / se), 2), int(a.size))

te10, idx10 = te_series(raw, 10, liq70)
te20, idx20 = te_series(raw, 20, liq70)
report["B_series_check"] = {"h10": mt(te10), "h20": mt(te20)}

# ---------------- C: drop-one year / regime ----------------
C = {"h10": {}, "h20": {}}
for hname, te, idxs in (("h10", te10, idx10), ("h20", te20, idx20)):
    yy = np.array([years[i] for i in idxs])
    rr = np.array([regs[i] for i in idxs])
    C[hname]["full"] = mt(te)
    for y in sorted(set(yy)):
        C[hname][f"drop_{y}"] = mt(te[yy != y])
        C[hname][f"only_{y}"] = mt(te[yy == y])
    for g in sorted(set(rr)):
        C[hname][f"dropreg_{g}"] = mt(te[rr != g])
report["C_drops"] = C
print("C drops h10:", C["h10"])
print("C drops h20:", C["h20"])

# ---------------- D: fresh shuffle nulls ----------------
def shuffle_stock(scores, seed):
    rng = np.random.default_rng(seed)
    out = scores.copy()
    for d in range(D):
        ok = np.isfinite(out[d])
        v = out[d, ok]
        rng.shuffle(v)
        out[d, ok] = v
    return out

def shuffle_industry(Fm_, seed):
    rng = np.random.default_rng(seed)
    out = np.full((D, N), np.nan)
    for d in range(D):
        sig = np.full(K, np.nan)
        for k in range(K):
            v = Fm_[d, ind == k]
            if np.isfinite(v).sum() >= 5:
                sig[k] = np.nanmean(v)
        kk = np.where(np.isfinite(sig))[0]
        if kk.size < 4:
            continue
        perm = rng.permutation(kk)
        for a, b in zip(kk, perm):
            out[d, ind == a] = sig[b]
    return jitter(out)

Dnulls = {"stock": {}, "indlabel": {}}
for seed in (7, 11, 13, 17, 19):
    s10, _ = te_series(shuffle_stock(raw, seed), 10, liq70)
    s20, _ = te_series(shuffle_stock(raw, seed), 20, liq70)
    Dnulls["stock"][seed] = {"h10": mt(s10), "h20": mt(s20)}
    i10, _ = te_series(shuffle_industry(Fm, seed), 10, liq70)
    i20, _ = te_series(shuffle_industry(Fm, seed), 20, liq70)
    Dnulls["indlabel"][seed] = {"h10": mt(i10), "h20": mt(i20)}
# 20-seed industry-label null spread
big = {"h10": [], "h20": []}
for seed in range(100, 120):
    sh = shuffle_industry(Fm, seed)
    a10, _ = te_series(sh, 10, liq70)
    a20, _ = te_series(sh, 20, liq70)
    big["h10"].append(mt(a10)[:2]); big["h20"].append(mt(a20)[:2])
Dnulls["indlabel_20seeds"] = big
m10 = np.array([x[0] for x in big["h10"]]); m20 = np.array([x[0] for x in big["h20"]])
Dnulls["indlabel_null_summary"] = {
    "h10_mean_range": [round(float(m10.min()), 5), round(float(m10.max()), 5)],
    "h10_null_sd": round(float(m10.std(ddof=1)), 5),
    "h10_real_z_vs_null": round(float((te10.mean() - m10.mean()) / m10.std(ddof=1)), 2),
    "h10_n_nulls_geq_real": int((m10 >= te10.mean()).sum()),
    "h20_mean_range": [round(float(m20.min()), 5), round(float(m20.max()), 5)],
    "h20_null_sd": round(float(m20.std(ddof=1)), 5),
    "h20_real_z_vs_null": round(float((te20.mean() - m20.mean()) / m20.std(ddof=1)), 2),
    "h20_n_nulls_geq_real": int((m20 >= te20.mean()).sum()),
}
report["D_fresh_nulls"] = Dnulls
print("D nulls:", json.dumps(Dnulls["indlabel_null_summary"]))

# ---------------- E: overlap correction at h20 ----------------
def nw_t(a, lags):
    n = a.size
    x = a - a.mean()
    g0 = float((x * x).mean())
    s = g0
    for l in range(1, lags + 1):
        gl = float((x[l:] * x[:-l]).mean())
        s += 2.0 * (1.0 - l / (lags + 1)) * gl
    se = np.sqrt(max(s, 1e-12) / n)
    return round(float(a.mean() / se), 2)

E = {}
for hname, te in (("h10", te10), ("h20", te20)):
    x = te - te.mean()
    ac1 = float((x[1:] * x[:-1]).mean() / (x * x).mean())
    E[hname] = {"lag1_autocorr": round(ac1, 3),
                "naive_t": mt(te)[1],
                "nw_t_lag1": nw_t(te, 1), "nw_t_lag2": nw_t(te, 2),
                "nonoverlap_even": mt(te[::2]), "nonoverlap_odd": mt(te[1::2])}
report["E_overlap"] = E
print("E overlap:", E)

# ---------------- F: multiple testing ----------------
def p2(t, n):
    return float(2 * (1 - sps.t.cdf(abs(t), df=n - 1)))

cells = 54  # 9 factors x 3 horizons x 2 usable variants (raw, sizeneut)
Fmt = {}
for label, t_, n_ in (("raw_h10", te10.mean() / (te10.std(ddof=1) / np.sqrt(te10.size)), te10.size),
                      ("raw_h20", te20.mean() / (te20.std(ddof=1) / np.sqrt(te20.size)), te20.size)):
    p = p2(t_, n_)
    Fmt[label] = {"t": round(float(t_), 2), "p_naive": round(p, 4),
                  "p_bonf54": round(min(1.0, p * cells), 3),
                  "p_sidak_eff10": round(1 - (1 - p) ** 10, 3)}
# best family cell claimed: sizeneut h20 t=2.2 n=65
p_best = p2(2.16, 65)
Fmt["best_cell_sizeneut_h20"] = {"t": 2.16, "p_naive": round(p_best, 4),
                                 "p_bonf54": round(min(1.0, p_best * cells), 3),
                                 "p_sidak_eff10": round(1 - (1 - p_best) ** 10, 3)}
report["F_multiple_testing"] = Fmt
print("F MT:", Fmt)

# ---------------- G: capturability + concentration ----------------
# winner industry per date (which supplier industry has max c2cu value)
sup_ks = [name2k[s] for s in EDGES]
winner = []
for d in range(D):
    vals = {}
    for ks in sup_ks:
        v = Fm[d, ind == ks]
        v = v[np.isfinite(v)]
        if v.size:
            vals[ks] = float(v[0])
    if vals:
        winner.append((d, max(vals, key=vals.get)))
win_count = {}
for d, k in winner:
    win_count[names[k]] = win_count.get(names[k], 0) + 1
# contribution of each winner industry to the h10 top-excess sum
contrib = {}
wmap = dict(winner)
for j, d in enumerate(idx10):
    k = wmap.get(d)
    if k is None:
        continue
    contrib.setdefault(names[k], []).append(float(te10[j]))
contrib_s = {k: {"n_dates": len(v), "mean_te": round(float(np.mean(v)), 5),
                 "share_of_total": round(float(np.sum(v) / te10.sum()), 3)} for k, v in contrib.items()}

# top-decile composition: limit-up fraction at base date, MV percentile
def board_limit(code):
    c = code.split(".")[0]
    if c.startswith(("300", "301")) or c.startswith(("688", "689")):
        return 0.195
    if code.endswith(".BJ") or c.startswith(("83", "87", "43", "92")):
        return 0.295
    return 0.097

limits = np.array([board_limit(c) for c in cols])
limup_fracs, mvpct, topsz = [], [], []
skip_te10 = []
# skip-day1 forward returns: prod(1+RET[t+2 .. t+1+h]) - 1
SK10 = np.full((D, N), np.nan)
for d, t in enumerate(base_idx):
    a, b = t + 2, t + 11
    if b >= nT:
        continue
    win = L1[a: b + 1 - 1 + 1]  # t+2 .. t+11 inclusive = 10 days
    win = L1[a: a + 10]
    nok = np.isfinite(win).sum(0)
    s = np.nansum(win, 0)
    SK10[d] = np.where(nok >= 8, np.expm1(s), np.nan)

for jj, d in enumerate(idx10):
    sc = np.where(liq70[d], raw[d], np.nan)
    rt = fwd[10][d]
    ok = np.isfinite(sc) & np.isfinite(rt)
    order = np.argsort(sc[ok])
    ids = np.where(ok)[0][order]
    top = ids[-max(1, ok.sum() // 10):]
    t = base_idx[d]
    r0 = RET[t, top]
    lim = np.isfinite(r0) & (r0 >= limits[top])
    limup_fracs.append(float(lim.mean()))
    mv = lnmv[d]
    okm = np.isfinite(mv)
    pct = np.array([float((mv[okm] < mv[s]).mean()) for s in top if np.isfinite(mv[s])])
    mvpct.append(float(np.median(pct)) if pct.size else np.nan)
    topsz.append(int(top.size))

ts10, _ = te_series(raw, 10, liq70, fwd_override=SK10)
G = {"winner_industry_counts": win_count,
     "winner_contrib_h10": contrib_s,
     "limup_frac_top_decile_mean": round(float(np.mean(limup_fracs)), 4),
     "limup_frac_top_decile_max": round(float(np.max(limup_fracs)), 4),
     "top_decile_median_mv_pctile": round(float(np.nanmedian(mvpct)), 3),
     "top_decile_size_median": int(np.median(topsz)),
     "h10_top_excess_skipday1": mt(ts10)}
report["G_capturability"] = G
print("G:", json.dumps(G, indent=1))

json.dump(report, open(OUT, "w"), indent=1)
print("saved", OUT)
