# project-ult-mvp20

Public orchestration shell for the Project ULT 13-industry MVP.

This repository owns the MVP manifest, module lock, runbooks, fixture evidence,
runtime BFF, frontend shell, and CI checks. It vendors a bounded snapshot of
selected upstream `project-ult-*` source directories under `upstream/` for
skeleton wiring, but the lock file still records the broader upstream module
set as pinned SHAs.

## Repository Map

- `mvp20/` — Python package for manifest validation, provider validation,
  overlay generation/compilation, scoring/coverage helpers, data-source
  adapters, and the read-only stdlib HTTP BFF (`mvp20 serve`).
- `config/` — auditable source of truth for the 13-industry universe,
  provider catalog, market adapters, field governance, industry graphs,
  industry overlays, and company-industry stock overlays.
- `runtime/` — local runtime artifacts: `hot.sqlite` for compiled graph
  snapshots / current realtime values and `history/` for optional Parquet
  minute replay. Treat this as local state, not canonical source.
- `scripts/` — collector, SQLite initialization, compaction, prompt
  generation, overlay verification, and audit utilities.
- `docs/` — operator runbooks, data-source audits, industry-graph docs,
  and generated audit reports.
- `FrontEnd/` — Vite + React + TypeScript + Tauri frontend. In
  `projectUlt` mode it targets the mvp20 BFF at `http://127.0.0.1:8701`
  or a compatible `/api` backend.
- `upstream/` — vendored source snapshots for `contracts`,
  `audit-eval`, `data-platform`, `entity-registry`, `graph-engine`,
  `main-core`, and `reasoner-runtime`. The full 14-module pin set is in
  `locks/modules.lock.yaml`.

## MVP Boundary

- The decision universe is organised by 13 industries declared in
  `config/mvp20.industries.yaml`. Each `graph_status: present` industry
  must have at least one constituent in `config/mvp20.universe.yaml`;
  pending industries are allowed to have no constituent yet.
- Constituents may belong to up to 3 industries (primary, secondary, and
  tertiary — e.g. 胜宏科技-H tagged AI_COMPUTE / SEMI_EQUIPMENT /
  CONSUMER_ELECTRONICS).
- A-share, Hong Kong, and US-listed constituents are accepted (via the
  validated `ts_code` formats `<NNNNNN>.SH|SZ|BJ`, `<NNNN[N]>.HK`, and
  `<SYMBOL>.US` — Berkshire-style multi-dot codes such as `BRK.B.US`
  also accepted). A and H listings of the same company stay as separate
  constituents (e.g. 紫金 601899.SH / 02899.HK).
- The MVP intentionally does not enforce a fixed total constituent count.
- `history_window_months=120`.
- `graph_depth=2`.
- Each industry with `graph_status: present` ships a structured causal
  graph at `config/industry_graphs/<slug>.yaml` (v3.1 template + v3.1.1
  valuation weights). Pending industries are reserved slots — the graph
  YAML is added later.
- The causal graph carries: industry priors (state probabilities, β
  values, valuation weights, tail risk, validation signals), shared
  nodes/edges with polarity and lag, and four render views
  (causal_propagation, core_factor, supply_chain, risk).
- All companies — Chinese industry leaders, Hong Kong dual listings, US
  ADRs, and upstream customers (e.g. Meta as an AI Capex driver) — live
  in `config/mvp20.universe.yaml`. Each constituent carries a `role`
  field (`target` / `customer` / `both`) so consumers can distinguish
  decision targets from upstream context entities.
- Each constituent also carries a `pool` field (`regular` / `core`).
  `regular` is the full ~300-stock leader pool that drives baseline
  scoring; `core` is the hand-curated subset that goes through deep-dive
  LLM analysis. Membership is human-curated (the schema does not promote
  automatically); `validate-manifest` reports a `pool_counts` summary so
  operators can see the split.
- External market-data providers are catalogued in
  `config/data_providers.yaml` and certified by `mvp20 validate-providers`.
  Active providers: Financial Modeling Prep (FMP, US primary —
  price / fundamentals / news / insider / SEC / analyst / DCF / macro / forex), Tushare
  (A-share primary), AKShare (A/HK free fallback), yfinance (US/HK free
  fallback), and Futu OpenAPI via the OpenD local gateway (HK / US
  deep data plus active options chain / IV; FMP options remain
  Premium-tier fallback).
  FRED stays planned for the macro epic. Secrets stay in env vars
  referenced by `secret_env_var`; the catalog rejects any inline
  `api_key` / `secret` / `token` fields. `mvp20 plan-backfill`
  automatically picks up the catalog when it sits next to the manifest
  and reports per-market provider coverage.
- Futu OpenD is treated as a special `auth_type: local_gateway`
  provider: the catalog declares only `gateway.host` / `gateway.port`
  (default `127.0.0.1:11111`) and the env var name
  (`FUTU_OPEND_PASSWORD`) for the encryption key the SDK uses to talk
  to the locally-running daemon. The catalog deliberately has no
  `base_url` for local_gateway providers because there is no remote
  HTTP endpoint — operators install OpenD from
  `https://www.futunn.com/download/OpenAPI`, log in once with a Futu
  account holding the relevant market-data subscriptions, and export
  `FUTU_OPEND_PASSWORD` locally.
- Walk-through fixtures under `config/industry_graphs/fixtures/` provide
  golden double-path examples (e.g. Meta Capex → NVDA) for downstream
  graph-engine simulators.
- Associated listed companies are graph and risk-summary context only.
- Buy/sell/recommendation decisions are emitted only for declared
  constituents.
- Provider gaps are recorded explicitly; missing data is not fabricated.

## Data Provider Capability Coverage

The provider vocabulary contains **51 capability slugs** when active,
tier-locked, and planned entries are counted together. The current active
5-provider catalog declares **47 active capability slugs**; FRED is still
planned. Per-provider endpoint inventories live under
[`docs/data_sources/`](docs/data_sources/) — these CSVs are the audit trail
proving every market and every important capability is covered.

### Spec data-point coverage

The provider capability table below is a source-capability inventory. It is
not the same thing as coverage of the **250 spec data points** in
[`docs/data_sources/coverage_audit.md`](docs/data_sources/coverage_audit.md).
Use the following audited dp_id coverage ladder when describing product
coverage:

| Coverage class | Count | Meaning |
|---|---:|---|
| Hard-data direct | ~100 / 250 | Fully available from the wired 4-source stack (Tushare / FMP / Futu / AKShare); objective and refreshable. |
| Hard-data proxy / partial | ~115 / 250 | Available through source proxies, partial disclosure, or multi-source aggregation; confidence should remain explicit. |
| Algorithmic derivation | ~15 / 250 | Produced by graph-engine / derive / scoring formulas from upstream hard data. |
| LLM / human / filing extraction | ~32 / 250 | Company profile, industry trend, and qualitative disclosure fields that require Codex/analyst extraction or explicit N/A / Unknown status. |
| Permanently unhandled | 0 | No spec field is impossible to handle, but not every field is a structured hard-data feed. |

Current local runtime snapshot
(`runtime/hot.sqlite:realtime_current`) has **31 612 rows**,
**181 distinct dp_id**, **328 stock tickers**, and **14 sentinel
market/industry entities**. **136 / 250 (54.4%)** of the
spec data points are now present in SQLite (intersection of distinct
dp_id with `config/data_point_roles.yaml`). **105 sentinel rows**
(`MARKET:CN` × 14, `MARKET:US` × 7, `INDUSTRY:<id>` × 5–8) cover
market-level and industry-level macro / policy / sector fields. The
current injection audit reports an average of **102.1 / 250 (40.8%)**
effective dp_ids per company and **96.0** realtime-injected dp_ids
(the per-stock count includes sentinel rows merged via
`read_hot_snapshot`'s `MARKET:<market>` and `INDUSTRY:<id>` fallback).
**123 distinct `source` labels** are written by adapters (Tushare /
FMP / Futu / AKShare / derive). Recheck with:

```bash
sqlite3 runtime/hot.sqlite \
  'select count(*), count(distinct dp_id), count(distinct ts_code), count(distinct source) from realtime_current;'
```

Coverage audit baseline:

- `104` means at least one of the 5 audited sources has full coverage. It is
  a coverage-capability number, not the number currently injected into
  `runtime/hot.sqlite`.
- `218` means full or partial coverage before adding the newer derivable-field
  product wording.
- `32` means no structured source covers the field directly; these fields use
  LLM / human / filing extraction, or are explicitly marked N/A / Unknown.

Avoid over-claiming proxy fields:

- `L5.surprise.sell_side` is a sell-side consensus proxy, not buy-side whisper.
- `L6.state.historical_percentile` is an alias / same-source signal for
  `L10.val.historical_quantile`, not an independent valuation signal.
- `L9.company.earnings_guidance` is `Inactive` when the company has no forecast
  announcement; that is not a missing-data failure.
- L0 partial fields are usually indirect proxies, such as commodity prices for
  raw-material cost, not direct company cost observations.
- Institutional-flow and gamma-like fields are currently proxy-backed; do not
  market them as complete 13F holdings or full options gamma exposure.

### Per-provider coverage

| Provider | mvp20 capabilities | Real endpoints / methods | Coverage notes |
|---|---:|---:|---|
| **Tushare** | 29 | 107 / 145 in-account endpoint rows | 100% in-universe; 38 out-of-scope (HK/US/期货/转债/基金/ETF/期权/外汇/黄金现货 except ETF-flow proxy rows — handled by other providers or asset-class外) |
| **FMP** *(Starter $14/mo)* | 20 active / 6 tier-locked | 48 / 80 Starter-accessible endpoint rows | Starter currently declares `analyst_estimates`, `dcf_valuation`, `sec_filings`, `macro`, and `forex`; Premium unlocks `earnings_transcripts`, minute bars, options endpoints, and FMP-specific 13F/institutional endpoints; Ultimate adds `esg_score`/`government_trading`. See [FMP_TIER_REQUIREMENTS.md](docs/data_sources/FMP_TIER_REQUIREMENTS.md) |
| **Futu OpenD** | 20 | 34 covered data mappings / 40 non-trading SDK rows | Trading/account methods deliberately excluded (mvp20 is read-only); 5 operational rows skipped; `get_security_filter` is a future screener/universe-expansion hook |
| **AKShare** | 27 | many | Free fallback; covers most A-share microstructure as Tushare cross-check |
| **yfinance** | 7 | many | Free fallback for US/HK base data |
| FRED (planned) | — | — | Activated when macro epic lands |

### Capability vocabulary (51 total, 47 active)

Grouped by purpose:
- **Price / quote**: `price_daily`, `price_intraday`, `quote_l2`, `tick_trades`,
  `realtime_push`, `broker_queue_hk`
- **Fundamentals**: `fundamentals`, `dividends`, `buyback`, `dcf_valuation`,
  `corporate_actions`
- **Analyst / research**: `analyst_estimates`, `earnings_calendar`,
  `earnings_transcripts`, `peer_comparison`
- **Filings / governance**: `sec_filings`, `insider_trading`,
  `institutional_holdings`, `government_trading`, `esg_score`
- **Capital flow / liquidity**: `capital_flow`, `cross_border_flow`,
  `market_capital_flow`, `margin_trading`
- **Microstructure / sentiment**: `dragon_tiger_list`, `limit_up_down`,
  `block_trade`, `share_unlock`, `holder_count`, `chip_distribution`,
  `sentiment_hot_list`
- **Market structure**: `sector_constituents`, `market_index`,
  `index_futures`, `warrants`, `ipo_calendar`, `ah_premium`,
  `risk_warning`, `equity_pledge`, `technical_factors`
- **Macro / rates**: `macro`, `treasury_rates`, `forex`, `commodities`
- **Reference / context**: `company_profile`, `trading_calendar`,
  `options_chain`, `options_iv`, `news`, `alternative_data`,
  `investor_relations_qa`

### Single-source capabilities (no fallback)

| Capability | Sole provider | Why it matters |
|---|---|---|
| `quote_l2` / `tick_trades` / `broker_queue_hk` / `realtime_push` / `warrants` / `index_futures` | **Futu OpenD** | HK / cross-market microstructure |
| `sec_filings` / `insider_trading` | **FMP** | Active US monitoring fields |
| `earnings_transcripts` | **FMP** | Tier-locked on current Starter plan; no active fallback |
| `dcf_valuation` / `treasury_rates` / `corporate_actions` / `peer_comparison` / `forex` | **FMP** | Active US valuation / macro utilities |
| `esg_score` / `government_trading` | **FMP** | Tier-locked Ultimate alternative data |
| `commodities` | **FRED** | Planned macro/commodity context |
| `investor_relations_qa` | **Tushare** | 上证 e 互动 / 深证易互动 — LLM training corpus |
| `alternative_data` | **AKShare** | Misc Chinese-source aggregates |

### Verification

```bash
mvp20 validate-providers     # certifies catalog structure + market coverage
```

Plus the per-CSV files in `docs/data_sources/` — re-read them when adding a
provider or capability.

## Phase Z: LLM-field governance schema

mvp20 now treats every LLM-derived dp_id as a first-class governance
object. The schema lives in
[`config/llm_field_governance.yaml`](config/llm_field_governance.yaml)
and currently registers **111 dp_ids** (the full LLM-candidate set in
the overlay schema). Each entry declares:

- `route` — `llm_close` (closed-loop, no web fetch),
  `llm_web` (web-enabled tier; requires `url` + `checksum` +
  `fetched_at`), `derive` (handled by `mvp20/derive.py`), or `skip`.
- `model_tier` — `cheap_extract`, `cheap_classify`, `analysis`, or
  `web_analysis`; consumed by both `codex_prompt_gen --model-tier` and
  the verifier's evidence-kind whitelist.
- `refresh_trigger` — `quarterly`, `event_driven`, or `on_demand`;
  combined with `Z2 fingerprint` (`mvp20/fingerprint.py`) so the next
  codex run knows when a field is stale.
- `write_policy` — typically `preserve_known_unless_triggered`, so
  `merge_preserve_existing_overlay` (Z1a, in `mvp20/overlays.py`) keeps
  the codex-filled value unless the trigger fires.

The accompanying pieces:

- **Z1a** — `merge_preserve_existing_overlay()` in `mvp20/overlays.py`
  preserves codex-filled Known / N/A / Optionality / Inactive values
  across `mvp20 generate-overlays`. The default behavior is
  preserve-merge; passing `--force` re-baselines every overlay from
  `SLOT_DEFS` (destructive — overwrites filled values).
- **Z1b** — minimal governance YAML (58 dp_ids) bootstrapping the
  schema; later expanded.
- **Z1c** — verifier (`scripts/verify_overlay_closed_loop.py`) splits
  policy into closed-loop vs web-enabled tiers based on `model_tier`.
- **Z1d** — `scripts/codex_prompt_gen.py` filters by governance
  allowlist (`route ∈ {llm_close, llm_web}`) and accepts
  `--model-tier` to scope a run to one tier.
- **Z2** — `mvp20/fingerprint.py` snapshots `(dp_id, upstream
  dp_id values, trigger event)` so a second codex run is cheap and
  idempotent unless the fingerprint changes.
- **Z3** — governance expanded from 58 → **111 dp_id** (full LLM
  schema coverage).
- **Z5** — four targeted fixes: status-induced fields no longer leak
  into prompt body, web_analysis prompt now lists `allowed_evidence_kinds`,
  event fingerprint trigger normalized, and `EVENT_DRIVEN_DP_IDS` set is
  shared between `codex_prompt_gen` and `merge_preserve_existing_overlay`.

## Bucket A: 31 hard-data dp_id extension

Bucket A (data-driven hard fields outside Phase X's 4-source baseline)
added **31 dp_ids**. At the Bucket A baseline, SQLite ∩ spec moved
105 → 136 and avg_realtime per stock moved 66.7 → 77.5. The current
runtime snapshot has moved further; use the "Spec data-point coverage"
section above for current numbers.

- **Tushare A (14)** — financial-report derived: balance-sheet ratios
  (asset-turnover, debt-to-equity, current ratio), cash-flow quality
  (OCF/NI, FCF/Sales), profitability deltas (gross-margin YoY,
  operating-margin QoQ), and working-capital indicators (DSO, DIO,
  DPO, cash-conversion-cycle).
- **Tushare B (12)** — valuation / sell-side / industry sentiment:
  forward P/E percentile vs industry, EV/EBITDA cross-section,
  sell-side rating distribution from `report_rc`, peer-relative
  revenue / earnings growth rank, and L0 industry sentiment
  aggregates.
- **Futu (3)** — option-chain derived: `L6.priced.iv` (current
  IV percentile), `L7.trade.iv` (IV change vs 30-day baseline),
  `L7.trade.options_cp` (call/put open-interest ratio).
- **AKShare (2)** — `L8.cap.outflow_cut` (large-cap outflow stress
  flag) and `L9.capital.etf_block` (ETF block-trade signal).

A/B test (Codex high / Codex low / minimax-M2 over 16 runs) — full
report and routing recommendations in
[`docs/audit/ab_test_codex_vs_minimax_v1.md`](docs/audit/ab_test_codex_vs_minimax_v1.md)
and [`docs/audit/codex_high_vs_low_v1.md`](docs/audit/codex_high_vs_low_v1.md).
See also
[`docs/data_sources/field_strategy_v1.md`](docs/data_sources/field_strategy_v1.md).

### Engine routing decisions

Picked from the A/B reports (paired-cell coverage / agreement /
token-economics):

| Tier | Recommended engine | Why |
|---|---|---|
| `cheap_extract` | **codex low** (xhigh on ambiguous SMB / consumer names) | codex-low Known coverage matches xhigh within 1 (7 vs 6) at 58% token save and 67% time save; minimax wins on flat coverage (+5) but loses local_dp_id grounding on B2B names. |
| `cheap_classify` | **codex high** | minimax leaves most slots `Unknown` (Known = 1 vs codex's 11); codex-low also drops to Known=2. Audit trail (`local_dp_id` evidence on `Inactive` slots) is required. |
| `analysis` | **minimax-M2** for bulk, **codex high** for high-materiality slots | 89% avg agreement and ~10x cheaper tokens at minimax. Reserve codex for high-materiality + low-minimax-confidence cells. codex-low works but lower local_dp_id overlap. |
| `web_analysis` | **codex high with real web** (else fall back to minimax-closed-loop) | When outbound network is sandboxed, codex emits `external_url` from training memory without checksum (soft verifier violation). minimax's industry-inference-only output is safer offline. |

## Scoring, Field Governance, and Market Adapter

mvp20 keeps the core company graph formula market-agnostic, then applies a
lightweight market adapter for A-share, US, and Hong Kong listings.

### Field governance layer

The 250 spec data points are governed by `config/data_point_roles.yaml`.
Node/schema metadata fields are governed separately by
`config/schema_field_roles.yaml`.

Every spec `dp_id` has:

- `field_role` — one of `identity`, `structure`, `raw_input`,
  `derived_metric`, `score_component`, `multiplier`, `discount`, `gate`,
  `aggregation`, `confidence`, `missing_control`, `evidence`, `display`,
  `audit`.
- `score_target` and `derived_target` — route the field to fundamental score,
  expectation gap, valuation rerating, funding score, market/theme/regime
  and policy multipliers, priced-in discount, risk discount, confidence
  multiplier, etc.
- `missing_policy` / `fallback_policy` — decide how the field behaves when
  it is `N/A`, `Unknown`, `Unavailable`, `Proxy`, `Inactive`, or
  `Optionality`.
- `neutral_value` / `confidence_penalty` / `proxy_candidates` — define
  missing-data balance without fabricating hard data.

The implementation lives in `mvp20/field_governance.py`. It validates all
250 `dp_id`s against `docs/data_sources/coverage_audit.md`, enriches overlay
node payloads, and keeps governance metadata out of the SQLite table schema.
Compiled snapshots carry governance fields inside JSON payloads only.

Missing-balance rules used by `mvp20/aggregator.py`:

- `N/A` — remove from the formula and renormalize siblings; no confidence
  penalty.
- `Unknown` — stays in the denominator, contributes zero score, and lowers
  coverage/confidence.
- `Unavailable` — try `proxy_candidates`; otherwise use `neutral_value` and
  lower confidence.
- `Proxy` — participates in the formula, but with lower evidence/confidence
  and `proxy_used` audit metadata.
- `Inactive` — no numerator or denominator contribution.
- `Optionality` — current contribution stays in the normal score; future
  option value goes to the long-horizon bucket.

Important neutral-value convention: additive score and discount fields use
`0.0`; multiplier fields use `1.0`, which means "no amplification and no
compression".

### Market adapter layer

Market-local behavior is configured in `config/market_adapters.yaml` and
implemented in `mvp20/market_adapter.py`. The shared company graph still
computes the core score. The market adapter only wraps that result:

```text
Market Adjusted Score =
  Core Final Score
  × Market Adapter Multiplier
  + Local Event Score
  + Local Funding Score
  - Local Risk Discount
  - Local Overheat / Uncertainty Discounts
```

`Market Adapter Multiplier` is horizon-specific:

```text
Market Adapter Multiplier_h =
  exp(kappa_market,h × Σ factor_weight_market,h,i × factor_score_i × stock_local_beta_i)
```

where `h` is `short`, `mid`, or `long`. Factor scores are normalized to
`[-1, 1]` with `tanh(raw_signal / 2)` by default. Missing stock profile betas
default to `1.0`, so existing overlays remain neutral until a
`stock_local_profile` is supplied.

The adapter infers market by ticker suffix unless `market_code` is present:

- `.SH`, `.SZ`, `.BJ` → `CN_A`
- `.HK` → `HK`
- everything else → `US`

Adapter components:

- `microstructure`
- `participant`
- `liquidity`
- `theme`
- `policy`
- `derivatives_shorting`
- `crossborder_fx`
- `market_regime`

The current v2 maps existing routed `role_components` into those buckets and
uses separate kappa / weight tables for short-, mid-, and long-horizon scores:

- A-share emphasizes theme heat, retail/hot-money funding, market regime,
  policy sensitivity, and local risk.
- US emphasizes options/gamma/volatility, institutional/funding signals,
  market regime, expectation events, and litigation/short/volatility risk.
- Hong Kong emphasizes southbound/cross-border flow proxies, liquidity repair,
  market regime, policy expectation, short/derivatives pressure, and local
  governance/liquidity discounts.

`score_company()` now returns both:

- `core_final_score` — result before market adapter.
- `final_score` / `market_adjusted_final_score` — result after market adapter.

The top-level `short_total`, `medium_total`, `long_total`, `mode`, and
`trading_signal` use the market-adjusted score so existing API/CLI consumers
continue to read the final decision result without changing field names.

## Not Claimed

- Default/full propagation enabled.
- Broad production rollout complete.
- M4.7/financial-doc complete.
- Contracts subtype changes.
- New relation types.

## Local Checks

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

# Install vendored upstream modules (no-deps to skip heavy transitive deps;
# adapter routes return 503 only when the vendored package fails its
# adapter import availability check — see Runtime services below.
# Order matters: contracts first (others depend on it).
for d in contracts audit-eval data-platform entity-registry graph-engine main-core reasoner-runtime; do
  .venv/bin/pip install -e "./upstream/$d" --no-deps --ignore-requires-python
done

.venv/bin/mvp20 validate-manifest --manifest config/mvp20.universe.yaml
.venv/bin/mvp20 verify-lock --lock locks/modules.lock.yaml
.venv/bin/mvp20 plan-backfill --manifest config/mvp20.universe.yaml
.venv/bin/mvp20 validate-graphs
.venv/bin/mvp20 validate-providers
.venv/bin/mvp20 generate-overlays --period 2026-Q1
.venv/bin/mvp20 validate-overlays
.venv/bin/mvp20 compile-overlays --db runtime/hot.sqlite
.venv/bin/mvp20 run-fixture-e2e
.venv/bin/python -c "from mvp20.adapters import audit_eval, data_platform, entity_registry, graph_engine, main_core, reasoner_runtime; print('adapters OK')"
.venv/bin/python -m pytest
.venv/bin/python -m pytest -q tests/test_field_governance.py tests/test_missing_balance.py tests/test_market_adapter.py tests/test_scoring.py
git diff --check
```

## Frontend ↔ Backend Dev Wiring

The `FrontEnd/` directory holds a Vite + React + TypeScript app that
expects an HTTP backend serving `/api/project-ult/*`. mvp20 ships a
read-only stdlib HTTP server (`mvp20 serve`) that exposes its
manifest / industry / provider data so the frontend can render real
data without standing up the full upstream `project-ult-frontend-api`.

### Start the backend

```bash
.venv/bin/mvp20 serve --port 8701
# → mvp20 HTTP server listening on http://127.0.0.1:8701/api/*
```

### Data layer architecture (phase 1 + 2)

The server now sits on top of **four storage layers** wired together by
`handle_stock_overlay`:

1. **Static overlay source** — YAML under
   `config/stock_overlays/<industry_id>/<ts_code>.yaml` and
   `config/industry_overlays/<industry_id>.yaml` (31 graph nodes per
   industry, agent-generated, git-tracked, quarterly cadence).
   `SPACE_ECONOMY` has pending industry
   graph/overlay stubs but no stock overlays.
2. **Compiled graph snapshot** — SQLite WAL file `runtime/hot.sqlite` stores
   `overlay_manifest`, `company_node_instance`, `company_edge_instance`,
   `overlay_alert`, and `company_graph_snapshot`. The frontend reads
   `company_graph_snapshot.payload_json` so requests do not merge YAML live.
3. **Hot snapshot** — the same SQLite WAL file is written by
   `scripts/collector.py` every ~60s; same `(ts_code, dp_id)` UPSERTs in
   place, so the table is always the current minute-level snapshot. Reads
   are sub-millisecond.
4. **Minute history** — columnar archive files under
   `runtime/history/minute/` appended by the same collector, queried via
   DuckDB for 24h / 7d replays. A daily `scripts/compact_history.py` cron
   compacts yesterday's per-minute files into one
   `runtime/history/daily_compact/date=YYYY-MM-DD` archive.

### Where downloaded data and graph information lives

The storage split is deliberate: durable graph definitions stay in YAML,
current values stay in SQLite for low-latency reads, and historical minute
series stay in Parquet for replay and analysis.

| Data / information type | Storage location | Update mode | Purpose |
|---|---|---|---|
| Industry graph templates | `config/industry_graphs/<industry_id>.yaml` | authored / quarterly | Base causal graph and industry priors |
| Industry overlay nodes | `config/industry_overlays/<industry_id>.yaml` | agent / quarterly | 31 industry graph nodes; inherited by stock overlays |
| Stock overlay source | `config/stock_overlays/<industry_id>/<ts_code>.yaml` | agent / quarterly | Full company graph slots, missing policies, calculation types, edges, scores, views |
| Field governance config | `config/data_point_roles.yaml`, `config/schema_field_roles.yaml` | authored / reviewed | 250 dp_id roles, score targets, missing fallback, proxy candidates, neutral values |
| Market adapter config | `config/market_adapters.yaml` | authored / reviewed | CN_A / US / HK local multipliers, scores, and discounts applied outside the core graph |
| Compiled overlay manifest | `runtime/hot.sqlite:overlay_manifest` | `mvp20 compile-overlays` | Which company-industry overlays exist and which one is primary |
| Compiled nodes | `runtime/hot.sqlite:company_node_instance` | `mvp20 compile-overlays` | Queryable node instances with status, materiality, and calculation metadata |
| Compiled edges | `runtime/hot.sqlite:company_edge_instance` | `mvp20 compile-overlays` | Hierarchy and causal edge instances kept separate |
| Frontend graph snapshot | `runtime/hot.sqlite:company_graph_snapshot` | `mvp20 compile-overlays` | Main API read object; avoids live YAML merging per request |
| Overlay alerts | `runtime/hot.sqlite:overlay_alert` | `mvp20 compile-overlays` | `Unknown + required` / `Unknown + conditional_required` alert records |
| Current minute values | `runtime/hot.sqlite:realtime_current` | collector UPSERT every ~60s | Latest market / flow / event values by `(ts_code, dp_id)` |
| Freshness metadata | `runtime/hot.sqlite:freshness_meta` | collector / compiler | Last successful sync timestamps and layer status |
| Minute history | `runtime/history/minute/partition_minute=YYYYMMDD_HHMM` | collector append when `--enable-history` is set | Time-series replay and analysis |
| Daily compact history | `runtime/history/daily_compact/date=YYYY-MM-DD` | daily compact job | Lower-file-count historical archive for DuckDB scans |

Important behavior:

- `realtime_current` stores only the latest value for each `(ts_code, dp_id)`;
  it overwrites in place and does not keep history.
- Parquet history is append-only by collector cycle and is used by
  `/api/project-ult/history`, not by the main stock-overlay read path.
- `company_graph_snapshot.payload_json` is the frontend's primary graph
  object. It contains `compiled_graph`, `scores`, `coverage`, `alerts`, and
  the static overlay source used to build the snapshot.
- Runtime files under `runtime/` are local artifacts. YAML under `config/`
  is the auditable source that should be reviewed and versioned.

Start collector + server together::

```bash
# One-shot: create the SQLite schema
.venv/bin/python scripts/init_hot_db.py

# Generate/validate/compile graph overlays
.venv/bin/mvp20 generate-overlays --period 2026-Q1
.venv/bin/mvp20 validate-overlays
.venv/bin/mvp20 compile-overlays --db runtime/hot.sqlite

# Terminal 1 — minute-level collector (use --source mock for development)
.venv/bin/python scripts/collector.py --source mock --interval 60 --enable-history

# Terminal 2 — BFF server
.venv/bin/mvp20 serve --port 8701

# Optional: pull 24h history for one (ts_code, dp_id)
curl "http://127.0.0.1:8701/api/project-ult/history?ts_code=300750.SZ&dp_id=L7.flow.netbuy"
# Optional: open SSE stream
curl -N "http://127.0.0.1:8701/api/project-ult/stream/realtime?ts_code=300750.SZ&industry_id=STORAGE_GRID"
```

The server is **read-only**. The table below lists the core route examples;
`mvp20/server.py` is the source of truth for the full route regex list.

| Route | Returns |
|---|---|
| `/api/health` | service liveness |
| `/api/project-ult/health` | mvp20 module count + lock validity |
| `/api/project-ult/compat` | schema versions |
| `/api/project-ult/manifests/latest` | universe.yaml + industries.yaml |
| `/api/project-ult/modules` | modules.lock.yaml as JSON |
| `/api/project-ult/reasoner/providers` | data_providers.yaml + validation summary |
| `/api/project-ult/profiles` | universe constituents (filterable by `industry` / `pool` / `role` / `market` query strings) |
| `/api/project-ult/industry-graphs` | list of 12 strict-valid industry graphs (or `?industry_id=X` for one; `SPACE_ECONOMY` is a pending stub) |
| `/api/project-ult/cycles` | empty list (cycles are produced by upstream main-core) |
| `/api/project-ult/stock-overlay?ts_code=X` | compiled primary-industry overlay + realtime + scores + coverage + alerts |
| `/api/project-ult/stock-overlay?ts_code=X&industry_id=Y` | compiled overlay for a specific company-industry view |
| `/api/project-ult/stream/realtime?ts_code=X&industry_id=Y` | Server-Sent Events stream emitting `snapshot` / `delta` / `heartbeat` frames |
| `/api/project-ult/history?ts_code=X&dp_id=Y` | time-ordered minute history points (Parquet + DuckDB) |
| `/api/subsystems/status` | per-module unknown/locked status |
| `/api/project-ult/market-events` | latest cross-stock realtime event stream payload |
| `/api/project-ult/technicals?ts_code=X` | MA / MACD / RSI / KDJ / BOLL / VOL / ATR / OBV pack |
| `/api/project-ult/aggregate`, `/api/project-ult/coverage`, `/api/project-ult/score` | derived layer aggregate, coverage, and score envelopes |
| `/api/admin/*`, `/api/alerts/*` | local mvp20 BFF empty-state stubs |

Adapter-backed route families include
`/api/project-ult/graph/*`, `/api/project-ult/data/canonical/*`,
`/api/project-ult/data/raw/*`, `/api/project-ult/entities*`,
`/api/project-ult/reasoner/*` except `/reasoner/providers`,
`/api/project-ult/cycles/<id>`, `/api/stocks/*`, `/api/pool/*`,
`/api/world-state/*`, `/api/project-ult/audit/*`, `/api/audit/*`,
`/api/project-ult/backtests*`, and `/api/backtest/*`.

Six upstream `project-ult-*` modules (graph-engine, audit-eval, main-core,
data-platform, entity-registry, reasoner-runtime) plus `contracts` (their
shared base) are now **vendored under `upstream/`** as plain source
directories (their original `.git/` removed; mvp20 main git tracks the
sources). Routes formerly returning 503 are now **skeleton-wired** via
`mvp20/adapters/<module>.py` — handlers call the vendored package's
`__version__` then return a 200 envelope with `fixture: true` and
`wire_depth: skeleton`. If a vendor package fails to import at adapter
load time (for example because a top-level Python package is missing), the adapter
returns a 503 `UPSTREAM_UNAVAILABLE` envelope with the import error in
`details.import_error` — UI still shows a clean banner, no crash.

There are no deliberately 503-only placeholder routes in the normal mvp20
surface anymore. Adapter routes can still return `503 UPSTREAM_UNAVAILABLE`
when a vendored package cannot import because an optional runtime dependency
is missing. `frontend-api` is intentionally NOT vendored under `upstream/` —
`FrontEnd/` is the sole frontend in this repo and mvp20 `server.py` acts as
its BFF directly. Legacy `/api/admin/*` and `/api/alerts/*` paths are handled
by mvp20 with empty stub envelopes (`module: mvp20-bff, fixture: true`) so the
UI shows clean empty states instead of error banners.

### Runtime services (optional, for deeper-than-skeleton wire)

The vendored packages have heavy runtime deps that are deliberately **not**
installed by `pip install -e ".[dev]"`:

| Vendor | Service | Notes |
|---|---|---|
| `graph-engine` | Neo4j on the standard Bolt port locally | `docker run -p 7687:7687 neo4j:5` |
| `data-platform` | DuckDB / Iceberg catalog | `pip install duckdb dbt-duckdb pyarrow` |
| `reasoner-runtime` | LLM API keys + `pip install litellm instructor` | env: `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` |
| `entity-registry` | (none — pure in-memory lib) | already wired |
| `main-core` | (none for skeleton) | only needs pydantic, already installed |
| `audit-eval` | DuckDB + evidently | `pip install duckdb evidently` |

Without these backing services, skeleton adapters still return 200 fixture
data as long as their vendored package imports. If a missing Python package
prevents that top-level import, the adapter availability check returns
`503 UPSTREAM_UNAVAILABLE`; unexpected handler exceptions are surfaced by the
HTTP layer as `500 HANDLER_ERROR`.

### Start the frontend

```bash
cd FrontEnd
npm install              # first time only
npm run dev              # Vite dev server on http://127.0.0.1:1420
```

Wiring is done via `FrontEnd/.env.local` (gitignored):

```
VITE_DATA_MODE=projectUlt
VITE_PROJECT_ULT_PROXY_TARGET=http://127.0.0.1:8701
```

With `VITE_PROJECT_ULT_PROXY_TARGET` set, Vite proxies every `/api/*`
request from `:1420` to mvp20 backend at `:8701`. The browser stays
same-origin (no CORS preflight). To test without the proxy, swap
`VITE_PROJECT_ULT_PROXY_TARGET` for `VITE_PROJECT_ULT_API_BASE_URL=http://127.0.0.1:8701/api`
— mvp20 server already advertises CORS for `http://127.0.0.1:1420`.

### Switch back to demo mode

```
# FrontEnd/.env.local
VITE_DATA_MODE=demo
```

In demo mode the frontend uses MSW handlers (`src/mocks/`) — no backend
required. Useful for visual debugging when the manifest / catalog isn't
relevant.

### Quick smoke

```bash
# Terminal 1
.venv/bin/mvp20 serve

# Terminal 2
cd FrontEnd && npm run dev

# Terminal 3 — proxy through Vite
curl http://127.0.0.1:1420/api/health
curl http://127.0.0.1:1420/api/project-ult/manifests/latest
```

The checked-in manifest is the curated 13-industry leader pool (A-share,
Hong Kong, and US listings; ~328 constituents covering the 12 present
industries). `live_evidence_blocked: true` remains until per-provider
data wiring is calibrated; flipping the gate is an explicit operator
action, not part of constituent ingestion.
