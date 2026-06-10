#!/usr/bin/env python3
"""Adversarial statistics check of the prob_features positive claim.

Reuses prob_sweep.run_spec (which itself reuses caliblib walk-forward +
evaluate) to independently verify the claimed weakest robustness cuts and
to extend the shuffle null. Creates NEW files only.
"""
import json
import sys

ROOT = "/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from factor_research.model.prob_variants.prob_sweep import run_spec  # noqa: E402

BASE = {
    "name": "abl_no_rvol__ic_weighted",
    "method": "ic_weighted",
    "features": ["ivol_60", "max5", "turnover_20", "ep_ttm"],
    "params": {"min_cov": 0.5},
    "min_train_dates": 12,
    "horizon": 20,
    "target": "rel",
    "variant": "empirical",
    "shrink": 0.5,
    "liquid": 0.70,
}

specs = []
specs.append(("base", dict(BASE)))
specs.append(("drop_up_turbulent", dict(BASE, drop_regime="up_turbulent")))
specs.append(("drop_2025", dict(BASE, drop_year="2025")))
specs.append(("parity0", dict(BASE, date_parity=0)))
specs.append(("parity1", dict(BASE, date_parity=1)))
# extra fresh shuffle seeds (beyond CLI seeds 7..19 already run)
for s in (23, 29, 31):
    specs.append((f"shuf_{s}", dict(BASE, shuffle=s)))

out = {}
for tag, spec in specs:
    r = run_spec(spec)
    out[tag] = {
        "disc_up_pp": r.get("disc_up_pp"),
        "n_test_dates": r.get("n_test_dates"),
        "reliability": r.get("reliability"),
    }
    d = r.get("disc_up_pp") or {}
    print(f"{tag:>18}: {d.get('mean'):+.3f}pp t={d.get('t'):+.2f} "
          f"n={r.get('n_test_dates')}", flush=True)

with open(ROOT + "/factor_research/model/reports/skeptic_stat_probfeat.json", "w") as f:
    json.dump(out, f, indent=1)
