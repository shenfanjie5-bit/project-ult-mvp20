from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from mvp20.market_adapter import apply_market_adapter, infer_market_code


ROOT = Path(__file__).resolve().parents[1]


def test_infer_market_code_from_ticker_suffix() -> None:
    assert infer_market_code({}, "300750.SZ") == "CN_A"
    assert infer_market_code({}, "00700.HK") == "HK"
    assert infer_market_code({}, "TSLA.US") == "US"
    assert infer_market_code({}, "NVDA") == "US"


def test_market_adapter_applies_local_multiplier_scores_and_discounts() -> None:
    final = {
        "short_total": 1.0,
        "medium_total": 1.0,
        "long_total": 1.0,
        "base_score": 1.0,
        "components": {},
    }
    role_components = {
        "theme_multiplier": 1.5,
        "policy_sensitivity_multiplier": 1.4,
        "funding_score": 0.2,
        "expectation_gap": 0.3,
        "risk_discount": 0.1,
    }

    out = apply_market_adapter(
        final_score=final,
        role_components=role_components,
        stock_overlay={"ts_code": "300750.SZ"},
    )

    assert out["market_code"] == "CN_A"
    assert out["multipliers"]["theme"] > 1.0
    assert out["multipliers"]["policy"] > 1.0
    assert out["multipliers"]["market_regime"] == pytest.approx(1.0)
    assert out["horizon_multipliers"]["short"] > out["horizon_multipliers"]["long"]
    assert out["local_scores"]["local_funding_score"] == pytest.approx(0.2)
    assert out["local_scores"]["local_event_score"] == pytest.approx(0.3)
    assert out["discounts"]["local_risk_discount"] == pytest.approx(0.1)
    assert out["adjusted_final_score"]["base_score"] > final["base_score"]


@pytest.mark.parametrize("ticker", ["300750.SZ", "TSLA.US", "00700.HK"])
def test_market_adapter_routes_expectation_gap_to_local_event_score(ticker: str) -> None:
    final = {
        "short_total": 0.0,
        "medium_total": 0.0,
        "long_total": 0.0,
        "base_score": 0.0,
        "components": {},
    }

    out = apply_market_adapter(
        final_score=final,
        role_components={"expectation_gap": 0.25},
        stock_overlay={"ts_code": ticker},
    )

    assert out["local_scores"]["local_event_score"] == pytest.approx(0.25)


def test_market_adapter_is_neutral_when_role_components_absent() -> None:
    final = {
        "short_total": 0.4,
        "medium_total": 0.5,
        "long_total": 0.6,
        "base_score": 0.5,
        "components": {},
    }

    out = apply_market_adapter(
        final_score=final,
        role_components={},
        stock_overlay={"ts_code": "TSLA.US"},
    )

    assert out["market_code"] == "US"
    assert out["multiplier"] == pytest.approx(1.0)
    assert out["adjusted_final_score"]["base_score"] == pytest.approx(0.5)


def test_market_adapter_uses_exp_formula_and_stock_local_beta() -> None:
    final = {
        "short_total": 50.0,
        "medium_total": 50.0,
        "long_total": 50.0,
        "base_score": 50.0,
        "components": {},
    }

    out = apply_market_adapter(
        final_score=final,
        role_components={"theme_multiplier": 1.8},
        stock_overlay={
            "ts_code": "300750.SZ",
            "stock_local_profile": {"theme_beta": 1.5},
        },
    )

    factor_score = math.tanh(0.8 / 2.0)
    adjusted_factor_score = factor_score * 1.5
    expected_short_multiplier = math.exp(0.80 * 0.25 * adjusted_factor_score)
    expected_mid_multiplier = math.exp(0.45 * 0.18 * adjusted_factor_score)

    assert out["factor_scores"]["theme"] == pytest.approx(factor_score)
    assert out["stock_betas"]["theme"] == pytest.approx(1.5)
    assert out["horizon_multipliers"]["short"] == pytest.approx(expected_short_multiplier)
    assert out["multiplier"] == pytest.approx(expected_mid_multiplier)
    assert out["adjusted_final_score"]["short_total"] == pytest.approx(
        50.0 * expected_short_multiplier
    )
    assert out["adjusted_final_score"]["base_score"] == pytest.approx(
        50.0 * expected_mid_multiplier
    )


def test_market_adapter_factor_weights_sum_to_one_by_market_horizon() -> None:
    payload = yaml.safe_load(
        (ROOT / "config/market_adapters.yaml").read_text(encoding="utf-8")
    )

    for market_rules in payload["market_rules"].values():
        for weights in market_rules["factor_weights"].values():
            assert sum(weights.values()) == pytest.approx(1.0)
