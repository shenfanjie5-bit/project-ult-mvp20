# A-share spec score trace audit

Generated: `2026-06-19T18:18:54.646993+00:00`

## Summary

| metric | count |
|---|---:|
| Spec dp_ids | 256 |
| Participating spec dp_ids | 174 |
| Score-relevant spec dp_ids | 174 |
| A-share universe ts_codes | 1641 |
| Runtime valid real dp_ids | 154 |
| Runtime valid real direct-stock dp_ids | 126 |
| Runtime valid real sentinel-origin dp_ids | 28 |
| Runtime numeric-signal dp_ids | 122 |
| Runtime numeric-signal direct-stock dp_ids | 96 |
| Runtime numeric-signal sentinel-origin dp_ids | 26 |
| Runtime bridge-emitted dp_ids | 107 |
| Overlay score-candidate dp_ids | 28 |
| Effective score-path dp_ids | 132 |
| Direct base-score candidate dp_ids | 105 |
| Participating gaps | 42 |
| All valid runtime but no numeric formula | 32 |
| Score-relevant valid runtime but no numeric formula | 18 |
| Non-scoring valid runtime without numeric formula | 14 |
| Numeric runtime blocked by non-scoring overlay | 0 |
| Mock-only dp_ids | 0 |

Definitions: runtime valid real = consumer-visible coverage after `read_hot_snapshot` sentinel merge: `Known/Proxy`, non-`mock:` source, non-empty value. Direct-stock counts have `_origin_ts_code == ts_code`; sentinel-origin counts come from merged `MARKET:` / `INDUSTRY:` rows. Runtime numeric-signal means `_realtime_signal(...)` returned a value. Runtime bridge-emitted means `synthesize_realtime_nodes(...)` actually created a scoring node. Effective score-path means either a bridge-emitted runtime node or a score-capable authored overlay node. Score-relevant excludes `none`, `audit_only`, `display_only`, `parent_score`, and `node_score` targets; the all-valid/no-numeric count is intentionally broader for data-quality triage.

## By Layer

| layer | total | participating | runtime valid | numeric | bridge | overlay | effective | gap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| L0 | 33 | 33 | 18 | 18 | 18 | 0 | 18 | 15 |
| L1 | 12 | 2 | 0 | 0 | 0 | 2 | 2 | 0 |
| L10 | 7 | 7 | 7 | 7 | 7 | 0 | 7 | 0 |
| L11 | 16 | 0 | 16 | 14 | 0 | 0 | 0 | 0 |
| L2 | 14 | 4 | 3 | 2 | 2 | 1 | 3 | 1 |
| L3 | 18 | 4 | 0 | 0 | 0 | 4 | 4 | 0 |
| L4 | 23 | 18 | 4 | 4 | 4 | 14 | 18 | 0 |
| L5 | 34 | 22 | 32 | 20 | 20 | 1 | 21 | 1 |
| L6 | 26 | 26 | 23 | 12 | 12 | 0 | 12 | 14 |
| L7 | 21 | 21 | 18 | 15 | 15 | 0 | 15 | 6 |
| L8 | 32 | 21 | 16 | 16 | 16 | 4 | 18 | 3 |
| L9 | 20 | 16 | 17 | 14 | 13 | 2 | 14 | 2 |

## Participating Gaps

`L0.compete.new_entrant`, `L0.compete.price_war`, `L0.compete.share_concentration`, `L0.cost.rent`, `L0.demand.frequency`, `L0.demand.penetration`, `L0.demand.replacement`, `L0.policy.access_license`, `L0.policy.regulation`, `L0.policy.subsidy`, `L0.policy.tax_trade`, `L0.price.product_asp`, `L0.tech.ai_automation`, `L0.tech.breakthrough`, `L0.tech.substitute_tech`, `L2.segment.revenue_share`, `L5.cf.capex`, `L6.mult.dcf`, `L6.mult.ev_ebitda`, `L6.mult.forward_pe`, `L6.mult.mcap_fcf`, `L6.mult.pb`, `L6.mult.pe`, `L6.mult.peg`, `L6.mult.ps`, `L6.path.tag`, `L6.priced.iv`, `L6.priced.realization_risk`, `L6.state.expansion_compression`, `L6.state.historical_percentile`, `L6.state.industry_center`, `L7.flow.block_trade`, `L7.mood.media_social`, `L7.reflex.tag`, `L7.trade.iv`, `L7.trade.margin_short`, `L7.trade.options_cp`, `L8.shock.black_swan`, `L8.shock.supply_break`, `L8.val.slope_risk_off`, `L9.company.mgmt_litigation`, `L9.media.social_buzz`

## All Valid Runtime But No Numeric Formula

`L11.mode`, `L11.trade.signal`, `L2.segment.revenue_share`, `L5.bs.ar_ap`, `L5.bs.cash_debt`, `L5.bs.inventory`, `L5.cf.buyback_dividend`, `L5.cf.capex`, `L5.cf.fcf`, `L5.cf.icf_fcf`, `L5.cf.ocf`, `L5.is.gross_profit`, `L5.is.net_profit`, `L5.is.revenue`, `L5.is.sga_rd`, `L6.mult.ev_ebitda`, `L6.mult.forward_pe`, `L6.mult.mcap_fcf`, `L6.mult.pb`, `L6.mult.pe`, `L6.mult.peg`, `L6.mult.ps`, `L6.path.tag`, `L6.state.expansion_compression`, `L6.state.historical_percentile`, `L6.state.industry_center`, `L7.flow.block_trade`, `L7.mood.media_social`, `L7.trade.margin_short`, `L9.company.mgmt_litigation`, `L9.macro.geo`, `L9.media.social_buzz`

## Score-Relevant Valid Runtime But No Numeric Formula

`L2.segment.revenue_share`, `L5.cf.capex`, `L6.mult.ev_ebitda`, `L6.mult.forward_pe`, `L6.mult.mcap_fcf`, `L6.mult.pb`, `L6.mult.pe`, `L6.mult.peg`, `L6.mult.ps`, `L6.path.tag`, `L6.state.expansion_compression`, `L6.state.historical_percentile`, `L6.state.industry_center`, `L7.flow.block_trade`, `L7.mood.media_social`, `L7.trade.margin_short`, `L9.company.mgmt_litigation`, `L9.media.social_buzz`

## Non-scoring Valid Runtime Without Numeric Formula

`L11.mode`, `L11.trade.signal`, `L5.bs.ar_ap`, `L5.bs.cash_debt`, `L5.bs.inventory`, `L5.cf.buyback_dividend`, `L5.cf.fcf`, `L5.cf.icf_fcf`, `L5.cf.ocf`, `L5.is.gross_profit`, `L5.is.net_profit`, `L5.is.revenue`, `L5.is.sga_rd`, `L9.macro.geo`

## Numeric Runtime Blocked By Non-scoring Overlay

- None

## Mock-only Runtime Fields

- None

## Sample Score Traces

### `300750.SZ`

- overlay: `/Users/fanjie/Desktop/Cowork/project-ult-mvp20/config/stock_overlays/STORAGE_GRID/300750.SZ.yaml`
- runtime snapshot dp_ids: 177
- aggregated nodes: 200
- scored dp_ids: 130
- synthetic realtime scored nodes: 84
- final base_score: 0.16915021136751843
- trading_signal: HOLD
- role_components: `{"capital_sentiment": -0.06864669711199663, "confidence_multiplier": 0.6628571428571428, "expectation_gap": -0.0009223585687351144, "funding_multiplier": 1.0576778545696826, "funding_score": -0.6949322145500433, "liquidity_multiplier": 0.9272598772454154, "market_regime_multiplier": 1.329971956273937, "multiplier_stack": 1.2186730930901435, "policy_sensitivity_multiplier": 0.9364588908767486, "priced_in_discount": 0.11989767069092253, "reflexivity_multiplier": 1.0, "risk_discount": 0.21432499612237085, "sentiment_score": 0.2928404892453325, "theme_multiplier": 0.9570040141243599, "valuation_pressure": 0.0, "valuation_rerating": 0.4293150778811663, "valuation_sensitivity_multiplier": 1.0103005}`
