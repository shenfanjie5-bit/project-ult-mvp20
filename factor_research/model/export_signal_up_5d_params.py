#!/usr/bin/env python3
"""Freeze A-share absolute 5d upside probability params.

Output: ``config/signal_up_5d_params.json``.

The target is:
    P(close[t+5] / close[t] - 1 > 0)

This is a separate artifact from ``signal_5d``. It never re-labels the
relative ``P(beat same-day liquid median)`` signal as absolute upside.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, os.getcwd())

from factor_research.model import signal_up_5d_common as C  # noqa: E402
from mvp20 import signal_up_5d  # noqa: E402


OUT = Path("config/signal_up_5d_params.json")
VALIDATION_DATES = 42
FAST_VALIDATION_DATES = 12


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except Exception:  # noqa: BLE001
        return None


def _fit_full_params(frame: dict[str, Any]) -> dict[str, Any]:
    X = frame["X"]
    y = frame["y"]
    fwd = frame["fwd"]
    cov = frame["coverage"]
    liquid = frame["liquid"]
    meta = frame["meta"]
    train_sel = liquid & np.isfinite(fwd) & (cov >= C.MIN_FEATURE_COV)
    model = C.fit_model_payload(X[train_sel], y[train_sel].astype(float), l2=C.MODEL_L2)

    score = C.technical_score(X, frame["features"])
    score_pct = C._score_percentiles(score, liquid)  # noqa: SLF001 - research helper
    baseline_model = C.fit_baseline_payload(score_pct, y, train_sel)
    return {
        "model": model,
        "baseline_model": baseline_model,
        "base_rate": float(np.mean(y[train_sel].astype(float))),
        "train_window": {
            "base_dates": [meta["base_dates"][0], meta["base_dates"][-1]],
            "n_dates": len(meta["base_dates"]),
            "n_observations": int(train_sel.sum()),
            "rule": "full matured panel for frozen serving params; validation is strict walk-forward",
        },
    }


def main() -> int:
    frame = C.load_frame()
    full = _fit_full_params(frame)
    validation_12 = C.run_walk_forward(n_dates=FAST_VALIDATION_DATES, top_n=20)
    validation_42 = C.run_walk_forward(n_dates=VALIDATION_DATES, top_n=20)
    gates = validation_42["validation_gates"]
    primary_enabled = bool(validation_42["primary_model_passed"])

    model = {
        "type": "ridge_logistic",
        "l2": C.MODEL_L2,
        "features": C.MODEL_FEATURES,
        "intercept": full["model"]["intercept"],
        "coefficients": full["model"]["coefficients"],
        "feature_means": full["model"]["feature_means"],
        "feature_stds": full["model"]["feature_stds"],
        "train_window": full["train_window"],
        "validation": {
            "fast_12_date": validation_12,
            "stability_42_date": validation_42,
            "gates": gates,
        },
        "primary_enabled": primary_enabled,
        "fallback_method": signal_up_5d.FALLBACK_METHOD,
    }
    params = {
        "version": 1,
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_sha": _git_sha(),
        "panel": {
            "base_dates": [frame["meta"]["base_dates"][0], frame["meta"]["base_dates"][-1]],
            "n_dates": len(frame["meta"]["base_dates"]),
            "n_stocks": len(frame["meta"]["cols"]),
        },
        "horizon_days": C.HORIZON_DAYS,
        "target": signal_up_5d.TARGET_LABEL,
        "target_kind": signal_up_5d.TARGET_KIND,
        "probability_semantics": signal_up_5d.PROBABILITY_SEMANTICS,
        "liquid_frac": C.LIQUID_FRAC,
        "min_feature_coverage": C.MIN_FEATURE_COV,
        "features": C.MODEL_FEATURES,
        "feature_audit": frame["feature_audit"],
        "method": signal_up_5d.MODEL_METHOD,
        "model": model,
        "baseline": {
            "method": signal_up_5d.BASELINE_METHOD,
            "features": ["technical_score_pct"],
            "model": full["baseline_model"],
            "note": "shadow score-derived baseline; does not use final_score.base_score",
        },
        "fallback": {
            "method": signal_up_5d.FALLBACK_METHOD,
            "probability": full["base_rate"],
            "validated": False,
            "reason": "constant train base-rate fallback is not a stock-specific production signal",
        },
        "base_rate": full["base_rate"],
        "calibration": {
            "fit": "ridge logistic over PIT-safe same-day stock, market, and industry features",
            "primary_probability_source": (
                signal_up_5d.MODEL_METHOD if primary_enabled else signal_up_5d.FALLBACK_METHOD
            ),
            "fast_12_date_summary": validation_12["summary"],
            "stability_42_date_summary": validation_42["summary"],
            "stability_42_date_gates": gates,
            "primary_model_passed": primary_enabled,
        },
        "caveats": [
            "target is absolute P(5d return > 0), not relative P(beat median)",
            "validated ONLY on the liquid top-70% by market cap with enough feature coverage",
            "BFF request path never trains; it serves this frozen artifact only",
            "fallback train base rate is emitted for transparency but is not a validated stock-specific signal",
            "existing final_score.base_score is excluded from the primary model and from production probability mapping",
            "A-share only; HK/US require separate history, feature, and calibration artifacts",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(C.jsonable(params), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  base_rate={full['base_rate']:.4f}")
    print(f"  primary_enabled={primary_enabled} gates={json.dumps(gates, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
