#!/usr/bin/env python3
"""Config sweep driver for logistic.py (loads panel once, loops configs).

Usage:
  .../python factor_research/model/prob_variants/sweep_logistic.py --jobs jobs.json --outdir DIR
jobs.json = list of kwargs dicts for logistic.run(); each result saved to
DIR/<tag>.json where tag encodes the kwargs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from factor_research.model.prob_variants import logistic as L  # noqa: E402


def tag_of(kw):
    parts = [
        f"h{kw.get('horizon', 10)}",
        kw.get("feature_set", "base5"),
        f"C{kw.get('Creg', 1.0)}",
        kw.get("pcal", "raw"),
        kw.get("target", "rel"),
        f"liq{kw.get('liquid', 0.70)}",
    ]
    if kw.get("shuffle") is not None:
        parts.append(f"shuf{kw['shuffle']}")
    if kw.get("drop_year"):
        parts.append(f"dropy{kw['drop_year']}")
    if kw.get("drop_regime"):
        parts.append(f"dropr_{kw['drop_regime']}")
    return "_".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    jobs = json.load(open(a.jobs))
    os.makedirs(a.outdir, exist_ok=True)
    for kw in jobs:
        tag = tag_of(kw)
        out = os.path.join(a.outdir, tag + ".json")
        if os.path.exists(out):
            print(f"[skip] {tag}")
            continue
        rep = L.run(**kw)
        json.dump(rep, open(out, "w"), indent=1, default=float)
        d = rep.get("discrimination_up_rate_top_minus_bottom", {})
        print(f"[done] {tag}: disc={100 * d.get('mean', float('nan')):+.2f}pp "
              f"t={d.get('t', float('nan')):.2f} bskill={rep.get('brier_skill', float('nan')):+.5f} "
              f"nD={rep.get('n_test_dates')}")


if __name__ == "__main__":
    main()
