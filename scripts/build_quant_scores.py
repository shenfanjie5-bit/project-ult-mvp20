#!/usr/bin/env python3
"""Offline builder for the two-layer quant score artifact (Phase 1, gap G2).

Computes TODAY's cross-section features for the onboarded universe and maps
them through the FROZEN calibration (config/quant_score_params.json) into
``runtime/quant_score/A_share.json``, which ``server.handle_score`` attaches
as the ``quant`` block.

Feature math is imported from the AUDITED research modules
(factor_research/model/panel.py + _datalib) — scripts/ may depend on
factor_research/ (mvp20/ core must not); reusing the exact code is the
anti-drift guarantee that the production features equal the validated ones.

Data: DockCase by-symbol archives (daily / daily_basic / income). ``asof`` =
the latest trade date present in the archive; the server marks the artifact
stale after 10 days, so an unrefreshed archive degrades honestly.

Run nightly after the DockCase refresh:
  .venv/bin/python scripts/build_quant_scores.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time

import numpy as np
import pandas as pd

os.environ.setdefault("DOCKCASE_WRITEBACK", "0")
os.environ.setdefault("DOCKCASE_CACHE", "1")
sys.path.insert(0, os.getcwd())

from factor_research import _datalib  # noqa: E402  (audited research code)
from factor_research.model import panel as P  # noqa: E402

log = logging.getLogger("build_quant")

LOOKBACK_SESSIONS = 320  # > 252 (mom_12_1 warmup inside price_features)


def _universe() -> list[str]:
    from mvp20.quant_score import load_params  # noqa: F401 (ensures params exist)
    from pathlib import Path
    overlays = Path("config/stock_overlays")
    return sorted({p.stem for p in overlays.glob("*/*.yaml") if "." in p.stem})


def _load_matrices(codes: list[str]) -> tuple:
    """RET/TO/MV [n_days x n] for the last LOOKBACK_SESSIONS, live from the
    by-symbol archive (no research npz cache — that one is universe-frozen)."""

    di = _datalib._file_index(_datalib.DAILY)
    bi = _datalib._file_index(_datalib.DBASIC)
    rets, tos, mvs, pe_series = {}, {}, {}, {}
    for ts in codes:
        src_d = di.get(ts)
        if src_d is None:
            continue
        path_d, fname = (src_d if isinstance(src_d, tuple) else (src_d, str(src_d)))
        # same universe filter as the research calibration (_datalib): ST/PT/退
        # names are OUTSIDE the calibration universe — ±5% limit regime and
        # delisting risk were never in the bins, so they must not get
        # validated:true rows.
        if any(t in str(fname).upper() for t in ("ST", "PT", "退")):
            continue
        try:
            x = pd.read_csv(path_d, usecols=["trade_date", "pct_chg"],
                            dtype={"trade_date": str})
        except Exception:  # noqa: BLE001
            continue
        x = x.dropna(subset=["trade_date"]).sort_values("trade_date").tail(LOOKBACK_SESSIONS)
        if len(x) < 70:  # need >=60d history for the prob features
            continue
        rets[ts] = x.set_index("trade_date")["pct_chg"].astype(float) / 100.0
        src = bi.get(ts)
        if src is not None:
            try:
                b = pd.read_csv(src[0] if isinstance(src, tuple) else src,
                                usecols=["trade_date", "turnover_rate", "total_mv", "pe_ttm"],
                                dtype={"trade_date": str})
                b = b.dropna(subset=["trade_date"]).sort_values("trade_date")
                b = b.set_index("trade_date").tail(LOOKBACK_SESSIONS)
                tos[ts] = b["turnover_rate"].astype(float)
                mvs[ts] = b["total_mv"].astype(float)
                pe_series[ts] = b["pe_ttm"].astype(float)
            except Exception:  # noqa: BLE001
                pass
    R = pd.DataFrame(rets).sort_index()
    TO = pd.DataFrame(tos).reindex(index=R.index, columns=R.columns)
    MV = pd.DataFrame(mvs).reindex(index=R.index, columns=R.columns)
    # ep_ttm mirrors research panel.value_features: the daily_basic row AT (or
    # last before) the as-of date — NaN if pe_ttm is NaN on that row (loss-
    # makers stay excluded). NOT last-non-null (that would resurrect a stale
    # positive PE for names that turned loss-making — feature drift).
    asof = R.index[-1] if len(R.index) else None
    pe_last: dict[str, float | None] = {}
    for ts in R.columns:
        s = pe_series.get(ts)
        if s is None or asof is None:
            pe_last[ts] = None
            continue
        s2 = s[s.index <= asof]
        v = s2.iloc[-1] if len(s2) else None
        pe_last[ts] = float(v) if v is not None and v == v else None
    return (R.values, TO.values, MV.values, list(R.index), list(R.columns), pe_last)


def main() -> int:
    t0 = time.time()
    from mvp20 import quant_score
    from pit_backtest import universe as puni

    params = quant_score.load_params()
    if params is None:
        print("ERROR: run factor_research/model/export_params.py first", file=sys.stderr)
        return 2

    codes_all = _universe()
    log.info("onboarded universe: %d", len(codes_all))
    RET, TO, MV, cal, cols, pe_last = _load_matrices(codes_all)
    asof = cal[-1]
    k_last = len(cal) - 1
    log.info("matrices: %d stocks x %d days, asof=%s (%.0fs)",
             len(cols), len(cal), asof, time.time() - t0)

    # price/volume features at the last day — EXACT research math
    pfeat, lnmv_raw, CUM, HAS, first_valid, mkt = P.price_features(
        RET, TO, MV, cal, [k_last])
    # earnings features (sue / npq_yoy), PIT by ann_date <= asof
    earn = _datalib.load_quarterly_earnings(cols, start="20180101")
    efeat = P.earnings_features(cols, cal, [k_last], earn)
    log.info("features done, earnings coverage %d/%d (%.0fs)",
             len(earn), len(cols), time.time() - t0)

    ep = np.array([
        (1.0 / pe_last[ts]) if (pe_last.get(ts) not in (None, 0)) else np.nan
        for ts in cols
    ])
    feat_names = ["sue", "npq_yoy", "ivol_60", "max5", "turnover_20", "ep_ttm"]
    feat = np.column_stack([
        efeat["sue"][0], efeat["npq_yoy"][0],
        pfeat["ivol_60"][0], pfeat["max5"][0], pfeat["turnover_20"][0], ep,
    ])
    lnmv = lnmv_raw[0]

    ind_map = puni.primary_industry_map()
    ind_names = sorted(set(ind_map.get(c, "UNKNOWN") for c in cols))
    code_of = {nm: i for i, nm in enumerate(ind_names)}
    industry = np.array([code_of.get(ind_map.get(c, "UNKNOWN"), -1) for c in cols],
                        dtype=np.int32)

    artifact = quant_score.build_artifact(asof, cols, feat, feat_names, lnmv,
                                          industry, params)
    path = quant_score.save_artifact(artifact)
    print(json.dumps({
        "artifact": str(path), "asof": asof,
        "n_rows": artifact["n_rows"], "n_validated": artifact["n_validated"],
        "elapsed_s": round(time.time() - t0, 1),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    raise SystemExit(main())
