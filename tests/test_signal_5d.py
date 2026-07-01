"""Hermetic tests for the A-share 5d relative signal artifact."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from mvp20 import signal_5d


def _fake_params() -> dict:
    bins = [{"n": 1000, "p_up": 0.46 + 0.008 * i, "mean": 0.0,
             "q10": -0.08, "q50": 0.0, "q90": 0.08}
            for i in range(10)]
    legacy = {
        "method": "ew_signed",
        "features": ["ivol_60", "ep_ttm", "strev"],
        "signs": {"ivol_60": -1, "ep_ttm": 1, "strev": 1},
        "base_rate": 0.5,
        "tilt_shrink": 0.5,
        "k_bins": 10,
        "bins": bins,
    }
    return {
        "version": 2,
        "built_at": "2026-06-20 00:00:00",
        "horizon_days": 5,
        "target": signal_5d.TARGET_LABEL,
        "target_kind": "relative_cross_section_median",
        "probability_semantics": "P(5d return beats same-day liquid-universe median); not absolute P(up)",
        "liquid_frac": 0.70,
        "k_bins": 10,
        "min_feature_coverage": 0.5,
        "features": ["ivol_60", "ep_ttm", "strev", "max5", "turnover_20", "rvol_20", "mom_6_1"],
        "method": "logistic_multifeature_7f",
        "model": {
            "type": "ridge_logistic",
            "l2": 0.2,
            "features": ["ivol_60", "ep_ttm", "strev", "max5", "turnover_20", "rvol_20", "mom_6_1"],
            "intercept": 0.0,
            "coefficients": [-0.18, 0.16, 0.22, -0.12, -0.10, -0.14, 0.20],
            "feature_means": [0.0] * 7,
            "feature_stds": [1.0] * 7,
            "primary_enabled": True,
            "validation": {
                "gates": {
                    "avg_unique_1dp_ge_50": True,
                    "avg_brier_skill_gt_0": True,
                    "avg_rank_ic_gt_fallback": True,
                    "avg_top_excess_gt_fallback": True,
                }
            },
        },
        "legacy_bin_calibration": legacy,
        "base_rate": 0.5,
        "tilt_shrink": 0.5,
        "bins": bins,
        "calibration": {"stage3_oos": {"brier_skill": 0.00038}},
        "caveats": ["relative target only"],
    }


def _fake_cross_section(n=360, seed=9):
    rng = np.random.default_rng(seed)
    codes = [f"{i:06d}.SZ" for i in range(1, n + 1)]
    names = ["ivol_60", "ep_ttm", "strev", "max5", "turnover_20", "rvol_20", "mom_6_1"]
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
    assert row["model_method"] == "logistic_multifeature_7f"
    assert row["probability_source"] == "logistic_multifeature_7f"
    assert row["probability_semantics"].startswith("P(5d return beats")
    assert isinstance(row["feature_coverage"], float)
    assert isinstance(row["model_probability"], float)
    assert isinstance(row["legacy_bin_probability"], float)
    assert row["direction"] in {"上涨", "下跌", "震荡"}
    assert row["signal_strength"] in {"强", "中", "弱"}
    assert isinstance(row["drivers"], list)
    assert isinstance(row["risks"], list)
    unique_probs = {r["probability"] for r in valid}
    assert len(unique_probs) > 10


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


def test_isotonic_probability_smoothing_preserves_raw_bins():
    stats = [
        {"n": 100, "p_up": 0.50},
        {"n": 100, "p_up": 0.55},
        {"n": 300, "p_up": 0.52},
        {"n": 100, "p_up": 0.58},
    ]
    smoothed = signal_5d.apply_isotonic_p_up(stats)
    probs = [s["p_up"] for s in smoothed]
    assert probs == sorted(probs)
    assert smoothed[1]["p_up_raw"] == 0.55
    assert smoothed[2]["p_up_raw"] == 0.52
    # Weighted pooling makes the violating middle block 0.5275.
    assert round(smoothed[1]["p_up"], 4) == 0.5275
    assert round(smoothed[2]["p_up"], 4) == 0.5275


def test_raw_bin_probability_prefers_unsmoothed_raw_value():
    params = _fake_params()
    params["model"]["primary_enabled"] = False
    bins = params["legacy_bin_calibration"]["bins"]
    for i, stat in enumerate(bins):
        stat["p_up_raw"] = 0.40 + 0.01 * i
    codes, feat, names, lnmv, industry = _fake_cross_section()
    rows = signal_5d.build_rows(codes, feat, names, lnmv, industry, params)
    valid = [r for r in rows.values() if r.get("validated")]

    assert valid
    for row in valid[:20]:
        expected = bins[row["bin"]]["p_up_raw"]
        assert row["raw_bin_probability"] == round(expected, 4)
        assert row["probability_source"] == "score_pct_linear_bin10"


def test_frozen_signal_5d_params_are_relative_and_monotone():
    root = Path(__file__).resolve().parents[1]
    params = json.loads((root / "config/signal_5d_params.json").read_text(encoding="utf-8"))
    probs = [float(b["p_up"]) for b in params["bins"]]
    assert params["version"] == 2
    assert params["method"] == "logistic_multifeature_7f"
    assert params["model"]["type"] == "ridge_logistic"
    assert params["model"]["fallback_method"] == "score_pct_linear_bin10"
    assert params["target_kind"] == "relative_cross_section_median"
    assert params["calibration"]["p_up_isotonic"] is True
    assert probs == sorted(probs)
    assert "absolute P(up)" in json.dumps(params["caveats"], ensure_ascii=False)


def test_workbench_frontend_prefers_signal_up_with_signal_5d_fallback():
    # The workbench prefers the absolute signal_up_5d, but when that model has
    # no governance-validated rows it falls back to the relative signal_5d
    # ranking. The fallback carries a DISTINCT label (5 日相对胜率, not
    # 5 日上涨概率) plus an explicit note, so the absolute/relative semantics
    # are never conflated even though both sources are wired in.
    root = Path(__file__).resolve().parents[1]
    page = (root / "FrontEnd/src/pages/MarketOverview/index.tsx").read_text(encoding="utf-8")
    hook = (root / "FrontEnd/src/api/hooks/useSignal5d.ts").read_text(encoding="utf-8")
    stock_detail = (root / "FrontEnd/src/pages/StockDetail/index.tsx").read_text(encoding="utf-8")
    stock_header = (
        root / "FrontEnd/src/pages/StockDetail/components/StockHeader.tsx"
    ).read_text(encoding="utf-8")
    assert "/project-ult/signals/top" in hook
    assert "/project-ult/signals/up-5d/top" in hook
    assert "deriveStockSignal" not in page
    assert "signal.upside_probability" not in page
    # Both sources are wired: absolute up-probability preferred, relative
    # win-rate as the validation-gated fallback.
    assert "5 日上涨概率" in page
    assert "5 日相对胜率" in page
    assert "派生预览概率" not in page
    assert "相对胜率预览" not in page
    assert "train_base_rate_unvalidated" in page
    assert "已切换显示 5 日相对胜率预览" not in page
    assert "signal_up_5d" in page
    assert "signal_5d" in page
    # Fallback must be explicit, not a silent substitution.
    assert "已回落到 signal_5d" in page
    assert "signal5d={score?.signal_5d ?? null}" in stock_detail
    assert "signal5d.probability" in stock_header
    assert "5 日相对胜率" in stock_header
    assert "跑赢同日流动性股票中位数概率" in stock_header
    assert "未来 5 日上涨概率" not in stock_header
