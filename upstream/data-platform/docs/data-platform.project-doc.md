# data-platform 完整项目文档

> **文档状态**：Draft v1
> **版本**：v0.1.1
> **作者**：Codex
> **创建日期**：2026-04-15
> **最后更新**：2026-04-15
> **文档目的**：把 `data-platform` 子项目从“数据都放这里”的模糊概念收束为可立项、可拆分、可实现、可验收的正式项目，使其成为主项目中唯一负责共享数据落地、结构化转换、基础 serving、Lite 模式摄取与 cycle 控制基础设施的子项目。

---

## 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| v0.1 | 2026-04-15 | 初稿 | Codex |
| v0.1.1 | 2026-04-15 | 补充 `entity-registry` 初始化位点与 `stock_basic` 输入的边界说明 | Codex |

---

## 1. 一句话定义

`data-platform` 是主项目中**唯一负责 Raw Zone 归档、Canonical/Formal/Analytical 数据落地、结构化数据接入、dbt 转换、DuckDB/Iceberg Serving、Lite 模式 Layer B 摄取落库与 cycle 控制表基础设施**的数据基座模块，它以“Layer A 是共享数据唯一真相存储层”和“数据落地、合同校验、业务判断严格分层”为不可协商约束。

它不是主系统业务判断模块，不是图谱传播模块，也不是 Dagster 编排定义模块。  
它不拥有 `canonical_entity` 的业务规则，不拥有 L4-L7 推荐逻辑，不拥有 Neo4j live graph 的运行态计算。

---

## 2. 文档定位与核心问题

本文解决的问题不是“怎么搭一个数据仓库”，而是：

1. **共享数据唯一落地问题**：主项目所有共享结构化数据必须有统一存储边界，否则各模块会各自落库、各自演化。
2. **Lite 阶段基础设施闭环问题**：P1 必须在单节点、少进程条件下打穿 API 采集、dbt 转换、Iceberg 写入、DuckDB 查询和 Layer B 队列闭环。
3. **数据与业务边界问题**：数据平台必须提供可复用的落地与 serving 能力，但不能侵入主系统判断、实体规则和编排策略。

---

## 3. 术语表

| 术语 | 定义 | 备注 |
|------|------|------|
| Raw Zone | 原始 API / 文件返回数据的归档区 | Parquet / JSON，非 Iceberg |
| Canonical Zone | 规范化后的共享结构化数据区 | Iceberg + Parquet |
| Formal Zone | 主系统正式发布对象区 | Iceberg + `cycle_publish_manifest` |
| Analytical Zone | 非 formal 的分析产物区 | Iceberg |
| Formal Serving | 面向下游模块的 `latest / by_id / by_snapshot` 读取语义 | 通过 DuckDB + Iceberg 实现 |
| DataSourceAdapter | 结构化数据源标准接入协议 | 由 `contracts` 定义，`data-platform` 实现 |
| Ingest Metadata | Layer B 落库时补写的摄取元数据 | 如 `submitted_at`、`ingest_seq` |
| Cycle Metadata | 一次日频 cycle 的控制元数据 | 如 cutoff、冻结时间、状态 |
| Candidate Selection | Phase 0 冻结后的本轮候选集合 | `cycle_candidate_selection` |
| Publish Manifest | Phase 3 发布清单 | `cycle_publish_manifest` |
| PG-backed SQL Catalog | Lite 模式 Iceberg catalog 选型 | 复用 PostgreSQL |

**规则**：
- `Raw Zone` 不等于 Iceberg namespace
- `Canonical / Formal / Analytical` 才是 Iceberg 的主要语义层
- `Ingest Metadata` 不是生产者 Ex payload 的一部分

---

## 4. 目标与非目标

### 4.1 项目目标

1. **落地共享数据**：为主项目提供唯一的 Raw / Canonical / Formal / Analytical 数据落地基础设施。
2. **接入结构化数据源**：实现 `DataSourceAdapter` 协议和首个 Tushare 参考实现。
3. **管理结构化转换**：通过 dbt 管理 staging / intermediate / marts 三层 SQL 转换。
4. **提供基础读取能力**：提供 Formal Serving 和 Canonical 查询基础能力，供其他子项目只读消费。
5. **实现 Lite 摄取闭环**：提供 PostgreSQL 队列、Python 校验、`ingest_metadata` 落库与 cycle 控制表。
6. **支撑周期控制**：提供 `cycle_candidate_selection`、`cycle_metadata`、`cycle_publish_manifest` 等表及最小流程原型。
7. **验证关键技术路径**：完成 Iceberg 写入链 architecture spike，确保 Lite 路径不是纸面承诺。
8. **提供实体初始化位点**：提供 `stock_basic` canonical 输入和 `canonical_entity` / `entity_alias` 的正式存储位点，供 `entity-registry` 完成业务初始化。

### 4.2 非目标

- **不做业务判断**：L4/L5/L6/L7 的业务决策归 `main-core`，因为数据平台只负责落地与服务。
- **不做图谱传播**：图谱 promotion、传播和 snapshot 计算归 `graph-engine`。
- **不定义实体业务规则**：`canonical_entity_id` 生成规则、别名与消歧规则归 `entity-registry`。
- **不拥有 Dagster job 定义**：具体 schedule、sensor、asset group wiring 归 `orchestrator`，本项目只提供 asset/resource 工厂。
- **不直接调用 LLM**：LLM 调用与回放字段生成归 `reasoner-runtime` 或上层业务模块。

---

## 5. 与现有工具的关系定位

### 5.1 架构位置

```text
结构化数据源 / 子系统提交 / 主系统 publish
  -> data-platform
      ├── Raw Zone
      ├── Canonical Zone
      ├── Formal Zone
      ├── Analytical Zone
      ├── dbt transforms
      ├── DuckDB serving
      └── Lite Layer B queue + cycle tables
  -> 下游消费方
      ├── entity-registry
      ├── graph-engine
      ├── main-core
      ├── audit-eval
      ├── subsystem-sdk / subsystems
      ├── orchestrator
      └── assembly
```

### 5.2 上游输入

| 来源 | 提供内容 | 说明 |
|------|----------|------|
| 结构化数据源 | 行情、财务、指数、公告元数据等 | 通过 `DataSourceAdapter` 接入 |
| `subsystem-sdk` / 子系统 | Ex-1 / Ex-2 / Ex-3 提交对象 | Lite 模式先写 PostgreSQL 队列 |
| `main-core` | Phase 3 formal objects 发布动作 | 表与存储约束由本模块提供 |
| `contracts` | schema、协议、错误码 | 本模块不能绕开合同定义 |

### 5.3 下游输出

| 目标 | 输出内容 | 消费方式 |
|------|----------|----------|
| `entity-registry` | `stock_basic` canonical 表、基础实体原料、`canonical_entity` / `entity_alias` 存储位点 | DuckDB / SQL / Python 接口 |
| `graph-engine` | candidate graph delta canonical 记录、graph snapshot 回写目标表 | Iceberg 表 |
| `main-core` | L2 数据、L3 特征表、formal serving | Python API / DuckDB 查询 |
| `audit-eval` | analytical namespace、历史特征、formal objects | Iceberg + DuckDB |
| `orchestrator` | asset/resource 工厂、dbt project、队列表、cycle 表 | Python import |
| `assembly` | 存储和本地环境配置 | 配置 + compose |

### 5.4 核心边界

- **Layer A 的共享真相落地只归 `data-platform`**
- **Raw Zone 是 Parquet / JSON 归档，不是 Iceberg namespace**
- **`canonical_entity` 业务规则不归 `data-platform`**
- **`data-platform` 提供 `canonical_entity` / `entity_alias` 的存储位点和 `stock_basic` canonical 输入，但初始化内容与规则归 `entity-registry`**
- **Dagster job / schedule / policy 不归 `data-platform`**
- **摄取元数据归 Layer B 落库逻辑，不进入生产者 Ex payload**

---

## 6. 设计哲学

### 6.1 设计原则

#### 原则 1：Storage-first, Logic-later

先把共享数据落地与读取边界定清，再让上层业务和图谱计算依赖它。  
如果没有稳定存储边界，后续模块会各自绕过平台直连数据源。

#### 原则 2：Lite-first Reality

所有设计先满足 Lite 模式真实可跑。  
不能依赖 Full 组件存在之后才成立，否则 P1 无法验证。

#### 原则 3：Single Landing Zone per Data Class

每类共享数据必须只有一个正式落地位置。  
例如 formal objects 只能通过 Formal Zone + manifest 暴露，不允许私有副本。

#### 原则 4：Execution/Ownership Separation

本模块拥有数据落地与资产工厂，不拥有调度定义。  
这样 `data-platform` 和 `orchestrator` 才能保持清晰边界。

### 6.2 反模式清单

| 反模式 | 为什么危险 |
|--------|-----------|
| 把 Raw Zone 也做成 Iceberg 正式层 | 会提高原始归档复杂度，并偏离主文档定义 |
| 在 `data-platform` 中写 L4-L7 业务逻辑 | 会让 Layer A 侵入主系统边界 |
| 让子系统直接写 Canonical / Formal 表 | 会绕开 Layer B 和 publish 机制 |
| 在 `data-platform` 中直接写 Dagster job/schedule | 会让数据平台和编排耦合 |
| 将 `submitted_at` / `ingest_seq` 暴露为生产者合同字段 | 会污染长期接口边界 |

---

## 7. 用户与消费方

### 7.1 直接消费方

| 消费方 | 消费内容 | 用途 |
|--------|----------|------|
| `main-core` | L2 数据、L3 特征表、formal objects 读取 | 主系统业务链 |
| `graph-engine` | candidate graph delta canonical 表、snapshot 回写位置 | 图谱更新与回写 |
| `entity-registry` | `stock_basic` 等 canonical 表 | 初始化与别名扩展 |
| `subsystem-sdk` / 子系统 | Lite 队列写入入口 | 候选提交 |
| `orchestrator` | asset/resource 工厂、dbt 目录、队列表 | Dagster 装配 |

### 7.2 间接用户

| 角色 | 关注点 |
|------|--------|
| 主编 / 架构 owner | 存储边界是否稳定、是否符合 Lite 约束 |
| 自动化代理 | 是否有清晰的表、接口和目录可依赖 |
| reviewer | 是否出现业务逻辑侵入数据平台 |

---

## 8. 总体系统结构

### 8.1 结构化数据接入主线

```text
结构化数据源
  -> DataSourceAdapter
  -> Raw Zone (Parquet / JSON)
  -> dbt staging
  -> dbt intermediate / marts
  -> Canonical / Feature Tables
  -> 下游模块读取
```

### 8.2 Lite 模式候选摄取主线

```text
subsystem-sdk / subsystem-*
  -> PostgreSQL 队列表
  -> Python 校验
  -> ingest_metadata 补写
  -> cycle_candidate_selection / cycle_metadata
  -> Canonical 写入或供后续阶段消费
```

### 8.3 Formal 发布主线

```text
main-core formal objects
  -> Formal Zone 单表 commit
  -> cycle_publish_manifest
  -> Formal Serving (latest / by_id / by_snapshot)
```

---

## 9. 领域对象设计

### 9.1 持久层对象

| 对象名 | 职责 | 归属 |
|--------|------|------|
| RawArtifact | 原始 API 返回数据归档 | Raw Zone |
| CanonicalTable | 规范化共享结构化表 | Canonical Zone |
| FormalTable | 正式发布对象表 | Formal Zone |
| AnalyticalTable | 分析性产物表 | Analytical Zone |
| CandidateQueueItem | Lite 模式候选队列项 | PostgreSQL |
| IngestMetadataRecord | 摄取元数据记录 | PostgreSQL / view |
| CycleMetadata | 一轮 cycle 的控制元数据 | PostgreSQL |
| CycleCandidateSelection | Phase 0 冻结的候选集合 | PostgreSQL |
| CyclePublishManifest | Formal 发布清单 | PostgreSQL |

### 9.2 运行时对象

| 对象名 | 职责 | 生命周期 |
|--------|------|----------|
| AdapterInstance | 具体数据源 adapter | 单次运行或进程级 |
| ServingQueryContext | Formal Serving 查询上下文 | 单次查询 |
| QueueValidationResult | 队列校验结果 | 单次摄取过程 |
| DbtRunContext | 一次 dbt 执行上下文 | 单次转换过程 |

### 9.3 核心对象详细设计

#### CandidateQueueItem

**角色**：Lite 模式下子系统提交候选对象的正式落库入口。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 队列主键 |
| payload_type | Enum | `Ex-0` / `Ex-1` / `Ex-2` / `Ex-3` |
| payload | JSON | 原始提交 payload |
| submitted_by | String | 子系统标识 |
| submitted_at | Timestamp | PG 服务端生成 |
| ingest_seq | Integer | BIGSERIAL 排序字段 |
| validation_status | Enum | `pending` / `accepted` / `rejected` |
| rejection_reason | String \| Null | 拒绝原因 |

#### CycleMetadata

**角色**：记录一次 cycle 的冻结边界和运行控制状态。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| cycle_id | String | 如 `CYCLE_YYYYMMDD` |
| cycle_date | Date | 对应交易日 |
| status | Enum | `pending` / `phase0` / `phase1` / `phase2` / `phase3` / `published` / `failed` |
| cutoff_submitted_at | Timestamp | 冻结时刻 |
| cutoff_ingest_seq | Integer | 冻结时最大 ingest_seq |
| candidate_count | Integer | 冻结数量 |
| selection_frozen_at | Timestamp | 冻结完成时间 |

#### CyclePublishManifest

**角色**：Formal 发布的一致性读取锚点。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| published_cycle_id | String | 发布 cycle ID |
| published_at | Timestamp | PG 服务端时间 |
| formal_table_snapshots | JSON | 每张 formal 表的 snapshot_id / version |

#### DataSourceAdapterImpl

**角色**：结构化数据源在本模块中的实现对象。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| source_id | String | 如 `tushare` |
| quota_config | JSON | 积分 / 限流配置 |
| assets_factory | Callable | 生成 asset 实现 |
| resources_factory | Callable | 生成资源配置 |
| staging_models | Array[String] | 对应 dbt staging models |

---

## 10. 数据模型设计

### 10.1 模型分层策略

- 原始返回数据 → Raw Zone（Parquet / JSON）
- 规范化共享结构化数据 → Canonical Zone（Iceberg）
- 主系统正式发布对象 → Formal Zone（Iceberg）
- 非 formal 分析性数据 → Analytical Zone（Iceberg）
- 摄取控制与运行元数据 → PostgreSQL

### 10.2 存储方案

| 存储用途 | 技术选型 | 理由 |
|----------|----------|------|
| Raw Zone | Parquet / JSON 文件归档 | 简单、可追溯、适合原始回放 |
| Canonical / Formal / Analytical | Apache Iceberg + Parquet | 版本化、time travel、共享查询 |
| 当前态 / 控制表 | PostgreSQL | 事务、状态控制、队列 |
| 分析查询 | DuckDB | 嵌入式、直读 Iceberg、适合 Lite 模式 |
| SQL 转换 | dbt Core + dbt-duckdb | 管理 75-90 个转换与测试 |

### 10.3 关系模型

- `cycle_candidate_selection.cycle_id -> cycle_metadata.cycle_id`
- `cycle_publish_manifest.published_cycle_id -> cycle_metadata.cycle_id`
- `CandidateQueueItem.id -> cycle_candidate_selection.candidate_id`
- formal object 实际读取必须经 `cycle_publish_manifest` 反查 snapshot

---

## 11. 核心计算/算法设计

### 11.1 Lite 模式候选冻结算法

**输入**：当前队列表中的待消费候选。

**输出**：本轮 `cycle_candidate_selection` 与 `cycle_metadata`。

**处理流程**：

```text
创建 cycle_id
  -> 在单个 PG 事务中读取当前待消费候选
  -> 写入 cycle_candidate_selection(cycle_id, candidate_id)
  -> 写入 cycle_metadata(cutoff_submitted_at, cutoff_ingest_seq, candidate_count, selection_frozen_at)
  -> 提交事务
```

### 11.2 Formal Serving 读取算法

**输入**：`latest` / `by_id(cycle_id)` / `by_snapshot(snapshot_id)` 查询请求。

**输出**：对应 formal object 版本。

**处理流程**：

```text
读取 cycle_publish_manifest
  -> 解析 formal_table_snapshots
  -> 通过 Iceberg time travel 选择 snapshot
  -> 用 DuckDB 查询返回结果
```

### 11.3 Iceberg 写入链验证算法

**输入**：1 个结构化数据源样本、1 个 staging model、schema 演化需求。

**输出**：可验证的 Lite 模式可行性结论。

**处理流程**：

```text
采集 1 个 API 样本
  -> 落 Raw Zone
  -> dbt staging 写 Canonical
  -> add column 演练
  -> time travel 验证
  -> 并发 commit 演练
  -> 形成 spike 结果
```

---

## 12. 触发/驱动引擎设计

### 12.1 触发源类型

| 类型 | 来源 | 示例 |
|------|------|------|
| 定时采集 | `orchestrator` | 每日 Tushare 行情拉取 |
| 子系统提交 | `subsystem-sdk` | Ex-2 候选信号写入队列 |
| formal 发布 | `main-core` | Phase 3 单表 commit 后写 manifest |

### 12.2 关键触发流程

```text
定时 / 提交事件
  -> asset / queue 入口
  -> 落库 / 校验 / 转换
  -> 写入目标区
  -> 供下游消费
```

---

## 13. 输出产物设计

### 13.1 Canonical 表

**面向**：`entity-registry`、`graph-engine`、`main-core`

**结构**：

```text
{
  table_name: String
  partition_key: String
  snapshot_id: Integer
  schema_version: String
}
```

### 13.2 Formal Serving 结果

**面向**：`main-core`、`audit-eval`、`assembly`

**结构**：

```text
{
  cycle_id: String
  snapshot_id: Integer
  object_type: String
  payload: Object
}
```

---

## 14. 系统模块拆分

**组织模式**：monorepo 下的独立 Python package + dbt project。

| 模块名 | 语言 | 运行位置 | 职责 |
|--------|------|----------|------|
| `data_platform.raw` | Python | 库/脚本 | Raw Zone 归档 |
| `data_platform.adapters` | Python | 库 | `DataSourceAdapter` 实现 |
| `data_platform.queue` | Python | 库 | Lite 队列与校验 |
| `data_platform.cycle` | Python | 库 | cycle 控制表与冻结逻辑 |
| `data_platform.serving` | Python | 库 | Formal Serving |
| `data_platform.dbt` | SQL + YAML | dbt project | staging/intermediate/marts |
| `data_platform.ddl` | SQL/Python | 库 | 表结构与 migration |

**关键设计决策**：

- `data-platform` 在主项目中的角色是**共享数据落地与查询基座**
- 它与其他子项目的关系是**上游提供数据与控制基础设施**
- 它必须独立成子项目，因为 P1 是所有后续模块的共同前置条件
- `Dagster definitions` 不在本项目内定义，只提供工厂与资源

---

## 15. 存储与技术路线

| 用途 | 技术选型 | 理由 |
|------|----------|------|
| Raw Zone | Parquet / JSON | 轻量、可回放 |
| Canonical/Formal/Analytical | Iceberg + Parquet | 版本化共享层 |
| 当前态 / 队列 / 控制表 | PostgreSQL | 事务、状态、PG-backed catalog |
| 分析查询 | DuckDB | Lite 模式嵌入式查询 |
| SQL 转换 | dbt Core + dbt-duckdb | 可视依赖、自动测试 |

最低要求：

- Python 3.12+
- PostgreSQL
- DuckDB
- dbt Core + dbt-duckdb
- Apache Iceberg（PG-backed SQL catalog）

---

## 16. API 与接口合同

### 16.1 Python 接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `get_formal_latest(object_type)` | 读取最近一次已发布 formal object | `object_type` |
| `get_formal_by_id(cycle_id, object_type)` | 读取指定 cycle formal object | `cycle_id`, `object_type` |
| `submit_candidate(payload)` | Lite 模式写入候选队列 | Ex payload |
| `freeze_cycle_candidates(cycle_id)` | 冻结本轮候选集合 | `cycle_id` |

### 16.2 协议接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `DataSourceAdapter` | 结构化数据源接入协议 | `get_assets / get_resources / get_staging_dbt_models / get_quota_config` |

### 16.3 版本与兼容策略

- 所有共享对象以 `contracts` 为准
- 表结构变更默认 backward compatible
- breaking change 必须先改 `contracts` 和本项目文档

---

## 18. 测试与验证策略

### 18.1 单元测试

- 队列校验逻辑
- cycle 冻结逻辑
- Formal Serving 查询逻辑
- adapter 实现与 quota 配置
- dbt model 基础测试

### 18.2 集成测试

| 场景 | 验证目标 |
|------|----------|
| 1 个 API 样本采集到 Canonical | 验证 P1a 最小闭环 |
| 100 条候选对象写队列并冻结 | 验证 P1c 闭环 |
| formal object 写入后通过 manifest 读取 | 验证 FIX-01 一致性读取 |
| schema add column 后旧 snapshot 可读 | 验证 Iceberg 演化路径 |

### 18.3 协议 / 契约测试

- `DataSourceAdapter` 实现符合 `contracts` 协议
- Ex payload 队列输入与 `contracts` 对齐
- `cycle_publish_manifest` 字段与正式合同对齐

### 18.4 性能 / 生命周期测试

- Iceberg 写入链 spike
- DuckDB time travel 查询
- 队列冻结事务正确性

---

## 19. 关键评价指标

### 19.1 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 1 API 最小闭环跑通时间 | `< 5 分钟` | 本地 Lite 环境 |
| Formal Serving 单次读取延迟 | `< 2 秒` | DuckDB + Iceberg 本地查询 |
| 100 条候选冻结事务耗时 | `< 3 秒` | 本地 PostgreSQL |

### 19.2 质量指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| P1a Iceberg 写入链 spike 成功率 | `100%` | 必须跑通 |
| dbt 基础测试通过率 | `100%` | staging 层最低要求 |
| manifest 一致性读取错误率 | `0` | 不允许读到半提交版本 |
| 摄取元数据与生产者 payload 混淆率 | `0` | 边界不能漂移 |

---

## 20. 项目交付物清单

### 20.1 存储与表结构

- Raw Zone 归档规范
- Canonical/Formal/Analytical 表定义
- `canonical_entity` / `entity_alias` 存储位点
- `cycle_candidate_selection`
- `cycle_metadata`
- `cycle_publish_manifest`

### 20.2 数据接入与转换

- Tushare adapter
- dbt project
- staging/intermediate/marts 模型骨架

### 20.3 服务与工具

- Formal Serving 读取接口
- Lite 队列写入与校验接口
- Iceberg 写入链 spike 结果

---

## 21. 实施路线图

### 阶段 0：P1a 骨架（1-2 周）

**阶段目标**：打通 1 个 API → 1 个 staging model → Canonical 的最小链路。

**交付**：
- PG-backed catalog
- DuckDB 查询
- dbt 骨架
- 1 个 API 样板

**退出条件**：Dagit 可视化依赖链可跑通，DuckDB 可查到 snapshot。

### 阶段 1：P1b 铺量（3-5 周）

**阶段目标**：扩展到完整结构化数据接入主线。

**交付**：
- 40 API 接入
- 40 staging models
- Raw Zone 归档规范

**退出条件**：结构化数据层每日自动更新。

### 阶段 2：P1c 摄取与 cycle 控制（1-2 周）

**阶段目标**：补完 Lite Layer B 和 cycle 基础设施。

**交付**：
- 队列表
- `cycle_candidate_selection`
- `cycle_metadata`
- `cycle_publish_manifest`

**退出条件**：候选冻结和 manifest 机制可单独演练通过。

---

## 22. 主要风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| Iceberg 写入链不通 | P1 全部阻塞 | 先做 spike，必要时切 PyIceberg 直写备选 |
| dbt / DuckDB / catalog 兼容问题 | 转换层返工成本高 | 先跑最小样例，再铺 40 API |
| 数据平台侵入编排或业务层 | 模块边界崩坏 | 严格坚持 M01/M09、M01/M05 边界 |
| manifest 读取被绕开 | formal 一致性失效 | 所有消费方必须先查 manifest |

---

## 23. 验收标准

项目完成的最低标准：

1. Raw Zone、Canonical、Formal、Analytical 的边界与落地方式全部明确并可运行
2. 至少 1 个 API 样例可以完成 Raw → staging → Canonical → DuckDB 读取闭环
3. Lite 队列、`cycle_candidate_selection`、`cycle_metadata`、`cycle_publish_manifest` 全部可用
4. `main-core`、`entity-registry`、`orchestrator` 能直接消费本项目提供的接口
5. 文档中定义的主项目角色、OWN/BAN/EDGE 与主项目 `12 + N` 模块表一致

---

## 24. 一句话结论

`data-platform` 子项目不是“数据都放这里”的模糊容器，而是主项目中唯一负责共享数据落地、基础转换、基础 serving 和 Lite 摄取控制的正式数据基座。  
它的稳定性直接决定后续 `main-core`、`graph-engine`、`entity-registry` 和子系统能否真正并行开发。

---

## 25. 自动化开发对接

### 25.1 自动化输入契约

| 项 | 规则 |
|----|------|
| `module_id` | `data-platform` |
| 脚本先读章节 | `§1` `§4` `§5.2` `§5.4` `§9` `§10` `§14` `§15` `§18` `§21` `§23` |
| 默认 issue 粒度 | 一次只实现一个表族、一个 adapter、一个 dbt / SQL 转换组，或一条最小 ingest / publish 路径 |
| 默认写入范围 | 当前 repo 的表定义、adapter、dbt / SQL、迁移脚本、测试、文档和运行配置 |
| 内部命名基线 | 以 `§9` / `§10` 的对象名、表名和 `§14` 内部模块名为准，不自发改表语义或另起平行命名 |
| 禁止越界 | 不把业务判断写进平台层、不绕开 ingest metadata / manifest 规则、不把 Raw Zone 改写成第二套真相体系 |
| 完成判定 | 同时满足 `§18`、`§21` 当前阶段退出条件和 `§23` 对应条目 |

### 25.2 推荐自动化任务顺序

1. 先落 Raw / Canonical / Formal / Analytical 位点、关键表定义和最小读写位点
2. 再落 adapter、dbt / SQL 转换链和基础 serving
3. 再落 `cycle_candidate_selection`、`cycle_metadata`、`cycle_publish_manifest` 等周期控制表
4. 最后补性能优化、运维脚本和 Full 路径预留

补充规则：

- 单个 issue 默认只改一条数据主线，不同时混做存储、adapter、dbt 和 serving 四类工作
- 未有 smoke / fixture 前，不进入优化类 issue

### 25.3 Blocker 升级条件

- Raw / Canonical / Formal / Analytical 任一层边界被改写
- `submitted_at` / `ingest_seq` 重新进入 producer payload
- `cycle_publish_manifest` 语义不清或出现绕开 manifest 直读 formal head 的设计
- 需要新增文档未冻结的长期基础服务 / daemon
