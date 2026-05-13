# reasoner-runtime 完整项目文档

> **文档状态**：Draft v1
> **版本**：v0.1.2
> **作者**：Codex
> **创建日期**：2026-04-15
> **最后更新**：2026-04-15
> **文档目的**：把 `reasoner-runtime` 子项目从“封装一下 LiteLLM”这种过窄理解收束为可立项、可拆分、可实现、可验收的正式项目，使其成为主项目中唯一负责 LLM 调用运行时、结构化输出校验、PII scrub、fallback/retry、可观测与回放字段生成的横切基础能力。

---

## 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| v0.1 | 2026-04-15 | 初稿 | Codex |
| v0.1.1 | 2026-04-15 | 收紧 replay bundle 五字段措辞并显式点名 `litellm` / `instructor` 供应链锁定范围 | Codex |
| v0.1.2 | 2026-04-15 | 把 `max_retries` 显式收进 client 构建接口约束 | Codex |

---

## 1. 一句话定义

`reasoner-runtime` 是主项目中**唯一负责把一次 LLM 调用做成统一接口、结构化输出、可回退、可观测、可审计和可复现**的运行时模块，它以“LLM 是增强器而不是 formal owner”和“调用运行时与业务 prompt/业务判断严格分离”为不可协商约束。

它不是选股模块，不是 analyzer 模块，也不是审计落库模块。  
它不决定为什么调用 LLM、不决定用结果做什么，也不直接写 Iceberg 或 Dagster event log。

---

## 2. 文档定位与核心问题

本文解决的问题不是“怎么接一个模型 SDK”，而是：

1. **统一调用入口问题**：如果 `main-core`、`entity-registry`、子系统各自直连 provider，fallback、成本追踪、回放字段和故障语义会立刻漂移。
2. **结构化输出与审计闭环问题**：主项目要求 formal LLM 调用必须保留 `sanitized_input / raw_output / parsed_result` 等回放字段，必须有单一模块负责生成这些运行时产物。
3. **运行时与业务边界问题**：prompt 模板、analyzer 策略、L4/L6/L7 业务判断必须留在调用方，不能被 `reasoner-runtime` 吞进去变成隐形业务层。

---

## 3. 术语表

| 术语 | 定义 | 备注 |
|------|------|------|
| Reasoner Request | 一次标准化 LLM 调用请求 | 包含 prompt/messages、目标 schema、provider 偏好等 |
| Structured Generation | 通过 LiteLLM + Instructor 生成结构化结果的调用路径 | 本模块主流程 |
| Replay Bundle | 一次调用生成的回放字段集合 | 核心五字段固定为 `sanitized_input`、`input_hash`、`raw_output`、`parsed_result`、`output_hash`，允许附加字段 |
| LLM Lineage | 一次调用实际使用的 provider / model / fallback_path / retry_count | 审计必录 |
| Provider Profile | 一个可被路由的 provider/model 配置 | 含超时、速率、fallback 优先级 |
| PII Scrub Handler | 在外发前统一脱敏的处理器 | 至少覆盖姓名 / 手机 / 账户三类 |
| Health Check | 对 provider/model 可用性、延迟、配额状态的主动探测 | Phase 0 末尾由 `orchestrator` 触发 |
| Task-level Failure | 单次业务调用失败但 LLM 基础设施仍可用 | 如单股票格式错误 |
| Infra-level Failure | fallback 链全部失败或无可用 provider | 必须硬停相关下游链路 |
| Callback Backend | OTEL / Langfuse 等观测回调后端 | 不改变对外调用接口 |

**规则**：
- `reasoner-runtime` 只生成运行时产物，不定义业务 prompt 语义
- 回放字段的内容格式必须与 `contracts` 保持一致
- `llm_health_check` 的触发归 `orchestrator`，实现能力归 `reasoner-runtime`

---

## 4. 目标与非目标

### 4.1 项目目标

1. **统一 LLM 调用**：提供所有业务模块共享的 `generate_structured()` 入口，屏蔽底层 provider 差异。
2. **保证结构化输出**：通过 Instructor 强制将模型输出校验为 Pydantic/contract 定义的结构化对象。
3. **生成回放字段**：生成 `sanitized_input`、`input_hash`、`raw_output`、`parsed_result`、`output_hash` 与 `llm_lineage`。
4. **管理 fallback/retry**：统一处理 provider 路由、重试、失败分类和基础设施级硬停语义。
5. **提供健康探测能力**：对每个 provider/model 组合执行可调用性和延迟探测。
6. **补齐最小观测层**：通过 LiteLLM callbacks / OTEL 记录 request_id、token、cost、latency、error 等最小可用观测数据。
7. **落实供应链约束**：至少对 `litellm`、`instructor` 两个关键 Python 包执行版本号 + SHA-256 hash 锁定，其它直接安全相关依赖按同一规则扩展。

### 4.2 非目标

- **不写业务 prompt**：prompt 模板、领域上下文拼装、L4/L6/L7 业务语义归调用方，因为这些属于业务逻辑而非运行时。
- **不实现 analyzer**：`SinglePromptAnalyzer`、`MultiAgentAnalyzer`、解析式消歧流程归 `main-core` 或 `entity-registry`，因为运行时只负责调用基础设施。
- **不直接持久化审计记录**：Iceberg / PostgreSQL 写入由调用方或 `audit-eval` 完成，因为运行时模块不拥有存储边界。
- **不拥有 Dagster resource 注入**：Dagster resource 的装配与生命周期归 `orchestrator`，本模块只提供 client/factory/interface。
- **不定义共享 schema**：输出对象 schema、错误枚举和审计字段定义归 `contracts`。

---

## 5. 与现有工具的关系定位

### 5.1 架构位置

```text
contracts + provider config + caller prompt/schema
  -> reasoner-runtime
      ├── LiteLLM routing
      ├── Instructor structured parsing
      ├── PII scrub
      ├── fallback / retry
      ├── OTEL / callbacks
      └── replay bundle generation
  -> caller modules
      ├── main-core
      ├── entity-registry
      ├── subsystem-*
      └── orchestrator (health check / resource wrapping)
```

### 5.2 上游输入

| 来源 | 提供内容 | 说明 |
|------|----------|------|
| `contracts` | 响应 schema、错误分类、审计字段定义 | 本模块不能自定义第二套结构化输出协议 |
| `main-core` | prompt/messages、业务上下文、目标 schema、调用参数 | 业务语义由调用方负责 |
| `entity-registry` | 消歧 prompt、候选实体上下文、目标 schema | 用于 LLM 辅助消歧 |
| `subsystem-*` | 抽取 / 分类场景的 prompt 与目标 schema | 仅在需要 LLM 的子系统中消费 |
| `assembly` | API key、provider profile、环境配置 | 凭据和部署注入不归本模块定义 |
| `orchestrator` | health check 执行时机、resource 生命周期 | 触发与运行管理在编排层 |

### 5.3 下游输出

| 目标 | 输出内容 | 消费方式 |
|------|----------|----------|
| `main-core` | 结构化结果、`llm_lineage`、replay bundle、cost/latency | Python import |
| `entity-registry` | 消歧结果、replay bundle、失败分类 | Python import |
| `subsystem-*` | 抽取结果、重试/回退能力 | Python import |
| `orchestrator` | `health_check()`、client factory、运行状态接口 | Python import |
| `audit-eval` | 审计字段生成规则与产出对象 | 通过调用方传递 |

### 5.4 核心边界

- **本模块拥有“怎么调用 LLM”，不拥有“为什么调用 LLM”**
- **审计字段由本模块生成，但不由本模块写入存储**
- **Dagster resource 装配归 `orchestrator`，本模块只提供 client/factory**
- **Langfuse 如后续启用，只能作为 callback backend，不改变对外接口**
- **业务模块不得绕过 `reasoner-runtime` 直连 provider SDK**

---

## 6. 设计哲学

### 6.1 设计原则

#### 原则 1：Runtime-first, Prompt-later

先把统一调用、回退、审计、脱敏和可观测这套运行时打稳，再让不同业务模块自由写 prompt。  
如果每个业务模块自己拼一套 runtime，最终不会得到“灵活”，只会得到不可审计的漂移。

#### 原则 2：LLM Is an Enhancer

LLM 只能增强判断，不能替代 formal publish 的 deterministic owner。  
因此 `reasoner-runtime` 只返回调用结果和运行时元数据，绝不拥有最终业务决策权。

#### 原则 3：Auditability by Construction

`sanitized_input`、`raw_output`、`parsed_result` 不是补充信息，而是调用完成时的必需产物。  
回放能力必须内建在运行时生成流程中，而不是靠调用方事后拼凑。

#### 原则 4：Security Before Observability

任何观测、日志、回放都必须建立在统一 PII scrub 之后。  
如果脱敏链与外发链、落盘链不是同一套实现，合规边界很快会失守。

### 6.2 反模式清单

| 反模式 | 为什么危险 |
|--------|-----------|
| 业务模块直接调用 OpenAI / Anthropic / 其他 provider SDK | fallback、审计字段、成本追踪口径全部失控 |
| 在 `reasoner-runtime` 里 hard-code L4/L6/L7 prompt 模板 | 运行时侵入业务层，后续模块边界崩坏 |
| 只保存解析结果，不保存 `sanitized_input` / `raw_output` | 无法回放，审计链断裂 |
| PII scrub 与真正外发链不是同一函数 | 日志脱敏了，但真实请求仍可能含敏感信息 |
| 把 Langfuse / OTEL 绑定成必选接口 | 观测后端一变化就破坏所有调用方 |

---

## 7. 用户与消费方

### 7.1 直接消费方

| 消费方 | 消费内容 | 用途 |
|--------|----------|------|
| `main-core` | 结构化生成、fallback、replay bundle | L4/L6/L7 正式调用 |
| `entity-registry` | 消歧调用、失败分类、回放字段 | LLM 辅助实体解析 |
| `subsystem-*` | 抽取/分类调用入口 | 子系统需要 LLM 时统一走这里 |
| `orchestrator` | `health_check()`、client factory | Phase 0 健康探测与运行管理 |

### 7.2 间接用户

| 角色 | 关注点 |
|------|--------|
| reviewer | 是否仍有直连 provider SDK 的越界实现 |
| 审计/回放使用者 | 能否知道当时喂了什么、返回了什么 |
| 主编 / 架构 owner | LLM 故障是否有稳定的硬停/回退语义 |

---

## 8. 总体系统结构

### 8.1 结构化调用主线

```text
caller module
  -> compose prompt/messages + target schema
  -> reasoner-runtime request normalization
  -> PII scrub
  -> LiteLLM provider routing
  -> Instructor parse
  -> replay bundle + lineage + metrics
  -> caller persists / consumes result
```

### 8.2 健康探测主线

```text
orchestrator Phase 0
  -> health_check(provider_profiles)
  -> per provider/model probe
  -> aggregate availability / latency / quota state
  -> pass / fail phase gate
```

### 8.3 失败回退主线

```text
primary provider failure
  -> fallback chain retry
  -> structured parse retry
  -> success => return lineage with fallback_path
  -> all failed => classify infra/task failure
```

---

## 9. 领域对象设计

### 9.1 持久层对象

| 对象名 | 职责 | 归属 |
|--------|------|------|
| ProviderProfile | 描述 provider/model/timeout/fallback 优先级 | Git 跟踪配置 |
| ScrubRuleSet | 描述脱敏规则与开关 | Git 跟踪配置 |
| DependencyLockEntry | 记录 `litellm` / `instructor` 等依赖版本与 hash | `requirements.txt` / lock 文件 |
| CallbackProfile | 描述 OTEL / Langfuse 等 callback backend 配置 | Git 跟踪配置 |

### 9.2 运行时对象

| 对象名 | 职责 | 生命周期 |
|--------|------|----------|
| ReasonerRequest | 一次标准化调用请求 | 单次调用期间 |
| StructuredGenerationResult | 一次结构化调用的返回对象 | 单次调用期间 |
| ReplayBundle | 一次调用生成的回放字段集合 | 单次调用结束后可持久化 |
| ProviderHealthStatus | 某个 provider/model 的探测结果 | 单次健康检查期间 |
| FallbackDecision | 一次回退链选择结果 | 单次调用期间 |

### 9.3 核心对象详细设计

#### ReasonerRequest

**角色**：调用方向 `reasoner-runtime` 提交的一次标准化请求。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| request_id | String | 请求唯一标识 |
| caller_module | String | 如 `main-core`、`entity-registry` |
| target_schema | String | 目标结构化 schema 名称 |
| messages | Array[Object] | 渲染后的消息数组 |
| configured_provider | String | 业务期望 provider |
| configured_model | String | 业务期望 model |
| max_retries | Integer | 必须显式传入，推荐 `2` |
| metadata | JSON | 如 `cycle_id`、`ticker`、`analyzer_type` |

#### StructuredGenerationResult

**角色**：一次调用对业务层返回的统一结果对象。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| parsed_result | JSON | Instructor 解析后的结构化结果 |
| actual_provider | String | 实际调用的 provider |
| actual_model | String | 实际调用的 model |
| fallback_path | Array[String] | 经历过的回退路径 |
| retry_count | Integer | 实际重试次数 |
| token_usage | JSON | prompt/completion/total tokens |
| cost_estimate | Number | 估算成本 |
| latency_ms | Integer | 调用总耗时 |

#### ReplayBundle

**角色**：供调用方写入审计系统的运行时回放字段集合。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| sanitized_input | String | 脱敏后的完整输入 |
| input_hash | String | `sha256(sanitized_input)` |
| raw_output | String | 模型原始返回文本 |
| parsed_result | JSON | 结构化输出 |
| output_hash | String | `sha256(raw_output)` |
| llm_lineage | JSON | provider/model/fallback_path/retry_count |

#### ProviderHealthStatus

**角色**：单个 provider/model 组合的健康探测结果。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| provider | String | provider 名 |
| model | String | model 名 |
| reachable | Boolean | 是否可达 |
| latency_ms | Integer | 探测延迟 |
| quota_status | Enum | `ok` / `limited` / `exhausted` |
| error | String | 失败摘要 |

#### FallbackDecision

**角色**：一次调用在 provider 链上的路由选择记录。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| configured_target | String | 初始目标 provider/model |
| attempts | Array[String] | 尝试过的 provider/model 序列 |
| final_target | String | 最终成功调用目标 |
| failure_class | Enum | `none` / `task_level` / `infra_level` |
| terminal_reason | String | 最终结论说明 |

---

## 10. 数据模型设计

### 10.1 模型分层策略

- 运行配置与脱敏规则 → Git 跟踪配置文件
- 依赖供应链锁定 → `requirements.txt` / lock 文件
- 单次调用结果对象 → 内存对象，由调用方决定是否落盘
- 健康检查结果 → 内存对象，通常由 `orchestrator` 消费

### 10.2 存储方案

| 存储用途 | 技术选型 | 理由 |
|----------|----------|------|
| provider / scrub / callback 配置 | YAML/TOML + Git | 可审计、可回滚 |
| Python 依赖锁定 | `requirements.txt` + `--require-hashes` | 满足供应链安全约束 |
| 运行时对象 | Python dataclass / Pydantic model | 与调用接口天然一致 |
| 观测输出 | OTEL / logging callback | Lite 模式最小可用 |

### 10.3 关系模型

- `ReasonerRequest.request_id` 应能映射到对应的 `StructuredGenerationResult` 与 `ReplayBundle`
- `StructuredGenerationResult.parsed_result` 必须与 `contracts` 中的目标 schema 对齐
- `ProviderHealthStatus(provider, model)` 对应 `ProviderProfile(provider, model)`

---

## 11. 核心计算/算法设计

### 11.1 结构化调用算法

**输入**：`ReasonerRequest`、ProviderProfile、目标 schema。

**输出**：`StructuredGenerationResult` + `ReplayBundle`。

**处理流程**：

```text
标准化请求
  -> 执行 PII scrub
  -> 计算 sanitized_input + input_hash
  -> 选择 provider/model
  -> 通过 LiteLLM 发起调用
  -> Instructor 解析输出
  -> 生成 parsed_result + raw_output + output_hash
  -> 生成 lineage / token / cost / latency
  -> 返回结果对象与 replay bundle
```

### 11.2 回退与重试算法

**输入**：主 provider、fallback 链、错误类型、`max_retries`。

**输出**：成功结果或失败分类。

**处理流程**：

```text
尝试 configured provider
  -> 若网络/配额/不可用失败，则切下一个 fallback target
  -> 若结构化解析失败，则按 max_retries 在当前 target 上重试
  -> 若成功，记录 fallback_path
  -> 若全链失败，分类为 infra_level 或 task_level
```

### 11.3 健康探测算法

**输入**：一组 ProviderProfile。

**输出**：`ProviderHealthStatus[]` 与聚合结论。

**处理流程**：

```text
遍历 provider/model 组合
  -> 发送最小测试请求
  -> 记录 reachable / latency / quota
  -> 聚合整体可用性
  -> 返回给 orchestrator 做 Gate 判定
```

### 11.4 脱敏链算法

**输入**：原始 messages / prompt / metadata。

**输出**：`sanitized_input`。

**处理流程**：

```text
接收渲染后的输入
  -> 应用 scrub rule set
  -> 替换姓名 / 手机 / 账户等敏感片段
  -> 输出脱敏文本
  -> 外发链、落盘链、日志链复用同一结果
```

---

## 12. 触发/驱动引擎设计

### 12.1 触发源类型

| 类型 | 来源 | 示例 |
|------|------|------|
| 同步业务调用 | `main-core` / `entity-registry` / `subsystem-*` | 结构化分析、消歧、抽取 |
| 健康探测 | `orchestrator` | Phase 0 末尾 `llm_health_check` |
| 回放读取 | `audit-eval` / 调用方 | 历史 replay bundle 消费 |

### 12.2 关键触发流程

```text
caller build request
  -> reasoner-runtime generate_structured
  -> replay bundle returned
  -> caller persists or handles failure
```

### 12.3 失败分级基线

| 类型 | 判定 | 处理路径 |
|------|------|----------|
| `infra_level` | fallback 链全部失败 / 无可用 provider | 由调用方或 `orchestrator` 视链路硬停 |
| `task_level` | 单次结构化解析失败、单股票任务失败但 provider 仍可用 | 由业务模块做降级或 `inconclusive` |
| `success_with_fallback` | 主 target 失败但 fallback 成功 | 返回结果并记录 lineage |

---

## 13. 输出产物设计

### 13.1 Structured Result Payload

**面向**：`main-core`、`entity-registry`、`subsystem-*`

**结构**：

```text
{
  parsed_result: Object
  actual_provider: String
  actual_model: String
  fallback_path: Array[String]
  retry_count: Integer
  token_usage: Object
  cost_estimate: Number
  latency_ms: Integer
}
```

### 13.2 Replay Bundle

**面向**：调用方、`audit-eval`

**结构**：

```text
{
  sanitized_input: String
  input_hash: String
  raw_output: String
  parsed_result: Object
  output_hash: String
  llm_lineage: Object
}
```

### 13.3 Health Check Report

**面向**：`orchestrator`

**结构**：

```text
{
  provider_statuses: Array[Object]
  all_critical_targets_available: Boolean
  summary: String
}
```

---

## 14. 系统模块拆分

**组织模式**：monorepo 下的独立 Python package，不包含业务 analyzer 实现。

| 模块名 | 语言 | 运行位置 | 职责 |
|--------|------|----------|------|
| `reasoner_runtime.core` | Python | 库 | 标准化请求与主调用入口 |
| `reasoner_runtime.providers` | Python | 库 | LiteLLM provider/profile 抽象 |
| `reasoner_runtime.structured` | Python | 库 | Instructor 初始化与结构化解析 |
| `reasoner_runtime.scrub` | Python | 库 | PII scrub handler |
| `reasoner_runtime.callbacks` | Python | 库 | OTEL / callback backend 适配 |
| `reasoner_runtime.health` | Python | 库 | provider/model 健康探测 |
| `reasoner_runtime.replay` | Python | 库 | replay bundle 与 lineage 生成 |
| `reasoner_runtime.config` | Python + YAML/TOML | 库 + 配置 | provider/scrub/callback 配置 |

**关键设计决策**：

- `reasoner-runtime` 在主项目中的角色是**横切运行时基础能力，不是业务层**
- 它与其他子项目的关系是**接受调用方 prompt/schema，返回结构化结果和运行时元数据**
- 它必须独立成子项目，因为 LLM 调用的稳定性、审计性和供应链约束必须统一治理
- `SinglePromptAnalyzer` / `MultiAgentAnalyzer` 不进入本项目代码树
- Iceberg / Dagster / PostgreSQL 持久化逻辑不进入本项目代码树

---

## 15. 存储与技术路线

| 用途 | 技术选型 | 理由 |
|------|----------|------|
| 统一 provider 调用 | LiteLLM | 与主文档冻结口径一致，支持 fallback 与成本追踪 |
| 结构化输出 | Instructor `from_provider()` | P2 立即引入，强制结构化 JSON |
| 最小观测层 | LiteLLM callbacks / OTEL | Lite 模式最小可用，无需新增服务 |
| PII scrub | 自定义统一 scrub handler | 合规强制项，必须和外发链同源 |
| 依赖安全 | `pip install --require-hashes` | 满足版本号 + SHA-256 锁定 |
| 可选观测后端 | Langfuse callback backend | 有痛点后引入，不改变接口 |

最低要求：

- Python 3.12+
- LiteLLM
- Instructor
- OTEL 相关最小依赖
- `requirements.txt` 中锁定 `litellm`、`instructor` 等版本与 hash

---

## 16. API 与接口合同

### 16.1 Python 接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `generate_structured(request)` | 执行一次结构化 LLM 调用 | `ReasonerRequest` |
| `health_check(provider_profiles)` | 检查 provider/model 健康状态 | ProviderProfile 列表 |
| `scrub_input(messages, metadata)` | 生成统一 `sanitized_input` | messages、metadata |
| `build_replay_bundle(...)` | 生成回放字段集合 | sanitized_input、raw_output、parsed_result、lineage |
| `classify_failure(error, context)` | 分类 infra/task 失败 | error、调用上下文 |
| `build_client(profile, max_retries)` | 构建可复用 runtime client | ProviderProfile、显式 `max_retries` |

### 16.2 协议 / 配置接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `ReasonerRequestSchema` | 调用请求 schema | 由 `contracts` 或本模块内部模型定义 |
| `ProviderProfileSchema` | provider 配置 schema | provider/model/timeout/fallback |
| `CallbackBackend` | 观测回调协议 | `on_start / on_success / on_error` |
| `ScrubRuleProvider` | 脱敏规则提供协议 | 规则集 |

### 16.3 版本与兼容策略

- 所有结构化输出必须以 `contracts` 中的目标 schema 为准
- `max_retries` 必须显式配置，默认不允许隐式依赖 Instructor 默认值
- `build_client()` 与等价 client factory 必须显式接收 `max_retries`，不允许把重试策略藏在内部默认值里
- Langfuse 等 callback backend 的引入不得改变 `generate_structured()` 的返回结构
- 调用方升级目标 schema 时，必须同步验证 replay bundle 仍可被 `audit-eval` 消费
- replay bundle 的核心五字段命名和语义必须稳定，如需附加字段不得改写这五个字段
- `requirements.txt` / lock 文件至少要对 `litellm`、`instructor` 维持版本号 + SHA-256 hash 锁定

---

## 18. 测试与验证策略

### 18.1 单元测试

- `scrub_input()` 对姓名 / 手机 / 账户三类敏感信息的脱敏测试
- fallback / retry 分类逻辑测试
- Instructor 初始化强制显式 `max_retries` 测试
- replay bundle 哈希生成正确性测试
- dependency lock / hash 校验测试

### 18.2 集成测试

| 场景 | 验证目标 |
|------|----------|
| 1 条结构化调用成功返回 | 验证 LiteLLM + Instructor 主链路 |
| 主 provider 失败、fallback 成功 | 验证 fallback_path 与 lineage 记录 |
| 结构化解析失败后重试成功 | 验证重试策略与成本记录 |
| `health_check()` 覆盖多个 provider/model | 验证按组合探测，不是单点探针 |
| 调用方写入 replay bundle | 验证与 `audit-eval` / 审计链对接 |

### 18.3 协议 / 契约测试

- `parsed_result` 与 `contracts` 的目标 schema 一致
- replay bundle 字段名与 `contracts` / 主文档口径一致
- 业务模块不直接 import 外部 provider SDK 的静态检查

### 18.4 安全与回归测试

- `sanitized_input` 外发链、落盘链、日志链一致性测试
- `raw_output` 持久化前不额外变形的回归测试
- 升级 `litellm` / `instructor` 后的兼容性回归测试

---

## 19. 关键评价指标

### 19.1 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 单次结构化调用运行时开销 | `< 500ms` 额外开销 | 不含模型实际推理时间 |
| `health_check()` 单 provider/model 探测耗时 | `< 3 秒` | Lite 环境基线 |
| replay bundle 生成耗时 | `< 100ms` | 单次调用后处理 |

### 19.2 质量指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 结构化解析成功率 | `> 99%` | 以稳定 schema 的正式调用为准 |
| PII scrub 覆盖率 | `>= 95%` | 对姓名 / 手机 / 账户样本集 |
| 业务模块直连 provider SDK 发生率 | `0` | 必须全部经过本模块 |
| replay bundle 字段缺失率 | `0` | formal 调用不允许漏字段 |
| provider 健康检查漏报率 | `0` | critical target 不可静默失败 |

---

## 20. 项目交付物清单

### 20.1 运行时核心

- `generate_structured()` 主入口
- provider/profile/fallback 抽象
- Instructor 结构化输出封装

### 20.2 审计与观测

- replay bundle 生成层
- `llm_lineage` / token / cost / latency 产出
- OTEL / callback 适配层

### 20.3 安全与稳定性

- PII scrub handler
- `health_check()` 探测能力
- dependency hash 锁定与校验脚本

---

## 21. 实施路线图

### 阶段 0：P2b 运行时骨架（2-3 天）

**阶段目标**：建立统一调用接口与最小 provider 配置骨架。

**交付**：
- `ReasonerRequest`
- `generate_structured()` 空骨架
- ProviderProfile 配置样板

**退出条件**：`main-core` 能 import 并发起最小空调用。

### 阶段 1：P2b 主链路打通（3-5 天）

**阶段目标**：打通 LiteLLM + Instructor + replay bundle。

**交付**：
- 结构化输出主链
- replay bundle 五字段
- fallback / retry

**退出条件**：1 条正式调用可产出完整结构化结果与回放字段。

### 阶段 2：P2b 安全与观测（2-4 天）

**阶段目标**：补齐 PII scrub、OTEL、供应链锁定。

**交付**：
- scrub handler
- OTEL callbacks
- `requirements.txt` hash 锁定

**退出条件**：外发前脱敏成立，最小观测数据可用。

### 阶段 3：P2-P4 跨模块接入（3-5 天）

**阶段目标**：接入 `main-core`、`entity-registry`，为子系统保留统一入口。

**交付**：
- 主系统调用适配
- entity resolution 调用适配
- `health_check()` 与 `orchestrator` 对接

**退出条件**：`orchestrator` 可以在 Phase 0 调用健康探测，业务模块不再直连 provider。

### 阶段 4：P6+ 可选观测后端（按需）

**阶段目标**：在不改接口的前提下接入 Langfuse 等 callback backend。

**交付**：
- Callback backend adapter
- 配置切换能力
- 回归测试

**退出条件**：观测后端变化不影响调用方代码。

---

## 22. 主要风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| PII scrub 过度导致上下文丢失 | 结构化结果质量下降，回放可解释性不足 | 建立黑盒样本集和覆盖率阈值 |
| `parsed_result` 随 schema 演化失配 | 回放和审计消费失败 | 以 `contracts` 为唯一 schema 来源并做契约测试 |
| fallback/retry 成本失控 | LLM 预算超支 | 重试次数显式配置并计入成本追踪 |
| 业务模块绕过运行时直连 provider | 审计链失效、观测漂移 | 静态检查 + code review 硬约束 |

---

## 23. 验收标准

项目完成的最低标准：

1. 所有业务模块都可以通过 `reasoner-runtime` 完成统一结构化调用，而不是直连 provider SDK
2. `generate_structured()` 能稳定产出结构化结果、`llm_lineage` 和 replay bundle 五字段
3. `health_check()` 能按 provider/model 组合执行探测，并可被 `orchestrator` 直接消费
4. PII scrub、fallback/retry、依赖 hash 锁定三项关键稳定性约束都已落地
5. 文档中定义的主项目角色、OWN/BAN/EDGE 与主项目 `12 + N` 模块边界一致

---

## 24. 一句话结论

`reasoner-runtime` 子项目不是某个 provider SDK 的包装层，而是主项目里唯一负责 LLM 调用统一性、可审计性和可回放性的运行时基座。  
它一旦边界失守，后面出现的不会只是“几处调用不一致”，而是整个 LLM 链路无法被统一治理。

---

## 25. 自动化开发对接

### 25.1 自动化输入契约

| 项 | 规则 |
|----|------|
| `module_id` | `reasoner-runtime` |
| 脚本先读章节 | `§1` `§4` `§5.4` `§9` `§15` `§16` `§18` `§21` `§23` |
| 默认 issue 粒度 | 一次只实现一个运行时对象、一个调用能力、一个可靠性能力或一组紧密相关测试 |
| 默认写入范围 | 当前 repo 的 runtime client、scrub / replay / health / callback 能力、测试、文档和依赖锁定配置 |
| 内部命名基线 | 以 `§9` 的对象名、`§14` 的内部模块名和 `§16` 的接口名为准 |
| 禁止越界 | 不写业务 prompt / analyzer、不直接持久化审计记录、不把重试或 provider 路由藏成隐式默认值 |
| 完成判定 | 同时满足 `§18`、`§21` 当前阶段退出条件和 `§23` 对应条目 |

### 25.2 推荐自动化任务顺序

1. 先落 `ReasonerRequest` / `StructuredGenerationResult` 等核心对象和 client factory
2. 再落 scrub、replay bundle、failure classify 和显式 `max_retries` 约束
3. 再落 health check、fallback / callback backend 和供应链锁定
4. 最后补可选观测后端与增强验证

补充规则：

- 单个 issue 默认只改一条运行时能力链，不混做业务 prompt 和存储逻辑
- 在 replay / scrub / retry 未稳定前，不进入 callback 或观测增强类 issue

### 25.3 Blocker 升级条件

- 需要把业务语义、prompt 模板或 analyzer 逻辑写进 runtime
- 需要依赖隐式重试、隐式 provider 默认值或未锁定的关键依赖
- 需要由 runtime 直接写 Iceberg / PostgreSQL / Dagster event log
- 无法给出结构化调用、replay bundle 或 health check 的验证命令
