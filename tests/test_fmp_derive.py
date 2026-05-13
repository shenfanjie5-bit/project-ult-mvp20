"""Tests for the three B.6d derived per-stock fetchers in ``fmp_source``.

We monkeypatch ``_get_json`` so the suite stays hermetic and validate:

  * ``L5.surprise.preprice`` — emits ``Known`` with the documented payload
    schema when /earnings returns a dated row + price history is long
    enough; emits ``Inactive`` when /earnings is empty.
  * ``L6.priced.news_age``   — emits ``Known`` with age + 7d/30d counts;
    emits ``Inactive`` when /news/stock is empty.
  * ``L11.short.technical``  — MA(20)/MA(50)/RSI(14)/MACD(12,26,9) payload
    is populated and numerically sane on a synthetic 50-bar series.
  * Non-US ts_codes (e.g. ``300750.SZ``) are silently skipped — they appear
    in the universe but never in the emitted rows.
  * The price-history cache is hit exactly once per symbol per cycle so
    preprice + technical share a single HTTP call.

Network is never actually touched; ``_get_api_key`` is also stubbed.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from mvp20.sources import fmp_source


# ---------------------------------------------------------------------------
# Helpers — build canned /historical-price-eod/light + /news + /earnings
# ---------------------------------------------------------------------------


def _price_series(symbol: str, *, days: int = 60,
                  start: float = 100.0, end: float = 120.0,
                  spike_last: float | None = None) -> list[dict]:
    """Build a desc-by-date price-history payload sloping linearly from
    ``start`` (oldest) to ``end`` (latest), optionally overriding the very
    last bar to ``spike_last`` to create RSI/MACD movement."""

    today = date(2026, 5, 12)
    step = (end - start) / max(days - 1, 1)
    rows: list[dict] = []
    for i in range(days):
        d = today - timedelta(days=(days - 1 - i))
        price = start + i * step
        rows.append({"symbol": symbol, "date": d.isoformat(),
                     "price": price, "volume": 1_000_000})
    if spike_last is not None:
        rows[-1]["price"] = spike_last
    # Return desc by date (FMP's native ordering).
    return list(reversed(rows))


def _earnings_upcoming(symbol: str = "NVDA",
                       upcoming_date: str = "2026-05-20") -> list[dict]:
    return [
        {"symbol": symbol, "date": upcoming_date, "epsActual": None,
         "epsEstimated": 1.76, "revenueActual": None,
         "revenueEstimated": 78_000_000_000},
        {"symbol": symbol, "date": "2026-02-25", "epsActual": 1.62,
         "epsEstimated": 1.54, "revenueActual": None,
         "revenueEstimated": None},
    ]


def _news_payload(latest_date: str = "2026-05-11 12:34:00",
                  count_7d: int = 4, count_30d: int = 12) -> list[dict]:
    """Build a news payload with ``count_30d`` rows; ``count_7d`` of them are
    within the last 7 days relative to today=2026-05-12 (set via monkeypatch).
    """

    today = date(2026, 5, 12)
    rows: list[dict] = []
    for i in range(count_7d):
        d = today - timedelta(days=i)
        rows.append({
            "symbol": "NVDA",
            "publishedDate": f"{d.isoformat()} 12:00:00",
            "title": f"Headline {i} " + ("x" * 200),
            "publisher": "Foo Wire",
            "url": "https://example.test/foo",
        })
    for i in range(count_30d - count_7d):
        d = today - timedelta(days=8 + i)
        rows.append({
            "symbol": "NVDA",
            "publishedDate": f"{d.isoformat()} 09:00:00",
            "title": f"Older headline {i}",
            "publisher": "Bar Wire",
            "url": "https://example.test/bar",
        })
    rows[0]["publishedDate"] = latest_date
    rows[0]["title"] = "FRESH NEWS HEADLINE " + ("y" * 150)
    return rows


def _make_fake_get_json(*, earnings_empty: bool = False,
                        news_empty: bool = False,
                        price_empty: bool = False):
    def fake(endpoint: str, params: dict | None = None, timeout: int = 15):
        params = params or {}
        if endpoint == "/historical-price-eod/light":
            if price_empty:
                return []
            sym = params.get("symbol", "")
            if sym == "^GSPC":
                # SPX slight uptrend over 60d.
                return _price_series("^GSPC", days=60, start=5000.0,
                                     end=5150.0)
            # Per-stock: 60 bars, linear, last bar spiked up to drive RSI.
            return _price_series(sym, days=60, start=100.0, end=120.0,
                                 spike_last=125.0)
        if endpoint == "/earnings":
            if earnings_empty:
                return []
            return _earnings_upcoming(params.get("symbol", "NVDA"))
        if endpoint == "/news/stock":
            if news_empty:
                return []
            return _news_payload()
        return None

    return fake


@pytest.fixture(autouse=True)
def _reset_price_cache():
    fmp_source._PRICE_HIST_CACHE.clear()
    yield
    fmp_source._PRICE_HIST_CACHE.clear()


@pytest.fixture()
def fake_api_key(monkeypatch):
    monkeypatch.setattr(fmp_source, "_get_api_key", lambda: "TESTKEY")


# ---------------------------------------------------------------------------
# SUPPORTED_DP_IDS contract
# ---------------------------------------------------------------------------


def test_supported_dp_ids_includes_three_derived():
    expected = {"L5.surprise.preprice", "L6.priced.news_age",
                "L11.short.technical"}
    assert expected.issubset(fmp_source.SUPPORTED_DP_IDS)


# ---------------------------------------------------------------------------
# L11.short.technical happy path
# ---------------------------------------------------------------------------


def test_short_technical_emits_all_indicators(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_fake_get_json())
    rows = fmp_source.fetch_short_technical_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)

    assert len(rows) == 1
    ts_code, dp_id, payload_json, status, conf, source, ts = rows[0]
    assert ts_code == "NVDA.US"
    assert dp_id == "L11.short.technical"
    assert status == "Known"
    payload = json.loads(payload_json)

    # All indicator keys present.
    for k in ("ma20", "ma50", "ma_signal", "rsi14", "rsi_zone",
             "macd_line", "macd_signal", "macd_histogram", "macd_cross",
             "latest_close", "as_of"):
        assert k in payload, k

    # Numeric sanity on the synthetic series (linear 100 → 120 with spike).
    assert 100.0 < payload["ma20"] < 130.0
    assert 100.0 < payload["ma50"] < 125.0
    # latest_close = 125 > ma20 > ma50 in our fixture → above_above.
    assert payload["ma_signal"] == "above_above"
    # Strong uptrend + final spike → RSI is solidly bullish.
    assert payload["rsi14"] is not None
    assert payload["rsi14"] > 50.0
    assert payload["rsi_zone"] in ("neutral", "overbought")
    # MACD line positive when fast EMA > slow EMA on an uptrend.
    assert payload["macd_line"] is not None
    assert payload["macd_line"] > 0
    # payload < 1KB
    assert len(payload_json.encode("utf-8")) <= 1024


def test_short_technical_inactive_on_short_series(monkeypatch, fake_api_key):
    """Fewer than 50 bars → Inactive with reason flag."""

    def fake(endpoint, params=None, timeout=15):
        if endpoint == "/historical-price-eod/light":
            sym = params.get("symbol", "")
            return _price_series(sym, days=30, start=100.0, end=110.0)
        return None

    monkeypatch.setattr(fmp_source, "_get_json", fake)
    rows = fmp_source.fetch_short_technical_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    assert len(rows) == 1
    assert rows[0][3] == "Inactive"
    assert rows[0][4] == 0.0
    payload = json.loads(rows[0][2])
    assert payload.get("reason") == "price_series_too_short"


# ---------------------------------------------------------------------------
# L6.priced.news_age happy path / inactive
# ---------------------------------------------------------------------------


def test_news_age_emits_required_fields(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_fake_get_json())
    # Pin "today" so age calc is deterministic — done inside payload via
    # datetime.now() which we can't easily monkeypatch; instead build the
    # fixture so the latest news_date is 2026-05-11, and assert age >= 0.
    rows = fmp_source.fetch_news_age_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    assert len(rows) == 1
    ts_code, dp_id, payload_json, status, conf, source, ts = rows[0]
    assert dp_id == "L6.priced.news_age"
    assert status == "Known"
    payload = json.loads(payload_json)
    for k in ("latest_news_age_days", "news_count_7d", "news_count_30d",
             "latest_title", "latest_date"):
        assert k in payload, k
    assert isinstance(payload["latest_news_age_days"], int)
    assert payload["latest_news_age_days"] >= 0
    assert payload["news_count_30d"] >= payload["news_count_7d"]
    # Title truncated to 100 chars.
    assert len(payload["latest_title"]) <= 100


def test_news_age_inactive_when_no_news(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json",
                        _make_fake_get_json(news_empty=True))
    rows = fmp_source.fetch_news_age_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    assert len(rows) == 1
    assert rows[0][3] == "Inactive"
    assert rows[0][4] == 0.0


# ---------------------------------------------------------------------------
# L5.surprise.preprice happy path / inactive
# ---------------------------------------------------------------------------


def test_preprice_known_when_earnings_dated(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_fake_get_json())
    rows = fmp_source.fetch_preprice_surprise_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    assert len(rows) == 1
    ts_code, dp_id, payload_json, status, conf, source, ts = rows[0]
    assert dp_id == "L5.surprise.preprice"
    assert status == "Known"
    payload = json.loads(payload_json)
    for k in ("earnings_date", "run_up_5d_pct", "run_up_10d_pct",
             "run_up_20d_pct", "spx_relative_5d", "spx_relative_10d",
             "is_upcoming"):
        assert k in payload, k
    assert payload["earnings_date"] == "2026-05-20"
    assert payload["is_upcoming"] is True
    # Stock spike at the last bar → positive 5d run-up.
    assert payload["run_up_5d_pct"] is not None
    assert payload["run_up_5d_pct"] > 0
    # SPX is up on the same window but stock outperforms → relative > 0.
    assert payload["spx_relative_5d"] is not None
    assert payload["spx_relative_5d"] > 0


def test_preprice_inactive_when_no_earnings(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json",
                        _make_fake_get_json(earnings_empty=True))
    rows = fmp_source.fetch_preprice_surprise_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    assert len(rows) == 1
    assert rows[0][3] == "Inactive"
    assert rows[0][4] == 0.0


# ---------------------------------------------------------------------------
# Cache + non-US skip
# ---------------------------------------------------------------------------


def test_price_history_cache_avoids_duplicate_fetch(monkeypatch, fake_api_key):
    """The cached helper must hit /historical-price-eod/light only once per
    symbol within the TTL window even when called twice (preprice +
    technical)."""

    call_log: list[str] = []
    base = _make_fake_get_json()

    def counting(endpoint, params=None, timeout=15):
        if endpoint == "/historical-price-eod/light":
            call_log.append(params.get("symbol", ""))
        return base(endpoint, params, timeout)

    monkeypatch.setattr(fmp_source, "_get_json", counting)

    # Run both fetchers back-to-back; both walk the same NVDA series.
    fmp_source.fetch_preprice_surprise_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    fmp_source.fetch_short_technical_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    # NVDA hit at most once; ^GSPC hit at most once.
    assert call_log.count("NVDA") == 1, call_log
    assert call_log.count("^GSPC") == 1, call_log


def test_non_us_ts_codes_skipped_in_fetch_batch(monkeypatch, fake_api_key):
    """fetch_batch must skip 300750.SZ — the three new dp_ids never appear
    for non-US tickers."""

    monkeypatch.setattr(fmp_source, "_get_json", _make_fake_get_json())
    universe = [{"ts_code": "NVDA.US"}, {"ts_code": "300750.SZ"}]
    rows = fmp_source.fetch_batch(universe, 0)
    new_dp_ids = {"L5.surprise.preprice", "L6.priced.news_age",
                  "L11.short.technical"}
    for r in rows:
        ts_code, dp_id = r[0], r[1]
        if dp_id in new_dp_ids:
            assert ts_code == "NVDA.US", (ts_code, dp_id)


def test_fetch_batch_emits_three_dp_ids(monkeypatch, fake_api_key):
    """End-to-end: fetch_batch on a US ticker emits all three new dp_ids."""

    monkeypatch.setattr(fmp_source, "_get_json", _make_fake_get_json())
    rows = fmp_source.fetch_batch([{"ts_code": "NVDA.US"}], 0)
    dp_ids = {r[1] for r in rows if r[0] == "NVDA.US"}
    assert "L5.surprise.preprice" in dp_ids
    assert "L6.priced.news_age" in dp_ids
    assert "L11.short.technical" in dp_ids


# ---------------------------------------------------------------------------
# Indicator helper unit tests (pure-Python math)
# ---------------------------------------------------------------------------


def test_rsi_returns_100_on_pure_uptrend():
    closes = [100 + i for i in range(20)]
    assert fmp_source._rsi(closes, 14) == pytest.approx(100.0)


def test_rsi_returns_zero_on_pure_downtrend():
    closes = [100 - i for i in range(20)]
    assert fmp_source._rsi(closes, 14) == pytest.approx(0.0, abs=1e-6)


def test_rsi_none_when_too_short():
    assert fmp_source._rsi([1.0, 2.0, 3.0], 14) is None


def test_ema_seeds_with_sma():
    closes = [10.0] * 20
    out = fmp_source._ema(closes, 12)
    # Flat input → EMA stays at 10.
    assert out and all(abs(v - 10.0) < 1e-9 for v in out)


def test_macd_none_when_short():
    closes = [1.0] * 30
    assert fmp_source._macd(closes) is None


def test_macd_returns_tuple_on_long_series():
    closes = [100.0 + i * 0.5 for i in range(50)]
    out = fmp_source._macd(closes)
    assert out is not None
    macd_line, signal, hist = out
    # All three are finite floats and histogram = line - signal.
    assert isinstance(macd_line, float)
    assert isinstance(signal, float)
    assert abs(hist - (macd_line - signal)) < 1e-9
