# 数据源覆盖审计：图谱 v2 spec vs 5 个数据源

> 自动生成。来源：5 个 sub-agent 各自审计 + main session 合并。
> spec：`图谱设计.md`（v2 完整版 12 层）
> 250 条数据点经过 5 个数据源（FMP Starter / Tushare / AKShare / yfinance / Futu OpenD）逐条比对。

## 1. 一句话结论

图谱 v2 共 **250** 数据点，5 个现接数据源（FMP Starter / Tushare / AKShare / yfinance / Futu OpenD）能覆盖：

- **104** 条至少 1 源 full（41%）
- **218** 条至少 1 源 full 或 partial（87%）
- **0** 条仅 FMP Premium 升级才能覆盖
- **32** 条彻底缺失（12%）—— 需 LLM 衍生 / 第三方源 / 留空

## 2. 各数据源覆盖汇总

| 数据源 | full | partial | premium_locked | none | 覆盖率 |
|---|---:|---:|---:|---:|---:|
| FMP | 48 | 139 | 18 | 45 | 74% |
| Tushare | 93 | 91 | 0 | 66 | 73% |
| AKShare | 69 | 85 | 0 | 96 | 61% |
| yfinance | 22 | 44 | 0 | 184 | 26% |
| Futu | 10 | 81 | 0 | 159 | 36% |

## 3. 按 12 层覆盖热力

「✓✓ 多源 full / ✓ 单源 full / ○ 仅 partial / $ premium / ✗ 缺失」

| 层 | 总数 | ✓✓ | ✓ | ○ | $ | ✗ | 关键短板 |
|---|---:|---:|---:|---:|---:|---:|---|
| L0 行业母图接入 | 33 | 3 | 2 | 14 | 0 | 14 | 14 条彻底缺失 |
| L10 验证指标 | 7 | 3 | 2 | 2 | 0 | 0 |  |
| L11 股价结果 | 16 | 1 | 2 | 13 | 0 | 0 | 全 partial（无 1 源直取） |
| L1 公司定位 | 12 | 0 | 0 | 10 | 0 | 2 | 2 条彻底缺失 |
| L2 业务结构 | 14 | 0 | 3 | 9 | 0 | 2 | 2 条彻底缺失 |
| L3_pccr | 18 | 0 | 0 | 12 | 0 | 6 | 6 条彻底缺失 |
| L4_operating | 23 | 4 | 0 | 12 | 0 | 7 | 7 条彻底缺失 |
| L5_financials | 28 | 20 | 6 | 1 | 0 | 1 | 1 条彻底缺失 |
| L6 估值定价 | 26 | 8 | 7 | 11 | 0 | 0 | 全 partial（无 1 源直取） |
| L7_capital_sentiment | 21 | 11 | 4 | 6 | 0 | 0 | 全 partial（无 1 源直取） |
| L8 风险抵消 | 32 | 9 | 6 | 17 | 0 | 0 | 全 partial（无 1 源直取） |
| L9_catalyst | 20 | 8 | 5 | 7 | 0 | 0 | 全 partial（无 1 源直取） |

## 4. 彻底缺失的 32 个数据点（5 源全 none，无 premium 解锁）

这些数据点全部走 LLM 衍生路径——codex 处理细节、prompt 模板、schema slot 规则、行业级/公司级共享逻辑，见 [`llm_derived_nodes.md`](./llm_derived_nodes.md)。schema 里这些节点 **必须留好**（未填时 `data_status: Unknown` + `missing_policy: unknown_reduce_confidence`），不能因缺数据跳过。

| data_point_id | layer | label | typical_kind | needs |
|---|---|---|---|---|
| `L0.demand.terminal` | L0_industry_uplink | 终端需求变化 | 行业时序 | quarterly+ |
| `L0.demand.user_count` | L0_industry_uplink | 用户/订单数量变化 | 行业时序 | quarterly+ |
| `L0.demand.frequency` | L0_industry_uplink | 消费频次变化 | 行业时序 | quarterly |
| `L0.demand.penetration` | L0_industry_uplink | 渗透率变化 | 行业时序 | quarterly |
| `L0.demand.replacement` | L0_industry_uplink | 替换周期变化 | 行业时序 | quarterly |
| `L0.supply.capacity` | L0_industry_uplink | 行业产能变化 | 行业时序 | quarterly |
| `L0.supply.channel_service` | L0_industry_uplink | 行业渠道/服务供给 | 行业时序 | quarterly |
| `L0.supply.chain_eff` | L0_industry_uplink | 供应链效率/人力供给 | 行业时序 | quarterly |
| `L0.price.discount` | L0_industry_uplink | 行业折扣力度 | 行业时序 | quarterly |
| `L0.price.pricing_power` | L0_industry_uplink | 行业提价能力 | 行业时序 | quarterly |
| `L0.cost.rent` | L0_industry_uplink | 行业租金成本 | 行业时序 | quarterly |
| `L0.cost.cac` | L0_industry_uplink | 行业获客成本 | 行业时序 | quarterly |
| `L0.compete.price_war` | L0_industry_uplink | 行业价格战 | 事件 | quarterly+ |
| `L0.compete.new_entrant` | L0_industry_uplink | 新进入者/替代品 | 事件 | quarterly |
| `L1.position.channel_edge` | L1_company_position | 渠道优势 | 公司画像 | quarterly |
| `L1.position.stickiness` | L1_company_position | 客户粘性 | 公司画像 | quarterly |
| `L2.newbiz.tam` | L2_business_structure | 新业务市场空间 | 公司画像 | oneoff |
| `L2.newbiz.uncertainty` | L2_business_structure | 新业务不确定性 | 公司画像 | quarterly |
| `L3.product.lifecycle` | L3_pccr | 产品生命周期/竞争力 | 公司画像 | quarterly |
| `L3.customer.segment_mix` | L3_pccr | 客户类型结构 | 公司画像 | quarterly |
| `L3.channel.mix` | L3_pccr | 渠道结构占比 | 公司画像 | quarterly |
| `L3.region.tier_mix` | L3_pccr | 城市层级结构 | 公司画像 | quarterly |
| `L3.delivery.lead_time` | L3_pccr | 交付周期/服务能力 | 公司画像 | quarterly |
| `L3.delivery.csat` | L3_pccr | 客户满意度 | 公司画像 | quarterly |
| `L4.volume.foot_traffic` | L4_operating | 门店客流 | 公司画像 | quarterly |
| `L4.volume.frequency` | L4_operating | 使用频次 | 公司画像 | quarterly |
| `L4.price.subscription` | L4_operating | 订阅价格 | 公司画像 | quarterly |
| `L4.price.discount` | L4_operating | 折扣率 | 公司画像 | quarterly |
| `L4.eff.capacity_utilization` | L4_operating | 产能利用率 | 公司画像 | quarterly |
| `L4.eff.conversion_retention` | L4_operating | 转化率/留存/复购 | 公司画像 | quarterly |
| `L4.share.customer_channel` | L4_operating | 客户/渠道/区域份额 | 公司画像 | quarterly |
| `L5.surprise.buy_whisper` | L5_financials | 买方/whisper预期 | 分析师预期 | quarterly |

## 5. FMP Premium ($29/mo) 升级 ROI

升级 Premium 后从 premium_locked 解锁 **4** 个数据点（之前没有 full 源覆盖的）：

| data_point_id | layer | label | FMP endpoint |
|---|---|---|---|
| `L6.mult.forward_pe` | L6_valuation | Forward PE | /analyst-estimates |
| `L6.mult.dcf` | L6_valuation | DCF估值 | /discounted-cash-flow |
| `L7.flow.institutional` | L7_capital_sentiment | 机构/对冲基金持仓 | /13F, /institutional-holder |
| `L7.trade.gamma` | L7_capital_sentiment | Gamma暴露 | /historical-chain |

## 6. 多源 full 覆盖（67 个安全数据点）

这些数据点至少 2 个数据源直接 full，cross-validate 最容易、最稳定。

| data_point_id | layer | label | full 源 |
|---|---|---|---|
| `L0.sentiment.sector_heat` | L0_industry_uplink | 板块热度/ETF流入 | Tushare, AKShare |
| `L0.sentiment.social` | L0_industry_uplink | 社媒/主题热度 | Tushare, AKShare |
| `L0.sentiment.leader_drag` | L0_industry_uplink | 龙头带动 | Tushare, AKShare |
| `L4.cost.raw_material` | L4_operating | 原材料成本 | FMP, Tushare, AKShare |
| `L4.cost.labor` | L4_operating | 人工成本 | FMP, Tushare, AKShare |
| `L4.eff.turnover` | L4_operating | 库存/应收账款周转 | FMP, Tushare, AKShare |
| `L4.eff.cycle` | L4_operating | 现金转换周期 | FMP, Tushare, AKShare |
| `L5.is.revenue` | L5_financials | 收入 | FMP, Tushare, AKShare, yfinance |
| `L5.is.revenue_growth` | L5_financials | 收入增速 | FMP, Tushare, AKShare, yfinance |
| `L5.is.gross_profit` | L5_financials | 毛利 | FMP, Tushare, AKShare, yfinance |
| `L5.is.gross_margin` | L5_financials | 毛利率 | FMP, Tushare, AKShare, yfinance |
| `L5.is.sga_rd` | L5_financials | 三费(销售/管理/研发) | FMP, Tushare, AKShare, yfinance |
| `L5.is.operating_profit` | L5_financials | 经营利润 | FMP, Tushare, AKShare, yfinance |
| `L5.is.net_profit` | L5_financials | 净利润 | FMP, Tushare, AKShare, yfinance |
| `L5.is.eps` | L5_financials | EPS | FMP, Tushare, AKShare, yfinance |
| `L5.is.margins` | L5_financials | 经营/净利率 | FMP, Tushare, AKShare, yfinance |
| `L5.bs.cash_debt` | L5_financials | 现金/有息负债 | FMP, Tushare, AKShare, yfinance |
| `L5.bs.inventory` | L5_financials | 存货 | FMP, Tushare, AKShare, yfinance |
| `L5.bs.ar_ap` | L5_financials | 应收/应付账款 | FMP, Tushare, AKShare, yfinance |
| `L5.bs.goodwill_ppe` | L5_financials | 商誉/固定资产 | FMP, Tushare, AKShare, yfinance |
| `L5.bs.leverage` | L5_financials | 资产负债率 | FMP, Tushare, AKShare, yfinance |
| `L5.cf.ocf` | L5_financials | 经营现金流 | FMP, Tushare, AKShare, yfinance |
| `L5.cf.icf_fcf` | L5_financials | 投资/融资现金流 | FMP, Tushare, AKShare, yfinance |
| `L5.cf.fcf` | L5_financials | 自由现金流 | FMP, Tushare, AKShare, yfinance |
| `L5.cf.capex` | L5_financials | Capex | FMP, Tushare, AKShare, yfinance |
| `L5.cf.buyback_dividend` | L5_financials | 回购/分红 | FMP, Tushare, AKShare, yfinance |
| `L5.surprise.preprice` | L5_financials | 股价提前反应 | FMP, Tushare, AKShare, Futu |
| `L6.mult.pe` | L6_valuation | PE | FMP, Tushare, AKShare |
| `L6.mult.ps` | L6_valuation | PS | FMP, Tushare, AKShare |
| `L6.mult.pb` | L6_valuation | PB | FMP, Tushare, AKShare |
| `L6.mult.mcap_fcf` | L6_valuation | 市值/FCF | FMP, AKShare |
| `L6.state.historical_percentile` | L6_valuation | 历史估值分位 | Tushare, AKShare |
| `L6.priced.run_up` | L6_valuation | 股价提前涨幅 | FMP, Tushare, AKShare, yfinance, Futu |
| `L6.priced.crowdedness` | L6_valuation | 资金拥挤度 | Tushare, AKShare |
| `L6.priced.discussion` | L6_valuation | 市场讨论热度 | Tushare, AKShare |
| `L7.flow.active_inflow` | L7_capital_sentiment | 主动资金流入 | Tushare, AKShare, Futu |
| `L7.flow.passive_northbound` | L7_capital_sentiment | 被动资金/外资 | Tushare, AKShare |
| `L7.flow.block_trade` | L7_capital_sentiment | 大宗交易 | Tushare, AKShare |
| `L7.trade.volume_turnover` | L7_capital_sentiment | 成交量/换手率 | FMP, Tushare, AKShare, yfinance, Futu |
| `L7.trade.margin_short` | L7_capital_sentiment | 融资融券/空头 | Tushare, AKShare |
| `L7.mood.media_social` | L7_capital_sentiment | 媒体/社媒热度 | Tushare, AKShare |
| `L7.mood.theme` | L7_capital_sentiment | 主题热度 | Tushare, AKShare |
| `L7.env.market_trend` | L7_capital_sentiment | 大盘/行业指数趋势 | FMP, Tushare, AKShare, yfinance, Futu |
| `L7.env.rates` | L7_capital_sentiment | 利率 | FMP, Tushare, AKShare |
| `L7.env.fx` | L7_capital_sentiment | 汇率 | FMP, AKShare |
| `L7.env.liquidity` | L7_capital_sentiment | 流动性 | Tushare, AKShare |
| `L8.industry.valuation_compression` | L8_risk | 行业估值压缩 | Tushare, AKShare |
| `L8.op.inventory_glut` | L8_risk | 库存积压 | FMP, Tushare, AKShare |
| `L8.fin.cash_ar` | L8_risk | 现金流/应收账款恶化 | FMP, Tushare, AKShare |
| `L8.fin.debt_pressure` | L8_risk | 债务压力 | FMP, Tushare, AKShare |
| `L8.val.overvalued` | L8_risk | 估值过高 | Tushare, AKShare |
| `L8.cap.crowdedness` | L8_risk | 资金拥挤 | Tushare, AKShare |
| `L8.cap.liquidity_short` | L8_risk | 流动性不足 | FMP, Tushare, AKShare, Futu |
| `L8.gov.management_change` | L8_risk | 管理层变动 | FMP, Tushare |
| `L8.gov.insider_sell` | L8_risk | 股东减持 | FMP, Tushare, AKShare |
| `L9.company.earnings_guidance` | L9_catalyst | 财报/预告/指引 | FMP, Tushare, AKShare |
| `L9.company.buyback_dividend` | L9_catalyst | 回购/分红 | FMP, Tushare, AKShare |
| `L9.media.report` | L9_catalyst | 媒体报道 | FMP, Tushare, AKShare |
| `L9.media.social_buzz` | L9_catalyst | 社媒发酵 | Tushare, AKShare |
| `L9.macro.rates` | L9_catalyst | 利率变化 | FMP, Tushare, AKShare |
| `L9.macro.fx` | L9_catalyst | 汇率变化 | FMP, AKShare |
| `L9.macro.cpi_employment` | L9_catalyst | 通胀/就业数据 | FMP, Tushare, AKShare |
| `L9.macro.liquidity` | L9_catalyst | 流动性变化 | Tushare, AKShare |
| `L10.industry.pmi` | L10_validation | 行业景气指数 | Tushare, AKShare |
| `L10.industry.fund_flow` | L10_validation | 行业资金流验证 | Tushare, AKShare |
| `L10.val.historical_quantile` | L10_validation | 估值历史分位 | Tushare, AKShare |
| `L11.short.technical` | L11_stock_result | 技术面反应 | FMP, Tushare, AKShare, Futu |

## 7. 完整覆盖矩阵（250 行）

「✓ full / ○ partial / $ premium_locked / — none」

| data_point_id | layer | label | FMP | Tushare | AKShare | yfinance | Futu | 总评 |
|---|---|---|:---:|:---:|:---:|:---:|:---:|---|
| `L0.demand.terminal` | L0 | 终端需求变化 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.demand.user_count` | L0 | 用户/订单数量变化 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.demand.frequency` | L0 | 消费频次变化 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.demand.penetration` | L0 | 渗透率变化 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.demand.replacement` | L0 | 替换周期变化 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.supply.capacity` | L0 | 行业产能变化 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.supply.inventory` | L0 | 行业库存变化 | — | — | ○ | — | — | ○ 仅 partial |
| `L0.supply.channel_service` | L0 | 行业渠道/服务供给 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.supply.chain_eff` | L0 | 供应链效率/人力供给 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.price.product_asp` | L0 | 行业产品价格/ASP | — | ○ | ○ | — | — | ○ 仅 partial |
| `L0.price.discount` | L0 | 行业折扣力度 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.price.contract_spot` | L0 | 合同价/现货价价差 | — | — | ○ | — | — | ○ 仅 partial |
| `L0.price.pricing_power` | L0 | 行业提价能力 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.cost.raw_material` | L0 | 原材料价格 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L0.cost.labor` | L0 | 行业人工成本 | ○ | — | — | — | — | ○ 仅 partial |
| `L0.cost.rent` | L0 | 行业租金成本 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.cost.energy_logistics` | L0 | 行业能源/物流成本 | ○ | — | ○ | — | — | ○ 仅 partial |
| `L0.cost.cac` | L0 | 行业获客成本 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.cost.capital` | L0 | 行业资金成本 | ○ | ✓ | ○ | — | — | ✓ 单源覆盖 |
| `L0.compete.share_concentration` | L0 | 市占率/集中度变化 | ○ | — | — | — | — | ○ 仅 partial |
| `L0.compete.price_war` | L0 | 行业价格战 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.compete.new_entrant` | L0 | 新进入者/替代品 | — | — | — | — | — | ✗ 完全缺失 |
| `L0.policy.subsidy` | L0 | 行业补贴政策 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L0.policy.regulation` | L0 | 监管/反垄断 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L0.policy.access_license` | L0 | 准入与牌照 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L0.policy.tax_trade` | L0 | 税收/出口限制 | ○ | — | ○ | — | — | ○ 仅 partial |
| `L0.tech.breakthrough` | L0 | 技术突破/产品迭代 | ○ | — | ○ | — | — | ○ 仅 partial |
| `L0.tech.ai_automation` | L0 | AI/自动化/降本 | ○ | — | ○ | — | — | ○ 仅 partial |
| `L0.tech.substitute_tech` | L0 | 替代技术 | ○ | — | ○ | — | — | ○ 仅 partial |
| `L0.sentiment.sector_heat` | L0 | 板块热度/ETF流入 | ○ | ✓ | ✓ | — | ○ | ✓✓ 多源覆盖 |
| `L0.sentiment.institutional` | L0 | 机构配置 | $ | ✓ | ○ | — | ○ | ✓ 单源覆盖 |
| `L0.sentiment.social` | L0 | 社媒/主题热度 | — | ✓ | ✓ | — | — | ✓✓ 多源覆盖 |
| `L0.sentiment.leader_drag` | L0 | 龙头带动 | ○ | ✓ | ✓ | — | ○ | ✓✓ 多源覆盖 |
| `L1.role.tag` | L1 | 行业角色标签 | ○ | ○ | ○ | ○ | — | ○ 仅 partial |
| `L1.model.tag` | L1 | 商业模式标签 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L1.position.market_share` | L1 | 公司市占率 | ○ | — | — | — | — | ○ 仅 partial |
| `L1.position.growth_rank` | L1 | 增速排名 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L1.position.brand` | L1 | 品牌影响力 | — | — | ○ | — | — | ○ 仅 partial |
| `L1.position.tech_barrier` | L1 | 技术壁垒 | ○ | — | — | — | — | ○ 仅 partial |
| `L1.position.cost_edge` | L1 | 成本优势 | ○ | — | ○ | — | — | ○ 仅 partial |
| `L1.position.channel_edge` | L1 | 渠道优势 | — | — | — | — | — | ✗ 完全缺失 |
| `L1.position.stickiness` | L1 | 客户粘性 | — | — | — | — | — | ✗ 完全缺失 |
| `L1.position.pricing_power` | L1 | 定价权 | ○ | ○ | ○ | — | ○ | ○ 仅 partial |
| `L1.moat.tags` | L1 | 护城河标签 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L1.stock_attr.tags` | L1 | 股价属性标签 | ○ | ○ | ○ | — | ○ | ○ 仅 partial |
| `L2.segment.revenue_share` | L2 | 业务线收入占比 | ○ | ✓ | ○ | ○ | ○ | ✓ 单源覆盖 |
| `L2.segment.profit_share` | L2 | 业务线利润占比 | ○ | ○ | ○ | ○ | ○ | ○ 仅 partial |
| `L2.segment.growth` | L2 | 业务线增速 | ○ | ✓ | ○ | ○ | ○ | ✓ 单源覆盖 |
| `L2.segment.gross_margin` | L2 | 业务线毛利率 | ○ | ✓ | ○ | ○ | ○ | ✓ 单源覆盖 |
| `L2.segment.opex_ratio` | L2 | 业务线费用率 | ○ | ○ | ○ | — | ○ | ○ 仅 partial |
| `L2.segment.cash_contrib` | L2 | 业务线现金流贡献 | ○ | — | — | — | ○ | ○ 仅 partial |
| `L2.segment.industry_exposure` | L2 | 业务线行业暴露度 | ○ | — | — | — | — | ○ 仅 partial |
| `L2.segment.compete_landscape` | L2 | 业务线竞争格局 | ○ | — | — | — | — | ○ 仅 partial |
| `L2.segment.business_risk` | L2 | 业务线业务风险 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L2.newbiz.tam` | L2 | 新业务市场空间 | — | — | — | — | — | ✗ 完全缺失 |
| `L2.newbiz.commercialization` | L2 | 新业务商业化进度 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L2.newbiz.revenue_contrib` | L2 | 新业务收入/利润贡献 | ○ | ○ | ○ | ○ | ○ | ○ 仅 partial |
| `L2.newbiz.valuation_contrib` | L2 | 新业务估值贡献 | ○ | — | — | — | — | ○ 仅 partial |
| `L2.newbiz.uncertainty` | L2 | 新业务不确定性 | — | — | — | — | — | ✗ 完全缺失 |
| `L3.product.portfolio` | L3 | 产品组合结构 | — | ○ | — | — | — | ○ 仅 partial |
| `L3.product.margin_mix` | L3 | 产品毛利/价格结构 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L3.product.lifecycle` | L3 | 产品生命周期/竞争力 | — | — | — | — | — | ✗ 完全缺失 |
| `L3.customer.segment_mix` | L3 | 客户类型结构 | — | — | — | — | — | ✗ 完全缺失 |
| `L3.customer.concentration` | L3 | 客户集中度/流失风险 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L3.customer.solvency` | L3 | 客户支付能力 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L3.channel.mix` | L3 | 渠道结构占比 | — | — | — | — | — | ✗ 完全缺失 |
| `L3.channel.overseas` | L3 | 海外渠道 | ○ | — | — | — | — | ○ 仅 partial |
| `L3.channel.cost` | L3 | 渠道费用 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L3.channel.efficiency` | L3 | 渠道效率 | ○ | — | — | — | — | ○ 仅 partial |
| `L3.region.domestic_overseas` | L3 | 国内/海外收入结构 | ○ | ○ | ○ | ○ | ○ | ○ 仅 partial |
| `L3.region.tier_mix` | L3 | 城市层级结构 | — | — | — | — | — | ✗ 完全缺失 |
| `L3.region.key_risk` | L3 | 重点/高风险区域 | ○ | — | — | — | — | ○ 仅 partial |
| `L3.region.fx_geo` | L3 | 汇率/地缘影响 | ○ | ○ | ○ | — | ○ | ○ 仅 partial |
| `L3.delivery.capacity_supply` | L3 | 产能/供应链 | ○ | — | — | — | — | ○ 仅 partial |
| `L3.delivery.lead_time` | L3 | 交付周期/服务能力 | — | — | — | — | — | ✗ 完全缺失 |
| `L3.delivery.fulfillment_cost` | L3 | 履约/售后成本 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L3.delivery.csat` | L3 | 客户满意度 | — | — | — | — | — | ✗ 完全缺失 |
| `L4.volume.sales` | L4 | 销量 | ○ | ○ | ○ | ○ | — | ○ 仅 partial |
| `L4.volume.orders` | L4 | 订单量 | ○ | — | ○ | — | — | ○ 仅 partial |
| `L4.volume.users` | L4 | 客户/用户数 | ○ | — | ○ | — | — | ○ 仅 partial |
| `L4.volume.foot_traffic` | L4 | 门店客流 | — | — | — | — | — | ✗ 完全缺失 |
| `L4.volume.shipments` | L4 | 出货量/交付量 | ○ | — | ○ | — | — | ○ 仅 partial |
| `L4.volume.frequency` | L4 | 使用频次 | — | — | — | — | — | ✗ 完全缺失 |
| `L4.price.asp_aov_arpu` | L4 | ASP/客单价/ARPU | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L4.price.subscription` | L4 | 订阅价格 | — | — | — | — | — | ✗ 完全缺失 |
| `L4.price.discount` | L4 | 折扣率 | — | — | — | — | — | ✗ 完全缺失 |
| `L4.price.pricing_power` | L4 | 提价能力 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L4.price.elasticity` | L4 | 价格弹性 | ○ | — | — | — | — | ○ 仅 partial |
| `L4.cost.raw_material` | L4 | 原材料成本 | ✓ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L4.cost.labor` | L4 | 人工成本 | ✓ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L4.cost.rent_energy_logistics` | L4 | 租金/能源/物流成本 | ○ | ○ | ○ | — | ○ | ○ 仅 partial |
| `L4.cost.cac_production` | L4 | 获客/单位生产成本 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L4.eff.capacity_utilization` | L4 | 产能利用率 | — | — | — | — | — | ✗ 完全缺失 |
| `L4.eff.turnover` | L4 | 库存/应收账款周转 | ✓ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L4.eff.store_labor` | L4 | 门店坪效/人效 | ○ | — | — | — | — | ○ 仅 partial |
| `L4.eff.conversion_retention` | L4 | 转化率/留存/复购 | — | — | — | — | — | ✗ 完全缺失 |
| `L4.eff.cycle` | L4 | 现金转换周期 | ✓ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L4.share.market` | L4 | 公司市占率 | ○ | — | — | — | — | ○ 仅 partial |
| `L4.share.customer_channel` | L4 | 客户/渠道/区域份额 | — | — | — | — | — | ✗ 完全缺失 |
| `L4.share.substitution` | L4 | 竞品替代 | ○ | — | — | — | — | ○ 仅 partial |
| `L5.is.revenue` | L5 | 收入 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.is.revenue_growth` | L5 | 收入增速 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.is.gross_profit` | L5 | 毛利 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.is.gross_margin` | L5 | 毛利率 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.is.sga_rd` | L5 | 三费(销售/管理/研发) | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.is.operating_profit` | L5 | 经营利润 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.is.net_profit` | L5 | 净利润 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.is.eps` | L5 | EPS | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.is.margins` | L5 | 经营/净利率 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.bs.cash_debt` | L5 | 现金/有息负债 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.bs.inventory` | L5 | 存货 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.bs.ar_ap` | L5 | 应收/应付账款 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.bs.goodwill_ppe` | L5 | 商誉/固定资产 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.bs.leverage` | L5 | 资产负债率 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.cf.ocf` | L5 | 经营现金流 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.cf.icf_fcf` | L5 | 投资/融资现金流 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.cf.fcf` | L5 | 自由现金流 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.cf.capex` | L5 | Capex | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.cf.buyback_dividend` | L5 | 回购/分红 | ✓ | ✓ | ✓ | ✓ | ○ | ✓✓ 多源覆盖 |
| `L5.fcst.revenue_margin` | L5 | 收入/毛利率预期 | $ | ✓ | — | — | — | ✓ 单源覆盖 |
| `L5.fcst.eps_cf` | L5 | EPS/现金流预期 | $ | ✓ | — | — | — | ✓ 单源覆盖 |
| `L5.fcst.guidance_change` | L5 | 公司指引变化 | ○ | ✓ | ○ | — | — | ✓ 单源覆盖 |
| `L5.fcst.revisions` | L5 | 分析师上修/下修 | $ | ✓ | — | — | — | ✓ 单源覆盖 |
| `L5.fcst.beat_probability` | L5 | 业绩兑现概率 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L5.surprise.sell_side` | L5 | 卖方一致预期 | $ | ✓ | — | — | — | ✓ 单源覆盖 |
| `L5.surprise.buy_whisper` | L5 | 买方/whisper预期 | — | — | — | — | — | ✗ 完全缺失 |
| `L5.surprise.preprice` | L5 | 股价提前反应 | ✓ | ✓ | ✓ | ○ | ✓ | ✓✓ 多源覆盖 |
| `L5.surprise.beat_miss` | L5 | 超预期/低于预期幅度 | ○ | ✓ | — | — | — | ✓ 单源覆盖 |
| `L6.mult.pe` | L6 | PE | ✓ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L6.mult.forward_pe` | L6 | Forward PE | $ | ○ | — | — | — | ○ 仅 partial |
| `L6.mult.ps` | L6 | PS | ✓ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L6.mult.pb` | L6 | PB | ✓ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L6.mult.ev_ebitda` | L6 | EV/EBITDA | ✓ | ○ | ○ | ○ | ○ | ✓ 单源覆盖 |
| `L6.mult.peg` | L6 | PEG | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L6.mult.mcap_fcf` | L6 | 市值/FCF | ✓ | ○ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L6.mult.dcf` | L6 | DCF估值 | $ | ○ | — | — | — | ○ 仅 partial |
| `L6.state.historical_percentile` | L6 | 历史估值分位 | ○ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L6.state.peer_compare` | L6 | 同业估值对比 | ○ | ✓ | ○ | — | ○ | ✓ 单源覆盖 |
| `L6.state.industry_center` | L6 | 行业估值中枢 | ○ | ✓ | ○ | — | ○ | ✓ 单源覆盖 |
| `L6.state.expansion_compression` | L6 | 估值扩张/压缩空间 | ○ | ✓ | ○ | — | ○ | ✓ 单源覆盖 |
| `L6.state.peg_match` | L6 | 估值与增速匹配度 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L6.priced.run_up` | L6 | 股价提前涨幅 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓✓ 多源覆盖 |
| `L6.priced.analyst_revision` | L6 | 分析师上修程度 | $ | ✓ | — | — | — | ✓ 单源覆盖 |
| `L6.priced.news_age` | L6 | 新闻传播时间 | ✓ | ○ | ○ | ○ | — | ✓ 单源覆盖 |
| `L6.priced.crowdedness` | L6 | 资金拥挤度 | ○ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L6.priced.iv` | L6 | 期权隐含波动 | $ | ○ | — | — | ✓ | ✓ 单源覆盖 |
| `L6.priced.discussion` | L6 | 市场讨论热度 | ○ | ✓ | ✓ | — | — | ✓✓ 多源覆盖 |
| `L6.priced.realization_risk` | L6 | 利好兑现风险 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L6.sens.growth_margin` | L6 | 对收入/利润率敏感 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L6.sens.cashflow` | L6 | 对现金流敏感 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L6.sens.rates` | L6 | 对利率敏感 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L6.sens.risk_narrative` | L6 | 对风险偏好/叙事敏感 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L6.path.tag` | L6 | 估值路径标签 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L6.path.second_derivative` | L6 | 二阶导变差 | ○ | ○ | — | — | ○ | ○ 仅 partial |
| `L7.flow.active_inflow` | L7 | 主动资金流入 | — | ✓ | ✓ | — | ✓ | ✓✓ 多源覆盖 |
| `L7.flow.etf_inflow` | L7 | ETF流入 | ○ | ○ | ✓ | — | — | ✓ 单源覆盖 |
| `L7.flow.passive_northbound` | L7 | 被动资金/外资 | — | ✓ | ✓ | — | ○ | ✓✓ 多源覆盖 |
| `L7.flow.institutional` | L7 | 机构/对冲基金持仓 | $ | ○ | ○ | — | ○ | ○ 仅 partial |
| `L7.flow.block_trade` | L7 | 大宗交易 | — | ✓ | ✓ | — | ○ | ✓✓ 多源覆盖 |
| `L7.trade.volume_turnover` | L7 | 成交量/换手率 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓✓ 多源覆盖 |
| `L7.trade.margin_short` | L7 | 融资融券/空头 | ○ | ✓ | ✓ | — | ○ | ✓✓ 多源覆盖 |
| `L7.trade.options_cp` | L7 | 期权Call/Put | $ | ○ | — | — | ✓ | ✓ 单源覆盖 |
| `L7.trade.iv` | L7 | 隐含波动率 | $ | ○ | — | — | ✓ | ✓ 单源覆盖 |
| `L7.trade.gamma` | L7 | Gamma暴露 | $ | — | — | — | ○ | ○ 仅 partial |
| `L7.mood.media_social` | L7 | 媒体/社媒热度 | ○ | ✓ | ✓ | ○ | — | ✓✓ 多源覆盖 |
| `L7.mood.theme` | L7 | 主题热度 | — | ✓ | ✓ | — | — | ✓✓ 多源覆盖 |
| `L7.mood.analyst_rating` | L7 | 分析师评级分布 | $ | ✓ | — | — | — | ✓ 单源覆盖 |
| `L7.mood.fomo` | L7 | FOMO程度 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L7.env.market_trend` | L7 | 大盘/行业指数趋势 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓✓ 多源覆盖 |
| `L7.env.rates` | L7 | 利率 | ✓ | ✓ | ✓ | — | — | ✓✓ 多源覆盖 |
| `L7.env.fx` | L7 | 汇率 | ✓ | ○ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L7.env.risk_appetite` | L7 | 风险偏好 | ○ | ○ | ○ | — | ○ | ○ 仅 partial |
| `L7.env.liquidity` | L7 | 流动性 | ○ | ✓ | ✓ | — | — | ✓✓ 多源覆盖 |
| `L7.env.style` | L7 | 市场风格 | ○ | ○ | ○ | — | ○ | ○ 仅 partial |
| `L7.reflex.tag` | L7 | 反身性环节标签 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L8.industry.demand_supply` | L8 | 行业需求/供给恶化 | — | ○ | — | — | — | ○ 仅 partial |
| `L8.industry.price_war` | L8 | 行业价格战 | — | ○ | — | — | — | ○ 仅 partial |
| `L8.industry.substitute` | L8 | 替代品出现 | ○ | — | ○ | — | — | ○ 仅 partial |
| `L8.industry.valuation_compression` | L8 | 行业估值压缩 | ○ | ✓ | ✓ | — | ○ | ✓✓ 多源覆盖 |
| `L8.op.order_miss` | L8 | 订单不兑现 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L8.op.product_fail` | L8 | 产品失败 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L8.op.customer_channel` | L8 | 客户流失/渠道失效 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L8.op.cost_overrun` | L8 | 成本失控 | ○ | ✓ | ○ | ○ | — | ✓ 单源覆盖 |
| `L8.op.inventory_glut` | L8 | 库存积压 | ✓ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L8.fin.revenue_profit_miss` | L8 | 收入/利润低于预期 | ○ | ✓ | — | — | — | ✓ 单源覆盖 |
| `L8.fin.eps_downward` | L8 | EPS下修 | $ | ✓ | — | — | — | ✓ 单源覆盖 |
| `L8.fin.cash_ar` | L8 | 现金流/应收账款恶化 | ✓ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L8.fin.debt_pressure` | L8 | 债务压力 | ✓ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L8.fin.goodwill_impairment` | L8 | 商誉减值 | ○ | ✓ | ○ | — | ○ | ✓ 单源覆盖 |
| `L8.val.overvalued` | L8 | 估值过高 | ○ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L8.val.priced_in` | L8 | 利好已定价/兑现 | ○ | ○ | ○ | — | ○ | ○ 仅 partial |
| `L8.val.slope_risk_off` | L8 | 增长斜率下降/风险偏好下降 | ○ | ○ | ○ | — | ○ | ○ 仅 partial |
| `L8.cap.crowdedness` | L8 | 资金拥挤 | ○ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L8.cap.outflow_cut` | L8 | ETF流出/机构减仓 | ○ | ○ | ✓ | — | ○ | ✓ 单源覆盖 |
| `L8.cap.short_increase` | L8 | 空头增加 | ○ | ✓ | ○ | — | ○ | ✓ 单源覆盖 |
| `L8.cap.liquidity_short` | L8 | 流动性不足 | ✓ | ✓ | ✓ | ○ | ✓ | ✓✓ 多源覆盖 |
| `L8.reg.tighten` | L8 | 监管收紧/反垄断 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L8.reg.license_risk` | L8 | 牌照/准入风险 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L8.reg.tax_trade` | L8 | 税收/出口限制 | ○ | — | ○ | — | — | ○ 仅 partial |
| `L8.reg.subsidy_off` | L8 | 补贴退坡 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L8.gov.management_change` | L8 | 管理层变动 | ✓ | ✓ | ○ | ○ | — | ✓✓ 多源覆盖 |
| `L8.gov.insider_sell` | L8 | 股东减持 | ✓ | ✓ | ✓ | — | ○ | ✓✓ 多源覆盖 |
| `L8.gov.fraud_control` | L8 | 财务造假/内控 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L8.gov.litigation` | L8 | 法律诉讼 | ○ | ○ | ○ | ○ | — | ○ 仅 partial |
| `L8.shock.crisis` | L8 | 安全/舆情危机 | ○ | ○ | ○ | ○ | — | ○ 仅 partial |
| `L8.shock.supply_break` | L8 | 供应中断/客户违约/自然灾害 | ○ | ○ | ○ | ○ | — | ○ 仅 partial |
| `L8.shock.black_swan` | L8 | 黑天鹅事件 | ○ | — | ○ | ○ | — | ○ 仅 partial |
| `L9.industry.data_price` | L9 | 行业数据/价格发布 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L9.industry.policy_change` | L9 | 行业政策变化 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L9.industry.compete_risk` | L9 | 行业竞争/风险事件 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L9.company.earnings_guidance` | L9 | 财报/预告/指引 | ✓ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L9.company.product_order` | L9 | 新产品发布/大订单 | ○ | ○ | ○ | ○ | — | ○ 仅 partial |
| `L9.company.ma` | L9 | 并购 | ○ | ○ | ○ | ○ | — | ○ 仅 partial |
| `L9.company.buyback_dividend` | L9 | 回购/分红 | ✓ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L9.company.mgmt_litigation` | L9 | 管理层变化/诉讼 | ○ | ✓ | ○ | ○ | — | ✓ 单源覆盖 |
| `L9.capital.inst_buy_sell` | L9 | 机构增持/减持 | $ | ✓ | ○ | — | ○ | ✓ 单源覆盖 |
| `L9.capital.etf_block` | L9 | ETF调整/大宗交易 | ○ | ○ | ✓ | — | ○ | ✓ 单源覆盖 |
| `L9.capital.margin_anomaly` | L9 | 融资/期权/空头异动 | ○ | ✓ | ○ | — | ○ | ✓ 单源覆盖 |
| `L9.media.report` | L9 | 媒体报道 | ✓ | ✓ | ✓ | ○ | — | ✓✓ 多源覆盖 |
| `L9.media.social_buzz` | L9 | 社媒发酵 | — | ✓ | ✓ | — | — | ✓✓ 多源覆盖 |
| `L9.media.analyst_action` | L9 | 分析师评级/研报变动 | $ | ✓ | — | — | — | ✓ 单源覆盖 |
| `L9.media.short_report` | L9 | 做空报告 | ○ | — | ○ | — | — | ○ 仅 partial |
| `L9.macro.rates` | L9 | 利率变化 | ✓ | ✓ | ✓ | — | — | ✓✓ 多源覆盖 |
| `L9.macro.fx` | L9 | 汇率变化 | ✓ | ○ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L9.macro.cpi_employment` | L9 | 通胀/就业数据 | ✓ | ✓ | ✓ | — | — | ✓✓ 多源覆盖 |
| `L9.macro.geo` | L9 | 地缘事件 | ○ | — | ○ | — | — | ○ 仅 partial |
| `L9.macro.liquidity` | L9 | 流动性变化 | ○ | ✓ | ✓ | — | — | ✓✓ 多源覆盖 |
| `L10.industry.sales_price` | L10 | 行业销量/价格验证 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L10.industry.inventory_orders` | L10 | 行业库存/订单验证 | ○ | ○ | ○ | — | — | ○ 仅 partial |
| `L10.industry.pmi` | L10 | 行业景气指数 | ○ | ✓ | ✓ | — | — | ✓✓ 多源覆盖 |
| `L10.industry.fund_flow` | L10 | 行业资金流验证 | ○ | ✓ | ✓ | — | ○ | ✓✓ 多源覆盖 |
| `L10.val.historical_quantile` | L10 | 估值历史分位 | ○ | ✓ | ✓ | ○ | ○ | ✓✓ 多源覆盖 |
| `L10.val.peer` | L10 | 同业估值 | ○ | ✓ | ○ | — | ○ | ✓ 单源覆盖 |
| `L10.val.expansion_compression` | L10 | 估值扩张/压缩方向 | ○ | ✓ | ○ | — | ○ | ✓ 单源覆盖 |
| `L11.short.event_impact` | L11 | 事件冲击分 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L11.short.flow_boost` | L11 | 资金放大分 | ○ | ○ | — | — | ○ | ○ 仅 partial |
| `L11.short.sentiment_shift` | L11 | 情绪变化分 | ○ | ○ | — | — | ○ | ○ 仅 partial |
| `L11.short.technical` | L11 | 技术面反应 | ✓ | ✓ | ✓ | ○ | ✓ | ✓✓ 多源覆盖 |
| `L11.short.score` | L11 | 1-5日综合影响分 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L11.mid.orders_revenue` | L11 | 订单/收入中线影响 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L11.mid.margin_guidance` | L11 | 毛利率/指引中线影响 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L11.mid.eps_upward` | L11 | EPS上修中线 | $ | ✓ | — | — | — | ✓ 单源覆盖 |
| `L11.mid.score` | L11 | 1-2季度综合影响分 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L11.long.industry_space` | L11 | 行业空间 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L11.long.compete_moat` | L11 | 竞争格局/护城河 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L11.long.business_model` | L11 | 商业模式稳定性 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L11.long.margin` | L11 | 长期利润率 | ○ | ✓ | ○ | — | — | ✓ 单源覆盖 |
| `L11.long.score` | L11 | 长线综合影响分 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L11.mode` | L11 | 当前模式状态 | ○ | ○ | — | — | — | ○ 仅 partial |
| `L11.trade.signal` | L11 | 交易意义信号 | ○ | ○ | — | — | — | ○ 仅 partial |

## 8. 引用文件

本报告是 5 份 sub-agent 审计的合并版。原始审计 markdown 与 250 条数据点清单是临时产物，已清理；如需重跑，重新发起 audit 即可。

持久来源：

- spec：`图谱设计.md`
- 数据源 catalog：`config/data_providers.yaml`
- 数据源 endpoints CSV：`docs/data_sources/{fmp,tushare,futu}_endpoints.csv`
- FMP tier 升级映射：`docs/data_sources/FMP_TIER_REQUIREMENTS.md`
