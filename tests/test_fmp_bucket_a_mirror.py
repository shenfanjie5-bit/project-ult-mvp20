"""Tests for the 22 Bucket-A mirror fetchers in ``fmp_source``.

These mirror the tushare A-share fetchers but emit for US tickers via FMP
endpoints. We monkeypatch ``_get_json`` so the suite stays hermetic and
validate, per spec:

  * Sub-A1 / L2.segment.{revenue_share, gross_margin, growth} — FMP doesn't
    break out segment cost, so gross_margin is always Inactive; share +
    growth emit Known when /revenue-product-segmentation returns rows.
  * Sub-A2 / L4.cost.{labor,raw_material}, L4.eff.{turnover,cycle},
    L8.fin.{cash_ar,debt_pressure} — derived from income / balance-sheet /
    cash-flow / key-metrics endpoints. labor uses the SGA+R&D proxy
    (no FMP labor breakdown), with proxy_method flagged in the payload.
  * Sub-A3 / L6.priced.analyst_revision, L7.mood.analyst_rating,
    L9.media.analyst_action, L7.trade.margin_short — grades-historical +
    analyst-stock-recommendations + short-interest. short-interest has a
    /key-metrics-ttm fallback for the Starter tier.
  * Sub-A4 / L5.fcst.guidance_change, L9.company.buyback_dividend,
    L9.company.earnings_guidance — analyst-estimates delta + buyback +
    dividends + earnings-calendar.
  * Sub-A5 / L6.state.{historical_percentile, expansion_compression,
    peer_compare}, L10.val.{historical_quantile,peer}, L6.priced.run_up —
    price-history + key-metrics + ratios-ttm + stock-peers.

Non-US ts_codes are silently skipped at the entrypoint.

Network is never touched: ``_get_api_key`` is stubbed and module-level
caches are reset between tests.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from mvp20.sources import fmp_source


# ---------------------------------------------------------------------------
# Cache reset + api-key stubs
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_caches():
    """Module-level caches must not leak between tests."""
    for cache in (
        fmp_source._SEGMENT_CACHE,
        fmp_source._KEY_METRICS_CACHE,
        fmp_source._KEY_METRICS_TTM_CACHE,
        fmp_source._INCOME_STMT_CACHE,
        fmp_source._BS_CACHE,
        fmp_source._CF_CACHE,
        fmp_source._GRADES_CACHE,
        fmp_source._ANALYST_REC_CACHE,
        fmp_source._BUYBACK_CACHE,
        fmp_source._DIVIDENDS_CACHE,
        fmp_source._EARNINGS_CAL_CACHE,
        fmp_source._SHORT_INTEREST_CACHE,
        fmp_source._STOCK_PEERS_CACHE,
        fmp_source._PRICE_HIST_CACHE,
    ):
        cache.clear()
    yield
    for cache in (
        fmp_source._SEGMENT_CACHE,
        fmp_source._KEY_METRICS_CACHE,
        fmp_source._KEY_METRICS_TTM_CACHE,
        fmp_source._INCOME_STMT_CACHE,
        fmp_source._BS_CACHE,
        fmp_source._CF_CACHE,
        fmp_source._GRADES_CACHE,
        fmp_source._ANALYST_REC_CACHE,
        fmp_source._BUYBACK_CACHE,
        fmp_source._DIVIDENDS_CACHE,
        fmp_source._EARNINGS_CAL_CACHE,
        fmp_source._SHORT_INTEREST_CACHE,
        fmp_source._STOCK_PEERS_CACHE,
        fmp_source._PRICE_HIST_CACHE,
    ):
        cache.clear()


@pytest.fixture()
def fake_api_key(monkeypatch):
    monkeypatch.setattr(fmp_source, "_get_api_key", lambda: "TESTKEY")


# ---------------------------------------------------------------------------
# Canned-payload helpers
# ---------------------------------------------------------------------------


def _income_payload(symbol: str = "NVDA",
                    current_period: str = "2024-12-31",
                    prior_period: str = "2023-12-31") -> list[dict]:
    return [
        {
            "symbol": symbol,
            "date": current_period,
            "revenue": 100_000_000_000.0,
            "costOfRevenue": 25_000_000_000.0,
            "grossProfit": 75_000_000_000.0,
            "sellingGeneralAndAdministrativeExpenses": 8_000_000_000.0,
            "researchAndDevelopmentExpenses": 12_000_000_000.0,
            "operatingIncome": 55_000_000_000.0,
            "netIncome": 48_000_000_000.0,
            "eps": 1.94,
        },
        {
            "symbol": symbol,
            "date": prior_period,
            "revenue": 60_000_000_000.0,
            "costOfRevenue": 17_000_000_000.0,
            "grossProfit": 43_000_000_000.0,
            "sellingGeneralAndAdministrativeExpenses": 6_000_000_000.0,
            "researchAndDevelopmentExpenses": 9_000_000_000.0,
            "operatingIncome": 28_000_000_000.0,
            "netIncome": 23_000_000_000.0,
            "eps": 0.93,
        },
    ]


def _balance_sheet_payload(symbol: str = "NVDA") -> list[dict]:
    return [
        {
            "symbol": symbol,
            "date": "2024-12-31",
            "cashAndCashEquivalents": 35_000_000_000.0,
            "totalDebt": 12_000_000_000.0,
            "totalAssets": 100_000_000_000.0,
            "totalLiabilities": 35_000_000_000.0,
            "inventory": 7_000_000_000.0,
            "accountsReceivables": 15_000_000_000.0,
            "accountPayables": 4_000_000_000.0,
            "goodwill": 5_000_000_000.0,
            "propertyPlantEquipmentNet": 8_000_000_000.0,
            "shortTermDebt": 2_000_000_000.0,
            "longTermDebt": 10_000_000_000.0,
        },
        {
            "symbol": symbol,
            "date": "2023-12-31",
            "cashAndCashEquivalents": 25_000_000_000.0,
            "totalDebt": 11_000_000_000.0,
            "totalAssets": 70_000_000_000.0,
            "totalLiabilities": 27_000_000_000.0,
            "inventory": 5_500_000_000.0,
            "accountsReceivables": 9_000_000_000.0,
            "accountPayables": 3_000_000_000.0,
            "goodwill": 4_500_000_000.0,
            "propertyPlantEquipmentNet": 7_000_000_000.0,
        },
    ]


def _cash_flow_payload(symbol: str = "NVDA") -> list[dict]:
    return [
        {
            "symbol": symbol,
            "date": "2024-12-31",
            "operatingCashFlow": 55_000_000_000.0,
            "freeCashFlow": 50_000_000_000.0,
            "capitalExpenditure": -5_000_000_000.0,
            "netCashProvidedByInvestingActivities": -10_000_000_000.0,
            "netCashProvidedByFinancingActivities": -30_000_000_000.0,
            "commonStockRepurchased": -27_000_000_000.0,
            "commonDividendsPaid": -2_000_000_000.0,
        },
    ]


def _key_metrics_payload(symbol: str = "NVDA") -> list[dict]:
    """Period-rated /key-metrics with the days-* fields used by L4.eff.* +
    PE/PB history for L6.state.historical_percentile."""

    return [
        {
            "symbol": symbol,
            "date": "2024-12-31",
            "daysOfInventoryOnHand": 90.5,
            "daysOfSalesOutstanding": 50.0,
            "daysOfPayablesOutstanding": 45.0,
            "peRatio": 32.5,
            "pbRatio": 18.2,
            "ebitda": 60_000_000_000.0,
        },
        {
            "symbol": symbol,
            "date": "2023-12-31",
            "daysOfInventoryOnHand": 75.0,
            "daysOfSalesOutstanding": 45.0,
            "daysOfPayablesOutstanding": 40.0,
            "peRatio": 28.0,
            "pbRatio": 15.0,
            "ebitda": 33_000_000_000.0,
        },
        {
            "symbol": symbol,
            "date": "2022-12-31",
            "peRatio": 25.0,
            "pbRatio": 11.0,
        },
        {
            "symbol": symbol,
            "date": "2021-12-31",
            "peRatio": 80.0,
            "pbRatio": 25.0,
        },
        {
            "symbol": symbol,
            "date": "2020-12-31",
            "peRatio": 45.0,
            "pbRatio": 20.0,
        },
    ]


def _key_metrics_ttm_payload(symbol: str = "NVDA",
                             short_ratio: float = 1.5) -> list[dict]:
    return [{
        "symbol": symbol,
        "ebitdaTTM": 65_000_000_000.0,
        "shortRatio": short_ratio,
    }]


def _ratios_ttm_payload(symbol: str = "NVDA",
                       pe: float = 35.0,
                       pb: float = 20.0) -> list[dict]:
    return [{
        "symbol": symbol,
        "priceToEarningsRatioTTM": pe,
        "priceToBookRatioTTM": pb,
    }]


def _segments_payload(symbol: str = "NVDA") -> list[dict]:
    return [
        {
            "symbol": symbol,
            "date": "2024-12-31",
            "data": {
                "Data Center": 80_000_000_000.0,
                "Gaming": 12_000_000_000.0,
                "Professional Visualization": 5_000_000_000.0,
                "Automotive": 3_000_000_000.0,
            },
        },
        {
            "symbol": symbol,
            "date": "2023-12-31",
            "data": {
                "Data Center": 40_000_000_000.0,
                "Gaming": 11_000_000_000.0,
                "Professional Visualization": 4_500_000_000.0,
                "Automotive": 4_500_000_000.0,
            },
        },
    ]


def _grades_payload(symbol: str = "NVDA",
                    today: date | None = None) -> list[dict]:
    """8 grades, 3 within the last 7 days (1 upgrade, 1 downgrade,
    1 maintain), the rest spread over 90 days. ``today`` defaults to the
    actual UTC today so the 7-day cutoff inside the fetcher always matches
    the test fixture window."""

    from datetime import datetime, timezone
    if today is None:
        today = datetime.now(timezone.utc).date()

    return [
        {"symbol": symbol, "date": (today - timedelta(days=2)).isoformat(),
         "gradingCompany": "Goldman", "action": "upgrade",
         "newGrade": "Buy", "previousGrade": "Hold"},
        {"symbol": symbol, "date": (today - timedelta(days=5)).isoformat(),
         "gradingCompany": "Morgan Stanley", "action": "downgrade",
         "newGrade": "Hold", "previousGrade": "Buy"},
        {"symbol": symbol, "date": (today - timedelta(days=6)).isoformat(),
         "gradingCompany": "JPM", "action": "hold",
         "newGrade": "Buy", "previousGrade": "Buy"},
        {"symbol": symbol, "date": (today - timedelta(days=20)).isoformat(),
         "gradingCompany": "BoA", "action": "initiate",
         "newGrade": "Buy", "previousGrade": None},
        {"symbol": symbol, "date": (today - timedelta(days=30)).isoformat(),
         "gradingCompany": "Goldman", "action": "downgrade",
         "newGrade": "Hold", "previousGrade": "Buy"},
        {"symbol": symbol, "date": (today - timedelta(days=45)).isoformat(),
         "gradingCompany": "Wells Fargo", "action": "upgrade",
         "newGrade": "Buy", "previousGrade": "Hold"},
        {"symbol": symbol, "date": (today - timedelta(days=60)).isoformat(),
         "gradingCompany": "Barclays", "action": "initiate",
         "newGrade": "Buy", "previousGrade": None},
        {"symbol": symbol, "date": (today - timedelta(days=85)).isoformat(),
         "gradingCompany": "UBS", "action": "upgrade",
         "newGrade": "Strong Buy", "previousGrade": "Buy"},
    ]


def _analyst_rec_payload(symbol: str = "NVDA") -> list[dict]:
    return [{
        "symbol": symbol,
        "date": "2026-05-01",
        "analystRatingsStrongBuy": 25,
        "analystRatingsBuy": 18,
        "analystRatingsHold": 8,
        "analystRatingsSell": 1,
        "analystRatingsStrongSell": 0,
    }]


def _short_interest_payload(symbol: str = "NVDA") -> list[dict]:
    return [{
        "symbol": symbol,
        "date": "2026-04-30",
        "shortInterestRatio": 1.2,
        "shortInterestPercentFloat": 0.015,
        "daysToCover": 1.3,
    }]


def _earnings_cal_payload(symbol: str = "NVDA") -> list[dict]:
    return [
        {"symbol": symbol, "date": "2026-05-20", "epsActual": None,
         "epsEstimated": 1.76, "revenueActual": None,
         "revenueEstimated": 78_000_000_000.0,
         "fiscalDateEnding": "2026-04-30"},
        {"symbol": symbol, "date": "2026-02-25", "epsActual": 1.62,
         "epsEstimated": 1.54, "revenueActual": 60_000_000_000.0,
         "revenueEstimated": 59_000_000_000.0,
         "fiscalDateEnding": "2026-01-31"},
    ]


def _analyst_estimates_payload(symbol: str = "NVDA") -> list[dict]:
    """Two forward annual rows that drive guidance_change delta."""
    today_iso = date(2026, 5, 12).isoformat()
    return [
        {"symbol": symbol, "date": "2027-01-31",
         "revenueAvg": 100_000_000_000.0, "ebitAvg": 60_000_000_000.0,
         "ebitdaAvg": 65_000_000_000.0, "epsAvg": 4.50,
         "epsLow": 4.0, "epsHigh": 5.0, "numAnalystsEps": 40,
         "numAnalystsRevenue": 38},
        {"symbol": symbol, "date": "2028-01-31",
         "revenueAvg": 130_000_000_000.0, "ebitAvg": 78_000_000_000.0,
         "ebitdaAvg": 85_000_000_000.0, "epsAvg": 5.50,
         "epsLow": 5.0, "epsHigh": 6.0, "numAnalystsEps": 30,
         "numAnalystsRevenue": 28},
        # one historical row to verify our forward filter
        {"symbol": symbol, "date": "2025-01-31",
         "epsAvg": 3.0, "epsLow": 2.5, "epsHigh": 3.5,
         "numAnalystsEps": 35, "revenueAvg": 80_000_000_000.0},
    ]


def _dividends_payload(symbol: str = "NVDA") -> list[dict]:
    return [
        {"symbol": symbol, "date": "2026-04-15", "dividend": 0.10,
         "adjDividend": 0.10, "paymentDate": "2026-05-01",
         "recordDate": "2026-04-22"},
        {"symbol": symbol, "date": "2026-01-15", "dividend": 0.10,
         "paymentDate": "2026-02-01", "recordDate": "2026-01-22"},
    ]


def _stock_peers_payload(symbol: str = "NVDA") -> list[dict]:
    return [{"symbol": symbol,
             "peersList": ["AMD", "AVGO", "INTC", "QCOM", "MRVL"]}]


def _price_series(symbol: str = "NVDA", *, days: int = 260,
                  start: float = 100.0, end: float = 130.0) -> list[dict]:
    """Build a desc-by-date price series sloping linearly."""
    today = date(2026, 5, 12)
    step = (end - start) / max(days - 1, 1)
    rows: list[dict] = []
    for i in range(days):
        d = today - timedelta(days=(days - 1 - i))
        rows.append({"symbol": symbol, "date": d.isoformat(),
                     "price": round(start + i * step, 4),
                     "volume": 1_000_000})
    return list(reversed(rows))


# ---------------------------------------------------------------------------
# Fake _get_json router
# ---------------------------------------------------------------------------


def _make_router(*,
                 segments=None, income=None, bs=None, cf=None,
                 key_metrics=None, key_metrics_ttm=None,
                 ratios_ttm=None, grades=None, analyst_rec=None,
                 short_interest=None, earnings_cal=None,
                 estimates=None, dividends=None, buyback=None,
                 peers=None, price_rows=None,
                 short_interest_status: str = "ok",
                 buyback_status: str = "empty"):
    """Build a fake ``_get_json(endpoint, params)`` returning the canned
    payloads keyed by endpoint. Use ``short_interest_status='401'`` to
    simulate an FMP Starter Premium-locked endpoint; ``buyback_status``
    similar."""

    def fake(endpoint: str, params=None, timeout: int = 15):
        params = params or {}
        sym = params.get("symbol", "") or (params.get("symbols", "") or "")
        if endpoint == "/income-statement":
            return income if income is not None else _income_payload(sym)
        if endpoint == "/balance-sheet-statement":
            return bs if bs is not None else _balance_sheet_payload(sym)
        if endpoint == "/cash-flow-statement":
            return cf if cf is not None else _cash_flow_payload(sym)
        if endpoint == "/key-metrics":
            return key_metrics if key_metrics is not None else _key_metrics_payload(sym)
        if endpoint == "/key-metrics-ttm":
            return key_metrics_ttm if key_metrics_ttm is not None else _key_metrics_ttm_payload(sym)
        if endpoint == "/ratios-ttm":
            return ratios_ttm if ratios_ttm is not None else _ratios_ttm_payload(sym)
        if endpoint == "/revenue-product-segmentation":
            return segments if segments is not None else _segments_payload(sym)
        if endpoint == "/grades":
            # Per-event grade history (newGrade / previousGrade / action).
            return grades if grades is not None else _grades_payload(sym)
        if endpoint == "/grades-historical":
            # Aggregate ratings distribution (analystRatingsStrongBuy etc.).
            return analyst_rec if analyst_rec is not None else _analyst_rec_payload(sym)
        if endpoint == "/analyst-stock-recommendations":
            # Older endpoint name; routed identically.
            return analyst_rec if analyst_rec is not None else _analyst_rec_payload(sym)
        if endpoint == "/short-interest":
            if short_interest_status == "401":
                return None  # mirrors _get_json's HTTPError return
            return short_interest if short_interest is not None else _short_interest_payload(sym)
        if endpoint == "/earnings-calendar":
            return earnings_cal if earnings_cal is not None else _earnings_cal_payload(sym)
        if endpoint == "/analyst-estimates":
            return estimates if estimates is not None else _analyst_estimates_payload(sym)
        if endpoint == "/dividends":
            return dividends if dividends is not None else _dividends_payload(sym)
        if endpoint == "/historical-buyback":
            if buyback_status == "401":
                return None
            return buyback if buyback is not None else []
        if endpoint == "/stock-peers":
            return peers if peers is not None else _stock_peers_payload(sym)
        if endpoint == "/historical-price-eod/light":
            if price_rows is not None:
                return price_rows
            if sym == "SPY":
                return _price_series("SPY", days=260, start=500.0, end=540.0)
            if sym == "^GSPC":
                return _price_series("^GSPC", days=80, start=5000.0,
                                     end=5150.0)
            return _price_series(sym, days=260, start=100.0, end=130.0)
        return None
    return fake


# ---------------------------------------------------------------------------
# SUPPORTED_DP_IDS contract
# ---------------------------------------------------------------------------

EXPECTED_22 = {
    "L2.segment.revenue_share", "L2.segment.gross_margin",
    "L2.segment.growth",
    "L4.cost.labor", "L4.cost.raw_material", "L4.eff.turnover",
    "L4.eff.cycle", "L8.fin.cash_ar", "L8.fin.debt_pressure",
    "L6.priced.analyst_revision", "L7.mood.analyst_rating",
    "L7.trade.margin_short", "L9.media.analyst_action",
    "L5.fcst.guidance_change", "L9.company.buyback_dividend",
    "L9.company.earnings_guidance",
    "L6.state.historical_percentile", "L6.state.expansion_compression",
    "L6.state.peer_compare",
    "L10.val.historical_quantile", "L10.val.peer", "L6.priced.run_up",
}


def test_supported_dp_ids_includes_22():
    assert EXPECTED_22.issubset(fmp_source.SUPPORTED_DP_IDS)


# ---------------------------------------------------------------------------
# Sub-A1: segments
# ---------------------------------------------------------------------------


def test_segments_emits_revenue_share_known_and_gross_margin_inactive(
        monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_segments_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    by_dp = {r[1]: r for r in rows}
    assert "L2.segment.revenue_share" in by_dp
    assert by_dp["L2.segment.revenue_share"][3] == "Known"
    payload = json.loads(by_dp["L2.segment.revenue_share"][2])
    assert payload["segments"]
    # Sum of pct close to 100
    total_pct = sum(s.get("revenue_pct") or 0 for s in payload["segments"])
    assert 99.0 <= total_pct <= 101.0
    # gross_margin always inactive (FMP doesn't expose segment cost)
    assert by_dp["L2.segment.gross_margin"][3] == "Inactive"
    # growth Known when 2 periods available
    assert by_dp["L2.segment.growth"][3] == "Known"
    g_payload = json.loads(by_dp["L2.segment.growth"][2])
    assert g_payload["segments"]


def test_segments_inactive_when_empty(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json",
                        _make_router(segments=[]))
    rows = fmp_source.fetch_segments_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    statuses = [r[3] for r in rows]
    assert statuses == ["Inactive", "Inactive", "Inactive"]


# ---------------------------------------------------------------------------
# Sub-A2: financial derived
# ---------------------------------------------------------------------------


def test_financial_derived_emits_six_dp_ids(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_financial_derived_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    dp_ids = {r[1] for r in rows}
    assert {"L4.cost.labor", "L4.cost.raw_material",
            "L4.eff.turnover", "L4.eff.cycle",
            "L8.fin.cash_ar", "L8.fin.debt_pressure"}.issubset(dp_ids)


def test_l4_cost_labor_uses_sga_rd_proxy(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_financial_derived_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    labor = next(r for r in rows if r[1] == "L4.cost.labor")
    assert labor[3] == "Known"
    payload = json.loads(labor[2])
    assert payload["proxy_method"] == "sga_rd_share"
    # SGA+R&D = 20bn, revenue = 100bn → 20%
    assert 19.0 < payload["labor_cost_pct"] < 21.0
    # YoY: 20% vs (6+9)/60=25% → -5pp
    assert payload["labor_cost_yoy_pct"] is not None
    assert -6.0 < payload["labor_cost_yoy_pct"] < -4.0


def test_l4_eff_turnover_and_cycle_compute_correctly(monkeypatch,
                                                     fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_financial_derived_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    by_dp = {r[1]: r for r in rows}
    t_payload = json.loads(by_dp["L4.eff.turnover"][2])
    assert t_payload["inventory_turnover_days"] == 90.5
    assert t_payload["ar_turnover_days"] == 50.0
    assert t_payload["ap_turnover_days"] == 45.0
    c_payload = json.loads(by_dp["L4.eff.cycle"][2])
    assert c_payload["ccc_days"] == round(90.5 + 50.0 - 45.0, 2)


def test_l8_fin_cash_ar_alerts_on_high_ar_yoy(monkeypatch, fake_api_key):
    # AR yoy: 15 → 9 = (15-9)/9 = +66% → WARN+ERROR triggered
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_financial_derived_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    cash_ar = next(r for r in rows if r[1] == "L8.fin.cash_ar")
    # AR 15b vs prior 9b → yoy ≈ 66% → ERROR severity
    payload = json.loads(cash_ar[2])
    assert payload["ar_yoy_pct"] is not None
    assert payload["ar_yoy_pct"] > 50.0
    assert payload["alert_severity"] == "ERROR"
    # Known when alert fires
    assert cash_ar[3] == "Known"


def test_l8_fin_debt_pressure_ratio(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_financial_derived_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    debt = next(r for r in rows if r[1] == "L8.fin.debt_pressure")
    payload = json.loads(debt[2])
    # totalDebt 12bn / ebitdaTTM 65bn ≈ 0.185 → no alert
    assert payload["interest_debt_to_ebitda"] is not None
    assert payload["interest_debt_to_ebitda"] < 1.0
    assert payload["alert_severity"] is None
    # No-alert mirror is Inactive (matches tushare behaviour)
    assert debt[3] == "Inactive"


def test_financial_derived_inactive_when_no_data(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json",
                        _make_router(income=[], bs=[], cf=[],
                                     key_metrics=[],
                                     key_metrics_ttm=[]))
    rows = fmp_source.fetch_financial_derived_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    statuses = {r[1]: r[3] for r in rows}
    for dp in ("L4.cost.labor", "L4.cost.raw_material",
               "L4.eff.turnover", "L4.eff.cycle",
               "L8.fin.cash_ar", "L8.fin.debt_pressure"):
        assert statuses[dp] == "Inactive", dp


# ---------------------------------------------------------------------------
# Sub-A3: grades + analyst recs + short interest
# ---------------------------------------------------------------------------


def test_grades_emits_three_dp_ids(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_grades_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    dp_ids = {r[1] for r in rows}
    assert {"L6.priced.analyst_revision", "L7.mood.analyst_rating",
            "L9.media.analyst_action"}.issubset(dp_ids)


def test_l7_mood_analyst_rating_uses_recommendation_distribution(
        monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_grades_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    rating = next(r for r in rows if r[1] == "L7.mood.analyst_rating")
    assert rating[3] == "Known"
    payload = json.loads(rating[2])
    # 25+18+8+1+0 = 52 total
    assert payload["n_reports"] == 52
    assert payload["strong_buy"] == 25
    # Average score is heavily bullish → > 4
    assert payload["avg_rating_score"] > 4.0


def test_l9_media_analyst_action_detects_7d_changes(monkeypatch,
                                                    fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_grades_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    action = next(r for r in rows if r[1] == "L9.media.analyst_action")
    payload = json.loads(action[2])
    # 1 upgrade + 1 downgrade in 7d
    assert payload["count_7d"] >= 2
    # action_type "mixed_event" when equal up/down
    assert payload["action_type"] in ("mixed_event", "upgrade_event",
                                      "downgrade_event")


def test_short_interest_fallback_when_premium_locked(monkeypatch,
                                                      fake_api_key):
    """When /short-interest returns 401 (None), the fetcher falls back to
    /key-metrics-ttm.shortRatio so the row still emits Known."""

    monkeypatch.setattr(
        fmp_source, "_get_json",
        _make_router(short_interest_status="401"))
    rows = fmp_source.fetch_short_interest_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    assert len(rows) == 1
    ts_code, dp_id, payload_json, status, _, source, _ = rows[0]
    assert dp_id == "L7.trade.margin_short"
    assert status == "Known"
    assert source == "fmp:key-metrics-ttm.fallback"
    payload = json.loads(payload_json)
    assert payload["short_interest_ratio"] == 1.5


def test_short_interest_inactive_when_no_fallback(monkeypatch,
                                                   fake_api_key):
    monkeypatch.setattr(
        fmp_source, "_get_json",
        _make_router(short_interest_status="401", key_metrics_ttm=[]))
    rows = fmp_source.fetch_short_interest_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    assert rows[0][3] == "Inactive"


# ---------------------------------------------------------------------------
# Sub-A4: earnings + buyback + dividend
# ---------------------------------------------------------------------------


def test_earnings_buyback_dividend_emits_three_dp_ids(monkeypatch,
                                                     fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_earnings_buyback_dividend_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    dp_ids = {r[1] for r in rows}
    assert {"L5.fcst.guidance_change", "L9.company.buyback_dividend",
            "L9.company.earnings_guidance"}.issubset(dp_ids)


def test_l5_fcst_guidance_change_classifies_upgrade(monkeypatch,
                                                    fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_earnings_buyback_dividend_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    g = next(r for r in rows if r[1] == "L5.fcst.guidance_change")
    assert g[3] == "Known"
    payload = json.loads(g[2])
    # Near forward 4.5, next 5.5 → upgrade
    assert payload["change_direction"] == "upgraded"
    assert payload["delta_pct"] is not None
    assert payload["delta_pct"] > 0


def test_l9_company_buyback_dividend_falls_back_to_cash_flow(monkeypatch,
                                                              fake_api_key):
    """When /historical-buyback is locked or empty, the buyback list is
    derived from /cash-flow-statement.commonStockRepurchased."""

    monkeypatch.setattr(
        fmp_source, "_get_json",
        _make_router(buyback_status="401"))
    rows = fmp_source.fetch_earnings_buyback_dividend_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    bd = next(r for r in rows if r[1] == "L9.company.buyback_dividend")
    assert bd[3] == "Known"
    payload = json.loads(bd[2])
    assert payload["buybacks"]
    assert payload["buybacks"][0]["source"] == \
        "cash-flow.commonStockRepurchased"
    # 27bn from canned cf
    assert payload["buybacks"][0]["amount"] == 27_000_000_000.0
    assert payload["dividends"]
    assert payload["dividends"][0]["cash_div_per_share"] == 0.10


def test_l9_company_earnings_guidance_picks_upcoming(monkeypatch,
                                                    fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_earnings_buyback_dividend_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    eg = next(r for r in rows if r[1] == "L9.company.earnings_guidance")
    assert eg[3] == "Known"
    payload = json.loads(eg[2])
    assert payload["next_earnings_date"] == "2026-05-20"
    assert payload["is_upcoming"] is True


# ---------------------------------------------------------------------------
# Sub-A5: price-history derived
# ---------------------------------------------------------------------------


def test_price_state_emits_six_dp_ids(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_price_state_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    dp_ids = {r[1] for r in rows}
    assert {"L6.state.historical_percentile",
            "L6.state.expansion_compression",
            "L6.state.peer_compare",
            "L10.val.historical_quantile",
            "L10.val.peer",
            "L6.priced.run_up"}.issubset(dp_ids)


def test_l6_priced_run_up_includes_d5_d20_d60(monkeypatch, fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_price_state_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    ru = next(r for r in rows if r[1] == "L6.priced.run_up")
    assert ru[3] == "Known"
    payload = json.loads(ru[2])
    for k in ("d5_pct", "d20_pct", "d60_pct", "latest_close",
              "history_days"):
        assert k in payload, k
    # Linear uptrend → positive run-ups
    assert payload["d20_pct"] > 0
    assert payload["d60_pct"] > 0


def test_l6_state_historical_percentile_uses_pe_history(monkeypatch,
                                                       fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_price_state_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    hp = next(r for r in rows if r[1] == "L6.state.historical_percentile")
    assert hp[3] == "Known"
    payload = json.loads(hp[2])
    assert payload["pe_percentile"] is not None
    # Current PE = 35 vs history [32.5, 28, 25, 80, 45]; 3/5 = 0.6
    assert 0.55 <= payload["pe_percentile"] <= 0.65
    # PB current 20 vs [18.2, 15, 11, 25, 20]; only 3 strictly less → 0.6
    assert payload["pb_percentile"] is not None


def test_l6_state_expansion_compression_picks_regime(monkeypatch,
                                                     fake_api_key):
    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_price_state_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    ec = next(r for r in rows if r[1] == "L6.state.expansion_compression")
    payload = json.loads(ec[2])
    assert payload["regime"] in ("compressed", "neutral", "expanded")
    assert payload["pe_current"] is not None


def test_l10_val_peer_uses_peer_median(monkeypatch, fake_api_key):
    """Override ratios so peers have known PE/PB medians."""

    def fake(endpoint, params=None, timeout=15):
        params = params or {}
        sym = params.get("symbol", "")
        if endpoint == "/ratios-ttm":
            pe_map = {"NVDA": 35.0, "AMD": 30.0, "AVGO": 25.0,
                      "INTC": 20.0, "QCOM": 22.0, "MRVL": 28.0}
            pb_map = {"NVDA": 20.0, "AMD": 18.0, "AVGO": 14.0,
                      "INTC": 8.0, "QCOM": 12.0, "MRVL": 15.0}
            return [{
                "symbol": sym,
                "priceToEarningsRatioTTM": pe_map.get(sym, 25.0),
                "priceToBookRatioTTM": pb_map.get(sym, 12.0),
            }]
        return _make_router()(endpoint, params, timeout)

    monkeypatch.setattr(fmp_source, "_get_json", fake)
    rows = fmp_source.fetch_price_state_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    val_peer = next(r for r in rows if r[1] == "L10.val.peer")
    assert val_peer[3] == "Known"
    payload = json.loads(val_peer[2])
    assert payload["stock_pe"] == 35.0
    # Median of [30, 25, 20, 22, 28] = 25
    assert payload["peer_pe_median"] == 25.0
    assert payload["validation_signal"] in ("convergent", "divergent")
    # Premium (35-25)/25 = 40% → divergent
    assert payload["premium_vs_peers_pct"] == pytest.approx(40.0, abs=0.01)
    assert payload["validation_signal"] == "divergent"
    assert "AMD" in payload["peers"]


# ---------------------------------------------------------------------------
# Top-level orchestrator + US-only filter
# ---------------------------------------------------------------------------


def test_bucket_a_mirror_skips_non_us(monkeypatch, fake_api_key):
    """A-share ts_codes must never appear in the emitted rows."""

    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    universe = [{"ts_code": "NVDA.US"}, {"ts_code": "000063.SZ"},
                {"ts_code": "AAPL.US"}]
    rows = fmp_source.fetch_bucket_a_mirror_batch(universe, 0)
    ts_codes = {r[0] for r in rows}
    assert "000063.SZ" not in ts_codes
    assert "NVDA.US" in ts_codes
    assert "AAPL.US" in ts_codes


def test_bucket_a_mirror_emits_all_22_for_nvda(monkeypatch, fake_api_key):
    """Sanity: every one of the 22 dp_ids appears for NVDA, either Known
    or Inactive (no silent drops)."""

    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    universe = [{"ts_code": "NVDA.US"}]
    rows = fmp_source.fetch_bucket_a_mirror_batch(universe, 0)
    nvda_dp_ids = {r[1] for r in rows if r[0] == "NVDA.US"}
    missing = EXPECTED_22 - nvda_dp_ids
    assert not missing, f"missing dp_ids: {missing}"


def test_bucket_a_isolated_failure_doesnt_poison_other_dp_ids(
        monkeypatch, fake_api_key):
    """If one sub-fetcher raises an unexpected exception, the others
    still emit. We trigger this by making /grades-historical raise."""

    base = _make_router()

    def failing(endpoint, params=None, timeout=15):
        if endpoint == "/grades-historical":
            raise RuntimeError("simulated downstream failure")
        return base(endpoint, params, timeout)

    monkeypatch.setattr(fmp_source, "_get_json", failing)
    rows = fmp_source.fetch_bucket_a_mirror_batch(
        [{"ts_code": "NVDA.US"}], 0)
    dp_ids = {r[1] for r in rows}
    # Even though grades failed, segments / financial / earnings / price
    # should still emit.
    assert "L2.segment.revenue_share" in dp_ids
    assert "L4.cost.labor" in dp_ids
    assert "L9.company.earnings_guidance" in dp_ids
    assert "L6.priced.run_up" in dp_ids


def test_fetch_batch_appends_bucket_a_rows(monkeypatch, fake_api_key):
    """End-to-end: fetch_batch returns the new 22 dp_ids alongside the
    legacy fundamentals."""

    monkeypatch.setattr(fmp_source, "_get_json", _make_router())
    rows = fmp_source.fetch_batch([{"ts_code": "NVDA.US"}], 0)
    nvda_dp_ids = {r[1] for r in rows if r[0] == "NVDA.US"}
    missing = EXPECTED_22 - nvda_dp_ids
    assert not missing, f"missing dp_ids in fetch_batch: {missing}"


# ---------------------------------------------------------------------------
# Failure tolerance
# ---------------------------------------------------------------------------


def test_segments_handles_401_response(monkeypatch, fake_api_key):
    """When /revenue-product-segmentation returns None (401), we emit three
    Inactive rows — no exception leaks."""

    def fake(endpoint, params=None, timeout=15):
        if endpoint == "/revenue-product-segmentation":
            return None
        return _make_router()(endpoint, params, timeout)

    monkeypatch.setattr(fmp_source, "_get_json", fake)
    rows = fmp_source.fetch_segments_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    assert all(r[3] == "Inactive" for r in rows)
    assert len(rows) == 3


def test_grades_inactive_when_no_grades(monkeypatch, fake_api_key):
    monkeypatch.setattr(
        fmp_source, "_get_json",
        _make_router(grades=[], analyst_rec=[]))
    rows = fmp_source.fetch_grades_batch(
        "TESTKEY", [("NVDA.US", "NVDA")], sleep_s=0.0)
    statuses = {r[1]: r[3] for r in rows}
    assert statuses["L6.priced.analyst_revision"] == "Inactive"
    assert statuses["L7.mood.analyst_rating"] == "Inactive"
    assert statuses["L9.media.analyst_action"] == "Inactive"


def test_classify_grade_buckets():
    assert fmp_source._classify_grade("Strong Buy")[1] == 5
    assert fmp_source._classify_grade("Buy")[1] == 4
    assert fmp_source._classify_grade("Hold")[1] == 3
    assert fmp_source._classify_grade("Sell")[1] == 1
    assert fmp_source._classify_grade("Underperform")[1] == 2
    assert fmp_source._classify_grade("Unknown rating xyz")[1] is None


def test_percentile_rank_helper():
    assert fmp_source._percentile_rank(5.0, [1, 2, 3, 4]) == 1.0
    assert fmp_source._percentile_rank(0.5, [1, 2, 3, 4]) == 0.0
    assert fmp_source._percentile_rank(2.5, [1, 2, 3, 4]) == 0.5
