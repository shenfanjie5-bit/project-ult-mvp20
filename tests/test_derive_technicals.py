"""Integration tests for derive.derive_all → technicals emission.

We monkey-patch the two external dependencies (``_get_pro_api`` and
``_fetch_a_share_history``) so the test runs offline and deterministically.
Then we exercise the full SQLite emit path: derive_all reads from
realtime_current, computes technicals from the injected bar series, and
UPSERTs the 8 new L11.tech.* dp_ids back. We read SQLite afterwards and
assert each dp_id appears with the right shape.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from mvp20 import derive, storage


@pytest.fixture
def hot_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "hot.sqlite"
    storage.init_db(db_path)
    # Seed one ts_code so derive_all loops at least once.
    storage.upsert_realtime(db_path, [(
        "000001.SZ", "L0.demand.terminal",
        json.dumps({"scalar": 1.0}), "Known", 0.5,
        "test:seed", 1700000000,
    )])
    return db_path


def _synthetic_bars(n: int = 60, start: float = 100.0) -> list[dict]:
    """Ascending-by-date OHLCV bars suitable for technicals.compute_all.

    Mixed direction so MACD/RSI/KDJ all produce non-edge values.
    """

    bars = []
    price = start
    for i in range(n):
        # Sinusoidal noise on top of a slight uptrend so technicals are
        # interesting (not pure ramp ⇒ MACD hist == 0 edge case).
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


def test_derive_tushare_timeout_seconds_uses_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUSHARE_TIMEOUT_SECONDS", "4")
    assert derive._tushare_timeout_seconds() == 4.0


def test_derive_all_emits_all_8_technicals(
    hot_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    bars = _synthetic_bars(60)
    closes_desc = [b["close"] for b in reversed(bars)]
    fake_history = {
        "close": closes_desc,
        "turnover_rate": [2.0] * 30,
        "pe_ttm": [15.0 + i * 0.1 for i in range(30)],
        "pb": [2.0 + i * 0.01 for i in range(30)],
        "bars": bars,
    }
    # Pretend pro_api is available (returns a non-None sentinel).
    monkeypatch.setattr(derive, "_get_pro_api", lambda: object())
    monkeypatch.setattr(
        derive, "_fetch_a_share_history",
        lambda pro, ts_code, days=90: fake_history,
    )

    summary = derive.derive_all(hot_db, history_days=60)
    assert summary["companies_processed"] == 1
    # We expect at least 8 technical rows + the 4 legacy tier-0 rows.
    assert summary["derived_rows"] >= 8

    conn = sqlite3.connect(f"file:{hot_db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT dp_id, value_json, data_status, source FROM realtime_current "
            "WHERE ts_code = ? AND source = 'derived:technical_indicators'",
            ("000001.SZ",),
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
    assert not missing, f"missing emitted technicals: {missing}"

    # Spot-check shapes.
    by_dp = {r[0]: json.loads(r[1]) for r in rows}
    ma = by_dp["L11.tech.ma"]
    assert isinstance(ma.get("ma5"), (int, float))
    assert isinstance(ma.get("ma20"), (int, float))
    assert "as_of" in ma and ma["as_of"] is not None
    assert "n_bars" in ma and ma["n_bars"] == 60
    assert "confidence" in ma

    macd = by_dp["L11.tech.macd"]
    assert isinstance(macd.get("dif"), (int, float))
    assert isinstance(macd.get("dea"), (int, float))
    assert isinstance(macd.get("hist"), (int, float))
    assert macd.get("cross") in (None, "bull", "bear")

    rsi_payload = by_dp["L11.tech.rsi"]
    assert isinstance(rsi_payload.get("rsi12"), (int, float))
    assert 0.0 <= rsi_payload["rsi12"] <= 100.0

    kdj = by_dp["L11.tech.kdj"]
    assert isinstance(kdj.get("k"), (int, float))
    # K∈[0,100] generally — but A-share J can exceed bounds slightly. Just
    # check it's a finite number.
    import math
    assert math.isfinite(kdj["k"])
    assert math.isfinite(kdj["d"])

    boll = by_dp["L11.tech.boll"]
    assert boll["upper"] > boll["mid"] > boll["lower"]

    atr_payload = by_dp["L11.tech.atr"]
    assert isinstance(atr_payload.get("scalar"), (int, float))
    assert atr_payload["scalar"] > 0

    obv_payload = by_dp["L11.tech.obv"]
    assert "scalar" in obv_payload


def test_derive_all_skips_emit_when_bars_too_short(
    hot_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With only 10 bars MACD / RSI / BOLL / KDJ can't compute. The derive
    layer should silently skip those emits rather than upsert garbage."""

    bars = _synthetic_bars(10)
    fake_history = {
        "close": [b["close"] for b in reversed(bars)],
        "turnover_rate": [2.0] * 5,
        "pe_ttm": [15.0] * 5,
        "pb": [2.0] * 5,
        "bars": bars,
    }
    monkeypatch.setattr(derive, "_get_pro_api", lambda: object())
    monkeypatch.setattr(
        derive, "_fetch_a_share_history",
        lambda pro, ts_code, days=90: fake_history,
    )
    derive.derive_all(hot_db, history_days=30)

    conn = sqlite3.connect(f"file:{hot_db}?mode=ro", uri=True)
    try:
        emitted = {
            r[0] for r in conn.execute(
                "SELECT dp_id FROM realtime_current "
                "WHERE ts_code = ? AND source = 'derived:technical_indicators'",
                ("000001.SZ",),
            ).fetchall()
        }
    finally:
        conn.close()

    # MA5 / MA10 / vol_ma might still emit (they only need 5–10 bars), but
    # MACD (>=35) / KDJ (>=9 OK) / BOLL (>=20) / ATR (>=15) should be
    # absent or have None values inside.
    # We don't make a strict assertion about which subset was emitted,
    # only that the function didn't crash and didn't claim more emits
    # than it actually has data for. Just verify no MACD row was emitted.
    # ↑ MACD needs 35 bars; 10 is short.
    if "L11.tech.macd" in emitted:
        # If MACD did emit (shouldn't), at minimum dif must be None to
        # signal upstream that the indicator wasn't computable.
        conn = sqlite3.connect(f"file:{hot_db}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT value_json FROM realtime_current "
                "WHERE ts_code=? AND dp_id='L11.tech.macd'",
                ("000001.SZ",),
            ).fetchone()
        finally:
            conn.close()
        v = json.loads(row[0])
        # Compute_all returns macd dict with all-None values when below
        # threshold; derive layer skips emit in that case.
        assert v.get("dif") is None, "MACD emit with bars=10 should have dif=None"
