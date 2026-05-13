# main-core 完整项目文档

> **文档状态**：Draft v1
> **版本**：v0.1.2
> **作者**：Codex
> **创建日期**：2026-04-15
> **最后更新**：2026-04-15
> **文档目的**：把 `main-core` 子项目从“主系统业务都在这里”这种过宽表述收束为可立项、可拆分、可实现、可验收的正式项目，使其成为主项目中唯一负责 L1-L8 业务链、共享状态判断、池管理、深度分析、正式建议与发布装配的核心业务模块。

---

## 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| v0.1 | 2026-04-15 | 初稿 | Codex |
| v0.1.1 | 2026-04-15 | 补充 L8 `dashboard_snapshot` / `report` 正式产物和 `backtest_result` 非归属边界 | Codex |
| v0.1.2 | 2026-04-15 | 补充 `analyzer_type` 在 P2/P8 阶段的默认取值约束 | Codex |

---

## 1. 一句话定义

`main-core` 是主项目中**唯一负责把市场数据、候选信号、图谱上下文和 LLM 增强结果融合为正式 `world_state_snapshot`、`official_alpha_pool`、`alpha_result_snapshot`、`recommendation_snapshot`、`dashboard_snapshot`、`report` 等 formal objects**的核心业务模块，它以“L4 是共享状态层”“L1-L8 必须保持单项目内强 package 边界”和“formal publish 必须走 manifest 语义”为不可协商约束。

它不是数据平台，不是图谱引擎，也不是 LLM runtime。  
它不直接管理存储引擎、不直接管理 Neo4j 实例、不直接绑定具体 provider SDK。

---

## 2. 文档定位与核心问题

本文解决的问题不是“怎么写一些策略逻辑”，而是：

1. **主业务链唯一归属问题**：L1-L8 是主项目的价值中心，必须有一个清晰的长期模块承接，而不是散落在编排、图谱、数据和审计模块里。
2. **内部分层失控问题**：如果 L3 特征、L4 状态、L6 推理、L7 建议在代码层互相直连，后续 P2/P5/P8 演进会迅速耦死。
3. **正式发布一致性问题**：formal object 的生成、约束、`inconclusive` 处理、override、manifest 发起必须由统一业务模块负责，否则“谁对最终 recommendation 负责”会失真。

---

## 3. 术语表

| 术语 | 定义 | 备注 |
|------|------|------|
| L1-L8 | 主系统内部业务链的八个层级步骤 | 本模块内部 package 分层，不是 8 个独立项目 |
| Feature / Signal Bundle | L3 产出的统一特征与信号集合 | 供 L4/L5/L6/L7 消费 |
| Feature Weight Multiplier | 特征漂移在线调整系数表 | 归 `l3_features` 在线业务状态 |
| World State Snapshot | L4 发布的正式市场状态快照 | L5/L6/L7 共享只读输入 |
| Official Alpha Pool | L5 发布的正式核心池对象 | 当前默认容量上限 100 |
| Alpha Result Snapshot | L6 发布的深度分析结果快照 | 由 analyzer interface 产出 |
| Recommendation Snapshot | L7 发布的正式建议快照 | formal recommendation 最终业务对象 |
| Override | 人工覆盖输入 | 优先于 reasoner，不优先于 Gate 异常 |
| Inconclusive | 任务级失败或高矛盾时的显式不确定结论 | 不能用历史 recommendation 顶替 |
| Publish Bundle | Phase 3 准备写入 formal zone 的对象集合 | 包含各类 formal object 与 manifest 元信息 |

**规则**：
- `world_state_snapshot` 是 L5/L6/L7 的共享只读状态，不是线性中间态
- `Feature Weight Multiplier` 的写入属于 `main-core`，不属于 `audit-eval`
- `SinglePromptAnalyzer` 是生产 fallback，`MultiAgentAnalyzer` 是 `l6_alpha` 的后续实现位

---

## 4. 目标与非目标

### 4.1 项目目标

1. **实现 L1-L8 主链**：建立从 L1/L2 数据读取到 L8 正式发布装配的完整业务链。
2. **产出正式状态**：生成正式 `world_state_snapshot` 并作为共享状态层服务 L5/L6/L7。
3. **管理正式池与分析结果**：生成 `official_alpha_pool`、`alpha_result_snapshot` 与 `recommendation_snapshot`。
4. **拥有 L8 正式输出装配**：生成 `dashboard_snapshot` 与 `report` 的正式业务内容。
5. **落实在线特征控制**：在 L3 中实现 `feature_weight_multiplier` 的在线写入与当轮生效。
6. **定义 analyzer 边界**：通过统一 `analyzer` interface 承载 `SinglePromptAnalyzer` 与后续 `MultiAgentAnalyzer`。
7. **保证 Phase 3 发布语义**：按“单表 commit + `cycle_publish_manifest`”的方式发起 formal publish。
8. **保留独立运行能力**：在不接子系统、不接图谱真实链路时，仍能基于纯市场数据跑通最小 L1-L8 闭环。

### 4.2 非目标

- **不拥有原始数据接入与存储**：Raw/Canonical/Formal/Analytical 的落地和 serving 归 `data-platform`，因为 `main-core` 只消费和发起发布。
- **不拥有图谱计算**：graph promotion、传播、snapshot 生成归 `graph-engine`，因为 `main-core` 只读取其正式产物。
- **不拥有 LLM runtime**：provider 路由、PII scrub、fallback/retry、回放字段生成归 `reasoner-runtime`。
- **不拥有审计持久化**：`audit_record`、`replay_record`、`retrospective_evaluation` 的正式写入归 `audit-eval`。
- **不拥有回测分析资产**：`backtest_result` 是 analytical asset，归 `audit-eval` / 离线分析链，不归 `main-core` formal publish。
- **不拆成 8 个子项目**：L1-L8 是一个项目内的强 package 分层，不是 8 个长期独立模块。

---

## 5. 与现有工具的关系定位

### 5.1 架构位置

```text
contracts + data-platform + entity-registry + reasoner-runtime + graph-engine
  -> main-core
      ├── l1_l2_basis
      ├── l3_features
      ├── l4_world_state
      ├── l5_universe
      ├── l6_alpha
      ├── l7_recommendation
      └── l8_publish
  -> outputs
      ├── world_state_snapshot
      ├── official_alpha_pool
      ├── alpha_result_snapshot
      ├── recommendation_snapshot
      └── publish bundle / audit payloads
```

### 5.2 上游输入

| 来源 | 提供内容 | 说明 |
|------|----------|------|
| `contracts` | formal object schema、analyzer 协议、错误码 | 本模块不能自定义第二套 formal 对象 |
| `data-platform` | L2 数据、L3 底层特征表、formal serving、cycle 表 | 数据读取和最终表落地都经由平台 |
| `entity-registry` | canonical entity、entity_profile、resolution 结果 | 用于池管理、分析上下文、相似特征 |
| `reasoner-runtime` | 结构化 LLM 调用、health/fallback/replay bundle | L4/L6/L7 的所有正式 LLM 调用统一依赖 |
| `graph-engine` | `graph_snapshot`、`graph_impact_snapshot`、图谱上下文 | 只读消费，不回写图谱算法 |
| Layer B 验证结果 | candidate facts / signals 的正式整合结果 | 通常经 `data-platform` 落地后读取 |

### 5.3 下游输出

| 目标 | 输出内容 | 消费方式 |
|------|----------|----------|
| `data-platform` | feature bundle、formal objects、manifest 写入请求 | Python API / publish service |
| `graph-engine` | 上一轮 `world_state_snapshot` | read-only regime context |
| `audit-eval` | audit payload、params snapshot、retrospective seed | Python API / write sink |
| `orchestrator` | assets/checks/factories | Python import |
| `assembly` | 主系统服务入口、最小运行配置 | Python import / compose |

### 5.4 核心边界

- **`main-core` 拥有业务语义，不拥有底层存储与执行引擎**
- **L1-L8 在一个项目内强制保留 package 边界，不拆成 8 个子项目**
- **`world_state_snapshot` 是共享只读状态层，L5/L6/L7 直接读取**
- **`feature_weight_multiplier` 的在线写入归 `l3_features`**
- **Phase 3 的 manifest 由 `main-core` 发起，但表定义与存储约束归 `data-platform`**

---

## 6. 设计哲学

### 6.1 设计原则

#### 原则 1：Business Core Stays Business

主系统的价值在于业务判断链本身。  
因此 `main-core` 必须拥有 L1-L8 的业务语义，而不是把关键判断拆散到数据、编排、图谱或 runtime 里。

#### 原则 2：Package Walls Matter

L3、L4、L5、L6、L7 的演进节奏不同。  
只有在同一项目内保留强 package 边界，后续 P2a/P2b/P8 才能扩展而不互相污染。

#### 原则 3：Formal Outputs Must Be Explicit

正式对象必须是显式对象，不是“若干表拼出来的当前态”。  
`world_state_snapshot`、`official_alpha_pool`、`alpha_result_snapshot`、`recommendation_snapshot` 都必须可版本化、可解释、可发布。

#### 原则 4：No Silent Fallback on Formal Decisions

formal 输出不能靠“沿用上一轮 recommendation”这种隐式兜底维持。  
任务级失败只能走 `inconclusive` 或 analyzer fallback，基础设施级失败必须硬停。

### 6.2 反模式清单

| 反模式 | 为什么危险 |
|--------|-----------|
| 把 `main-core` 再拆成 8 个独立项目 | 业务链被人为切断，接口爆炸，迭代成本失控 |
| 在 `data-platform` / `orchestrator` 中偷偷写 L4-L7 业务逻辑 | formal owner 漂移，责任边界失真 |
| L3 直接 import L6 或 L7 的内部实现 | 分层反向耦合，后续 P8/P7 演进困难 |
| 用上一轮 recommendation 顶当前 formal output | 会把失败处理伪装成正常发布，审计不可接受 |
| 绕过 manifest 直接读取 formal 表 head | 可能读到半提交状态，破坏发布一致性 |

---

## 7. 用户与消费方

### 7.1 直接消费方

| 消费方 | 消费内容 | 用途 |
|--------|----------|------|
| `graph-engine` | `world_state_snapshot` | 传播计算 regime context |
| `audit-eval` | audit payload、L4/L7 偏差对照种子 | 审计、回放、retrospective |
| `orchestrator` | phase_2 / phase_3 assets 与 checks | 日频执行图装配 |
| 分析师 / 上层展示层 | recommendation / report payload | 人工复盘与消费 |

### 7.2 间接用户

| 角色 | 关注点 |
|------|--------|
| 主编 / 架构 owner | L1-L8 是否真的是唯一 formal 业务链 |
| reviewer | package 边界是否被破坏 |
| 自动化代理 | 哪些逻辑归 `main-core`，哪些必须去别的模块改 |

---

## 8. 总体系统结构

### 8.1 Phase 2 主业务链

```text
L1/L2 basis data
  -> L3 feature / signal bundle
  -> L4 world state
  -> L5 universe selection
  -> L6 alpha analysis
  -> L7 recommendation
  -> L8 publish bundle assembly
```

### 8.2 L4 共享状态主线

```text
L3 signal bundle + macro/market context + graph impact
  -> baseline regime
  -> optional LLM delta (bounded to +/-1)
  -> final world_state_snapshot
  -> read-only fanout to L5 / L6 / L7
```

### 8.3 Phase 3 发布主线

```text
formal objects prepared
  -> per-object single table commit
  -> request manifest write
  -> emit audit payload / retrospective seed
  -> publish complete
```

---

## 9. 领域对象设计

### 9.1 持久层对象

| 对象名 | 职责 | 归属 |
|--------|------|------|
| FeatureBundleSnapshot | L3 产出的特征与信号快照 | Iceberg feature 表（由 `data-platform` 持久化） |
| WorldStateSnapshot | L4 正式市场状态 | Formal Zone |
| OfficialAlphaPool | L5 正式核心池与变更记录 | Formal Zone |
| AlphaResultSnapshot | L6 深度分析结果 | Formal Zone |
| RecommendationSnapshot | L7 正式建议 | Formal Zone |
| OverrideRecord | override 业务记录 | 业务对象，持久化由外部审计/状态表承接 |

### 9.2 运行时对象

| 对象名 | 职责 | 生命周期 |
|--------|------|----------|
| FeatureSignalBundle | 一轮运行中的统一特征和信号集合 | 单个 cycle 的 Phase 2 期间 |
| WorldStateDecision | L4 的中间判断对象 | 单轮 L4 计算期间 |
| UniverseSelectionPlan | L5 的池变更计划 | 单轮 L5 计算期间 |
| AlphaAnalysisContext | L6 分析上下文 | 单股票分析期间 |
| PublishBundle | 一轮 Phase 3 的正式对象装配结果 | 单轮发布期间 |

### 9.3 核心对象详细设计

#### FeatureSignalBundle

**角色**：L3 对外暴露给 L4/L5/L6/L7 的统一输入包。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| cycle_id | String | 当前 cycle |
| entity_id | String | `ENT_*` 主键 |
| feature_values | JSON | 数值特征集合 |
| signal_values | JSON | 结构化信号集合 |
| graph_features | JSON | 图谱相关特征 |
| feature_weight_multiplier | JSON | 当轮在线调整系数 |
| generated_at | Timestamp | 生成时间 |

#### WorldStateSnapshot

**角色**：L4 发布的正式共享状态。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| cycle_id | String | 当前 cycle |
| baseline_regime | String | 规则骨架给出的基线状态 |
| llm_delta | Integer | LLM 修正档位，范围 `-1` / `0` / `+1` |
| final_regime | String | 最终正式状态 |
| llm_rationale | String | LLM 修正理由 |
| actual_model_used | String | 实际模型 |
| actual_provider | String | 实际 provider |
| fallback_path | Array[String] | fallback 路径 |

#### OfficialAlphaPool

**角色**：L5 发布的正式池对象。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| cycle_id | String | 当前 cycle |
| observation_pool_size | Integer | 观测池规模 |
| official_alpha_pool_capacity | Integer | 核心池容量上限 |
| selected_entities | Array[String] | 入池实体列表 |
| added_entities | Array[String] | 本轮新增 |
| removed_entities | Array[String] | 本轮移除 |
| freeze_reason_map | JSON | 冻结说明 |

#### AlphaResultSnapshot

**角色**：L6 对核心池股票的正式深度分析结果。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| cycle_id | String | 当前 cycle |
| entity_id | String | 分析对象 |
| analyzer_type | String | P2 固定为 `single_prompt_v1`，P8 A/B 通过后才允许 `multi_agent_v1` |
| score | Number | 综合评分 |
| confidence | Number | 置信度 |
| rationale | String | 主要论据摘要 |
| similar_cases | JSON | 相似检索结果摘要 |
| status | Enum | `ok` / `inconclusive` |

#### RecommendationSnapshot

**角色**：L7 发布的正式建议对象。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| cycle_id | String | 当前 cycle |
| entity_id | String | 建议对象 |
| action_type | String | 如 `buy` / `hold` / `reduce` / `inconclusive` |
| rating | String \| Null | 评级 |
| confidence | Number \| Null | 置信度 |
| triggered_by | String | `system` / `human_decision` |
| override_applied | Boolean | 是否应用 override |
| constraints_applied | JSON | regime / risk 约束 |

#### DashboardSnapshot

**角色**：L8 面向展示层的正式 dashboard 快照。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| cycle_id | String | 当前 cycle |
| world_state_ref | String | 引用的 `world_state_snapshot` |
| pool_ref | String | 引用的 `official_alpha_pool` |
| recommendation_ref | String | 引用的 `recommendation_snapshot` |
| summary_cards | JSON | 首页与列表页汇总卡片 |

#### FormalReport

**角色**：L8 面向人工消费的正式报告对象。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| cycle_id | String | 当前 cycle |
| report_type | String | 日报 / 周报 / 专题 |
| recommendation_ref | String | 关联的正式建议 |
| narrative_sections | JSON | 解释性正文结构 |
| appendix_refs | JSON | 图谱、池、审计引用 |

#### PublishBundle

**角色**：Phase 3 待发布的正式对象与发布元数据集合。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| cycle_id | String | 当前 cycle |
| formal_objects | JSON | 各 formal object payload |
| manifest_candidate | JSON | 各表 snapshot/version 信息 |
| audit_payload | JSON | 供 `audit-eval` 持久化的业务审计载荷 |
| retrospective_seed | JSON | 供回溯评估使用的种子信息 |

---

## 10. 数据模型设计

### 10.1 模型分层策略

- 正式业务对象 → Formal Zone，由 `data-platform` 承接落地
- L3 特征快照 → Iceberg feature 表，由 `data-platform` 承接落地
- 运行中间对象 → Python / Pydantic 内存对象
- override / audit / retrospective 持久化 → 由 `audit-eval` 或外部状态表承接

### 10.2 存储方案

| 存储用途 | 技术选型 | 理由 |
|----------|----------|------|
| L2/L3 输入读取 | DuckDB + Iceberg / serving API | 复用 `data-platform` 的读取语义 |
| formal objects 写入 | Iceberg single-table commit | 与主文档 FIX-01 对齐 |
| 发布一致性锚点 | `cycle_publish_manifest` | 通过 PG 保证发布清单可见性 |
| 运行时业务对象 | Python dataclass / Pydantic model | 便于分层建模与测试 |

### 10.3 关系模型

- `FeatureSignalBundle.cycle_id -> WorldStateSnapshot.cycle_id -> OfficialAlphaPool.cycle_id`
- `OfficialAlphaPool.selected_entities` 决定 `AlphaResultSnapshot.entity_id` 的分析集合
- `RecommendationSnapshot.entity_id` 必须属于对应 cycle 的 `OfficialAlphaPool`
- `PublishBundle.manifest_candidate` 对应 `cycle_publish_manifest.formal_table_snapshots`

---

## 11. 核心计算/算法设计

### 11.1 L3 特征与在线调整算法

**输入**：L2 市场数据、graph impact、候选信号、既有 multiplier 状态。

**输出**：`FeatureSignalBundle`。

**处理流程**：

```text
读取 dbt marts / Python 特征
  -> 合并 graph_impact 和候选信号
  -> 应用当轮 feature_weight_multiplier
  -> 生成 feature / signal bundle
  -> 写出 feature bundle snapshot
```

### 11.2 L4 混合驱动状态算法

**输入**：L3 signal bundle、宏观/市场上下文、可选 LLM 修正。

**输出**：`WorldStateSnapshot`。

**处理流程**：

```text
规则骨架生成 baseline_regime
  -> 调用 reasoner-runtime 获取结构化修正建议
  -> 将 llm_delta 限定在 +/-1
  -> 合成 final_regime
  -> 输出 world_state_snapshot
```

### 11.3 L5/L6/L7 主业务链算法

**输入**：world state、feature bundle、graph snapshot、entity profile、相似检索结果。

**输出**：`OfficialAlphaPool` + `AlphaResultSnapshot` + `RecommendationSnapshot`。

**处理流程**：

```text
L5 基于 world_state 与规则筛出 observation/core pool
  -> L6 对核心池执行 analyzer.analyze(stock, context)
  -> 若任务级失败，则标记 inconclusive 或降级到 SinglePromptAnalyzer
  -> L7 叠加 regime / risk / override 生成正式 recommendation
```

### 11.4 Phase 3 发布算法

**输入**：四类 formal object、audit payload、manifest 元数据。

**输出**：`PublishBundle` 与发布请求。

**处理流程**：

```text
装配 world_state / pool / alpha / recommendation
  -> 逐类单表 commit 到 formal zone
  -> 所有对象成功后发起 manifest 写入
  -> 产出 audit payload 与 retrospective seed
  -> 标记当前 cycle 发布完成
```

---

## 12. 触发/驱动引擎设计

### 12.1 触发源类型

| 类型 | 来源 | 示例 |
|------|------|------|
| 日频主链触发 | `orchestrator` | Phase 2 / Phase 3 执行 |
| 人工覆盖触发 | human / authorized analyst | override 提交 |
| 回溯评估触发 | `audit-eval` | T+1/T+5/T+20 retrospective 回填 |

### 12.2 关键触发流程

```text
Phase 2 start
  -> L3 features
  -> L4 world state
  -> L5 pool
  -> L6 alpha
  -> L7 recommendation
  -> L8 publish bundle
```

### 12.3 失败语义基线

| 场景 | 处理路径 | 说明 |
|------|---------|------|
| LLM 基础设施级失败 | 硬停相关下游链路 | 不允许静默降级 |
| 单股票任务级失败 | 标记 `inconclusive` 或退回 `SinglePromptAnalyzer` | 不能用上一轮 recommendation 顶替 |
| Phase 3 单表 commit 失败 | 本轮发布失败，不写 manifest | 已写部分对消费方不可见 |
| override 与 Gate 冲突 | Gate 优先 | override 不覆盖异常检查 |

---

## 13. 输出产物设计

### 13.1 World State Snapshot

**面向**：L5/L6/L7、`graph-engine`

**结构**：

```text
{
  cycle_id: String
  baseline_regime: String
  llm_delta: Integer
  final_regime: String
  llm_rationale: String
}
```

### 13.2 Official Alpha Pool / Alpha Result / Recommendation

**面向**：分析师、`audit-eval`、上层展示

**结构**：

```text
{
  official_alpha_pool: Object
  alpha_result_snapshot: Object
  recommendation_snapshot: Object
}
```

### 13.3 Dashboard Snapshot / Report

**面向**：分析师、上层展示层

**结构**：

```text
{
  dashboard_snapshot: Object
  report: Object
}
```

### 13.4 Publish Bundle

**面向**：`data-platform`、`audit-eval`

**结构**：

```text
{
  formal_objects: Object
  manifest_candidate: Object
  audit_payload: Object
  retrospective_seed: Object
}
```

---

## 14. 系统模块拆分

**组织模式**：单个 Python 项目，内部按 L1-L8 强 package 边界组织。

| 模块名 | 语言 | 运行位置 | 职责 |
|--------|------|----------|------|
| `main_core.l1_l2_basis` | Python | 库 | 对象 / 市场 / 日历基础读取 |
| `main_core.l3_features` | Python | 库 | 特征整合、signal bundle、multiplier 在线调整 |
| `main_core.l4_world_state` | Python | 库 | 规则骨架 + LLM 修正后的共享状态 |
| `main_core.l5_universe` | Python | 库 | observation/core pool 管理与冻结 |
| `main_core.l6_alpha` | Python | 库 | analyzer interface、SinglePromptAnalyzer、MultiAgent slot |
| `main_core.l7_recommendation` | Python | 库 | recommendation 生成、override 应用、inconclusive 处理 |
| `main_core.l8_publish` | Python | 库 | formal object 装配、manifest 发起、publish bundle |

**关键设计决策**：

- `main-core` 在主项目中的角色是**唯一 formal 业务链 owner**
- 它与其他子项目的关系是**读取上游正式产物、生成 formal objects、把落地交给下游**
- 它必须独立成子项目，因为主系统的核心业务语义只能有一个 owner
- L1-L8 不拆成 8 个长期项目，只在同一项目中做 package 分层
- 跨 package 只走显式 interface，不允许任意横跳

---

## 15. 存储与技术路线

| 用途 | 技术选型 | 理由 |
|------|----------|------|
| L2/L3 数据读取 | DuckDB / Formal Serving / Canonical 查询 | 复用平台能力 |
| L4/L6/L7 LLM 调用 | `reasoner-runtime` | 不在本模块重复实现 runtime |
| 相似检索 Lite | numpy / scipy | Lite 模式零运维 |
| 相似检索 Full | Milvus | 记录规模超过阈值后切换 |
| 发布一致性 | `cycle_publish_manifest` | 与 FIX-01 一致 |

最低要求：

- Python 3.12+
- 可读取 `data-platform` 提供的 L2/L3 数据
- 可调用 `reasoner-runtime`
- 可读取 `graph-engine` 的正式快照（接入后）

---

## 16. API 与接口合同

### 16.1 Python 接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `build_feature_signal_bundle(cycle_id)` | 生成 L3 特征与信号集合 | `cycle_id` |
| `derive_world_state(bundle)` | 生成正式 world state | `FeatureSignalBundle` |
| `select_official_alpha_pool(world_state, bundle)` | 生成正式池对象 | 状态 + 特征 |
| `analyze_stock(entity_id, context)` | 执行单股票深度分析 | `entity_id`、`AlphaAnalysisContext` |
| `generate_recommendations(pool, analyses, world_state)` | 生成正式建议 | 池对象、分析结果、状态 |
| `prepare_publish_bundle(cycle_id)` | 组装 formal objects 与 manifest 数据 | `cycle_id` |
| `submit_override(override_input)` | 提交人工覆盖 | override payload |

### 16.2 协议接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `AnalyzerInterface` | L6 可插拔分析接口 | `analyze(stock, context) -> alpha_result` |
| `WorldStatePolicy` | L4 规则骨架与修正约束接口 | state inputs |
| `RecommendationConstraintProvider` | L7 regime / risk 约束接口 | world state、risk context |

### 16.3 版本与兼容策略

- formal object 的 schema 必须以 `contracts` 为准
- `SinglePromptAnalyzer` 与 `MultiAgentAnalyzer` 必须共享同一 `AnalyzerInterface`
- `AlphaResultSnapshot.analyzer_type` 在 P2 阶段固定为 `single_prompt_v1`，只有 P8 A/B 通过后才允许出现 `multi_agent_v1`
- Phase 3 任何消费侧都必须经 manifest 读取 formal outputs，不能直读表 head
- `feature_weight_multiplier` 的变更必须体现在当轮 `FeatureSignalBundle` 中并可审计

---

## 18. 测试与验证策略

### 18.1 单元测试

- L3 feature bundle 组装与 multiplier 生效测试
- L4 `llm_delta` 被限制在 `+/-1` 的规则测试
- L5 pool 容量、冻结与移除逻辑测试
- L6 analyzer interface 一致性测试
- L7 `inconclusive` 与 override 应用测试

### 18.2 集成测试

| 场景 | 验证目标 |
|------|----------|
| 无子系统、无图谱的纯市场数据闭环 | 验证 P2 最小 L1-L8 自运行 |
| 接入 graph snapshot 后的 L4-L7 闭环 | 验证跨模块整合 |
| 单股票 LLM 任务级失败 | 验证 `inconclusive` / fallback 路径 |
| Phase 3 多 formal object 发布 | 验证 manifest 语义 |
| override 提交并生效 | 验证人工覆盖边界与审计载荷 |

### 18.3 协议 / 契约测试

- `WorldStateSnapshot`、`OfficialAlphaPool`、`AlphaResultSnapshot`、`RecommendationSnapshot` 与 `contracts` 对齐
- `AnalyzerInterface` 两种实现输出口径一致
- recommendation 读取流程不绕过 manifest

### 18.4 边界与回归测试

- `main_core.l*` package 之间禁止反向直连的静态检查
- 不允许使用上一轮 recommendation 作为当前 formal output 的回归测试
- `feature_weight_multiplier` 由 `main-core` 写入而非 `audit-eval` 的边界测试

---

## 19. 关键评价指标

### 19.1 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 纯市场数据最小 L1-L8 闭环耗时 | `< 30 分钟` | 本地 Lite 环境 |
| 单股票 L6 分析平均耗时 | `< 60 秒` | 不含 provider 排队异常 |
| Phase 3 formal bundle 装配耗时 | `< 5 分钟` | 不含上游 Phase 2 |

### 19.2 质量指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| L6 结构化结果格式错误率 | `< 1%` | 连续 5 个交易日基线 |
| `llm_delta` 越界率 | `0` | 不允许超过 `+/-1` |
| `inconclusive` 丢失显式标记率 | `0` | 任务级失败必须被记录 |
| manifest 绕过读取发生率 | `0` | formal publish 语义不可破坏 |
| `official_alpha_pool_capacity` 越界率 | `0` | 必须服从参数化上限 |

---

## 20. 项目交付物清单

### 20.1 主业务链

- L1-L8 package 骨架
- L4 `world_state_snapshot`
- L5 `official_alpha_pool`
- L6 `alpha_result_snapshot`
- L7 `recommendation_snapshot`
- L8 `dashboard_snapshot`
- L8 `report`

### 20.2 发布与约束

- Phase 3 publish bundle
- manifest 发起逻辑
- override 接口
- `inconclusive` 处理规则

### 20.3 测试与运行支撑

- analyzer interface
- 纯市场数据最小闭环测试
- package 边界 lint / contract test

---

## 21. 实施路线图

### 阶段 0：P2a 纯数据骨架（3-5 天）

**阶段目标**：在不依赖图谱和子系统的前提下打通 L1-L3。

**交付**：
- `l1_l2_basis`
- `l3_features`
- 最小 feature bundle

**退出条件**：纯市场数据可产出可消费的 L3 bundle。

### 阶段 1：P2b L4-L7 正式链（5-8 天）

**阶段目标**：打通 L4/L5/L6/L7 的正式业务链。

**交付**：
- `world_state_snapshot`
- `official_alpha_pool`
- `SinglePromptAnalyzer`
- `recommendation_snapshot`
- `dashboard_snapshot` / `report` 骨架

**退出条件**：可基于纯市场数据生成第一份正式 recommendation。

### 阶段 2：P2c 发布与审计对接（3-5 天）

**阶段目标**：完成 L8 publish bundle、manifest 发起和 audit payload 输出。

**交付**：
- `l8_publish`
- manifest 发起逻辑
- retrospective seed

**退出条件**：Phase 3 发布链和 audit 对接跑通。

### 阶段 3：P3-P5 图谱与子系统接入（按依赖推进）

**阶段目标**：接入 `graph-engine` 和 Layer B 候选信号，形成完整业务闭环。

**交付**：
- graph snapshot / impact 接入
- candidate signal 接入
- shared state 闭环

**退出条件**：`world_state -> graph -> L3 -> world_state` 时序闭环成立。

### 阶段 4：P8 MultiAgent 选项（按需）

**阶段目标**：在不破坏 `AnalyzerInterface` 的前提下加入 `MultiAgentAnalyzer`。

**交付**：
- `MultiAgentAnalyzer`
- A/B 评估脚本
- parity / scoring 结果

**退出条件**：满足可判定性三要素后再决定是否切生产。

---

## 22. 主要风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| L3/L4/L6 代码层耦合失控 | 后续演进和测试成本暴涨 | package 边界 + CI lint 硬约束 |
| world state 修正过强 | L4 失去可解释性 | `llm_delta` 强制 `+/-1` 上限 |
| recommendation 被隐式兜底 | formal 语义失真 | 禁止历史 recommendation 复用，任务级失败显式 `inconclusive` |
| manifest 语义被调用方绕开 | 读到半提交状态 | 统一 Formal Serving/读取约束 |

---

## 23. 验收标准

项目完成的最低标准：

1. `main-core` 能在不依赖子系统和图谱真实输入时，用纯市场数据跑通最小 L1-L8 闭环
2. `world_state_snapshot`、`official_alpha_pool`、`alpha_result_snapshot`、`recommendation_snapshot`、`dashboard_snapshot`、`report` 六类主业务 formal object 都有正式对象定义与生成路径
3. `feature_weight_multiplier` 在线调整逻辑在 `l3_features` 中生效，并能影响当轮输出
4. Phase 3 发布必须经过 manifest 语义，且不允许用上一轮 recommendation 顶替当前 formal output
5. 文档中定义的主项目角色、OWN/BAN/EDGE 与主项目 `12 + N` 模块边界一致

---

## 24. 一句话结论

`main-core` 子项目不是“剩下的业务都放这里”的收纳箱，而是主项目里唯一负责 formal 业务判断链和正式对象生成的核心 owner。  
它如果没有清晰的内部分层和对外边界，后面每一个模块都会开始长出自己的“半个主系统”。

---

## 25. 自动化开发对接

### 25.1 自动化输入契约

| 项 | 规则 |
|----|------|
| `module_id` | `main-core` |
| 脚本先读章节 | `§1` `§4` `§5.2` `§5.4` `§8` `§9` `§14` `§16` `§18` `§21` `§23` |
| 默认 issue 粒度 | 一次只实现一个 `l_*` 包、一类 formal object，或一条最小业务闭环 |
| 默认写入范围 | 当前 repo 的 `l1`-`l8` 自有实现、formal object 组装、测试、文档和本模块配置 |
| 内部命名基线 | 严格以 `§14` 的内部包边界和 `§9` formal object 命名为准，不另起并列主链 |
| 禁止越界 | 不直连 provider SDK、不重写 `data-platform` / `graph-engine` / `reasoner-runtime` / `audit-eval` 的职责、不绕开 manifest 发布 |
| 完成判定 | 同时满足 `§18`、`§21` 当前阶段退出条件和 `§23` 对应条目 |

### 25.2 推荐自动化任务顺序

1. 先落包骨架、formal object、最小状态对象和 `AnalyzerInterface`
2. 再落 `l1`-`l3` 数据 / 特征主干
3. 再落 `l4`-`l7` 判断链，默认先按 `single_prompt_v1` 路线实现
4. 最后补 `l8` 发布装配和 P8 以后的 `MultiAgent` 可选路径

补充规则：

- 单个 issue 默认只改一个 `l_*` 包；只有打通一条最小验收路径时才允许跨包联动
- `analyzer_type`、`feature_weight_multiplier`、manifest 语义的改动必须单独成 issue

### 25.3 Blocker 升级条件

- 需要新增或修改共享 contract、manifest 语义或 formal object 字段
- 需要在本项目中直连 provider、图谱写入、审计落库或平台存储细节
- `analyzer_type` 默认值与 `single_prompt_v1` 基线冲突
- 无法给出从输入到 formal object 的最小闭环验证路径
