> 文档状态: Draft
> 版本: 0.1.0

# TESTPLAN

本文直接承接 `docs/contracts.project-doc.md` 的 §18.1~§18.4 测试与验证策略，并补充 §19 的性能指标目标值。阶段 0 只要求骨架和文档 gate 可验证；后续 schema、协议、导出器和兼容检查落地时，必须同步补齐对应测试。

## 单元测试

对应 §18.1，最小用例包括：

- Ex-0~Ex-3 Pydantic 模型字段校验。
- Formal Object schema 校验，且 formal object 清单只能包含 `world_state_snapshot`、`official_alpha_pool`、`alpha_result_snapshot`、`recommendation_snapshot`、`dashboard_snapshot`、`report`、`audit_record`、`replay_record`。
- `DataSourceAdapter` / `AlphaAnalyzer` 协议对象校验。
- 错误码注册表校验。
- `ContractVersionEntry` 版本号、发布时间和兼容说明校验。

## 集成测试

对应 §18.2，最小用例包括：

- `contracts` 被 `data-platform` 引用时，adapter 协议和 cycle 对象可导入。
- `contracts` 被 `subsystem-sdk` 引用时，Ex-0~Ex-3 校验器可运行。
- `contracts` 被 `main-core` 引用时，Formal Object 和 analyzer 协议可运行。
- `contracts` 不 import `data-platform`、`main-core`、`graph-engine`、`entity-registry`、`reasoner-runtime`、`orchestrator` 等业务模块。

## 契约测试

对应 §18.3，最小用例包括：

- JSON Schema 导出结果与源 Pydantic 模型一致。
- `python -m contracts.export --output-dir ./artifacts --version 0.1.0` 能导出完整 JSON Schema 构建产物。
- 导出产物只作为自动生成 artifact 校验，不作为手写合同源文件。
- 兼容性检查能识别 breaking change。

### 阶段 2 CI gate

仓库内通用 CI 入口为 `bash scripts/ci.sh`。该脚本必须按以下顺序执行：

- `${PYTHON:-python3} -m pip install -e '.[dev]'`，验证 editable install 与开发依赖安装路径。
- `python -c 'import contracts, contracts.schemas, contracts.protocols, contracts.export, contracts.compat'`，验证公开模块可导入。
- `pytest --collect-only -q`，并确认至少收集到一个测试。
- `pytest -q`，运行完整测试套件。
- `python -m contracts.export --output-dir <tmp>/json_schema --version ${CONTRACTS_VERSION:-0.1.0}`，导出当前 JSON Schema。
- `python -m contracts.compat --baseline ${CONTRACTS_BASELINE:-artifacts/baselines/0.1.0/json_schema} --current <tmp>/json_schema`，拦截 breaking change。

`CONTRACTS_BASELINE` 必须指向已发布的 JSON Schema baseline 目录；缺失时 CI 应返回非 0 并提示配置 baseline。`contracts.compat` 的 breaking change 返回码必须由 CI 透传为失败。

## 兼容测试

对应 §18.4，最小用例包括：

- 新增可选字段不破坏旧消费方。
- 删除必填字段必须触发失败。
- 字段类型变更必须触发失败。
- breaking change 必须显式升级主版本，并说明迁移方案。
- Ex-0~Ex-3 不得加入 `submitted_at`、`ingest_seq` 等 Ingest Metadata。

## 性能指标

对应 §19.1，目标值如下：

| 指标 | 目标值 | 场景 |
|------|--------|------|
| JSON Schema 全量导出耗时 | `< 5 秒` | 本地开发环境 |
| 兼容性检查耗时 | `< 10 秒` | 单次 CI 检查 |

### 阶段 2 实测数据

| 执行日期 | Python 版本 | Schema 数量 | JSON Schema 导出耗时 | 兼容检查耗时 | Breaking smoke 耗时 | 验证命令 |
|----------|-------------|-------------|-----------------------|--------------|---------------------|----------|
| 2026-04-15 | Python 3.14.3 | 16 | `0.004220s` | `0.001465s` | `0.001262s` | `PYTHONPATH=src python3 -m pytest -q -s tests/test_milestone2_performance.py` |

## 质量指标

对应 §19.2，目标值如下：

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 首批 10+ 模块共享对象覆盖率 | `100%` | 不允许私有自定义共享 schema |
| Ex-0~Ex-3 合同误用率 | `0` | 不允许语义漂移 |
| breaking change 漏检率 | `0` | CI 必须拦截 |
