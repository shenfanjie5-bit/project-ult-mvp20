# Codex Fill Guide — 公司图谱 LLM 衍生 + spec 缺失字段填充

> 主指南。任何 codex CLI 调用都应当先消化本文档，再处理 per-overlay prompt。

## 任务

把 `config/{industry_overlays,stock_overlays}/**/*.yaml` 里 `data_status: Unknown` 的 LLM 衍生节点填上 `value` + `confidence` + `evidence_sources`。**无信息时保留 `Unknown` 并填 `missing_reason`**。

字段标准、状态机、缺失策略 100% 以 `图谱设计.md` 为准（v2 完整版 12 层）。

---

## 1. 哪些字段要填

每只公司 overlay 有 **33 个节点**，其中 **32 个是 LLM 衍生**（剩 1 个是 `company` 主节点，已自动填）。32 个分布：

| 层 | 字段数 | 例 |
|---|---:|---|
| **L0 行业母图接入**（14 条） | 14 | `L0.demand.terminal` / `L0.supply.capacity` / `L0.price.pricing_power` ... |
| **L1 公司定位** | 2 | `L1.position.channel_edge` / `L1.position.stickiness` |
| **L2 新业务期权** | 2 | `L2.newbiz.tam` / `L2.newbiz.uncertainty` |
| **L3 产品/客户/渠道/区域** | 6 | `L3.product.lifecycle` / `L3.customer.segment_mix` ... |
| **L4 经营软指标** | 7 | `L4.volume.foot_traffic` / `L4.eff.capacity_utilization` ... |
| **L5 财务场外信号** | 1 | `L5.surprise.buy_whisper` |

**L0 行业级 14 条优先填 `industry_overlay`**（每行业一份），公司 overlay 通过 `inherit_from_industry: true` 继承。L1-L5 公司专属在公司 overlay 里填。

---

## 2. 关键字段填法（每个 node 项内）

| 字段 | 填法 |
|---|---|
| `data_status` | **`Known`** 有信息填完时<br>**`Unknown`** 找不到信息时（保留，**不要改成 N/A**）<br>**`N/A`** 公司天然不适用时（如订阅价对非订阅模式公司）<br>**`Inactive`** 节点存在但当前无事件触发（如价格战字段，没价格战时） |
| `value` | 结构化 JSON dict（不是单 scalar）。参考 `docs/data_sources/llm_derived_nodes.md` 每个 dp_id 的 `output_schema` |
| `confidence` | 0-1 浮点。LLM 衍生通常 < 0.7。证据强写 0.65-0.75；弱写 0.35-0.55 |
| `evidence_quality` | `low` / `medium` / `high`。一手数据缺失默认 `low`；年报/研报为 `medium`；多源交叉验证 `high` |
| `evidence_sources` | 列表，详见下文 §2a。**按 model_tier 分层**——closed-loop tier 只允本地引用；web_analysis tier 允许 web kind 且必须含 `url + checksum + fetched_at` |
| `last_updated` | ISO 时间戳，例 `"2026-05-11T12:00:00+08:00"` |
| `missing_reason` | 当 `data_status: Unknown` 时**必填**。例：`"pending LLM/company-specific research"` / `"信息不可得：公司未披露此项"` |

**不动**的字段（codex 不要改）：
- `node_id` / `dp_id` / `node_name` / `node_type` / `layer` / `parent_node` / `child_nodes`
- `direction` / `base_weight` / `time_horizon`
- `required_level` / `missing_policy` / `alert_policy` / `calculation_type` / `aggregation_policy`
- `materiality` / `derived_slot` / `inherit_from_industry`

---

## 2a. Evidence sources (按 model_tier 分层)

每个 dp_id 在 `config/llm_field_governance.yaml`（Z1b 任务，未来产出）声明一个 `model_tier`。
verifier `scripts/verify_overlay_closed_loop.py` 按此 tier 决定允许哪些 `evidence_sources.kind`。
没有 governance.yaml 时（pre-Z1b）默认按 closed-loop 严格闭环。

### closed-loop 字段 (`model_tier ∈ {cheap_extract, cheap_classify, analysis}`)

`evidence_sources` **只允许**以下 kind：

| kind | source 字段含义 | 示例 |
|---|---|---|
| `local_dp_id` | 引用 prompt 里 inline 的 SQLite dp_id | `source: "L5.is.revenue@runtime/hot.sqlite"` |
| `local_overlay` | 引用本地 yaml 节点 | `source: "config/industry_overlays/AI_COMPUTE.yaml#L0.demand.terminal"` |
| `industry_inference` | 行业框架推断（confidence ≤ 0.5） | `source: "industry_framework"`, `reasoning: "..."` |

**严禁**：web URL / annual_report PDF / research_report / 任何 `http(s)://` 引用。

找不到本地证据 → `data_status: Unknown` + `missing_reason: "no_local_evidence"`。

### web-enabled 字段 (`model_tier == web_analysis`)

允许 closed-loop 三种 kind + 以下额外 kind：

| kind | 必填字段 |
|---|---|
| `annual_report` | url, checksum (sha256), fetched_at (ISO), excerpt |
| `research_report` | url, checksum, fetched_at, publisher, excerpt |
| `investor_relations` | url, checksum, fetched_at, excerpt |
| `external_url` | url, checksum, fetched_at, kind_detail, excerpt |

**所有 web evidence 必须含 `url + checksum + fetched_at`**——便于 audit + replay。

未带 checksum 的 web evidence 视为 `evidence_quality=low` + `confidence ≤ 0.5`。

### 通用规则（两种 tier 都适用）

- `evidence_sources` 数组 ≥ 1 条；为 0 → `data_status: Unknown`
- `confidence ∈ [0, 1]`
- `last_updated`: ISO timestamp
- 不许 hallucinate URL —— 任何 web kind 的 url 必须真实可访问

---

## 3. 处理 5 种缺失情况（必读：`图谱设计.md` 第 23 节）

| 情况 | data_status | missing_policy | 怎么处理 |
|---|---|---|---|
| 公司天然不适用 | `N/A` | `not_applicable_remove` | 删除该节点的参与权重（父节点重归一化）—— 例：非订阅公司的 `L4.price.subscription` |
| 理论适用但拿不到 | `Unknown` | `unknown_reduce_confidence` | 保留节点，降置信度 — 例：未披露的产能利用率 |
| 节点存在但无事件 | `Inactive` | `inactive_zero_weight` | active_weight=0，事件触发时恢复 — 例：政策风险节点暂无监管事件 |
| 适用但影响很小 | `Low Materiality` | (可折叠) | 收入/利润占比 < 5% 的业务线 |
| 期权价值节点 | `Optionality` | (拆分当前 vs 未来) | 新业务 TAM 字段 |

**默认行为**：找不到信息 → `Unknown` + `missing_reason` 写清原因。**不要瞎编**。

---

## 4. 4 类输入材料（按优先级）

按 spec 23 节"证据型子节点"原则：

1. **年报 / 半年报 / 季报**（最高优先级，公司官方披露）
2. **业绩说明会纪要 / 调研笔记**（公司管理层第一手）
3. **第三方研报**（券商行业 / 公司研报）
4. **行业数据库** / 媒体报道（最低优先级）

每个 `evidence_sources` 项必须包含真实来源（不要 hallucinate URL）。如果没找到证据 → `Unknown`。

---

## 5. 行业级（L0）vs 公司级（L1-L5）的分工

**`industry_overlays/<industry_id>.yaml`** 由本指南填 14 条 L0 字段：
- 这 14 条**只填一次**，所有该行业公司通过 `inherit_from_industry: true` 共享
- L0 字段例：`L0.demand.terminal`（终端需求变化）/ `L0.supply.capacity`（产能变化）/ `L0.price.pricing_power`（提价能力）

**`stock_overlays/<industry_id>/<ts_code>.yaml`** 由本指南填 18 条 L1-L5 公司字段：
- 同一公司跨多个行业（如 胜宏科技-H 跨 AI_COMPUTE/SEMI_EQUIPMENT/CONSUMER_ELECTRONICS）需要每个 overlay 都填，但 L1-L5 应当**一致**（公司本质不会因行业视图变）

---

## 6. 执行步骤（codex CLI 推荐工作流）

### Phase 1: 行业 overlay 14 字段（一次性）

对每个 industry_overlay YAML：

```bash
# 由 mvp20 助手脚本生成 per-industry prompt（含已填行业图谱节点 + spec 14 条任务）
.venv/bin/python scripts/codex_prompt_gen.py \
    --industry AI_COMPUTE \
    --out /tmp/codex_AI_COMPUTE.md

# 喂给 codex CLI
codex --prompt-file /tmp/codex_AI_COMPUTE.md
```

预计 12 个 active 行业（SPACE_ECONOMY pending 不处理）× 1 次调用 = **12 次**。

### Phase 2: 公司 overlay 18 字段（每股一次）

```bash
.venv/bin/python scripts/codex_prompt_gen.py \
    --industry STORAGE_GRID \
    --ts-code 300750.SZ \
    --out /tmp/codex_300750_SZ.md

codex --prompt-file /tmp/codex_300750_SZ.md
```

预计 353 个 overlay 文件 × 1 = **353 次调用**。可并行（codex CLI 支持 batch）。

### Phase 3: 校验

```bash
.venv/bin/mvp20 validate-overlays  # 重跑校验，alerts 数应当大幅下降
.venv/bin/mvp20 compile-overlays --db runtime/hot.sqlite  # 重新编译
.venv/bin/mvp20 audit-injection  # 看新覆盖率
```

---

## 7. 输出 YAML 范例（公司级 L1.position.channel_edge）

```yaml
- node_id: 300750.SZ:L1.position.channel_edge
  dp_id: L1.position.channel_edge
  node_name: 渠道/供应链位置优势
  node_type: Company Position
  layer: company_position
  parent_node: 300750.SZ:company
  direction: positive
  base_weight: 1.0
  active_weight: 1.0
  time_horizon: [short, medium, long]
  status: Known                          # ← codex 改
  update_frequency: quarterly
  required_level: conditional_required
  data_status: Known                     # ← codex 改: Unknown → Known
  missing_policy: unknown_reduce_confidence
  calculation_type: multiplicative_factor
  aggregation_policy: multiply_chain
  alert_policy: warn_if_material
  materiality: 0.75
  derived_slot: true
  inherit_from_industry: false
  value:                                 # ← codex 新增（按 llm_derived_nodes.md L1 output_schema）
    strength: 显著
    components:
      - 直供海外汽车厂（特斯拉/宝马/福特/大众）一线品牌
      - 国内动力电池配套份额超 35%
      - 与下游车企长协订单可见性高
    peers_comparison:
      vs_byd: "近似规模，CATL 海外渠道更深"
      vs_lg: "CATL 中国本土供应链优势明显"
  confidence: 0.72                       # ← codex 新增
  evidence_quality: medium               # ← codex 新增
  evidence_sources:                      # ← codex 新增
    - kind: annual_report
      title: 宁德时代 2025 年报第三节"业务概况"
      source: szse.cn 公告
      published_at: "2026-03-15"
      excerpt: "公司动力电池系统国内市占率 36.7%，海外市占率 26.5%..."
    - kind: research_report
      title: 中信证券深度报告《CATL：全球动力电池龙头护城河》
      source: 中信证券
      published_at: "2026-02-20"
      excerpt: "公司与特斯拉/福特/大众/Stellantis 等海外车企..."
  last_updated: "2026-05-11T15:30:00+08:00"
```

---

## 8. 输出 YAML 范例（无信息时 — `Unknown` 保留）

```yaml
- node_id: 300750.SZ:L4.volume.foot_traffic
  dp_id: L4.volume.foot_traffic
  node_name: 门店客流
  data_status: N/A                       # 宁德是 B2B 制造商，无门店模式
  missing_policy: not_applicable_remove
  missing_reason: "宁德时代是 B2B 动力电池制造商，无零售门店渠道"
  ... (其他字段保持不变)
```

或：

```yaml
- node_id: 300750.SZ:L4.eff.capacity_utilization
  dp_id: L4.eff.capacity_utilization
  node_name: 产能利用率
  data_status: Unknown                   # 公司未披露具体数字
  missing_reason: "公司年报披露'产能持续扩张'但未给具体利用率%"
  ... (其他字段保持不变)
```

---

## 9. 幂等规则

- 跑两遍 codex，已填的 `data_status: Known` 节点**不要重填**（除非新信息出现）
- 跑两遍，已标 `N/A` 的节点不要变成 `Unknown` 反之亦然
- `last_updated` 仅在 value 真正改变时更新

---

## 10. 关键文件清单

| 文件 | 用途 |
|---|---|
| `图谱设计.md` | spec v2 完整版，字段定义、状态机权威 |
| `docs/data_sources/coverage_audit.md` | spec 250 数据点覆盖矩阵 |
| `docs/data_sources/llm_derived_nodes.md` | 32 LLM 衍生节点的 prompt 模板 + output_schema |
| `docs/audit/injection_audit.csv` | 当前每公司已填字段，避免重复 |
| `config/industry_overlays/<id>.yaml` | 行业级 overlay（14 L0 字段，编辑此处）|
| `config/stock_overlays/<id>/<ts>.yaml` | 公司 overlay（18 L1-L5 字段，编辑此处）|
| `scripts/codex_prompt_gen.py` | 生成 per-overlay 具体 prompt |

---

## 11. 不要做的事

- ❌ 不要 hallucinate 数据 — 找不到证据填 `Unknown`
- ❌ 不要修改 `图谱设计.md` / `coverage_audit.md` / `llm_derived_nodes.md`（这些是输入）
- ❌ 不要改 overlay 的 `node_id` / `dp_id` / `child_nodes` / `parent_node`（结构由 mvp20 编译器维护）
- ❌ 不要改 `industry_graphs/*.yaml`（行业母图 freeze）
- ❌ 不要改 `realtime_current` 或 SQLite（由 collector / derive 管理）
- ❌ 不要新建 dp_id（spec 已 freeze 250）
