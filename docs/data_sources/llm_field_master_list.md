# LLM 字段决策 Master List

> 给 codex 做最终路由决策的 250 字段完整清单。
> codex 任务：对每个 LLM 候选字段（C/D bucket）决定：route / frequency / evidence_sources / immutability。
> A/B/E bucket 已机械化默认（codex 可 override 但通常不需要）。

## 0. TL;DR

| 维度 | 数量 |
|---|---:|
| spec 总字段 | 250 |
| A bucket (默认 `sqlite_hard`) | 106 |
| B bucket (默认 `derive`) | 28 |
| C bucket (默认 `llm_close`，待 codex 确认) | 103 |
| D bucket (默认 `llm_web`，待 codex 确认) | 8 |
| E bucket (默认 `skip`) | 5 |
| 历史已填 32 字段 (被 X5 误擦) | 32 (内嵌 C) |
| X5 新增 26 字段 (已加 SLOT_DEFS) | 26 (内嵌 C) |
| **待 codex 真正决策 (C + D)** | **111** |
| **机械默认 (A + B + E)** | **139** |

### 0.1 当前非 LLM 生成口径（2026-06-24）

2026-06-24 的 3 股 A/B 验收确认：原 `C + D` 的 111 个 LLM 候选字段中，有 55 个可以优先走非 LLM 主路径。这里统计的是完整 250 spec 字段口径，不是当前 `stock_overlay` YAML 已物化的 116 个节点口径。

| 口径 | 数量 | 说明 |
|---|---:|---|
| 机械化非 LLM 生成 | 134 | `sqlite_hard` 106 + `derive` 28 |
| 已验证 LLM 候选可转非 LLM 主路径 | 55 | parser / formula / event screen / industry applicability / local proxy first |
| **当前非 LLM 生成字段** | **189 / 250** | `106 + 28 + 55`，占 75.6% |
| 仍需 LLM 主路径 | 56 | 剩余 `C + D` 字段，含本地语义判断和 web/external evidence |
| 非生成字段 | 5 | `skip` |
| 不需要 LLM 的宽口径 | 194 / 250 | 非 LLM 生成 189 + `skip` 5 |

验收依据：

- `docs/audit/2026-06-24_a_share_3_stock_non_llm_vs_gpt55_xhigh_ab.json`
- `docs/audit/2026-06-24_a_share_3_stock_non_llm_vs_gpt55_xhigh_ab.md`
- `docs/audit/2026-06-24_a_share_non_llm_materialization.json`
- `docs/audit/2026-06-24_a_share_non_llm_materialization.md`
- 3 股样本：`300750.SZ`、`600999.SH`、`600754.SH`
- A/B 结果：165 条记录，B 组 schema invalid 0，evidence issue 0，`A_RULE_NEEDS_REVIEW_OR_FIX` 0。

### 0.2 A 股非 LLM 物化结果（2026-06-24）

`scripts/materialize_a_share_non_llm_fields.py` 已将 55 个已验证 LLM 候选非 LLM-first 字段写入 A 股 `stock_overlay`。本节统计的是“公司 × 字段”的实际写入 cell，不改变上一节的单只股票 250 spec 字段路由口径。

| 口径 | 数量 |
|---|---:|
| A 股 overlay 数 | 1,646 |
| 本轮目标字段 | 55 |
| 本轮目标 cell | 90,530 |
| 已物化 cell | 90,530 |
| 可用非 LLM candidate | 86,701 |
| 本地证据不足 / review gate，已写成 `Unknown + missing_reason` | 3,829 |
| schema invalid | 0 |
| 2% 抽查样本 | 1,811 / 1,811 通过 |

3,829 个 `Unknown` cell 不是 schema 错误，也没有伪装成 `Known` / `Proxy`。它们主要是底层本地证据缺失或仍需 review gate：

- `missing capex or PPE`: 1,550
- `missing L3.region.domestic_overseas runtime value`: 706
- `no local extractor implemented`: 377
- `main business text does not directly expose both domestic and overseas business lines`: 343
- `missing forecast revisions and EPS consensus`: 338
- `missing gross margin`: 278

当前 overlay 状态复核：扫描 1,646 个 A 股 overlay 的 55 个目标字段，共 90,530 个节点，缺失节点 0，strict schema errors 0，`Unknown` 缺 `missing_reason` 0。

---

## 1. 决策框架

### 1.1 5 个 route 选项

| route | 含义 | 字段类型 |
|---|---|---|
| `sqlite_hard` | SQLite hard data 直取（不走 LLM） | 财务/估值/资金/技术指标 |
| `derive` | graph-engine 派生层算 | L11 综合分 / L6.sens.* |
| `llm_close` | LLM + 本地文本（不出网） | 公司画像 / 行业先验 |
| `llm_web` | LLM + web fetch（开放搜索） | 三方研报 / 行业面板 / 专利库 |
| `skip` | 永远不填 / 必须人工 / premium 升级 | 期权 Greeks / FMP Premium |

### 1.2 frequency（更新频率）选项

| frequency | 含义 | 触发更新条件 |
|---|---|---|
| `realtime_minute` | 分钟级 | collector cycle |
| `daily_eod` | 日 EOD | 每日 collector cycle |
| `quarterly_filing` | 季报披露 | Tushare/FMP 财报 end_date 变化 |
| `annual_filing` | 年报披露 | 年报 ann_date 变化 |
| `event_driven` | 事件驱动 | 公告/新闻发布 |
| `static_picture` | 静态画像 | 永久不更新（除非显式 refresh）|
| `monthly_macro` | 月度宏观 | PMI/CPI 等月度发布 |

### 1.3 immutability 原则

- **LLM 产出字段一旦 data_status=Known，永久保留 value/evidence_sources/confidence/last_updated**
- 触发 refresh 的唯一条件：
  - `quarterly_filing` 字段：新季度财报披露
  - `annual_filing` 字段：新年报披露
  - `event_driven` 字段：新事件
  - `static_picture` 字段：**只有显式 `llm-refresh --dp_id X --ts_code Y` 命令**触发
- `compile-overlays` / schema 扩展操作**绝对不能擦 LLM 字段的 value 数据**

### 1.4 codex 决策输出格式

对每个**待决策**字段（标 `[需 codex 决策]`），把占位行替换为 `codex_decision:` YAML block：

```yaml
codex_decision:
  route: llm_close   # 或 sqlite_hard / derive / llm_web / skip
  frequency: annual_filing
  evidence_sources:  # codex 期望 LLM 引用什么本地数据
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "industry_inference"
  immutability_rule: source_updated  # 或 explicit_refresh / never
  notes: "年报+投关问答能填；fallback industry_inference"
```

---

## 2. 完整 250 字段清单（按 layer 分组）

字段状态符号：
- `Hist32` = 历史 LLM 已填 32 字段（被 X5 误擦）
- `X5-26` = X5 26 新字段（已加 SLOT_DEFS 进 overlays.py）
- `OverlayKnown` = overlay yaml 节点 data_status=Known/Optionality（非 hist/X5 来源）
- `SQLite` = SQLite `realtime_current` 表已 emit
- `missing` = 三处都没有

### 2.1 L0 行业母图接入（33）

#### `L0.compete.new_entrant` — 新进入者/替代品  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.compete.price_war` — 行业价格战  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.compete.share_concentration` — 市占率/集中度变化  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.cost.cac` — 行业获客成本  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.cost.capital` — 行业资金成本  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `monthly_macro`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L0.cost.energy_logistics` — 行业能源/物流成本  *(bucket C, spec `○`, state `SQLite`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.cost.labor` — 行业人工成本  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.cost.raw_material` — 原材料价格  *(bucket C, spec `○`, state `SQLite`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.cost.rent` — 行业租金成本  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.demand.frequency` — 消费频次变化  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.demand.penetration` — 渗透率变化  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.demand.replacement` — 替换周期变化  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.demand.terminal` — 终端需求变化  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.demand.user_count` — 用户/订单数量变化  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.policy.access_license` — 准入与牌照  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L0.policy.regulation` — 监管/反垄断  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L0.policy.subsidy` — 行业补贴政策  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L0.policy.tax_trade` — 税收/出口限制  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L0.price.contract_spot` — 合同价/现货价价差  *(bucket C, spec `missing`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.price.discount` — 行业折扣力度  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.price.pricing_power` — 行业提价能力  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.price.product_asp` — 行业产品价格/ASP  *(bucket C, spec `missing`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.sentiment.institutional` — 机构配置  *(bucket A, spec `$`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L0.sentiment.leader_drag` — 龙头带动  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L0.sentiment.sector_heat` — 板块热度/ETF流入  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L0.sentiment.social` — 社媒/主题热度  *(bucket A, spec `missing`, state `X5-26`) **[X5-26]***

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L0.supply.capacity` — 行业产能变化  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.supply.chain_eff` — 供应链效率/人力供给  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.supply.channel_service` — 行业渠道/服务供给  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.supply.inventory` — 行业库存变化  *(bucket C, spec `missing`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.tech.ai_automation` — AI/自动化/降本  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.tech.breakthrough` — 技术突破/产品迭代  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L0.tech.substitute_tech` — 替代技术  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "industry_inference"
    - "L9.event.news_flow@runtime"
    - "L0.* peer industry priors"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

### 2.2 L1 公司定位（12）

#### `L1.moat.tags` — 护城河标签  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L1.model.tag` — 商业模式标签  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L1.position.brand` — 品牌影响力  *(bucket C, spec `missing`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L1.position.channel_edge` — 渠道优势  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L1.position.cost_edge` — 成本优势  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L1.position.growth_rank` — 增速排名  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L1.position.market_share` — 公司市占率  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L1.position.pricing_power` — 定价权  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L1.position.stickiness` — 客户粘性  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L1.position.tech_barrier` — 技术壁垒  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L1.role.tag` — 行业角色标签  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L1.stock_attr.tags` — 股价属性标签  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

### 2.3 L2 业务结构（14）

#### `L2.newbiz.commercialization` — 新业务商业化进度  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L2.newbiz.revenue_contrib` — 新业务收入/利润贡献  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L2.newbiz.tam` — 新业务市场空间  *(bucket D, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_web` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "<web fetch: 三方研报/IDC/Counterpoint/IR 站>"
    - "L9.disclosure.qa_recent@runtime (fallback)"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L2.newbiz.uncertainty` — 新业务不确定性  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L2.newbiz.valuation_contrib` — 新业务估值贡献  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L2.segment.business_risk` — 业务线业务风险  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L2.segment.cash_contrib` — 业务线现金流贡献  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L2.segment.compete_landscape` — 业务线竞争格局  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L2.segment.gross_margin` — 业务线毛利率  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L2.segment.growth` — 业务线增速  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L2.segment.industry_exposure` — 业务线行业暴露度  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L2.segment.opex_ratio` — 业务线费用率  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L2.segment.profit_share` — 业务线利润占比  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L2.segment.revenue_share` — 业务线收入占比  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

### 2.4 L3 产品/客户/渠道/区域（18）

#### `L3.channel.cost` — 渠道费用  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L3.channel.efficiency` — 渠道效率  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L3.channel.mix` — 渠道结构占比  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L3.channel.overseas` — 海外渠道  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L3.customer.concentration` — 客户集中度/流失风险  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L3.customer.segment_mix` — 客户类型结构  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L3.customer.solvency` — 客户支付能力  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L3.delivery.capacity_supply` — 产能/供应链  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L3.delivery.csat` — 客户满意度  *(bucket D, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_web` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "<web fetch: 三方研报/IDC/Counterpoint/IR 站>"
    - "L9.disclosure.qa_recent@runtime (fallback)"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L3.delivery.fulfillment_cost` — 履约/售后成本  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L3.delivery.lead_time` — 交付周期/服务能力  *(bucket D, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_web` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "<web fetch: 三方研报/IDC/Counterpoint/IR 站>"
    - "L9.disclosure.qa_recent@runtime (fallback)"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L3.product.lifecycle` — 产品生命周期/竞争力  *(bucket D, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_web` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "<web fetch: 三方研报/IDC/Counterpoint/IR 站>"
    - "L9.disclosure.qa_recent@runtime (fallback)"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L3.product.margin_mix` — 产品毛利/价格结构  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L3.product.portfolio` — 产品组合结构  *(bucket C, spec `missing`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L3.region.domestic_overseas` — 国内/海外收入结构  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L3.region.fx_geo` — 汇率/地缘影响  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `annual_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L3.region.key_risk` — 重点/高风险区域  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L3.region.tier_mix` — 城市层级结构  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.disclosure.qa_recent@runtime"
    - "L1.company.main_business@runtime"
    - "annual_filing_excerpt"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

### 2.5 L4 经营层（23）

#### `L4.cost.cac_production` — 获客/单位生产成本  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L4.cost.labor` — 人工成本  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L4.cost.raw_material` — 原材料成本  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L4.cost.rent_energy_logistics` — 租金/能源/物流成本  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L4.eff.capacity_utilization` — 产能利用率  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L4.eff.conversion_retention` — 转化率/留存/复购  *(bucket D, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_web` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "<web fetch: 三方研报/IDC/Counterpoint/IR 站>"
    - "L9.disclosure.qa_recent@runtime (fallback)"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L4.eff.cycle` — 现金转换周期  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L4.eff.store_labor` — 门店坪效/人效  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L4.eff.turnover` — 库存/应收账款周转  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L4.price.asp_aov_arpu` — ASP/客单价/ARPU  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L4.price.discount` — 折扣率  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L4.price.elasticity` — 价格弹性  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L4.price.pricing_power` — 提价能力  *(bucket C, spec `○`, state `X5-26`) **[X5-26]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L4.price.subscription` — 订阅价格  *(bucket C, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L4.share.customer_channel` — 客户/渠道/区域份额  *(bucket D, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_web` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "<web fetch: 三方研报/IDC/Counterpoint/IR 站>"
    - "L9.disclosure.qa_recent@runtime (fallback)"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L4.share.market` — 公司市占率  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `quarterly_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L4.share.substitution` — 竞品替代  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `quarterly_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L4.volume.foot_traffic` — 门店客流  *(bucket D, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_web` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "<web fetch: 三方研报/IDC/Counterpoint/IR 站>"
    - "L9.disclosure.qa_recent@runtime (fallback)"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L4.volume.frequency` — 使用频次  *(bucket D, spec `missing`, state `Hist32`) **[Hist32]***

- route: `llm_web` *(默认建议; codex 可改)*
- frequency: `static_picture` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "<web fetch: 三方研报/IDC/Counterpoint/IR 站>"
    - "L9.disclosure.qa_recent@runtime (fallback)"
- immutability: `explicit_refresh`
- codex_decision: `[需 codex 决策]`

#### `L4.volume.orders` — 订单量  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `quarterly_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L4.volume.sales` — 销量  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `quarterly_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L4.volume.shipments` — 出货量/交付量  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `quarterly_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L4.volume.users` — 客户/用户数  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `quarterly_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.is.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
    - "industry_inference"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

### 2.6 L5 财务（28）

#### `L5.bs.ar_ap` — 应收/应付账款  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.bs.cash_debt` — 现金/有息负债  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.bs.goodwill_ppe` — 商誉/固定资产  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.bs.inventory` — 存货  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.bs.leverage` — 资产负债率  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.cf.buyback_dividend` — 回购/分红  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.cf.capex` — Capex  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.cf.fcf` — 自由现金流  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.cf.icf_fcf` — 投资/融资现金流  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.cf.ocf` — 经营现金流  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.fcst.beat_probability` — 业绩兑现概率  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `quarterly_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L5.fcst.*@runtime"
    - "L9.disclosure.qa_recent@runtime"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L5.fcst.eps_cf` — EPS/现金流预期  *(bucket A, spec `$`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.fcst.guidance_change` — 公司指引变化  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.fcst.revenue_margin` — 收入/毛利率预期  *(bucket A, spec `$`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.fcst.revisions` — 分析师上修/下修  *(bucket A, spec `$`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.is.eps` — EPS  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.is.gross_margin` — 毛利率  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.is.gross_profit` — 毛利  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.is.margins` — 经营/净利率  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.is.net_profit` — 净利润  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.is.operating_profit` — 经营利润  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.is.revenue` — 收入  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.is.revenue_growth` — 收入增速  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.is.sga_rd` — 三费(销售/管理/研发)  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.surprise.beat_miss` — 超预期/低于预期幅度  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.surprise.buy_whisper` — 买方/whisper预期  *(bucket E, spec `missing`, state `Hist32`) **[Hist32]***

- route: `skip`
- frequency: `realtime_minute`
- immutability: `source_updated`
- codex_decision: `default_accepted`

#### `L5.surprise.preprice` — 股价提前反应  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L5.surprise.sell_side` — 卖方一致预期  *(bucket A, spec `$`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `quarterly_filing`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

### 2.7 L6 估值定价（26）

#### `L6.mult.dcf` — DCF估值  *(bucket E, spec `$`, state `SQLite`)*

- route: `skip`
- frequency: `quarterly_filing`
- immutability: `source_updated`
- codex_decision: `default_accepted`

#### `L6.mult.ev_ebitda` — EV/EBITDA  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.mult.forward_pe` — Forward PE  *(bucket E, spec `$`, state `missing`)*

- route: `skip`
- frequency: `quarterly_filing`
- immutability: `source_updated`
- codex_decision: `default_accepted`

#### `L6.mult.mcap_fcf` — 市值/FCF  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.mult.pb` — PB  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.mult.pe` — PE  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.mult.peg` — PEG  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.mult.ps` — PS  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.path.second_derivative` — 二阶导变差  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.path.tag` — 估值路径标签  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.priced.analyst_revision` — 分析师上修程度  *(bucket A, spec `$`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.priced.crowdedness` — 资金拥挤度  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.priced.discussion` — 市场讨论热度  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.priced.iv` — 期权隐含波动  *(bucket A, spec `$`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.priced.news_age` — 新闻传播时间  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.priced.realization_risk` — 利好兑现风险  *(bucket B, spec `○`, state `missing`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.priced.run_up` — 股价提前涨幅  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.sens.cashflow` — 对现金流敏感  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.sens.growth_margin` — 对收入/利润率敏感  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.sens.rates` — 对利率敏感  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.sens.risk_narrative` — 对风险偏好/叙事敏感  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.state.expansion_compression` — 估值扩张/压缩空间  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.state.historical_percentile` — 历史估值分位  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.state.industry_center` — 行业估值中枢  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.state.peer_compare` — 同业估值对比  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L6.state.peg_match` — 估值与增速匹配度  *(bucket B, spec `○`, state `missing`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

### 2.8 L7 资金情绪宏观（21）

#### `L7.env.fx` — 汇率  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.env.liquidity` — 流动性  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.env.market_trend` — 大盘/行业指数趋势  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.env.rates` — 利率  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.env.risk_appetite` — 风险偏好  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.env.style` — 市场风格  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.flow.active_inflow` — 主动资金流入  *(bucket A, spec `missing`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.flow.block_trade` — 大宗交易  *(bucket A, spec `missing`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.flow.etf_inflow` — ETF流入  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.flow.institutional` — 机构/对冲基金持仓  *(bucket E, spec `$`, state `SQLite`)*

- route: `skip`
- frequency: `realtime_minute`
- immutability: `source_updated`
- codex_decision: `default_accepted`

#### `L7.flow.passive_northbound` — 被动资金/外资  *(bucket A, spec `missing`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.mood.analyst_rating` — 分析师评级分布  *(bucket A, spec `$`, state `missing`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.mood.fomo` — FOMO程度  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.mood.media_social` — 媒体/社媒热度  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.mood.theme` — 主题热度  *(bucket A, spec `missing`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.reflex.tag` — 反身性环节标签  *(bucket B, spec `○`, state `missing`)*

- route: `derive`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.trade.gamma` — Gamma暴露  *(bucket E, spec `$`, state `missing`)*

- route: `skip`
- frequency: `realtime_minute`
- immutability: `source_updated`
- codex_decision: `default_accepted`

#### `L7.trade.iv` — 隐含波动率  *(bucket A, spec `$`, state `missing`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.trade.margin_short` — 融资融券/空头  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.trade.options_cp` — 期权Call/Put  *(bucket A, spec `$`, state `missing`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L7.trade.volume_turnover` — 成交量/换手率  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `realtime_minute`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

### 2.9 L8 风险抵消（32）

#### `L8.cap.crowdedness` — 资金拥挤  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.cap.liquidity_short` — 流动性不足  *(bucket A, spec `✓`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.cap.outflow_cut` — ETF流出/机构减仓  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.cap.short_increase` — 空头增加  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.fin.cash_ar` — 现金流/应收账款恶化  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.fin.debt_pressure` — 债务压力  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.fin.eps_downward` — EPS下修  *(bucket A, spec `$`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.fin.goodwill_impairment` — 商誉减值  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.fin.revenue_profit_miss` — 收入/利润低于预期  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.gov.fraud_control` — 财务造假/内控  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.gov.insider_sell` — 股东减持  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.gov.litigation` — 法律诉讼  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.gov.management_change` — 管理层变动  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.industry.demand_supply` — 行业需求/供给恶化  *(bucket C, spec `missing`, state `SQLite`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `quarterly_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.industry.price_war` — 行业价格战  *(bucket C, spec `missing`, state `SQLite`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `quarterly_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.industry.substitute` — 替代品出现  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `quarterly_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.industry.valuation_compression` — 行业估值压缩  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.op.cost_overrun` — 成本失控  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.op.customer_channel` — 客户流失/渠道失效  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `quarterly_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.op.inventory_glut` — 库存积压  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.op.order_miss` — 订单不兑现  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `quarterly_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.op.product_fail` — 产品失败  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `quarterly_filing` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.reg.license_risk` — 牌照/准入风险  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.reg.subsidy_off` — 补贴退坡  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.reg.tax_trade` — 税收/出口限制  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.reg.tighten` — 监管收紧/反垄断  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.shock.black_swan` — 黑天鹅事件  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.shock.crisis` — 安全/舆情危机  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.shock.supply_break` — 供应中断/客户违约/自然灾害  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L8.industry.*@runtime"
    - "policy_text"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L8.val.overvalued` — 估值过高  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.val.priced_in` — 利好已定价/兑现  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L8.val.slope_risk_off` — 增长斜率下降/风险偏好下降  *(bucket B, spec `○`, state `missing`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

### 2.10 L9 催化剂（20）

#### `L9.capital.etf_block` — ETF调整/大宗交易  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L9.capital.inst_buy_sell` — 机构增持/减持  *(bucket A, spec `$`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L9.capital.margin_anomaly` — 融资/期权/空头异动  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L9.company.buyback_dividend` — 回购/分红  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L9.company.earnings_guidance` — 财报/预告/指引  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L9.company.ma` — 并购  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L9.event.recent_filings@runtime"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L9.company.mgmt_litigation` — 管理层变化/诉讼  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L9.company.product_order` — 新产品发布/大订单  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L9.event.recent_filings@runtime"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L9.industry.compete_risk` — 行业竞争/风险事件  *(bucket C, spec `○`, state `SQLite`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L9.event.recent_filings@runtime"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L9.industry.data_price` — 行业数据/价格发布  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L9.event.recent_filings@runtime"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L9.industry.policy_change` — 行业政策变化  *(bucket C, spec `○`, state `SQLite`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L9.event.recent_filings@runtime"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L9.macro.cpi_employment` — 通胀/就业数据  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L9.macro.fx` — 汇率变化  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L9.macro.geo` — 地缘事件  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L9.event.recent_filings@runtime"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L9.macro.liquidity` — 流动性变化  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L9.macro.rates` — 利率变化  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L9.media.analyst_action` — 分析师评级/研报变动  *(bucket A, spec `$`, state `missing`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L9.media.report` — 媒体报道  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L9.media.short_report` — 做空报告  *(bucket C, spec `○`, state `missing`)*

- route: `llm_close` *(默认建议; codex 可改)*
- frequency: `event_driven` *(默认建议; codex 可改)*
- evidence_sources_hint:
    - "L9.event.news_flow@runtime"
    - "L9.event.recent_filings@runtime"
- immutability: `source_updated`
- codex_decision: `[需 codex 决策]`

#### `L9.media.social_buzz` — 社媒发酵  *(bucket A, spec `missing`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `event_driven`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

### 2.11 L10 验证指标（7）

#### `L10.industry.fund_flow` — 行业资金流验证  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `monthly_macro`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L10.industry.inventory_orders` — 行业库存/订单验证  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `monthly_macro`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L10.industry.pmi` — 行业景气指数  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `monthly_macro`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L10.industry.sales_price` — 行业销量/价格验证  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `monthly_macro`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L10.val.expansion_compression` — 估值扩张/压缩方向  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `monthly_macro`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L10.val.historical_quantile` — 估值历史分位  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `monthly_macro`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L10.val.peer` — 同业估值  *(bucket A, spec `○`, state `missing`)*

- route: `sqlite_hard`
- frequency: `monthly_macro`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

### 2.12 L11 股价结果（16）

#### `L11.long.business_model` — 商业模式稳定性  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.long.compete_moat` — 竞争格局/护城河  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.long.industry_space` — 行业空间  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.long.margin` — 长期利润率  *(bucket A, spec `○`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.long.score` — 长线综合影响分  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.mid.eps_upward` — EPS上修中线  *(bucket A, spec `$`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.mid.margin_guidance` — 毛利率/指引中线影响  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.mid.orders_revenue` — 订单/收入中线影响  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.mid.score` — 1-2季度综合影响分  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.mode` — 当前模式状态  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.short.event_impact` — 事件冲击分  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.short.flow_boost` — 资金放大分  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.short.score` — 1-5日综合影响分  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.short.sentiment_shift` — 情绪变化分  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.short.technical` — 技术面反应  *(bucket A, spec `✓`, state `SQLite`)*

- route: `sqlite_hard`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

#### `L11.trade.signal` — 交易意义信号  *(bucket B, spec `○`, state `SQLite`)*

- route: `derive`
- frequency: `daily_eod`
- immutability: `n/a (not LLM)`
- codex_decision: `default_accepted`

---

## 3. 重点决策区（codex 你看这里）

### 3.1 LLM 历史已填（被 X5 误擦） — 32 字段

> 默认建议：`route=llm_close`, `frequency=static_picture`, `immutability=explicit_refresh`。
> 这 32 字段已确认是公司/行业**静态画像**类。codex 只需要确认 default 或微调。

| dp_id | bucket | label | 默认 route | 默认 frequency |
|---|:-:|---|---|---|
| `L0.compete.new_entrant` | C | 新进入者/替代品 | `llm_close` | `static_picture` |
| `L0.compete.price_war` | C | 行业价格战 | `llm_close` | `static_picture` |
| `L0.cost.cac` | C | 行业获客成本 | `llm_close` | `static_picture` |
| `L0.cost.rent` | C | 行业租金成本 | `llm_close` | `static_picture` |
| `L0.demand.frequency` | C | 消费频次变化 | `llm_close` | `static_picture` |
| `L0.demand.penetration` | C | 渗透率变化 | `llm_close` | `static_picture` |
| `L0.demand.replacement` | C | 替换周期变化 | `llm_close` | `static_picture` |
| `L0.demand.terminal` | C | 终端需求变化 | `llm_close` | `static_picture` |
| `L0.demand.user_count` | C | 用户/订单数量变化 | `llm_close` | `static_picture` |
| `L0.price.discount` | C | 行业折扣力度 | `llm_close` | `static_picture` |
| `L0.price.pricing_power` | C | 行业提价能力 | `llm_close` | `static_picture` |
| `L0.supply.capacity` | C | 行业产能变化 | `llm_close` | `static_picture` |
| `L0.supply.chain_eff` | C | 供应链效率/人力供给 | `llm_close` | `static_picture` |
| `L0.supply.channel_service` | C | 行业渠道/服务供给 | `llm_close` | `static_picture` |
| `L1.position.channel_edge` | C | 渠道优势 | `llm_close` | `static_picture` |
| `L1.position.stickiness` | C | 客户粘性 | `llm_close` | `static_picture` |
| `L2.newbiz.tam` | D | 新业务市场空间 | `llm_web` | `static_picture` |
| `L2.newbiz.uncertainty` | C | 新业务不确定性 | `llm_close` | `static_picture` |
| `L3.channel.mix` | C | 渠道结构占比 | `llm_close` | `static_picture` |
| `L3.customer.segment_mix` | C | 客户类型结构 | `llm_close` | `static_picture` |
| `L3.delivery.csat` | D | 客户满意度 | `llm_web` | `static_picture` |
| `L3.delivery.lead_time` | D | 交付周期/服务能力 | `llm_web` | `static_picture` |
| `L3.product.lifecycle` | D | 产品生命周期/竞争力 | `llm_web` | `static_picture` |
| `L3.region.tier_mix` | C | 城市层级结构 | `llm_close` | `static_picture` |
| `L4.eff.capacity_utilization` | C | 产能利用率 | `llm_close` | `static_picture` |
| `L4.eff.conversion_retention` | D | 转化率/留存/复购 | `llm_web` | `static_picture` |
| `L4.price.discount` | C | 折扣率 | `llm_close` | `static_picture` |
| `L4.price.subscription` | C | 订阅价格 | `llm_close` | `static_picture` |
| `L4.share.customer_channel` | D | 客户/渠道/区域份额 | `llm_web` | `static_picture` |
| `L4.volume.foot_traffic` | D | 门店客流 | `llm_web` | `static_picture` |
| `L4.volume.frequency` | D | 使用频次 | `llm_web` | `static_picture` |
| `L5.surprise.buy_whisper` | E | 买方/whisper预期 | `skip` | `realtime_minute` |

### 3.2 X5 新增 26 字段（已加 SLOT_DEFS）

> 默认建议：`route=llm_close`。
> 这 26 字段是 X5 工作流已上 overlays.py 的新槽位；当前治理 schema
> 注册 111 个 dp_id，compiled stock overlay 为 112 个 graph nodes（含
> `company` root）。历史 "59 slot" 只保留为 X5-only 子集口径。
> codex 关注：frequency 决策（公司画像 → static_picture; 经营 → quarterly）。

| dp_id | bucket | label | 默认 route | 默认 frequency |
|---|:-:|---|---|---|
| `L0.price.contract_spot` | C | 合同价/现货价价差 | `llm_close` | `static_picture` |
| `L0.price.product_asp` | C | 行业产品价格/ASP | `llm_close` | `static_picture` |
| `L0.sentiment.social` | A | 社媒/主题热度 | `sqlite_hard` | `daily_eod` |
| `L0.supply.inventory` | C | 行业库存变化 | `llm_close` | `static_picture` |
| `L1.position.brand` | C | 品牌影响力 | `llm_close` | `static_picture` |
| `L1.position.cost_edge` | C | 成本优势 | `llm_close` | `static_picture` |
| `L1.position.market_share` | C | 公司市占率 | `llm_close` | `static_picture` |
| `L1.position.pricing_power` | C | 定价权 | `llm_close` | `static_picture` |
| `L1.position.tech_barrier` | C | 技术壁垒 | `llm_close` | `static_picture` |
| `L2.newbiz.commercialization` | C | 新业务商业化进度 | `llm_close` | `static_picture` |
| `L2.newbiz.revenue_contrib` | C | 新业务收入/利润贡献 | `llm_close` | `static_picture` |
| `L2.newbiz.valuation_contrib` | C | 新业务估值贡献 | `llm_close` | `static_picture` |
| `L2.segment.business_risk` | C | 业务线业务风险 | `llm_close` | `static_picture` |
| `L2.segment.cash_contrib` | C | 业务线现金流贡献 | `llm_close` | `static_picture` |
| `L2.segment.compete_landscape` | C | 业务线竞争格局 | `llm_close` | `static_picture` |
| `L2.segment.industry_exposure` | C | 业务线行业暴露度 | `llm_close` | `static_picture` |
| `L3.channel.overseas` | C | 海外渠道 | `llm_close` | `static_picture` |
| `L3.customer.solvency` | C | 客户支付能力 | `llm_close` | `static_picture` |
| `L3.delivery.capacity_supply` | C | 产能/供应链 | `llm_close` | `static_picture` |
| `L3.region.key_risk` | C | 重点/高风险区域 | `llm_close` | `static_picture` |
| `L4.cost.cac_production` | C | 获客/单位生产成本 | `llm_close` | `static_picture` |
| `L4.cost.rent_energy_logistics` | C | 租金/能源/物流成本 | `llm_close` | `static_picture` |
| `L4.eff.store_labor` | C | 门店坪效/人效 | `llm_close` | `static_picture` |
| `L4.price.asp_aov_arpu` | C | ASP/客单价/ARPU | `llm_close` | `static_picture` |
| `L4.price.elasticity` | C | 价格弹性 | `llm_close` | `static_picture` |
| `L4.price.pricing_power` | C | 提价能力 | `llm_close` | `static_picture` |

### 3.3 ⚠️ LLM 候选但从未在 pipeline — 55 字段

> 这 55 字段 spec 分类为 C bucket，但既不在 hist32 也不在 X5-26；
> 其中 49 个完全 missing / 6 个在 SQLite 是 partial fetcher 落库的近似（需 X5 复填）。
> **codex 决策重点**：是否纳入下一批 LLM trial？哪些 prompt evidence_sources 已具备？

#### 3.3.a 完全 missing 49 个（C bucket 新候选）

| dp_id | bucket | label | spec | 默认建议 |
|---|:-:|---|:-:|---|
| `L0.compete.share_concentration` | C | 市占率/集中度变化 | `○` | `route=llm_close` `freq=static_picture` `[需 codex 决策]` |
| `L0.cost.labor` | C | 行业人工成本 | `○` | `route=llm_close` `freq=static_picture` `[需 codex 决策]` |
| `L0.policy.access_license` | C | 准入与牌照 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L0.policy.regulation` | C | 监管/反垄断 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L0.policy.subsidy` | C | 行业补贴政策 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L0.policy.tax_trade` | C | 税收/出口限制 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L0.tech.ai_automation` | C | AI/自动化/降本 | `○` | `route=llm_close` `freq=static_picture` `[需 codex 决策]` |
| `L0.tech.breakthrough` | C | 技术突破/产品迭代 | `○` | `route=llm_close` `freq=static_picture` `[需 codex 决策]` |
| `L0.tech.substitute_tech` | C | 替代技术 | `○` | `route=llm_close` `freq=static_picture` `[需 codex 决策]` |
| `L1.moat.tags` | C | 护城河标签 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L1.model.tag` | C | 商业模式标签 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L1.position.growth_rank` | C | 增速排名 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L1.role.tag` | C | 行业角色标签 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L1.stock_attr.tags` | C | 股价属性标签 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L2.segment.opex_ratio` | C | 业务线费用率 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L2.segment.profit_share` | C | 业务线利润占比 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L3.channel.cost` | C | 渠道费用 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L3.channel.efficiency` | C | 渠道效率 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L3.customer.concentration` | C | 客户集中度/流失风险 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L3.delivery.fulfillment_cost` | C | 履约/售后成本 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L3.product.margin_mix` | C | 产品毛利/价格结构 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L3.product.portfolio` | C | 产品组合结构 | `missing` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L3.region.domestic_overseas` | C | 国内/海外收入结构 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L3.region.fx_geo` | C | 汇率/地缘影响 | `○` | `route=llm_close` `freq=annual_filing` `[需 codex 决策]` |
| `L4.share.market` | C | 公司市占率 | `○` | `route=llm_close` `freq=quarterly_filing` `[需 codex 决策]` |
| `L4.share.substitution` | C | 竞品替代 | `○` | `route=llm_close` `freq=quarterly_filing` `[需 codex 决策]` |
| `L4.volume.orders` | C | 订单量 | `○` | `route=llm_close` `freq=quarterly_filing` `[需 codex 决策]` |
| `L4.volume.sales` | C | 销量 | `○` | `route=llm_close` `freq=quarterly_filing` `[需 codex 决策]` |
| `L4.volume.shipments` | C | 出货量/交付量 | `○` | `route=llm_close` `freq=quarterly_filing` `[需 codex 决策]` |
| `L4.volume.users` | C | 客户/用户数 | `○` | `route=llm_close` `freq=quarterly_filing` `[需 codex 决策]` |
| `L5.fcst.beat_probability` | C | 业绩兑现概率 | `○` | `route=llm_close` `freq=quarterly_filing` `[需 codex 决策]` |
| `L8.gov.fraud_control` | C | 财务造假/内控 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L8.gov.litigation` | C | 法律诉讼 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L8.industry.substitute` | C | 替代品出现 | `○` | `route=llm_close` `freq=quarterly_filing` `[需 codex 决策]` |
| `L8.op.customer_channel` | C | 客户流失/渠道失效 | `○` | `route=llm_close` `freq=quarterly_filing` `[需 codex 决策]` |
| `L8.op.order_miss` | C | 订单不兑现 | `○` | `route=llm_close` `freq=quarterly_filing` `[需 codex 决策]` |
| `L8.op.product_fail` | C | 产品失败 | `○` | `route=llm_close` `freq=quarterly_filing` `[需 codex 决策]` |
| `L8.reg.license_risk` | C | 牌照/准入风险 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L8.reg.subsidy_off` | C | 补贴退坡 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L8.reg.tax_trade` | C | 税收/出口限制 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L8.reg.tighten` | C | 监管收紧/反垄断 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L8.shock.black_swan` | C | 黑天鹅事件 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L8.shock.crisis` | C | 安全/舆情危机 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L8.shock.supply_break` | C | 供应中断/客户违约/自然灾害 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L9.company.ma` | C | 并购 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L9.company.product_order` | C | 新产品发布/大订单 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L9.industry.data_price` | C | 行业数据/价格发布 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L9.macro.geo` | C | 地缘事件 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |
| `L9.media.short_report` | C | 做空报告 | `○` | `route=llm_close` `freq=event_driven` `[需 codex 决策]` |

#### 3.3.b SQLite alias 占位 6 个（X5 复填候选）

> 这 6 个 dp_id 在 SQLite emit 但语义可能是 partial fetcher 的近似值（如 `L0.cost.raw_material` 接近大宗商品价格）；
> codex 需要决策：让 LLM 重写还是保留 SQLite 数据。

| dp_id | bucket | label | 默认建议 |
|---|:-:|---|---|
| `L0.cost.energy_logistics` | C | 行业能源/物流成本 | `route=llm_close` 但 SQLite 已有 alias 数据；codex 决策是否 override `[需 codex 决策]` |
| `L0.cost.raw_material` | C | 原材料价格 | `route=llm_close` 但 SQLite 已有 alias 数据；codex 决策是否 override `[需 codex 决策]` |
| `L8.industry.demand_supply` | C | 行业需求/供给恶化 | `route=llm_close` 但 SQLite 已有 alias 数据；codex 决策是否 override `[需 codex 决策]` |
| `L8.industry.price_war` | C | 行业价格战 | `route=llm_close` 但 SQLite 已有 alias 数据；codex 决策是否 override `[需 codex 决策]` |
| `L9.industry.compete_risk` | C | 行业竞争/风险事件 | `route=llm_close` 但 SQLite 已有 alias 数据；codex 决策是否 override `[需 codex 决策]` |
| `L9.industry.policy_change` | C | 行业政策变化 | `route=llm_close` 但 SQLite 已有 alias 数据；codex 决策是否 override `[需 codex 决策]` |

### 3.4 Bucket D 8 字段（web-llm 候选）

> 这 8 字段 C bucket 闭环数据不充分，必须 web 才能填。
> codex 决策重点：现在就开 web 还是先 fallback 到 C bucket close-LLM 试一次？

| dp_id | label | 必需 web 源 | 默认建议 |
|---|---|---|---|
| `L2.newbiz.tam` | 新业务市场空间 | IDC/Gartner/Counterpoint | `route=llm_web` `freq=static_picture` `[需 codex 决策: 开 web 还是降级 C]` |
| `L3.delivery.csat` | 客户满意度 | Trustpilot/App Store/黑猫投诉 | `route=llm_web` `freq=static_picture` `[需 codex 决策: 开 web 还是降级 C]` |
| `L3.delivery.lead_time` | 交付周期/服务能力 | 渠道调研/Reddit/雪球 | `route=llm_web` `freq=static_picture` `[需 codex 决策: 开 web 还是降级 C]` |
| `L3.product.lifecycle` | 产品生命周期/竞争力 | 中信/中金/Goldman 行业 PDF | `route=llm_web` `freq=static_picture` `[需 codex 决策: 开 web 还是降级 C]` |
| `L4.eff.conversion_retention` | 转化率/留存/复购 | 用户调研稿/三方 app 数据 | `route=llm_web` `freq=static_picture` `[需 codex 决策: 开 web 还是降级 C]` |
| `L4.share.customer_channel` | 客户/渠道/区域份额 | IDC/Counterpoint/IHS/中怡康 | `route=llm_web` `freq=static_picture` `[需 codex 决策: 开 web 还是降级 C]` |
| `L4.volume.foot_traffic` | 门店客流 | Sensormatic/Placer.ai/极海 | `route=llm_web` `freq=static_picture` `[需 codex 决策: 开 web 还是降级 C]` |
| `L4.volume.frequency` | 使用频次 | QuestMobile/Sensor Tower/七麦 | `route=llm_web` `freq=static_picture` `[需 codex 决策: 开 web 还是降级 C]` |

### 3.5 边界 case

> spec 元数据与实测不一致 / 语义模糊的字段，需 codex 决策最终归属。

| dp_id | 当前 bucket | 边界争议 | 建议 |
|---|:-:|---|---|
| `L6.mult.dcf` | E（spec `$`）/ A（实测 SQLite） | FMP `/discounted-cash-flow` Starter tier 已能访问 | spec 应改 ✓; 默认 `route=sqlite_hard` |
| `L7.flow.institutional` | E（spec `$`）/ A 实测 SQLite | Tushare `top_list` 龙虎榜代理填入；语义近似 | 接受 alias; `route=sqlite_hard` with low-confidence flag |
| `L6.mult.forward_pe` | E（spec `$`）→ B 候选 | Tushare `forecast` EPS / 股价可派生 | 升 `route=derive`（依赖 L5.fcst.* 补完） |
| `L7.trade.gamma` | E（spec `$`）→ B 候选 | Futu LV2 期权链可推（已 ○ partial） | 升 `route=derive`（前提 Futu 期权稳定） |
| `L5.surprise.buy_whisper` | E（实测 OverlayKnown）| LLM 是否能 simulate buy-side whisper? | `route=skip`（接受永久 Unknown）或 `llm_close`（低 confidence） |
| `L1.position.tech_barrier` | C / D 中间 | 部分需要专利数据库 | `route=llm_close` 主体 + 允许 D fallback |
| `L1.position.brand` | C | 行业研报有可能给品牌价值排名 | `route=llm_close`; evidence 允许引外部 ranking |
| `L8.industry.substitute` | C-leaning-D | 替代技术判断常依赖券商 | `route=llm_close`，未来 M2 升 D |
| `L4.price.subscription` | C-leaning-D（互联网公司） | 公司 pricing page 有；IR 不一定全答 | `route=llm_close`，允许 evidence 引官网 pricing |
| `L4.eff.capacity_utilization` | C | 业绩会有部分；周期股专门披露 | `route=llm_close` `freq=quarterly_filing` |

---

## 4. 输出格式

codex 处理完后回写本文件：
1. 所有 C/D bucket 字段下 `[需 codex 决策]` 占位替换为 `codex_decision:` YAML block
2. A/B/E bucket 字段保留 `default_accepted` 或 codex override 为新值
3. 在边界 case 区域（§3.5）给出 final binding 决策

## 5. 注意事项

- 不要凭训练记忆改 spec 字段语义
- 决策依据：本地数据可行性 + 字段语义 + frequency 合理性
- 有疑问的字段在 `notes` 写"待人类 review"
- **关键 immutability 红线**：codex 决策填了 frequency = static_picture 的字段，schema/compile 操作必须保留 value（防 X5 误擦事件复发）

---

## 6. 数据来源与方法

- spec 250 dp_id: `config/data_point_roles.yaml`
- bucket 分类: `docs/data_sources/field_strategy_v1.md` §2 完整决策表（已校验全 250 字段映射）
- 5 源覆盖: `docs/data_sources/coverage_audit.md` §7
- SQLite 实测: `runtime/hot.sqlite` `realtime_current` (181 distinct dp_id, 136 在 spec 250 内)
- overlay 实测: `config/{industry,stock}_overlays/**/*.yaml` (stock overlay 每文件 112 graph nodes；Known/Optionality 48 total / 47 in spec)
- 历史 32 / X5 26: prompt context（已在 §3.1 / §3.2 单独列出）
