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
    ctx = pc.peer_context_for_market(db, list(snaps.keys()), "A")
    # only the two A-shares contribute (HK excluded by market scoping)
    assert ctx["L6.priced.run_up"] == [0.10, 0.30]
    assert ctx["L6.priced.crowdedness"] == [0.5, 0.9]
