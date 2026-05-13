# contracts 完整项目文档

> **文档状态**：Draft v1
> **版本**：v0.1.2
> **作者**：Codex
> **创建日期**：2026-04-15
> **最后更新**：2026-04-15
> **文档目的**：把 `contracts` 子项目从“大家默认会有的一组 schema”收束为可立项、可拆分、可实现、可验收的正式项目，使其成为主项目所有子项目共享的唯一合同来源。

---

## 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| v0.1 | 2026-04-15 | 初稿 | Codex |
| v0.1.1 | 2026-04-15 | 补充 Ex / formal object / analyzer 核心字段摘要，与主文档附录 G 和 6.1 对齐 | Codex |
| v0.1.2 | 2026-04-15 | 补充 Avro 只作为 CI 自动导出构建产物的兼容策略说明 | Codex |

---

## 1. 一句话定义

`contracts` 是主项目中**唯一负责定义和发布跨子项目共享 schema、协议、错误码、版本规则与兼容策略**的合同模块，它以 Pydantic 模型和自动导出的 JSON Schema 为唯一真相来源，并以“禁止 schema 漂移”和“禁止实现先于合同”为不可协商约束。

它不是业务实现模块，也不是存储模块，更不是编排模块。  
它不负责数据写入、图谱计算、LLM 调用、Dagster 编排和子系统抓取。

---

## 2. 文档定位与核心问题

本文解决的问题不是“怎么写一个公共 types 包”，而是：

1. **跨模块 schema 漂移问题**：多个子项目并行开发时，如果没有单一合同源，接口会快速失控。
2. **实施切片与长期模块脱节问题**：P0/P1/P2/P3 是施工波次，不是长期接口定义；需要一个长期稳定的合同模块承接所有共享协议。
3. **自动化开发代理缺乏共同语言问题**：Claude Code、Codex 和后续脚本化开发都必须引用同一套定义，不能各自发明术语和字段。

---

## 3. 术语表

| 术语 | 定义 | 备注 |
|------|------|------|
| Contract | 跨子项目共享的正式接口定义，包括 schema、协议、错误码和兼容规则 | 本项目核心对象 |
| Contract Source of Truth | 合同的唯一真相来源 | 本项目中为 Pydantic 模型 |
| Schema Artifact | 从 Pydantic 自动导出的 JSON Schema 等构建产物 | 不是手写源文件 |
| Ex-0 | 子系统 Metadata / 心跳合同 | 不可改写为其他含义 |
| Ex-1 | Candidate Facts 合同 | 子系统到 Layer B |
| Ex-2 | Candidate Signals 合同 | 子系统到 Layer B |
| Ex-3 | Candidate Graph Deltas 合同 | 子系统到 Layer B |
| Formal Object | 主系统正式发布对象的 schema | 如 world_state_snapshot |
| Ingest Metadata | Layer B 在摄取时补写的元数据，如 `submitted_at`、`ingest_seq` | 不属于生产者 payload |
| Compatibility Rule | 合同演进时必须满足的兼容规则 | 默认 backward compatible |

**规则**：
- 后续所有子项目文档必须严格使用这些术语
- `Ex-0 ~ Ex-3` 的语义不能漂移
- `Contract Source of Truth` 只能有一套

---

## 4. 目标与非目标

### 4.1 项目目标

1. **定义共享合同**：为 12 个长期模块和首批 `N=2` 子系统提供唯一可引用的 schema 与协议定义。
2. **冻结关键对象**：冻结 Ex-0~Ex-3、formal objects、cycle 元数据、核心协议接口。
3. **提供自动导出**：从 Pydantic 自动导出 JSON Schema，避免手写多套 schema。
4. **约束兼容演进**：定义 breaking change 与 backward compatible change 的判定规则。
5. **支持自动化开发**：让 orchestrator、Claude Code、Codex 都能直接以本模块作为 issue 路由和接口验证的依据。
6. **支持集成测试**：为 contract test 提供稳定的唯一基线。

### 4.2 非目标

- **不实现业务逻辑**：因为业务逻辑属于 `main-core`、`graph-engine`、`entity-registry` 等模块。
- **不直接做 IO**：因为数据库、文件写入、消息发送都不属于合同模块职责。
- **不手写 Avro 双轨合同**：Lite 阶段只维护 Pydantic + JSON Schema；Avro 如需存在，只作为后续自动化导出产物。
- **不承载环境配置**：运行时资源配置属于 `orchestrator` 或具体业务模块。

---

## 5. 与现有工具的关系定位

### 5.1 架构位置

```text
主项目权威文档 / 模块边界决议
  -> contracts
      -> data-platform
      -> entity-registry
      -> reasoner-runtime
      -> graph-engine
      -> main-core
      -> audit-eval
      -> subsystem-sdk
      -> subsystem-announcement
      -> subsystem-news
      -> orchestrator
      -> assembly
      -> feature-store
      -> stream-layer
```

### 5.2 上游输入

| 来源 | 提供内容 | 说明 |
|------|----------|------|
| 主项目权威文档 | 正式术语、正式对象、Layer 约束 | `contracts` 只能依据权威文档定义，不得自行发明 |
| 模块冻结决议 | 长期模块清单、边界、首批 N | 决定要定义哪些合同 |
| 实施切片规划 | P0/P1/P2/P3/P4/P5 施工波次 | 影响合同上线顺序，但不决定合同真相 |

### 5.3 下游输出

| 目标 | 输出内容 | 消费方式 |
|------|----------|----------|
| `data-platform` | 表 schema、cycle 控制表、adapter 协议 | Python import + schema artifact |
| `entity-registry` | entity 相关对象、resolution 协议 | Python import |
| `reasoner-runtime` | LLM 回放字段、错误码、协议对象 | Python import |
| `graph-engine` | graph delta、snapshot、impact snapshot schema | Python import |
| `main-core` | formal objects、analyzer 协议、业务对象 | Python import |
| `audit-eval` | audit/replay/retrospective schema | Python import |
| `subsystem-sdk` 与子系统 | Ex-0~Ex-3 payload schema | Python import + validator |
| `orchestrator` | Gate 枚举、policy 配置类型、接口协议 | Python import |
| `assembly` | 模块版本矩阵、contract test 基线 | 文件读取 + import |

### 5.4 核心边界

- **Pydantic 模型是唯一真相来源**
- **Ex-0 是 Metadata / 心跳，不得改写**
- **摄取元数据不属于生产者 payload**
- **contracts 不依赖任何业务模块**
- **任何 breaking change 先改合同文档再改实现**

---

## 6. 设计哲学

### 6.1 设计原则

#### 原则 1：Contract-first

所有跨模块实现必须先有合同定义，再有代码实现。  
如果实现先于合同，后续多代理开发必然出现漂移。

#### 原则 2：Single Source of Truth

合同定义只能有一个源头。  
本项目选择 Pydantic 模型作为唯一真相来源，JSON Schema 为导出产物。

#### 原则 3：Backward Compatible by Default

默认合同演进只能做向后兼容变更。  
需要 breaking change 时，必须显式升级版本并说明迁移方案。

#### 原则 4：No Runtime Ownership

合同模块只拥有“定义”，不拥有“执行”。  
一旦开始拥有运行时行为，就会和业务模块边界混淆。

### 6.2 反模式清单

| 反模式 | 为什么危险 |
|--------|-----------|
| 在业务模块内私自新增共享字段 | 会导致并行开发时字段定义失控 |
| 手写第二套 schema 源文件 | 会导致双源不一致 |
| 把 `submitted_at` / `ingest_seq` 写进 Ex payload | 会把 Lite 实现细节污染到长期合同 |
| 让 contracts 依赖具体运行时库 | 会把合同模块拖入实现层 |

---

## 7. 用户与消费方

### 7.1 直接消费方

| 消费方 | 消费内容 | 用途 |
|--------|----------|------|
| Claude Code / Codex | schema、协议、错误码 | 并行开发时统一接口语言 |
| `data-platform` | DDL 对应对象、adapter 协议 | 落表、写入、Serving |
| `main-core` | formal objects、运行时协议 | 业务链实现 |
| `subsystem-sdk` | Ex-0~Ex-3 | 子系统输出校验 |
| `orchestrator` | Gate 类型、policy 配置类型 | 编排和 contract test |

### 7.2 间接用户

| 角色 | 关注点 |
|------|--------|
| 主编 / 架构 owner | 合同是否清晰、边界是否稳定 |
| reviewer | PR 是否改变了共享接口 |
| CI | 是否出现 breaking change |

---

## 8. 总体系统结构

### 8.1 合同定义主线

```text
主项目权威文档 / 模块决议
  -> Pydantic 模型定义
  -> JSON Schema 导出
  -> 版本号登记
  -> 发布给各子项目消费
```

### 8.2 合同消费主线

```text
contracts
  -> 各子项目 import 合同
  -> 本地验证 / contract test
  -> 集成测试
  -> e2e 最小 cycle
```

---

## 9. 领域对象设计

### 9.1 持久层对象

| 对象名 | 职责 | 归属 |
|--------|------|------|
| ContractVersionEntry | 记录合同版本、发布日期、兼容性说明 | Git 跟踪文件 |
| SchemaArtifact | JSON Schema 等导出文件 | 构建产物目录 |
| ErrorCodeRegistry | 错误码清单 | Python 源文件 |

### 9.2 运行时对象

| 对象名 | 职责 | 生命周期 |
|--------|------|----------|
| ContractPackage | 运行时被 import 的合同包 | 进程启动到结束 |
| CompatibilityCheckResult | 一次兼容性检查的结果 | 单次检查过程 |

### 9.3 核心对象详细设计

#### ContractPackage

**角色**：整个主项目共享合同的唯一运行时入口。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| version | String | 合同版本号，如 `0.1.0` |
| schemas | Dict[String, Any] | 所有 schema 注册表 |
| protocols | Dict[String, Any] | 所有协议定义 |
| error_codes | Dict[String, String] | 错误码清单 |

#### SchemaArtifact

**角色**：从 Pydantic 模型导出的结构化 schema 文件。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| name | String | schema 名称 |
| source_model | String | 源 Pydantic 模型名 |
| artifact_type | Enum | 当前为 `json_schema` |
| version | String | 与合同版本对齐 |
| output_path | String | 导出路径 |

#### CompatibilityRule

**角色**：定义合同变更是否允许。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| rule_id | String | 规则 ID |
| rule_name | String | 规则名 |
| severity | Enum | `error` / `warning` |
| description | String | 规则说明 |
| applies_to | Array[String] | 作用对象 |

#### ExPayloadSchema

**角色**：子系统 Ex-0~Ex-3 的正式 payload 定义。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| ex_type | Enum | `Ex-0` / `Ex-1` / `Ex-2` / `Ex-3` |
| payload_model | String | 对应 Pydantic 模型 |
| version | String | 合同版本 |
| required_fields | Array[String] | 本层 payload 的必填字段 |
| producer_owned_fields | Array[String] | 生产者拥有字段 |
| notes | String | 特殊约束说明 |

#### FormalObjectSchema

**角色**：主系统 formal object 的正式定义摘要。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| object_name | String | formal object 名称 |
| payload_model | String | 对应 Pydantic 模型 |
| required_fields | Array[String] | 关键必填字段 |
| publish_owner | String | 正式发布 owner |
| zone | Enum | `formal` / `analytical` |
| notes | String | 特殊约束 |

#### AlphaAnalyzerContract

**角色**：L6 可插拔 analyzer 的统一协议摘要。

**建议字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| interface_name | String | 当前固定为 `AlphaAnalyzer` |
| signature | String | `analyze(stock, context) -> alpha_result` |
| required_result_fields | Array[String] | `score`、`direction`、`confidence`、`rationale`、`evidence_refs`、`analyzer_name`、`analyzer_version` |
| notes | String | `SinglePromptAnalyzer` / `MultiAgentAnalyzer` 必须共用同一接口 |

---

## 10. 数据模型设计

### 10.1 模型分层策略

- 共享协议与对象定义 → Python 源文件持久化
- 自动导出的 JSON Schema → 构建产物
- 一次性兼容性检查结果 → 内存对象或测试输出

### 10.2 存储方案

| 存储用途 | 技术选型 | 理由 |
|----------|----------|------|
| 合同定义 | Python + Pydantic v2 | 单一真相来源，便于自动导出 |
| schema 构建产物 | JSON Schema 文件 | 可被测试和其他工具消费 |
| 版本记录 | Git 跟踪 Markdown / TOML / Python 常量 | 简单、透明、可审计 |

---

## 14. 系统模块拆分

**组织模式**：monorepo 下的独立 Python package。

| 模块名 | 语言 | 运行位置 | 职责 |
|--------|------|----------|------|
| `contracts.core` | Python | 库 | 共享对象、枚举、错误码 |
| `contracts.protocols` | Python | 库 | `DataSourceAdapter`、`AlphaAnalyzer` 等协议 |
| `contracts.schemas` | Python | 库 | Ex-0~Ex-3、formal objects、cycle 对象 |
| `contracts.export` | Python | CLI/库 | 自动导出 JSON Schema |
| `contracts.compat` | Python | CLI/库 | 兼容性检查 |

**关键设计决策**：

- `contracts` 在主项目中的角色是**主项目所有子项目的合同根节点**
- 它与其他子项目的关系是**单向输出**，不反向依赖其他业务模块
- 它必须独立成子项目，因为所有后续 issue 路由、contract test 和自动化开发都依赖它

---

## 15. 存储与技术路线

| 用途 | 技术选型 | 理由 |
|------|----------|------|
| 合同定义 | Python 3.12 + Pydantic v2 | 统一类型系统，便于生成 JSON Schema |
| schema 导出 | Python CLI | 可直接纳入 CI |
| 兼容检查 | Python 测试 / 脚本 | 简单可控 |

最低要求：

- Python 3.12+
- Pydantic v2
- pytest

---

## 16. API 与接口合同

### 16.1 Python 包接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `contracts.schemas` | 导出全部共享 schema | 无 |
| `contracts.protocols` | 导出全部共享协议 | 无 |
| `contracts.errors` | 导出错误码与异常类型 | 无 |

### 16.2 CLI / 脚本接口

| 名称 | 功能 | 参数 |
|------|------|------|
| `python -m contracts.export` | 导出 JSON Schema | 输出目录、版本号 |
| `python -m contracts.compat` | 检查兼容性 | 基线版本、当前版本 |

### 16.3 版本与兼容策略

- 默认只允许 backward compatible change
- breaking change 必须显式升级主版本
- 任何新增共享字段，先改 `contracts`，再改消费方
- `Ex-0` 固定为 Metadata / 心跳，核心字段至少包括 `subsystem_id`、`version`、`heartbeat_at`、`status`、`last_output_at`、`pending_count`
- `Ex-1` 核心字段至少包括 `fact_id`、`entity_id`、`fact_type`、`fact_content`、`confidence`、`source_reference`、`extracted_at`、`subsystem_id`
- `Ex-2` 核心字段至少包括 `signal_id`、`signal_type`、`direction`、`magnitude`、`affected_entities`、`affected_sectors`、`time_horizon`、`evidence`、`confidence`、`subsystem_id`
- `Ex-3` 核心字段至少包括 `delta_id`、`delta_type`、`source_node`、`target_node`、`relation_type`、`properties`、`evidence`、`subsystem_id`
- formal object 清单固定包含 `world_state_snapshot`、`official_alpha_pool`、`alpha_result_snapshot`、`recommendation_snapshot`、`dashboard_snapshot`、`report`、`audit_record`、`replay_record`
- `backtest_result` 明确是 analytical asset，不得被注册成 formal object
- `AlphaAnalyzer` 的 `alpha_result` 返回字段必须固定包含 `score`、`direction`、`confidence`、`rationale`、`evidence_refs`、`analyzer_name`、`analyzer_version`
- Lite 阶段只维护 Pydantic + JSON Schema 两层真相；Avro 如需存在，只能作为 CI 自动导出构建产物，不得手写维护第二套合同源文件

---

## 18. 测试与验证策略

### 18.1 单元测试

- Ex-0~Ex-3 Pydantic 模型校验
- formal objects schema 校验
- `DataSourceAdapter` / `AlphaAnalyzer` 协议对象校验
- 错误码注册表校验

### 18.2 集成测试

| 场景 | 验证目标 |
|------|----------|
| `contracts` 被 `data-platform` 引用 | adapter 协议和 cycle 对象可导入 |
| `contracts` 被 `subsystem-sdk` 引用 | Ex-0~Ex-3 校验器可运行 |
| `contracts` 被 `main-core` 引用 | formal objects 和 analyzer 协议可运行 |

### 18.3 协议 / 契约测试

- JSON Schema 导出结果与源 Pydantic 模型一致
- 兼容性检查能识别 breaking change

### 18.4 版本与兼容测试

- 新增字段不破坏旧消费方
- 删除字段或改类型必须触发失败

---

## 19. 关键评价指标

### 19.1 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| JSON Schema 全量导出耗时 | `< 5 秒` | 本地开发环境 |
| 兼容性检查耗时 | `< 10 秒` | 单次 CI 检查 |

### 19.2 质量指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 首批 10+ 模块共享对象覆盖率 | `100%` | 不允许私有自定义共享 schema |
| Ex-0~Ex-3 合同误用率 | `0` | 不允许语义漂移 |
| breaking change 漏检率 | `0` | CI 必须拦截 |

---

## 20. 项目交付物清单

### 20.1 核心合同

- Ex-0~Ex-3 Pydantic 模型
- formal objects Pydantic 模型
- cycle 元数据对象
- analyzer 协议与 `alpha_result` 返回字段定义
- 错误码注册表

### 20.2 协议层

- `DataSourceAdapter`
- `AlphaAnalyzer`
- 其他共享协议

### 20.3 工具层

- JSON Schema 导出脚本
- 兼容性检查脚本
- contract test 样例

---

## 21. 实施路线图

### 阶段 0：合同骨架（1-2 天）

**阶段目标**：建立 `contracts` 项目骨架和最小版本号。

**交付**：
- 包结构
- 版本号 `0.1.0`
- README / MODULE_SPEC / TESTPLAN

**退出条件**：其他模块可以 import 空骨架。

### 阶段 1：核心合同冻结（3-5 天）

**阶段目标**：冻结首批必须合同。

**交付**：
- Ex-0~Ex-3
- formal objects
- cycle 元数据
- 核心协议

**退出条件**：`data-platform`、`main-core`、`subsystem-sdk` 可直接消费。

### 阶段 2：导出与兼容检查（2-3 天）

**阶段目标**：提供自动导出和兼容校验能力。

**交付**：
- JSON Schema 导出
- 兼容性检查
- contract test

**退出条件**：CI 可自动拦截 breaking change。

---

## 22. 主要风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 合同定义过慢 | 阻塞所有下游模块 | 先冻结最小核心对象，再补完整 |
| 字段语义漂移 | 集成失败、返工成本高 | 所有共享字段必须先入 `contracts` |
| 双源 schema | 测试和实现不一致 | 坚持 Pydantic 单一真相来源 |

---

## 23. 验收标准

项目完成的最低标准：

1. Ex-0~Ex-3、formal objects、cycle 元数据都有正式 Pydantic 定义
2. `data-platform`、`main-core`、`subsystem-sdk` 能直接 import 并通过最小 contract test
3. JSON Schema 能从 Pydantic 自动导出
4. compatibility check 能拦截 breaking change
5. 文档中定义的主项目角色和上下游关系，与主项目 `12 + N` 模块表一致

---

## 24. 一句话结论

`contracts` 子项目不是“公共类型杂货铺”，而是主项目所有子项目共享的正式合同根模块。  
它的质量直接决定后续 12 + N 并行开发能否稳定进行。

---

## 25. 自动化开发对接

### 25.1 自动化输入契约

| 项 | 规则 |
|----|------|
| `module_id` | `contracts` |
| 脚本先读章节 | `§1` `§3` `§4` `§5.4` `§9` `§14` `§16` `§18` `§21` `§23` |
| 默认 issue 粒度 | 一次只实现一个 schema 族、一个导出器、一个兼容检查器，或一组紧密相关测试 |
| 默认写入范围 | 当前 repo 的合同模型、导出脚本、兼容检查、测试、文档与构建配置 |
| 内部命名基线 | 以 `§9` 对象名、`§14` 内部模块名和 `§16` 接口名为准，不另起第二套 schema 命名体系 |
| 禁止越界 | 不写业务逻辑、不手写第二套合同真相、不绕过兼容检查直接改共享字段 |
| 完成判定 | 同时满足 `§18`、`§21` 当前阶段退出条件和 `§23` 对应条目 |

### 25.2 推荐自动化任务顺序

1. 先落 schema 主干、枚举、错误码和导出脚手架
2. 再落兼容性检查、breaking change 检测和 CI 集成
3. 再补 contract examples、下游夹具和说明文档
4. breaking change 必须单独成 issue，不与普通字段扩展混做

补充规则：

- 单个 issue 默认只改一个 schema 族或一个导出/兼容子模块
- 先补 schema 与测试，再允许下游实现依赖它

### 25.3 Blocker 升级条件

- 任一共享字段语义与主文档或已有子项目文档冲突
- 需要手写 Avro 或第二套 schema 源文件
- 需要靠修改下游业务实现来掩盖合同 breaking change
- 缺少导出 / compat 命令，无法形成可验证 gate
