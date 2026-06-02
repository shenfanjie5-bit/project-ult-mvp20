# Complete spec fields — 000977.SZ

All **250** canonical spec dp_ids (`config/data_point_roles.yaml`), as the scorer sees them for `000977.SZ` via `read_hot_snapshot` (sentinel-merged) + compiled overlay (`company_node_instance`).

## Summary

| metric | count | of 250 |
|---|---:|---:|
| usable (real or overlay-Known) | 151 | 60.4% |
| &nbsp;&nbsp;real source (self) | 88 | 35.2% |
| &nbsp;&nbsp;real source (sentinel L0/macro) | 16 | 6.4% |
| &nbsp;&nbsp;overlay-only (LLM/authored) | 47 | 18.8% |
| inactive (event-driven, idle) | 34 | 13.6% |
| mock-only | 1 | 0.4% |
| unknown / N/A / absent | 64 | 25.6% |
| **participates_in_score (spec)** | 223 | 89.2% |
| **effectively in-score (usable + participates)** | 124 | 49.6% |

## By layer

| layer | total | real_self | real_sentinel | overlay | inactive | mock | unknown | in_score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| L0 | 33 | 0 | 6 | 0 | 2 | 0 | 25 | 6 |
| L1 | 12 | 0 | 0 | 12 | 0 | 0 | 0 | 12 |
| L2 | 14 | 3 | 0 | 6 | 0 | 0 | 5 | 9 |
| L3 | 18 | 0 | 0 | 14 | 0 | 0 | 4 | 14 |
| L4 | 23 | 4 | 0 | 10 | 0 | 0 | 9 | 14 |
| L5 | 28 | 24 | 0 | 2 | 1 | 0 | 1 | 15 |
| L6 | 26 | 17 | 1 | 0 | 0 | 0 | 8 | 18 |
| L7 | 21 | 9 | 4 | 0 | 0 | 1 | 7 | 13 |
| L8 | 32 | 8 | 0 | 3 | 20 | 0 | 1 | 11 |
| L9 | 20 | 4 | 3 | 0 | 11 | 0 | 2 | 7 |
| L10 | 7 | 3 | 2 | 0 | 0 | 0 | 2 | 5 |
| L11 | 16 | 16 | 0 | 0 | 0 | 0 | 0 | 0 |

## All 250 dp_ids

| dp_id | bucket | in_score | participates | score_target | rt_status | source | origin | overlay | value |
|---|---|:--:|:--:|---|---|---|---|---|---|
| `L0.compete.new_entrant` | inactive | · | ✓ | fundamental_score |  |  |  | Inactive |  |
| `L0.compete.price_war` | inactive | · | ✓ | fundamental_score |  |  |  | Inactive |  |
| `L0.compete.share_concentration` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.cost.cac` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.cost.capital` | real_sentinel | ✓ | ✓ | fundamental_score | Known | tushare:shibor_lpr | MKT |  | {"lpr_1y_pct": 3.0, "lpr_5y_pct": 3.5, "industr… |
| `L0.cost.energy_logistics` | real_sentinel | ✓ | ✓ | fundamental_score | Known | tushare:fut_daily+akshare:macro_shipping_bdi | MKT | Unknown | {"crude_pct": -2.956, "crude_close_cny_per_bbl"… |
| `L0.cost.labor` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.cost.raw_material` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.cost.rent` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.demand.frequency` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.demand.penetration` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.demand.replacement` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.demand.terminal` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.demand.user_count` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.policy.access_license` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.policy.regulation` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.policy.subsidy` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.policy.tax_trade` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.price.contract_spot` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.price.discount` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.price.pricing_power` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.price.product_asp` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.sentiment.institutional` | real_sentinel | ✓ | ✓ | funding_multiplier | Known | tushare:top10_holders | IND |  | {"industry_id": "AI_COMPUTE", "mean_inst_holdin… |
| `L0.sentiment.leader_drag` | real_sentinel | ✓ | ✓ | reflexivity_multiplier | Known | tushare:daily_basic.industry_pct | IND |  | {"industry_id": "AI_COMPUTE", "leader_5d_pct": … |
| `L0.sentiment.sector_heat` | real_sentinel | ✓ | ✓ | theme_multiplier | Known | tushare:moneyflow_ind_ths | IND |  | {"boards": [{"board_name": "计算机设备", "change_pct… |
| `L0.sentiment.social` | real_sentinel | ✓ | ✓ | sentiment_score | Known | tushare:dc_hot+ths_hot | IND | Unknown | {"industry_id": "AI_COMPUTE", "hot_stocks_count… |
| `L0.supply.capacity` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.supply.chain_eff` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.supply.channel_service` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.supply.inventory` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.tech.ai_automation` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.tech.breakthrough` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L0.tech.substitute_tech` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L1.moat.tags` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L1.model.tag` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L1.position.brand` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L1.position.channel_edge` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L1.position.cost_edge` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L1.position.growth_rank` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L1.position.market_share` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L1.position.pricing_power` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L1.position.stickiness` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L1.position.tech_barrier` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L1.role.tag` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L1.stock_attr.tags` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L2.newbiz.commercialization` | unknown | · | ✓ | optionality_score |  |  |  | Optionality |  |
| `L2.newbiz.revenue_contrib` | unknown | · | ✓ | optionality_score |  |  |  | Optionality |  |
| `L2.newbiz.tam` | unknown | · | ✓ | optionality_score |  |  |  | Optionality |  |
| `L2.newbiz.uncertainty` | unknown | · | ✓ | uncertainty_discount |  |  |  | Optionality |  |
| `L2.newbiz.valuation_contrib` | unknown | · | ✓ | optionality_score |  |  |  | Optionality |  |
| `L2.segment.business_risk` | overlay | ✓ | ✓ | risk_discount |  |  |  | Known |  |
| `L2.segment.cash_contrib` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L2.segment.compete_landscape` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L2.segment.gross_margin` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:fina_mainbz | self |  | {"segments": [{"item": "其他业务", "gross_margin_pc… |
| `L2.segment.growth` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:fina_mainbz | self |  | {"segments": [{"item": "其他业务", "yoy_pct": 37.41… |
| `L2.segment.industry_exposure` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L2.segment.opex_ratio` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L2.segment.profit_share` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L2.segment.revenue_share` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:fina_mainbz | self |  | {"segments": [{"item": "服务器产品", "revenue_pct": … |
| `L3.channel.cost` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L3.channel.efficiency` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L3.channel.mix` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L3.channel.overseas` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L3.customer.concentration` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L3.customer.segment_mix` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L3.customer.solvency` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L3.delivery.capacity_supply` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L3.delivery.csat` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L3.delivery.fulfillment_cost` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L3.delivery.lead_time` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L3.product.lifecycle` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L3.product.margin_mix` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L3.product.portfolio` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L3.region.domestic_overseas` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L3.region.fx_geo` | overlay | ✓ | ✓ | risk_discount |  |  |  | Known |  |
| `L3.region.key_risk` | overlay | ✓ | ✓ | risk_discount |  |  |  | Known |  |
| `L3.region.tier_mix` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L4.cost.cac_production` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L4.cost.labor` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:cashflow+income.derived | self |  | {"labor_cost_pct": 2.0796, "labor_cost_yoy_pct"… |
| `L4.cost.raw_material` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:income.derived | self |  | {"raw_material_cost_pct": 91.2812, "cogs_yoy_pc… |
| `L4.cost.rent_energy_logistics` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L4.eff.capacity_utilization` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L4.eff.conversion_retention` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L4.eff.cycle` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:balancesheet+income.derived | self |  | {"ccc_days": 91.47, "dio": 120.14, "dso": 43.89… |
| `L4.eff.store_labor` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L4.eff.turnover` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:balancesheet+income.derived | self |  | {"inventory_turnover_days": 120.14, "ar_turnove… |
| `L4.price.asp_aov_arpu` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L4.price.discount` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L4.price.elasticity` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L4.price.pricing_power` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L4.price.subscription` | unknown | · | ✓ | fundamental_score |  |  |  | N/A |  |
| `L4.share.customer_channel` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L4.share.market` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L4.share.substitution` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L4.volume.foot_traffic` | unknown | · | ✓ | fundamental_score |  |  |  | N/A |  |
| `L4.volume.frequency` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L4.volume.orders` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L4.volume.sales` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L4.volume.shipments` | overlay | ✓ | ✓ | fundamental_score |  |  |  | Known |  |
| `L4.volume.users` | unknown | · | ✓ | fundamental_score |  |  |  | Unknown |  |
| `L5.bs.ar_ap` | real_self | · | · | none | Known | tushare:balancesheet | self |  | {"accounts_receivable": 17298413677.34, "accoun… |
| `L5.bs.cash_debt` | real_self | · | · | none | Known | tushare:balancesheet | self |  | {"cash": 10743857216.69, "debt": 16201407103.02… |
| `L5.bs.goodwill_ppe` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:balancesheet | self |  | {"goodwill": 643015.39, "fix_assets_ppe": 24561… |
| `L5.bs.inventory` | real_self | · | · | none | Known | tushare:balancesheet | self |  | {"scalar": 44207128840.13, "inventory_to_assets… |
| `L5.bs.leverage` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:balancesheet.derived | self |  | {"leverage_ratio": 0.7321070004762255, "period"… |
| `L5.cf.buyback_dividend` | real_self | · | · | none | Known | tushare:cashflow | self |  | {"dividend_paid": 86821834.27, "buyback_paid": … |
| `L5.cf.capex` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:cashflow | self |  | {"scalar": 27671143.44, "unit": "元", "period": … |
| `L5.cf.fcf` | real_self | · | · | none | Known | tushare:cashflow | self |  | {"scalar": -7770904958.33, "unit": "元", "period… |
| `L5.cf.icf_fcf` | real_self | · | · | none | Known | tushare:cashflow | self |  | {"investing_cf": -126680414.03, "financing_cf":… |
| `L5.cf.ocf` | real_self | · | · | none | Known | tushare:cashflow | self |  | {"scalar": -7771612162.74, "unit": "元", "period… |
| `L5.fcst.beat_probability` | overlay | ✓ | ✓ | expectation_gap |  |  |  | Known |  |
| `L5.fcst.eps_cf` | real_self | ✓ | ✓ | expectation_gap | Known | tushare:report_rc | self |  | {"eps_avg": 2.272692307692308, "eps_low": 0.4, … |
| `L5.fcst.guidance_change` | real_self | ✓ | ✓ | expectation_gap | Known | tushare:forecast | self |  | {"prev_type": "预增", "current_type": "预增", "prev… |
| `L5.fcst.revenue_margin` | real_self | ✓ | ✓ | expectation_gap | Known | tushare:report_rc | self |  | {"revenue_avg": 196131293913.0435, "operating_p… |
| `L5.fcst.revisions` | real_self | ✓ | ✓ | expectation_gap | Known | tushare:report_rc.derived | self |  | {"consensus_eps_revision_30d_pct": -3.548632817… |
| `L5.is.eps` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:income | self |  | {"scalar": 0.4119, "unit": "元/股", "period": "20… |
| `L5.is.gross_margin` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:income.derived | self |  | {"scalar": 0.06639155141217369, "unit": "ratio"… |
| `L5.is.gross_profit` | real_self | · | · | none | Known | tushare:income.derived | self |  | {"scalar": 2354929961.3500023, "unit": "元", "pe… |
| `L5.is.margins` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:income.derived | self |  | {"operating": 0.018819132295417443, "net": 0.01… |
| `L5.is.net_profit` | real_self | · | · | none | Known | tushare:income | self |  | {"scalar": 604884837.99, "unit": "元", "period":… |
| `L5.is.operating_profit` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:income | self |  | {"scalar": 667520754.47, "unit": "元", "period":… |
| `L5.is.revenue` | real_self | · | · | none | Known | tushare:income | self |  | {"scalar": 35470325836.04, "unit": "元", "period… |
| `L5.is.revenue_growth` | real_self | ✓ | ✓ | fundamental_score | Known | tushare:income.derived | self |  | {"yoy_pct": -0.7060527534693255, "qoq_pct": 0.0… |
| `L5.is.sga_rd` | real_self | · | · | none | Known | tushare:income | self |  | {"sga_total": 499676503.59000003, "sell_exp": 3… |
| `L5.surprise.beat_miss` | inactive | · | ✓ | expectation_gap | Inactive | tushare:express+forecast | self |  | {"reason": "express missing yoy_sales"} |
| `L5.surprise.buy_whisper` | overlay | ✓ | ✓ | expectation_gap |  |  |  | Known |  |
| `L5.surprise.preprice` | unknown | · | ✓ | expectation_gap |  |  |  |  |  |
| `L5.surprise.sell_side` | real_self | ✓ | ✓ | expectation_gap | Known | tushare:report_rc | self |  | {"n_reports_90d": 24, "rating_distribution": {"… |
| `L6.mult.dcf` | unknown | · | ✓ | valuation_rerating |  |  |  |  |  |
| `L6.mult.ev_ebitda` | unknown | · | ✓ | valuation_rerating |  |  |  |  |  |
| `L6.mult.forward_pe` | unknown | · | ✓ | valuation_rerating |  |  |  |  |  |
| `L6.mult.mcap_fcf` | real_self | ✓ | ✓ | valuation_rerating | Known | tushare:daily_basic+cashflow | self |  | {"scalar": -12.023368719215414, "unit": "ratio"… |
| `L6.mult.pb` | real_self | ✓ | ✓ | valuation_rerating | Known | tushare:daily_basic | self |  | {"scalar": 4.2667, "unit": "ratio", "ttm": true… |
| `L6.mult.pe` | real_self | ✓ | ✓ | valuation_rerating | Known | tushare:daily_basic | self |  | {"scalar": 37.1448, "unit": "ratio", "ttm": tru… |
| `L6.mult.peg` | unknown | · | ✓ | valuation_rerating |  |  |  |  |  |
| `L6.mult.ps` | real_self | ✓ | ✓ | valuation_rerating | Known | tushare:daily_basic | self |  | {"scalar": 0.6187, "unit": "ratio", "ttm": true… |
| `L6.path.second_derivative` | real_self | ✓ | ✓ | valuation_rerating | Known | derive:l6_path_second_derivative | self |  | {"second_derivative": 0.014301328400874395, "d2… |
| `L6.path.tag` | real_self | ✓ | ✓ | valuation_rerating | Known | derive:l6_path_tag | self |  | {"tag": "估值压缩", "label": "compression", "pe_per… |
| `L6.priced.analyst_revision` | real_self | ✓ | ✓ | expectation_gap | Known | tushare:report_rc | self |  | {"upgrades": 0, "downgrades": 0, "maintains": 4… |
| `L6.priced.crowdedness` | real_self | ✓ | ✓ | priced_in_discount | Known | tushare:daily_basic.history | self |  | {"percentile": 0.9587628865979382, "label": "ex… |
| `L6.priced.discussion` | real_self | ✓ | ✓ | priced_in_discount | Known | tushare:dc_hot+ths_hot | self |  | {"dc_hot_count_30d": 1, "ths_hot_count_30d": 0,… |
| `L6.priced.iv` | unknown | · | ✓ | volatility_risk |  |  |  |  |  |
| `L6.priced.news_age` | unknown | · | ✓ | priced_in_discount |  |  |  |  |  |
| `L6.priced.realization_risk` | unknown | · | ✓ | priced_in_discount |  |  |  |  |  |
| `L6.priced.run_up` | real_self | ✓ | ✓ | priced_in_discount | Known | derived:price_history | self |  | {"d5_pct": 0.07976845969222089, "d20_pct": 0.28… |
| `L6.sens.cashflow` | real_self | ✓ | ✓ | valuation_sensitivity_multiplier | Known | derive:l6_sens_cashflow | self |  | {"multiplier": 0.76, "drivers": ["ocf_q=-22%", … |
| `L6.sens.growth_margin` | real_self | ✓ | ✓ | valuation_sensitivity_multiplier | Known | derive:l6_sens_growth_margin | self |  | {"multiplier": 0.5625, "drivers": ["gm=6.64%", … |
| `L6.sens.rates` | real_self | ✓ | ✓ | rate_sensitivity_multiplier | Known | derive:l6_sens_rates | self |  | {"multiplier": 1.0, "drivers": ["LPR_1Y=3.00%"]… |
| `L6.sens.risk_narrative` | real_self | ✓ | ✓ | narrative_sensitivity_multiplier | Known | derive:l6_sens_risk_narrative | self |  | {"multiplier": 1.045, "drivers": ["media_24h=20… |
| `L6.state.expansion_compression` | real_self | ✓ | ✓ | valuation_rerating | Known | tushare:daily_basic.history_long | self |  | {"pe_current": 37.1448, "pe_60d_ma": 38.8028, "… |
| `L6.state.historical_percentile` | real_self | ✓ | ✓ | valuation_rerating | Known | tushare:daily_basic.history | self |  | {"history_window_days": 183, "pe_percentile": 0… |
| `L6.state.industry_center` | real_sentinel | ✓ | ✓ | valuation_rerating | Known | tushare:daily_basic.industry_median | IND |  | {"industry_id": "AI_COMPUTE", "industry_pe_medi… |
| `L6.state.peer_compare` | real_self | ✓ | ✓ | valuation_rerating | Known | tushare:daily_basic.peer_compare | self |  | {"stock_pe": 37.1448, "industry_pe_median": 71.… |
| `L6.state.peg_match` | unknown | · | ✓ | valuation_rerating |  |  |  |  |  |
| `L7.env.fx` | unknown | · | ✓ | market_regime_multiplier |  |  |  |  |  |
| `L7.env.liquidity` | real_sentinel | ✓ | ✓ | market_regime_multiplier | Known | tushare:cn_m | MKT |  | {"m2_yoy_pct": 8.6, "m1_yoy_pct": 5.0, "m2_minu… |
| `L7.env.market_trend` | real_sentinel | ✓ | ✓ | market_regime_multiplier | Known | tushare:index_daily | MKT |  | {"scope": "A_share_market", "sse_name": "上证指数",… |
| `L7.env.rates` | real_sentinel | ✓ | ✓ | market_regime_multiplier | Known | tushare:shibor_lpr | MKT |  | {"lpr_1y_pct": 3.0, "lpr_5y_pct": 3.5, "shibor_… |
| `L7.env.risk_appetite` | real_self | ✓ | ✓ | market_regime_multiplier | Known | derive:l7_env_risk_appetite | self |  | {"multiplier": 1.0124103952379409, "label": "ne… |
| `L7.env.style` | unknown | · | ✓ | market_regime_multiplier |  |  |  |  |  |
| `L7.flow.active_inflow` | real_self | ✓ | ✓ | funding_score | Known | tushare:moneyflow | self |  | {"main_net": -63662.44, "big_orders_net": 36051… |
| `L7.flow.block_trade` | real_self | ✓ | ✓ | funding_score | Known | tushare:block_trade | self |  | {"total_amount": 12154.09, "trade_count": 1, "t… |
| `L7.flow.etf_inflow` | real_sentinel | ✓ | ✓ | funding_multiplier | Known | tushare:fund_share | MKT |  | {"top_etf_inflow": [{"ts_code": "560460.SH", "n… |
| `L7.flow.institutional` | unknown | · | ✓ | funding_multiplier |  |  |  |  |  |
| `L7.flow.passive_northbound` | mock_only | · | ✓ | funding_multiplier | Known | mock:tushare | self |  | {"scalar": 106.9398, "unit": "mock", "tick": 0} |
| `L7.mood.analyst_rating` | real_self | ✓ | ✓ | sentiment_score | Known | tushare:report_rc | self |  | {"strong_buy": 13, "buy": 8, "hold": 0, "sell":… |
| `L7.mood.fomo` | real_self | ✓ | ✓ | overheat_risk | Known | derive:l7_mood_fomo | self |  | {"score": 0.6000000000000001, "label": "elevate… |
| `L7.mood.media_social` | real_self | ✓ | ✓ | sentiment_score | Known | tushare:ths_hot.热股 | self |  | {"rank_overall": 99, "in_top_100": true, "last_… |
| `L7.mood.theme` | real_self | ✓ | ✓ | theme_multiplier | Known | tushare:ths_hot.概念板块 | self |  | {"concept_count": 20, "top_concepts": [{"concep… |
| `L7.reflex.tag` | unknown | · | ✓ | reflexivity_multiplier |  |  |  |  |  |
| `L7.trade.gamma` | unknown | · | ✓ | gamma_multiplier |  |  |  |  |  |
| `L7.trade.iv` | unknown | · | ✓ | volatility_risk |  |  |  |  |  |
| `L7.trade.margin_short` | real_self | ✓ | ✓ | funding_score | Known | tushare:margin_detail | self |  | {"margin_balance": 4121296718.0, "short_balance… |
| `L7.trade.options_cp` | unknown | · | ✓ | options_momentum_multiplier |  |  |  |  |  |
| `L7.trade.volume_turnover` | real_self | ✓ | ✓ | liquidity_multiplier | Known | tushare:daily_basic | self |  | {"turnover_rate_pct": 8.2657, "volume_ratio": 1… |
| `L8.cap.crowdedness` | inactive | · | ✓ | risk_discount | Inactive | tushare:daily_basic.history | self |  | {"turnover_30d_avg": 5.7759, "industry_pct_rank… |
| `L8.cap.liquidity_short` | real_self | ✓ | ✓ | risk_discount | Known | tushare:daily.history | self |  | {"amount_30d_avg": 6046885.87, "industry_pct_ra… |
| `L8.cap.outflow_cut` | real_self | ✓ | ✓ | risk_discount | Known | tushare:moneyflow.5d | self |  | {"signal": true, "main_net_5d": -1412549800.0, … |
| `L8.cap.short_increase` | inactive | · | ✓ | risk_discount | Inactive | tushare:margin_detail.history | self |  | {"rqye_30d": 8165947.1333, "rqye_90d": 7747144.… |
| `L8.fin.cash_ar` | real_self | ✓ | ✓ | risk_discount | Known | tushare:cashflow+income+balancesheet.derived | self |  | {"ocf_to_ni": -12.8481, "ar_yoy_pct": 2.1072, "… |
| `L8.fin.debt_pressure` | real_self | ✓ | ✓ | risk_discount | Known | tushare:balancesheet+fina_indicator.derived | self |  | {"interest_debt_to_ebitda": 4.6738, "debt_to_as… |
| `L8.fin.eps_downward` | inactive | · | ✓ | risk_discount | Inactive | tushare:forecast.derived | self |  | {"prev_eps_estimate": 60000.0, "current_eps_est… |
| `L8.fin.goodwill_impairment` | inactive | · | ✓ | risk_discount | Inactive | tushare:balancesheet | self |  | {"reason": "goodwill not in cached balancesheet… |
| `L8.fin.revenue_profit_miss` | inactive | · | ✓ | risk_discount | Inactive | tushare:express+forecast.derived | self |  | {"reason": "no miss detected", "alert_severity"… |
| `L8.gov.fraud_control` | inactive | · | ✓ | risk_discount |  |  |  | Inactive |  |
| `L8.gov.insider_sell` | real_self | ✓ | ✓ | risk_discount | Known | tushare:stk_holdertrade|alias→L8.gov.insider_sell | self |  | {"net_change_pct": -0.0025, "direction": "aggre… |
| `L8.gov.litigation` | inactive | · | ✓ | risk_discount |  |  |  | Inactive |  |
| `L8.gov.management_change` | real_self | ✓ | ✓ | risk_discount | Known | tushare:stk_managers|alias→L8.gov.management_change | self |  | {"events": [{"type": "高管变动", "person": "金冉", "t… |
| `L8.industry.demand_supply` | inactive | · | ✓ | risk_discount | Inactive | derive:l8_industry_demand_supply | self | Inactive | {"value": 0.0, "_inactive": true, "missing_inpu… |
| `L8.industry.price_war` | inactive | · | ✓ | risk_discount | Inactive | derive:l8_industry_price_war | self | Inactive | {"value": 0.0, "_inactive": true, "missing_inpu… |
| `L8.industry.substitute` | inactive | · | ✓ | risk_discount |  |  |  | Inactive |  |
| `L8.industry.valuation_compression` | inactive | · | ✓ | risk_discount | Inactive | tushare:daily_basic.industry_pe | IND |  | {"industry_pe_30d": 31.6155, "industry_pe_90d":… |
| `L8.op.cost_overrun` | inactive | · | ✓ | risk_discount | Inactive | tushare:income.derived | self |  | {"revenue_yoy": -24.3031, "cost_yoy": -26.8051,… |
| `L8.op.customer_channel` | overlay | ✓ | ✓ | risk_discount |  |  |  | Known |  |
| `L8.op.inventory_glut` | inactive | · | ✓ | risk_discount | Inactive | tushare:balancesheet+fina_indicator.derived | self |  | {"inventory_yoy_pct": -3.6502, "turnover_yoy_pc… |
| `L8.op.order_miss` | overlay | ✓ | ✓ | risk_discount |  |  |  | Known |  |
| `L8.op.product_fail` | inactive | · | ✓ | risk_discount |  |  |  | Inactive |  |
| `L8.reg.license_risk` | inactive | · | ✓ | risk_discount |  |  |  | Inactive |  |
| `L8.reg.subsidy_off` | inactive | · | ✓ | risk_discount |  |  |  | Inactive |  |
| `L8.reg.tax_trade` | overlay | ✓ | ✓ | risk_discount |  |  |  | Known |  |
| `L8.reg.tighten` | inactive | · | ✓ | risk_discount |  |  |  | Inactive |  |
| `L8.shock.black_swan` | inactive | · | ✓ | risk_discount |  |  |  | Inactive |  |
| `L8.shock.crisis` | inactive | · | ✓ | risk_discount |  |  |  | Inactive |  |
| `L8.shock.supply_break` | inactive | · | ✓ | risk_discount |  |  |  | Inactive |  |
| `L8.val.overvalued` | real_self | ✓ | ✓ | risk_discount | Known | derived:from_quantile | self |  | {"is_overvalued": true, "severity": "extreme", … |
| `L8.val.priced_in` | real_self | ✓ | ✓ | risk_discount | Known | derive:l8_val_priced_in | self |  | {"priced_in_score": 0.35, "label": "partial", "… |
| `L8.val.slope_risk_off` | unknown | · | ✓ | risk_discount |  |  |  |  |  |
| `L9.capital.etf_block` | inactive | · | ✓ | expectation_gap | Inactive | akshare:stock_dzjy_mrmx | self |  | {"events_count": 0, "as_of": "2026-05-15T20:52:… |
| `L9.capital.inst_buy_sell` | unknown | · | ✓ | expectation_gap |  |  |  |  |  |
| `L9.capital.margin_anomaly` | inactive | · | ✓ | expectation_gap | Inactive | tushare:margin_detail.history | self |  | {"rzmre_5d": 384363860.8, "rzmre_30d": 60497984… |
| `L9.company.buyback_dividend` | real_self | ✓ | ✓ | expectation_gap | Known | tushare:dividend | self |  | {"latest_ann_date": "20260411", "div_proc": "预案… |
| `L9.company.earnings_guidance` | real_self | ✓ | ✓ | expectation_gap | Known | tushare:forecast | self |  | {"type": "预增", "change_pct_min": 61.34, "change… |
| `L9.company.ma` | inactive | · | ✓ | expectation_gap |  |  |  | Inactive |  |
| `L9.company.mgmt_litigation` | real_self | ✓ | ✓ | risk_discount | Known | tushare:stk_managers | self |  | {"events": [{"type": "高管变动", "person": "金冉", "t… |
| `L9.company.product_order` | inactive | · | ✓ | expectation_gap |  |  |  | Inactive |  |
| `L9.industry.compete_risk` | inactive | · | ✓ | risk_discount | Inactive | akshare:stock_info_global_cls | MKT |  | {"count_24h": 0, "top_headlines": [], "as_of": … |
| `L9.industry.data_price` | inactive | · | ✓ | expectation_gap |  |  |  | Inactive |  |
| `L9.industry.policy_change` | inactive | · | ✓ | policy_sensitivity_multiplier | Inactive | akshare:stock_info_global_cls | MKT |  | {"count_24h": 0, "top_headlines": [], "as_of": … |
| `L9.macro.cpi_employment` | real_sentinel | ✓ | ✓ | expectation_gap | Known | tushare:cn_cpi+cn_ppi | MKT |  | {"cpi_yoy_pct": 1.2, "cpi_mom_pct": 0.3, "ppi_y… |
| `L9.macro.fx` | unknown | · | ✓ | risk_discount |  |  |  |  |  |
| `L9.macro.geo` | inactive | · | ✓ | expectation_gap |  |  |  | Inactive |  |
| `L9.macro.liquidity` | inactive | · | ✓ | expectation_gap | Inactive | tushare:cn_m | MKT |  | {"m2_yoy_pct": 8.6, "m2_yoy_change_pct": 0.0999… |
| `L9.macro.rates` | real_sentinel | ✓ | ✓ | risk_discount | Known | tushare:shibor_lpr | MKT |  | {"lpr_1y_pct": 3.0, "lpr_5y_pct": 3.5, "lpr_1y_… |
| `L9.media.analyst_action` | inactive | · | ✓ | expectation_gap | Inactive | tushare:report_rc | self |  | {"recent_changes": [], "count_7d": 0, "action_t… |
| `L9.media.report` | real_sentinel | ✓ | ✓ | expectation_gap | Known | akshare:stock_info_global_cls | MKT |  | {"count_24h": 20, "top_headlines": [{"title": "… |
| `L9.media.short_report` | inactive | · | ✓ | expectation_gap |  |  |  | Inactive |  |
| `L9.media.social_buzz` | real_self | ✓ | ✓ | expectation_gap | Known | tushare:ths_hot.热股 | self |  | {"in_xq_top_buzz": true, "follow_count": 86501.… |
| `L10.industry.fund_flow` | real_sentinel | ✓ | ✓ | confidence_multiplier | Known | tushare:moneyflow_ind_ths | IND |  | {"industry_ths_name": "计算机设备", "net_amount": -4… |
| `L10.industry.inventory_orders` | unknown | · | ✓ | confidence_multiplier |  |  |  |  |  |
| `L10.industry.pmi` | real_sentinel | ✓ | ✓ | confidence_multiplier | Known | tushare:cn_pmi | MKT |  | {"manufacturing_pmi": 50.3, "non_manufacturing_… |
| `L10.industry.sales_price` | unknown | · | ✓ | confidence_multiplier |  |  |  |  |  |
| `L10.val.expansion_compression` | real_self | ✓ | ✓ | confidence_multiplier | Known | derive:l10_val_expansion_compression | self |  | {"pe_current": 37.1448, "pe_60d_ma": 38.8028, "… |
| `L10.val.historical_quantile` | real_self | ✓ | ✓ | confidence_multiplier | Known | derived:pe_pb_history | self |  | {"pe_percentile": 0.8703703703703703, "pb_perce… |
| `L10.val.peer` | real_self | ✓ | ✓ | confidence_multiplier | Known | tushare:daily_basic.peer_compare | self |  | {"stock_pe": 37.1448, "stock_pb": 4.2667, "indu… |
| `L11.long.business_model` | real_self | · | · | audit_only | Known | derive:bootstrap_l11_subscore | self |  | {"score": -0.719102, "ocf_quality_pct": -21.910… |
| `L11.long.compete_moat` | real_self | · | · | audit_only | Known | derive:bootstrap_l11_subscore | self |  | {"score": -0.5, "gross_margin": 6.6392, "roe": … |
| `L11.long.industry_space` | real_self | · | · | audit_only | Known | derive:bootstrap_l11_subscore | self |  | {"score": 0.05999999999999943, "pmi": 50.3} |
| `L11.long.margin` | real_self | · | · | audit_only | Known | derive:bootstrap_l11_subscore | self |  | {"score": -0.414735, "net_margin_pct": 1.7053} |
| `L11.long.score` | real_self | · | · | audit_only | Known | derive:l11_long_score | self |  | {"score": -0.38676740000000015, "label": "beari… |
| `L11.mid.eps_upward` | real_self | · | · | audit_only | Known | derive:bootstrap_l11_subscore | self |  | {"score": 0.6779, "guidance": {"type": "预增", "c… |
| `L11.mid.margin_guidance` | real_self | · | · | audit_only | Known | derive:bootstrap_l11_subscore | self |  | {"score": -0.7344320000000001, "gross_margin_pc… |
| `L11.mid.orders_revenue` | real_self | · | · | audit_only | Known | derive:bootstrap_l11_subscore | self |  | {"score": -0.486062, "yoy_pct": -24.3031} |
| `L11.mid.score` | real_self | · | · | audit_only | Known | derive:l11_mid_score | self |  | {"score": -0.21138440000000006, "label": "neutr… |
| `L11.mode` | real_self | · | · | audit_only | Known | derive:l11_mode | self |  | {"mode": "trend_reversal", "label": "trend_reve… |
| `L11.short.event_impact` | real_self | · | · | audit_only | Known | derive:bootstrap_l11_subscore | self |  | {"score": 0.025000000000000022, "news_count_24h… |
| `L11.short.flow_boost` | real_self | · | · | audit_only | Known | derive:bootstrap_l11_subscore | self |  | {"score": -0.39354259999999996, "main_net": -63… |
| `L11.short.score` | real_self | · | · | audit_only | Known | derive:l11_short_score | self |  | {"score": 0.019116760407621322, "label": "neutr… |
| `L11.short.sentiment_shift` | real_self | · | · | audit_only | Known | derive:bootstrap_l11_subscore | self |  | {"score": 0.5, "in_top_100": true, "in_xq_buzz"… |
| `L11.short.technical` | real_self | · | · | audit_only | Known | derive:bootstrap_l11_subscore | self |  | {"score": 0.14839770203810643, "d20_pct": 0.286… |
| `L11.trade.signal` | real_self | · | · | audit_only | Known | derive:l11_trade_signal | self |  | {"signal": "AVOID", "mix_score": -0.20637400989… |
