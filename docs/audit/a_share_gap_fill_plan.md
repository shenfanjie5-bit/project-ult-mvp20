# A-share Gap Fill Plan

Generated on 2026-05-27. This is the integrated follow-up to
`a_share_spec_completion.md`, `a_share_llm_fill_plan.md`, and
`a_share_web_paid_gap_plan.md`.

## Baseline

Current A-share audit basis:

- Spec universe: 250 dp_ids.
- Effective runtime real-source coverage: 121 / 250.
- Compiled overlay coverage: 66 / 250.
- Combined real A-share coverage: 185 / 250, so 65 dp_ids remain.
- Mock-only effective runtime rows: 4 dp_ids. These are visible in runtime
  snapshots but do not count as real completion until the collector/derive path
  writes a non-`mock:*` source.

Remaining gap shape (65 total):

| bucket | count | main fix path |
|---|---:|---|
| Tushare / collector-first | 1 | Per-stock northbound via `hk_hold`/valid proxy. |
| Closed-loop company overlay | 13 | Use local SQLite facts only; no web evidence. |
| Closed-loop industry/L0 overlay | 25 | 24 `L0.*` gaps plus `L8.reg.tax_trade`; fill only with local evidence. |
| Web/paid/alt-data/N/A | 11 | Use allowlisted fetch cache or licensed feeds; otherwise `Unknown`/`N/A`. |
| Derived/model/sentinel work | 15 | Add formula/event/sentinel logic after upstream facts land. |

Completed in the latest refresh:

| fixed group | count | result |
|---|---:|---|
| Tushare core market/flow | 4 | `tushare-core` replaced mock PE/PB/turnover/active inflow rows. |
| Derive / market / crowding | 3 | `derive-snapshot` replaced mock trade signal; `tushare-market-env` landed market trend; `tushare-crowding` landed turnover-history crowdedness. |
| Tushare report forecast | 3 | `tushare-report-rc` landed `L5.fcst.*` rows. |

## Tushare First

### Completed core refresh

`scripts/collector.py --source tushare-core --max-cycles 1` completed and
upserted 576 rows. It replaced A-share mock rows for:

| dp_id | real source path | action |
|---|---|---|
| `L6.mult.pe` | `daily_basic` | Real A-share rows landed. |
| `L6.mult.pb` | `daily_basic` | Real A-share rows landed. |
| `L7.trade.volume_turnover` | `daily_basic.turnover_rate` / `volume_ratio` | Real A-share rows landed. |
| `L7.flow.active_inflow` | `moneyflow` | Real A-share rows landed. |

### Still pending Tushare/core source

| dp_id | real source path | current blocker |
|---|---|---|
| `L7.flow.passive_northbound` | `hk_hold` / `moneyflow_hsgt` | Per-stock mock rows still win in snapshot priority; current `hk_hold` run did not provide replacement per-stock rows. |

### New mapping in this pass

This pass added code/tests for these Tushare-backed fields and then landed the
focused collector rows:

| dp_id | source | caveat |
|---|---|---|
| `L5.fcst.revenue_margin` | `report_rc` | Landed via `tushare-report-rc`; broker report permission remains token-tier gated in other environments. |
| `L5.fcst.eps_cf` | `report_rc` | Landed via `tushare-report-rc`; cash-flow estimate remains null unless Tushare exposes it; EPS is real. |
| `L5.fcst.revisions` | `report_rc.derived` | Landed via `tushare-report-rc`; derived from recent-vs-older EPS consensus. |
| `L6.priced.crowdedness` | `daily_basic.history` | Landed via `tushare-crowding`. |
| `L7.env.market_trend` | `index_daily` to `MARKET:CN` | Landed via `tushare-market-env`. |

`L7.env.market_trend` has now landed through `tushare-market-env`,
`L6.priced.crowdedness` has landed through `tushare-crowding`, and
`L5.fcst.*` has landed through `tushare-report-rc`. The remaining Tushare-first
gap is per-stock `L7.flow.passive_northbound`.

Recommended refresh:

```bash
.venv/bin/python scripts/collector.py --source tushare-core --max-cycles 1
.venv/bin/python scripts/collector.py --source tushare-market-env --max-cycles 1
.venv/bin/python scripts/collector.py --source tushare-crowding --max-cycles 1
.venv/bin/python scripts/collector.py --source tushare-report-rc --max-cycles 1
.venv/bin/python -m mvp20.cli derive-snapshot --db runtime/hot.sqlite
.venv/bin/python scripts/check_a_share_spec_completion.py
```

Do not promote the report numbers until the generated JSON shows the relevant
dp_ids under `effective_real_handled_dp_ids`.

## Closed-loop LLM / Overlay

Ready company-level overlay fields, using only local Tushare facts such as
`L1.company.main_business`, `L9.disclosure.qa_recent`,
`L8.gov.management_table`, local financial rows, and local annual-report
excerpts:

| group | dp_ids |
|---|---|
| Channel / region | `L3.channel.mix`, `L3.channel.overseas`, `L3.region.domestic_overseas`, `L3.region.fx_geo`, `L3.region.key_risk`, `L3.region.tier_mix` |
| Cost / price / share / volume | `L4.cost.rent_energy_logistics`, `L4.eff.store_labor`, `L4.price.asp_aov_arpu`, `L4.price.subscription`, `L4.share.market`, `L4.volume.orders`, `L4.volume.users` |

L0 industry fields are fillable only after local peer/industry rollups are
available in the prompt. Do not let the model infer industry demand, pricing,
capacity, policy, or technology events from memory. Use `Unknown` or
`Inactive` when local evidence is absent.

Verification path:

```bash
.venv/bin/python scripts/codex_prompt_gen.py --industry AI_COMPUTE --ts-code 000063.SZ --model-tier analysis --list-only
.venv/bin/python scripts/verify_overlay_closed_loop.py --check-excerpt --check-schema --quiet
```

## Web / Paid Data

These fields should not be forced through Tushare or closed-loop LLM unless
direct local disclosure exists:

| field | source requirement |
|---|---|
| `L3.delivery.csat` | Public aggregate ratings, complaint counts, survey disclosures, or issuer service metrics with checksumed evidence. |
| `L4.eff.conversion_retention` | First-party disclosure or licensed app/customer panel. Revenue proxy is not enough. |
| `L4.volume.foot_traffic` | Licensed retail/location panel or issuer/operator traffic disclosure. |
| `L4.volume.frequency` | First-party usage disclosure or licensed app/consumer panel. |
| `L7.trade.iv`, `L7.trade.options_cp`, `L7.trade.gamma` | Licensed options chain/Greeks/OI or ETF/index sentinel proxy; A-share single-stock rows should be `N/A`/`Unavailable` without a legitimate option mapping. |

Social/theme mock rows should be replaced by bounded hard-source snapshots
before LLM summarization:

- `L7.mood.media_social`
- `L7.mood.theme`
- `L9.media.social_buzz`

## Remaining Derived Work

The remaining gaps need formula or event-source design rather than a simple
field mapping:

- `L5.surprise.preprice`: requires announcement/earnings date plus price-window
  reaction.
- `L6.mult.ev_ebitda`, `L6.mult.forward_pe`, `L6.mult.peg`,
  `L6.state.peg_match`: derive after forecast and balance-sheet facts land.
- `L6.priced.news_age`, `L6.priced.realization_risk`, `L7.reflex.tag`:
  require event/news age and realization state.
- `L7.env.fx`, `L9.macro.fx`, `L7.env.style`: add market/factor/FX sentinel
  rows before counting them as A-share real coverage.
- `L10.industry.inventory_orders`, `L10.industry.sales_price`: require
  industry validation rows or local rollups.
