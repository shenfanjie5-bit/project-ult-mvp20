"""Tests for the China macro/industry batch in ``mvp20.sources.tushare_source``.

All Tushare HTTP calls are stubbed via monkeypatch so the suite stays
hermetic. The point is to lock down:

  * ``SUPPORTED_DP_IDS`` covers the 6+ Phase-B.8 macro dp_ids.
  * Sentinel ts_codes use the documented format (``MARKET:CN`` /
    ``INDUSTRY:<slug>``) and stay parseable by downstream consumers.
  * Per-endpoint failures isolate — one Tushare API blowing up does not
    drop the rest of the macro batch.
  * The in-process ``_LAST_MACRO_FETCH`` cache short-circuits the second
    call within the 600s window.
  * ``INDUSTRY_TO_THS_NAME`` only emits rows for mapped industries.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mvp20.sources import tushare_source


# ---------------------------------------------------------------------------
# Helpers — tiny DataFrame-like stub. We don't want a hard pandas dep on the
# test path beyond what tushare_source already uses, so we build minimal
# objects that quack like ``pandas.DataFrame``.
# ---------------------------------------------------------------------------


class _StubDF:
    """Quacks like a tiny pandas.DataFrame for the calls our code makes."""

    def __init__(self, records: list[dict[str, Any]]):
        self._rows = list(records)

    def __len__(self) -> int:
        return len(self._rows)

    def sort_values(self, key, ascending: bool = True) -> "_StubDF":
        return _StubDF(sorted(
            self._rows,
            key=lambda r: (r.get(key) is None, r.get(key)),
            reverse=not ascending,
        ))

    def head(self, n: int) -> "_StubDF":
        return _StubDF(self._rows[:n])

    @property
    def iloc(self):
        rows = self._rows

        class _IL:
            def __getitem__(self, i):
                return _Row(rows[i])

        return _IL()

    def to_dict(self, orient: str = "records") -> list[dict[str, Any]]:
        assert orient == "records"
        return list(self._rows)

    def __getitem__(self, key):
        # Used by daily_basic quantile (`df["pe_ttm"].dropna().tolist()`).
        return _Column([r.get(key) for r in self._rows])


class _Row(dict):
    def to_dict(self) -> dict[str, Any]:
        return dict(self)

    def get(self, key, default=None):
        return super().get(key, default)


class _Column:
    def __init__(self, values: list[Any]):
        self._v = values

    def dropna(self) -> "_Column":
        return _Column([v for v in self._v if v is not None and v == v])

    def tolist(self) -> list[Any]:
        return list(self._v)


class _StubPro:
    """Captures call counts so the cache test can verify replays."""

    def __init__(self, **endpoint_data):
        # endpoint_data maps method name -> DataFrame OR Exception OR callable
        self._data = endpoint_data
        self.call_counts: dict[str, int] = {k: 0 for k in endpoint_data}

    def _dispatch(self, name: str, **kwargs):
        self.call_counts[name] = self.call_counts.get(name, 0) + 1
        v = self._data.get(name)
        if isinstance(v, Exception):
            raise v
        if callable(v):
            return v(**kwargs)
        return v

    def cn_pmi(self, **kw):              return self._dispatch("cn_pmi", **kw)
    def shibor_lpr(self, **kw):          return self._dispatch("shibor_lpr", **kw)
    def cn_m(self, **kw):                return self._dispatch("cn_m", **kw)
    def cn_cpi(self, **kw):              return self._dispatch("cn_cpi", **kw)
    def cn_ppi(self, **kw):              return self._dispatch("cn_ppi", **kw)
    def daily_basic(self, **kw):         return self._dispatch("daily_basic", **kw)
    def index_daily(self, **kw):         return self._dispatch("index_daily", **kw)
    def moneyflow_ind_ths(self, **kw):   return self._dispatch("moneyflow_ind_ths", **kw)
    def moneyflow_hsgt(self, **kw):      return self._dispatch("moneyflow_hsgt", **kw)
    def fund_basic(self, **kw):          return self._dispatch("fund_basic", **kw)
    def fund_share(self, **kw):          return self._dispatch("fund_share", **kw)
    def stk_managers(self, **kw):        return self._dispatch("stk_managers", **kw)


@pytest.fixture(autouse=True)
def _clear_macro_cache():
    """Reset the module-level cache between tests so they stay independent."""

    tushare_source._LAST_MACRO_FETCH["ts"] = 0
    tushare_source._LAST_MACRO_FETCH["rows"] = []
    yield
    tushare_source._LAST_MACRO_FETCH["ts"] = 0
    tushare_source._LAST_MACRO_FETCH["rows"] = []


# ---------------------------------------------------------------------------
# SUPPORTED_DP_IDS contract
# ---------------------------------------------------------------------------


def test_supported_dp_ids_includes_phase_b8_macro() -> None:
    expected = {
        "L10.industry.pmi",
        "L7.env.rates",
        "L9.macro.rates",
        "L7.env.liquidity",
        "L9.macro.liquidity",
        "L9.macro.cpi_employment",
        "L7.env.market_trend",
        "L10.val.historical_quantile",
        "L10.industry.fund_flow",
    }
    assert expected.issubset(tushare_source.SUPPORTED_DP_IDS)


def test_tushare_timeout_seconds_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUSHARE_TIMEOUT_SECONDS", "3.5")
    assert tushare_source._tushare_timeout_seconds() == 3.5


def test_tushare_timeout_seconds_falls_back_on_invalid_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUSHARE_TIMEOUT_SECONDS", "bad")
    assert (
        tushare_source._tushare_timeout_seconds()
        == tushare_source.DEFAULT_TUSHARE_TIMEOUT_SECONDS
    )


def test_industry_to_ths_name_keys_match_present_industry_slugs() -> None:
    """Every key in INDUSTRY_TO_THS_NAME must correspond to a real slug in
    config/mvp20.industries.yaml — otherwise the mapping is dead code."""

    active = set(tushare_source._active_industry_ids())
    # Allow SPACE_ECONOMY (pending) in the dict but otherwise everything
    # must be a known industry id.
    known = active | {"SPACE_ECONOMY"}
    for slug in tushare_source.INDUSTRY_TO_THS_NAME:
        assert slug in known, f"Unknown industry slug: {slug}"


def test_industry_to_ths_name_has_at_least_five_real_mappings() -> None:
    real = [k for k, v in tushare_source.INDUSTRY_TO_THS_NAME.items() if v]
    assert len(real) >= 5, f"Only {len(real)} real mappings: {real}"


# ---------------------------------------------------------------------------
# _emit_market_trend -> L7.env.market_trend (MARKET:CN)
# ---------------------------------------------------------------------------


def test_emit_market_trend_returns_market_cn_row() -> None:
    def _index_daily(**kw):
        base = 1000.0
        return _StubDF([
            {"ts_code": kw["ts_code"], "trade_date": f"202605{i:02d}",
             "close": base + i * 2.0, "pct_chg": 0.2}
            for i in range(70, 0, -1)
        ])

    pro = _StubPro(index_daily=_index_daily)
    rows = tushare_source._emit_market_trend(pro, now=1700000000)
    assert len(rows) == 1
    ts_code, dp_id, value_json, status, conf, source, _ = rows[0]
    assert ts_code == "MARKET:CN"
    assert dp_id == "L7.env.market_trend"
    assert status == "Known"
    assert conf == 0.8
    assert source == "tushare:index_daily"
    payload = json.loads(value_json)
    assert payload["regime"] in {"bull", "range", "bear"}
    assert payload["sse_last"] is not None
    assert payload["sse_1d_pct"] == pytest.approx(0.002)
    assert payload["csi300_20d_pct"] is not None


# ---------------------------------------------------------------------------
# _market_index_payload / _ratio_change — unit contract (regression).
#
# Guards against a past bug where ``pct_chg_1d`` was left in PERCENTAGE POINTS
# (e.g. 2.5) while the multi-day window fields (d5/d20/d60) were decimal ratios
# (e.g. 0.02) — a ~100x unit mismatch inside the SAME payload. Tushare reports
# ``pct_chg`` in percentage points, so the payload must divide it by 100 to put
# the 1-day field on the same decimal scale as the window changes.
# ---------------------------------------------------------------------------


def test_ratio_change_returns_decimal_ratio() -> None:
    # +2% move expressed as a decimal ratio, not "2" percentage points.
    assert tushare_source._ratio_change(100.0, 102.0) == pytest.approx(0.02)
    # Symmetric down move.
    assert tushare_source._ratio_change(100.0, 98.0) == pytest.approx(-0.02)


def test_market_index_payload_1d_and_window_share_decimal_scale() -> None:
    # 6 trading days, oldest -> newest. Closes chosen so the 5-day window change
    # is hand-computable: latest close 102.0, close 5 rows back 100.0.
    #   d5_pct = 102.0 / 100.0 - 1 = 0.02 (decimal)
    # Latest-day pct_chg is given in PERCENTAGE POINTS (2.5 == +2.5%):
    #   pct_chg_1d = 2.5 / 100 = 0.025 (decimal)
    latest_pct_chg = 2.5  # percentage points, as Tushare reports it
    records = [
        {"trade_date": "20260520", "close": 100.0, "pct_chg": 1.0},  # 5 rows back
        {"trade_date": "20260521", "close": 100.5, "pct_chg": 0.5},
        {"trade_date": "20260522", "close": 101.0, "pct_chg": 0.5},
        {"trade_date": "20260523", "close": 101.5, "pct_chg": 0.5},
        {"trade_date": "20260526", "close": 99.5, "pct_chg": -2.0},
        {"trade_date": "20260527", "close": 102.0, "pct_chg": latest_pct_chg},  # latest
    ]

    payload = tushare_source._market_index_payload(records)
    assert payload is not None

    # 1-day field must be the DECIMAL ratio (2.5 / 100), not the raw 2.5.
    assert payload["pct_chg_1d"] == pytest.approx(latest_pct_chg / 100.0)
    assert payload["pct_chg_1d"] == pytest.approx(0.025)

    # 5-day window change, hand-computed: 102/100 - 1 = 0.02.
    assert payload["d5_pct"] == pytest.approx(0.02)

    # Unit lock: a normal daily/weekly move is well under 1.0 as a decimal. A
    # percentage-point value (e.g. 2.5) would fail this, so dropping the /100
    # conversion would break the test. Both fields must be on the same scale.
    assert abs(payload["pct_chg_1d"]) < 1.0
    assert abs(payload["d5_pct"]) < 1.0

    # Other fields behave: latest close surfaced, full history counted, and the
    # longer windows are absent because we only supplied 6 rows.
    assert payload["last"] == pytest.approx(102.0)
    assert payload["latest_date"] == "20260527"
    assert payload["history_days"] == len(records)
    assert payload["d20_pct"] is None
    assert payload["d60_pct"] is None


# ---------------------------------------------------------------------------
# _emit_pmi → L10.industry.pmi (MARKET:CN)
# ---------------------------------------------------------------------------


def test_emit_pmi_returns_single_market_cn_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pro = _StubPro(cn_pmi=_StubDF([
        {"month": "202604", "pmi010000": 50.4, "pmi020100": 51.2,
         "pmi030000": 50.9},
        {"month": "202603", "pmi010000": 49.8, "pmi020100": 50.7,
         "pmi030000": 50.3},
    ]))
    rows = tushare_source._emit_pmi(pro, now=1700000000)
    assert len(rows) == 1
    ts_code, dp_id, value_json, status, conf, source, updated_at = rows[0]
    assert ts_code == "MARKET:CN"
    assert dp_id == "L10.industry.pmi"
    payload = json.loads(value_json)
    assert payload["manufacturing_pmi"] == 50.4
    assert payload["non_manufacturing_pmi"] == 51.2
    assert payload["composite_pmi"] == 50.9
    assert payload["latest_month"] == "202604"
    assert status == "Known"
    assert source == "tushare:cn_pmi"
    assert updated_at == 1700000000


def test_emit_pmi_returns_empty_on_api_failure() -> None:
    pro = _StubPro(cn_pmi=RuntimeError("permission denied"))
    rows = tushare_source._emit_pmi(pro, now=1700000000)
    assert rows == []


# ---------------------------------------------------------------------------
# _emit_rates → L7.env.rates (state) + L9.macro.rates (event)
# ---------------------------------------------------------------------------


def test_emit_rates_emits_state_and_inactive_event_when_unchanged() -> None:
    # LPR unchanged across both months → L9 event must be Inactive.
    pro = _StubPro(shibor_lpr=_StubDF([
        {"date": "20260420", "1y": 3.45, "5y": 3.95,
         "1w": 1.75, "1m": 1.95, "3m": 2.05},
        {"date": "20260320", "1y": 3.45, "5y": 3.95,
         "1w": 1.72, "1m": 1.93, "3m": 2.02},
    ]))
    rows = tushare_source._emit_rates(pro, now=1700000000)
    assert len(rows) == 2
    state = next(r for r in rows if r[1] == "L7.env.rates")
    event = next(r for r in rows if r[1] == "L9.macro.rates")
    assert state[3] == "Known"
    assert event[3] == "Inactive"
    state_payload = json.loads(state[2])
    assert state_payload["lpr_1y_pct"] == 3.45
    assert state_payload["shibor_3m_pct"] == 2.05


def test_emit_rates_marks_event_known_when_lpr_moves() -> None:
    pro = _StubPro(shibor_lpr=_StubDF([
        {"date": "20260420", "1y": 3.30, "5y": 3.80,
         "1w": 1.75, "1m": 1.95, "3m": 2.05},
        {"date": "20260320", "1y": 3.45, "5y": 3.95,
         "1w": 1.72, "1m": 1.93, "3m": 2.02},
    ]))
    rows = tushare_source._emit_rates(pro, now=1700000000)
    event = next(r for r in rows if r[1] == "L9.macro.rates")
    payload = json.loads(event[2])
    assert event[3] == "Known"
    # 3.30 - 3.45 = -0.15pct = -15 bp
    assert payload["lpr_1y_change_bp"] == -15.0
    assert payload["lpr_5y_change_bp"] == -15.0


# ---------------------------------------------------------------------------
# _emit_money_supply → L7.env.liquidity + L9.macro.liquidity
# ---------------------------------------------------------------------------


def test_emit_money_supply_threshold_marks_event_inactive() -> None:
    pro = _StubPro(cn_m=_StubDF([
        {"month": "202604", "m0": 12, "m0_yoy": 4.0,
         "m1": 70, "m1_yoy": 1.5, "m2": 290, "m2_yoy": 8.4},
        {"month": "202603", "m0": 12, "m0_yoy": 4.0,
         "m1": 69, "m1_yoy": 1.3, "m2": 287, "m2_yoy": 8.3},  # delta = 0.1 → below 0.3 threshold
    ]))
    rows = tushare_source._emit_money_supply(pro, now=1700000000)
    state = next(r for r in rows if r[1] == "L7.env.liquidity")
    event = next(r for r in rows if r[1] == "L9.macro.liquidity")
    assert state[3] == "Known"
    assert event[3] == "Inactive"
    payload = json.loads(state[2])
    assert payload["m2_yoy_pct"] == 8.4
    assert payload["m1_yoy_pct"] == 1.5


def test_emit_money_supply_threshold_marks_event_known_when_m2_moves() -> None:
    pro = _StubPro(cn_m=_StubDF([
        {"month": "202604", "m0_yoy": 4.0, "m1_yoy": 1.5,
         "m2_yoy": 9.0, "m0": 0, "m1": 0, "m2": 0},
        {"month": "202603", "m0_yoy": 4.0, "m1_yoy": 1.3,
         "m2_yoy": 8.0, "m0": 0, "m1": 0, "m2": 0},  # delta = 1.0pct → above 0.3
    ]))
    rows = tushare_source._emit_money_supply(pro, now=1700000000)
    event = next(r for r in rows if r[1] == "L9.macro.liquidity")
    assert event[3] == "Known"


# ---------------------------------------------------------------------------
# _emit_cpi_ppi → L9.macro.cpi_employment
# ---------------------------------------------------------------------------


def test_emit_cpi_ppi_merges_both_endpoints() -> None:
    pro = _StubPro(
        cn_cpi=_StubDF([{"month": "202604", "nt_yoy": 0.4, "nt_mom": 0.2}]),
        cn_ppi=_StubDF([{"month": "202604", "ppi_yoy": -2.5}]),
    )
    rows = tushare_source._emit_cpi_ppi(pro, now=1700000000)
    assert len(rows) == 1
    ts_code, dp_id, value_json, status, *_ = rows[0]
    assert ts_code == "MARKET:CN"
    assert dp_id == "L9.macro.cpi_employment"
    assert status == "Known"
    payload = json.loads(value_json)
    assert payload["cpi_yoy_pct"] == 0.4
    assert payload["ppi_yoy_pct"] == -2.5
    assert payload["latest_month"] == "202604"
    assert payload["employment_unemployment_pct"] is None  # TODO sentinel


# ---------------------------------------------------------------------------
# _emit_market_pe_quantile → L10.val.historical_quantile (MARKET:CN)
# ---------------------------------------------------------------------------


def test_emit_market_pe_quantile_requires_enough_samples() -> None:
    pro = _StubPro(daily_basic=_StubDF([
        {"ts_code": f"{i:06d}.SH", "trade_date": "20260506", "pe_ttm": i + 1}
        for i in range(200)
    ]))
    rows = tushare_source._emit_market_pe_quantile(pro, now=1700000000)
    assert len(rows) == 1
    payload = json.loads(rows[0][2])
    assert payload["scope"] == "A_share_market"
    assert payload["sample_size"] == 200
    assert payload["p10"] < payload["p50"] < payload["p90"]


def test_emit_market_pe_quantile_skips_small_samples() -> None:
    pro = _StubPro(daily_basic=_StubDF([
        {"ts_code": "300750.SZ", "trade_date": "20260506", "pe_ttm": 20.0},
    ]))
    rows = tushare_source._emit_market_pe_quantile(pro, now=1700000000)
    assert rows == []  # <100 samples ⇒ skip


# ---------------------------------------------------------------------------
# _emit_industry_fund_flow → L10.industry.fund_flow per INDUSTRY:<slug>
# ---------------------------------------------------------------------------


def test_emit_industry_fund_flow_only_emits_mapped_industries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unmapped industries (THS_NAME=None) get silently skipped."""

    monkeypatch.setattr(
        tushare_source, "_active_industry_ids",
        lambda: ["AI_COMPUTE", "DOMESTIC_CONSUMPTION", "SEMI_EQUIPMENT"],
    )
    # Pick THS names that match the current INDUSTRY_TO_THS_NAME values so
    # the test stays in sync with mapping tweaks.
    ai_ths = tushare_source.INDUSTRY_TO_THS_NAME["AI_COMPUTE"]
    semi_ths = tushare_source.INDUSTRY_TO_THS_NAME["SEMI_EQUIPMENT"]
    pro = _StubPro(moneyflow_ind_ths=_StubDF([
        {"ts_code": "881101.TI", "industry": ai_ths, "trade_date": "20260506",
         "close": 1.2, "pct_change": 0.5, "net_amount": 12.3,
         "buy_amount": 50.0, "sell_amount": 37.7, "net_d5_amount": 80.1},
        {"ts_code": "881102.TI", "industry": semi_ths,
         "trade_date": "20260506", "close": 2.1, "pct_change": -0.3,
         "net_amount": -5.2, "buy_amount": 40.0, "sell_amount": 45.2,
         "net_d5_amount": -10.0},
        # 内需 not mapped → ignored
        {"ts_code": "881103.TI", "industry": "内需消费", "trade_date": "20260506",
         "close": 0.9, "pct_change": 0.1, "net_amount": 1.0,
         "buy_amount": 1.0, "sell_amount": 0.0, "net_d5_amount": 1.0},
    ]))
    rows = tushare_source._emit_industry_fund_flow(pro, now=1700000000)
    industries = sorted(r[0] for r in rows)
    assert industries == ["INDUSTRY:AI_COMPUTE", "INDUSTRY:SEMI_EQUIPMENT"]
    for r in rows:
        assert r[1] == "L10.industry.fund_flow"
        payload = json.loads(r[2])
        assert "net_amount" in payload
        assert "trade_date" in payload


# ---------------------------------------------------------------------------
# fetch_macro_china_batch integration: cache + sentinel format + isolation.
# ---------------------------------------------------------------------------


def _patch_pro(monkeypatch: pytest.MonkeyPatch, pro):
    monkeypatch.setattr(tushare_source, "_get_pro_api", lambda: pro)


def test_fetch_macro_china_batch_returns_sentinel_ts_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tushare_source, "_active_industry_ids",
        lambda: ["AI_COMPUTE", "SEMI_EQUIPMENT"],
    )
    pro = _StubPro(
        cn_pmi=_StubDF([
            {"month": "202604", "pmi010000": 50.1, "pmi020100": 51.0,
             "pmi030000": 50.5},
        ]),
        shibor_lpr=_StubDF([
            {"date": "20260420", "1y": 3.45, "5y": 3.95,
             "1w": 1.75, "1m": 1.95, "3m": 2.05},
        ]),
        cn_m=_StubDF([
            {"month": "202604", "m0_yoy": 4.0, "m1_yoy": 1.5,
             "m2_yoy": 8.4, "m0": 0, "m1": 0, "m2": 0},
        ]),
        cn_cpi=_StubDF([
            {"month": "202604", "nt_yoy": 0.4, "nt_mom": 0.2},
        ]),
        cn_ppi=_StubDF([
            {"month": "202604", "ppi_yoy": -2.5},
        ]),
        daily_basic=_StubDF([
            {"ts_code": f"{i:06d}.SH", "trade_date": "20260506",
             "pe_ttm": i + 1}
            for i in range(150)
        ]),
        moneyflow_ind_ths=_StubDF([
            {"ts_code": "881101.TI",
             "industry": tushare_source.INDUSTRY_TO_THS_NAME["AI_COMPUTE"],
             "trade_date": "20260506", "close": 1.2, "pct_change": 0.5,
             "net_amount": 12.3, "buy_amount": 50.0, "sell_amount": 37.7,
             "net_d5_amount": 80.1},
        ]),
    )
    _patch_pro(monkeypatch, pro)

    rows = tushare_source.fetch_macro_china_batch(now=1700000000)
    assert rows, "expected at least the 6 macro dp_ids when all APIs succeed"
    # Sentinel ts_code format
    for ts_code, *_ in rows:
        assert ts_code == "MARKET:CN" or ts_code.startswith("INDUSTRY:")
    # All standard 7-tuple
    for row in rows:
        assert len(row) == 7
        ts_code, dp_id, value_json, status, conf, source, updated_at = row
        json.loads(value_json)  # parseable
        assert status in {"Known", "Inactive"}
        assert 0.0 <= conf <= 1.0
        assert source.startswith("tushare:")
        assert isinstance(updated_at, int) and updated_at > 0

    seen = {r[1] for r in rows}
    expected = {
        "L10.industry.pmi", "L7.env.rates", "L9.macro.rates",
        "L7.env.liquidity", "L9.macro.liquidity",
        "L9.macro.cpi_employment", "L10.val.historical_quantile",
        "L10.industry.fund_flow",
    }
    assert expected.issubset(seen), f"missing: {expected - seen}"

    # Industry sentinels match config slugs.
    industry_rows = [r for r in rows if r[0].startswith("INDUSTRY:")]
    assert industry_rows
    for r in industry_rows:
        slug = r[0].removeprefix("INDUSTRY:")
        assert slug in tushare_source.INDUSTRY_TO_THS_NAME


def test_fetch_macro_china_batch_emits_zero_rows_on_total_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tushare_source, "_active_industry_ids", lambda: ["AI_COMPUTE"],
    )
    pro = _StubPro(
        cn_pmi=RuntimeError("403 permission"),
        shibor_lpr=RuntimeError("403 permission"),
        cn_m=RuntimeError("403 permission"),
        cn_cpi=RuntimeError("403 permission"),
        cn_ppi=RuntimeError("403 permission"),
        daily_basic=RuntimeError("403 permission"),
        index_daily=RuntimeError("403 permission"),
        moneyflow_ind_ths=RuntimeError("403 permission"),
    )
    _patch_pro(monkeypatch, pro)
    rows = tushare_source.fetch_macro_china_batch(now=1700000000)
    assert rows == []  # no crash; just empty


def test_fetch_macro_china_batch_caches_within_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tushare_source, "_active_industry_ids", lambda: ["AI_COMPUTE"],
    )
    pro = _StubPro(
        cn_pmi=_StubDF([
            {"month": "202604", "pmi010000": 50.1, "pmi020100": 51.0,
             "pmi030000": 50.5},
        ]),
        shibor_lpr=_StubDF([
            {"date": "20260420", "1y": 3.45, "5y": 3.95,
             "1w": 1.75, "1m": 1.95, "3m": 2.05},
        ]),
        cn_m=_StubDF([
            {"month": "202604", "m0_yoy": 4.0, "m1_yoy": 1.5,
             "m2_yoy": 8.4, "m0": 0, "m1": 0, "m2": 0},
        ]),
        cn_cpi=_StubDF([
            {"month": "202604", "nt_yoy": 0.4, "nt_mom": 0.2},
        ]),
        cn_ppi=_StubDF([
            {"month": "202604", "ppi_yoy": -2.5},
        ]),
        daily_basic=_StubDF([]),  # too few samples → no L10.val row, fine
        moneyflow_ind_ths=_StubDF([
            {"ts_code": "881101.TI",
             "industry": tushare_source.INDUSTRY_TO_THS_NAME["AI_COMPUTE"],
             "trade_date": "20260506", "close": 1.2, "pct_change": 0.5,
             "net_amount": 12.3, "buy_amount": 50.0, "sell_amount": 37.7,
             "net_d5_amount": 80.1},
        ]),
    )
    _patch_pro(monkeypatch, pro)

    t0 = 1700000000
    first = tushare_source.fetch_macro_china_batch(now=t0)
    assert first
    cn_pmi_calls_after_first = pro.call_counts["cn_pmi"]
    assert cn_pmi_calls_after_first == 1

    # Second call inside 600s TTL must replay cache, not hit pro.cn_pmi again.
    second = tushare_source.fetch_macro_china_batch(now=t0 + 60)
    assert second == first
    assert pro.call_counts["cn_pmi"] == cn_pmi_calls_after_first  # unchanged

    # Move past the TTL → fetch again.
    third = tushare_source.fetch_macro_china_batch(
        now=t0 + tushare_source._MACRO_CACHE_TTL_S + 1,
    )
    assert third
    assert pro.call_counts["cn_pmi"] == cn_pmi_calls_after_first + 1


def test_fetch_macro_china_batch_returns_empty_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If TUSHARE_TOKEN is missing, fetch_macro_china_batch returns [] (no crash)."""

    monkeypatch.setattr(tushare_source, "_get_pro_api", lambda: None)
    rows = tushare_source.fetch_macro_china_batch(now=1700000000)
    assert rows == []


# ---------------------------------------------------------------------------
# X2 declared-but-silent fetchers — passive_northbound + etf_inflow +
# mgmt_litigation. These dp_ids were in SUPPORTED_DP_IDS but emitted 0 rows
# pre-X2; the tests below pin the new payload contract so the fetcher can't
# regress.
# ---------------------------------------------------------------------------


def test_emit_passive_northbound_market_cn_payload() -> None:
    """``L7.flow.passive_northbound`` market-wide row from moneyflow_hsgt."""

    pro = _StubPro(moneyflow_hsgt=_StubDF([
        {"trade_date": "20260512", "north_money": 405543.48,
         "south_money": 53807.88, "hgt": 190836.94, "sgt": 214706.54,
         "ggt_ss": 30241.74, "ggt_sz": 23566.14},
        {"trade_date": "20260511", "north_money": 423994.49,
         "south_money": 53799.97, "hgt": 196283.8, "sgt": 227710.69,
         "ggt_ss": 30207.67, "ggt_sz": 23592.3},
        {"trade_date": "20260508", "north_money": 357041.96,
         "south_money": 53799.26, "hgt": 163362.53, "sgt": 193679.43,
         "ggt_ss": 30172.42, "ggt_sz": 23626.84},
        {"trade_date": "20260507", "north_money": 300000.0,
         "south_money": 50000.0, "hgt": 150000.0, "sgt": 150000.0,
         "ggt_ss": 30000.0, "ggt_sz": 23000.0},
        {"trade_date": "20260506", "north_money": 250000.0,
         "south_money": 45000.0, "hgt": 125000.0, "sgt": 125000.0,
         "ggt_ss": 29000.0, "ggt_sz": 22000.0},
    ]))
    rows = tushare_source._emit_passive_northbound(pro, now=1700000000)
    assert len(rows) == 1
    ts_code, dp_id, value_json, status, conf, source, ts = rows[0]
    assert ts_code == "MARKET:CN"
    assert dp_id == "L7.flow.passive_northbound"
    assert status == "Known"
    assert source == "tushare:moneyflow_hsgt"
    payload = json.loads(value_json)
    assert payload["north_net_amount"] == 405543.48
    assert payload["south_net_amount"] == 53807.88
    assert payload["latest_date"] == "20260512"
    assert payload["scope"] == "A_share_market"
    # 5d MA = (405543.48 + 423994.49 + 357041.96 + 300000 + 250000) / 5
    expected_ma = (405543.48 + 423994.49 + 357041.96 + 300000.0 + 250000.0) / 5
    assert abs(payload["north_net_5d_ma"] - expected_ma) < 0.01


def test_emit_passive_northbound_empty_on_failure() -> None:
    pro = _StubPro(moneyflow_hsgt=RuntimeError("permission denied"))
    rows = tushare_source._emit_passive_northbound(pro, now=1700000000)
    assert rows == []


def test_emit_etf_inflow_returns_market_cn_row_with_top_etf_payload() -> None:
    """``L7.flow.etf_inflow`` aggregated from fund_basic + fund_share diffs."""

    # 3 ETFs; per-ETF fund_share returns latest + prior trade_date with
    # share deltas.
    basic_rows = [
        {"ts_code": "510050.SH", "name": "上证50ETF", "market": "E",
         "delist_date": None},
        {"ts_code": "510300.SH", "name": "沪深300ETF", "market": "E",
         "delist_date": None},
        {"ts_code": "159915.SZ", "name": "创业板ETF", "market": "E",
         "delist_date": None},
    ]

    def share_for(ts_code, **_kw):
        # 2 rows per ETF, latest first
        if ts_code == "510050.SH":
            return _StubDF([
                {"ts_code": ts_code, "trade_date": "20260512",
                 "fd_share": 1242426.68},
                {"ts_code": ts_code, "trade_date": "20260511",
                 "fd_share": 1200000.0},  # +3.5% delta
            ])
        if ts_code == "510300.SH":
            return _StubDF([
                {"ts_code": ts_code, "trade_date": "20260512",
                 "fd_share": 800000.0},
                {"ts_code": ts_code, "trade_date": "20260511",
                 "fd_share": 850000.0},  # -5.9% delta
            ])
        return _StubDF([
            {"ts_code": ts_code, "trade_date": "20260512",
             "fd_share": 500000.0},
            {"ts_code": ts_code, "trade_date": "20260511",
             "fd_share": 510000.0},  # -1.96% delta
        ])

    pro = _StubPro(fund_basic=_StubDF(basic_rows), fund_share=share_for)
    rows = tushare_source._emit_etf_inflow(pro, now=1700000000)
    assert len(rows) == 1
    ts_code, dp_id, value_json, status, *_ = rows[0]
    assert ts_code == "MARKET:CN"
    assert dp_id == "L7.flow.etf_inflow"
    assert status == "Known"
    payload = json.loads(value_json)
    # top_etf_inflow sorted by abs(share_delta_pct), 510300.SH (-5.9%) first
    assert payload["etf_sampled"] == 3
    assert len(payload["top_etf_inflow"]) == 3
    assert payload["top_etf_inflow"][0]["ts_code"] == "510300.SH"
    assert payload["top_etf_inflow"][0]["share_delta_pct"] < 0


def test_emit_etf_inflow_empty_on_basic_failure() -> None:
    pro = _StubPro(fund_basic=RuntimeError("api outage"))
    rows = tushare_source._emit_etf_inflow(pro, now=1700000000)
    assert rows == []


def test_fetch_a_share_mgmt_litigation_emits_known_when_events_in_window() -> None:
    """Verifies the X2 mgmt_litigation fix: stk_managers in-window events
    → ``L9.company.mgmt_litigation`` Known + payload with events array."""

    def managers_for(ts_code, **_kw):
        # 2 recent events (within window) + 1 ancient (out of window)
        from mvp20.sources.tushare_source import _previous_n_days
        recent = _previous_n_days(30)
        ancient = "20180101"
        return _StubDF([
            {"ts_code": ts_code, "ann_date": recent,
             "name": "陈某", "title": "副总经理",
             "begin_date": recent, "end_date": None,
             "gender": "M", "lev": 1, "edu": "硕士", "national": "中国",
             "birthday": "197801"},
            {"ts_code": ts_code, "ann_date": recent,
             "name": "李某", "title": "董事",
             "begin_date": "20200101", "end_date": recent,
             "gender": "M", "lev": 2, "edu": "本科", "national": "中国",
             "birthday": "196505"},
            {"ts_code": ts_code, "ann_date": ancient,
             "name": "王某", "title": "监事",
             "begin_date": ancient, "end_date": None,
             "gender": "M", "lev": 3, "edu": "本科", "national": "中国",
             "birthday": "197003"},
        ])

    pro = _StubPro(stk_managers=managers_for)
    rows = tushare_source._fetch_a_share_mgmt_litigation(
        pro, ["600519.SH"], now=1700000000, lookback_days=180,
    )
    assert len(rows) == 1
    ts_code, dp_id, value_json, status, *_ = rows[0]
    assert ts_code == "600519.SH"
    assert dp_id == "L9.company.mgmt_litigation"
    assert status == "Known"
    payload = json.loads(value_json)
    assert payload["count_window"] == 2
    assert len(payload["events"]) == 2
    # The 高管离职 event (end_date set) classified correctly
    types = {e["type"] for e in payload["events"]}
    assert "高管离职" in types


def test_fetch_a_share_mgmt_litigation_emits_inactive_on_empty_frame() -> None:
    pro = _StubPro(stk_managers=_StubDF([]))
    rows = tushare_source._fetch_a_share_mgmt_litigation(
        pro, ["600519.SH"], now=1700000000,
    )
    assert len(rows) == 1
    assert rows[0][1] == "L9.company.mgmt_litigation"
    assert rows[0][3] == "Inactive"
