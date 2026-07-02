"""F6-tag: business-model archetype gross-margin re-center.

Hermetic tests for ``_resolve_gross_margin_median`` + the ``L5.is.gross_margin``
re-center, using a monkeypatched ts_code→archetype map (so the tests don't
depend on the live config/business_model_archetypes.yaml content).
"""
from __future__ import annotations

import pytest

from mvp20 import aggregator
from mvp20.aggregator import (
    _ARCHETYPE_GM_MEDIAN,
    _GROSS_MARGIN_MEDIAN,
    _realtime_field_signal,
    _resolve_gross_margin_median,
)


@pytest.fixture
def archetype_map(monkeypatch):
    """Inject a deterministic ts_code→archetype map, bypassing the live yaml."""
    monkeypatch.setattr(
        aggregator,
        "_ARCHETYPE_BY_TS_CACHE",
        {
            "EMS.SZ": "ASSEMBLER_EMS",  # tight archetype → in the median table
            "FIN.SH": "FINANCIAL_DIVIDEND",  # GM meaningless → skip
            "WIDE.SZ": "COMM_NETWORK_EQUIP",  # wide/mixed → NOT in table → universe
        },
    )


def test_resolve_uses_archetype_median_for_tight_archetype(archetype_map):
    assert _resolve_gross_margin_median("EMS.SZ") == pytest.approx(
        _ARCHETYPE_GM_MEDIAN["ASSEMBLER_EMS"]
    )


def test_resolve_financial_returns_none_to_skip(archetype_map):
    assert _resolve_gross_margin_median("FIN.SH") is None


def test_resolve_wide_archetype_falls_back_to_universe(archetype_map):
    # COMM_NETWORK_EQUIP is intentionally absent from the gated median table
    # (it would floor 中兴 against Cisco/Arista), so it must use the universe.
    assert _resolve_gross_margin_median("WIDE.SZ") == pytest.approx(_GROSS_MARGIN_MEDIAN)


def test_resolve_unclassified_falls_back_to_universe(archetype_map):
    assert _resolve_gross_margin_median("UNKNOWN.SZ") == pytest.approx(
        _GROSS_MARGIN_MEDIAN
    )


def test_resolve_none_ts_falls_back_to_universe():
    assert _resolve_gross_margin_median(None) == pytest.approx(_GROSS_MARGIN_MEDIAN)


def test_thin_margin_ems_not_floored_by_archetype_recenter(archetype_map):
    """A 6.6% gross margin (浪潮-like) floors against the universe (0.29) but reads
    only mildly negative against the EMS archetype median (~0.10)."""
    payload = {"scalar": 0.066}
    universe = _realtime_field_signal(
        "L5.is.gross_margin", payload, "fundamental_score", None
    )
    archetyped = _realtime_field_signal(
        "L5.is.gross_margin", payload, "fundamental_score", "EMS.SZ"
    )
    assert universe < -0.5  # universe-centered: near the floor
    assert -0.25 < archetyped < 0.0  # archetype-centered: mild, not floored
    assert archetyped > universe


def test_gross_margin_skipped_for_financial(archetype_map):
    # A bank's reported "gross margin" is not a meaningful signal → None (no node).
    assert (
        _realtime_field_signal(
            "L5.is.gross_margin", {"scalar": 0.97}, "fundamental_score", "FIN.SH"
        )
        is None
    )


def test_gross_margin_unchanged_without_ts_code():
    """Back-compat: the existing call path (no ts_code) is bit-for-bit the old
    universe-centered behaviour."""
    payload = {"scalar": 0.40}
    no_ts = _realtime_field_signal("L5.is.gross_margin", payload, "fundamental_score")
    explicit_none = _realtime_field_signal(
        "L5.is.gross_margin", payload, "fundamental_score", None
    )
    assert no_ts == explicit_none
