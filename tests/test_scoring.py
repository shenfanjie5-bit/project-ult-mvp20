"""Tests for the spec §27/§30 scoring + mode-classifier module."""

from __future__ import annotations

import pytest

from mvp20.scoring import (
    HORIZON_DEFAULT_WEIGHTS,
    MODE_DE_RATING,
    MODE_DIGESTION,
    MODE_MODERATE_BULL,
    MODE_STRONG_BULL,
    MODE_STRUCTURAL_DIVERGENCE,
    MODE_TREND_REVERSAL,
    MODE_WAIT_FOR_CONFIRMATION,
    SIGNAL_BUY_THRESHOLD,
    SIGNAL_HOLD_THRESHOLD,
    SIGNAL_WATCH_THRESHOLD,
    classify_mode,
    compute_company_score,
    compute_final_score,
    compute_path_score,
    score_company,
)


# ---------------------------------------------------------------------------
# Spec §27.1 — path score
# ---------------------------------------------------------------------------


class TestPathScore:
    def test_pure_positive_path(self) -> None:
        """All multiplicative inputs at canonical positive values; no
        discounts. Expected: clean positive product."""

        score = compute_path_score(
            direction=1.0,
            event_strength=1.0,
            transmission_strength=1.0,
            company_exposure=1.0,
            revenue_share=1.0,
            profit_elasticity=1.0,
            confidence=1.0,
            time_factor=1.0,
            expectation_gap=1.0,
            capital_amplification=1.0,
            priced_in_discount=0.0,
            risk_discount=0.0,
        )
        assert score == pytest.approx(1.0)

    def test_negative_direction_flips_sign(self) -> None:
        score = compute_path_score(
            direction=-1.0,
            event_strength=0.8,
            transmission_strength=0.5,
            company_exposure=0.7,
            revenue_share=0.6,
            profit_elasticity=1.0,
            confidence=1.0,
            time_factor=1.0,
            expectation_gap=0.5,
            capital_amplification=1.0,
            priced_in_discount=0.0,
            risk_discount=0.0,
        )
        assert score < 0
        assert score == pytest.approx(-0.8 * 0.5 * 0.7 * 0.6 * 0.5)

    def test_discounts_subtract(self) -> None:
        """Priced-in + risk discounts are subtracted (not multiplied)."""

        score = compute_path_score(
            direction=1.0,
            event_strength=1.0,
            transmission_strength=1.0,
            company_exposure=1.0,
            revenue_share=1.0,
            profit_elasticity=1.0,
            confidence=1.0,
            time_factor=1.0,
            expectation_gap=1.0,
            capital_amplification=1.0,
            priced_in_discount=0.3,
            risk_discount=0.2,
        )
        assert score == pytest.approx(1.0 - 0.3 - 0.2)

    def test_zero_in_multiplicative_zeros_product(self) -> None:
        """Spec §27.1: a single 0 in the multiplicative chain collapses the
        whole product (the path is genuinely irrelevant)."""

        score = compute_path_score(
            direction=1.0,
            event_strength=0.0,  # ⇐ zero
            transmission_strength=1.0,
            company_exposure=1.0,
            revenue_share=1.0,
            profit_elasticity=1.0,
            confidence=1.0,
            time_factor=1.0,
            expectation_gap=1.0,
            capital_amplification=1.0,
            priced_in_discount=0.1,
            risk_discount=0.0,
        )
        assert score == pytest.approx(-0.1)

    def test_handles_none_inputs(self) -> None:
        """``None`` should be coerced to 0 (so a missing input doesn't crash
        the formula). Direction None ⇒ 0 ⇒ whole product 0."""

        score = compute_path_score(
            direction=None,  # type: ignore[arg-type]
            event_strength=0.5,
            transmission_strength=0.5,
            company_exposure=0.5,
            revenue_share=1.0,
            profit_elasticity=1.0,
            confidence=1.0,
            time_factor=1.0,
            expectation_gap=0.0,
            capital_amplification=1.0,
            priced_in_discount=0.0,
            risk_discount=0.0,
        )
        assert score == 0.0

    def test_string_direction_normalizes(self) -> None:
        """Overlay YAML uses string directions like 'positive'/'negative'."""

        pos = compute_path_score(
            direction="positive",  # type: ignore[arg-type]
            event_strength=0.5,
            transmission_strength=1.0,
            company_exposure=1.0,
            revenue_share=1.0,
            profit_elasticity=1.0,
            confidence=1.0,
            time_factor=1.0,
            expectation_gap=1.0,
            capital_amplification=1.0,
            priced_in_discount=0.0,
            risk_discount=0.0,
        )
        neg = compute_path_score(
            direction="negative",  # type: ignore[arg-type]
            event_strength=0.5,
            transmission_strength=1.0,
            company_exposure=1.0,
            revenue_share=1.0,
            profit_elasticity=1.0,
            confidence=1.0,
            time_factor=1.0,
            expectation_gap=1.0,
            capital_amplification=1.0,
            priced_in_discount=0.0,
            risk_discount=0.0,
        )
        assert pos == 0.5
        assert neg == -0.5


# ---------------------------------------------------------------------------
# Spec §27.3 — company score
# ---------------------------------------------------------------------------


class TestCompanyScore:
    def _industry_var(self, score: float, **overrides) -> dict:
        v = {
            "score": score,
            "exposure": 1.0,
            "revenue_share": 1.0,
            "profit_elasticity": 1.0,
            "financial_sensitivity": 1.0,
            "valuation_sensitivity": 1.0,
            "name": "test",
        }
        v.update(overrides)
        return v

    def test_no_industry_vars_uses_only_other_terms(self) -> None:
        out = compute_company_score(
            industry_variables=[],
            company_event_score=0.3,
            capital_sentiment_score=0.2,
            risk_discount=0.05,
            valuation_pressure=0.0,
            priced_in_discount=0.0,
        )
        assert out["score"] == pytest.approx(0.3 + 0.2 - 0.05)
        assert out["components"]["industry_contrib"] == 0.0

    def test_multiple_industry_vars_sum(self) -> None:
        out = compute_company_score(
            industry_variables=[
                self._industry_var(0.3),
                self._industry_var(0.4, exposure=0.5),
                self._industry_var(-0.1),
            ],
            company_event_score=0.0,
            capital_sentiment_score=0.0,
            risk_discount=0.0,
            valuation_pressure=0.0,
            priced_in_discount=0.0,
        )
        # 0.3 + 0.4*0.5 + (-0.1) = 0.4
        assert out["score"] == pytest.approx(0.4)
        assert out["components"]["industry_contrib"] == pytest.approx(0.4)
        assert len(out["industry_contributions"]) == 3

    def test_discount_terms_subtract(self) -> None:
        out = compute_company_score(
            industry_variables=[self._industry_var(0.5)],
            company_event_score=0.2,
            capital_sentiment_score=0.1,
            risk_discount=0.1,
            valuation_pressure=0.1,
            priced_in_discount=0.05,
        )
        # 0.5 + 0.2 + 0.1 - 0.1 - 0.1 - 0.05
        assert out["score"] == pytest.approx(0.55)

    def test_multiplier_chain_applied(self) -> None:
        out = compute_company_score(
            industry_variables=[
                self._industry_var(
                    1.0, exposure=0.5, revenue_share=0.5,
                    profit_elasticity=2.0, financial_sensitivity=1.5,
                    valuation_sensitivity=1.0,
                )
            ],
            company_event_score=0.0,
            capital_sentiment_score=0.0,
            risk_discount=0.0,
            valuation_pressure=0.0,
            priced_in_discount=0.0,
        )
        # 1.0 * 0.5 * 0.5 * 2.0 * 1.5 * 1.0 = 0.75
        assert out["score"] == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Spec §27.4 — stock final score (three horizons)
# ---------------------------------------------------------------------------


class TestFinalScore:
    def test_unweighted_base(self) -> None:
        out = compute_final_score(
            fundamental_score=0.4,
            expectation_gap_score=0.1,
            valuation_rerating_score=0.05,
            capital_sentiment_score=0.1,
            risk_discount=0.05,
            priced_in_discount=0.02,
        )
        expected = 0.4 + 0.1 + 0.05 + 0.1 - 0.05 - 0.02
        assert out["base_score"] == pytest.approx(expected)
        # When no horizon weights are supplied, every horizon == base.
        assert out["short_total"] == pytest.approx(expected)
        assert out["medium_total"] == pytest.approx(expected)
        assert out["long_total"] == pytest.approx(expected)

    def test_horizon_weights_emphasize_short_events(self) -> None:
        """Spec §28: short-line weights events + capital flow more, long-line
        weights fundamentals more."""

        out = compute_final_score(
            fundamental_score=0.0,
            expectation_gap_score=0.0,
            valuation_rerating_score=0.0,
            capital_sentiment_score=1.0,    # only capital signal active
            risk_discount=0.0,
            priced_in_discount=0.0,
            horizons={
                "short":  {"fundamental": 0.1, "expectation_gap": 0.2,
                           "valuation_rerating": 0.1, "capital_sentiment": 0.6},
                "medium": {"fundamental": 0.5, "expectation_gap": 0.3,
                           "valuation_rerating": 0.1, "capital_sentiment": 0.1},
                "long":   {"fundamental": 0.6, "expectation_gap": 0.05,
                           "valuation_rerating": 0.3, "capital_sentiment": 0.05},
            },
        )
        assert out["short_total"] == pytest.approx(0.6)
        assert out["medium_total"] == pytest.approx(0.1)
        assert out["long_total"] == pytest.approx(0.05)
        # short should dominate when only capital_sentiment is non-zero.
        assert out["short_total"] > out["medium_total"] > out["long_total"]

    def test_long_horizon_emphasizes_fundamental(self) -> None:
        out = compute_final_score(
            fundamental_score=1.0,
            expectation_gap_score=0.0,
            valuation_rerating_score=0.0,
            capital_sentiment_score=0.0,
            risk_discount=0.0,
            priced_in_discount=0.0,
            horizons={
                "short":  {"fundamental": 0.1, "capital_sentiment": 0.6,
                           "expectation_gap": 0.2, "valuation_rerating": 0.1},
                "medium": {"fundamental": 0.5, "capital_sentiment": 0.1,
                           "expectation_gap": 0.3, "valuation_rerating": 0.1},
                "long":   {"fundamental": 0.6, "capital_sentiment": 0.05,
                           "expectation_gap": 0.05, "valuation_rerating": 0.3},
            },
        )
        assert out["long_total"] > out["medium_total"] > out["short_total"]

    def test_trading_meaning_string_present(self) -> None:
        out = compute_final_score(
            fundamental_score=0.5,
            expectation_gap_score=0.0,
            valuation_rerating_score=0.0,
            capital_sentiment_score=0.0,
            risk_discount=0.0,
            priced_in_discount=0.0,
        )
        assert "短" in out["trading_meaning"]
        assert "中" in out["trading_meaning"]
        assert "长" in out["trading_meaning"]


# ---------------------------------------------------------------------------
# Spec §30 — mode classifier (7 modes, one case each)
# ---------------------------------------------------------------------------


def _final(short: float = 0.0, medium: float = 0.0, long_: float = 0.0) -> dict:
    return {"short_total": short, "medium_total": medium, "long_total": long_}


class TestClassifyMode:
    def test_strong_bull(self) -> None:
        """Industry ↑ + exposure high + financial ↑ + valuation not over +
        capital ↑ (spec §30 强多头)."""

        result = classify_mode(
            final_score=_final(0.5, 0.6, 0.5),
            signals={
                "industry_trend": 0.5,
                "exposure": 0.7,
                "financial_revision": 0.3,
                "valuation_pressure": 0.4,
                "capital_flow": 0.4,
            },
        )
        assert result["mode"] == MODE_STRONG_BULL
        assert result["confidence"] > 0.3

    def test_moderate_bull(self) -> None:
        """Fundamentals strong, but expectation gap narrow (gap < 0.4) and
        valuation merely "reasonable" (not under 0.6) — spec §30 温和多头."""

        result = classify_mode(
            final_score=_final(0.2, 0.3, 0.2),
            signals={
                "industry_trend": 0.3,
                "exposure": 0.6,
                "financial_revision": 0.1,
                "valuation_pressure": 0.7,
                "capital_flow": 0.1,
                "expectation_gap": 0.2,
            },
        )
        assert result["mode"] == MODE_MODERATE_BULL

    def test_digestion(self) -> None:
        """Priced-in high, new catalyst low, finance stable, capital rotating
        (spec §30 震荡消化)."""

        result = classify_mode(
            final_score=_final(0.05, 0.10, 0.05),
            signals={
                "industry_trend": 0.05,  # not enough for divergence/bull
                "exposure": 0.6,
                "financial_revision": 0.05,
                "valuation_pressure": 0.5,
                "capital_flow": 0.0,
                "priced_in": 0.7,
                "new_catalyst": 0.1,
            },
        )
        assert result["mode"] == MODE_DIGESTION

    def test_structural_divergence(self) -> None:
        """Industry-wide tailwind, but this name's exposure is limited
        (spec §30 结构分化)."""

        result = classify_mode(
            final_score=_final(0.05, 0.05, 0.05),
            signals={
                "industry_trend": 0.4,
                "exposure": 0.2,            # ⇐ low exposure
                "financial_revision": 0.0,
                "valuation_pressure": 0.4,
                "capital_flow": 0.0,
            },
        )
        assert result["mode"] == MODE_STRUCTURAL_DIVERGENCE

    def test_de_rating(self) -> None:
        """Earnings flat but slowing, valuation high, capital exiting
        (spec §30 杀估值)."""

        result = classify_mode(
            final_score=_final(-0.1, -0.05, 0.0),
            signals={
                "industry_trend": 0.1,
                "exposure": 0.5,
                "financial_revision": 0.05,
                "valuation_pressure": 0.8,
                "capital_flow": -0.4,
            },
        )
        assert result["mode"] == MODE_DE_RATING

    def test_trend_reversal(self) -> None:
        """Industry ↓ + financial ↓ + capital ↓ (spec §30 趋势反转)."""

        result = classify_mode(
            final_score=_final(-0.4, -0.5, -0.5),
            signals={
                "industry_trend": -0.5,
                "exposure": 0.6,
                "financial_revision": -0.4,
                "valuation_pressure": 0.5,
                "capital_flow": -0.5,
                "competition": -0.3,
            },
        )
        assert result["mode"] == MODE_TREND_REVERSAL

    def test_wait_for_confirmation(self) -> None:
        """Event present, operating data not confirmed yet
        (spec §30 等待验证)."""

        result = classify_mode(
            final_score=_final(0.05, 0.05, 0.05),
            signals={
                "industry_trend": 0.0,
                "exposure": 0.6,
                "financial_revision": 0.0,
                "valuation_pressure": 0.5,
                "capital_flow": 0.0,
                "event_present": 1.0,
                "operating_confirmed": 0.1,
                "expectation_gap": 0.1,
            },
        )
        assert result["mode"] == MODE_WAIT_FOR_CONFIRMATION

    def test_fallback_negative_score_to_trend_reversal(self) -> None:
        """No specific rule fires but the central score is meaningfully
        negative — fallback should NOT claim a bull mode."""

        result = classify_mode(
            final_score=_final(-0.3, -0.3, -0.3),
            signals={},
        )
        assert result["mode"] == MODE_TREND_REVERSAL


# ---------------------------------------------------------------------------
# Trading signal thresholds
# ---------------------------------------------------------------------------


class TestTradingSignal:
    def _final_with_scores(self, val: float) -> dict:
        """Build the final_score-like dict used by score_company shaped
        results, with the same value across all horizons."""

        return _final(val, val, val)

    def test_signal_buy_at_threshold(self) -> None:
        from mvp20.scoring import _trading_signal_from_mix
        v = SIGNAL_BUY_THRESHOLD + 0.05
        assert _trading_signal_from_mix(v, v, v) == "BUY"

    def test_signal_hold(self) -> None:
        from mvp20.scoring import _trading_signal_from_mix
        v = (SIGNAL_BUY_THRESHOLD + SIGNAL_HOLD_THRESHOLD) / 2
        assert _trading_signal_from_mix(v, v, v) == "HOLD"

    def test_signal_watch(self) -> None:
        from mvp20.scoring import _trading_signal_from_mix
        v = (SIGNAL_HOLD_THRESHOLD + SIGNAL_WATCH_THRESHOLD) / 2
        assert _trading_signal_from_mix(v, v, v) == "WATCH"

    def test_signal_avoid(self) -> None:
        from mvp20.scoring import _trading_signal_from_mix
        v = SIGNAL_WATCH_THRESHOLD - 0.20
        assert _trading_signal_from_mix(v, v, v) == "AVOID"

    def test_horizon_weights_used(self) -> None:
        """Weighted mix uses HORIZON_DEFAULT_WEIGHTS by default; medium
        carries the largest weight, so a strong-medium picture should
        push the mix higher than the simple average would."""

        from mvp20.scoring import _trading_signal_from_mix
        # short=0, medium=0.8, long=0 — default weights give
        # 0 * 0.30 + 0.8 * 0.45 + 0 * 0.25 = 0.36 ⇒ HOLD
        assert _trading_signal_from_mix(0.0, 0.8, 0.0) == "HOLD"


# ---------------------------------------------------------------------------
# Orchestrator — score_company end-to-end
# ---------------------------------------------------------------------------


class TestScoreCompany:
    def _baseline_overlay(self) -> dict:
        return {
            "ts_code": "300750.SZ",
            "industry_id": "STORAGE_GRID",
            "name": "宁德时代",
        }

    def test_handles_empty_aggregator(self) -> None:
        result = score_company(
            stock_overlay=self._baseline_overlay(),
            aggregated_nodes={},
            coverage_report={},
            realtime_data={},
        )
        assert result["ts_code"] == "300750.SZ"
        assert "mode" in result
        assert result["trading_signal"] in {"BUY", "HOLD", "WATCH", "AVOID"}
        # No signals ⇒ wait_for_confirmation fallback.
        assert result["mode"] in {
            MODE_WAIT_FOR_CONFIRMATION,
            MODE_TREND_REVERSAL,
        }

    def test_strong_bull_end_to_end(self) -> None:
        """Wire a 'clean bull' aggregator payload and assert the
        orchestrator surfaces strong_bull + BUY."""

        agg = {
            "industry_variables": [
                {"name": "demand", "score": 0.5, "exposure": 0.7,
                 "revenue_share": 1.0, "profit_elasticity": 1.2,
                 "financial_sensitivity": 1.0, "valuation_sensitivity": 1.0,
                 "direction": 1.0, "confidence": 0.8},
            ],
            "company_event_score": 0.2,
            "capital_sentiment_score": 0.3,
            "risk_discount": 0.05,
            "valuation_pressure": 0.0,
            "priced_in_discount": 0.0,
            "expectation_gap_score": 0.2,
            "valuation_rerating_score": 0.1,
            # Signals for the mode classifier:
            "industry_trend": 0.6,
            "company_exposure_overall": 0.7,
            "financial_revision": 0.3,
            "capital_flow": 0.4,
            "competition": 0.1,
        }
        result = score_company(
            stock_overlay=self._baseline_overlay(),
            aggregated_nodes=agg,
            coverage_report={"data_coverage": 0.7},
            realtime_data={},
        )
        assert result["mode"] == MODE_STRONG_BULL
        assert result["trading_signal"] == "BUY"
        assert result["short_total"] > 0
        assert result["company_score"]["score"] > 0

    def test_top_paths_surface_aggregated_nodes(self) -> None:
        agg = {
            "industry_variables": [],
            "nodes": {
                "demand": {"path_score": 0.5, "direction": 1.0,
                           "name": "需求强度", "node_id": "demand"},
                "discount": {"path_score": -0.3, "direction": -1.0,
                             "name": "价格压力", "node_id": "discount"},
                "cost": {"path_score": -0.2, "direction": -1.0,
                         "name": "成本压力", "node_id": "cost"},
                "noise": {"path_score": 0.0, "direction": 0.0,
                          "name": "noise", "node_id": "noise"},
            },
        }
        result = score_company(
            stock_overlay=self._baseline_overlay(),
            aggregated_nodes=agg,
        )
        top = result["top_paths"]
        assert len(top["positive"]) >= 1
        assert top["positive"][0]["rationale"] == "需求强度"
        assert top["negative"][0]["rationale"] == "价格压力"
        # ranked by magnitude
        assert top["negative"][0]["score"] < top["negative"][1]["score"]

    def test_horizon_weights_propagate(self) -> None:
        agg = {
            "industry_variables": [],
            "company_event_score": 0.0,
            "capital_sentiment_score": 1.0,  # only capital signal
            "risk_discount": 0.0,
            "valuation_pressure": 0.0,
            "priced_in_discount": 0.0,
            "expectation_gap_score": 0.0,
            "valuation_rerating_score": 0.0,
        }
        horizons = {
            "short":  {"fundamental": 0.1, "expectation_gap": 0.2,
                       "valuation_rerating": 0.1, "capital_sentiment": 0.6},
            "medium": {"fundamental": 0.5, "expectation_gap": 0.3,
                       "valuation_rerating": 0.1, "capital_sentiment": 0.1},
            "long":   {"fundamental": 0.6, "expectation_gap": 0.05,
                       "valuation_rerating": 0.3, "capital_sentiment": 0.05},
        }
        result = score_company(
            stock_overlay=self._baseline_overlay(),
            aggregated_nodes=agg,
            horizons=horizons,
        )
        # capital sentiment is short-weighted ⇒ short > medium > long.
        assert result["short_total"] > result["medium_total"]
        assert result["medium_total"] > result["long_total"]


# ---------------------------------------------------------------------------
# Sanity: default horizon weights sum to 1.0
# ---------------------------------------------------------------------------


def test_default_horizon_weights_sum_to_one() -> None:
    total = sum(HORIZON_DEFAULT_WEIGHTS.values())
    assert total == pytest.approx(1.0)


def test_role_configuration_takes_priority_over_layer_inference() -> None:
    stock_overlay = {
        "ts_code": "ROLE.TEST",
        "industry_id": "TEST",
        "nodes": [
            {
                "node_id": "raw",
                "node_name": "raw",
                "layer": "industry_macro",
                "materiality": 1.0,
                "field_role": "raw_input",
                "score_target": "none",
                "participates_in_score": False,
            },
            {
                "node_id": "fund",
                "node_name": "fund",
                "layer": "non_industry_layer",
                "materiality": 1.0,
                "field_role": "score_component",
                "score_target": "fundamental_score",
                "participates_in_score": True,
            },
            {
                "node_id": "risk",
                "node_name": "risk",
                "layer": "non_industry_layer",
                "field_role": "discount",
                "score_target": "risk_discount",
                "participates_in_score": True,
            },
            {
                "node_id": "capital",
                "node_name": "capital",
                "layer": "non_industry_layer",
                "field_role": "multiplier",
                "score_target": "capital_sentiment",
                "participates_in_score": True,
            },
        ],
    }
    aggregated = {
        "raw": {
            "score": 1.0,
            "confidence": 1.0,
            "field_role": "raw_input",
            "score_target": "none",
            "participates_in_score": False,
            "score_enabled": False,
        },
        "fund": {
            "score": 0.8,
            "confidence": 1.0,
            "field_role": "score_component",
            "score_target": "fundamental_score",
            "participates_in_score": True,
            "score_enabled": True,
        },
        "risk": {
            "score": -0.2,
            "confidence": 1.0,
            "field_role": "discount",
            "score_target": "risk_discount",
            "participates_in_score": True,
            "score_enabled": True,
        },
        "capital": {
            "score": 0.3,
            "confidence": 1.0,
            "field_role": "multiplier",
            "score_target": "capital_sentiment",
            "participates_in_score": True,
            "score_enabled": True,
        },
    }

    result = score_company(stock_overlay, aggregated_nodes=aggregated)

    assert result["company_score"]["components"]["industry_contrib"] == pytest.approx(0.8)
    assert result["role_components"]["risk_discount"] == pytest.approx(0.2)
    assert result["role_components"]["capital_sentiment"] == pytest.approx(0.3)


def test_scoring_keeps_legacy_layer_inference_when_roles_are_absent() -> None:
    stock_overlay = {
        "ts_code": "LEGACY.TEST",
        "industry_id": "TEST",
        "nodes": [
            {
                "node_id": "industry_node",
                "node_name": "industry",
                "layer": "industry_macro",
                "materiality": 1.0,
            },
        ],
    }
    aggregated = {
        "industry_node": {
            "score": 0.6,
            "confidence": 1.0,
        },
    }

    result = score_company(stock_overlay, aggregated_nodes=aggregated)

    assert result["company_score"]["components"]["industry_contrib"] == pytest.approx(0.6)
    assert result["role_components"] == {}


def test_confidence_role_compresses_final_score_without_adding_signal() -> None:
    stock_overlay = {
        "ts_code": "CONF.TEST",
        "industry_id": "TEST",
        "nodes": [
            {
                "node_id": "fund",
                "node_name": "fund",
                "layer": "industry_macro",
                "materiality": 1.0,
                "field_role": "score_component",
                "score_target": "fundamental_score",
                "participates_in_score": True,
            },
            {
                "node_id": "validation",
                "node_name": "validation",
                "layer": "validation_metric",
                "field_role": "confidence",
                "score_target": "confidence_multiplier",
                "participates_in_score": True,
            },
        ],
    }
    aggregated = {
        "fund": {
            "score": 1.0,
            "confidence": 1.0,
            "field_role": "score_component",
            "score_target": "fundamental_score",
            "participates_in_score": True,
            "score_enabled": True,
        },
        "validation": {
            "score": 1.0,
            "confidence": 0.5,
            "field_role": "confidence",
            "score_target": "confidence_multiplier",
            "participates_in_score": True,
            "score_enabled": True,
        },
    }

    result = score_company(stock_overlay, aggregated_nodes=aggregated)

    assert result["company_score"]["components"]["industry_contrib"] == pytest.approx(1.0)
    assert result["role_components"]["confidence_multiplier"] == pytest.approx(0.5)
    assert result["final_score"]["base_score"] == pytest.approx(0.5)


def test_semantic_targets_route_to_additive_multiplier_and_discount_channels() -> None:
    stock_overlay = {
        "ts_code": "SEM.TEST",
        "industry_id": "TEST",
        "nodes": [
            {
                "node_id": "fund",
                "node_name": "fund",
                "layer": "industry_macro",
                "materiality": 1.0,
                "field_role": "score_component",
                "score_target": "fundamental_score",
                "participates_in_score": True,
            },
            {
                "node_id": "funding",
                "node_name": "funding",
                "layer": "funding_sentiment",
                "field_role": "score_component",
                "score_target": "funding_score",
                "participates_in_score": True,
            },
            {
                "node_id": "theme",
                "node_name": "theme",
                "layer": "funding_sentiment",
                "field_role": "multiplier",
                "score_target": "theme_multiplier",
                "participates_in_score": True,
            },
            {
                "node_id": "uncertainty",
                "node_name": "uncertainty",
                "layer": "business_optionality",
                "field_role": "discount",
                "score_target": "uncertainty_discount",
                "participates_in_score": True,
            },
        ],
    }
    aggregated = {
        "fund": {
            "score": 1.0,
            "confidence": 1.0,
            "field_role": "score_component",
            "score_target": "fundamental_score",
            "participates_in_score": True,
            "score_enabled": True,
        },
        "funding": {
            "score": 0.2,
            "confidence": 1.0,
            "field_role": "score_component",
            "score_target": "funding_score",
            "participates_in_score": True,
            "score_enabled": True,
        },
        "theme": {
            "score": 0.5,
            "confidence": 1.0,
            "field_role": "multiplier",
            "score_target": "theme_multiplier",
            "participates_in_score": True,
            "score_enabled": True,
        },
        "uncertainty": {
            "score": -0.1,
            "confidence": 1.0,
            "field_role": "discount",
            "score_target": "uncertainty_discount",
            "participates_in_score": True,
            "score_enabled": True,
        },
    }

    result = score_company(stock_overlay, aggregated_nodes=aggregated)

    assert result["company_score"]["components"]["industry_contrib"] == pytest.approx(1.0)
    assert result["role_components"]["funding_score"] == pytest.approx(0.2)
    assert result["role_components"]["theme_multiplier"] == pytest.approx(1.5)
    assert result["role_components"]["risk_discount"] == pytest.approx(0.1)
    assert result["core_final_score"]["base_score"] == pytest.approx(1.6)
    assert result["market_adapter"]["market_code"] == "US"
    assert result["final_score"]["base_score"] > result["core_final_score"]["base_score"]


def test_score_company_outputs_core_and_market_adjusted_scores() -> None:
    stock_overlay = {
        "ts_code": "300750.SZ",
        "industry_id": "TEST",
        "nodes": [
            {
                "node_id": "fund",
                "node_name": "fund",
                "layer": "industry_macro",
                "materiality": 1.0,
                "field_role": "score_component",
                "score_target": "fundamental_score",
                "participates_in_score": True,
            },
            {
                "node_id": "theme",
                "node_name": "theme",
                "layer": "funding_sentiment",
                "field_role": "multiplier",
                "score_target": "theme_multiplier",
                "participates_in_score": True,
            },
        ],
    }
    aggregated = {
        "fund": {
            "score": 1.0,
            "confidence": 1.0,
            "field_role": "score_component",
            "score_target": "fundamental_score",
            "participates_in_score": True,
            "score_enabled": True,
        },
        "theme": {
            "score": 0.5,
            "confidence": 1.0,
            "field_role": "multiplier",
            "score_target": "theme_multiplier",
            "participates_in_score": True,
            "score_enabled": True,
        },
    }

    result = score_company(stock_overlay, aggregated_nodes=aggregated)

    assert result["core_final_score"]["base_score"] == pytest.approx(1.5)
    assert result["market_adapter"]["market_code"] == "CN_A"
    assert result["market_adjusted_final_score"] is result["final_score"]
    assert result["short_total"] == pytest.approx(result["final_score"]["short_total"])
