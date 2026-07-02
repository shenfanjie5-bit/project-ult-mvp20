#!/usr/bin/env python3
"""A1 — rigorous stress-test of the forecast (业绩预告) event signal.

Pre-registered KILL criteria (FROZEN, see REPORT_A1_forecast.md):
  K1  post-event CAR monotonic with signed sign AND significant (bootstrap CI
      excludes 0). Horizon chosen A PRIORI: h=1 (announcement reaction), also h=3.
  K2  walk-forward OOS sign-accuracy > 50% with 95% CI lower bound > 50%.
  K3  long-only (and long-short) net-abnormal P&L > 0 in a MAJORITY of
      non-overlapping half-year folds after 25bps round-trip cost
      (also 15 / 40 bps).

Tasks:
  1. magnitude monotonicity / coefficient curve (quintiles + subtype);
     sign x magnitude interaction.
  2. P&L robustness: per-fold, cost sensitivity, extreme-event drop (top/bottom
     1% by abnormal return) and winsorization.
  3. walk-forward OOS sign accuracy, broken down +sign vs -sign.
  4. explicit K1/K2/K3 verdict at h=1 and h=3 with after-cost edge per event.

READ-ONLY on mvp20/. Writes nothing except stdout (captured into the report).
Run from REPO ROOT:
  DOCKCASE_WRITEBACK=0 DOCKCASE_CACHE=1 \
    factor_research/.venv_research/bin/python \
    factor_research/04_event_study/run_A1_forecast.py
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)  # nanmean of empty slice on edge days
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eventlib as E  # noqa: E402

# The clean-percentage subtypes: magnitude == announced YoY net-profit growth and
# is directly comparable. 扭亏/首亏/续亏/续盈/不确定 are loss-base ratio artifacts
# (a turn-to-profit off a near-zero base produces a meaningless +1.01..+106 ratio)
# and MUST be treated as separate categorical buckets, never pooled into a
# numeric quintile. This mirrors the brief's "separate bucket for NaN-magnitude".
CLEAN_POS = {"预增", "略增"}
CLEAN_NEG = {"预减", "略减"}
CLEAN = CLEAN_POS | CLEAN_NEG
SPECIAL = {"扭亏", "首亏", "续亏", "续盈", "不确定"}  # 续盈 small/noisy, 不确定 sign=0

SECT = "=" * 78


def hr(title):
    print(f"\n{SECT}\n{title}\n{SECT}")


def boot_mean_ci(x, n=4000, seed=0):
    """(mean, lo, hi, t, n) with percentile bootstrap CI. Mirrors eventlib._boot_ci
    but a touch more bootstrap reps + returns t. Used for the coefficient curve."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 10:
        return (np.nan, np.nan, np.nan, np.nan, len(x))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    bs = x[idx].mean(axis=1)
    sd = x.std(ddof=1)
    t = x.mean() / (sd / np.sqrt(len(x))) if sd > 0 else np.nan
    return (float(x.mean()), float(np.percentile(bs, 2.5)),
            float(np.percentile(bs, 97.5)), float(t), len(x))


def bps(v):
    return "nan" if not np.isfinite(v) else f"{v*1e4:+.1f}"


# ───────────────────────────── load ─────────────────────────────
hr("0. LOAD + UNIVERSE")
P = E.panel()
print(f"panel: {P['cal'][0]}..{P['cal'][-1]}  {len(P['cal'])} trading days x {len(P['cols'])} stocks")
ev_all = E.load_events("forecast")
ev = E.attach_alignment(ev_all)
print(f"forecast events: {len(ev_all)} loaded -> {len(ev)} priceable (PIT-aligned, e>=0 & j>=0)")
print("sign distribution:", ev["sign"].value_counts().to_dict())
print("\nsubtype x sign:")
print(pd.crosstab(ev["subtype"], ev["sign"]).to_string())

# tag families for downstream grouping
fam = np.where(ev["subtype"].isin(CLEAN), "clean",
               np.where(ev["subtype"].isin(SPECIAL), "special", "other"))
ev = ev.assign(family=fam)
print("\nfamily counts:", ev["family"].value_counts().to_dict())
print("(clean = 预增/略增/预减/略减 with interpretable magnitude; "
      "special = 扭亏/首亏/续亏/续盈/不确定 = loss-base / sign-0 buckets)")

# precompute abnormal returns at the two a-priori horizons (size-decile adjusted)
ABN = {h: E.abnormal_series(ev, h, method="size") for h in (1, 3)}


# ════════════════════════════════════════════════════════════════
# TASK 1 — MAGNITUDE MONOTONICITY / COEFFICIENT CURVE
# ════════════════════════════════════════════════════════════════
hr("TASK 1 — MAGNITUDE MONOTONICITY & SIGNED-COEFFICIENT CURVE")

print("""
DESIGN NOTE (load-bearing): forecast 'magnitude' = avg(p_change_min,p_change_max)
is only a comparable growth number for 预增/略增/预减/略减. For 扭亏(turn-to-profit)
the prior-year base is a loss, so the % ratio explodes to +1.01..+106 and is NOT a
strength measure; 首亏/续亏 produce symmetric garbage (down to -383). Pooling all
events into one numeric quintile would just sort on this artifact. Therefore:
  (a) magnitude quintiles are formed WITHIN the clean subtypes only;
  (b) the special loss-base subtypes are reported as their own categorical buckets
      (the brief's 'separate bucket for NaN-magnitude 扭亏/首亏').
""")

# ---- 1a. categorical curve by SUBTYPE (full ordering, both horizons) ----
print("--- 1a. mean abnormal CAR by SUBTYPE (size-adj) ---")
sub_rows = []
for h in (1, 3):
    abn = ABN[h]
    for st, g in ev.assign(abn=abn).groupby("subtype"):
        m, lo, hi, t, n = boot_mean_ci(g["abn"].values, seed=11)
        sgn = g["sign"].iloc[0]
        sub_rows.append(dict(horizon=h, subtype=st, sign=sgn, n=n,
                             mean_bps=m * 1e4 if np.isfinite(m) else np.nan,
                             lo_bps=lo * 1e4 if np.isfinite(lo) else np.nan,
                             hi_bps=hi * 1e4 if np.isfinite(hi) else np.nan,
                             t=t, sig=bool(np.isfinite(lo) and (lo > 0 or hi < 0))))
sub_df = pd.DataFrame(sub_rows)
# order positive subtypes by expected strength, then negative
order = ["预增", "略增", "扭亏", "续盈", "不确定", "续亏", "首亏", "略减", "预减"]
sub_df["__o"] = sub_df["subtype"].map({s: i for i, s in enumerate(order)})
for h in (1, 3):
    print(f"\n  horizon h={h}:")
    t = sub_df[sub_df.horizon == h].sort_values("__o")
    print(t[["subtype", "sign", "n", "mean_bps", "lo_bps", "hi_bps", "t", "sig"]]
          .to_string(index=False,
                     formatters={"mean_bps": "{:+.1f}".format, "lo_bps": "{:+.1f}".format,
                                 "hi_bps": "{:+.1f}".format, "t": "{:+.2f}".format}))

# ---- 1b. magnitude quintiles WITHIN clean subtypes ----
# Positive side (预增/略增): magnitude>0, bigger should be better (more positive abn).
# Negative side (预减/略减): magnitude<0, more negative should be worse (more negative abn).
def quintile_curve(mask, signed_label, abn, h, by_abs=False):
    sub = ev[mask].copy()
    a = abn[mask.values]
    sub = sub.assign(abn=a)
    key = sub["magnitude"].abs() if by_abs else sub["magnitude"]
    sub = sub[np.isfinite(key)]
    if len(sub) < 50:
        return None
    key = key.loc[sub.index]
    # rank into quintiles (Q1 = smallest key, Q5 = largest)
    sub = sub.assign(q=pd.qcut(key.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]))
    rows = []
    for q, g in sub.groupby("q", observed=True):
        m, lo, hi, t, n = boot_mean_ci(g["abn"].values, seed=23)
        rows.append(dict(quintile=int(q), n=n,
                         mag_lo=g["magnitude"].min(), mag_hi=g["magnitude"].max(),
                         mag_med=g["magnitude"].median(),
                         mean_bps=m * 1e4, lo_bps=lo * 1e4, hi_bps=hi * 1e4, t=t,
                         sig=bool(np.isfinite(lo) and (lo > 0 or hi < 0))))
    out = pd.DataFrame(rows)
    out.attrs["label"] = signed_label
    return out


print("\n\n--- 1b. MAGNITUDE-QUINTILE COEFFICIENT CURVE (within clean subtypes) ---")
print("    Q1 = smallest |growth|, Q5 = largest |growth|. This IS the empirical")
print("    basis for a signed coefficient: abn_CAR as a function of forecast strength.")

curves = {}
for h in (1, 3):
    abn = ABN[h]
    pos_mask = ev["subtype"].isin(CLEAN_POS)
    neg_mask = ev["subtype"].isin(CLEAN_NEG)
    cpos = quintile_curve(pos_mask, "POSITIVE 预增/略增 (signed magnitude asc)", abn, h)
    cneg = quintile_curve(neg_mask, "NEGATIVE 预减/略减 (signed magnitude asc; Q1=most negative)", abn, h)
    curves[(h, "pos")] = cpos
    curves[(h, "neg")] = cneg
    for tag, c in (("POS", cpos), ("NEG", cneg)):
        if c is None:
            continue
        print(f"\n  [h={h}] {c.attrs['label']}")
        print(c[["quintile", "n", "mag_lo", "mag_hi", "mag_med",
                 "mean_bps", "lo_bps", "hi_bps", "t", "sig"]]
              .to_string(index=False,
                         formatters={"mag_lo": "{:+.2f}".format, "mag_hi": "{:+.2f}".format,
                                     "mag_med": "{:+.2f}".format, "mean_bps": "{:+.1f}".format,
                                     "lo_bps": "{:+.1f}".format, "hi_bps": "{:+.1f}".format,
                                     "t": "{:+.2f}".format}))
        # monotonicity diagnostics
        mv = c["mean_bps"].values
        if tag == "POS":
            sp = pearman = None
            rho = pd.Series(mv).corr(pd.Series(c["quintile"].values), method="spearman")
            mono = np.all(np.diff(mv) >= 0)
            print(f"     Q5-Q1 spread = {mv[-1]-mv[0]:+.1f} bps ; "
                  f"Spearman(quintile,abn)={rho:+.2f} ; strictly-increasing={mono}")
        else:
            rho = pd.Series(mv).corr(pd.Series(c["quintile"].values), method="spearman")
            # for the negative side Q1=most negative magnitude -> expect Q1 most negative abn
            # i.e. abn should INCREASE (toward 0) as we go Q1->Q5; spread Q5-Q1>0 = monotone
            mono = np.all(np.diff(mv) >= 0)
            print(f"     Q5-Q1 spread = {mv[-1]-mv[0]:+.1f} bps "
                  f"(expect >0: bigger drop -> more negative abn) ; "
                  f"Spearman={rho:+.2f} ; increasing={mono}")

# ---- 1c. sign x magnitude interaction: does a BIG 预增 beat a SMALL 预增? ----
print("\n\n--- 1c. SIGN x MAGNITUDE INTERACTION (big vs small within each clean type) ---")
print("    Within 预增 and within 预减, split at the median |magnitude|; test big-minus-small.")
for h in (1, 3):
    abn = ABN[h]
    print(f"\n  h={h}:")
    for st in ["预增", "略增", "预减", "略减"]:
        m = ev["subtype"] == st
        sub = ev[m].assign(abn=abn[m.values])
        sub = sub[np.isfinite(sub["magnitude"]) & np.isfinite(sub["abn"])]
        if len(sub) < 40:
            continue
        med = sub["magnitude"].abs().median()
        big = sub[sub["magnitude"].abs() >= med]["abn"].values
        small = sub[sub["magnitude"].abs() < med]["abn"].values
        mb, *_ , nb = boot_mean_ci(big, seed=31)
        ms, *_ , ns = boot_mean_ci(small, seed=32)
        # diff CI via bootstrap of the difference of means
        rng = np.random.default_rng(7)
        bb = big[rng.integers(0, len(big), (3000, len(big)))].mean(1)
        ss = small[rng.integers(0, len(small), (3000, len(small)))].mean(1)
        d = bb - ss
        dlo, dhi = np.percentile(d, [2.5, 97.5])
        dmean = mb - ms
        dsig = (dlo > 0 or dhi < 0)
        print(f"    {st:>3}: big(|mag|>=med, n={nb}) {bps(mb)}bps  vs  small(n={ns}) {bps(ms)}bps "
              f" | big-small = {dmean*1e4:+.1f}bps [{dlo*1e4:+.1f},{dhi*1e4:+.1f}] sig={dsig}")


# ════════════════════════════════════════════════════════════════
# TASK 2 — P&L ROBUSTNESS
# ════════════════════════════════════════════════════════════════
hr("TASK 2 — P&L ROBUSTNESS (per-fold, cost sensitivity, extreme-event removal)")

def pnl_table(ev, h, long_short, cost_bps, trim_pct=0.0, winsor_pct=0.0,
              method="size"):
    """Per-fold mean abnormal of the signed strategy net of cost, with optional
    trimming (drop top/bottom trim_pct of LONG-leg+SHORT-leg abnormal returns) or
    winsorizing. Returns (per_fold_df, summary)."""
    evf = E.walk_forward_folds(ev)
    abn = E.abnormal_series(evf, h, method=method)
    e2 = evf.assign(abn=abn).dropna(subset=["abn"])
    cost = cost_bps / 1e4
    # build leg returns: long = +abn for sign>0 ; short leg = -abn for sign<0
    longs = e2[e2["sign"] > 0].assign(leg=lambda d: d["abn"])
    shorts = e2[e2["sign"] < 0].assign(leg=lambda d: -d["abn"])
    legs = pd.concat([longs, shorts]) if long_short else longs.copy()
    legs = legs.copy()
    # optional extreme handling applied to the strategy LEG return distribution
    if trim_pct > 0:
        lo, hi = np.percentile(legs["leg"], [trim_pct * 100, (1 - trim_pct) * 100])
        legs = legs[(legs["leg"] >= lo) & (legs["leg"] <= hi)]
    if winsor_pct > 0:
        lo, hi = np.percentile(legs["leg"], [winsor_pct * 100, (1 - winsor_pct) * 100])
        legs["leg"] = legs["leg"].clip(lo, hi)
    rows = []
    for fold, g in legs.groupby("fold"):
        net = g["leg"].mean() - cost
        rows.append(dict(fold=fold, n=len(g), gross_bps=g["leg"].mean() * 1e4,
                         net_bps=net * 1e4, win=bool(net > 0)))
    pf = pd.DataFrame(rows).sort_values("fold").reset_index(drop=True)
    wins = int(pf["win"].sum()); nf = len(pf)
    summ = dict(h=h, long_short=long_short, cost_bps=cost_bps, trim_pct=trim_pct,
                winsor_pct=winsor_pct, folds=nf, wins=wins,
                win_rate=wins / nf if nf else np.nan,
                mean_net_bps=pf["net_bps"].mean(),
                pass_majority=bool(nf and wins > nf / 2))
    return pf, summ

print("\n--- 2a. baseline per-fold P&L (25bps round-trip) ---")
for h in (1, 3):
    for ls in (False, True):
        pf, s = pnl_table(ev, h, ls, 25)
        tag = "LONG-SHORT" if ls else "LONG-ONLY "
        print(f"\n  [h={h}] {tag} @25bps -> wins {s['wins']}/{s['folds']}  "
              f"mean_net={s['mean_net_bps']:+.1f}bps  pass={s['pass_majority']}")
        print(pf.to_string(index=False,
                           formatters={"gross_bps": "{:+.1f}".format, "net_bps": "{:+.1f}".format}))

print("\n\n--- 2b. cost sensitivity (15 / 25 / 40 bps) ---")
cost_rows = []
for h in (1, 3):
    for ls in (False, True):
        for cb in (15, 25, 40):
            _, s = pnl_table(ev, h, ls, cb)
            cost_rows.append(dict(h=h, strat="LS" if ls else "LO", cost_bps=cb,
                                  wins=s["wins"], folds=s["folds"],
                                  mean_net_bps=s["mean_net_bps"],
                                  pass_majority=s["pass_majority"]))
cost_df = pd.DataFrame(cost_rows)
print(cost_df.to_string(index=False, formatters={"mean_net_bps": "{:+.1f}".format}))

print("\n\n--- 2c. EXTREME-EVENT ROBUSTNESS: is the edge carried by a few outliers? ---")
print("    Drop top & bottom 1% of strategy-leg abnormal returns; also winsorize at 1%.")
ext_rows = []
for h in (1, 3):
    for ls in (False, True):
        _, base = pnl_table(ev, h, ls, 25)
        _, trim = pnl_table(ev, h, ls, 25, trim_pct=0.01)
        _, wins = pnl_table(ev, h, ls, 25, winsor_pct=0.01)
        ext_rows.append(dict(h=h, strat="LS" if ls else "LO",
                             base_net_bps=base["mean_net_bps"], base_wins=f"{base['wins']}/{base['folds']}",
                             trim1_net_bps=trim["mean_net_bps"], trim1_wins=f"{trim['wins']}/{trim['folds']}",
                             wins1_net_bps=wins["mean_net_bps"], wins1_wins=f"{wins['wins']}/{wins['folds']}"))
ext_df = pd.DataFrame(ext_rows)
print(ext_df.to_string(index=False,
                       formatters={"base_net_bps": "{:+.1f}".format,
                                   "trim1_net_bps": "{:+.1f}".format,
                                   "wins1_net_bps": "{:+.1f}".format}))


# ════════════════════════════════════════════════════════════════
# TASK 3 — WALK-FORWARD OOS SIGN ACCURACY
# ════════════════════════════════════════════════════════════════
hr("TASK 3 — WALK-FORWARD OOS SIGN ACCURACY (overall + by side)")

def oos_breakdown(ev, h, side=None, method="size"):
    """sign-accuracy with 95% binomial CI. side=+1/-1 restricts to that event sign."""
    evf = E.walk_forward_folds(ev)
    abn = E.abnormal_series(evf, h, method=method)
    e2 = evf.assign(abn=abn).dropna(subset=["abn"])
    e2 = e2[e2["sign"] != 0]
    if side is not None:
        e2 = e2[e2["sign"] == side]
    hit = (np.sign(e2["abn"]) == np.sign(e2["sign"])).astype(int)
    n, k = len(hit), int(hit.sum())
    if n < 30:
        return dict(n=n, acc=np.nan, ci_lo=np.nan, ci_hi=np.nan, pass50=False)
    p = k / n
    se = np.sqrt(p * (1 - p) / n)
    per_fold = e2.assign(hit=hit).groupby("fold")["hit"].agg(["mean", "size"])
    return dict(n=n, acc=p, ci_lo=p - 1.96 * se, ci_hi=p + 1.96 * se,
                pass50=bool(p - 1.96 * se > 0.5),
                per_fold={f: (round(m, 3), int(sz)) for f, (m, sz) in per_fold.iterrows()})

for h in (1, 3):
    print(f"\n--- h={h} ---")
    overall = E.kill2_oos_sign(ev, h=h)  # library version (matches K2 spec exactly)
    print(f"  OVERALL (lib kill2): acc={overall['acc']:.4f}  ci_lo={overall['ci_lo']:.4f}  "
          f"n={overall['n']}  PASS(ci_lo>0.5)={overall['pass']}")
    print(f"           per-fold acc: {overall['per_fold']}")
    pos = oos_breakdown(ev, h, side=1.0)
    neg = oos_breakdown(ev, h, side=-1.0)
    print(f"  +SIGN only: acc={pos['acc']:.4f}  ci=[{pos['ci_lo']:.4f},{pos['ci_hi']:.4f}]  "
          f"n={pos['n']}  pass50={pos['pass50']}")
    print(f"  -SIGN only: acc={neg['acc']:.4f}  ci=[{neg['ci_lo']:.4f},{neg['ci_hi']:.4f}]  "
          f"n={neg['n']}  pass50={neg['pass50']}")
    print(f"     +side per-fold (acc,n): {pos['per_fold']}")
    print(f"     -side per-fold (acc,n): {neg['per_fold']}")


# ════════════════════════════════════════════════════════════════
# TASK 4 — EXPLICIT KILL VERDICTS
# ════════════════════════════════════════════════════════════════
hr("TASK 4 — EXPLICIT KILL #1 / #2 / #3 VERDICTS (h=1 and h=3)")

study = E.event_study(ev, horizons=(1, 3, 5, 10), by="sign")
print("\nreference: abnormal CAR by sign (size-adj):")
print(study.to_string(index=False))

for h in (1, 3):
    print(f"\n{'-'*70}\nHORIZON h={h}\n{'-'*70}")
    # K1
    k1 = E.kill1_monotonic_significant(study, horizon=h)
    print(f"K1 monotonic+significant: PASS={k1['pass']}  "
          f"pos_mean={bps(k1.get('pos_mean', np.nan))}bps (sig={k1.get('pos_sig')})  "
          f"neg_mean={bps(k1.get('neg_mean', np.nan))}bps (sig={k1.get('neg_sig')})  "
          f"spread={bps(k1.get('spread', np.nan))}bps")
    # K2
    k2 = E.kill2_oos_sign(ev, h=h)
    print(f"K2 OOS sign-acc>50% (ci_lo>0.5): PASS={k2['pass']}  "
          f"acc={k2['acc']:.4f}  ci_lo={k2['ci_lo']:.4f}  n={k2['n']}")
    # K3 at the three cost levels, long-only and long-short
    print("K3 portfolio majority-of-folds net>0:")
    for ls in (False, True):
        tag = "LS" if ls else "LO"
        cells = []
        for cb in (15, 25, 40):
            s, _ = E.kill3_portfolio_majority(ev, h=h, cost_bps=cb, long_short=ls)
            cells.append(f"{cb}bps: {s['wins']}/{s['folds']} net={s['mean_net']*1e4:+.1f}bps "
                         f"PASS={s['pass']}")
        print(f"   [{tag}] " + " | ".join(cells))

# ───── after-cost edge per event (honest, bps) ─────
hr("AFTER-COST EDGE PER EVENT (bps) — the deployable number")
print("""
Edge per event = mean strategy-leg abnormal return minus round-trip cost.
Long-only: average over +sign events only (the only ones you'd act on long).
Long-short: average over both legs (long +sign, short -sign).
Gross is the size-decile-adjusted abnormal CAR; net subtracts 25bps.
""")
for h in (1, 3):
    abn = ABN[h]
    e2 = ev.assign(abn=abn).dropna(subset=["abn"])
    long_gross = e2[e2["sign"] > 0]["abn"].mean()
    short_gross = (-e2[e2["sign"] < 0]["abn"]).mean()
    ls_gross = pd.concat([e2[e2["sign"] > 0]["abn"], -e2[e2["sign"] < 0]["abn"]]).mean()
    for cb in (15, 25, 40):
        c = cb / 1e4
        print(f"  h={h} cost={cb}bps | LONG-ONLY net={bps(long_gross-c)}bps "
              f"(gross {bps(long_gross)}) | SHORT-leg net={bps(short_gross-c)}bps "
              f"(gross {bps(short_gross)}) | LONG-SHORT avg-leg net={bps(ls_gross-c)}bps "
              f"(gross {bps(ls_gross)})")

print("\n[done]")
