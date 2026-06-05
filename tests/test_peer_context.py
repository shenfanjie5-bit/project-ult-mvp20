"""R-3a — cross-sectional de-common-mode of the priced_in cluster.

Hermetic tests (no live DB) for:
  * the ``_xs_percentile`` / ``_xs_bad_tail`` ranking helpers,
  * ``build_peer_context`` population gathering,
  * the run_up / crowdedness normalizers under a cross-sectional reference,
  * the fall-through guard (a peer-governed None must NOT re-acquire the legacy
    absolute / generic-percentile signal),
  * back-compat: with peer_context=None every path is bit-for-bit the old code,
  * ``peer_context.peer_context_for_market`` market scoping + cache.
"""
from __future__ import annotations

import math

import pytest

from mvp20.aggregator import (
    _realtime_field_signal,
    _realtime_signal,
    _xs_bad_tail,
    _xs_percentile,
    build_peer_context,
)


# --------------------------------------------------------------------------- #
# ranking helpers
# --------------------------------------------------------------------------- #
POP = [0.0, 0.25, 0.5, 0.75, 1.0]  # n=5, median element 0.5 → xs 0.5


def test_xs_percentile_median_is_half():
    assert _xs_percentile(0.5, POP) == pytest.approx(0.5)


def test_xs_percentile_extremes():
    assert _xs_percentile(0.0, POP) == pytest.approx(0.1)   # (0+1)/2 / 5
    assert _xs_percentile(1.0, POP) == pytest.approx(0.9)   # (4+5)/2 / 5
    assert _xs_percentile(99.0, POP) == pytest.approx(1.0)  # above all


def test_xs_percentile_empty_pop_is_none():
    assert _xs_percentile(0.5, []) is None


def test_xs_bad_tail_median_and_below_are_none():
    # at/below the cross-sectional median → no signal vs peers → None (skip node)
    assert _xs_bad_tail(0.5, POP) is None
    assert _xs_bad_tail(0.0, POP) is None
    assert _xs_bad_tail(None, POP) is None
    assert _xs_bad_tail(0.5, None) is None


def test_xs_bad_tail_high_side_scales():
    # 1.0 → xs 0.9 → (0.9-0.5)*2 = 0.8 ; 0.75 → xs 0.7 → 0.4
    assert _xs_bad_tail(1.0, POP) == pytest.approx(0.8)
    assert _xs_bad_tail(0.75, POP) == pytest.approx(0.4)


# --------------------------------------------------------------------------- #
# build_peer_context
# --------------------------------------------------------------------------- #
def _snap(d20=None, crowd_pct=None):
    s = {}
    if d20 is not None:
        s["L6.priced.run_up"] = {"value": {"d20_pct": d20}}
    if crowd_pct is not None:
        s["L6.priced.crowdedness"] = {"value": {"percentile": crowd_pct}}
    return s


def test_build_peer_context_collects_sorted_populations():
    snaps = {
        "A.SZ": _snap(d20=0.30, crowd_pct=0.9),
        "B.SZ": _snap(d20=0.05, crowd_pct=0.4),
        "C.SZ": _snap(d20=0.10, crowd_pct=0.6),
    }
    ctx = build_peer_context(snaps)
    assert ctx["L6.priced.run_up"] == [0.05, 0.10, 0.30]       # sorted
    assert ctx["L6.priced.crowdedness"] == [0.4, 0.6, 0.9]


def test_build_peer_context_omits_absent_fields():
    # No usable run_up anywhere → dp_id omitted entirely (→ absolute fallback).
    ctx = build_peer_context({"A.SZ": _snap(crowd_pct=0.5), "B.SZ": _snap(crowd_pct=0.7)})
    assert "L6.priced.run_up" not in ctx
    assert ctx["L6.priced.crowdedness"] == [0.5, 0.7]


def test_build_peer_context_run_up_falls_back_to_d5():
    ctx = build_peer_context({"A.SZ": {"L6.priced.run_up": {"value": {"d5_pct": 0.12}}}})
    assert ctx["L6.priced.run_up"] == [0.12]


# --------------------------------------------------------------------------- #
# run_up normalizer
# --------------------------------------------------------------------------- #
RUN_POP = [0.0, 0.05, 0.10, 0.15, 0.20]  # median element 0.10


def test_run_up_cross_sectional_penalizes_only_high_tail():
    ctx = {"L6.priced.run_up": RUN_POP}
    # top run-up → discount > 0
    top = _realtime_field_signal("L6.priced.run_up", {"d20_pct": 0.20},
                                 "priced_in_discount", "X.SZ", ctx)
    assert top is not None and top > 0.0
    # median run-up → no signal vs peers (None → node skipped, no common-mode)
    med = _realtime_field_signal("L6.priced.run_up", {"d20_pct": 0.10},
                                 "priced_in_discount", "X.SZ", ctx)
    assert med is None


def test_run_up_absolute_back_compat_without_peer_context():
    # peer_context=None → original absolute 20%-saturating magnitude.
    assert _realtime_field_signal("L6.priced.run_up", {"d20_pct": 0.10},
                                  "priced_in_discount") == pytest.approx(0.5)
    assert _realtime_field_signal("L6.priced.run_up", {"d20_pct": -0.05},
                                  "priced_in_discount") == pytest.approx(0.0)
    assert _realtime_field_signal("L6.priced.run_up", {"d20_pct": 0.40},
                                  "priced_in_discount") == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# crowdedness normalizer + fall-through guard
# --------------------------------------------------------------------------- #
CROWD_POP = [0.30, 0.50, 0.70, 0.85, 0.95]  # median element 0.70


def test_crowdedness_cross_sectional_high_tail_negative_magnitude():
    ctx = {"L6.priced.crowdedness": CROWD_POP}
    sig = _realtime_field_signal("L6.priced.crowdedness", {"percentile": 0.95},
                                 "priced_in_discount", "X.SZ", ctx)
    assert sig is not None and sig < 0.0          # negative (priced_in direction)
    # downstream abs() → a real discount magnitude
    assert abs(sig) > 0.0


def test_crowdedness_below_median_skips_node_no_fallthrough():
    """The crux: with a peer reference, a below-median crowdedness must return
    None *and not* fall through to the legacy generic-percentile path (which
    would re-inject the abs'd common-mode discount). Verified through the public
    ``_realtime_signal`` entry point (where the fall-through would happen)."""
    ctx = {"L6.priced.crowdedness": CROWD_POP}
    out = _realtime_signal("L6.priced.crowdedness", {"percentile": 0.40},
                           "priced_in_discount", "X.SZ", ctx)
    assert out is None  # NOT -(0.40-0.5)*2 = +0.1 from the legacy path


def test_crowdedness_legacy_percentile_path_when_no_peer_context():
    # Back-compat: peer_context=None → field rule returns None → _realtime_signal
    # falls through to the generic inverted-percentile path (the old behaviour).
    field = _realtime_field_signal("L6.priced.crowdedness", {"percentile": 0.97},
                                   "priced_in_discount")
    assert field is None  # no field rule without a reference
    legacy = _realtime_signal("L6.priced.crowdedness", {"percentile": 0.97},
                              "priced_in_discount")
    assert legacy == pytest.approx(-(0.97 - 0.5) * 2.0)  # inverted, unchanged


# --------------------------------------------------------------------------- #
# peer_context provisioning module
# --------------------------------------------------------------------------- #
def test_market_of():
    from mvp20.peer_context import market_of
    assert market_of("300750.SZ") == "A"
    assert market_of("600519.SH") == "A"
    assert market_of("000001.BJ") == "A"
    assert market_of("00700.HK") == "HK"
    assert market_of("AAPL") == "US"


def test_peer_context_for_market_filters_and_caches(tmp_path, monkeypatch):
    from mvp20 import peer_context as pc
    pc.clear_cache()
    # fake read_hot_snapshot keyed by ts_code
    snaps = {
        "A.SZ": _snap(d20=0.30, crowd_pct=0.9),
        "B.SZ": _snap(d20=0.10, crowd_pct=0.5),
        "X.HK": _snap(d20=0.99, crowd_pct=0.99),  # different market → excluded
    }
    import mvp20.storage as storage
    monkeypatch.setattr(storage, "read_hot_snapshot", lambda db, ts: snaps.get(ts, {}))
    db = tmp_path / "hot.sqlite"
    db.write_text("x")  # needs to exist for mtime
    ctx = pc.peer_context_for_market(db, list(snaps.keys()), "A", overlays_dir=tmp_path)
    # only the two A-shares contribute (HK excluded by market scoping)
    assert ctx["L6.priced.run_up"] == [0.10, 0.30]
    assert ctx["L6.priced.crowdedness"] == [0.5, 0.9]


# --------------------------------------------------------------------------- #
# R-3b.2 — hierarchical valuation pools + cross-sectional valr
# --------------------------------------------------------------------------- #
from mvp20.aggregator import _valuation_pooled, _xs_valuation_signal  # noqa: E402
from mvp20.peer_context import build_valuation_pools  # noqa: E402


def _pe_snap(pe):
    return {"L6.mult.pe": {"value": {"scalar": pe}}}


def test_build_valuation_pools_hierarchical_resolution():
    # arch BIG (5 ≥ n_min) → ARCH; arch SMALL (2 < n_min) but industry I1 (7) → IND;
    # arch TINY (1) + industry I2 (1) → MARKET.
    snaps = {f"A{i}.SZ": _pe_snap(pe) for i, pe in enumerate([10, 20, 30, 40, 50], 1)}
    snaps.update({"B1.SZ": _pe_snap(15), "B2.SZ": _pe_snap(25), "C1.SZ": _pe_snap(100)})
    arch = {**{f"A{i}.SZ": "BIG" for i in range(1, 6)},
            "B1.SZ": "SMALL", "B2.SZ": "SMALL", "C1.SZ": "TINY"}
    ind = {**{f"A{i}.SZ": "I1" for i in range(1, 6)},
           "B1.SZ": "I1", "B2.SZ": "I1", "C1.SZ": "I2"}
    pools = build_valuation_pools(snaps, arch, ind, n_min=3)
    assert pools["_val_pe_pool_of"]["A1.SZ"] == "ARCH:BIG"
    assert pools["_val_pe_pool"]["ARCH:BIG"] == [10, 20, 30, 40, 50]
    assert pools["_val_pe_pool_of"]["B1.SZ"] == "IND:I1"      # arch too thin → industry
    assert pools["_val_pe_pool"]["IND:I1"] == [10, 15, 20, 25, 30, 40, 50]
    assert pools["_val_pe_pool_of"]["C1.SZ"] == "MARKET:A"     # both thin → market


def _pooled_ctx():
    # X cheap (PE 10) vs pool [10..50]; Y expensive (PE 50); Z only PS.
    return {
        "_val_pe_of": {"X.SZ": 10.0, "Y.SZ": 50.0},
        "_val_pe_pool_of": {"X.SZ": "ARCH:K", "Y.SZ": "ARCH:K"},
        "_val_pe_pool": {"ARCH:K": [10.0, 20.0, 30.0, 40.0, 50.0]},
        "_val_ps_of": {"Z.SZ": 1.0},
        "_val_ps_pool_of": {"Z.SZ": "ARCH:K"},
        "_val_ps_pool": {"ARCH:K": [1.0, 3.0, 5.0, 7.0, 9.0]},
    }


def test_valuation_pooled_flag():
    assert _valuation_pooled(_pooled_ctx()) is True
    assert _valuation_pooled({"L6.priced.run_up": [1, 2]}) is False  # R-3a only
    assert _valuation_pooled(None) is False


def test_xs_valuation_signal_cheap_positive_expensive_negative():
    ctx = _pooled_ctx()
    assert _xs_valuation_signal("X.SZ", ctx) == pytest.approx(0.8)   # cheap → +
    assert _xs_valuation_signal("Y.SZ", ctx) == pytest.approx(-0.8)  # expensive → -
    assert _xs_valuation_signal("Z.SZ", ctx) == pytest.approx(0.8)   # PS fallback (PS 1 = cheap)
    assert _xs_valuation_signal("UNKNOWN.SZ", ctx) is None


def test_peer_compare_cross_sectional_when_pooled():
    ctx = _pooled_ctx()
    sig = _realtime_field_signal("L6.state.peer_compare", {"stock_pe": 10.0},
                                 "valuation_rerating", "X.SZ", ctx)
    assert sig == pytest.approx(0.8)  # cheap vs pool


def test_peer_compare_none_without_pools_falls_through_to_legacy():
    # No valuation pools → field rule returns None → generic path uses the legacy
    # premium_vs_industry_pct (tanh/30, flipped). Back-compat.
    field = _realtime_field_signal("L6.state.peer_compare",
                                   {"premium_vs_industry_pct": 30.0}, "valuation_rerating")
    assert field is None
    legacy = _realtime_signal("L6.state.peer_compare",
                              {"premium_vs_industry_pct": 30.0}, "valuation_rerating")
    assert legacy == pytest.approx(-math.tanh(30.0 / 30.0))  # premium → expensive → negative


@pytest.mark.parametrize("dp_id", [
    "L6.state.historical_percentile", "L6.state.expansion_compression",
    "L6.path.tag", "L6.mult.ps", "L6.mult.ev_ebitda", "L6.mult.forward_pe",
])
def test_contaminated_valr_signals_suppressed_when_pooled(dp_id):
    ctx = _pooled_ctx()
    # field rule returns None (suppressed) AND the fall-through guard stops it from
    # re-acquiring its legacy signal via _realtime_signal.
    assert _realtime_field_signal(dp_id, {"scalar": 50.0, "pe_percentile": 0.99,
                                          "ratio_vs_250d": 1.5, "percentile": 0.9},
                                  "valuation_rerating", "X.SZ", ctx) is None
    assert _realtime_signal(dp_id, {"scalar": 50.0, "pe_percentile": 0.99,
                                    "ratio_vs_250d": 1.5}, "valuation_rerating",
                            "X.SZ", ctx) is None


def test_suppressed_signals_unchanged_without_pools():
    # Back-compat: without valuation pools, ps keeps its absolute log-ratio signal.
    sig = _realtime_signal("L6.mult.ps", {"scalar": 100.0}, "valuation_rerating")
    assert sig is not None and sig < 0.0  # high P/S → expensive → negative


def test_peg_match_and_second_derivative_not_suppressed_when_pooled():
    ctx = _pooled_ctx()
    # peg_match carries an already-signed score → generic path #1 passes it through
    # (NOT suppressed — growth-adjusted, orthogonal to level).
    assert _realtime_signal("L6.state.peg_match", {"score": -0.7},
                            "valuation_rerating", "X.SZ", ctx) == pytest.approx(-0.7)
    # second_derivative (path) survives via the curated signed-pct field.
    assert _realtime_signal("L6.path.second_derivative", {"second_derivative": 0.2},
                            "valuation_rerating", "X.SZ", ctx) == pytest.approx(math.tanh(0.2))


def test_save_load_peer_context_roundtrip(tmp_path):
    from mvp20.peer_context import save_peer_context, load_peer_context
    ctx = _pooled_ctx()
    p = tmp_path / "pc.json"
    save_peer_context(ctx, p)
    loaded = load_peer_context(p)
    assert loaded["_val_pe_of"]["X.SZ"] == 10.0
    assert _xs_valuation_signal("Y.SZ", loaded) == pytest.approx(-0.8)
    assert load_peer_context(tmp_path / "missing.json") is None


def test_save_peer_context_atomic_failure_keeps_prior(tmp_path, monkeypatch):
    """A crash mid-write must leave the PRIOR artifact intact (not a half-written
    file) and clean up the temp — otherwise load_peer_context returns None and the
    WHOLE A-share pool silently falls back to degraded absolute valuation."""
    from mvp20.peer_context import save_peer_context, load_peer_context
    import json as _json

    p = tmp_path / "peer_context_A.json"
    save_peer_context({"_val_pe_of": {"A.SZ": 1.0}}, p)
    assert load_peer_context(p)["_val_pe_of"]["A.SZ"] == 1.0

    def _boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(_json, "dump", _boom)
    with pytest.raises(OSError):
        save_peer_context({"_val_pe_of": {"A.SZ": 999.0}}, p)

    # prior artifact intact (json.load is not patched), no temp leftover
    assert load_peer_context(p)["_val_pe_of"]["A.SZ"] == 1.0
    assert list(p.parent.glob(".peer_context.*")) == []
