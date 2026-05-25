# LLM 衍生节点清单

`coverage_audit.md` Section 4 列出的 **32 条彻底缺失**数据点（5 源全 none，无 premium 升级解锁）—— codex 给每只股票建图时这些节点全部走 LLM 衍生路径。X5 新增 **26 条 closed-loop slot**（Group A/B/C，详见 §3a/§4a/§4b），合计 58 条 LLM 衍生节点。

> **本文件不重复 spec 的状态机定义**——所有缺失处理字段（`data_status` / `required_level` / `missing_policy` / `alert_policy` / `materiality` / `data_source` / `evidence_quality` 等）的语义、报警分级、汇总规则全部以 `图谱设计.md` 为准。本文件只补充：32 + 26 = 58 条具体是哪些 / 怎么用 LLM 填 / 行业级与公司级如何分摊 / 成本估算。

> 关键映射：5 源全 none 的 32 条 → spec 状态 **`data_status: Unknown`**（理论上适用，但拿不到一手数据）→ `missing_policy: unknown_reduce_confidence`。LLM 衍生填充后：状态切到 **`data_status: Known`** + `data_source: llm_derived` + `evidence_quality: low|medium`（取决于证据材料），自然反映在置信度计算里——参见 spec 第 23 节"置信度计算"。

---

## 全局约束（X5 closed-loop → Z1c 按 model_tier 分层）

X5 之后所有 codex 衍生填充须遵守 closed-loop 规则；Z1c 在此基础上引入 **`model_tier` 分层**：

> **权威规则文档** → `docs/codex/codex_fill_guide.md` §2a "Evidence sources (按 model_tier 分层)"。
> 本文件不再重复枚举字段约束，避免双源失同步。

简述（详情以 codex_fill_guide.md §2a 为准）：

- `cheap_extract` / `cheap_classify` / `analysis` tier ⇒ **closed-loop**：只允
  `local_dp_id` / `local_overlay` / `industry_inference`，**禁止任何 `http(s)://`**。
- `web_analysis` tier ⇒ **web-enabled**：允许 `annual_report` / `research_report` /
  `investor_relations` / `external_url`，但每条 web evidence **必须含
  `url + checksum (sha256) + fetched_at (ISO)`**——便于 audit + replay。
- 未带 checksum 的 web evidence → `evidence_quality=low` + `confidence ≤ 0.5`。
- 任一 tier 都 **禁止 hallucinate URL** —— 找不到证据 → `data_status: Unknown` +
  `missing_reason: "no_local_evidence"`。

每个 dp_id 的 `model_tier` 在 `config/llm_field_governance.yaml`（Z1b 产出）声明。
`scripts/verify_overlay_closed_loop.py` 按此 tier 判违规：
- `cheap_*` / `analysis` 字段含 web evidence ⇒ 硬违规，可 `--auto-demote` 降级为
  `data_status: Unknown` + `missing_reason: "evidence_violation_<reason>"`。
- `web_analysis` 字段缺 `url` / `checksum` / `fetched_at` ⇒ 软违规（warn），不 auto-demote。
- 未在 governance.yaml 注册的 dp_id ⇒ 默认按 closed-loop 处理（向后兼容 pre-Z1b 状态）。

新增 flag：`--strict-web-only` 只扫 `web_analysis` tier 字段（用于专项 verify）。

---

## 1. 两类衍生节点

| 类别 | 数据点数 | 共享粒度 | LLM 调用估算 |
|---|---:|---|---:|
| **行业级（L0 共享）** | 14 | 每行业一份；行业内所有公司 reuse | 12 个 active 行业各一次批量输出 |
| **公司级（L1-L5 专属）** | 18 | 每个 company-industry overlay 一份 | 353 个 overlay 文件；可按公司复用研究材料 |

**重要**：codex 处理顺序应该是 **先行业级后公司级**——行业级数据是公司级判断的输入参考（如行业产能 ↑ 影响公司"渠道优势"的相对地位）。

---

## 2. 跟 spec 字段标准的对齐

每条 LLM 衍生节点的字段填法（参见 spec 第 17 节"节点字段模板"）：

| spec 字段 | 32 条节点的取值 |
|---|---|
| `data_status` | 未填时 **`Unknown`**；LLM 填后 **`Known`**；公司不适用时 **`N/A`**（如非订阅模式公司的 L4.price.subscription） |
| `required_level` | 见下表"required_level 建议"（多数 `conditional_required`，少数 `optional`） |
| `missing_policy` | `unknown_reduce_confidence`（理论上适用但拿不到数据）/ `not_applicable_remove`（公司不适用） |
| `alert_policy` | `warn_if_material`（材料公司必填路径上）/ `no_alert`（边缘节点） |
| `data_source` | LLM 填后置 `llm_derived`；附 `evidence_sources: [{kind, title, published_at, excerpt}]` |
| `evidence_quality` | 由 LLM 自评 `low / medium / high`，默认 `low`（一手数据缺失） |
| `confidence` | LLM 输出 0-1；通常 < 0.7（一手数据缺失天花板） |
| `materiality` | 由 codex 按行业属性 / 公司业务结构静态决定 |
| `last_updated` | LLM 填充时间戳 |
| `update_frequency` | 见下表"输出频率"（多数 `quarterly`，部分 `quarterly+` / `oneoff`） |

未填的节点 schema 仍然完整存在——前端 StockGraphPanel 看到 `data_status: Unknown` → 渲染灰虚线 + tooltip："等待 LLM 衍生 / 一手数据缺失"。

---

## 3. 行业级 overlay（每行业一份，行业内复用）

> codex 处理：对每个 `industry_id`（12 个 present 行业），跑一次 LLM 调用拿行业结构化输出，落到 `config/industry_overlays/<industry_id>.yaml`。当前每个 industry overlay 文件有 31 个 graph nodes；下方 14 条是早期核心 L0 子集，不代表完整文件结构。所有该行业公司的数据 overlay 通过 `inherit_from` 引用这份。

### 通用 prompt 模板

```
Industry: {industry_name_cn}
Period: {YYYY-Q?}
Data sources to consult: 行业研报、券商月度/季度行业报告、PMI/产销数据、龙头公司业绩会纪要

For each industry overlay field, output JSON with:
- value: structured per-field schema
- yoy_pct: float | null
- trend: enum[up, flat, down, mixed] | null
- magnitude: enum[strong, moderate, weak] | null
- confidence: float 0-1
- evidence_quality: enum[low, medium, high]
- evidence_sources: [{kind, title, source, published_at, excerpt}]
- not_applicable: bool
- notes: short rationale
```

### 早期核心 L0 子集清单

| data_point_id | label_cn | spec category | required_level | output_format | 频率 |
|---|---|---|---|---|---|
| `L0.demand.terminal` | 终端需求变化 | 需求 | conditional_required | yoy% + trend | quarterly+ |
| `L0.demand.user_count` | 用户/订单数量变化 | 需求 | conditional_required | yoy% + trend | quarterly+ |
| `L0.demand.frequency` | 消费频次变化 | 需求 | optional | yoy% + trend | quarterly |
| `L0.demand.penetration` | 渗透率变化 | 需求 | conditional_required | absolute% + delta | quarterly |
| `L0.demand.replacement` | 替换周期变化 | 需求 | optional | months + trend | quarterly |
| `L0.supply.capacity` | 行业产能变化 | 供给 | conditional_required | yoy% + trend | quarterly |
| `L0.supply.channel_service` | 渠道/服务供给 | 供给 | conditional_required | qualitative + magnitude | quarterly |
| `L0.supply.chain_eff` | 供应链效率/人力供给 | 供给 | conditional_required | qualitative + magnitude | quarterly |
| `L0.price.discount` | 行业折扣力度 | 价格 | conditional_required | yoy delta% + trend | quarterly |
| `L0.price.pricing_power` | 行业提价能力 | 价格 | conditional_required | strong/moderate/weak + trend | quarterly |
| `L0.cost.rent` | 行业租金成本 | 成本 | conditional_required | yoy% + trend | quarterly |
| `L0.cost.cac` | 行业获客成本 | 成本 | conditional_required | yoy% + trend | quarterly |
| `L0.compete.price_war` | 行业价格战 | 竞争 | conditional_required | bool + intensity + duration | quarterly+ |
| `L0.compete.new_entrant` | 新进入者/替代品 | 竞争 | conditional_required | count + threat_level | quarterly |

### 注意事项

- 行业级数据**幂等**：同一季度同一行业 LLM 输出应当稳定，不应每次跑差距大。出现差距 > 30% → 触发 reviewer 标记
- L0.compete.price_war / L0.compete.new_entrant 是事件形态，可能空季度（无价格战、无新进入者）—— 此时 `data_status: Inactive`，**不是 Unknown**（spec 第 23 节明确区分）
- `optional` 标记的字段（消费频次、替换周期）—— 部分行业（如金融、能源）天然不适用 → 公司继承时改 `data_status: N/A`，`missing_policy: not_applicable_remove`，按 spec 重归一化

---

## 3a. X5 Group B — 行业级 L0 补强（5 条，其中 1 条已在 §3）

> codex 处理：同 §3 — 在行业 overlay yaml 加这 5 条节点的 value。Group B 是
> 行业级补强（每行业一份，行业内所有公司 inherit_from_industry=True）。

| dp_id | label_cn | required_level | output_schema |
|---|---|---|---|
| `L0.price.contract_spot` | 长协 vs 现货价差 | conditional_required | `{contract_pct: float, spot_pct: float, spread_pct: float, trend: enum[widening, narrowing, stable]}` |
| `L0.price.product_asp` | 行业产品 ASP | conditional_required | `{asp_value: float, asp_unit: text, yoy_pct: float, qoq_pct: float, trend: enum}` |
| `L0.supply.inventory` | 行业库存水平 | conditional_required | `{inventory_days: float, vs_normal_pct: float, channel_inventory_state: enum[低/正常/高], trend: enum}` |
| `L0.sentiment.social` | 社交情绪/舆情 | optional | `{sentiment_score: float (-1..1), volume_idx: float, top_themes: [text], trend: enum, evidence_quality: low}` |
| `L0.price.discount` | 行业折扣力度 | conditional_required | (见 §3 — 已声明) |

### Group B prompt 模板

```
Industry: {industry_name_cn}
Period: {YYYY-Q?}

Local SQLite facts available (inline):
{每个相关 dp_id 的 ts_code / payload 摘要}

For each of the 4 fields above (L0.price.discount 在 §3 内已处理):
- value: 按上表 output_schema 输出 JSON
- yoy_pct/qoq_pct/spread_pct: float | null
- trend: enum[up, down, flat, widening, narrowing, stable, mixed] | null
- confidence: float 0-1（local 充分 ≤ 0.7；industry_inference ≤ 0.5）
- evidence_quality: enum[low, medium, high]
- evidence_sources: [{kind: "local_dp_id"|"local_overlay"|"industry_inference", ...}]
- not_applicable: bool
- notes: short rationale (中文)

如果 prompt 没有给出该行业的具体本地数据 → 输出 `data_status: Unknown` +
`missing_reason: "no_local_evidence"`。**绝不**引用未在 prompt 内 inline 的外部数据。
```

---

## 4. 公司级 18 条（每股一份）

> codex 处理：按 `industry_id + ts_code` 展开 company-industry overlay，拿 18 条结构化输出，落到 `config/stock_overlays/<industry_id>/<ts_code>.yaml` 的 `nodes` / `llm_derived_slots`。同一家公司跨多个行业时必须生成多个 overlay 文件，API 通过 `industry_id` 切换视图。

### 4.1 公司定位 / 软指标（L1-L2，4 条）

| data_point_id | label_cn | required_level | output_schema | 输入材料 |
|---|---|---|---|---|
| `L1.position.channel_edge` | 渠道优势 | conditional_required | `{strength: enum[显著/一般/弱], components: [], peers_comparison: {}}` | 年报+招股书+调研纪要 |
| `L1.position.stickiness` | 客户粘性 | conditional_required | `{retention_rate: float, switching_cost: enum[高/中/低], churn_signals: []}` | 年报+财报电话会 |
| `L2.newbiz.tam` | 新业务市场空间 | optional | `{tam_usd_or_cny: number, tam_year: int, source: text}` | 招股书+公司发布会+三方研报 |
| `L2.newbiz.uncertainty` | 新业务不确定性 | optional | `{level: enum[高/中/低], factors: [], catalyst_required: []}` | 调研纪要+研报 |

> 注：L2 两条对应 spec 第 23 节 "Optionality 未来期权节点" —— 评分要拆当前贡献和未来估值贡献两部分，不能按当前收入占比 0 直接归零。

### 4.2 产品 / 客户 / 渠道 / 区域结构（L3，6 条）

| data_point_id | label_cn | required_level | output_schema | 输入材料 |
|---|---|---|---|---|
| `L3.product.lifecycle` | 产品生命周期/竞争力 | conditional_required | `{phase: enum[导入/成长/成熟/衰退], competitive_score: 0-5}` | 年报+行业报告 |
| `L3.customer.segment_mix` | 客户类型结构 | conditional_required | `{segments: [{name, revenue_pct}], concentration_top5_pct: float}` | 年报披露大客户表 |
| `L3.channel.mix` | 渠道结构占比 | conditional_required | `{direct_pct, distributor_pct, ecommerce_pct, others_pct}` | 年报销售渠道章节 |
| `L3.region.tier_mix` | 城市层级结构 | optional | `{tier1_pct, tier2_pct, tier3_pct, overseas_pct}` | 年报区域披露 |
| `L3.delivery.lead_time` | 交付周期/服务能力 | optional | `{lead_time_days: number, on_time_rate: float, trend: enum}` | 业绩会+调研纪要 |
| `L3.delivery.csat` | 客户满意度 | optional | `{nps_or_csat: float, complaint_rate: float, trend: enum}` | 第三方调研+业绩会 |

### 4.3 公司经营软指标（L4，7 条）

| data_point_id | label_cn | required_level | output_schema | 输入材料 |
|---|---|---|---|---|
| `L4.volume.foot_traffic` | 门店客流 | conditional_required | `{yoy_pct: float, monthly_trend: []}` | 业绩会+渠道调研 |
| `L4.volume.frequency` | 使用频次 | optional | `{frequency_per_user: float, yoy_delta_pct: float}` | 业绩会+三方数据 |
| `L4.price.subscription` | 订阅价格 | conditional_required | `{tiers: [{name, price, currency}], trend: enum}` | 公司公告+业绩会 |
| `L4.price.discount` | 折扣率 | conditional_required | `{avg_discount_pct: float, trend: enum, season_high: bool}` | 业绩会+渠道调研 |
| `L4.eff.capacity_utilization` | 产能利用率 | conditional_required | `{utilization_pct: float, trend: enum, bottleneck: text}` | 年报+业绩会 |
| `L4.eff.conversion_retention` | 转化率/留存/复购 | conditional_required | `{conversion_pct, retention_30d, repurchase_rate, trend}` | 业绩会+用户调研 |
| `L4.share.customer_channel` | 客户/渠道/区域份额 | conditional_required | `{customer_share_top5, channel_share, region_share, trend}` | 年报+三方报告 |

> L4 大量字段对**特定商业模式不适用**：非门店模式公司 → `L4.volume.foot_traffic` 切 `data_status: N/A`；非订阅模式 → `L4.price.subscription` 切 N/A。spec 第 23 节"N/A 不适用节点"汇总规则适用——剔除该节点并重归一化兄弟节点权重。

### 4.4 财务场外信号（L5，1 条）

| data_point_id | label_cn | required_level | output_schema | 输入材料 |
|---|---|---|---|---|
| `L5.surprise.buy_whisper` | 买方/whisper 预期 | optional | `{whisper_eps: float, whisper_revenue: number, vs_consensus_pct: float, source_count: int}` | 买方圈讨论+卖方私下沟通+预测平台 |

### 4a. X5 Group A — 公司画像补强（16 条 L1-L3）

> codex 处理：在公司 overlay yaml 加这 16 条节点的 value。**所有判断都基于** prompt
> 里 inline 注入的 SQLite dp_id（特别是 `L1.company.main_business` /
> `L9.disclosure.qa_recent` / `L8.gov.management_table` / `L5.is.*` / `L5.bs.*` /
> 行业 overlay L0 上下文）。

#### Group A.1 — L1 公司定位（5 条）

| dp_id | label_cn | required_level | output_schema |
|---|---|---|---|
| `L1.position.market_share` | 市场份额与排名 | conditional_required | `{rank: int \| null, share_pct: float \| null, market_size_unit: text, peers: [text], trend: enum, source_year: text}` |
| `L1.position.brand` | 品牌力/认知度 | conditional_required | `{tier: enum[领导/挑战者/跟随者/利基], category: text, qualitative_signals: [text]}` |
| `L1.position.tech_barrier` | 技术壁垒/专利 | conditional_required | `{patent_count_known: int \| null, key_tech: [text], moat_score: 0-5, rd_intensity_pct: float \| null}` |
| `L1.position.cost_edge` | 成本优势 | conditional_required | `{vs_peers_gp_pct: float \| null, drivers: [text], duration: enum[短期/中期/长期/结构]}` |
| `L1.position.pricing_power` | 公司定价权 | conditional_required | `{strength: enum[强/中/弱], asp_yoy_pct: float \| null, switching_cost: enum, evidence: [text]}` |

#### Group A.2 — L2 业务结构 + 新业务 (7 条)

| dp_id | label_cn | required_level | output_schema |
|---|---|---|---|
| `L2.segment.cash_contrib` | 主营现金贡献结构 | conditional_required | `{segments: [{name, revenue_pct, gross_margin_pct \| null, cash_contrib_pct \| null}]}` |
| `L2.segment.industry_exposure` | 细分行业敞口 | conditional_required | `{exposures: [{industry_id, weight_pct}], cyclical_sensitivity: enum}` |
| `L2.segment.compete_landscape` | 细分竞争格局 | conditional_required | `{competitive_intensity: enum[低/中/高/极高], top_peers: [text], top3_share_pct: float \| null}` |
| `L2.segment.business_risk` | 业务结构性风险 | conditional_required | `{risk_factors: [{type, severity: enum[低/中/高], rationale}], net_risk: enum}` |
| `L2.newbiz.commercialization` | 新业务商业化进度 | optional | `{stage: enum[早期/试点/规模化/成熟], traction_signals: [text], rev_share_pct: float \| null}` (Optionality split: `{current_contribution, future_option_value}`) |
| `L2.newbiz.revenue_contrib` | 新业务当前营收占比 | optional | `{revenue_pct: float \| null, qoq_growth_pct: float \| null}` (Optionality split) |
| `L2.newbiz.valuation_contrib` | 新业务估值贡献 | optional | `{est_valuation_contribution_pct: float \| null, method: enum[DCF/可比/期权], notes: text}` (Optionality split) |

#### Group A.3 — L3 客户/渠道/区域/交付 (4 条)

| dp_id | label_cn | required_level | output_schema |
|---|---|---|---|
| `L3.customer.solvency` | 大客户偿付能力 | conditional_required | `{top_customers_solvency: [{name_proxy, credit_signal: enum[好/中/警示]}], ar_concentration_risk: enum}` |
| `L3.channel.overseas` | 海外渠道铺货与本土化 | optional | `{overseas_revenue_pct: float \| null, key_markets: [text], localization_stage: enum}` |
| `L3.region.key_risk` | 重点区域风险 | optional | `{key_region: text, risk_type: enum[政策/汇率/地缘/天气], severity: enum, exposure_pct: float \| null}` |
| `L3.delivery.capacity_supply` | 交付产能/供应链稳定 | conditional_required | `{capacity_utilization_pct: float \| null, supplier_concentration: enum, bottleneck: text}` |

### 4b. X5 Group C — L4 运营软指标 (6 条)

| dp_id | label_cn | required_level | output_schema |
|---|---|---|---|
| `L4.price.asp_aov_arpu` | ASP / AOV / ARPU | conditional_required | `{metric_kind: enum[ASP/AOV/ARPU], value: float, currency: text, yoy_pct: float \| null, trend: enum}` |
| `L4.price.pricing_power` | 公司定价权（运营） | conditional_required | `{strength: enum, recent_price_adjustment: text \| null, customer_pushback: enum[无/弱/强]}` |
| `L4.price.elasticity` | 价格弹性 | optional | `{elasticity: float \| null, estimation_method: enum[empirical/inferred/industry_inference], notes: text}` |
| `L4.cost.cac_production` | 获客/单位生产成本 | conditional_required | `{cac_or_unit_cost: float \| null, trend: enum, drivers: [text]}` |
| `L4.cost.rent_energy_logistics` | 租金/能源/物流 | optional | `{rent_yoy_pct: float \| null, energy_yoy_pct: float \| null, logistics_yoy_pct: float \| null, trend: enum}` |
| `L4.eff.store_labor` | 门店/人效 | optional | `{revenue_per_employee: float \| null, revenue_per_store: float \| null, yoy_pct: float \| null, trend: enum}` |

### Group A / C prompt 增量段落（必须附在 §4 公司级模板后）

```
Local SQLite facts inline-injected for this stock:
- L1.company.main_business (from tushare:stock_company): {main_business 摘要}
- L9.disclosure.qa_recent (from tushare:irm_qa_*): {最新 Q&A 摘要}
- L8.gov.management_table (from tushare:stk_managers): {高管名单 + 任期 + 变动次数}
- L5.is.* / L5.bs.* / L5.cf.* (from tushare:income/balancesheet/cashflow): {YoY 摘要}
- L6.mult.pe / L6.mult.pb (from tushare:daily_basic): {当前估值}
- 行业 overlay L0.* (from config/industry_overlays/<industry_id>.yaml): {已填的 L0 值}

For each Group A / Group C field above, output JSON. Each field schema is per
the table above. For each field, additionally include:
- data_status: enum[Known, N/A, Unknown, Inactive]
- confidence: float 0-1 (≤ 0.7 cap)
- evidence_quality: enum[low, medium, high]
- evidence_sources: [{kind, ...}]  where kind ∈ {local_dp_id, local_overlay, industry_inference}
- missing_reason: text (filled only when data_status != Known)

如果 prompt 里没有 L1.company.main_business inline 注入，**不要**凭训练记忆补；
直接 `data_status: Unknown` + `missing_reason: "no_local_evidence"`。
```

### 通用 prompt 模板（公司级）

```
Company: {ts_code} {name}
Industry: {industry_id} ({industry_name_cn})
Period: {YYYY-Q?}
Industry context: {引用对应行业 overlay 的 31 个 graph nodes from industry_overlays/<industry_id>.yaml}

For each of the 18 fields below, output JSON. Each field schema is fixed (see fields).
For each field, additionally include:
- data_status: enum[Known, N/A, Unknown, Inactive]  // 若公司天然不适用，输出 N/A
- confidence: float 0-1
- evidence_quality: enum[low, medium, high]
- evidence_sources: [{kind, title, published_at, excerpt}]
```

### 注意事项

- **`data_status: N/A`** 是合法终态——比如非订阅模式公司不需要 `L4.price.subscription` slot 仍然保留，但 value 留 null + data_status=N/A + missing_policy=not_applicable_remove
- 行业级数据点应当**作为 prompt 输入**给公司级调用——公司级判断（如"渠道优势"）要基于行业上下文
- L4 的"门店客流""产能利用率"等 LLM 衍生 confidence 通常 < 0.6（不是公开数据）→ `evidence_quality: low`，前端 UI 标"低置信度"警告

---

## 5. schema slot 必须留好（即使未填）

每个 company-industry stock overlay 现在包含 112 个 graph nodes（111
个治理 dp_id 加 `company` root）。节点存在不代表已填；历史文档中的
"32 slot" 只对应早期 X5 缺失字段子集。参考 spec 第二节"批量建图落地原则"和第 23 节"缺失节点的汇总规则"。

```yaml
# config/stock_overlays/STORAGE_GRID/300750.SZ.yaml（codex 生成）
ts_code: 300750.SZ
name: 宁德时代
industry_id: STORAGE_GRID
primary_industry: true
available_industries: [STORAGE_GRID]
schema_version: 1

nodes:
  # === 行业继承节点（引用 industry_overlays/<primary_industry>.yaml；当前每个 industry overlay 31 nodes）===
  - dp_id: L0.demand.terminal
    node_id: 300750.SZ:L0.demand.terminal
    inherit_from_industry: true
    required_level: conditional_required
    data_status: Unknown      # 行业 overlay 未填时；填后切 Known
    missing_policy: unknown_reduce_confidence
    calculation_type: multiplicative_factor
    aggregation_policy: multiply_chain
    alert_policy: warn_if_material
    materiality: 0.8           # codex 按行业静态打
  
  # ...其他行业继承节点 ...
  
  # === 公司级治理节点（stock overlay 总计 112 graph nodes，含 company root）===
  - dp_id: L1.position.channel_edge
    node_id: 300750.SZ:L1.position.channel_edge
    required_level: conditional_required
    data_status: Unknown       # LLM 填后切 Known + data_source: llm_derived
    missing_policy: unknown_reduce_confidence
    calculation_type: multiplicative_factor
    aggregation_policy: multiply_chain
    alert_policy: warn_if_material
    materiality: 0.7
    value: null
    confidence: null
    evidence_quality: null
    evidence_sources: []
    data_source: null          # LLM 填后置 'llm_derived'
    last_updated: null
  
  # ...其他 17 条公司级 ...
```

前端渲染规则：
- `data_status: Known` → 实线 + 数值
- `data_status: Unknown` → 灰虚线 + "等待 LLM 衍生"
- `data_status: N/A` → 不渲染（spec 规定剔除并重归一化）
- `data_status: Inactive` → 灰实线 + "暂未触发"
- `data_status: Low Materiality` → 折叠到详情页
- `data_status: Optionality` → 双值显示（当前贡献 + 未来估值期权）

---

## 6. codex 工作流程

```
Phase A: 行业级填充（12 个 active 行业）
  for industry_id in 12_industries:
    call LLM with industry prompt → industry overlay structured output
    write to config/industry_overlays/<industry_id>.yaml
    set data_status: Known + data_source: llm_derived for filled fields
    set data_status: Inactive for fields that LLM determined "no event currently"
    set data_status: Unknown for fields LLM cannot determine even with research

Phase B: 公司级填充（353 个 company-industry overlay 文件）
  for membership in universe.constituents × active industry_ids:
    industry_context = read industry_overlays/<industry_id>.yaml
    call LLM with company prompt + industry_context → 18 条结构化输出
    write to config/stock_overlays/<industry_id>/<ts_code>.yaml
    LLM 应判断每条字段：
      - 公司天然不适用 → data_status: N/A + missing_policy: not_applicable_remove
      - 适用且能从材料推断 → data_status: Known + data_source: llm_derived
      - 适用但材料不足 → data_status: Unknown + missing_policy: unknown_reduce_confidence

Phase C: 编译与报警
  run mvp20 validate-overlays
  run mvp20 compile-overlays --db runtime/hot.sqlite
  compiler writes:
    - overlay_manifest
    - company_node_instance
    - company_edge_instance
    - company_graph_snapshot
    - overlay_alert

Phase D: 人工 review（按需）
  reviewer 抽查 confidence < 0.6 或 evidence_quality: low 的输出
  确认后置 reviewed_at + reviewer
  必要时改写 value 并切 data_source: manual
  报警字段（data_status: Unknown 且 required_level: required）必须 review
```

成本估算取决于实际批量策略。当前文件粒度是 353 个 company-industry overlay；可以按公司复用材料，但最终必须写回到各自的 `<industry_id>/<ts_code>.yaml`。

---

## 7. 引用

- spec 完整版：`图谱设计.md`
  - 字段标准：第 17 节"节点字段模板"
  - 缺失处理总则：第 二节"批量建图落地原则"
  - 报警规则：第 17 节末"字段必填与报警规则"
  - 状态机详解：第 23 节"缺失节点的汇总规则"
- 数据源覆盖矩阵：`docs/data_sources/coverage_audit.md`
  - 32 条数据点完整列表：Section 4
- 数据源 catalog：`config/data_providers.yaml`
- 数据源 endpoints CSV：`docs/data_sources/{fmp,tushare,futu}_endpoints.csv`
