# graph-engine 完整项目文档

> **文档状态**：Draft v1
> **版本**：v0.1.1
> **作者**：Codex
> **创建日期**：2026-04-15
> **最后更新**：2026-04-15
> **文档目的**：把 `graph-engine` 子项目从“Neo4j 那一层”这种模糊理解收束为可立项、可拆分、可实现、可验收的正式项目，使其成为主项目中唯一负责图谱 promotion、传播计算、运行态热镜像、graph snapshot 生成、Cold Reload 与图查询能力的共享图谱计算模块。

---

## 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| v0.1 | 2026-04-15 | 初稿 | Codex |
| v0.1.1 | 2026-04-15 | 补充文本图谱禁区、LightRAG 排除和传播权重解释项 | Codex |

---

## 1. 一句话定义

`graph-engine` 是主项目中**唯一负责把 Layer A 中的图谱 canonical truth 通过 graph promotion 转成可计算的 Neo4j live graph，并基于只读 regime context 执行三类传播、生成 `graph_snapshot` / `graph_impact_snapshot`、维护 `neo4j_graph_status` 与 Cold Reload 闭环**的统一图谱计算模块，它以“图谱 canonical truth 永远在 Iceberg”“Neo4j 只是热镜像”“图谱计算与主系统业务判断严格分层”为不可协商约束。

它不是数据平台，不是 formal recommendation 模块，也不是事件流编排器。  
它不拥有 `canonical_entity` 规则，不拥有 L4-L7 业务判断，不拥有 Kafka/Flink 触发编排。

---

## 2. 文档定位与核心问题

本文解决的问题不是“怎么接一个图库”，而是：

1. **truth 与 mirror 的边界问题**：图谱正式真相在 Layer A，Neo4j 只是运行态热镜像，必须把写入顺序、回写语义和故障恢复写死，否则图谱层会悄悄变成第二真相源。
2. **传播与业务分层问题**：图谱传播会消费 `world_state_snapshot` 作为 regime context，但不能因此反向长进 `main-core`，必须保持数据依赖存在、代码反向依赖不存在。
3. **运行态一致性问题**：Phase 0 校验、Phase 1 增量更新、Cold Reload、只读查询和后续事件驱动局部模拟都共享同一套 live graph 约束，必须由一个长期模块整体持有。

---

## 3. 术语表

| 术语 | 定义 | 备注 |
|------|------|------|
| Graph Canonical Truth | Layer A 中正式持久化的图节点、图边、图断言与历史快照 | 真相只在 Iceberg |
| Live Graph | Neo4j 中的运行态图谱 | Graph Canonical Truth 的热镜像 |
| Candidate Graph Delta | 通过 Layer B 校验后的候选图谱变更 | Phase 1 才进入 canonical write |
| Graph Promotion | 把候选图谱变更提升为正式节点/边/断言并同步 live graph 的过程 | `graph-engine` 核心职责 |
| Graph Snapshot | 一轮 cycle 完成后形成的正式图结构快照 | 写回 Layer A |
| Graph Impact Snapshot | 一轮传播计算后的影响快照 | 供 L3/L6/L7 消费 |
| Regime Context | 来自 `world_state_snapshot` 的只读市场状态上下文 | 调整传播通道权重 |
| Cold Reload | 从 Iceberg 全量重建 Neo4j live graph 的恢复流程 | Phase 0 内执行 |
| GDS Projection | Neo4j Graph Data Science 的投影图 | 用于传播计算 |
| Graph Status | `neo4j_graph_status` 中记录的 live graph 状态 | `ready / rebuilding / failed` |
| Read-only Local Simulation | 在只读命名投影上做局部传播模拟 | Full 模式由 `stream-layer` 触发 |

**规则**：
- 图谱 canonical truth 永远在 Iceberg，Neo4j 不得成为正式 truth
- 所有读取 Neo4j 的动作都必须先检查 `graph_status == ready`
- `graph-engine` 只能读取 `world_state_snapshot`，不能回写业务状态
- 局部事件模拟可以读取 live graph，但不能把结果写回正式 live graph

---

## 4. 目标与非目标

### 4.1 项目目标

1. **维护运行态图谱**：建立 Neo4j schema、索引、约束与 live graph 更新闭环。
2. **执行图谱 promotion**：把经 Layer B 校验冻结的 `Candidate Graph Delta` 提升为正式节点、边和断言。
3. **完成传播计算**：实现 fundamental / event / reflexive 三类传播，并允许按 regime context 调整权重和衰减。
4. **生成正式快照**：产出 `graph_snapshot` 与 `graph_impact_snapshot` 并回写 Layer A。
5. **保证一致性恢复**：实现 `neo4j_graph_status`、Phase 0 一致性校验与 Cold Reload。
6. **提供只读图服务**：向 `main-core`、`audit-eval`、后续 `stream-layer` 暴露图查询与只读局部模拟能力。
7. **保持边界清晰**：让 `graph-engine` 只做图谱计算与图服务，不侵入数据平台、实体规则和 formal recommendation 逻辑。

### 4.2 非目标

- **不拥有图谱 canonical 存储命名空间**：Layer A 的表路径、namespace 和底层存储策略归 `data-platform`，因为图谱层只拥有图语义和计算动作。
- **不定义实体规则**：`canonical_entity_id` 生成规则、别名、mention resolution 归 `entity-registry`。
- **不发布 formal recommendation**：正式世界状态、股票池、研究结果与建议归 `main-core`。
- **不实现 Dagster 编排策略**：Phase 0/1 的 asset wiring、schedule、sensor 与 Gate 策略归 `orchestrator`。
- **不拥有 Kafka/Flink 事件触发链**：Full 模式事件驱动编排归 `stream-layer`，本模块只提供只读图模拟和查询能力。
- **不直接管理 Neo4j 部署生命周期**：容器、实例、连接配置与环境编排归 `assembly`，本模块只定义 schema、查询、写入和恢复逻辑。
- **不做原始文本图谱抽取**：公告、新闻、研报等文本的解析与结构化归子系统和上游候选对象链路，`graph-engine` 只消费合同化后的图谱变更候选。
- **不承载 LightRAG 或类似文本检索式图工具**：chunk 检索、向量召回、文本到图节点映射不属于本模块职责。

---

## 5. 与现有工具的关系定位

### 5.1 架构位置

```text
contracts + data-platform + entity-registry + read-only world_state
  -> graph-engine
      ├── graph promotion
      ├── Neo4j live graph sync
      ├── GDS projection
      ├── propagation engine
      ├── graph_snapshot / graph_impact_snapshot
      ├── cold reload
      ├── neo4j_graph_status
      └── query / readonly simulation
  -> consumers
      ├── main-core
      ├── audit-eval
      ├── stream-layer
      ├── orchestrator
      └── assembly
```

### 5.2 上游输入

| 来源 | 提供内容 | 说明 |
|------|----------|------|
| `contracts` | graph delta / snapshot / impact snapshot schema、错误码 | 不允许绕开合同定义 |
| `data-platform` | Graph Canonical Truth 表、candidate graph delta canonical 记录、snapshot 回写位置 | Layer A 是正式持久化层 |
| `entity-registry` | `canonical_entity`、cross listing / entity 锚点 | 图节点必须锚定正式实体 |
| `main-core` | `world_state_snapshot` | 只读 regime context，不建立代码反向依赖 |
| `subsystem-*` | 候选图谱变更原料 | 先经 Layer B 校验与冻结，再由本模块消费 |
| `assembly` | Neo4j 连接、运行配置、环境变量 | 部署注入不归本模块定义 |

### 5.3 下游输出

| 目标 | 输出内容 | 消费方式 |
|------|----------|----------|
| `data-platform` | `graph_snapshot`、`graph_impact_snapshot`、`neo4j_graph_status` 语义写入 | Iceberg / PostgreSQL |
| `main-core` | 图谱上下文、graph impact、子图查询结果 | 只读 Python API / DuckDB 读取 |
| `audit-eval` | 传播历史、snapshot 历史、一致性状态 | Iceberg / PostgreSQL |
| `stream-layer` | 只读局部传播模拟、受影响子图查询 | Python API |
| `orchestrator` | Phase 0/1 纯函数、asset 工厂、consistency check 入口 | Python import |

### 5.4 核心边界

- **图谱 canonical truth 在 Iceberg，Neo4j 只是热镜像**
- **Graph delta 的顺序必须是 Layer A 先写成功，再同步 Neo4j**
- **`world_state_snapshot` 以数据输入方式进入，不允许 `graph-engine` 反向 import `main-core` 代码**
- **日频 graph promotion 可以写 live graph，事件驱动局部模拟只能读 live graph**
- **`graph-engine` 必须整体持有 promotion / propagation / reload / snapshot，不能拆成多个独立子项目**
- **本模块只接受合同化后的 `CandidateGraphDelta` / snapshot 输入，原始文本、chunk、LightRAG artifact 不得直接进入 graph promotion**

---

## 6. 设计哲学

### 6.1 设计原则

#### 原则 1：Truth Before Mirror

Neo4j 的价值在于计算速度和查询便利，不在于成为正式真相。  
所有出现争议、缺失或崩溃的场景，都必须允许直接丢弃 Neo4j 并从 Iceberg 重建。

#### 原则 2：Promotion Before Propagation

传播计算只能建立在已经 promotion 成功的正式图之上。  
如果 candidate graph delta 还没有先进入 Layer A，就不能直接拿去更新 live graph。

#### 原则 3：Regime Is Read-only

图谱传播允许读取 `world_state_snapshot` 调整传播通道，但不能反向修改 world state。  
这样可以保留“图计算影响业务判断、业务状态影响图计算”的时序错开关系，而不是制造运行时循环依赖。

#### 原则 4：Reload Is a First-class Path

Cold Reload 不是异常补丁，而是正式主路径的一部分。  
如果系统不能稳定地清空、重建、校验 live graph，它就不具备长期运维价值。

#### 原则 5：One Graph Project, Many Packages

`graph-engine` 内部可以分 package，但外部必须是一个项目。  
promotion、传播、snapshot、reload 和 status 共享同一套状态约束，拆成多个项目只会制造集成成本。

### 6.2 反模式清单

| 反模式 | 为什么危险 |
|--------|-----------|
| 直接把 Neo4j 当正式图谱真相 | 会破坏 Iceberg canonical truth 原则，恢复与审计都会失真 |
| graph delta 绕过 Layer A 直接写 live graph | 会让 Neo4j 与 Iceberg 出现不可追踪偏差 |
| 在传播计算里加入 recommendation 逻辑 | 会让图层侵入 `main-core`，边界失效 |
| 事件驱动局部模拟直接写回 live graph | 会污染日频正式图状态，破坏 formal / interim 分层 |
| 用代码 import `main-core` 内部函数读取 regime | 会形成反向依赖，阻断项目并行开发 |
| 把 promotion / propagation / reload 拆成独立项目 | 共享状态和故障恢复语义会被撕裂 |

---

## 7. 用户与消费方

### 7.1 直接消费方

| 消费方 | 消费内容 | 用途 |
|--------|----------|------|
| `main-core` | `graph_snapshot`、`graph_impact_snapshot`、子图查询 | L3/L5/L6/L7 图谱上下文 |
| `audit-eval` | snapshot 历史、传播路径、一致性状态 | 回放、评估、故障排查 |
| `stream-layer` | 只读局部传播模拟与受影响子图 | 事件驱动 interim 分析 |
| `orchestrator` | Phase 0 一致性检查、Phase 1 图谱更新入口 | Dagster 装配 |

### 7.2 间接用户

| 角色 | 关注点 |
|------|--------|
| 主编 / 架构 owner | 图谱 truth / mirror 边界是否稳定 |
| reviewer | 是否有人把图谱逻辑写进主系统或编排层 |
| 运维 / 值班人员 | Cold Reload 是否可重放、graph_status 是否可解释 |

---

## 8. 总体系统结构

### 8.1 Phase 0 一致性主线

```text
latest graph canonical truth in Layer A
  -> compare with neo4j live graph
  -> if mismatch then cold_reload()
  -> rebuild indexes + GDS projection
  -> verify node/edge/checksum
  -> graph_status = ready
```

### 8.2 Phase 1 图谱更新主线

```text
validated candidate graph deltas
  -> write canonical record into Layer A
  -> promote into Neo4j live graph
  -> read world_state(N-1) as regime context
  -> run propagation
  -> generate graph_snapshot(N) + graph_impact_snapshot(N)
  -> write snapshots back to Layer A
```

### 8.3 只读查询 / 局部模拟主线

```text
query or event seed
  -> check graph_status == ready
  -> open readonly projection / query subgraph
  -> run readonly local simulation
  -> return interim result without mutating live graph
```

---

## 9. 领域对象设计

### 9.1 持久层对象

| 对象名 | 职责 | 归属 |
|--------|------|------|
| GraphNodeRecord | 正式图节点记录 | Layer A Canonical Zone |
| GraphEdgeRecord | 正式图边记录 | Layer A Canonical Zone |
| GraphAssertionRecord | 图断言与证据记录 | Layer A Canonical / Analytical |
| CandidateGraphDelta | 候选图谱变更记录 | Layer A Canonical 输入 |
| GraphSnapshot | 一轮 cycle 的正式图结构快照 | Layer A Canonical / Analytical |
| GraphImpactSnapshot | 一轮传播结果快照 | Layer A Analytical |
| Neo4jGraphStatus | live graph 状态与一致性元数据 | PostgreSQL 当前态 |

### 9.2 运行时对象

| 对象名 | 职责 | 生命周期 |
|--------|------|----------|
| PromotionPlan | 一次 graph promotion 的待执行计划 | 单次 Phase 1 期间 |
| PropagationContext | 一轮传播所需输入上下文 | 单次传播期间 |
| PropagationResult | 传播后的路径、影响分数与节点更新摘要 | 单次传播期间 |
| ColdReloadPlan | 一次重建 live graph 的执行计划 | 单次 Cold Reload 期间 |
| ReadonlySimulationRequest | 一次局部图传播模拟请求 | 单次查询 / 事件期间 |

### 9.3 核心对象详细设计

#### CandidateGraphDelta

**角色**：经 Layer B 校验冻结后，等待 graph promotion 的候选变更。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| delta_id | String | 唯一标识 |
| cycle_id | String | 所属 cycle |
| delta_type | String | `node_add` / `edge_add` / `edge_update` / `assertion_add` |
| source_entity_ids | Array[String] | 涉及的 canonical entity 锚点 |
| payload | JSON | 节点/边/断言候选内容 |
| validation_status | String | `validated` / `rejected` / `frozen` |

#### GraphSnapshot

**角色**：一轮正式图更新后的结构性快照。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| cycle_id | String | 所属 cycle |
| snapshot_id | String | 图快照唯一标识 |
| graph_generation_id | Integer | 对应的 live graph 代际 |
| node_count | Integer | 节点数 |
| edge_count | Integer | 边数 |
| key_label_counts | JSON | 核心标签计数 |
| checksum | String | 关键节点/边校验摘要 |
| created_at | Timestamp | 生成时间 |

#### GraphImpactSnapshot

**角色**：传播计算后的正式影响快照。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| cycle_id | String | 所属 cycle |
| impact_snapshot_id | String | 唯一标识 |
| regime_context_ref | String | 使用的 `world_state_snapshot` 引用 |
| activated_paths | JSON | 激活传播路径摘要 |
| impacted_entities | JSON | 受影响实体与影响分数 |
| channel_breakdown | JSON | `fundamental / event / reflexive` 分通道结果 |

#### Neo4jGraphStatus

**角色**：描述 live graph 当前是否可读、对应哪一代 canonical truth。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| graph_status | String | `ready` / `rebuilding` / `failed` |
| graph_generation_id | Integer | 每次 reload 成功后递增 |
| node_count | Integer | live graph 节点数 |
| edge_count | Integer | live graph 边数 |
| key_label_counts | JSON | 核心标签计数 |
| checksum | String | 关键属性抽样 hash |
| last_verified_at | Timestamp | 最近一次通过校验时间 |
| last_reload_at | Timestamp | 最近一次冷重载成功时间 |

#### PropagationContext

**角色**：把 live graph 当前态和 read-only regime context 包成一次传播输入。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| cycle_id | String | 当前 cycle |
| world_state_ref | String | `world_state_snapshot` 引用 |
| graph_generation_id | Integer | 使用的 live graph 代际 |
| enabled_channels | Array[String] | 启用的传播通道 |
| decay_policy | JSON | 各通道衰减规则 |

---

## 10. 数据模型设计

### 10.1 模型分层策略

- 正式图节点、图边、图断言、graph snapshot -> Layer A 持久化
- live graph 当前态 -> Neo4j 运行态热镜像
- 一致性状态与 reload 元数据 -> PostgreSQL 当前态
- GDS projection、传播中间结果、只读局部模拟结果 -> 内存 / 临时对象

### 10.2 存储方案

| 存储用途 | 技术选型 | 理由 |
|----------|----------|------|
| Graph Canonical Truth | Iceberg | 正式历史版本、可审计、可重建 |
| Live Graph | Neo4j | 图查询、传播计算、增量更新 |
| Graph Status | PostgreSQL | 当前态读写简单、便于 Gate 检查 |
| 传播中间对象 | Python dataclass / Pydantic | 接口稳定、易测试 |
| GDS Projection | Neo4j GDS 内存投影 | 提升传播计算性能 |

### 10.3 关系模型

- `CandidateGraphDelta.source_entity_ids -> canonical_entity.canonical_entity_id`
- `GraphSnapshot.graph_generation_id -> Neo4jGraphStatus.graph_generation_id`
- `GraphImpactSnapshot.regime_context_ref -> world_state_snapshot.id`
- `GraphNodeRecord` / `GraphEdgeRecord` 是 Iceberg truth，Neo4j live graph 只是运行态镜像

---

## 11. 核心计算/算法设计

### 11.1 Graph Promotion 算法

**输入**：冻结后的 `CandidateGraphDelta` 集合、当前 Graph Canonical Truth。

**输出**：更新后的正式图节点/边/断言与 Neo4j 增量操作计划。

**处理流程**：

```text
读取 candidate graph deltas
  -> 校验依赖 entity 锚点已存在
  -> 生成 PromotionPlan
  -> 先写 Layer A canonical records
  -> 成功后再生成 Neo4j MERGE / UPDATE 操作
  -> 更新 live graph
```

### 11.2 增量同步算法

**输入**：PromotionPlan、live graph 当前态。

**输出**：同步后的 Neo4j live graph。

**处理流程**：

```text
for each promoted node/edge/assertion
  -> MERGE 节点 / 边
  -> 更新必要属性
  -> 维护索引可见性
  -> 记录同步摘要
```

### 11.3 三类传播算法

**输入**：live graph、`world_state_snapshot`、传播参数。

**输出**：节点影响分数、路径摘要、通道分解结果。

**处理流程**：

```text
read graph_status == ready
  -> build PropagationContext
  -> run fundamental propagation
  -> run event propagation
  -> run reflexive propagation
  -> merge channel results
  -> apply path_score = relation_weight * evidence_confidence * channel_multiplier * regime_multiplier * recency_decay
  -> emit GraphImpactSnapshot payload
```

**说明**：

- fundamental 通道强调供应链、产业链、股权与基本面传导
- event 通道强调公告、政策、制裁、停复牌等事件冲击
- reflexive 通道强调资金、情绪、行为反馈与二阶影响
- regime context 只负责调整权重、延迟与衰减，不负责替代图谱传播逻辑
- 单条传播路径的核心权重项至少包括 `relation_weight`、`evidence_confidence`、`channel_multiplier`、`regime_multiplier` 和 `recency_decay`，实现可以扩展，但不能退化成不可解释黑盒分数

### 11.4 Snapshot 生成算法

**输入**：同步后的 live graph、传播结果。

**输出**：`GraphSnapshot` 与 `GraphImpactSnapshot`。

**处理流程**：

```text
统计当前 live graph node_count / edge_count
  -> 生成 key_label_counts + checksum
  -> 组装 GraphSnapshot
  -> 组装 GraphImpactSnapshot
  -> 回写 Layer A
```

### 11.5 Cold Reload 算法

**输入**：最新 Graph Canonical Truth、当前 `neo4j_graph_status`。

**输出**：重建后的 live graph 与新的 ready 状态。

**处理流程**：

```text
set graph_status = rebuilding
  -> clear Neo4j
  -> full load nodes / edges / assertions from Iceberg
  -> rebuild indexes and GDS projection
  -> verify node_count + edge_count + checksum
  -> if pass set graph_status = ready and bump graph_generation_id
  -> else set graph_status = failed
```

### 11.6 Read-only 局部模拟算法

**输入**：事件 seed、只读 live graph、可选 regime context。

**输出**：局部受影响子图与 interim impact 结果。

**处理流程**：

```text
check graph_status == ready
  -> create readonly named projection
  -> run local propagation simulation
  -> return impacted subgraph
  -> drop readonly projection
```

**规则**：这个流程不修改 live graph，不写正式 snapshot，不替代日频 Phase 1。

---

## 12. 触发/驱动引擎设计

### 12.1 触发源类型

| 类型 | 来源 | 示例 |
|------|------|------|
| 一致性触发 | `orchestrator` / manual | Phase 0 校验、手动 reload |
| 日频更新触发 | `orchestrator` | Phase 1 graph promotion + propagation |
| 只读查询触发 | `main-core` / `audit-eval` | 子图查询、impact 查询 |
| 局部模拟触发 | `stream-layer` | 突发事件 interim 传播模拟 |

### 12.2 关键触发流程

```text
phase_1_graph_update()
  -> promote_graph_deltas()
  -> sync_live_graph()
  -> compute_propagation()
  -> persist_graph_snapshots()
```

### 12.3 启动顺序基线

| 阶段 | 动作 | 说明 |
|------|------|------|
| P1-P2 | `data-platform` 先准备好 graph canonical truth 表与回写位置 | 图谱 truth 先有落地 |
| P2-P3 | `entity-registry` 提供稳定的 canonical entity 锚点 | 图节点不能漂移 |
| P3a | `graph-engine` 打通 schema + promotion + 单通道传播 + snapshot 回写 | 先做图谱主干 |
| P3b | 增补三类传播、Cold Reload、只读局部模拟 | 完整图谱能力 |

---

## 13. 输出产物设计

### 13.1 Graph Snapshot

**面向**：`main-core`、`audit-eval`

**结构**：

```text
{
  cycle_id: String
  snapshot_id: String
  graph_generation_id: Integer
  node_count: Integer
  edge_count: Integer
  key_label_counts: Object
  checksum: String
}
```

### 13.2 Graph Impact Snapshot

**面向**：`main-core`、`audit-eval`

**结构**：

```text
{
  cycle_id: String
  impact_snapshot_id: String
  regime_context_ref: String
  channel_breakdown: Object
  impacted_entities: Array[Object]
  activated_paths: Array[Object]
}
```

### 13.3 Graph Query Result

**面向**：`main-core`、`stream-layer`

**结构**：

```text
{
  graph_generation_id: Integer
  subgraph_nodes: Array[Object]
  subgraph_edges: Array[Object]
  status: String
}
```

### 13.4 Graph Status Payload

**面向**：`orchestrator`、运维

**结构**：

```text
{
  graph_status: String
  graph_generation_id: Integer
  node_count: Integer
  edge_count: Integer
  checksum: String
  last_verified_at: Timestamp
}
```

---

## 14. 系统模块拆分

**组织模式**：单个 Python 项目，内部按 promotion / propagation / reload / query / snapshot 分 package。

| 模块名 | 语言 | 运行位置 | 职责 |
|--------|------|----------|------|
| `graph_engine.schema` | Python + Cypher | 库 | 节点/边 schema、索引、约束 |
| `graph_engine.promotion` | Python | 库 | candidate graph delta -> canonical promotion |
| `graph_engine.sync` | Python | 库 | Iceberg -> Neo4j 增量同步 |
| `graph_engine.propagation` | Python | 库 | 三类传播与通道融合 |
| `graph_engine.snapshots` | Python | 库 | `graph_snapshot` / `graph_impact_snapshot` 生成 |
| `graph_engine.reload` | Python | 库 | Cold Reload 与一致性恢复 |
| `graph_engine.status` | Python | 库 | `neo4j_graph_status` 状态流转 |
| `graph_engine.query` | Python | 库 | 子图查询与只读局部模拟 |

**关键设计决策**：

- `graph-engine` 必须是一个项目，不再拆成 promotion / propagation / reload 多个子项目
- 它对 `main-core` 只有**数据输入依赖**，没有代码反向依赖
- 它拥有图谱计算语义与状态流转，但不拥有 Layer A 的物理存储策略
- `neo4j_graph_status` 的状态机语义归本模块，物理 PostgreSQL 资源由 `data-platform` / `assembly` 提供
- Full 模式事件触发归 `stream-layer`，但只读局部图模拟能力仍由本模块提供

---

## 15. 存储与技术路线

| 用途 | 技术选型 | 理由 |
|------|----------|------|
| Live Graph | Neo4j 5.x | 原生图查询、增量更新、属性敏感传播 |
| 图传播算法 | Neo4j GDS + Cypher | PageRank / path / 中心性 / 自定义传播 |
| 正式图持久化 | Iceberg | graph canonical truth 与快照历史 |
| graph_status 当前态 | PostgreSQL | 轻量、稳定、便于 Gate |
| 回补 / 诊断读取 | DuckDB / Python | Lite 模式查询便利 |

最低要求：

- Neo4j 可用，并支持所需索引与 GDS projection
- 可读取 `data-platform` 提供的 graph canonical truth
- 可读取 `main-core` 发布的 `world_state_snapshot`，但只按合同/数据表读取
- Cold Reload 全流程在 Lite 环境可跑通

---

## 16. API 与接口合同

### 16.1 Python 接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `promote_graph_deltas(cycle_id, selection_ref)` | 执行 graph promotion | `cycle_id`、候选集合引用 |
| `sync_live_graph(promotion_batch)` | 把 promotion 结果同步到 Neo4j | `promotion_batch` |
| `compute_graph_snapshots(cycle_id, world_state_ref)` | 生成图快照和影响快照 | `cycle_id`、`world_state_ref` |
| `check_live_graph_consistency(snapshot_ref)` | 校验 Neo4j 与 Iceberg 一致性 | `snapshot_ref` |
| `cold_reload(snapshot_ref)` | 从 Iceberg 全量重建 live graph | `snapshot_ref` |
| `query_subgraph(seed_entities, depth)` | 查询局部子图 | entity ids、深度 |
| `simulate_readonly_impact(seed_entities, context)` | 执行只读局部传播模拟 | seeds、上下文 |

### 16.2 协议接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `GraphPromotionInterface` | graph delta -> promotion 语义接口 | candidate delta payload |
| `PropagationEngineInterface` | 图传播执行接口 | graph ref、regime context |
| `GraphQueryInterface` | 子图查询与只读模拟接口 | seeds、filters |
| `GraphSnapshotSchema` | graph snapshot schema | 由 `contracts` 定义 |
| `GraphImpactSnapshotSchema` | impact snapshot schema | 由 `contracts` 定义 |

### 16.3 版本与兼容策略

- `graph_snapshot` / `graph_impact_snapshot` 返回结构必须通过 `contracts` 发布
- 读取 `world_state_snapshot` 时只能依赖 schema 与表语义，不能 import `main-core` 内部代码
- `graph_generation_id` 的递增语义必须稳定，供回放和审计使用
- 只读局部模拟接口不得写正式 snapshot，也不得修改 live graph

---

## 18. 测试与验证策略

### 18.1 单元测试

- graph promotion 对同一 delta 幂等执行测试
- `graph_status` 状态流转测试
- three-channel propagation 融合逻辑测试
- `world_state_snapshot` 只读 regime context 应用测试
- 只读局部模拟不写 live graph 测试

### 18.2 集成测试

| 场景 | 验证目标 |
|------|----------|
| candidate graph delta -> Layer A -> Neo4j | 验证写入顺序与增量同步 |
| Phase 0 一致性校验 + Cold Reload | 验证可重建、可恢复 |
| 单 cycle 传播计算 + snapshot 回写 | 验证 Phase 1 主干闭环 |
| `main-core` 读取 `graph_impact_snapshot` | 验证下游消费接口稳定 |
| `stream-layer` 只读局部模拟 | 验证 interim 路径不写正式 live graph |

### 18.3 协议 / 契约测试

- graph delta / snapshot / impact snapshot schema 与 `contracts` 对齐
- 读取 `world_state_snapshot` 只走合同层，不建立反向代码依赖
- Graph Canonical Truth 表与 snapshot 回写位置符合 `data-platform` 约定
- graph promotion 输入不得包含原始文本、chunk 或 LightRAG artifact

### 18.4 性能与回归测试

- 10 万节点 / 50-100 万边传播在目标预算内完成
- Cold Reload 从清空到 ready 在超时上限内完成
- `graph_status != ready` 时任何读请求都被阻断
- 随机抽样校验 Neo4j 与 Iceberg checksum 不漂移

---

## 19. 关键评价指标

### 19.1 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| Phase 1 单轮传播耗时 | `< 60 秒` | Lite 规模目标 |
| Phase 0 一致性校验耗时 | `< 5 秒` | 正常 cycle 常态 |
| Cold Reload 典型耗时 | `< 90 秒` | 正常规模下目标值 |
| Cold Reload 硬超时 | `< 5 分钟` | 超过即判失败 |

### 19.2 质量指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| ready 状态下 Neo4j / Iceberg 计数偏差率 | `0` | 出现偏差必须 reload |
| 事件驱动局部模拟误写正式图次数 | `0` | interim 与 formal 严格分离 |
| `graph_snapshot` / `graph_impact_snapshot` 产出成功率 | `100%` | 成功 cycle 必须完整产出 |
| 反向代码依赖事件数 | `0` | `graph-engine` 不 import `main-core` |

---

## 20. 项目交付物清单

### 20.1 图谱主干能力

- Neo4j schema / 索引 / 约束
- graph promotion
- live graph 增量同步
- `graph_snapshot`
- `graph_impact_snapshot`

### 20.2 运维与恢复能力

- `neo4j_graph_status`
- Phase 0 一致性校验
- Cold Reload
- GDS projection 重建

### 20.3 图服务能力

- 子图查询接口
- 传播路径查询接口
- 只读局部传播模拟接口

---

## 21. 实施路线图

### 阶段 0：图谱性能与模型 Spike（2-3 天）

**阶段目标**：先验证 Neo4j + GDS 在目标规模下可承受。

**交付**：
- 目标规模压测脚本
- 基础 schema 草案
- 传播预算报告

**退出条件**：确认 Lite 目标规模下传播可以落在 1 分钟预算内。

### 阶段 1：P3a 图谱主干（4-6 天）

**阶段目标**：打通 graph promotion、增量同步、单通道传播和 snapshot 回写。

**交付**：
- graph promotion
- live graph sync
- 一种传播通道
- `graph_snapshot` / `graph_impact_snapshot`

**退出条件**：候选图谱变更能进入正式图，并完成单轮快照回写。

### 阶段 2：P3a 运维闭环（3-5 天）

**阶段目标**：补齐 `neo4j_graph_status`、一致性校验和 Cold Reload。

**交付**：
- `neo4j_graph_status`
- consistency check
- cold reload
- GDS projection rebuild

**退出条件**：Neo4j 可被清空、重建、校验并重新进入 `ready`。

### 阶段 3：P3b 完整传播（5-8 天）

**阶段目标**：补齐三类传播和 regime-aware 参数调整。

**交付**：
- fundamental propagation
- event propagation
- reflexive propagation
- channel merge 逻辑

**退出条件**：图谱完整传播语义可稳定产出正式 impact snapshot。

### 阶段 4：P3b 只读服务与后续集成（3-5 天）

**阶段目标**：为 `main-core`、`audit-eval`、`stream-layer` 提供稳定只读接口。

**交付**：
- subgraph query
- readonly local simulation
- 消费方接入样例

**退出条件**：事件驱动链路可以读取图谱做 interim 分析，但不写正式图。

---

## 22. 主要风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 把 Neo4j 当成正式 truth | 审计与恢复失真 | 强制 Truth Before Mirror，reload 以 Iceberg 为准 |
| graph delta 写入顺序被破坏 | Neo4j / Iceberg 偏差 | 固化 Phase 1 顺序并做契约测试 |
| 传播复杂度失控 | 无法满足日频预算 | 先做 Spike，再逐步启用通道 |
| regime context 形成代码反向依赖 | 项目边界被破坏 | 只读表语义 + 合同层读取 |
| 局部模拟误写 live graph | interim / formal 混淆 | 只读 projection + 回归测试 |
| Cold Reload 失败后状态悬挂 | 整个 cycle 阻塞 | `failed` 状态显式暴露并要求人工介入 |

---

## 23. 验收标准

项目完成的最低标准：

1. `graph-engine` 能把冻结后的 `CandidateGraphDelta` 先写入 Layer A，再同步到 Neo4j live graph
2. `graph-engine` 能稳定生成并回写 `graph_snapshot` 与 `graph_impact_snapshot`
3. `neo4j_graph_status`、一致性校验和 Cold Reload 闭环都可运行，且 `graph_status` 可被外部读取
4. 三类传播（fundamental / event / reflexive）都具备正式实现，并能使用只读 regime context
5. `graph-engine` 不反向 import `main-core`，只通过合同和数据输入读取 `world_state_snapshot`
6. Full 模式局部图模拟保持只读，不污染正式 live graph
7. 文档中定义的 OWN / BAN / EDGE 与主项目 `12 + N` 模块边界一致

---

## 24. 一句话结论

`graph-engine` 子项目不是“存一份 Neo4j 数据”的辅助层，而是主项目里唯一负责把正式图谱真相转成可计算运行态、再把传播结果稳稳送回正式历史的图计算 owner。  
它如果边界不稳，后面的图特征、传播判断、事件冲击和审计回放都会一起失真。

---

## 25. 自动化开发对接

### 25.1 自动化输入契约

| 项 | 规则 |
|----|------|
| `module_id` | `graph-engine` |
| 脚本先读章节 | `§1` `§4` `§5.2` `§5.4` `§9` `§11` `§14` `§16` `§18` `§21` `§23` |
| 默认 issue 粒度 | 一次只实现一个图能力：promotion、propagation、reload/status、query/simulation 四类之一 |
| 默认写入范围 | 当前 repo 的图对象、Neo4j schema、传播算法、恢复逻辑、测试、文档和本模块配置 |
| 内部命名基线 | 以 `§9` 对象名、`§11` 算法名和 `§14` 内部模块名为准 |
| 禁止越界 | 不把 Neo4j 当 truth、不接原始文本 / LightRAG artifact、不反向 import `main-core`、不把 interim 路径写成 formal |
| 完成判定 | 同时满足 `§18`、`§21` 当前阶段退出条件和 `§23` 对应条目 |

### 25.2 推荐自动化任务顺序

1. 先落 graph promotion、snapshot 回写和最小 Neo4j schema
2. 再落 propagation 主干和传播权重解释项
3. 再落 `neo4j_graph_status`、consistency check 和 Cold Reload
4. 最后补 query / readonly local simulation 和 Full 路径只读接口

补充规则：

- 单个 issue 默认只改一条图能力链，不把 promotion、reload、query 混成大 PR
- 在压测预算、fixture 和 consistency check 未稳定前，不进入优化类 issue

### 25.3 Blocker 升级条件

- 输入开始包含原始文本、chunk、LightRAG artifact 或未合同化对象
- 设计上把 Neo4j 变成正式 truth 或允许跳过 Layer A 先写 Neo4j
- 需要反向 import `main-core` 内部实现或让实时链路写 formal live graph
- 无法给出 promotion / propagation / reload 的最小可验证样本
