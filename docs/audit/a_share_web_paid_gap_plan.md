# A-share Web and Paid Data Gap Plan

Generated on 2026-05-26. Scope: A-share spec completion gaps that should not be solved by more Tushare endpoints alone. This document intentionally does not modify the main completion audit, field strategy, tests, README, or frontend files.

## Scope and Current Read

The working audit baseline is: spec total 250 fields; real runtime coverage excluding mock is roughly 111 fields; compiled overlays cover 66 fields; combined coverage is roughly 175 fields; the remaining gap is roughly 75 fields. This plan focuses on fields where the missing work is one of:

- open web evidence with strict checksum and replay
- paid market data, options data, retail/app/traffic panels, or sentiment vendors
- LLM summarization over fetched evidence
- explicit `Unknown`, `Unavailable`, or `N/A` because the metric is not legitimately observable for an A-share issuer

This plan does not propose large scale crawling. Every web path below starts with bounded pilots, allowlisted hosts, raw artifact checksums, and a fallback to `Unknown` rather than fabricated evidence.

## Quick Decisions

| decision | fields | action |
|---|---|---|
| Do not try to solve with Tushare | `L3.delivery.csat`, `L4.eff.conversion_retention`, `L4.volume.foot_traffic`, `L4.volume.frequency` | Use web/paid alt-data only when evidence is issuer-specific and checksumed; otherwise leave `Unknown` or `N/A`. |
| Public web plus LLM is acceptable as a pilot | `L3.delivery.csat`, `L2.newbiz.tam`, selected `L3.product.lifecycle`, selected `L4.share.customer_channel` | Use annual reports, IR pages, app store aggregate ratings, complaint portals, public research releases, and industry-panel press releases. No raw UGC bulk storage. |
| Paid source is required for production-grade values | `L4.volume.foot_traffic`, most `L4.eff.conversion_retention`, most `L4.volume.frequency`, `L7.trade.gamma` | Use retail traffic panels, mobile/app intelligence panels, licensed options/Greeks/OI feeds, or keep `Unknown`. |
| Existing social/theme fields should be hard-source first, not LLM-first | `L0.sentiment.social`, `L7.mood.media_social`, `L7.mood.theme`, `L9.media.social_buzz` | Replace mock rows with real AKShare/Tushare fetches and cache artifacts; LLM may only normalize or summarize after hard evidence exists. |
| A-share per-stock options fields must not be faked | `L7.trade.iv`, `L7.trade.options_cp`, `L7.trade.gamma` | A-share listed options are ETF/index oriented, not broad single-stock options. Per-stock rows should be `N/A`/`Unavailable` unless a legitimate listed option, cross-listing, ETF basket proxy, or licensed vendor mapping exists. |
| Do not crawl now | buy-side whisper, paywalled research PDFs, full social timelines/comments, location traces, app clickstream, minute-level options Greeks without entitlement | Keep out of scope until legal/data entitlement is explicit. |

Reference checks used for source feasibility:

- Tushare `dc_hot` documents Eastmoney App hot rankings, extraction cadence, and non-commercial limitation: <https://tushare.pro/document/2?doc_id=321>
- Futu OpenD option chain API returns static option-chain data and requires separate quote subscription for dynamic quote/order-book fields: <https://openapi.futunn.com/futu-api-doc/quote/get-option-chain.html>
- AKShare changelog confirms `stock_hot_keyword_em` and related hot-rank interfaces exist but also shows repeated fixes, so it should be treated as public best-effort, not a guaranteed SLA source: <https://xlxm.cn/document/akshare/document/changelog.html>
- SSE and SZSE options pages show China exchange equity options are ETF/index-underlying oriented, for example SSE CSI 300 ETF options and SZSE CSI 300 ETF options: <https://english.sse.com.cn/news/newsrelease/c/4970464.shtml>, <https://www.szse.cn/English/products/options/overview/index.html>
- Apple App Store Connect definitions show conversion, sessions, active devices, and retention-style metrics are owner-side analytics and opt-in constrained; third-party/public pages should be treated as proxies unless data entitlement exists: <https://developer.apple.com/help/app-store-connect-analytics/reference/metrics-definitions>

## Field Routing Matrix

| field | current A-share gap shape | Tushare fit | acceptable source type | route | refresh | storage |
|---|---|---|---|---|---|---|
| `L3.delivery.csat` | missing, overlay exists but `Unknown` | Poor | Public aggregate ratings, complaint counts, verified surveys, IR/customer satisfaction disclosures | `llm_web` over allowlisted evidence | monthly for app/consumer; quarterly otherwise | Overlay payload, not hot table, unless source gives numeric time series |
| `L4.eff.conversion_retention` | missing, overlay `Unknown` | Poor | First-party app analytics, paid mobile panel, disclosed retention/repurchase KPI, subscription cohort reports | paid preferred; `llm_web` only for disclosed issuer-specific KPI | monthly or quarterly | Paid hard rows when licensed; otherwise overlay |
| `L4.volume.foot_traffic` | missing, overlay often `Unknown`/`N/A` | Poor | Retail footfall panels, store traffic press releases, shopping-mall/operator panels | paid preferred; public releases only as low-frequency proxy | weekly/monthly if paid; quarterly if public | Paid hard rows for issuer/store-region; overlay for low-frequency public proxy |
| `L4.volume.frequency` | missing, overlay `Unknown` | Poor | First-party app usage, Sensor Tower/data.ai/QuestMobile-style panels, public app ranking as weak proxy | paid preferred; public rank is `Proxy`, not `Known` | monthly | Paid hard rows or overlay with `Proxy` |
| `L7.trade.iv` | spec `$`; A-share gap in current audit | Poor for per-stock | Futu HK/US options, domestic ETF/index options feed, licensed options IV feed | hard data where listed option exists; else `N/A`/`Unavailable` | daily EOD, intraday only with entitlement | `realtime_current` for listed option universe; no per-stock fabrication |
| `L7.trade.options_cp` | spec `$`; A-share gap in current audit | Poor for per-stock | Licensed option chain volume/OI; Futu for HK/US; domestic ETF/index options | hard data where listed option exists; else `N/A`/`Unavailable` | daily EOD | `realtime_current` or sentinel ETF/index rows |
| `L7.trade.gamma` | spec `$`; only partial feasibility | Not suitable | Licensed option chain with Greeks/OI, or derive from IV surface plus contract specs | paid/derive only | daily EOD or intraday with entitlement | Derived hard row with evidence refs to option chain raw artifacts |
| `L0.sentiment.social` | source_status says missing but real Tushare `dc_hot+ths_hot` rows exist | Good | Tushare hot lists, optionally AKShare hot rankings | hard source; no web LLM needed | intraday or daily EOD | `INDUSTRY:<id>` sentinel rows in `realtime_current` |
| `L7.mood.media_social` | partial | Medium | AKShare EM hot rank and keyword data, Tushare hot lists | hard source first, LLM only summarization | daily/intraday bounded | `realtime_current` per stock |
| `L7.mood.theme` | currently mock-only in audit | Medium | AKShare `stock_hot_keyword_em`, Tushare theme/concept hot data | replace mock with real public fetch; no LLM-first fill | daily/intraday bounded | `realtime_current` per stock, cache raw snapshot |
| `L9.media.social_buzz` | currently mock-only in audit | Weak to medium | AKShare Xueqiu hot snapshots, Tushare hot lists, licensed social sentiment | replace mock with real public fetch; paid source if production SLA needed | daily bounded | `realtime_current`; use `Inactive` when not in top list |

## Evidence Contract

All public web or paid evidence must fit in existing storage without schema migration. The current hot table only has `value_json`, `source`, and `updated_at`; therefore evidence belongs inside `value_json` for hard rows or inside overlay node payloads for web/LLM rows.

Minimum evidence shape:

```json
{
  "value": 0.73,
  "unit": "ratio",
  "metric_window": "2026-Q1",
  "method": "issuer_disclosed_or_vendor_panel",
  "data_status": "Known",
  "evidence_quality": "medium",
  "confidence": 0.68,
  "evidence_sources": [
    {
      "kind": "external_url",
      "provider": "provider_or_site_name",
      "issuer": "issuer_or_vendor_name",
      "source_url": "https://example.com/source",
      "canonical_url": "https://example.com/source",
      "title": "source title",
      "published_at": "2026-04-30",
      "fetched_at": "2026-05-26T10:30:00Z",
      "checksum_sha256": "sha256-of-fetched-normalized-content",
      "content_type": "text/html",
      "access_tier": "public",
      "license_note": "public summary only",
      "raw_artifact_ref": "raw/web/provider/dt=20260526/artifact.jsonl",
      "parser_version": "web_paid_gap_v1"
    }
  ]
}
```

Additional fields for paid feeds:

- `vendor_contract_id` or redacted entitlement id
- `entitlement_scope`, for example `CN_ETF_OPTIONS_EOD` or `MOBILE_APP_PANEL_MONTHLY`
- `quote_delay` for market data
- `terms_hash` for the relevant data-use terms
- `record_id` or vendor row id
- `redistribution_allowed: false` by default

Additional fields for LLM outputs:

- `model`, `prompt_fingerprint`, `input_evidence_refs`, and `output_checksum_sha256`
- no `source_url` generated by the model unless it already came from the fetch layer
- if any web evidence lacks checksum or fetched content, cap `confidence` at `0.5` and keep `evidence_quality=low`

## Source Rules by Field Class

### Customer Satisfaction and CSAT

Fields: `L3.delivery.csat`.

Allowed public evidence:

- App Store, Google Play, Trustpilot, black-cat style complaint portals, and issuer customer satisfaction disclosures, but only aggregate rating/count/complaint trend fields.
- Annual reports or ESG/customer service disclosures when they provide issuer-owned survey metrics.

Not allowed for `Known`:

- A handful of scraped comments.
- LLM memory.
- Generic brand reputation articles without issuer-specific numeric or strongly attributable evidence.

Acceptable payload:

- `nps_or_csat`, `rating_avg`, `rating_count`, `complaint_count`, `complaint_rate_proxy`, `trend`, `sample_window`, `coverage_scope`.
- `Known` only when sample size and issuer mapping are clear. Otherwise `Proxy` or `Unknown`.

### Conversion, Retention, Repurchase, and Frequency

Fields: `L4.eff.conversion_retention`, `L4.volume.frequency`.

Allowed production evidence:

- First-party analytics exported by the issuer, if available.
- Paid mobile/app intelligence panels.
- Explicit issuer disclosures such as retention rate, monthly active users, orders per active user, repurchase rate, subscription renewal rate.

Allowed public proxy:

- Public app ranking, search index, or active-device rank may support `Proxy`, not `Known`.

Not allowed:

- Inferring retention from revenue growth alone.
- Crawling user clickstream, private app telemetry, or cookie/device identifiers.

### Foot Traffic

Fields: `L4.volume.foot_traffic`.

Production-grade evidence requires a retail/location panel or issuer/operator disclosed traffic counts. Public news releases can support a quarterly proxy if they are issuer/store specific. Do not scrape map POI popularity, mobile location traces, or mall Wi-Fi/Bluetooth data without explicit entitlement.

Recommended status policy:

- Non-store business models: `N/A` with `missing_policy=not_applicable_remove`.
- Store businesses without panel or disclosure: `Unknown`, not low-confidence `Known`.
- Public industry-level traffic release only: `Proxy`, unless directly issuer-specific.

### Options IV, Call/Put, and Gamma

Fields: `L7.trade.iv`, `L7.trade.options_cp`, `L7.trade.gamma`.

For A-share issuers, these fields require special handling because domestic listed options are ETF/index oriented. The safe mapping is:

- per-stock A-share with no listed option: `N/A` or `Unavailable`
- ETF/index option sentinel, for example an ETF/index row: hard data if licensed or public EOD is sufficient
- cross-listed HK/US ticker with listed options: Futu/OpenD or other licensed feed can populate per listed ticker
- A-share basket exposure proxy from ETF/index options: `Proxy`, never `Known`, and must include mapping method and basket weights

Gamma requires Greeks, open interest, contract multiplier, strike, underlying price, and expiry. It should be derived only from raw option-chain artifacts with contract-level checksums. If a vendor supplies gamma directly, still store the raw row id and vendor entitlement.

### Social, Theme, and Buzz

Fields: `L0.sentiment.social`, `L7.mood.media_social`, `L7.mood.theme`, `L9.media.social_buzz`.

Recommended path:

1. Keep `L0.sentiment.social` on Tushare `dc_hot+ths_hot` industry sentinel rows.
2. Replace mock `L7.mood.theme` and `L9.media.social_buzz` rows with real AKShare/Tushare bounded snapshots.
3. Use source status `Inactive` when a stock is absent from a top list; absence from top-N is a valid event state, not a missing-data error.
4. Let LLM summarize theme strings only after hard source rows exist.

Do not bulk crawl social timelines, comment streams, forum posts, or user profiles for this phase.

## Landing Pattern

Use the current storage split:

- Hard and frequently refreshed data goes to `realtime_current`.
- Web/LLM company or industry judgment goes to overlay payloads.
- Raw fetched artifacts should be cached outside the hot table, then referenced from `value_json.evidence_sources[].raw_artifact_ref`.
- Existing `verify_overlay_closed_loop.py` semantics should remain: closed-loop tiers cannot include `http(s)://`; `web_analysis` tiers must include URL, checksum, and fetched timestamp.

Recommended source naming:

- `web:app_store_rating`
- `web:blackcat_complaint`
- `web:issuer_ir`
- `web:research_release`
- `akshare:stock_hot_rank_em+keyword`
- `akshare:xq_hot`
- `tushare:dc_hot+ths_hot`
- `paid:sensortower_app_panel`
- `paid:questmobile_app_panel`
- `paid:retail_traffic_panel`
- `paid:futu_option_chain`
- `paid:wind_options_greeks`
- `derive:option_gamma_exposure`

## Execution Sequence

### Phase 0: Policy and allowlist

- Add a provider allowlist for web-enabled D fields.
- Require fetch cache, checksum, parser version, and fetched timestamp before LLM sees any web text.
- Add a review queue for `confidence < 0.6` or `evidence_quality=low`.

### Phase 1: Remove mock from social/theme

- Keep `L0.sentiment.social` on real Tushare hot-list rows.
- Turn on real AKShare snapshots for `L7.mood.theme` and `L9.media.social_buzz` with bounded universe, rate limit, and cache.
- Treat endpoint failure as no rows or `Inactive`, not synthetic Known.

### Phase 2: Two public-web pilots

- Pilot `L3.delivery.csat` on app/consumer/service issuers with aggregate ratings and complaint counts.
- Pilot one research-release field, preferably `L2.newbiz.tam` or `L3.product.lifecycle`, because public industry reports and issuer IR pages are easier to audit than behavioral data.
- Measure Known rate, checksum completeness, URL survival, and reviewer rejection rate for two months before expanding.

### Phase 3: Paid data POC

- Options POC: choose one legitimate universe, either HK/US listed options via Futu/OpenD or domestic ETF/index options via licensed vendor. Populate `L7.trade.iv` and `L7.trade.options_cp`; derive `L7.trade.gamma` only after contract-level Greeks/OI are stable.
- App panel POC: one vendor for `L4.volume.frequency` and `L4.eff.conversion_retention`.
- Retail traffic POC: one vendor or public panel for `L4.volume.foot_traffic` on domestic consumption/retail names.

### Phase 4: Promote labels only after real evidence

- Promote a field from `missing`/`$` only after the non-mock real snapshot proves coverage.
- Keep per-stock A-share options fields as `N/A`/`Unavailable` unless the source truly provides issuer-level listed options or a documented proxy.
- Keep all paid-source payloads redacted and redistributable-safe.

## Explicit Do-Not-Crawl List

- Paywalled broker reports or copyrighted PDFs unless the workspace has a license and stores only metadata/excerpts allowed by terms.
- Full UGC/social comments, timelines, profiles, or private messages.
- App telemetry, clickstream, device identifiers, location traces, or map popularity data without entitlement.
- Minute-level option-chain scraping from broker UI or unofficial pages.
- Any source that cannot provide `source_url` or vendor row id, `fetched_at`, and checksum.

## Acceptance Checklist

Before a new web/paid field counts as real A-share completion:

- `source` is not `mock:*`.
- `data_status` is one of `Known`, `Proxy`, `Inactive`, `N/A`, or `Unavailable` with a defensible reason.
- Every web evidence item has `source_url`, `fetched_at`, and `checksum_sha256`.
- Every paid evidence item has issuer/vendor id, entitlement scope, fetched timestamp, and raw artifact reference.
- LLM outputs cite only fetch-layer evidence refs; no model-invented URLs.
- Refresh frequency matches the source reality, not the dashboard's desired cadence.
- If the source is an ETF/index option proxy for an A-share stock, the row is `Proxy`, not `Known`.
