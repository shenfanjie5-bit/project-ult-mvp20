# 项目任务拆解

## 阶段 0：合同骨架

**目标**：建立 `contracts` 项目骨架、版本号和最小运行时入口，使其他业务模块可直接 import 空骨架。
**前置依赖**：无

### ISSUE-001: 配置 pyproject.toml 与开发依赖
**labels**: P0, infrastructure, milestone-0, ready

#### 背景与目标
依据 §15 要求，`contracts` 必须基于 Python 3.12+、Pydantic v2、pytest 构建，作为合同真相的唯一运行时。当前 `pyproject.toml` 仍为 scaffold 默认值（Python 3.11、空 dependencies），需要补齐依赖与构建配置，为后续 Pydantic 模型和 CLI 导出/兼容检查提供基础。参见 §15 存储与技术路线、§14 模块拆分。

#### 所属模块
contracts / 根包构建配置（`pyproject.toml`）

#### 实现范围
- 将 `requires-python` 从 `>=3.11` 改为 `>=3.12`。
- 在 `[project].dependencies` 中加入 `pydantic>=2.5,<3`。
- 在 `[project.optional-dependencies]` 中新增 `dev` 组，包含 `pytest>=8`、`pytest-cov>=4`。
- 在 `[tool.setuptools]` 中将 `packages` 改为 `find` 形式并指定 `where = ["src"]`。
- 新增 `[tool.setuptools.package-dir]` 映射 `"" = "src"`。
- 在 `[project.scripts]` 中登记 `contracts-export = "contracts.export.__main__:main"` 与 `contracts-compat = "contracts.compat.__main__:main"` 占位入口（允许指向 stub）。

#### 不在本次范围
- 不实现任何 Pydantic schema 或协议（留给阶段 1）。
- 不实现 `contracts.export` / `contracts.compat` 真实逻辑（留给阶段 2）。
- 不新增 Avro 相关依赖（§4.2 非目标）。
- 不触碰 `src/` 实际代码（由 ISSUE-002 完成）。

#### 关键交付物
- `pyproject.toml` 更新后能用 `pip install -e .[dev]` 成功安装。
- `requires-python = ">=3.12"`。
- `dependencies = ["pydantic>=2.5,<3"]`。
- `optional-dependencies.dev = ["pytest>=8", "pytest-cov>=4"]`。
- `tool.setuptools` 配置切换到 `src` 布局：`package-dir = {"" = "src"}`，`packages = {find = {where = ["src"]}}`。
- `project.scripts` 条目指向 `contracts.export.__main__:main` 与 `contracts.compat.__main__:main`。
- 保留现有 `[tool.pytest.ini_options]` 块。

#### 验收标准
- [ ] `python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); assert d['project']['requires-python'] == '>=3.12'"` 成功。
- [ ] `pip install -e .[dev]` 在 Python 3.12 环境下零错误完成。
- [ ] `pytest --collect-only` 无错误（可以为 0 test）。
- [ ] `pyproject.toml` 中出现且仅出现一条 `pydantic` 依赖，且版本 `>=2.5,<3`。
- [ ] 不含任何 Avro / jsonschema-manual 维护依赖。

#### 验证命令
```bash
cd /Users/fanjie/Desktop/Cowork/project-ult/contracts
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
python -c "import pydantic; print(pydantic.VERSION)"
pytest --collect-only
```

#### 依赖
无前置依赖

---

### ISSUE-002: 建立 src/contracts 包骨架与子模块
**labels**: P0, infrastructure, milestone-0, ready

#### 背景与目标
§14 明确 `contracts` 必须拆分为 `contracts.core`、`contracts.protocols`、`contracts.schemas`、`contracts.export`、`contracts.compat` 五个子模块。阶段 0 退出条件（§21）是“其他模块可以 import 空骨架”，因此需要先把包目录、`__init__.py`、占位 `__all__` 搭好，以便 `data-platform`、`main-core` 等下游尽早开始写 import 语句。

#### 所属模块
contracts / 源码树根（`src/contracts/`）

#### 实现范围
- 在 `src/` 下创建 `contracts/` 包以及 `__init__.py`。
- 创建子模块目录：`core/`、`protocols/`、`schemas/`、`export/`、`compat/`，均附空 `__init__.py`。
- `contracts/__init__.py` 中 re-export：`from contracts import core, protocols, schemas`（`export`、`compat` 为 CLI 子包，不必 re-export）。
- 为 `export`、`compat` 各写一个 `__main__.py` 占位入口，函数签名 `def main() -> int: raise NotImplementedError("实现见阶段 2")`。
- 在 `contracts/__init__.py` 中声明 `__all__ = ["core", "protocols", "schemas", "__version__"]`。
- `__version__` 由 ISSUE-003 定义，这里先 `from contracts.core.version import __version__`，若 ISSUE-003 未合并，允许用临时 `__version__ = "0.0.0.dev0"`，由 ISSUE-003 替换。

#### 不在本次范围
- 不实现 `ContractPackage`、`SchemaArtifact`、`CompatibilityRule` 等具体类（留给阶段 1/2）。
- 不实现任何 Ex-0~Ex-3、formal object Pydantic 模型（阶段 1）。
- 不实现错误码注册表（阶段 1）。
- 不写任何业务逻辑或 IO。

#### 关键交付物
- 目录结构：
  ```
  src/contracts/__init__.py
  src/contracts/core/__init__.py
  src/contracts/protocols/__init__.py
  src/contracts/schemas/__init__.py
  src/contracts/export/__init__.py
  src/contracts/export/__main__.py
  src/contracts/compat/__init__.py
  src/contracts/compat/__main__.py
  ```
- 每个 `__init__.py` 至少包含一个 module docstring，指明该子包职责（中文）。
- `contracts/__init__.py` 暴露 `__all__`、`__version__`。
- `export/__main__.py` 与 `compat/__main__.py` 各包含 `def main() -> int` 函数。

#### 验收标准
- [ ] `python -c "import contracts; import contracts.core, contracts.protocols, contracts.schemas, contracts.export, contracts.compat"` 成功。
- [ ] `python -c "import contracts; print(contracts.__all__)"` 输出包含 `core`、`protocols`、`schemas`、`__version__`。
- [ ] `python -m contracts.export` 抛 `NotImplementedError`（占位），不抛 `ModuleNotFoundError`。
- [ ] `python -m contracts.compat` 抛 `NotImplementedError`（占位），不抛 `ModuleNotFoundError`。
- [ ] 所有 `__init__.py` 均有中文 docstring。
- [ ] 不存在 `src/contracts/legacy.py`、`src/contracts/utils.py` 等未在 §14 中定义的顶层文件。

#### 验证命令
```bash
cd /Users/fanjie/Desktop/Cowork/project-ult/contracts
source .venv/bin/activate
python -c "import contracts, contracts.core, contracts.protocols, contracts.schemas, contracts.export, contracts.compat; print('ok')"
python -c "import contracts; print(contracts.__all__, contracts.__version__)"
( python -m contracts.export; echo "exit=$?" ) 2>&1 | grep -E "NotImplementedError|exit="
```

#### 依赖
依赖 #ISSUE-001（pyproject.toml src 布局与 Python 3.12 依赖）

---

### ISSUE-003: 版本号常量与 ContractVersionEntry 骨架
**labels**: P0, infrastructure, milestone-0, ready

#### 背景与目标
§9.1 把 `ContractVersionEntry` 列为持久层对象，§16.3 要求 breaking change 必须显式升级主版本。阶段 0 要求有 `0.1.0` 初始版本号（§21）。本 issue 提供唯一版本常量和最小 `ContractVersionEntry` 数据结构，供后续 export/compat 写入和 README 引用。

#### 所属模块
contracts / `contracts.core.version`

#### 实现范围
- 新增 `src/contracts/core/version.py`，定义模块常量 `__version__: str = "0.1.0"`。
- 在同文件新增 Pydantic v2 模型 `ContractVersionEntry`，字段：`version: str`、`released_at: datetime`、`compatibility_note: str = ""`、`breaking: bool = False`。
- 同文件暴露 `CURRENT_VERSION_ENTRY: ContractVersionEntry`，默认值：`version=__version__`、`released_at=datetime(2026, 4, 15, tzinfo=timezone.utc)`、`compatibility_note="初始骨架版本"`、`breaking=False`。
- 在 `src/contracts/core/__init__.py` 中 re-export `__version__`、`ContractVersionEntry`、`CURRENT_VERSION_ENTRY`。
- 在 `src/contracts/__init__.py` 中把占位 `__version__` 替换为 `from contracts.core.version import __version__`。
- 新增 `docs/CHANGELOG.md`，首条记录 `0.1.0 — 2026-04-15 — 初始骨架版本`。

#### 不在本次范围
- 不实现 `SchemaArtifact`、`CompatibilityRule` 模型（归阶段 1/2）。
- 不实现兼容性检查逻辑（阶段 2）。
- 不登记任何 Ex / formal object（阶段 1）。
- 不写 TOML / YAML 形式的版本存储（§10.2 允许 Python 常量即可）。

#### 关键交付物
- `contracts.core.version.__version__ == "0.1.0"`。
- `ContractVersionEntry(BaseModel)`：
  - `version: str`
  - `released_at: datetime`（必须 timezone-aware）
  - `compatibility_note: str = ""`
  - `breaking: bool = False`
- `CURRENT_VERSION_ENTRY` 常量，`version == __version__`。
- `contracts.__version__ == "0.1.0"`。
- `docs/CHANGELOG.md` 存在，至少含一条。

#### 验收标准
- [ ] `python -c "import contracts; assert contracts.__version__ == '0.1.0'"` 成功。
- [ ] `python -c "from contracts.core import ContractVersionEntry, CURRENT_VERSION_ENTRY; assert CURRENT_VERSION_ENTRY.version == '0.1.0'"` 成功。
- [ ] `ContractVersionEntry(version='0.2.0', released_at='not-a-date')` 触发 Pydantic 校验失败。
- [ ] `CURRENT_VERSION_ENTRY.released_at.tzinfo is not None`。
- [ ] `docs/CHANGELOG.md` 至少包含字符串 `0.1.0` 与 `2026-04-15`。
- [ ] `pyproject.toml` 的 `[project].version` 与 `contracts.__version__` 完全一致（都是 `0.1.0`）。

#### 验证命令
```bash
cd /Users/fanjie/Desktop/Cowork/project-ult/contracts
source .venv/bin/activate
python -c "import contracts; from contracts.core import ContractVersionEntry, CURRENT_VERSION_ENTRY; assert contracts.__version__ == CURRENT_VERSION_ENTRY.version == '0.1.0'; print('ok')"
python -c "from contracts.core import ContractVersionEntry; import pydantic; 
try:
    ContractVersionEntry(version='x', released_at='not-a-date')
    raise SystemExit('should fail')
except pydantic.ValidationError:
    print('validation ok')"
grep -q "0.1.0" docs/CHANGELOG.md && echo "changelog ok"
```

#### 依赖
依赖 #ISSUE-002（需要 `contracts.core` 包存在）

---

### ISSUE-004: 编写 README / MODULE_SPEC / TESTPLAN 骨架
**labels**: P0, infrastructure, milestone-0, ready

#### 背景与目标
§21 阶段 0 交付物明确列出 README、MODULE_SPEC、TESTPLAN。当前 README 为 scaffold 默认内容，且没有 MODULE_SPEC 与 TESTPLAN。本 issue 补齐三份文档，明确 `contracts` 定位（§1）、术语（§3）、边界（§5.4）、测试策略（§18），为后续 issue 的 reviewer 和自动化脚本提供稳定参考。

#### 所属模块
contracts / 文档（`README.md`、`docs/MODULE_SPEC.md`、`docs/TESTPLAN.md`）

#### 实现范围
- 重写 `README.md`：概述 §1 一句话定义、§5.1 架构位置图、`pip install -e .[dev]` 快速开始、与 §4.2 非目标警告。
- 新增 `docs/MODULE_SPEC.md`：严格复用 §3 术语表、§14 模块拆分、§16 API/CLI 接口合同、§9.3 核心对象字段表。
- 新增 `docs/TESTPLAN.md`：直接引用 §18.1~§18.4，列出单元、集成、契约、兼容四类测试各自期望的最小用例；列出 §19 性能指标目标值。
- 在 README 顶部加 “合同真相源：`src/contracts/schemas`；导出产物：`artifacts/json_schema/`（阶段 2 生成）” 的显著提示。
- 所有文档用中文。
- 在 README 末尾加指向 `docs/contracts.project-doc.md`、`docs/CHANGELOG.md`、`CLAUDE.md`、`AGENTS.md` 的链接。

#### 不在本次范围
- 不编写具体 schema 字段详细文档（留给 §20.1 实际模型实现时同步完成）。
- 不写 Dagster、CI 配置说明（属于 orchestrator / CI 脚本职责）。
- 不重复抄写 §25 自动化规则（放在 CLAUDE.md / AGENTS.md 已够）。
- 不生成任何 Avro 说明（§4.2）。

#### 关键交付物
- `README.md` 覆盖：项目定位、依赖、安装、目录结构、引用 §1/§4.2/§5.1。
- `docs/MODULE_SPEC.md` 覆盖：术语表、模块拆分、API/CLI 接口、核心对象字段摘要。
- `docs/TESTPLAN.md` 覆盖：单元 / 集成 / 契约 / 兼容四类测试列表、§19 指标。
- 每份文档在文件头写入 `> 文档状态: Draft` 与 `> 版本: 0.1.0` 元信息。
- 三份文件纯文本 + 标准 Markdown，不含图片或外部图床引用。

#### 验收标准
- [ ] `README.md` 包含字符串 `contracts` 与 `0.1.0` 与 `pip install -e .[dev]`。
- [ ] `docs/MODULE_SPEC.md` 包含字符串 `Ex-0`、`Ex-1`、`Ex-2`、`Ex-3`、`Formal Object`、`Ingest Metadata`。
- [ ] `docs/TESTPLAN.md` 包含字符串 `JSON Schema 全量导出耗时`、`< 5 秒`、`< 10 秒`。
- [ ] 三份文件均不含 Avro 作为维护目标的表述（只允许“CI 自动导出产物”）。
- [ ] 三份文件均以 `> 文档状态` 开头作为首行 blockquote。
- [ ] `ls docs/*.md` 至少列出 `contracts.project-doc.md`、`CHANGELOG.md`、`MODULE_SPEC.md`、`TESTPLAN.md`。

#### 验证命令
```bash
cd /Users/fanjie/Desktop/Cowork/project-ult/contracts
grep -l "pip install -e .\[dev\]" README.md
grep -c "Ex-0\|Ex-1\|Ex-2\|Ex-3" docs/MODULE_SPEC.md
grep "< 5 秒\|< 10 秒" docs/TESTPLAN.md
head -1 README.md docs/MODULE_SPEC.md docs/TESTPLAN.md
ls docs/
```

#### 依赖
依赖 #ISSUE-003（README / MODULE_SPEC 引用版本号 `0.1.0`）

---

### ISSUE-005: 骨架冒烟测试与最小 CI 配置
**labels**: P0, infrastructure, milestone-0, ready, testing

#### 背景与目标
阶段 0 退出条件（§21）是“其他模块可以 import 空骨架”，必须通过自动化测试持续验证。本 issue 提供最小单元测试 + 一个可执行的 CI 入口脚本，让后续 issue 在合并前能跑通 `pytest`，避免阶段 1 合同模型一来就踩 import 错误。

#### 所属模块
contracts / `tests/`、`scripts/ci.sh`

#### 实现范围
- 新增 `tests/__init__.py`（空文件）与 `tests/test_skeleton_imports.py`。
- 测试内容：
  - `test_package_imports`：顺序 import `contracts`、`contracts.core`、`contracts.protocols`、`contracts.schemas`、`contracts.export`、`contracts.compat`。
  - `test_version_constant`：断言 `contracts.__version__ == "0.1.0"` 且等于 `contracts.core.CURRENT_VERSION_ENTRY.version`。
  - `test_cli_entrypoints_registered`：通过 `importlib.metadata.entry_points(group="console_scripts")` 查到 `contracts-export` 和 `contracts-compat`；若 entry point 系统不可用则 fallback 到 `python -m contracts.export` 能 import。
  - `test_no_business_deps`：在 `contracts` 包内 grep 不得出现对 `data_platform`、`main_core`、`graph_engine`、`entity_registry`、`reasoner_runtime`、`orchestrator` 的 import（用 `ast` 遍历 `src/contracts/` 实现）。
- 新增 `scripts/ci.sh`：
  ```
  #!/usr/bin/env bash
  set -euo pipefail
  pip install -e .[dev]
  pytest -q
  ```
  赋予可执行权限。
- 在 `docs/TESTPLAN.md` 中追加一节“阶段 0 冒烟测试”引用本 issue 的用例名。

#### 不在本次范围
- 不接入 GitHub Actions workflow（由后续基础设施 issue 决定 CI 平台）。
- 不覆盖 schema 模型（无模型，留给阶段 1）。
- 不做性能或 breaking change 检查（阶段 2）。
- 不引入 mypy / ruff / black 等工具，保持 §15 的最低依赖。

#### 关键交付物
- `tests/test_skeleton_imports.py` 至少 4 个 test 函数。
- `scripts/ci.sh` 可执行、返回 0。
- `test_no_business_deps` 使用 `ast.parse` 检查 `src/contracts/` 下所有 `.py`，检测到业务模块 import 即 fail。
- 对模糊情况的默认行为：若 `contracts.export.__main__.main` 抛 `NotImplementedError`，`test_cli_entrypoints_registered` 应只检查入口注册，不调用 main；若 `importlib.metadata` 查不到 entry point（例如未 `pip install -e`），测试应 skip 并附说明。
- README 中新增“跑测试”段落：`bash scripts/ci.sh`。

#### 验收标准
- [ ] `pytest -q` 在全新 venv 中通过率 100%，`tests/test_skeleton_imports.py` 收集到 ≥4 个用例。
- [ ] `bash scripts/ci.sh` 退出码 0。
- [ ] 手动在 `src/contracts/core/version.py` 中加一行 `import data_platform`，重跑 `pytest`，`test_no_business_deps` 必须失败（回滚该改动后恢复）。
- [ ] `scripts/ci.sh` 有执行权限（`test -x scripts/ci.sh`）。
- [ ] `contracts-export` 与 `contracts-compat` 两个 console script 均已注册（`pip show -f project-ult-contracts` 或 `importlib.metadata.entry_points` 可见）。
- [ ] `test_cli_entrypoints_registered` 在 entry point 缺失时走 `pytest.skip` 分支并附 reason，不 silent pass。

#### 验证命令
```bash
cd /Users/fanjie/Desktop/Cowork/project-ult/contracts
source .venv/bin/activate
bash scripts/ci.sh
pytest -q tests/test_skeleton_imports.py -v
python -c "from importlib.metadata import entry_points; eps=entry_points(group='console_scripts'); print([e.name for e in eps if e.name.startswith('contracts-')])"
```

#### 依赖
依赖 #ISSUE-002（需要包骨架）, 依赖 #ISSUE-003（测试引用 `__version__`）

---

## 阶段 1：核心合同冻结

**目标**：冻结 Ex-0~Ex-3、formal objects、cycle 元数据与核心协议，使 `data-platform`、`main-core`、`subsystem-sdk` 可直接消费。
**前置依赖**：阶段 0 全部完成

### ISSUE-006: 共享枚举与类型基元
**labels**: P0, feature, milestone-1
**摘要**: 在 `contracts.core` 下实现 `ExType`、`Direction`、`Severity`、`Zone` 等共享枚举以及通用类型别名（`EntityId`、`SubsystemId` 等），为 Ex / formal object 模型提供统一底层类型。
**依赖**: #ISSUE-005（阶段 0 骨架全部 ready）

---

### ISSUE-007: 错误码注册表 contracts.errors
**labels**: P0, feature, milestone-1
**摘要**: 实现 §9.1 的 `ErrorCodeRegistry`，包含枚举式错误码、对应中文描述、`ContractError` 异常基类，供所有下游统一抛错。
**依赖**: #ISSUE-006（复用 enum 基础工具）

---

### ISSUE-008: Ex-0 Metadata / 心跳 schema
**labels**: P0, feature, milestone-1
**摘要**: 按 §16.3 冻结 `Ex-0` Pydantic 模型，字段至少包含 `subsystem_id`、`version`、`heartbeat_at`、`status`、`last_output_at`、`pending_count`；禁止混入 `submitted_at` / `ingest_seq`。
**依赖**: #ISSUE-006（ExType 枚举）, #ISSUE-007（错误码）

---

### ISSUE-009: Ex-1 Candidate Facts schema
**labels**: P0, feature, milestone-1
**摘要**: 冻结 `Ex-1` Pydantic 模型，字段至少含 `fact_id`、`entity_id`、`fact_type`、`fact_content`、`confidence`、`source_reference`、`extracted_at`、`subsystem_id`；严格剥离 Ingest Metadata。
**依赖**: #ISSUE-008（Ex 层基类 / 公共字段）

---

### ISSUE-010: Ex-2 Candidate Signals schema
**labels**: P0, feature, milestone-1
**摘要**: 冻结 `Ex-2` Pydantic 模型，字段至少含 `signal_id`、`signal_type`、`direction`、`magnitude`、`affected_entities`、`affected_sectors`、`time_horizon`、`evidence`、`confidence`、`subsystem_id`。
**依赖**: #ISSUE-009（复用 Ex 层基类与 `Direction` 枚举）

---

### ISSUE-011: Ex-3 Candidate Graph Deltas schema
**labels**: P0, feature, milestone-1
**摘要**: 冻结 `Ex-3` Pydantic 模型，字段至少含 `delta_id`、`delta_type`、`source_node`、`target_node`、`relation_type`、`properties`、`evidence`、`subsystem_id`。
**依赖**: #ISSUE-010（复用 Ex 层基类）

---

### ISSUE-012: Formal objects schema 族
**labels**: P0, feature, milestone-1
**摘要**: 冻结 §16.3 列出的 formal objects：`world_state_snapshot`、`official_alpha_pool`、`alpha_result_snapshot`、`recommendation_snapshot`、`dashboard_snapshot`、`report`、`audit_record`、`replay_record`；显式拒绝将 `backtest_result` 注册为 formal object。
**依赖**: #ISSUE-006（共享枚举 `Zone`）, #ISSUE-007（错误码）

---

### ISSUE-013: Cycle 元数据对象
**labels**: P0, feature, milestone-1
**摘要**: 实现 cycle 控制所需的元数据对象（cycle_id、phase、开始/结束时间、上一个 cycle 引用等），供 `data-platform` 控制表和 `orchestrator` Gate 判定使用。
**依赖**: #ISSUE-006（时间 / ID 类型别名）

---

### ISSUE-014: DataSourceAdapter 协议
**labels**: P0, feature, milestone-1
**摘要**: 在 `contracts.protocols` 下用 `typing.Protocol` 定义 `DataSourceAdapter`，给出 adapter 必须实现的方法签名与返回类型，供 `data-platform` 落表与 `subsystem-sdk` 落盘消费。
**依赖**: #ISSUE-013（引用 cycle 元数据类型）

---

### ISSUE-015: AlphaAnalyzer 协议与 alpha_result 字段冻结
**labels**: P0, feature, milestone-1
**摘要**: 按 §9.3、§16.3 冻结 `AlphaAnalyzer` 协议：`analyze(stock, context) -> alpha_result`，`alpha_result` 必含 `score`、`direction`、`confidence`、`rationale`、`evidence_refs`、`analyzer_name`、`analyzer_version`；`SinglePromptAnalyzer`、`MultiAgentAnalyzer` 共用同一接口。
**依赖**: #ISSUE-012（formal object `alpha_result_snapshot`）

---

### ISSUE-016: Ex-0~Ex-3 Pydantic 校验单元测试
**labels**: P0, testing, milestone-1
**摘要**: 覆盖 §18.1 要求的 Ex-0~Ex-3 字段必填 / 非法值 / 枚举约束 / 禁止 `submitted_at` 等 Ingest Metadata 出现；每个 Ex 至少 6 条用例。
**依赖**: #ISSUE-008, #ISSUE-009, #ISSUE-010, #ISSUE-011

---

### ISSUE-017: Formal objects 与 cycle 元数据单元测试
**labels**: P0, testing, milestone-1
**摘要**: 覆盖 §18.1 formal objects 校验、`backtest_result` 被拒绝注册为 formal object、cycle 元数据字段约束。
**依赖**: #ISSUE-012, #ISSUE-013

---

### ISSUE-018: 协议对象结构测试（DataSourceAdapter / AlphaAnalyzer）
**labels**: P0, testing, milestone-1
**摘要**: 用 `typing.get_type_hints`、`runtime_checkable` 校验 adapter/analyzer 协议方法签名与返回字段；用 fake 实现验证 `alpha_result` 必填字段。
**依赖**: #ISSUE-014, #ISSUE-015

---

## 阶段 2：导出与兼容检查

**目标**：提供 JSON Schema 自动导出与兼容性检查能力，让 CI 可拦截 breaking change。
**前置依赖**：阶段 1 全部完成

### ISSUE-019: JSON Schema 导出 CLI
**labels**: P1, feature, milestone-2
**摘要**: 在 `contracts.export` 中实现 `python -m contracts.export --out artifacts/json_schema --version <ver>`，遍历 `contracts.schemas` 全部 Pydantic 模型输出 JSON Schema；对齐 §19 性能目标（<5 秒）。
**依赖**: #ISSUE-016, #ISSUE-017, #ISSUE-018（schema/协议已冻结）

---

### ISSUE-020: CompatibilityRule 与兼容性检查 CLI
**labels**: P1, feature, milestone-2
**摘要**: 在 `contracts.compat` 中实现 `CompatibilityRule` 模型与 `python -m contracts.compat --baseline <ver>` CLI，识别新增字段、删除字段、改类型等事件；默认仅允许 backward compatible（§16.3）。
**依赖**: #ISSUE-019（使用导出 JSON Schema 作为输入）

---

### ISSUE-021: Contract examples 与下游夹具
**labels**: P1, testing, milestone-2
**摘要**: 在 `fixtures/` 下为每个 Ex / formal object / cycle 对象提供最小合法样例与反例，供 `data-platform`、`subsystem-sdk`、`main-core` 做 contract test。
**依赖**: #ISSUE-019（确保 schema 与样例一致可导出）

---

### ISSUE-022: CI 集成与 breaking change 拦截
**labels**: P1, infrastructure, milestone-2
**摘要**: 扩展 `scripts/ci.sh`，依次执行 `pytest`、`python -m contracts.export` 与 `python -m contracts.compat --baseline <上一个发布版本>`；出现 breaking change 时返回非 0 退出码。
**依赖**: #ISSUE-020, #ISSUE-021

---

### ISSUE-023: 性能与验收冒烟
**labels**: P1, testing, milestone-2
**摘要**: 按 §19 给出的 `< 5 秒`（导出）与 `< 10 秒`（兼容检查）阈值新增基线计时测试，并在 `docs/TESTPLAN.md` 记录实际数据，作为阶段 2 退出条件证据。
**依赖**: #ISSUE-022

---
