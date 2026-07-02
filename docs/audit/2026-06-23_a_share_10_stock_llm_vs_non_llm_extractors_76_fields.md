# A-share 10-stock LLM vs non-LLM extractor comparison

- Generated: `2026-06-23T11:35:56+08:00`
- Baseline: `current stock overlay values; no fresh LLM call`
- Non-LLM: `local parser/formula/event-screen candidates only; read-only`
- Stocks: `10`
- Fields: `76` total; non-cheap-extract `76`
- Tier counts: `{'analysis': 50, 'web_analysis': 8, 'cheap_classify': 18}`

## Topline

- Baseline available cells: `652/760`
- Non-LLM candidate available cells: `466/760` (`0.6132`)
- Score-field non-LLM candidate available cells: `185/250` (`0.74`)
- Fields with at least one non-LLM candidate in this sample: `49`
- Fields not reproduced by this harness yet: `27`
- Of those, extractor/parser gaps: `4`
- Semantic or external-source gated fields: `23`

## Sample

| ts_code | name | industry |
|---|---|---|
| `600754.SH` | 锦江酒店 | `DOMESTIC_CONSUMPTION` |
| `300418.SZ` | 昆仑万维 | `HK_CN_INTERNET` |
| `300476.SZ` | 胜宏科技 | `CONSUMER_ELECTRONICS` |
| `000333.SZ` | 美的集团 | `EXPORT_MFG` |
| `300308.SZ` | 中际旭创 | `AI_COMPUTE` |
| `603256.SH` | 宏和科技 | `SEMI_EQUIPMENT` |
| `000657.SZ` | 中钨高新 | `NONFERROUS_METALS` |
| `600999.SH` | 招商证券 | `FINANCIAL_HIGH_DIVIDEND` |
| `300750.SZ` | 宁德时代 | `STORAGE_GRID` |
| `002008.SZ` | 大族激光 | `ROBOTICS` |

## Comparison Buckets

| bucket | cells |
|---|---:|
| `both_available` | 284 |
| `non_llm_missing_llm_available:gated` | 241 |
| `status_match_value_differs` | 96 |
| `non_llm_found_baseline_missing` | 84 |
| `non_llm_missing_llm_available` | 29 |
| `both_missing:gated` | 20 |
| `both_missing` | 4 |
| `status_and_value_close` | 2 |

## Candidate Categories

| category | cells |
|---|---:|
| `formula_proxy` | 219 |
| `keep_llm_for_now` | 150 |
| `event_policy` | 149 |
| `web_or_external` | 80 |
| `parser_formula_first` | 74 |
| `event_policy_gated` | 31 |
| `existing_deterministic_parser` | 21 |
| `strict_no_llm_now` | 20 |
| `unclassified` | 16 |

## Field Summary

| dp_id | tier | score | baseline avail | non-LLM avail | close | missing vs baseline | top methods |
|---|---|---:|---:|---:|---:|---:|---|
| `L1.position.brand` | `analysis` | `False` | 10 | 0 | 0 | 10 | semantic_review_required:10 |
| `L1.position.channel_edge` | `analysis` | `False` | 10 | 0 | 0 | 10 | semantic_review_required:10 |
| `L1.position.cost_edge` | `analysis` | `False` | 10 | 0 | 0 | 10 | semantic_review_required:10 |
| `L1.position.market_share` | `analysis` | `True` | 10 | 10 | 0 | 0 | peer_revenue_rank:10 |
| `L1.position.pricing_power` | `analysis` | `False` | 10 | 0 | 0 | 10 | semantic_review_required:10 |
| `L1.position.stickiness` | `analysis` | `False` | 10 | 0 | 0 | 10 | semantic_review_required:10 |
| `L1.position.tech_barrier` | `analysis` | `False` | 10 | 0 | 0 | 10 | semantic_review_required:10 |
| `L2.newbiz.commercialization` | `analysis` | `False` | 10 | 0 | 0 | 10 | semantic_review_required:10 |
| `L2.newbiz.revenue_contrib` | `analysis` | `False` | 10 | 0 | 0 | 10 | semantic_review_required:10 |
| `L2.newbiz.tam` | `web_analysis` | `False` | 10 | 0 | 0 | 10 | external_source_required:10 |
| `L2.newbiz.uncertainty` | `analysis` | `True` | 10 | 0 | 0 | 10 | semantic_review_required:10 |
| `L2.newbiz.valuation_contrib` | `analysis` | `False` | 10 | 0 | 0 | 10 | semantic_review_required:10 |
| `L2.segment.business_risk` | `analysis` | `False` | 10 | 0 | 0 | 10 | semantic_review_required:10 |
| `L2.segment.cash_contrib` | `analysis` | `False` | 10 | 10 | 0 | 0 | segment_revenue_share_runtime:10 |
| `L2.segment.compete_landscape` | `analysis` | `False` | 10 | 0 | 0 | 10 | semantic_review_required:10 |
| `L2.segment.industry_exposure` | `analysis` | `False` | 10 | 10 | 0 | 0 | segment_revenue_share_runtime:10 |
| `L2.segment.opex_ratio` | `analysis` | `False` | 10 | 10 | 0 | 0 | company_opex_ratio_runtime:10 |
| `L2.segment.profit_share` | `analysis` | `False` | 10 | 10 | 0 | 0 | segment_profit_share_runtime:10 |
| `L3.channel.cost` | `analysis` | `True` | 10 | 10 | 0 | 0 | sga_revenue_ratio:10 |
| `L3.channel.efficiency` | `analysis` | `True` | 10 | 10 | 0 | 0 | channel_efficiency_formula:10 |
| `L3.channel.overseas` | `analysis` | `False` | 7 | 9 | 0 | 1 | region_mix_runtime:10 |
| `L3.customer.concentration` | `analysis` | `False` | 9 | 3 | 1 | 6 | no_non_llm_extractor:7, script_fill:3 |
| `L3.customer.segment_mix` | `analysis` | `False` | 10 | 0 | 0 | 10 | no_non_llm_extractor:6, parser_todo_source_present:4 |
| `L3.customer.solvency` | `analysis` | `False` | 9 | 9 | 0 | 0 | ar_revenue_proxy:9, no_non_llm_extractor:1 |
| `L3.delivery.capacity_supply` | `analysis` | `False` | 8 | 7 | 0 | 3 | capex_ppe_proxy:10 |
| `L3.delivery.csat` | `web_analysis` | `False` | 5 | 0 | 0 | 5 | external_source_required:10 |
| `L3.delivery.fulfillment_cost` | `analysis` | `True` | 10 | 10 | 0 | 0 | fulfillment_cost_formula:10 |
| `L3.delivery.lead_time` | `web_analysis` | `False` | 5 | 0 | 0 | 5 | external_source_required:10 |
| `L3.product.lifecycle` | `web_analysis` | `False` | 10 | 0 | 0 | 10 | external_source_required:10 |
| `L3.product.margin_mix` | `analysis` | `False` | 10 | 10 | 0 | 0 | segment_gross_margin_runtime:10 |
| `L3.product.portfolio` | `analysis` | `False` | 10 | 9 | 0 | 1 | script_fill:9, no_non_llm_extractor:1 |
| `L3.region.domestic_overseas` | `analysis` | `False` | 8 | 9 | 1 | 1 | script_fill:9, no_non_llm_extractor:1 |
| `L3.region.fx_geo` | `analysis` | `False` | 10 | 9 | 0 | 1 | region_mix_runtime:10 |
| `L3.region.key_risk` | `analysis` | `False` | 7 | 0 | 0 | 7 | semantic_review_required:10 |
| `L3.region.tier_mix` | `analysis` | `False` | 8 | 9 | 0 | 1 | region_mix_runtime:10 |
| `L4.cost.cac_production` | `analysis` | `True` | 10 | 10 | 0 | 0 | sga_revenue_ratio:10 |
| `L4.cost.rent_energy_logistics` | `analysis` | `True` | 10 | 9 | 0 | 1 | gross_margin_proxy:10 |
| `L4.eff.capacity_utilization` | `analysis` | `True` | 6 | 7 | 0 | 2 | capex_ppe_proxy:10 |
| `L4.eff.conversion_retention` | `web_analysis` | `True` | 9 | 0 | 0 | 9 | external_source_required:10 |
| `L4.eff.store_labor` | `analysis` | `False` | 8 | 10 | 0 | 0 | sga_revenue_ratio:10 |
| `L4.price.asp_aov_arpu` | `analysis` | `True` | 7 | 10 | 0 | 0 | revenue_growth_proxy:10 |
| `L4.price.discount` | `analysis` | `True` | 9 | 9 | 0 | 1 | gross_margin_proxy:10 |
| `L4.price.elasticity` | `analysis` | `False` | 6 | 9 | 0 | 0 | gross_margin_proxy:10 |
| `L4.price.pricing_power` | `analysis` | `False` | 10 | 9 | 0 | 1 | gross_margin_proxy:10 |
| `L4.price.subscription` | `analysis` | `True` | 10 | 0 | 0 | 10 | semantic_review_required:10 |
| `L4.share.customer_channel` | `web_analysis` | `True` | 6 | 0 | 0 | 6 | external_source_required:10 |
| `L4.share.market` | `analysis` | `True` | 10 | 10 | 0 | 0 | peer_revenue_rank:10 |
| `L4.share.substitution` | `analysis` | `True` | 10 | 10 | 0 | 0 | revenue_growth_proxy:10 |
| `L4.volume.foot_traffic` | `web_analysis` | `True` | 10 | 0 | 0 | 10 | external_source_required:10 |
| `L4.volume.frequency` | `web_analysis` | `False` | 9 | 0 | 0 | 9 | external_source_required:10 |
| `L4.volume.orders` | `analysis` | `True` | 8 | 10 | 0 | 0 | revenue_growth_proxy:10 |
| `L4.volume.sales` | `analysis` | `True` | 8 | 10 | 0 | 0 | revenue_growth_proxy:10 |
| `L4.volume.shipments` | `analysis` | `True` | 7 | 10 | 0 | 0 | revenue_growth_proxy:10 |
| `L4.volume.users` | `analysis` | `False` | 7 | 10 | 0 | 0 | revenue_growth_proxy:10 |
| `L5.fcst.beat_probability` | `analysis` | `True` | 10 | 10 | 0 | 0 | forecast_revision_formula:10 |
| `L5.surprise.buy_whisper` | `analysis` | `False` | 9 | 0 | 0 | 9 | semantic_review_required:10 |
| `L8.gov.fraud_control` | `analysis` | `False` | 10 | 10 | 0 | 0 | event_keyword_screen:10 |
| `L8.gov.litigation` | `analysis` | `False` | 10 | 9 | 0 | 1 | event_keyword_screen:10 |
| `L8.industry.demand_supply` | `cheap_classify` | `True` | 7 | 10 | 0 | 0 | existing_runtime_or_derive:10 |
| `L8.industry.price_war` | `cheap_classify` | `False` | 5 | 10 | 0 | 0 | existing_runtime_or_derive:10 |
| `L8.industry.substitute` | `cheap_classify` | `False` | 5 | 10 | 0 | 0 | event_keyword_screen:10 |
| `L8.op.customer_channel` | `cheap_classify` | `False` | 6 | 10 | 0 | 0 | event_keyword_screen:10 |
| `L8.op.order_miss` | `cheap_classify` | `False` | 7 | 10 | 0 | 0 | event_keyword_screen:10 |
| `L8.op.product_fail` | `cheap_classify` | `False` | 3 | 10 | 0 | 0 | event_keyword_screen:10 |
| `L8.reg.license_risk` | `cheap_classify` | `False` | 3 | 10 | 0 | 0 | event_keyword_screen:10 |
| `L8.reg.subsidy_off` | `cheap_classify` | `False` | 3 | 10 | 0 | 0 | event_keyword_screen:10 |
| `L8.reg.tax_trade` | `cheap_classify` | `False` | 5 | 10 | 0 | 0 | event_keyword_screen:10 |
| `L8.reg.tighten` | `cheap_classify` | `False` | 3 | 10 | 0 | 0 | event_keyword_screen:10 |
| `L8.shock.black_swan` | `cheap_classify` | `True` | 10 | 0 | 0 | 10 | event_keyword_screen:10 |
| `L8.shock.crisis` | `cheap_classify` | `True` | 10 | 10 | 0 | 0 | event_keyword_screen:10 |
| `L8.shock.supply_break` | `cheap_classify` | `True` | 10 | 10 | 0 | 0 | event_keyword_screen:10 |
| `L9.company.ma` | `cheap_classify` | `False` | 10 | 10 | 0 | 0 | event_keyword_screen:10 |
| `L9.company.product_order` | `cheap_classify` | `False` | 10 | 10 | 0 | 0 | event_keyword_screen:10 |
| `L9.industry.data_price` | `cheap_classify` | `False` | 10 | 0 | 0 | 10 | event_keyword_screen:10 |
| `L9.macro.geo` | `cheap_classify` | `False` | 10 | 0 | 0 | 10 | event_keyword_screen:10 |
| `L9.media.short_report` | `cheap_classify` | `True` | 10 | 10 | 0 | 0 | event_keyword_screen:10 |

## Interpretation

- `status_and_value_close` is strong evidence that the local candidate matches the current overlay baseline.
- `non_llm_missing_llm_available` means the current harness cannot reproduce a baseline value; it is not yet proof that LLM is mandatory.
- `*:gated` means deterministic logic can screen or package evidence, but Known writes still need LLM/human or connector review.
- Web-analysis fields are treated as connector gaps, not prompt-quality gaps.
