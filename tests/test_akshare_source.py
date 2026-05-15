"""Tests for ``mvp20.sources.akshare_source``.

Network/akshare calls are stubbed via monkeypatch so the test suite stays
hermetic. The point of these tests is to lock down:

  * ``SUPPORTED_DP_IDS`` covers the Tier-1 dp_ids the collector wires.
  * ``fetch_batch`` returns the standard 7-tuple shape understood by
    ``mvp20.storage.upsert_realtime``.
  * HK / US ts_codes are skipped (akshare source is A-share-only today).
  * One endpoint failing (e.g. announcement scraping) does not kill the
    remaining fetchers — partial output is still useful.
"""

from __future__ import annotations

import json

import pytest

from mvp20.sources import akshare_source


# ---------------------------------------------------------------------------
# SUPPORTED_DP_IDS contract
# ---------------------------------------------------------------------------


def test_supported_dp_ids_covers_tier1() -> None:
    expected_tier1 = {
        "L9.event.intraday_news",
        "L9.event.intraday_announcement",
        "L7.mood.media_social",
        "L9.media.social_buzz",
        "L7.mood.theme",
        # Bucket A append (per A-share fund-flow + block-trade signals).
        "L8.cap.outflow_cut",
        "L9.capital.etf_block",
    }
    assert expected_tier1.issubset(akshare_source.SUPPORTED_DP_IDS)
    assert expected_tier1 == akshare_source.TIER1_DP_IDS


def test_supported_dp_ids_covers_market_level() -> None:
    # The MARKET:CN-keyed CLS telegraph buckets — see ``MARKET_LEVEL_DP_IDS``.
    expected_market = {
        "L9.media.report",
        "L9.industry.policy_change",
        "L9.industry.compete_risk",
    }
    assert expected_market.issubset(akshare_source.SUPPORTED_DP_IDS)
    assert expected_market == akshare_source.MARKET_LEVEL_DP_IDS


def test_supported_dp_ids_includes_tier2_stubs() -> None:
    # Tier-2 stubs are declared so collector can list akshare as a
    # primary-source hint, even though the fetcher is a TODO.
    assert "L0.cost.raw_material" in akshare_source.SUPPORTED_DP_IDS
    assert "L0.sentiment.sector_heat" in akshare_source.SUPPORTED_DP_IDS


# ---------------------------------------------------------------------------
# ts_code helpers
# ---------------------------------------------------------------------------


def test_to_a_share_code_strips_suffix() -> None:
    assert akshare_source.to_a_share_code("300750.SZ") == "300750"
    assert akshare_source.to_a_share_code("600519.SH") == "600519"
    assert akshare_source.to_a_share_code("832735.BJ") == "832735"


def test_to_a_share_code_returns_none_for_non_a_share() -> None:
    assert akshare_source.to_a_share_code("00700.HK") is None
    assert akshare_source.to_a_share_code("AAPL.US") is None
    assert akshare_source.to_a_share_code("") is None


def test_to_a_share_em_symbol_adds_prefix() -> None:
    assert akshare_source.to_a_share_em_symbol("300750.SZ") == "SZ300750"
    assert akshare_source.to_a_share_em_symbol("600519.SH") == "SH600519"
    assert akshare_source.to_a_share_em_symbol("832735.BJ") == "BJ832735"
    assert akshare_source.to_a_share_em_symbol("00700.HK") is None


# ---------------------------------------------------------------------------
# fetch_batch shape
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_universe() -> list[dict]:
    return [
        {"ts_code": "300750.SZ", "name": "宁德时代"},
        {"ts_code": "600519.SH", "name": "贵州茅台"},
        {"ts_code": "00700.HK",  "name": "腾讯"},     # skipped
        {"ts_code": "AAPL.US",   "name": "Apple"},     # skipped
    ]


def _stub_intraday_news(a_codes, now, top_n_per_stock=5, sleep_s=0.0):
    return [
        (ts, "L9.event.intraday_news",
         json.dumps({"count_24h": 3, "as_of": "2026-05-12T00:00:00+08:00"}),
         "Known", 0.6, "akshare:em_news", now)
        for ts in a_codes
    ]


def _stub_intraday_announcement(a_codes, now, top_n_per_stock=5, sleep_s=0.0):
    return [
        (ts, "L9.event.intraday_announcement",
         json.dumps({"count_recent": 2, "as_of": "2026-05-12T00:00:00+08:00"}),
         "Known", 0.65, "akshare:stock_individual_notice_report", now)
        for ts in a_codes
    ]


def _stub_media_social_theme(a_codes, now, sleep_s=0.0):
    rows = []
    for ts in a_codes:
        rows.append((ts, "L7.mood.media_social",
                     json.dumps({"rank_overall": 10}),
                     "Known", 0.55, "akshare:em", now))
        rows.append((ts, "L7.mood.theme",
                     json.dumps({"concept_count": 3}),
                     "Known", 0.55, "akshare:em", now))
    return rows


def _stub_social_buzz(a_codes, now):
    return [
        (ts, "L9.media.social_buzz",
         json.dumps({"in_xq_top_buzz": True, "follow_count": 1000}),
         "Known", 0.55, "akshare:xq_hot", now)
        for ts in a_codes
    ]


def _stub_l8_outflow(a_codes, now):
    return [
        (ts, "L8.cap.outflow_cut",
         json.dumps({"signal": True, "main_net_5d": -2.5e8}),
         "Known", 0.65, "akshare:stock_fund_flow_individual.5d", now)
        for ts in a_codes
    ]


def _stub_l9_block(a_codes, now):
    return [
        (ts, "L9.capital.etf_block",
         json.dumps({"events_count": 0}),
         "Inactive", 0.5, "akshare:stock_dzjy_mrmx", now)
        for ts in a_codes
    ]


def _stub_cls_telegraph(now):
    """3-row MARKET:CN stub mirroring the real ``fetch_cls_telegraph_batch``."""

    return [
        ("MARKET:CN", "L9.media.report",
         json.dumps({"count_24h": 5, "top_headlines": []}),
         "Known", 0.6, "akshare:stock_info_global_cls", now),
        ("MARKET:CN", "L9.industry.policy_change",
         json.dumps({"count_24h": 1, "top_headlines": []}),
         "Known", 0.55, "akshare:stock_info_global_cls", now),
        ("MARKET:CN", "L9.industry.compete_risk",
         json.dumps({"count_24h": 1, "top_headlines": []}),
         "Known", 0.55, "akshare:stock_info_global_cls", now),
    ]


def _stub_x2_empty(_now):
    """No-op for the 3 X2 industry-level batches (raw_material /
    energy_logistics / sector_heat). These hit live akshare endpoints
    when un-stubbed and would slow / flake the test."""

    return []


def _patch_x2_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(akshare_source, "fetch_raw_material_batch",
                        _stub_x2_empty)
    monkeypatch.setattr(akshare_source, "fetch_energy_logistics_batch",
                        _stub_x2_empty)
    monkeypatch.setattr(akshare_source, "fetch_sector_heat_batch",
                        _stub_x2_empty)


def test_fetch_batch_emits_seven_tuples_for_a_share_only(
    fake_universe: list[dict], monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(akshare_source, "fetch_intraday_news",
                        _stub_intraday_news)
    monkeypatch.setattr(akshare_source, "fetch_intraday_announcement",
                        _stub_intraday_announcement)
    monkeypatch.setattr(akshare_source, "fetch_media_social_and_theme",
                        _stub_media_social_theme)
    monkeypatch.setattr(akshare_source, "fetch_social_buzz",
                        _stub_social_buzz)
    monkeypatch.setattr(akshare_source, "fetch_l8_cap_outflow_cut",
                        _stub_l8_outflow)
    monkeypatch.setattr(akshare_source, "fetch_l9_capital_etf_block",
                        _stub_l9_block)
    monkeypatch.setattr(akshare_source, "fetch_cls_telegraph_batch",
                        _stub_cls_telegraph)
    _patch_x2_batches(monkeypatch)

    rows = akshare_source.fetch_batch(fake_universe, tick=0)

    assert rows, "fetch_batch must emit at least one row"
    # 2 A-share × (news + announcement + 2 mood + buzz + 2 bucket-A) + 3 MARKET:CN = 17
    assert len(rows) == 17

    # Every row is a 7-tuple in the expected shape
    valid_keys = {"300750.SZ", "600519.SH", "MARKET:CN"}
    seen_dp_ids: set[str] = set()
    for row in rows:
        assert len(row) == 7
        ts_code, dp_id, value_json, status, conf, source, updated_at = row
        assert ts_code in valid_keys  # HK/US filtered out, MARKET:CN allowed
        assert dp_id in (akshare_source.TIER1_DP_IDS
                         | akshare_source.MARKET_LEVEL_DP_IDS)
        # value must be JSON string (storage layer needs str/dict)
        json.loads(value_json)
        assert status in {"Known", "Inactive"}
        assert 0.0 <= conf <= 1.0
        assert source.startswith("akshare:")
        assert isinstance(updated_at, int) and updated_at > 0
        seen_dp_ids.add(dp_id)
    # All Tier-1 + 3 market-level dp_ids represented
    assert seen_dp_ids == (akshare_source.TIER1_DP_IDS
                           | akshare_source.MARKET_LEVEL_DP_IDS)


def test_fetch_batch_skips_when_no_a_share_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-stock fetchers are skipped but MARKET:CN catalysts still run."""

    monkeypatch.setattr(akshare_source, "fetch_intraday_news",
                        _stub_intraday_news)
    monkeypatch.setattr(akshare_source, "fetch_intraday_announcement",
                        _stub_intraday_announcement)
    monkeypatch.setattr(akshare_source, "fetch_media_social_and_theme",
                        _stub_media_social_theme)
    monkeypatch.setattr(akshare_source, "fetch_social_buzz",
                        _stub_social_buzz)
    monkeypatch.setattr(akshare_source, "fetch_l8_cap_outflow_cut",
                        _stub_l8_outflow)
    monkeypatch.setattr(akshare_source, "fetch_l9_capital_etf_block",
                        _stub_l9_block)
    monkeypatch.setattr(akshare_source, "fetch_cls_telegraph_batch",
                        _stub_cls_telegraph)
    _patch_x2_batches(monkeypatch)

    rows = akshare_source.fetch_batch(
        [{"ts_code": "AAPL.US"}, {"ts_code": "00700.HK"}], tick=1,
    )
    # No A-share constituents → Tier-1 fetchers skipped, but the
    # market-level CLS telegraph still emits its 3 MARKET:CN rows.
    assert len(rows) == 3
    assert {r[0] for r in rows} == {"MARKET:CN"}
    assert {r[1] for r in rows} == akshare_source.MARKET_LEVEL_DP_IDS


def test_fetch_batch_isolates_per_fetcher_failures(
    fake_universe: list[dict], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One fetcher raising must not lose the output of the others."""

    def boom(*_a, **_k):
        raise RuntimeError("simulated upstream HTML break")

    monkeypatch.setattr(akshare_source, "fetch_intraday_news", boom)
    monkeypatch.setattr(akshare_source, "fetch_intraday_announcement",
                        _stub_intraday_announcement)
    monkeypatch.setattr(akshare_source, "fetch_media_social_and_theme",
                        _stub_media_social_theme)
    monkeypatch.setattr(akshare_source, "fetch_social_buzz",
                        _stub_social_buzz)
    monkeypatch.setattr(akshare_source, "fetch_l8_cap_outflow_cut",
                        _stub_l8_outflow)
    monkeypatch.setattr(akshare_source, "fetch_l9_capital_etf_block",
                        _stub_l9_block)
    monkeypatch.setattr(akshare_source, "fetch_cls_telegraph_batch",
                        _stub_cls_telegraph)
    _patch_x2_batches(monkeypatch)

    rows = akshare_source.fetch_batch(fake_universe, tick=2)
    dp_ids = {r[1] for r in rows}
    # intraday_news skipped due to RuntimeError, others still flowed.
    assert "L9.event.intraday_news" not in dp_ids
    assert {"L9.event.intraday_announcement", "L7.mood.media_social",
            "L7.mood.theme", "L9.media.social_buzz"}.issubset(dp_ids)
    # CLS catalysts also still flowed.
    assert akshare_source.MARKET_LEVEL_DP_IDS.issubset(dp_ids)


# ---------------------------------------------------------------------------
# health_check uses the akshare module that's installed in the test env
# (akshare is a hard dependency in pyproject.toml). We mock at the module
# attribute level so the test never hits the network.
# ---------------------------------------------------------------------------


def test_health_check_returns_ok_when_any_probe_responds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import akshare as ak

    class _FakeDF:
        def __len__(self):
            return 100

    # First probe returns rows → ok=True; second probe never gets called.
    monkeypatch.setattr(ak, "stock_news_main_cx", lambda: _FakeDF())
    def _should_not_be_called():
        raise AssertionError("second probe should be skipped on first success")
    monkeypatch.setattr(ak, "stock_hot_rank_em", _should_not_be_called)

    result = akshare_source.health_check()
    assert result["ok"] is True
    assert result["probe_endpoint"] == "stock_news_main_cx"
    assert result["probe_rows"] == 100
    assert result["tier1_count"] == len(akshare_source.TIER1_DP_IDS)


def test_health_check_falls_through_to_second_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the first probe fails or returns 0 rows, the second is tried."""

    import akshare as ak

    class _FakeDF:
        def __init__(self, n): self._n = n
        def __len__(self): return self._n

    def _first_fails():
        raise RuntimeError("simulated CDN outage")

    monkeypatch.setattr(ak, "stock_news_main_cx", _first_fails)
    monkeypatch.setattr(ak, "stock_hot_rank_em", lambda: _FakeDF(50))

    result = akshare_source.health_check()
    assert result["ok"] is True
    assert result["probe_endpoint"] == "stock_hot_rank_em"
    assert result["probe_rows"] == 50


def test_health_check_returns_not_ok_when_all_probes_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import akshare as ak

    def _raise():
        raise RuntimeError("simulated CDN outage")

    monkeypatch.setattr(ak, "stock_news_main_cx", _raise)
    monkeypatch.setattr(ak, "stock_hot_rank_em", _raise)
    result = akshare_source.health_check()
    assert result["ok"] is False
    assert "simulated CDN outage" in result["error"]


# ---------------------------------------------------------------------------
# X2 industry-level fetchers: raw_material / energy_logistics / sector_heat
# (declared-but-silent pre-X2). All upstream akshare calls are monkeypatched
# so the suite stays hermetic.
# ---------------------------------------------------------------------------


class _AkStubDF:
    """Tiny DataFrame stand-in: ``len``, ``to_dict(orient='records')``."""

    def __init__(self, rows):
        self._rows = list(rows)

    def __len__(self):
        return len(self._rows)

    def to_dict(self, orient="records"):
        return list(self._rows)


@pytest.fixture(autouse=True)
def _reset_x2_caches() -> None:
    """Clear the X2 module-level TTL caches between tests."""

    akshare_source._LAST_COMMODITY_FETCH["ts"] = 0
    akshare_source._LAST_COMMODITY_FETCH["rows"] = []
    akshare_source._LAST_LOGISTICS_FETCH["ts"] = 0
    akshare_source._LAST_LOGISTICS_FETCH["rows"] = []
    akshare_source._LAST_SECTOR_HEAT_FETCH["ts"] = 0
    akshare_source._LAST_SECTOR_HEAT_FETCH["rows"] = []
    yield
    akshare_source._LAST_COMMODITY_FETCH["ts"] = 0
    akshare_source._LAST_COMMODITY_FETCH["rows"] = []
    akshare_source._LAST_LOGISTICS_FETCH["ts"] = 0
    akshare_source._LAST_LOGISTICS_FETCH["rows"] = []
    akshare_source._LAST_SECTOR_HEAT_FETCH["ts"] = 0
    akshare_source._LAST_SECTOR_HEAT_FETCH["rows"] = []


def test_fetch_raw_material_batch_emits_industry_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``L0.cost.raw_material`` emits one INDUSTRY:<id> row per mapped slug."""

    import akshare as ak

    # Stub the industry yaml + active set so the test is deterministic.
    monkeypatch.setattr(
        akshare_source, "_load_industry_yaml",
        lambda fn: {
            "NONFERROUS_METALS": ["CU0", "AL0"],
            "STORAGE_GRID": ["LC0"],
        } if fn == "industry_to_commodity.yaml" else {},
    )
    monkeypatch.setattr(
        akshare_source, "_active_industry_ids_akshare",
        lambda: ["NONFERROUS_METALS", "STORAGE_GRID"],
    )

    def fake_futures_main_sina(symbol):
        # 2 rows per commodity, ascending date, so latest is last row.
        prices = {
            "CU0": (100.0, 105.0),  # +5% delta
            "AL0": (200.0, 198.0),  # -1% delta
            "LC0": (50.0, 52.0),    # +4% delta
        }
        if symbol not in prices:
            raise RuntimeError(f"unmapped {symbol}")
        prev, cur = prices[symbol]
        return _AkStubDF([
            {"日期": "2026-05-08", "收盘价": prev,
             "开盘价": prev, "最高价": prev, "最低价": prev,
             "成交量": 1, "持仓量": 1, "动态结算价": prev},
            {"日期": "2026-05-12", "收盘价": cur,
             "开盘价": cur, "最高价": cur, "最低价": cur,
             "成交量": 1, "持仓量": 1, "动态结算价": cur},
        ])

    monkeypatch.setattr(ak, "futures_main_sina", fake_futures_main_sina)

    rows = akshare_source.fetch_raw_material_batch(now=1700000000)
    assert len(rows) == 2
    industries = sorted(r[0] for r in rows)
    assert industries == ["INDUSTRY:NONFERROUS_METALS",
                          "INDUSTRY:STORAGE_GRID"]
    for r in rows:
        ts_code, dp_id, val, status, conf, source, ts = r
        assert dp_id == "L0.cost.raw_material"
        assert status == "Known"
        assert source == "akshare:futures_main_sina"
        assert ts == 1700000000
        payload = json.loads(val)
        assert "commodities" in payload
        assert payload["avg_pct_change"] is not None
        assert payload["symbols_resolved"] >= 1


def test_fetch_raw_material_batch_skips_unmapped_industries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Industries with ``null`` / missing mapping emit nothing (no half rows)."""

    monkeypatch.setattr(
        akshare_source, "_load_industry_yaml",
        lambda _fn: {
            "AI_COMPUTE": None,
            "HK_CN_INTERNET": None,
        },
    )
    monkeypatch.setattr(
        akshare_source, "_active_industry_ids_akshare",
        lambda: ["AI_COMPUTE", "HK_CN_INTERNET"],
    )
    rows = akshare_source.fetch_raw_material_batch(now=1700000000)
    assert rows == []


def test_fetch_energy_logistics_batch_emits_market_cn_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``L0.cost.energy_logistics`` returns a single MARKET:CN row with
    crude_pct + bdi_pct payload."""

    import akshare as ak

    def fake_futures(symbol):
        assert symbol == "SC0"
        return _AkStubDF([
            {"日期": "2026-05-08", "收盘价": 600.0,
             "开盘价": 600, "最高价": 600, "最低价": 600,
             "成交量": 1, "持仓量": 1, "动态结算价": 600},
            {"日期": "2026-05-12", "收盘价": 612.0,  # +2% delta
             "开盘价": 612, "最高价": 612, "最低价": 612,
             "成交量": 1, "持仓量": 1, "动态结算价": 612},
        ])

    def fake_bdi():
        return _AkStubDF([
            {"日期": "2026-05-08", "最新值": 2900,
             "涨跌幅": 0, "近3月涨跌幅": 0, "近6月涨跌幅": 0,
             "近1年涨跌幅": 0, "近2年涨跌幅": 0, "近3年涨跌幅": 0},
            {"日期": "2026-05-12", "最新值": 3000,   # +3.4% delta
             "涨跌幅": 0, "近3月涨跌幅": 0, "近6月涨跌幅": 0,
             "近1年涨跌幅": 0, "近2年涨跌幅": 0, "近3年涨跌幅": 0},
        ])

    monkeypatch.setattr(ak, "futures_main_sina", fake_futures)
    monkeypatch.setattr(ak, "macro_shipping_bdi", fake_bdi)

    rows = akshare_source.fetch_energy_logistics_batch(now=1700000000)
    assert len(rows) == 1
    ts_code, dp_id, val, status, conf, source, ts = rows[0]
    assert ts_code == "MARKET:CN"
    assert dp_id == "L0.cost.energy_logistics"
    assert status == "Known"
    assert ts == 1700000000
    payload = json.loads(val)
    assert payload["crude_pct"] == 2.0
    assert abs(payload["bdi_pct"] - 3.448) < 0.01
    assert payload["crude_close_cny_per_bbl"] == 612.0
    assert payload["bdi_close"] == 3000.0


def test_fetch_energy_logistics_batch_emits_partial_on_one_source_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If BDI fails but crude succeeds, the row still emits with
    bdi_pct=None (not skipping the whole batch)."""

    import akshare as ak

    def fake_futures(symbol):
        return _AkStubDF([
            {"日期": "2026-05-08", "收盘价": 600.0,
             "开盘价": 600, "最高价": 600, "最低价": 600,
             "成交量": 1, "持仓量": 1, "动态结算价": 600},
            {"日期": "2026-05-12", "收盘价": 612.0,
             "开盘价": 612, "最高价": 612, "最低价": 612,
             "成交量": 1, "持仓量": 1, "动态结算价": 612},
        ])

    def fake_bdi_fail():
        raise RuntimeError("akshare BDI 502")

    monkeypatch.setattr(ak, "futures_main_sina", fake_futures)
    monkeypatch.setattr(ak, "macro_shipping_bdi", fake_bdi_fail)

    rows = akshare_source.fetch_energy_logistics_batch(now=1700000000)
    assert len(rows) == 1
    payload = json.loads(rows[0][2])
    assert payload["crude_pct"] == 2.0
    assert payload["bdi_pct"] is None


def test_fetch_sector_heat_batch_emits_industry_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``L0.sentiment.sector_heat`` aggregates THS sector boards per
    industry from ``stock_board_industry_summary_ths``."""

    import akshare as ak

    monkeypatch.setattr(
        akshare_source, "_load_industry_yaml",
        lambda fn: {
            "SEMI_EQUIPMENT": ["半导体"],
            "AI_COMPUTE": ["软件开发", "计算机设备"],
        } if fn == "industry_to_em_board.yaml" else {},
    )
    monkeypatch.setattr(
        akshare_source, "_active_industry_ids_akshare",
        lambda: ["SEMI_EQUIPMENT", "AI_COMPUTE"],
    )

    def fake_summary_ths():
        return _AkStubDF([
            {"序号": 1, "板块": "半导体", "涨跌幅": 0.35,
             "总成交量": 4227.42, "总成交额": 3900.96, "净流入": 10.5,
             "上涨家数": 80, "下跌家数": 20, "均价": 92.28,
             "领涨股": "芯源微", "领涨股-最新价": 273.74,
             "领涨股-涨跌幅": 15.76},
            {"序号": 2, "板块": "软件开发", "涨跌幅": 1.20,
             "总成交量": 1000.0, "总成交额": 500.0, "净流入": 5.2,
             "上涨家数": 50, "下跌家数": 10, "均价": 45.0,
             "领涨股": "alpha", "领涨股-最新价": 100.0,
             "领涨股-涨跌幅": 9.95},
            {"序号": 3, "板块": "计算机设备", "涨跌幅": 0.85,
             "总成交量": 600.0, "总成交额": 300.0, "净流入": 1.5,
             "上涨家数": 30, "下跌家数": 25, "均价": 35.0,
             "领涨股": "beta", "领涨股-最新价": 50.0,
             "领涨股-涨跌幅": 5.0},
            # Unrelated board, should NOT show up in any payload
            {"序号": 4, "板块": "白酒", "涨跌幅": -0.4,
             "总成交量": 200.0, "总成交额": 200.0, "净流入": -3.0,
             "上涨家数": 5, "下跌家数": 15, "均价": 100.0,
             "领涨股": "x", "领涨股-最新价": 200.0,
             "领涨股-涨跌幅": 1.0},
        ])

    monkeypatch.setattr(ak, "stock_board_industry_summary_ths",
                        fake_summary_ths)

    rows = akshare_source.fetch_sector_heat_batch(now=1700000000)
    industries = sorted(r[0] for r in rows)
    assert industries == ["INDUSTRY:AI_COMPUTE", "INDUSTRY:SEMI_EQUIPMENT"]
    for r in rows:
        ts_code, dp_id, val, status, conf, source, ts = r
        assert dp_id == "L0.sentiment.sector_heat"
        assert status == "Known"
        assert source == "akshare:stock_board_industry_summary_ths"
        payload = json.loads(val)
        assert "boards" in payload
        assert payload["avg_change_pct"] is not None
        # AI_COMPUTE has 2 boards averaged (1.20 + 0.85)/2 = 1.025
        if ts_code == "INDUSTRY:AI_COMPUTE":
            assert abs(payload["avg_change_pct"] - 1.025) < 0.01
            assert payload["top_leader"]["leader_stock"] == "alpha"
        else:
            # SEMI_EQUIPMENT: single 半导体 board, change_pct 0.35
            assert payload["avg_change_pct"] == 0.35
            assert payload["top_leader"]["leader_stock"] == "芯源微"


def test_fetch_sector_heat_batch_empty_when_summary_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import akshare as ak

    monkeypatch.setattr(
        akshare_source, "_load_industry_yaml",
        lambda _fn: {"SEMI_EQUIPMENT": ["半导体"]},
    )
    monkeypatch.setattr(
        akshare_source, "_active_industry_ids_akshare",
        lambda: ["SEMI_EQUIPMENT"],
    )
    monkeypatch.setattr(
        ak, "stock_board_industry_summary_ths",
        lambda: (_ for _ in ()).throw(RuntimeError("502 Bad Gateway")),
    )
    rows = akshare_source.fetch_sector_heat_batch(now=1700000000)
    assert rows == []


def test_supported_dp_ids_covers_x2_industry_ids() -> None:
    """SUPPORTED_DP_IDS already had the three X2 ids declared (Tier-2 stub).
    Confirm they are still present after the X2 wire-up."""

    expected = {
        "L0.cost.raw_material",
        "L0.cost.energy_logistics",
        "L0.sentiment.sector_heat",
    }
    assert expected.issubset(akshare_source.SUPPORTED_DP_IDS)
