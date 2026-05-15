"""FMP (Financial Modeling Prep) Starter-tier source for US fundamentals.

Per the FMP_TIER_REQUIREMENTS doc, the Starter plan ($14/mo) covers:
- /profile           : company_profile (sector / industry / mcap / beta / …)
- /income-statement  : revenue / cogs / sga / rd / gross_profit / op_income /
                       net_income / eps / margins
- /balance-sheet-statement : cash / debt / inventory / AR / AP / goodwill /
                             PPE / leverage
- /cash-flow-statement     : ocf / fcf / icf / fncf / capex / buyback / div
- /ratios-ttm        : PE / PB / PS / P/FCF / PEG (priceToEarningsGrowthRatio)
- /key-metrics-ttm   : EV/EBITDA / EV/EBIT / ROE / ROA / ROIC
- /financial-growth  : YoY revenue / EPS / net-income growth
- /analyst-estimates : forward consensus revenue / EBIT / EBITDA / EPS
- /discounted-cash-flow : FMP-model intrinsic DCF value
- /quote             : live last / change / volume / day-range
- /historical-price-full   : EOD bars
- /sec-filings-search/symbol : per-symbol SEC filings index (form_type, date, link)
- /news/stock        : per-symbol news stream (title, date, publisher, url)
- /acquisition-of-beneficial-ownership : 13D/G institutional snapshots
- /insider-trading/search : SEC Form 4 insider transactions

We fill the L5/L6 multi-source-full dp_ids for US tickers; HK is best handled
by Futu and A-share by Tushare. L9 event dp_ids (recent_filings + news_flow)
are filled per-symbol from /sec-filings-search/symbol and /news/stock.

This module is intentionally one-shot quarterly-cadence: the collector calls
``fetch_batch`` once per cycle but FMP fundamentals only change quarterly, so
the UPSERT into realtime_current overwrites with the same value. Event
dp_ids change daily; UPSERT keeps the latest snapshot. The ``source`` field
records ``fmp:<endpoint>`` so the audit tool can attribute each dp_id.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable

import urllib.request
import urllib.error
import urllib.parse

log = logging.getLogger("mvp20.sources.fmp")

# FMP migrated v3 endpoints to "Legacy" tier on 2025-08-31; new subscriptions
# must use /stable/* which takes `symbol` as a query param instead of a path
# segment.
FMP_BASE = "https://financialmodelingprep.com/stable"


SUPPORTED_DP_IDS = {
    # Income statement (per-symbol annual, latest period)
    "L5.is.revenue",
    "L5.is.revenue_growth",
    "L5.is.cogs",
    "L5.is.gross_profit",
    "L5.is.gross_margin",
    "L5.is.sga_rd",
    "L5.is.operating_profit",
    "L5.is.net_profit",
    "L5.is.eps",
    "L5.is.margins",
    # Balance sheet
    "L5.bs.cash_debt",
    "L5.bs.inventory",
    "L5.bs.ar_ap",
    "L5.bs.goodwill_ppe",
    "L5.bs.leverage",
    # Cash flow
    "L5.cf.ocf",
    "L5.cf.icf_fcf",
    "L5.cf.fcf",
    "L5.cf.capex",
    "L5.cf.buyback_dividend",
    # Multiples / valuation
    "L6.mult.pe",
    "L6.mult.pb",
    "L6.mult.ps",
    "L6.mult.peg",
    "L6.mult.mcap_fcf",
    "L6.mult.ev_ebitda",
    "L6.mult.dcf",
    # Analyst estimates / forecasts (sell-side consensus)
    "L5.fcst.revenue_margin",
    "L5.fcst.eps_cf",
    "L5.fcst.revisions",
    "L5.surprise.sell_side",
    # L9 events (US-only, per-symbol; lookback ~30d) ──
    "L9.event.recent_filings",
    "L9.event.news_flow",
    # B.6b ─ holders / insider events (US-only, per-symbol) ─
    "L7.holders.institutional",
    "L9.event.insider_trades",
    # B.6c ─ market-level macro (US, sentinel ts_code "MARKET:US") ─
    # Emitted by fetch_macro_us_batch(); two dp_ids per raw source — the
    # L7.env.* row is the current state (snapshot), the L9.macro.* row is
    # the event-trigger view that flips to Known only when |Δ| breaches a
    # daily threshold. Same payload, different framing.
    "L7.env.market_trend",
    "L7.env.rates",
    "L7.env.fx",
    "L7.env.style",
    "L9.macro.rates",
    "L9.macro.fx",
    "L9.macro.cpi_employment",
    # B.6d ─ per-stock derived dp_ids (US-only) ──
    # Cheap signals derived on top of price/news endpoints we already pull;
    # see fetch_preprice_surprise_batch / fetch_news_age_batch /
    # fetch_short_technical_batch.
    "L5.surprise.preprice",
    "L6.priced.news_age",
    "L11.short.technical",
    # B.6e ─ Bucket-A mirror: 22 fields cloned from tushare A-share fetchers
    # so US tickers populate the same dp_ids. See fetch_bucket_a_mirror_batch
    # and Sub-A1..Sub-A5 sub-helpers below. All emit US-only — A-shares are
    # filtered out before any HTTP call so this is byte-equivalent to the
    # tushare path for non-US codes.
    "L2.segment.revenue_share",
    "L2.segment.gross_margin",
    "L2.segment.growth",
    "L4.cost.labor",
    "L4.cost.raw_material",
    "L4.eff.turnover",
    "L4.eff.cycle",
    "L8.fin.cash_ar",
    "L8.fin.debt_pressure",
    "L6.priced.analyst_revision",
    "L7.mood.analyst_rating",
    "L7.trade.margin_short",
    "L9.media.analyst_action",
    "L5.fcst.guidance_change",
    "L9.company.buyback_dividend",
    "L9.company.earnings_guidance",
    "L6.state.historical_percentile",
    "L6.state.expansion_compression",
    "L6.state.peer_compare",
    "L10.val.historical_quantile",
    "L10.val.peer",
    "L6.priced.run_up",
}


def is_us(ts_code: str) -> bool:
    return ts_code.endswith(".US")


def to_fmp_symbol(ts_code: str) -> str | None:
    """Convert ``NVDA.US`` / ``BRK.B.US`` to FMP's ``NVDA`` / ``BRK-B``.
    BRK-B is FMP convention for class-B shares (dash instead of dot)."""

    if not is_us(ts_code):
        return None
    raw = ts_code[:-3]
    # BRK.B → BRK-B
    return raw.replace(".", "-")


# ---------------------------------------------------------------------------
# Auth + HTTP
# ---------------------------------------------------------------------------


def _get_api_key() -> str | None:
    key = os.environ.get("FMP_API_KEY")
    if not key:
        from . import load_dotenv
        load_dotenv()
        key = os.environ.get("FMP_API_KEY")
    return key


def _get_json(endpoint: str, params: dict | None = None, timeout: int = 15):
    key = _get_api_key()
    if not key:
        raise RuntimeError("FMP_API_KEY missing in env / .env")
    qs = dict(params or {})
    qs["apikey"] = key
    url = f"{FMP_BASE}{endpoint}?{urllib.parse.urlencode(qs)}"
    req = urllib.request.Request(url, headers={"User-Agent": "mvp20-collector/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data
    except urllib.error.HTTPError as e:
        log.warning("[fmp] %s HTTP %s: %s", endpoint, e.code, e.read()[:200])
        return None
    except (urllib.error.URLError, TimeoutError) as e:
        log.warning("[fmp] %s network error: %s", endpoint, e)
        return None


def health_check() -> dict:
    """Probe FMP: tiny /stable/quote?symbol=AAPL call, verify api key."""

    if not _get_api_key():
        return {"ok": False, "error": "FMP_API_KEY missing in env / .env"}
    try:
        data = _get_json("/quote", {"symbol": "AAPL"})
        if data and isinstance(data, list) and data:
            return {
                "ok": True,
                "symbol": data[0].get("symbol"),
                "last_price": data[0].get("price"),
                "market_cap": data[0].get("marketCap"),
            }
        return {"ok": False, "error": f"unexpected payload: {str(data)[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Batch fetch
# ---------------------------------------------------------------------------


def _safe(d: dict, key: str):
    v = d.get(key)
    if v is None:
        return None
    if isinstance(v, float) and v != v:
        return None
    return v


# ---------------------------------------------------------------------------
# L9 event helpers (per-symbol)
# ---------------------------------------------------------------------------


def _iso_date(raw) -> str | None:
    """Normalise FMP's mixed date formats ("2024-12-18 00:00:00" /
    "2026-05-11 11:12:42" / plain "2024-12-18") to "YYYY-MM-DD"."""

    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # First whitespace-token (drops the time part).
    return s.split()[0][:10]


def fetch_sec_filings_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    lookback_days: int = 30,
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Pull recent SEC filings for each US (ts_code, fmp_symbol).

    Endpoint: ``GET /stable/sec-filings-search/symbol`` (probed live —
    requires ``from`` + ``to`` query params; returns up to ~1000 rows per
    call, sorted desc by filingDate). One HTTP call per symbol.

    Output row dp_id: ``L9.event.recent_filings``. Payload schema:
    ``{count: N, latest_date: "YYYY-MM-DD", top: [...max 5], lookback_days}``.
    Each ``top[i]`` carries ``{form_type, date, accepted_date, link}``.
    """

    if not api_key:
        return []

    today = datetime.now(timezone.utc).date()
    from_d = (today - timedelta(days=lookback_days)).isoformat()
    to_d = today.isoformat()

    now = int(time.time())
    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        data = _get_json(
            "/sec-filings-search/symbol",
            {"symbol": sym, "from": from_d, "to": to_d},
        )
        if data is None:
            # network error / 403 / 404 — skip silently
            continue
        if not isinstance(data, list):
            log.warning("[fmp] sec-filings %s: unexpected payload type", sym)
            continue

        if not data:
            rows.append((
                ts_code, "L9.event.recent_filings",
                json.dumps({"count": 0, "latest_date": None, "top": [],
                            "lookback_days": lookback_days},
                           ensure_ascii=False),
                "Unknown", 0.75, "fmp:sec-filings", now,
            ))
            continue

        top: list[dict] = []
        for rec in data[:5]:
            top.append({
                "form_type": rec.get("formType"),
                "date": _iso_date(rec.get("filingDate")),
                "accepted_date": _iso_date(rec.get("acceptedDate")),
                "link": rec.get("link") or rec.get("finalLink"),
            })
        latest = _iso_date(data[0].get("filingDate"))
        payload = {
            "count": len(data),
            "latest_date": latest,
            "top": top,
            "lookback_days": lookback_days,
        }
        rows.append((
            ts_code, "L9.event.recent_filings",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.75, "fmp:sec-filings", now,
        ))
    return rows


def fetch_news_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    lookback_days: int = 30,
    max_items: int = 10,
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Pull recent news for each US (ts_code, fmp_symbol).

    Endpoint: ``GET /stable/news/stock`` (probed live — supports
    ``symbols``, ``from``, ``to``, ``limit``). One HTTP call per symbol.

    Output row dp_id: ``L9.event.news_flow``. Payload schema:
    ``{count_30d: N, latest_date: "YYYY-MM-DD", top_headlines: [...max 5]}``.
    """

    if not api_key:
        return []

    today = datetime.now(timezone.utc).date()
    from_d = (today - timedelta(days=lookback_days)).isoformat()
    to_d = today.isoformat()

    now = int(time.time())
    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        data = _get_json(
            "/news/stock",
            {"symbols": sym, "from": from_d, "to": to_d, "limit": max_items},
        )
        if data is None:
            continue
        if not isinstance(data, list):
            log.warning("[fmp] news %s: unexpected payload type", sym)
            continue

        if not data:
            rows.append((
                ts_code, "L9.event.news_flow",
                json.dumps({"count_30d": 0, "latest_date": None,
                            "top_headlines": [], "lookback_days": lookback_days},
                           ensure_ascii=False),
                "Unknown", 0.75, "fmp:news", now,
            ))
            continue

        top: list[dict] = []
        for rec in data[:5]:
            top.append({
                "title": rec.get("title"),
                "date": _iso_date(rec.get("publishedDate")),
                "source": rec.get("publisher") or rec.get("site"),
                "url": rec.get("url"),
            })
        latest = _iso_date(data[0].get("publishedDate"))
        payload = {
            "count_30d": len(data),
            "latest_date": latest,
            "top_headlines": top,
            "lookback_days": lookback_days,
        }
        rows.append((
            ts_code, "L9.event.news_flow",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.75, "fmp:news", now,
        ))
    return rows


def fetch_institutional_holders_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Pull 13D/G beneficial-owner snapshots per US (ts_code, fmp_symbol).

    Endpoint: ``GET /stable/acquisition-of-beneficial-ownership`` (probed
    live on Starter — returns the cumulative SEC 13D/G beneficial ownership
    history for the symbol; each row has nameOfReportingPerson, percentOfClass,
    amountBeneficiallyOwned, filingDate). One HTTP call per symbol.

    Note: institutional 13F holdings (``/institutional-ownership/*``) are
    locked behind Premium tier (HTTP 402). 13D/G beneficial-ownership is the
    Starter-accessible alternative — captures the >=5% shareholders.

    Output row dp_id: ``L7.holders.institutional``. Payload schema::

        {
          "total_institutional_count": N,
          "total_ownership_pct": float (sum of percentOfClass),
          "top5": [{"name", "shares", "pct", "filing_date"}],
          "latest_filing_date": "YYYY-MM-DD"
        }
    """

    if not api_key:
        return []

    now = int(time.time())
    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        data = _get_json(
            "/acquisition-of-beneficial-ownership",
            {"symbol": sym},
        )
        if data is None:
            # network / restricted endpoint / quota — skip silently
            continue
        if not isinstance(data, list):
            log.warning("[fmp] beneficial-ownership %s: unexpected payload type",
                        sym)
            continue

        if not data:
            rows.append((
                ts_code, "L7.holders.institutional",
                json.dumps({"total_institutional_count": 0,
                            "total_ownership_pct": None,
                            "top5": [], "latest_filing_date": None},
                           ensure_ascii=False),
                "Unknown", 0.75, "fmp:beneficial-ownership", now,
            ))
            continue

        # Aggregate: keep latest filing per reporting-person so we don't
        # double-count amendments. FMP scrapes the 13D/G text imperfectly so
        # we drop names that look like parsing artifacts (digits, parens-only,
        # "page N of N" boilerplate).
        latest_by_person: dict[str, dict] = {}
        for rec in data:
            name = (rec.get("nameOfReportingPerson") or "").strip()
            if not name:
                continue
            low = name.lower()
            if any(s in low for s in ("page ", "###-##-####", "no. ", "no.")):
                continue
            # Need at least one letter (filter pure-numeric / punctuation rows)
            if not any(ch.isalpha() for ch in name):
                continue
            date = _iso_date(rec.get("filingDate"))
            cur = latest_by_person.get(name)
            if cur is None or (date and date > (cur.get("filing_date") or "")):
                try:
                    shares = int(rec.get("amountBeneficiallyOwned") or 0)
                except (TypeError, ValueError):
                    shares = None
                try:
                    pct = float(rec.get("percentOfClass") or 0)
                except (TypeError, ValueError):
                    pct = None
                latest_by_person[name] = {
                    "name": name,
                    "shares": shares,
                    "pct": pct,
                    "filing_date": date,
                }

        if not latest_by_person:
            rows.append((
                ts_code, "L7.holders.institutional",
                json.dumps({"total_institutional_count": 0,
                            "total_ownership_pct": None,
                            "top5": [], "latest_filing_date": None},
                           ensure_ascii=False),
                "Unknown", 0.75, "fmp:beneficial-ownership", now,
            ))
            continue

        holders = sorted(
            latest_by_person.values(),
            key=lambda h: (h.get("pct") or 0.0),
            reverse=True,
        )
        top5 = holders[:5]
        total_pct = sum((h.get("pct") or 0.0) for h in holders) or None
        latest_filing = max(
            (h.get("filing_date") for h in holders if h.get("filing_date")),
            default=None,
        )
        payload = {
            "total_institutional_count": len(holders),
            "total_ownership_pct": total_pct,
            "top5": top5,
            "latest_filing_date": latest_filing,
        }
        rows.append((
            ts_code, "L7.holders.institutional",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.75, "fmp:beneficial-ownership", now,
        ))
    return rows


def fetch_insider_trades_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    lookback_days: int = 90,
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Pull recent SEC Form 4 insider transactions per US (ts_code, fmp_symbol).

    Endpoint: ``GET /stable/insider-trading/search`` (probed live on Starter —
    supports ``symbol`` + ``limit``; returns rows sorted desc by filingDate
    with transactionType / securitiesTransacted / price / reportingName).
    One HTTP call per symbol.

    Output row dp_id: ``L9.event.insider_trades``. Payload schema::

        {
          "count_90d": N,
          "buys": <A-Award / P-Purchase count>,
          "sells": <S-Sale count>,
          "net_action_value": <sum(buy_value) - sum(sell_value), USD>,
          "latest_date": "YYYY-MM-DD",
          "top": [{insider, title, action, shares, value, date}...],
          "lookback_days": 90
        }

    Transaction-type taxonomy (FMP / SEC Form 4 code → bucket):
      * ``P-Purchase``, ``A-Award``    → buy
      * ``S-Sale``                     → sell
      * ``M-Exempt``, ``F-InKind``,
        ``G-Gift``, others             → neutral (not counted in net value)
    """

    if not api_key:
        return []

    today = datetime.now(timezone.utc).date()
    cutoff_iso = (today - timedelta(days=lookback_days)).isoformat()

    BUY_CODES = {"P-Purchase", "A-Award"}
    SELL_CODES = {"S-Sale"}

    now = int(time.time())
    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        # /insider-trading/search has no date filter — pull a bounded page
        # and filter client-side. Starter returns up to 100/call.
        data = _get_json(
            "/insider-trading/search",
            {"symbol": sym, "limit": 100},
        )
        if data is None:
            continue
        if not isinstance(data, list):
            log.warning("[fmp] insider-trading %s: unexpected payload type",
                        sym)
            continue

        recent = [
            r for r in data
            if (_iso_date(r.get("filingDate")) or "") >= cutoff_iso
        ]

        if not recent:
            rows.append((
                ts_code, "L9.event.insider_trades",
                json.dumps({"count_90d": 0, "buys": 0, "sells": 0,
                            "net_action_value": 0.0, "latest_date": None,
                            "top": [], "lookback_days": lookback_days},
                           ensure_ascii=False),
                "Unknown", 0.75, "fmp:insider-trading", now,
            ))
            continue

        buys = 0
        sells = 0
        net_value = 0.0
        for rec in recent:
            ttype = rec.get("transactionType") or ""
            try:
                shares = float(rec.get("securitiesTransacted") or 0)
                price = float(rec.get("price") or 0)
            except (TypeError, ValueError):
                shares = 0.0
                price = 0.0
            value = shares * price
            if ttype in BUY_CODES:
                buys += 1
                net_value += value
            elif ttype in SELL_CODES:
                sells += 1
                net_value -= value

        top: list[dict] = []
        for rec in recent[:5]:
            try:
                shares_top = float(rec.get("securitiesTransacted") or 0)
                price_top = float(rec.get("price") or 0)
            except (TypeError, ValueError):
                shares_top = 0.0
                price_top = 0.0
            top.append({
                "insider": rec.get("reportingName"),
                "title": rec.get("typeOfOwner"),
                "action": rec.get("transactionType"),
                "shares": shares_top,
                "value": shares_top * price_top,
                "date": _iso_date(rec.get("filingDate")),
            })
        latest = _iso_date(recent[0].get("filingDate"))
        payload = {
            "count_90d": len(recent),
            "buys": buys,
            "sells": sells,
            "net_action_value": net_value,
            "latest_date": latest,
            "top": top,
            "lookback_days": lookback_days,
        }
        rows.append((
            ts_code, "L9.event.insider_trades",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.75, "fmp:insider-trading", now,
        ))
    return rows


def fetch_analyst_estimates_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Pull sell-side consensus estimates per US (ts_code, fmp_symbol).

    Endpoint: ``GET /stable/analyst-estimates?symbol=X&period=annual``
    (probed live on Starter — returns ~10 rows per call, mixing 5y of
    history with 5y of forward consensus). One HTTP call per symbol.

    The endpoint returns ``revenueLow/High/Avg``, ``ebitLow/High/Avg``,
    ``ebitdaLow/High/Avg``, ``epsLow/High/Avg``, plus ``numAnalystsRevenue``
    and ``numAnalystsEps`` per row. We emit four dp_ids:

    * ``L5.fcst.revenue_margin`` — next-year revenue consensus + derived
      ebit / ebitda margin (FMP doesn't expose ebitMargin directly, so we
      compute ``ebitAvg / revenueAvg`` and ``ebitdaAvg / revenueAvg``).
    * ``L5.fcst.eps_cf``         — next-year EPS consensus (low/avg/high).
    * ``L5.fcst.revisions``      — YoY revision trend: compares forward
      ``epsAvg`` across consecutive forward years to surface acceleration
      vs deceleration. Crude proxy for buy/sell-side revision flow.
    * ``L5.surprise.sell_side``  — sell-side dispersion (epsHigh - epsLow)
      and analyst count for the next forward year. High dispersion → high
      surprise potential at the next print.
    """

    if not api_key:
        return []

    now = int(time.time())
    rows: list[tuple] = []
    today_iso = datetime.now(timezone.utc).date().isoformat()
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        data = _get_json(
            "/analyst-estimates",
            {"symbol": sym, "period": "annual"},
        )
        if data is None:
            continue
        if not isinstance(data, list) or not data:
            log.warning("[fmp] analyst-estimates %s: empty / unexpected payload", sym)
            continue

        # FMP returns rows sorted desc by date (furthest forward first).
        # Split into forward / past based on date string compared to today.
        forward = [r for r in data if (r.get("date") or "") > today_iso]
        # Sort forward asc so [0] is the nearest forward year.
        forward.sort(key=lambda r: r.get("date") or "")

        if not forward:
            # All rows are historical — use the most recent one (which is
            # the consensus going into the print) as the "current" estimate.
            forward = sorted(data, key=lambda r: r.get("date") or "", reverse=True)

        near = forward[0] if forward else None
        if near is None:
            continue
        near_date = near.get("date")
        rev_avg = _safe(near, "revenueAvg")
        ebit_avg = _safe(near, "ebitAvg")
        ebitda_avg = _safe(near, "ebitdaAvg")
        eps_avg = _safe(near, "epsAvg")
        eps_low = _safe(near, "epsLow")
        eps_high = _safe(near, "epsHigh")
        n_rev = _safe(near, "numAnalystsRevenue")
        n_eps = _safe(near, "numAnalystsEps")
        ebit_margin = (ebit_avg / rev_avg) if (ebit_avg is not None and rev_avg) else None
        ebitda_margin = (ebitda_avg / rev_avg) if (ebitda_avg is not None and rev_avg) else None

        if rev_avg is not None or ebit_margin is not None:
            rows.append((
                ts_code, "L5.fcst.revenue_margin",
                json.dumps({
                    "revenue_avg": rev_avg,
                    "ebit_avg": ebit_avg,
                    "ebitda_avg": ebitda_avg,
                    "ebit_margin": ebit_margin,
                    "ebitda_margin": ebitda_margin,
                    "num_analysts": n_rev,
                    "period": near_date,
                    "unit": "USD",
                }, ensure_ascii=False),
                "Known", 0.8, "fmp:analyst-estimates", now,
            ))

        if eps_avg is not None or eps_low is not None or eps_high is not None:
            rows.append((
                ts_code, "L5.fcst.eps_cf",
                json.dumps({
                    "eps_avg": eps_avg,
                    "eps_low": eps_low,
                    "eps_high": eps_high,
                    "num_analysts": n_eps,
                    "period": near_date,
                    "unit": "USD/share",
                }, ensure_ascii=False),
                "Known", 0.8, "fmp:analyst-estimates", now,
            ))

        # ── revisions: forward-year EPS trend (yr+1 vs yr+2, etc.) ──
        # Without point-in-time revisions, we proxy revision direction by
        # the slope of forward-year consensus: if epsAvg is rising into the
        # far future, the analyst pool is bullish on growth (upgrades);
        # flat/declining = downgrades.
        if len(forward) >= 2:
            eps_series = []
            for rec in forward[:4]:
                v = _safe(rec, "epsAvg")
                if v is not None:
                    eps_series.append({"period": rec.get("date"),
                                       "eps_avg": v,
                                       "num_analysts": _safe(rec, "numAnalystsEps")})
            if len(eps_series) >= 2:
                first = eps_series[0]["eps_avg"]
                last = eps_series[-1]["eps_avg"]
                # CAGR over the forward window; sign + magnitude proxies
                # revision direction.
                yrs = max(len(eps_series) - 1, 1)
                try:
                    if first and first > 0 and last is not None:
                        cagr = (last / first) ** (1.0 / yrs) - 1.0
                    else:
                        cagr = None
                except (ZeroDivisionError, ValueError):
                    cagr = None
                direction = (
                    "up" if (cagr is not None and cagr > 0.02) else
                    "down" if (cagr is not None and cagr < -0.02) else
                    "flat"
                )
                rows.append((
                    ts_code, "L5.fcst.revisions",
                    json.dumps({
                        "forward_eps_cagr": cagr,
                        "direction": direction,
                        "forward_eps_series": eps_series,
                        "as_of": today_iso,
                    }, ensure_ascii=False),
                    "Known", 0.7, "fmp:analyst-estimates.derived", now,
                ))

        # ── sell_side surprise potential: high-low spread / avg ──
        if eps_avg and eps_low is not None and eps_high is not None:
            try:
                spread = float(eps_high) - float(eps_low)
                spread_pct = spread / abs(float(eps_avg)) if eps_avg else None
            except (TypeError, ValueError, ZeroDivisionError):
                spread = None
                spread_pct = None
            rows.append((
                ts_code, "L5.surprise.sell_side",
                json.dumps({
                    "eps_avg": eps_avg,
                    "eps_low": eps_low,
                    "eps_high": eps_high,
                    "spread": spread,
                    "spread_pct": spread_pct,
                    "num_analysts": n_eps,
                    "period": near_date,
                    "unit": "USD/share",
                }, ensure_ascii=False),
                "Known", 0.7, "fmp:analyst-estimates.derived", now,
            ))

    return rows


def fetch_dcf_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Pull intrinsic-value DCF estimate per US (ts_code, fmp_symbol).

    Endpoint: ``GET /stable/discounted-cash-flow?symbol=X`` (probed live on
    Starter — returns a single ``{symbol, date, dcf, "Stock Price"}`` row
    representing FMP's standard DCF model). One HTTP call per symbol.

    Output row dp_id: ``L6.mult.dcf``. Payload schema::

        {
          "scalar": <dcf intrinsic value, USD>,
          "stock_price": <reference price at calc date>,
          "implied_upside": <dcf / stock_price - 1, e.g. -0.45 = 45% overvalued>,
          "as_of": "YYYY-MM-DD",
          "unit": "USD"
        }
    """

    if not api_key:
        return []

    now = int(time.time())
    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        data = _get_json("/discounted-cash-flow", {"symbol": sym})
        if data is None:
            continue
        if not isinstance(data, list) or not data:
            log.warning("[fmp] dcf %s: empty / unexpected payload", sym)
            continue
        r = data[0]
        dcf_val = _safe(r, "dcf")
        # FMP uses "Stock Price" (with space + capital) as the key; tolerate
        # the friendlier "stockPrice" / "price" variants as well.
        stock_price = r.get("Stock Price") or r.get("stockPrice") or r.get("price")
        if dcf_val is None:
            continue
        try:
            dcf_f = float(dcf_val)
        except (TypeError, ValueError):
            continue
        upside = None
        if stock_price:
            try:
                sp_f = float(stock_price)
                if sp_f:
                    upside = dcf_f / sp_f - 1.0
            except (TypeError, ValueError):
                upside = None
        rows.append((
            ts_code, "L6.mult.dcf",
            json.dumps({
                "scalar": dcf_f,
                "stock_price": stock_price,
                "implied_upside": upside,
                "as_of": r.get("date"),
                "unit": "USD",
            }, ensure_ascii=False),
            "Known", 0.7, "fmp:discounted-cash-flow", now,
        ))
    return rows


def fetch_financial_growth_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Pull revenue/EPS growth ratios per US (ts_code, fmp_symbol).

    Endpoint: ``GET /stable/financial-growth?symbol=X&period=annual&limit=2``
    (probed live on Starter — returns YoY growth rates for revenue, gross
    profit, EBIT, operating income, net income, EPS, etc.). One HTTP call
    per symbol; cheaper than re-fetching two income-statements to derive
    YoY ourselves.

    Output row dp_id: ``L5.is.revenue_growth``. Payload schema mirrors the
    tushare version: ``{yoy_pct, qoq_pct?, current_period, ...}``.
    """

    if not api_key:
        return []

    now = int(time.time())
    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        data = _get_json(
            "/financial-growth",
            {"symbol": sym, "period": "annual", "limit": 2},
        )
        if data is None:
            continue
        if not isinstance(data, list) or not data:
            continue
        r = data[0]
        yoy = _safe(r, "revenueGrowth")
        eps_g = _safe(r, "epsgrowth")
        net_g = _safe(r, "netIncomeGrowth")
        period = r.get("date") or r.get("fiscalYear")
        if yoy is None and eps_g is None and net_g is None:
            continue
        rows.append((
            ts_code, "L5.is.revenue_growth",
            json.dumps({
                "yoy_pct": yoy,
                "eps_growth_yoy": eps_g,
                "net_income_growth_yoy": net_g,
                "current_period": period,
            }, ensure_ascii=False),
            "Known", 0.85, "fmp:financial-growth", now,
        ))
    return rows


# ---------------------------------------------------------------------------
# B.6c ─ market-level macro fetcher (US sentinel "MARKET:US")
# ---------------------------------------------------------------------------

# Module-level cache: macro endpoints update slowly (treasury once/day, CPI
# monthly, FX intraday). We re-fetch at most every _MACRO_TTL_S seconds and
# replay the cached rows in between. This lets the collector call
# fetch_macro_us_batch() on every cycle without burning the FMP quota.
_MACRO_TTL_S = 600  # 10 minutes
_LAST_MACRO_FETCH: dict[str, float] = {"ts": 0.0}
_MACRO_CACHE: list[tuple] = []

# Sentinel ts_code for market-wide rows (NOT registered in universe.yaml;
# storage.upsert_realtime doesn't enforce FK on ts_code).
MARKET_US_TS_CODE = "MARKET:US"


def _emit_inactive(dp_id: str, source: str, now: int,
                   reason: str = "endpoint_unavailable") -> tuple:
    """Row factory for endpoints we couldn't fetch (e.g. 401 on Starter).
    data_status='Inactive' signals downstream that the row exists for
    completeness but the value is not authoritative."""

    return (
        MARKET_US_TS_CODE, dp_id,
        json.dumps({"reason": reason}, ensure_ascii=False),
        "Inactive", 0.0, source, now,
    )


def _pct_change(first: float | None, last: float | None) -> float | None:
    """Safe percentage change ``(last/first - 1)`` returning None on bad
    inputs."""

    try:
        if first is None or last is None or not first:
            return None
        return float(last) / float(first) - 1.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _fetch_index_30d(symbol: str, lookback_days: int = 30):
    """Pull last ``lookback_days`` of historical-index closes for ``symbol``
    (e.g. ``^GSPC``). Returns ``(latest_close, first_close, latest_date)``
    or (None, None, None) on any error."""

    today = datetime.now(timezone.utc).date()
    from_d = (today - timedelta(days=lookback_days + 10)).isoformat()  # pad
    # /stable/historical-price-eod/light returns chronological list with
    # {symbol, date, price, volume}; same param shape as v3.
    data = _get_json(
        "/historical-price-eod/light",
        {"symbol": symbol, "from": from_d},
    )
    if data is None or not isinstance(data, list) or not data:
        return None, None, None
    # FMP returns rows desc by date. We want oldest = first, newest = last.
    rows = sorted(data, key=lambda r: r.get("date") or "")
    if len(rows) < 2:
        return None, None, None
    latest = rows[-1]
    first = rows[0]
    try:
        last_close = float(latest.get("price") or latest.get("close") or 0)
        first_close = float(first.get("price") or first.get("close") or 0)
    except (TypeError, ValueError):
        return None, None, None
    return last_close, first_close, _iso_date(latest.get("date"))


def _fetch_market_trend(now: int) -> list[tuple]:
    """Emit ``L7.env.market_trend`` for the three US benchmarks.
    Endpoint: ``/historical-price-eod/light?symbol=^GSPC&from=…`` x3.

    NDX is restricted on FMP Starter (Premium-only ``^NDX`` returns 402),
    so we use the QQQ ETF as a tracking proxy. Same exposure, same beta
    profile, but Starter-accessible. ``ndx_source`` records the surrogate.
    """

    out: list[tuple] = []
    payload: dict = {}
    latest_dates: list[str] = []
    # (payload_key, fmp_symbol, surrogate_note)
    series_map = (
        ("spx", "^GSPC", None),
        ("ndx", "QQQ", "QQQ ETF (proxies ^NDX; Premium-locked on Starter)"),
        ("dji", "^DJI", None),
    )
    for key, sym, note in series_map:
        last_c, first_c, latest_date = _fetch_index_30d(sym, lookback_days=30)
        pct = _pct_change(first_c, last_c)
        payload[f"{key}_30d_pct"] = pct
        payload[f"{key}_last"] = last_c
        if note:
            payload[f"{key}_source"] = note
        if latest_date:
            latest_dates.append(latest_date)
    payload["latest_date"] = max(latest_dates) if latest_dates else None
    payload["lookback_days"] = 30

    # If every series came back empty, log it as Inactive so downstream
    # readers know the source is currently unreachable.
    if all(payload.get(f"{k}_last") is None
           for k in ("spx", "ndx", "dji")):
        out.append(_emit_inactive(
            "L7.env.market_trend", "fmp:historical-index", now,
            reason="no_index_data",
        ))
        return out

    out.append((
        MARKET_US_TS_CODE, "L7.env.market_trend",
        json.dumps(payload, ensure_ascii=False),
        "Known", 0.85, "fmp:historical-index", now,
    ))
    return out


def _fetch_treasury(now: int) -> list[tuple]:
    """Emit ``L7.env.rates`` (snapshot) and ``L9.macro.rates`` (event-trigger
    when 10Y daily change > 5bp). Endpoint: ``/stable/treasury-rates`` —
    Starter accessible (the ``/treasury`` v3 path was renamed in the /stable
    migration); returns curve points keyed ``month1 / month3 / month6 /
    year1 / year2 / year5 / year7 / year10 / year20 / year30`` (yields in
    percent)."""

    out: list[tuple] = []
    today = datetime.now(timezone.utc).date()
    from_d = (today - timedelta(days=10)).isoformat()
    data = _get_json("/treasury-rates", {"from": from_d})
    if data is None or not isinstance(data, list) or not data:
        out.append(_emit_inactive(
            "L7.env.rates", "fmp:treasury", now, reason="no_data"))
        out.append(_emit_inactive(
            "L9.macro.rates", "fmp:treasury", now, reason="no_data"))
        return out

    rows = sorted(data, key=lambda r: r.get("date") or "")
    latest = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None

    def _curve(rec: dict) -> dict:
        return {
            "1y": _safe(rec, "year1"),
            "2y": _safe(rec, "year2"),
            "5y": _safe(rec, "year5"),
            "10y": _safe(rec, "year10"),
            "30y": _safe(rec, "year30"),
        }

    cur = _curve(latest)
    slope_10y_2y = None
    if cur["10y"] is not None and cur["2y"] is not None:
        try:
            slope_10y_2y = float(cur["10y"]) - float(cur["2y"])
        except (TypeError, ValueError):
            slope_10y_2y = None
    snapshot = {
        **cur,
        "slope_10y_2y": slope_10y_2y,
        "as_of": latest.get("date"),
        "unit": "percent",
    }
    out.append((
        MARKET_US_TS_CODE, "L7.env.rates",
        json.dumps(snapshot, ensure_ascii=False),
        "Known", 0.85, "fmp:treasury", now,
    ))

    # ── Event view: flip Known only if 10Y |Δ| > 5bp/day ──
    change_bp = None
    status = "Unknown"
    prev_curve = _curve(prev) if prev else {}
    if cur["10y"] is not None and prev_curve.get("10y") is not None:
        try:
            change_bp = (float(cur["10y"]) - float(prev_curve["10y"])) * 100.0
        except (TypeError, ValueError):
            change_bp = None
    if change_bp is not None and abs(change_bp) > 5.0:
        status = "Known"
    event_payload = {
        "10y": cur["10y"],
        "10y_prev": prev_curve.get("10y"),
        "change_bp": change_bp,
        "threshold_bp": 5.0,
        "as_of": latest.get("date"),
        "prev_date": (prev or {}).get("date"),
    }
    out.append((
        MARKET_US_TS_CODE, "L9.macro.rates",
        json.dumps(event_payload, ensure_ascii=False),
        status, 0.8, "fmp:treasury.derived", now,
    ))
    return out


def _fetch_cpi_employment(now: int, lookback_days: int = 60) -> list[tuple]:
    """Emit ``L9.macro.cpi_employment`` from the FMP economic calendar.
    Endpoint: ``/stable/economic-calendar?from=&to=`` — Starter accessible
    on the macro plan; returns events tagged with country=US and an
    actual/previous/estimate triplet."""

    out: list[tuple] = []
    today = datetime.now(timezone.utc).date()
    from_d = (today - timedelta(days=lookback_days)).isoformat()
    to_d = today.isoformat()
    data = _get_json("/economic-calendar", {"from": from_d, "to": to_d})
    if data is None or not isinstance(data, list):
        out.append(_emit_inactive(
            "L9.macro.cpi_employment", "fmp:economic-calendar", now,
            reason="no_data"))
        return out

    cpi_yoy = None
    cpi_date = None
    nfp_k = None
    nfp_date = None
    unemp = None
    unemp_date = None
    for rec in data:
        country = (rec.get("country") or "").upper()
        if country not in ("US", "UNITED STATES"):
            continue
        ev = (rec.get("event") or "")
        evlow = ev.lower()
        actual = rec.get("actual")
        if actual is None:
            continue
        date = _iso_date(rec.get("date"))
        # CPI YoY: prefer "Core CPI YoY" / "CPI YoY"
        if ("cpi" in evlow and ("yoy" in evlow or "y/y" in evlow)
                and "core" not in evlow):
            try:
                if cpi_date is None or (date and date > cpi_date):
                    cpi_yoy = float(actual)
                    cpi_date = date
            except (TypeError, ValueError):
                pass
        # Non-farm payrolls (in thousands)
        if "nonfarm" in evlow or "non-farm" in evlow or "nfp" in evlow:
            try:
                if nfp_date is None or (date and date > nfp_date):
                    nfp_k = float(actual)
                    nfp_date = date
            except (TypeError, ValueError):
                pass
        # Unemployment rate (already in percent)
        if "unemployment rate" in evlow:
            try:
                if unemp_date is None or (date and date > unemp_date):
                    unemp = float(actual)
                    unemp_date = date
            except (TypeError, ValueError):
                pass

    latest_event_date = max(
        (d for d in (cpi_date, nfp_date, unemp_date) if d),
        default=None,
    )
    has_any = any(v is not None for v in (cpi_yoy, nfp_k, unemp))
    payload = {
        "cpi_yoy_latest": cpi_yoy,
        "cpi_yoy_date": cpi_date,
        "nfp_latest_k": nfp_k,
        "nfp_date": nfp_date,
        "unemployment_pct": unemp,
        "unemployment_date": unemp_date,
        "latest_event_date": latest_event_date,
        "lookback_days": lookback_days,
    }
    out.append((
        MARKET_US_TS_CODE, "L9.macro.cpi_employment",
        json.dumps(payload, ensure_ascii=False),
        "Known" if has_any else "Unknown", 0.8, "fmp:economic-calendar", now,
    ))
    return out


def _fetch_fx(now: int) -> list[tuple]:
    """Emit ``L7.env.fx`` (snapshot) and ``L9.macro.fx`` (event when DXY
    daily |Δ| > 0.5%).

    The ICE U.S. Dollar Index (``DXY``) itself is not in FMP's symbol
    universe on Starter — it's an ICE-licensed index, not a freely-quoted
    instrument. We use the ``UUP`` ETF (Invesco DB US Dollar Index Bullish
    Fund) as a Starter-accessible proxy; UUP tracks the Bloomberg Dollar
    Spot Index (DBV) which correlates >0.98 with DXY over 1-day windows.
    ``dxy_source`` records the surrogate symbol explicitly.
    """

    out: list[tuple] = []
    eur_last, eur_first, eur_date = _fetch_index_30d("EURUSD", lookback_days=30)
    dxy_last, dxy_first, dxy_date = _fetch_index_30d("UUP", lookback_days=30)
    if eur_last is None and dxy_last is None:
        out.append(_emit_inactive(
            "L7.env.fx", "fmp:historical-price-eod", now,
            reason="no_fx_data"))
        out.append(_emit_inactive(
            "L9.macro.fx", "fmp:historical-price-eod", now,
            reason="no_fx_data"))
        return out

    eur_pct = _pct_change(eur_first, eur_last)
    snapshot = {
        "eurusd": eur_last,
        "dxy": dxy_last,
        "dxy_source": "UUP ETF (proxy; DXY index Premium-locked on Starter)",
        "eurusd_30d_pct": eur_pct,
        "latest_date": eur_date or dxy_date,
    }
    # data_status: Proxy because DXY is sourced via the UUP ETF (DXY index
    # itself is Premium-locked on FMP Starter). EURUSD is real; DXY proxy
    # is the key driver. Governance v1 introduced "Proxy" precisely so
    # aggregator can apply confidence_penalty automatically.
    out.append((
        MARKET_US_TS_CODE, "L7.env.fx",
        json.dumps(snapshot, ensure_ascii=False),
        "Proxy", 0.8, "fmp:historical-price-eod", now,
    ))

    # ── Event view: DXY proxy daily |Δ| > 0.5% ──
    # We need the last 2 closes — re-pull a short window to compute the
    # 1-day delta cleanly (the 30d series gives endpoints only).
    daily_change_pct = None
    status = "Unknown"
    if dxy_last is not None:
        today = datetime.now(timezone.utc).date()
        from_d = (today - timedelta(days=7)).isoformat()
        dxy_data = _get_json(
            "/historical-price-eod/light",
            {"symbol": "UUP", "from": from_d},
        )
        if dxy_data and isinstance(dxy_data, list) and len(dxy_data) >= 2:
            rows = sorted(dxy_data, key=lambda r: r.get("date") or "")
            try:
                last_v = float(rows[-1].get("price") or 0)
                prev_v = float(rows[-2].get("price") or 0)
                if prev_v:
                    daily_change_pct = last_v / prev_v - 1.0
            except (TypeError, ValueError):
                daily_change_pct = None
    if daily_change_pct is not None and abs(daily_change_pct) > 0.005:
        # Event triggered but all data is DXY-via-UUP proxy. Mark Proxy so
        # downstream aggregator applies confidence_penalty per governance v1.
        status = "Proxy"
    event_payload = {
        "dxy": dxy_last,
        "dxy_source": "UUP ETF",
        "daily_change_pct": daily_change_pct,
        "threshold_pct": 0.005,
        "as_of": dxy_date,
    }
    out.append((
        MARKET_US_TS_CODE, "L9.macro.fx",
        json.dumps(event_payload, ensure_ascii=False),
        status, 0.75, "fmp:historical-price-eod.derived", now,
    ))
    return out


def _fetch_style(now: int) -> list[tuple]:
    """Emit ``L7.env.style`` — growth-vs-value tilt as IWF/IWD ratio.
    Endpoints: ``/quote?symbol=IWF`` + ``/quote?symbol=IWD`` for the live
    price + 30d ratio via historical."""

    iwf_data = _get_json("/quote", {"symbol": "IWF"})
    iwd_data = _get_json("/quote", {"symbol": "IWD"})
    iwf_price = None
    iwd_price = None
    if iwf_data and isinstance(iwf_data, list) and iwf_data:
        iwf_price = _safe(iwf_data[0], "price")
    if iwd_data and isinstance(iwd_data, list) and iwd_data:
        iwd_price = _safe(iwd_data[0], "price")

    if iwf_price is None or iwd_price is None:
        return [_emit_inactive(
            "L7.env.style", "fmp:quote", now, reason="no_quote_data")]

    try:
        ratio = float(iwf_price) / float(iwd_price) if iwd_price else None
    except (TypeError, ValueError, ZeroDivisionError):
        ratio = None

    # 30d ratio change: pull historical for both, compute then/now ratio.
    iwf_last, iwf_first, _ = _fetch_index_30d("IWF", lookback_days=30)
    iwd_last, iwd_first, latest_date = _fetch_index_30d("IWD", lookback_days=30)
    ratio_30d_pct = None
    if iwf_first and iwd_first and iwf_last and iwd_last:
        try:
            then_ratio = float(iwf_first) / float(iwd_first)
            now_ratio = float(iwf_last) / float(iwd_last)
            if then_ratio:
                ratio_30d_pct = now_ratio / then_ratio - 1.0
        except (TypeError, ValueError, ZeroDivisionError):
            ratio_30d_pct = None

    payload = {
        "iwf": iwf_price,
        "iwd": iwd_price,
        "ratio": ratio,
        "ratio_30d_pct": ratio_30d_pct,
        "latest_date": latest_date,
    }
    return [(
        MARKET_US_TS_CODE, "L7.env.style",
        json.dumps(payload, ensure_ascii=False),
        "Known", 0.8, "fmp:quote.derived", now,
    )]


def fetch_macro_us_batch(tick: int) -> list[tuple]:
    """Pull US-side market-wide macro rows (7 dp_ids, sentinel ts_code
    ``MARKET:US``). Re-fetches at most every ``_MACRO_TTL_S`` seconds;
    cached rows are replayed with the original ``updated_at`` so the
    collector can call this every cycle.

    Each endpoint is wrapped in try/except — a 401 or network blip on
    one source emits an ``Inactive`` row for that dp_id while leaving
    the others intact.
    """

    if not _get_api_key():
        log.warning("[fmp.macro] FMP_API_KEY missing — skipping macro batch")
        return []

    age = float(tick) - _LAST_MACRO_FETCH.get("ts", 0.0)
    if _MACRO_CACHE and age < _MACRO_TTL_S:
        return list(_MACRO_CACHE)

    now = int(tick)
    rows: list[tuple] = []

    for label, fn in (
        ("market_trend", _fetch_market_trend),
        ("treasury", _fetch_treasury),
        ("cpi_employment", _fetch_cpi_employment),
        ("fx", _fetch_fx),
        ("style", _fetch_style),
    ):
        try:
            rows.extend(fn(now))
        except Exception as exc:  # noqa: BLE001
            log.warning("[fmp.macro] %s failed: %s", label, exc)

    _LAST_MACRO_FETCH["ts"] = float(tick)
    _MACRO_CACHE.clear()
    _MACRO_CACHE.extend(rows)
    return rows


# ---------------------------------------------------------------------------
# B.6d ─ per-stock derived dp_ids (US-only)
# ---------------------------------------------------------------------------
#
# We add three cheap derived signals on top of FMP endpoints we already pull:
#
#   * ``L5.surprise.preprice``  — pre-earnings run-up (5/10/20d) relative to SPX
#   * ``L6.priced.news_age``    — staleness of latest news / 7d & 30d volume
#   * ``L11.short.technical``   — MA(20)/MA(50)/RSI(14)/MACD(12,26,9), pure Python
#
# /historical-price-eod/light is the only price endpoint hit; we cache the 80d
# close series per symbol with a 5-min TTL so multiple fetchers can share the
# pull (preprice + technical use the same series). SPX series is cached under
# its own symbol key (``^GSPC``) for the relative-strength leg of preprice.

_PRICE_HIST_TTL_S = 300  # 5 minutes
_PRICE_HIST_CACHE: dict[str, tuple[int, list]] = {}


def _fetch_price_history_cached(symbol: str, lookback_days: int = 80) -> list[dict]:
    """Return desc-sorted ``[{date, price, ...}]`` rows for ``symbol`` from
    /historical-price-eod/light. 5-min TTL cache keyed by ``symbol`` (independent
    of lookback because we always pull a generous 80d window).

    Returns ``[]`` on any error so callers can branch cleanly.
    """

    now_s = int(time.time())
    cached = _PRICE_HIST_CACHE.get(symbol)
    if cached and (now_s - cached[0]) < _PRICE_HIST_TTL_S:
        return cached[1]

    today = datetime.now(timezone.utc).date()
    from_d = (today - timedelta(days=lookback_days)).isoformat()
    data = _get_json("/historical-price-eod/light",
                     {"symbol": symbol, "from": from_d})
    if not isinstance(data, list):
        _PRICE_HIST_CACHE[symbol] = (now_s, [])
        return []
    # FMP returns rows desc by date — keep as-is so index 0 is the latest bar.
    rows = sorted(data, key=lambda r: r.get("date") or "", reverse=True)
    _PRICE_HIST_CACHE[symbol] = (now_s, rows)
    return rows


def _close_series_asc(rows: list[dict]) -> list[float]:
    """Extract ascending close series (oldest → latest) from price-history rows."""

    asc = sorted(rows, key=lambda r: r.get("date") or "")
    closes: list[float] = []
    for r in asc:
        v = r.get("price") if r.get("price") is not None else r.get("close")
        try:
            closes.append(float(v))
        except (TypeError, ValueError):
            continue
    return closes


# ── Pure-Python technical indicators ──────────────────────────────────────


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _ema(closes: list[float], period: int) -> list[float]:
    if len(closes) < period:
        return []
    k = 2.0 / (period + 1.0)
    seed = sum(closes[:period]) / period
    out = [seed]
    for c in closes[period:]:
        out.append(c * k + out[-1] * (1.0 - k))
    return out


def _macd(closes: list[float]) -> tuple[float, float, float] | None:
    """Return ``(macd_line, signal, histogram)`` using MACD(12,26,9). None when
    fewer than 35 closes are available (26 + 9 lag)."""

    if len(closes) < 35:
        return None
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    if not ema12 or not ema26:
        return None
    # Both ema series end at the latest bar; ema26 is shorter (starts 14 bars
    # later than ema12). Align by trailing window.
    n = min(len(ema12), len(ema26))
    e12 = ema12[-n:]
    e26 = ema26[-n:]
    macd_line = [e12[i] - e26[i] for i in range(n)]
    signal = _ema(macd_line, 9)
    if not signal:
        return None
    return macd_line[-1], signal[-1], macd_line[-1] - signal[-1]


def _macd_cross(macd_line_now: float, signal_now: float,
                macd_line_prev: float, signal_prev: float) -> str | None:
    """Return ``"bull"`` when MACD crosses above signal on the latest bar,
    ``"bear"`` when it crosses below, ``None`` otherwise."""

    if macd_line_prev <= signal_prev and macd_line_now > signal_now:
        return "bull"
    if macd_line_prev >= signal_prev and macd_line_now < signal_now:
        return "bear"
    return None


# ── L5.surprise.preprice ──────────────────────────────────────────────────


def fetch_preprice_surprise_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Pre-earnings run-up per US (ts_code, fmp_symbol).

    For each symbol pulls ``/earnings?symbol=X&limit=20`` to identify the next
    upcoming earnings_date (or most recent past one if no future row is left
    in the calendar). Then uses the cached 80d price history to compute the
    5/10/20-trading-day run-up into that date, and subtracts the equivalent
    SPX move for the same window. SPX series is shared across all symbols
    via ``_PRICE_HIST_CACHE`` so we only pull it once per cycle.

    dp_id: ``L5.surprise.preprice``. Payload::

        {
          "earnings_date": "YYYY-MM-DD",
          "run_up_5d_pct": float|None,
          "run_up_10d_pct": float|None,
          "run_up_20d_pct": float|None,
          "spx_relative_5d": float|None,
          "spx_relative_10d": float|None,
          "is_upcoming": bool
        }

    Emits ``Inactive`` rows when /earnings has no data, when there is no
    earnings date in the window, or when the price series is too short.
    """

    if not api_key:
        return []

    now = int(time.time())
    rows: list[tuple] = []

    # Pull SPX once via the shared cache so per-symbol loops don't re-fetch.
    spx_rows = _fetch_price_history_cached("^GSPC", lookback_days=80)
    spx_by_date: dict[str, float] = {}
    for r in spx_rows:
        d = r.get("date")
        try:
            spx_by_date[d] = float(r.get("price") or r.get("close") or 0)
        except (TypeError, ValueError):
            continue

    today_iso = datetime.now(timezone.utc).date().isoformat()

    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        earn = _get_json("/earnings", {"symbol": sym, "limit": 20})
        if not isinstance(earn, list) or not earn:
            rows.append((
                ts_code, "L5.surprise.preprice",
                json.dumps({"reason": "no_earnings_calendar"},
                           ensure_ascii=False),
                "Inactive", 0.0, "fmp:earnings.derived", now,
            ))
            continue

        # Prefer next upcoming (epsActual null and date > today); else most
        # recent past (epsActual not null, date <= today).
        upcoming = [d for d in earn
                    if d.get("epsActual") is None
                    and (d.get("date") or "") > today_iso]
        upcoming.sort(key=lambda d: d.get("date") or "")
        past = [d for d in earn
                if d.get("epsActual") is not None
                and (d.get("date") or "") <= today_iso]
        past.sort(key=lambda d: d.get("date") or "", reverse=True)

        if upcoming:
            earnings_rec = upcoming[0]
            is_upcoming = True
        elif past:
            earnings_rec = past[0]
            is_upcoming = False
        else:
            rows.append((
                ts_code, "L5.surprise.preprice",
                json.dumps({"reason": "no_dated_earnings"},
                           ensure_ascii=False),
                "Inactive", 0.0, "fmp:earnings.derived", now,
            ))
            continue

        earnings_date = earnings_rec.get("date")
        # For upcoming earnings, the run-up is measured up to the most recent
        # trading day (we can't read the future). For past earnings, we anchor
        # at the trading day at-or-before the earnings date itself.
        price_rows = _fetch_price_history_cached(sym, lookback_days=80)
        if len(price_rows) < 21:
            rows.append((
                ts_code, "L5.surprise.preprice",
                json.dumps({"reason": "price_series_too_short"},
                           ensure_ascii=False),
                "Inactive", 0.0, "fmp:earnings.derived", now,
            ))
            continue

        # price_rows is sorted desc by date. Find anchor index.
        anchor_idx = 0  # latest bar by default (upcoming case)
        if not is_upcoming and earnings_date:
            for i, r in enumerate(price_rows):
                if (r.get("date") or "") <= earnings_date:
                    anchor_idx = i
                    break

        def _stock_close_at(offset: int) -> float | None:
            j = anchor_idx + offset
            if j >= len(price_rows):
                return None
            try:
                v = price_rows[j].get("price") or price_rows[j].get("close")
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        anchor_price = _stock_close_at(0)
        if anchor_price is None or anchor_price <= 0:
            rows.append((
                ts_code, "L5.surprise.preprice",
                json.dumps({"reason": "anchor_price_unavailable"},
                           ensure_ascii=False),
                "Inactive", 0.0, "fmp:earnings.derived", now,
            ))
            continue

        def _runup(offset: int) -> float | None:
            p = _stock_close_at(offset)
            if p is None or p == 0:
                return None
            return anchor_price / p - 1.0

        run5 = _runup(5)
        run10 = _runup(10)
        run20 = _runup(20)

        # SPX over the same calendar window — match by date string.
        anchor_date = price_rows[anchor_idx].get("date")
        spx_anchor = spx_by_date.get(anchor_date)

        def _spx_runup(offset: int) -> float | None:
            j = anchor_idx + offset
            if j >= len(price_rows) or spx_anchor is None or spx_anchor <= 0:
                return None
            ref_date = price_rows[j].get("date")
            spx_ref = spx_by_date.get(ref_date)
            if spx_ref is None or spx_ref <= 0:
                return None
            return spx_anchor / spx_ref - 1.0

        spx5 = _spx_runup(5)
        spx10 = _spx_runup(10)

        rel5 = (run5 - spx5) if (run5 is not None and spx5 is not None) else None
        rel10 = (run10 - spx10) if (run10 is not None and spx10 is not None) else None

        payload = {
            "earnings_date": earnings_date,
            "run_up_5d_pct": run5,
            "run_up_10d_pct": run10,
            "run_up_20d_pct": run20,
            "spx_relative_5d": rel5,
            "spx_relative_10d": rel10,
            "is_upcoming": is_upcoming,
        }
        rows.append((
            ts_code, "L5.surprise.preprice",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.75, "fmp:earnings.derived", now,
        ))
    return rows


# ── L6.priced.news_age ────────────────────────────────────────────────────


def fetch_news_age_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    sleep_s: float = 0.21,
) -> list[tuple]:
    """News staleness signal per US (ts_code, fmp_symbol).

    Pulls ``/news/stock?symbols=X&from=…`` over the last 30 days and emits:

      * ``latest_news_age_days`` — days since the most recent headline.
      * ``news_count_7d`` / ``news_count_30d`` — flow density.
      * ``latest_title`` — first 100 chars of the most recent headline.

    dp_id: ``L6.priced.news_age``. Emits ``Inactive`` when /news/stock returns
    nothing usable.
    """

    if not api_key:
        return []

    today = datetime.now(timezone.utc).date()
    from_d = (today - timedelta(days=30)).isoformat()
    to_d = today.isoformat()

    now = int(time.time())
    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        data = _get_json("/news/stock",
                         {"symbols": sym, "from": from_d, "to": to_d,
                          "limit": 50})
        if data is None or not isinstance(data, list) or not data:
            rows.append((
                ts_code, "L6.priced.news_age",
                json.dumps({"reason": "no_news"},
                           ensure_ascii=False),
                "Inactive", 0.0, "fmp:news.derived", now,
            ))
            continue

        # Sort desc by publishedDate so [0] is most recent.
        items = sorted(data, key=lambda r: r.get("publishedDate") or "",
                       reverse=True)
        latest = items[0]
        latest_date = _iso_date(latest.get("publishedDate"))
        age_days: int | None = None
        if latest_date:
            try:
                dt = datetime.strptime(latest_date, "%Y-%m-%d").date()
                age_days = (today - dt).days
            except ValueError:
                age_days = None

        seven_days_ago = (today - timedelta(days=7)).isoformat()
        count_7d = sum(1 for r in items
                       if (_iso_date(r.get("publishedDate")) or "")
                       >= seven_days_ago)
        count_30d = len(items)

        title = (latest.get("title") or "")[:100]

        payload = {
            "latest_news_age_days": age_days,
            "news_count_7d": count_7d,
            "news_count_30d": count_30d,
            "latest_title": title,
            "latest_date": latest_date,
        }
        rows.append((
            ts_code, "L6.priced.news_age",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.75, "fmp:news.derived", now,
        ))
    return rows


# ── L11.short.technical ───────────────────────────────────────────────────


def fetch_short_technical_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Short-term technical signals per US (ts_code, fmp_symbol).

    Uses the cached 50+-bar close series from /historical-price-eod/light to
    derive MA(20), MA(50), RSI(14), MACD(12,26,9). All math is implemented in
    pure Python — no talib / pandas-ta dependency.

    dp_id: ``L11.short.technical``. Payload::

        {
          "ma20": float,
          "ma50": float,
          "ma_signal": "above_above" | "above_below" | "below_above" | "below_below",
          "rsi14": float,
          "rsi_zone": "oversold" | "neutral" | "overbought",
          "macd_line": float,
          "macd_signal": float,
          "macd_histogram": float,
          "macd_cross": "bull" | "bear" | None,
          "latest_close": float,
          "as_of": "YYYY-MM-DD"
        }
    """

    if not api_key:
        return []

    now = int(time.time())
    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        price_rows = _fetch_price_history_cached(sym, lookback_days=80)
        closes = _close_series_asc(price_rows)
        if len(closes) < 50:
            rows.append((
                ts_code, "L11.short.technical",
                json.dumps({"reason": "price_series_too_short",
                            "have_bars": len(closes)},
                           ensure_ascii=False),
                "Inactive", 0.0, "fmp:technical.derived", now,
            ))
            continue

        latest_close = closes[-1]
        ma20 = sum(closes[-20:]) / 20.0
        ma50 = sum(closes[-50:]) / 50.0
        ma_signal = (
            f"{'above' if latest_close > ma20 else 'below'}_"
            f"{'above' if latest_close > ma50 else 'below'}"
        )

        rsi = _rsi(closes, 14)
        if rsi is None:
            rsi_zone = None
        elif rsi < 30:
            rsi_zone = "oversold"
        elif rsi > 70:
            rsi_zone = "overbought"
        else:
            rsi_zone = "neutral"

        macd_t = _macd(closes)
        if macd_t is None:
            macd_line = macd_signal = macd_hist = None
            macd_cross = None
        else:
            macd_line, macd_signal, macd_hist = macd_t
            # Detect crossover by recomputing MACD on closes[:-1].
            prev = _macd(closes[:-1])
            if prev is not None:
                macd_cross = _macd_cross(macd_line, macd_signal,
                                         prev[0], prev[1])
            else:
                macd_cross = None

        as_of = None
        if price_rows:
            as_of = price_rows[0].get("date")

        payload = {
            "ma20": ma20,
            "ma50": ma50,
            "ma_signal": ma_signal,
            "rsi14": rsi,
            "rsi_zone": rsi_zone,
            "macd_line": macd_line,
            "macd_signal": macd_signal,
            "macd_histogram": macd_hist,
            "macd_cross": macd_cross,
            "latest_close": latest_close,
            "as_of": as_of,
        }
        rows.append((
            ts_code, "L11.short.technical",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.7, "fmp:technical.derived", now,
        ))
    return rows


# ---------------------------------------------------------------------------
# B.6e ── Bucket-A mirror: 22 fields paralleling the tushare A-share fetchers
# ---------------------------------------------------------------------------
#
# The A-share path emits 22 dp_ids that the US path historically missed:
#   * L2.segment.{revenue_share,gross_margin,growth}            (3)
#   * L4.cost.{labor,raw_material} / L4.eff.{turnover,cycle}    (4)
#   * L8.fin.{cash_ar,debt_pressure}                             (2)
#   * L6.priced.analyst_revision / L7.mood.analyst_rating /
#     L7.trade.margin_short / L9.media.analyst_action            (4)
#   * L5.fcst.guidance_change / L9.company.{buyback_dividend,
#     earnings_guidance}                                         (3)
#   * L6.state.{historical_percentile,expansion_compression,
#     peer_compare} / L10.val.{historical_quantile,peer} /
#     L6.priced.run_up                                           (6)
#
# This block re-uses /income-statement, /balance-sheet-statement,
# /cash-flow-statement, /key-metrics, /key-metrics-ttm,
# /revenue-product-segmentation, /grades-historical,
# /analyst-stock-recommendations, /historical-buyback,
# /dividends-calendar, /earnings-calendar, /stock-peers,
# /historical-price-eod/light. All endpoints are FMP-Starter-accessible per
# the spec; the few Premium-locked ones (/short-interest, /historical-buyback
# on some tiers) fall back to derived proxies via key-metrics so the row
# always emits — Inactive when no fallback exists.
#
# Module-level caches are TTL-keyed so the per-symbol loop doesn't re-hit
# the same endpoint multiple times when several Bucket-A fetchers need it.
# Default TTL: 10 minutes (financial data is day-level).

_BUCKET_A_FMP_TTL_S = 600

_SEGMENT_CACHE: dict[str, tuple[int, list[dict]]] = {}
_KEY_METRICS_CACHE: dict[str, tuple[int, list[dict]]] = {}
_INCOME_STMT_CACHE: dict[str, tuple[int, list[dict]]] = {}
_BS_CACHE: dict[str, tuple[int, list[dict]]] = {}
_CF_CACHE: dict[str, tuple[int, list[dict]]] = {}
_GRADES_CACHE: dict[str, tuple[int, list[dict]]] = {}
_ANALYST_REC_CACHE: dict[str, tuple[int, list[dict]]] = {}
_BUYBACK_CACHE: dict[str, tuple[int, list[dict]]] = {}
_DIVIDENDS_CACHE: dict[str, tuple[int, list[dict]]] = {}
_EARNINGS_CAL_CACHE: dict[str, tuple[int, list[dict]]] = {}
_SHORT_INTEREST_CACHE: dict[str, tuple[int, dict | list]] = {}
_STOCK_PEERS_CACHE: dict[str, tuple[int, list[str]]] = {}
_KEY_METRICS_TTM_CACHE: dict[str, tuple[int, list[dict]]] = {}


def _cached_get_list(
    cache: dict[str, tuple[int, list[dict]]],
    key: str,
    endpoint: str,
    params: dict,
    ttl: int = _BUCKET_A_FMP_TTL_S,
) -> list[dict]:
    """Generic ``list[dict]`` cache wrapper around ``_get_json``.

    Returns ``[]`` on any error / non-list payload so the caller can branch
    cleanly. Populates the cache with ``[]`` on miss so we don't retry the
    same failing endpoint within the TTL."""

    now_s = int(time.time())
    cached = cache.get(key)
    if cached and (now_s - cached[0]) < ttl:
        return cached[1]
    data = _get_json(endpoint, params)
    if not isinstance(data, list):
        cache[key] = (now_s, [])
        return []
    cache[key] = (now_s, data)
    return data


def _bucket_a_inactive(ts_code: str, dp_id: str, source: str, now: int,
                       reason: str = "no_data") -> tuple:
    """Inactive row factory for the Bucket-A mirror — mirrors the format
    used in the tushare path so downstream readers see byte-identical
    layouts across US and CN universes."""

    return (
        ts_code, dp_id,
        json.dumps({"reason": reason}, ensure_ascii=False),
        "Inactive", 0.0, source, now,
    )


def _bucket_a_known(ts_code: str, dp_id: str, payload: dict, source: str,
                    now: int, confidence: float = 0.75) -> tuple:
    """Known row factory for the Bucket-A mirror."""

    return (
        ts_code, dp_id,
        json.dumps(payload, ensure_ascii=False),
        "Known", confidence, source, now,
    )


# ── /revenue-product-segmentation cache (segments per symbol) ─────────────


def _fetch_segments_cached(symbol: str) -> list[dict]:
    """Pull product-segmentation rows for ``symbol``. FMP /stable endpoint
    returns one row per fiscal period, each with a ``data`` dict mapping
    segment-name → revenue. We sort desc by date so [0] is the latest
    period."""

    rows = _cached_get_list(
        _SEGMENT_CACHE, symbol,
        "/revenue-product-segmentation",
        {"symbol": symbol, "period": "annual"},
    )
    return sorted(rows, key=lambda r: r.get("date") or "", reverse=True)


def fetch_segments_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Emit L2.segment.{revenue_share, gross_margin, growth} per US symbol.

    FMP /revenue-product-segmentation exposes only revenue per segment; FMP
    does not break out segment-level cost. We therefore emit
    ``L2.segment.gross_margin`` as ``Inactive`` with a ``proxy`` field
    pointing back at the company-level gross-margin from /income-statement
    — same fallback the spec calls out."""

    if not api_key:
        return []

    now = int(time.time())
    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        recs = _fetch_segments_cached(sym)
        if not recs:
            rows.append(_bucket_a_inactive(
                ts_code, "L2.segment.revenue_share",
                "fmp:revenue-product-segmentation", now,
                "no_segments"))
            rows.append(_bucket_a_inactive(
                ts_code, "L2.segment.gross_margin",
                "fmp:revenue-product-segmentation", now,
                "no_segments"))
            rows.append(_bucket_a_inactive(
                ts_code, "L2.segment.growth",
                "fmp:revenue-product-segmentation", now,
                "no_segments"))
            continue

        latest = recs[0]
        latest_data = latest.get("data") or {}
        latest_period = latest.get("date")
        if not isinstance(latest_data, dict) or not latest_data:
            rows.append(_bucket_a_inactive(
                ts_code, "L2.segment.revenue_share",
                "fmp:revenue-product-segmentation", now,
                "no_segment_data"))
            rows.append(_bucket_a_inactive(
                ts_code, "L2.segment.gross_margin",
                "fmp:revenue-product-segmentation", now,
                "no_segment_data"))
            rows.append(_bucket_a_inactive(
                ts_code, "L2.segment.growth",
                "fmp:revenue-product-segmentation", now,
                "no_segment_data"))
            continue

        # ── revenue_share ──
        items: list[tuple[str, float]] = []
        for name, val in latest_data.items():
            try:
                fv = float(val)
            except (TypeError, ValueError):
                continue
            items.append((str(name), fv))
        total = sum(v for _, v in items if v > 0)
        rev_segs: list[dict] = []
        if total > 0:
            for name, val in items:
                if val <= 0:
                    continue
                rev_segs.append({
                    "item": name,
                    "revenue_pct": round(val / total * 100.0, 4),
                    "revenue": val,
                    "period": latest_period,
                })
            rev_segs.sort(key=lambda r: r.get("revenue_pct") or 0.0,
                          reverse=True)
            rows.append(_bucket_a_known(
                ts_code, "L2.segment.revenue_share",
                {"segments": rev_segs, "period": latest_period,
                 "unit": "USD"},
                "fmp:revenue-product-segmentation", now, 0.8))
        else:
            rows.append(_bucket_a_inactive(
                ts_code, "L2.segment.revenue_share",
                "fmp:revenue-product-segmentation", now,
                "no_positive_segment_revenue"))

        # ── gross_margin per segment — FMP doesn't break out segment cost ─
        rows.append(_bucket_a_inactive(
            ts_code, "L2.segment.gross_margin",
            "fmp:revenue-product-segmentation", now,
            "fmp_no_segment_cost; use_company_gross_margin_proxy"))

        # ── growth (yoy of segment revenue) ──
        prior = recs[1] if len(recs) >= 2 else None
        prior_data = (prior.get("data") if prior else None) or {}
        if isinstance(prior_data, dict) and prior_data:
            growth_segs: list[dict] = []
            for name, val in items:
                prev = prior_data.get(name)
                try:
                    fv = float(val)
                    pv = float(prev) if prev is not None else None
                except (TypeError, ValueError):
                    continue
                if pv is None or pv == 0:
                    continue
                yoy_pct = (fv - pv) / abs(pv) * 100.0
                growth_segs.append({
                    "item": name,
                    "yoy_pct": round(yoy_pct, 4),
                    "current": fv,
                    "prior": pv,
                    "period": latest_period,
                })
            if growth_segs:
                growth_segs.sort(key=lambda r: r.get("yoy_pct") or 0.0,
                                 reverse=True)
                rows.append(_bucket_a_known(
                    ts_code, "L2.segment.growth",
                    {"segments": growth_segs, "period": latest_period,
                     "prior_period": prior.get("date") if prior else None},
                    "fmp:revenue-product-segmentation", now, 0.75))
            else:
                rows.append(_bucket_a_inactive(
                    ts_code, "L2.segment.growth",
                    "fmp:revenue-product-segmentation", now,
                    "no_yoy_comparable_segments"))
        else:
            rows.append(_bucket_a_inactive(
                ts_code, "L2.segment.growth",
                "fmp:revenue-product-segmentation", now,
                "no_prior_period"))
    return rows


# ── Income / balance-sheet / cash-flow caches (annual, last 2 periods) ────


def _fetch_income_stmt_cached(symbol: str, limit: int = 2) -> list[dict]:
    rows = _cached_get_list(
        _INCOME_STMT_CACHE, symbol,
        "/income-statement",
        {"symbol": symbol, "period": "annual", "limit": limit},
    )
    return sorted(rows, key=lambda r: r.get("date") or "", reverse=True)


def _fetch_bs_cached(symbol: str, limit: int = 2) -> list[dict]:
    rows = _cached_get_list(
        _BS_CACHE, symbol,
        "/balance-sheet-statement",
        {"symbol": symbol, "period": "annual", "limit": limit},
    )
    return sorted(rows, key=lambda r: r.get("date") or "", reverse=True)


def _fetch_cf_cached(symbol: str, limit: int = 2) -> list[dict]:
    rows = _cached_get_list(
        _CF_CACHE, symbol,
        "/cash-flow-statement",
        {"symbol": symbol, "period": "annual", "limit": limit},
    )
    return sorted(rows, key=lambda r: r.get("date") or "", reverse=True)


def _fetch_key_metrics_cached(symbol: str, limit: int = 2) -> list[dict]:
    """``/key-metrics`` — period-rated metrics with the
    daysOfInventoryOnHand / Sales / Payables fields used for L4.eff.*."""

    rows = _cached_get_list(
        _KEY_METRICS_CACHE, symbol,
        "/key-metrics",
        {"symbol": symbol, "period": "annual", "limit": limit},
    )
    return sorted(rows, key=lambda r: r.get("date") or "", reverse=True)


def _fetch_key_metrics_ttm_cached(symbol: str) -> list[dict]:
    return _cached_get_list(
        _KEY_METRICS_TTM_CACHE, symbol,
        "/key-metrics-ttm", {"symbol": symbol},
    )


# ── L4.cost.* / L4.eff.* / L8.fin.* (financial derived) ───────────────────


def fetch_financial_derived_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    sleep_s: float = 0.0,
) -> list[tuple]:
    """Emit 6 financial-derived dp_ids per US symbol.

    Re-uses /income-statement, /balance-sheet-statement, /cash-flow-statement,
    /key-metrics caches so per-symbol cost is ~4 HTTP at most (cached across
    Bucket-A fetchers). ``sleep_s`` defaults to 0 because callers run this
    after another fetcher that already paced /income-statement etc.
    """

    if not api_key:
        return []

    now = int(time.time())
    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        inc = _fetch_income_stmt_cached(sym, limit=2)
        bs = _fetch_bs_cached(sym, limit=2)
        cf = _fetch_cf_cached(sym, limit=2)
        km = _fetch_key_metrics_cached(sym, limit=2)
        kmt = _fetch_key_metrics_ttm_cached(sym)

        latest_inc = inc[0] if inc else None
        prior_inc = inc[1] if len(inc) >= 2 else None
        latest_bs = bs[0] if bs else None
        prior_bs = bs[1] if len(bs) >= 2 else None
        latest_cf = cf[0] if cf else None
        latest_km = km[0] if km else None
        latest_kmt = kmt[0] if kmt else None

        period = (latest_inc or {}).get("date") if latest_inc else None

        # ── L4.cost.labor — proxy via SGA + R&D share of revenue ──
        if latest_inc:
            try:
                rev = _safe(latest_inc, "revenue")
                sga = _safe(latest_inc,
                            "sellingGeneralAndAdministrativeExpenses") or 0.0
                rd = _safe(latest_inc, "researchAndDevelopmentExpenses") or 0.0
                if rev and rev != 0:
                    labor_cost_pct = (
                        (float(sga) + float(rd)) / float(rev)) * 100.0
                    labor_yoy_pct = None
                    if prior_inc:
                        p_rev = _safe(prior_inc, "revenue")
                        p_sga = _safe(
                            prior_inc,
                            "sellingGeneralAndAdministrativeExpenses") or 0.0
                        p_rd = _safe(
                            prior_inc,
                            "researchAndDevelopmentExpenses") or 0.0
                        if p_rev and p_rev != 0:
                            prior_pct = ((float(p_sga) + float(p_rd))
                                         / float(p_rev)) * 100.0
                            labor_yoy_pct = labor_cost_pct - prior_pct
                    rows.append(_bucket_a_known(
                        ts_code, "L4.cost.labor",
                        {
                            "labor_cost_pct": round(labor_cost_pct, 4),
                            "labor_cost_yoy_pct": (
                                round(labor_yoy_pct, 4)
                                if labor_yoy_pct is not None else None
                            ),
                            "proxy_method": "sga_rd_share",
                            "latest_period": period,
                            "unit": "pct",
                        },
                        "fmp:income-statement.derived", now, 0.7))
                else:
                    rows.append(_bucket_a_inactive(
                        ts_code, "L4.cost.labor",
                        "fmp:income-statement.derived", now,
                        "missing_revenue"))
            except (TypeError, ValueError):
                rows.append(_bucket_a_inactive(
                    ts_code, "L4.cost.labor",
                    "fmp:income-statement.derived", now, "compute_error"))
        else:
            rows.append(_bucket_a_inactive(
                ts_code, "L4.cost.labor",
                "fmp:income-statement.derived", now,
                "no_income_statement"))

        # ── L4.cost.raw_material — cogs share of revenue + YoY ──
        if latest_inc:
            rev = _safe(latest_inc, "revenue")
            cogs = _safe(latest_inc, "costOfRevenue")
            if rev and cogs is not None:
                try:
                    raw_pct = (float(cogs) / float(rev)) * 100.0
                    cogs_yoy_pct = None
                    if prior_inc:
                        p_cogs = _safe(prior_inc, "costOfRevenue")
                        if p_cogs and float(p_cogs) != 0:
                            cogs_yoy_pct = ((float(cogs) - float(p_cogs))
                                            / float(p_cogs)) * 100.0
                    rows.append(_bucket_a_known(
                        ts_code, "L4.cost.raw_material",
                        {
                            "raw_material_cost_pct": round(raw_pct, 4),
                            "cogs_yoy_pct": (
                                round(cogs_yoy_pct, 4)
                                if cogs_yoy_pct is not None else None
                            ),
                            "primary_commodity": None,
                            "labor_adjusted": False,
                            "proxy_method": "cogs_share_no_labor_breakdown",
                            "latest_period": period,
                        },
                        "fmp:income-statement.derived", now, 0.7))
                except (TypeError, ValueError):
                    rows.append(_bucket_a_inactive(
                        ts_code, "L4.cost.raw_material",
                        "fmp:income-statement.derived", now,
                        "compute_error"))
            else:
                rows.append(_bucket_a_inactive(
                    ts_code, "L4.cost.raw_material",
                    "fmp:income-statement.derived", now,
                    "missing_revenue_or_cogs"))
        else:
            rows.append(_bucket_a_inactive(
                ts_code, "L4.cost.raw_material",
                "fmp:income-statement.derived", now,
                "no_income_statement"))

        # ── L4.eff.turnover & L4.eff.cycle from /key-metrics days fields ──
        # FMP /stable named these ``daysOfInventoryOutstanding`` /
        # ``daysOfSalesOutstanding`` / ``daysOfPayablesOutstanding``, plus an
        # already-derived ``cashConversionCycle``. Older docs called the
        # inventory field ``daysOfInventoryOnHand`` — try both for safety.
        dio = dso = dpo = ccc_from_api = None
        if latest_km:
            dio_raw = (_safe(latest_km, "daysOfInventoryOutstanding")
                       or _safe(latest_km, "daysOfInventoryOnHand"))
            dso_raw = _safe(latest_km, "daysOfSalesOutstanding")
            dpo_raw = _safe(latest_km, "daysOfPayablesOutstanding")
            ccc_raw = _safe(latest_km, "cashConversionCycle")
            try:
                dio = float(dio_raw) if dio_raw is not None else None
                dso = float(dso_raw) if dso_raw is not None else None
                dpo = float(dpo_raw) if dpo_raw is not None else None
                ccc_from_api = (
                    float(ccc_raw) if ccc_raw is not None else None)
            except (TypeError, ValueError):
                dio = dso = dpo = ccc_from_api = None

        turnover_status = "Inactive"
        turnover_payload: dict
        if dio is not None or dso is not None or dpo is not None:
            turnover_payload = {
                "inventory_turnover_days": round(dio, 2) if dio is not None else None,
                "ar_turnover_days": round(dso, 2) if dso is not None else None,
                "ap_turnover_days": round(dpo, 2) if dpo is not None else None,
                "latest_period": (latest_km or {}).get("date") or period,
                "unit": "days",
            }
            turnover_status = "Known"
            rows.append(_bucket_a_known(
                ts_code, "L4.eff.turnover", turnover_payload,
                "fmp:key-metrics", now, 0.75))
        else:
            turnover_payload = {"reason": "no_days_metrics"}
            rows.append(_bucket_a_inactive(
                ts_code, "L4.eff.turnover", "fmp:key-metrics", now,
                "no_days_metrics"))

        if (turnover_status == "Known" and dio is not None and dso is not None
                and dpo is not None):
            ccc = dio + dso - dpo
            rows.append(_bucket_a_known(
                ts_code, "L4.eff.cycle",
                {
                    "ccc_days": round(ccc, 2),
                    "dio": round(dio, 2),
                    "dso": round(dso, 2),
                    "dpo": round(dpo, 2),
                    "latest_period": turnover_payload.get("latest_period"),
                },
                "fmp:key-metrics.derived", now, 0.75))
        elif ccc_from_api is not None:
            # FMP already publishes ``cashConversionCycle`` — surface it even
            # when one of the three day components is missing.
            rows.append(_bucket_a_known(
                ts_code, "L4.eff.cycle",
                {
                    "ccc_days": round(ccc_from_api, 2),
                    "dio": round(dio, 2) if dio is not None else None,
                    "dso": round(dso, 2) if dso is not None else None,
                    "dpo": round(dpo, 2) if dpo is not None else None,
                    "latest_period": (turnover_payload.get("latest_period")
                                      if isinstance(turnover_payload, dict)
                                      else period),
                    "source_field": "cashConversionCycle",
                },
                "fmp:key-metrics", now, 0.75))
        else:
            rows.append(_bucket_a_inactive(
                ts_code, "L4.eff.cycle", "fmp:key-metrics.derived", now,
                "incomplete_DIO_DSO_DPO"))

        # ── L8.fin.cash_ar — OCF/NI + AR yoy alert ──
        ocf_to_ni = ar_yoy_pct = None
        if latest_cf and latest_inc:
            ni = _safe(latest_inc, "netIncome")
            ocf = _safe(latest_cf, "operatingCashFlow")
            if ni and ni != 0 and ocf is not None:
                try:
                    ocf_to_ni = float(ocf) / float(ni)
                except (TypeError, ValueError):
                    ocf_to_ni = None
        if latest_bs and prior_bs:
            cur_ar = _safe(latest_bs, "accountsReceivables")
            prv_ar = _safe(prior_bs, "accountsReceivables")
            if cur_ar is not None and prv_ar and float(prv_ar) != 0:
                try:
                    ar_yoy_pct = ((float(cur_ar) - float(prv_ar))
                                  / abs(float(prv_ar))) * 100.0
                except (TypeError, ValueError):
                    ar_yoy_pct = None
        alert_severity = None
        warn_trig = ((ocf_to_ni is not None and ocf_to_ni < 0.8)
                     or (ar_yoy_pct is not None and ar_yoy_pct > 20.0))
        err_trig = ((ocf_to_ni is not None and ocf_to_ni < 0.5)
                    or (ar_yoy_pct is not None and ar_yoy_pct > 50.0))
        if err_trig:
            alert_severity = "ERROR"
        elif warn_trig:
            alert_severity = "WARN"
        if ocf_to_ni is None and ar_yoy_pct is None:
            rows.append(_bucket_a_inactive(
                ts_code, "L8.fin.cash_ar",
                "fmp:cash-flow.derived", now,
                "no_ocf_ni_or_ar_yoy"))
        else:
            payload = {
                "ocf_to_ni": round(ocf_to_ni, 4) if ocf_to_ni is not None else None,
                "ar_yoy_pct": round(ar_yoy_pct, 4) if ar_yoy_pct is not None else None,
                "alert_severity": alert_severity,
                "latest_period": period,
            }
            # Mirror tushare: "Known" only when an alert fires.
            if alert_severity:
                rows.append(_bucket_a_known(
                    ts_code, "L8.fin.cash_ar", payload,
                    "fmp:cash-flow.derived", now, 0.8))
            else:
                rows.append((
                    ts_code, "L8.fin.cash_ar",
                    json.dumps(payload, ensure_ascii=False),
                    "Inactive", 0.0, "fmp:cash-flow.derived", now,
                ))

        # ── L8.fin.debt_pressure — interest_debt / EBITDA ──
        total_debt = ebitda = None
        debt_to_assets = None
        if latest_bs:
            total_debt = _safe(latest_bs, "totalDebt")
            if total_debt is None:
                st = _safe(latest_bs, "shortTermDebt") or 0
                lt = _safe(latest_bs, "longTermDebt") or 0
                total_debt = (st + lt) if (st or lt) else None
            tot_assets = _safe(latest_bs, "totalAssets")
            tot_liab = _safe(latest_bs, "totalLiabilities")
            if tot_assets and tot_liab is not None:
                try:
                    debt_to_assets = float(tot_liab) / float(tot_assets)
                except (TypeError, ValueError):
                    debt_to_assets = None
        if latest_kmt:
            ebitda = _safe(latest_kmt, "ebitdaTTM")
            # FMP /stable's /key-metrics-ttm doesn't expose ebitdaTTM
            # directly — derive from enterpriseValueTTM / evToEBITDATTM.
            if ebitda is None:
                ev_ttm = _safe(latest_kmt, "enterpriseValueTTM")
                ev_eb_ttm = _safe(latest_kmt, "evToEBITDATTM")
                if ev_ttm and ev_eb_ttm and float(ev_eb_ttm) != 0:
                    try:
                        ebitda = float(ev_ttm) / float(ev_eb_ttm)
                    except (TypeError, ValueError, ZeroDivisionError):
                        ebitda = None
        if ebitda is None and latest_km:
            ebitda = _safe(latest_km, "ebitda")
            # FMP /key-metrics doesn't expose ebitda directly; derive from
            # ``enterpriseValue / evToEBITDA`` when both fields are present.
            if ebitda is None:
                ev = _safe(latest_km, "enterpriseValue")
                ev_to_ebitda = _safe(latest_km, "evToEBITDA")
                if ev and ev_to_ebitda and float(ev_to_ebitda) != 0:
                    try:
                        ebitda = float(ev) / float(ev_to_ebitda)
                    except (TypeError, ValueError, ZeroDivisionError):
                        ebitda = None
        ratio = None
        if total_debt is not None and ebitda and float(ebitda) != 0:
            try:
                ratio = float(total_debt) / float(ebitda)
            except (TypeError, ValueError):
                ratio = None
        alert = None
        if ratio is not None and ratio > 4.0:
            alert = "ERROR"
        elif ratio is not None and ratio > 2.5:
            alert = "WARN"
        if ratio is None and debt_to_assets is None:
            rows.append(_bucket_a_inactive(
                ts_code, "L8.fin.debt_pressure",
                "fmp:balance-sheet.derived", now,
                "no_debt_or_ebitda"))
        else:
            payload = {
                "interest_debt_to_ebitda": (
                    round(ratio, 4) if ratio is not None else None),
                "debt_to_assets": (
                    round(debt_to_assets, 4)
                    if debt_to_assets is not None else None),
                "alert_severity": alert,
                "interest_debt_usd": (
                    float(total_debt) if total_debt is not None else None),
                "ebitda_usd": float(ebitda) if ebitda is not None else None,
                "latest_period": period,
            }
            if alert:
                rows.append(_bucket_a_known(
                    ts_code, "L8.fin.debt_pressure", payload,
                    "fmp:balance-sheet.derived", now, 0.8))
            else:
                rows.append((
                    ts_code, "L8.fin.debt_pressure",
                    json.dumps(payload, ensure_ascii=False),
                    "Inactive", 0.0, "fmp:balance-sheet.derived", now,
                ))
    return rows


# ── /grades-historical + /analyst-stock-recommendations + /short-interest ─


def _fetch_grades_cached(symbol: str) -> list[dict]:
    """Pull per-event grade history (one row per upgrade/downgrade/initiate)
    from /grades. FMP's /grades-historical returns aggregate ratings buckets
    (see _fetch_analyst_recs_cached) — different shape, different purpose.
    """

    rows = _cached_get_list(
        _GRADES_CACHE, symbol,
        "/grades",
        {"symbol": symbol, "limit": 200},
    )
    return sorted(rows, key=lambda r: r.get("date") or "", reverse=True)


def _fetch_analyst_recs_cached(symbol: str) -> list[dict]:
    """Pull aggregate rating-bucket distribution. FMP exposes this under
    /grades-historical on Starter (the /analyst-stock-recommendations name
    returns 404 on this tier). The payload schema matches what the older
    /analyst-stock-recommendations endpoint used to return, so we keep the
    same downstream parser."""

    rows = _cached_get_list(
        _ANALYST_REC_CACHE, symbol,
        "/grades-historical",
        {"symbol": symbol, "limit": 12},
    )
    if rows:
        return sorted(rows, key=lambda r: r.get("date") or "", reverse=True)
    # Fall back to the older endpoint name if the new one is unavailable.
    rows = _cached_get_list(
        _ANALYST_REC_CACHE, f"_old_{symbol}",
        "/analyst-stock-recommendations",
        {"symbol": symbol, "limit": 12},
    )
    return sorted(rows, key=lambda r: r.get("date") or "", reverse=True)


_GRADE_SCORE: dict[str, int] = {
    # Buy bucket
    "strong buy": 5, "buy": 4, "outperform": 4, "overweight": 4,
    "accumulate": 4, "positive": 4, "add": 4, "long-term buy": 4,
    "top pick": 5, "market outperform": 4,
    # Hold bucket
    "hold": 3, "neutral": 3, "market perform": 3, "sector perform": 3,
    "equal-weight": 3, "in-line": 3, "peer perform": 3,
    # Sell bucket
    "underperform": 2, "underweight": 2, "reduce": 2, "negative": 2,
    "sell": 1, "strong sell": 1, "weak hold": 2, "market underperform": 2,
    "below average": 2,
}


def _classify_grade(grade: str) -> tuple[str, int | None]:
    """Map FMP grade text → (bucket, 1..5 score). Unknown grade → (None, None)."""

    g = (grade or "").strip().lower()
    if not g:
        return ("", None)
    score = _GRADE_SCORE.get(g)
    if score is None:
        # Crude keyword fallback
        if any(k in g for k in ("strong buy", "top pick")):
            score = 5
        elif any(k in g for k in ("buy", "outperform", "overweight",
                                  "accumulate", "positive", "long-term")):
            score = 4
        elif any(k in g for k in ("hold", "neutral", "market perform",
                                  "sector perform", "equal", "in-line")):
            score = 3
        elif any(k in g for k in ("underperform", "underweight",
                                  "reduce", "negative")):
            score = 2
        elif any(k in g for k in ("sell",)):
            score = 1
    if score is None:
        return (g, None)
    bucket = (
        "strong_buy" if score == 5 else
        "buy" if score == 4 else
        "hold" if score == 3 else
        "sell" if score == 2 else
        "strong_sell"
    )
    return (bucket, score)


def fetch_grades_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Emit L6.priced.analyst_revision + L7.mood.analyst_rating +
    L9.media.analyst_action from /grades-historical."""

    if not api_key:
        return []

    today = datetime.now(timezone.utc).date()
    cutoff_90d = (today - timedelta(days=90)).isoformat()
    cutoff_7d = (today - timedelta(days=7)).isoformat()

    now = int(time.time())
    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        data = _fetch_grades_cached(sym)
        # data is desc; filter to last 90d.
        recent = [
            r for r in data
            if (_iso_date(r.get("date")) or "") >= cutoff_90d
        ]
        if not recent:
            rows.append(_bucket_a_inactive(
                ts_code, "L6.priced.analyst_revision",
                "fmp:grades-historical", now, "no_grades_90d"))
            rows.append(_bucket_a_inactive(
                ts_code, "L7.mood.analyst_rating",
                "fmp:grades-historical", now, "no_grades_90d"))
            rows.append(_bucket_a_inactive(
                ts_code, "L9.media.analyst_action",
                "fmp:grades-historical", now, "no_grades_7d"))
            continue

        # ── L6.priced.analyst_revision (90d) ──
        upgrades = downgrades = maintains = initiations = 0
        by_broker: dict[str, list[dict]] = {}
        for r in recent:
            broker = str(r.get("gradingCompany") or "")
            if not broker:
                continue
            by_broker.setdefault(broker, []).append(r)
        for lst in by_broker.values():
            lst.sort(key=lambda x: x.get("date") or "")
        for broker, lst in by_broker.items():
            last_score: int | None = None
            for r in lst:
                action = (r.get("action") or "").lower()
                _, score = _classify_grade(r.get("newGrade") or r.get("grade")
                                           or "")
                if score is None:
                    continue
                if action == "initiate" or last_score is None:
                    initiations += 1
                elif action == "upgrade" or score > last_score:
                    upgrades += 1
                elif action == "downgrade" or score < last_score:
                    downgrades += 1
                else:
                    maintains += 1
                last_score = score
        denom = upgrades + downgrades + maintains
        net = (upgrades - downgrades) / denom if denom > 0 else 0.0
        rev_payload = {
            "upgrades": upgrades,
            "downgrades": downgrades,
            "maintains": maintains,
            "initiations": initiations,
            "net_revision_score": round(net, 4),
            "period_days": 90,
            "n_reports": len(recent),
        }
        rows.append(_bucket_a_known(
            ts_code, "L6.priced.analyst_revision", rev_payload,
            "fmp:grades-historical", now, 0.75))

        # ── L7.mood.analyst_rating — distribution from /analyst-rec ──
        rec_rows = _fetch_analyst_recs_cached(sym)
        if rec_rows:
            cur = rec_rows[0]
            sb = int(_safe(cur, "analystRatingsStrongBuy") or 0)
            b = int(_safe(cur, "analystRatingsBuy") or 0)
            h = int(_safe(cur, "analystRatingsHold") or 0)
            s = int(_safe(cur, "analystRatingsSell") or 0)
            ss = int(_safe(cur, "analystRatingsStrongSell") or 0)
            total = sb + b + h + s + ss
            if total > 0:
                avg = (sb * 5 + b * 4 + h * 3 + s * 2 + ss * 1) / total
                rating_payload = {
                    "strong_buy": sb,
                    "buy": b,
                    "hold": h,
                    "sell": s,
                    "strong_sell": ss,
                    "n_reports": total,
                    "avg_rating_score": round(avg, 4),
                    "as_of": cur.get("date"),
                    "period_days": 30,
                }
                rows.append(_bucket_a_known(
                    ts_code, "L7.mood.analyst_rating", rating_payload,
                    "fmp:analyst-stock-recommendations", now, 0.8))
            else:
                # Fall back to /grades-historical bucket count.
                bucket_counts = {"strong_buy": 0, "buy": 0, "hold": 0,
                                 "sell": 0, "strong_sell": 0}
                scores: list[int] = []
                for r in recent:
                    bk, sc = _classify_grade(r.get("newGrade")
                                             or r.get("grade") or "")
                    if sc is None:
                        continue
                    bucket_counts[bk] = bucket_counts.get(bk, 0) + 1
                    scores.append(sc)
                if scores:
                    rows.append(_bucket_a_known(
                        ts_code, "L7.mood.analyst_rating",
                        {**bucket_counts,
                         "n_reports": len(scores),
                         "avg_rating_score": round(
                             sum(scores) / len(scores), 4),
                         "period_days": 90,
                         "source": "grades-historical_fallback"},
                        "fmp:grades-historical.derived", now, 0.7))
                else:
                    rows.append(_bucket_a_inactive(
                        ts_code, "L7.mood.analyst_rating",
                        "fmp:analyst-stock-recommendations", now,
                        "no_ratings_or_grades"))
        else:
            # /analyst-stock-recommendations unavailable — derive from grades.
            bucket_counts = {"strong_buy": 0, "buy": 0, "hold": 0,
                             "sell": 0, "strong_sell": 0}
            scores = []
            for r in recent:
                bk, sc = _classify_grade(r.get("newGrade") or r.get("grade")
                                         or "")
                if sc is None:
                    continue
                bucket_counts[bk] = bucket_counts.get(bk, 0) + 1
                scores.append(sc)
            if scores:
                rows.append(_bucket_a_known(
                    ts_code, "L7.mood.analyst_rating",
                    {**bucket_counts,
                     "n_reports": len(scores),
                     "avg_rating_score": round(sum(scores) / len(scores), 4),
                     "period_days": 90,
                     "source": "grades-historical_fallback"},
                    "fmp:grades-historical.derived", now, 0.7))
            else:
                rows.append(_bucket_a_inactive(
                    ts_code, "L7.mood.analyst_rating",
                    "fmp:analyst-stock-recommendations", now,
                    "no_ratings"))

        # ── L9.media.analyst_action — 7d rating changes ──
        recent_7d = [
            r for r in recent
            if (_iso_date(r.get("date")) or "") >= cutoff_7d
        ]
        recent_changes: list[dict] = []
        up7 = down7 = 0
        for r in recent_7d:
            action = (r.get("action") or "").lower()
            new_g = r.get("newGrade") or r.get("grade")
            prev_g = r.get("previousGrade")
            if action in ("upgrade", "up"):
                up7 += 1
                ctype = "upgrade"
            elif action in ("downgrade", "down"):
                down7 += 1
                ctype = "downgrade"
            else:
                # If we have prev grade, infer.
                _, sc_new = _classify_grade(new_g or "")
                _, sc_prev = _classify_grade(prev_g or "")
                if (sc_new is not None and sc_prev is not None
                        and sc_new != sc_prev):
                    if sc_new > sc_prev:
                        up7 += 1
                        ctype = "upgrade"
                    else:
                        down7 += 1
                        ctype = "downgrade"
                else:
                    continue
            recent_changes.append({
                "date": _iso_date(r.get("date")),
                "broker": r.get("gradingCompany"),
                "prev_rating": prev_g,
                "new_rating": new_g,
                "change_type": ctype,
            })
        count_7d = up7 + down7
        if count_7d == 0:
            rows.append((
                ts_code, "L9.media.analyst_action",
                json.dumps({
                    "recent_changes": [],
                    "count_7d": 0,
                    "upgrades_7d": 0,
                    "downgrades_7d": 0,
                    "action_type": "none",
                }, ensure_ascii=False),
                "Inactive", 0.0, "fmp:grades-historical.derived", now,
            ))
        else:
            action_type = ("upgrade_event" if up7 > down7 else
                           "downgrade_event" if down7 > up7 else
                           "mixed_event")
            rows.append(_bucket_a_known(
                ts_code, "L9.media.analyst_action",
                {
                    "recent_changes": recent_changes[:10],
                    "count_7d": count_7d,
                    "upgrades_7d": up7,
                    "downgrades_7d": down7,
                    "action_type": action_type,
                },
                "fmp:grades-historical.derived", now, 0.8))
    return rows


def fetch_short_interest_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Emit L7.trade.margin_short from /short-interest (Premium) with a
    /key-metrics-ttm.shortRatio fallback on 401/403/empty."""

    if not api_key:
        return []
    now = int(time.time())
    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)
        # Try /short-interest first (may 401 on Starter).
        cached = _SHORT_INTEREST_CACHE.get(sym)
        now_s = int(time.time())
        if cached and (now_s - cached[0]) < _BUCKET_A_FMP_TTL_S:
            data = cached[1]
        else:
            data = _get_json("/short-interest", {"symbol": sym})
            _SHORT_INTEREST_CACHE[sym] = (now_s, data if data is not None else [])

        short_ratio = None
        days_to_cover = None
        short_pct_float = None
        as_of = None
        source = "fmp:short-interest"
        if isinstance(data, list) and data:
            r = data[0]
            short_ratio = _safe(r, "shortInterestRatio")
            short_pct_float = _safe(r, "shortInterestPercentFloat") \
                or _safe(r, "shortPercentOfFloat")
            days_to_cover = _safe(r, "daysToCover")
            as_of = r.get("date") or r.get("settlementDate")

        # Fallback to /key-metrics-ttm.shortRatio if /short-interest empty
        if short_ratio is None and short_pct_float is None:
            km = _fetch_key_metrics_ttm_cached(sym)
            if km and isinstance(km, list) and km:
                sr = _safe(km[0], "shortRatio") or _safe(km[0],
                                                         "shortRatioTTM")
                if sr is not None:
                    try:
                        short_ratio = float(sr)
                        source = "fmp:key-metrics-ttm.fallback"
                    except (TypeError, ValueError):
                        short_ratio = None

        if (short_ratio is None and short_pct_float is None
                and days_to_cover is None):
            rows.append(_bucket_a_inactive(
                ts_code, "L7.trade.margin_short", source, now,
                "no_short_interest_available"))
            continue
        payload = {
            "short_interest_ratio": (
                float(short_ratio) if short_ratio is not None else None),
            "short_pct_float": (
                float(short_pct_float)
                if short_pct_float is not None else None),
            "days_to_cover": (
                float(days_to_cover) if days_to_cover is not None else None),
            "as_of": as_of,
            "unit": "ratio",
        }
        rows.append(_bucket_a_known(
            ts_code, "L7.trade.margin_short", payload, source, now, 0.7))
    return rows


# ── /earnings-calendar + /historical-buyback + /dividends-calendar ────────


def _fetch_earnings_calendar_cached(symbol: str) -> list[dict]:
    rows = _cached_get_list(
        _EARNINGS_CAL_CACHE, symbol,
        "/earnings-calendar",
        {"symbol": symbol, "limit": 20},
    )
    return sorted(rows, key=lambda r: r.get("date") or "", reverse=True)


def _fetch_buyback_cached(symbol: str) -> list[dict]:
    # On Starter the "historical buyback" endpoint may 401; cache an empty
    # list to short-circuit retries within the TTL.
    rows = _cached_get_list(
        _BUYBACK_CACHE, symbol,
        "/historical-buyback",
        {"symbol": symbol, "limit": 8},
    )
    return sorted(rows, key=lambda r: r.get("date") or "", reverse=True)


def _fetch_dividends_cached(symbol: str) -> list[dict]:
    rows = _cached_get_list(
        _DIVIDENDS_CACHE, symbol,
        "/dividends",
        {"symbol": symbol, "limit": 8},
    )
    return sorted(rows, key=lambda r: r.get("date") or "", reverse=True)


def fetch_earnings_buyback_dividend_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Emit L5.fcst.guidance_change + L9.company.buyback_dividend +
    L9.company.earnings_guidance."""

    if not api_key:
        return []

    today_iso = datetime.now(timezone.utc).date().isoformat()
    now = int(time.time())
    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)

        # ── L5.fcst.guidance_change — compare last two annual estimates ──
        est = _cached_get_list(
            {}, sym,  # not cached separately (cheap, called once per cycle)
            "/analyst-estimates",
            {"symbol": sym, "period": "annual"},
            ttl=_BUCKET_A_FMP_TTL_S,
        )
        # est is desc by date by FMP convention; sort defensively.
        est_sorted = sorted(est, key=lambda r: r.get("date") or "",
                            reverse=True)
        forward = [r for r in est_sorted
                   if (r.get("date") or "") > today_iso]
        forward.sort(key=lambda r: r.get("date") or "")  # nearest first
        if len(forward) >= 2:
            # ``prev`` = nearer forward year (the period closer to "now"),
            # ``cur``  = next forward year. The delta captures the forward
            # trajectory of consensus EPS — a positive delta means analysts
            # see EPS growing y/y → upgraded outlook; negative → downgraded.
            prev = forward[0]
            cur = forward[1]
            cur_eps = _safe(cur, "epsAvg")
            prev_eps = _safe(prev, "epsAvg")
            if cur_eps is not None and prev_eps is not None and prev_eps != 0:
                try:
                    delta = (float(cur_eps) - float(prev_eps))
                    delta_pct = (delta / abs(float(prev_eps))) * 100.0
                except (TypeError, ValueError):
                    delta_pct = None
                direction = "unchanged"
                if delta_pct is not None:
                    if delta_pct > 1.0:
                        direction = "upgraded"
                    elif delta_pct < -1.0:
                        direction = "downgraded"
                rows.append(_bucket_a_known(
                    ts_code, "L5.fcst.guidance_change",
                    {
                        "prev_eps_avg": float(prev_eps),
                        "current_eps_avg": float(cur_eps),
                        "delta_pct": (
                            round(delta_pct, 4)
                            if delta_pct is not None else None),
                        "change_direction": direction,
                        "current_period": cur.get("date"),
                        "prev_period": prev.get("date"),
                        "source_endpoint": "analyst-estimates.forward_trajectory",
                    },
                    "fmp:analyst-estimates.derived", now, 0.75))
            else:
                rows.append(_bucket_a_inactive(
                    ts_code, "L5.fcst.guidance_change",
                    "fmp:analyst-estimates.derived", now,
                    "missing_eps_avg_in_estimates"))
        elif len(forward) == 1:
            cur = forward[0]
            rows.append(_bucket_a_known(
                ts_code, "L5.fcst.guidance_change",
                {
                    "prev_eps_avg": None,
                    "current_eps_avg": _safe(cur, "epsAvg"),
                    "delta_pct": None,
                    "change_direction": "new",
                    "current_period": cur.get("date"),
                    "prev_period": None,
                },
                "fmp:analyst-estimates.derived", now, 0.6))
        else:
            rows.append(_bucket_a_inactive(
                ts_code, "L5.fcst.guidance_change",
                "fmp:analyst-estimates.derived", now,
                "no_forward_estimates"))

        # ── L9.company.buyback_dividend ──
        buybacks = _fetch_buyback_cached(sym)
        dividends = _fetch_dividends_cached(sym)
        # If buyback endpoint locked, fall back to /cash-flow-statement
        # commonStockRepurchased we already cached above.
        if not buybacks:
            cf = _fetch_cf_cached(sym, limit=4)
            buyback_proxy = []
            for r in cf:
                amt = _safe(r, "commonStockRepurchased")
                if amt is None:
                    continue
                try:
                    buyback_proxy.append({
                        "date": r.get("date"),
                        "amount": abs(float(amt)),
                        "fiscal_period": r.get("date"),
                        "source": "cash-flow.commonStockRepurchased",
                    })
                except (TypeError, ValueError):
                    continue
        else:
            buyback_proxy = [{
                "date": r.get("date"),
                "amount": _safe(r, "amount") or _safe(r, "totalCost"),
                "shares": _safe(r, "shares") or _safe(r, "buybackShares"),
                "source": "historical-buyback",
            } for r in buybacks[:4]]
        div_list = []
        for r in dividends[:4]:
            div_list.append({
                "date": r.get("date") or r.get("declarationDate"),
                "cash_div_per_share": _safe(r, "dividend") or _safe(r,
                                                                   "adjDividend"),
                "pay_date": r.get("paymentDate") or r.get("payDate"),
                "record_date": r.get("recordDate"),
            })
        if not buyback_proxy and not div_list:
            rows.append(_bucket_a_inactive(
                ts_code, "L9.company.buyback_dividend",
                "fmp:buyback+dividends", now,
                "no_buyback_or_dividend_history"))
        else:
            rows.append(_bucket_a_known(
                ts_code, "L9.company.buyback_dividend",
                {
                    "buybacks": buyback_proxy,
                    "dividends": div_list,
                    "latest_buyback_date": (
                        buyback_proxy[0]["date"] if buyback_proxy else None),
                    "latest_dividend_date": (
                        div_list[0]["date"] if div_list else None),
                    "as_of": today_iso,
                    "unit": "USD",
                },
                "fmp:buyback+dividends", now, 0.75))

        # ── L9.company.earnings_guidance — next earnings event ──
        cal = _fetch_earnings_calendar_cached(sym)
        upcoming = [r for r in cal
                    if (r.get("date") or "") > today_iso]
        upcoming.sort(key=lambda r: r.get("date") or "")
        past = [r for r in cal
                if (r.get("date") or "") <= today_iso]
        past.sort(key=lambda r: r.get("date") or "", reverse=True)
        if upcoming or past:
            rec = upcoming[0] if upcoming else past[0]
            is_upcoming = bool(upcoming)
            rows.append(_bucket_a_known(
                ts_code, "L9.company.earnings_guidance",
                {
                    "next_earnings_date": rec.get("date"),
                    "is_upcoming": is_upcoming,
                    "eps_estimated": _safe(rec, "epsEstimated"),
                    "eps_actual": _safe(rec, "epsActual"),
                    "revenue_estimated": _safe(rec, "revenueEstimated"),
                    "revenue_actual": _safe(rec, "revenueActual"),
                    "fiscal_period": rec.get("fiscalDateEnding")
                                     or rec.get("date"),
                    "unit": "USD",
                },
                "fmp:earnings-calendar", now, 0.8))
        else:
            rows.append(_bucket_a_inactive(
                ts_code, "L9.company.earnings_guidance",
                "fmp:earnings-calendar", now,
                "no_earnings_calendar_data"))
    return rows


# ── Price-history derived: state.*, val.*, run_up (6 dp_ids) ──────────────


def _fetch_stock_peers_cached(symbol: str) -> list[str]:
    """Return the list of FMP-suggested peer symbols for ``symbol``. Caches
    the list with the same 10-min TTL. Falls back to ``[]`` on any error.
    """

    now_s = int(time.time())
    cached = _STOCK_PEERS_CACHE.get(symbol)
    if cached and (now_s - cached[0]) < _BUCKET_A_FMP_TTL_S:
        return cached[1]
    data = _get_json("/stock-peers", {"symbol": symbol})
    peers: list[str] = []
    if isinstance(data, list):
        for r in data:
            if not isinstance(r, dict):
                continue
            ps = r.get("peersList") or r.get("peers") or []
            if isinstance(ps, list):
                for p in ps:
                    if isinstance(p, str) and p and p != symbol:
                        peers.append(p)
            sym = r.get("symbol")
            if isinstance(sym, str) and sym and sym != symbol:
                peers.append(sym)
    elif isinstance(data, dict):
        ps = data.get("peersList") or data.get("peers") or []
        if isinstance(ps, list):
            peers.extend(p for p in ps if isinstance(p, str) and p != symbol)
    # Dedup keeping order
    seen = set()
    unique_peers: list[str] = []
    for p in peers:
        if p in seen:
            continue
        seen.add(p)
        unique_peers.append(p)
    _STOCK_PEERS_CACHE[symbol] = (now_s, unique_peers[:10])
    return unique_peers[:10]


def _percentile_rank(value: float, series: list[float]) -> float | None:
    """Fraction of ``series`` entries strictly less than ``value``."""
    if value is None or not series:
        return None
    n = len(series)
    lt = sum(1 for s in series if s < value)
    return lt / n if n > 0 else None


def fetch_price_state_batch(
    api_key: str | None,
    us_codes: Iterable[tuple[str, str]],
    sleep_s: float = 0.21,
) -> list[tuple]:
    """Emit the 6 price-history derived dp_ids:
    L6.state.historical_percentile, L6.state.expansion_compression,
    L6.state.peer_compare, L10.val.historical_quantile, L10.val.peer,
    L6.priced.run_up.

    Shares ``_PRICE_HIST_CACHE`` with the preprice/technical fetchers so the
    per-symbol price pull happens once per cycle. PE/PB history is computed
    from key-metrics period rows (limited to 5 annual periods). For
    market-wide quantile we use SPY as a Starter-accessible market proxy
    (FMP doesn't expose a market-wide PE_ttm endpoint without bulk-EOD).
    """

    if not api_key:
        return []

    now = int(time.time())
    today_iso = datetime.now(timezone.utc).date().isoformat()

    # Pre-pull SPY series once for L10.val.historical_quantile fallback.
    spy_rows = _fetch_price_history_cached("SPY", lookback_days=260)
    spy_closes = _close_series_asc(spy_rows)

    rows: list[tuple] = []
    for ts_code, sym in us_codes:
        if sleep_s:
            time.sleep(sleep_s)

        # ── Get current PE/PB from /ratios-ttm cache ──
        ratios_cached = _cached_get_list(
            {}, sym, "/ratios-ttm", {"symbol": sym},
        )
        cur_pe = cur_pb = None
        if ratios_cached:
            r = ratios_cached[0]
            cur_pe = _safe(r, "priceToEarningsRatioTTM")
            cur_pb = _safe(r, "priceToBookRatioTTM")

        # ── Build PE/PB history from /key-metrics (5 annual periods) ──
        # FMP /stable's /key-metrics doesn't always expose peRatio/pbRatio
        # directly — derive PE from earningsYield (1/PE) and PB from
        # marketCap / (totalAssets - totalLiabilities) when needed.
        km = _fetch_key_metrics_cached(sym, limit=5)
        pe_history: list[float] = []
        pb_history: list[float] = []
        for r in km:
            pe = _safe(r, "peRatio") or _safe(r, "priceToEarningsRatio")
            pb = _safe(r, "pbRatio") or _safe(r, "priceToBookRatio")
            if pe is None:
                ey = _safe(r, "earningsYield")
                if ey and float(ey) > 0:
                    try:
                        pe = 1.0 / float(ey)
                    except (TypeError, ValueError, ZeroDivisionError):
                        pe = None
            if pe is not None:
                try:
                    fv = float(pe)
                    if fv > 0:
                        pe_history.append(fv)
                except (TypeError, ValueError):
                    pass
            if pb is not None:
                try:
                    fv = float(pb)
                    if fv > 0:
                        pb_history.append(fv)
                except (TypeError, ValueError):
                    pass

        # ── L6.state.historical_percentile + L10.val.historical_quantile ──
        pe_pct = (_percentile_rank(float(cur_pe), pe_history)
                  if cur_pe is not None and pe_history else None)
        pb_pct = (_percentile_rank(float(cur_pb), pb_history)
                  if cur_pb is not None and pb_history else None)
        if pe_pct is not None or pb_pct is not None:
            hist_payload = {
                "pe_percentile": (
                    round(pe_pct, 4) if pe_pct is not None else None),
                "pb_percentile": (
                    round(pb_pct, 4) if pb_pct is not None else None),
                "current_pe": (
                    float(cur_pe) if cur_pe is not None else None),
                "current_pb": (
                    float(cur_pb) if cur_pb is not None else None),
                "history_window_periods": max(len(pe_history),
                                              len(pb_history)),
                "as_of": today_iso,
            }
            rows.append(_bucket_a_known(
                ts_code, "L6.state.historical_percentile", hist_payload,
                "fmp:key-metrics.derived", now, 0.7))
        else:
            rows.append(_bucket_a_inactive(
                ts_code, "L6.state.historical_percentile",
                "fmp:key-metrics.derived", now,
                "insufficient_pe_pb_history"))

        # ── L10.val.historical_quantile — market-wide PE quantile via SPY ──
        spy_pct = None
        if spy_closes and len(spy_closes) >= 60:
            cur_spy = spy_closes[-1]
            spy_window = spy_closes[-250:] if len(spy_closes) >= 250 else spy_closes
            spy_pct = _percentile_rank(cur_spy, spy_window)
        if spy_pct is not None:
            rows.append(_bucket_a_known(
                ts_code, "L10.val.historical_quantile",
                {
                    "market_proxy": "SPY",
                    "price_percentile": round(spy_pct, 4),
                    "current_price": spy_closes[-1] if spy_closes else None,
                    "history_window_days": (
                        min(250, len(spy_closes)) if spy_closes else 0),
                    "as_of": today_iso,
                    "stock_pe_percentile": (
                        round(pe_pct, 4) if pe_pct is not None else None),
                    "method": "spy_price_quantile + stock_pe_percentile",
                },
                "fmp:historical-price.derived", now, 0.65))
        elif pe_pct is not None:
            # Fall back to stock-level PE percentile only.
            rows.append(_bucket_a_known(
                ts_code, "L10.val.historical_quantile",
                {
                    "market_proxy": None,
                    "price_percentile": None,
                    "stock_pe_percentile": round(pe_pct, 4),
                    "history_window_days": 0,
                    "as_of": today_iso,
                    "method": "stock_pe_only (SPY unavailable)",
                },
                "fmp:key-metrics.derived", now, 0.5))
        else:
            rows.append(_bucket_a_inactive(
                ts_code, "L10.val.historical_quantile",
                "fmp:historical-price.derived", now,
                "no_spy_or_pe_history"))

        # ── L6.state.expansion_compression — PE current vs 60d/250d MA ──
        # FMP doesn't expose daily PE_ttm history per symbol on Starter; we
        # use price as a proxy (assumes EPS is roughly constant intra-year,
        # which is good enough as a directional regime classifier).
        price_rows = _fetch_price_history_cached(sym, lookback_days=260)
        closes = _close_series_asc(price_rows)
        if cur_pe is not None and len(closes) >= 60:
            cur_price = closes[-1]
            window_60 = closes[-60:]
            window_250 = closes[-250:] if len(closes) >= 250 else closes
            ma_60 = sum(window_60) / len(window_60)
            ma_250 = sum(window_250) / len(window_250)
            if ma_250 and ma_250 > 0:
                ratio = cur_price / ma_250
                if ratio < 0.95:
                    regime = "compressed"
                elif ratio > 1.05:
                    regime = "expanded"
                else:
                    regime = "neutral"
                slope = (cur_price - ma_250) / ma_250
                rows.append(_bucket_a_known(
                    ts_code, "L6.state.expansion_compression",
                    {
                        "pe_current": float(cur_pe),
                        "price_current": cur_price,
                        "price_60d_ma": round(ma_60, 4),
                        "price_250d_ma": round(ma_250, 4),
                        "ratio_vs_250d": round(ratio, 4),
                        "slope": round(slope, 4),
                        "regime": regime,
                        "n_days_60d": len(window_60),
                        "n_days_250d": len(window_250),
                        "method": "price_proxy_for_pe_ma",
                    },
                    "fmp:historical-price.derived", now, 0.65))
            else:
                rows.append(_bucket_a_inactive(
                    ts_code, "L6.state.expansion_compression",
                    "fmp:historical-price.derived", now,
                    "ma_250d_zero_or_missing"))
        else:
            rows.append(_bucket_a_inactive(
                ts_code, "L6.state.expansion_compression",
                "fmp:historical-price.derived", now,
                "insufficient_price_history_or_no_pe"))

        # ── L6.state.peer_compare + L10.val.peer ──
        peers = _fetch_stock_peers_cached(sym)
        peer_pes: list[float] = []
        peer_pbs: list[float] = []
        peer_details: list[dict] = []
        # Avoid HTTP per-peer if many peers; cap to 5.
        for p in peers[:5]:
            pr = _cached_get_list(
                {}, p, "/ratios-ttm", {"symbol": p},
            )
            if not pr:
                continue
            pe_p = _safe(pr[0], "priceToEarningsRatioTTM")
            pb_p = _safe(pr[0], "priceToBookRatioTTM")
            if pe_p is not None:
                try:
                    fv = float(pe_p)
                    if fv > 0:
                        peer_pes.append(fv)
                except (TypeError, ValueError):
                    pass
            if pb_p is not None:
                try:
                    fv = float(pb_p)
                    if fv > 0:
                        peer_pbs.append(fv)
                except (TypeError, ValueError):
                    pass
            peer_details.append({"symbol": p, "pe": pe_p, "pb": pb_p})

        if cur_pe is not None and peer_pes:
            sorted_pes = sorted(peer_pes)
            mid = len(sorted_pes) // 2
            median_pe = (sorted_pes[mid] if len(sorted_pes) % 2 == 1 else
                         (sorted_pes[mid - 1] + sorted_pes[mid]) / 2.0)
            median_pb = None
            if peer_pbs:
                sorted_pbs = sorted(peer_pbs)
                mid_b = len(sorted_pbs) // 2
                median_pb = (sorted_pbs[mid_b] if len(sorted_pbs) % 2 == 1
                             else (sorted_pbs[mid_b - 1]
                                   + sorted_pbs[mid_b]) / 2.0)
            premium_pct = ((float(cur_pe) - median_pe)
                           / median_pe * 100.0) if median_pe > 0 else None
            validation = ("convergent"
                          if premium_pct is not None
                          and abs(premium_pct) < 15.0
                          else "divergent")
            peer_compare = {
                "stock_pe": float(cur_pe),
                "peer_pe_median": round(median_pe, 4),
                "premium_vs_peers_pct": (
                    round(premium_pct, 4)
                    if premium_pct is not None else None),
                "peer_count": len(peer_pes),
                "peers": [p["symbol"] for p in peer_details],
            }
            val_peer = {
                "stock_pe": float(cur_pe),
                "stock_pb": float(cur_pb) if cur_pb is not None else None,
                "peer_pe_median": round(median_pe, 4),
                "peer_pb_median": (
                    round(median_pb, 4) if median_pb is not None else None),
                "premium_vs_peers_pct": (
                    round(premium_pct, 4)
                    if premium_pct is not None else None),
                "validation_signal": validation,
                "peer_count": len(peer_pes),
                "peers": [p["symbol"] for p in peer_details],
                "as_of": today_iso,
            }
            rows.append(_bucket_a_known(
                ts_code, "L6.state.peer_compare", peer_compare,
                "fmp:stock-peers.derived", now, 0.7))
            rows.append(_bucket_a_known(
                ts_code, "L10.val.peer", val_peer,
                "fmp:stock-peers.derived", now, 0.7))
        else:
            reason = ("no_peers" if not peers else
                      "no_peer_pe_data" if not peer_pes else
                      "missing_stock_pe")
            rows.append(_bucket_a_inactive(
                ts_code, "L6.state.peer_compare",
                "fmp:stock-peers.derived", now, reason))
            rows.append(_bucket_a_inactive(
                ts_code, "L10.val.peer",
                "fmp:stock-peers.derived", now, reason))

        # ── L6.priced.run_up — 5/20/60d price change relative to SPX ──
        if len(closes) >= 7:
            latest = closes[-1]
            # ``closes`` is ascending; index from the end.
            out: dict[str, float | None] = {}
            for window in (5, 20, 60):
                if len(closes) > window:
                    ref = closes[-(window + 1)]
                    if ref and ref != 0:
                        out[f"d{window}_pct"] = round(
                            (latest - ref) / ref, 6)
                    else:
                        out[f"d{window}_pct"] = None
                else:
                    out[f"d{window}_pct"] = None
            # SPX-relative for 20d window (parallels preprice spx_relative_*).
            spx_rel_20 = None
            if len(spy_closes) >= 21:
                spy_latest = spy_closes[-1]
                spy_ref = spy_closes[-21]
                if spy_ref and spy_ref != 0:
                    spy_d20 = (spy_latest - spy_ref) / spy_ref
                    if out.get("d20_pct") is not None:
                        spx_rel_20 = round(
                            out["d20_pct"] - spy_d20, 6)
            rows.append(_bucket_a_known(
                ts_code, "L6.priced.run_up",
                {
                    **out,
                    "spx_relative_20d": spx_rel_20,
                    "latest_close": latest,
                    "history_days": len(closes),
                    "as_of": today_iso,
                },
                "fmp:historical-price.derived", now, 0.75))
        else:
            rows.append(_bucket_a_inactive(
                ts_code, "L6.priced.run_up",
                "fmp:historical-price.derived", now,
                "insufficient_price_history"))
    return rows


# ── Top-level Bucket-A orchestrator ───────────────────────────────────────


def fetch_bucket_a_mirror_batch(
    constituents: Iterable[dict],
    tick: int,
    now: int | None = None,
) -> list[tuple]:
    """Emit the 22 Bucket-A mirror dp_ids for every US ts_code.

    Wraps each sub-fetcher in its own try/except so a single endpoint outage
    (e.g. /short-interest 401 on Starter, /historical-buyback locked) doesn't
    poison the rest of the batch.
    """

    api_key = _get_api_key()
    if not api_key:
        return []

    us_tickers: list[tuple[str, str]] = []
    for c in constituents:
        ts = c.get("ts_code")
        if ts and is_us(ts):
            sym = to_fmp_symbol(ts)
            if sym:
                us_tickers.append((ts, sym))
    if not us_tickers:
        return []

    rows: list[tuple] = []

    try:
        rows.extend(fetch_segments_batch(api_key, us_tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] segments batch failed: %s", exc)

    try:
        rows.extend(fetch_financial_derived_batch(api_key, us_tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] financial-derived batch failed: %s", exc)

    try:
        rows.extend(fetch_grades_batch(api_key, us_tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] grades batch failed: %s", exc)

    try:
        rows.extend(fetch_short_interest_batch(api_key, us_tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] short-interest batch failed: %s", exc)

    try:
        rows.extend(fetch_earnings_buyback_dividend_batch(api_key, us_tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] earnings/buyback/dividend batch failed: %s", exc)

    try:
        rows.extend(fetch_price_state_batch(api_key, us_tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] price-state batch failed: %s", exc)

    return rows


def fetch_batch(constituents: Iterable[dict], tick: int) -> list[tuple]:
    """Pull US fundamentals (income / balance sheet / cash flow / key metrics)
    for every ``.US`` ts_code in the universe.

    HK / A-share rows are silently skipped (Futu and Tushare handle them).
    """

    if not _get_api_key():
        log.warning("[fmp] FMP_API_KEY missing — skipping batch")
        return []

    us_tickers: list[tuple[str, str]] = []  # (ts_code, fmp_symbol)
    for c in constituents:
        ts = c.get("ts_code")
        if ts and is_us(ts):
            sym = to_fmp_symbol(ts)
            if sym:
                us_tickers.append((ts, sym))

    if not us_tickers:
        return []

    now = int(time.time())
    rows: list[tuple] = []

    # ── Bulk income-statement (per symbol; Starter doesn't expose batch) ──
    # Limit concurrency by sequential calls; Starter is rate-limited at
    # 300 calls/min so 115 US × 4 endpoints = 460 calls — well under limit.
    for ts_code, sym in us_tickers:
        # ── /income-statement?symbol=X&limit=1 (latest annual) ──
        inc = _get_json("/income-statement", {"symbol": sym, "limit": 1})
        if inc and isinstance(inc, list) and inc:
            r = inc[0]
            revenue = _safe(r, "revenue")
            gross_profit = _safe(r, "grossProfit")
            op_income = _safe(r, "operatingIncome")
            net_income = _safe(r, "netIncome")
            cogs = _safe(r, "costOfRevenue")
            sga = _safe(r, "sellingGeneralAndAdministrativeExpenses")
            rd = _safe(r, "researchAndDevelopmentExpenses")
            # Margins: stable endpoint dropped grossProfitRatio /
            # operatingIncomeRatio / netIncomeRatio columns — derive ourselves
            # so we don't lose coverage when FMP renames fields.
            gross_margin = (gross_profit / revenue) if (gross_profit is not None and revenue) else None
            op_margin = (op_income / revenue) if (op_income is not None and revenue) else None
            net_margin = (net_income / revenue) if (net_income is not None and revenue) else None
            period = r.get("date") or r.get("calendarYear")

            scalar_mappings: list[tuple[str, float | None, str]] = [
                ("L5.is.revenue", revenue, "USD"),
                ("L5.is.gross_profit", gross_profit, "USD"),
                ("L5.is.gross_margin", gross_margin, "ratio"),
                ("L5.is.operating_profit", op_income, "USD"),
                ("L5.is.net_profit", net_income, "USD"),
                ("L5.is.eps", _safe(r, "eps"), "USD/share"),
                ("L5.is.cogs", cogs, "USD"),
            ]
            for dp_id, val, unit in scalar_mappings:
                if val is None:
                    continue
                try:
                    rows.append((
                        ts_code, dp_id,
                        json.dumps({"scalar": float(val), "unit": unit,
                                    "period": period}, ensure_ascii=False),
                        "Known", 0.85, "fmp:income-statement", now,
                    ))
                except (TypeError, ValueError):
                    continue

            # L5.is.margins — combined operating/net margins
            if op_margin is not None or net_margin is not None:
                rows.append((
                    ts_code, "L5.is.margins",
                    json.dumps({
                        "operating": op_margin,
                        "net": net_margin,
                        "period": period,
                    }, ensure_ascii=False),
                    "Known", 0.85, "fmp:income-statement", now,
                ))

            # L5.is.sga_rd — 三费 (SG&A + R&D). FMP gives SG&A as a single
            # combined line (sellingGeneralAndAdministrativeExpenses) plus a
            # separate R&D line — mirroring tushare's sga_total + rd_exp.
            if sga is not None or rd is not None:
                sga_val = float(sga) if sga is not None else 0.0
                rd_val = float(rd) if rd is not None else 0.0
                total = sga_val + rd_val
                rows.append((
                    ts_code, "L5.is.sga_rd",
                    json.dumps({
                        "sga": sga_val if sga is not None else None,
                        "rd": rd_val if rd is not None else None,
                        "total": total,
                        "sga_rd_ratio_revenue": (total / revenue) if revenue else None,
                        "unit": "USD",
                        "period": period,
                    }, ensure_ascii=False),
                    "Known", 0.85, "fmp:income-statement", now,
                ))

        # ── /ratios-ttm?symbol=X (PE / PB / PS / P/FCF / PEG) ──
        ratios = _get_json("/ratios-ttm", {"symbol": sym})
        if ratios and isinstance(ratios, list) and ratios:
            r = ratios[0]
            mappings = [
                ("L6.mult.pe", _safe(r, "priceToEarningsRatioTTM")),
                ("L6.mult.pb", _safe(r, "priceToBookRatioTTM")),
                ("L6.mult.ps", _safe(r, "priceToSalesRatioTTM")),
                ("L6.mult.mcap_fcf", _safe(r, "priceToFreeCashFlowRatioTTM")),
                ("L6.mult.peg", _safe(r, "priceToEarningsGrowthRatioTTM")),
            ]
            for dp_id, val in mappings:
                if val is None:
                    continue
                try:
                    rows.append((
                        ts_code, dp_id,
                        json.dumps({"scalar": float(val), "unit": "ratio", "ttm": True},
                                   ensure_ascii=False),
                        "Known", 0.85, "fmp:ratios-ttm", now,
                    ))
                except (TypeError, ValueError):
                    continue

        # ── /key-metrics-ttm?symbol=X (EV/EBITDA TTM) ──
        # New on Starter as of 2025-08-31 (replaces v3 /enterprise-values).
        # Single field of interest right now; the endpoint also serves
        # working_capital / returnOnInvestedCapitalTTM / etc. for future use.
        km = _get_json("/key-metrics-ttm", {"symbol": sym})
        if km and isinstance(km, list) and km:
            r = km[0]
            ev_ebitda = _safe(r, "evToEBITDATTM")
            if ev_ebitda is not None:
                try:
                    rows.append((
                        ts_code, "L6.mult.ev_ebitda",
                        json.dumps({"scalar": float(ev_ebitda), "unit": "ratio",
                                    "ttm": True}, ensure_ascii=False),
                        "Known", 0.85, "fmp:key-metrics-ttm", now,
                    ))
                except (TypeError, ValueError):
                    pass

        # ── /balance-sheet-statement?symbol=X&limit=1 (latest annual) ──
        bs = _get_json("/balance-sheet-statement", {"symbol": sym, "limit": 1})
        if bs and isinstance(bs, list) and bs:
            r = bs[0]
            cash = _safe(r, "cashAndCashEquivalents")
            # FMP stable derives totalDebt = shortTermDebt + longTermDebt.
            debt = _safe(r, "totalDebt")
            if debt is None:
                st_debt = _safe(r, "shortTermDebt") or 0
                lt_debt = _safe(r, "longTermDebt") or 0
                debt = st_debt + lt_debt if (st_debt or lt_debt) else None
            tot_assets = _safe(r, "totalAssets")
            tot_liab = _safe(r, "totalLiabilities")
            inventory = _safe(r, "inventory")
            ar = _safe(r, "accountsReceivables")
            ap = _safe(r, "accountPayables")
            goodwill = _safe(r, "goodwill")
            ppe = _safe(r, "propertyPlantEquipmentNet")
            period = r.get("date")
            if cash is not None or debt is not None:
                rows.append((
                    ts_code, "L5.bs.cash_debt",
                    json.dumps({"cash": cash, "debt": debt, "net": (cash or 0) - (debt or 0),
                                "period": period}, ensure_ascii=False),
                    "Known", 0.85, "fmp:balance-sheet", now,
                ))
            if tot_assets and tot_liab is not None:
                rows.append((
                    ts_code, "L5.bs.leverage",
                    json.dumps({"leverage_ratio": tot_liab / tot_assets, "period": period},
                               ensure_ascii=False),
                    "Known", 0.85, "fmp:balance-sheet.derived", now,
                ))
            if inventory is not None:
                rows.append((
                    ts_code, "L5.bs.inventory",
                    json.dumps({
                        "scalar": float(inventory),
                        "inventory_to_assets": (inventory / tot_assets) if tot_assets else None,
                        "unit": "USD",
                        "period": period,
                    }, ensure_ascii=False),
                    "Known", 0.85, "fmp:balance-sheet", now,
                ))
            if ar is not None or ap is not None:
                rows.append((
                    ts_code, "L5.bs.ar_ap",
                    json.dumps({
                        "accounts_receivable": float(ar) if ar is not None else None,
                        "accounts_payable": float(ap) if ap is not None else None,
                        "net_working_capital_change_proxy": (
                            (ar or 0) - (ap or 0)
                        ),
                        "unit": "USD",
                        "period": period,
                    }, ensure_ascii=False),
                    "Known", 0.85, "fmp:balance-sheet", now,
                ))
            if goodwill is not None or ppe is not None:
                rows.append((
                    ts_code, "L5.bs.goodwill_ppe",
                    json.dumps({
                        "goodwill": float(goodwill) if goodwill is not None else None,
                        "fix_assets_ppe": float(ppe) if ppe is not None else None,
                        "goodwill_to_assets": (goodwill / tot_assets) if (goodwill is not None and tot_assets) else None,
                        "unit": "USD",
                        "period": period,
                    }, ensure_ascii=False),
                    "Known", 0.85, "fmp:balance-sheet", now,
                ))

        # ── /cash-flow-statement?symbol=X&limit=1 ──
        cf = _get_json("/cash-flow-statement", {"symbol": sym, "limit": 1})
        if cf and isinstance(cf, list) and cf:
            r = cf[0]
            period = r.get("date")
            ocf = _safe(r, "operatingCashFlow")
            fcf = _safe(r, "freeCashFlow")
            capex = _safe(r, "capitalExpenditure")
            icf = _safe(r, "netCashProvidedByInvestingActivities")
            fncf = _safe(r, "netCashProvidedByFinancingActivities")
            buyback = _safe(r, "commonStockRepurchased")
            # Prefer commonDividendsPaid (common-stock dividends only) over
            # netDividendsPaid (which can include preferred). Fall back to
            # netDividendsPaid when the common-only line isn't reported.
            div_paid = _safe(r, "commonDividendsPaid")
            if div_paid is None:
                div_paid = _safe(r, "netDividendsPaid")
            for dp_id, val in (("L5.cf.ocf", ocf), ("L5.cf.fcf", fcf), ("L5.cf.capex", capex)):
                if val is None:
                    continue
                rows.append((
                    ts_code, dp_id,
                    json.dumps({"scalar": float(val), "unit": "USD", "period": period},
                               ensure_ascii=False),
                    "Known", 0.85, "fmp:cash-flow", now,
                ))
            if icf is not None or fncf is not None:
                rows.append((
                    ts_code, "L5.cf.icf_fcf",
                    json.dumps({
                        "investing_cf": float(icf) if icf is not None else None,
                        "financing_cf": float(fncf) if fncf is not None else None,
                        "unit": "USD",
                        "period": period,
                    }, ensure_ascii=False),
                    "Known", 0.85, "fmp:cash-flow", now,
                ))
            if buyback is not None or div_paid is not None:
                # FMP reports outflows as negatives; take absolute value so
                # the payload reads as "$N spent on buybacks / dividends".
                buyback_amt = abs(float(buyback)) if buyback is not None else None
                div_amt = abs(float(div_paid)) if div_paid is not None else None
                rows.append((
                    ts_code, "L5.cf.buyback_dividend",
                    json.dumps({
                        "dividend_paid": div_amt,
                        "buyback_paid": buyback_amt,
                        "unit": "USD",
                        "period": period,
                    }, ensure_ascii=False),
                    "Known", 0.85, "fmp:cash-flow", now,
                ))

    # ── L9 event injection (per-symbol; sleep 0.21s between calls to stay
    #    well under 300/min Starter quota). 115 US × 2 endpoints ≈ 230
    #    calls → ~49s for the L9 pass.
    api_key = _get_api_key()
    try:
        rows.extend(fetch_sec_filings_batch(api_key, us_tickers, lookback_days=30))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] sec-filings batch failed: %s", exc)
    try:
        rows.extend(fetch_news_batch(api_key, us_tickers, lookback_days=30,
                                     max_items=10))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] news batch failed: %s", exc)

    # ── B.6b: institutional 13D/G holders + insider Form 4 trades ──
    # ~115 US × 2 endpoints ≈ 230 extra calls → ~49s at 0.21s/call.
    # Each function is wrapped in try/except so a single endpoint outage
    # (e.g. Starter tier locking 13F /institutional-ownership) doesn't
    # poison the rest of the batch.
    try:
        rows.extend(fetch_institutional_holders_batch(api_key, us_tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] institutional-holders batch failed: %s", exc)
    try:
        rows.extend(fetch_insider_trades_batch(api_key, us_tickers,
                                               lookback_days=90))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] insider-trades batch failed: %s", exc)

    # ── L5/L6 deep fields: analyst-estimates, DCF, financial-growth ──
    # ~115 US × 3 endpoints ≈ 345 extra calls → ~72s at 0.21s/call. Total
    # cycle (across all FMP endpoints) is now ~115 × ~9 endpoints ≈ 1035
    # calls — well under the 300/min Starter ceiling at 0.21s pacing.
    try:
        rows.extend(fetch_analyst_estimates_batch(api_key, us_tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] analyst-estimates batch failed: %s", exc)
    try:
        rows.extend(fetch_dcf_batch(api_key, us_tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] dcf batch failed: %s", exc)
    try:
        rows.extend(fetch_financial_growth_batch(api_key, us_tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] financial-growth batch failed: %s", exc)

    # ── B.6d: per-stock derived dp_ids (US-only) ──
    # preprice → /earnings + cached price hist (incl. ^GSPC for relative leg)
    # news_age → /news/stock (last 30d)
    # technical → cached price hist only (no extra HTTP after preprice ran)
    # Each fetcher wraps its own try/except internally; an outer guard here
    # mirrors the rest of fetch_batch so an unexpected exception in one
    # fetcher can't poison the others.
    try:
        rows.extend(fetch_preprice_surprise_batch(api_key, us_tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] preprice-surprise batch failed: %s", exc)
    try:
        rows.extend(fetch_news_age_batch(api_key, us_tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] news-age batch failed: %s", exc)
    try:
        rows.extend(fetch_short_technical_batch(api_key, us_tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] short-technical batch failed: %s", exc)

    # ── B.6c: market-level macro (US sentinel "MARKET:US") ──
    # Throttled to every _MACRO_TTL_S seconds; intermediate cycles replay
    # the cache. Wrapped in try/except so any macro endpoint outage doesn't
    # poison the fundamentals batch.
    try:
        rows.extend(fetch_macro_us_batch(now))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] macro_us batch failed: %s", exc)

    # ── B.6e: Bucket-A mirror — 22 dp_ids cloned from the tushare path ──
    # See fetch_bucket_a_mirror_batch + Sub-A1..Sub-A5 fetchers above.
    # Wrapped at the outer level too so any unexpected exception inside any
    # sub-fetcher doesn't poison the fundamentals pass.
    try:
        rows.extend(fetch_bucket_a_mirror_batch(constituents, tick, now))
    except Exception as exc:  # noqa: BLE001
        log.warning("[fmp] bucket-A mirror batch failed: %s", exc)

    return rows
