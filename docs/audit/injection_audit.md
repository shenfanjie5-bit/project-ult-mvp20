# Injection Audit Report

> 三层数据架构覆盖度：overlay (LLM 衍生 schema, per-stock) + realtime (Tushare/FMP/Futu/akshare 灌入, per-stock) + L0 inherit (行业 overlay 共享, per-industry)。
> Spec 总 dp_id 数 = **250**（来源：`docs/data_sources/coverage_audit.md` § 7）。

## Summary

- Total companies: **328**
- Average effective dp_ids: **102.1 / 250** = **40.8%**
- Per-layer averages:
  - overlay Known: **1.1** (LLM/codex 填; per-stock)
  - overlay Optionality: **5.0**
  - realtime injected: **96.0** (Tushare/FMP/Futu/akshare)
  - L0 inherit (Known industry rows): **0.0**
- With ≥1 realtime value: **328** / with zero: **0**

| Market | Total | With realtime | Coverage |
|---|---:|---:|---:|
| A | 116 | 116 | 100% |
| HK | 97 | 97 | 100% |
| US | 115 | 115 | 100% |

## Coverage Distribution

- effective ≥ 50: **328** stocks
- effective 40–49: **0**
- effective 30–39: **0**
- effective 20–29: **0**
- effective < 20: **0**

## Per-Industry Aggregates

| Industry | Stocks | overlay K avg | overlay Opt avg | realtime avg | L0 inherit | effective avg | best (ts, eff) | worst (ts, eff) |
|---|---:|---:|---:|---:|---:|---:|---|---|
| AI_COMPUTE | 32 | 2.3 | 5.0 | 98.0 | 0.0 | 105.3 | `000977.SZ` (177) | `00728.HK` (55) |
| ANTI_INVOLUTION_CYCLICAL | 29 | 1.0 | 5.0 | 95.2 | 0.0 | 101.2 | `002648.SZ` (134) | `00323.HK` (55) |
| CONSUMER_ELECTRONICS | 23 | 1.0 | 5.0 | 102.7 | 0.0 | 108.7 | `002938.SZ` (135) | `00285.HK` (55) |
| DOMESTIC_CONSUMPTION | 33 | 1.0 | 5.0 | 93.6 | 0.0 | 99.6 | `300144.SZ` (133) | `00027.HK` (55) |
| EXPORT_MFG | 23 | 1.0 | 5.0 | 95.6 | 0.0 | 101.6 | `000333.SZ` (133) | `00175.HK` (55) |
| FINANCIAL_HIGH_DIVIDEND | 30 | 1.0 | 5.0 | 93.7 | 0.0 | 99.7 | `600900.SH` (133) | `00005.HK` (55) |
| HK_CN_INTERNET | 25 | 1.0 | 5.0 | 93.1 | 0.0 | 99.1 | `002230.SZ` (133) | `00700.HK` (55) |
| INNOVATIVE_PHARMA | 29 | 1.0 | 5.0 | 92.4 | 0.0 | 98.4 | `603259.SH` (134) | `01093.HK` (55) |
| NONFERROUS_METALS | 30 | 1.0 | 5.0 | 93.7 | 0.0 | 99.7 | `601899.SH` (134) | `00358.HK` (55) |
| ROBOTICS | 24 | 1.0 | 5.0 | 97.8 | 0.0 | 103.8 | `002008.SZ` (135) | `00300.HK` (55) |
| SEMI_EQUIPMENT | 22 | 1.0 | 5.0 | 104.8 | 0.0 | 110.8 | `002156.SZ` (133) | `00522.HK` (55) |
| STORAGE_GRID | 28 | 1.0 | 5.0 | 94.8 | 0.0 | 100.8 | `002594.SZ` (134) | `00819.HK` (55) |

## Top sources contributing realtime dp_ids

| source | total rows | unique dp_ids | example dp_id |
|---|---:|---:|---|
| `tushare:fina_indicator` | 1832 | 16 | `L5.fina.asset_turnover` |
| `derive:bootstrap_l11_subscore` | 3608 | 11 | `L11.long.business_model` |
| `fmp:income-statement` | 1033 | 9 | `L5.is.cogs` |
| `tushare:income.derived` | 680 | 6 | `L4.cost.raw_material` |
| `tushare:income` | 579 | 5 | `L5.is.eps` |
| `fmp:cash-flow` | 575 | 5 | `L5.cf.buyback_dividend` |
| `tushare:cashflow` | 563 | 5 | `L5.cf.buyback_dividend` |
| `tushare:balancesheet` | 547 | 5 | `L5.bs.ar_ap` |
| `mock:tushare` | 1312 | 4 | `L7.flow.margin_balance` |
| `mock:akshare` | 1312 | 4 | `L7.mood.media_social` |
| `tushare:report_rc` | 464 | 4 | `L5.surprise.sell_side` |
| `fmp:balance-sheet` | 460 | 4 | `L5.bs.ar_ap` |
| `mock:futu` | 984 | 3 | `L6.priced.crowdedness` |
| `futu:option_chain` | 487 | 3 | `L6.priced.iv` |
| `tushare:stk_holdertrade` | 348 | 3 | `L9.event.holder_trade_signal` |
| `tushare:fina_mainbz` | 348 | 3 | `L2.segment.gross_margin` |
| `fmp:revenue-product-segmentation` | 345 | 3 | `L2.segment.gross_margin` |
| `fmp:ratios-ttm` | 345 | 3 | `L6.mult.mcap_fcf` |
| `fmp:historical-price.derived` | 345 | 3 | `L10.val.historical_quantile` |
| `fmp:analyst-estimates.derived` | 345 | 3 | `L5.fcst.guidance_change` |
| `fmp:grades-historical` | 127 | 3 | `L6.priced.analyst_revision` |
| `tushare:shibor_lpr` | 3 | 3 | `L0.cost.capital` |
| `akshare:stock_info_global_cls` | 3 | 3 | `L9.industry.compete_risk` |
| `mock:tushare/futu/fmp` | 656 | 2 | `L6.mult.pb` |
| `mock:tushare/futu` | 656 | 2 | `L7.flow.active_inflow` |
| `mock:mvp20-bff` | 656 | 2 | `L11.short_term` |
| `tushare:stk_managers` | 232 | 2 | `L8.gov.management_table` |
| `tushare:margin_detail.history` | 232 | 2 | `L8.cap.short_increase` |
| `tushare:forecast` | 232 | 2 | `L5.fcst.guidance_change` |
| `tushare:daily_basic.peer_compare` | 232 | 2 | `L10.val.peer` |
| `tushare:daily_basic.history` | 232 | 2 | `L6.state.historical_percentile` |
| `tushare:balancesheet+income.derived` | 232 | 2 | `L4.eff.cycle` |
| `tushare:balancesheet+fina_indicator.derived` | 232 | 2 | `L8.fin.debt_pressure` |
| `fmp:stock-peers.derived` | 230 | 2 | `L10.val.peer` |
| `fmp:income-statement.derived` | 230 | 2 | `L4.cost.labor` |
| `fmp:balance-sheet.derived` | 230 | 2 | `L5.bs.leverage` |
| `fmp:analyst-estimates` | 230 | 2 | `L5.fcst.eps_cf` |
| `fmp:key-metrics.derived` | 206 | 2 | `L4.eff.cycle` |
| `fmp:key-metrics` | 139 | 2 | `L4.eff.cycle` |
| `tushare:dc_hot+ths_hot` | 128 | 2 | `L0.sentiment.social` |
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
| `derive:l11_short_score` | 328 | 1 | `L11.short.score` |
| `derive:l11_mode` | 328 | 1 | `L11.mode` |
| `derive:l11_mid_score` | 328 | 1 | `L11.mid.score` |
| `derive:l11_long_score` | 328 | 1 | `L11.long.score` |
| `derive:l10_val_expansion_compression` | 328 | 1 | `L10.val.expansion_compression` |
| `derive:l8_val_overvalued` | 212 | 1 | `L8.val.overvalued` |
| `futu:option_chain.cp` | 149 | 1 | `L7.trade.options_cp` |
| `tushare:stock_company` | 116 | 1 | `L1.company.main_business` |
| `tushare:stk_managers|alias→L8.gov.management_change` | 116 | 1 | `L8.gov.management_change` |
| `tushare:stk_holdertrade|alias→L8.gov.insider_sell` | 116 | 1 | `L8.gov.insider_sell` |
| `tushare:margin_detail` | 116 | 1 | `L7.trade.margin_short` |
| `tushare:forecast.derived` | 116 | 1 | `L8.fin.eps_downward` |
| `tushare:express+forecast.derived` | 116 | 1 | `L8.fin.revenue_profit_miss` |
| `tushare:express+forecast` | 116 | 1 | `L5.surprise.beat_miss` |
| `tushare:dividend` | 116 | 1 | `L9.company.buyback_dividend` |
| `tushare:daily_basic.history_long` | 116 | 1 | `L6.state.expansion_compression` |
| `tushare:daily_basic` | 116 | 1 | `L6.mult.ps` |
| `tushare:daily.history` | 116 | 1 | `L8.cap.liquidity_short` |
| `tushare:cashflow+income.derived` | 116 | 1 | `L4.cost.labor` |
| `tushare:cashflow+income+balancesheet.derived` | 116 | 1 | `L8.fin.cash_ar` |
| `tushare:balancesheet.derived` | 116 | 1 | `L5.bs.leverage` |
| `derived:price_history` | 116 | 1 | `L6.priced.run_up` |
| `derived:pe_pb_history` | 116 | 1 | `L10.val.historical_quantile` |
| `derived:from_quantile` | 116 | 1 | `L8.val.overvalued` |
| `akshare:stock_fund_flow_individual.5d` | 116 | 1 | `L8.cap.outflow_cut` |
| `akshare:stock_dzjy_mrmx` | 116 | 1 | `L9.capital.etf_block` |
| `fmp:short-interest` | 115 | 1 | `L7.trade.margin_short` |
| `fmp:sec-filings` | 115 | 1 | `L9.event.recent_filings` |
| `fmp:news.derived` | 115 | 1 | `L6.priced.news_age` |
| `fmp:news` | 115 | 1 | `L9.event.news_flow` |
| `fmp:key-metrics-ttm` | 115 | 1 | `L6.mult.ev_ebitda` |
| `fmp:insider-trading` | 115 | 1 | `L9.event.insider_trades` |
| `fmp:financial-growth` | 115 | 1 | `L5.is.revenue_growth` |
| `fmp:earnings.derived` | 115 | 1 | `L5.surprise.preprice` |
| `fmp:earnings-calendar` | 115 | 1 | `L9.company.earnings_guidance` |
| `fmp:discounted-cash-flow` | 115 | 1 | `L6.mult.dcf` |
| `fmp:cash-flow.derived` | 115 | 1 | `L8.fin.cash_ar` |
| `fmp:buyback+dividends` | 115 | 1 | `L9.company.buyback_dividend` |
| `fmp:beneficial-ownership` | 115 | 1 | `L7.holders.institutional` |
| `fmp:grades-historical.derived` | 109 | 1 | `L9.media.analyst_action` |
| `fmp:analyst-stock-recommendations` | 109 | 1 | `L7.mood.analyst_rating` |
| `tushare:daily_basic+cashflow` | 108 | 1 | `L6.mult.mcap_fcf` |
| `derive:l6_priced_run_up` | 97 | 1 | `L6.priced.run_up` |
| `tushare:irm_qa_sh` | 62 | 1 | `L9.disclosure.qa_recent` |
| `tushare:irm_qa_sz` | 54 | 1 | `L9.disclosure.qa_recent` |
| `tushare:block_trade` | 15 | 1 | `L7.flow.block_trade` |
| `tushare:top10_holders` | 12 | 1 | `L0.sentiment.institutional` |
| `tushare:daily_basic.industry_pe` | 12 | 1 | `L8.industry.valuation_compression` |
| `tushare:daily_basic.industry_pct` | 12 | 1 | `L0.sentiment.leader_drag` |
| `tushare:daily_basic.industry_median` | 12 | 1 | `L6.state.industry_center` |
| `akshare:stock_board_industry_summary_ths` | 9 | 1 | `L0.sentiment.sector_heat` |
| `tushare:moneyflow_ind_ths` | 8 | 1 | `L10.industry.fund_flow` |
| `akshare:futures_main_sina` | 7 | 1 | `L0.cost.raw_material` |
| `tushare:top_list` | 4 | 1 | `L9.capital.inst_buy_sell` |
| `tushare:top_list|alias→L7.flow.institutional` | 2 | 1 | `L7.flow.institutional` |
| `tushare:moneyflow_hsgt` | 1 | 1 | `L7.flow.passive_northbound` |
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
| `annual_report:cninfo:2025` | 1 | 1 | `L9.disclosure.annual_report` |
| `akshare:futures_main_sina+macro_shipping_bdi` | 1 | 1 | `L0.cost.energy_logistics` |

## Layer 1: overlay schema dp_ids (112 unique across all companies)

LLM-derived slots — codex fills these; data sources cannot. Each company has ~33 of these in its primary overlay.

- `L0.compete.new_entrant`
- `L0.compete.price_war`
- `L0.compete.share_concentration`
- `L0.cost.cac`
- `L0.cost.energy_logistics`
- `L0.cost.labor`
- `L0.cost.raw_material`
- `L0.cost.rent`
- `L0.demand.frequency`
- `L0.demand.penetration`
- `L0.demand.replacement`
- `L0.demand.terminal`
- `L0.demand.user_count`
- `L0.policy.access_license`
- `L0.policy.regulation`
- `L0.policy.subsidy`
- `L0.policy.tax_trade`
- `L0.price.contract_spot`
- `L0.price.discount`
- `L0.price.pricing_power`
- `L0.price.product_asp`
- `L0.sentiment.social`
- `L0.supply.capacity`
- `L0.supply.chain_eff`
- `L0.supply.channel_service`
- `L0.supply.inventory`
- `L0.tech.ai_automation`
- `L0.tech.breakthrough`
- `L0.tech.substitute_tech`
- `L1.moat.tags`
- `L1.model.tag`
- `L1.position.brand`
- `L1.position.channel_edge`
- `L1.position.cost_edge`
- `L1.position.growth_rank`
- `L1.position.market_share`
- `L1.position.pricing_power`
- `L1.position.stickiness`
- `L1.position.tech_barrier`
- `L1.role.tag`
- `L1.stock_attr.tags`
- `L2.newbiz.commercialization`
- `L2.newbiz.revenue_contrib`
- `L2.newbiz.tam`
- `L2.newbiz.uncertainty`
- `L2.newbiz.valuation_contrib`
- `L2.segment.business_risk`
- `L2.segment.cash_contrib`
- `L2.segment.compete_landscape`
- `L2.segment.industry_exposure`
- `L2.segment.opex_ratio`
- `L2.segment.profit_share`
- `L3.channel.cost`
- `L3.channel.efficiency`
- `L3.channel.mix`
- `L3.channel.overseas`
- `L3.customer.concentration`
- `L3.customer.segment_mix`
- `L3.customer.solvency`
- `L3.delivery.capacity_supply`
- `L3.delivery.csat`
- `L3.delivery.fulfillment_cost`
- `L3.delivery.lead_time`
- `L3.product.lifecycle`
- `L3.product.margin_mix`
- `L3.product.portfolio`
- `L3.region.domestic_overseas`
- `L3.region.fx_geo`
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
- `L4.share.market`
- `L4.share.substitution`
- `L4.volume.foot_traffic`
- `L4.volume.frequency`
- `L4.volume.orders`
- `L4.volume.sales`
- `L4.volume.shipments`
- `L4.volume.users`
- `L5.fcst.beat_probability`
- `L5.surprise.buy_whisper`
- `L8.gov.fraud_control`
- `L8.gov.litigation`
- `L8.industry.demand_supply`
- `L8.industry.price_war`
- `L8.industry.substitute`
- `L8.op.customer_channel`
- `L8.op.order_miss`
- `L8.op.product_fail`
- `L8.reg.license_risk`
- `L8.reg.subsidy_off`
- `L8.reg.tax_trade`
- `L8.reg.tighten`
- `L8.shock.black_swan`
- `L8.shock.crisis`
- `L8.shock.supply_break`
- `L9.company.ma`
- `L9.company.product_order`
- `L9.industry.data_price`
- `L9.macro.geo`
- `L9.media.short_report`
- `company`

## Layer 2: realtime dp_ids (147 unique across all companies)

Data points actually written by collector (`realtime_current`). Exposed via the `realtime` field of `/api/project-ult/stock-overlay`.

- `L1.company.main_business`
- `L10.val.expansion_compression`
- `L10.val.historical_quantile`
- `L10.val.peer`
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
- `L11.short_term`
- `L11.trade.signal`
- `L2.segment.gross_margin`
- `L2.segment.growth`
- `L2.segment.revenue_share`
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
- `L5.fcst.guidance_change`
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
- `L5.surprise.beat_miss`
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
- `L6.priced.analyst_revision`
- `L6.priced.crowdedness`
- `L6.priced.discussion`
- `L6.priced.iv`
- `L6.priced.news_age`
- `L6.priced.run_up`
- `L6.sens.cashflow`
- `L6.sens.growth_margin`
- `L6.sens.rates`
- `L6.sens.risk_narrative`
- `L6.state.expansion_compression`
- `L6.state.historical_percentile`
- `L6.state.peer_compare`
- `L7.env.risk_appetite`
- `L7.flow.active_inflow`
- `L7.flow.block_trade`
- `L7.flow.institutional`
- `L7.flow.margin_balance`
- `L7.flow.passive_northbound`
- `L7.holders.institutional`
- `L7.market.l2_quote`
- `L7.market.tick_count_5min`
- `L7.mood.analyst_rating`
- `L7.mood.fomo`
- `L7.mood.media_social`
- `L7.mood.theme`
- `L7.trade.iv`
- `L7.trade.margin_short`
- `L7.trade.options_cp`
- `L7.trade.volume_turnover`
- `L8.cap.crowdedness`
- `L8.cap.liquidity_short`
- `L8.cap.outflow_cut`
- `L8.cap.short_increase`
- `L8.fin.cash_ar`
- `L8.fin.debt_pressure`
- `L8.fin.eps_downward`
- `L8.fin.goodwill_impairment`
- `L8.fin.revenue_profit_miss`
- `L8.gov.insider_sell`
- `L8.gov.management_change`
- `L8.gov.management_table`
- `L8.industry.demand_supply`
- `L8.industry.price_war`
- `L8.op.cost_overrun`
- `L8.op.inventory_glut`
- `L8.val.overvalued`
- `L8.val.priced_in`
- `L9.capital.etf_block`
- `L9.capital.inst_buy_sell`
- `L9.capital.margin_anomaly`
- `L9.company.buyback_dividend`
- `L9.company.earnings_guidance`
- `L9.company.mgmt_litigation`
- `L9.disclosure.annual_report`
- `L9.disclosure.qa_recent`
- `L9.event.holder_trade_signal`
- `L9.event.insider_trades`
- `L9.event.intraday_announcement`
- `L9.event.intraday_block_trade`
- `L9.event.intraday_news`
- `L9.event.major_holder_decrease`
- `L9.event.major_holder_increase`
- `L9.event.news_flow`
- `L9.event.recent_filings`
- `L9.media.analyst_action`
- `L9.media.social_buzz`

## Layer 3: L0 inherit dp_ids (0 unique across all industries)

`Known` industry-level rows from `config/industry_overlays/*.yaml`. Shared by every stock in an industry; not stored per-company.


## Per-Stock Detail

| ts_code | name | market | industry | overlay K | overlay Opt | realtime | L0 inh | effective | spec % |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| `00005.HK` | 汇丰控股 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `000063.SZ` | 中兴通讯 | A | AI_COMPUTE | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `00027.HK` | 银河娱乐 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `000333.SZ` | 美的集团 | A | EXPORT_MFG | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `000400.SZ` | 许继电气 | A | STORAGE_GRID | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `000425.SZ` | 徐工机械 | A | EXPORT_MFG | 1 | 5 | 126 | 0 | 132 | 52.8% |
| `000651.SZ` | 格力电器 | A | EXPORT_MFG | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `000725.SZ` | 京东方A | A | CONSUMER_ELECTRONICS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `000786.SZ` | 北新建材 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `000932.SZ` | 华菱钢铁 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `000977.SZ` | 浪潮信息 | A | AI_COMPUTE | 43 | 5 | 129 | 0 | 177 | 70.8% |
| `00175.HK` | 吉利汽车 | HK | EXPORT_MFG | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `002008.SZ` | 大族激光 | A | ROBOTICS | 1 | 5 | 129 | 0 | 135 | 54.0% |
| `002050.SZ` | 三花智控 | A | ROBOTICS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `002074.SZ` | 国轩高科 | A | STORAGE_GRID | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `002126.SZ` | 银轮股份 | A | EXPORT_MFG | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `002156.SZ` | 通富微电 | A | SEMI_EQUIPMENT | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `002230.SZ` | 科大讯飞 | A | HK_CN_INTERNET | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `002241.SZ` | 歌尔股份 | A | CONSUMER_ELECTRONICS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `002371.SZ` | 北方华创 | A | SEMI_EQUIPMENT | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `002384.SZ` | 东山精密 | A | CONSUMER_ELECTRONICS | 1 | 5 | 128 | 0 | 134 | 53.6% |
| `002409.SZ` | 雅克科技 | A | SEMI_EQUIPMENT | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `002460.SZ` | 赣锋锂业 | A | NONFERROUS_METALS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `002463.SZ` | 沪电股份 | A | AI_COMPUTE | 1 | 5 | 128 | 0 | 134 | 53.6% |
| `002466.SZ` | 天齐锂业 | A | NONFERROUS_METALS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `002472.SZ` | 双环传动 | A | ROBOTICS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `002475.SZ` | 立讯精密 | A | CONSUMER_ELECTRONICS | 1 | 5 | 128 | 0 | 134 | 53.6% |
| `002555.SZ` | 三七互娱 | A | HK_CN_INTERNET | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `002594.SZ` | 比亚迪 | A | STORAGE_GRID | 1 | 5 | 128 | 0 | 134 | 53.6% |
| `002624.SZ` | 完美世界 | A | HK_CN_INTERNET | 1 | 5 | 126 | 0 | 132 | 52.8% |
| `002648.SZ` | 卫星化学 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 128 | 0 | 134 | 53.6% |
| `002747.SZ` | 埃斯顿 | A | ROBOTICS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `00285.HK` | 比亚迪电子 | HK | CONSUMER_ELECTRONICS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `002916.SZ` | 深南电路 | A | AI_COMPUTE | 1 | 5 | 126 | 0 | 132 | 52.8% |
| `002920.SZ` | 德赛西威 | A | EXPORT_MFG | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `00293.HK` | 国泰航空 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `002938.SZ` | 鹏鼎控股 | A | CONSUMER_ELECTRONICS | 1 | 5 | 129 | 0 | 135 | 54.0% |
| `00300.HK` | 美的集团-H | HK | ROBOTICS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00323.HK` | 马鞍山钢铁 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00347.HK` | 鞍钢股份 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00358.HK` | 江西铜业 | HK | NONFERROUS_METALS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00386.HK` | 中国石油化工股份 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00388.HK` | 香港交易所 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00522.HK` | ASMPT | HK | SEMI_EQUIPMENT | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00669.HK` | 创科实业 | HK | ROBOTICS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00700.HK` | 腾讯控股 | HK | HK_CN_INTERNET | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00728.HK` | 中国电信 | HK | AI_COMPUTE | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00762.HK` | 中国联通 | HK | AI_COMPUTE | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00763.HK` | 中兴通讯 | HK | AI_COMPUTE | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00780.HK` | 同程旅行 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00819.HK` | 天能动力 | HK | STORAGE_GRID | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00836.HK` | 华润电力 | HK | STORAGE_GRID | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00914.HK` | 海螺水泥 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00916.HK` | 龙源电力 | HK | STORAGE_GRID | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00939.HK` | 建设银行 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00941.HK` | 中国移动 | HK | AI_COMPUTE | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00981.HK` | 中芯国际 | HK | AI_COMPUTE | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `00992.HK` | 联想集团 | HK | AI_COMPUTE | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01024.HK` | 快手-W | HK | HK_CN_INTERNET | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01053.HK` | 重庆钢铁 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01093.HK` | 石药集团 | HK | INNOVATIVE_PHARMA | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01157.HK` | 中联重科 | HK | ROBOTICS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01177.HK` | 中国生物制药 | HK | INNOVATIVE_PHARMA | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01179.HK` | 华住集团-S | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01208.HK` | 五矿资源 | HK | NONFERROUS_METALS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01211.HK` | 比亚迪股份 | HK | STORAGE_GRID | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01299.HK` | 友邦保险 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01313.HK` | 华润建材科技 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01347.HK` | 华虹半导体 | HK | SEMI_EQUIPMENT | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01378.HK` | 中国宏桥 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01385.HK` | 上海复旦 | HK | SEMI_EQUIPMENT | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01398.HK` | 工商银行 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01415.HK` | 高伟电子 | HK | CONSUMER_ELECTRONICS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01478.HK` | 丘钛科技 | HK | CONSUMER_ELECTRONICS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01530.HK` | 三生制药 | HK | INNOVATIVE_PHARMA | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01772.HK` | 赣锋锂业 | HK | NONFERROUS_METALS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01787.HK` | 山东黄金 | HK | NONFERROUS_METALS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01801.HK` | 信达生物 | HK | INNOVATIVE_PHARMA | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01810.HK` | 小米集团-W | HK | HK_CN_INTERNET | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01818.HK` | 招金矿业 | HK | NONFERROUS_METALS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01866.HK` | 中国心连心化肥 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01880.HK` | 中国中免 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `01928.HK` | 金沙中国 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02015.HK` | 理想汽车 | HK | EXPORT_MFG | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02018.HK` | 瑞声科技 | HK | CONSUMER_ELECTRONICS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02138.HK` | 医思健康 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02208.HK` | 金风科技 | HK | STORAGE_GRID | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02259.HK` | 紫金黄金国际 | HK | NONFERROUS_METALS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02269.HK` | 药明生物 | HK | INNOVATIVE_PHARMA | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02318.HK` | 中国平安 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02333.HK` | 长城汽车 | HK | EXPORT_MFG | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02338.HK` | 潍柴动力 | HK | EXPORT_MFG | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02359.HK` | 药明康德 | HK | INNOVATIVE_PHARMA | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02367.HK` | 巨子生物 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02380.HK` | 中国电力 | HK | STORAGE_GRID | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02382.HK` | 舜宇光学科技 | HK | CONSUMER_ELECTRONICS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02476.HK` | 胜宏科技-H | HK | AI_COMPUTE | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02498.HK` | 速腾聚创 | HK | ROBOTICS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02600.HK` | 中国铝业 | HK | NONFERROUS_METALS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02628.HK` | 中国人寿 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02727.HK` | 上海电气 | HK | ROBOTICS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02878.HK` | 晶门半导体 | HK | SEMI_EQUIPMENT | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `02899.HK` | 紫金矿业 | HK | NONFERROUS_METALS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `03323.HK` | 中国建材 | HK | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `03606.HK` | 福耀玻璃 | HK | EXPORT_MFG | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `03690.HK` | 美团-W | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `03692.HK` | 翰森制药 | HK | INNOVATIVE_PHARMA | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `03750.HK` | 宁德时代-H | HK | STORAGE_GRID | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `03800.HK` | 协鑫科技 | HK | STORAGE_GRID | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `03931.HK` | 中创新航 | HK | STORAGE_GRID | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `03968.HK` | 招商银行 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `03993.HK` | 洛阳钼业 | HK | NONFERROUS_METALS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `06030.HK` | 中信证券 | HK | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `06088.HK` | 鸿腾精密 | HK | AI_COMPUTE | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `06160.HK` | 百济神州 | HK | INNOVATIVE_PHARMA | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `06690.HK` | 海尔智家 | HK | EXPORT_MFG | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `06862.HK` | 海底捞 | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `09618.HK` | 京东集团-SW | HK | HK_CN_INTERNET | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `09626.HK` | 哔哩哔哩-W | HK | HK_CN_INTERNET | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `09660.HK` | 地平线机器人-W | HK | ROBOTICS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `09696.HK` | 天齐锂业 | HK | NONFERROUS_METALS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `09868.HK` | 小鹏汽车 | HK | EXPORT_MFG | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `09880.HK` | 优必选 | HK | ROBOTICS | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `09888.HK` | 百度集团-SW | HK | HK_CN_INTERNET | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `09926.HK` | 康方生物 | HK | INNOVATIVE_PHARMA | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `09961.HK` | 携程集团-S | HK | DOMESTIC_CONSUMPTION | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `09988.HK` | 阿里巴巴-W | HK | HK_CN_INTERNET | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `09995.HK` | 荣昌生物 | HK | INNOVATIVE_PHARMA | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `09999.HK` | 网易-S | HK | HK_CN_INTERNET | 1 | 5 | 49 | 0 | 55 | 22.0% |
| `300014.SZ` | 亿纬锂能 | A | STORAGE_GRID | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `300024.SZ` | 机器人 | A | ROBOTICS | 1 | 5 | 126 | 0 | 132 | 52.8% |
| `300033.SZ` | 同花顺 | A | HK_CN_INTERNET | 1 | 5 | 125 | 0 | 131 | 52.4% |
| `300059.SZ` | 东方财富 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 126 | 0 | 132 | 52.8% |
| `300073.SZ` | 当升科技 | A | STORAGE_GRID | 1 | 5 | 126 | 0 | 132 | 52.8% |
| `300124.SZ` | 汇川技术 | A | ROBOTICS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `300144.SZ` | 宋城演艺 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `300274.SZ` | 阳光电源 | A | STORAGE_GRID | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `300308.SZ` | 中际旭创 | A | AI_COMPUTE | 1 | 5 | 128 | 0 | 134 | 53.6% |
| `300346.SZ` | 南大光电 | A | SEMI_EQUIPMENT | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `300347.SZ` | 泰格医药 | A | INNOVATIVE_PHARMA | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `300394.SZ` | 天孚通信 | A | AI_COMPUTE | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `300413.SZ` | 芒果超媒 | A | HK_CN_INTERNET | 1 | 5 | 126 | 0 | 132 | 52.8% |
| `300418.SZ` | 昆仑万维 | A | HK_CN_INTERNET | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `300433.SZ` | 蓝思科技 | A | CONSUMER_ELECTRONICS | 1 | 5 | 128 | 0 | 134 | 53.6% |
| `300476.SZ` | 胜宏科技 | A | CONSUMER_ELECTRONICS | 1 | 5 | 128 | 0 | 134 | 53.6% |
| `300502.SZ` | 新易盛 | A | AI_COMPUTE | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `300666.SZ` | 江丰电子 | A | SEMI_EQUIPMENT | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `300750.SZ` | 宁德时代 | A | STORAGE_GRID | 1 | 5 | 128 | 0 | 134 | 53.6% |
| `300759.SZ` | 康龙化成 | A | INNOVATIVE_PHARMA | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `300760.SZ` | 迈瑞医疗 | A | INNOVATIVE_PHARMA | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `300896.SZ` | 爱美客 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600009.SH` | 上海机场 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 126 | 0 | 132 | 52.8% |
| `600019.SH` | 宝钢股份 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600029.SH` | 南方航空 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600030.SH` | 中信证券 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 118 | 0 | 124 | 49.6% |
| `600031.SH` | 三一重工 | A | EXPORT_MFG | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600036.SH` | 招商银行 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 117 | 0 | 123 | 49.2% |
| `600111.SH` | 北方稀土 | A | NONFERROUS_METALS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600183.SH` | 生益科技 | A | CONSUMER_ELECTRONICS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600196.SH` | 复星医药 | A | INNOVATIVE_PHARMA | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600258.SH` | 首旅酒店 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600276.SH` | 恒瑞医药 | A | INNOVATIVE_PHARMA | 1 | 5 | 126 | 0 | 132 | 52.8% |
| `600309.SH` | 万华化学 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600312.SH` | 平高电气 | A | STORAGE_GRID | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600346.SH` | 恒力石化 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600362.SH` | 江西铜业 | A | NONFERROUS_METALS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600406.SH` | 国电南瑞 | A | STORAGE_GRID | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600426.SH` | 华鲁恒升 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 126 | 0 | 132 | 52.8% |
| `600489.SH` | 中金黄金 | A | NONFERROUS_METALS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600547.SH` | 山东黄金 | A | NONFERROUS_METALS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600584.SH` | 长电科技 | A | SEMI_EQUIPMENT | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600585.SH` | 海螺水泥 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600660.SH` | 福耀玻璃 | A | EXPORT_MFG | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600690.SH` | 海尔智家 | A | EXPORT_MFG | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600754.SH` | 锦江酒店 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600801.SH` | 华新水泥 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600900.SH` | 长江电力 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `600989.SH` | 宝丰能源 | A | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `601021.SH` | 春秋航空 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `601088.SH` | 中国神华 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `601111.SH` | 中国国航 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `601138.SH` | 工业富联 | A | AI_COMPUTE | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `601288.SH` | 农业银行 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 116 | 0 | 122 | 48.8% |
| `601318.SH` | 中国平安 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 118 | 0 | 124 | 49.6% |
| `601360.SH` | 三六零 | A | HK_CN_INTERNET | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `601398.SH` | 工商银行 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 118 | 0 | 124 | 49.6% |
| `601600.SH` | 中国铝业 | A | NONFERROUS_METALS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `601628.SH` | 中国人寿 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 118 | 0 | 124 | 49.6% |
| `601689.SH` | 拓普集团 | A | ROBOTICS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `601888.SH` | 中国中免 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `601899.SH` | 紫金矿业 | A | NONFERROUS_METALS | 1 | 5 | 128 | 0 | 134 | 53.6% |
| `601939.SH` | 建设银行 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 117 | 0 | 123 | 49.2% |
| `601988.SH` | 中国银行 | A | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 117 | 0 | 123 | 49.2% |
| `603259.SH` | 药明康德 | A | INNOVATIVE_PHARMA | 1 | 5 | 128 | 0 | 134 | 53.6% |
| `603501.SH` | 韦尔股份 | A | CONSUMER_ELECTRONICS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `603728.SH` | 鸣志电器 | A | ROBOTICS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `603799.SH` | 华友钴业 | A | NONFERROUS_METALS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `603986.SH` | 兆易创新 | A | CONSUMER_ELECTRONICS | 1 | 5 | 128 | 0 | 134 | 53.6% |
| `603993.SH` | 洛阳钼业 | A | NONFERROUS_METALS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `688012.SH` | 中微公司 | A | SEMI_EQUIPMENT | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `688017.SH` | 绿的谐波 | A | ROBOTICS | 1 | 5 | 125 | 0 | 131 | 52.4% |
| `688041.SH` | 海光信息 | A | AI_COMPUTE | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `688072.SH` | 拓荆科技 | A | SEMI_EQUIPMENT | 1 | 5 | 126 | 0 | 132 | 52.8% |
| `688120.SH` | 华海清科 | A | SEMI_EQUIPMENT | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `688126.SH` | 沪硅产业 | A | SEMI_EQUIPMENT | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `688180.SH` | 君实生物 | A | INNOVATIVE_PHARMA | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `688235.SH` | 百济神州 | A | INNOVATIVE_PHARMA | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `688248.SH` | 南网科技 | A | STORAGE_GRID | 1 | 5 | 126 | 0 | 132 | 52.8% |
| `688256.SH` | 寒武纪 | A | AI_COMPUTE | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `688363.SH` | 华熙生物 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `688366.SH` | 昊海生科 | A | DOMESTIC_CONSUMPTION | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `688578.SH` | 艾力斯 | A | INNOVATIVE_PHARMA | 1 | 5 | 125 | 0 | 131 | 52.4% |
| `688777.SH` | 中控技术 | A | ROBOTICS | 1 | 5 | 127 | 0 | 133 | 53.2% |
| `AA.US` | Alcoa | US | NONFERROUS_METALS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `AAL.US` | American Airlines | US | DOMESTIC_CONSUMPTION | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `AAPL.US` | Apple | US | CONSUMER_ELECTRONICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `ABBV.US` | AbbVie | US | DOMESTIC_CONSUMPTION | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `ABNB.US` | Airbnb | US | DOMESTIC_CONSUMPTION | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `AEM.US` | Agnico Eagle | US | NONFERROUS_METALS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `ALB.US` | Albemarle | US | NONFERROUS_METALS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `AMAT.US` | Applied Materials | US | SEMI_EQUIPMENT | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `AMD.US` | AMD | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `AMGN.US` | Amgen | US | INNOVATIVE_PHARMA | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `AMKR.US` | Amkor | US | SEMI_EQUIPMENT | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `AMZN.US` | Amazon (AWS) | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `ANET.US` | Arista Networks | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `APTV.US` | Aptiv | US | EXPORT_MFG | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `ARM.US` | Arm | US | CONSUMER_ELECTRONICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `ASML.US` | ASML | US | SEMI_EQUIPMENT | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `AVGO.US` | Broadcom | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `B.US` | Barrick Mining | US | NONFERROUS_METALS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `BABA.US` | Alibaba (ADR) | US | HK_CN_INTERNET | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `BAC.US` | Bank of America | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `BEKE.US` | KE Holdings | US | HK_CN_INTERNET | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `BIDU.US` | Baidu | US | HK_CN_INTERNET | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `BILI.US` | Bilibili | US | HK_CN_INTERNET | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `BKNG.US` | Booking | US | DOMESTIC_CONSUMPTION | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `BLK.US` | BlackRock | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `BRK.B.US` | Berkshire Hathaway | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `BWA.US` | BorgWarner | US | EXPORT_MFG | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `CAT.US` | Caterpillar | US | EXPORT_MFG | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `CGNX.US` | Cognex | US | ROBOTICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `CLF.US` | Cleveland-Cliffs | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `CMI.US` | Cummins | US | EXPORT_MFG | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `CSCO.US` | Cisco | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `DAL.US` | Delta | US | DOMESTIC_CONSUMPTION | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `DD.US` | DuPont | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `DE.US` | Deere | US | EXPORT_MFG | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `DELL.US` | Dell | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `DHR.US` | Danaher | US | INNOVATIVE_PHARMA | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `DIS.US` | Disney | US | DOMESTIC_CONSUMPTION | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `DOW.US` | Dow | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `ENPH.US` | Enphase | US | STORAGE_GRID | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `ENTG.US` | Entegris | US | SEMI_EQUIPMENT | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `ETN.US` | Eaton | US | STORAGE_GRID | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `FCX.US` | Freeport-McMoRan | US | NONFERROUS_METALS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `FLNC.US` | Fluence | US | STORAGE_GRID | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `FSLR.US` | First Solar | US | STORAGE_GRID | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `FUTU.US` | Futu | US | HK_CN_INTERNET | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `GE.US` | GE Aerospace | US | EXPORT_MFG | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `GEV.US` | GE Vernova | US | STORAGE_GRID | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `GFS.US` | GlobalFoundries | US | SEMI_EQUIPMENT | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `GILD.US` | Gilead | US | INNOVATIVE_PHARMA | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `GLW.US` | Corning | US | CONSUMER_ELECTRONICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `GOOGL.US` | Alphabet (Google) | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `GS.US` | Goldman Sachs | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `HLT.US` | Hilton | US | DOMESTIC_CONSUMPTION | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `HON.US` | Honeywell | US | ROBOTICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `HPQ.US` | HP | US | CONSUMER_ELECTRONICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `INTC.US` | Intel | US | CONSUMER_ELECTRONICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `ISRG.US` | Intuitive Surgical | US | ROBOTICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `JBL.US` | Jabil | US | CONSUMER_ELECTRONICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `JD.US` | JD.com | US | HK_CN_INTERNET | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `JPM.US` | JPMorgan | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `KLAC.US` | KLA | US | SEMI_EQUIPMENT | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `LLY.US` | Eli Lilly | US | INNOVATIVE_PHARMA | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `LRCX.US` | Lam Research | US | SEMI_EQUIPMENT | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `LYB.US` | LyondellBasell | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `LYV.US` | Live Nation | US | DOMESTIC_CONSUMPTION | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `MA.US` | Mastercard | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `MAR.US` | Marriott | US | DOMESTIC_CONSUMPTION | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `META.US` | Meta Platforms | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `MGA.US` | Magna | US | EXPORT_MFG | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `MLM.US` | Martin Marietta | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `MP.US` | MP Materials | US | NONFERROUS_METALS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `MRK.US` | Merck | US | INNOVATIVE_PHARMA | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `MRNA.US` | Moderna | US | INNOVATIVE_PHARMA | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `MRVL.US` | Marvell | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `MS.US` | Morgan Stanley | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `MSFT.US` | Microsoft | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `MU.US` | Micron | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `NEE.US` | NextEra Energy | US | STORAGE_GRID | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `NEM.US` | Newmont | US | NONFERROUS_METALS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `NTES.US` | NetEase | US | HK_CN_INTERNET | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `NUE.US` | Nucor | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `NVDA.US` | NVIDIA | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `NVO.US` | Novo Nordisk | US | INNOVATIVE_PHARMA | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `OC.US` | Owens Corning | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `PDD.US` | PDD | US | HK_CN_INTERNET | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `PGR.US` | Progressive | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `PWR.US` | Quanta Services | US | STORAGE_GRID | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `QCOM.US` | Qualcomm | US | CONSUMER_ELECTRONICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `QS.US` | QuantumScape | US | STORAGE_GRID | 1 | 5 | 103 | 0 | 109 | 43.6% |
| `REGN.US` | Regeneron | US | INNOVATIVE_PHARMA | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `RIO.US` | Rio Tinto | US | NONFERROUS_METALS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `ROK.US` | Rockwell Automation | US | ROBOTICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `RS.US` | Reliance | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `SBUX.US` | Starbucks | US | DOMESTIC_CONSUMPTION | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `SCCO.US` | Southern Copper | US | NONFERROUS_METALS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `SLDP.US` | Solid Power | US | STORAGE_GRID | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `SMCI.US` | Super Micro | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `STLD.US` | Steel Dynamics | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `SYM.US` | Symbotic | US | ROBOTICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `TCOM.US` | Trip.com | US | HK_CN_INTERNET | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `TECK.US` | Teck | US | NONFERROUS_METALS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `TER.US` | Teradyne | US | SEMI_EQUIPMENT | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `TME.US` | Tencent Music | US | HK_CN_INTERNET | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `TMO.US` | Thermo Fisher | US | INNOVATIVE_PHARMA | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `TSLA.US` | Tesla | US | ROBOTICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `TSM.US` | TSMC (ADR) | US | AI_COMPUTE | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `TTMI.US` | TTM Technologies | US | CONSUMER_ELECTRONICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `UAL.US` | United Airlines | US | DOMESTIC_CONSUMPTION | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `V.US` | Visa | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `VMC.US` | Vulcan Materials | US | ANTI_INVOLUTION_CYCLICAL | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `VRTX.US` | Vertex | US | INNOVATIVE_PHARMA | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `WFC.US` | Wells Fargo | US | FINANCIAL_HIGH_DIVIDEND | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `WHR.US` | Whirlpool | US | EXPORT_MFG | 1 | 5 | 105 | 0 | 111 | 44.4% |
| `ZBRA.US` | Zebra | US | ROBOTICS | 1 | 5 | 105 | 0 | 111 | 44.4% |
