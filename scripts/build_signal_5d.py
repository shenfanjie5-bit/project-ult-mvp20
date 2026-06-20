#!/usr/bin/env python3
"""Build the A-share 5d relative signal artifact.

Input data:
  DockCase by-symbol daily / daily_basic archives via scripts.build_quant_scores

Output:
  runtime/signal_5d/A_share.json

Run after DockCase refresh:
  .venv/bin/python scripts/build_signal_5d.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time

import numpy as np

os.environ.setdefault("DOCKCASE_WRITEBACK", "0")
os.environ.setdefault("DOCKCASE_CACHE", "1")
sys.path.insert(0, os.getcwd())

from factor_research.model import panel as P  # noqa: E402
from pit_backtest import universe as puni  # noqa: E402
from scripts import build_quant_scores as bq  # noqa: E402
from mvp20 import signal_5d  # noqa: E402


log = logging.getLogger("build_signal_5d")


def main() -> int:
    t0 = time.time()
    params = signal_5d.load_params()
    if params is None:
        print(
            "ERROR: run factor_research/model/export_signal_5d_params.py first",
            file=sys.stderr,
        )
        return 2

    codes_all = bq._universe()
    log.info("onboarded universe: %d", len(codes_all))
    ret, to, mv, cal, cols, pe_last = bq._load_matrices(codes_all)
    if len(cal) == 0 or len(cols) == 0:
        print("ERROR: no DockCase daily/daily_basic rows loaded", file=sys.stderr)
        return 2
    asof = cal[-1]
    k_last = len(cal) - 1
    log.info("matrices: %d stocks x %d days, asof=%s", len(cols), len(cal), asof)

    pfeat, lnmv_raw, *_ = P.price_features(ret, to, mv, cal, [k_last])
    ep = np.array([
        (1.0 / pe_last[ts]) if (pe_last.get(ts) not in (None, 0)) else np.nan
        for ts in cols
    ])
    feat_names = [
        "ivol_60",
        "ep_ttm",
        "strev",
        "max5",
        "turnover_20",
        "rvol_20",
        "mom_6_1",
    ]
    feat = np.column_stack([
        pfeat["ivol_60"][0],
        ep,
        pfeat["strev"][0],
        pfeat["max5"][0],
        pfeat["turnover_20"][0],
        pfeat["rvol_20"][0],
        pfeat["mom_6_1"][0],
    ])
    lnmv = lnmv_raw[0]

    ind_map = puni.primary_industry_map()
    ind_names = sorted(set(ind_map.get(c, "UNKNOWN") for c in cols))
    code_of = {nm: i for i, nm in enumerate(ind_names)}
    industry = np.array([code_of.get(ind_map.get(c, "UNKNOWN"), -1) for c in cols],
                        dtype=np.int32)

    artifact = signal_5d.build_artifact(asof, cols, feat, feat_names, lnmv,
                                        industry, params)
    path = signal_5d.save_artifact(artifact)
    print(json.dumps({
        "artifact": str(path),
        "asof": asof,
        "horizon_days": artifact["horizon_days"],
        "target": artifact["target"],
        "n_rows": artifact["n_rows"],
        "n_validated": artifact["n_validated"],
        "validated_ratio": artifact["coverage"]["validated_ratio"],
        "elapsed_s": round(time.time() - t0, 1),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    raise SystemExit(main())
