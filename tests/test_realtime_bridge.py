"""Tests for the realtime -> final_score bridge in mvp20.aggregator.

Covers:
- ``_realtime_signal``: the signed normalizer (score passthrough, signed
  percentile with valuation/risk inversion, yoy_pct, curated signed-percent
  fields incl. premium sign-flip, unmapped shapes -> None).
- ``synthesize_realtime_nodes``: gating (participates_in_score, mock source,
  data_status, dedupe vs authored overlay) and node shape/direction.
- End-to-end: realtime snapshot lifts ``aggregate_company_graph`` ->
  ``score_company`` off zero, with the correct valuation sign, and the same
  setup with ``realtime_snapshot=None`` stays ~0 (proves the bridge is cause).
"""

from __future__ import annotations

import math

import pytest

from mvp20.aggregator import (
    _realtime_signal,
    aggregate_company_graph,
    synthesize_realtime_nodes,
)
from mvp20.field_governance import (
    DataPointGovernance,
    FieldGovernanceRegistry,
)
from mvp20.scoring import score_company


# ---------------------------------------------------------------------------
# Fake governance registry — small + explicit so tests don't depend on the
# full config/data_point_roles.yaml.
# ---------------------------------------------------------------------------


def _gov(dp_id: str, *, target: str, participates: bool = True) -> DataPointGovernance:
    return DataPointGovernance(
        dp_id=dp_id,
        field_role="score_component" if participates else "audit",
        score_target=target,
        calculation_type="raw_value",
        aggregation_policy="none",
        missing_policy="unknown_reduce_confidence",
        fallback_policy="unknown_zero_score",
        proxy_candidates=(),
        min_required_coverage=0.5,
        neutral_value=0.0,
        confidence_penalty=1.0,
        participates_in_score=participates,
    )


def _registry(rules: dict[str, DataPointGovernance]) -> FieldGovernanceRegistry:
    return FieldGovernanceRegistry(rules, schema_version=1, source="test")


# ---------------------------------------------------------------------------
# _realtime_signal
# ---------------------------------------------------------------------------


def test_signal_score_passthrough_clipped():
    assert _realtime_signal("x", {"score": 0.4}, "fundamental_score") == pytest.approx(0.4)
    assert _realtime_signal("x", {"score": -0.4}, "fundamental_score") == pytest.approx(-0.4)
    # Out-of-range explicit sub-scores are clipped, not rejected.
    assert _realtime_signal("x", {"score": 1.5}, "fundamental_score") == pytest.approx(1.0)
    assert _realtime_signal("x", {"intensity": -2.0}, "fundamental_score") == pytest.approx(-1.0)
    assert _realtime_signal("x", {"strength": 0.25}, "fundamental_score") == pytest.approx(0.25)


def test_signal_percentile_inverted_for_valuation():
    # High percentile + valuation_rerating => expensive => NEGATIVE drag.
    val = _realtime_signal(
        "x", {"pe_percentile": 0.95, "pb_percentile": 0.9}, "valuation_rerating"
    )
    assert val == pytest.approx((0.95 - 0.5) * 2.0 * -1.0)
    assert val < 0


def test_signal_percentile_inverted_for_risk_targets():
    # risk_discount / overheat_risk / priced_in_discount all invert.
    for target in ("risk_discount", "overheat_risk", "priced_in_discount"):
        sig = _realtime_signal("x", {"crowd_percentile": 0.8}, target)
        assert sig == pytest.approx((0.8 - 0.5) * 2.0 * -1.0)
        assert sig < 0


def test_signal_percentile_positive_for_non_inverted_target():
    # Same high percentile on a non-inverted target stays POSITIVE.
    sig = _realtime_signal("x", {"pct_percentile": 0.9}, "expectation_gap")
    assert sig == pytest.approx((0.9 - 0.5) * 2.0)
    assert sig > 0


def test_signal_percentile_takes_max_of_multiple():
    sig = _realtime_signal(
        "x", {"pe_percentile": 0.2, "pb_percentile": 0.7}, "expectation_gap"
    )
    assert sig == pytest.approx((0.7 - 0.5) * 2.0)


def test_signal_yoy_pct():
    assert _realtime_signal("x", {"yoy_pct": 50.0}, "fundamental_score") == pytest.approx(
        math.tanh(1.0)
    )
    assert _realtime_signal("x", {"yoy_pct": -50.0}, "fundamental_score") == pytest.approx(
        -math.tanh(1.0)
    )


def test_signal_curated_eps_revision():
    assert _realtime_signal(
        "x", {"consensus_eps_revision_30d_pct": 10.0}, "expectation_gap"
    ) == pytest.approx(math.tanh(10.0 / 20.0))


def test_signal_curated_premium_is_sign_flipped():
    # Premium to industry = expensive = NEGATIVE. Discount = positive.
    rich = _realtime_signal(
        "x", {"premium_vs_industry_pct": 30.0}, "valuation_rerating"
    )
    cheap = _realtime_signal(
        "x", {"premium_vs_industry_pct": -30.0}, "valuation_rerating"
    )
    assert rich == pytest.approx(-math.tanh(30.0 / 30.0))
    assert rich < 0
    assert cheap == pytest.approx(math.tanh(30.0 / 30.0))
    assert cheap > 0


def test_signal_curated_second_derivative():
    assert _realtime_signal(
        "x", {"second_derivative": 1.0}, "valuation_rerating"
    ) == pytest.approx(math.tanh(1.0))


def test_signal_bare_numeric_passthrough_and_range():
    assert _realtime_signal("x", 0.3, "fundamental_score") == pytest.approx(0.3)
    assert _realtime_signal("x", -1.0, "fundamental_score") == pytest.approx(-1.0)
    # Out-of-range bare numerics are ambiguous (not pre-normalized) -> None.
    assert _realtime_signal("x", 5, "fundamental_score") is None
    # bool is not a numeric signal.
    assert _realtime_signal("x", True, "fundamental_score") is None


def test_signal_unmapped_shapes_return_none():
    # Bespoke financial dicts -> None (no fabricated direction).
    assert _realtime_signal("x", {"ccc_days": 30}, "fundamental_score") is None
    assert _realtime_signal("x", {"goodwill_to_assets": 0.1}, "fundamental_score") is None
    assert _realtime_signal("x", {"leverage_ratio": 1.2}, "fundamental_score") is None
    # multiplier dicts are centered at 1.0, not signed at 0 -> None.
    assert _realtime_signal("x", {"multiplier": 1.2, "drivers": []}, "x") is None
    assert _realtime_signal("x", None, "fundamental_score") is None
    assert _realtime_signal("x", "strong", "fundamental_score") is None
    assert _realtime_signal("x", [1, 2, 3], "fundamental_score") is None


# ---------------------------------------------------------------------------
# synthesize_realtime_nodes
# ---------------------------------------------------------------------------


def _full_snapshot() -> dict[str, dict]:
    return {
        "L6.derived.sub": {  # participating, derived score -> include
            "value": {"score": 0.4},
            "data_status": "Known",
            "confidence": 0.7,
            "source": "derive:test",
            "updated_at": 1_700_000_000,
        },
        "L11.trade.signal": {  # participates_in_score=False -> exclude
            "value": {"score": 0.9},
            "data_status": "Known",
            "confidence": 0.9,
            "source": "derive:test",
        },
        "L6.mock.pe": {  # mock: source -> exclude
            "value": {"score": 0.5},
            "data_status": "Known",
            "confidence": 0.8,
            "source": "mock:tushare",
        },
        "L6.unknown.metric": {  # data_status Unknown -> exclude
            "value": {"score": 0.5},
            "data_status": "Unknown",
            "confidence": 0.6,
            "source": "derive:test",
        },
        "L6.unmapped.dict": {  # participating but unmapped shape -> skip
            "value": {"ccc_days": 30},
            "data_status": "Known",
            "confidence": 0.6,
            "source": "tushare:x",
        },
        "L6.already.authored": {  # in existing_dp_ids -> exclude (dedupe)
            "value": {"score": 0.5},
            "data_status": "Known",
            "confidence": 0.6,
            "source": "derive:test",
        },
    }


def _full_registry() -> FieldGovernanceRegistry:
    return _registry({
        "L6.derived.sub": _gov("L6.derived.sub", target="fundamental_score"),
        "L11.trade.signal": _gov("L11.trade.signal", target="audit_only", participates=False),
        "L6.mock.pe": _gov("L6.mock.pe", target="valuation_rerating"),
        "L6.unknown.metric": _gov("L6.unknown.metric", target="fundamental_score"),
        "L6.unmapped.dict": _gov("L6.unmapped.dict", target="fundamental_score"),
        "L6.already.authored": _gov("L6.already.authored", target="fundamental_score"),
    })


def test_synthesize_gates_and_dedupes():
    nodes = synthesize_realtime_nodes(
        _full_snapshot(),
        _full_registry(),
        existing_dp_ids={"L6.already.authored"},
        ts_code="300750.SZ",
    )
    emitted = {n["dp_id"] for n in nodes}
    assert emitted == {"L6.derived.sub"}
    assert "L11.trade.signal" not in emitted  # participates_in_score=False
    assert "L6.mock.pe" not in emitted  # mock: source
    assert "L6.unknown.metric" not in emitted  # Unknown status
    assert "L6.unmapped.dict" not in emitted  # normalizer returned None
    assert "L6.already.authored" not in emitted  # deduped vs overlay


def test_synthesize_node_shape_and_direction():
    snap = {
        "L6.pos": {
            "value": {"score": 0.4},
            "data_status": "Known",
            "confidence": 0.7,
            "source": "derive:test",
            "updated_at": 1_700_000_000,
        },
        "L6.neg": {  # high valuation percentile -> negative direction
            "value": {"pe_percentile": 0.95},
            "data_status": "Proxy",
            "confidence": 0.6,
            "source": "tushare:daily",
        },
    }
    reg = _registry({
        "L6.pos": _gov("L6.pos", target="fundamental_score"),
        "L6.neg": _gov("L6.neg", target="valuation_rerating"),
    })
    nodes = {n["dp_id"]: n for n in synthesize_realtime_nodes(
        snap, reg, existing_dp_ids=set(), ts_code="300750.SZ"
    )}

    pos = nodes["L6.pos"]
    assert pos["node_id"] == "300750.SZ:L6.pos:rt"
    assert pos["parent_node"] is None
    assert pos["direction"] == "positive"
    assert pos["value"] == {"score": pytest.approx(0.4)}
    assert pos["data_status"] == "Known"
    assert pos["confidence"] == pytest.approx(0.7)
    assert pos["last_updated"] == 1_700_000_000
    assert pos["synthetic_realtime"] is True

    neg = nodes["L6.neg"]
    assert neg["direction"] == "negative"  # high valuation = drag
    # abs(signal) stored, sign carried by direction.
    assert neg["value"]["score"] == pytest.approx(abs((0.95 - 0.5) * 2.0 * -1.0))


def test_synthesize_returns_empty_without_registry():
    assert synthesize_realtime_nodes(
        _full_snapshot(), None, existing_dp_ids=set(), ts_code="X.SZ"
    ) == []


# ---------------------------------------------------------------------------
# End-to-end: aggregate_company_graph + score_company
# ---------------------------------------------------------------------------


def _minimal_overlay() -> dict:
    """Two authored nodes, both Unknown so they score ~0 on their own.

    Carries governance fields inline (like the real compiled overlays) so
    score_company detects the flat-governance path without a registry arg.
    """

    def node(node_id, dp_id, target):
        return {
            "node_id": node_id,
            "dp_id": dp_id,
            "node_name": node_id,
            "parent_node": None,
            "direction": "positive",
            "base_weight": 1.0,
            "active_weight": 1.0,
            "materiality": 1.0,
            "confidence": 0.5,
            "data_status": "Unknown",
            "status": "Unknown",
            "value": None,
            "field_role": "score_component",
            "score_target": target,
            "participates_in_score": True,
        }

    return {
        "ts_code": "300750.SZ",
        "industry_id": "STORAGE_GRID",
        "nodes": [
            node("auth_fund", "L5.is.eps", "fundamental_score"),
            node("auth_val", "L6.mult.pe", "valuation_rerating"),
        ],
    }


def _bridge_snapshot() -> dict[str, dict]:
    return {
        # Positive derived sub-score -> lifts fundamental_score.
        "L11.long.score": {
            "value": {"score": 0.4},
            "data_status": "Known",
            "confidence": 0.8,
            "source": "derive:l11",
            "updated_at": 1_700_000_000,
        },
        # High valuation percentile -> pushes valuation_rerating NEGATIVE.
        "L6.state.historical_percentile": {
            "value": {"pe_percentile": 0.95, "pb_percentile": 0.9},
            "data_status": "Known",
            "confidence": 0.7,
            "source": "tushare:daily",
            "updated_at": 1_700_000_000,
        },
    }


def _bridge_registry() -> FieldGovernanceRegistry:
    return _registry({
        "L11.long.score": _gov("L11.long.score", target="fundamental_score"),
        "L6.state.historical_percentile": _gov(
            "L6.state.historical_percentile", target="valuation_rerating"
        ),
        # Authored dp_ids — present so dedupe + governance line up.
        "L5.is.eps": _gov("L5.is.eps", target="fundamental_score"),
        "L6.mult.pe": _gov("L6.mult.pe", target="valuation_rerating"),
    })


def test_end_to_end_bridge_lifts_score_off_zero():
    overlay = _minimal_overlay()
    reg = _bridge_registry()
    snap = _bridge_snapshot()

    # Without the bridge: authored nodes are Unknown -> ~0.
    agg_none = aggregate_company_graph(overlay, role_registry=reg, realtime_snapshot=None)
    res_none = score_company(overlay, aggregated_nodes=agg_none)
    assert res_none["short_total"] == pytest.approx(0.0, abs=1e-9)
    assert res_none["medium_total"] == pytest.approx(0.0, abs=1e-9)
    assert res_none["long_total"] == pytest.approx(0.0, abs=1e-9)

    # With the bridge: synthetic realtime leaves drive a non-zero score.
    agg = aggregate_company_graph(overlay, role_registry=reg, realtime_snapshot=snap)
    res = score_company(overlay, aggregated_nodes=agg)
    nonzero = (
        abs(res["short_total"]) + abs(res["medium_total"]) + abs(res["long_total"])
    )
    assert nonzero > 0.0

    # Synthetic nodes exist and carry the right governance + sign.
    val_node = agg["300750.SZ:L6.state.historical_percentile:rt"]
    fund_node = agg["300750.SZ:L11.long.score:rt"]
    assert val_node["score_target"] == "valuation_rerating"
    assert val_node["score"] < 0  # high percentile => negative rerating
    assert fund_node["score_target"] == "fundamental_score"
    assert fund_node["score"] > 0  # positive derived sub-score lifts target


def test_end_to_end_role_components_directions():
    """The valuation percentile drags valuation_rerating negative while the
    positive sub-score lifts fundamental_score positive."""

    from mvp20.scoring import _role_components_from_flat

    overlay = _minimal_overlay()
    reg = _bridge_registry()
    agg = aggregate_company_graph(
        overlay, role_registry=reg, realtime_snapshot=_bridge_snapshot()
    )
    comps = _role_components_from_flat(agg)
    assert comps["valuation_rerating"] < 0
    # fundamental_score isn't a direct role-component key, but it flows into the
    # company score via industry_variables; assert the node sign instead.
    fund_node = agg["300750.SZ:L11.long.score:rt"]
    assert fund_node["score"] > 0


def test_realtime_snapshot_none_is_backcompat():
    """Passing no snapshot must not add any synthetic nodes."""

    overlay = _minimal_overlay()
    reg = _bridge_registry()
    agg = aggregate_company_graph(overlay, role_registry=reg, realtime_snapshot=None)
    assert not any(nid.endswith(":rt") for nid in agg)
    # Only the authored nodes are present.
    assert set(agg) == {"auth_fund", "auth_val"}


def test_confidence_multiplier_node_is_score_neutral():
    """confidence_multiplier-target realtime fields are consumed via confidence
    (scoring._confidence_multiplier_from_flat), NOT a directional score. A
    percentile payload that would otherwise yield a large signed magnitude must
    be synthesized with a NEUTRAL direction / zero score so it cannot pollute
    the top-path ranking — while still being present to contribute confidence.
    A directional target (valuation_rerating) with the same payload keeps its
    signed magnitude."""

    reg = _registry({
        "L10.val.historical_quantile": _gov(
            "L10.val.historical_quantile", target="confidence_multiplier"
        ),
        "L6.path.tag": _gov("L6.path.tag", target="valuation_rerating"),
    })
    snap = {
        "L10.val.historical_quantile": {
            "value": {"pe_percentile": 1.0, "pb_percentile": 0.9},
            "data_status": "Known", "source": "derived:pe_pb_history",
            "confidence": 0.6,
        },
        "L6.path.tag": {
            "value": {"pe_percentile": 1.0}, "data_status": "Known",
            "source": "derive:l6_path_tag", "confidence": 0.5,
        },
    }
    nodes = {
        n["dp_id"]: n
        for n in synthesize_realtime_nodes(
            snap, reg, existing_dp_ids=set(), ts_code="X"
        )
    }

    cm = nodes["L10.val.historical_quantile"]
    assert cm["direction"] == "neutral"
    assert cm["value"]["score"] == 0.0
    assert cm["confidence"] == pytest.approx(0.6)  # confidence preserved

    val = nodes["L6.path.tag"]
    assert val["direction"] == "negative"  # high percentile inverted for valuation
    assert val["value"]["score"] > 0       # magnitude preserved


# ---------------------------------------------------------------------------
# Per-field realtime rules (the 8 governance fields) — unit tests on
# ``_realtime_signal`` + end-to-end DIRECTION tests on the final score.
# ---------------------------------------------------------------------------


# 1. L6.priced.analyst_revision → expectation_gap (additive, signed)


def test_field_analyst_revision_signed_and_clipped():
    assert _realtime_signal(
        "L6.priced.analyst_revision",
        {"net_revision_score": 0.8},
        "expectation_gap",
    ) == pytest.approx(0.8)
    assert _realtime_signal(
        "L6.priced.analyst_revision",
        {"net_revision_score": -0.6},
        "expectation_gap",
    ) == pytest.approx(-0.6)
    # Out-of-range is clipped, not rejected.
    assert _realtime_signal(
        "L6.priced.analyst_revision",
        {"net_revision_score": 2.0},
        "expectation_gap",
    ) == pytest.approx(1.0)
    # Missing key → None.
    assert _realtime_signal(
        "L6.priced.analyst_revision", {"foo": 1}, "expectation_gap"
    ) is None


# 2. L9.company.earnings_guidance → expectation_gap (additive, signed)


def test_field_earnings_guidance_avg_over_100():
    # De-saturated: tanh(avg/100), so +60 → tanh(0.6)≈0.537 (not 0.6, not 1.0).
    sig = _realtime_signal(
        "L9.company.earnings_guidance",
        {"change_pct_min": 40.0, "change_pct_max": 80.0},
        "expectation_gap",
    )
    assert sig == pytest.approx(math.tanh(((40.0 + 80.0) / 2.0) / 100.0))  # tanh(0.6)
    neg = _realtime_signal(
        "L9.company.earnings_guidance",
        {"change_pct_min": -50.0, "change_pct_max": -30.0},
        "expectation_gap",
    )
    assert neg == pytest.approx(math.tanh(-0.4))
    assert neg < 0
    # Either bound missing/None → None.
    assert _realtime_signal(
        "L9.company.earnings_guidance",
        {"change_pct_min": 10.0, "change_pct_max": None},
        "expectation_gap",
    ) is None
    assert _realtime_signal(
        "L9.company.earnings_guidance", {"change_pct_max": 10.0}, "expectation_gap"
    ) is None


# 3. L5.fcst.guidance_change → expectation_gap (additive, signed)


def test_field_guidance_change_direction_and_floor():
    # Real source vocab is upgraded/downgraded; spec also lists up/down.
    # Magnitude is de-saturated: tanh(|current_range_pct|/100), so +50% →
    # tanh(0.5)≈0.462 (not 0.5, not pinned at 1.0).
    up = _realtime_signal(
        "L5.fcst.guidance_change",
        {"change_direction": "upgraded", "current_range_pct": 50.0},
        "expectation_gap",
    )
    assert up == pytest.approx(math.tanh(0.5))
    down = _realtime_signal(
        "L5.fcst.guidance_change",
        {"change_direction": "downgraded", "current_range_pct": 50.0},
        "expectation_gap",
    )
    assert down == pytest.approx(-math.tanh(0.5))
    # "up" alias also works.
    assert _realtime_signal(
        "L5.fcst.guidance_change",
        {"change_direction": "up", "current_range_pct": 50.0},
        "expectation_gap",
    ) == pytest.approx(math.tanh(0.5))
    # Nonzero direction floored at ~0.1 even when the range is tiny
    # (tanh(0.01)≈0.01 < floor → floor wins).
    floored = _realtime_signal(
        "L5.fcst.guidance_change",
        {"change_direction": "upgraded", "current_range_pct": 1.0},
        "expectation_gap",
    )
    assert floored == pytest.approx(0.1)
    # unchanged → 0.0 (not None).
    assert _realtime_signal(
        "L5.fcst.guidance_change",
        {"change_direction": "unchanged", "current_range_pct": 20.0},
        "expectation_gap",
    ) == pytest.approx(0.0)
    # Unknown direction ("new") → None.
    assert _realtime_signal(
        "L5.fcst.guidance_change",
        {"change_direction": "new", "current_range_pct": 20.0},
        "expectation_gap",
    ) is None
    # Missing direction → None.
    assert _realtime_signal(
        "L5.fcst.guidance_change", {"current_range_pct": 20.0}, "expectation_gap"
    ) is None


# 4. L7.mood.analyst_rating → sentiment_score (additive, signed)


def test_field_analyst_rating_recentered_on_consensus():
    # A-share ratings cluster near the top (universe mean 4.63), so the rule
    # re-centers on the consensus: signal = clip((avg - 4.63) / 0.46, -1, 1).
    # Above-consensus → positive, consensus → 0, below-consensus → negative.
    # 5.0 → (5.0-4.63)/0.46 ≈ +0.804.
    assert _realtime_signal(
        "L7.mood.analyst_rating", {"avg_rating_score": 5.0}, "sentiment_score"
    ) == pytest.approx(0.804, abs=1e-3)
    # 4.63 (= universe mean) → exactly neutral.
    assert _realtime_signal(
        "L7.mood.analyst_rating", {"avg_rating_score": 4.63}, "sentiment_score"
    ) == pytest.approx(0.0)
    # 4.5 (modal bucket) is just below consensus → mildly negative.
    assert _realtime_signal(
        "L7.mood.analyst_rating", {"avg_rating_score": 4.5}, "sentiment_score"
    ) == pytest.approx((4.5 - 4.63) / 0.46)
    # 4.0 is > 1σ below consensus → clips at -1.0.
    assert _realtime_signal(
        "L7.mood.analyst_rating", {"avg_rating_score": 4.0}, "sentiment_score"
    ) == pytest.approx(-1.0)
    # Missing key → None (unchanged).
    assert _realtime_signal(
        "L7.mood.analyst_rating", {"n_reports": 5}, "sentiment_score"
    ) is None


# 5. L6.state.expansion_compression → valuation_rerating (additive, signed)


def test_field_expansion_compression_expensive_is_negative():
    rich = _realtime_signal(
        "L6.state.expansion_compression",
        {"ratio_vs_250d": 1.4, "regime": "expanded"},
        "valuation_rerating",
    )
    assert rich == pytest.approx(-math.tanh((1.4 - 1.0) * 2.0))
    assert rich < 0  # expanded / expensive must drag the score down
    cheap = _realtime_signal(
        "L6.state.expansion_compression",
        {"ratio_vs_250d": 0.7, "regime": "compressed"},
        "valuation_rerating",
    )
    assert cheap == pytest.approx(-math.tanh((0.7 - 1.0) * 2.0))
    assert cheap > 0
    # ratio at 1.0 → neutral.
    assert _realtime_signal(
        "L6.state.expansion_compression",
        {"ratio_vs_250d": 1.0},
        "valuation_rerating",
    ) == pytest.approx(0.0)
    # ratio missing → fall back to regime.
    assert _realtime_signal(
        "L6.state.expansion_compression",
        {"regime": "expanded"},
        "valuation_rerating",
    ) == pytest.approx(-0.5)
    assert _realtime_signal(
        "L6.state.expansion_compression",
        {"regime": "compressed"},
        "valuation_rerating",
    ) == pytest.approx(0.5)
    # No ratio + no regime → None.
    assert _realtime_signal(
        "L6.state.expansion_compression", {"slope": 0.1}, "valuation_rerating"
    ) is None


# 6. L8.val.overvalued → risk_discount (magnitude, sign ignored downstream)


def test_field_overvalued_magnitude():
    sig = _realtime_signal(
        "L8.val.overvalued",
        {"max_quantile": 0.95, "severity": "high"},
        "risk_discount",
    )
    # FU-1 (A): overvalued's risk-side contribution is scaled to HALF — the same
    # PE/PB percentile already drives valuation_rerating, so 0.95 → 0.475.
    assert sig == pytest.approx(0.475)
    assert sig >= 0
    # Clip to [0, 1] BEFORE the 0.5 scale → 1.4 clips to 1.0, then ×0.5 = 0.5.
    assert _realtime_signal(
        "L8.val.overvalued", {"max_quantile": 1.4}, "risk_discount"
    ) == pytest.approx(0.5)
    # Missing key → None.
    assert _realtime_signal(
        "L8.val.overvalued", {"severity": "high"}, "risk_discount"
    ) is None


# 7. L8.val.priced_in → risk_discount (magnitude)


def test_field_priced_in_magnitude():
    assert _realtime_signal(
        "L8.val.priced_in", {"priced_in_score": 0.7}, "risk_discount"
    ) == pytest.approx(0.7)
    assert _realtime_signal(
        "L8.val.priced_in", {"priced_in_score": 1.5}, "risk_discount"
    ) == pytest.approx(1.0)
    # Missing key → None.
    assert _realtime_signal(
        "L8.val.priced_in", {"foo": 1}, "risk_discount"
    ) is None


# 8. L6.priced.run_up → priced_in_discount (magnitude; only a run-UP counts)


def test_field_run_up_only_counts_upside():
    # +18% over 20d → 0.18 / 0.20 = 0.9 magnitude.
    sig = _realtime_signal(
        "L6.priced.run_up",
        {"d20_pct": 0.18, "d5_pct": 0.05, "d60_pct": 0.3},
        "priced_in_discount",
    )
    assert sig == pytest.approx(0.18 / 0.20)
    # Saturates at 1.0 for >= +20%.
    assert _realtime_signal(
        "L6.priced.run_up", {"d20_pct": 0.5}, "priced_in_discount"
    ) == pytest.approx(1.0)
    # A DECLINE must NOT count as priced-in → 0 magnitude.
    assert _realtime_signal(
        "L6.priced.run_up", {"d20_pct": -0.1}, "priced_in_discount"
    ) == pytest.approx(0.0)
    # d20 missing → fall back to d5.
    assert _realtime_signal(
        "L6.priced.run_up", {"d20_pct": None, "d5_pct": 0.1}, "priced_in_discount"
    ) == pytest.approx(0.1 / 0.20)
    # All None → None.
    assert _realtime_signal(
        "L6.priced.run_up",
        {"d20_pct": None, "d5_pct": None, "d60_pct": None},
        "priced_in_discount",
    ) is None


# 9. L5.bs.leverage → fundamental_score (additive, signed; higher debt = worse)


def test_field_leverage_higher_debt_is_negative():
    # 0.5 is neutral; 1.0 → -clip(0.5*1.5)= -0.75; 0.2 → -clip(-0.3*1.5)= +0.45.
    assert _realtime_signal(
        "L5.bs.leverage", {"leverage_ratio": 1.0}, "fundamental_score"
    ) == pytest.approx(-0.75)
    assert _realtime_signal(
        "L5.bs.leverage", {"leverage_ratio": 1.0}, "fundamental_score"
    ) < 0
    assert _realtime_signal(
        "L5.bs.leverage", {"leverage_ratio": 0.2}, "fundamental_score"
    ) == pytest.approx(0.45)
    assert _realtime_signal(
        "L5.bs.leverage", {"leverage_ratio": 0.2}, "fundamental_score"
    ) > 0
    # 0.5 → exactly neutral.
    assert _realtime_signal(
        "L5.bs.leverage", {"leverage_ratio": 0.5}, "fundamental_score"
    ) == pytest.approx(0.0)
    # Saturates: very high leverage clips at -1.0.
    assert _realtime_signal(
        "L5.bs.leverage", {"leverage_ratio": 2.0}, "fundamental_score"
    ) == pytest.approx(-1.0)
    # Missing key → None.
    assert _realtime_signal(
        "L5.bs.leverage", {"foo": 1}, "fundamental_score"
    ) is None


# 10. L5.bs.goodwill_ppe → fundamental_score (additive, signed; goodwill = risk)


def test_field_goodwill_higher_is_strongly_negative():
    # 0.4 → -clip(0.4*2.5)= -1.0 (strongly negative); 0.0 → 0.
    assert _realtime_signal(
        "L5.bs.goodwill_ppe", {"goodwill_to_assets": 0.4}, "fundamental_score"
    ) == pytest.approx(-1.0)
    assert _realtime_signal(
        "L5.bs.goodwill_ppe", {"goodwill_to_assets": 0.0}, "fundamental_score"
    ) == pytest.approx(0.0)
    # A small goodwill share is mildly negative (0.1 → -0.25).
    assert _realtime_signal(
        "L5.bs.goodwill_ppe", {"goodwill_to_assets": 0.1}, "fundamental_score"
    ) == pytest.approx(-0.25)
    # Missing key → None.
    assert _realtime_signal(
        "L5.bs.goodwill_ppe", {"ppe_to_assets": 0.3}, "fundamental_score"
    ) is None


# ---------------------------------------------------------------------------
# Company-fundamental-QUALITY fields (5) → fundamental_score (additive, signed).
# Cross-sectional re-center clip((value - MEDIAN) / SCALE, -1, 1) vs the
# A-share universe; direction per field. (Industry-mixing caveat lives on the
# constants block in aggregator.py.)
# ---------------------------------------------------------------------------


# 11. L5.is.gross_margin → fundamental_score (higher margin = better → POSITIVE)


def test_field_gross_margin_higher_is_positive():
    # ASYMMETRIC re-center (M-2 fix): clip(delta/scale, -1, 1) where delta =
    # gm - 0.29, scale = 0.22 above the median (POSITIVE side unchanged) and a
    # WIDER 0.35 below it, so a structurally thin (single-digit) margin reads
    # moderately negative instead of flooring at -1.0, while a genuinely
    # collapsed margin still approaches -1.0.
    # --- Positive side: unchanged from the symmetric scale ---
    # 0.51 → (0.51-0.29)/0.22 = 1.0 (saturates positive).
    assert _realtime_signal(
        "L5.is.gross_margin", {"scalar": 0.51}, "fundamental_score"
    ) == pytest.approx(1.0)
    assert _realtime_signal(
        "L5.is.gross_margin", {"scalar": 0.51}, "fundamental_score"
    ) > 0
    # 0.40 → (0.40-0.29)/0.22 = +0.5 (above median, un-saturated).
    assert _realtime_signal(
        "L5.is.gross_margin", {"scalar": 0.40}, "fundamental_score"
    ) == pytest.approx((0.40 - 0.29) / 0.22)
    # --- Negative side: wider 0.35 scale (M-2). ---
    # 0.10 → (0.10-0.29)/0.35 ≈ -0.543 (below median → negative, but NOT floored).
    assert _realtime_signal(
        "L5.is.gross_margin", {"scalar": 0.10}, "fundamental_score"
    ) == pytest.approx((0.10 - 0.29) / 0.35)
    assert _realtime_signal(
        "L5.is.gross_margin", {"scalar": 0.10}, "fundamental_score"
    ) < 0
    # Structurally thin EMS/代工 margin (~7%) is moderately negative, NOT pinned
    # at -1.0 (the bug M-2 fixes; previously (0.07-0.29)/0.22 = -1.0).
    thin = _realtime_signal(
        "L5.is.gross_margin", {"scalar": 0.07}, "fundamental_score"
    )
    assert thin == pytest.approx((0.07 - 0.29) / 0.35)
    assert -0.8 < thin < -0.4
    # A genuinely collapsed / negative gross margin still saturates to -1.0
    # (direction stays negative — the asymmetry must NOT rescue a real loss).
    assert _realtime_signal(
        "L5.is.gross_margin", {"scalar": -0.10}, "fundamental_score"
    ) == pytest.approx(-1.0)
    # At the median → exactly neutral.
    assert _realtime_signal(
        "L5.is.gross_margin", {"scalar": 0.29}, "fundamental_score"
    ) == pytest.approx(0.0)
    # Missing / None / non-numeric metric key → None.
    assert _realtime_signal(
        "L5.is.gross_margin", {"net": 0.2}, "fundamental_score"
    ) is None
    assert _realtime_signal(
        "L5.is.gross_margin", {"scalar": None}, "fundamental_score"
    ) is None


# 12. L5.is.margins → fundamental_score (higher net margin = better → POSITIVE)


def test_field_net_margins_higher_is_positive():
    # clip((nm - 0.12) / 0.16, -1, 1) — uses the ``net`` key (not operating).
    # 0.20 → (0.20-0.12)/0.16 = +0.5 (above median → positive).
    assert _realtime_signal(
        "L5.is.margins", {"net": 0.20, "operating": 0.05}, "fundamental_score"
    ) == pytest.approx((0.20 - 0.12) / 0.16)
    assert _realtime_signal(
        "L5.is.margins", {"net": 0.20}, "fundamental_score"
    ) > 0
    # 0.02 → (0.02-0.12)/0.16 = -0.625 (below median → negative).
    assert _realtime_signal(
        "L5.is.margins", {"net": 0.02}, "fundamental_score"
    ) == pytest.approx((0.02 - 0.12) / 0.16)
    assert _realtime_signal(
        "L5.is.margins", {"net": 0.02}, "fundamental_score"
    ) < 0
    # At the median → neutral.
    assert _realtime_signal(
        "L5.is.margins", {"net": 0.12}, "fundamental_score"
    ) == pytest.approx(0.0)
    # ``operating`` present but ``net`` missing → None (must read the net key).
    assert _realtime_signal(
        "L5.is.margins", {"operating": 0.25}, "fundamental_score"
    ) is None
    assert _realtime_signal(
        "L5.is.margins", {"net": None}, "fundamental_score"
    ) is None


# 13. L4.eff.cycle → fundamental_score (lower cash-cycle = better → INVERSE)


def test_field_cycle_lower_ccc_is_positive():
    # -clip((ccc - 36.0) / 100.0, -1, 1) — high cycle is BAD → negative.
    # 136 → -clip((136-36)/100) = -1.0 (slow cycle saturates negative).
    assert _realtime_signal(
        "L4.eff.cycle", {"ccc_days": 136.0}, "fundamental_score"
    ) == pytest.approx(-1.0)
    assert _realtime_signal(
        "L4.eff.cycle", {"ccc_days": 136.0}, "fundamental_score"
    ) < 0  # high cycle is bad
    # 86 → -clip((86-36)/100) = -0.5 (above median → still negative, un-saturated).
    assert _realtime_signal(
        "L4.eff.cycle", {"ccc_days": 86.0}, "fundamental_score"
    ) == pytest.approx(-(86.0 - 36.0) / 100.0)
    # 16 → -clip((16-36)/100) = +0.2 (below median → positive).
    assert _realtime_signal(
        "L4.eff.cycle", {"ccc_days": 16.0}, "fundamental_score"
    ) == pytest.approx(-(16.0 - 36.0) / 100.0)
    assert _realtime_signal(
        "L4.eff.cycle", {"ccc_days": 16.0}, "fundamental_score"
    ) > 0
    # At the median → neutral.
    assert _realtime_signal(
        "L4.eff.cycle", {"ccc_days": 36.0}, "fundamental_score"
    ) == pytest.approx(0.0)
    # Missing / non-numeric → None.
    assert _realtime_signal(
        "L4.eff.cycle", {"days": 30}, "fundamental_score"
    ) is None
    assert _realtime_signal(
        "L4.eff.cycle", {"ccc_days": "slow"}, "fundamental_score"
    ) is None


# 14. L4.eff.turnover → fundamental_score (lower inventory days = better → INVERSE)


def test_field_turnover_lower_days_is_positive():
    # -clip((td - 96.0) / 120.0, -1, 1) — high inventory days is BAD → negative.
    # 216 → -clip((216-96)/120) = -1.0 (saturates negative).
    assert _realtime_signal(
        "L4.eff.turnover", {"inventory_turnover_days": 216.0}, "fundamental_score"
    ) == pytest.approx(-1.0)
    assert _realtime_signal(
        "L4.eff.turnover", {"inventory_turnover_days": 216.0}, "fundamental_score"
    ) < 0  # slow turnover is bad
    # 156 → -clip((156-96)/120) = -0.5 (above median → negative, un-saturated).
    assert _realtime_signal(
        "L4.eff.turnover", {"inventory_turnover_days": 156.0}, "fundamental_score"
    ) == pytest.approx(-(156.0 - 96.0) / 120.0)
    # 36 → -clip((36-96)/120) = +0.5 (below median → positive).
    assert _realtime_signal(
        "L4.eff.turnover", {"inventory_turnover_days": 36.0}, "fundamental_score"
    ) == pytest.approx(-(36.0 - 96.0) / 120.0)
    assert _realtime_signal(
        "L4.eff.turnover", {"inventory_turnover_days": 36.0}, "fundamental_score"
    ) > 0
    # At the median → neutral.
    assert _realtime_signal(
        "L4.eff.turnover", {"inventory_turnover_days": 96.0}, "fundamental_score"
    ) == pytest.approx(0.0)
    # Missing key → None.
    assert _realtime_signal(
        "L4.eff.turnover", {"turnover_ratio": 4.0}, "fundamental_score"
    ) is None


# 15. L4.cost.labor → fundamental_score (cost UP = bad → NEGATIVE; self-contained)


def test_field_labor_cost_up_is_negative():
    # -clip(tanh(yoy / 5.0), -1, 1). Cost rising → negative; falling → positive.
    # +10% → -tanh(2.0) ≈ -0.964 (above 0 / rising cost → negative).
    assert _realtime_signal(
        "L4.cost.labor", {"labor_cost_yoy_pct": 10.0}, "fundamental_score"
    ) == pytest.approx(-math.tanh(10.0 / 5.0))
    assert _realtime_signal(
        "L4.cost.labor", {"labor_cost_yoy_pct": 10.0}, "fundamental_score"
    ) < 0  # rising labor cost drags fundamental down
    # -10% → -tanh(-2.0) ≈ +0.964 (falling cost → positive).
    assert _realtime_signal(
        "L4.cost.labor", {"labor_cost_yoy_pct": -10.0}, "fundamental_score"
    ) == pytest.approx(-math.tanh(-10.0 / 5.0))
    assert _realtime_signal(
        "L4.cost.labor", {"labor_cost_yoy_pct": -10.0}, "fundamental_score"
    ) > 0
    # 0% yoy → neutral.
    assert _realtime_signal(
        "L4.cost.labor", {"labor_cost_yoy_pct": 0.0}, "fundamental_score"
    ) == pytest.approx(0.0)
    # Missing key → None.
    assert _realtime_signal(
        "L4.cost.labor", {"labor_cost": 1000.0}, "fundamental_score"
    ) is None


# ---------------------------------------------------------------------------
# End-to-end: a high-quality fundamental snapshot (high margins, fast cash
# cycle, falling labor cost) yields a POSITIVE fundamental contribution to the
# company score; a low-quality one (thin margins, slow cycle, rising cost)
# yields a negative contribution. Routes through the dead-sink industry_contrib.
# ---------------------------------------------------------------------------


def _quality_snapshot(*, high: bool) -> dict[str, dict]:
    """Five fundamental-quality fields for one company, all Known, all
    targeting fundamental_score. ``high`` picks a best-in-class vs a
    worst-in-class profile."""

    if high:
        payloads = {
            "L5.is.gross_margin": {"scalar": 0.55},          # rich gross margin
            "L5.is.margins": {"net": 0.30, "operating": 0.35},  # rich net margin
            "L4.eff.cycle": {"ccc_days": -40.0},             # negative cash cycle
            "L4.eff.turnover": {"inventory_turnover_days": 20.0},  # fast turnover
            "L4.cost.labor": {"labor_cost_yoy_pct": -8.0},   # labor cost falling
        }
    else:
        payloads = {
            "L5.is.gross_margin": {"scalar": 0.05},          # thin gross margin
            "L5.is.margins": {"net": -0.05, "operating": 0.01},  # loss-making
            "L4.eff.cycle": {"ccc_days": 160.0},             # very slow cash cycle
            "L4.eff.turnover": {"inventory_turnover_days": 240.0},  # slow turnover
            "L4.cost.labor": {"labor_cost_yoy_pct": 12.0},   # labor cost surging
        }
    return {
        dp_id: {
            "value": payload,
            "data_status": "Known",
            "confidence": 1.0,
            "source": "tushare:test",
            "updated_at": 1_700_000_000,
        }
        for dp_id, payload in payloads.items()
    }


def _quality_registry() -> FieldGovernanceRegistry:
    return _registry({
        "L5.is.eps": _gov("L5.is.eps", target="fundamental_score"),
        "L5.is.gross_margin": _gov("L5.is.gross_margin", target="fundamental_score"),
        "L5.is.margins": _gov("L5.is.margins", target="fundamental_score"),
        "L4.eff.cycle": _gov("L4.eff.cycle", target="fundamental_score"),
        "L4.eff.turnover": _gov("L4.eff.turnover", target="fundamental_score"),
        "L4.cost.labor": _gov("L4.cost.labor", target="fundamental_score"),
    })


def test_e2e_quality_fundamentals_drive_contribution_sign():
    """High-quality fundamentals → positive industry_contrib (and base_score);
    low-quality → negative. The 5 new fields all route through the dead-sink
    fundamental_score path collapsed into ``realtime_fundamental``."""

    overlay = _deadsink_overlay()  # one Unknown fundamental seed → base ~0 alone
    reg = _quality_registry()

    agg_hi = aggregate_company_graph(
        overlay, role_registry=reg, realtime_snapshot=_quality_snapshot(high=True)
    )
    res_hi = score_company(overlay, aggregated_nodes=agg_hi)
    contrib_hi = res_hi["company_score"]["components"]["industry_contrib"]
    base_hi = res_hi["core_final_score"]["base_score"]

    agg_lo = aggregate_company_graph(
        overlay, role_registry=reg, realtime_snapshot=_quality_snapshot(high=False)
    )
    res_lo = score_company(overlay, aggregated_nodes=agg_lo)
    contrib_lo = res_lo["company_score"]["components"]["industry_contrib"]
    base_lo = res_lo["core_final_score"]["base_score"]

    assert contrib_hi > 0  # rich margins + fast cycle + falling cost lift it
    assert contrib_lo < 0  # thin margins + slow cycle + rising cost drag it
    assert contrib_hi > contrib_lo
    assert base_hi > base_lo


# ---------------------------------------------------------------------------
# Dead-sink routing: a synthetic ``fundamental_score`` node must now INCREASE
# the company score (was a dead sink — moved base_score by +0.000), while a
# synthetic live-sink target (valuation_rerating) keeps counting EXACTLY ONCE
# via the flat sink and is NOT also routed through industry_variables.
# ---------------------------------------------------------------------------


def _deadsink_overlay() -> dict:
    """One authored Unknown seed (score ~0) so any non-zero base score comes
    entirely from the synthetic realtime node under test."""

    return {
        "ts_code": "300750.SZ",
        "industry_id": "STORAGE_GRID",
        "nodes": [
            {
                "node_id": "auth_seed",
                "dp_id": "L5.is.eps",
                "node_name": "auth_seed",
                "parent_node": None,
                "direction": "positive",
                "base_weight": 1.0,
                "active_weight": 1.0,
                "materiality": 1.0,
                "confidence": 0.5,
                "data_status": "Unknown",
                "status": "Unknown",
                "value": None,
                "field_role": "score_component",
                "score_target": "fundamental_score",
                "participates_in_score": True,
            }
        ],
    }


def test_fundamental_synthetic_node_now_increases_score():
    """Replicates the verified dead-sink: a synthetic ``fundamental_score``
    Known node (score 0.9) used to move base_score by +0.000. After routing
    dead-sink synthetic nodes through industry_contrib it INCREASES the score
    and shows up in the industry-variable contributions."""

    from mvp20.scoring import _industry_variables_from_flat

    overlay = _deadsink_overlay()
    reg = _registry({
        "L5.is.eps": _gov("L5.is.eps", target="fundamental_score"),
        "L6.fund.metric": _gov("L6.fund.metric", target="fundamental_score"),
    })
    snap = {
        "L6.fund.metric": {
            "value": {"score": 0.9},
            "data_status": "Known",
            "confidence": 1.0,
            "source": "derive:fund",
            "updated_at": 1_700_000_000,
        }
    }
    agg = aggregate_company_graph(overlay, role_registry=reg, realtime_snapshot=snap)

    # Flag survives aggregation so scoring can detect the synthetic origin.
    synth = agg["300750.SZ:L6.fund.metric:rt"]
    assert synth["synthetic_realtime"] is True
    assert synth["score_target"] == "fundamental_score"
    assert synth["score"] == pytest.approx(0.9)

    res = score_company(overlay, aggregated_nodes=agg)
    base = res["core_final_score"]["base_score"]
    contrib = res["company_score"]["components"]["industry_contrib"]
    # Was +0.000; now the full +0.9 reaches the score via industry_contrib.
    # Single synthetic node: damped mean = Σ(0.9×1.0)/max(1.0, 1.0) = 0.9
    # (Σconf=1.0 → floor=1.0 → unchanged from the raw signed score).
    assert base == pytest.approx(0.9)
    assert contrib == pytest.approx(0.9)

    # Synthetic dead-sink nodes are now collapsed into a SINGLE damped-mean
    # industry variable named "realtime_fundamental" (no longer one var per
    # node_id), so its score is the collapsed 0.9.
    ivars = _industry_variables_from_flat(agg, overlay)
    rt = [v for v in ivars if v["node_id"] == "realtime_fundamental"]
    assert len(rt) == 1
    assert rt[0]["score"] == pytest.approx(0.9)


def test_optionality_synthetic_node_routes_through_industry():
    """``optionality_score`` is the other dead-sink target (no flat sink); it
    must also reach the score via industry_contrib."""

    overlay = _deadsink_overlay()
    reg = _registry({
        "L5.is.eps": _gov("L5.is.eps", target="fundamental_score"),
        "L2.opt.newbiz": _gov("L2.opt.newbiz", target="optionality_score"),
    })
    snap = {
        "L2.opt.newbiz": {
            "value": {"score": 0.6},
            "data_status": "Known",
            "confidence": 1.0,
            "source": "derive:opt",
            "updated_at": 1_700_000_000,
        }
    }
    agg = aggregate_company_graph(overlay, role_registry=reg, realtime_snapshot=snap)
    res = score_company(overlay, aggregated_nodes=agg)
    assert res["company_score"]["components"]["industry_contrib"] == pytest.approx(0.6)
    assert res["core_final_score"]["base_score"] == pytest.approx(0.6)


def test_valuation_synthetic_node_counts_once_no_double_count():
    """A synthetic ``valuation_rerating`` node already has a flat sink in
    _role_components_from_flat (path #1). It must NOT be routed a second time
    through industry_variables — assert (a) it is absent from the industry-
    variable output, (b) industry_contrib stays 0, and (c) base_score equals
    the single flat-sink contribution only."""

    from mvp20.scoring import _industry_variables_from_flat

    overlay = _deadsink_overlay()
    reg = _registry({
        "L5.is.eps": _gov("L5.is.eps", target="fundamental_score"),
        "L6.val.pct": _gov("L6.val.pct", target="valuation_rerating"),
    })
    snap = {
        "L6.val.pct": {
            "value": {"pe_percentile": 0.95},
            "data_status": "Known",
            "confidence": 1.0,
            "source": "tushare:daily",
            "updated_at": 1_700_000_000,
        }
    }
    agg = aggregate_company_graph(overlay, role_registry=reg, realtime_snapshot=snap)

    # (a) Not present in the industry-variable contributions.
    ivars = _industry_variables_from_flat(agg, overlay)
    assert not any(
        str(v["node_id"]).endswith("L6.val.pct:rt") for v in ivars
    )

    res = score_company(overlay, aggregated_nodes=agg)
    # (b) industry_contrib unchanged by the valuation node.
    assert res["company_score"]["components"]["industry_contrib"] == pytest.approx(0.0)

    # (c) Single-count: the node's signal is (0.95-0.5)*2*-1 = -0.9; it lands
    # ONLY via the valuation_rerating flat sink, so base_score == -0.9, not -1.8.
    expected_single = (0.95 - 0.5) * 2.0 * -1.0
    assert res["role_components"]["valuation_rerating"] == pytest.approx(expected_single)
    assert res["core_final_score"]["base_score"] == pytest.approx(expected_single)


def test_e2e_leverage_and_goodwill_drag_fundamental_via_bridge():
    """End-to-end: high leverage and high goodwill (both fundamental_score)
    now reach the score through the dead-sink route and drag it negative,
    while a clean balance sheet stays neutral/positive."""

    heavy_lev = _base_score_for(
        "L5.bs.leverage", "fundamental_score", {"leverage_ratio": 1.0}
    )
    light_lev = _base_score_for(
        "L5.bs.leverage", "fundamental_score", {"leverage_ratio": 0.2}
    )
    assert heavy_lev < light_lev
    assert heavy_lev < 0  # high leverage drags fundamental negative

    high_gw = _base_score_for(
        "L5.bs.goodwill_ppe", "fundamental_score", {"goodwill_to_assets": 0.4}
    )
    no_gw = _base_score_for(
        "L5.bs.goodwill_ppe", "fundamental_score", {"goodwill_to_assets": 0.0}
    )
    assert high_gw < no_gw
    assert no_gw == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# End-to-end DIRECTION tests: a realtime snapshot for one field must move the
# final ``base_score`` in the expected direction (additive: sign; discount:
# more magnitude → lower). We compare two snapshots through the real
# aggregate_company_graph + score_company path.
# ---------------------------------------------------------------------------


def _field_overlay(dp_id: str, target: str) -> dict:
    """Minimal governance-flat overlay carrying ONE authored Unknown node so
    the base score is ~0 until the realtime snapshot injects the field."""

    return {
        "ts_code": "300750.SZ",
        "industry_id": "STORAGE_GRID",
        "nodes": [
            {
                "node_id": "auth_seed",
                "dp_id": "L5.is.eps",
                "node_name": "auth_seed",
                "parent_node": None,
                "direction": "positive",
                "base_weight": 1.0,
                "active_weight": 1.0,
                "materiality": 1.0,
                "confidence": 0.5,
                "data_status": "Unknown",
                "status": "Unknown",
                "value": None,
                "field_role": "score_component",
                "score_target": "fundamental_score",
                "participates_in_score": True,
            }
        ],
    }


def _base_score_for(dp_id: str, target: str, payload: dict) -> float:
    """Run the full bridge for a single realtime field and return base_score."""

    overlay = _field_overlay(dp_id, target)
    reg = _registry({
        dp_id: _gov(dp_id, target=target),
        "L5.is.eps": _gov("L5.is.eps", target="fundamental_score"),
    })
    snap = {
        dp_id: {
            "value": payload,
            "data_status": "Known",
            "confidence": 1.0,
            "source": "tushare:test",
            "updated_at": 1_700_000_000,
        }
    }
    agg = aggregate_company_graph(overlay, role_registry=reg, realtime_snapshot=snap)
    res = score_company(overlay, aggregated_nodes=agg)
    # ``base_score`` is the unweighted ``f + e + vr + cs - r - p`` sum; read it
    # from the pre-market-adapter core score so the comparison isolates the
    # field's contribution (no regime multiplier in the way).
    return res["core_final_score"]["base_score"]


def test_e2e_analyst_revision_up_beats_down():
    up = _base_score_for(
        "L6.priced.analyst_revision",
        "expectation_gap",
        {"net_revision_score": 0.8},
    )
    down = _base_score_for(
        "L6.priced.analyst_revision",
        "expectation_gap",
        {"net_revision_score": -0.8},
    )
    assert up > down


def test_e2e_earnings_guidance_beat_beats_miss():
    beat = _base_score_for(
        "L9.company.earnings_guidance",
        "expectation_gap",
        {"change_pct_min": 50.0, "change_pct_max": 70.0},  # 预增 ~ +60
    )
    miss = _base_score_for(
        "L9.company.earnings_guidance",
        "expectation_gap",
        {"change_pct_min": -50.0, "change_pct_max": -30.0},  # 预减 ~ -40
    )
    assert beat > miss


def test_e2e_guidance_change_up_beats_down():
    up = _base_score_for(
        "L5.fcst.guidance_change",
        "expectation_gap",
        {"change_direction": "upgraded", "current_range_pct": 50.0},
    )
    down = _base_score_for(
        "L5.fcst.guidance_change",
        "expectation_gap",
        {"change_direction": "downgraded", "current_range_pct": 50.0},
    )
    assert up > down


def test_e2e_analyst_rating_buy_beats_sell():
    # Re-centered on the A-share consensus (mean 4.63): a top rating still beats
    # a rock-bottom one, but a CONSENSUS-rated (4.63) name now contributes ~0 to
    # sentiment — not the old uniform +0.8 every stock used to get.
    strong_buy = _base_score_for(
        "L7.mood.analyst_rating", "sentiment_score", {"avg_rating_score": 5.0}
    )
    strong_sell = _base_score_for(
        "L7.mood.analyst_rating", "sentiment_score", {"avg_rating_score": 1.0}
    )
    consensus = _base_score_for(
        "L7.mood.analyst_rating", "sentiment_score", {"avg_rating_score": 4.63}
    )
    assert strong_buy > strong_sell
    assert strong_buy > consensus  # above-consensus rated higher than consensus
    assert consensus == pytest.approx(0.0, abs=1e-9)  # average rating → ~0 sentiment


def test_e2e_expansion_compression_expensive_lowers_score():
    expensive = _base_score_for(
        "L6.state.expansion_compression",
        "valuation_rerating",
        {"ratio_vs_250d": 1.4, "regime": "expanded"},
    )
    cheap = _base_score_for(
        "L6.state.expansion_compression",
        "valuation_rerating",
        {"ratio_vs_250d": 0.7, "regime": "compressed"},
    )
    assert expensive < cheap


def test_e2e_overvalued_higher_quantile_lowers_score():
    very = _base_score_for(
        "L8.val.overvalued", "risk_discount", {"max_quantile": 0.95}
    )
    not_ov = _base_score_for(
        "L8.val.overvalued", "risk_discount", {"max_quantile": 0.0}
    )
    assert very < not_ov


def test_e2e_priced_in_higher_lowers_score():
    high = _base_score_for(
        "L8.val.priced_in", "risk_discount", {"priced_in_score": 0.9}
    )
    low = _base_score_for(
        "L8.val.priced_in", "risk_discount", {"priced_in_score": 0.0}
    )
    assert high < low


def test_e2e_run_up_lowers_score_decline_neutral():
    run_up = _base_score_for(
        "L6.priced.run_up", "priced_in_discount", {"d20_pct": 0.18}
    )
    flat = _base_score_for(
        "L6.priced.run_up", "priced_in_discount", {"d20_pct": 0.0}
    )
    # A run-up is priced in → subtracts → lower than no run-up.
    assert run_up < flat
    # A decline is NOT priced in → same as flat (magnitude 0).
    decline = _base_score_for(
        "L6.priced.run_up", "priced_in_discount", {"d20_pct": -0.1}
    )
    assert decline == pytest.approx(flat)


# ---------------------------------------------------------------------------
# Same-disclosure dedup + de-saturation for the 业绩预告 guidance pair.
# ``L9.company.earnings_guidance`` (LEVEL) and ``L5.fcst.guidance_change``
# (REVISION) both target expectation_gap off the SAME forecast; emitting both
# double-counts, and both used to pin at 1.0 for a strong forecast.
# ---------------------------------------------------------------------------

# BYD-like strong forecast: avg change_pct ≈ +102%, current_range_pct ≈ +102%.
_BYD_EARNINGS_GUIDANCE = {"change_pct_min": 86.0, "change_pct_max": 118.0}
_BYD_GUIDANCE_CHANGE = {"change_direction": "upgraded", "current_range_pct": 102.0}


def _guidance_pair_registry() -> FieldGovernanceRegistry:
    return _registry({
        "L9.company.earnings_guidance": _gov(
            "L9.company.earnings_guidance", target="expectation_gap"
        ),
        "L5.fcst.guidance_change": _gov(
            "L5.fcst.guidance_change", target="expectation_gap"
        ),
    })


def _guidance_entry(value: dict, *, source: str = "tushare:forecast",
                    data_status: str = "Known") -> dict:
    return {
        "value": value,
        "data_status": data_status,
        "confidence": 0.85,
        "source": source,
        "updated_at": 1_700_000_000,
    }


def test_guidance_desaturation_not_pinned():
    # LEVEL: avg = (86+118)/2 = 102 → tanh(1.02) ≈ 0.77, strictly < 1.0.
    lvl = _realtime_signal(
        "L9.company.earnings_guidance", _BYD_EARNINGS_GUIDANCE, "expectation_gap"
    )
    assert lvl == pytest.approx(math.tanh(1.02))
    assert lvl < 1.0
    # REVISION: current_range_pct = 102 → tanh(1.02) ≈ 0.77, strictly < 1.0.
    rev = _realtime_signal(
        "L5.fcst.guidance_change",
        {"current_range_pct": 102.0, "change_direction": "upgraded"},
        "expectation_gap",
    )
    assert rev == pytest.approx(math.tanh(1.02))
    assert rev < 1.0


def test_guidance_change_downgraded_is_negative():
    down = _realtime_signal(
        "L5.fcst.guidance_change",
        {"change_direction": "downgraded", "current_range_pct": 102.0},
        "expectation_gap",
    )
    assert down == pytest.approx(-math.tanh(1.02))
    assert down < 0


def test_dedup_revision_subsumes_level_when_present():
    # Both present + revision is a clean upgraded signal → only the REVISION
    # field emits; the LEVEL field is suppressed (no double-count).
    snap = {
        "L9.company.earnings_guidance": _guidance_entry(_BYD_EARNINGS_GUIDANCE),
        "L5.fcst.guidance_change": _guidance_entry(_BYD_GUIDANCE_CHANGE),
    }
    emitted = {
        n["dp_id"] for n in synthesize_realtime_nodes(
            snap, _guidance_pair_registry(), existing_dp_ids=set(),
            ts_code="002594.SZ",
        )
    }
    assert emitted == {"L5.fcst.guidance_change"}
    assert "L9.company.earnings_guidance" not in emitted


def test_dedup_keeps_level_when_revision_yields_none():
    # change_direction="new" → guidance_change signal is None, so it does NOT
    # suppress; earnings_guidance is KEPT as the fallback.
    snap = {
        "L9.company.earnings_guidance": _guidance_entry(_BYD_EARNINGS_GUIDANCE),
        "L5.fcst.guidance_change": _guidance_entry(
            {"change_direction": "new", "current_range_pct": 102.0}
        ),
    }
    emitted = {
        n["dp_id"] for n in synthesize_realtime_nodes(
            snap, _guidance_pair_registry(), existing_dp_ids=set(),
            ts_code="002594.SZ",
        )
    }
    assert "L9.company.earnings_guidance" in emitted
    assert "L5.fcst.guidance_change" not in emitted  # None signal → skipped


def test_dedup_keeps_level_when_revision_absent():
    # Only the LEVEL field present → emitted (nothing to dedup against).
    snap = {
        "L9.company.earnings_guidance": _guidance_entry(_BYD_EARNINGS_GUIDANCE),
    }
    emitted = {
        n["dp_id"] for n in synthesize_realtime_nodes(
            snap, _guidance_pair_registry(), existing_dp_ids=set(),
            ts_code="002594.SZ",
        )
    }
    assert emitted == {"L9.company.earnings_guidance"}


def test_dedup_does_not_suppress_on_mock_primary():
    # Revision present but from a mock source → it fails the synthesis gates, so
    # it must NOT suppress the LEVEL field. earnings_guidance is kept.
    snap = {
        "L9.company.earnings_guidance": _guidance_entry(_BYD_EARNINGS_GUIDANCE),
        "L5.fcst.guidance_change": _guidance_entry(
            _BYD_GUIDANCE_CHANGE, source="mock:tushare"
        ),
    }
    emitted = {
        n["dp_id"] for n in synthesize_realtime_nodes(
            snap, _guidance_pair_registry(), existing_dp_ids=set(),
            ts_code="002594.SZ",
        )
    }
    assert "L9.company.earnings_guidance" in emitted  # mock primary can't suppress
    assert "L5.fcst.guidance_change" not in emitted   # mock source → not emitted


def test_dedup_does_not_suppress_on_unknown_primary():
    # Revision present but data_status Unknown → fails the gate, so it does NOT
    # suppress the LEVEL field.
    snap = {
        "L9.company.earnings_guidance": _guidance_entry(_BYD_EARNINGS_GUIDANCE),
        "L5.fcst.guidance_change": _guidance_entry(
            _BYD_GUIDANCE_CHANGE, data_status="Unknown"
        ),
    }
    emitted = {
        n["dp_id"] for n in synthesize_realtime_nodes(
            snap, _guidance_pair_registry(), existing_dp_ids=set(),
            ts_code="002594.SZ",
        )
    }
    assert "L9.company.earnings_guidance" in emitted


def _guidance_pair_overlay() -> dict:
    """Overlay with one authored Unknown seed so the base is ~0 until the
    realtime guidance pair is injected."""

    return {
        "ts_code": "002594.SZ",
        "industry_id": "AUTO",
        "nodes": [
            {
                "node_id": "auth_seed",
                "dp_id": "L5.is.eps",
                "node_name": "auth_seed",
                "parent_node": None,
                "direction": "positive",
                "base_weight": 1.0,
                "active_weight": 1.0,
                "materiality": 1.0,
                "confidence": 0.5,
                "data_status": "Unknown",
                "status": "Unknown",
                "value": None,
                "field_role": "score_component",
                "score_target": "fundamental_score",
                "participates_in_score": True,
            }
        ],
    }


def test_e2e_guidance_pair_counts_one_expectation_gap_node():
    """BYD-like strong-positive pair: exactly ONE synthetic expectation_gap node
    survives (the revision), and its magnitude is de-saturated (< 1.0), so the
    disclosure can't double-count two pinned 1.0 nodes."""

    overlay = _guidance_pair_overlay()
    reg = _registry({
        "L9.company.earnings_guidance": _gov(
            "L9.company.earnings_guidance", target="expectation_gap"
        ),
        "L5.fcst.guidance_change": _gov(
            "L5.fcst.guidance_change", target="expectation_gap"
        ),
        "L5.is.eps": _gov("L5.is.eps", target="fundamental_score"),
    })
    snap = {
        "L9.company.earnings_guidance": _guidance_entry(_BYD_EARNINGS_GUIDANCE),
        "L5.fcst.guidance_change": _guidance_entry(_BYD_GUIDANCE_CHANGE),
    }
    agg = aggregate_company_graph(overlay, role_registry=reg, realtime_snapshot=snap)

    # Synthetic expectation_gap nodes from the guidance pair.
    eg_nodes = {
        nid: r
        for nid, r in agg.items()
        if nid.endswith(":rt") and r.get("score_target") == "expectation_gap"
    }
    # Exactly ONE node (the revision), not two — the level field is deduped.
    assert len(eg_nodes) == 1
    assert "002594.SZ:L5.fcst.guidance_change:rt" in eg_nodes
    assert "002594.SZ:L9.company.earnings_guidance:rt" not in agg

    # The surviving node's contribution is de-saturated: |score| < 1.0 (and far
    # below the ~2.0 two pinned 1.0 nodes would have produced).
    eg_contribution = sum(abs(r["score"]) for r in eg_nodes.values())
    assert eg_contribution < 1.0
