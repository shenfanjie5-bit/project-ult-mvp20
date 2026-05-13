# 项目进度跟踪 — contracts

> **文档状态**：Draft v1
> **版本**：0.1.3
> **最后更新**：2026-04-27
> **用途**：跟踪 `contracts` 子项目各阶段与 issue 的交付状态。每次 issue 状态变化时同步更新本文件。

---

## 总览

| 阶段 | 里程碑 | 目标 | Issue 数 | 状态 | 退出条件（来源） |
|------|--------|------|----------|------|------------------|
| 阶段 0 | milestone-0 · 合同骨架 | 建立包骨架、版本号、文档、冒烟测试 | 5 | 已完成 | 其他模块可 import 空骨架（§21） |
| 阶段 1 | milestone-1 · 核心合同冻结 | 冻结 Ex-0~Ex-3、formal objects、cycle、核心协议 | 13 | 进行中 | `data-platform`、`main-core`、`subsystem-sdk` 可直接消费（§21） |
| 阶段 2 | milestone-2 · 导出与兼容检查 | 提供 JSON Schema 自动导出与 breaking change 拦截 | 5 | 已完成 | CI 可自动拦截 breaking change（§21），性能冒烟满足 §19 |

状态语义：`未开始` / `进行中` / `已完成` / `阻塞中`。
标识规则：`ISSUE-xxx` 为内部任务编号；`GH #n` 为 GitHub issue 编号；阶段 1 测试项状态与验收证据需同时保留两者映射，避免仅靠内部编号追踪。

---

## 阶段 0：合同骨架（milestone-0）

**目标**：建立 `contracts` 项目骨架和最小版本号，保证其他模块可 import 空骨架。
**前置依赖**：无
**总体状态**：已完成

| 内部 Issue | GitHub Issue | 标题 | 优先级 | 依赖 | 状态 |
|------------|--------------|------|--------|------|------|
| ISSUE-001 | GH #2 | 配置 pyproject.toml 与开发依赖 | P0 | 无 | 已完成 |
| ISSUE-002 | GH #3 | 建立 src/contracts 包骨架与子模块 | P0 | ISSUE-001 | 已完成 |
| ISSUE-003 | GH #4 | 版本号常量与 ContractVersionEntry 骨架 | P0 | ISSUE-002 | 已完成 |
| ISSUE-004 | GH #5 | 编写 README / MODULE_SPEC / TESTPLAN 骨架 | P0 | ISSUE-003 | 已完成 |
| ISSUE-005 | GH #6 | 骨架冒烟测试与最小 CI 配置 | P0 | ISSUE-002, ISSUE-003 | 已完成 |

阶段 0 验收：
- [x] 全部 5 个 issue 通过各自验收标准（GH #2–GH #6 / ISSUE-001–ISSUE-005）
- [x] `python -c "import contracts"` 成功，`contracts.__version__ == "0.1.3"`
- [x] `bash scripts/ci.sh` 入口存在并执行 `pip install -e .[dev,shared-fixtures]`、全量 `pytest -q`、JSON Schema export 和 compat
- [x] README / MODULE_SPEC / TESTPLAN 三份文档就绪

---

## 阶段 1：核心合同冻结（milestone-1）

**目标**：冻结首批必须合同，使下游业务模块可直接消费。
**前置依赖**：阶段 0（已完成）
**总体状态**：进行中

| 内部 Issue | GitHub Issue | 标题 | 优先级 | 依赖 | 状态 |
|------------|--------------|------|--------|------|------|
| ISSUE-006 | GH #7 | 共享枚举与类型基元 | P0 | ISSUE-005 | 已完成 |
| ISSUE-007 | GH #8 | 错误码注册表 contracts.errors | P0 | ISSUE-006 | 已完成 |
| ISSUE-008 | GH #9 | Ex-0 Metadata / 心跳 schema | P0 | ISSUE-006, ISSUE-007 | 已完成 |
| ISSUE-009 | GH #10 | Ex-1 Candidate Facts schema | P0 | ISSUE-008 | 已完成 |
| ISSUE-010 | GH #11 | Ex-2 Candidate Signals schema | P0 | ISSUE-009 | 已完成 |
| ISSUE-011 | GH #12 | Ex-3 Candidate Graph Deltas schema | P0 | ISSUE-010 | 已完成 |
| ISSUE-012 | GH #13 | Formal objects schema 族 | P0 | ISSUE-006, ISSUE-007 | 已完成 |
| ISSUE-013 | GH #14 | Cycle 元数据对象 | P0 | ISSUE-006 | 已完成 |
| ISSUE-014 | GH #15 | DataSourceAdapter 协议 | P0 | ISSUE-013 | 已完成 |
| ISSUE-015 | GH #16 | AlphaAnalyzer 协议与 alpha_result 冻结 | P0 | ISSUE-012 | 已完成 |
| ISSUE-016 | GH #17 | Ex-0~Ex-3 Pydantic 校验单元测试 | P0 | ISSUE-008–ISSUE-011 | 已完成 |
| ISSUE-017 | GH #18 | Formal objects 与 cycle 元数据单元测试 | P0 | ISSUE-012, ISSUE-013 | 已完成 |
| ISSUE-018 | GH #19 | 协议对象结构测试 | P0 | ISSUE-014 / GH #15, ISSUE-015 / GH #16 | 已完成 |

阶段 1 验收：
- [x] Ex-0~Ex-3、formal objects、cycle 元数据全部有正式 Pydantic 定义（§23.1）
- [ ] `data-platform`、`main-core`、`subsystem-sdk` 可直接 import 并通过最小 contract test（§23.2）
- [x] `backtest_result` 未被注册为 formal object（§16.3 / §6.2）
- [x] `submitted_at` / `ingest_seq` 未出现在任何 Ex payload 中（§5.4）

阶段 1 当前验收证据：
- [x] GH #7 / ISSUE-006：`PYTHONPATH=src python3 - <<'PY' ...` 输出 `core types ok`
- [x] GH #7 / ISSUE-006：`python3 -m pytest -q tests/test_skeleton_imports.py tests/test_core_types.py` 退出码 0
- [x] GH #7 / ISSUE-006：`bash scripts/ci.sh` 退出码 0，并继续执行包边界检查
- [x] GH #7 / ISSUE-006：`git ls-files | grep -E '(__pycache__|\.DS_Store)$'` 无输出
- [ ] GH #7 / ISSUE-006：`python -m pip install -e .[dev]` 未在当前沙箱执行成功；当前环境无 `python` 命令，`python3` 受 PEP 668 externally-managed-environment 限制
- [x] GH #8 / ISSUE-007：`PYTHONPATH=src python3 - <<'PY' ...` 输出 `errors ok`
- [x] GH #8 / ISSUE-007：`python3 -m pytest -q tests/test_errors.py tests/test_skeleton_imports.py tests/test_core_types.py` 退出码 0
- [x] GH #8 / ISSUE-007：`bash scripts/ci.sh` 退出码 0；当前沙箱因 `setuptools` 不可用使用 `PYTHONPATH=src` 回退路径，并继续执行包边界检查
- [x] GH #13 / ISSUE-012：`PYTHONPATH=src python3 - <<'PY' ...` 输出 `formal objects ok`
- [x] GH #13 / ISSUE-012：`python3 -m pytest -q tests/test_formal_objects.py tests/test_skeleton_imports.py` 退出码 0；当前环境未安装 console scripts，既有 entrypoint 检查按测试逻辑 skip
- [x] GH #13 / ISSUE-012：`bash scripts/ci.sh` 退出码 0；当前沙箱因 `setuptools` 不可用使用 `PYTHONPATH=src` 回退路径
- [ ] GH #13 / ISSUE-012：`python -m pip install -e .[dev]` 未执行；当前沙箱禁止全局 package installation
- [x] GH #16 / ISSUE-015：`PYTHONPATH=src python3 - <<'PY' ...` 输出 `alpha analyzer contract ok`
- [x] GH #16 / ISSUE-015：`PYTHONPATH=src python3 -m pytest -q tests/test_alpha_analyzer_protocol.py tests/test_skeleton_imports.py` 退出码 0；当前环境未安装 console scripts，既有 entrypoint 检查按测试逻辑 skip
- [x] GH #16 / ISSUE-015：`bash scripts/ci.sh` 退出码 0；当前沙箱因 `setuptools` 不可用使用 `PYTHONPATH=src` 回退路径
- [ ] GH #16 / ISSUE-015：`python -m pip install -e .[dev]` 未执行；当前沙箱禁止全局 package installation
- [x] GH #9 / ISSUE-008：`PYTHONPATH=src python3 - <<'PY' ...` 输出 `ex0 ok`
- [x] GH #9 / ISSUE-008：`PYTHONPATH=src python3 -m pytest -q tests/test_ex0_metadata.py tests/test_skeleton_imports.py` 退出码 0；当前环境未安装 console scripts，既有 entrypoint 检查按测试逻辑 skip
- [x] GH #9 / ISSUE-008：`bash scripts/ci.sh` 退出码 0；当前沙箱因 `setuptools` 不可用使用 `PYTHONPATH=src` 回退路径
- [ ] GH #9 / ISSUE-008：`python -m pip install -e .[dev]` 未执行；当前沙箱禁止全局 package installation
- [x] GH #10 / ISSUE-009：`PYTHONPATH=src python3 - <<'PY' ...` 输出 `ex1 ok`
- [x] GH #10 / ISSUE-009：`PYTHONPATH=src python3 -m pytest -q tests/test_ex1_candidate_fact.py tests/test_ex0_metadata.py tests/test_skeleton_imports.py` 退出码 0；当前环境未安装 console scripts，既有 entrypoint 检查按测试逻辑 skip
- [x] GH #10 / ISSUE-009：`bash scripts/ci.sh` 退出码 0；当前沙箱因 `setuptools` 不可用使用 `PYTHONPATH=src` 回退路径
- [ ] GH #10 / ISSUE-009：`python -m pip install -e .[dev]` 未执行；当前沙箱禁止全局 package installation，且当前环境无 `python` 命令
- [x] GH #11 / ISSUE-010：`PYTHONPATH=src python3 - <<'PY' ...` 输出 `ex2 ok`
- [x] GH #11 / ISSUE-010：`python3 -m pytest -q tests/test_ex2_candidate_signal.py tests/test_ex1_candidate_fact.py tests/test_skeleton_imports.py` 退出码 0；当前环境未安装 console scripts，既有 entrypoint 检查按测试逻辑 skip
- [x] GH #11 / ISSUE-010：`bash scripts/ci.sh` 退出码 0；当前沙箱因 `setuptools` 不可用使用 `PYTHONPATH=src` 回退路径
- [ ] GH #11 / ISSUE-010：`python -m pip install -e .[dev]` 未执行；当前沙箱禁止全局 package installation，且当前环境无 `python` 命令
- [ ] GH #11 / ISSUE-010：`pytest -q tests/test_ex2_candidate_signal.py tests/test_ex1_candidate_fact.py tests/test_skeleton_imports.py` 在当前环境返回 `command not found`；已使用 `python3 -m pytest` 等价验证
- [x] GH #12 / ISSUE-011：`PYTHONPATH=src python3 - <<'PY' ...` 输出 `ex3 ok`
- [x] GH #12 / ISSUE-011：`PYTHONPATH=src python3 -m pytest -q tests/test_ex3_candidate_graph_delta.py tests/test_ex2_candidate_signal.py tests/test_skeleton_imports.py` 退出码 0；当前环境未安装 console scripts，既有 entrypoint 检查按测试逻辑 skip
- [x] GH #12 / ISSUE-011：`bash scripts/ci.sh` 退出码 0；当前沙箱因 `setuptools` 不可用使用 `PYTHONPATH=src` 回退路径
- [ ] GH #12 / ISSUE-011：`python -m pip install -e .[dev]` 未执行；当前沙箱禁止全局 package installation，且当前环境无 `python` 命令
- [ ] GH #12 / ISSUE-011：`pytest -q tests/test_ex3_candidate_graph_delta.py tests/test_ex2_candidate_signal.py tests/test_skeleton_imports.py` 未执行；当前环境无 `pytest` 命令，已使用 `python3 -m pytest` 等价验证
- [x] GH #14 / ISSUE-013：`PYTHONPATH=src python3 - <<'PY' ...` 输出 `cycle ok`
- [x] GH #14 / ISSUE-013：`PYTHONPATH=src python3 -m pytest -q tests/test_cycle_metadata.py tests/test_skeleton_imports.py` 退出码 0；当前环境未安装 console scripts，既有 entrypoint 检查按测试逻辑 skip
- [x] GH #14 / ISSUE-013：`bash scripts/ci.sh` 退出码 0；当前沙箱因 `setuptools` 不可用使用 `PYTHONPATH=src` 回退路径
- [ ] GH #14 / ISSUE-013：`python -m pip install -e .[dev]` 未执行；当前沙箱禁止全局 package installation，且当前环境无 `python` 命令
- [x] GH #18 / ISSUE-017：`PYTHONPATH=src python3 -m pytest --collect-only tests/test_formal_objects_and_cycle.py` 收集 18 个测试，退出码 0
- [x] GH #18 / ISSUE-017：`PYTHONPATH=src python3 -m pytest -q tests/test_formal_objects_and_cycle.py tests/test_skeleton_imports.py` 退出码 0；当前环境未安装 console scripts，既有 entrypoint 检查按测试逻辑 skip
- [x] GH #18 / ISSUE-017：`bash scripts/ci.sh` 退出码 0；当前沙箱因 `setuptools` 不可用使用 `PYTHONPATH=src` 回退路径
- [ ] GH #18 / ISSUE-017：`python -m pip install -e .[dev]` 未执行；当前沙箱禁止全局 package installation，且当前环境无 `python` 命令
- [ ] GH #18 / ISSUE-017：`pytest --collect-only tests/test_formal_objects_and_cycle.py` 与 `pytest -q tests/test_formal_objects_and_cycle.py tests/test_skeleton_imports.py` 在当前环境返回 `command not found`；已使用 `python3 -m pytest` 等价验证
- [x] GH #15 / ISSUE-014：`PYTHONPATH=src python3 - <<'PY' ...` 输出 `adapter protocol ok`
- [x] GH #15 / ISSUE-014：`PYTHONPATH=src python3 -m pytest -q tests/test_data_source_adapter_protocol.py tests/test_skeleton_imports.py` 退出码 0；当前环境未安装 console scripts，既有 entrypoint 检查按测试逻辑 skip
- [x] GH #15 / ISSUE-014：`bash scripts/ci.sh` 退出码 0；当前沙箱因 `setuptools` 不可用使用 `PYTHONPATH=src` 回退路径
- [ ] GH #15 / ISSUE-014：`python -m pip install -e .[dev]` 未执行；当前沙箱禁止全局 package installation，且当前环境无 `python` 命令
- [ ] GH #15 / ISSUE-014：`pytest -q tests/test_data_source_adapter_protocol.py tests/test_skeleton_imports.py` 在当前环境返回 `command not found`；已使用 `python3 -m pytest` 等价验证
- [x] GH #19 / ISSUE-018：`PYTHONPATH=src python3 -m pytest --collect-only tests/test_protocols.py` 收集 4 个测试，退出码 0
- [x] GH #19 / ISSUE-018：`PYTHONPATH=src python3 -m pytest -q tests/test_protocols.py tests/test_skeleton_imports.py` 退出码 0；当前环境未安装 console scripts，既有 entrypoint 检查按测试逻辑 skip
- [x] GH #19 / ISSUE-018：`bash scripts/ci.sh` 退出码 0；当前沙箱因 `setuptools` 不可用使用 `PYTHONPATH=src` 回退路径
- [ ] GH #19 / ISSUE-018：`python -m pip install -e .[dev]` 未执行；当前沙箱禁止全局 package installation，且当前环境无 `python` 命令
- [ ] GH #19 / ISSUE-018：`pytest --collect-only tests/test_protocols.py` 与 `pytest -q tests/test_protocols.py tests/test_skeleton_imports.py` 未执行；当前环境无 `pytest` 命令，已使用 `python3 -m pytest` 等价验证
- [x] GH #17 / ISSUE-016：`PYTHONPATH=src python3 -m pytest --collect-only tests/test_ex_payloads.py` 收集 68 个测试，退出码 0
- [x] GH #17 / ISSUE-016：`PYTHONPATH=src python3 -m pytest -q tests/test_skeleton_imports.py tests/test_ex_payloads.py` 退出码 0；`tests/test_skeleton_imports.py` 中既有 entrypoint 检查按测试逻辑 skip
- [x] GH #17 / ISSUE-016：`bash scripts/ci.sh` 退出码 0；当前沙箱因 `setuptools` 不可用使用 `PYTHONPATH=src` 回退路径
- [ ] GH #17 / ISSUE-016：`python -m pip install -e .[dev]` 未执行；当前沙箱禁止全局 package installation，且当前环境无 `python` 命令
- [ ] GH #17 / ISSUE-016：`pytest --collect-only tests/test_ex_payloads.py` 与 `pytest -q tests/test_skeleton_imports.py tests/test_ex_payloads.py` 未执行；当前环境无 `pytest` 命令，已使用 `python3 -m pytest` 等价验证

---

## 阶段 2：导出与兼容检查（milestone-2）

**目标**：提供 JSON Schema 自动导出与 breaking change 拦截。
**前置依赖**：阶段 1 核心 schema / formal object / protocol 已落地（GH #7–GH #19 / ISSUE-006–ISSUE-018）。
**总体状态**：已完成

| 内部 Issue | GitHub Issue | 标题 | 优先级 | 依赖 | 状态 |
|------------|--------------|------|--------|------|------|
| ISSUE-019 | GH #20 | JSON Schema 导出 CLI | P1 | ISSUE-016–ISSUE-018 | 已完成 |
| ISSUE-020 | GH #21 | CompatibilityRule 与兼容性检查 CLI | P1 | ISSUE-019 / GH #20 | 已完成 |
| ISSUE-021 | GH #22 | Contract examples 与下游夹具 | P1 | ISSUE-019 / GH #20 | 已完成 |
| ISSUE-022 | GH #23 | CI 集成与 breaking change 拦截 | P1 | ISSUE-020 / GH #21, ISSUE-021 / GH #22 | 已完成 |
| ISSUE-023 | GH #24 | 性能与验收冒烟 | P1 | ISSUE-022 / GH #23 | 已完成 |

阶段 2 验收：
- [x] JSON Schema 能从 Pydantic 自动导出，耗时 `< 5 秒`（§19.1 / §23.3）
- [x] compatibility check 能拦截 breaking change，耗时 `< 10 秒`（§19.1 / §23.4）
- [x] CI 脚本在检测到 breaking change 时退出码非 0
- [x] `fixtures/` 覆盖全部 Ex / formal object / cycle 对象

阶段 2 当前验收证据：
- [x] GH #20 / ISSUE-019：`SCHEMA_MODEL_REGISTRY` 当前导出 28 个 Pydantic JSON Schema；`tests/test_export_json_schema_contract.py` 与 `tests/test_export_cli.py` 覆盖 registry、manifest、schema metadata 与 CLI 入口。
- [x] GH #21 / ISSUE-020：`tests/test_compat_rules.py` 与 `tests/test_compat_cli.py` 覆盖删除 schema、删除字段、required 变更、字段类型 / `$ref` / `anyOf` 变更和 enum 变更。
- [x] GH #22 / ISSUE-021：`fixtures/manifest.json` 与 `tests/test_contract_fixtures.py` 覆盖 Ex-0~Ex-3、formal objects 与 cycle fixture 校验。
- [x] GH #23 / ISSUE-022：`scripts/ci.sh` 按 editable install、import smoke、pytest collect、pytest、JSON Schema 导出、compat gate 顺序执行；`PYTHONPATH=src python3 -m pytest -q tests/test_ci_pipeline.py` 通过，覆盖匹配 baseline 通过与 breaking baseline 失败。
- [x] GH #24 / ISSUE-023：`PYTHONPATH=src python3 -m pytest -q -s tests/test_milestone2_performance.py` 通过；当前 registry 导出 28 个 schema，同源兼容检查和 breaking-change 检查维持毫秒级。

---

## 风险快照（源自 §22）

| 风险 | 当前状态 | 缓解措施 |
|------|----------|----------|
| 合同定义过慢阻塞下游 | 监测中 | 阶段 0 优先出骨架，让下游先写 import |
| 字段语义漂移 | 监测中 | 阶段 1 所有共享字段先入 `contracts` |
| 双源 schema | 监测中 | 坚持 Pydantic 单一真相源，Avro 仅允许 CI 自动导出 |

---

## 更新日志

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-04-15 | 完成 GH #24 / ISSUE-023 性能与验收冒烟，记录阶段 2 实测数据并将 milestone-2 状态更新为已完成 | GH #24 |
| 2026-04-15 | 完成 GitHub #17 / ISSUE-016 Ex-0~Ex-3 Pydantic 校验单元测试，记录沙箱验证结果 | GH #17 |
| 2026-04-15 | 完成 GH #19 / ISSUE-018 协议对象结构测试，记录沙箱验证结果 | GH #19 |
| 2026-04-15 | 完成 GH #15 / ISSUE-014 DataSourceAdapter 协议，记录沙箱验证结果 | GH #15 |
| 2026-04-15 | 完成 GH #12 / ISSUE-011 Ex-3 Candidate Graph Deltas schema，记录沙箱验证结果 | GH #12 |
| 2026-04-15 | 完成 GH #11 / ISSUE-010 Ex-2 Candidate Signals schema，记录沙箱验证结果 | GH #11 |
| 2026-04-15 | 完成 GH #18 / ISSUE-017 Formal objects 与 cycle 元数据单元测试，记录沙箱验证结果 | GH #18 |
| 2026-04-15 | 完成 GH #10 / ISSUE-009 Ex-1 Candidate Facts schema，记录沙箱验证结果 | GH #10 |
| 2026-04-15 | 完成 GH #14 / ISSUE-013 Cycle 元数据对象，记录沙箱验证结果 | GH #14 |
| 2026-04-15 | 完成 GH #9 / ISSUE-008 Ex-0 Metadata / 心跳 schema，记录沙箱验证结果 | GH #9 |
| 2026-04-15 | 完成 GH #16 / ISSUE-015 AlphaAnalyzer 协议与 `alpha_result` 字段冻结，记录沙箱验证结果 | GH #16 |
| 2026-04-15 | 完成 GH #13 / ISSUE-012 Formal objects schema 族，记录沙箱验证结果 | GH #13 |
| 2026-04-15 | 完成 GH #8 / ISSUE-007 错误码注册表 `contracts.errors`，记录沙箱验证结果 | GH #8 |
| 2026-04-15 | 完成 GH #7 / ISSUE-006 共享枚举、类型基元与 `ContractBaseModel`，记录沙箱验证结果 | GH #7 |
| 2026-04-15 | 同步 milestone-0 与 GH #2–GH #6 完成状态，补齐阶段 0 验收证据 | GH #32 |
| 2026-04-15 | 初始化任务拆解与进度表 | PM 初稿 |
