"""Tests for the Bucket A append on ``mvp20.sources.akshare_source``.

Covers the 2 new per-A-share fetchers wired in this batch:

  * ``L8.cap.outflow_cut``  via ``fetch_l8_cap_outflow_cut``
    — backed by ``ak.stock_fund_flow_individual(symbol='5日排行')``.
  * ``L9.capital.etf_block`` via ``fetch_l9_capital_etf_block``
    — backed by ``ak.stock_dzjy_mrmx`` daily snapshots aggregated over
    the last 5 trade days.

All network calls are stubbed via monkeypatch so the suite stays
hermetic. Tests verify:

  - signal threshold logic (cumulative net outflow + stage % drawdown)
  - CN amount-string parsing (e.g. ``"-1.23亿"`` → -1.23e8)
  - HK / US ts_codes skip cleanly without crashing
  - upstream failures (akshare not installed, endpoint raises) → empty
    or Inactive rows, never a fetch_batch-level crash
  - per-fetcher 10-min TTL cache reuses prior result on the next call
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mvp20.sources import akshare_source


# ---------------------------------------------------------------------------
# Fixtures: a tiny fake universe + stubbed market-wide snapshots.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_bucket_a_caches() -> None:
    """The 2 module-level dicts memoise the last fetch; reset between tests
    so cache hits in one test don't bleed into another."""

    akshare_source._LAST_OUTFLOW_FETCH["ts"] = 0
    akshare_source._LAST_OUTFLOW_FETCH["rows"] = []
    akshare_source._LAST_OUTFLOW_FETCH["key"] = ""
    akshare_source._LAST_BLOCK_FETCH["ts"] = 0
    akshare_source._LAST_BLOCK_FETCH["rows"] = []
    akshare_source._LAST_BLOCK_FETCH["key"] = ""


# ---------------------------------------------------------------------------
# _parse_cn_amount
# ---------------------------------------------------------------------------


def test_parse_cn_amount_handles_yi_wan_and_plain() -> None:
    assert akshare_source._parse_cn_amount("1.23亿") == pytest.approx(1.23e8)
    assert akshare_source._parse_cn_amount("-4.44亿") == pytest.approx(-4.44e8)
    assert akshare_source._parse_cn_amount("2832.86万") == pytest.approx(2.83286e7)
    assert akshare_source._parse_cn_amount(-1e8) == pytest.approx(-1e8)
    assert akshare_source._parse_cn_amount(0) == 0.0


def test_parse_cn_amount_returns_none_for_bad_input() -> None:
    assert akshare_source._parse_cn_amount(None) is None
    assert akshare_source._parse_cn_amount("") is None
    assert akshare_source._parse_cn_amount("--") is None
    assert akshare_source._parse_cn_amount("abc") is None
    assert akshare_source._parse_cn_amount("1.2.3亿") is None


# ---------------------------------------------------------------------------
# L8.cap.outflow_cut — signal logic + snapshot lookup
# ---------------------------------------------------------------------------


def _make_outflow_snapshot(
    rows: list[tuple[str, str, str]],
) -> Any:
    """Return a fake DataFrame compatible with the akshare ``.to_dict``
    call path. Each input tuple is (代码, 资金流入净额, 阶段涨跌幅).
    """

    class _FakeDF:
        def __init__(self, recs: list[dict]) -> None:
            self._recs = recs

        def __len__(self) -> int:
            return len(self._recs)

        def to_dict(self, orient: str = "records") -> list[dict]:
            assert orient == "records"
            return list(self._recs)

    recs = [
        {
            "序号": i + 1,
            "股票代码": code,
            "股票简称": f"name{code}",
            "最新价": 100.0 + i,
            "阶段涨跌幅": pct,
            "连续换手率": "1.0%",
            "资金流入净额": amt,
        }
        for i, (code, amt, pct) in enumerate(rows)
    ]
    return _FakeDF(recs)


def test_outflow_signal_triggers_when_main_net_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """≥ 100M CNY 5d net outflow → Known + signal=True."""

    import akshare as ak

    fake = _make_outflow_snapshot([
        ("300750", "-1.5亿", "-5.0%"),  # main_net below threshold → signal
        ("600519", "1.2亿",  "3.0%"),   # net inflow → no signal
    ])
    monkeypatch.setattr(ak, "stock_fund_flow_individual",
                        lambda symbol="5日排行": fake)

    rows = akshare_source.fetch_l8_cap_outflow_cut(
        ["300750.SZ", "600519.SH"], now=1_700_000_000,
    )
    assert len(rows) == 2
    by_code = {r[0]: r for r in rows}

    cd, dp_id, vj, status, conf, source, ts = by_code["300750.SZ"]
    assert dp_id == "L8.cap.outflow_cut"
    assert status == "Known"
    assert conf == 0.65
    assert source.startswith("akshare:")
    payload = json.loads(vj)
    assert payload["signal"] is True
    assert payload["main_net_5d"] == pytest.approx(-1.5e8)
    assert payload["alert_severity"] == "WARN"

    payload2 = json.loads(by_code["600519.SH"][2])
    assert payload2["signal"] is False
    assert payload2["main_net_5d"] == pytest.approx(1.2e8)
    assert payload2["alert_severity"] is None
    assert by_code["600519.SH"][3] == "Inactive"  # no signal


def test_outflow_signal_triggers_on_stage_drawdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """5d stage drawdown ≤ -10% triggers the signal even when net flow
    is shallow / unparseable."""

    import akshare as ak

    fake = _make_outflow_snapshot([
        ("300750", "0.0万", "-12.5%"),  # stage_pct triggers
    ])
    monkeypatch.setattr(ak, "stock_fund_flow_individual",
                        lambda symbol="5日排行": fake)

    rows = akshare_source.fetch_l8_cap_outflow_cut(
        ["300750.SZ"], now=1_700_000_000,
    )
    assert len(rows) == 1
    payload = json.loads(rows[0][2])
    assert payload["signal"] is True
    assert payload["stage_pct_change_5d"] == pytest.approx(-12.5)
    assert rows[0][3] == "Known"


def test_outflow_emits_inactive_when_stock_missing_from_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stock absent from the THS 5日排行 → Inactive, no crash."""

    import akshare as ak

    fake = _make_outflow_snapshot([("000001", "-2亿", "-15.0%")])
    monkeypatch.setattr(ak, "stock_fund_flow_individual",
                        lambda symbol="5日排行": fake)

    rows = akshare_source.fetch_l8_cap_outflow_cut(
        ["300750.SZ"], now=1_700_000_000,
    )
    assert len(rows) == 1
    cd, dp_id, vj, status, _, _, _ = rows[0]
    assert status == "Inactive"
    assert json.loads(vj)["signal"] is False
    assert json.loads(vj)["reason"] == "not_in_ths_5d_rank_top"


def test_outflow_skips_hk_and_us_ts_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-A ts_codes silently drop — fetcher emits 0 rows for them."""

    import akshare as ak

    fake = _make_outflow_snapshot([("00700", "-5亿", "-20.0%")])
    monkeypatch.setattr(ak, "stock_fund_flow_individual",
                        lambda symbol="5日排行": fake)

    rows = akshare_source.fetch_l8_cap_outflow_cut(
        ["00700.HK", "AAPL.US"], now=1_700_000_000,
    )
    assert rows == []


def test_outflow_handles_endpoint_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the underlying akshare call raises (502 / JSONDecodeError),
    fetcher returns Inactive rows rather than propagating the exception."""

    import akshare as ak

    def _boom(symbol: str = "5日排行") -> Any:
        raise RuntimeError("simulated upstream HTML break")

    monkeypatch.setattr(ak, "stock_fund_flow_individual", _boom)
    rows = akshare_source.fetch_l8_cap_outflow_cut(
        ["300750.SZ"], now=1_700_000_000,
    )
    # With an empty snapshot every stock falls to the Inactive branch.
    assert len(rows) == 1
    assert rows[0][3] == "Inactive"
    payload = json.loads(rows[0][2])
    assert payload["signal"] is False


def test_outflow_uses_ttl_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second call inside the 10-min window must not re-hit akshare."""

    import akshare as ak

    call_count = {"n": 0}

    def _counting_call(symbol: str = "5日排行") -> Any:
        call_count["n"] += 1
        return _make_outflow_snapshot([("300750", "-2亿", "-3.0%")])

    monkeypatch.setattr(ak, "stock_fund_flow_individual", _counting_call)

    now = 1_700_000_000
    rows_a = akshare_source.fetch_l8_cap_outflow_cut(["300750.SZ"], now=now)
    rows_b = akshare_source.fetch_l8_cap_outflow_cut(["300750.SZ"], now=now + 60)
    assert rows_a == rows_b
    assert call_count["n"] == 1  # 2nd call served from cache


# ---------------------------------------------------------------------------
# L9.capital.etf_block — dzjy aggregation
# ---------------------------------------------------------------------------


class _FakeBlockDF:
    """Mini-DataFrame stand-in for ``ak.stock_dzjy_mrmx`` output."""

    def __init__(self, recs: list[dict]) -> None:
        self._recs = recs

    def __len__(self) -> int:
        return len(self._recs)

    def to_dict(self, orient: str = "records") -> list[dict]:
        assert orient == "records"
        return list(self._recs)


def _make_dzjy_row(code: str, price: float, vol: int, amt: float) -> dict:
    return {
        "序号": 1,
        "交易日期": "2026-05-13",
        "证券代码": code,
        "证券简称": f"name{code}",
        "成交价": price,
        "成交量": vol,
        "成交额": amt,
        "买方营业部": "机构专用",
        "卖方营业部": "broker",
    }


def test_block_aggregates_events_across_trade_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple daily snapshots accumulate per-stock event counts."""

    import akshare as ak

    # 3 trade days returning data; weekends / holidays return empty.
    call_log: list[str] = []
    day_data = {
        "20260513": [_make_dzjy_row("300750", 430.0, 100000, 4.3e7)],
        "20260512": [
            _make_dzjy_row("300750", 425.0, 50000, 2.125e7),
            _make_dzjy_row("600519", 1500.0, 1000, 1.5e6),
        ],
        "20260511": [_make_dzjy_row("600519", 1495.0, 800, 1.196e6)],
    }

    def _fake_dzjy(start_date: str, end_date: str) -> Any:
        call_log.append(start_date)
        recs = day_data.get(start_date)
        if recs is None:
            # Weekends produce NoneType subscript errors upstream — simulate.
            raise TypeError("'NoneType' object is not subscriptable")
        return _FakeBlockDF(recs)

    monkeypatch.setattr(ak, "stock_dzjy_mrmx", _fake_dzjy)

    rows = akshare_source.fetch_l9_capital_etf_block(
        ["300750.SZ", "600519.SH"],
        now=1_700_000_000,
        reference_date="20260513",
    )
    assert len(rows) == 2
    assert call_log[:3] == ["20260513", "20260512", "20260511"]
    by_code = {r[0]: r for r in rows}

    p1 = json.loads(by_code["300750.SZ"][2])
    assert p1["events_count"] == 2
    assert p1["total_amount_cny"] == pytest.approx(4.3e7 + 2.125e7)
    assert p1["events_sample"][0]["price"] in (430.0, 425.0)
    assert by_code["300750.SZ"][3] == "Known"
    assert by_code["300750.SZ"][4] == 0.7

    p2 = json.loads(by_code["600519.SH"][2])
    assert p2["events_count"] == 2
    assert p2["total_volume"] == pytest.approx(1000 + 800)


def test_block_emits_inactive_when_no_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stock with zero dzjy events in the 5-day window → Inactive."""

    import akshare as ak

    # One day with events for a different code; our target has zero.
    def _fake_dzjy(start_date: str, end_date: str) -> Any:
        return _FakeBlockDF([_make_dzjy_row("000001", 10.0, 100, 1000)])

    monkeypatch.setattr(ak, "stock_dzjy_mrmx", _fake_dzjy)

    rows = akshare_source.fetch_l9_capital_etf_block(
        ["300750.SZ"], now=1_700_000_000,
    )
    assert len(rows) == 1
    assert rows[0][3] == "Inactive"
    payload = json.loads(rows[0][2])
    assert payload["events_count"] == 0


def test_block_swallows_endpoint_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every call raising means the aggregator yields an empty map but
    the fetcher must still return Inactive rows, not crash."""

    import akshare as ak

    def _boom(start_date: str, end_date: str) -> Any:
        raise TypeError("simulated upstream None")

    monkeypatch.setattr(ak, "stock_dzjy_mrmx", _boom)

    rows = akshare_source.fetch_l9_capital_etf_block(
        ["300750.SZ"], now=1_700_000_000,
    )
    assert len(rows) == 1
    assert rows[0][3] == "Inactive"


def test_block_skips_non_a_share_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    import akshare as ak

    monkeypatch.setattr(ak, "stock_dzjy_mrmx",
                        lambda start_date, end_date: _FakeBlockDF([]))
    rows = akshare_source.fetch_l9_capital_etf_block(
        ["00700.HK", "AAPL.US"], now=1_700_000_000,
    )
    assert rows == []


def test_block_uses_ttl_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cache TTL identical to outflow path — second call within window
    serves cached rows."""

    import akshare as ak

    call_count = {"n": 0}

    def _counting(start_date: str, end_date: str) -> Any:
        call_count["n"] += 1
        return _FakeBlockDF(
            [_make_dzjy_row("300750", 430.0, 1000, 430000)],
        )

    monkeypatch.setattr(ak, "stock_dzjy_mrmx", _counting)

    now = 1_700_000_000
    rows_a = akshare_source.fetch_l9_capital_etf_block(
        ["300750.SZ"], now=now,
    )
    n_after_first = call_count["n"]
    rows_b = akshare_source.fetch_l9_capital_etf_block(
        ["300750.SZ"], now=now + 60,
    )
    assert rows_a == rows_b
    # Cache hit — counter unchanged.
    assert call_count["n"] == n_after_first


# ---------------------------------------------------------------------------
# Module-level guards
# ---------------------------------------------------------------------------


def test_outflow_no_crash_when_akshare_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the akshare import inside the snapshot helper raises ImportError,
    we degrade gracefully to all-Inactive rather than crashing."""

    import builtins
    real_import = builtins.__import__

    def _no_akshare(name: str, *args, **kwargs):
        if name == "akshare":
            raise ImportError("akshare not installed in this env")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_akshare)
    rows = akshare_source.fetch_l8_cap_outflow_cut(
        ["300750.SZ"], now=1_700_000_000,
    )
    assert len(rows) == 1
    assert rows[0][3] == "Inactive"


def test_block_no_crash_when_akshare_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins
    real_import = builtins.__import__

    def _no_akshare(name: str, *args, **kwargs):
        if name == "akshare":
            raise ImportError("akshare not installed in this env")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_akshare)
    rows = akshare_source.fetch_l9_capital_etf_block(
        ["300750.SZ"], now=1_700_000_000,
    )
    assert len(rows) == 1
    assert rows[0][3] == "Inactive"


def test_bucket_a_dp_ids_registered_in_supported_set() -> None:
    """Sanity: the 2 new dp_ids must appear in both TIER1 and SUPPORTED."""

    assert "L8.cap.outflow_cut" in akshare_source.TIER1_DP_IDS
    assert "L9.capital.etf_block" in akshare_source.TIER1_DP_IDS
    assert "L8.cap.outflow_cut" in akshare_source.SUPPORTED_DP_IDS
    assert "L9.capital.etf_block" in akshare_source.SUPPORTED_DP_IDS
