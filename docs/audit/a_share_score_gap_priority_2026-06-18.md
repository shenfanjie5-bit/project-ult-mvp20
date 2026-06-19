# A-share score gap priority

Generated: `2026-06-19T11:45:29.195689+00:00`

## Summary

| metric | count |
|---|---:|
| Score-relevant formula gaps | 18 |
| Actionable formula gaps | 0 |
| Governance/intentional formula gaps | 18 |
| Participating gaps | 53 |
| Actionable participating gaps | 32 |
| Governance/intentional participating gaps | 21 |

### Formula Gap By Route

| route | count |
|---|---:|
| business_semantics_review | 3 |
| intentional_alias_duplicate | 1 |
| intentional_data_only | 3 |
| intentional_derived_bridge_review | 1 |
| intentional_fallback_duplicate | 1 |
| intentional_peer_context_suppressed | 6 |
| valuation_peer_context_review | 3 |

### Formula Gap By Priority

| priority | count |
|---|---:|
| P3_governance_or_design_review | 18 |

### Formula Gap By Bucket

| bucket | count |
|---|---:|
| design_review | 6 |
| intentional_governance | 12 |

## Score-Relevant Formula Gaps

| priority | bucket | subtype | route | dp_id | target | valid ts_codes | main sources | repair hint |
|---|---|---|---|---|---|---:|---|---|
| P3_governance_or_design_review | design_review | sign_or_business_semantics_required | business_semantics_review | `L5.cf.capex` | fundamental_score | 1640 | tushare:cashflow:1640 | capex needs a defined intensity/trend policy; high capex can be investment or drag |
| P3_governance_or_design_review | design_review | sign_or_business_semantics_required | business_semantics_review | `L2.segment.revenue_share` | fundamental_score | 1637 | tushare:fina_mainbz:1641 | segment revenue share needs a concentration/strategy policy before it has a score direction |
| P3_governance_or_design_review | design_review | sign_or_business_semantics_required | business_semantics_review | `L7.flow.block_trade` | funding_score | 115 | tushare:block_trade:115 | block-trade amount/count needs buyer/seller direction or discount/premium before funding_score has a sign |
| P3_governance_or_design_review | intentional_governance | duplicate_evidence | intentional_alias_duplicate | `L9.company.mgmt_litigation` | risk_discount | 389 | tushare:stk_managers:1641 | legacy duplicate of L8.gov.management_change in the current Tushare adapter; do not double-count the same stk_managers events into risk_discount |
| P3_governance_or_design_review | intentional_governance | data_only_no_safe_signal | intentional_data_only | `L6.mult.mcap_fcf` | valuation_rerating | 1548 | tushare:daily_basic+cashflow:1548 | negative FCF makes mcap/FCF sign-aware; no safe scalar formula yet |
| P3_governance_or_design_review | intentional_governance | data_only_no_safe_signal | intentional_data_only | `L7.trade.margin_short` | funding_score | 1514 | tushare:margin_detail:1514 | snapshot margin/short payload lacks clean directional signal |
| P3_governance_or_design_review | intentional_governance | data_only_no_safe_signal | intentional_data_only | `L6.mult.peg` | valuation_rerating | 909 | derive:l6_mult_peg:1535 | scored through L6.state.peg_match; direct raw PEG would double-count |
| P3_governance_or_design_review | intentional_governance | derived_replacement | intentional_derived_bridge_review | `L7.mood.media_social` | sentiment_score | 79 | tushare:ths_hot.热股:1641 | already consumed by L7.mood.fomo -> overheat_risk/risk_discount; a direct sentiment_score formula would reuse the same hot-list evidence |
| P3_governance_or_design_review | intentional_governance | duplicate_evidence | intentional_fallback_duplicate | `L9.media.social_buzz` | expectation_gap | 79 | tushare:ths_hot.热股:1641 | same Tushare ths_hot 热股 evidence as L7.mood.media_social in the current adapter; do not score as a separate expectation_gap field without a distinct source |
| P3_governance_or_design_review | intentional_governance | peer_context_suppressed | intentional_peer_context_suppressed | `L6.path.tag` | valuation_rerating | 1641 | derive:l6_path_tag:1641 | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| P3_governance_or_design_review | intentional_governance | peer_context_suppressed | intentional_peer_context_suppressed | `L6.state.historical_percentile` | valuation_rerating | 1641 | tushare:daily_basic.history:1641 | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| P3_governance_or_design_review | intentional_governance | peer_context_suppressed | intentional_peer_context_suppressed | `L6.mult.ps` | valuation_rerating | 1637 | tushare:daily_basic:1637 | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| P3_governance_or_design_review | intentional_governance | peer_context_suppressed | intentional_peer_context_suppressed | `L6.mult.ev_ebitda` | valuation_rerating | 1197 | derive:l6_mult_ev_ebitda:1535 | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| P3_governance_or_design_review | intentional_governance | peer_context_suppressed | intentional_peer_context_suppressed | `L6.mult.forward_pe` | valuation_rerating | 1050 | derive:l6_mult_forward_pe:1535 | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| P3_governance_or_design_review | intentional_governance | peer_context_suppressed | intentional_peer_context_suppressed | `L6.state.expansion_compression` | valuation_rerating | 31 | tushare:daily_basic.history_long:1641 | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| P3_governance_or_design_review | design_review | valuation_context_required | valuation_peer_context_review | `L6.mult.pb` | valuation_rerating | 1641 | tushare:daily_basic:1641 | PB needs peer/historical valuation context; direct absolute PB scoring would mix balance-sheet intensity across industries |
| P3_governance_or_design_review | design_review | valuation_context_required | valuation_peer_context_review | `L6.state.industry_center` | valuation_rerating | 1641 | tushare:daily_basic.industry_median:1641 | industry-center payload is a reference baseline; score the stock-vs-peer spread through peer_compare/percentile, not as a standalone direction |
| P3_governance_or_design_review | design_review | valuation_context_required | valuation_peer_context_review | `L6.mult.pe` | valuation_rerating | 1405 | tushare:daily_basic:1405 | trailing PE should be scored through peer/historical valuation context; a direct scalar formula would double-count or ignore industry regime |

## Participating Gap Route Counts

| route | count |
|---|---:|
| a_share_listed_options_or_na_required | 3 |
| business_semantics_review | 3 |
| intentional_alias_duplicate | 1 |
| intentional_data_only | 3 |
| intentional_derived_bridge_review | 1 |
| intentional_fallback_duplicate | 1 |
| intentional_peer_context_suppressed | 6 |
| llm_or_web_required | 28 |
| manual_review_required | 4 |
| valuation_peer_context_review | 3 |

| priority | count |
|---|---:|
| P2_llm_or_web_extraction | 28 |
| P3_governance_or_design_review | 21 |
| P3_manual_review | 4 |

| bucket | count |
|---|---:|
| blocking_actionable | 28 |
| design_review | 6 |
| intentional_governance | 12 |
| manual_triage | 4 |
| universe_not_applicable | 3 |

## Participating Gap Details

| priority | bucket | subtype | route | dp_id | target | valid ts_codes | main sources | repair hint |
|---|---|---|---|---|---|---:|---|---|
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.compete.new_entrant` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.compete.price_war` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.compete.share_concentration` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.cost.cac` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.cost.labor` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.cost.rent` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.demand.frequency` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.demand.penetration` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.demand.replacement` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.demand.terminal` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.demand.user_count` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.policy.access_license` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.policy.regulation` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.policy.subsidy` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.policy.tax_trade` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.price.contract_spot` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.price.discount` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.price.pricing_power` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.price.product_asp` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.supply.capacity` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.supply.chain_eff` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.supply.channel_service` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.supply.inventory` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.tech.ai_automation` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.tech.breakthrough` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L0.tech.substitute_tech` | fundamental_score | 0 |  | Add LLM/web extraction with source evidence, freshness, and confidence before scoring. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L8.shock.black_swan` | risk_discount | 0 |  | Convert event magnitude/freshness into bounded discount for risk_discount. |
| P2_llm_or_web_extraction | blocking_actionable | requires_llm_or_web | llm_or_web_required | `L8.shock.supply_break` | risk_discount | 0 |  | Convert event magnitude/freshness into bounded discount for risk_discount. |
| P3_governance_or_design_review | universe_not_applicable | listed_option_universe_required | a_share_listed_options_or_na_required | `L6.priced.iv` | volatility_risk | 0 |  | A-share single-stock option coverage is not broad enough to fabricate; only populate for a legitimate listed-option universe or mark N/A/Unavailable |
| P3_governance_or_design_review | universe_not_applicable | listed_option_universe_required | a_share_listed_options_or_na_required | `L7.trade.iv` | volatility_risk | 0 |  | A-share per-stock IV needs a licensed listed-option mapping; otherwise keep it out of scoring instead of proxying from unrelated instruments |
| P3_governance_or_design_review | universe_not_applicable | listed_option_universe_required | a_share_listed_options_or_na_required | `L7.trade.options_cp` | options_momentum_multiplier | 0 |  | A-share per-stock call/put ratios require real option-chain volume/OI; do not infer them from stock turnover or sentiment |
| P3_governance_or_design_review | design_review | sign_or_business_semantics_required | business_semantics_review | `L5.cf.capex` | fundamental_score | 1640 | tushare:cashflow:1640 | capex needs a defined intensity/trend policy; high capex can be investment or drag |
| P3_governance_or_design_review | design_review | sign_or_business_semantics_required | business_semantics_review | `L2.segment.revenue_share` | fundamental_score | 1637 | tushare:fina_mainbz:1641 | segment revenue share needs a concentration/strategy policy before it has a score direction |
| P3_governance_or_design_review | design_review | sign_or_business_semantics_required | business_semantics_review | `L7.flow.block_trade` | funding_score | 115 | tushare:block_trade:115 | block-trade amount/count needs buyer/seller direction or discount/premium before funding_score has a sign |
| P3_governance_or_design_review | intentional_governance | duplicate_evidence | intentional_alias_duplicate | `L9.company.mgmt_litigation` | risk_discount | 389 | tushare:stk_managers:1641 | legacy duplicate of L8.gov.management_change in the current Tushare adapter; do not double-count the same stk_managers events into risk_discount |
| P3_governance_or_design_review | intentional_governance | data_only_no_safe_signal | intentional_data_only | `L6.mult.mcap_fcf` | valuation_rerating | 1548 | tushare:daily_basic+cashflow:1548 | negative FCF makes mcap/FCF sign-aware; no safe scalar formula yet |
| P3_governance_or_design_review | intentional_governance | data_only_no_safe_signal | intentional_data_only | `L7.trade.margin_short` | funding_score | 1514 | tushare:margin_detail:1514 | snapshot margin/short payload lacks clean directional signal |
| P3_governance_or_design_review | intentional_governance | data_only_no_safe_signal | intentional_data_only | `L6.mult.peg` | valuation_rerating | 909 | derive:l6_mult_peg:1535 | scored through L6.state.peg_match; direct raw PEG would double-count |
| P3_governance_or_design_review | intentional_governance | derived_replacement | intentional_derived_bridge_review | `L7.mood.media_social` | sentiment_score | 79 | tushare:ths_hot.热股:1641 | already consumed by L7.mood.fomo -> overheat_risk/risk_discount; a direct sentiment_score formula would reuse the same hot-list evidence |
| P3_governance_or_design_review | intentional_governance | duplicate_evidence | intentional_fallback_duplicate | `L9.media.social_buzz` | expectation_gap | 79 | tushare:ths_hot.热股:1641 | same Tushare ths_hot 热股 evidence as L7.mood.media_social in the current adapter; do not score as a separate expectation_gap field without a distinct source |
| P3_governance_or_design_review | intentional_governance | peer_context_suppressed | intentional_peer_context_suppressed | `L6.path.tag` | valuation_rerating | 1641 | derive:l6_path_tag:1641 | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| P3_governance_or_design_review | intentional_governance | peer_context_suppressed | intentional_peer_context_suppressed | `L6.state.historical_percentile` | valuation_rerating | 1641 | tushare:daily_basic.history:1641 | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| P3_governance_or_design_review | intentional_governance | peer_context_suppressed | intentional_peer_context_suppressed | `L6.mult.ps` | valuation_rerating | 1637 | tushare:daily_basic:1637 | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| P3_governance_or_design_review | intentional_governance | peer_context_suppressed | intentional_peer_context_suppressed | `L6.mult.ev_ebitda` | valuation_rerating | 1197 | derive:l6_mult_ev_ebitda:1535 | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| P3_governance_or_design_review | intentional_governance | peer_context_suppressed | intentional_peer_context_suppressed | `L6.mult.forward_pe` | valuation_rerating | 1050 | derive:l6_mult_forward_pe:1535 | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| P3_governance_or_design_review | intentional_governance | peer_context_suppressed | intentional_peer_context_suppressed | `L6.state.expansion_compression` | valuation_rerating | 31 | tushare:daily_basic.history_long:1641 | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| P3_governance_or_design_review | design_review | valuation_context_required | valuation_peer_context_review | `L6.mult.pb` | valuation_rerating | 1641 | tushare:daily_basic:1641 | PB needs peer/historical valuation context; direct absolute PB scoring would mix balance-sheet intensity across industries |
| P3_governance_or_design_review | design_review | valuation_context_required | valuation_peer_context_review | `L6.state.industry_center` | valuation_rerating | 1641 | tushare:daily_basic.industry_median:1641 | industry-center payload is a reference baseline; score the stock-vs-peer spread through peer_compare/percentile, not as a standalone direction |
| P3_governance_or_design_review | design_review | valuation_context_required | valuation_peer_context_review | `L6.mult.pe` | valuation_rerating | 1405 | tushare:daily_basic:1405 | trailing PE should be scored through peer/historical valuation context; a direct scalar formula would double-count or ignore industry regime |
| P3_manual_review | manual_triage | manual_triage | manual_review_required | `L6.mult.dcf` | valuation_rerating | 0 |  | Manual governance and formula review required. |
| P3_manual_review | manual_triage | manual_triage | manual_review_required | `L6.priced.realization_risk` | priced_in_discount | 0 |  | Convert event magnitude/freshness into bounded discount for priced_in_discount. |
| P3_manual_review | manual_triage | manual_triage | manual_review_required | `L7.reflex.tag` | reflexivity_multiplier | 0 |  | Add multiplier formula around neutral 1.0 and route into reflexivity_multiplier. |
| P3_manual_review | manual_triage | manual_triage | manual_review_required | `L8.val.slope_risk_off` | risk_discount | 0 |  | Convert event magnitude/freshness into bounded discount for risk_discount. |
