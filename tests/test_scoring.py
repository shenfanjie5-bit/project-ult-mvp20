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
    SPEC28_DEFAULT_HORIZON_MIX,
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
        # R-2b: ``industry_contrib`` is now the RAW weighted_sum Σ(score×weight)
        # where weight = exposure×rev_share×prof_e×fin_s×val_s×confidence.
        # weights: v1 conf1 → w=1.0; v2 exposure0.5 conf1 → w=0.5; v3 w=1.0.
        # weighted_sum = 0.3*1 + 0.4*0.5 + (-0.1)*1 = 0.4 (surfaced for
        # transparency). The value that enters ``score`` is the COVERAGE-WEIGHTED
        # MEAN weighted_sum/weight_sum = 0.4 / (1.0+0.5+1.0) = 0.4/2.5 = 0.16
        # (already in [-1,1]; no tanh). No other channels here, so score == mean.
        assert out["components"]["industry_contrib"] == pytest.approx(0.4)
        assert out["components"]["industry_contrib_bounded"] == pytest.approx(0.16)
        assert out["score"] == pytest.approx(0.16)
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
        # R-2b: the fundamental block is now the COVERAGE-WEIGHTED MEAN of the
        # industry vars (already in [-1,1], no tanh). A single node's mean is
        # the node score itself (the multipliers only scale its weight, which
        # cancels in the 1-node mean), so mean = 0.5. The discount/additive
        # channels then subtract/add unchanged:
        #   score = 0.5 + 0.2 + 0.1 - 0.1 - 0.1 - 0.05 = 0.55.
        # The raw weighted_sum (0.5*weight, weight=1.0 here) still lives in
        # components["industry_contrib"].
        assert out["components"]["industry_contrib"] == pytest.approx(0.5)
        assert out["score"] == pytest.approx(0.5 + 0.2 + 0.1 - 0.1 - 0.1 - 0.05)

    def test_multiplier_chain_applied_to_raw_contrib_not_mean(self) -> None:
        # R-2b: the multiplier chain (exposure×rev_share×prof_e×fin_s×val_s) now
        # scales only the WEIGHT, not the value that enters ``score``. For a
        # SINGLE industry var the coverage-weighted mean is the node score
        # itself (the weight cancels: weighted_sum/weight_sum = score×w / w =
        # score), so score = 1.0 regardless of the multipliers. The multipliers
        # still surface in the RAW weighted_sum reported as
        # components["industry_contrib"]: contrib = score×weight, and with
        # confidence defaulting to 1.0 the weight == the product chain
        # 0.5*0.5*2.0*1.5*1.0 = 0.75 → weighted_sum = 1.0*0.75 = 0.75.
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
        assert out["components"]["industry_contrib"] == pytest.approx(0.75)
        assert out["components"]["industry_contrib_bounded"] == pytest.approx(1.0)
        assert out["score"] == pytest.approx(1.0)


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
        push the mix higher than the simple average would.

        T3 thresholds (BUY 0.30 / HOLD -0.10 / WATCH -0.45): pick a
        medium-only input where the weighted mix clears BUY but the naive
        simple average would not — this is what proves the weighting (not
        just the magnitude) is doing the work.
        """

        from mvp20.scoring import _trading_signal_from_mix
        # short=0, medium=0.7, long=0 — default weights give
        # 0 * 0.30 + 0.7 * 0.45 + 0 * 0.25 = 0.315 ⇒ BUY (≥ 0.30).
        # The simple average would be 0.7 / 3 = 0.233 ⇒ only HOLD (≥ -0.10,
        # < 0.30), so the BUY label here is attributable to medium's heavier
        # weight rather than the raw magnitude.
        assert _trading_signal_from_mix(0.0, 0.7, 0.0) == "BUY"


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


# ---------------------------------------------------------------------------
# Spec §28 default per-horizon component mix
# ---------------------------------------------------------------------------


def test_spec28_default_horizon_mix_component_weights_sum_to_one() -> None:
    """Each horizon's 4 component weights must sum to 1.0 (so the mix is
    a proper convex combination, not an arbitrary scaling)."""

    for horizon, weights in SPEC28_DEFAULT_HORIZON_MIX.items():
        total = sum(weights.values())
        assert total == pytest.approx(1.0), (
            f"horizon={horizon} weights={weights} sum={total}"
        )


def test_spec28_default_horizon_mix_short_emphasises_capital_sentiment() -> None:
    """Short horizon must weight capital_sentiment > fundamental (intraday
    moves are flow-driven). Long horizon must invert that ordering."""

    s = SPEC28_DEFAULT_HORIZON_MIX["short"]
    l = SPEC28_DEFAULT_HORIZON_MIX["long"]
    assert s["capital_sentiment"] > s["fundamental"]
    assert l["fundamental"] > l["capital_sentiment"]


def test_score_company_horizons_diverge_without_explicit_override() -> None:
    """Regression for the bug surfaced on 浪潮信息 (000977.SZ) where the
    UI rendered 短/中/长 all equal because the BFF called ``score_company``
    without supplying ``horizons``. After wiring SPEC §28 defaults inside
    ``score_company``, three horizons must differ as long as the input
    signal is not perfectly symmetric across components."""

    stock_overlay = {"ts_code": "TEST.HORIZON", "industry_id": "TEST"}
    # Inject only a fundamental signal (industry-driven) so the per-horizon
    # weight on `fundamental` (short=0.20 vs long=0.60) directly shows up
    # as a divergent total. No risk / priced-in / capital so the math is
    # unambiguous.
    aggregated = {
        "industry_variables": [],
        "company_event_score": 0.0,
        "capital_sentiment_score": 0.0,
        "risk_discount": 0.0,
        "valuation_pressure": 0.0,
        "priced_in_discount": 0.0,
        "expectation_gap_score": 0.0,
        "valuation_rerating_score": 0.0,
        "nodes": {
            "fund": {
                "node_id": "fund",
                "path_score": 0.5,
                "direction": 1.0,
                "name": "fundamental",
            },
        },
        # Inject industry_contrib via the company-aggregate shortcut.
        "company_event_score": 0.0,
    }
    # Use the envelope shape so industry_contrib flows through.
    aggregated["industry_variables"] = [
        {"score": 0.5, "weight": 1.0, "confidence": 1.0},
    ]

    result = score_company(
        stock_overlay=stock_overlay,
        aggregated_nodes=aggregated,
    )
    short_t = result["short_total"]
    medium_t = result["medium_total"]
    long_t = result["long_total"]
    # Fundamental dominates ⇒ long > medium > short (since long has the
    # heaviest fundamental weight: 0.60 vs 0.50 vs 0.20).
    assert long_t > medium_t > short_t, (
        f"expected long > medium > short with fundamental-only signal; "
        f"got short={short_t} medium={medium_t} long={long_t}"
    )


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
    # R-2b: the fundamental is the single-node coverage-weighted mean = the node
    # score (1.0), already in [-1,1] (no tanh). The 0.5 confidence multiplier
    # then halves base_score → 1.0 * 0.5 = 0.5. The intent stands: confidence
    # COMPRESSES the score (scales it down) without adding any new signal.
    assert result["final_score"]["base_score"] == pytest.approx(1.0 * 0.5)


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
    # R-2b: fundamental is the single-node coverage-weighted mean = 1.0 (no
    # tanh). The post-tanh ``fundamental *= multiplier_stack`` was REMOVED, so
    # the theme_multiplier (1.5) no longer scales the fundamental block — it is
    # still routed to role_components for downstream/timing channels. The
    # additive funding_score (+0.2) and the risk_discount (-0.1) net +0.1 on top
    # of the fundamental: base_score = 1.0 + 0.2 - 0.1 = 1.1. The semantic
    # routing intent stands: additive→add, discount→subtract, multiplier→its
    # own channel. Pre-R-2b this was tanh(1.0)*1.5 + 0.1.
    assert result["core_final_score"]["base_score"] == pytest.approx(1.0 + 0.2 - 0.1)
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

    # R-2b: fundamental is the single-node coverage-weighted mean = 1.0 (no
    # tanh), and the ``fundamental *= multiplier_stack`` step was REMOVED, so
    # the theme_multiplier (1.5) no longer scales the fundamental block. No
    # additive/discount channels here ⇒ core base_score = 1.0. Pre-R-2b:
    # tanh(1.0)*1.5.
    assert result["core_final_score"]["base_score"] == pytest.approx(1.0)
    assert result["market_adapter"]["market_code"] == "CN_A"
    assert result["market_adjusted_final_score"] is result["final_score"]
    assert result["short_total"] == pytest.approx(result["final_score"]["short_total"])


# ---------------------------------------------------------------------------
# Damped role-target roll-up: ``Σ(score×conf) / max(1.0, Σconf)``.
#   * Σconf ≤ 1 (sparse / single low-conf node) → denominator floored to 1.0
#     → identical to the raw confidence-weighted sum (UNCHANGED behaviour).
#   * Σconf > 1 (signals stack) → averages, killing the inflation.
# ---------------------------------------------------------------------------


class TestDampedRoleTarget:
    def _node(self, score: float, conf: float, target: str = "expectation_gap") -> dict:
        return {"score": score, "confidence": conf, "score_target": target}

    def test_sparse_single_low_conf_node_is_unchanged(self) -> None:
        """One node score 0.8 conf 0.5: Σconf=0.5 ≤ 1 → max(1.0, 0.5)=1.0,
        so damp = 0.8×0.5 / 1.0 = 0.4 == the non-damped sum (0.4)."""

        from mvp20.scoring import _sum_role_target

        agg = {"n1": self._node(0.8, 0.5)}
        non_damped = _sum_role_target(agg, "expectation_gap", damp=False)
        damped = _sum_role_target(agg, "expectation_gap", damp=True)
        assert non_damped == pytest.approx(0.4)   # 0.8 * 0.5
        assert damped == pytest.approx(0.4)        # / max(1.0, 0.5) = /1.0
        assert damped == pytest.approx(non_damped)

    def test_dense_signals_average_not_sum(self) -> None:
        """Three nodes each score 0.8 conf 0.9: Σconf=2.7 > 1.
        non-damped = 3 × (0.8×0.9) = 2.16.
        damped = 2.16 / max(1.0, 2.7) = 2.16 / 2.7 = 0.8 (≈ per-node score)."""

        from mvp20.scoring import _sum_role_target

        agg = {f"n{i}": self._node(0.8, 0.9) for i in range(3)}
        non_damped = _sum_role_target(agg, "expectation_gap", damp=False)
        damped = _sum_role_target(agg, "expectation_gap", damp=True)
        assert non_damped == pytest.approx(2.16)   # 3 * 0.72
        assert damped == pytest.approx(0.8)         # 2.16 / 2.7
        assert damped < non_damped

    def test_absolute_true_dampens_magnitude(self) -> None:
        """absolute=True takes abs(score) before ×conf, then damps once.
        Three nodes score -0.8 conf 0.9: |−0.8|×0.9 = 0.72 each.
        non-damped = 2.16; damped = 2.16 / 2.7 = 0.8."""

        from mvp20.scoring import _sum_role_target

        agg = {f"n{i}": self._node(-0.8, 0.9, "risk_discount") for i in range(3)}
        non_damped = _sum_role_target(agg, "risk_discount", absolute=True, damp=False)
        damped = _sum_role_target(agg, "risk_discount", absolute=True, damp=True)
        assert non_damped == pytest.approx(2.16)
        assert damped == pytest.approx(0.8)
        assert damped < non_damped

    def test_no_matching_node_returns_zero(self) -> None:
        from mvp20.scoring import _sum_role_target

        assert _sum_role_target({}, "expectation_gap", damp=True) == pytest.approx(0.0)


class TestDampedRoleTargets:
    """``_sum_role_targets`` over a SET — damping applied ONCE over the
    combined group (accumulate total + conf_sum across all targets, divide
    a single time), NOT per-target."""

    def test_sparse_set_is_unchanged(self) -> None:
        """One node (funding_score) score 0.8 conf 0.5 in a 2-target set:
        Σconf=0.5 ≤ 1 → damp = 0.4 == non-damped sum."""

        from mvp20.scoring import _sum_role_targets

        agg = {"a": {"score": 0.8, "confidence": 0.5, "score_target": "funding_score"}}
        targets = {"funding_score", "sentiment_score"}
        non_damped = _sum_role_targets(agg, targets, damp=False)
        damped = _sum_role_targets(agg, targets, damp=True)
        assert non_damped == pytest.approx(0.4)
        assert damped == pytest.approx(0.4)
        assert damped == pytest.approx(non_damped)

    def test_dense_set_dampens_once_over_combined_group(self) -> None:
        """Three nodes (one per target in the set), each score 0.8 conf 0.9:
        combined Σ(score×conf)=2.16, combined Σconf=2.7.
        damped = 2.16 / max(1.0, 2.7) = 0.8 — a SINGLE divide over the group,
        not 3 separate per-target damps (each of which would also be 0.8 and
        then SUM back to 2.4)."""

        from mvp20.scoring import _sum_role_targets

        agg = {
            "a": {"score": 0.8, "confidence": 0.9, "score_target": "funding_score"},
            "b": {"score": 0.8, "confidence": 0.9, "score_target": "sentiment_score"},
            "c": {"score": 0.8, "confidence": 0.9, "score_target": "capital_sentiment"},
        }
        targets = {"funding_score", "sentiment_score", "capital_sentiment"}
        non_damped = _sum_role_targets(agg, targets, damp=False)
        damped = _sum_role_targets(agg, targets, damp=True)
        assert non_damped == pytest.approx(2.16)
        assert damped == pytest.approx(0.8)        # combined-once, NOT 2.4
        assert damped < non_damped

    def test_absolute_true_set_dampens_once(self) -> None:
        from mvp20.scoring import _sum_role_targets

        agg = {
            "a": {"score": -0.8, "confidence": 0.9, "score_target": "risk_discount"},
            "b": {"score": -0.8, "confidence": 0.9, "score_target": "overheat_risk"},
            "c": {"score": -0.8, "confidence": 0.9, "score_target": "volatility_risk"},
        }
        targets = {"risk_discount", "overheat_risk", "volatility_risk"}
        non_damped = _sum_role_targets(agg, targets, absolute=True, damp=False)
        damped = _sum_role_targets(agg, targets, absolute=True, damp=True)
        assert non_damped == pytest.approx(2.16)
        assert damped == pytest.approx(0.8)
        assert damped < non_damped

    def test_no_matching_node_returns_zero(self) -> None:
        from mvp20.scoring import _sum_role_targets

        assert _sum_role_targets({}, {"funding_score"}, damp=True) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Fundamental collapse: synthetic dead-sink nodes (fundamental_score /
# optionality_score) collapse into a SINGLE "realtime_fundamental" damped-mean
# industry variable so industry_contrib does not scale linearly with the
# synthetic node count.
# ---------------------------------------------------------------------------


class TestFundamentalCollapse:
    def _governed_overlay(self) -> dict:
        # One authored governance node so _has_role_governance() is True and
        # the synthetic dead-sink rescue path runs. The authored node carries
        # no aggregate score (kept out of the collapse below).
        return {
            "ts_code": "X",
            "industry_id": "TEST",
            "nodes": [
                {
                    "node_id": "auth",
                    "dp_id": "L5.is.eps",
                    "node_name": "auth",
                    "layer": "industry_macro",
                    "field_role": "score_component",
                    "score_target": "fundamental_score",
                    "participates_in_score": True,
                }
            ],
        }

    def _synthetic(self, score: float, conf: float) -> dict:
        return {
            "score": score,
            "confidence": conf,
            "score_target": "fundamental_score",
            "synthetic_realtime": True,
            "participates_in_score": True,
            "score_enabled": True,
        }

    def test_three_synthetic_nodes_collapse_to_one_damped_mean(self) -> None:
        """3 synthetic fundamental_score nodes (0.6/0.9, 0.9/0.9, 0.3/0.9).
        Σ(score×conf) = (0.6+0.9+0.3)×0.9 = 1.8×0.9 = 1.62; Σconf = 2.7.
        damped mean = 1.62 / max(1.0, 2.7) = 0.6. Exactly ONE
        "realtime_fundamental" var, score 0.6, conf = mean(0.9)=0.9."""

        from mvp20.scoring import _industry_variables_from_flat

        overlay = self._governed_overlay()
        agg = {
            # authored node has no real score → excluded from the collapse,
            # but its presence keeps the governance path on.
            "auth": {
                "score": 0.0, "confidence": 0.5,
                "field_role": "score_component",
                "score_target": "fundamental_score",
                "participates_in_score": True, "score_enabled": True,
            },
            "X:dp1:rt": self._synthetic(0.6, 0.9),
            "X:dp2:rt": self._synthetic(0.9, 0.9),
            "X:dp3:rt": self._synthetic(0.3, 0.9),
        }
        ivars = _industry_variables_from_flat(agg, overlay)
        rt = [v for v in ivars if v["node_id"] == "realtime_fundamental"]
        assert len(rt) == 1                              # collapsed to ONE var
        assert rt[0]["score"] == pytest.approx(0.6)      # 1.62 / 2.7
        assert rt[0]["confidence"] == pytest.approx(0.9)  # mean conf
        assert rt[0]["name"] == "realtime_fundamental"

    def test_industry_contrib_does_not_scale_linearly_with_node_count(self) -> None:
        """1 vs 3 synthetic nodes of the SAME score/conf must NOT triple the
        industry contribution. With per-node summing (the old behaviour) 3
        nodes would have summed to 3×. With the damped-mean collapse the
        contribution stays bounded near the single-node value."""

        from mvp20.scoring import score_company

        overlay = self._governed_overlay()

        def contrib_for(n: int) -> float:
            agg = {
                "auth": {
                    "score": 0.0, "confidence": 0.5,
                    "field_role": "score_component",
                    "score_target": "fundamental_score",
                    "participates_in_score": True, "score_enabled": True,
                },
            }
            for i in range(n):
                agg[f"X:dp{i}:rt"] = self._synthetic(0.8, 0.9)
            res = score_company(overlay, aggregated_nodes=agg)
            return res["company_score"]["components"]["industry_contrib"]

        one = contrib_for(1)
        three = contrib_for(3)
        # Two stages now bound the contribution against node count:
        #  (1) the dead-sink rescue collapses the synthetic nodes into ONE
        #      "realtime_fundamental" var via a damped mean — 1 node →
        #      0.72/max(1.0,0.9)=0.72; 3 nodes → 2.16/2.7=0.8.
        #  (2) R-2b: ``industry_contrib`` is then the RAW weighted_sum of the
        #      industry vars = collapsed_score × weight, weight = mean_conf (0.9)
        #      since the synthetic var defaults the other multipliers to 1.0:
        #        1 node → 0.72 * 0.9 = 0.648
        #        3 nodes → 0.80 * 0.9 = 0.720
        assert one == pytest.approx(0.648)
        assert three == pytest.approx(0.72)
        # Crucially NOT linear: 3 nodes is ~1.1×, not 3× (per-node summing
        # would have been 3 * 0.648 ≈ 1.94).
        assert three < 3.0 * one
        assert three < 1.0
