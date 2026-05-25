# FMP Tier Requirements

Mapping of every mvp20 capability declared on FMP to the **minimum FMP
subscription tier** required to actually call that endpoint. Source: FMP
pricing page + endpoint-level access notes (verified 2026-05-10; check
https://site.financialmodelingprep.com/developer/docs/pricing for current).

> **CURRENT SUBSCRIPTION: Starter** ($14/mo, 300 req/min, 5+ years history)
>
> The 20 Starter-accessible capabilities are declared as `active` on FMP in
> `config/data_providers.yaml`. The 6 capabilities behind Premium / Ultimate
> tiers are listed in `tier_locked_premium` / `tier_locked_ultimate` blocks
> there but **not** in the active capability list — calls to them would
> return `401 Subscription Required`. One of those six has NO fallback
> provider: `earnings_transcripts`. Two Ultimate-tier ones (`esg_score`,
> `government_trading`) also have no fallback. The remaining tier-locked
> capabilities have working fallbacks on Tushare / Futu OpenD (see Fallback
> section below).
>
> **Update 2026-05** — user empirically verified that `sec_filings`,
> `dcf_valuation`, and `analyst_estimates` are reachable on Starter
> (see Changelog at bottom). The table below now follows the active catalog;
> pricing-page-derived historical notes remain in the Changelog.

## Tier ladder

| Tier | Cost | Calls/day or /min | Notable inclusions |
|---|---|---|---|
| **F** Free | $0 | 250 calls/day | Basic price/profile, very limited historical |
| **S** Starter | $14/mo | 300 calls/min | 5+ years history, basic statements, calendars |
| **P** Premium | $29/mo | 750 calls/min | 30+ years history, intraday minute bars, options, 13F, transcripts, SEC, analyst |
| **U** Ultimate | $49/mo | 3000 calls/min | ESG, Senate/House trading, full alternative data |

## Per-capability tier (mvp20 declared)

| mvp20 capability | min tier | sample endpoint | notes |
|---|:---:|---|---|
| **Already in S (Starter) tier** | | | |
| `price_daily` | S | `/historical-price-full` | |
| `company_profile` | S | `/profile` | |
| `fundamentals` (basic) | S | `/income-statement` | Full historical needs P |
| `earnings_calendar` | S | `/earning_calendar` | |
| `news` | S | `/stock_news` | |
| `dividends` | S | `/historical-stock-dividend` | |
| `buyback` | S | `/historical/buyback` | |
| `market_index` | S | `/historical-index` | Full risk-premium needs P |
| `treasury_rates` | S | `/stable/treasury-rates` | Round 4 — DCF discount rate |
| `macro` | S | `/stable/economic-calendar` | US CPI / employment calendar used by `fetch_macro_us_batch` |
| `corporate_actions` | S | `/historical-stock-split` | M&A history needs P |
| `trading_calendar` | S | `/market-hours` | |
| `ipo_calendar` | S | `/ipo_calendar` | |
| `peer_comparison` | S | `/stock_peers` | Round 4 |
| `insider_trading` (basic) | S | `/insider-trading` | Daily updates need P |
| `price_intraday` (1h/4h) | S | `/historical-chart/1hour` | Minute bars need P |
| `analyst_estimates` | S | `/stable/analyst-estimates` | Starter verified 2026-05; also dual-sourced by Tushare `report_rc` |
| `dcf_valuation` | S | `/stable/discounted-cash-flow` | Starter verified 2026-05 |
| `sec_filings` | S | `/stable/sec-filings-search/symbol` | Starter verified 2026-05; FMP single-source |
| `forex` | S | `/stable/historical-price-eod` | EURUSD / DXY style macro inputs |
| **⚠ Need P (Premium $29/mo)** | | | |
| `price_intraday` (1min/5min/15min/30min) | **P** | `/historical-chart/1min` | High-frequency only on Premium |
| `earnings_transcripts` | **P** | `/earning_call_transcript` | NLP fuel for core-pool LLM |
| `institutional_holdings` (13F) | **P** | `/13F` | Tushare covers basic top10 holders on its own; 13F is US-specific |
| `options_chain` | **P** | `/historical-chain` | Futu also covers (deeper; via OpenD) |
| `options_iv` | **P** | `/historical-volatility` | Futu also covers via Greeks |
| `fundamentals` (full historical 30Y) | P | `/income-statement?limit=120` | Basic history is on S |
| **⚠ Need U (Ultimate $49/mo)** | | | |
| `esg_score` | **U** | `/esg-environmental-social-governance-data` | Round 4 |
| `government_trading` | **U** | `/senate-trading` | Round 4 — Pelosi-trades-style alpha |

## What you can do with each tier

### If you have **Starter** ($14/mo)
You get out-of-the-box:
- All baseline US price / fundamentals / news / calendar capabilities
- Round 3 + Round 4 starter additions (treasury_rates, corp_actions, dividends,
  buyback, market_index, peer_comparison, ipo_calendar, trading_calendar)
- Empirically verified 2026-05 additions: SEC filing index, analyst estimates,
  DCF valuation, macro calendar, and forex/DXY-style macro inputs
- Hourly intraday bars (good enough for daily-cycle scoring)

You **cannot** access (these will return 401 / `Subscription Required`):
- Earnings call transcripts → `earnings_transcripts` capability dead
- 13F filings → `institutional_holdings` falls back to Tushare's basic
  `top10_holders` (less granular)
- Options chain / IV → falls back to Futu OpenD (better coverage anyway)
- Minute-bar intraday → `price_intraday` for sub-hourly will not work;
  hourly+ still fine
- ESG / Senate trading → both dead (Ultimate only)

### If you have **Premium** ($29/mo) — *recommended for mvp20 round-3+ scope*
You unlock everything mvp20 declares except:
- ESG screening
- Senate/House trading

This tier mainly adds transcripts, FMP-native options, FMP-native 13F /
institutional endpoints, and minute bars. The two remaining Ultimate gaps
(`esg_score` and `government_trading`) are nice-to-have but not central to the
13-industry graph priors.

### If you have **Free** tier
Severely limited — only `price_daily` and basic `company_profile` work in
practice. **Not recommended for mvp20 production**; even Round 2 capabilities
will hit the 250 calls/day ceiling fast (328 constituents × 1 call/day = 328
just for daily price refresh).

## Fallback / cross-source resilience

For capabilities where FMP is **not** the only declared provider, mvp20 can
silently fall back when FMP returns a tier-mismatch error:

| Capability | FMP tier | Fallback provider(s) | Notes |
|---|:---:|---|---|
| `institutional_holdings` | P | tushare (`top10_*`), futu (`get_holding_change_list`) | Tushare for A; Futu for HK |
| `options_chain` / `options_iv` | P | futu | Futu OpenD via local gateway, deeper |
| `dividends` | S | tushare (`dividend`), akshare, yfinance | 4 sources total |
| `market_index` | S | All 4 other providers | 5-source redundancy |
| `price_intraday` (1min) | P | futu (`get_cur_kline`) | Futu OpenD includes minute bars |
| `earnings_transcripts` | P | — | **No fallback** — single-sourced |
| `esg_score` | U | — | **No fallback** — single-sourced |
| `government_trading` | U | — | **No fallback** — single-sourced |

The tier-locked single-sourced FMP capabilities (`earnings_transcripts`,
`esg_score`, `government_trading`) become **hard dependencies** if your epic
needs them. `sec_filings` is also FMP-single-source, but it is active on the
current Starter plan.

## Action items by current FMP plan

| Your plan | Action |
|---|---|
| **Free** | Upgrade to Starter — Free is too restrictive for 328-constituent daily refresh |
| **Starter** | Current default. OK for active mvp20 FMP capabilities including SEC filing index, analyst estimates, DCF, macro calendar, and forex. Upgrade only for transcripts / FMP-native 13F / FMP-native options / minute bars |
| **Premium** | Sufficient for everything except ESG / Senate trading |
| **Ultimate** | Full coverage; nothing is gated |

## How mvp20 enforces this

`config/data_providers.yaml` now encodes the operator-curated split between
the current Starter `capabilities` list and the `tier_locked_premium` /
`tier_locked_ultimate` blocks. Runtime still needs to handle provider truth:
if an FMP HTTP call comes back 401 with `Subscription Required`, the ingest
client should log `provider_unavailable_reason: insufficient_tier` and route
to fallback providers where available.

## Changelog

- **2026-05-12** — User empirically verified with a Starter API key that the
  following endpoints, previously documented as Premium-locked on the pricing
  page, return 200 with usable payloads:
  - `analyst_estimates`: `GET /stable/analyst-estimates?symbol=AAPL&period=annual`
    returns analyst forecast rows on Starter. Moved from `tier_locked_premium`
    to active `capabilities` in `config/data_providers.yaml`. Capability is
    now dual-sourced (FMP + Tushare `report_rc`).
  - `dcf_valuation`: `GET /stable/discounted-cash-flow?symbol=AAPL` returns
    DCF intrinsic value on Starter. Moved from `tier_locked_premium` to
    active `capabilities`. Capability remains FMP-single-source (no
    fallback) but is no longer tier-locked.
  - `sec_filings`: `GET /stable/sec-filings-search/symbol` returns per-symbol
    SEC filings index on Starter (previously surfaced in B.5 agent probing,
    `fmp_source.fetch_sec_filings_batch` implements it). Moved from
    `tier_locked_premium` to active `capabilities`. Remains FMP-single-source.
  - Net effect: 3 capabilities that were dark on Starter are now active.
    `earnings_transcripts` is the only remaining FMP-only capability still
    locked behind Premium. Tests in `tests/test_providers.py` were updated
    to reflect the new coverage (`test_premium_locked_capabilities_have_no_active_provider`,
    `test_fmp_starter_tier_unique_capabilities`,
    `test_analyst_estimates_dual_sourced_fmp_and_tushare`).
