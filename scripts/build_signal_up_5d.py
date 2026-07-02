#!/usr/bin/env python3
"""Build the A-share absolute 5d upside probability artifact.

Input data:
  DockCase by-symbol daily / daily_basic archives via scripts.build_quant_scores

Output:
  runtime/signal_up_5d/A_share.json
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
from mvp20 import signal_up_5d  # noqa: E402


log = logging.getLogger("build_signal_up_5d")


def _rolling_return(ret: np.ndarray, k: int, window: int) -> np.ndarray:
    if k - window < 0:
        return np.full(ret.shape[1], np.nan, dtype=float)
    win = ret[k - window + 1:k + 1]
    cnt = np.isfinite(win).sum(axis=0)
    lr = np.log1p(np.nan_to_num(win, nan=0.0))
    val = np.exp(lr.sum(axis=0)) - 1.0
    return np.where(cnt >= max(1, int(window * 0.6)), val, np.nan)


def _rsi_14(ret: np.ndarray, k: int) -> np.ndarray:
    if k - 14 < 0:
        return np.full(ret.shape[1], np.nan, dtype=float)
    win = ret[k - 13:k + 1]
    cnt = np.isfinite(win).sum(axis=0)
    gains = np.where(np.isfinite(win) & (win > 0), win, 0.0)
    losses = np.where(np.isfinite(win) & (win < 0), -win, 0.0)
    avg_gain = gains.sum(axis=0) / np.maximum(cnt, 1)
    avg_loss = losses.sum(axis=0) / np.maximum(cnt, 1)
    rs = avg_gain / np.where(avg_loss > 1e-12, avg_loss, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi = np.where((avg_loss <= 1e-12) & (avg_gain > 0), 100.0, rsi)
    rsi = np.where((avg_loss <= 1e-12) & (avg_gain <= 1e-12), 50.0, rsi)
    return np.where(cnt >= 10, rsi, np.nan)


def _vol_20(ret: np.ndarray, k: int) -> np.ndarray:
    if k - 20 < 0:
        return np.full(ret.shape[1], np.nan, dtype=float)
    win = ret[k - 19:k + 1]
    cnt = np.isfinite(win).sum(axis=0)
    return np.where(cnt >= 12, np.nanstd(win, axis=0), np.nan)


def _drawdown_20(ret: np.ndarray, k: int) -> np.ndarray:
    if k - 20 < 0:
        return np.full(ret.shape[1], np.nan, dtype=float)
    win = ret[k - 19:k + 1]
    cnt = np.isfinite(win).sum(axis=0)
    lr = np.log1p(np.nan_to_num(win, nan=0.0))
    px = np.exp(np.cumsum(lr, axis=0))
    peak = np.maximum.accumulate(px, axis=0)
    dd = px[-1] / np.where(peak.max(axis=0) > 0, peak.max(axis=0), np.nan) - 1.0
    return np.where(cnt >= 12, dd, np.nan)


def _weighted_market_return(ret_window: np.ndarray, mv_row: np.ndarray) -> np.ndarray:
    ok = np.isfinite(ret_window) & np.isfinite(mv_row) & (mv_row > 0)
    out = np.full(ret_window.shape, np.nan, dtype=float)
    if ok.sum() >= 30:
        out[:] = float(np.average(ret_window[ok], weights=mv_row[ok]))
    return out


def _industry_return(ret_window: np.ndarray, industry: np.ndarray) -> np.ndarray:
    out = np.full(ret_window.shape, np.nan, dtype=float)
    for ind in sorted(set(int(x) for x in industry if int(x) >= 0)):
        sel = industry == ind
        vals = ret_window[sel]
        ok = np.isfinite(vals)
        if ok.sum() >= 3:
            out[sel] = float(np.mean(vals[ok]))
    return out


def _feature_matrix(
    ret: np.ndarray,
    to: np.ndarray,
    mv: np.ndarray,
    cal: list[str],
    k_last: int,
    cols: list[str],
    industry: np.ndarray,
) -> tuple[np.ndarray, list[str], np.ndarray]:
    del cols
    pfeat, lnmv_raw, *_ = P.price_features(ret, to, mv, cal, [k_last])
    ret_1d = ret[k_last]
    ret_5d = _rolling_return(ret, k_last, 5)
    ret_20d = _rolling_return(ret, k_last, 20)
    ret_60d = _rolling_return(ret, k_last, 60)
    rsi_14 = _rsi_14(ret, k_last)
    vol_20d = _vol_20(ret, k_last)
    drawdown_20 = _drawdown_20(ret, k_last)
    market_ret_5d = _weighted_market_return(ret_5d, mv[k_last])
    market_ret_20d = _weighted_market_return(ret_20d, mv[k_last])
    industry_ret_5d = _industry_return(ret_5d, industry)
    industry_ret_20d = _industry_return(ret_20d, industry)
    feat_names = list(signal_up_5d.MODEL_FEATURES)
    feat = np.column_stack([
        ret_1d,
        ret_5d,
        ret_20d,
        ret_60d,
        pfeat["mom_6_1"][0],
        rsi_14,
        vol_20d,
        pfeat["ivol_60"][0],
        pfeat["max5"][0],
        pfeat["turnover_20"][0],
        pfeat["rvol_20"][0],
        drawdown_20,
        market_ret_5d,
        market_ret_20d,
        industry_ret_5d,
        industry_ret_20d,
    ])
    return feat, feat_names, lnmv_raw[0]


def main() -> int:
    t0 = time.time()
    params = signal_up_5d.load_params()
    if params is None:
        print(
            "ERROR: run factor_research/model/export_signal_up_5d_params.py first",
            file=sys.stderr,
        )
        return 2

    codes_all = bq._universe()
    log.info("onboarded universe: %d", len(codes_all))
    ret, to, mv, cal, cols, _pe_last = bq._load_matrices(codes_all)
    if len(cal) == 0 or len(cols) == 0:
        print("ERROR: no DockCase daily/daily_basic rows loaded", file=sys.stderr)
        return 2
    asof = cal[-1]
    k_last = len(cal) - 1
    log.info("matrices: %d stocks x %d days, asof=%s", len(cols), len(cal), asof)

    ind_map = puni.primary_industry_map()
    ind_names = sorted(set(ind_map.get(c, "UNKNOWN") for c in cols))
    code_of = {nm: i for i, nm in enumerate(ind_names)}
    industry = np.array([code_of.get(ind_map.get(c, "UNKNOWN"), -1) for c in cols],
                        dtype=np.int32)

    feat, feat_names, lnmv = _feature_matrix(ret, to, mv, cal, k_last, cols, industry)
    artifact = signal_up_5d.build_artifact(
        asof, cols, feat, feat_names, lnmv, industry, params,
    )
    path = signal_up_5d.save_artifact(artifact)
    print(json.dumps({
        "artifact": str(path),
        "asof": asof,
        "horizon_days": artifact["horizon_days"],
        "target": artifact["target"],
        "target_kind": artifact["target_kind"],
        "n_rows": artifact["n_rows"],
        "n_validated": artifact["n_validated"],
        "validated_ratio": artifact["coverage"]["validated_ratio"],
        "probability_source": artifact["probability_source"],
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
