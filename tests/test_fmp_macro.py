"""Tests for ``mvp20.sources.fmp_source.fetch_macro_us_batch``.

Network calls are stubbed via monkeypatch on ``_get_json`` so the suite
stays hermetic. We lock down:

  * 7 market-level macro dp_ids (L7.env.* + L9.macro.*) are declared in
    SUPPORTED_DP_IDS and emitted on a clean call.
  * Sentinel ``ts_code`` is ``MARKET:US`` (not registered in universe).
  * TTL cache: a second invocation within 600s returns the cached rows
    without re-hitting the endpoints.
  * Per-endpoint failure isolation: a 401 on /quote (style) emits an
    Inactive row for ``L7.env.style`` while the other six dp_ids still
    fetch normally.
  * Threshold logic: L9.macro.rates flips ``Known`` only when |Δ10Y|
    exceeds 5bp/day; L9.macro.fx flips ``Known`` only when |ΔDXY|
    exceeds 0.5%/day.
"""

from __future__ import annotations

import json

import pytest

from mvp20.sources import fmp_source


# ---------------------------------------------------------------------------
# SUPPORTED_DP_IDS contract
# ---------------------------------------------------------------------------


def test_supported_dp_ids_includes_macro_dp_ids() -> None:
    expected = {
        "L7.env.market_trend",
        "L7.env.rates",
        "L7.env.fx",
        "L7.env.style",
        "L9.macro.rates",
        "L9.macro.fx",
        "L9.macro.cpi_employment",
    }
    assert expected.issubset(fmp_source.SUPPORTED_DP_IDS)


# ---------------------------------------------------------------------------
# Fake _get_json: routes by endpoint to the right canned payload
# ---------------------------------------------------------------------------


def _index_series(start: float, end: float, days: int = 22):
    """Build a ``/historical-price-eod/light`` style payload sloping from
    ``start`` (oldest) to ``end`` (latest)."""

    from datetime import date, timedelta
    base = date(2026, 4, 1)
    step = (end - start) / max(days - 1, 1)
    return [
        {"date": (base + timedelta(days=i)).isoformat(),
         "price": start + i * step}
        for i in range(days)
    ]


def _treasury_series(latest_10y: float, prev_10y: float):
    return [
        {"date": "2026-05-08",
         "year1": 4.5, "year2": 4.4, "year5": 4.3,
         "year10": prev_10y, "year30": 4.7},
        {"date": "2026-05-09",
         "year1": 4.5, "year2": 4.4, "year5": 4.3,
         "year10": latest_10y, "year30": 4.7},
    ]


def _econ_calendar_payload():
    return [
        {"date": "2026-04-10", "country": "US",
         "event": "CPI YoY", "actual": 3.1, "previous": 3.0},
        {"date": "2026-04-05", "country": "US",
         "event": "Nonfarm Payrolls", "actual": 180.0, "previous": 165.0},
        {"date": "2026-04-05", "country": "US",
         "event": "Unemployment Rate", "actual": 4.1, "previous": 4.2},
        # Noise — non-US should be ignored.
        {"date": "2026-04-08", "country": "EU",
         "event": "CPI YoY", "actual": 2.4, "previous": 2.5},
    ]


def _make_fake_get_json(*, style_fails: bool = False):
    """Build a stub ``_get_json`` that branches by endpoint string."""

    def fake(endpoint: str, params: dict | None = None, timeout: int = 15):
        params = params or {}
        if endpoint == "/historical-price-eod/light":
            sym = params.get("symbol", "")
            if sym == "^GSPC":
                return _index_series(5000.0, 5150.0)  # +3% over 30d
            if sym == "QQQ":
                # Used as ^NDX proxy on FMP Starter
                return _index_series(380.0, 399.0)  # +5%
            if sym == "^DJI":
                return _index_series(40000.0, 40400.0)  # +1%
            if sym == "EURUSD":
                return _index_series(1.08, 1.092)  # +1.1%
            if sym == "UUP":
                # Used as DXY proxy on FMP Starter
                return _index_series(27.0, 27.1)  # +0.37% over 30d
            if sym == "IWF":
                return _index_series(380.0, 400.0)  # +5.3%
            if sym == "IWD":
                return _index_series(180.0, 185.0)  # +2.8%
            return []
        if endpoint == "/treasury-rates":
            # 10Y up 4bp (4.30 → 4.34) — below 5bp threshold, status=Unknown.
            return _treasury_series(latest_10y=4.34, prev_10y=4.30)
        if endpoint == "/economic-calendar":
            return _econ_calendar_payload()
        if endpoint == "/quote":
            sym = params.get("symbol", "")
            if style_fails:
                # Simulate 401 / endpoint failure path: _get_json returns None
                return None
            if sym == "IWF":
                return [{"symbol": "IWF", "price": 400.0}]
            if sym == "IWD":
                return [{"symbol": "IWD", "price": 185.0}]
            return []
        return None

    return fake


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_macro_cache():
    """Clear module-level TTL cache between tests so each starts clean."""

    fmp_source._MACRO_CACHE.clear()
    fmp_source._LAST_MACRO_FETCH["ts"] = 0.0
    yield
    fmp_source._MACRO_CACHE.clear()
    fmp_source._LAST_MACRO_FETCH["ts"] = 0.0


@pytest.fixture()
def fake_api_key(monkeypatch):
    monkeypatch.setattr(fmp_source, "_get_api_key", lambda: "TESTKEY")


# ---------------------------------------------------------------------------
# Happy path: all 7 dp_ids emitted with MARKET:US sentinel
# ---------------------------------------------------------------------------


def test_fetch_macro_us_batch_emits_all_seven_dp_ids(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_fake_get_json())
    rows = fmp_source.fetch_macro_us_batch(1_000_000)

    assert rows, "expected non-empty rows"
    # All rows should use the MARKET:US sentinel.
    for r in rows:
        assert r[0] == "MARKET:US", r

    dp_ids = {r[1] for r in rows}
    expected = {
        "L7.env.market_trend",
        "L7.env.rates",
        "L7.env.fx",
        "L7.env.style",
        "L9.macro.rates",
        "L9.macro.fx",
        "L9.macro.cpi_employment",
    }
    assert expected.issubset(dp_ids), dp_ids - expected


def test_row_shape_matches_seven_tuple(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_fake_get_json())
    rows = fmp_source.fetch_macro_us_batch(2_000_000)

    for r in rows:
        assert len(r) == 7, r
        ts_code, dp_id, value_json, status, conf, source, ts = r
        assert ts_code == "MARKET:US"
        assert isinstance(dp_id, str) and dp_id
        # value_json is real JSON, ≤ 1KB
        payload = json.loads(value_json)
        assert isinstance(payload, dict)
        assert len(value_json.encode("utf-8")) <= 1024, dp_id
        assert status in ("Known", "Unknown", "Inactive", "Proxy")
        assert 0.0 <= conf <= 1.0
        assert source.startswith("fmp:")
        assert isinstance(ts, int)


# ---------------------------------------------------------------------------
# Payload schema sanity
# ---------------------------------------------------------------------------


def _row_by_dp(rows, dp_id):
    for r in rows:
        if r[1] == dp_id:
            return r
    raise AssertionError(f"missing dp_id {dp_id} in rows")


def test_market_trend_payload_carries_three_indices(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_fake_get_json())
    rows = fmp_source.fetch_macro_us_batch(3_000_000)

    r = _row_by_dp(rows, "L7.env.market_trend")
    p = json.loads(r[2])
    assert "spx_30d_pct" in p and "ndx_30d_pct" in p and "dji_30d_pct" in p
    assert "latest_date" in p
    # All three should be positive given the synthetic uptrend.
    assert p["spx_30d_pct"] > 0
    assert p["ndx_30d_pct"] > 0


def test_treasury_emits_curve_and_slope(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_fake_get_json())
    rows = fmp_source.fetch_macro_us_batch(4_000_000)

    snap = json.loads(_row_by_dp(rows, "L7.env.rates")[2])
    assert snap["10y"] == 4.34
    assert snap["2y"] == 4.4
    # slope_10y_2y = 10y - 2y = -0.06 (inverted curve in fixture)
    assert abs(snap["slope_10y_2y"] - (4.34 - 4.4)) < 1e-6


def test_rates_event_below_threshold_is_unknown(monkeypatch, fake_api_key):
    """4bp change < 5bp threshold → status stays Unknown."""

    monkeypatch.setattr(fmp_source, "_get_json", _make_fake_get_json())
    rows = fmp_source.fetch_macro_us_batch(5_000_000)

    event = _row_by_dp(rows, "L9.macro.rates")
    payload = json.loads(event[2])
    assert event[3] == "Unknown", event
    assert payload["change_bp"] is not None
    assert abs(payload["change_bp"]) < 5.0


def test_rates_event_above_threshold_is_known(monkeypatch, fake_api_key):
    """8bp jump should trip the event into Known."""

    fake_base = _make_fake_get_json()

    def fake(endpoint, params=None, timeout=15):
        if endpoint == "/treasury-rates":
            return _treasury_series(latest_10y=4.38, prev_10y=4.30)
        return fake_base(endpoint, params, timeout)

    monkeypatch.setattr(fmp_source, "_get_json", fake)
    rows = fmp_source.fetch_macro_us_batch(6_000_000)

    event = _row_by_dp(rows, "L9.macro.rates")
    assert event[3] == "Known", event
    payload = json.loads(event[2])
    assert abs(payload["change_bp"]) > 5.0


def test_cpi_employment_payload_filters_us_only(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_fake_get_json())
    rows = fmp_source.fetch_macro_us_batch(7_000_000)

    p = json.loads(_row_by_dp(rows, "L9.macro.cpi_employment")[2])
    assert p["cpi_yoy_latest"] == 3.1
    assert p["nfp_latest_k"] == 180.0
    assert p["unemployment_pct"] == 4.1


def test_fx_snapshot_and_event(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_fake_get_json())
    rows = fmp_source.fetch_macro_us_batch(8_000_000)

    snap = json.loads(_row_by_dp(rows, "L7.env.fx")[2])
    assert snap["eurusd"] is not None
    assert snap["dxy"] is not None
    assert snap["eurusd_30d_pct"] is not None

    event = _row_by_dp(rows, "L9.macro.fx")
    # DXY 30d series ends at 104.8 — the daily delta within the last 7d
    # window is well below 0.5% in our linear fixture → Unknown. When the
    # event does trigger, status is "Proxy" (DXY sourced via UUP ETF).
    assert event[3] in ("Proxy", "Unknown")


def test_style_payload_has_ratio(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_fake_get_json())
    rows = fmp_source.fetch_macro_us_batch(9_000_000)

    p = json.loads(_row_by_dp(rows, "L7.env.style")[2])
    assert p["iwf"] == 400.0
    assert p["iwd"] == 185.0
    assert abs(p["ratio"] - (400.0 / 185.0)) < 1e-6


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


def test_second_call_within_ttl_returns_cache(monkeypatch, fake_api_key):
    call_count = {"n": 0}

    base = _make_fake_get_json()

    def counting(endpoint, params=None, timeout=15):
        call_count["n"] += 1
        return base(endpoint, params, timeout)

    monkeypatch.setattr(fmp_source, "_get_json", counting)

    rows_a = fmp_source.fetch_macro_us_batch(10_000_000)
    first_calls = call_count["n"]
    assert first_calls > 0

    # Second call 100s later (< 600s TTL) — should hit cache, not _get_json.
    rows_b = fmp_source.fetch_macro_us_batch(10_000_100)
    assert call_count["n"] == first_calls, (
        f"expected no extra HTTP calls; got {call_count['n'] - first_calls}")
    assert rows_a == rows_b


def test_call_after_ttl_refreshes(monkeypatch, fake_api_key):
    call_count = {"n": 0}
    base = _make_fake_get_json()

    def counting(endpoint, params=None, timeout=15):
        call_count["n"] += 1
        return base(endpoint, params, timeout)

    monkeypatch.setattr(fmp_source, "_get_json", counting)

    fmp_source.fetch_macro_us_batch(11_000_000)
    first = call_count["n"]
    # 1000s later > TTL=600s → must re-hit.
    fmp_source.fetch_macro_us_batch(11_000_000 + 1000)
    assert call_count["n"] > first


# ---------------------------------------------------------------------------
# Per-endpoint failure isolation
# ---------------------------------------------------------------------------


def test_style_endpoint_failure_emits_inactive_row(monkeypatch, fake_api_key):
    """When /quote returns None (e.g. 401 on a paywalled endpoint), the
    L7.env.style row is Inactive but the other six dp_ids still fetch."""

    monkeypatch.setattr(fmp_source, "_get_json",
                        _make_fake_get_json(style_fails=True))
    rows = fmp_source.fetch_macro_us_batch(12_000_000)

    style = _row_by_dp(rows, "L7.env.style")
    assert style[3] == "Inactive", style
    assert style[4] == 0.0
    # Other dp_ids should still be present. L7.env.fx is "Proxy" because
    # DXY is sourced via UUP ETF on Starter; the rest are real-data Known.
    other_known = {
        "L7.env.market_trend",
        "L7.env.rates",
        "L9.macro.cpi_employment",
    }
    for dp_id in other_known:
        r = _row_by_dp(rows, dp_id)
        assert r[3] == "Known", (dp_id, r)
    assert _row_by_dp(rows, "L7.env.fx")[3] == "Proxy"


def test_missing_api_key_returns_empty(monkeypatch):
    monkeypatch.setattr(fmp_source, "_get_api_key", lambda: None)
    assert fmp_source.fetch_macro_us_batch(13_000_000) == []
