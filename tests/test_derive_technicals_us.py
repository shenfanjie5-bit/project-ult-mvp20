"""Integration tests for derive.derive_all → technicals emission across
non-A-share markets (US + HK).

Identical structure to ``test_derive_technicals.py`` but exercises the
US (NVDA.US, FMP-backed) and HK (00700.HK, FMP-backed) branches of the
new market-aware fetcher dispatch in ``derive_all``. We monkey-patch the
fetchers so the test runs offline and deterministically.

Mock contract: ``_fetch_us_share_history`` / ``_fetch_hk_share_history``
return a dict shaped like ``_fetch_a_share_history`` —
``{"bars": [...], "close": [...], "turnover_rate": [], "pe_ttm": [], "pb": []}``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from mvp20 import derive, storage


def _synthetic_bars(n: int = 60, start: float = 100.0) -> list[dict]:
    """Ascending-by-date OHLCV bars suitable for technicals.compute_all."""

    bars = []
    for i in range(n):
        from math import sin
        price = start + i * 0.3 + 2.0 * sin(i / 4.0)
        bars.append({
            "date": f"2024-01-{i + 1:02d}",
            "open": price - 0.2,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price,
            "vol": 1000.0 + i * 50,
        })
    return bars


def _fake_history(bars: list[dict]) -> dict:
    return {
        "close": [b["close"] for b in reversed(bars)],
        "turnover_rate": [],
        "pe_ttm": [],
        "pb": [],
        "bars": bars,
    }


@pytest.fixture
def us_db(tmp_path: Path) -> Path:
    """Hot SQLite seeded with a single US-share ts_code."""

    db_path = tmp_path / "hot.sqlite"
    storage.init_db(db_path)
    storage.upsert_realtime(db_path, [(
        "NVDA.US", "L0.demand.terminal",
        json.dumps({"scalar": 1.0}), "Known", 0.5,
        "test:seed", 1700000000,
    )])
    return db_path


@pytest.fixture
def hk_db(tmp_path: Path) -> Path:
    """Hot SQLite seeded with a single HK-share ts_code."""

    db_path = tmp_path / "hot.sqlite"
    storage.init_db(db_path)
    storage.upsert_realtime(db_path, [(
        "00700.HK", "L0.demand.terminal",
        json.dumps({"scalar": 1.0}), "Known", 0.5,
        "test:seed", 1700000000,
    )])
    return db_path


def _assert_all_8_technicals_emitted(db_path: Path, ts_code: str) -> dict[str, dict]:
    """Read back the 8 L11.tech.* rows for ``ts_code`` and assert each is
    present + source-tagged correctly. Returns a ``{dp_id: payload}`` map
    for downstream spot-checks."""

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT dp_id, value_json, source FROM realtime_current "
            "WHERE ts_code = ? AND source = 'derived:technical_indicators'",
            (ts_code,),
        ).fetchall()
    finally:
        conn.close()

    emitted = {r[0] for r in rows}
    expected = {
        "L11.tech.ma", "L11.tech.macd", "L11.tech.rsi",
        "L11.tech.kdj", "L11.tech.boll", "L11.tech.vol_ma",
        "L11.tech.atr", "L11.tech.obv",
    }
    missing = expected - emitted
    assert not missing, f"missing emitted technicals for {ts_code}: {missing}"
    for _, _, src in rows:
        assert src == "derived:technical_indicators"
    return {r[0]: json.loads(r[1]) for r in rows}


def test_derive_all_emits_us_technicals(
    us_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``derive_all(a_share_only=False)`` should route NVDA.US through
    ``_fetch_us_share_history`` and emit all 8 L11.tech.* dp_ids."""

    bars = _synthetic_bars(60)
    fake = _fake_history(bars)
    # US does not need Tushare. Mock _get_pro_api so the function doesn't
    # try to load tushare / read env tokens.
    monkeypatch.setattr(derive, "_get_pro_api", lambda: None)
    monkeypatch.setattr(
        derive, "_fetch_us_share_history",
        lambda ts_code, days=90: fake,
    )
    # Belt-and-suspenders: if A-share path is wrongly taken, fail loudly.
    def _unexpected_a_share(*args, **kwargs):  # pragma: no cover
        raise AssertionError("A-share fetcher invoked for NVDA.US")
    monkeypatch.setattr(derive, "_fetch_a_share_history", _unexpected_a_share)

    summary = derive.derive_all(
        us_db, history_days=60, a_share_only=False, limit_companies=1,
    )
    assert summary["companies_processed"] == 1
    assert summary["derived_rows"] >= 8

    by_dp = _assert_all_8_technicals_emitted(us_db, "NVDA.US")

    # Spot-check a couple of shapes — same contract as the A-share test.
    ma = by_dp["L11.tech.ma"]
    assert isinstance(ma.get("ma5"), (int, float))
    assert ma.get("n_bars") == 60
    assert "confidence" in ma

    macd = by_dp["L11.tech.macd"]
    assert isinstance(macd.get("dif"), (int, float))

    rsi = by_dp["L11.tech.rsi"]
    assert 0.0 <= rsi["rsi12"] <= 100.0


def test_derive_all_emits_hk_technicals(
    hk_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same story for 00700.HK via ``_fetch_hk_share_history``. Asserts
    the HK branch fires and produces all 8 L11.tech.* rows offline."""

    bars = _synthetic_bars(60, start=300.0)
    fake = _fake_history(bars)
    monkeypatch.setattr(derive, "_get_pro_api", lambda: None)
    monkeypatch.setattr(
        derive, "_fetch_hk_share_history",
        lambda ts_code, days=90: fake,
    )
    def _unexpected_a_share(*args, **kwargs):  # pragma: no cover
        raise AssertionError("A-share fetcher invoked for 00700.HK")
    monkeypatch.setattr(derive, "_fetch_a_share_history", _unexpected_a_share)

    summary = derive.derive_all(
        hk_db, history_days=60, a_share_only=False, limit_companies=1,
    )
    assert summary["companies_processed"] == 1
    assert summary["derived_rows"] >= 8

    by_dp = _assert_all_8_technicals_emitted(hk_db, "00700.HK")
    boll = by_dp["L11.tech.boll"]
    assert boll["upper"] >= boll["mid"] >= boll["lower"]
    atr_payload = by_dp["L11.tech.atr"]
    assert isinstance(atr_payload.get("scalar"), (int, float))
    assert atr_payload["scalar"] > 0


def test_a_share_only_skips_us_hk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity: with ``a_share_only=True`` (default), a US ts_code in the
    universe is filtered out — no technicals emitted for NVDA.US."""

    db_path = tmp_path / "hot.sqlite"
    storage.init_db(db_path)
    storage.upsert_realtime(db_path, [(
        "NVDA.US", "L0.demand.terminal",
        json.dumps({"scalar": 1.0}), "Known", 0.5,
        "test:seed", 1700000000,
    )])

    monkeypatch.setattr(derive, "_get_pro_api", lambda: object())
    # If the US fetcher gets called under a_share_only=True, fail.
    def _unexpected_us(*args, **kwargs):  # pragma: no cover
        raise AssertionError("US fetcher invoked under a_share_only=True")
    monkeypatch.setattr(derive, "_fetch_us_share_history", _unexpected_us)

    summary = derive.derive_all(db_path, history_days=60, a_share_only=True)
    assert summary["companies_processed"] == 0
    assert summary["derived_rows"] == 0


def test_us_fetcher_strips_suffix_and_calls_fmp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_fetch_us_share_history`` should strip ``.US`` and forward the
    bare symbol to ``_fetch_price_history_cached``."""

    captured: dict[str, object] = {}

    def _fake_cached(symbol: str, lookback_days: int = 80):
        captured["symbol"] = symbol
        captured["lookback_days"] = lookback_days
        # Mimic FMP /historical-price-eod/light shape (desc by date).
        return [
            {"symbol": symbol, "date": "2024-03-02", "price": 101.0, "volume": 1000},
            {"symbol": symbol, "date": "2024-03-01", "price": 100.0, "volume": 900},
        ]

    monkeypatch.setattr(
        "mvp20.sources.fmp_source._fetch_price_history_cached", _fake_cached,
    )
    out = derive._fetch_us_share_history("NVDA.US", days=90)
    assert captured["symbol"] == "NVDA"
    # ``max(days, 80)`` policy → 90 here.
    assert captured["lookback_days"] == 90
    assert len(out["bars"]) == 2
    assert out["bars"][0]["date"] == "2024-03-01"  # ascending
    assert out["bars"][-1]["close"] == 101.0
    # Fallback OHLC mapping when only ``price`` is present.
    assert out["bars"][0]["high"] == 100.0
    assert out["bars"][0]["low"] == 100.0


def test_hk_fetcher_normalises_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``00700.HK`` → ``0700.HK`` (FMP wants 4-digit form)."""

    captured: dict[str, object] = {}

    def _fake_cached(symbol: str, lookback_days: int = 80):
        captured["symbol"] = symbol
        return [
            {"symbol": symbol, "date": "2024-03-02", "price": 320.0, "volume": 1000},
            {"symbol": symbol, "date": "2024-03-01", "price": 318.0, "volume": 900},
        ]

    monkeypatch.setattr(
        "mvp20.sources.fmp_source._fetch_price_history_cached", _fake_cached,
    )
    out = derive._fetch_hk_share_history("00700.HK", days=60)
    assert captured["symbol"] == "0700.HK"
    assert len(out["bars"]) == 2
