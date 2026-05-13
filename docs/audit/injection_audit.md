# Injection Audit Report

> 三层数据架构覆盖度：overlay (LLM 衍生 schema, per-stock) + realtime (Tushare/FMP/Futu/akshare 灌入, per-stock) + L0 inherit (行业 overlay 共享, per-industry)。
> Spec 总 dp_id 数 = **250**（来源：`docs/data_sources/coverage_audit.md` § 7）。

## Summary

- Total companies: **328**
- Average effective dp_ids: **72.8 / 250** = **29.1%**
- Per-layer averages:
  - overlay Known: **1.0** (LLM/codex 填; per-stock)
  - overlay Optionality: **5.0**
  - realtime injected: **66.8** (Tushare/FMP/Futu/akshare)
  - L0 inherit (Known industry rows): **0.0**
- With ≥1 realtime value: **328** / with zero: **0**

| Market | Total | With realtime | Coverage |
|---|---:|---:|---:|
| A | 116 | 116 | 100% |
| HK | 97 | 97 | 100% |
| US | 115 | 115 | 100% |

## Coverage Distribution

- effective ≥ 50: **231** stocks
- effective 40–49: **0**
- effective 30–39: **97**
- effective 20–29: **0**
- effective < 20: **0**

## Per-Industry Aggregates

| Industry | Stocks | overlay K avg | overlay Opt avg | realtime avg | L0 inherit | effective avg | best (ts, eff) | worst (ts, eff) |
|---|---:|---:|---:|---:|---:|---:|---|---|
| AI_COMPUTE | 32 | 1.0 | 5.0 | 68.1 | 0.0 | 74.1 | `000063.SZ` (105) | `00728.HK` (39) |
| ANTI_INVOLUTION_CYCLICAL | 29 | 1.0 | 5.0 | 66.1 | 0.0 | 72.1 | `002648.SZ` (103) | `00323.HK` (38) |
| CONSUMER_ELECTRONICS | 23 | 1.0 | 5.0 | 72.2 | 0.0 | 78.2 | `002384.SZ` (103) | `00285.HK` (38) |
| DOMESTIC_CONSUMPTION | 33 | 1.0 | 5.0 | 65.0 | 0.0 | 71.0 | `300144.SZ` (102) | `00027.HK` (38) |
| EXPORT_MFG | 23 | 1.0 | 5.0 | 66.4 | 0.0 | 72.4 | `000333.SZ` (102) | `00175.HK` (38) |
| FINANCIAL_HIGH_DIVIDEND | 30 | 1.0 | 5.0 | 64.6 | 0.0 | 70.6 | `600900.SH` (102) | `00005.HK` (38) |
| HK_CN_INTERNET | 25 | 1.0 | 5.0 | 63.7 | 0.0 | 69.7 | `002230.SZ` (102) | `00700.HK` (38) |
| INNOVATIVE_PHARMA | 29 | 1.0 | 5.0 | 63.8 | 0.0 | 69.8 | `603259.SH` (103) | `01093.HK` (38) |
| NONFERROUS_METALS | 30 | 1.0 | 5.0 | 65.0 | 0.0 | 71.0 | `601899.SH` (103) | `00358.HK` (38) |
| ROBOTICS | 24 | 1.0 | 5.0 | 68.8 | 0.0 | 74.8 | `002008.SZ` (104) | `00300.HK` (38) |
| SEMI_EQUIPMENT | 22 | 1.0 | 5.0 | 74.1 | 0.0 | 80.1 | `002156.SZ` (102) | `00522.HK` (39) |
| STORAGE_GRID | 28 | 1.0 | 5.0 | 66.1 | 0.0 | 72.1 | `300750.SZ` (106) | `00819.HK` (38) |

## Top sources contributing realtime dp_ids

| source | total rows | unique dp_ids | example dp_id |
|---|---:|---:|---|
| `tushare:fina_indicator` | 1832 | 16 | `L5.fina.asset_turnover` |
| `derive:bootstrap_l11_subscore` | 3608 | 11 | `L11.long.business_model` |
| `fmp:income-statement` | 1033 | 9 | `L5.is.cogs` |
| `tushare:income` | 579 | 5 | `L5.is.eps` |
| `fmp:ratios-ttm` | 575 | 5 | `L6.mult.mcap_fcf` |
| `fmp:cash-flow` | 575 | 5 | `L5.cf.buyback_dividend` |
| `tushare:income.derived` | 564 | 5 | `L4.cost.raw_material` |
| `tushare:cashflow` | 563 | 5 | `L5.cf.buyback_dividend` |
| `tushare:daily_basic` | 460 | 4 | `L6.mult.pb` |
| `fmp:balance-sheet` | 460 | 4 | `L5.bs.ar_ap` |
| `tushare:balancesheet` | 431 | 4 | `L5.bs.ar_ap` |
| `futu:snapshot` | 406 | 3 | `L6.mult.pb` |
| `tushare:stk_holdertrade` | 348 | 3 | `L9.event.holder_trade_signal` |
| `akshare:stock_info_global_cls` | 3 | 3 | `L9.industry.compete_risk` |
| `tushare:balancesheet+income.derived` | 232 | 2 | `L4.eff.cycle` |
| `tushare:balancesheet+fina_indicator.derived` | 232 | 2 | `L8.fin.debt_pressure` |
| `fmp:analyst-estimates.derived` | 230 | 2 | `L5.fcst.revisions` |
| `fmp:analyst-estimates` | 230 | 2 | `L5.fcst.eps_cf` |
| `tushare:stk_managers` | 119 | 2 | `L8.gov.management_table` |
| `tushare:shibor_lpr` | 2 | 2 | `L7.env.rates` |
| `tushare:cn_m` | 2 | 2 | `L7.env.liquidity` |
| `derive:l8_val_priced_in` | 328 | 1 | `L8.val.priced_in` |
| `derive:l8_industry_price_war` | 328 | 1 | `L8.industry.price_war` |
| `derive:l8_industry_demand_supply` | 328 | 1 | `L8.industry.demand_supply` |
| `derive:l7_mood_fomo` | 328 | 1 | `L7.mood.fomo` |
| `derive:l7_env_risk_appetite` | 328 | 1 | `L7.env.risk_appetite` |
| `derive:l6_sens_risk_narrative` | 328 | 1 | `L6.sens.risk_narrative` |
| `derive:l6_sens_rates` | 328 | 1 | `L6.sens.rates` |
| `derive:l6_sens_growth_margin` | 328 | 1 | `L6.sens.growth_margin` |
| `derive:l6_sens_cashflow` | 328 | 1 | `L6.sens.cashflow` |
| `derive:l6_path_tag` | 328 | 1 | `L6.path.tag` |
| `derive:l6_path_second_derivative` | 328 | 1 | `L6.path.second_derivative` |
| `derive:l11_trade_signal` | 328 | 1 | `L11.trade.signal` |
| `derive:l11_short_score` | 328 | 1 | `L11.short.score` |
| `derive:l11_mode` | 328 | 1 | `L11.mode` |
| `derive:l11_mid_score` | 328 | 1 | `L11.mid.score` |
| `derive:l11_long_score` | 328 | 1 | `L11.long.score` |
| `derive:l10_val_expansion_compression` | 328 | 1 | `L10.val.expansion_compression` |
| `futu` | 212 | 1 | `L7.market.l2_quote` |
| `tushare:stk_managers|alias→L8.gov.management_change` | 116 | 1 | `L8.gov.management_change` |
| `tushare:stk_holdertrade|alias→L8.gov.insider_sell` | 116 | 1 | `L8.gov.insider_sell` |
| `tushare:report_rc` | 116 | 1 | `L5.surprise.sell_side` |
| `tushare:moneyflow` | 116 | 1 | `L7.flow.active_inflow` |
| `tushare:margin_detail` | 116 | 1 | `L7.trade.margin_short` |
| `tushare:forecast` | 116 | 1 | `L9.company.earnings_guidance` |
| `tushare:dividend` | 116 | 1 | `L9.company.buyback_dividend` |
| `tushare:daily_basic.history` | 116 | 1 | `L6.state.historical_percentile` |
| `tushare:cashflow+income.derived` | 116 | 1 | `L4.cost.labor` |
| `tushare:cashflow+income+balancesheet.derived` | 116 | 1 | `L8.fin.cash_ar` |
| `tushare:balancesheet.derived` | 116 | 1 | `L5.bs.leverage` |
| `derived:turnover_history` | 116 | 1 | `L6.priced.crowdedness` |
| `derived:price_history` | 116 | 1 | `L6.priced.run_up` |
| `derived:pe_pb_history` | 116 | 1 | `L10.val.historical_quantile` |
| `derived:from_quantile` | 116 | 1 | `L8.val.overvalued` |
| `akshare:xq_hot` | 116 | 1 | `L9.media.social_buzz` |
| `akshare:stock_individual_notice_report` | 116 | 1 | `L9.event.intraday_announcement` |
| `akshare:stock_hot_rank_em+keyword` | 116 | 1 | `L7.mood.media_social` |
| `akshare:stock_hot_keyword_em` | 116 | 1 | `L7.mood.theme` |
| `akshare:em_news` | 116 | 1 | `L9.event.intraday_news` |
| `fmp:sec-filings` | 115 | 1 | `L9.event.recent_filings` |
| `fmp:news.derived` | 115 | 1 | `L6.priced.news_age` |
| `fmp:news` | 115 | 1 | `L9.event.news_flow` |
| `fmp:key-metrics-ttm` | 115 | 1 | `L6.mult.ev_ebitda` |
| `fmp:insider-trading` | 115 | 1 | `L9.event.insider_trades` |
| `fmp:financial-growth` | 115 | 1 | `L5.is.revenue_growth` |
| `fmp:earnings.derived` | 115 | 1 | `L5.surprise.preprice` |
| `fmp:discounted-cash-flow` | 115 | 1 | `L6.mult.dcf` |
| `fmp:beneficial-ownership` | 115 | 1 | `L7.holders.institutional` |
| `fmp:balance-sheet.derived` | 115 | 1 | `L5.bs.leverage` |
| `tushare:daily_basic+cashflow` | 108 | 1 | `L6.mult.mcap_fcf` |
| `futu:capital_flow` | 30 | 1 | `L7.flow.active_inflow` |
| `tushare:block_trade` | 13 | 1 | `L7.flow.block_trade` |
| `akshare:stock_board_industry_summary_ths` | 9 | 1 | `L0.sentiment.sector_heat` |
| `tushare:moneyflow_ind_ths` | 8 | 1 | `L10.industry.fund_flow` |
| `akshare:futures_main_sina` | 7 | 1 | `L0.cost.raw_material` |
| `tushare:top_list` | 3 | 1 | `L9.capital.inst_buy_sell` |
| `tushare:stock_company` | 3 | 1 | `L1.company.main_business` |
| `tushare:irm_qa_sz` | 2 | 1 | `L9.disclosure.qa_recent` |
| `tushare:top_list|alias→L7.flow.institutional` | 1 | 1 | `L7.flow.institutional` |
| `tushare:moneyflow_hsgt` | 1 | 1 | `L7.flow.passive_northbound` |
| `tushare:irm_qa_sh` | 1 | 1 | `L9.disclosure.qa_recent` |
| `tushare:fund_share` | 1 | 1 | `L7.flow.etf_inflow` |
| `tushare:daily_basic.cross_section` | 1 | 1 | `L10.val.historical_quantile` |
| `tushare:cn_pmi` | 1 | 1 | `L10.industry.pmi` |
| `tushare:cn_cpi+cn_ppi` | 1 | 1 | `L9.macro.cpi_employment` |
| `fmp:treasury.derived` | 1 | 1 | `L9.macro.rates` |
| `fmp:treasury` | 1 | 1 | `L7.env.rates` |
| `fmp:quote.derived` | 1 | 1 | `L7.env.style` |
| `fmp:historical-price-eod.derived` | 1 | 1 | `L9.macro.fx` |
| `fmp:historical-price-eod` | 1 | 1 | `L7.env.fx` |
| `fmp:historical-index` | 1 | 1 | `L7.env.market_trend` |
| `fmp:economic-calendar` | 1 | 1 | `L9.macro.cpi_employment` |
| `akshare:futures_main_sina+macro_shipping_bdi` | 1 | 1 | `L0.cost.energy_logistics` |

## Layer 1: overlay schema dp_ids (59 unique across all companies)

LLM-derived slots — codex fills these; data sources cannot. Each company has ~33 of these in its primary overlay.

- `L0.compete.new_entrant`
- `L0.compete.price_war`
- `L0.cost.cac`
- `L0.cost.rent`
- `L0.demand.frequency`
- `L0.demand.penetration`
- `L0.demand.replacement`
- `L0.demand.terminal`
- `L0.demand.user_count`
- `L0.price.contract_spot`
- `L0.price.discount`
- `L0.price.pricing_power`
- `L0.price.product_asp`
- `L0.sentiment.social`
- `L0.supply.capacity`
- `L0.supply.chain_eff`
- `L0.supply.channel_service`
- `L0.supply.inventory`
- `L1.position.brand`
- `L1.position.channel_edge`
- `L1.position.cost_edge`
- `L1.position.market_share`
- `L1.position.pricing_power`
- `L1.position.stickiness`
- `L1.position.tech_barrier`
- `L2.newbiz.commercialization`
- `L2.newbiz.revenue_contrib`
- `L2.newbiz.tam`
- `L2.newbiz.uncertainty`
- `L2.newbiz.valuation_contrib`
- `L2.segment.business_risk`
- `L2.segment.cash_contrib`
- `L2.segment.compete_landscape`
- `L2.segment.industry_exposure`
- `L3.channel.mix`
- `L3.channel.overseas`
- `L3.customer.segment_mix`
- `L3.customer.solvency`
- `L3.delivery.capacity_supply`
- `L3.delivery.csat`
- `L3.delivery.lead_time`
- `L3.product.lifecycle`
- `L3.region.key_risk`
- `L3.region.tier_mix`
- `L4.cost.cac_production`
- `L4.cost.rent_energy_logistics`
- `L4.eff.capacity_utilization`
- `L4.eff.conversion_retention`
- `L4.eff.store_labor`
- `L4.price.asp_aov_arpu`
- `L4.price.discount`
- `L4.price.elasticity`
- `L4.price.pricing_power`
- `L4.price.subscription`
- `L4.share.customer_channel`
- `L4.volume.foot_traffic`
- `L4.volume.frequency`
- `L5.surprise.buy_whisper`
- `company`

## Layer 2: realtime dp_ids (116 unique across all companies)

Data points actually written by collector (`realtime_current`). Exposed via the `realtime` field of `/api/project-ult/stock-overlay`.

- `L1.company.main_business`
- `L10.val.expansion_compression`
- `L10.val.historical_quantile`
- `L11.long.business_model`
- `L11.long.compete_moat`
- `L11.long.industry_space`
- `L11.long.margin`
- `L11.long.score`
- `L11.mid.eps_upward`
- `L11.mid.margin_guidance`
- `L11.mid.orders_revenue`
- `L11.mid.score`
- `L11.mode`
- `L11.short.event_impact`
- `L11.short.flow_boost`
- `L11.short.score`
- `L11.short.sentiment_shift`
- `L11.short.technical`
- `L11.trade.signal`
- `L4.cost.labor`
- `L4.cost.raw_material`
- `L4.eff.cycle`
- `L4.eff.turnover`
- `L5.bs.ar_ap`
- `L5.bs.cash_debt`
- `L5.bs.goodwill_ppe`
- `L5.bs.inventory`
- `L5.bs.leverage`
- `L5.cf.buyback_dividend`
- `L5.cf.capex`
- `L5.cf.fcf`
- `L5.cf.icf_fcf`
- `L5.cf.ocf`
- `L5.fcst.eps_cf`
- `L5.fcst.revenue_margin`
- `L5.fcst.revisions`
- `L5.fina.asset_turnover`
- `L5.fina.bps`
- `L5.fina.cfps`
- `L5.fina.debt_ratio`
- `L5.fina.eps`
- `L5.fina.gross_margin`
- `L5.fina.net_margin`
- `L5.fina.net_profit_yoy`
- `L5.fina.ocf_quality`
- `L5.fina.profit_yoy_q`
- `L5.fina.revenue_yoy`
- `L5.fina.revenue_yoy_q`
- `L5.fina.roa`
- `L5.fina.roe`
- `L5.fina.total_revenue_yoy`
- `L5.fina.working_capital`
- `L5.is.cogs`
- `L5.is.eps`
- `L5.is.gross_margin`
- `L5.is.gross_profit`
- `L5.is.margins`
- `L5.is.net_profit`
- `L5.is.operating_profit`
- `L5.is.revenue`
- `L5.is.revenue_growth`
- `L5.is.sga_rd`
- `L5.surprise.preprice`
- `L5.surprise.sell_side`
- `L6.mult.dcf`
- `L6.mult.ev_ebitda`
- `L6.mult.mcap_fcf`
- `L6.mult.pb`
- `L6.mult.pe`
- `L6.mult.peg`
- `L6.mult.ps`
- `L6.path.second_derivative`
- `L6.path.tag`
- `L6.priced.crowdedness`
- `L6.priced.news_age`
- `L6.priced.run_up`
- `L6.sens.cashflow`
- `L6.sens.growth_margin`
- `L6.sens.rates`
- `L6.sens.risk_narrative`
- `L6.state.historical_percentile`
- `L7.env.risk_appetite`
- `L7.flow.active_inflow`
- `L7.flow.block_trade`
- `L7.flow.institutional`
- `L7.holders.institutional`
- `L7.market.l2_quote`
- `L7.mood.fomo`
- `L7.mood.media_social`
- `L7.mood.theme`
- `L7.trade.margin_short`
- `L7.trade.volume_turnover`
- `L8.fin.cash_ar`
- `L8.fin.debt_pressure`
- `L8.gov.insider_sell`
- `L8.gov.management_change`
- `L8.gov.management_table`
- `L8.industry.demand_supply`
- `L8.industry.price_war`
- `L8.op.inventory_glut`
- `L8.val.overvalued`
- `L8.val.priced_in`
- `L9.capital.inst_buy_sell`
- `L9.company.buyback_dividend`
- `L9.company.earnings_guidance`
- `L9.company.mgmt_litigation`
- `L9.disclosure.qa_recent`
- `L9.event.holder_trade_signal`
- `L9.event.insider_trades`
- `L9.event.intraday_announcement`
- `L9.event.intraday_news`
- `L9.event.major_holder_decrease`
- `L9.event.major_holder_increase`
- `L9.event.news_flow`
- `L9.event.recent_filings`
- `L9.media.social_buzz`

## Layer 3: L0 inherit dp_ids (0 unique across all industries)

`Known` industry-level rows from `config/industry_overlays/*.yaml`. Shared by every stock in an industry; not stored per-company.


## Per-Stock Detail

| ts_code | name | market | industry | overlay K | overlay Opt | realtime | L0 inh | effective | spec % |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| `00005.HK` | 汇丰控股 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `000063.SZ` | 中兴通讯 | A | AI_COMPUTE | 1 | 5 | 99 | 0 | 105 | 42.0% |
| `00027.HK` | 银河娱乐 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `000333.SZ` | 美的集团 | A | EXPORT_MFG | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `000400.SZ` | 许继电气 | A | STORAGE_GRID | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `000425.SZ` | 徐工机械 | A | EXPORT_MFG | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `000651.SZ` | 格力电器 | A | EXPORT_MFG | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `000725.SZ` | 京东方A | A | CONSUMER_ELECTRONICS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `000786.SZ` | 北新建材 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `000932.SZ` | 华菱钢铁 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `000977.SZ` | 浪潮信息 | A | AI_COMPUTE | 1 | 5 | 97 | 0 | 103 | 41.2% |
| `00175.HK` | 吉利汽车 | HK | EXPORT_MFG | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `002008.SZ` | 大族激光 | A | ROBOTICS | 1 | 5 | 98 | 0 | 104 | 41.6% |
| `002050.SZ` | 三花智控 | A | ROBOTICS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `002074.SZ` | 国轩高科 | A | STORAGE_GRID | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `002126.SZ` | 银轮股份 | A | EXPORT_MFG | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `002156.SZ` | 通富微电 | A | SEMI_EQUIPMENT | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `002230.SZ` | 科大讯飞 | A | HK_CN_INTERNET | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `002241.SZ` | 歌尔股份 | A | CONSUMER_ELECTRONICS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `002371.SZ` | 北方华创 | A | SEMI_EQUIPMENT | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `002384.SZ` | 东山精密 | A | CONSUMER_ELECTRONICS | 1 | 5 | 97 | 0 | 103 | 41.2% |
| `002409.SZ` | 雅克科技 | A | SEMI_EQUIPMENT | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `002460.SZ` | 赣锋锂业 | A | NONFERROUS_METALS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `002463.SZ` | 沪电股份 | A | AI_COMPUTE | 1 | 5 | 97 | 0 | 103 | 41.2% |
| `002466.SZ` | 天齐锂业 | A | NONFERROUS_METALS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `002472.SZ` | 双环传动 | A | ROBOTICS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `002475.SZ` | 立讯精密 | A | CONSUMER_ELECTRONICS | 1 | 5 | 97 | 0 | 103 | 41.2% |
| `002555.SZ` | 三七互娱 | A | HK_CN_INTERNET | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `002594.SZ` | 比亚迪 | A | STORAGE_GRID | 1 | 5 | 97 | 0 | 103 | 41.2% |
| `002624.SZ` | 完美世界 | A | HK_CN_INTERNET | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `002648.SZ` | 卫星化学 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 97 | 0 | 103 | 41.2% |
| `002747.SZ` | 埃斯顿 | A | ROBOTICS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `00285.HK` | 比亚迪电子 | HK | CONSUMER_ELECTRONICS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `002916.SZ` | 深南电路 | A | AI_COMPUTE | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `002920.SZ` | 德赛西威 | A | EXPORT_MFG | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `00293.HK` | 国泰航空 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `002938.SZ` | 鹏鼎控股 | A | CONSUMER_ELECTRONICS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `00300.HK` | 美的集团-H | HK | ROBOTICS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00323.HK` | 马鞍山钢铁 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00347.HK` | 鞍钢股份 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00358.HK` | 江西铜业 | HK | NONFERROUS_METALS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00386.HK` | 中国石油化工股份 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00388.HK` | 香港交易所 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00522.HK` | ASMPT | HK | SEMI_EQUIPMENT | 1 | 5 | 33 | 0 | 39 | 15.6% |
| `00669.HK` | 创科实业 | HK | ROBOTICS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00700.HK` | 腾讯控股 | HK | HK_CN_INTERNET | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00728.HK` | 中国电信 | HK | AI_COMPUTE | 1 | 5 | 33 | 0 | 39 | 15.6% |
| `00762.HK` | 中国联通 | HK | AI_COMPUTE | 1 | 5 | 33 | 0 | 39 | 15.6% |
| `00763.HK` | 中兴通讯 | HK | AI_COMPUTE | 1 | 5 | 33 | 0 | 39 | 15.6% |
| `00780.HK` | 同程旅行 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00819.HK` | 天能动力 | HK | STORAGE_GRID | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00836.HK` | 华润电力 | HK | STORAGE_GRID | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00914.HK` | 海螺水泥 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00916.HK` | 龙源电力 | HK | STORAGE_GRID | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00939.HK` | 建设银行 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `00941.HK` | 中国移动 | HK | AI_COMPUTE | 1 | 5 | 33 | 0 | 39 | 15.6% |
| `00981.HK` | 中芯国际 | HK | AI_COMPUTE | 1 | 5 | 33 | 0 | 39 | 15.6% |
| `00992.HK` | 联想集团 | HK | AI_COMPUTE | 1 | 5 | 33 | 0 | 39 | 15.6% |
| `01024.HK` | 快手-W | HK | HK_CN_INTERNET | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01053.HK` | 重庆钢铁 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01093.HK` | 石药集团 | HK | INNOVATIVE_PHARMA | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01157.HK` | 中联重科 | HK | ROBOTICS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01177.HK` | 中国生物制药 | HK | INNOVATIVE_PHARMA | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01179.HK` | 华住集团-S | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01208.HK` | 五矿资源 | HK | NONFERROUS_METALS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01211.HK` | 比亚迪股份 | HK | STORAGE_GRID | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01299.HK` | 友邦保险 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01313.HK` | 华润建材科技 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01347.HK` | 华虹半导体 | HK | SEMI_EQUIPMENT | 1 | 5 | 33 | 0 | 39 | 15.6% |
| `01378.HK` | 中国宏桥 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01385.HK` | 上海复旦 | HK | SEMI_EQUIPMENT | 1 | 5 | 33 | 0 | 39 | 15.6% |
| `01398.HK` | 工商银行 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01415.HK` | 高伟电子 | HK | CONSUMER_ELECTRONICS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01478.HK` | 丘钛科技 | HK | CONSUMER_ELECTRONICS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01530.HK` | 三生制药 | HK | INNOVATIVE_PHARMA | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01772.HK` | 赣锋锂业 | HK | NONFERROUS_METALS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01787.HK` | 山东黄金 | HK | NONFERROUS_METALS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01801.HK` | 信达生物 | HK | INNOVATIVE_PHARMA | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01810.HK` | 小米集团-W | HK | HK_CN_INTERNET | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01818.HK` | 招金矿业 | HK | NONFERROUS_METALS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01866.HK` | 中国心连心化肥 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01880.HK` | 中国中免 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `01928.HK` | 金沙中国 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02015.HK` | 理想汽车 | HK | EXPORT_MFG | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02018.HK` | 瑞声科技 | HK | CONSUMER_ELECTRONICS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02138.HK` | 医思健康 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02208.HK` | 金风科技 | HK | STORAGE_GRID | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02259.HK` | 紫金黄金国际 | HK | NONFERROUS_METALS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02269.HK` | 药明生物 | HK | INNOVATIVE_PHARMA | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02318.HK` | 中国平安 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02333.HK` | 长城汽车 | HK | EXPORT_MFG | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02338.HK` | 潍柴动力 | HK | EXPORT_MFG | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02359.HK` | 药明康德 | HK | INNOVATIVE_PHARMA | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02367.HK` | 巨子生物 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02380.HK` | 中国电力 | HK | STORAGE_GRID | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02382.HK` | 舜宇光学科技 | HK | CONSUMER_ELECTRONICS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02476.HK` | 胜宏科技-H | HK | AI_COMPUTE | 1 | 5 | 33 | 0 | 39 | 15.6% |
| `02498.HK` | 速腾聚创 | HK | ROBOTICS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02600.HK` | 中国铝业 | HK | NONFERROUS_METALS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02628.HK` | 中国人寿 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02727.HK` | 上海电气 | HK | ROBOTICS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `02878.HK` | 晶门半导体 | HK | SEMI_EQUIPMENT | 1 | 5 | 33 | 0 | 39 | 15.6% |
| `02899.HK` | 紫金矿业 | HK | NONFERROUS_METALS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `03323.HK` | 中国建材 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `03606.HK` | 福耀玻璃 | HK | EXPORT_MFG | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `03690.HK` | 美团-W | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `03692.HK` | 翰森制药 | HK | INNOVATIVE_PHARMA | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `03750.HK` | 宁德时代-H | HK | STORAGE_GRID | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `03800.HK` | 协鑫科技 | HK | STORAGE_GRID | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `03931.HK` | 中创新航 | HK | STORAGE_GRID | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `03968.HK` | 招商银行 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `03993.HK` | 洛阳钼业 | HK | NONFERROUS_METALS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `06030.HK` | 中信证券 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `06088.HK` | 鸿腾精密 | HK | AI_COMPUTE | 1 | 5 | 33 | 0 | 39 | 15.6% |
| `06160.HK` | 百济神州 | HK | INNOVATIVE_PHARMA | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `06690.HK` | 海尔智家 | HK | EXPORT_MFG | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `06862.HK` | 海底捞 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `09618.HK` | 京东集团-SW | HK | HK_CN_INTERNET | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `09626.HK` | 哔哩哔哩-W | HK | HK_CN_INTERNET | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `09660.HK` | 地平线机器人-W | HK | ROBOTICS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `09696.HK` | 天齐锂业 | HK | NONFERROUS_METALS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `09868.HK` | 小鹏汽车 | HK | EXPORT_MFG | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `09880.HK` | 优必选 | HK | ROBOTICS | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `09888.HK` | 百度集团-SW | HK | HK_CN_INTERNET | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `09926.HK` | 康方生物 | HK | INNOVATIVE_PHARMA | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `09961.HK` | 携程集团-S | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `09988.HK` | 阿里巴巴-W | HK | HK_CN_INTERNET | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `09995.HK` | 荣昌生物 | HK | INNOVATIVE_PHARMA | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `09999.HK` | 网易-S | HK | HK_CN_INTERNET | 1 | 5 | 32 | 0 | 38 | 15.2% |
| `300014.SZ` | 亿纬锂能 | A | STORAGE_GRID | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `300024.SZ` | 机器人 | A | ROBOTICS | 1 | 5 | 94 | 0 | 100 | 40.0% |
| `300033.SZ` | 同花顺 | A | HK_CN_INTERNET | 1 | 5 | 94 | 0 | 100 | 40.0% |
| `300059.SZ` | 东方财富 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `300073.SZ` | 当升科技 | A | STORAGE_GRID | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `300124.SZ` | 汇川技术 | A | ROBOTICS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `300144.SZ` | 宋城演艺 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `300274.SZ` | 阳光电源 | A | STORAGE_GRID | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `300308.SZ` | 中际旭创 | A | AI_COMPUTE | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `300346.SZ` | 南大光电 | A | SEMI_EQUIPMENT | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `300347.SZ` | 泰格医药 | A | INNOVATIVE_PHARMA | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `300394.SZ` | 天孚通信 | A | AI_COMPUTE | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `300413.SZ` | 芒果超媒 | A | HK_CN_INTERNET | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `300418.SZ` | 昆仑万维 | A | HK_CN_INTERNET | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `300433.SZ` | 蓝思科技 | A | CONSUMER_ELECTRONICS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `300476.SZ` | 胜宏科技 | A | CONSUMER_ELECTRONICS | 1 | 5 | 97 | 0 | 103 | 41.2% |
| `300502.SZ` | 新易盛 | A | AI_COMPUTE | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `300666.SZ` | 江丰电子 | A | SEMI_EQUIPMENT | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `300750.SZ` | 宁德时代 | A | STORAGE_GRID | 1 | 5 | 100 | 0 | 106 | 42.4% |
| `300759.SZ` | 康龙化成 | A | INNOVATIVE_PHARMA | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `300760.SZ` | 迈瑞医疗 | A | INNOVATIVE_PHARMA | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `300896.SZ` | 爱美客 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600009.SH` | 上海机场 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `600019.SH` | 宝钢股份 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600029.SH` | 南方航空 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600030.SH` | 中信证券 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 90 | 0 | 96 | 38.4% |
| `600031.SH` | 三一重工 | A | EXPORT_MFG | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600036.SH` | 招商银行 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 86 | 0 | 92 | 36.8% |
| `600111.SH` | 北方稀土 | A | NONFERROUS_METALS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600183.SH` | 生益科技 | A | CONSUMER_ELECTRONICS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600196.SH` | 复星医药 | A | INNOVATIVE_PHARMA | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600258.SH` | 首旅酒店 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600276.SH` | 恒瑞医药 | A | INNOVATIVE_PHARMA | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `600309.SH` | 万华化学 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600312.SH` | 平高电气 | A | STORAGE_GRID | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600346.SH` | 恒力石化 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600362.SH` | 江西铜业 | A | NONFERROUS_METALS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600406.SH` | 国电南瑞 | A | STORAGE_GRID | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600426.SH` | 华鲁恒升 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `600489.SH` | 中金黄金 | A | NONFERROUS_METALS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600547.SH` | 山东黄金 | A | NONFERROUS_METALS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600584.SH` | 长电科技 | A | SEMI_EQUIPMENT | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600585.SH` | 海螺水泥 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600660.SH` | 福耀玻璃 | A | EXPORT_MFG | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600690.SH` | 海尔智家 | A | EXPORT_MFG | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600754.SH` | 锦江酒店 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600801.SH` | 华新水泥 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600900.SH` | 长江电力 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `600989.SH` | 宝丰能源 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `601021.SH` | 春秋航空 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `601088.SH` | 中国神华 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `601111.SH` | 中国国航 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `601138.SH` | 工业富联 | A | AI_COMPUTE | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `601288.SH` | 农业银行 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 85 | 0 | 91 | 36.4% |
| `601318.SH` | 中国平安 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 87 | 0 | 93 | 37.2% |
| `601360.SH` | 三六零 | A | HK_CN_INTERNET | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `601398.SH` | 工商银行 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 87 | 0 | 93 | 37.2% |
| `601600.SH` | 中国铝业 | A | NONFERROUS_METALS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `601628.SH` | 中国人寿 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 87 | 0 | 93 | 37.2% |
| `601689.SH` | 拓普集团 | A | ROBOTICS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `601888.SH` | 中国中免 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `601899.SH` | 紫金矿业 | A | NONFERROUS_METALS | 1 | 5 | 97 | 0 | 103 | 41.2% |
| `601939.SH` | 建设银行 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 86 | 0 | 92 | 36.8% |
| `601988.SH` | 中国银行 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 86 | 0 | 92 | 36.8% |
| `603259.SH` | 药明康德 | A | INNOVATIVE_PHARMA | 1 | 5 | 97 | 0 | 103 | 41.2% |
| `603501.SH` | 韦尔股份 | A | CONSUMER_ELECTRONICS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `603728.SH` | 鸣志电器 | A | ROBOTICS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `603799.SH` | 华友钴业 | A | NONFERROUS_METALS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `603986.SH` | 兆易创新 | A | CONSUMER_ELECTRONICS | 1 | 5 | 97 | 0 | 103 | 41.2% |
| `603993.SH` | 洛阳钼业 | A | NONFERROUS_METALS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `688012.SH` | 中微公司 | A | SEMI_EQUIPMENT | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `688017.SH` | 绿的谐波 | A | ROBOTICS | 1 | 5 | 94 | 0 | 100 | 40.0% |
| `688041.SH` | 海光信息 | A | AI_COMPUTE | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `688072.SH` | 拓荆科技 | A | SEMI_EQUIPMENT | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `688120.SH` | 华海清科 | A | SEMI_EQUIPMENT | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `688126.SH` | 沪硅产业 | A | SEMI_EQUIPMENT | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `688180.SH` | 君实生物 | A | INNOVATIVE_PHARMA | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `688235.SH` | 百济神州 | A | INNOVATIVE_PHARMA | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `688248.SH` | 南网科技 | A | STORAGE_GRID | 1 | 5 | 95 | 0 | 101 | 40.4% |
| `688256.SH` | 寒武纪 | A | AI_COMPUTE | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `688363.SH` | 华熙生物 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `688366.SH` | 昊海生科 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `688578.SH` | 艾力斯 | A | INNOVATIVE_PHARMA | 1 | 5 | 94 | 0 | 100 | 40.0% |
| `688777.SH` | 中控技术 | A | ROBOTICS | 1 | 5 | 96 | 0 | 102 | 40.8% |
| `AA.US` | Alcoa | US | NONFERROUS_METALS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `AAL.US` | American Airlines | US | DOMESTIC_CONSUMPTION | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `AAPL.US` | Apple | US | CONSUMER_ELECTRONICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `ABBV.US` | AbbVie | US | DOMESTIC_CONSUMPTION | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `ABNB.US` | Airbnb | US | DOMESTIC_CONSUMPTION | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `AEM.US` | Agnico Eagle | US | NONFERROUS_METALS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `ALB.US` | Albemarle | US | NONFERROUS_METALS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `AMAT.US` | Applied Materials | US | SEMI_EQUIPMENT | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `AMD.US` | AMD | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `AMGN.US` | Amgen | US | INNOVATIVE_PHARMA | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `AMKR.US` | Amkor | US | SEMI_EQUIPMENT | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `AMZN.US` | Amazon (AWS) | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `ANET.US` | Arista Networks | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `APTV.US` | Aptiv | US | EXPORT_MFG | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `ARM.US` | Arm | US | CONSUMER_ELECTRONICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `ASML.US` | ASML | US | SEMI_EQUIPMENT | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `AVGO.US` | Broadcom | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `B.US` | Barrick Mining | US | NONFERROUS_METALS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `BABA.US` | Alibaba (ADR) | US | HK_CN_INTERNET | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `BAC.US` | Bank of America | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `BEKE.US` | KE Holdings | US | HK_CN_INTERNET | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `BIDU.US` | Baidu | US | HK_CN_INTERNET | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `BILI.US` | Bilibili | US | HK_CN_INTERNET | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `BKNG.US` | Booking | US | DOMESTIC_CONSUMPTION | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `BLK.US` | BlackRock | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `BRK.B.US` | Berkshire Hathaway | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `BWA.US` | BorgWarner | US | EXPORT_MFG | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `CAT.US` | Caterpillar | US | EXPORT_MFG | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `CGNX.US` | Cognex | US | ROBOTICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `CLF.US` | Cleveland-Cliffs | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `CMI.US` | Cummins | US | EXPORT_MFG | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `CSCO.US` | Cisco | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `DAL.US` | Delta | US | DOMESTIC_CONSUMPTION | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `DD.US` | DuPont | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `DE.US` | Deere | US | EXPORT_MFG | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `DELL.US` | Dell | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `DHR.US` | Danaher | US | INNOVATIVE_PHARMA | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `DIS.US` | Disney | US | DOMESTIC_CONSUMPTION | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `DOW.US` | Dow | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `ENPH.US` | Enphase | US | STORAGE_GRID | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `ENTG.US` | Entegris | US | SEMI_EQUIPMENT | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `ETN.US` | Eaton | US | STORAGE_GRID | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `FCX.US` | Freeport-McMoRan | US | NONFERROUS_METALS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `FLNC.US` | Fluence | US | STORAGE_GRID | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `FSLR.US` | First Solar | US | STORAGE_GRID | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `FUTU.US` | Futu | US | HK_CN_INTERNET | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `GE.US` | GE Aerospace | US | EXPORT_MFG | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `GEV.US` | GE Vernova | US | STORAGE_GRID | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `GFS.US` | GlobalFoundries | US | SEMI_EQUIPMENT | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `GILD.US` | Gilead | US | INNOVATIVE_PHARMA | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `GLW.US` | Corning | US | CONSUMER_ELECTRONICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `GOOGL.US` | Alphabet (Google) | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `GS.US` | Goldman Sachs | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `HLT.US` | Hilton | US | DOMESTIC_CONSUMPTION | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `HON.US` | Honeywell | US | ROBOTICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `HPQ.US` | HP | US | CONSUMER_ELECTRONICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `INTC.US` | Intel | US | CONSUMER_ELECTRONICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `ISRG.US` | Intuitive Surgical | US | ROBOTICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `JBL.US` | Jabil | US | CONSUMER_ELECTRONICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `JD.US` | JD.com | US | HK_CN_INTERNET | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `JPM.US` | JPMorgan | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `KLAC.US` | KLA | US | SEMI_EQUIPMENT | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `LLY.US` | Eli Lilly | US | INNOVATIVE_PHARMA | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `LRCX.US` | Lam Research | US | SEMI_EQUIPMENT | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `LYB.US` | LyondellBasell | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `LYV.US` | Live Nation | US | DOMESTIC_CONSUMPTION | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `MA.US` | Mastercard | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `MAR.US` | Marriott | US | DOMESTIC_CONSUMPTION | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `META.US` | Meta Platforms | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `MGA.US` | Magna | US | EXPORT_MFG | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `MLM.US` | Martin Marietta | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `MP.US` | MP Materials | US | NONFERROUS_METALS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `MRK.US` | Merck | US | INNOVATIVE_PHARMA | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `MRNA.US` | Moderna | US | INNOVATIVE_PHARMA | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `MRVL.US` | Marvell | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `MS.US` | Morgan Stanley | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `MSFT.US` | Microsoft | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `MU.US` | Micron | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `NEE.US` | NextEra Energy | US | STORAGE_GRID | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `NEM.US` | Newmont | US | NONFERROUS_METALS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `NTES.US` | NetEase | US | HK_CN_INTERNET | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `NUE.US` | Nucor | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `NVDA.US` | NVIDIA | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `NVO.US` | Novo Nordisk | US | INNOVATIVE_PHARMA | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `OC.US` | Owens Corning | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `PDD.US` | PDD | US | HK_CN_INTERNET | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `PGR.US` | Progressive | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `PWR.US` | Quanta Services | US | STORAGE_GRID | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `QCOM.US` | Qualcomm | US | CONSUMER_ELECTRONICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `QS.US` | QuantumScape | US | STORAGE_GRID | 1 | 5 | 65 | 0 | 71 | 28.4% |
| `REGN.US` | Regeneron | US | INNOVATIVE_PHARMA | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `RIO.US` | Rio Tinto | US | NONFERROUS_METALS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `ROK.US` | Rockwell Automation | US | ROBOTICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `RS.US` | Reliance | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `SBUX.US` | Starbucks | US | DOMESTIC_CONSUMPTION | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `SCCO.US` | Southern Copper | US | NONFERROUS_METALS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `SLDP.US` | Solid Power | US | STORAGE_GRID | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `SMCI.US` | Super Micro | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `STLD.US` | Steel Dynamics | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `SYM.US` | Symbotic | US | ROBOTICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `TCOM.US` | Trip.com | US | HK_CN_INTERNET | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `TECK.US` | Teck | US | NONFERROUS_METALS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `TER.US` | Teradyne | US | SEMI_EQUIPMENT | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `TME.US` | Tencent Music | US | HK_CN_INTERNET | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `TMO.US` | Thermo Fisher | US | INNOVATIVE_PHARMA | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `TSLA.US` | Tesla | US | ROBOTICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `TSM.US` | TSMC (ADR) | US | AI_COMPUTE | 1 | 5 | 68 | 0 | 74 | 29.6% |
| `TTMI.US` | TTM Technologies | US | CONSUMER_ELECTRONICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `UAL.US` | United Airlines | US | DOMESTIC_CONSUMPTION | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `V.US` | Visa | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `VMC.US` | Vulcan Materials | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `VRTX.US` | Vertex | US | INNOVATIVE_PHARMA | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `WFC.US` | Wells Fargo | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `WHR.US` | Whirlpool | US | EXPORT_MFG | 1 | 5 | 67 | 0 | 73 | 29.2% |
| `ZBRA.US` | Zebra | US | ROBOTICS | 1 | 5 | 67 | 0 | 73 | 29.2% |
