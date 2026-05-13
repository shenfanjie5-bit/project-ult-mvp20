# 字段数据源策略 v1

> 决策矩阵：spec 250 dp_id × 5 个 bucket（闭环硬数据 / 闭环派生 / 闭环 LLM / web LLM / premium 或 skip）
>
> 来源交叉：
>
> - **spec source of truth**: `config/data_point_roles.yaml`（250 dp_id）+ `docs/data_sources/coverage_audit.md` §7 完整覆盖矩阵
> - **实测 SQLite**: `runtime/hot.sqlite` `realtime_current` 表 distinct dp_id（132 个；105 在 spec 250 内）
> - **实测 overlay yaml**: `config/{industry_overlays,stock_overlays}/**/*.yaml` 节点 `data_status ∈ {Known, Optionality}`（30 个在 spec 250 内 / X5 候选）
>
> 用户提出的架构原则（来自任务上下文）：
>
> 1. **闭环数据系统**：LLM 默认不出网，输入只能是本地 SQLite 硬数据 + overlay yaml + 行业框架知识
> 2. **未来可能开放**：部分字段允许 LLM 自己 web search（公开年报 / 三方研报 / IR 站）
> 3. **决策依据**：字段语义 + 闭环数据是否够 + web fetch 价值
>
> 本文件只研究 + 出决策，不改代码。下游消费者：X5 工作流 / X4 derive 扩展 / 未来 D bucket 试点。

---

## 1. 总览

### 1.1 5 个 bucket 定义

| Bucket | 含义 | 数据流 | 典型例 |
|---|---|---|---|
| **A** closed-hard | 现接 5 源已有 1 个以上 ✓ full 直接出值 | fetcher → SQLite `realtime_current` | `L5.is.revenue`, `L7.trade.volume_turnover` |
| **B** closed-derived | 上游 raw 数据齐，graph-engine derive 算 | SQLite raw → derive 层 → SQLite 派生 dp | `L11.short.score`, `L6.sens.rates`, `L7.mood.fomo` |
| **C** closed-llm | LLM + 本地文本（IR、年报、业绩会、industry framework prior）即可填，不出网 | overlay yaml LLM 槽 + 本地 RAG 文本库 | `L1.position.brand`, `L0.demand.terminal`, `L4.price.discount` |
| **D** web-llm | 必须 LLM + 外部 fetch（年报全文 / 三方研报 / IR 站直读 / app 数据） | overlay yaml LLM 槽 + 受信 web 源 | `L3.product.lifecycle`, `L4.volume.foot_traffic`, `L2.newbiz.tam` |
| **E** premium-or-skip | premium-locked 升级或永远走 LLM/人工/付费 alt-data | FMP Premium / Futu LV2 / 付费 vendor | `L7.flow.institutional`, `L5.surprise.buy_whisper`, `L6.mult.forward_pe` |

### 1.2 分布（250 字段）

| Bucket | 数 | 占比 |
|---|---:|---:|
| A | 106 | 42.4% |
| B | 28 | 11.2% |
| C | 103 | 41.2% |
| D | 8 | 3.2% |
| E | 5 | 2.0% |
| **合计** | **250** | **100%** |

### 1.3 按 layer × bucket 矩阵

| Layer | 字段数 | A 硬 | B 派生 | C 闭环 LLM | D web LLM | E premium |
|---|---:|---:|---:|---:|---:|---:|
| L0 | 33 | 5 | 0 | 28 | 0 | 0 |
| L1 | 12 | 0 | 0 | 12 | 0 | 0 |
| L2 | 14 | 3 | 0 | 10 | 1 | 0 |
| L3 | 18 | 0 | 0 | 15 | 3 | 0 |
| L4 | 23 | 4 | 0 | 15 | 4 | 0 |
| L5 | 28 | 26 | 0 | 1 | 0 | 1 |
| L6 | 26 | 15 | 9 | 0 | 0 | 2 |
| L7 | 21 | 15 | 4 | 0 | 0 | 2 |
| L8 | 32 | 15 | 2 | 15 | 0 | 0 |
| L9 | 20 | 13 | 0 | 7 | 0 | 0 |
| L10 | 7 | 7 | 0 | 0 | 0 | 0 |
| L11 | 16 | 3 | 13 | 0 | 0 | 0 |
| **合计** | **250** | **106** | **28** | **103** | **8** | **5** |

### 1.4 按 bucket × 当前实测状态交叉

（实测 = SQLite `realtime_current` 已 emit / overlay yaml 节点 data_status=Known/Optionality / 全无）

| Bucket | SQLite 已 emit | OverlayKnown | 都没（missing） | 小计 |
|---|---:|---:|---:|---:|
| A | 73 | 0 | 33 | 106 |
| B | 24 | 0 | 4 | 28 |
| C | 6 | 21 | 76 | 103 |
| D | 0 | 8 | 0 | 8 |
| E | 2 | 1 | 2 | 5 |
| **合计** | **105** | **30** | **115** | **250** |

**关键观察**：

- A bucket 106 个中 33 个还没 emit（fetcher 没接全 / dp_id alias 不匹配 / 行业级未实例化）— X4 hot snapshot 主战场
- C bucket 103 个中 76 个尚未填（X5 工作流核心 KPI；现在只填了 21 个 + 6 个 SQLite 误标）
- D bucket 8 个全在 overlay 试填阶段（实际产物质量待评估，可能其中部分要重判到 C）
- B bucket 28 个中 4 个 missing 是因为下游派生未触发（L11.long.* / L11.mode 等待 X4 contribution chain）

---

## 2. 完整 250 字段决策矩阵（按 layer 分组）

### 2.1 L0 行业母图接入（33）

| dp_id | 标签 | spec 覆盖 | 实测状态 | Bucket | 决策依据 |
|---|---|---|---|:-:|---|
| `L0.compete.new_entrant` | 新进入者/替代品 | ✗ 完全缺失 | missing | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.compete.price_war` | 行业价格战 | ✗ 完全缺失 | missing | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.compete.share_concentration` | 市占率/集中度变化 | ○ 仅 partial | missing | **C** | partial fallback (uncategorized) |
| `L0.cost.cac` | 行业获客成本 | ✗ 完全缺失 | OverlayKnown | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.cost.capital` | 行业资金成本 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L0.cost.energy_logistics` | 行业能源/物流成本 | ○ 仅 partial | SQLite | **C** | partial fallback (uncategorized) |
| `L0.cost.labor` | 行业人工成本 | ○ 仅 partial | missing | **C** | partial fallback (uncategorized) |
| `L0.cost.raw_material` | 原材料价格 | ○ 仅 partial | SQLite | **C** | partial fallback (uncategorized) |
| `L0.cost.rent` | 行业租金成本 | ✗ 完全缺失 | OverlayKnown | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.demand.frequency` | 消费频次变化 | ✗ 完全缺失 | OverlayKnown | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.demand.penetration` | 渗透率变化 | ✗ 完全缺失 | OverlayKnown | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.demand.replacement` | 替换周期变化 | ✗ 完全缺失 | OverlayKnown | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.demand.terminal` | 终端需求变化 | ✗ 完全缺失 | OverlayKnown | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.demand.user_count` | 用户/订单数量变化 | ✗ 完全缺失 | OverlayKnown | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.policy.access_license` | 准入与牌照 | ○ 仅 partial | missing | **C** | partial fallback (uncategorized) |
| `L0.policy.regulation` | 监管/反垄断 | ○ 仅 partial | missing | **C** | partial fallback (uncategorized) |
| `L0.policy.subsidy` | 行业补贴政策 | ○ 仅 partial | missing | **C** | partial fallback (uncategorized) |
| `L0.policy.tax_trade` | 税收/出口限制 | ○ 仅 partial | missing | **C** | partial fallback (uncategorized) |
| `L0.price.contract_spot` | 合同价/现货价价差 | ○ 仅 partial | missing | **C** | partial fallback (uncategorized) |
| `L0.price.discount` | 行业折扣力度 | ✗ 完全缺失 | OverlayKnown | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.price.pricing_power` | 行业提价能力 | ✗ 完全缺失 | OverlayKnown | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.price.product_asp` | 行业产品价格/ASP | ○ 仅 partial | missing | **C** | partial fallback (uncategorized) |
| `L0.sentiment.institutional` | 机构配置 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L0.sentiment.leader_drag` | 龙头带动 | ✓✓ 多源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L0.sentiment.sector_heat` | 板块热度/ETF流入 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L0.sentiment.social` | 社媒/主题热度 | ✓✓ 多源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L0.supply.capacity` | 行业产能变化 | ✗ 完全缺失 | OverlayKnown | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.supply.chain_eff` | 供应链效率/人力供给 | ✗ 完全缺失 | OverlayKnown | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.supply.channel_service` | 行业渠道/服务供给 | ✗ 完全缺失 | OverlayKnown | **C** | 行业级画像; LLM + 龙头 IR 业绩会 + 行业框架 prior; 已在 industry_overlays 试填 |
| `L0.supply.inventory` | 行业库存变化 | ○ 仅 partial | missing | **C** | partial fallback (uncategorized) |
| `L0.tech.ai_automation` | AI/自动化/降本 | ○ 仅 partial | missing | **C** | partial fallback (uncategorized) |
| `L0.tech.breakthrough` | 技术突破/产品迭代 | ○ 仅 partial | missing | **C** | partial fallback (uncategorized) |
| `L0.tech.substitute_tech` | 替代技术 | ○ 仅 partial | missing | **C** | partial fallback (uncategorized) |

### 2.2 L1 公司定位（12）

| dp_id | 标签 | spec 覆盖 | 实测状态 | Bucket | 决策依据 |
|---|---|---|---|:-:|---|
| `L1.moat.tags` | 护城河标签 | ○ 仅 partial | missing | **C** | 分类标签; LLM + 行业框架 + 多源 partial 收敛 |
| `L1.model.tag` | 商业模式标签 | ○ 仅 partial | missing | **C** | 分类标签; LLM + 行业框架 + 多源 partial 收敛 |
| `L1.position.brand` | 品牌影响力 | ○ 仅 partial | missing | **C** | 公司定位叙事; LLM + 年报 + IR |
| `L1.position.channel_edge` | 渠道优势 | ✗ 完全缺失 | OverlayKnown | **C** | 公司定位; IR 问答 + 年报渠道章节 + 同业对比 |
| `L1.position.cost_edge` | 成本优势 | ○ 仅 partial | missing | **C** | 公司定位叙事; LLM + 年报 + IR |
| `L1.position.growth_rank` | 增速排名 | ○ 仅 partial | missing | **C** | 公司定位叙事; LLM + 年报 + IR |
| `L1.position.market_share` | 公司市占率 | ○ 仅 partial | missing | **C** | 公司定位叙事; LLM + 年报 + IR |
| `L1.position.pricing_power` | 定价权 | ○ 仅 partial | missing | **C** | 公司定位叙事; LLM + 年报 + IR |
| `L1.position.stickiness` | 客户粘性 | ✗ 完全缺失 | OverlayKnown | **C** | 公司定位; IR 问答 + 年报渠道章节 + 同业对比 |
| `L1.position.tech_barrier` | 技术壁垒 | ○ 仅 partial | missing | **C** | 公司定位叙事; LLM + 年报 + IR |
| `L1.role.tag` | 行业角色标签 | ○ 仅 partial | missing | **C** | 分类标签; LLM + 行业框架 + 多源 partial 收敛 |
| `L1.stock_attr.tags` | 股价属性标签 | ○ 仅 partial | missing | **C** | 分类标签; LLM + 行业框架 + 多源 partial 收敛 |

### 2.3 L2 业务结构（14）

| dp_id | 标签 | spec 覆盖 | 实测状态 | Bucket | 决策依据 |
|---|---|---|---|:-:|---|
| `L2.newbiz.commercialization` | 新业务商业化进度 | ○ 仅 partial | missing | **C** | 业务线叙事; LLM + 年报分部章节 |
| `L2.newbiz.revenue_contrib` | 新业务收入/利润贡献 | ○ 仅 partial | missing | **C** | 业务线叙事; LLM + 年报分部章节 |
| `L2.newbiz.tam` | 新业务市场空间 | ✗ 完全缺失 | OverlayKnown | **D** | TAM 需要外部行业研报(IDC/Gartner/Counterpoint); 公司披露不完整 |
| `L2.newbiz.uncertainty` | 新业务不确定性 | ✗ 完全缺失 | OverlayKnown | **C** | IR + roadmap 公告 + 行业框架 |
| `L2.newbiz.valuation_contrib` | 新业务估值贡献 | ○ 仅 partial | missing | **C** | 业务线叙事; LLM + 年报分部章节 |
| `L2.segment.business_risk` | 业务线业务风险 | ○ 仅 partial | missing | **C** | 业务线叙事; LLM + 年报分部章节 |
| `L2.segment.cash_contrib` | 业务线现金流贡献 | ○ 仅 partial | missing | **C** | 业务线叙事; LLM + 年报分部章节 |
| `L2.segment.compete_landscape` | 业务线竞争格局 | ○ 仅 partial | missing | **C** | 业务线叙事; LLM + 年报分部章节 |
| `L2.segment.gross_margin` | 业务线毛利率 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L2.segment.growth` | 业务线增速 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L2.segment.industry_exposure` | 业务线行业暴露度 | ○ 仅 partial | missing | **C** | 业务线叙事; LLM + 年报分部章节 |
| `L2.segment.opex_ratio` | 业务线费用率 | ○ 仅 partial | missing | **C** | 业务线叙事; LLM + 年报分部章节 |
| `L2.segment.profit_share` | 业务线利润占比 | ○ 仅 partial | missing | **C** | 业务线叙事; LLM + 年报分部章节 |
| `L2.segment.revenue_share` | 业务线收入占比 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |

### 2.4 L3 产品/客户/渠道/区域（18）

| dp_id | 标签 | spec 覆盖 | 实测状态 | Bucket | 决策依据 |
|---|---|---|---|:-:|---|
| `L3.channel.cost` | 渠道费用 | ○ 仅 partial | missing | **C** | 产品/客户/渠道/区域结构叙事; LLM + 年报分项 |
| `L3.channel.efficiency` | 渠道效率 | ○ 仅 partial | missing | **C** | 产品/客户/渠道/区域结构叙事; LLM + 年报分项 |
| `L3.channel.mix` | 渠道结构占比 | ✗ 完全缺失 | OverlayKnown | **C** | 年报销售渠道章节明确披露 |
| `L3.channel.overseas` | 海外渠道 | ○ 仅 partial | missing | **C** | 产品/客户/渠道/区域结构叙事; LLM + 年报分项 |
| `L3.customer.concentration` | 客户集中度/流失风险 | ○ 仅 partial | missing | **C** | 产品/客户/渠道/区域结构叙事; LLM + 年报分项 |
| `L3.customer.segment_mix` | 客户类型结构 | ✗ 完全缺失 | OverlayKnown | **C** | 年报客户/segment 占比披露 |
| `L3.customer.solvency` | 客户支付能力 | ○ 仅 partial | missing | **C** | 产品/客户/渠道/区域结构叙事; LLM + 年报分项 |
| `L3.delivery.capacity_supply` | 产能/供应链 | ○ 仅 partial | missing | **C** | 产品/客户/渠道/区域结构叙事; LLM + 年报分项 |
| `L3.delivery.csat` | 客户满意度 | ✗ 完全缺失 | OverlayKnown | **D** | CSAT/NPS 多来自三方调研(App 评分、Trustpilot 等聚合) |
| `L3.delivery.fulfillment_cost` | 履约/售后成本 | ○ 仅 partial | missing | **C** | 产品/客户/渠道/区域结构叙事; LLM + 年报分项 |
| `L3.delivery.lead_time` | 交付周期/服务能力 | ✗ 完全缺失 | OverlayKnown | **D** | 服务运营细节披露不一致; 需要渠道调研 |
| `L3.product.lifecycle` | 产品生命周期/竞争力 | ✗ 完全缺失 | OverlayKnown | **D** | 产品生命周期阶段需要券商行业研报或专业分析 |
| `L3.product.margin_mix` | 产品毛利/价格结构 | ○ 仅 partial | missing | **C** | 产品/客户/渠道/区域结构叙事; LLM + 年报分项 |
| `L3.product.portfolio` | 产品组合结构 | ○ 仅 partial | missing | **C** | 产品/客户/渠道/区域结构叙事; LLM + 年报分项 |
| `L3.region.domestic_overseas` | 国内/海外收入结构 | ○ 仅 partial | missing | **C** | 产品/客户/渠道/区域结构叙事; LLM + 年报分项 |
| `L3.region.fx_geo` | 汇率/地缘影响 | ○ 仅 partial | missing | **C** | 产品/客户/渠道/区域结构叙事; LLM + 年报分项 |
| `L3.region.key_risk` | 重点/高风险区域 | ○ 仅 partial | missing | **C** | 产品/客户/渠道/区域结构叙事; LLM + 年报分项 |
| `L3.region.tier_mix` | 城市层级结构 | ✗ 完全缺失 | OverlayKnown | **C** | 年报区域分项披露 |

### 2.5 L4 经营层（23）

| dp_id | 标签 | spec 覆盖 | 实测状态 | Bucket | 决策依据 |
|---|---|---|---|:-:|---|
| `L4.cost.cac_production` | 获客/单位生产成本 | ○ 仅 partial | missing | **C** | 运营软指标; 混合硬数据 + IR 叙事 |
| `L4.cost.labor` | 人工成本 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L4.cost.raw_material` | 原材料成本 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L4.cost.rent_energy_logistics` | 租金/能源/物流成本 | ○ 仅 partial | missing | **C** | 运营软指标; 混合硬数据 + IR 叙事 |
| `L4.eff.capacity_utilization` | 产能利用率 | ✗ 完全缺失 | OverlayKnown | **C** | 年报 + 业绩会披露产能利用率 |
| `L4.eff.conversion_retention` | 转化率/留存/复购 | ✗ 完全缺失 | OverlayKnown | **D** | 用户行为指标; 业绩会不规律披露; 三方用户调研 |
| `L4.eff.cycle` | 现金转换周期 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L4.eff.store_labor` | 门店坪效/人效 | ○ 仅 partial | missing | **C** | 运营软指标; 混合硬数据 + IR 叙事 |
| `L4.eff.turnover` | 库存/应收账款周转 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L4.price.asp_aov_arpu` | ASP/客单价/ARPU | ○ 仅 partial | missing | **C** | 运营软指标; 混合硬数据 + IR 叙事 |
| `L4.price.discount` | 折扣率 | ✗ 完全缺失 | OverlayKnown | **C** | IR + 电商/渠道调研, 可观察数据 |
| `L4.price.elasticity` | 价格弹性 | ○ 仅 partial | missing | **C** | 运营软指标; 混合硬数据 + IR 叙事 |
| `L4.price.pricing_power` | 提价能力 | ○ 仅 partial | missing | **C** | 运营软指标; 混合硬数据 + IR 叙事 |
| `L4.price.subscription` | 订阅价格 | ✗ 完全缺失 | OverlayKnown | **C** | 公司公告 + 定价页 + IR |
| `L4.share.customer_channel` | 客户/渠道/区域份额 | ✗ 完全缺失 | OverlayKnown | **D** | 细分市占率来自 IDC/Counterpoint/IHS 等付费研究 |
| `L4.share.market` | 公司市占率 | ○ 仅 partial | missing | **C** | 运营软指标; 混合硬数据 + IR 叙事 |
| `L4.share.substitution` | 竞品替代 | ○ 仅 partial | missing | **C** | 运营软指标; 混合硬数据 + IR 叙事 |
| `L4.volume.foot_traffic` | 门店客流 | ✗ 完全缺失 | OverlayKnown | **D** | 客流量来自三方零售面板(Sensormatic、AzureSpace、店里店外) |
| `L4.volume.frequency` | 使用频次 | ✗ 完全缺失 | OverlayKnown | **D** | 使用频次来自三方 App 分析(QuestMobile、Sensor Tower、AppAnnie) |
| `L4.volume.orders` | 订单量 | ○ 仅 partial | missing | **C** | 运营软指标; 混合硬数据 + IR 叙事 |
| `L4.volume.sales` | 销量 | ○ 仅 partial | missing | **C** | 运营软指标; 混合硬数据 + IR 叙事 |
| `L4.volume.shipments` | 出货量/交付量 | ○ 仅 partial | missing | **C** | 运营软指标; 混合硬数据 + IR 叙事 |
| `L4.volume.users` | 客户/用户数 | ○ 仅 partial | missing | **C** | 运营软指标; 混合硬数据 + IR 叙事 |

### 2.6 L5 财务（28）

| dp_id | 标签 | spec 覆盖 | 实测状态 | Bucket | 决策依据 |
|---|---|---|---|:-:|---|
| `L5.bs.ar_ap` | 应收/应付账款 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.bs.cash_debt` | 现金/有息负债 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.bs.goodwill_ppe` | 商誉/固定资产 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.bs.inventory` | 存货 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.bs.leverage` | 资产负债率 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.cf.buyback_dividend` | 回购/分红 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.cf.capex` | Capex | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.cf.fcf` | 自由现金流 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.cf.icf_fcf` | 投资/融资现金流 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.cf.ocf` | 经营现金流 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.fcst.beat_probability` | 业绩兑现概率 | ○ 仅 partial | missing | **C** | 分析师预期/超预期; Tushare ✓ 部分; LLM fallback |
| `L5.fcst.eps_cf` | EPS/现金流预期 | ✓ 单源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.fcst.guidance_change` | 公司指引变化 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.fcst.revenue_margin` | 收入/毛利率预期 | ✓ 单源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.fcst.revisions` | 分析师上修/下修 | ✓ 单源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.is.eps` | EPS | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.is.gross_margin` | 毛利率 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.is.gross_profit` | 毛利 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.is.margins` | 经营/净利率 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.is.net_profit` | 净利润 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.is.operating_profit` | 经营利润 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.is.revenue` | 收入 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.is.revenue_growth` | 收入增速 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.is.sga_rd` | 三费(销售/管理/研发) | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.surprise.beat_miss` | 超预期/低于预期幅度 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.surprise.buy_whisper` | 买方/whisper预期 | ✗ 完全缺失 | OverlayKnown | **E** | buy-side whisper 需要付费 alt-data feed; LLM/web 都无稳定来源 |
| `L5.surprise.preprice` | 股价提前反应 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L5.surprise.sell_side` | 卖方一致预期 | ✓ 单源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |

### 2.7 L6 估值定价（26）

| dp_id | 标签 | spec 覆盖 | 实测状态 | Bucket | 决策依据 |
|---|---|---|---|:-:|---|
| `L6.mult.dcf` | DCF估值 | ○ 仅 partial | SQLite | **E** | FMP Premium ($) 才解锁; 无其他源 full |
| `L6.mult.ev_ebitda` | EV/EBITDA | ✓ 单源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.mult.forward_pe` | Forward PE | ○ 仅 partial | missing | **E** | FMP Premium ($) 才解锁; 无其他源 full |
| `L6.mult.mcap_fcf` | 市值/FCF | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.mult.pb` | PB | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.mult.pe` | PE | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.mult.peg` | PEG | ○ 仅 partial | SQLite | **B** | 估值状态/路径/敏感性派生自 L6 multiples + 历史 |
| `L6.mult.ps` | PS | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.path.second_derivative` | 二阶导变差 | ○ 仅 partial | SQLite | **B** | 估值路径标签派生自 L6 multiples + 历史轨迹 |
| `L6.path.tag` | 估值路径标签 | ○ 仅 partial | SQLite | **B** | 估值路径标签派生自 L6 multiples + 历史轨迹 |
| `L6.priced.analyst_revision` | 分析师上修程度 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.priced.crowdedness` | 资金拥挤度 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.priced.discussion` | 市场讨论热度 | ✓✓ 多源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.priced.iv` | 期权隐含波动 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.priced.news_age` | 新闻传播时间 | ✓ 单源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.priced.realization_risk` | 利好兑现风险 | ○ 仅 partial | missing | **B** | 估值状态/路径/敏感性派生自 L6 multiples + 历史 |
| `L6.priced.run_up` | 股价提前涨幅 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.sens.cashflow` | 对现金流敏感 | ○ 仅 partial | SQLite | **B** | 敏感性派生自财务+市场 raw |
| `L6.sens.growth_margin` | 对收入/利润率敏感 | ○ 仅 partial | SQLite | **B** | 敏感性派生自财务+市场 raw |
| `L6.sens.rates` | 对利率敏感 | ○ 仅 partial | SQLite | **B** | 敏感性派生自财务+市场 raw |
| `L6.sens.risk_narrative` | 对风险偏好/叙事敏感 | ○ 仅 partial | SQLite | **B** | 敏感性派生自财务+市场 raw |
| `L6.state.expansion_compression` | 估值扩张/压缩空间 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.state.historical_percentile` | 历史估值分位 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.state.industry_center` | 行业估值中枢 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.state.peer_compare` | 同业估值对比 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L6.state.peg_match` | 估值与增速匹配度 | ○ 仅 partial | missing | **B** | 估值状态/路径/敏感性派生自 L6 multiples + 历史 |

### 2.8 L7 资金情绪宏观（21）

| dp_id | 标签 | spec 覆盖 | 实测状态 | Bucket | 决策依据 |
|---|---|---|---|:-:|---|
| `L7.env.fx` | 汇率 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.env.liquidity` | 流动性 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.env.market_trend` | 大盘/行业指数趋势 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.env.rates` | 利率 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.env.risk_appetite` | 风险偏好 | ○ 仅 partial | SQLite | **B** | 资金/情绪派生自 L7 raw flow |
| `L7.env.style` | 市场风格 | ○ 仅 partial | SQLite | **B** | 资金/情绪派生自 L7 raw flow |
| `L7.flow.active_inflow` | 主动资金流入 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.flow.block_trade` | 大宗交易 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.flow.etf_inflow` | ETF流入 | ✓ 单源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.flow.institutional` | 机构/对冲基金持仓 | ○ 仅 partial | SQLite | **E** | FMP Premium ($) 才解锁; 无其他源 full |
| `L7.flow.passive_northbound` | 被动资金/外资 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.mood.analyst_rating` | 分析师评级分布 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.mood.fomo` | FOMO程度 | ○ 仅 partial | SQLite | **B** | FOMO 派生自 L7 turnover + L6 priced run-up |
| `L7.mood.media_social` | 媒体/社媒热度 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.mood.theme` | 主题热度 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.reflex.tag` | 反身性环节标签 | ○ 仅 partial | missing | **B** | 反身性标签派生自 L7 资金 + L6 priced 信号 |
| `L7.trade.gamma` | Gamma暴露 | ○ 仅 partial | missing | **E** | FMP Premium ($) 才解锁; 无其他源 full |
| `L7.trade.iv` | 隐含波动率 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.trade.margin_short` | 融资融券/空头 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.trade.options_cp` | 期权Call/Put | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L7.trade.volume_turnover` | 成交量/换手率 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |

### 2.9 L8 风险抵消（32）

| dp_id | 标签 | spec 覆盖 | 实测状态 | Bucket | 决策依据 |
|---|---|---|---|:-:|---|
| `L8.cap.crowdedness` | 资金拥挤 | ✓✓ 多源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.cap.liquidity_short` | 流动性不足 | ✓✓ 多源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.cap.outflow_cut` | ETF流出/机构减仓 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.cap.short_increase` | 空头增加 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.fin.cash_ar` | 现金流/应收账款恶化 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.fin.debt_pressure` | 债务压力 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.fin.eps_downward` | EPS下修 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.fin.goodwill_impairment` | 商誉减值 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.fin.revenue_profit_miss` | 收入/利润低于预期 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.gov.fraud_control` | 财务造假/内控 | ○ 仅 partial | missing | **C** | 治理风险叙事; LLM + 公告 + 法律新闻 |
| `L8.gov.insider_sell` | 股东减持 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.gov.litigation` | 法律诉讼 | ○ 仅 partial | missing | **C** | 治理风险叙事; LLM + 公告 + 法律新闻 |
| `L8.gov.management_change` | 管理层变动 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.industry.demand_supply` | 行业需求/供给恶化 | ○ 仅 partial | SQLite | **C** | 行业风险叙事; LLM + 行业新闻 + 政策文本 |
| `L8.industry.price_war` | 行业价格战 | ○ 仅 partial | SQLite | **C** | 行业风险叙事; LLM + 行业新闻 + 政策文本 |
| `L8.industry.substitute` | 替代品出现 | ○ 仅 partial | missing | **C** | 行业风险叙事; LLM + 行业新闻 + 政策文本 |
| `L8.industry.valuation_compression` | 行业估值压缩 | ✓✓ 多源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.op.cost_overrun` | 成本失控 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.op.customer_channel` | 客户流失/渠道失效 | ○ 仅 partial | missing | **C** | 运营风险叙事; LLM + 业绩会 + 公告 |
| `L8.op.inventory_glut` | 库存积压 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.op.order_miss` | 订单不兑现 | ○ 仅 partial | missing | **C** | 运营风险叙事; LLM + 业绩会 + 公告 |
| `L8.op.product_fail` | 产品失败 | ○ 仅 partial | missing | **C** | 运营风险叙事; LLM + 业绩会 + 公告 |
| `L8.reg.license_risk` | 牌照/准入风险 | ○ 仅 partial | missing | **C** | 监管风险叙事; LLM + 政策/法规文本 |
| `L8.reg.subsidy_off` | 补贴退坡 | ○ 仅 partial | missing | **C** | 监管风险叙事; LLM + 政策/法规文本 |
| `L8.reg.tax_trade` | 税收/出口限制 | ○ 仅 partial | missing | **C** | 监管风险叙事; LLM + 政策/法规文本 |
| `L8.reg.tighten` | 监管收紧/反垄断 | ○ 仅 partial | missing | **C** | 监管风险叙事; LLM + 政策/法规文本 |
| `L8.shock.black_swan` | 黑天鹅事件 | ○ 仅 partial | missing | **C** | 冲击事件叙事; LLM + 实时新闻分类 |
| `L8.shock.crisis` | 安全/舆情危机 | ○ 仅 partial | missing | **C** | 冲击事件叙事; LLM + 实时新闻分类 |
| `L8.shock.supply_break` | 供应中断/客户违约/自然灾害 | ○ 仅 partial | missing | **C** | 冲击事件叙事; LLM + 实时新闻分类 |
| `L8.val.overvalued` | 估值过高 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L8.val.priced_in` | 利好已定价/兑现 | ○ 仅 partial | SQLite | **B** | 估值风险派生自 L6 分位 + 价格行为 |
| `L8.val.slope_risk_off` | 增长斜率下降/风险偏好下降 | ○ 仅 partial | missing | **B** | 估值风险派生自 L6 分位 + 价格行为 |

### 2.10 L9 催化剂（20）

| dp_id | 标签 | spec 覆盖 | 实测状态 | Bucket | 决策依据 |
|---|---|---|---|:-:|---|
| `L9.capital.etf_block` | ETF调整/大宗交易 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L9.capital.inst_buy_sell` | 机构增持/减持 | ✓ 单源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L9.capital.margin_anomaly` | 融资/期权/空头异动 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L9.company.buyback_dividend` | 回购/分红 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L9.company.earnings_guidance` | 财报/预告/指引 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L9.company.ma` | 并购 | ○ 仅 partial | missing | **C** | 事件/新闻分类; LLM + L9 news flow |
| `L9.company.mgmt_litigation` | 管理层变化/诉讼 | ✓ 单源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L9.company.product_order` | 新产品发布/大订单 | ○ 仅 partial | missing | **C** | 事件/新闻分类; LLM + L9 news flow |
| `L9.industry.compete_risk` | 行业竞争/风险事件 | ○ 仅 partial | SQLite | **C** | 事件/新闻分类; LLM + L9 news flow |
| `L9.industry.data_price` | 行业数据/价格发布 | ○ 仅 partial | missing | **C** | 事件/新闻分类; LLM + L9 news flow |
| `L9.industry.policy_change` | 行业政策变化 | ○ 仅 partial | SQLite | **C** | 事件/新闻分类; LLM + L9 news flow |
| `L9.macro.cpi_employment` | 通胀/就业数据 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L9.macro.fx` | 汇率变化 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L9.macro.geo` | 地缘事件 | ○ 仅 partial | missing | **C** | 事件/新闻分类; LLM + L9 news flow |
| `L9.macro.liquidity` | 流动性变化 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L9.macro.rates` | 利率变化 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L9.media.analyst_action` | 分析师评级/研报变动 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L9.media.report` | 媒体报道 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L9.media.short_report` | 做空报告 | ○ 仅 partial | missing | **C** | 事件/新闻分类; LLM + L9 news flow |
| `L9.media.social_buzz` | 社媒发酵 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |

### 2.11 L10 验证指标（7）

| dp_id | 标签 | spec 覆盖 | 实测状态 | Bucket | 决策依据 |
|---|---|---|---|:-:|---|
| `L10.industry.fund_flow` | 行业资金流验证 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L10.industry.inventory_orders` | 行业库存/订单验证 | ○ 仅 partial | missing | **A** | 验证指标; Tushare/AKShare full; partial 是因 FMP 不全 |
| `L10.industry.pmi` | 行业景气指数 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L10.industry.sales_price` | 行业销量/价格验证 | ○ 仅 partial | missing | **A** | 验证指标; Tushare/AKShare full; partial 是因 FMP 不全 |
| `L10.val.expansion_compression` | 估值扩张/压缩方向 | ✓ 单源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L10.val.historical_quantile` | 估值历史分位 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L10.val.peer` | 同业估值 | ✓ 单源覆盖 | missing | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |

### 2.12 L11 股价结果（16）

| dp_id | 标签 | spec 覆盖 | 实测状态 | Bucket | 决策依据 |
|---|---|---|---|:-:|---|
| `L11.long.business_model` | 商业模式稳定性 | ○ 仅 partial | SQLite | **B** | L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合 |
| `L11.long.compete_moat` | 竞争格局/护城河 | ○ 仅 partial | SQLite | **B** | L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合 |
| `L11.long.industry_space` | 行业空间 | ○ 仅 partial | SQLite | **B** | L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合 |
| `L11.long.margin` | 长期利润率 | ✓ 单源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L11.long.score` | 长线综合影响分 | ○ 仅 partial | SQLite | **B** | 派生分数/信号; graph-engine 由 L0-L9 上游分数链式聚合 |
| `L11.mid.eps_upward` | EPS上修中线 | ✓ 单源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L11.mid.margin_guidance` | 毛利率/指引中线影响 | ○ 仅 partial | SQLite | **B** | L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合 |
| `L11.mid.orders_revenue` | 订单/收入中线影响 | ○ 仅 partial | SQLite | **B** | L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合 |
| `L11.mid.score` | 1-2季度综合影响分 | ○ 仅 partial | SQLite | **B** | 派生分数/信号; graph-engine 由 L0-L9 上游分数链式聚合 |
| `L11.mode` | 当前模式状态 | ○ 仅 partial | SQLite | **B** | 派生分数/信号; graph-engine 由 L0-L9 上游分数链式聚合 |
| `L11.short.event_impact` | 事件冲击分 | ○ 仅 partial | SQLite | **B** | L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合 |
| `L11.short.flow_boost` | 资金放大分 | ○ 仅 partial | SQLite | **B** | L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合 |
| `L11.short.score` | 1-5日综合影响分 | ○ 仅 partial | SQLite | **B** | 派生分数/信号; graph-engine 由 L0-L9 上游分数链式聚合 |
| `L11.short.sentiment_shift` | 情绪变化分 | ○ 仅 partial | SQLite | **B** | L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合 |
| `L11.short.technical` | 技术面反应 | ✓✓ 多源覆盖 | SQLite | **A** | spec 已 ✓ — 多源/单源 full 直取硬数据 |
| `L11.trade.signal` | 交易意义信号 | ○ 仅 partial | SQLite | **B** | 派生分数/信号; graph-engine 由 L0-L9 上游分数链式聚合 |

---

## 3. 按 bucket 详细分析

### 3.A bucket A — closed-hard（106 个，42.4%）

> **定义**：spec coverage_audit §7 总评 ✓ 单源 full 或 ✓✓ 多源 full；现接 5 源（FMP / Tushare / AKShare / yfinance / Futu）任一源能直接出值。

**实测**：106 个中 73 个已在 SQLite `realtime_current` 落库（69%）；33 个 spec ✓ 但 SQLite 还没 emit。

**33 个 spec ✓ 但还没 emit 的 dp_id**：

- `L0.cost.capital` — 行业资金成本 (spec: ✓ 单源覆盖)
- `L0.sentiment.institutional` — 机构配置 (spec: ✓ 单源覆盖)
- `L0.sentiment.leader_drag` — 龙头带动 (spec: ✓✓ 多源覆盖)
- `L0.sentiment.social` — 社媒/主题热度 (spec: ✓✓ 多源覆盖)
- `L10.industry.inventory_orders` — 行业库存/订单验证 (spec: ○ 仅 partial)
- `L10.industry.sales_price` — 行业销量/价格验证 (spec: ○ 仅 partial)
- `L10.val.peer` — 同业估值 (spec: ✓ 单源覆盖)
- `L2.segment.gross_margin` — 业务线毛利率 (spec: ✓ 单源覆盖)
- `L2.segment.growth` — 业务线增速 (spec: ✓ 单源覆盖)
- `L2.segment.revenue_share` — 业务线收入占比 (spec: ✓ 单源覆盖)
- `L5.fcst.guidance_change` — 公司指引变化 (spec: ✓ 单源覆盖)
- `L5.surprise.beat_miss` — 超预期/低于预期幅度 (spec: ✓ 单源覆盖)
- `L6.priced.analyst_revision` — 分析师上修程度 (spec: ✓ 单源覆盖)
- `L6.priced.discussion` — 市场讨论热度 (spec: ✓✓ 多源覆盖)
- `L6.priced.iv` — 期权隐含波动 (spec: ✓ 单源覆盖)
- `L6.state.expansion_compression` — 估值扩张/压缩空间 (spec: ✓ 单源覆盖)
- `L6.state.industry_center` — 行业估值中枢 (spec: ✓ 单源覆盖)
- `L6.state.peer_compare` — 同业估值对比 (spec: ✓ 单源覆盖)
- `L7.mood.analyst_rating` — 分析师评级分布 (spec: ✓ 单源覆盖)
- `L7.trade.iv` — 隐含波动率 (spec: ✓ 单源覆盖)
- `L7.trade.options_cp` — 期权Call/Put (spec: ✓ 单源覆盖)
- `L8.cap.crowdedness` — 资金拥挤 (spec: ✓✓ 多源覆盖)
- `L8.cap.liquidity_short` — 流动性不足 (spec: ✓✓ 多源覆盖)
- `L8.cap.outflow_cut` — ETF流出/机构减仓 (spec: ✓ 单源覆盖)
- `L8.cap.short_increase` — 空头增加 (spec: ✓ 单源覆盖)
- `L8.fin.eps_downward` — EPS下修 (spec: ✓ 单源覆盖)
- `L8.fin.goodwill_impairment` — 商誉减值 (spec: ✓ 单源覆盖)
- `L8.fin.revenue_profit_miss` — 收入/利润低于预期 (spec: ✓ 单源覆盖)
- `L8.industry.valuation_compression` — 行业估值压缩 (spec: ✓✓ 多源覆盖)
- `L8.op.cost_overrun` — 成本失控 (spec: ✓ 单源覆盖)
- `L9.capital.etf_block` — ETF调整/大宗交易 (spec: ✓ 单源覆盖)
- `L9.capital.margin_anomaly` — 融资/期权/空头异动 (spec: ✓ 单源覆盖)
- `L9.media.analyst_action` — 分析师评级/研报变动 (spec: ✓ 单源覆盖)

**A 没 emit 的根因（按现状推断）**：

- **行业级 L0.*** 部分字段（如 `L0.cost.capital`、`L0.sentiment.*`）— 行业级 fetcher 还没全接，需要按 industry_id 实例化
- **L2.segment.*** 三个 ✓ 字段（Tushare 分部数据）— Tushare `fina_indicator` 已抓但 dp_id 没 alias 到这三个字段
- **L4.cost.raw_material / labor / eff.turnover / eff.cycle** — `L4.cost.*` 已 emit（去重不算），但 alias 表可能漏映射
- **L5.fcst.*** 单源 ✓ 全部依赖 Tushare 分析师预期接口（`forecast` / `report_rc`），fetcher 尚未实现
- **L8.gov.management_change / insider_sell** 多源 full 但需要 alias 到 disclosure / insider trades 接口
- **L9.media.report / L9.macro.cpi_employment / L9.company.earnings_guidance** — 多源 full 但 alias 链不完整
- **L11.short.technical** — Futu/FMP K 线 + 指标都全，需要 derive 层算 RSI/MA 等再回写

**推荐 next action**（A bucket，X4 主线）：

1. 跑 `scripts/audit_dp_alias.py`（如不存在则建一个）：对 A bucket 33 个 missing 跑 reverse-mapping 检查现有 fetcher 是否产值但 dp_id 没正确 alias
2. 补 Tushare 分析师预期 fetcher（5 个 L5.fcst.* + L5.surprise.sell_side / beat_miss）
3. 行业级 dp_id 批量实例化（L0.sentiment.* / L0.cost.capital）— 按 industry_id 12 个分别 emit
4. derive 层补 L11.short.technical 与 L9 媒体/宏观字段

### 3.B bucket B — closed-derived（28 个，11.2%）

> **定义**：spec coverage_audit 仅 ○ partial，但语义上是 raw 数据的派生（计算/聚合/打分/标签）；graph-engine X4 derive 层能算。

**全部 28 个字段（按 layer）**：

**L6**（9）：
- `L6.mult.peg` — PEG：估值状态/路径/敏感性派生自 L6 multiples + 历史
- `L6.state.peg_match` — 估值与增速匹配度：估值状态/路径/敏感性派生自 L6 multiples + 历史
- `L6.priced.realization_risk` — 利好兑现风险：估值状态/路径/敏感性派生自 L6 multiples + 历史
- `L6.sens.growth_margin` — 对收入/利润率敏感：敏感性派生自财务+市场 raw
- `L6.sens.cashflow` — 对现金流敏感：敏感性派生自财务+市场 raw
- `L6.sens.rates` — 对利率敏感：敏感性派生自财务+市场 raw
- `L6.sens.risk_narrative` — 对风险偏好/叙事敏感：敏感性派生自财务+市场 raw
- `L6.path.tag` — 估值路径标签：估值路径标签派生自 L6 multiples + 历史轨迹
- `L6.path.second_derivative` — 二阶导变差：估值路径标签派生自 L6 multiples + 历史轨迹

**L7**（4）：
- `L7.mood.fomo` — FOMO程度：FOMO 派生自 L7 turnover + L6 priced run-up
- `L7.env.risk_appetite` — 风险偏好：资金/情绪派生自 L7 raw flow
- `L7.env.style` — 市场风格：资金/情绪派生自 L7 raw flow
- `L7.reflex.tag` — 反身性环节标签：反身性标签派生自 L7 资金 + L6 priced 信号

**L8**（2）：
- `L8.val.priced_in` — 利好已定价/兑现：估值风险派生自 L6 分位 + 价格行为
- `L8.val.slope_risk_off` — 增长斜率下降/风险偏好下降：估值风险派生自 L6 分位 + 价格行为

**L11**（13）：
- `L11.short.event_impact` — 事件冲击分：L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合
- `L11.short.flow_boost` — 资金放大分：L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合
- `L11.short.sentiment_shift` — 情绪变化分：L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合
- `L11.short.score` — 1-5日综合影响分：派生分数/信号; graph-engine 由 L0-L9 上游分数链式聚合
- `L11.mid.orders_revenue` — 订单/收入中线影响：L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合
- `L11.mid.margin_guidance` — 毛利率/指引中线影响：L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合
- `L11.mid.score` — 1-2季度综合影响分：派生分数/信号; graph-engine 由 L0-L9 上游分数链式聚合
- `L11.long.industry_space` — 行业空间：L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合
- `L11.long.compete_moat` — 竞争格局/护城河：L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合
- `L11.long.business_model` — 商业模式稳定性：L11 结果分; graph-engine 从 L1-L9 contribution chain 聚合
- `L11.long.score` — 长线综合影响分：派生分数/信号; graph-engine 由 L0-L9 上游分数链式聚合
- `L11.mode` — 当前模式状态：派生分数/信号; graph-engine 由 L0-L9 上游分数链式聚合
- `L11.trade.signal` — 交易意义信号：派生分数/信号; graph-engine 由 L0-L9 上游分数链式聚合

**派生路径示例**：

```
L11.short.score = w1*L11.short.event_impact + w2*L11.short.flow_boost + w3*L11.short.sentiment_shift + w4*L11.short.technical
    ↑                ↑                          ↑                          ↑                              ↑
    derive 算总和    derive(L9事件分类→打分)     derive(L7资金流→打分)       derive(L7情绪→打分)            A bucket 已有 raw

L6.sens.rates = corr(equity_return, rate_change) over rolling N quarters
    ← 输入：L11 价格 ts + L9.macro.rates ts，全 A bucket

L6.path.tag ∈ {早周期 / 中周期 / 末端泡沫 / 估值修复} ← 多分类，输入 L6.mult.* 历史 + L6.priced.run_up

L7.mood.fomo = z_score(L7.trade.volume_turnover) + L6.priced.run_up + L8.cap.crowdedness
```

**实测 B bucket 状态**：24 已 emit / 4 missing（`L11.long.industry_space`, `L11.long.compete_moat`, `L11.long.business_model`, `L11.long.score`）— X4 contribution chain 长线分尚未实现。

**推荐 next action**（B bucket，X4 derive 主线）：

1. L11 长线 4 字段 derive：从 L1.position.* + L2.newbiz.* + L8.industry.* 聚合（依赖 C/D bucket 先填）
2. L6.sens.* 4 字段：跑 rolling correlation derive job（依赖 K 线 + 财务 + 宏观 ts，全 A 齐）
3. L11.mid.* 3 字段：依赖 L5.fcst.* 上游（A bucket 缺口需要先补）
4. L8.val.* / L8.cap.*：纯 L6 + L7 raw 派生，可立即上线

### 3.C bucket C — closed-llm（103 个，41.2%）← X5 核心战场

> **定义**：spec ✗ 完全缺失 或 ○ partial，且字段语义是文本叙事/分类/定性判断；LLM 用本地材料（IR 问答库、年报章节、业绩会纪要、行业 prior）即可填。

**实测状态**：21 已在 overlay yaml Known / 6 误标在 SQLite（可能是占位）/ 76 完全未填。

**已在 overlay 试填的 21 个**（验证 X5 prompt 可行性的 trial）：

- `L0.cost.cac` — 行业获客成本
- `L0.cost.rent` — 行业租金成本
- `L0.demand.frequency` — 消费频次变化
- `L0.demand.penetration` — 渗透率变化
- `L0.demand.replacement` — 替换周期变化
- `L0.demand.terminal` — 终端需求变化
- `L0.demand.user_count` — 用户/订单数量变化
- `L0.price.discount` — 行业折扣力度
- `L0.price.pricing_power` — 行业提价能力
- `L0.supply.capacity` — 行业产能变化
- `L0.supply.chain_eff` — 供应链效率/人力供给
- `L0.supply.channel_service` — 行业渠道/服务供给
- `L1.position.channel_edge` — 渠道优势
- `L1.position.stickiness` — 客户粘性
- `L2.newbiz.uncertainty` — 新业务不确定性
- `L3.channel.mix` — 渠道结构占比
- `L3.customer.segment_mix` — 客户类型结构
- `L3.region.tier_mix` — 城市层级结构
- `L4.eff.capacity_utilization` — 产能利用率
- `L4.price.discount` — 折扣率
- `L4.price.subscription` — 订阅价格

**已知 SQLite emit 误标 6 个**（应该是占位/alias，可能 dp_id 命名相似）：

- `L0.cost.energy_logistics` — 行业能源/物流成本（可能是 partial fetcher 落库的近似值，需 X5 复填）
- `L0.cost.raw_material` — 原材料价格（可能是 partial fetcher 落库的近似值，需 X5 复填）
- `L8.industry.demand_supply` — 行业需求/供给恶化（可能是 partial fetcher 落库的近似值，需 X5 复填）
- `L8.industry.price_war` — 行业价格战（可能是 partial fetcher 落库的近似值，需 X5 复填）
- `L9.industry.compete_risk` — 行业竞争/风险事件（可能是 partial fetcher 落库的近似值，需 X5 复填）
- `L9.industry.policy_change` — 行业政策变化（可能是 partial fetcher 落库的近似值，需 X5 复填）

**完全未填 76 个**（X5 之后扩展空间）：按 layer 分组：

**L0**（14）：
- `L0.supply.inventory` — 行业库存变化
- `L0.price.product_asp` — 行业产品价格/ASP
- `L0.price.contract_spot` — 合同价/现货价价差
- `L0.cost.labor` — 行业人工成本
- `L0.compete.share_concentration` — 市占率/集中度变化
- `L0.compete.price_war` — 行业价格战
- `L0.compete.new_entrant` — 新进入者/替代品
- `L0.policy.subsidy` — 行业补贴政策
- `L0.policy.regulation` — 监管/反垄断
- `L0.policy.access_license` — 准入与牌照
- `L0.policy.tax_trade` — 税收/出口限制
- `L0.tech.breakthrough` — 技术突破/产品迭代
- `L0.tech.ai_automation` — AI/自动化/降本
- `L0.tech.substitute_tech` — 替代技术

**L1**（10）：
- `L1.role.tag` — 行业角色标签
- `L1.model.tag` — 商业模式标签
- `L1.position.market_share` — 公司市占率
- `L1.position.growth_rank` — 增速排名
- `L1.position.brand` — 品牌影响力
- `L1.position.tech_barrier` — 技术壁垒
- `L1.position.cost_edge` — 成本优势
- `L1.position.pricing_power` — 定价权
- `L1.moat.tags` — 护城河标签
- `L1.stock_attr.tags` — 股价属性标签

**L2**（9）：
- `L2.segment.profit_share` — 业务线利润占比
- `L2.segment.opex_ratio` — 业务线费用率
- `L2.segment.cash_contrib` — 业务线现金流贡献
- `L2.segment.industry_exposure` — 业务线行业暴露度
- `L2.segment.compete_landscape` — 业务线竞争格局
- `L2.segment.business_risk` — 业务线业务风险
- `L2.newbiz.commercialization` — 新业务商业化进度
- `L2.newbiz.revenue_contrib` — 新业务收入/利润贡献
- `L2.newbiz.valuation_contrib` — 新业务估值贡献

**L3**（12）：
- `L3.product.portfolio` — 产品组合结构
- `L3.product.margin_mix` — 产品毛利/价格结构
- `L3.customer.concentration` — 客户集中度/流失风险
- `L3.customer.solvency` — 客户支付能力
- `L3.channel.overseas` — 海外渠道
- `L3.channel.cost` — 渠道费用
- `L3.channel.efficiency` — 渠道效率
- `L3.region.domestic_overseas` — 国内/海外收入结构
- `L3.region.key_risk` — 重点/高风险区域
- `L3.region.fx_geo` — 汇率/地缘影响
- `L3.delivery.capacity_supply` — 产能/供应链
- `L3.delivery.fulfillment_cost` — 履约/售后成本

**L4**（12）：
- `L4.volume.sales` — 销量
- `L4.volume.orders` — 订单量
- `L4.volume.users` — 客户/用户数
- `L4.volume.shipments` — 出货量/交付量
- `L4.price.asp_aov_arpu` — ASP/客单价/ARPU
- `L4.price.pricing_power` — 提价能力
- `L4.price.elasticity` — 价格弹性
- `L4.cost.rent_energy_logistics` — 租金/能源/物流成本
- `L4.cost.cac_production` — 获客/单位生产成本
- `L4.eff.store_labor` — 门店坪效/人效
- `L4.share.market` — 公司市占率
- `L4.share.substitution` — 竞品替代

**L5**（1）：
- `L5.fcst.beat_probability` — 业绩兑现概率

**L8**（13）：
- `L8.industry.substitute` — 替代品出现
- `L8.op.order_miss` — 订单不兑现
- `L8.op.product_fail` — 产品失败
- `L8.op.customer_channel` — 客户流失/渠道失效
- `L8.reg.tighten` — 监管收紧/反垄断
- `L8.reg.license_risk` — 牌照/准入风险
- `L8.reg.tax_trade` — 税收/出口限制
- `L8.reg.subsidy_off` — 补贴退坡
- `L8.gov.fraud_control` — 财务造假/内控
- `L8.gov.litigation` — 法律诉讼
- `L8.shock.crisis` — 安全/舆情危机
- `L8.shock.supply_break` — 供应中断/客户违约/自然灾害
- `L8.shock.black_swan` — 黑天鹅事件

**L9**（5）：
- `L9.industry.data_price` — 行业数据/价格发布
- `L9.company.product_order` — 新产品发布/大订单
- `L9.company.ma` — 并购
- `L9.media.short_report` — 做空报告
- `L9.macro.geo` — 地缘事件

**关键证据来源**（按字段类型）：

| 证据源 | 适用字段 | 已闭环 | 备注 |
|---|---|:-:|---|
| **年报 / 半年报全文** | L1 position, L2 segment, L3 customer/channel/region | ⚠ | 公司公告 raw 文本可批量爬到本地，但当前流程缺一步 RAG 索引 |
| **业绩会纪要 / 调研纪要** | L1 stickiness, L4 capacity/discount, L8 op risk | ✗ | 通常付费源或券商内部材料；闭环最难 |
| **行业 prior（codex 内置）** | L0.* 14 条行业字段 | ✓ | 已在 `industry_overlays/*.yaml` 实践 |
| **公开 IR 问答库** | L1, L3, L4 软指标 | ⚠ | 巨潮/SSE/SZSE 互动易已可抓，需 fetcher |
| **L9 新闻流原始文本** | L8.industry/shock/reg, L9 events | ⚠ | SQLite `realtime_current` 有 L9.event.news_flow，可作输入 |

**风险**（C bucket）：

1. **本地材料不全 → Known 率不达预期**：若 IR 库未抓取，预计 L1/L3/L4 字段 Known 率仅 30-50%
2. **行业 prior 主观性**：codex/X5 prompt 的行业判断是经验，会被反向影响（confirmation bias）；需要业绩会脚注校验
3. **数据时效**：年报落后 3-6 月，业绩会落后 1-2 月；LLM 输出时效性弱于 A bucket
4. **同一字段不同 industry 差异大**：L1.position.brand 在消费品（强品牌效应）vs B2B（弱）权重不同，prompt 模板要按 industry_id 分支

**推荐 next action**（C bucket，X5 战场）：

1. **先跑 trial**：X5 已并行的 26 个新字段（Group A 公司画像 + B 行业补 + C L4 软指标）跑完后，看 Known 率分布
2. **Known 率 > 60%** → 把 C bucket 76 个 missing 字段批量扩 prompt
3. **Known 率 < 40%** → 先补 IR 问答库 fetcher（接巨潮/SSE 互动易）再回跑
4. **每字段 evidence_quality 阈值**：< low 不接受落 Known（保持 Unknown + 触发人工 review）

### 3.D bucket D — web-llm（8 个，3.2%）← 用户提的 "未来开放 web search"

> **定义**：spec ✗ 完全缺失，且 C bucket 闭环材料判断不充分；必须让 LLM 跑外部 fetch（券商研报 / 第三方研究 / IR 站直读 / app 数据聚合）。

**全部 8 个字段**（已在 overlay 试填阶段，目前的 evidence_sources 应当已经有外部链接）：

- `L2.newbiz.tam` — 新业务市场空间：TAM 需要外部行业研报(IDC/Gartner/Counterpoint); 公司披露不完整
- `L3.delivery.csat` — 客户满意度：CSAT/NPS 多来自三方调研(App 评分、Trustpilot 等聚合)
- `L3.delivery.lead_time` — 交付周期/服务能力：服务运营细节披露不一致; 需要渠道调研
- `L3.product.lifecycle` — 产品生命周期/竞争力：产品生命周期阶段需要券商行业研报或专业分析
- `L4.eff.conversion_retention` — 转化率/留存/复购：用户行为指标; 业绩会不规律披露; 三方用户调研
- `L4.share.customer_channel` — 客户/渠道/区域份额：细分市占率来自 IDC/Counterpoint/IHS 等付费研究
- `L4.volume.foot_traffic` — 门店客流：客流量来自三方零售面板(Sensormatic、AzureSpace、店里店外)
- `L4.volume.frequency` — 使用频次：使用频次来自三方 App 分析(QuestMobile、Sensor Tower、AppAnnie)

**为什么必须 web 不能闭环**：

| dp_id | 闭环不够的原因 | 必需 web 源 |
|---|---|---|
| `L2.newbiz.tam` | 公司披露不全；TAM 数字来自 IDC/Gartner/Counterpoint/Frost | 三方付费研报摘要 / IDC 新闻稿 |
| `L3.product.lifecycle` | 生命周期阶段是相对判断，需要看券商行业研报视角 | 中信/中金/Goldman 行业 PDF |
| `L3.delivery.lead_time` | 服务运营细节披露不规律 | 渠道调研稿 / Reddit / 雪球用户反馈聚合 |
| `L3.delivery.csat` | CSAT/NPS 主要来自三方调研 | Trustpilot / Apple App Store / Google Play / 黑猫投诉 |
| `L4.volume.foot_traffic` | 客流量是付费零售面板（Sensormatic / Placer.ai / 极海/Fastdata） | 三方零售面板 free tier / 月报新闻稿 |
| `L4.volume.frequency` | App 行为指标 | QuestMobile / Sensor Tower / 七麦 free tier |
| `L4.eff.conversion_retention` | 用户行为指标，业绩会披露不规律 | 用户调研稿 / 三方 app 数据 |
| `L4.share.customer_channel` | 细分市占率来自付费机构研究 | IDC / Counterpoint / IHS / 中怡康 free release |

**推荐开通次序**（优先级 = 价值 × 可行性）：

**Top 10 候选（按优先开通建议）**：

| 排名 | dp_id | 价值 | 可行性 | 备注 |
|---:|---|:-:|:-:|---|
| 1 | `L2.newbiz.tam` | 高 | 高 | 新业务估值核心；公开 IDC/Gartner 新闻稿即可，技术风险低 |
| 2 | `L3.product.lifecycle` | 高 | 中 | 中线持仓判断核心；券商研报访问门槛中（部分公开） |
| 3 | `L4.share.customer_channel` | 高 | 中 | 竞争格局核心；IDC/Counterpoint 季度 release 部分公开 |
| 4 | `L3.delivery.csat` | 中 | 高 | 消费品/服务公司必要；Trustpilot/App Store 可结构化抓 |
| 5 | `L4.volume.foot_traffic` | 中 | 中 | 零售/餐饮专用；月度面板新闻稿即可 |
| 6 | `L4.eff.conversion_retention` | 中 | 中 | 互联网公司专用；业绩会摘要可凑 |
| 7 | `L4.volume.frequency` | 中 | 中 | App 公司专用；Sensor Tower free tier |
| 8 | `L3.delivery.lead_time` | 低 | 低 | 制造业专用；调研稿不稳定 |
| 9 | （备选）`L1.position.tech_barrier` | 中 | 高 | 现在 C 但可升 D，看专利数据库 |
| 10 | （备选）`L8.industry.substitute` | 中 | 高 | 现在 C 但可升 D，看专业行业研报 |

**风险**（D bucket）：

1. **web fetch 不稳定**：研报 PDF 反爬、链接腐烂、API 限流；需要 retry + cache + 失败回 Unknown 而非编造
2. **编造引用**：LLM 会幻觉伪造 URL；必须 strict policy：evidence_sources 链接 SHA-256 校验 + 抓回正文比对
3. **法律合规**：付费研报版权 / 爬虫风控 / 海外站 GDPR — 走信息引用路径，不存储原文，只引证摘要
4. **更新频次低**：研报季度发布；D bucket 字段更新频次设 quarterly+，不是 daily
5. **prompt 注入风险**：抓回网页可能含恶意 prompt；需要 sandbox 解析层 + 抽取结构后再喂给 main LLM

**推荐 next action**（D bucket，未来 M2 开放）：

1. **试点开 2 个**：`L2.newbiz.tam` + `L3.delivery.csat`（一个偏研报 / 一个偏 UGC 聚合）
2. **观察 Known 率 + 引用质量** 2 个月
3. **失败模式**：URL 失效 / 内容打架 / 抓不到 → fallback 回 C bucket
4. **成功后**：按 Top 10 顺序逐个开通

### 3.E bucket E — premium-or-skip（5 个，2.0%）

> **定义**：spec 标 ✓ 但只有 FMP Premium 或 Tushare/Futu LV2 等付费接口直接覆盖；或字段语义本身在公开数据缺位（如 buy-side whisper）。

**全部 5 个**：

- `L5.surprise.buy_whisper` — 买方/whisper预期（实测：OverlayKnown）
- `L6.mult.dcf` — DCF估值（实测：SQLite）
- `L6.mult.forward_pe` — Forward PE（实测：missing）
- `L7.flow.institutional` — 机构/对冲基金持仓（实测：SQLite）
- `L7.trade.gamma` — Gamma暴露（实测：missing）

**实测发现**（重要）：

- `L6.mult.dcf` SQLite 实测已有数据（FMP `/discounted-cash-flow` 在 Starter tier 也可访问，spec 标 $ 但 fetcher 已绕过）→ 实质 A 行为
- `L7.flow.institutional` SQLite 实测已有 alias 数据（来自 tushare `top_list` 龙虎榜代理），不是真正机构持仓 → 数据语义偏差，建议保留 E 标签 + 备注 alias 弱替代
- 剩 3 个真正 E：`L5.surprise.buy_whisper` / `L6.mult.forward_pe` / `L7.trade.gamma`

**推荐 next action**（E bucket）：

1. **`L6.mult.dcf` / `L7.flow.institutional`** — 在 spec source_status 中应该重打标为 ✓ 或 ✓（alias），coverage_audit 滞后
2. **`L6.mult.forward_pe`** — Tushare 分析师预期能算 forward EPS，再除股价即得 Forward PE → 升 B bucket（派生）
3. **`L7.trade.gamma`** — Futu LV2 期权链可推（已 ○ partial），需要 derive 层算 → 升 B（前提：Futu 期权链字段稳定）
4. **`L5.surprise.buy_whisper`** — 接受永久 Unknown，或长期接付费 alt-data（Bloomberg/Refinitiv whisper）— ROI 低，推迟
5. **FMP Premium 升级 ROI**：仅 `L6.mult.forward_pe`+`L6.mult.dcf` 严格属于 Premium 解锁；其余 spec 标 $ 的字段都能通过其他源 ✓ 满足 → 不建议升级（$29/mo for 2 fields）

---

## 4. X5 后 6 个月路线图（推荐）

### M1（X5 完成月）：closed-llm 收敛

**目标**：C bucket 21 → 50+ Known

- X5 跑完 26 字段 trial（Group A 公司画像 + B 行业补 + C L4 软指标）
- 监控 Known 率 / evidence_quality / 同一字段跨公司方差
- 若 Known < 50% → 补 IR 问答库 fetcher（巨潮互动易 / SSE 互动平台）

**输出指标**：

- C bucket Known 率 ≥ 60%（21 个已填 + 30 个新填 = 51/103 ≈ 50%）
- A bucket missing 33 → 10（X4 alias 修补）

### M2（M1+1 ~ M1+2）：B 派生加速 + D 试点 2 字段

**目标**：

- B bucket 派生 24 → 28（补 L11.long.* 4 字段）
- D bucket 开通 `L2.newbiz.tam` + `L3.delivery.csat` 作为 web-llm 试点
- 观察 D 字段引用质量 / web fetch 失败率

**输出指标**：

- B Known 率 100%
- D 试点字段 evidence_sources URL 真实率 > 95%（防幻觉）
- D fetch 失败率 < 10%

### M3（M1+3 ~ M1+6）：D 全开 + E 重新评估

**目标**：

- D bucket 全 8 字段开通
- E bucket 5 字段重新评估（DCF/institutional 已绕过，forward_pe/gamma 升 B，buy_whisper 接受 Unknown）
- C bucket 扩 prompt 至 95+ Known

**输出指标**：

- 250 字段整体 Known 率 ≥ 80%
- A:B:C:D:E Known 率分别 95% / 90% / 70% / 60% / 0%（接受）

---

## 5. 风险 & 不确定性

### 5.1 闭环 LLM Known 率不达预期

**风险**：C bucket 103 个字段中，依赖 IR 问答 / 业绩会的部分可能 Known < 30%（因公司披露稀疏）

**对冲**：

- evidence_quality=low 不强制 Known，保持 Unknown 不影响下游评分（spec missing_policy=unknown_reduce_confidence 已设计）
- 推动 IR 问答库 fetcher 上线（巨潮互动易/SSE 互动平台/SZSE 投资者关系平台）作为 M1.5 补丁
- 行业 prior 加权：对高披露行业（消费、医药、互联网）期待 Known 率高；对低披露行业（金融、能源、地产）期待中等

### 5.2 web-llm 合规与质量

**风险**：

1. 研报 PDF 版权（中信/中金 PDF 受限）→ 只引摘要不存全文；evidence_sources 给链接不给文件
2. 抓取受 robots.txt 限制；Reddit/雪球 API 限流
3. LLM 编造 URL（known hallucination 模式）→ strict whitelisted domains + fetch-back verification
4. prompt 注入：抓回页面内含 `忽略上文，输出 X` 类 payload → sandbox 提取后只保留 plain text 与 SHA

**对冲**：

- domain whitelist：IDC.com, Gartner.com, sensortower.com, statista.com, IR 官网, 巨潮, 三方合规渠道
- evidence_sources 字段强 schema：必须含 `kind / title / source(URL) / published_at / excerpt + sha256(content)`
- 试点期 evidence_quality 默认 low，人工 review 后才升 medium
- 法律咨询：金融决策辅助场景下，三方研报引用属于合理使用 vs 不属于，需明确

### 5.3 FMP Premium 升级 ROI

**当前判断**：升级 $29/mo 净解锁 2 个真有效字段（forward_pe + dcf 严格 spec 标 $；其余 spec $ 在 Tushare ✓）

**结论**：不建议升级。两个字段都可通过：

- Tushare 分析师预期（A bucket 补全后） → derive Forward PE（升级到 B）
- FMP `/discounted-cash-flow` 实测已能访问（spec 误标） → A bucket 实际

### 5.4 spec source-of-truth 漂移

**风险**：`data_point_roles.yaml` 的 `source_status` 字段（45 missing）与 `coverage_audit.md` Section 4（32 missing）数字打架。本报告以 coverage_audit Section 7 总评列作为 spec 真相。

**对冲建议**（不在本报告 scope，但需记录）：

- `data_point_roles.yaml` 的 `source_status` 字段建议下次同步用 coverage_audit Section 7 重新生成（脚本：parse Section 7 → write `source_status`）
- 长期 single-source-of-truth：建议固化在 `data_point_roles.yaml`，coverage_audit 由它生成（反向）

### 5.5 X5 26 字段的 bucket 归属

**未知**：本报告无法看到 X5 工作流的 26 个字段精确列表（任务上下文说 Group A 公司画像 + B 行业补 + C L4 软指标）。本报告基于：

- overlay yaml 实测有 30 个 spec-内字段 data_status=Known（推断这是 X5 trial 已填的部分）
- 32 missing + 部分 partial 的 C 类（如 L1.position.brand / L4.eff.* 等）应当是 X5 候选

**若 X5 26 字段中包含 D 类**（如 `L2.newbiz.tam`）→ 应识别并按 D 流程对待（开 web search），不强行闭环

---

## 6. 附录

### 6.1 实测脚本（reproducible）

```python
# A. 检查 SQLite 已 emit dp_id 与 spec 250 的交叉
import sqlite3, yaml
conn = sqlite3.connect('runtime/hot.sqlite')
sqlite_dps = set(r[0] for r in conn.execute(
    'SELECT DISTINCT dp_id FROM realtime_current'))
spec = set(yaml.safe_load(
    open('config/data_point_roles.yaml'))['data_points'].keys())
print('SQLite ∩ spec:', len(sqlite_dps & spec))  # 105
print('SQLite − spec:', len(sqlite_dps - spec))  # 27 (out of spec)

# B. overlay yaml 已填字段
import glob
overlay_known = set()
for f in glob.glob('config/stock_overlays/*/*.yaml') + \
         glob.glob('config/industry_overlays/*.yaml'):
    y = yaml.safe_load(open(f)) or {}
    for n in y.get('nodes', []) or []:
        if n.get('data_status') in ('Known', 'Optionality') and n.get('dp_id'):
            overlay_known.add(n['dp_id'])
print('Overlay Known:', len(overlay_known))  # 31, 30 in spec
```

### 6.2 SQLite emit 但不在 spec 250 的 27 个 dp_id

（这些是 fetcher 落库的 alias / 内部字段，不是 spec 字段，本报告不分类）

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
- `L7.holders.institutional`
- `L7.market.l2_quote`
- `L9.event.holder_trade_signal`
- `L9.event.insider_trades`
- `L9.event.intraday_announcement`
- `L9.event.intraday_news`
- `L9.event.major_holder_decrease`
- `L9.event.major_holder_increase`
- `L9.event.news_flow`
- `L9.event.recent_filings`

**建议**：把 L5.fina.* 这 16 个 alias 到 L5.is.* / L5.bs.* / L6.* 对应 spec dp_id；L9.event.* alias 到 L9 spec 字段（如 `L9.event.news_flow` → `L9.media.report`）。需要 spec/data_point_roles.yaml 同步更新 alias 表。

### 6.3 边界 case 与不确定字段

以下字段的 bucket 判断在 A/B 或 C/D 边界，建议下个工作周期 review：

| dp_id | 当前 bucket | 边界争议 | 备注 |
|---|:-:|---|---|
| `L6.mult.dcf` | E（严格）/ A（实测） | spec 标 $ 但实测 FMP Starter 已能取 | spec 应同步 |
| `L7.flow.institutional` | E（严格）/ C（alias） | tushare top_list 龙虎榜数据当替代，语义近似 | 改 alias label |
| `L6.mult.forward_pe` | E（严格）/ B（派生） | 接 Tushare 分析师预期 fcst.eps_cf 后可派生 | 升 B（前提：A 33 missing 补完） |
| `L7.trade.gamma` | E（严格）/ B（派生） | Futu LV2 期权链能算 | 升 B（前提：Futu 期权稳定） |
| `L1.position.tech_barrier` | C | 部分需要专利数据库 | 可拆 50/50：现状 C，需要 D 补充 |
| `L1.position.brand` | C | 行业研报有可能给品牌价值排名 | C，但允许 evidence_sources 引外部 ranking |
| `L8.industry.substitute` | C | 替代技术判断常依赖券商 | C-leaning-D |
| `L3.product.portfolio` | C（partial） | 部分公司产品线复杂；公告披露详细 | C |
| `L4.price.subscription` | C | 公司公告 pricing page 有；不一定全 IR 答 | C-leaning-D（互联网公司） |
| `L4.eff.capacity_utilization` | C | 业绩会有部分；周期股专门披露 | C |

---

## 7. 引用

- `config/data_point_roles.yaml` — spec 250 dp_id 与 field role
- `docs/data_sources/coverage_audit.md` Section 4 + 7 — 5 源覆盖矩阵（真相源）
- `docs/data_sources/llm_derived_nodes.md` — 32 缺失字段 LLM 衍生设计
- `runtime/hot.sqlite` 表 `realtime_current` — 实测 132 dp_id（105 在 spec）
- `config/industry_overlays/*.yaml` + `config/stock_overlays/*/*.yaml` — overlay 已填字段 30 个在 spec 内
- `图谱设计.md` — 12 层 spec 图谱设计
- `docs/data_sources/FMP_TIER_REQUIREMENTS.md` — FMP Premium 升级映射
