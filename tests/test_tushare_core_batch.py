"""Tests for the fast Tushare core collector path."""

from __future__ import annotations

import json
from typing import Any

from mvp20.sources import tushare_source


class _StubDF:
    def __init__(self, records: list[dict[str, Any]]):
        self._rows = list(records)

    def __len__(self) -> int:
        return len(self._rows)

    def __getitem__(self, key):
        if isinstance(key, list) and all(isinstance(v, bool) for v in key):
            return _StubDF([r for r, keep in zip(self._rows, key, strict=False) if keep])
        if key == "ts_code":
            return _Series([r.get("ts_code") for r in self._rows])
        if isinstance(key, list):
            return _StubDF([{k: r.get(k) for k in key} for r in self._rows])
        return _Series([r.get(key) for r in self._rows])

    def __iter__(self):
        return iter(self._rows)

    def to_dict(self, orient: str = "records") -> list[dict[str, Any]]:
        assert orient == "records"
        return [dict(r) for r in self._rows]


class _Series:
    def __init__(self, values):
        self._values = list(values)

    def isin(self, values):
        allowed = set(values)
        return [v in allowed for v in self._values]


class _StubPro:
    def daily_basic(self, **_kw):
        return _StubDF([
            {
                "ts_code": "000001.SZ",
                "trade_date": "20260526",
                "turnover_rate": 1.2,
                "volume_ratio": 0.9,
                "pe_ttm": 8.5,
                "pb": 0.7,
                "ps_ttm": 1.1,
            },
            {"ts_code": "AAPL.US", "trade_date": "20260526"},
        ])

    def moneyflow(self, **_kw):
        return _StubDF([
            {
                "ts_code": "000001.SZ",
                "trade_date": "20260526",
                "net_mf_amount": 10.0,
                "buy_lg_amount": 4.0,
                "sell_lg_amount": 1.0,
                "buy_elg_amount": 3.0,
                "sell_elg_amount": 2.0,
            },
        ])

    def hk_hold(self, **_kw):
        return _StubDF([
            {
                "ts_code": "000001.SZ",
                "trade_date": "20260525",
                "vol": 100.0,
                "ratio": 2.3,
            },
        ])


def test_fetch_core_batch_emits_fast_market_and_flow_rows(monkeypatch):
    monkeypatch.setattr(tushare_source, "_get_pro_api", lambda: _StubPro())
    rows = tushare_source.fetch_core_batch(
        [{"ts_code": "000001.SZ"}, {"ts_code": "AAPL.US"}],
        tick=0,
    )

    by_dp = {r[1]: r for r in rows}
    assert {
        "L6.mult.pe",
        "L6.mult.pb",
        "L6.mult.ps",
        "L7.trade.volume_turnover",
        "L7.flow.active_inflow",
        "L7.flow.passive_northbound",
    }.issubset(by_dp)
    assert by_dp["L6.mult.pe"][5] == "tushare:daily_basic"
    assert by_dp["L7.flow.active_inflow"][5] == "tushare:moneyflow"
    payload = json.loads(by_dp["L7.trade.volume_turnover"][2])
    assert payload["turnover_rate_pct"] == 1.2


def test_fetch_core_batch_pe_payload_carries_mcap_and_shares(monkeypatch):
    """L6.mult.pe payload should carry mcap + share count in base units.

    Tushare daily_basic reports total_mv in 万元 and total_share in 万股;
    the collector converts both to base units (×10000) so the snapshot-derive
    layer can compute EV/EBITDA and forward P/E.
    """

    class _MvPro(_StubPro):
        def daily_basic(self, **_kw):
            return _StubDF([
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260526",
                    "pe_ttm": 8.5,
                    "pb": 0.7,
                    "ps_ttm": 1.1,
                    "total_mv": 86585.0,      # 万元
                    "total_share": 1234.0,    # 万股
                },
            ])

    monkeypatch.setattr(tushare_source, "_get_pro_api", lambda: _MvPro())
    rows = tushare_source.fetch_core_batch([{"ts_code": "000001.SZ"}], tick=0)
    by_dp = {r[1]: r for r in rows}

    pe_payload = json.loads(by_dp["L6.mult.pe"][2])
    assert pe_payload["scalar"] == 8.5
    assert pe_payload["total_mv_cny"] == 86585.0 * 10000.0
    assert pe_payload["total_share"] == 1234.0 * 10000.0
    # mcap / shares should yield a sane per-share price.
    price = pe_payload["total_mv_cny"] / pe_payload["total_share"]
    assert price == 86585.0 / 1234.0
    # pb / ps payloads must NOT carry the mcap/share keys.
    pb_payload = json.loads(by_dp["L6.mult.pb"][2])
    assert "total_mv_cny" not in pb_payload
    assert "total_share" not in pb_payload


def test_fetch_core_batch_hk_hold_falls_back_to_recent_trade_day(monkeypatch):
    class _FallbackPro(_StubPro):
        def __init__(self):
            self.hk_hold_dates: list[str] = []

        def hk_hold(self, **kw):
            self.hk_hold_dates.append(kw["trade_date"])
            if len(self.hk_hold_dates) == 1:
                return _StubDF([])
            return _StubDF([
                {
                    "ts_code": "000001.SZ",
                    "trade_date": kw["trade_date"],
                    "vol": 100.0,
                    "ratio": 2.3,
                },
            ])

    pro = _FallbackPro()
    monkeypatch.setattr(tushare_source, "_get_pro_api", lambda: pro)

    rows = tushare_source.fetch_core_batch([{"ts_code": "000001.SZ"}], tick=0)

    northbound = [r for r in rows if r[1] == "L7.flow.passive_northbound"]
    assert len(northbound) == 1
    assert len(pro.hk_hold_dates) == 2


def test_fetch_report_rc_constituents_batch_filters_a_shares(monkeypatch):
    seen: dict[str, Any] = {}

    def fake_fetch(pro, codes, now, lookback_days=90):
        seen["pro"] = pro
        seen["codes"] = codes
        seen["lookback_days"] = lookback_days
        return [(
            "000001.SZ", "L5.fcst.eps_cf", "{}", "Known", 0.8,
            "tushare:report_rc", now,
        )]

    monkeypatch.setattr(tushare_source, "_get_pro_api", lambda: object())
    monkeypatch.setattr(tushare_source, "_fetch_a_share_report_rc", fake_fetch)

    rows = tushare_source.fetch_report_rc_constituents_batch(
        [{"ts_code": "000001.SZ"}, {"ts_code": "AAPL.US"}],
        tick=0,
        lookback_days=30,
    )

    assert rows[0][1] == "L5.fcst.eps_cf"
    assert seen["codes"] == ["000001.SZ"]
    assert seen["lookback_days"] == 30


def test_fetch_crowding_batch_emits_priced_crowdedness(monkeypatch):
    records = [
        {"ts_code": "000001.SZ", "trade_date": f"202605{i:02d}", "turnover_rate": float(i)}
        for i in range(1, 31)
    ]

    monkeypatch.setattr(tushare_source, "_get_pro_api", lambda: object())
    monkeypatch.setattr(
        tushare_source,
        "_get_daily_basic_history",
        lambda pro, ts_code, now: list(reversed(records)),
    )

    rows = tushare_source.fetch_crowding_batch(
        [{"ts_code": "000001.SZ"}, {"ts_code": "AAPL.US"}],
        tick=0,
    )

    assert len(rows) == 1
    ts_code, dp_id, value_json, status, _conf, source, _now = rows[0]
    assert ts_code == "000001.SZ"
    assert dp_id == "L6.priced.crowdedness"
    assert status == "Known"
    assert source == "tushare:daily_basic.history"
    payload = json.loads(value_json)
    assert payload["label"] in {"neutral", "elevated", "crowded", "extreme"}


def test_fetch_market_env_batch_isolates_sentinel_fetchers(monkeypatch):
    monkeypatch.setattr(tushare_source, "_get_pro_api", lambda: object())
    monkeypatch.setattr(
        tushare_source,
        "_emit_market_trend",
        lambda pro, now: [(
            "MARKET:CN", "L7.env.market_trend", "{}", "Known", 0.8,
            "tushare:index_daily", now,
        )],
    )
    monkeypatch.setattr(
        tushare_source,
        "_emit_market_style",
        lambda pro, now: [(
            "MARKET:CN", "L7.env.style", "{}", "Known", 0.75,
            "tushare:index_daily", now,
        )],
    )
    monkeypatch.setattr(
        tushare_source,
        "_emit_passive_northbound",
        lambda pro, now: [(
            "MARKET:CN", "L7.flow.passive_northbound", "{}", "Known", 0.8,
            "tushare:moneyflow_hsgt", now,
        )],
    )

    rows = tushare_source.fetch_market_env_batch([], tick=0)

    assert {r[1] for r in rows} == {
        "L7.env.market_trend",
        "L7.env.style",
        "L7.flow.passive_northbound",
    }
