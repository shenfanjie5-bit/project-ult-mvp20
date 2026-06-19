# A-share formula-policy review packets

- Generated: `2026-06-19T16:39:02+08:00`
- Formula-policy packets: `6`
- Current input available: `6`
- Valuation peer-context packets: `3`
- Business-semantics packets: `3`
- Replacement path ready: `3`
- Direct formula ready: `0`
- Known draft sufficient: `0`
- Policy contracts valid: `6`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Policy Families

| policy_family | count |
|---|---:|
| `block_trade_directional_flow` | 1 |
| `capex_intensity_and_trend` | 1 |
| `segment_concentration_and_strategy` | 1 |
| `valuation_peer_context` | 3 |

## Review Packets

| policy_family | dp_id | target | valid ts_codes | replacement ready | direct formula ready | required review |
|---|---|---|---:|---|---|---|
| `block_trade_directional_flow` | `L7.flow.block_trade` | `funding_score` | 115 | False | False | block-trade amount and count; block price versus close/VWAP; buyer/seller side or seat/shareholder identity; event freshness and free-float/notional normalizer |
| `capex_intensity_and_trend` | `L5.cf.capex` | `fundamental_score` | 1640 | False | False | capex scalar; reviewed denominator such as revenue, assets, or operating cash flow; historical capex trend; growth-stage / industry capex intensity baseline; policy for when capex is investment versus cash-flow drag |
| `segment_concentration_and_strategy` | `L2.segment.revenue_share` | `fundamental_score` | 1637 | False | False | segment revenue percentages; segment taxonomy or target-strategy labels; industry peer concentration baseline; policy for whether concentration is advantage, risk, or neutral |
| `valuation_peer_context` | `L6.mult.pb` | `valuation_rerating` | 1641 | True | False | stock valuation scalar; industry or peer-pool median/percentile; peer pool size and as-of trade_date; non-positive / loss-making handling policy; reviewed bounds and score direction |
| `valuation_peer_context` | `L6.mult.pe` | `valuation_rerating` | 1405 | True | False | stock valuation scalar; industry or peer-pool median/percentile; peer pool size and as-of trade_date; non-positive / loss-making handling policy; reviewed bounds and score direction |
| `valuation_peer_context` | `L6.state.industry_center` | `valuation_rerating` | 1641 | True | False | stock valuation scalar; industry or peer-pool median/percentile; peer pool size and as-of trade_date; non-positive / loss-making handling policy; reviewed bounds and score direction |

## Interpretation

- These packets are policy handoff artifacts, not scoring changes.
- `direct_formula_ready_count = 0` keeps raw PE/PB/capex/segment/block-trade payloads out of final score until policy review is complete.
- Valuation packets should prefer the already scoring `L6.state.peer_compare` route unless a reviewer approves a fallback.
