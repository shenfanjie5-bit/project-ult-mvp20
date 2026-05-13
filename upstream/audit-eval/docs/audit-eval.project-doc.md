# audit-eval 完整项目文档

> **文档状态**：Draft v1
> **版本**：v0.1.1
> **作者**：Codex
> **创建日期**：2026-04-15
> **最后更新**：2026-04-15
> **文档目的**：把 `audit-eval` 子项目从“做点审计和回测”的宽泛理解收束为可立项、可拆分、可实现、可验收的正式项目，使其成为主项目中唯一负责 `audit_record` / `replay_record` 持久化、历史回放、回溯评估、第三层漂移告警和回测分析资产的审计与评估模块。

---

## 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| v0.1 | 2026-04-15 | 初稿 | Codex |
| v0.1.1 | 2026-04-15 | 补充 Evidently 三层分工硬边界并收紧 replay bundle 消费措辞 | Codex |

---

## 1. 一句话定义

`audit-eval` 是主项目中**唯一负责把主系统输出的 audit payload、LLM replay bundle、formal publish 快照引用和后验市场结果组织成 `audit_record`、`replay_record`、`retrospective_evaluation`、Evidently 评估报告和 `backtest_result` 等正式审计与分析资产**的模块，它以“回放是重现历史产物而不是重新请求当前模型”“在线运行时控制与离线评估产物严格分层”“所有评估都必须尊重点时点一致性与 manifest 语义”为不可协商约束。

它不是 formal recommendation 生成模块，也不是 LLM runtime。  
它不负责写 `feature_weight_multiplier`，不负责生成当轮 `world_state_snapshot` / `recommendation_snapshot`，也不直接调用 provider SDK。

---

## 2. 文档定位与核心问题

本文解决的问题不是“怎么记日志”，而是：

1. **正式审计闭环问题**：主项目要求 formal output 必须可审计、可回放、可追责，必须有一个长期模块统一接住 `audit_record` / `replay_record`，否则运行记录会散落在主系统、Dagster 和日志里。
2. **在线控制与离线评估分层问题**：Evidently、偏差评估、回测、审计回放都在“评估”语义下，但其中只有一部分会影响当轮运行，必须把运行时控制和评估产物分开，否则会造成 `main-core` 与 `audit-eval` 反向缠绕。
3. **历史重现问题**：回放必须回答“当时喂了什么、模型回了什么、正式对象指向哪组已发布快照、之后市场验证如何”，而不是用今天的 prompt 或模型重跑一次假装复现。

---

## 3. 术语表

| 术语 | 定义 | 备注 |
|------|------|------|
| Audit Record | 一次 formal cycle 的正式审计记录 | 属于 formal object |
| Replay Record | 支撑历史重现的正式回放记录 | 属于 formal object |
| Audit Payload | `main-core` 在 Phase 3 输出给本模块的业务审计载荷 | 包含 params、cost、L4 审计字段等 |
| Replay Bundle | `reasoner-runtime` 为单次 formal LLM 调用生成的回放字段集合 | 核心五字段固定，允许附加字段 |
| Retrospective Evaluation | 对历史判断做 T+1/T+5/T+20 后验偏差评估的分析资产 | 属于 analytical asset |
| Alert Score | `max(trend_deviation, risk_deviation)` | 驱动即时告警 |
| Learning Score | `trend × 0.6 + risk × 0.4` | 驱动经验沉淀 |
| Drift Report | 基于 Evidently 生成的漂移评估报告与告警产物 | analytical asset |
| Analytical Publish | 向 `analytical` namespace 写入版本化分析资产的过程 | 不走 formal Gate |
| Point-in-time Feature | 严格对应历史时点可见性的特征值 | 回测必需 |
| Manifest Snapshot Set | 由 `cycle_publish_manifest` 指定的一组已发布 formal snapshot | replay / 对账必须基于它读取 |

**规则**：
- 回放定义为**读取历史审计与正式快照**，不是重新请求当前模型
- `audit_record` / `replay_record` 属于 formal object，必须受 manifest 语义保护
- `retrospective_evaluation` / `drift_report` / `backtest_result` 属于 analytical asset，不进入 formal publish
- 在线运行时写 `feature_weight_multiplier` 归 `main-core`，不归 `audit-eval`
- `sanitized_input / raw_output / parsed_result` 的生成归 `reasoner-runtime`，本模块负责持久化与消费

---

## 4. 目标与非目标

### 4.1 项目目标

1. **持久化正式审计记录**：把 `audit_payload` 和 replay 相关字段落成 `audit_record` / `replay_record`。
2. **提供历史回放能力**：给定 `cycle_id + object_ref`，可重现当时的输入、输出、发布快照和执行上下文。
3. **实现多时域偏差评估**：对 L4 / L7 等历史判断做 T+1 / T+5 / T+20 回溯评估。
4. **沉淀评估摘要**：向 `main-core` 提供最近 20 天的 retrospective summary，服务 L6/L7 经验闭环。
5. **承接 Evidently 评估产物**：拥有漂移报告定义、阈值和第三层结构性告警规则，并输出 analytical 资产。
6. **提供回测分析能力**：通过 Alphalens 和 Backtrader 生成 point-in-time 合法的 `backtest_result`。
7. **守住边界**：让审计、回放、评估和回测集中在一个子项目里，而不侵入 `main-core` 的在线业务控制。

### 4.2 非目标

- **不生成 formal recommendation**：正式业务判断归 `main-core`，因为“谁对 recommendation 负责”不能被审计模块稀释。
- **不生成 formal `report` / `dashboard_snapshot`**：L8 中的正式报告与正式 dashboard 快照仍归 `main-core` 装配与发布，本模块只承接审计、回放和评估资产。
- **不拥有在线漂移控制逻辑**：写 `feature_weight_multiplier` 会影响当轮输出，属于 `main-core.l3_features`。
- **不生成 replay bundle 五字段**：`sanitized_input` / `input_hash` / `raw_output` / `parsed_result` / `output_hash` 的生成归 `reasoner-runtime`。
- **不定义存储路径和 manifest 表结构**：namespace、分区和底层 Formal / Analytical 表约定归 `data-platform`。
- **不定义 Dagster 编排策略**：何时触发写入、回填、回放任务和 dashboard 刷新归 `orchestrator`。
- **不直接调用当前模型做“回放”**：回放如果重新请求模型，就失去了审计含义。

---

## 5. 与现有工具的关系定位

### 5.1 架构位置

```text
main-core publish bundle + reasoner-runtime replay bundle + formal snapshots
  -> audit-eval
      ├── audit_record
      ├── replay_record
      ├── retrospective_evaluation
      ├── drift_report / evidently report
      ├── backtest_result
      ├── replay query
      └── retrospective summary / dashboards
  -> consumers
      ├── analysts / reviewers
      ├── main-core
      ├── orchestrator
      ├── assembly
      └── future dashboards
```

### 5.2 上游输入

| 来源 | 提供内容 | 说明 |
|------|----------|------|
| `main-core` | `audit_payload`、`retrospective_seed`、formal object refs | Phase 3 在线输出 |
| `reasoner-runtime` | replay bundle、`llm_lineage`、cost / latency / reliability metrics | 通过调用方传递给本模块 |
| `data-platform` | `cycle_publish_manifest`、formal / analytical 读取语义、历史特征和行情 | 本模块按 manifest 语义读取 |
| `graph-engine` | `graph_snapshot` / `graph_impact_snapshot` refs、graph status 历史 | 回放与 retrospective 需要 |
| `orchestrator` | Dagster run history、任务触发、AssetCheck 结果 | 执行过程审计链的一部分 |
| `entity-registry` | `entity_reference` / `resolution_case` 审计链 | 实体解析回放与复核可读消费 |
| `assembly` | Streamlit / Superset / 本地配置 | 部署和环境注入 |

### 5.3 下游输出

| 目标 | 输出内容 | 消费方式 |
|------|----------|----------|
| 分析师 / reviewer | replay 查询结果、偏差摘要、回测报告 | UI / DuckDB / Python API |
| `main-core` | retrospective summary、长期告警摘要 | Python API / 表读取 |
| `orchestrator` | drift alert、retrospective alert、回填完成状态 | AssetCheck / 状态读取 |
| `assembly` | 审计与评估 dashboard 配置入口 | 配置 + app wiring |
| 外部展示层 | `backtest_result`、`retrospective_evaluation`、drift reports | analytical reads |

### 5.4 核心边界

- **`audit_record` / `replay_record` 的正式写入只归 `audit-eval`**
- **正式 `report` / `dashboard_snapshot` 仍归 `main-core`，`audit-eval` 只消费它们的历史快照做回放与评估**
- **回放必须基于历史 `audit_record` + manifest snapshot set + Dagster run history，不允许重调当前模型**
- **Evidently 的第三层结构性告警与报告定义归 `audit-eval`，但当轮 `feature_weight_multiplier` 写入不归它**
- **Evidently 三层分工固定为：第一层预处理归 `data-platform`，第二层在线 multiplier 写回归 `main-core.l3_features`，第三层结构性告警归 `audit-eval`**
- **`audit-eval` 消费 formal objects 和历史特征，但不生成 formal recommendation**
- **回测只能使用 point-in-time 特征，不能读取未来值**

---

## 6. 设计哲学

### 6.1 设计原则

#### 原则 1：Record What Actually Happened

审计系统记录的是“系统真实做了什么”，不是“事后觉得应该怎么表达”。  
因此 `audit_record` 必须直接持久化真实 params、真实 lineage、真实输出和真实失败/降级痕迹。

#### 原则 2：Replay Means Reconstruct, Not Re-run

如果回放重新请求今天的模型，得到的只会是“新的猜测”，不是历史产物。  
所以 replay 的核心是读取历史 `sanitized_input`、`raw_output`、`parsed_result`、manifest 快照和 run history，做重建与解释。

#### 原则 3：Online Control and Offline Evaluation Must Split

凡是会改写当轮运行结果的逻辑，都不应藏在评估模块里。  
`audit-eval` 可以检测、解释、告警，但不能写入当轮业务控制字段。

#### 原则 4：Manifest-first Audit

凡是读取 formal object 做回放或评估，都必须先经过 `cycle_publish_manifest`。  
直接读表 head 会把半提交数据、后续覆盖数据和历史发布数据混在一起。

#### 原则 5：Point-in-time or It Did Not Happen

回测和 retrospective 都不能偷看未来。  
任何不保证时点一致性的分析产物，即使看起来很漂亮，也不具备工程价值。

### 6.2 反模式清单

| 反模式 | 为什么危险 |
|--------|-----------|
| 用当前 prompt / 当前模型做“回放” | 历史重现失真，无法追责 |
| 审计模块直接写 `feature_weight_multiplier` | 评估模块侵入当轮业务控制 |
| retrospective 直接读 formal 表 head | 会读到错误版本，回放与评估结果失真 |
| 回测读取未来可见特征 | look-ahead bias，结果不可用 |
| 在 `audit-eval` 中复制 provider 调用逻辑 | 会和 `reasoner-runtime` 形成第二套 LLM runtime |
| 把 drift report、retrospective、backtest 散落在不同项目 | 长期评估链路无法形成统一资产层 |

---

## 7. 用户与消费方

### 7.1 直接消费方

| 消费方 | 消费内容 | 用途 |
|--------|----------|------|
| 分析师 / reviewer | replay、偏差摘要、回测报告 | 复盘、追责、校正 |
| `main-core` | retrospective summary、长期 drift / bias 摘要 | 经验沉淀与上下文输入 |
| `orchestrator` | 告警状态、回填状态 | 调度与 Gate 辅助 |
| 运维 / 值班人员 | Dagster run history 对照、graph status 对照 | 故障排查 |

### 7.2 间接用户

| 角色 | 关注点 |
|------|--------|
| 主编 / 架构 owner | formal 输出是否可审计、可回放 |
| 自动化代理 | 是否有稳定的回放、评估与分析接口可读写 |
| dashboard 使用者 | 偏差趋势、hit_rate_rel、drift 告警是否可见 |

---

## 8. 总体系统结构

### 8.1 Phase 3 审计持久化主线

```text
main-core publish bundle
  -> extract audit_payload + retrospective_seed
  -> write audit_record
  -> materialize replay_record
  -> return formal table snapshot refs
  -> join cycle_publish_manifest visibility
```

### 8.2 Replay 主线

```text
cycle_id + object_ref
  -> read replay_record
  -> load audit_record + manifest snapshot set
  -> load historical formal objects / graph refs / run history
  -> reconstruct historical artifact
  -> return replay view
```

### 8.3 Retrospective 主线

```text
retrospective_seed + future market outcome
  -> compute trend_deviation / risk_deviation
  -> derive alert_score / learning_score
  -> write retrospective_evaluation
  -> aggregate multi-day summary
  -> emit alert if thresholds hit
```

### 8.4 Drift 与回测主线

```text
historical feature windows
  -> run Evidently report
  -> write drift_report to analytical namespace

historical formal objects + point-in-time features
  -> run Alphalens / optional Backtrader
  -> write backtest_result
```

---

## 9. 领域对象设计

### 9.1 持久层对象

| 对象名 | 职责 | 归属 |
|--------|------|------|
| AuditRecord | 正式审计记录 | Formal Zone |
| ReplayRecord | 正式回放索引 / 还原记录 | Formal Zone |
| RetrospectiveEvaluation | 多时域偏差评估结果 | Analytical Zone |
| DriftReport | Evidently 报告与长期告警结果 | Analytical Zone |
| BacktestResult | 信号质量 / 策略模拟结果 | Analytical Zone |
| RetrospectiveSummary | 多日聚合评估摘要 | Analytical Zone / current view |

### 9.2 运行时对象

| 对象名 | 职责 | 生命周期 |
|--------|------|----------|
| AuditWriteBundle | 一次写 `audit_record` / `replay_record` 的输入包 | 单次 Phase 3 期间 |
| ReplayRequest | 一次历史回放请求 | 单次查询期间 |
| ReplayView | 回放结果的内存表示 | 单次查询期间 |
| RetrospectiveJob | 一次 T+1 / T+5 / T+20 回填任务 | 单次回填期间 |
| BacktestJob | 一次回测执行任务 | 单次离线任务期间 |

### 9.3 核心对象详细设计

#### AuditRecord

**角色**：记录一次 formal cycle 中真实发生的业务参数、LLM lineage、成本、降级和输出痕迹。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| record_id | String | 唯一标识 |
| cycle_id | String | 所属 cycle |
| layer | String | `L3` / `L4` / `L5` / `L6` / `L7` / `L8` |
| object_ref | String | 如 `world_state` / `ticker` / `recommendation_id` |
| params_snapshot | JSON | 业务参数快照 |
| llm_lineage | JSON | provider / model / fallback_path / retry_count |
| llm_cost | JSON | token / cost / latency / reliability_metrics |
| sanitized_input | Text \| Null | 脱敏后的完整输入 |
| input_hash | String \| Null | `sha256(sanitized_input)` |
| raw_output | Text \| Null | LLM 原始输出 |
| parsed_result | JSON \| Null | Instructor 解析后的结构 |
| output_hash | String \| Null | `sha256(raw_output)` |
| degradation_flags | JSON | Gate 降级、失败、repair 信息 |
| created_at | Timestamp | 写入时间 |

#### ReplayRecord

**角色**：描述如何从历史记录和已发布快照重建某个对象或某次判断。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| replay_id | String | 唯一标识 |
| cycle_id | String | 所属 cycle |
| object_ref | String | 回放对象 |
| audit_record_ids | Array[String] | 相关审计记录引用 |
| manifest_cycle_id | String | 对应 `cycle_publish_manifest` |
| formal_snapshot_refs | JSON | 各 formal 表 snapshot refs |
| graph_snapshot_ref | String \| Null | 关联图快照 |
| dagster_run_id | String | 对应 run history |
| replay_mode | String | 固定为 `read_history` |
| created_at | Timestamp | 写入时间 |

#### RetrospectiveEvaluation

**角色**：对历史判断做后验偏差计算的分析资产。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| evaluation_id | String | 唯一标识 |
| cycle_id | String | 被评估 cycle |
| object_ref | String | 被评估对象 |
| horizon | String | `T+1` / `T+5` / `T+20` |
| trend_deviation | Number | 趋势偏差 |
| risk_deviation | Number | 风险偏差 |
| alert_score | Number | `max(trend_deviation, risk_deviation)` |
| learning_score | Number | `trend × 0.6 + risk × 0.4` |
| deviation_level | Integer | 0-4 |
| hit_rate_rel | Number \| Null | 相对基准命中率 |
| baseline_vs_llm_breakdown | JSON | 规则基线 vs LLM 修正拆分 |
| evaluated_at | Timestamp | 计算时间 |

#### DriftReport

**角色**：记录一轮特征漂移检测与结构性变化告警结果。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| report_id | String | 唯一标识 |
| cycle_id | String \| Null | 若与日频 cycle 对齐则记录 |
| baseline_ref | String | 参考窗口 |
| target_ref | String | 目标窗口 |
| evidently_json_ref | String | 报告 JSON 位置 |
| drifted_features | JSON | 漂移特征清单 |
| regime_warning_level | String | `none` / `warning` / `critical` |
| alert_rules_version | String | 告警规则版本 |
| created_at | Timestamp | 产出时间 |

#### BacktestResult

**角色**：记录一次离线回测或信号质量评估结果。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| backtest_id | String | 唯一标识 |
| job_ref | String | 回测任务标识 |
| engine | String | `alphalens` / `backtrader` |
| feature_ref | String | 使用的点时点特征版本 |
| formal_snapshot_range | JSON | 读取的 formal 历史范围 |
| metrics | JSON | IC、分组收益、衰减等结果 |
| pit_check_passed | Boolean | 是否通过 point-in-time 检查 |
| created_at | Timestamp | 写入时间 |

---

## 10. 数据模型设计

### 10.1 模型分层策略

- `audit_record` / `replay_record` -> Formal Zone，受 manifest 可见性保护
- `retrospective_evaluation` / `drift_report` / `backtest_result` -> Analytical Zone
- `RetrospectiveSummary` -> Analytical 聚合视图或当前态表
- Dagster run history / graph status / manifest -> 外部读取，不在本模块重复建真相

### 10.2 存储方案

| 存储用途 | 技术选型 | 理由 |
|----------|----------|------|
| 正式审计记录 | Iceberg formal tables | 版本化、time travel、受 manifest 约束 |
| 分析评估资产 | Iceberg analytical tables | 版本化分析产物 |
| 当前态摘要 / 告警状态 | PostgreSQL 或 analytical current view | 便于 dashboard / orchestration 读取 |
| 快速审计查询 | DuckDB | 直读 Iceberg，Lite 模式足够 |
| Drift 评估 | Evidently JSON + Iceberg ref | 保留完整报告正文 |

### 10.3 关系模型

- `ReplayRecord.audit_record_ids -> AuditRecord.record_id`
- `ReplayRecord.manifest_cycle_id -> cycle_publish_manifest.published_cycle_id`
- `RetrospectiveEvaluation.cycle_id -> cycle_metadata.cycle_id`
- `AuditRecord.object_ref` 与 formal object 主键 / object_ref 对齐
- `BacktestResult.feature_ref` 必须指向 point-in-time 可验证的历史特征版本

---

## 11. 核心计算/算法设计

### 11.1 审计持久化算法

**输入**：`AuditWriteBundle`、manifest 候选信息、回放字段。

**输出**：`audit_record` 与 `replay_record`。

**处理流程**：

```text
read publish bundle
  -> normalize audit payload
  -> validate replay bundle fields exist when formal LLM call happened
  -> write audit_record rows
  -> build replay_record rows with manifest refs + run refs
  -> return written snapshot refs
```

**规则**：

- formal LLM 调用发生时，五字段缺一不可
- 审计记录的是实际发生的 fallback / retry，不是配置里的理想值
- `audit_record` / `replay_record` 都要受 manifest 语义约束

### 11.2 Replay 重建算法

**输入**：`cycle_id + object_ref` 或 `replay_id`。

**输出**：`ReplayView`。

**处理流程**：

```text
lookup replay_record
  -> load related audit_record rows
  -> load manifest snapshot set
  -> time travel read historical formal objects
  -> load graph snapshot refs if present
  -> load dagster run history summary
  -> reconstruct replay view
```

**规则**：

- 不重新请求模型
- 不读取 formal 表 head
- replay view 中要区分“模型原始输出”和“结构化解析结果”

### 11.3 Retrospective 评估算法

**输入**：`retrospective_seed`、未来市场真实结果、历史基准。

**输出**：`retrospective_evaluation`。

**处理流程**：

```text
load historical prediction seed
  -> load future realized market outcome
  -> compute trend_deviation / risk_deviation
  -> compute alert_score / learning_score
  -> assign deviation_level
  -> compute hit_rate_rel and baseline_vs_llm_breakdown
  -> write retrospective_evaluation
```

**主文档约束写死**：

- `alert_score = max(trend_deviation, risk_deviation)`
- `learning_score = trend × 0.6 + risk × 0.4`
- horizon 至少支持 `T+1` / `T+5` / `T+20`

### 11.4 累积告警算法

**输入**：最近 N 天 `retrospective_evaluation`。

**输出**：warning / critical / emergency 告警。

**处理流程**：

```text
load recent T+1 alert_score history
  -> count consecutive / rolling threshold breaches
  -> combine with L7 hit_rate_rel when needed
  -> emit warning / critical / emergency
  -> persist alert summary
```

**主文档阈值写死**：

- 连续 3 天 `alert_score >= 2` -> `WARNING`
- 连续 3 天 `alert_score >= 3` 或最近 5 天 4 天 `>= 2` -> `CRITICAL`
- 连续 5 天 `>= 2` 或连续 3 天 `>= 3` 且 `L7 hit_rate_rel < 35%` -> `EMERGENCY`

### 11.5 Drift 报告算法

**输入**：历史特征窗口、参考窗口、Evidently 配置。

**输出**：`drift_report` 和 regime warning。

**处理流程**：

```text
read reference window + current window
  -> run Evidently profile / report
  -> classify drifted features
  -> apply rule thresholds
  -> write JSON report ref
  -> emit structural warning only
```

**边界**：

- 这里只做第三层结构性告警，不直接生效当轮权重调整
- 任何试图写 `feature_weight_multiplier` 或其他当轮控制字段的 drift job 都应 fail-fast
- 报告 JSON 的写路径归 `data-platform` analytical namespace
- 报告内容定义、阈值、长期告警规则归 `audit-eval`

### 11.6 回测算法

**输入**：历史 formal objects、point-in-time features、历史行情。

**输出**：`backtest_result`。

**处理流程**：

```text
select historical time range
  -> validate point-in-time feature availability
  -> run Alphalens IC / group return / decay
  -> optionally run Backtrader strategy simulation
  -> write analytical asset
```

**规则**：

- 回测不在日频 cycle 内执行
- point-in-time 检查未通过时，结果不得发布为正式 backtest_result
- NautilusTrader 属于后续按需扩展，不作为当前子项目前提

---

## 12. 触发/驱动引擎设计

### 12.1 触发源类型

| 类型 | 来源 | 示例 |
|------|------|------|
| Phase 3 写入触发 | `orchestrator` / `main-core` | 写 `audit_record` / `replay_record` |
| 延迟回填触发 | `orchestrator` | T+1 / T+5 / T+20 retrospective 回填 |
| 周期评估触发 | 定时任务 | Drift report 计算 |
| 手动查询触发 | 分析师 / reviewer | replay 查询 |
| 离线研究触发 | 人工 / 定时 | Alphalens / Backtrader 回测 |

### 12.2 关键触发流程

```text
phase_3_audit_write()
  -> persist_audit_records()
  -> persist_replay_records()
  -> emit retrospective jobs
```

### 12.3 启动顺序基线

| 阶段 | 动作 | 说明 |
|------|------|------|
| P1-P2 | `data-platform` 先提供 manifest 语义、formal / analytical 读写位点 | 审计与回放都依赖正确快照读取 |
| P2 | `reasoner-runtime` 先产出 replay bundle 五字段 | 没有历史输入/输出就谈不上 replay |
| P2c | `audit-eval` 打通 `audit_record` / `replay_record` / T+1 retrospective 骨架 | 先建在线审计闭环 |
| P5 | 增补多时域 retrospective、Evidently 结构性告警和 dashboard | 形成长期评估闭环 |
| P10 | 增补回测骨架与长期研究接口 | 离线分析增强 |

---

## 13. 输出产物设计

### 13.1 Audit Record

**面向**：审计、追责、回放入口

**结构**：

```text
{
  cycle_id: String
  layer: String
  object_ref: String
  params_snapshot: Object
  llm_lineage: Object
  llm_cost: Object
  sanitized_input: String | null
  raw_output: String | null
  parsed_result: Object | null
}
```

### 13.2 Replay View

**面向**：分析师、reviewer

**结构**：

```text
{
  cycle_id: String
  object_ref: String
  manifest_snapshot_set: Object
  audit_records: Array[Object]
  historical_formal_objects: Object
  dagster_run_summary: Object
}
```

### 13.3 Retrospective Summary

**面向**：`main-core`、dashboard

**结构**：

```text
{
  date_window: String
  composite_learning_score_mean: Number
  trend: Number
  baseline_vs_llm_breakdown: Object
  l7_hit_rate_rel_trend: Number
  alert_state: String
}
```

### 13.4 Drift Alert Payload

**面向**：`orchestrator`、分析师

**结构**：

```text
{
  report_id: String
  regime_warning_level: String
  drifted_features: Array[String]
  evidently_json_ref: String
}
```

### 13.5 Backtest Result

**面向**：研究、回顾分析

**结构**：

```text
{
  backtest_id: String
  engine: String
  metrics: Object
  pit_check_passed: Boolean
  formal_snapshot_range: Object
}
```

---

## 14. 系统模块拆分

**组织模式**：单个 Python 项目，内部按在线审计、后验评估、离线回测三层分 package。

| 模块名 | 语言 | 运行位置 | 职责 |
|--------|------|----------|------|
| `audit_eval.audit` | Python | 库 | `audit_record` / `replay_record` 写入与读取 |
| `audit_eval.retro` | Python + dbt | 库 | `retrospective_evaluation`、摘要、累积告警 |
| `audit_eval.drift` | Python | 库 | Evidently 报告定义、阈值、第三层结构性告警 |
| `audit_eval.backtest` | Python | 库 | Alphalens / Backtrader 回测 |
| `audit_eval.ui` | Python | 应用 / 库 | Streamlit dashboard、查询界面 |

**关键设计决策**：

- `audit_record` / `replay_record` 与 `retrospective` / `backtest` 放在一个项目里，但内部包边界必须清楚
- 在线写入与离线分析同属一个 owner，因为它们共享 manifest、time travel、replay 和长期评估语义
- `feature_weight_multiplier` 运行时写入不进入本项目
- 如果 P10 之后真的引入 NautilusTrader 或多策略研究平台，再考虑把回测拆成独立项目；当前先保留在 `audit-eval`

---

## 15. 存储与技术路线

| 用途 | 技术选型 | 理由 |
|------|----------|------|
| 正式审计表 | Iceberg formal tables | 与 manifest 语义对齐 |
| 分析评估表 | Iceberg analytical tables | 版本化 + time travel |
| 查询 / 回放 | DuckDB | Lite 模式直接读 Iceberg 方便 |
| 回溯评估计算 | dbt + DuckDB | T+1 / T+5 / T+20 回填适合 SQL / 批式 |
| 漂移评估 | Evidently | 报告化输出成熟 |
| 回测 | Alphalens + Backtrader | P10 当前主线组合 |
| Lite dashboard | Streamlit | 快速交付、依赖轻 |
| Full dashboard | Superset | P6+ 生产化展示 |

最低要求：

- 能读取 `cycle_publish_manifest`
- 能 time travel 读取 formal / analytical 历史版本
- 能接到 `main-core` 输出的 `audit_payload` / `retrospective_seed`
- 能消费 `reasoner-runtime` 生成的 replay bundle

---

## 16. API 与接口合同

### 16.1 Python 接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `persist_audit_records(write_bundle)` | 写正式审计记录 | `AuditWriteBundle` |
| `persist_replay_records(write_bundle)` | 写正式回放记录 | `AuditWriteBundle` |
| `replay_cycle_object(cycle_id, object_ref)` | 回放指定对象 | `cycle_id`、`object_ref` |
| `compute_retrospective(horizon, date_ref)` | 计算指定时域偏差 | `horizon`、日期 |
| `build_retrospective_summary(window)` | 生成摘要 | 时间窗口 |
| `run_drift_report(reference_ref, target_ref)` | 生成漂移报告 | 参考窗口、目标窗口 |
| `run_backtest(job_config)` | 执行回测 | 回测配置 |

### 16.2 协议接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `AuditRecordSchema` | 正式审计对象 schema | 由 `contracts` 定义 |
| `ReplayRecordSchema` | 正式回放对象 schema | 由 `contracts` 定义 |
| `RetrospectiveEvaluationSchema` | retrospective 对象 schema | 由 `contracts` 定义 |
| `BacktestResultSchema` | backtest 结果 schema | 由 `contracts` 定义 |
| `DriftReportSchema` | drift 报告 schema | 由 `contracts` 定义 |

### 16.3 版本与兼容策略

- `audit_record` 的 replay 五字段名和语义必须与 `contracts` 完全一致
- `replay_record` 的语义必须始终是 `read_history`，不能悄悄演变成“重跑当前模型”
- `retrospective_summary` 的字段应稳定，供 `main-core` 长期读取
- drift alert 规则版本要显式记录，便于历史解释
- `run_drift_report()` 只能生成第三层结构性告警，不得写在线控制字段；报告 JSON 写路径归 `data-platform`

---

## 18. 测试与验证策略

### 18.1 单元测试

- `audit_record` 五字段校验测试
- replay 读取不触发模型调用测试
- `alert_score` / `learning_score` 公式测试
- drift report 阈值判断测试
- point-in-time feature 检查测试

### 18.2 集成测试

| 场景 | 验证目标 |
|------|----------|
| Phase 3 写 `audit_record` / `replay_record` | 验证 formal 审计闭环 |
| `cycle_id + object_ref` 历史回放 | 验证 replay 语义与 manifest 读取 |
| T+1 / T+5 / T+20 回填 | 验证 retrospective 多时域闭环 |
| Evidently 报告生成并入 analytical | 验证 drift 报告路径 |
| Alphalens 回测一次完成 | 验证离线 backtest 主干 |

### 18.3 协议 / 契约测试

- `audit_record` / `replay_record` / `retrospective_evaluation` schema 与 `contracts` 对齐
- replay 读取 formal object 时必须先查 `cycle_publish_manifest`
- replay bundle 字段来源于 `reasoner-runtime`，本模块不自造第二套字段

### 18.4 回归与质量测试

- `feature_weight_multiplier` 不被本模块写入的边界测试
- drift report 只做告警不改当轮业务状态的边界测试
- Backtest 读未来值的 look-ahead bias 防护测试
- Dagster run history 缺失时 replay 降级展示但不伪造执行链测试

---

## 19. 关键评价指标

### 19.1 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 单次 replay 查询耗时 | `< 5 秒` | Lite 模式典型单对象 |
| T+1 retrospective 日常回填耗时 | `< 10 分钟` | 单日批量 |
| Drift report 单次生成耗时 | `< 5 分钟` | 日频窗口 |
| Alphalens 单任务耗时 | `< 30 分钟` | 典型研究窗口 |

### 19.2 质量指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| formal LLM 调用 replay 字段缺失率 | `0` | 审计链不能断 |
| replay 错读非 manifest 版本发生率 | `0` | 历史重现必须精确 |
| retrospective 多时域回填完成率 | `100%` | T+1 / T+5 / T+20 都要补齐 |
| drift 告警误写在线控制字段次数 | `0` | 边界必须守住 |
| backtest point-in-time 检查通过前发布次数 | `0` | 不允许脏结果入库 |

---

## 20. 项目交付物清单

### 20.1 正式审计能力

- `audit_record`
- `replay_record`
- replay 查询接口
- 审计 dashboard 基础页

### 20.2 后验评估能力

- `retrospective_evaluation`
- retrospective summary
- 累积告警逻辑
- drift report / Evidently 报告定义

### 20.3 离线分析能力

- `backtest_result`
- Alphalens 集成
- Backtrader 可选集成
- point-in-time 检查器

---

## 21. 实施路线图

### 阶段 0：Replay 格式与 manifest 对账 Spike（2-3 天）

**阶段目标**：先把 replay 语义和正式快照读取验证清楚。

**交付**：
- replay 字段样例
- manifest 对账脚本
- 历史重建演示脚本

**退出条件**：给定一个 sample cycle，能不调用模型完成 replay 重建。

### 阶段 1：P2c 在线审计闭环（3-5 天）

**阶段目标**：打通 `audit_record` / `replay_record` 正式写入。

**交付**：
- 审计写入接口
- 回放记录接口
- 基础查询接口

**退出条件**：一轮 formal cycle 能稳定留下完整审计与回放记录。

### 阶段 2：P2c 基础 retrospective（3-5 天）

**阶段目标**：先做 T+1 偏差计算和摘要。

**交付**：
- `retrospective_evaluation` T+1
- retrospective summary
- 基础 dashboard 视图

**退出条件**：最近若干 cycle 能看见可解释的偏差曲线和摘要。

### 阶段 3：P5 多时域评估与 drift（4-6 天）

**阶段目标**：补齐 T+5 / T+20 回填、累积告警和 Evidently 第三层告警。

**交付**：
- T+5 / T+20 回填
- warning / critical / emergency 告警
- drift report

**退出条件**：长期评估闭环形成，drift 规则可稳定输出 analytical 资产。

### 阶段 4：P10 回测能力（4-7 天）

**阶段目标**：补齐 Alphalens 和可选 Backtrader。

**交付**：
- point-in-time 检查器
- `backtest_result`
- 回测任务入口

**退出条件**：至少一种历史信号可产出可解释的信号质量报告。

---

## 22. 主要风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| replay 被实现成重新调模型 | 历史重现失真 | 把 `read_history` 语义写入合同与回归测试 |
| manifest 读取被绕开 | 正式历史错位 | 所有 replay / retrospective 先查 manifest |
| drift 逻辑侵入在线控制 | 主系统边界失效 | 明确 `feature_weight_multiplier` 不归本模块 |
| retrospective 使用错误未来窗口 | 评估失真 | 固定 horizon 规则与时间窗口校验 |
| 回测存在 look-ahead bias | 分析结果无效 | point-in-time 检查为硬前置 |
| 审计资产过大查询过慢 | 分析效率下降 | 建立摘要表、DuckDB 查询模板和必要索引 |

---

## 23. 验收标准

项目完成的最低标准：

1. `audit-eval` 能把 `main-core` 输出的 `audit_payload` 与 replay bundle 持久化为 `audit_record` / `replay_record`
2. 给定 `cycle_id + object_ref`，系统能在不调用当前模型的前提下完成历史 replay
3. `retrospective_evaluation` 至少支持 `T+1` / `T+5` / `T+20` 三个 horizon，并能产出 `alert_score` / `learning_score`
4. Evidently 第三层结构性告警和报告定义由本模块拥有，但不会写在线业务控制字段
5. `backtest_result` 只能在 point-in-time 检查通过后写入 analytical 资产
6. `audit-eval` 不拥有 formal recommendation 逻辑，也不拥有 replay bundle 生成逻辑
7. 文档中定义的 OWN / BAN / EDGE 与主项目 `12 + N` 模块边界一致

---

## 24. 一句话结论

`audit-eval` 子项目不是“顺手记一下日志”的附属层，而是主项目里唯一负责把正式运行痕迹、历史判断质量和长期经验沉淀组织成可审计、可回放、可评估资产的 owner。  
它如果边界不稳，后面所有“为什么当时这么判断、后来证明对不对、应该怎样调整”都会失去可信答案。

---

## 25. 自动化开发对接

### 25.1 自动化输入契约

| 项 | 规则 |
|----|------|
| `module_id` | `audit-eval` |
| 脚本先读章节 | `§1` `§4` `§5.2` `§5.4` `§8` `§11` `§14` `§16` `§18` `§21` `§23` |
| 默认 issue 粒度 | 一次只实现 audit / replay / retrospective / drift / backtest 五类能力中的一类 |
| 默认写入范围 | 当前 repo 的 `audit_eval.*` 包、dbt / 评估逻辑、测试、dashboard 视图、文档和本模块配置 |
| 内部命名基线 | 以 `§14` 的内部包名和 `§9` / `§13` 的对象名为准 |
| 禁止越界 | 不写在线控制字段、不把 replay 实现成重调当前模型、不读取未来可见特征 |
| 完成判定 | 同时满足 `§18`、`§21` 当前阶段退出条件和 `§23` 对应条目 |

### 25.2 推荐自动化任务顺序

1. 先落 `audit_record` / `replay_record` 和 manifest-based replay 主干
2. 再落 `T+1` retrospective 与 summary
3. 再落 Evidently 第三层结构性告警与长期 drift 资产
4. 最后按 `P10` 后置补 `backtest_result` 和研究接口

补充规则：

- 单个 issue 默认只做一类评估能力，不把 replay、drift、backtest 混在一起
- 在 replay / manifest 路径未稳定前，不进入 backtest 或 dashboard 强化

### 25.3 Blocker 升级条件

- 任何 drift / retrospective 任务试图写 `feature_weight_multiplier` 或其他在线控制字段
- replay 需要重新请求当前模型才能完成
- backtest 无 point-in-time 检查或需要读取未来可见值
- 需要在 `P10` 之前引入 NautilusTrader 或第二套研究平台
