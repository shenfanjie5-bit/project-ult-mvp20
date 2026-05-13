> 文档状态: Draft
> 版本: 0.1.3

# contracts

> **合同真相源：`src/contracts/schemas`；导出产物：`artifacts/json_schema/`（阶段 2 生成）**

`contracts` 是主项目中唯一负责定义和发布跨子项目共享 schema、协议、错误码、版本规则与兼容策略的合同模块。Pydantic 模型是唯一合同真相来源，JSON Schema 只从模型自动导出为构建产物。

## 架构位置

`contracts` 位于主项目权威文档和所有业务子项目之间，只向下游输出合同，不反向依赖业务模块。

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

## 非目标警告

本模块不实现业务逻辑、不直接做 IO、不承载运行时环境配置，也不手写双轨合同源文件。Avro 如需存在，只能作为 CI 自动导出产物，不得在 `contracts/` 下手写维护。

## 快速开始

本项目要求 Python 3.12+，运行时依赖 Pydantic v2，开发测试依赖 pytest。

```bash
pip install -e .[dev,shared-fixtures]
pytest
```

JSON Schema 导出和兼容性检查是默认 CI gate：

```bash
python -m contracts.export --output-dir ./artifacts/json_schema
python -m contracts.compat --baseline artifacts/baselines/0.1.0/json_schema --current HEAD
```

当前 package version 由 `contracts.__version__` 统一声明；导出 metadata 默认使用同一版本，避免 CLI/包版本漂移。

## 目录结构

```text
contracts/
├── src/
│   └── contracts/
│       ├── core/        # 共享对象、枚举、错误码
│       ├── protocols/   # DataSourceAdapter、AlphaAnalyzer 等协议
│       ├── schemas/     # Ex-0~Ex-3、formal objects、cycle 对象
│       ├── export/      # JSON Schema 自动导出 CLI / 库
│       └── compat/      # 兼容性检查 CLI / 库
├── tests/
├── docs/
└── artifacts/           # 构建产物目录，不手写合同源文件
```

## 合同边界

- `src/contracts/schemas` 承载 Pydantic schema 定义。
- `src/contracts/protocols` 承载 `DataSourceAdapter`、`AlphaAnalyzer` 等共享协议。
- `src/contracts/core` 承载共享对象、枚举、错误码和版本记录。
- `submitted_at`、`ingest_seq` 等 Ingest Metadata 由 Layer B 摄取时补写，不写入 Ex-0~Ex-3 生产者 payload。
- 新增共享字段必须先改 `contracts`，再改消费方。

## 参考文档

- [完整项目文档](docs/contracts.project-doc.md)
- [变更记录](docs/CHANGELOG.md)
- [Claude 指令](CLAUDE.md)
- [Codex / Agent 指令](AGENTS.md)
