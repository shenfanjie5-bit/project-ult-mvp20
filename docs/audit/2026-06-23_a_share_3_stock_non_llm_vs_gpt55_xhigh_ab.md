# A-share 3-stock non-LLM vs GPT-5.5 xhigh A/B audit

- Generated: `2026-06-23T21:07:35+08:00`
- Temp worktree: `/private/tmp/project_ult_ab_gpt55_run`
- Target fields: `55`
- Records: `165`
- A available: `151`
- B available: `98`
- B schema invalid: `0`
- B evidence issues: `0`
- Main overlay unchanged: `True`

## Samples

| ts_code | name | industry | batches | prompt/log directory | temp overlay |
|---|---|---|---:|---|---|
| `300750.SZ` | 宁德时代 | `STORAGE_GRID` | 7 | `/private/tmp/project_ult_ab_gpt55_run/tmp_ab_prompts` | `/private/tmp/project_ult_ab_gpt55_run/config/stock_overlays/STORAGE_GRID/300750.SZ.yaml` |
| `600999.SH` | 招商证券 | `FINANCIAL_HIGH_DIVIDEND` | 7 | `/private/tmp/project_ult_ab_gpt55_run/tmp_ab_prompts` | `/private/tmp/project_ult_ab_gpt55_run/config/stock_overlays/FINANCIAL_HIGH_DIVIDEND/600999.SH.yaml` |
| `600754.SH` | 锦江酒店 | `DOMESTIC_CONSUMPTION` | 7 | `/private/tmp/project_ult_ab_gpt55_run/tmp_ab_prompts` | `/private/tmp/project_ult_ab_gpt55_run/config/stock_overlays/DOMESTIC_CONSUMPTION/600754.SH.yaml` |

## Buckets

| bucket | count |
|---|---:|
| `status_diff` | 77 |
| `a_only` | 59 |
| `status_match_value_differs` | 10 |
| `both_missing` | 8 |
| `b_only` | 6 |
| `scalar_close` | 5 |

## Verdicts

| verdict | count |
|---|---:|
| `A_RULE_ACCEPTABLE_B_MISSING` | 59 |
| `MANUAL_REVIEW_PROXY_DIFF` | 53 |
| `MANUAL_REVIEW` | 40 |
| `A_RULE_NEEDS_REVIEW_OR_FIX` | 6 |
| `A_RULE_ACCEPTABLE` | 5 |
| `MANUAL_REVIEW_VALUE_DIFF` | 2 |

## Tier Summary

| tier | buckets |
|---|---|
| `analysis` | `{"a_only": 39, "b_only": 6, "both_missing": 8, "scalar_close": 5, "status_diff": 34, "status_match_value_differs": 10}` |
| `cheap_classify` | `{"a_only": 17, "status_diff": 28}` |
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
| `300750.SZ` | `L2.segment.opex_ratio` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `company_opex_ratio_runtime` | `Proxy` | `Known` | `{"added_keys": ["admin_expense_ratio", "company_opex_ratio", "evidence_summary", "rd_expense_ratio", "segment_breakdown", "selling_expense_ratio", "sga_ratio"], "changed_key_cou...` |
| `300750.SZ` | `L2.segment.profit_share` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `segment_profit_share_runtime` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "segments"], "kind": "mapping", "removed_keys": ["top_profit_share_pct"]}` |
| `300750.SZ` | `L3.channel.cost` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `sga_revenue_ratio` | `Proxy` | `Unknown` | `{"added_keys": ["channel_breakdown", "evidence_summary", "selling_expense", "selling_expense_ratio", "sga_rd_ratio"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": ...` |
| `300750.SZ` | `L3.channel.efficiency` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_efficiency_formula` | `Proxy` | `Unknown` | `{"added_keys": ["channel_mix_available", "efficiency_metrics", "evidence_summary", "notes", "revenue"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_k...` |
| `300750.SZ` | `L3.channel.mix` | `cheap_extract` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_mix_business_proxy` | `Proxy` | `Unknown` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["ecommerce_pct", "notes"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.channel.overseas` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `region_mix_runtime` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["localization_stage", "notes", "overseas_revenue_pct"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.customer.concentration` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L3.customer.solvency` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `ar_revenue_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["ar_concentration_risk", "notes"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.delivery.capacity_supply` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `capex_ppe_proxy` | `Proxy` | `Proxy` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "supplier_concentration"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.product.margin_mix` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_gross_margin_runtime` | `Known` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["gross_margin_pct", "margin_tier", "notes"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.product.portfolio` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_VALUE_DIFF` | `script_fill` | `Known` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "products"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L3.region.domestic_overseas` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `script_fill` | `Known` | `Unknown` | `{"added_keys": ["notes", "regions"], "changed_key_count": 2, "changed_keys": ["domestic_pct", "overseas_pct"], "kind": "mapping", "removed_keys": ["source"]}` |
| `300750.SZ` | `L3.region.fx_geo` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Proxy` | `{"added_keys": ["macro_fx_direction", "risk_event", "rmb_appreciation_pct", "usdcnh_change_pct"], "changed_key_count": 4, "changed_keys": ["domestic_pct", "fx_exposure_score", "...` |
| `300750.SZ` | `L3.region.tier_mix` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `region_mix_runtime` | `Proxy` | `Unknown` | `{"added_keys": [], "changed_key_count": 3, "changed_keys": ["notes", "overseas_pct", "tier3_pct"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.cost.cac_production` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Proxy` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["drivers", "notes"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.cost.rent_energy_logistics` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Proxy` | `{"added_keys": ["energy_yoy_pct", "evidence_summary", "logistics_yoy_pct", "rent_yoy_pct"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys":...` |
| `300750.SZ` | `L4.eff.capacity_utilization` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `capex_ppe_proxy` | `Proxy` | `Proxy` | `{"added_keys": [], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.eff.store_labor` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `N/A` | `{"added_keys": ["evidence_summary", "revenue_per_employee", "revenue_per_store"], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.price.asp_aov_arpu` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["currency", "evidence_summary"], "changed_key_count": 4, "changed_keys": ["metric_kind", "notes", "trend", "yoy_pct"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.price.discount` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.price.elasticity` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["estimation_method", "notes"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.price.pricing_power` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "strength"], "kind": "mapping", "removed_keys": []}` |
| `300750.SZ` | `L4.share.market` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L4.share.substitution` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L4.volume.orders` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L4.volume.sales` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L4.volume.shipments` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L4.volume.users` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `300750.SZ` | `L8.gov.litigation` | `analysis` | `b_only` | `A_RULE_NEEDS_REVIEW_OR_FIX` | `event_keyword_screen` | `Unknown` | `Inactive` | `{"added_keys": ["event_state", "evidence_summary", "notes", "score"], "changed_key_count": 1, "changed_keys": ["keyword_hits"], "kind": "mapping", "removed_keys": ["screening_st...` |
| `300750.SZ` | `L8.industry.demand_supply` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `existing_runtime_or_derive` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["_inactive", "missing_in...` |
| `300750.SZ` | `L8.industry.price_war` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `existing_runtime_or_derive` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["_inactive", "missing_in...` |
| `300750.SZ` | `L8.industry.substitute` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"added_keys": ["evidence_summary", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "keyword_...` |
| `300750.SZ` | `L8.op.customer_channel` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "keyword_...` |
| `300750.SZ` | `L8.op.order_miss` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "guidance_state", "guidance_summary", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "re...` |
| `300750.SZ` | `L8.op.product_fail` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"added_keys": ["evidence_summary", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "keyword_...` |
| `300750.SZ` | `L8.reg.license_risk` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"added_keys": ["evidence_summary", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "keyword_...` |
| `300750.SZ` | `L8.reg.subsidy_off` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"added_keys": ["evidence_summary", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "keyword_...` |
| `300750.SZ` | `L8.reg.tax_trade` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "notes", "policy_signal", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_...` |
| `300750.SZ` | `L8.reg.tighten` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "notes", "policy_signal", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_...` |
| `300750.SZ` | `L8.shock.crisis` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_signal", "evidence_summary", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_s...` |
| `300750.SZ` | `L8.shock.supply_break` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_signal", "evidence_summary", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_s...` |
| `300750.SZ` | `L9.company.ma` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_active", "event_type", "evidence_summary", "notes", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_st...` |
| `300750.SZ` | `L9.company.product_order` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_active", "event_type", "evidence_summary", "notes", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_st...` |
| `300750.SZ` | `L9.media.short_report` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_active", "evidence_summary", "notes", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["keyword_hits", "score"]}` |
| `600999.SH` | `L1.moat.tags` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L1.model.tag` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L1.position.growth_rank` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `peer_growth_rank` | `Proxy` | `Known` | `{"added_keys": [], "changed_key_count": 4, "changed_keys": ["evidence_summary", "notes", "rank", "source_year"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L1.position.market_share` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 6, "changed_keys": ["market_size_unit", "notes", "rank", "share_pct", "source_year", "trend"], "kind": "mapping", "remo...` |
| `600999.SH` | `L1.role.tag` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L1.stock_attr.tags` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L2.segment.cash_contrib` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "segments"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L2.segment.industry_exposure` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["cyclical_sensitivity", "exposures", "notes"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L2.segment.opex_ratio` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `company_opex_ratio_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "overall_opex_ratio_pct", "period", "revenue", "segment_opex_ratios", "sga_total"], "changed_key_count": 1, "changed_keys": ["notes"], "kind"...` |
| `600999.SH` | `L2.segment.profit_share` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_profit_share_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "net_profit", "operating_profit", "period", "profit_basis"], "changed_key_count": 2, "changed_keys": ["notes", "segments"], "kind": "mapping"...` |
| `600999.SH` | `L3.channel.cost` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `sga_revenue_ratio` | `Proxy` | `Unknown` | `{"added_keys": ["channel_cost_amount", "channel_cost_pct", "evidence_summary"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": ["ratio", "...` |
| `600999.SH` | `L3.channel.efficiency` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_efficiency_formula` | `Proxy` | `Unknown` | `{"added_keys": ["channel_efficiency", "evidence_summary", "notes", "revenue_per_channel"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["score...` |
| `600999.SH` | `L3.channel.mix` | `cheap_extract` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_mix_business_proxy` | `Proxy` | `Unknown` | `{"added_keys": [], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L3.channel.overseas` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 4, "changed_keys": ["key_markets", "localization_stage", "notes", "overseas_revenue_pct"], "kind": "mapping", "removed_...` |
| `600999.SH` | `L3.customer.concentration` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600999.SH` | `L3.customer.solvency` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600999.SH` | `L3.delivery.capacity_supply` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `capex_ppe_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "supplier_concentration"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L3.delivery.fulfillment_cost` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `fulfillment_cost_formula` | `Proxy` | `Unknown` | `{"added_keys": ["drivers", "evidence_summary", "fulfillment_cost_ratio", "trend"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": ["gross_...` |
| `600999.SH` | `L3.product.margin_mix` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_gross_margin_runtime` | `Known` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 4, "changed_keys": ["gross_margin_pct", "margin_tier", "notes", "product_margin_split"], "kind": "mapping", "removed_ke...` |
| `600999.SH` | `L3.product.portfolio` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_VALUE_DIFF` | `script_fill` | `Known` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "products"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L3.region.fx_geo` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Known` | `{"added_keys": ["direction", "evidence_summary", "fx_risk_score", "risk_event", "usdcnh_change_pct"], "changed_key_count": 2, "changed_keys": ["notes", "overseas_pct"], "kind": ...` |
| `600999.SH` | `L3.region.tier_mix` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Known` | `{"added_keys": [], "changed_key_count": 3, "changed_keys": ["notes", "overseas_pct", "tier3_pct"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L4.cost.cac_production` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["drivers", "notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L4.cost.rent_energy_logistics` | `analysis` | `b_only` | `A_RULE_NEEDS_REVIEW_OR_FIX` | `gross_margin_proxy` | `Unknown` | `N/A` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600999.SH` | `L4.eff.capacity_utilization` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `capex_ppe_proxy` | `Proxy` | `Unknown` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L4.eff.store_labor` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "revenue_per_employee", "revenue_per_store"], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600999.SH` | `L4.price.asp_aov_arpu` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` | `{"added_keys": ["currency", "evidence_summary"], "changed_key_count": 5, "changed_keys": ["metric_kind", "notes", "trend", "value", "yoy_pct"], "kind": "mapping", "removed_keys"...` |
| `600999.SH` | `L4.price.discount` | `analysis` | `b_only` | `A_RULE_NEEDS_REVIEW_OR_FIX` | `gross_margin_proxy` | `Unknown` | `Known` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600999.SH` | `L4.price.elasticity` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `gross_margin_proxy` | `Unknown` | `Unknown` | `{"kind": "same"}` |
| `600999.SH` | `L4.price.pricing_power` | `analysis` | `b_only` | `A_RULE_NEEDS_REVIEW_OR_FIX` | `gross_margin_proxy` | `Unknown` | `Known` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600999.SH` | `L4.share.market` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `peer_revenue_rank` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "metric_kind", "revenue_cny"], "changed_key_count": 4, "changed_keys": ["notes", "rank", "share_pct", "trend"], "kind": "mapping", "removed_k...` |
| `600999.SH` | `L4.share.substitution` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` | `{"added_keys": ["current_revenue_growth_yoy_pct", "evidence_summary", "qoq_pct", "risk_level", "trend"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "r...` |
| `600999.SH` | `L4.volume.orders` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "metric_kind", "order_count", "trend"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": ["score", "yoy_...` |
| `600999.SH` | `L4.volume.sales` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "metric_kind", "period", "trend", "unit", "value"], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": ["s...` |
| `600999.SH` | `L4.volume.shipments` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `N/A` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L4.volume.users` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L5.fcst.beat_probability` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `forecast_revision_formula` | `Proxy` | `Known` | `{"added_keys": ["analyst_count", "cashflow_estimate_available", "consensus_eps_2026e", "eps_revision_30d_pct", "evidence_summary", "notes", "probability_band"], "changed_key_cou...` |
| `600999.SH` | `L8.gov.fraud_control` | `analysis` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "notes", "risk_active", "risk_level"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "keywor...` |
| `600999.SH` | `L8.gov.litigation` | `analysis` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "notes", "risk_active", "risk_level"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "keywor...` |
| `600999.SH` | `L8.industry.demand_supply` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `existing_runtime_or_derive` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.industry.price_war` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `existing_runtime_or_derive` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.industry.substitute` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.op.customer_channel` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.op.order_miss` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.op.product_fail` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.reg.license_risk` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.reg.subsidy_off` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L8.reg.tax_trade` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "notes", "risk_active", "risk_level"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "keywor...` |
| `600999.SH` | `L8.reg.tighten` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "notes", "risk_active", "risk_level"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "keywor...` |
| `600999.SH` | `L8.shock.crisis` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "notes", "risk_active", "risk_level"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "keywor...` |
| `600999.SH` | `L8.shock.supply_break` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["evidence_summary", "notes", "risk_active", "risk_level"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "keywor...` |
| `600999.SH` | `L9.company.ma` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600999.SH` | `L9.company.product_order` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_active", "event_type", "evidence_summary", "notes"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_state", "keywo...` |
| `600999.SH` | `L9.media.short_report` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_active", "evidence_summary", "notes"], "changed_key_count": 1, "changed_keys": ["event_state"], "kind": "mapping", "removed_keys": ["keyword_hits", "score"]}` |
| `600754.SH` | `L1.moat.tags` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L1.model.tag` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L1.position.growth_rank` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `peer_growth_rank` | `Proxy` | `Known` | `{"added_keys": [], "changed_key_count": 4, "changed_keys": ["evidence_summary", "notes", "rank", "source_year"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L1.position.market_share` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 6, "changed_keys": ["market_size_unit", "notes", "rank", "share_pct", "source_year", "trend"], "kind": "mapping", "remo...` |
| `600754.SH` | `L1.role.tag` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L1.stock_attr.tags` | `cheap_extract` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `rule_tagging` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "tags"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L2.segment.cash_contrib` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `segment_revenue_share_runtime` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "segments"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L2.segment.industry_exposure` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["cyclical_sensitivity", "exposures", "notes"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L2.segment.opex_ratio` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `company_opex_ratio_runtime` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L2.segment.profit_share` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `segment_profit_share_runtime` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L3.channel.cost` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `sga_revenue_ratio` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L3.channel.efficiency` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_efficiency_formula` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L3.channel.mix` | `cheap_extract` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_mix_business_proxy` | `Proxy` | `Unknown` | `{"added_keys": [], "changed_key_count": 1, "changed_keys": ["notes"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L3.channel.overseas` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `region_mix_runtime` | `Unknown` | `Unknown` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600754.SH` | `L3.customer.concentration` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600754.SH` | `L3.customer.solvency` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `ar_revenue_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["ar_concentration_risk", "notes"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L3.delivery.capacity_supply` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `capex_ppe_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "supplier_concentration"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L3.product.margin_mix` | `analysis` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_gross_margin_runtime` | `Known` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 4, "changed_keys": ["gross_margin_pct", "margin_tier", "notes", "product_margin_split"], "kind": "mapping", "removed_ke...` |
| `600754.SH` | `L3.product.portfolio` | `analysis` | `b_only` | `A_RULE_NEEDS_REVIEW_OR_FIX` | `no_non_llm_extractor` | `Unknown` | `Known` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600754.SH` | `L3.region.domestic_overseas` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600754.SH` | `L3.region.fx_geo` | `analysis` | `b_only` | `A_RULE_NEEDS_REVIEW_OR_FIX` | `region_mix_runtime` | `Unknown` | `Known` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600754.SH` | `L3.region.tier_mix` | `analysis` | `both_missing` | `MANUAL_REVIEW` | `region_mix_runtime` | `Unknown` | `Unknown` | `{"a_type": "NoneType", "b_type": "dict", "kind": "scalar_or_type"}` |
| `600754.SH` | `L4.cost.cac_production` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 3, "changed_keys": ["drivers", "notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.cost.rent_energy_logistics` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Known` | `{"added_keys": ["energy_yoy_pct", "evidence_summary", "logistics_yoy_pct", "rent_yoy_pct"], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "remov...` |
| `600754.SH` | `L4.eff.capacity_utilization` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `capex_ppe_proxy` | `Proxy` | `Known` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.eff.store_labor` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary", "revenue_per_employee", "revenue_per_store"], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.price.asp_aov_arpu` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` | `{"added_keys": ["currency", "evidence_summary"], "changed_key_count": 5, "changed_keys": ["metric_kind", "notes", "trend", "value", "yoy_pct"], "kind": "mapping", "removed_keys"...` |
| `600754.SH` | `L4.price.discount` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` | `{"added_keys": [], "changed_key_count": 2, "changed_keys": ["notes", "trend"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.price.elasticity` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["estimation_method", "notes"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.price.pricing_power` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Known` | `{"added_keys": ["evidence_summary"], "changed_key_count": 2, "changed_keys": ["notes", "strength"], "kind": "mapping", "removed_keys": []}` |
| `600754.SH` | `L4.share.market` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L4.share.substitution` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L4.volume.orders` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L4.volume.sales` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L4.volume.shipments` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L4.volume.users` | `analysis` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L5.fcst.beat_probability` | `analysis` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `forecast_revision_formula` | `Proxy` | `Known` | `{"added_keys": ["assessment", "beat_probability_pct", "evidence_summary", "key_drivers", "notes"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys":...` |
| `600754.SH` | `L8.gov.fraud_control` | `analysis` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_count", "evidence_summary", "lookback_days", "media_negative_count", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kin...` |
| `600754.SH` | `L8.gov.litigation` | `analysis` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_count", "evidence_summary", "lookback_days", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_...` |
| `600754.SH` | `L8.industry.demand_supply` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `existing_runtime_or_derive` | `Inactive` | `Known` | `{"added_keys": ["demand_trend", "event_count", "evidence_summary", "notes", "risk_active", "severity", "supply_trend"], "changed_key_count": 0, "changed_keys": [], "kind": "mapp...` |
| `600754.SH` | `L8.industry.price_war` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `existing_runtime_or_derive` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L8.industry.substitute` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L8.op.customer_channel` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["channel_topic", "event_count", "evidence_summary", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_...` |
| `600754.SH` | `L8.op.order_miss` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_count", "evidence_summary", "guidance_type", "notes", "profit_change_range_pct", "profit_range_wan", "risk_active", "severity"], "changed_key_count": 0, "...` |
| `600754.SH` | `L8.op.product_fail` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_count", "evidence_summary", "notes", "risk_active", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping", "removed_keys": ["event_st...` |
| `600754.SH` | `L8.reg.license_risk` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L8.reg.subsidy_off` | `cheap_classify` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` | `{"a_type": "dict", "b_type": "NoneType", "kind": "scalar_or_type"}` |
| `600754.SH` | `L8.reg.tax_trade` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_count", "evidence_summary", "fx_risk_event", "notes", "policy_event_count", "risk_active", "rmb_appreciation_pct", "severity", "threshold_pct", "usdcnh_ch...` |
| `600754.SH` | `L8.reg.tighten` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["company_specific", "event_count", "evidence_summary", "negative_policy_count", "notes", "policy_event_count", "risk_active", "severity"], "changed_key_count": 0...` |
| `600754.SH` | `L8.shock.crisis` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["event_count", "evidence_summary", "media_count_24h", "negative_media_count", "notes", "risk_active", "severity", "social_buzz_active"], "changed_key_count": 0, ...` |
| `600754.SH` | `L8.shock.supply_break` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["company_specific", "event_count", "evidence_summary", "industry_compete_risk_count_24h", "media_count_24h", "notes", "risk_active", "severity"], "changed_key_co...` |
| `600754.SH` | `L9.company.ma` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["active", "company_specific", "event_count", "event_type", "evidence_summary", "notes", "severity"], "changed_key_count": 0, "changed_keys": [], "kind": "mapping...` |
| `600754.SH` | `L9.company.product_order` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["active", "announcement_count_recent", "company_specific", "event_type", "evidence_summary", "notes", "severity"], "changed_key_count": 0, "changed_keys": [], "k...` |
| `600754.SH` | `L9.media.short_report` | `cheap_classify` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` | `{"added_keys": ["active", "direct_a_share_short_report_documents", "event_type", "evidence_summary", "notes", "severity", "social_buzz_active"], "changed_key_count": 0, "changed...` |

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
| `300750.SZ` | `L3.channel.cost` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `sga_revenue_ratio` | `Proxy` | `Unknown` |
| `300750.SZ` | `L3.channel.efficiency` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_efficiency_formula` | `Proxy` | `Unknown` |
| `300750.SZ` | `L3.channel.mix` | `cheap_extract` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_mix_business_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L3.channel.overseas` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `region_mix_runtime` | `Proxy` | `Unknown` |
| `300750.SZ` | `L3.customer.concentration` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` |
| `300750.SZ` | `L3.customer.solvency` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `ar_revenue_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L3.delivery.capacity_supply` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `capex_ppe_proxy` | `Proxy` | `Proxy` |
| `300750.SZ` | `L3.delivery.fulfillment_cost` | `analysis` | `True` | `scalar_close` | `A_RULE_ACCEPTABLE` | `fulfillment_cost_formula` | `Proxy` | `Proxy` |
| `300750.SZ` | `L3.product.margin_mix` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_gross_margin_runtime` | `Known` | `Known` |
| `300750.SZ` | `L3.product.portfolio` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_VALUE_DIFF` | `script_fill` | `Known` | `Known` |
| `300750.SZ` | `L3.region.domestic_overseas` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `script_fill` | `Known` | `Unknown` |
| `300750.SZ` | `L3.region.fx_geo` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Proxy` |
| `300750.SZ` | `L3.region.tier_mix` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `region_mix_runtime` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.cost.cac_production` | `analysis` | `True` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Proxy` |
| `300750.SZ` | `L4.cost.rent_energy_logistics` | `analysis` | `True` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Proxy` |
| `300750.SZ` | `L4.eff.capacity_utilization` | `analysis` | `True` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `capex_ppe_proxy` | `Proxy` | `Proxy` |
| `300750.SZ` | `L4.eff.store_labor` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `N/A` |
| `300750.SZ` | `L4.price.asp_aov_arpu` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.price.discount` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.price.elasticity` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.price.pricing_power` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Known` |
| `300750.SZ` | `L4.share.market` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.share.substitution` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.volume.orders` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.volume.sales` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.volume.shipments` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L4.volume.users` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `300750.SZ` | `L5.fcst.beat_probability` | `analysis` | `True` | `scalar_close` | `A_RULE_ACCEPTABLE` | `forecast_revision_formula` | `Proxy` | `Known` |
| `300750.SZ` | `L8.gov.fraud_control` | `analysis` | `False` | `scalar_close` | `A_RULE_ACCEPTABLE` | `event_keyword_screen` | `Inactive` | `Inactive` |
| `300750.SZ` | `L8.gov.litigation` | `analysis` | `False` | `b_only` | `A_RULE_NEEDS_REVIEW_OR_FIX` | `event_keyword_screen` | `Unknown` | `Inactive` |
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
| `300750.SZ` | `L9.company.ma` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
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
| `600999.SH` | `L3.channel.cost` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `sga_revenue_ratio` | `Proxy` | `Unknown` |
| `600999.SH` | `L3.channel.efficiency` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_efficiency_formula` | `Proxy` | `Unknown` |
| `600999.SH` | `L3.channel.mix` | `cheap_extract` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_mix_business_proxy` | `Proxy` | `Unknown` |
| `600999.SH` | `L3.channel.overseas` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Known` |
| `600999.SH` | `L3.customer.concentration` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` |
| `600999.SH` | `L3.customer.solvency` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` |
| `600999.SH` | `L3.delivery.capacity_supply` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `capex_ppe_proxy` | `Proxy` | `Unknown` |
| `600999.SH` | `L3.delivery.fulfillment_cost` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `fulfillment_cost_formula` | `Proxy` | `Unknown` |
| `600999.SH` | `L3.product.margin_mix` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_gross_margin_runtime` | `Known` | `Known` |
| `600999.SH` | `L3.product.portfolio` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_VALUE_DIFF` | `script_fill` | `Known` | `Known` |
| `600999.SH` | `L3.region.domestic_overseas` | `analysis` | `False` | `scalar_close` | `A_RULE_ACCEPTABLE` | `script_fill` | `Known` | `Known` |
| `600999.SH` | `L3.region.fx_geo` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Known` |
| `600999.SH` | `L3.region.tier_mix` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `region_mix_runtime` | `Proxy` | `Known` |
| `600999.SH` | `L4.cost.cac_production` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` |
| `600999.SH` | `L4.cost.rent_energy_logistics` | `analysis` | `True` | `b_only` | `A_RULE_NEEDS_REVIEW_OR_FIX` | `gross_margin_proxy` | `Unknown` | `N/A` |
| `600999.SH` | `L4.eff.capacity_utilization` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `capex_ppe_proxy` | `Proxy` | `Unknown` |
| `600999.SH` | `L4.eff.store_labor` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` |
| `600999.SH` | `L4.price.asp_aov_arpu` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` |
| `600999.SH` | `L4.price.discount` | `analysis` | `True` | `b_only` | `A_RULE_NEEDS_REVIEW_OR_FIX` | `gross_margin_proxy` | `Unknown` | `Known` |
| `600999.SH` | `L4.price.elasticity` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `gross_margin_proxy` | `Unknown` | `Unknown` |
| `600999.SH` | `L4.price.pricing_power` | `analysis` | `False` | `b_only` | `A_RULE_NEEDS_REVIEW_OR_FIX` | `gross_margin_proxy` | `Unknown` | `Known` |
| `600999.SH` | `L4.share.market` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `peer_revenue_rank` | `Proxy` | `Known` |
| `600999.SH` | `L4.share.substitution` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` |
| `600999.SH` | `L4.volume.orders` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` |
| `600999.SH` | `L4.volume.sales` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` |
| `600999.SH` | `L4.volume.shipments` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `N/A` |
| `600999.SH` | `L4.volume.users` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `600999.SH` | `L5.fcst.beat_probability` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `forecast_revision_formula` | `Proxy` | `Known` |
| `600999.SH` | `L8.gov.fraud_control` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600999.SH` | `L8.gov.litigation` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600999.SH` | `L8.industry.demand_supply` | `cheap_classify` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `existing_runtime_or_derive` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.industry.price_war` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `existing_runtime_or_derive` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.industry.substitute` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.op.customer_channel` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.op.order_miss` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.op.product_fail` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.reg.license_risk` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.reg.subsidy_off` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600999.SH` | `L8.reg.tax_trade` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600999.SH` | `L8.reg.tighten` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
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
| `600754.SH` | `L2.segment.cash_contrib` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `segment_revenue_share_runtime` | `Proxy` | `Unknown` |
| `600754.SH` | `L2.segment.industry_exposure` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_revenue_share_runtime` | `Proxy` | `Known` |
| `600754.SH` | `L2.segment.opex_ratio` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `company_opex_ratio_runtime` | `Proxy` | `Unknown` |
| `600754.SH` | `L2.segment.profit_share` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `segment_profit_share_runtime` | `Proxy` | `Unknown` |
| `600754.SH` | `L3.channel.cost` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `sga_revenue_ratio` | `Proxy` | `Unknown` |
| `600754.SH` | `L3.channel.efficiency` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_efficiency_formula` | `Proxy` | `Unknown` |
| `600754.SH` | `L3.channel.mix` | `cheap_extract` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `channel_mix_business_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L3.channel.overseas` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `region_mix_runtime` | `Unknown` | `Unknown` |
| `600754.SH` | `L3.customer.concentration` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` |
| `600754.SH` | `L3.customer.solvency` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `ar_revenue_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L3.delivery.capacity_supply` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `capex_ppe_proxy` | `Proxy` | `Known` |
| `600754.SH` | `L3.delivery.fulfillment_cost` | `analysis` | `True` | `scalar_close` | `A_RULE_ACCEPTABLE` | `fulfillment_cost_formula` | `Proxy` | `Known` |
| `600754.SH` | `L3.product.margin_mix` | `analysis` | `False` | `status_match_value_differs` | `MANUAL_REVIEW_PROXY_DIFF` | `segment_gross_margin_runtime` | `Known` | `Known` |
| `600754.SH` | `L3.product.portfolio` | `analysis` | `False` | `b_only` | `A_RULE_NEEDS_REVIEW_OR_FIX` | `no_non_llm_extractor` | `Unknown` | `Known` |
| `600754.SH` | `L3.region.domestic_overseas` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `no_non_llm_extractor` | `Unknown` | `Unknown` |
| `600754.SH` | `L3.region.fx_geo` | `analysis` | `False` | `b_only` | `A_RULE_NEEDS_REVIEW_OR_FIX` | `region_mix_runtime` | `Unknown` | `Known` |
| `600754.SH` | `L3.region.tier_mix` | `analysis` | `False` | `both_missing` | `MANUAL_REVIEW` | `region_mix_runtime` | `Unknown` | `Unknown` |
| `600754.SH` | `L4.cost.cac_production` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` |
| `600754.SH` | `L4.cost.rent_energy_logistics` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Known` |
| `600754.SH` | `L4.eff.capacity_utilization` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `capex_ppe_proxy` | `Proxy` | `Known` |
| `600754.SH` | `L4.eff.store_labor` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `sga_revenue_ratio` | `Proxy` | `Known` |
| `600754.SH` | `L4.price.asp_aov_arpu` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `revenue_growth_proxy` | `Proxy` | `Known` |
| `600754.SH` | `L4.price.discount` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L4.price.elasticity` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `gross_margin_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L4.price.pricing_power` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `gross_margin_proxy` | `Proxy` | `Known` |
| `600754.SH` | `L4.share.market` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `peer_revenue_rank` | `Proxy` | `Unknown` |
| `600754.SH` | `L4.share.substitution` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L4.volume.orders` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L4.volume.sales` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L4.volume.shipments` | `analysis` | `True` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L4.volume.users` | `analysis` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `revenue_growth_proxy` | `Proxy` | `Unknown` |
| `600754.SH` | `L5.fcst.beat_probability` | `analysis` | `True` | `status_diff` | `MANUAL_REVIEW_PROXY_DIFF` | `forecast_revision_formula` | `Proxy` | `Known` |
| `600754.SH` | `L8.gov.fraud_control` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L8.gov.litigation` | `analysis` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L8.industry.demand_supply` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `existing_runtime_or_derive` | `Inactive` | `Known` |
| `600754.SH` | `L8.industry.price_war` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `existing_runtime_or_derive` | `Inactive` | `Unknown` |
| `600754.SH` | `L8.industry.substitute` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600754.SH` | `L8.op.customer_channel` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L8.op.order_miss` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L8.op.product_fail` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L8.reg.license_risk` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600754.SH` | `L8.reg.subsidy_off` | `cheap_classify` | `False` | `a_only` | `A_RULE_ACCEPTABLE_B_MISSING` | `event_keyword_screen` | `Inactive` | `Unknown` |
| `600754.SH` | `L8.reg.tax_trade` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L8.reg.tighten` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L8.shock.crisis` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L8.shock.supply_break` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L9.company.ma` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L9.company.product_order` | `cheap_classify` | `False` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
| `600754.SH` | `L9.media.short_report` | `cheap_classify` | `True` | `status_diff` | `MANUAL_REVIEW` | `event_keyword_screen` | `Inactive` | `Known` |
