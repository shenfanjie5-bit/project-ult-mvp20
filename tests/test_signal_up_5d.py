"""Hermetic tests for the A-share absolute 5d upside probability artifact."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from mvp20 import signal_5d, signal_up_5d


def _fake_params(primary_enabled: bool = True) -> dict:
    return {
        "version": 1,
        "built_at": "2026-06-21 00:00:00",
        "horizon_days": 5,
        "target": signal_up_5d.TARGET_LABEL,
        "target_kind": signal_up_5d.TARGET_KIND,
        "probability_semantics": signal_up_5d.PROBABILITY_SEMANTICS,
        "liquid_frac": 0.70,
        "min_feature_coverage": 0.5,
        "features": list(signal_up_5d.MODEL_FEATURES),
        "method": signal_up_5d.MODEL_METHOD,
        "model": {
            "type": "ridge_logistic",
            "l2": 0.8,
            "features": list(signal_up_5d.MODEL_FEATURES),
            "intercept": -0.05,
            "coefficients": [0.04 if i % 2 == 0 else -0.03 for i in range(len(signal_up_5d.MODEL_FEATURES))],
            "feature_means": [0.0] * len(signal_up_5d.MODEL_FEATURES),
            "feature_stds": [1.0] * len(signal_up_5d.MODEL_FEATURES),
            "primary_enabled": primary_enabled,
            "validation": {
                "gates": {
                    "avg_brier_skill_gt_0": primary_enabled,
                    "avg_logloss_skill_ge_0": primary_enabled,
                    "avg_auc_gt_0_52": primary_enabled,
                    "avg_calibration_error_lt_fallback": primary_enabled,
                    "top_decile_up_rate_gt_universe": primary_enabled,
                    "avg_unique_1dp_ge_50": primary_enabled,
                    "no_leakage_audit_pass": True,
                }
            },
            "fallback_method": signal_up_5d.FALLBACK_METHOD,
        },
        "baseline": {
            "method": signal_up_5d.BASELINE_METHOD,
            "features": ["ret_20d"],
            "model": {
                "type": "ridge_logistic",
                "intercept": 0.0,
                "coefficients": [0.1],
                "feature_means": [0.0],
                "feature_stds": [1.0],
            },
        },
        "fallback": {
            "method": signal_up_5d.FALLBACK_METHOD,
            "probability": 0.459,
            "validated": False,
        },
        "base_rate": 0.459,
        "calibration": {"primary_model_passed": primary_enabled},
        "caveats": ["target is absolute P(5d return > 0), not relative P(beat median)"],
    }


def _fake_cross_section(n=360, seed=21):
    rng = np.random.default_rng(seed)
    codes = [f"{i:06d}.SZ" for i in range(1, n + 1)]
    names = list(signal_up_5d.MODEL_FEATURES)
    feat = rng.normal(scale=0.04, size=(n, len(names)))
    feat[:, names.index("rsi_14")] = rng.uniform(20, 80, size=n)
    lnmv = np.linspace(12.0, 18.0, n) + rng.normal(scale=0.1, size=n)
    industry = rng.integers(0, 6, size=n).astype(np.int32)
    return codes, feat, names, lnmv, industry


def test_build_rows_contract_is_absolute_and_separate_from_relative_signal():
    params = _fake_params(primary_enabled=True)
    codes, feat, names, lnmv, industry = _fake_cross_section()
    rows = signal_up_5d.build_rows(codes, feat, names, lnmv, industry, params)
    valid = [r for r in rows.values() if r.get("validated")]
    assert 0.6 < len(valid) / len(codes) < 0.8
    row = valid[0]
    assert row["target"] == signal_up_5d.TARGET_LABEL
    assert row["target_kind"] == "absolute_up_5d"
    assert row["target_display"] == signal_up_5d.TARGET_DISPLAY
    assert row["probability_semantics"] == signal_up_5d.PROBABILITY_SEMANTICS
    assert "p_up_5d" in row
    assert "p_beat_median" not in row
    assert 0.0 <= row["probability"] <= 1.0
    assert row["probability"] == row["p_up_5d"]
    assert row["model_method"] == signal_up_5d.MODEL_METHOD
    assert row["probability_source"] == signal_up_5d.MODEL_METHOD
    assert isinstance(row["model_probability"], float)
    assert isinstance(row["fallback_probability"], float)
    assert isinstance(row["baseline_probability"], float)
    assert row["direction"] in {"上涨", "下跌", "震荡"}
    assert row["signal_strength"] in {"强", "中", "弱"}


def test_failed_gate_emits_shadow_not_validated_probability():
    params = _fake_params(primary_enabled=False)
    codes, feat, names, lnmv, industry = _fake_cross_section()
    rows = signal_up_5d.build_rows(codes, feat, names, lnmv, industry, params)
    available = [r for r in rows.values() if r.get("available")]
    assert available
    assert not any(r.get("validated") for r in available)
    row = next(r for r in available if "failed production gates" in r.get("reason", ""))
    assert row["probability_source"] == signal_up_5d.FALLBACK_METHOD
    assert row["probability"] == row["fallback_probability"]
    assert isinstance(row["model_probability_shadow"], float)
    assert "failed production gates" in row["reason"]


def test_artifact_roundtrip_lookup_and_stale(tmp_path):
    params = _fake_params(primary_enabled=True)
    codes, feat, names, lnmv, industry = _fake_cross_section()
    artifact = signal_up_5d.build_artifact("20260619", codes, feat, names, lnmv,
                                           industry, params)
    signal_up_5d.save_artifact(artifact, root=tmp_path)
    ts = next(t for t, r in artifact["rows"].items() if r.get("validated"))

    got = signal_up_5d.lookup(ts, root=tmp_path, today="20260620")
    assert got["available"] is True
    assert got["stale"] is False
    assert got["asof"] == "20260619"
    assert got["source_artifact"].endswith("A_share.json")
    assert got["target_kind"] == "absolute_up_5d"

    stale = signal_up_5d.lookup(ts, root=tmp_path, today="20260710")
    assert stale["stale"] is True
    assert stale["validated"] is False
    assert "older than" in stale["reason"]


def test_frozen_signal_up_5d_params_are_absolute_and_not_base_score_mapping():
    root = Path(__file__).resolve().parents[1]
    params = json.loads((root / "config/signal_up_5d_params.json").read_text(encoding="utf-8"))
    assert params["version"] == 1
    assert params["target_kind"] == "absolute_up_5d"
    assert params["target"] == signal_up_5d.TARGET_LABEL
    assert "P(5d return > 0)" in params["probability_semantics"]
    assert params["method"] == signal_up_5d.MODEL_METHOD
    assert params["model"]["type"] == "ridge_logistic"
    assert params["model"]["fallback_method"] == signal_up_5d.FALLBACK_METHOD
    assert params["fallback"]["method"] == signal_up_5d.FALLBACK_METHOD
    payload = json.dumps(params, ensure_ascii=False)
    assert "base_score" not in params["features"]
    assert "base_score-to-probability reuse" in payload
    assert "P(5d return beats" not in params["probability_semantics"]


def test_signal_5d_and_signal_up_5d_do_not_overlap_artifacts_or_targets():
    assert signal_5d.ARTIFACT_DIR != signal_up_5d.ARTIFACT_DIR
    assert signal_5d.PARAMS_PATH != signal_up_5d.PARAMS_PATH
    assert signal_5d.TARGET_LABEL != signal_up_5d.TARGET_LABEL
    assert signal_up_5d.TARGET_KIND == "absolute_up_5d"
    assert signal_5d.TARGET_LABEL.startswith("P(5d beat")


def test_stock_detail_frontend_distinguishes_absolute_and_relative_labels():
    root = Path(__file__).resolve().parents[1]
    stock_detail = (root / "FrontEnd/src/pages/StockDetail/index.tsx").read_text(encoding="utf-8")
    hook = (root / "FrontEnd/src/api/hooks/useStockScore.ts").read_text(encoding="utf-8")
    header = (
        root / "FrontEnd/src/pages/StockDetail/components/StockHeader.tsx"
    ).read_text(encoding="utf-8")
    market_page = (root / "FrontEnd/src/pages/MarketOverview/index.tsx").read_text(encoding="utf-8")

    assert "signal_up_5d?: SignalUp5dBlock" in hook
    assert "signalUp5d={score?.signal_up_5d ?? null}" in stock_detail
    assert "5 日上涨概率" in header
    assert "5 日相对胜率" in header
    assert "signal_up_5d 后端信号" in header
    assert "signal_5d 后端信号" in header
    assert "派生预览，不是上涨概率模型" in header
    assert "signal.upside_probability" in header
    assert "5 日上涨概率" in market_page
    assert "signal_up_5d" in market_page
    assert "派生预览概率" not in market_page
    assert "5 日相对胜率" not in market_page
    assert "相对胜率预览" not in market_page
