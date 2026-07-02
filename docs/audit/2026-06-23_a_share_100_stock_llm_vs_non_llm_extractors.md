# A-share LLM vs non-LLM extractor comparison

- Generated: `2026-06-23T12:17:42+08:00`
- Baseline: `current stock overlay values; no fresh LLM call`
- Non-LLM: `local parser/formula/event-screen candidates only; read-only`
- Stocks: `100`
- Fields: `82` total; non-cheap-extract `76`
- Tier counts: `{'cheap_extract': 6, 'analysis': 50, 'web_analysis': 8, 'cheap_classify': 18}`

## Topline

- Baseline available cells: `6221/8200`
- Non-LLM candidate available cells: `5226/8200` (`0.6373`)
- Non-LLM candidate schema-valid cells: `5226/5226` (`1.0`)
- Score-field non-LLM candidate available cells: `2053/2700` (`0.7604`)
- Score-field schema-invalid candidate cells: `0`
- Fields with at least one non-LLM candidate in this sample: `55`
- Fields not reproduced by this harness yet: `27`
- Of those, extractor/parser gaps: `1`
- Of those, event-review gates: `3`
- Semantic or external-source gated fields: `23`

## Sample

| ts_code | name | industry |
|---|---|---|
| `600754.SH` | 锦江酒店 | `DOMESTIC_CONSUMPTION` |
| `300476.SZ` | 胜宏科技 | `CONSUMER_ELECTRONICS` |
| `000333.SZ` | 美的集团 | `EXPORT_MFG` |
| `300308.SZ` | 中际旭创 | `AI_COMPUTE` |
| `300418.SZ` | 昆仑万维 | `HK_CN_INTERNET` |
| `603256.SH` | 宏和科技 | `SEMI_EQUIPMENT` |
| `000657.SZ` | 中钨高新 | `NONFERROUS_METALS` |
| `600999.SH` | 招商证券 | `FINANCIAL_HIGH_DIVIDEND` |
| `300750.SZ` | 宁德时代 | `STORAGE_GRID` |
| `002008.SZ` | 大族激光 | `ROBOTICS` |
| `300347.SZ` | 泰格医药 | `INNOVATIVE_PHARMA` |
| `600801.SH` | 华新水泥 | `ANTI_INVOLUTION_CYCLICAL` |
| `601888.SH` | 中国中免 | `DOMESTIC_CONSUMPTION` |
| `601111.SH` | 中国国航 | `DOMESTIC_CONSUMPTION` |
| `601688.SH` | 华泰证券 | `FINANCIAL_HIGH_DIVIDEND` |
| `688072.SH` | 拓荆科技 | `SEMI_EQUIPMENT` |
| `000001.SZ` | 平安银行 | `FINANCIAL_HIGH_DIVIDEND` |
| `002460.SZ` | 赣锋锂业 | `NONFERROUS_METALS` |
| `002415.SZ` | 海康威视 | `AI_COMPUTE` |
| `002916.SZ` | 深南电路 | `CONSUMER_ELECTRONICS` |
| `002916.SZ` | 深南电路 | `AI_COMPUTE` |
| `300394.SZ` | 天孚通信 | `AI_COMPUTE` |
| `300502.SZ` | 新易盛 | `AI_COMPUTE` |
| `002281.SZ` | 光迅科技 | `AI_COMPUTE` |
| `601100.SH` | 恒立液压 | `EXPORT_MFG` |
| `688082.SH` | 盛美上海 | `SEMI_EQUIPMENT` |
| `688249.SH` | 晶合集成 | `SEMI_EQUIPMENT` |
| `688256.SH` | 寒武纪 | `AI_COMPUTE` |
| `002463.SZ` | 沪电股份 | `AI_COMPUTE` |
| `002463.SZ` | 沪电股份 | `CONSUMER_ELECTRONICS` |
| `600029.SH` | 南方航空 | `DOMESTIC_CONSUMPTION` |
| `000977.SZ` | 浪潮信息 | `AI_COMPUTE` |
| `688041.SH` | 海光信息 | `AI_COMPUTE` |
| `600547.SH` | 山东黄金 | `NONFERROUS_METALS` |
| `002050.SZ` | 三花智控 | `ROBOTICS` |
| `601899.SH` | 紫金矿业 | `NONFERROUS_METALS` |
| `688498.SH` | 源杰科技 | `SEMI_EQUIPMENT` |
| `688981.SH` | 中芯国际 | `SEMI_EQUIPMENT` |
| `002920.SZ` | 德赛西威 | `EXPORT_MFG` |
| `603799.SH` | 华友钴业 | `NONFERROUS_METALS` |
| `688783.SH` | 西安奕材-U | `SEMI_EQUIPMENT` |
| `002028.SZ` | 思源电气 | `STORAGE_GRID` |
| `300144.SZ` | 宋城演艺 | `DOMESTIC_CONSUMPTION` |
| `601919.SH` | 中远海控 | `DOMESTIC_CONSUMPTION` |
| `600025.SH` | 华能水电 | `FINANCIAL_HIGH_DIVIDEND` |
| `002352.SZ` | 顺丰控股 | `DOMESTIC_CONSUMPTION` |
| `002747.SZ` | 埃斯顿 | `ROBOTICS` |
| `000063.SZ` | 中兴通讯 | `AI_COMPUTE` |
| `002156.SZ` | 通富微电 | `SEMI_EQUIPMENT` |
| `002050.SZ` | 三花智控 | `EXPORT_MFG` |
| `300604.SZ` | 长川科技 | `SEMI_EQUIPMENT` |
| `600938.SH` | 中国海油 | `ANTI_INVOLUTION_CYCLICAL` |
| `603986.SH` | 兆易创新 | `CONSUMER_ELECTRONICS` |
| `688126.SH` | 沪硅产业 | `SEMI_EQUIPMENT` |
| `002624.SZ` | 完美世界 | `HK_CN_INTERNET` |
| `601600.SH` | 中国铝业 | `NONFERROUS_METALS` |
| `600487.SH` | 亨通光电 | `AI_COMPUTE` |
| `600900.SH` | 长江电力 | `FINANCIAL_HIGH_DIVIDEND` |
| `600930.SH` | 华电新能 | `FINANCIAL_HIGH_DIVIDEND` |
| `601816.SH` | 京沪高铁 | `DOMESTIC_CONSUMPTION` |
| `600690.SH` | 海尔智家 | `EXPORT_MFG` |
| `000932.SZ` | 华菱钢铁 | `ANTI_INVOLUTION_CYCLICAL` |
| `688235.SH` | 百济神州 | `INNOVATIVE_PHARMA` |
| `002466.SZ` | 天齐锂业 | `NONFERROUS_METALS` |
| `002475.SZ` | 立讯精密 | `CONSUMER_ELECTRONICS` |
| `688111.SH` | 金山办公 | `HK_CN_INTERNET` |
| `002555.SZ` | 三七互娱 | `HK_CN_INTERNET` |
| `003816.SZ` | 中国广核 | `FINANCIAL_HIGH_DIVIDEND` |
| `001289.SZ` | 龙源电力 | `FINANCIAL_HIGH_DIVIDEND` |
| `603728.SH` | 鸣志电器 | `ROBOTICS` |
| `688808.SH` | 联讯仪器 | `ROBOTICS` |
| `002230.SZ` | 科大讯飞 | `HK_CN_INTERNET` |
| `600406.SH` | 国电南瑞 | `STORAGE_GRID` |
| `601138.SH` | 工业富联 | `AI_COMPUTE` |
| `600019.SH` | 宝钢股份 | `ANTI_INVOLUTION_CYCLICAL` |
| `600309.SH` | 万华化学 | `ANTI_INVOLUTION_CYCLICAL` |
| `603993.SH` | 洛阳钼业 | `NONFERROUS_METALS` |
| `600176.SH` | 中国巨石 | `ANTI_INVOLUTION_CYCLICAL` |
| `000400.SZ` | 许继电气 | `STORAGE_GRID` |
| `601088.SH` | 中国神华 | `FINANCIAL_HIGH_DIVIDEND` |
| `600941.SH` | XD中国移 | `AI_COMPUTE` |
| `688017.SH` | 绿的谐波 | `ROBOTICS` |
| `601288.SH` | 农业银行 | `FINANCIAL_HIGH_DIVIDEND` |
| `600028.SH` | 中国石化 | `ANTI_INVOLUTION_CYCLICAL` |
| `601939.SH` | 建设银行 | `FINANCIAL_HIGH_DIVIDEND` |
| `688820.SH` | 盛合晶微 | `SEMI_EQUIPMENT` |
| `600584.SH` | 长电科技 | `SEMI_EQUIPMENT` |
| `600188.SH` | 兖矿能源 | `FINANCIAL_HIGH_DIVIDEND` |
| `600989.SH` | 宝丰能源 | `ANTI_INVOLUTION_CYCLICAL` |
| `601857.SH` | 中国石油 | `ANTI_INVOLUTION_CYCLICAL` |
| `688347.SH` | 华虹公司 | `SEMI_EQUIPMENT` |
| `300073.SZ` | 当升科技 | `STORAGE_GRID` |
| `601601.SH` | 中国太保 | `FINANCIAL_HIGH_DIVIDEND` |
| `688795.SH` | 摩尔线程-U | `SEMI_EQUIPMENT` |
| `600362.SH` | 江西铜业 | `NONFERROUS_METALS` |
| `600489.SH` | 中金黄金 | `NONFERROUS_METALS` |
| `601991.SH` | 大唐发电 | `FINANCIAL_HIGH_DIVIDEND` |
| `603501.SH` | 韦尔股份 | `CONSUMER_ELECTRONICS` |
| `603893.SH` | 瑞芯微 | `SEMI_EQUIPMENT` |
| `300759.SZ` | 康龙化成 | `INNOVATIVE_PHARMA` |

## Comparison Buckets

| bucket | cells |
|---|---:|
| `both_available` | 2807 |
| `non_llm_missing_llm_available:gated` | 2216 |
| `non_llm_found_baseline_missing` | 1467 |
| `status_match_value_differs` | 930 |
| `both_missing:gated` | 395 |
| `non_llm_missing_llm_available` | 246 |
| `both_missing` | 117 |
| `status_and_value_close` | 22 |

## Candidate Categories

| category | cells |
|---|---:|
| `formula_proxy` | 2194 |
| `keep_llm_for_now` | 1500 |
| `event_policy` | 1489 |
| `web_or_external` | 800 |
| `parser_formula_first` | 743 |
| `cheap_extract_rule` | 400 |
| `event_policy_gated` | 311 |
| `existing_deterministic_parser` | 204 |
| `strict_no_llm_now` | 200 |
| `unclassified` | 159 |
| `cheap_extract_formula` | 100 |
| `cheap_extract_parser` | 100 |

## Field Summary

| dp_id | tier | score | baseline avail | non-LLM avail | close | missing vs baseline | top methods |
|---|---|---:|---:|---:|---:|---:|---|
| `L1.moat.tags` | `cheap_extract` | `False` | 100 | 100 | 0 | 0 | rule_tagging:100 |
| `L1.model.tag` | `cheap_extract` | `False` | 100 | 100 | 0 | 0 | rule_tagging:100 |
| `L1.position.brand` | `analysis` | `False` | 100 | 0 | 0 | 100 | semantic_review_required:100 |
| `L1.position.channel_edge` | `analysis` | `False` | 91 | 0 | 0 | 91 | semantic_review_required:100 |
| `L1.position.cost_edge` | `analysis` | `False` | 97 | 0 | 0 | 97 | semantic_review_required:100 |
| `L1.position.growth_rank` | `cheap_extract` | `True` | 100 | 100 | 0 | 0 | peer_growth_rank:100 |
| `L1.position.market_share` | `analysis` | `True` | 70 | 100 | 0 | 0 | peer_revenue_rank:100 |
| `L1.position.pricing_power` | `analysis` | `False` | 99 | 0 | 0 | 99 | semantic_review_required:100 |
| `L1.position.stickiness` | `analysis` | `False` | 81 | 0 | 0 | 81 | semantic_review_required:100 |
| `L1.position.tech_barrier` | `analysis` | `False` | 100 | 0 | 0 | 100 | semantic_review_required:100 |
| `L1.role.tag` | `cheap_extract` | `False` | 100 | 100 | 0 | 0 | rule_tagging:100 |
| `L1.stock_attr.tags` | `cheap_extract` | `False` | 100 | 100 | 0 | 0 | rule_tagging:100 |
| `L2.newbiz.commercialization` | `analysis` | `False` | 100 | 0 | 0 | 100 | semantic_review_required:100 |
| `L2.newbiz.revenue_contrib` | `analysis` | `False` | 100 | 0 | 0 | 100 | semantic_review_required:100 |
| `L2.newbiz.tam` | `web_analysis` | `False` | 100 | 0 | 0 | 100 | external_source_required:100 |
| `L2.newbiz.uncertainty` | `analysis` | `True` | 100 | 0 | 0 | 100 | semantic_review_required:100 |
| `L2.newbiz.valuation_contrib` | `analysis` | `False` | 100 | 0 | 0 | 100 | semantic_review_required:100 |
| `L2.segment.business_risk` | `analysis` | `False` | 100 | 0 | 0 | 100 | semantic_review_required:100 |
| `L2.segment.cash_contrib` | `analysis` | `False` | 100 | 100 | 0 | 0 | segment_revenue_share_runtime:100 |
| `L2.segment.compete_landscape` | `analysis` | `False` | 92 | 0 | 0 | 92 | semantic_review_required:100 |
| `L2.segment.industry_exposure` | `analysis` | `False` | 100 | 100 | 0 | 0 | segment_revenue_share_runtime:100 |
| `L2.segment.opex_ratio` | `analysis` | `False` | 100 | 100 | 0 | 0 | company_opex_ratio_runtime:100 |
| `L2.segment.profit_share` | `analysis` | `False` | 100 | 90 | 0 | 10 | segment_profit_share_runtime:100 |
| `L3.channel.cost` | `analysis` | `True` | 100 | 100 | 0 | 0 | sga_revenue_ratio:100 |
| `L3.channel.efficiency` | `analysis` | `True` | 90 | 100 | 0 | 0 | channel_efficiency_formula:100 |
| `L3.channel.mix` | `cheap_extract` | `True` | 88 | 100 | 0 | 0 | channel_mix_business_proxy:100 |
| `L3.channel.overseas` | `analysis` | `False` | 57 | 84 | 0 | 10 | region_mix_runtime:100 |
| `L3.customer.concentration` | `analysis` | `False` | 59 | 38 | 0 | 21 | no_non_llm_extractor:62, script_fill:38 |
| `L3.customer.segment_mix` | `analysis` | `False` | 95 | 0 | 0 | 95 | no_non_llm_extractor:57, parser_todo_source_present:43 |
| `L3.customer.solvency` | `analysis` | `False` | 91 | 94 | 0 | 1 | ar_revenue_proxy:94, no_non_llm_extractor:6 |
| `L3.delivery.capacity_supply` | `analysis` | `False` | 72 | 66 | 0 | 24 | capex_ppe_proxy:100 |
| `L3.delivery.csat` | `web_analysis` | `False` | 11 | 0 | 0 | 11 | external_source_required:100 |
| `L3.delivery.fulfillment_cost` | `analysis` | `True` | 98 | 100 | 0 | 0 | fulfillment_cost_formula:100 |
| `L3.delivery.lead_time` | `web_analysis` | `False` | 26 | 0 | 0 | 26 | external_source_required:100 |
| `L3.product.lifecycle` | `web_analysis` | `False` | 100 | 0 | 0 | 100 | external_source_required:100 |
| `L3.product.margin_mix` | `analysis` | `False` | 97 | 90 | 0 | 7 | segment_gross_margin_runtime:100 |
| `L3.product.portfolio` | `analysis` | `False` | 100 | 82 | 0 | 18 | script_fill:82, no_non_llm_extractor:18 |
| `L3.region.domestic_overseas` | `analysis` | `False` | 84 | 84 | 22 | 13 | script_fill:84, no_non_llm_extractor:16 |
| `L3.region.fx_geo` | `analysis` | `False` | 100 | 84 | 0 | 16 | region_mix_runtime:100 |
| `L3.region.key_risk` | `analysis` | `False` | 66 | 0 | 0 | 66 | semantic_review_required:100 |
| `L3.region.tier_mix` | `analysis` | `False` | 77 | 84 | 0 | 11 | region_mix_runtime:100 |
| `L4.cost.cac_production` | `analysis` | `True` | 100 | 100 | 0 | 0 | sga_revenue_ratio:100 |
| `L4.cost.rent_energy_logistics` | `analysis` | `True` | 76 | 94 | 0 | 5 | gross_margin_proxy:100 |
| `L4.eff.capacity_utilization` | `analysis` | `True` | 22 | 66 | 0 | 6 | capex_ppe_proxy:100 |
| `L4.eff.conversion_retention` | `web_analysis` | `True` | 73 | 0 | 0 | 73 | external_source_required:100 |
| `L4.eff.store_labor` | `analysis` | `False` | 84 | 100 | 0 | 0 | sga_revenue_ratio:100 |
| `L4.price.asp_aov_arpu` | `analysis` | `True` | 27 | 100 | 0 | 0 | revenue_growth_proxy:100 |
| `L4.price.discount` | `analysis` | `True` | 72 | 94 | 0 | 3 | gross_margin_proxy:100 |
| `L4.price.elasticity` | `analysis` | `False` | 26 | 94 | 0 | 0 | gross_margin_proxy:100 |
| `L4.price.pricing_power` | `analysis` | `False` | 99 | 94 | 0 | 5 | gross_margin_proxy:100 |
| `L4.price.subscription` | `analysis` | `True` | 98 | 0 | 0 | 98 | semantic_review_required:100 |
| `L4.share.customer_channel` | `web_analysis` | `True` | 25 | 0 | 0 | 25 | external_source_required:100 |
| `L4.share.market` | `analysis` | `True` | 63 | 100 | 0 | 0 | peer_revenue_rank:100 |
| `L4.share.substitution` | `analysis` | `True` | 100 | 100 | 0 | 0 | revenue_growth_proxy:100 |
| `L4.volume.foot_traffic` | `web_analysis` | `True` | 95 | 0 | 0 | 95 | external_source_required:100 |
| `L4.volume.frequency` | `web_analysis` | `False` | 64 | 0 | 0 | 64 | external_source_required:100 |
| `L4.volume.orders` | `analysis` | `True` | 36 | 100 | 0 | 0 | revenue_growth_proxy:100 |
| `L4.volume.sales` | `analysis` | `True` | 55 | 100 | 0 | 0 | revenue_growth_proxy:100 |
| `L4.volume.shipments` | `analysis` | `True` | 38 | 100 | 0 | 0 | revenue_growth_proxy:100 |
| `L4.volume.users` | `analysis` | `False` | 46 | 100 | 0 | 0 | revenue_growth_proxy:100 |
| `L5.fcst.beat_probability` | `analysis` | `True` | 100 | 99 | 0 | 1 | forecast_revision_formula:100 |
| `L5.surprise.buy_whisper` | `analysis` | `False` | 87 | 0 | 0 | 87 | semantic_review_required:100 |
| `L8.gov.fraud_control` | `analysis` | `False` | 100 | 100 | 0 | 0 | event_keyword_screen:100 |
| `L8.gov.litigation` | `analysis` | `False` | 100 | 89 | 0 | 11 | event_keyword_screen:100 |
| `L8.industry.demand_supply` | `cheap_classify` | `True` | 41 | 100 | 0 | 0 | existing_runtime_or_derive:100 |
| `L8.industry.price_war` | `cheap_classify` | `False` | 17 | 100 | 0 | 0 | existing_runtime_or_derive:100 |
| `L8.industry.substitute` | `cheap_classify` | `False` | 17 | 100 | 0 | 0 | event_keyword_screen:100 |
| `L8.op.customer_channel` | `cheap_classify` | `False` | 27 | 100 | 0 | 0 | event_keyword_screen:100 |
| `L8.op.order_miss` | `cheap_classify` | `False` | 36 | 100 | 0 | 0 | event_keyword_screen:100 |
| `L8.op.product_fail` | `cheap_classify` | `False` | 7 | 100 | 0 | 0 | event_keyword_screen:100 |
| `L8.reg.license_risk` | `cheap_classify` | `False` | 9 | 100 | 0 | 0 | event_keyword_screen:100 |
| `L8.reg.subsidy_off` | `cheap_classify` | `False` | 11 | 100 | 0 | 0 | event_keyword_screen:100 |
| `L8.reg.tax_trade` | `cheap_classify` | `False` | 21 | 100 | 0 | 0 | event_keyword_screen:100 |
| `L8.reg.tighten` | `cheap_classify` | `False` | 8 | 100 | 0 | 0 | event_keyword_screen:100 |
| `L8.shock.black_swan` | `cheap_classify` | `True` | 100 | 0 | 0 | 100 | event_keyword_screen:100 |
| `L8.shock.crisis` | `cheap_classify` | `True` | 100 | 100 | 0 | 0 | event_keyword_screen:100 |
| `L8.shock.supply_break` | `cheap_classify` | `True` | 100 | 100 | 0 | 0 | event_keyword_screen:100 |
| `L9.company.ma` | `cheap_classify` | `False` | 100 | 100 | 0 | 0 | event_keyword_screen:100 |
| `L9.company.product_order` | `cheap_classify` | `False` | 100 | 100 | 0 | 0 | event_keyword_screen:100 |
| `L9.industry.data_price` | `cheap_classify` | `False` | 100 | 0 | 0 | 100 | event_keyword_screen:100 |
| `L9.macro.geo` | `cheap_classify` | `False` | 100 | 0 | 0 | 100 | event_keyword_screen:100 |
| `L9.media.short_report` | `cheap_classify` | `True` | 100 | 100 | 0 | 0 | event_keyword_screen:100 |

## Interpretation

- `status_and_value_close` is strong evidence that the local candidate matches the current overlay baseline.
- `non_llm_missing_llm_available` means the current harness cannot reproduce a baseline value; it is not yet proof that LLM is mandatory.
- `*:gated` means deterministic logic can screen or package evidence, but Known writes still need LLM/human or connector review.
- Web-analysis fields are treated as connector gaps, not prompt-quality gaps.
