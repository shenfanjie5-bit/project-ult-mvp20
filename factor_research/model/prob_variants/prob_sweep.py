#!/usr/bin/env python3
"""prob_features family sweep driver (ISOLATED research; creates NEW files only).

Sweeps P(up)-layer composites through caliblib.walk_forward_calibrated/evaluate
(the audited walk-forward calibration), caching the panel / neutralized cube /
rank-layer scores in-process so a large grid is affordable. NO modeling logic
is re-implemented here: scoring = harness.walk_forward, calibration + metrics =
caliblib. Subset cuts (drop-year / drop-regime) only FILTER the per-test-date
recs before caliblib.evaluate(), exactly as sanctioned.

Usage:
  prob_sweep.py --specs specs.json --out results.json
spec = {name, features[], method, params{}, horizon, target, variant,
        shrink, liquid, shuffle(null|int), drop_year(null|"2024"),
        drop_regime(null|"up_calm")}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np

ROOT = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

from factor_research.model import harness as H   # noqa: E402
from factor_research.model import caliblib as C  # noqa: E402

# ---------------------------------------------------------------- caches ----
_PANEL = None
_Z = None
_SCORES = {}


def _cached_load_panel(path=None):
    global _PANEL
    if _PANEL is None:
        _PANEL = _orig_load_panel(path)
    return _PANEL


def _cached_neutralize(z, meta, cache=True):
    global _Z
    if _Z is None:
        _Z = _orig_neutralize(z, meta, cache=cache)
    return _Z


def _cached_walk_forward(Z, fwd, meta, config):
    key = (json.dumps(config, sort_keys=True),
           hashlib.md5(np.ascontiguousarray(fwd)).hexdigest())
    if key not in _SCORES:
        _SCORES[key] = _orig_walk_forward(Z, fwd, meta, config)
    return _SCORES[key].copy()   # copy: caliblib mutates scores under --shuffle


_orig_load_panel = H.load_panel
_orig_neutralize = H.neutralize
_orig_walk_forward = H.walk_forward
H.load_panel = _cached_load_panel
H.neutralize = _cached_neutralize
H.walk_forward = _cached_walk_forward
# caliblib imported harness as module object -> patches apply there too.


# ------------------------------------------------------------- one eval ----
def _reliability_summary(rel):
    """monotonicity of the reliability curve: spearman(p_pred, p_real) and
    fraction of adjacent increasing steps."""
    if not rel or len(rel) < 3:
        return {"n_bins": len(rel) if rel else 0}
    pp = np.array([r["p_pred"] for r in rel])
    pr = np.array([r["p_real"] for r in rel])
    rho = H._spearman(pp, pr)
    steps = np.diff(pr)
    return {"n_bins": len(rel), "spearman_pred_real": float(rho),
            "frac_increasing_steps": float(np.mean(steps > 0)),
            "p_real_range": [float(pr.min()), float(pr.max())],
            "p_pred_range": [float(pp.min()), float(pp.max())]}


def run_spec(spec):
    cfg = {"name": spec["name"], "method": spec["method"],
           "features": spec["features"],
           "params": spec.get("params", {"min_cov": 0.5}),
           "min_train_dates": spec.get("min_train_dates", 12)}
    t0 = time.time()
    recs = C.walk_forward_calibrated(
        cfg,
        horizon=spec.get("horizon", 10),
        liquid=spec.get("liquid", 0.70),
        variant=spec.get("variant", "empirical"),
        shrink=spec.get("shrink", 0.5),
        shuffle=spec.get("shuffle"),
        target=spec.get("target", "rel"),
    )
    dy = spec.get("drop_year")
    dr = spec.get("drop_regime")
    par = spec.get("date_parity")          # 0/1: every-2nd test date ->
    if dy:                                 # non-overlapping labels at h20
        recs = [r for r in recs if r["date"][:4] != str(dy)]
    if dr:
        recs = [r for r in recs if r["regime"] != dr]
    if par is not None:
        recs = [r for i, r in enumerate(recs) if i % 2 == int(par)]
    rep = C.evaluate(recs)
    out = {k: spec.get(k) for k in
           ("name", "features", "method", "horizon", "target", "variant",
            "shrink", "liquid", "shuffle", "drop_year", "drop_regime",
            "date_parity")}
    if "error" in rep:
        out["error"] = rep["error"]
        return out
    out["n_test_dates"] = rep["n_test_dates"]
    out["n_obs"] = rep["n_obs"]
    out["disc_up_pp"] = {k: (round(v * 100, 3) if k in ("mean",) else round(v, 3))
                         for k, v in rep["discrimination_up_rate_top_minus_bottom"].items()}
    out["disc_ret_pp"] = {k: (round(v * 100, 3) if k in ("mean",) else round(v, 3))
                          for k, v in rep["discrimination_ret_top_minus_bottom"].items()}
    out["brier_skill"] = round(rep["brier_skill"], 5)
    out["coverage_q10_q90"] = round(rep["interval_coverage_q10_q90"], 4)
    out["reliability"] = _reliability_summary(rep["reliability"])
    out["variance_split_date_share"] = round(rep["variance_split"]["date_share"], 4)
    out["secs"] = round(time.time() - t0, 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    specs = json.load(open(a.specs))
    results = []
    if os.path.exists(a.out):
        results = json.load(open(a.out))
    done = {json.dumps({k: r.get(k) for k in
                        ("name", "horizon", "target", "variant", "shrink",
                         "liquid", "shuffle", "drop_year", "drop_regime")},
                       sort_keys=True) for r in results}
    for i, spec in enumerate(specs):
        key = json.dumps({k: spec.get(k) for k in
                          ("name", "horizon", "target", "variant", "shrink",
                           "liquid", "shuffle", "drop_year", "drop_regime")},
                         sort_keys=True)
        if key in done:
            continue
        r = run_spec(spec)
        results.append(r)
        json.dump(results, open(a.out, "w"), indent=1, default=float)
        d = r.get("disc_up_pp", {})
        print(f"[{i+1}/{len(specs)}] {r['name']} h{r['horizon']} {r['target']} "
              f"{r['variant']}/s{r.get('shrink')} liq{r['liquid']} "
              f"shuf={r.get('shuffle')} dy={r.get('drop_year')} dr={r.get('drop_regime')}"
              f" -> disc_up {d.get('mean')}pp t={d.get('t')} "
              f"bs={r.get('brier_skill')} ({r.get('secs')}s)", flush=True)
    print("DONE", len(results))


if __name__ == "__main__":
    main()
