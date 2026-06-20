"""Hermetic tests for the A-share 5d relative signal artifact."""
from __future__ import annotations

import json

import numpy as np

from mvp20 import signal_5d


def _fake_params() -> dict:
    bins = [{"n": 1000, "p_up": 0.46 + 0.008 * i, "mean": 0.0,
             "q10": -0.08, "q50": 0.0, "q90": 0.08}
            for i in range(10)]
    return {
        "version": 1,
        "built_at": "2026-06-20 00:00:00",
        "horizon_days": 5,
        "target": signal_5d.TARGET_LABEL,
        "liquid_frac": 0.70,
        "k_bins": 10,
        "min_feature_coverage": 0.5,
        "features": ["ivol_60", "ep_ttm", "strev"],
        "method": "ew_signed",
        "signs": {"ivol_60": -1, "ep_ttm": 1, "strev": 1},
        "base_rate": 0.5,
        "tilt_shrink": 0.5,
        "bins": bins,
        "calibration": {"stage3_oos": {"brier_skill": 0.00038}},
        "caveats": ["relative target only"],
    }


def _fake_cross_section(n=360, seed=9):
    rng = np.random.default_rng(seed)
    codes = [f"{i:06d}.SZ" for i in range(1, n + 1)]
    names = ["ivol_60", "ep_ttm", "strev"]
    feat = rng.normal(size=(n, len(names)))
    # More liquid names should include both high and low scores.
    lnmv = np.linspace(12.0, 18.0, n) + rng.normal(scale=0.1, size=n)
    industry = rng.integers(0, 6, size=n).astype(np.int32)
    return codes, feat, names, lnmv, industry


def test_build_rows_contract_is_relative_and_validated():
    params = _fake_params()
    codes, feat, names, lnmv, industry = _fake_cross_section()
    rows = signal_5d.build_rows(codes, feat, names, lnmv, industry, params)
    assert len(rows) == len(codes)
    valid = [r for r in rows.values() if r.get("validated")]
    assert 0.6 < len(valid) / len(codes) < 0.8
    row = valid[0]
    assert row["horizon_days"] == 5
    assert row["target"] == signal_5d.TARGET_LABEL
    assert "p_up" not in json.dumps(row)
    assert row["target_display"] == signal_5d.TARGET_DISPLAY
    assert row["direction"] in {"上涨", "下跌", "震荡"}
    assert row["signal_strength"] in {"强", "中", "弱"}
    assert isinstance(row["drivers"], list)
    assert isinstance(row["risks"], list)


def test_artifact_roundtrip_lookup_and_stale(tmp_path):
    params = _fake_params()
    codes, feat, names, lnmv, industry = _fake_cross_section()
    artifact = signal_5d.build_artifact("20260619", codes, feat, names, lnmv,
                                        industry, params)
    signal_5d.save_artifact(artifact, root=tmp_path)
    ts = next(t for t, r in artifact["rows"].items() if r.get("validated"))

    got = signal_5d.lookup(ts, root=tmp_path, today="20260620")
    assert got["available"] is True
    assert got["stale"] is False
    assert got["asof"] == "20260619"
    assert got["source_artifact"].endswith("A_share.json")

    stale = signal_5d.lookup(ts, root=tmp_path, today="20260710")
    assert stale["stale"] is True
    assert stale["validated"] is False
    assert "older than" in stale["reason"]


def test_direction_strength_thresholds():
    assert signal_5d.direction_from_probability(0.53, 0.50) == "上涨"
    assert signal_5d.direction_from_probability(0.47, 0.50) == "下跌"
    assert signal_5d.direction_from_probability(0.505, 0.50) == "震荡"
    assert signal_5d.strength_from_probability(0.54, 0.50) == "强"
    assert signal_5d.strength_from_probability(0.515, 0.50) == "中"
    assert signal_5d.strength_from_probability(0.505, 0.50) == "弱"
