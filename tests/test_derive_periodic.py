"""Integration tests for the weekly / monthly periodic technical-indicator
drivers (``derive.derive_all_weekly`` / ``derive_all_monthly``).

Both share the same private helper ``_derive_technicals_for_period`` and
emit only the 5 indicators that carry useful information at lower
frequency (MA / MACD / RSI / KDJ / BOLL) — ATR / OBV / VOL_MA are
intentionally absent because their scalar interpretation is
frequency-bound to the daily product. See ``derive._derive_technicals_for_period``
for the design rationale.

Strategy mirrors ``tests/test_derive_technicals.py``: monkey-patch the
two Tushare fetchers (``_fetch_a_share_weekly_history`` /
``_fetch_a_share_monthly_history``) and ``_get_pro_api`` so the test
runs offline and deterministically. Then assert all 5 dp_ids land in
``realtime_current`` with the right source string.
"""

from __future__ import annotations

import json
import sqlite3
from math import sin
from pathlib import Path

import pytest

from mvp20 import derive, storage


@pytest.fixture
def hot_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "hot.sqlite"
    storage.init_db(db_path)
    # Seed one ts_code so the weekly/monthly derive loop runs at least once.
    storage.upsert_realtime(db_path, [(
        "000001.SZ", "L0.demand.terminal",
        json.dumps({"scalar": 1.0}), "Known", 0.5,
        "test:seed", 1700000000,
    )])
    return db_path


def _synthetic_bars(n: int, start: float = 100.0, day_step: int = 7) -> list[dict]:
    """Ascending OHLCV bars suitable for ``technicals.compute_all``.

    ``day_step`` is used only to vary the date label so weekly vs monthly
    runs produce distinguishable ``as_of`` strings. Bar math itself is
    frequency-agnostic — the technicals lib treats every bar as one tick.
    """

    bars: list[dict] = []
    for i in range(n):
        price = start + i * 0.3 + 2.0 * sin(i / 4.0)
        # Cycle date-of-month so the synthetic stamp stays valid even for
        # weekly_step=7 across many bars. Format-only — not used by math.
        day = (i * day_step) % 28 + 1
        month = ((i * day_step) // 28) % 12 + 1
        year = 2024 + ((i * day_step) // (28 * 12))
        bars.append({
            "date": f"{year:04d}-{month:02d}-{day:02d}",
            "open": price - 0.2,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price,
            "vol": 1000.0 + i * 50,
        })
    return bars


# ---------------------------------------------------------------------------
# derive_all_weekly
# ---------------------------------------------------------------------------


def test_derive_all_weekly_emits_5_periodic_technicals(
    hot_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """60 synthetic weekly bars → all 5 ``L11.tech.*_weekly`` rows land."""

    bars = _synthetic_bars(60, day_step=7)
    monkeypatch.setattr(derive, "_get_pro_api", lambda: object())
    monkeypatch.setattr(
        derive, "_fetch_a_share_weekly_history",
        lambda pro, ts_code, weeks=120: bars,
    )

    summary = derive.derive_all_weekly(hot_db, history_weeks=60, limit_companies=1)
    assert summary["companies_processed"] == 1
    # 5 indicators × 1 company.
    assert summary["derived_rows"] >= 5

    conn = sqlite3.connect(f"file:{hot_db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT dp_id, value_json, data_status, source "
            "FROM realtime_current WHERE ts_code = ? "
            "AND source = 'derived:technical_indicators_weekly'",
            ("000001.SZ",),
        ).fetchall()
    finally:
        conn.close()

    emitted = {r[0] for r in rows}
    expected = {
        "L11.tech.ma_weekly",
        "L11.tech.macd_weekly",
        "L11.tech.rsi_weekly",
        "L11.tech.kdj_weekly",
        "L11.tech.boll_weekly",
    }
    missing = expected - emitted
    assert not missing, f"missing weekly tech emits: {missing}"

    # No daily / monthly dp_ids should be in this source bucket.
    bad = {dp for dp in emitted if not dp.endswith("_weekly")}
    assert not bad, f"weekly source bucket leaked non-weekly dp_ids: {bad}"

    by_dp = {r[0]: json.loads(r[1]) for r in rows}

    ma = by_dp["L11.tech.ma_weekly"]
    assert isinstance(ma.get("ma5"), (int, float))
    assert isinstance(ma.get("ma20"), (int, float))
    assert "n_bars" in ma and ma["n_bars"] == 60
    # Confidence on weekly should be lower than the 0.95 daily baseline.
    assert ma["confidence"] < 0.95
    assert ma["confidence"] > 0.5

    macd = by_dp["L11.tech.macd_weekly"]
    assert isinstance(macd.get("dif"), (int, float))
    assert isinstance(macd.get("dea"), (int, float))
    assert macd.get("cross") in (None, "bull", "bear")

    rsi_payload = by_dp["L11.tech.rsi_weekly"]
    assert isinstance(rsi_payload.get("rsi12"), (int, float))
    assert 0.0 <= rsi_payload["rsi12"] <= 100.0

    boll = by_dp["L11.tech.boll_weekly"]
    assert boll["upper"] > boll["mid"] > boll["lower"]


def test_derive_all_weekly_skips_atr_obv_volma(
    hot_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Weekly emit deliberately excludes ATR / OBV / VOL_MA — their scalar
    interpretation is calibrated against daily-trading frequency and
    consumers are wired up against the daily product."""

    bars = _synthetic_bars(60, day_step=7)
    monkeypatch.setattr(derive, "_get_pro_api", lambda: object())
    monkeypatch.setattr(
        derive, "_fetch_a_share_weekly_history",
        lambda pro, ts_code, weeks=120: bars,
    )
    derive.derive_all_weekly(hot_db, history_weeks=60, limit_companies=1)

    conn = sqlite3.connect(f"file:{hot_db}?mode=ro", uri=True)
    try:
        emitted = {
            r[0] for r in conn.execute(
                "SELECT dp_id FROM realtime_current "
                "WHERE ts_code = ? AND source = 'derived:technical_indicators_weekly'",
                ("000001.SZ",),
            ).fetchall()
        }
    finally:
        conn.close()

    for dp in (
        "L11.tech.atr_weekly",
        "L11.tech.obv_weekly",
        "L11.tech.vol_ma_weekly",
    ):
        assert dp not in emitted, f"unexpected weekly emit: {dp}"


# ---------------------------------------------------------------------------
# derive_all_monthly
# ---------------------------------------------------------------------------


def test_derive_all_monthly_emits_5_periodic_technicals(
    hot_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """36 synthetic monthly bars → all 5 ``L11.tech.*_monthly`` rows land."""

    bars = _synthetic_bars(36, day_step=28)
    monkeypatch.setattr(derive, "_get_pro_api", lambda: object())
    monkeypatch.setattr(
        derive, "_fetch_a_share_monthly_history",
        lambda pro, ts_code, months=36: bars,
    )

    summary = derive.derive_all_monthly(hot_db, history_months=36, limit_companies=1)
    assert summary["companies_processed"] == 1
    assert summary["derived_rows"] >= 5

    conn = sqlite3.connect(f"file:{hot_db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT dp_id, value_json, source "
            "FROM realtime_current WHERE ts_code = ? "
            "AND source = 'derived:technical_indicators_monthly'",
            ("000001.SZ",),
        ).fetchall()
    finally:
        conn.close()

    emitted = {r[0] for r in rows}
    expected = {
        "L11.tech.ma_monthly",
        "L11.tech.macd_monthly",
        "L11.tech.rsi_monthly",
        "L11.tech.kdj_monthly",
        "L11.tech.boll_monthly",
    }
    missing = expected - emitted
    assert not missing, f"missing monthly tech emits: {missing}"

    by_dp = {r[0]: json.loads(r[1]) for r in rows}

    ma = by_dp["L11.tech.ma_monthly"]
    assert ma["n_bars"] == 36
    # Monthly should be the most-stale tier — confidence below weekly.
    assert ma["confidence"] < 0.90
    assert ma["confidence"] > 0.4

    macd = by_dp["L11.tech.macd_monthly"]
    assert isinstance(macd.get("dif"), (int, float))
    assert isinstance(macd.get("dea"), (int, float))


def test_derive_all_monthly_too_few_bars_skips_macd(
    hot_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With <26 monthly bars MACD can't compute. The helper should silently
    skip MACD emit rather than upsert all-None garbage."""

    bars = _synthetic_bars(20, day_step=28)  # 20 < 26 → no MACD
    monkeypatch.setattr(derive, "_get_pro_api", lambda: object())
    monkeypatch.setattr(
        derive, "_fetch_a_share_monthly_history",
        lambda pro, ts_code, months=36: bars,
    )
    derive.derive_all_monthly(hot_db, history_months=20, limit_companies=1)

    conn = sqlite3.connect(f"file:{hot_db}?mode=ro", uri=True)
    try:
        emitted = {
            r[0] for r in conn.execute(
                "SELECT dp_id FROM realtime_current "
                "WHERE ts_code = ? AND source = 'derived:technical_indicators_monthly'",
                ("000001.SZ",),
            ).fetchall()
        }
    finally:
        conn.close()

    # MA / RSI / KDJ / BOLL might still emit (windows ≤ 20). MACD must not.
    assert "L11.tech.macd_monthly" not in emitted
    # At least MA / RSI should emit given 20 bars.
    assert "L11.tech.ma_monthly" in emitted


# ---------------------------------------------------------------------------
# Helper-level sanity (period_suffix routing)
# ---------------------------------------------------------------------------


def test_derive_technicals_for_period_returns_empty_for_empty_bars() -> None:
    """Empty input ⇒ empty emit list, no exception."""

    assert derive._derive_technicals_for_period([], "_weekly") == []
    assert derive._derive_technicals_for_period([], "_monthly") == []


def test_derive_technicals_for_period_uses_correct_source() -> None:
    """``period_suffix`` selects the source string."""

    bars = _synthetic_bars(40)
    weekly = derive._derive_technicals_for_period(bars, "_weekly")
    monthly = derive._derive_technicals_for_period(bars, "_monthly")
    assert all(src == "derived:technical_indicators_weekly" for _, _, src in weekly)
    assert all(src == "derived:technical_indicators_monthly" for _, _, src in monthly)
    # And the dp_ids carry the right suffix.
    assert all(dp.endswith("_weekly") for dp, _, _ in weekly)
    assert all(dp.endswith("_monthly") for dp, _, _ in monthly)
