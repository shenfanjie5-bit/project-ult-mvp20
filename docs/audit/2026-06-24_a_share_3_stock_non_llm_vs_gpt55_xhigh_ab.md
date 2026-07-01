# A-share 3-stock non-LLM vs GPT-5.5 xhigh A/B audit

- Generated: `2026-06-24T00:57:01+08:00`
- Temp worktree: `/private/tmp/project_ult_ab_gpt55_run_fixcheck`
- Target fields: `55`
- Records: `165`
- A available: `158`
- B available: `96`
- B schema invalid: `0`
- B evidence issues: `0`
- Main overlay unchanged: `True`

## Samples

| ts_code | name | industry | batches | prompt/log directory | temp overlay |
|---|---|---|---:|---|---|
| `300750.SZ` | 宁德时代 | `STORAGE_GRID` | 7 | `/private/tmp/project_ult_ab_gpt55_run_fixcheck/tmp_ab_prompts` | `/private/tmp/project_ult_ab_gpt55_run_fixcheck/config/stock_overlays/STORAGE_GRID/300750.SZ.yaml` |
| `600999.SH` | 招商证券 | `FINANCIAL_HIGH_DIVIDEND` | 7 | `/private/tmp/project_ult_ab_gpt55_run_fixcheck/tmp_ab_prompts` | `/private/tmp/project_ult_ab_gpt55_run_fixcheck/config/stock_overlays/FINANCIAL_HIGH_DIVIDEND/600999.SH.yaml` |
| `600754.SH` | 锦江酒店 | `DOMESTIC_CONSUMPTION` | 7 | `/private/tmp/project_ult_ab_gpt55_run_fixcheck/tmp_ab_prompts` | `/private/tmp/project_ult_ab_gpt55_run_fixcheck/config/stock_overlays/DOMESTIC_CONSUMPTION/600754.SH.yaml` |

## Buckets

| bucket | count |
|---|---:|
| `status_diff` | 82 |
| `a_only` | 62 |
| `status_match_value_differs` | 12 |
| `both_missing` | 7 |
| `scalar_close` | 2 |

## Verdicts

| verdict | count |
|---|---:|
| `MANUAL_REVIEW_PROXY_DIFF` | 65 |
| `A_RULE_ACCEPTABLE_B_MISSING` | 62 |
| `MANUAL_REVIEW` | 32 |
| `MANUAL_REVIEW_VALUE_DIFF` | 4 |
| `A_RULE_ACCEPTABLE` | 2 |

## Tier Summary

| tier | buckets |
|---|---|
| `analysis` | `{"a_only": 36, "both_missing": 7, "scalar_close": 2, "status_diff": 45, "status_match_value_differs": 12}` |
| `cheap_classify` | `{"a_only": 23, "status_diff": 22}` |
| `cheap_extract` | `{"a_only": 3, "status_diff": 15}` |

## Conflict / Review Queue

| ts_code | dp_id | tier | bucket | verdict | A method | A status | B status | diff |
|---|---|---|---|---|---|---|---|---|
| `300750.SZ` | `L1.moat.tags` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L1.model.tag` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L1.position.growth_rank` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `peer_growth_rank` | `Proxy` | `Known` | `{"added_keys": [], "changed_key_count": 4, "changed_keys": ["evidence_summary", "notes", "rank", "source_year"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L1.position.market_share` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 6, "changed_keys": ["market_size_unit", "notes", "rank", "share_pct", "source_year", "trend"], "kind": "mapping", "remo...` |
| `300750.SZ` | `L1.role.tag` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L1.stock_attr.tags` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L2.segment.cash_contrib` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L2.segment.industry_exposure` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["cyclical_sensitivity", "exposures", "notes"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L2.segment.opex_ratio` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `company_opex_ratio_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "ratio"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": ["score"]}` |
| `300750.SZ` | `L2.segment.profit_share` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `segment_profit_share_runtime` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["notes", "segments", "top_profit_share_pct"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.channel.cost` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` | `{"added_keys": ["cost_ratio", "evidence_summary", "trend"], "changed_key_count": 2, "changed_keys": ["notes", "score"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.channel.efficiency` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_efficiency_formula` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary", "notes", "revenue_per_channel", "trend"], "changed_key_count": 2, "changed_keys": ["score", "sga_rd_ratio_revenue"], "kind": "mapping", "remo...` |
| `300750.SZ` | `L3.channel.mix` | `cheap_extract` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_mix_business_proxy` | `Proxy` | `Unknown` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["ecommerce_pct", "notes"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.channel.overseas` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `region_mix_runtime` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["localization_stage", "notes", "overseas_revenue_pct"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.customer.concentration` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L3.customer.solvency` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `ar_revenue_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["ar_concentration_risk", "notes"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.delivery.capacity_supply` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `capex_ppe_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "supplier_concentration"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.delivery.fulfillment_cost` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `fulfillment_cost_formula` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L3.product.margin_mix` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_gross_margin_runtime` | `Known` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 4, "changed_keys": ["gross_margin_pct", "margin_tier", "notes", "product_margin_split"], "kind": "mapping", "removed_ke...` |
| `300750.SZ` | `L3.product.portfolio` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_VALUE_DIFF` | `script_fill` | `Known` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "products"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.region.domestic_overseas` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `script_fill` | `Known` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L3.region.fx_geo` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 4, "changed_keys": ["domestic_pct", "fx_exposure_score", "notes", "overseas_pct"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.region.tier_mix` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `region_mix_runtime` | `Proxy` | `Unknown` | `{"added_keys": [], "changed_key_count": 3, "changed_keys": ["notes", "overseas_pct", "tier3_pct"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.cost.cac_production` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["drivers", "notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.cost.rent_energy_logistics` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["energy_yoy_pct", "evidence_summary", "logistics_yoy_pct", "rent_yoy_pct"], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "remov...` |
| `300750.SZ` | `L4.eff.capacity_utilization` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `capex_ppe_proxy` | `Proxy` | `Unknown` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.eff.store_labor` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `N/A` | `{"added_keys": ["evidence_summary", "revenue_per_employee", "revenue_per_store"], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.price.asp_aov_arpu` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` | `{"added_keys": ["currency", "evidence_summary"], "changed_key_count": 5, "changed_keys": ["metric_kind", "notes", "trend", "value", "yoy_pct"], "kind": "mapping", "removed_keys"...` |
| `300750.SZ` | `L4.price.discount` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.price.elasticity` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["estimation_method", "notes"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.price.pricing_power` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "strength"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.share.market` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 6, "changed_keys": ["market_size_unit", "notes", "rank", "share_pct", "source_year", "trend"], "kind": "mapping", "remo...` |
| `300750.SZ` | `L4.share.substitution` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "risk_level", "substitution_risk", "trend"], "changed_key_count": 2, "changed_keys": ["notes", "score"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.volume.orders` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary", "metric_kind", "trend", "unit", "value"], "changed_key_count": 3, "changed_keys": ["notes", "score", "yoy_pct"], "kind": "mapping", "removed_...` |
| `300750.SZ` | `L4.volume.sales` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "metric_kind", "trend", "unit", "value"], "changed_key_count": 3, "changed_keys": ["notes", "score", "yoy_pct"], "kind": "mapping", "removed_...` |
| `300750.SZ` | `L4.volume.shipments` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary", "metric_kind", "trend", "unit", "value"], "changed_key_count": 3, "changed_keys": ["notes", "score", "yoy_pct"], "kind": "mapping", "removed_...` |
| `300750.SZ` | `L4.volume.users` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L5.fcst.beat_probability` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `forecast_revision_formula` | `Proxy` | `Known` | `{"added_keys": ["analyst_count", "beat_probability_pct", "consensus_eps_avg", "consensus_eps_high", "consensus_eps_low", "drivers", "evidence_summary", "notes", "reports_90d", "...` |
| `300750.SZ` | `L8.gov.fraud_control` | `analysis` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_active", "evidence_summary", "fraud_or_internal_control_signal", "media_negative_count", "notes", "observed_event_type", "recent_filing_source_available",...` |
| `300750.SZ` | `L8.gov.litigation` | `analysis` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_active", "evidence_summary", "litigation_signal", "media_negative_count", "notes", "observed_event_type", "recent_filing_source_available", "risk_level"],...` |
| `300750.SZ` | `L8.industry.demand_supply` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `existing_runtime_or_derive` | `Inactive` | `Known` | `{"added_keys": ["capacity_trend", "demand_supply_signal", "demand_trend", "event_active", "evidence_summary", "inventory_state", "notes", "risk_level"], "changed_key_count": 0, ...` |
| `300750.SZ` | `L8.industry.price_war` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `existing_runtime_or_derive` | `Inactive` | `Known` | `{"added_keys": ["direct_compete_source_available", "event_active", "evidence_summary", "notes", "price_pressure", "price_war_signal", "pricing_power_state", "risk_level"], "chan...` |
| `300750.SZ` | `L8.industry.substitute` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L8.op.customer_channel` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["channel_failure_signal", "customer_loss_signal", "customer_order_progress", "event_active", "evidence_summary", "notes", "risk_level"], "changed_key_count": 0, ...` |
| `300750.SZ` | `L8.op.order_miss` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["customer_progress", "event_active", "evidence_summary", "guidance_profit_range", "guidance_type", "notes", "order_miss_signal", "risk_level"], "changed_key_coun...` |
| `300750.SZ` | `L8.op.product_fail` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L8.reg.license_risk` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L8.reg.subsidy_off` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L8.reg.tax_trade` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_active", "evidence_summary", "fx_direction", "fx_risk_event", "notes", "risk_level", "tax_trade_signal", "usdcnh_change_pct"], "changed_key_count": 0, "ch...` |
| `300750.SZ` | `L8.reg.tighten` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["company_specific_signal", "event_active", "evidence_summary", "negative_policy_count", "notes", "policy_event_active", "regulation_tighten_signal", "risk_level"...` |
| `300750.SZ` | `L8.shock.crisis` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["company_specific_signal", "crisis_signal", "event_active", "evidence_summary", "media_event_active", "media_negative_count", "notes", "risk_level", "social_buzz...` |
| `300750.SZ` | `L8.shock.supply_break` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["company_specific_signal", "compete_risk_event_active", "event_active", "evidence_summary", "media_negative_count", "notes", "risk_level", "supply_break_signal"]...` |
| `300750.SZ` | `L9.company.ma` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L9.company.product_order` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["company_specific_signal", "event_active", "evidence_summary", "notes", "product_or_order_signal", "recent_announcement_count"], "changed_key_count": 0, "changed...` |
| `300750.SZ` | `L9.media.short_report` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["direct_a_share_short_report_documents", "event_active", "evidence_summary", "notes", "short_report_signal", "social_buzz_signal"], "changed_key_count": 0, "chan...` |
| `600999.SH` | `L1.moat.tags` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L1.model.tag` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L1.position.growth_rank` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `peer_growth_rank` | `Proxy` | `Known` | `{"added_keys": [], "changed_key_count": 4, "changed_keys": ["evidence_summary", "notes", "rank", "source_year"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L1.position.market_share` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 6, "changed_keys": ["market_size_unit", "notes", "rank", "share_pct", "source_year", "trend"], "kind": "mapping", "remo...` |
| `600999.SH` | `L1.role.tag` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L1.stock_attr.tags` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L2.segment.cash_contrib` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L2.segment.industry_exposure` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["cyclical_sensitivity", "notes"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L2.segment.opex_ratio` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `company_opex_ratio_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "ratio"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": ["score"]}` |
| `600999.SH` | `L2.segment.profit_share` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_profit_share_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["notes", "segments", "top_profit_share_pct"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L3.channel.cost` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` | `{"added_keys": ["cost_ratio", "evidence_summary", "trend"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": ["score"]}` |
| `600999.SH` | `L3.channel.efficiency` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_efficiency_formula` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary", "notes", "revenue_per_channel", "trend"], "changed_key_count": 1, "changed_keys": ["sga_rd_ratio_revenue"], "kind": "mapping", "removed_keys"...` |
| `600999.SH` | `L3.channel.mix` | `cheap_extract` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_mix_business_proxy` | `Proxy` | `Unknown` | `{"added_keys": [], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L3.channel.overseas` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 4, "changed_keys": ["key_markets", "localization_stage", "notes", "overseas_revenue_pct"], "kind": "mapping", "removed_...` |
| `600999.SH` | `L3.customer.concentration` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600999.SH` | `L3.customer.solvency` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600999.SH` | `L3.delivery.capacity_supply` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `capex_ppe_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L3.delivery.fulfillment_cost` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `fulfillment_cost_formula` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "fulfillment_cost_pct", "trend"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": ["gross_margin", "sco...` |
| `600999.SH` | `L3.product.margin_mix` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_gross_margin_runtime` | `Known` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 4, "changed_keys": ["gross_margin_pct", "margin_tier", "notes", "product_margin_split"], "kind": "mapping", "removed_ke...` |
| `600999.SH` | `L3.product.portfolio` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_VALUE_DIFF` | `script_fill` | `Known` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "products"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L3.region.tier_mix` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Known` | `{"added_keys": [], "changed_key_count": 3, "changed_keys": ["notes", "overseas_pct", "tier3_pct"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L4.cost.cac_production` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["drivers", "notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L4.cost.rent_energy_logistics` | `analysis` | `status_diff` | `MANUAL_REVIEW` | `industry_applicability_matrix` | `N/A` | `Known` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["evidence_summary", "notes"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L4.eff.capacity_utilization` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `capex_ppe_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L4.eff.store_labor` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "revenue_per_employee", "revenue_per_store"], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L4.price.asp_aov_arpu` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` | `{"added_keys": ["currency", "evidence_summary"], "changed_key_count": 3, "changed_keys": ["metric_kind", "notes", "value"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L4.price.discount` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `financial_price_signal_text` | `Known` | `Unknown` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L4.price.elasticity` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `gross_margin_proxy` | `Unknown` | `Unknown` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600999.SH` | `L4.price.pricing_power` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `financial_price_signal_text` | `Known` | `Known` | `{"added_keys": [], "changed_key_count": 4, "changed_keys": ["evidence_summary", "notes", "recent_price_adjustment", "strength"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L4.share.market` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 6, "changed_keys": ["market_size_unit", "notes", "rank", "share_pct", "source_year", "trend"], "kind": "mapping", "remo...` |
| `600999.SH` | `L4.share.substitution` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "risk_level", "substitution_risk", "trend"], "changed_key_count": 2, "changed_keys": ["notes", "score"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L4.volume.orders` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "metric_kind", "trend", "unit", "value"], "changed_key_count": 3, "changed_keys": ["notes", "score", "yoy_pct"], "kind": "mapping", "removed_...` |
| `600999.SH` | `L4.volume.sales` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "metric_kind", "trend", "unit", "value"], "changed_key_count": 2, "changed_keys": ["notes", "score"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L4.volume.shipments` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `N/A` | `{"added_keys": ["evidence_summary", "metric_kind", "trend", "unit", "value"], "changed_key_count": 3, "changed_keys": ["notes", "score", "yoy_pct"], "kind": "mapping", "removed_...` |
| `600999.SH` | `L4.volume.users` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["customer_count", "evidence_summary", "proxy_metrics", "user_count_yoy_pct"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys...` |
| `600999.SH` | `L5.fcst.beat_probability` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `forecast_revision_formula` | `Proxy` | `Known` | `{"added_keys": ["analyst_count", "beat_probability", "consensus_eps_2026e", "eps_high", "eps_low", "evidence_summary", "notes", "probability_band", "revision_30d_pct", "revision...` |
| `600999.SH` | `L8.gov.fraud_control` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `event_keyword_screen` | `Inactive` | `Inactive` | `{"added_keys": ["direct_fraud_or_internal_control_signal", "evidence_summary", "latest_management_ann_date", "management_event_count_180d", "notes", "risk_active", "risk_level"]...` |
| `600999.SH` | `L8.gov.litigation` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `event_keyword_screen` | `Inactive` | `Inactive` | `{"added_keys": ["direct_litigation_signal", "evidence_summary", "latest_management_ann_date", "management_event_count_180d", "notes", "risk_active", "risk_level"], "changed_key_...` |
| `600999.SH` | `L8.industry.demand_supply` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `existing_runtime_or_derive` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.industry.price_war` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `existing_runtime_or_derive` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.industry.substitute` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.op.customer_channel` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.op.order_miss` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.op.product_fail` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.reg.license_risk` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.reg.subsidy_off` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.reg.tax_trade` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"added_keys": ["affected_business", "event_active", "evidence_summary", "notes", "risk_level"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": [...` |
| `600999.SH` | `L8.reg.tighten` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"added_keys": ["affected_business", "event_active", "evidence_summary", "notes", "risk_level"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": [...` |
| `600999.SH` | `L8.shock.crisis` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["affected_business", "event_active", "evidence_summary", "notes", "risk_level"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": [...` |
| `600999.SH` | `L8.shock.supply_break` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["affected_business", "event_active", "evidence_summary", "notes", "risk_level"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": [...` |
| `600999.SH` | `L9.company.ma` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"added_keys": ["deal_type", "event_active", "evidence_summary", "notes", "target_or_asset"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["ev...` |
| `600999.SH` | `L9.company.product_order` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["affected_business", "event_active", "event_type", "evidence_summary", "notes"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": [...` |
| `600999.SH` | `L9.media.short_report` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["direct_a_share_short_report_documents", "event_active", "evidence_summary", "notes"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_ke...` |
| `600754.SH` | `L1.moat.tags` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L1.model.tag` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L1.position.growth_rank` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `peer_growth_rank` | `Proxy` | `Known` | `{"added_keys": [], "changed_key_count": 4, "changed_keys": ["evidence_summary", "notes", "rank", "source_year"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L1.position.market_share` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L1.role.tag` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L1.stock_attr.tags` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L2.segment.cash_contrib` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L2.segment.industry_exposure` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["cyclical_sensitivity", "exposures", "notes"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L2.segment.opex_ratio` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `company_opex_ratio_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "ratio"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": ["score"]}` |
| `600754.SH` | `L2.segment.profit_share` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `segment_profit_share_runtime` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L3.channel.cost` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` | `{"added_keys": ["cost_ratio", "evidence_summary", "trend"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": ["score"]}` |
| `600754.SH` | `L3.channel.efficiency` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_efficiency_formula` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L3.channel.mix` | `cheap_extract` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_mix_business_proxy` | `Proxy` | `Unknown` | `{"added_keys": [], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L3.channel.overseas` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `region_mix_runtime` | `Unknown` | `Unknown` | `{"kind": "same"}` |
| `600754.SH` | `L3.customer.concentration` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` | `{"kind": "same"}` |
| `600754.SH` | `L3.customer.solvency` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `ar_revenue_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L3.delivery.capacity_supply` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `capex_ppe_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["bottleneck", "notes", "supplier_concentration"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L3.delivery.fulfillment_cost` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `fulfillment_cost_formula` | `Proxy` | `Known` | `{"added_keys": ["drivers", "evidence_summary", "fulfillment_cost_ratio", "gross_margin_pct", "trend"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "rem...` |
| `600754.SH` | `L3.product.margin_mix` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_gross_margin_runtime` | `Known` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 4, "changed_keys": ["gross_margin_pct", "margin_tier", "notes", "product_margin_split"], "kind": "mapping", "removed_ke...` |
| `600754.SH` | `L3.product.portfolio` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_VALUE_DIFF` | `main_business_product_parser` | `Known` | `Known` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["evidence_summary", "notes"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L3.region.domestic_overseas` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_VALUE_DIFF` | `main_business_region_parser` | `Known` | `Known` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["evidence_summary", "notes"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L3.region.fx_geo` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `macro_fx_only` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L3.region.tier_mix` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `region_mix_runtime` | `Unknown` | `Unknown` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600754.SH` | `L4.cost.cac_production` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["drivers", "notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.cost.rent_energy_logistics` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `industry_applicability_matrix` | `N/A` | `Unknown` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["evidence_summary", "notes"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.eff.capacity_utilization` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `capex_ppe_proxy` | `Proxy` | `Known` | `{"added_keys": [], "changed_key_count": 3, "changed_keys": ["bottleneck", "notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.eff.store_labor` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "revenue_per_employee", "revenue_per_store"], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.price.asp_aov_arpu` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["currency", "evidence_summary"], "changed_key_count": 4, "changed_keys": ["metric_kind", "notes", "trend", "yoy_pct"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.price.discount` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Known` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.price.elasticity` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["estimation_method", "notes"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.price.pricing_power` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "strength"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.share.market` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 6, "changed_keys": ["market_size_unit", "notes", "rank", "share_pct", "source_year", "trend"], "kind": "mapping", "remo...` |
| `600754.SH` | `L4.share.substitution` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary", "risk_level", "substitution_risk", "trend"], "changed_key_count": 3, "changed_keys": ["notes", "score", "yoy_pct"], "kind": "mapping", "remov...` |
| `600754.SH` | `L4.volume.orders` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary", "metric_kind", "trend", "unit", "value"], "changed_key_count": 3, "changed_keys": ["notes", "score", "yoy_pct"], "kind": "mapping", "removed_...` |
| `600754.SH` | `L4.volume.sales` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "metric_kind", "trend", "unit", "value"], "changed_key_count": 3, "changed_keys": ["notes", "score", "yoy_pct"], "kind": "mapping", "removed_...` |
| `600754.SH` | `L4.volume.shipments` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary", "metric_kind", "trend", "unit", "value"], "changed_key_count": 3, "changed_keys": ["notes", "score", "yoy_pct"], "kind": "mapping", "removed_...` |
| `600754.SH` | `L4.volume.users` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary", "trend", "user_count"], "changed_key_count": 2, "changed_keys": ["notes", "yoy_pct"], "kind": "mapping", "removed_keys": ["score"]}` |
| `600754.SH` | `L5.fcst.beat_probability` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `forecast_revision_formula` | `Proxy` | `Known` | `{"added_keys": ["analyst_count", "assessment", "beat_probability", "cashflow_estimate_available", "consensus_eps_2026e", "eps_revision_30d_pct", "evidence_summary", "notes", "po...` |
| `600754.SH` | `L8.gov.fraud_control` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `event_keyword_screen` | `Inactive` | `Inactive` | `{"added_keys": ["evidence_summary", "notes", "risk_level"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["score"]}` |
| `600754.SH` | `L8.gov.litigation` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `event_keyword_screen` | `Inactive` | `Inactive` | `{"added_keys": ["evidence_summary", "notes", "risk_level"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["score"]}` |
| `600754.SH` | `L8.industry.demand_supply` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `existing_runtime_or_derive` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "industry_signals", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["_in...` |
| `600754.SH` | `L8.industry.price_war` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `existing_runtime_or_derive` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L8.industry.substitute` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L8.op.customer_channel` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["channel_metrics", "evidence_summary", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["even...` |
| `600754.SH` | `L8.op.order_miss` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "metric_snapshot", "notes", "risk_active", "risk_type", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_...` |
| `600754.SH` | `L8.op.product_fail` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L8.reg.license_risk` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L8.reg.subsidy_off` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L8.reg.tax_trade` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"added_keys": ["event_active", "evidence_summary", "notes", "risk_type"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "keywor...` |
| `600754.SH` | `L8.reg.tighten` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_active", "evidence_summary", "impact_direction", "notes", "risk_type"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["e...` |
| `600754.SH` | `L8.shock.crisis` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_active", "evidence_summary", "impact_direction", "notes", "risk_type"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["e...` |
| `600754.SH` | `L8.shock.supply_break` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_active", "evidence_summary", "impact_direction", "notes", "risk_type"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["e...` |
| `600754.SH` | `L9.company.ma` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"added_keys": ["catalyst_type", "event_active", "evidence_summary", "notes"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "ke...` |
| `600754.SH` | `L9.company.product_order` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["catalyst_type", "event_active", "evidence_summary", "impact_direction", "notes"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys":...` |
| `600754.SH` | `L9.media.short_report` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["catalyst_type", "event_active", "evidence_summary", "impact_direction", "notes"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys":...` |

## Full A/B Table

| ts_code | dp_id | tier | score | bucket | verdict | A method | A status | B status |
|---|---|---|---:|---|---|---|---|---|
| `300750.SZ` | `L1.moat.tags` | `cheap_extract` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` |
| `300750.SZ` | `L1.model.tag` | `cheap_extract` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` |
| `300750.SZ` | `L1.position.growth_rank` | `cheap_extract` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `peer_growth_rank` | `Proxy` | `Known` |
| `300750.SZ` | `L1.position.market_share` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` |
| `300750.SZ` | `L1.role.tag` | `cheap_extract` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` |
| `300750.SZ` | `L1.stock_attr.tags` | `cheap_extract` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` |
| `300750.SZ` | `L2.segment.cash_contrib` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` |
| `300750.SZ` | `L2.segment.industry_exposure` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` |
| `300750.SZ` | `L2.segment.opex_ratio` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `company_opex_ratio_runtime` | `Proxy` | `Known` |
| `300750.SZ` | `L2.segment.profit_share` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `segment_profit_share_runtime` | `Proxy` | `Unknown` |
| `300750.SZ` | `L3.channel.cost` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` |
| `300750.SZ` | `L3.channel.efficiency` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_efficiency_formula` | `Proxy` | `Unknown` |
| `300750.SZ` | `L3.channel.mix` | `cheap_extract` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_mix_business_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L3.channel.overseas` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `region_mix_runtime` | `Proxy` | `Unknown` |
| `300750.SZ` | `L3.customer.concentration` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` |
| `300750.SZ` | `L3.customer.solvency` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `ar_revenue_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L3.delivery.capacity_supply` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `capex_ppe_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L3.delivery.fulfillment_cost` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `fulfillment_cost_formula` | `Proxy` | `Unknown` |
| `300750.SZ` | `L3.product.margin_mix` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_gross_margin_runtime` | `Known` | `Known` |
| `300750.SZ` | `L3.product.portfolio` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_VALUE_DIFF` | `script_fill` | `Known` | `Known` |
| `300750.SZ` | `L3.region.domestic_overseas` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `script_fill` | `Known` | `Unknown` |
| `300750.SZ` | `L3.region.fx_geo` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Known` |
| `300750.SZ` | `L3.region.tier_mix` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `region_mix_runtime` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.cost.cac_production` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` |
| `300750.SZ` | `L4.cost.rent_energy_logistics` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.eff.capacity_utilization` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `capex_ppe_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.eff.store_labor` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `N/A` |
| `300750.SZ` | `L4.price.asp_aov_arpu` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` |
| `300750.SZ` | `L4.price.discount` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.price.elasticity` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.price.pricing_power` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Known` |
| `300750.SZ` | `L4.share.market` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.share.substitution` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` |
| `300750.SZ` | `L4.volume.orders` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.volume.sales` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` |
| `300750.SZ` | `L4.volume.shipments` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.volume.users` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L5.fcst.beat_probability` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `forecast_revision_formula` | `Proxy` | `Known` |
| `300750.SZ` | `L8.gov.fraud_control` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `300750.SZ` | `L8.gov.litigation` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `300750.SZ` | `L8.industry.demand_supply` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `existing_runtime_or_derive` | `Inactive` | `Known` |
| `300750.SZ` | `L8.industry.price_war` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `existing_runtime_or_derive` | `Inactive` | `Known` |
| `300750.SZ` | `L8.industry.substitute` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `300750.SZ` | `L8.op.customer_channel` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `300750.SZ` | `L8.op.order_miss` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `300750.SZ` | `L8.op.product_fail` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `300750.SZ` | `L8.reg.license_risk` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `300750.SZ` | `L8.reg.subsidy_off` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `300750.SZ` | `L8.reg.tax_trade` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `300750.SZ` | `L8.reg.tighten` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `300750.SZ` | `L8.shock.crisis` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `300750.SZ` | `L8.shock.supply_break` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `300750.SZ` | `L9.company.ma` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `300750.SZ` | `L9.company.product_order` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `300750.SZ` | `L9.media.short_report` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600999.SH` | `L1.moat.tags` | `cheap_extract` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` |
| `600999.SH` | `L1.model.tag` | `cheap_extract` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` |
| `600999.SH` | `L1.position.growth_rank` | `cheap_extract` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `peer_growth_rank` | `Proxy` | `Known` |
| `600999.SH` | `L1.position.market_share` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` |
| `600999.SH` | `L1.role.tag` | `cheap_extract` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` |
| `600999.SH` | `L1.stock_attr.tags` | `cheap_extract` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` |
| `600999.SH` | `L2.segment.cash_contrib` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` |
| `600999.SH` | `L2.segment.industry_exposure` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` |
| `600999.SH` | `L2.segment.opex_ratio` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `company_opex_ratio_runtime` | `Proxy` | `Known` |
| `600999.SH` | `L2.segment.profit_share` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_profit_share_runtime` | `Proxy` | `Known` |
| `600999.SH` | `L3.channel.cost` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` |
| `600999.SH` | `L3.channel.efficiency` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_efficiency_formula` | `Proxy` | `Unknown` |
| `600999.SH` | `L3.channel.mix` | `cheap_extract` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_mix_business_proxy` | `Proxy` | `Unknown` |
| `600999.SH` | `L3.channel.overseas` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Known` |
| `600999.SH` | `L3.customer.concentration` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` |
| `600999.SH` | `L3.customer.solvency` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` |
| `600999.SH` | `L3.delivery.capacity_supply` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `capex_ppe_proxy` | `Proxy` | `Unknown` |
| `600999.SH` | `L3.delivery.fulfillment_cost` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `fulfillment_cost_formula` | `Proxy` | `Known` |
| `600999.SH` | `L3.product.margin_mix` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_gross_margin_runtime` | `Known` | `Known` |
| `600999.SH` | `L3.product.portfolio` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_VALUE_DIFF` | `script_fill` | `Known` | `Known` |
| `600999.SH` | `L3.region.domestic_overseas` | `analysis` | `False` | `scalar_close` | `A_RULE_ACCEPTABLE` | `script_fill` | `Known` | `Known` |
| `600999.SH` | `L3.region.fx_geo` | `analysis` | `False` | `scalar_close` | `A_RULE_ACCEPTABLE` | `region_mix_runtime` | `Proxy` | `Known` |
| `600999.SH` | `L3.region.tier_mix` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Known` |
| `600999.SH` | `L4.cost.cac_production` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` |
| `600999.SH` | `L4.cost.rent_energy_logistics` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW` | `industry_applicability_matrix` | `N/A` | `Known` |
| `600999.SH` | `L4.eff.capacity_utilization` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `capex_ppe_proxy` | `Proxy` | `Unknown` |
| `600999.SH` | `L4.eff.store_labor` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` |
| `600999.SH` | `L4.price.asp_aov_arpu` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` |
| `600999.SH` | `L4.price.discount` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `financial_price_signal_text` | `Known` | `Unknown` |
| `600999.SH` | `L4.price.elasticity` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `gross_margin_proxy` | `Unknown` | `Unknown` |
| `600999.SH` | `L4.price.pricing_power` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `financial_price_signal_text` | `Known` | `Known` |
| `600999.SH` | `L4.share.market` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` |
| `600999.SH` | `L4.share.substitution` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` |
| `600999.SH` | `L4.volume.orders` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` |
| `600999.SH` | `L4.volume.sales` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` |
| `600999.SH` | `L4.volume.shipments` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `N/A` |
| `600999.SH` | `L4.volume.users` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `600999.SH` | `L5.fcst.beat_probability` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `forecast_revision_formula` | `Proxy` | `Known` |
| `600999.SH` | `L8.gov.fraud_control` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `event_keyword_screen` | `Inactive` | `Inactive` |
| `600999.SH` | `L8.gov.litigation` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `event_keyword_screen` | `Inactive` | `Inactive` |
| `600999.SH` | `L8.industry.demand_supply` | `cheap_classify` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `existing_runtime_or_derive` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.industry.price_war` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `existing_runtime_or_derive` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.industry.substitute` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.op.customer_channel` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.op.order_miss` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.op.product_fail` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.reg.license_risk` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.reg.subsidy_off` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.reg.tax_trade` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.reg.tighten` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.shock.crisis` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600999.SH` | `L8.shock.supply_break` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600999.SH` | `L9.company.ma` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L9.company.product_order` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600999.SH` | `L9.media.short_report` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L1.moat.tags` | `cheap_extract` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` |
| `600754.SH` | `L1.model.tag` | `cheap_extract` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` |
| `600754.SH` | `L1.position.growth_rank` | `cheap_extract` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `peer_growth_rank` | `Proxy` | `Known` |
| `600754.SH` | `L1.position.market_share` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` |
| `600754.SH` | `L1.role.tag` | `cheap_extract` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` |
| `600754.SH` | `L1.stock_attr.tags` | `cheap_extract` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` |
| `600754.SH` | `L2.segment.cash_contrib` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` |
| `600754.SH` | `L2.segment.industry_exposure` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` |
| `600754.SH` | `L2.segment.opex_ratio` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `company_opex_ratio_runtime` | `Proxy` | `Known` |
| `600754.SH` | `L2.segment.profit_share` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `segment_profit_share_runtime` | `Proxy` | `Unknown` |
| `600754.SH` | `L3.channel.cost` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` |
| `600754.SH` | `L3.channel.efficiency` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_efficiency_formula` | `Proxy` | `Unknown` |
| `600754.SH` | `L3.channel.mix` | `cheap_extract` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_mix_business_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L3.channel.overseas` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `region_mix_runtime` | `Unknown` | `Unknown` |
| `600754.SH` | `L3.customer.concentration` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` |
| `600754.SH` | `L3.customer.solvency` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `ar_revenue_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L3.delivery.capacity_supply` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `capex_ppe_proxy` | `Proxy` | `Known` |
| `600754.SH` | `L3.delivery.fulfillment_cost` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `fulfillment_cost_formula` | `Proxy` | `Known` |
| `600754.SH` | `L3.product.margin_mix` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_gross_margin_runtime` | `Known` | `Known` |
| `600754.SH` | `L3.product.portfolio` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_VALUE_DIFF` | `main_business_product_parser` | `Known` | `Known` |
| `600754.SH` | `L3.region.domestic_overseas` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_VALUE_DIFF` | `main_business_region_parser` | `Known` | `Known` |
| `600754.SH` | `L3.region.fx_geo` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `macro_fx_only` | `Proxy` | `Known` |
| `600754.SH` | `L3.region.tier_mix` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `region_mix_runtime` | `Unknown` | `Unknown` |
| `600754.SH` | `L4.cost.cac_production` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` |
| `600754.SH` | `L4.cost.rent_energy_logistics` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `industry_applicability_matrix` | `N/A` | `Unknown` |
| `600754.SH` | `L4.eff.capacity_utilization` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `capex_ppe_proxy` | `Proxy` | `Known` |
| `600754.SH` | `L4.eff.store_labor` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` |
| `600754.SH` | `L4.price.asp_aov_arpu` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L4.price.discount` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Known` |
| `600754.SH` | `L4.price.elasticity` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L4.price.pricing_power` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Known` |
| `600754.SH` | `L4.share.market` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` |
| `600754.SH` | `L4.share.substitution` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L4.volume.orders` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L4.volume.sales` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` |
| `600754.SH` | `L4.volume.shipments` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L4.volume.users` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L5.fcst.beat_probability` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `forecast_revision_formula` | `Proxy` | `Known` |
| `600754.SH` | `L8.gov.fraud_control` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `event_keyword_screen` | `Inactive` | `Inactive` |
| `600754.SH` | `L8.gov.litigation` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `event_keyword_screen` | `Inactive` | `Inactive` |
| `600754.SH` | `L8.industry.demand_supply` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `existing_runtime_or_derive` | `Inactive` | `Known` |
| `600754.SH` | `L8.industry.price_war` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `existing_runtime_or_derive` | `Inactive` | `Unknown` |
| `600754.SH` | `L8.industry.substitute` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600754.SH` | `L8.op.customer_channel` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L8.op.order_miss` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L8.op.product_fail` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600754.SH` | `L8.reg.license_risk` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600754.SH` | `L8.reg.subsidy_off` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600754.SH` | `L8.reg.tax_trade` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600754.SH` | `L8.reg.tighten` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L8.shock.crisis` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L8.shock.supply_break` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L9.company.ma` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600754.SH` | `L9.company.product_order` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L9.media.short_report` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
