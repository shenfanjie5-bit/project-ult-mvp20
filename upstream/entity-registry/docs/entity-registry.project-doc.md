# entity-registry 完整项目文档

> **文档状态**：Draft v1
> **版本**：v0.1.1
> **作者**：Codex
> **创建日期**：2026-04-15
> **最后更新**：2026-04-15
> **文档目的**：把 `entity-registry` 子项目从“几张实体表”这种静态理解收束为可立项、可拆分、可实现、可验收的正式项目，使其成为主项目中唯一负责 ENT_* 命名空间、实体主数据、别名体系、引用记录、消歧决策与 mention resolution 的公共能力模块。

---

## 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| v0.1 | 2026-04-15 | 初稿 | Codex |
| v0.1.1 | 2026-04-15 | 补充 LLM 依赖硬边界、两级解析分工和禁止自建 runtime 安全栈约束 | Codex |

---

## 1. 一句话定义

`entity-registry` 是主项目中**唯一负责定义和维护 `canonical_entity` / `entity_alias` / `entity_reference` / `resolution_case` 四类对象，并把裸文本引用稳定解析为 ENT_* canonical_entity_id** 的实体主数据与解析模块，它以“ENT_* 命名空间唯一”“上市公司 ID 锚定交易所编码不随更名变化”和“实体解析与业务判断严格分离”为不可协商约束。

它不是数据采集模块，不是主系统推荐模块，也不是图谱传播模块。  
它不负责 Tushare 等数据源抓取，不负责 L4-L7 业务判断，也不直接拥有 LLM runtime。

---

## 2. 文档定位与核心问题

本文解决的问题不是“怎么做一个别名字典”，而是：

1. **统一实体真相问题**：如果各模块自己发明股票、公司、机构、人物的 ID 和别名映射，整个主项目的图谱、候选信号和 formal 对象都会失去一致实体锚点。
2. **解析链路闭环问题**：系统不仅需要静态主数据，还需要记录原始引用、解析过程和消歧决策，否则后续审计、回滚和人工复查都无从谈起。
3. **启动顺序与边界问题**：`entity-registry` 既依赖 `data-platform` 提供的 `stock_basic` canonical 输入，又被 Layer B 校验、主系统、图谱和子系统依赖，必须先把 OWN/BAN/EDGE 写清楚，避免循环依赖。

---

## 3. 术语表

| 术语 | 定义 | 备注 |
|------|------|------|
| Canonical Entity | 系统级正式实体对象 | 以 `canonical_entity_id` 唯一标识 |
| Canonical Entity ID | 实体正式 ID | 如 `ENT_STOCK_300750.SZ` |
| Entity Alias | canonical entity 的别名映射 | 如简称、全称、英文名、代码、曾用名 |
| Entity Reference | 一次原始引用记录 | 包含 raw mention、上下文、解析结果 |
| Resolution Case | 一次消歧决策记录 | 包含候选集合、最终选择、理由 |
| Deterministic Matching | 查表、代码匹配、规则匹配等确定性解析 | 实体解析第一层 |
| Fuzzy Matching | Blocking + 相似度 + clustering 的模糊解析 | 实体解析第二层的一部分 |
| Mention Resolution | 基于上下文把一次 mention 归到正确实体的过程 | 可调用 LLM 辅助 |
| Unresolved Reference | 尚未完成解析的引用 | 不允许直接伪造 canonical ID |
| Cross Listing | A+H 等双地上市关联 | 双上市分别独立 ID，再做关联 |

**规则**：
- 所有系统内正式引用实体的对象最终都应落到 `canonical_entity_id`
- 未解析实体必须进入 `entity_reference` / `resolution_case`，不能直接丢弃
- `canonical_entity_id` 生成规则由 `entity-registry` 拥有，规则版本通过 `contracts` 发布

---

## 4. 目标与非目标

### 4.1 项目目标

1. **建立 ENT_* 命名空间**：建立统一的 canonical entity 标识规则和对象模型。
2. **初始化上市公司主数据**：从 `stock_basic` canonical 结果初始化 `canonical_entity` 和 `entity_alias`。
3. **提供实体解析能力**：实现确定性匹配、模糊匹配、LLM 辅助消歧和 mention resolution 接口。
4. **保留解析审计链**：通过 `entity_reference` 和 `resolution_case` 记录原始引用与决策路径。
5. **支撑跨模块引用**：让 `main-core`、`graph-engine`、子系统、Layer B 校验都能使用统一实体锚点。
6. **支持批量解析与回补**：支持离线批处理、未解析引用回补和人工复核队列。
7. **避免启动死锁**：明确 `data-platform` 先提供 `stock_basic` canonical 输入，`entity-registry` 再完成主数据与完整解析能力。

### 4.2 非目标

- **不负责原始数据抓取**：Tushare/公告/新闻等源数据接入归 `data-platform` 或各子系统。
- **不负责业务推荐**：选股、排序、recommendation、world state 判断归 `main-core`。
- **不负责图谱算法**：图谱节点/边的传播计算归 `graph-engine`，本模块只提供实体锚点和关联能力。
- **不直接绑定 provider SDK，也不复制 runtime 安全栈**：LLM 辅助消歧统一通过 `reasoner-runtime` 调用，本模块不得自建 provider client、PII scrub、retry/backoff 或 lineage 记录逻辑。
- **不把未解析文本直接当正式实体**：裸文本 mention 不允许绕过解析流程直接进入 formal 链路。

---

## 5. 与现有工具的关系定位

### 5.1 架构位置

```text
data-platform canonical stock_basic + contracts + reasoner-runtime
  -> entity-registry
      ├── canonical_entity
      ├── entity_alias
      ├── entity_reference
      ├── resolution_case
      ├── deterministic matcher
      ├── fuzzy matcher
      └── mention resolution API
  -> consumers
      ├── main-core
      ├── graph-engine
      ├── subsystem-*
      ├── subsystem-sdk / Layer B validation
      └── audit / review flows
```

### 5.2 上游输入

| 来源 | 提供内容 | 说明 |
|------|----------|------|
| `contracts` | ENT_* 相关 schema、规则版本、解析接口合同 | 本模块不能绕开合同定义 |
| `data-platform` | `stock_basic` canonical 表、后续结构化主数据 | 这是初始化与增量更新的正式输入 |
| `reasoner-runtime` | LLM 辅助消歧调用能力 | 仅在第二层解析中消费 |
| `subsystem-*` / `main-core` / `graph-engine` | 原始 mention、上下文、待解析实体引用 | 通过 API 或批任务输入 |
| `assembly` | 配置、运行环境、批任务入口 | 部署与运行注入不归本模块定义 |

### 5.3 下游输出

| 目标 | 输出内容 | 消费方式 |
|------|----------|----------|
| `main-core` | `canonical_entity`、entity profile、mention resolution 结果 | Python API / DuckDB 读取 |
| `graph-engine` | 统一实体锚点、cross listing / alias 查询能力 | Python API / 表读取 |
| `subsystem-*` | mention resolution API、批量解析任务 | Python API |
| `subsystem-sdk` / Layer B | canonical_entity_id 可解析性检查 | Python API / 校验器 |
| `audit-eval` / 人工复核 | `entity_reference`、`resolution_case` | 读取解析审计链 |

### 5.4 核心边界

- **ENT_* 命名空间和实体解析只归 `entity-registry`**
- **`stock_basic` 的 canonical 写入归 `data-platform`，`canonical_entity` 初始化归 `entity-registry`**
- **LLM 辅助消歧依赖 `reasoner-runtime`，但业务 prompt 语义归本模块解析逻辑**
- **两级解析都由本模块拥有业务语义，但第二级模型辅助裁决必须经由 `reasoner-runtime` 的公开结构化接口**
- **未解析文本不能直接变成 formal 引用**
- **A+H 双上市分别拥有独立 canonical ID，再通过关联关系连接**

---

## 6. 设计哲学

### 6.1 设计原则

#### 原则 1：Entity Truth Comes First

实体 ID 一旦漂移，后续图谱、信号、特征、formal recommendation 全都会漂移。  
因此 `canonical_entity_id` 规则和别名体系必须先稳定，再谈上层业务融合。

#### 原则 2：Reference Before Confidence

所有解析都要先把原始引用留住，再谈最终置信度。  
没有 `entity_reference` 和 `resolution_case`，任何“看起来解析成功”的结果都不可审计。

#### 原则 3：Deterministic First, LLM Second

确定性匹配永远是第一层。  
只有在查表、代码匹配、规则匹配和模糊候选仍不能判定时，才进入 LLM 辅助消歧，这样才能控制成本和可解释性。

#### 原则 4：Start Small, Resolve Fully Later

P1 先完成上市公司主数据和最小实体锚点，P4 再完善 HanLP/Splink/LLM 解析链。  
这样可以避免 `data-platform` 和 `entity-registry` 在初始化阶段互相阻塞。

### 6.2 反模式清单

| 反模式 | 为什么危险 |
|--------|-----------|
| 用数据源原始 code/id 直接当系统 canonical ID | 一旦换源或改名，全链路引用失效 |
| 未解析 mention 直接写到 formal 对象中 | 下游无法统一 join 和审计 |
| 所有解析都直接走 LLM | 成本高、稳定性差、无法解释 |
| 让 `entity-registry` 直接依赖 Tushare adapter 私有实现 | 形成对 `data-platform` 内部实现的反向耦合 |
| A+H 双上市共用一个 canonical ID | 会把交易所维度、报价维度和业务维度混在一起 |

---

## 7. 用户与消费方

### 7.1 直接消费方

| 消费方 | 消费内容 | 用途 |
|--------|----------|------|
| `main-core` | canonical entity / profile / resolution | L1 对象层、L5/L6 分析上下文 |
| `graph-engine` | 统一实体 ID 与 cross listing 关系 | 图谱节点锚点 |
| `subsystem-*` | mention resolution、批量解析 | 文本抽取和分类后对齐正式实体 |
| `subsystem-sdk` / Layer B 校验 | canonical_entity_id resolvable 检查 | 输入治理 |

### 7.2 间接用户

| 角色 | 关注点 |
|------|--------|
| 主编 / 架构 owner | 实体是否能跨模块稳定对齐 |
| reviewer | 是否有人绕过 ENT_* 命名空间 |
| 人工复核人员 | 未解析引用和消歧决策是否可追踪 |

---

## 8. 总体系统结构

### 8.1 初始化主线

```text
data-platform stock_basic canonical
  -> initialize canonical_entity
  -> initialize entity_alias
  -> expose ENT_* base registry
```

### 8.2 解析主线

```text
raw mention + source context
  -> deterministic matching
  -> fuzzy candidate generation
  -> optional LLM-assisted disambiguation
  -> write entity_reference / resolution_case
  -> return canonical_entity_id or unresolved
```

### 8.3 批量回补主线

```text
unresolved references
  -> batch clustering / Splink
  -> candidate shortlist
  -> manual review or LLM assist
  -> promote to canonical entity / alias
```

---

## 9. 领域对象设计

### 9.1 持久层对象

| 对象名 | 职责 | 归属 |
|--------|------|------|
| CanonicalEntity | 系统级正式实体主数据 | Canonical Zone / 当前态 |
| EntityAlias | 别名、代码、曾用名、英文名映射 | Canonical Zone |
| EntityReference | 原始引用记录与解析结果 | Canonical / Analytical 辅助表 |
| ResolutionCase | 消歧决策记录 | Analytical / review 表 |
| UnresolvedQueueItem | 待回补的未解析引用 | 当前态 / review 队列 |

### 9.2 运行时对象

| 对象名 | 职责 | 生命周期 |
|--------|------|----------|
| MentionCandidateSet | 一次 mention 的候选实体集合 | 单次解析期间 |
| ResolutionContext | 解析所需上下文 | 单次解析期间 |
| ResolutionDecision | 本次解析的决策结果 | 单次解析结束前 |
| BatchResolutionJob | 一次批量回补任务 | 单次批任务期间 |

### 9.3 核心对象详细设计

#### CanonicalEntity

**角色**：系统的正式实体主键对象。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| canonical_entity_id | String | 如 `ENT_STOCK_300750.SZ` |
| entity_type | String | `stock` / `corp` / `person` / `org` / `index` |
| display_name | String | 正式展示名 |
| status | String | `active` / `inactive` / `merged` |
| anchor_code | String \| Null | 对上市公司为 `ts_code` |
| cross_listing_group | String \| Null | 双上市关联组 |

#### EntityAlias

**角色**：所有指向 canonical entity 的别名与代码映射。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| canonical_entity_id | String | 目标实体 |
| alias_text | String | 别名文本 |
| alias_type | String | `full_name` / `short_name` / `code` / `english` / `former_name` / `cnspell` |
| confidence | Number | 别名可信度 |
| source | String | 来源系统 |
| is_primary | Boolean | 是否主别名 |

#### EntityReference

**角色**：记录一次原始文本或结构化输入中的实体引用。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| reference_id | String | 唯一标识 |
| raw_mention_text | String | 原始 mention |
| source_context | JSON | 来源上下文摘要 |
| resolved_entity_id | String \| Null | 解析后的 canonical entity |
| resolution_method | String | `deterministic` / `fuzzy` / `llm` / `manual` / `unresolved` |
| resolution_confidence | Number \| Null | 解析置信度 |

#### ResolutionCase

**角色**：一次消歧决策的正式审计对象。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| case_id | String | 唯一标识 |
| reference_id | String | 对应的 EntityReference |
| candidate_entity_ids | Array[String] | 候选集合 |
| selected_entity_id | String \| Null | 最终选择 |
| decision_type | String | `auto` / `llm_assisted` / `manual_review` |
| decision_rationale | String | 决策理由 |

#### MentionCandidateSet

**角色**：一次解析过程中形成的候选实体集合。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| raw_mention_text | String | 原始 mention |
| deterministic_hits | Array[String] | 确定性命中 |
| fuzzy_hits | Array[String] | 模糊候选 |
| llm_required | Boolean | 是否需要 LLM 辅助 |
| final_status | String | `resolved` / `unresolved` / `manual_review` |

---

## 10. 数据模型设计

### 10.1 模型分层策略

- 正式实体主数据与别名 → Canonical Zone / 当前态
- 原始引用记录与解析历史 → Canonical / Analytical 辅助表
- 人工复核队列 → 当前态表或 review 表
- 单次解析上下文与候选集合 → 内存对象

### 10.2 存储方案

| 存储用途 | 技术选型 | 理由 |
|----------|----------|------|
| `canonical_entity` / `entity_alias` | Iceberg + PostgreSQL 当前态 | 既要版本化也要当前态快速查 |
| `entity_reference` / `resolution_case` | Iceberg | 便于审计与回放 |
| review / unresolved 队列 | PostgreSQL | 当前态、便于人工流转 |
| 运行时解析对象 | Python dataclass / Pydantic model | 便于接口与测试 |

### 10.3 关系模型

- `EntityAlias.canonical_entity_id -> CanonicalEntity.canonical_entity_id`
- `EntityReference.resolved_entity_id -> CanonicalEntity.canonical_entity_id`
- `ResolutionCase.reference_id -> EntityReference.reference_id`
- `cross_listing_group` 用于关联 A+H 等独立 canonical ID 的关联组

---

## 11. 核心计算/算法设计

### 11.1 Canonical 初始化算法

**输入**：`stock_basic` canonical 表。

**输出**：首版 `canonical_entity` 与 `entity_alias`。

**处理流程**：

```text
读取 stock_basic canonical
  -> 按 ts_code 生成 ENT_STOCK_{ts_code}
  -> 写 canonical_entity 主记录
  -> 从 name/fullname/enname/cnspell/symbol 生成 entity_alias
  -> 输出初始 registry snapshot
```

### 11.2 两级实体解析算法

**输入**：raw mention、上下文、alias 表、可选候选集。

**输出**：resolved entity 或 unresolved。

**处理流程**：

```text
先做 Level 1 deterministic matching
  -> 若唯一命中则直接解析
  -> 否则在本模块内做 blocking + 相似度 / Splink 候选生成
  -> 若候选仍不明确，则把候选集 + 上下文交给 reasoner-runtime 公开结构化接口辅助裁决
  -> 生成 EntityReference + ResolutionCase
```

**说明**：

- Level 1 的确定性命中、候选生成和 unresolved 策略归 `entity-registry`
- provider 路由、PII scrub、retry/backoff、lineage 记录归 `reasoner-runtime`

### 11.3 Mention Resolution 算法

**输入**：文本 mention、文档上下文、候选实体集。

**输出**：单次解析决策。

**处理流程**：

```text
NER/结构化抽取获得 mention
  -> 结合上下文生成 ResolutionContext
  -> 查询 alias 与 canonical candidates
  -> 若需要则做 LLM-assisted disambiguation
  -> 返回 selected entity 或 unresolved
```

### 11.4 批量回补算法

**输入**：未解析引用集合。

**输出**：批量 resolution 更新与 review 列表。

**处理流程**：

```text
收集 unresolved references
  -> Splink clustering / blocking
  -> 生成候选组
  -> 自动解析能解决的部分
  -> 其余进入 manual review
```

---

## 12. 触发/驱动引擎设计

### 12.1 触发源类型

| 类型 | 来源 | 示例 |
|------|------|------|
| 初始化触发 | `data-platform` / `orchestrator` | `stock_basic` 首次可读后初始化 |
| 同步解析调用 | `main-core` / `subsystem-*` | mention resolution |
| 批量回补触发 | 定时 / manual | unresolved 批处理 |

### 12.2 关键触发流程

```text
new reference arrives
  -> resolve_mention()
  -> write reference / case
  -> return canonical_entity_id or unresolved
```

### 12.3 启动顺序基线

| 阶段 | 动作 | 说明 |
|------|------|------|
| P1a | `data-platform` 先让 `stock_basic` canonical 可读 | 不要求完整 alias / resolution |
| P1b | `entity-registry` 初始化 `canonical_entity` / `entity_alias` | 建立最小 ENT_* 锚点 |
| P4 | 引入 HanLP + Splink + LLM 辅助消歧 | 补完完整解析能力 |

---

## 13. 输出产物设计

### 13.1 Canonical Entity Registry Snapshot

**面向**：`main-core`、`graph-engine`

**结构**：

```text
{
  canonical_entity: Object
  aliases: Array[Object]
  cross_listing_group: String | null
}
```

### 13.2 Mention Resolution Result

**面向**：`subsystem-*`、`main-core`

**结构**：

```text
{
  raw_mention_text: String
  resolved_entity_id: String | null
  resolution_method: String
  resolution_confidence: Number | null
}
```

### 13.3 Resolution Audit Payload

**面向**：人工复核、`audit-eval`

**结构**：

```text
{
  entity_reference: Object
  resolution_case: Object
  unresolved: Boolean
}
```

---

## 14. 系统模块拆分

**组织模式**：单个 Python 项目，内部按实体主数据、解析、审计链分层。

| 模块名 | 语言 | 运行位置 | 职责 |
|--------|------|----------|------|
| `entity_registry.core` | Python | 库 | ENT_* 规则与主对象定义 |
| `entity_registry.aliases` | Python | 库 | alias 管理与查表 |
| `entity_registry.references` | Python | 库 | entity_reference 记录 |
| `entity_registry.resolution` | Python | 库 | deterministic/fuzzy/LLM 辅助消歧 |
| `entity_registry.batch` | Python | 库 | 批量解析与回补任务 |
| `entity_registry.review` | Python | 库 | manual review 队列与工具 |
| `entity_registry.init` | Python | 库 | 从 `stock_basic` 初始化主数据 |

**关键设计决策**：

- `entity-registry` 在主项目中的角色是**唯一实体锚点与解析 owner**
- 它与其他子项目的关系是**消费 canonical 输入，向全局输出统一实体引用能力**
- 它必须独立成子项目，因为 ENT_* 命名空间与解析审计链不能散落在各模块中维护
- `data-platform` 负责 `stock_basic` 可读，`entity-registry` 负责 `canonical_entity` 初始化
- `reasoner-runtime` 是解析能力的下游依赖，而不是被本模块替代

---

## 15. 存储与技术路线

| 用途 | 技术选型 | 理由 |
|------|----------|------|
| 主数据与别名 | Iceberg + PostgreSQL 当前态 | 版本化 + 快速查找兼顾 |
| NER / 中文预处理 | HanLP | Lite 模式可用，适合中文实体抽取 |
| 模糊匹配 / clustering | Splink | 大规模记录链接与候选生成 |
| LLM 辅助消歧 | `reasoner-runtime` | 不在本模块复制 runtime |
| 批量查询与回补 | DuckDB / Python | 轻量可跑 |

最低要求：

- Python 3.12+
- 可读取 `data-platform` 提供的 `stock_basic` canonical 数据
- 可调用 `reasoner-runtime` 的结构化调用接口（完整解析阶段）
- HanLP / Splink 在 P4 启用前可为空实现

---

## 16. API 与接口合同

### 16.1 Python 接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `initialize_from_stock_basic(snapshot_ref)` | 初始化 `canonical_entity` / `entity_alias` | `snapshot_ref` |
| `lookup_alias(alias_text)` | 查别名映射 | `alias_text` |
| `resolve_mention(raw_mention_text, context)` | 单次 mention resolution | mention + context |
| `batch_resolve(references)` | 批量解析 | 引用列表 |
| `register_unresolved_reference(reference)` | 记录未解析引用 | reference payload |
| `get_entity_profile(canonical_entity_id)` | 查询正式实体主数据 | `canonical_entity_id` |

### 16.2 协议接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `MentionResolutionInterface` | 统一解析接口 | mention、context |
| `EntityIdRuleProvider` | canonical ID 生成规则接口 | raw entity data |
| `ResolutionAuditSchema` | 引用与决策审计 schema | 由 `contracts` 定义 |

### 16.3 版本与兼容策略

- `canonical_entity_id` 规则版本必须通过 `contracts` 发布
- `resolve_mention()` 返回结构必须稳定，不能因内部切换 HanLP/Splink/LLM 路径而改变接口
- 所有 LLM 辅助消歧都必须通过 `reasoner-runtime` 的公开结构化接口，禁止在本模块复制 provider client、PII scrub、retry/backoff
- 所有需要正式实体锚点的下游对象应优先使用 `canonical_entity_id`，未解析时显式返回 unresolved
- A+H 双上市不得因别名收敛而合并成一个 canonical ID

---

## 18. 测试与验证策略

### 18.1 单元测试

- `ENT_STOCK_{ts_code}` / 非上市自增 ID 生成规则测试
- alias 查表与唯一命中测试
- unresolved reference 记录测试
- A+H 双上市独立 ID 测试
- deterministic / fuzzy / llm 路径选择测试

### 18.2 集成测试

| 场景 | 验证目标 |
|------|----------|
| 从 `stock_basic` 初始化 registry | 验证 P1 最小主数据闭环 |
| 中文公司名别名解析 | 验证 alias + HanLP 路径 |
| 多候选歧义 mention | 验证 Splink + LLM 辅助消歧 |
| 子系统批量 mention resolution | 验证批量接口与审计链 |
| unresolved 回补后晋升为正式实体 | 验证 review 闭环 |

### 18.3 协议 / 契约测试

- `canonical_entity` / `entity_alias` / `entity_reference` / `resolution_case` 与 `contracts` 对齐
- Ex-* 等需要实体锚点的对象最终能对齐到 `canonical_entity_id`
- `entity-registry` 依赖 `reasoner-runtime` 而不直连 provider SDK

### 18.4 边界与回归测试

- 禁止直接依赖 `data-platform` 私有 adapter 实现的静态检查
- 禁止自建 provider client、PII scrub、retry/backoff 的静态检查
- 禁止未解析裸文本直接进入 formal 引用的回归测试
- 规则匹配与 LLM 辅助消歧结果的一致性抽样检查

---

## 19. 关键评价指标

### 19.1 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 单次 alias 解析延迟 | `< 50ms` | 纯查表路径 |
| 单次 mention resolution 平均耗时 | `< 2 秒` | 不含极端复杂 LLM 解析 |
| 1 次 `stock_basic` 初始化耗时 | `< 10 分钟` | 全量 A 股上市公司 |

### 19.2 质量指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 上市公司覆盖率 | `100%` | `canonical_entity` 覆盖全部 A 股上市公司 |
| unresolved 误判为 resolved 的错误率 | `< 1%` | 重点控制误绑定 |
| A+H 错误合并率 | `0` | 双上市实体必须分离 |
| 下游裸文本实体引用发生率 | `0` | formal 链路不允许裸文本锚点 |

---

## 20. 项目交付物清单

### 20.1 主数据对象

- `canonical_entity`
- `entity_alias`
- `entity_reference`
- `resolution_case`

### 20.2 解析能力

- deterministic matcher
- fuzzy matcher / Splink 集成
- LLM 辅助消歧
- mention resolution API

### 20.3 初始化与运维支撑

- `stock_basic` 初始化任务
- unresolved review 队列
- 批量回补任务

---

## 21. 实施路线图

### 阶段 0：P1 最小实体锚点（2-4 天）

**阶段目标**：基于 `stock_basic` 建立最小 ENT_* registry。

**交付**：
- `canonical_entity`
- `entity_alias`
- 初始化任务

**退出条件**：全部 A 股上市公司有正式 canonical_entity_id。

### 阶段 1：P1-P2 确定性解析（3-5 天）

**阶段目标**：打通 alias 查表、代码匹配和基础 profile 查询。

**交付**：
- alias lookup
- deterministic matching
- `get_entity_profile()`

**退出条件**：主系统和图谱能稳定读取 ENT_* 锚点。

### 阶段 2：P4 模糊解析与 LLM 辅助（5-8 天）

**阶段目标**：接入 HanLP、Splink 和 `reasoner-runtime`。

**交付**：
- HanLP NER
- Splink 候选生成
- LLM-assisted disambiguation

**退出条件**：复杂新闻/公告 mention 能进入完整解析链。

### 阶段 3：P4-P5 批量回补与人工复核（3-5 天）

**阶段目标**：建立 unresolved 批处理与 review 闭环。

**交付**：
- batch resolve
- review queue
- resolution_case 审计链

**退出条件**：未解析引用不再静默堆积。

---

## 22. 主要风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 初始化阶段与 `data-platform` 循环等待 | P1 启动阻塞 | 明确 `stock_basic` 可读在前，registry 初始化在后 |
| 误把模糊别名绑定到错误实体 | 下游 formal 对象污染 | Deterministic first + unresolved 优先 |
| LLM 辅助消歧过度依赖 | 成本与稳定性失控 | 仅在第二层候选仍冲突时调用 |
| A+H / 跨市场实体混淆 | 图谱和主系统 join 错误 | 独立 ID + cross listing 关联 |

---

## 23. 验收标准

项目完成的最低标准：

1. `entity-registry` 能基于 `stock_basic` 初始化完整 A 股上市公司的 `canonical_entity` 与 `entity_alias`
2. `canonical_entity`、`entity_alias`、`entity_reference`、`resolution_case` 四类对象都有正式对象定义和可运行实现
3. `resolve_mention()` 能返回稳定的 `canonical_entity_id` 或显式 unresolved 结果
4. `entity-registry` 明确依赖 `reasoner-runtime` 做 LLM 辅助消歧，但不直连 provider SDK，也不复制 PII scrub / retry / lineage 逻辑
5. 文档中定义的主项目角色、OWN/BAN/EDGE 与主项目 `12 + N` 模块边界一致

---

## 24. 一句话结论

`entity-registry` 子项目不是一套静态字典表，而是主项目里唯一负责“实体到底是谁”这件事的正式 owner。  
它如果边界不稳，后面所有图谱关系、候选信号和 formal recommendation 都会失去统一锚点。

---

## 25. 自动化开发对接

### 25.1 自动化输入契约

| 项 | 规则 |
|----|------|
| `module_id` | `entity-registry` |
| 脚本先读章节 | `§1` `§4` `§5.2` `§5.4` `§9` `§11` `§14` `§16` `§18` `§21` `§23` |
| 默认 issue 粒度 | 一次只实现一个对象族、一个解析阶段或一条最小 resolution 路径 |
| 默认写入范围 | 当前 repo 的实体主数据、解析逻辑、审计链、测试、fixture 和文档 |
| 内部命名基线 | 以 `§9` 的对象名、`§11` 的算法分层和 `§14` 的内部模块名为准 |
| 禁止越界 | 不直连 provider SDK、不依赖 `data-platform` 私有 adapter、不让 unresolved 裸文本进入 formal 链路 |
| 完成判定 | 同时满足 `§18`、`§21` 当前阶段退出条件和 `§23` 对应条目 |

### 25.2 推荐自动化任务顺序

1. 先落 `canonical_entity`、`entity_alias` 和 `stock_basic` 初始化主干
2. 再落 deterministic lookup、profile 查询和 unresolved 记录
3. 再落 fuzzy candidate + `reasoner-runtime` 辅助裁决
4. 最后补批量回补、人工复核和长期审计链增强

补充规则：

- 单个 issue 默认只覆盖一个解析阶段，不把初始化、确定性、模糊裁决和人工复核混做
- 先保证 deterministic path 可跑，再允许引入 runtime 辅助消歧

### 25.3 Blocker 升级条件

- 需要自建 provider client、PII scrub 或 retry/backoff
- 需要把 `stock_basic` 读取建立在 `data-platform` 私有实现之上
- 需要把未解析 mention 直接晋升为 formal 实体锚点
- 无法给出 deterministic / unresolved / runtime-assisted 三类路径的验证样本
