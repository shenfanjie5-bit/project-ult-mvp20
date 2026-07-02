#!/usr/bin/env python3
"""Generate spec lists for the prob_features sweep stages."""
import json
import sys

CORE = ["rvol_20", "ivol_60", "max5", "turnover_20", "ep_ttm"]

SETS = {
    "core": CORE,
    "core_strev": CORE + ["strev"],
    "core_beta": CORE + ["beta_60"],
    "abl_no_rvol": [f for f in CORE if f != "rvol_20"],
    "abl_no_ivol": [f for f in CORE if f != "ivol_60"],
    "abl_no_max5": [f for f in CORE if f != "max5"],
    "abl_no_turn": [f for f in CORE if f != "turnover_20"],
    "abl_no_ep": [f for f in CORE if f != "ep_ttm"],
    "min_pair": ["ivol_60", "ep_ttm"],
}


def stage1():
    """h10, empirical, liquid .70: all sets x {ew_signed, ic_weighted} x {rel, abs}."""
    specs = []
    for sname, feats in SETS.items():
        for method in ("ew_signed", "ic_weighted"):
            for target in ("rel", "abs"):
                specs.append({
                    "name": f"{sname}__{method}",
                    "features": feats, "method": method,
                    "params": {"min_cov": 0.5},
                    "horizon": 10, "target": target,
                    "variant": "empirical", "shrink": 0.5, "liquid": 0.70,
                })
    return specs


def stage2():
    """h5 + h20, empirical, rel (primary) for all sets x both methods;
    abs reported only for core to bound the story."""
    specs = []
    for h in (5, 20):
        for sname, feats in SETS.items():
            for method in ("ew_signed", "ic_weighted"):
                specs.append({
                    "name": f"{sname}__{method}",
                    "features": feats, "method": method,
                    "params": {"min_cov": 0.5},
                    "horizon": h, "target": "rel",
                    "variant": "empirical", "shrink": 0.5, "liquid": 0.70,
                })
        specs.append({
            "name": "core__ew_signed",
            "features": SETS["core"], "method": "ew_signed",
            "params": {"min_cov": 0.5},
            "horizon": h, "target": "abs",
            "variant": "empirical", "shrink": 0.5, "liquid": 0.70,
        })
    return specs


if __name__ == "__main__":
    stage = sys.argv[1]
    out = sys.argv[2]
    specs = {"1": stage1, "2": stage2}[stage]()
    json.dump(specs, open(out, "w"), indent=1)
    print(f"{len(specs)} specs -> {out}")
