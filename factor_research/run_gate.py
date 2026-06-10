#!/usr/bin/env python3
"""Phase-3b RESULTS5: 'regime-as-gate' avoidance benefit — empirical quantification.

Research question: does a regime-gate (skip BUY signals in BAD regime) avoid
bad-regime drawdowns without sacrificing much good-regime upside?

Design:
  - Regime classifier: market 60d trend + 20d vol vs expanding/past-only median.
    BAD regime = up-trend (trend60>0) AND high-vol (vol20>expanding_median).
    Economic rationale: this is the "high-vol risk-on rally" where the model's
    reversal+low-vol tilts invert (proven in RESULTS2_regime_and_sue.md: corr
    market_vol↔RVOL_IC = +0.27; model fails when momentum beats reversal).
    NOTE: definition is economically motivated, NOT tuned on test data.
  - Avoidance test A (REAL base_score, 3 dates): BUY-cohort forward +10/+20d returns.
  - Avoidance test B (PROXY L=z(STREV)-z(RVOL), 2023-2026 many windows): top-decile
    BUY cohort — UNGATED vs GATED (skip BUY in BAD regime → 0/cash those windows).
  - Reuses run_prototype.py's regime(), zscore(), load_price_matrices() exactly.
"""
from __future__ import annotations
import os, sys, math, json, sqlite3, warnings
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
from pit_backtest.metrics import rank_ic
from factor_research._datalib import load_price_matrices

def log(*a): print(*a, flush=True)

LOOKBACK = 21    # reversal window (trading days ~1 month)
VOLWIN   = 20    # realized vol window
TRENDWIN = 60    # market trend window
HORIZONS = [10, 20]
DECILE   = 0.1   # top-decile = BUY proxy for proxy factor

# ─── helpers ────────────────────────────────────────────────────────────────

def zscore(v):
    m = np.isfinite(v)
    if m.sum() < 30: return np.full_like(v, np.nan)
    mu, sd = np.nanmean(v[m]), np.nanstd(v[m])
    if sd < 1e-9: return np.full_like(v, np.nan)
    z = (v - mu) / sd
    return np.clip(z, -3, 3)


def fwd_ret_vec(k, h, CUM, HAS, first_valid, n):
    """Forward +h-day simple return vector for all stocks at date index k."""
    if k + h >= n:
        return None
    fr = np.exp(CUM[k + h] - CUM[k]) - 1.0
    ok = HAS[k] & (first_valid <= k) & HAS[k + 1:k + h + 1].any(0)
    return np.where(ok, fr, np.nan)


def regime(k, mkt_cum, mvol_series):
    """Classify market regime at index k (exactly as run_prototype.py).

    Returns (trend60, vol20, vmed, label, is_bad).
    BAD = up-trend AND high-vol  (high-vol risk-on rally — model tilts invert).
    """
    trend60 = math.exp(mkt_cum[k] - mkt_cum[k - TRENDWIN]) - 1.0
    vol20   = mvol_series[k]
    past_vols = mvol_series[max(0, k - 250):k]
    past_vols = past_vols[np.isfinite(past_vols)]
    vmed = float(np.median(past_vols)) if len(past_vols) > 20 else 0.22
    trend_dir = "up" if trend60 > 0 else "dn"
    vol_state  = "hivol" if (np.isfinite(vol20) and vol20 > vmed) else "lovol"
    is_bad = (trend60 > 0) and (np.isfinite(vol20) and vol20 > vmed)
    label = f"{trend_dir}/{vol_state}"
    return trend60, float(vol20) if np.isfinite(vol20) else float("nan"), float(vmed), label, is_bad


def components(k, CUM, HAS, first_valid, RET, VOLWIN=VOLWIN, LOOKBACK=LOOKBACK):
    """Short-term reversal + realized vol (proxy factors, as in run_prototype)."""
    past = np.exp(CUM[k] - CUM[k - LOOKBACK]) - 1.0
    strev = -past  # reversal = negate past return
    rvol  = np.nanstd(RET[k - VOLWIN + 1:k + 1], axis=0, ddof=1) * math.sqrt(252)
    listed = (first_valid <= k - LOOKBACK) & HAS[k]
    sz = zscore(np.where(listed, strev, np.nan))
    rz = zscore(np.where(listed, rvol,  np.nan))
    return sz, rz


def cohort_stats(factor, fwd, top_frac=DECILE):
    """Return mean fwd return and hit-rate for top-decile of factor."""
    m = np.isfinite(factor) & np.isfinite(fwd)
    if m.sum() < 20:
        return float("nan"), float("nan"), 0
    f, r = factor[m], fwd[m]
    thresh = np.percentile(f, (1 - top_frac) * 100)
    top = r[f >= thresh]
    if len(top) == 0:
        return float("nan"), float("nan"), 0
    return float(np.mean(top)), float(np.mean(top > 0)), len(top)


def signal_cohort_stats(signal_mask, fwd):
    """Return stats for a boolean mask cohort (e.g., BUY signal)."""
    m = signal_mask & np.isfinite(fwd)
    if m.sum() < 5:
        return float("nan"), float("nan"), 0
    r = fwd[m]
    return float(np.mean(r)), float(np.mean(r > 0)), int(m.sum())


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    log("Loading price matrices…")
    RET, TO, MV, cal, cols = load_price_matrices("20230101")
    n, m = RET.shape
    LR  = np.log1p(np.nan_to_num(RET, nan=0.0))
    CUM = np.cumsum(LR, axis=0)
    HAS = ~np.isnan(RET)
    first_valid = np.where(HAS.any(0), HAS.argmax(0), n + 1)

    mkt     = np.nanmean(RET, axis=1)
    mkt_lr  = np.log1p(np.nan_to_num(mkt, 0.0))
    mkt_cum = np.cumsum(mkt_lr)
    mvol_series = np.array([
        np.std(mkt[max(0, k - VOLWIN + 1):k + 1], ddof=1) * math.sqrt(252)
        if k >= VOLWIN else np.nan
        for k in range(n)
    ])

    results = {
        "meta": {
            "note": "regime-as-gate avoidance study. BAD regime = trend60>0 AND vol20>expanding_median "
                    "(high-vol risk-on, where model's reversal+low-vol tilts invert). "
                    "Gate = skip BUY / top-decile in BAD regime (AVOIDANCE, not reversal). "
                    "Proxy factor L=z(STREV)-z(RVOL) (corr +0.5/-0.5 with real short_total). "
                    "Gate definition is economically motivated, NOT tuned on test data. "
                    "Caveat: 3 real dates (tiny n), overlapping proxy windows.",
        }
    }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PART A: REAL base_score at 3 dates
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    log("\n==== PART A: REAL base_score BUY-cohort analysis (3 dates) ====")
    c = sqlite3.connect("file:runtime/backtest/backtest.sqlite?mode=ro", uri=True)

    real_dates = {
        "20260116": None,
        "20260309": None,
        "20260421": None,
    }
    for bd in real_dates:
        # map to calendar index
        cand = [d for d in cal if d <= bd]
        if not cand:
            continue
        k = cal.index(cand[-1])
        tr, vol, vmed, reg_label, is_bad = regime(k, mkt_cum, mvol_series)

        # Fetch scores from DB
        rows = {r[0]: (r[1], r[2]) for r in c.execute(
            "SELECT ts_code, base_score, trading_signal FROM scores WHERE base_date=?", (bd,)
        )}
        bs   = np.array([rows.get(ts, (np.nan, ""))[0] for ts in cols])
        sigs = np.array([rows.get(ts, (np.nan, ""))[1] for ts in cols])
        buy_mask = np.array([s == "BUY" for s in sigs])

        # Fallback to top-decile if BUY count is < 20 (not needed here but defensive)
        n_buy = int(buy_mask.sum())
        use_topdecile = n_buy < 20
        if use_topdecile:
            thresh = np.nanpercentile(bs, 90)
            buy_mask = np.isfinite(bs) & (bs >= thresh)
            log(f"  {bd}: only {n_buy} BUY signals — using top-decile of base_score instead")

        date_res = {
            "regime": reg_label,
            "is_bad_regime": bool(is_bad),
            "trend60": round(tr, 4),
            "vol20": round(vol, 4),
            "vol_median": round(vmed, 4),
            "n_buy": n_buy,
            "used_topdecile": use_topdecile,
        }

        for h in HORIZONS:
            fr = fwd_ret_vec(k, h, CUM, HAS, first_valid, n)
            if fr is None:
                date_res[f"h{h}"] = None
                continue
            mean_r, hitrate, cnt = signal_cohort_stats(buy_mask, fr)
            ic_all   = rank_ic(bs, fr)["ic"]
            date_res[f"h{h}"] = {
                "buy_cohort_mean_ret": round(mean_r, 4) if np.isfinite(mean_r) else None,
                "buy_cohort_hitrate":  round(hitrate, 3) if np.isfinite(hitrate) else None,
                "buy_cohort_n":        cnt,
                "ic_base_score":       round(ic_all, 4) if np.isfinite(ic_all) else None,
            }

        real_dates[bd] = date_res
        regime_flag = " *** BAD REGIME ***" if is_bad else ""
        for h in HORIZONS:
            d = date_res.get(f"h{h}")
            if d is None:
                continue
            log(f"  {bd} [{reg_label}]{regime_flag}  +{h}d:  BUY cohort mean={d['buy_cohort_mean_ret']:+.3f}  "
                f"hitrate={d['buy_cohort_hitrate']:.2f}  n={d['buy_cohort_n']}  "
                f"IC(all)={d['ic_base_score']:+.4f}")

    c.close()
    results["real_dates"] = real_dates

    # Gate verdict on real dates
    log("\n  -> Gate verdict (skip BUY on 20260421 which is BAD regime):")
    # cumulative BUY-cohort mean return over good dates vs including bad date
    good_dates = [bd for bd, v in real_dates.items() if v and not v["is_bad_regime"]]
    bad_dates  = [bd for bd, v in real_dates.items() if v and v["is_bad_regime"]]
    log(f"     GOOD regime dates: {good_dates}")
    log(f"     BAD regime dates:  {bad_dates}")
    for h in HORIZONS:
        good_rets = [real_dates[bd][f"h{h}"]["buy_cohort_mean_ret"]
                     for bd in good_dates
                     if real_dates[bd].get(f"h{h}") and real_dates[bd][f"h{h}"]["buy_cohort_mean_ret"] is not None]
        all_rets  = [real_dates[bd][f"h{h}"]["buy_cohort_mean_ret"]
                     for bd in list(real_dates)
                     if real_dates[bd] and real_dates[bd].get(f"h{h}") and real_dates[bd][f"h{h}"]["buy_cohort_mean_ret"] is not None]
        if good_rets and all_rets:
            log(f"     +{h}d: UNGATED mean(all 3 dates)={np.mean(all_rets):+.4f}  "
                f"GATED(good-only)={np.mean(good_rets):+.4f}  "
                f"Δ GATED−UNGATED={np.mean(good_rets)-np.mean(all_rets):+.4f}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PART B: PROXY factor — many windows 2023-2026
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    log("\n==== PART B: PROXY L=z(STREV)-z(RVOL) top-decile gate study ====")

    min_k = max(LOOKBACK, TRENDWIN) + 1
    base_idx = [k for k in range(min_k, n - max(HORIZONS)) if k % 10 == 0]
    log(f"  Total base windows: {len(base_idx)}")

    # Per-window records
    records = []  # {yr, k, date, regime_label, is_bad, h10_ung, h10_gate, h20_ung, h20_gate, ...}
    for k in base_idx:
        sz, rz = components(k, CUM, HAS, first_valid, RET)
        L = sz - rz
        tr, vol, vmed, reg_label, is_bad = regime(k, mkt_cum, mvol_series)
        yr = cal[k][:4]

        rec = {
            "yr": yr, "k": k, "date": cal[k],
            "regime": reg_label, "is_bad": is_bad,
            "trend60": round(tr, 4),
            "vol20": round(vol, 4) if np.isfinite(vol) else None,
        }
        for h in HORIZONS:
            fr = fwd_ret_vec(k, h, CUM, HAS, first_valid, n)
            if fr is None:
                rec[f"h{h}_ung_ret"]  = None
                rec[f"h{h}_ung_hit"]  = None
                rec[f"h{h}_gate_ret"] = None
                rec[f"h{h}_gate_hit"] = None
                rec[f"h{h}_n"]        = 0
                continue
            mean_r, hitrate, cnt = cohort_stats(L, fr, top_frac=DECILE)
            rec[f"h{h}_ung_ret"]  = round(mean_r, 5) if np.isfinite(mean_r) else None
            rec[f"h{h}_ung_hit"]  = round(hitrate, 4) if np.isfinite(hitrate) else None
            # Gated: if BAD regime → 0 (cash, skip BUY)
            rec[f"h{h}_gate_ret"] = 0.0 if is_bad else rec[f"h{h}_ung_ret"]
            rec[f"h{h}_gate_hit"] = None if is_bad else rec[f"h{h}_ung_hit"]
            rec[f"h{h}_n"]        = cnt
        records.append(rec)

    # Aggregate stats
    def agg_stats(recs, h, gated=False):
        key_ret = f"h{h}_gate_ret" if gated else f"h{h}_ung_ret"
        key_hit = f"h{h}_gate_hit" if gated else f"h{h}_ung_hit"
        rets = [r[key_ret] for r in recs if r[key_ret] is not None]
        hits = [r[key_hit] for r in recs if r[key_hit] is not None]
        rets_arr = np.array(rets)
        if len(rets_arr) == 0:
            return {}
        return {
            "n_windows": len(rets),
            "mean_ret":  round(float(np.mean(rets_arr)), 5),
            "std_ret":   round(float(np.std(rets_arr)), 5),
            "median_ret": round(float(np.median(rets_arr)), 5),
            "worst_ret": round(float(np.min(rets_arr)), 5),
            "best_ret":  round(float(np.max(rets_arr)), 5),
            "hitrate":   round(float(np.mean(hits)), 4) if hits else None,
            "pct_positive": round(float(np.mean(rets_arr > 0)), 3),
        }

    total_windows = len(records)
    bad_windows  = sum(1 for r in records if r["is_bad"])
    log(f"  Bad-regime windows: {bad_windows}/{total_windows} "
        f"({bad_windows/total_windows*100:.1f}%)")

    proxy_res = {}
    for h in HORIZONS:
        ung  = agg_stats(records, h, gated=False)
        gate = agg_stats(records, h, gated=True)
        delta = round(gate["mean_ret"] - ung["mean_ret"], 5) if ung and gate else None
        # Worst windows: top 5 worst ungated returns
        worst5 = sorted([r for r in records if r.get(f"h{h}_ung_ret") is not None],
                        key=lambda r: r[f"h{h}_ung_ret"])[:5]
        worst5_info = [{
            "date": r["date"], "regime": r["regime"],
            "is_bad": r["is_bad"],
            "ung_ret": r[f"h{h}_ung_ret"],
            "gate_ret": r[f"h{h}_gate_ret"],
        } for r in worst5]

        # Per-year breakdown
        years = sorted(set(r["yr"] for r in records))
        per_year = {}
        for yr in years:
            yr_recs = [r for r in records if r["yr"] == yr]
            per_year[yr] = {
                "n_windows": len(yr_recs),
                "n_bad": sum(1 for r in yr_recs if r["is_bad"]),
                "ungated": agg_stats(yr_recs, h, gated=False),
                "gated":   agg_stats(yr_recs, h, gated=True),
            }

        proxy_res[f"h{h}"] = {
            "n_total_windows": total_windows,
            "n_bad_windows":   bad_windows,
            "frac_gated":      round(bad_windows / total_windows, 3),
            "ungated":   ung,
            "gated":     gate,
            "delta_gated_minus_ungated": delta,
            "worst5_windows_ungated":    worst5_info,
            "per_year":  per_year,
        }

        log(f"\n  +{h}d  UNGATED: mean={ung['mean_ret']:+.5f}  median={ung['median_ret']:+.5f}  "
            f"hitrate={ung['hitrate']:.3f}  worst={ung['worst_ret']:+.5f}")
        log(f"       GATED:   mean={gate['mean_ret']:+.5f}  median={gate['median_ret']:+.5f}  "
            f"worst={gate['worst_ret']:+.5f}  "
            f"Δ(gated−ung)={delta:+.5f}")
        log(f"       Fraction gated: {bad_windows}/{total_windows}={bad_windows/total_windows*100:.1f}%")
        log(f"       Per-year (ungated mean / gated mean / n_bad):")
        for yr in years:
            py = per_year[yr]
            ung_y  = py["ungated"].get("mean_ret", None)
            gate_y = py["gated"].get("mean_ret", None)
            log(f"         {yr}: ung={ung_y:+.4f}  gate={gate_y:+.4f}  "
                f"n_bad={py['n_bad']}/{py['n_windows']}")

    results["proxy_gate_study"] = proxy_res
    results["proxy_gate_study"]["bad_window_fraction"] = round(bad_windows / total_windows, 3)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PART C: IC-level gate analysis (complementary)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    log("\n==== PART C: IC-level gate (skip bad-regime from IC average) ====")
    ic_records = []
    for k in base_idx:
        sz, rz = components(k, CUM, HAS, first_valid, RET)
        L = sz - rz
        tr, vol, vmed, reg_label, is_bad = regime(k, mkt_cum, mvol_series)
        yr = cal[k][:4]
        for h in HORIZONS:
            fr = fwd_ret_vec(k, h, CUM, HAS, first_valid, n)
            if fr is None: continue
            ic_val = rank_ic(L, fr)["ic"]
            if not np.isfinite(ic_val): continue
            ic_records.append({"yr": yr, "h": h, "ic": ic_val, "is_bad": is_bad, "regime": reg_label})

    ic_res = {}
    for h in HORIZONS:
        recs = [r for r in ic_records if r["h"] == h]
        all_ic  = np.array([r["ic"] for r in recs])
        good_ic = np.array([r["ic"] for r in recs if not r["is_bad"]])
        bad_ic  = np.array([r["ic"] for r in recs if r["is_bad"]])
        log(f"\n  +{h}d IC:  all-windows mean={np.mean(all_ic):+.4f}  "
            f"good-regime mean={np.mean(good_ic):+.4f}  "
            f"bad-regime mean={np.mean(bad_ic):+.4f}")
        ic_res[f"h{h}"] = {
            "all_mean_ic":  round(float(np.mean(all_ic)),  4),
            "good_mean_ic": round(float(np.mean(good_ic)), 4),
            "bad_mean_ic":  round(float(np.mean(bad_ic)),  4),
            "n_all": len(all_ic), "n_good": len(good_ic), "n_bad": len(bad_ic),
        }
    results["ic_gate_analysis"] = ic_res

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Save JSON
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _to_json(obj):
        """Recursively convert non-serializable types to native Python."""
        if isinstance(obj, dict):
            return {k: _to_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_to_json(v) for v in obj]
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj) if np.isfinite(obj) else None
        return obj

    out_path = "factor_research/data/gate_results.json"
    os.makedirs("factor_research/data", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(_to_json(results), f, ensure_ascii=False, indent=2)
    log(f"\nWrote {out_path}")
    return results


if __name__ == "__main__":
    main()
