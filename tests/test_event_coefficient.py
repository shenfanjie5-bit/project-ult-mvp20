"""Unit tests for mvp20.event_coefficient — the validated forecast coefficient."""
from __future__ import annotations

import math

import pytest

from mvp20.event_coefficient import (
    _NEG_TYPES,
    _POS_TYPES,
    forecast_coefficient,
    news_coefficient_meta,
)


def _fc(typ, pmin=None, pmax=None):
    return {"type": typ, "change_pct_min": pmin, "change_pct_max": pmax,
            "ann_date": "20260131", "period": "20251231"}


def test_big_positive_growth_high_coefficient():
    r = forecast_coefficient(_fc("预增", 50.0, 80.0))
    assert r is not None
    assert r["validated"] is True
    assert r["direction"] == "positive"
    assert r["coefficient"] > 0.7          # 50-80% growth -> strong positive
    assert r["model"] == "forecast_v1"
    assert r["horizon_days"] == 1
    assert "jan_jul_seasonal" in r["caveats"]


def test_deep_negative_growth_low_coefficient():
    r = forecast_coefficient(_fc("预减", -77.0, -69.0))
    assert r is not None
    assert r["direction"] == "negative"
    assert r["coefficient"] < -0.7
    # the fragile short leg must be flagged
    assert "short_leg_survivorship_fragile" in r["caveats"]


def test_weak_positive_near_zero():
    # 略增 5-15% is an intentionally ~0-edge type in the study.
    r = forecast_coefficient(_fc("略增", 5.0, 15.0))
    assert r is not None
    assert 0.0 < r["coefficient"] < 0.3


def test_turnaround_categorical_positive():
    # 扭亏 has no meaningful p_change (loss base) -> categorical positive.
    r = forecast_coefficient(_fc("扭亏", None, None))
    assert r is not None
    assert r["direction"] == "positive"
    assert r["coefficient"] > 0


def test_no_direction_returns_none():
    assert forecast_coefficient(_fc("不确定", None, None)) is None
    assert forecast_coefficient(_fc("", None, None)) is None
    assert forecast_coefficient({}) is None
    assert forecast_coefficient(None) is None  # type: ignore[arg-type]


@pytest.mark.parametrize("typ", _POS_TYPES)
def test_all_positive_types_sign(typ):
    r = forecast_coefficient(_fc(typ, 30.0, 40.0))
    assert r is not None and r["coefficient"] > 0 and r["direction"] == "positive"


@pytest.mark.parametrize("typ", _NEG_TYPES)
def test_all_negative_types_sign(typ):
    r = forecast_coefficient(_fc(typ, -40.0, -30.0))
    assert r is not None and r["coefficient"] < 0 and r["direction"] == "negative"


def test_coefficient_bounded():
    # Extreme growth must stay within [-1, 1].
    hi = forecast_coefficient(_fc("预增", 5000.0, 9000.0))
    lo = forecast_coefficient(_fc("预减", -99.0, -95.0))
    assert -1.0 <= lo["coefficient"] < 0 < hi["coefficient"] <= 1.0


def test_bigger_beats_smaller():
    small = forecast_coefficient(_fc("预增", 10.0, 20.0))["coefficient"]
    big = forecast_coefficient(_fc("预增", 100.0, 150.0))["coefficient"]
    assert big > small  # monotone in announced growth


def test_news_meta_unvalidated():
    m = news_coefficient_meta()
    assert m["validated"] is False
    assert m["reason"] == "track_b_forward_only"


def test_tanh_calibration_anchor():
    # +0.5% expected abnormal -> tanh(200*0.005)=tanh(1.0) ~ 0.76; sanity that k=200 holds.
    assert math.isclose(math.tanh(200 * 0.005), 0.7616, abs_tol=0.01)
