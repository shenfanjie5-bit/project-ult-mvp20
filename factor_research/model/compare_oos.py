#!/usr/bin/env python3
"""Apples-to-apples head-to-head: evaluate ANY model config vs the production
base_score on the IDENTICAL cells where base_score exists (250-stock sample x 14
monthly dates, 2024-01..2025-12), out-of-sample and walk-forward.

For each realbase date De:
  * compute the 26 PIT features for the full universe AT De (reusing panel.py),
  * neutralize them the same way,
  * fit the config on the MAIN panel's base dates strictly < De (walk-forward),
  * predict the De cross-section, restrict to that date's base_score universe,
  * compare model vs base_score deciles/top-excess on the SAME stocks.

Builds factor_research/model/panel_realbase.npz once (cache).
CLI: compare_oos.py --config '<json|path>' --horizon 10
"""
from __future__ import annotations
import argparse, json, os, sqlite3, sys
import numpy as np
sys.path.insert(0, os.getcwd())
os.environ.setdefault("DOCKCASE_WRITEBACK", "0")
from factor_research._datalib import load_price_matrices, load_quarterly_earnings
from factor_research.model import panel as P
from factor_research.model import harness as H

HERE = os.path.dirname(os.path.abspath(__file__))
RB_DB = "factor_research/pit_extra/realbase.sqlite"
RB_CACHE = os.path.join(HERE, "panel_realbase.npz")
FEAT_ORDER = None  # set from panel_meta


def _feat_order():
    return json.load(open(os.path.join(HERE, "panel_meta.json")))["feat_names"]


def build_realbase_panel():
    """features + fwd + regimes at the 14 base_score dates, full universe."""
    if os.path.exists(RB_CACHE):
        d = np.load(RB_CACHE, allow_pickle=True)
        return d
    RET, TO, MV, cal, cols = load_price_matrices("20230101")
    con = sqlite3.connect(f"file:{RB_DB}?mode=ro", uri=True)
    rb_dates = [r[0] for r in con.execute("SELECT DISTINCT base_date FROM scores ORDER BY base_date")]
    con.close()
    base_idx = []
    used_dates = []
    for bd in rb_dates:
        cand = [d for d in cal if d <= bd]
        if not cand:
            continue
        base_idx.append(cal.index(cand[-1]))
        used_dates.append(bd)
    pfeat, lnmv_raw, CUM, HAS, first_valid, mkt = P.price_features(RET, TO, MV, cal, base_idx)
    fwd = P.forward_returns(CUM, HAS, first_valid, base_idx, (5, 10, 20))
    vfeat = P.value_features(cols, cal, base_idx)
    qfeat = P.quality_features(cols, cal, base_idx)
    earn = load_quarterly_earnings(cols, start="20180101")
    efeat = P.earnings_features(cols, cal, base_idx, earn)
    regs = P.regime_tags(mkt, None, base_idx, cal)
    from pit_backtest import universe
    ind_map = universe.primary_industry_map()
    meta = json.load(open(os.path.join(HERE, "panel_meta.json")))
    ind_names = meta["industry_names"]
    ind_code = {nm: i for i, nm in enumerate(ind_names)}
    industry = np.array([ind_code.get(ind_map.get(c, "UNKNOWN"), -1) for c in cols], np.int32)
    allf = {}; allf.update(vfeat); allf.update(qfeat)
    allf.update({"sue": efeat["sue"], "npq_yoy": efeat["npq_yoy"]}); allf.update(pfeat)
    order = meta["feat_names"]
    feat = np.stack([allf[nm] for nm in order], axis=2).astype(np.float32)
    np.savez_compressed(RB_CACHE, feat=feat, fwd5=fwd[5], fwd10=fwd[10], fwd20=fwd[20],
                        ln_mv=lnmv_raw.astype(np.float32), industry=industry,
                        base_dates=np.array(used_dates), regimes=np.array([r["regime"] for r in regs]),
                        cols=np.array(cols))
    return np.load(RB_CACHE, allow_pickle=True)


def main(cfg, horizon=10):
    order = _feat_order()
    # main panel (training source) — neutralized
    zmain, meta = H.load_panel()
    Zmain = H.neutralize(zmain, meta)
    fwd_main = zmain[f"fwd{horizon}"].astype(np.float64)
    main_dates = meta["base_dates"]
    main_regs = [r["regime"] for r in meta["regimes"]]
    # realbase panel (test cells) — neutralize independently (per-date, self-contained)
    rb = build_realbase_panel()
    Zrb = H.neutralize({"feat": rb["feat"], "ln_mv": rb["ln_mv"], "industry": rb["industry"]}, None, cache=False)
    fwd_rb = rb[f"fwd{horizon}"].astype(np.float64)
    rb_dates = [str(x) for x in rb["base_dates"]]
    rb_regs = [str(x) for x in rb["regimes"]]
    cols = [str(x) for x in rb["cols"]]
    colidx = {c: j for j, c in enumerate(cols)}

    feats = list(cfg["features"]); idx = [order.index(f) for f in feats]
    method = cfg["method"]; params = cfg.get("params", {}); fitter = H.FITTERS[method]
    min_train = cfg.get("min_train_dates", 12)

    # base_score per (date, ts)
    con = sqlite3.connect(f"file:{RB_DB}?mode=ro", uri=True)
    bs_of = {}
    for bd in rb_dates:
        bs_of[bd] = {ts: bs for ts, bs in con.execute(
            "SELECT ts_code, base_score FROM scores WHERE base_date=?", (bd,)) if bs is not None}
    con.close()

    rows = []
    for e, De in enumerate(rb_dates):
        tr = [i for i, d in enumerate(main_dates) if d < De]
        if len(tr) < min_train:
            continue
        Ztr = Zmain[tr][:, :, idx]; ytr = fwd_main[tr]
        Zte = Zrb[e][:, idx]
        ctx = {"train_reg": [main_regs[i] for i in tr], "test_reg": rb_regs[e], "test_idx": e}
        try:
            sc = fitter(Ztr, ytr, Zte, feats, params, ctx)
        except Exception as ex:
            print(f"  [warn] {De} fit failed: {ex}", file=sys.stderr); continue
        # restrict to this date's base_score universe
        uni = [ts for ts in bs_of[De] if ts in colidx]
        ji = np.array([colidx[ts] for ts in uni])
        msc = sc[ji]; bsc = np.array([bs_of[De][ts] for ts in uni]); rt = fwd_rb[e][ji]
        ok = np.isfinite(msc) & np.isfinite(rt) & np.isfinite(bsc)
        if ok.sum() < 50:
            continue
        msc, bsc, rt = msc[ok], bsc[ok], rt[ok]
        uni_mean = float(rt.mean())
        def topexc(score):
            dec = H._deciles(score, rt, 5)
            return (float(dec[-1] - dec[0]), float(dec[-1] - uni_mean)) if dec is not None else (np.nan, np.nan)
        m_q, m_top = topexc(msc); b_q, b_top = topexc(bsc)
        rows.append({"date": De, "n": int(ok.sum()), "regime": rb_regs[e], "uni_mean": uni_mean,
                     "model_ic": H._spearman(msc, rt), "base_ic": H._spearman(bsc, rt),
                     "model_q5q1": m_q, "base_q5q1": b_q,
                     "model_top_excess": m_top, "base_top_excess": b_top})

    def agg(key):
        v = np.array([r[key] for r in rows if np.isfinite(r[key])])
        return {"mean": float(v.mean()), "pos%": float((v > 0).mean()),
                "t": float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))) if len(v) > 1 else None,
                "ci": H._boot_ci([r[key] for r in rows])} if len(v) else None
    summary = {"horizon": horizon, "n_dates": len(rows), "config_name": cfg.get("name"),
               "MODEL": {k: agg(f"model_{k}") for k in ["ic", "q5q1", "top_excess"]},
               "BASE_SCORE": {k: agg(f"base_{k}") for k in ["ic", "q5q1", "top_excess"]},
               "per_date": rows}
    print(json.dumps({k: v for k, v in summary.items() if k != "per_date"}, indent=1, default=float))
    print("\nPER-DATE (model vs base) top_excess:")
    for r in rows:
        print(f"  {r['date']} [{r['regime']:14}] n={r['n']:3}  model_topExc={r['model_top_excess']:+.4f}  base_topExc={r['base_top_excess']:+.4f}  (model_IC={r['model_ic']:+.2f} base_IC={r['base_ic']:+.2f})")
    json.dump(summary, open(os.path.join(HERE, "reports", "compare_oos.json"), "w"), indent=1, default=float)
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--horizon", type=int, default=10)
    a = ap.parse_args()
    cfg = json.load(open(a.config)) if os.path.exists(a.config) else json.loads(a.config)
    os.makedirs(os.path.join(HERE, "reports"), exist_ok=True)
    main(cfg, a.horizon)
