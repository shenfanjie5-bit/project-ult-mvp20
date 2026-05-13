> 文档状态: Draft
> 版本: 0.1.0

# MODULE_SPEC

本文是 `contracts` 阶段 0 模块规格骨架，复用 `docs/contracts.project-doc.md` 的 §3 术语表、§14 模块拆分、§16 API / CLI 接口合同与 §9.3 核心对象字段摘要。具体 Pydantic schema 字段详细文档会在模型实现阶段随代码同步补齐。

## 术语表

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

规则：

- 后续所有子项目文档必须严格使用这些术语。
- `Ex-0 ~ Ex-3` 的语义不能漂移。
- `Contract Source of Truth` 只能有一套，当前固定为 Pydantic 模型。

## 模块拆分

`contracts` 是 monorepo 下的独立 Python package，内部模块按 §14 拆分：

| 模块名 | 语言 | 运行位置 | 职责 |
|--------|------|----------|------|
| `contracts.core` | Python | 库 | 共享对象、枚举、错误码 |
| `contracts.protocols` | Python | 库 | `DataSourceAdapter`、`AlphaAnalyzer` 等协议 |
| `contracts.schemas` | Python | 库 | Ex-0~Ex-3、formal objects、cycle 对象 |
| `contracts.export` | Python | CLI / 库 | 自动导出 JSON Schema |
| `contracts.compat` | Python | CLI / 库 | 兼容性检查 |

关键边界：

- `contracts` 是主项目所有子项目的合同根节点。
- `contracts` 与业务子项目是单向输出关系，不反向依赖任何业务模块。
- 合同定义先于业务实现；任何新增共享字段必须先进入本模块。

## Python API

按 §16.1，阶段 0 保留以下包接口方向：

| 名称 | 功能 | 参数 |
|------|------|------|
| `contracts.schemas` | 导出全部共享 schema | 无 |
| `contracts.protocols` | 导出全部共享协议 | 无 |
| `contracts.core` | 导出共享对象、枚举、错误码与版本记录 | 无 |

后续如果需要独立 `contracts.errors`，必须先在本模块补齐包结构与测试，再允许消费方引用。

## CLI 接口

按 §16.2，阶段 2 形成正式实现：

| 名称 | 功能 | 参数 |
|------|------|------|
| `python -m contracts.export` | 导出 JSON Schema | 输出目录、版本号 |
| `python -m contracts.compat` | 检查兼容性 | 基线版本、当前版本 |

阶段 0 的 CLI 入口只保证可导入和可注册，具体逻辑留给导出与兼容检查阶段。

## 版本与兼容策略

按 §16.3：

- 默认只允许 backward compatible change。
- breaking change 必须显式升级主版本。
- 任何新增共享字段，先改 `contracts`，再改消费方。
- `backtest_result` 是 analytical asset，不得注册为 Formal Object。
- Avro 如需存在，只能作为 CI 自动导出产物，不得手写维护第二套合同源文件。

## 核心对象字段摘要

### ContractPackage

角色：整个主项目共享合同的唯一运行时入口。

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | String | 合同版本号，如 `0.1.0` |
| `schemas` | Dict[String, Any] | 所有 schema 注册表 |
| `protocols` | Dict[String, Any] | 所有协议定义 |
| `error_codes` | Dict[String, String] | 错误码清单 |

### SchemaArtifact

角色：从 Pydantic 模型导出的结构化 schema 文件。Pydantic 模型是唯一合同真相来源，JSON Schema 只是自动生成的构建产物。

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | String | schema 名称 |
| `source_model` | String | 源 Pydantic 模型名 |
| `artifact_type` | Enum | 当前为 `json_schema` |
| `version` | String | 与合同版本对齐 |
| `output_path` | String | 导出路径 |

### CompatibilityRule

角色：定义合同变更是否允许。

| 字段 | 类型 | 说明 |
|------|------|------|
| `rule_id` | String | 规则 ID |
| `rule_name` | String | 规则名 |
| `severity` | Enum | `error` / `warning` |
| `description` | String | 规则说明 |
| `applies_to` | Array[String] | 作用对象 |

### ExPayloadSchema

角色：子系统 Ex-0~Ex-3 的正式 payload 定义。

| 字段 | 类型 | 说明 |
|------|------|------|
| `ex_type` | Enum | `Ex-0` / `Ex-1` / `Ex-2` / `Ex-3` |
| `payload_model` | String | 对应 Pydantic 模型 |
| `version` | String | 合同版本 |
| `required_fields` | Array[String] | 本层 payload 的必填字段 |
| `producer_owned_fields` | Array[String] | 生产者拥有字段 |
| `notes` | String | 特殊约束说明 |

### Ex-0 Metadata / 心跳

| 必填字段 |
|----------|
| `subsystem_id` |
| `version` |
| `heartbeat_at` |
| `status` |
| `last_output_at` |
| `pending_count` |

### Ex-1 Candidate Facts

| 必填字段 |
|----------|
| `fact_id` |
| `entity_id` |
| `fact_type` |
| `fact_content` |
| `confidence` |
| `source_reference` |
| `extracted_at` |
| `subsystem_id` |

### Ex-2 Candidate Signals

| 必填字段 |
|----------|
| `signal_id` |
| `signal_type` |
| `direction` |
| `magnitude` |
| `affected_entities` |
| `affected_sectors` |
| `time_horizon` |
| `evidence` |
| `confidence` |
| `subsystem_id` |

### Ex-3 Candidate Graph Deltas

| 必填字段 |
|----------|
| `delta_id` |
| `delta_type` |
| `source_node` |
| `target_node` |
| `relation_type` |
| `properties` |
| `evidence` |
| `subsystem_id` |

### FormalObjectSchema

角色：主系统 Formal Object 的正式定义摘要。

| 字段 | 类型 | 说明 |
|------|------|------|
| `object_name` | String | Formal Object 名称 |
| `payload_model` | String | 对应 Pydantic 模型 |
| `required_fields` | Array[String] | 关键必填字段 |
| `publish_owner` | String | 正式发布 owner |
| `zone` | Enum | `formal` / `analytical` |
| `notes` | String | 特殊约束 |

Formal Object 清单固定为：

- `world_state_snapshot`
- `official_alpha_pool`
- `alpha_result_snapshot`
- `recommendation_snapshot`
- `dashboard_snapshot`
- `report`
- `audit_record`
- `replay_record`

### AlphaAnalyzerContract

角色：L6 可插拔 analyzer 的统一协议摘要。

| 字段 | 类型 | 说明 |
|------|------|------|
| `interface_name` | String | 当前固定为 `AlphaAnalyzer` |
| `signature` | String | `analyze(stock, context) -> alpha_result` |
| `required_result_fields` | Array[String] | `score`、`direction`、`confidence`、`rationale`、`evidence_refs`、`analyzer_name`、`analyzer_version` |
| `notes` | String | `SinglePromptAnalyzer` / `MultiAgentAnalyzer` 必须共用同一接口 |

`alpha_result` 必填字段固定为：

- `score`
- `direction`
- `confidence`
- `rationale`
- `evidence_refs`
- `analyzer_name`
- `analyzer_version`
