# 项目任务拆解

> 对应项目文档：`docs/main-core.project-doc.md`（v0.1.2）
> 里程碑映射依据：项目文档 §21 实施路线图 + §25.2 自动化推荐顺序
> 模块边界基线：§4（OWN/BAN）、§5.4（不可协商约束）、§14（模块拆分）

---

## 阶段 0：包骨架与 formal 对象基线（milestone-0）

**目标**：落地 `main_core.l1`-`main_core.l8` 单项目强 package 骨架、六类 formal object 的 Pydantic schema，以及 `AnalyzerInterface` / `WorldStatePolicy` / `RecommendationConstraintProvider` 三类协议接口，为后续 L1-L8 实现提供零分歧基线。
**前置依赖**：无

### ISSUE-001: 搭建 main-core 单项目强 package 骨架与边界静态检查
**labels**: P0, infrastructure, milestone-0

#### 背景与目标
按项目文档 §5.4 与 §14，`main-core` 必须在**同一个 Python 项目内**保留 L1-L8 的强 package 边界，不允许拆成 8 个子项目，也不允许跨层反向 import。本 issue 负责把当前空骨架扩展为带有 `main_core.l1_l2_basis` … `main_core.l8_publish` 七个子 package、共享 `main_core.common` 基础包、以及最关键的 **package 边界静态 lint** 的可运行 Python 项目。这是后续所有 formal object、analyzer、publish bundle 实现的承载基底，若 package 边界不先硬化，§6.2 反模式（L3 反向 import L6/L7）几乎必然发生。本 issue 同时落地 `pytest` / `ruff` / `import-linter` 的最小 CI 脚本，供后续每一个 issue 复用。

#### 所属模块
- primary writable paths（本 issue 可写入）：
  - `pyproject.toml`
  - `src/main_core/__init__.py`
  - `src/main_core/common/__init__.py`, `src/main_core/common/types.py`, `src/main_core/common/errors.py`
  - `src/main_core/l1_l2_basis/__init__.py`
  - `src/main_core/l3_features/__init__.py`
  - `src/main_core/l4_world_state/__init__.py`
  - `src/main_core/l5_universe/__init__.py`
  - `src/main_core/l6_alpha/__init__.py`
  - `src/main_core/l7_recommendation/__init__.py`
  - `src/main_core/l8_publish/__init__.py`
  - `tests/__init__.py`, `tests/test_package_boundaries.py`, `tests/conftest.py`
  - `.importlinter`（或 `setup.cfg` 内 `[importlinter]` 段）
  - `ruff.toml`
  - `scripts/check_boundaries.sh`
- adjacent read-only / integration paths（可读不可写）：
  - `docs/main-core.project-doc.md`（参考 §5.4、§14）
  - `CLAUDE.md`（项目 OWN/BAN 约束）
- off-limits paths（本 issue 禁止触碰，留给后续 issue）：
  - `src/main_core/l*/` 内的任何业务实现文件（本 issue 只允许空 `__init__.py` + 占位 `README`）
  - 任何 `schemas.py` / `protocols.py`（归 ISSUE-002 / ISSUE-003）
  - `data-platform` / `graph-engine` / `reasoner-runtime` / `audit-eval` 相关 stub（跨模块禁区）

#### 实现范围
- **项目元数据**：
  - `pyproject.toml`：在现有基础上新增 `[project.optional-dependencies]`，`dev = ["pytest>=8", "pytest-cov>=5", "ruff>=0.5", "import-linter>=2.0", "pydantic>=2.6"]`；`[tool.setuptools.packages.find]` 指向 `src`；`[tool.setuptools.package-dir] = {"" = "src"}`。
- **共享基础包**：
  - `src/main_core/common/types.py`：`CycleId = NewType("CycleId", str)`、`EntityId = NewType("EntityId", str)`、`Regime = Literal["risk_off", "neutral", "risk_on"]`（占位，实际取值可在 §9 对照后修正）。
  - `src/main_core/common/errors.py`：`class MainCoreError(Exception)`、`class InconclusiveError(MainCoreError)`、`class ManifestPublishError(MainCoreError)`、`class BoundaryViolationError(MainCoreError)`。
- **L 包骨架**（每个都仅放空 `__init__.py` + `_README.md` 指明职责与 §14 行号）：
  - `src/main_core/l1_l2_basis/__init__.py` 等七个。
- **边界静态检查**：
  - `.importlinter`：两类 contract——（a）`layered`：`l1_l2_basis < l3_features < l4_world_state < l5_universe < l6_alpha < l7_recommendation < l8_publish`，上层可 import 下层，下层禁止 import 上层；（b）`forbidden`：`l3_features` 禁止 import `l6_alpha`、`l7_recommendation`、`l8_publish`；`l4_world_state` 禁止 import `l8_publish`。
  - `ruff.toml`：启用 `E,F,I,B,UP,PL`，`line-length = 100`，`target-version = "py311"`。
- **测试与脚本**：
  - `tests/test_package_boundaries.py`：`test_all_layers_importable()`（逐个 `import main_core.l*`）、`test_importlinter_contracts_pass()`（`subprocess` 调 `lint-imports` 并断言 rc=0）。
  - `scripts/check_boundaries.sh`：依次执行 `ruff check .`、`lint-imports`、`pytest tests/test_package_boundaries.py`。

#### 不在本次范围
- 不实现任何 L1-L8 的业务函数（如 `build_feature_signal_bundle`、`derive_world_state` 等）——归 ISSUE-004 起的后续 issue。
- 不定义任何 Pydantic formal object schema（`WorldStateSnapshot` 等）——归 ISSUE-002。
- 不定义 `AnalyzerInterface` / `WorldStatePolicy` 等协议类——归 ISSUE-003。
- 不新增 `data-platform` / `reasoner-runtime` / `graph-engine` / `audit-eval` 的 stub 或 adapter——跨模块边界，按 §4.2 属于禁区。
- 不配置 GitHub Actions 工作流文件——本 issue 只需本地 `scripts/check_boundaries.sh` 可跑；CI 文件留给后续 DevOps 类 issue（一旦需要新增则单独立 issue）。
- 不动 `CLAUDE.md` / `AGENTS.md`（项目约束源文件）。

#### 关键交付物
- `pyproject.toml`：新增 `dev` optional dependencies 与 `[tool.setuptools.packages.find] where = ["src"]`。
- `src/main_core/common/types.py`：导出 `CycleId`、`EntityId`、`Regime` 三个类型别名。
- `src/main_core/common/errors.py`：导出 `MainCoreError`、`InconclusiveError`、`ManifestPublishError`、`BoundaryViolationError`。
- 七个 `src/main_core/l*/__init__.py`：每个包含 `"""L? package — see §14 of main-core.project-doc.md."""` 的单行 docstring，无实际符号。
- `.importlinter`：包含 `layered` 与 `forbidden` 两条 contract，根 package = `main_core`。
- `ruff.toml`：`line-length = 100`、`target-version = "py311"`、`select = ["E","F","I","B","UP","PL"]`。
- `tests/test_package_boundaries.py`：≥ 3 个测试（importable / importlinter pass / forbidden contract triggers on synthetic violation）。
- `scripts/check_boundaries.sh`：可执行脚本，按顺序跑 ruff → lint-imports → pytest 边界测试。
- 执行 `pip install -e .[dev]` 后 `scripts/check_boundaries.sh` 必须 exit code 0。

#### 验收标准
**骨架可用性：**
- [ ] `python -c "import main_core.l1_l2_basis, main_core.l3_features, main_core.l4_world_state, main_core.l5_universe, main_core.l6_alpha, main_core.l7_recommendation, main_core.l8_publish"` 无报错。
- [ ] `python -c "from main_core.common.errors import MainCoreError, InconclusiveError, ManifestPublishError, BoundaryViolationError"` 无报错。
- [ ] `pip install -e .[dev]` 可成功在 Python 3.11/3.12 环境安装。

**边界静态约束：**
- [ ] `lint-imports` 在当前骨架上 exit 0。
- [ ] 在临时添加一条违反 layered 的 import（例如让 `l3_features/__init__.py` `from main_core.l6_alpha import *`）后，`lint-imports` exit 非 0；该反例在 PR 合入前必须回滚。
- [ ] `ruff check src tests` exit 0。

**测试：**
- [ ] `pytest tests/test_package_boundaries.py` 至少 3 个用例全部通过。
- [ ] 所有新建测试运行时间 < 10 秒。

**文档：**
- [ ] 每个 `l*/__init__.py` 的 docstring 明确指向 §14 对应职责描述。
- [ ] `scripts/check_boundaries.sh` 在 README 或 AGENTS.md 中被引用（只追加，不重写）。

#### 验证命令
```bash
# 安装依赖
pip install -e .[dev]

# Unit tests — 本 issue 专属
pytest tests/test_package_boundaries.py -v

# Integration check — 导入全部 L 包
python -c "import main_core.l1_l2_basis, main_core.l3_features, main_core.l4_world_state, main_core.l5_universe, main_core.l6_alpha, main_core.l7_recommendation, main_core.l8_publish; print('ok')"

# Boundary lint
lint-imports

# 一键回归
bash scripts/check_boundaries.sh
```

#### 依赖
无前置依赖

---

### ISSUE-002: 定义六类 formal object 与运行时 bundle 的 Pydantic schema
**labels**: P0, feature, milestone-0

#### 背景与目标
按项目文档 §9 与 §20.1，`main-core` OWN 的正式业务对象包括 `WorldStateSnapshot`、`OfficialAlphaPool`、`AlphaResultSnapshot`、`RecommendationSnapshot`、`DashboardSnapshot`、`FormalReport` 六类 formal object，以及 `FeatureSignalBundle` 与 `PublishBundle` 两类跨层运行时对象，加上 `OverrideRecord`。这些对象是 L1-L8 各层之间唯一的显式契约载体（§6.1 原则 3），若 schema 不先固化，后续 L3/L4/L6/L7 的实现会出现字段漂移。本 issue 只做 **Pydantic v2 model + 字段级校验 + JSON 序列化 + 单元测试**，不实现任何生成这些对象的业务逻辑。字段命名与语义严格对齐 §9.3 每张小表；其中三条硬约束必须在 validator 层就拦下：`llm_delta ∈ {-1,0,+1}`（§9 WorldStateSnapshot）、`analyzer_type ∈ {"single_prompt_v1","multi_agent_v1"}` 且 P2 阶段默认 `single_prompt_v1`（§16.3）、`official_alpha_pool.selected_entities` 长度 ≤ `official_alpha_pool_capacity`（§9 OfficialAlphaPool）。

#### 所属模块
- primary writable paths：
  - `src/main_core/common/schemas/__init__.py`
  - `src/main_core/common/schemas/feature_bundle.py`
  - `src/main_core/common/schemas/world_state.py`
  - `src/main_core/common/schemas/pool.py`
  - `src/main_core/common/schemas/alpha.py`
  - `src/main_core/common/schemas/recommendation.py`
  - `src/main_core/common/schemas/dashboard.py`
  - `src/main_core/common/schemas/report.py`
  - `src/main_core/common/schemas/publish.py`
  - `src/main_core/common/schemas/override.py`
  - `tests/schemas/__init__.py`
  - `tests/schemas/test_feature_bundle.py`
  - `tests/schemas/test_world_state.py`
  - `tests/schemas/test_pool.py`
  - `tests/schemas/test_alpha.py`
  - `tests/schemas/test_recommendation.py`
  - `tests/schemas/test_dashboard_report.py`
  - `tests/schemas/test_publish.py`
- adjacent read-only paths：
  - `src/main_core/common/types.py`、`src/main_core/common/errors.py`（来自 ISSUE-001）
  - `docs/main-core.project-doc.md` §9、§13、§16.3
- off-limits paths：
  - `src/main_core/l*/`（任何具体层的业务实现）
  - `src/main_core/common/schemas/protocols.py`（归 ISSUE-003）
  - 任何 `data-platform` / `contracts` 外部仓库的 schema 文件（按 §4.2 归 `contracts` 模块，本模块只能引用不能重写）

#### 实现范围
- **基础类型**（`common/schemas/__init__.py`）：
  - `re-export` 每个 model；提供 `class FormalObjectBase(pydantic.BaseModel)`：`model_config = ConfigDict(extra="forbid", frozen=True, strict=True)`、`def to_json(self) -> str`、`@classmethod def from_json(cls, s: str) -> Self`。
- **L3 运行时**（`feature_bundle.py`）：
  - `class FeatureSignalBundle(FormalObjectBase)`：字段 `cycle_id: CycleId`、`entity_id: EntityId`、`feature_values: dict[str, float]`、`signal_values: dict[str, Any]`、`graph_features: dict[str, Any]`、`feature_weight_multiplier: dict[str, float]`、`generated_at: datetime`。
  - validator：`feature_weight_multiplier` 所有 value 必须 `> 0`。
- **L4 formal**（`world_state.py`）：
  - `class WorldStateSnapshot(FormalObjectBase)`：`cycle_id`、`baseline_regime: Regime`、`llm_delta: Literal[-1,0,1]`、`final_regime: Regime`、`llm_rationale: str`、`actual_model_used: str`、`actual_provider: str`、`fallback_path: list[str]`。
  - validator：`final_regime` 必须与 `baseline_regime` + `llm_delta` 在 regime 序列上一致；越界抛 `ValueError`。
- **L5 formal**（`pool.py`）：
  - `class OfficialAlphaPool(FormalObjectBase)`：`cycle_id`、`observation_pool_size: int`、`official_alpha_pool_capacity: int = 100`、`selected_entities: list[EntityId]`、`added_entities: list[EntityId]`、`removed_entities: list[EntityId]`、`freeze_reason_map: dict[EntityId, str]`。
  - validator：`len(selected_entities) <= official_alpha_pool_capacity`；`official_alpha_pool_capacity > 0`。
- **L6 formal**（`alpha.py`）：
  - `AnalyzerType = Literal["single_prompt_v1","multi_agent_v1"]`
  - `AlphaStatus = Literal["ok","inconclusive"]`
  - `class AlphaResultSnapshot(FormalObjectBase)`：`cycle_id`、`entity_id`、`analyzer_type: AnalyzerType`、`score: float | None`、`confidence: float`、`rationale: str`、`similar_cases: list[dict]`、`status: AlphaStatus`。
  - validator：当 `status == "inconclusive"` 时 `score is None`；P2 默认 `analyzer_type = "single_prompt_v1"`（通过工厂函数 `single_prompt_result(...)`）。
- **L7 formal**（`recommendation.py`）：
  - `ActionType = Literal["buy","hold","reduce","inconclusive"]`
  - `class RecommendationSnapshot(FormalObjectBase)`：`cycle_id`、`entity_id`、`action_type: ActionType`、`rating: str | None`、`confidence: float | None`、`triggered_by: Literal["system","human_decision"]`、`override_applied: bool`、`constraints_applied: dict[str, Any]`。
  - validator：`action_type == "inconclusive"` ⇒ `confidence is None`。
- **L8 formal**（`dashboard.py`、`report.py`）：按 §9.3 字段逐一映射，`summary_cards` / `narrative_sections` / `appendix_refs` 均为 `dict[str, Any]`（后续 L8 issue 再收敛）。
- **Publish/Override**（`publish.py`、`override.py`）：
  - `class PublishBundle(FormalObjectBase)`：`cycle_id`、`formal_objects: dict[str, Any]`、`manifest_candidate: dict[str, Any]`、`audit_payload: dict[str, Any]`、`retrospective_seed: dict[str, Any]`。
  - `class OverrideRecord(FormalObjectBase)`：`cycle_id`、`entity_id`、`submitted_by: str`、`action_type: ActionType`、`rationale: str`、`submitted_at: datetime`。
- **测试**：每个 model 至少 1 条 happy-path 构造、1 条字段缺失/类型错误、1 条 validator 触发（共 8 个测试文件，≥ 24 条 assert）。

#### 不在本次范围
- 不实现任何生成这些对象的业务函数（`build_feature_signal_bundle`、`derive_world_state` 等）——归 milestone-1/2。
- 不实现 `AnalyzerInterface` 协议类——归 ISSUE-003。
- 不对接 `contracts` 外部仓库或做 schema 注册——按 §4.2 属跨模块边界。
- 不写 formal publish 的 Iceberg 表结构——归 `data-platform`（§4.2 禁区）。
- 不在 schema 内嵌入业务规则（如 regime 状态机 transition 全表）——validator 只校 §9 明文硬约束。

#### 关键交付物
- 10 个 schema 文件，总计 9 个 Pydantic model + 1 个 `__init__.py` re-export。
- `FormalObjectBase` 基类：`extra="forbid"`, `frozen=True`, `strict=True`。
- 关键 validator：
  - `WorldStateSnapshot`: 拒绝 `llm_delta ∉ {-1,0,1}`。
  - `AlphaResultSnapshot`: 拒绝未知 `analyzer_type`，`inconclusive` ⇒ `score is None`。
  - `OfficialAlphaPool`: 拒绝 `len(selected_entities) > official_alpha_pool_capacity`。
- `to_json()` / `from_json()`：round-trip 等价。
- 8 个测试文件，总计 ≥ 24 个测试用例。

#### 验收标准
**Schema 正确性：**
- [ ] 9 个 model 都继承自 `FormalObjectBase`，均 `frozen=True` 且 `extra="forbid"`。
- [ ] 每个 model 的字段名、类型与 §9.3 一一对应（评审时逐字段比对）。
- [ ] `WorldStateSnapshot(llm_delta=2, ...)` 抛 `ValidationError`。
- [ ] `OfficialAlphaPool(selected_entities=[...101 个], official_alpha_pool_capacity=100)` 抛 `ValidationError`。
- [ ] `AlphaResultSnapshot(analyzer_type="gpt5_v2", ...)` 抛 `ValidationError`。
- [ ] `AlphaResultSnapshot(status="inconclusive", score=0.5, ...)` 抛 `ValidationError`。

**序列化：**
- [ ] 所有 9 个 model 均通过 `from_json(to_json())` round-trip 相等测试。

**测试：**
- [ ] `pytest tests/schemas -v` 通过，用例数 ≥ 24。
- [ ] 每个 model 至少覆盖 happy / missing / invalid 三类场景。
- [ ] 测试运行 < 15 秒。

**边界：**
- [ ] 无任何 `from main_core.l*` import（schema 不依赖 L 包业务层）。
- [ ] `lint-imports` 依旧通过（不引入新边界违规）。

#### 验证命令
```bash
# Unit tests
pytest tests/schemas -v

# Schema import sanity
python -c "from main_core.common.schemas import FeatureSignalBundle, WorldStateSnapshot, OfficialAlphaPool, AlphaResultSnapshot, RecommendationSnapshot, DashboardSnapshot, FormalReport, PublishBundle, OverrideRecord; print('ok')"

# Boundary regression
lint-imports

# Full regression
pytest -q
```

#### 依赖
依赖 #ISSUE-001（package 骨架与边界 lint 必须先落地才能挂 schema 包）

---

### ISSUE-003: 定义 AnalyzerInterface / WorldStatePolicy / RecommendationConstraintProvider 三类协议接口
**labels**: P0, feature, milestone-0

#### 背景与目标
项目文档 §16.2、§25.2 明确：L6 的可插拔分析、L4 的规则骨架、L7 的 regime/risk 约束必须通过**显式协议接口**暴露，而不是散落在具体实现里。本 issue 负责把这三类协议用 `typing.Protocol` + `abc` 双重方式固定下来，并给出 P2 阶段的最小 `SinglePromptAnalyzerStub`、`DefaultWorldStatePolicyStub`、`NullConstraintProviderStub`——`Stub` 仅做签名占位返回 `NotImplementedError` 或可预期的空对象，供后续 milestone-2 的 issue 替换为真实实现。协议必须满足 §16.3 的三个兼容硬约束：`SinglePromptAnalyzer` 与 `MultiAgentAnalyzer` 必须共享同一 `AnalyzerInterface`；`analyzer_type` 在 P2 默认 `single_prompt_v1`；协议入参出参必须全部使用 ISSUE-002 的 Pydantic schema，不允许裸 dict。本 issue 与 ISSUE-002 合并完成 milestone-0 的"包骨架 + formal object + AnalyzerInterface"三件套（§25.2 第 1 步）。

#### 所属模块
- primary writable paths：
  - `src/main_core/common/protocols/__init__.py`
  - `src/main_core/common/protocols/analyzer.py`
  - `src/main_core/common/protocols/world_state_policy.py`
  - `src/main_core/common/protocols/constraint_provider.py`
  - `src/main_core/common/contexts.py`（放 `AlphaAnalysisContext` 等运行时上下文对象）
  - `src/main_core/l6_alpha/stubs.py`（`SinglePromptAnalyzerStub`）
  - `src/main_core/l4_world_state/stubs.py`（`DefaultWorldStatePolicyStub`）
  - `src/main_core/l7_recommendation/stubs.py`（`NullConstraintProviderStub`）
  - `tests/protocols/__init__.py`
  - `tests/protocols/test_analyzer_interface.py`
  - `tests/protocols/test_world_state_policy.py`
  - `tests/protocols/test_constraint_provider.py`
- adjacent read-only paths：
  - `src/main_core/common/schemas/*`（ISSUE-002 已落地）
  - `docs/main-core.project-doc.md` §11、§16.2、§16.3
- off-limits paths：
  - 任何真实 LLM 调用实现（归 milestone-2 `l6_alpha` 的后续 issue）。
  - `reasoner-runtime` adapter / provider SDK（§4.2 禁区）。
  - `l5_universe` pool selection 逻辑、`l4_world_state` 真实 regime 规则——本 issue 只落 policy 接口。
  - ISSUE-002 schema 文件（本 issue 只 import，不改动）。

#### 实现范围
- **运行时上下文**（`common/contexts.py`）：
  - `class AlphaAnalysisContext(BaseModel)`：`cycle_id`、`entity_id`、`feature_bundle: FeatureSignalBundle`、`world_state: WorldStateSnapshot`、`similar_cases: list[dict]`；`frozen=True`。
  - `class WorldStateInputs(BaseModel)`：`cycle_id`、`feature_bundle: FeatureSignalBundle`、`macro_context: dict[str, Any]`、`graph_impact: dict[str, Any]`。
  - `class RecommendationConstraintInputs(BaseModel)`：`world_state: WorldStateSnapshot`、`risk_context: dict[str, Any]`。
- **AnalyzerInterface**（`protocols/analyzer.py`）：
  - `class AnalyzerInterface(Protocol)`：
    - `analyzer_type: ClassVar[str]`
    - `def analyze(self, context: AlphaAnalysisContext) -> AlphaResultSnapshot: ...`
  - `class AnalyzerBase(ABC)`：`@property @abstractmethod analyzer_type`; `@abstractmethod analyze(...)`——给具体 Analyzer 做继承入口。
- **WorldStatePolicy**（`protocols/world_state_policy.py`）：
  - `class WorldStatePolicy(Protocol)`：
    - `def baseline(self, inputs: WorldStateInputs) -> Regime: ...`
    - `def bound_delta(self, raw_delta: int) -> Literal[-1,0,1]: ...`
    - `def compose(self, baseline: Regime, delta: Literal[-1,0,1]) -> Regime: ...`
- **RecommendationConstraintProvider**（`protocols/constraint_provider.py`）：
  - `class RecommendationConstraintProvider(Protocol)`：
    - `def gate(self, inputs: RecommendationConstraintInputs, candidate: RecommendationSnapshot) -> RecommendationSnapshot: ...`
  - 注释引用 §12.3：Gate 优先于 override。
- **三个 Stub**：每个返回文档字符串中写明"P2 placeholder, wired in milestone-2"；`analyze` 抛 `NotImplementedError("implemented in ISSUE-008")`；`bound_delta` 实际实现 `max(-1, min(1, raw_delta))`（因为这是硬数学约束，可以直接落，不需要业务 context）。
- **测试**：
  - `test_analyzer_interface.py`：用 `isinstance(instance, AnalyzerInterface)` 的 `runtime_checkable` 校验（给 Protocol 加 `@runtime_checkable`）；stub `analyzer_type == "single_prompt_v1"`；`analyze` 抛 `NotImplementedError`。
  - `test_world_state_policy.py`：`bound_delta(3) == 1`、`bound_delta(-2) == -1`、`bound_delta(0) == 0`。
  - `test_constraint_provider.py`：stub `gate(...)` 原样返回输入 candidate（null provider 合同）。

#### 不在本次范围
- 不实现真实的 `SinglePromptAnalyzer`（调用 LLM 的版本）——归 milestone-2 ISSUE-008。
- 不实现真实的 regime 规则骨架或 LLM delta 调用——归 milestone-2 ISSUE-006。
- 不实现 override 业务流程——归 milestone-2 ISSUE-009。
- 不实现 MultiAgentAnalyzer——归 milestone-5。
- 不把 protocol 注册到任何 registry/plugin 机制（如 entry points）——目前三类协议消费方屈指可数，直接构造即可；若后续需要再单独立 issue。
- 不连接 `reasoner-runtime`（§4.2 禁区）。

#### 关键交付物
- `AnalyzerInterface`（Protocol, `@runtime_checkable`）与 `AnalyzerBase`（ABC）。
- `WorldStatePolicy`、`RecommendationConstraintProvider` 两个 Protocol。
- `AlphaAnalysisContext`、`WorldStateInputs`、`RecommendationConstraintInputs` 三个运行时 context model（`frozen=True`）。
- 三个 stub 类，分别放在对应 L 包下（不污染 common）。
- `common/protocols/__init__.py` re-export 全部协议。
- ≥ 9 个单测（三协议各 3 条：签名可 import / stub 行为符合 null 合同 / isinstance runtime 检查）。

#### 验收标准
**协议结构：**
- [ ] `AnalyzerInterface` 带 `@runtime_checkable`，`analyzer_type` 为 `ClassVar[str]`。
- [ ] `SinglePromptAnalyzerStub` 的 `analyzer_type == "single_prompt_v1"` 且是 `AnalyzerInterface` 的 `isinstance`。
- [ ] `WorldStatePolicy.bound_delta` 对任意 `int` 输入返回值严格属于 `{-1,0,1}`。
- [ ] `RecommendationConstraintProvider.gate` 签名明确输入输出均为 Pydantic 对象。

**边界：**
- [ ] `common/protocols/*.py` 不 import 任何 `main_core.l*`（反向依赖硬禁）。
- [ ] 三个 stub 各自放在对应 L 包下（`l4_world_state/stubs.py`、`l6_alpha/stubs.py`、`l7_recommendation/stubs.py`），不跨层摆放。
- [ ] `lint-imports` 通过。

**测试：**
- [ ] `pytest tests/protocols -v` 通过，用例数 ≥ 9。
- [ ] `SinglePromptAnalyzerStub().analyze(...)` 抛 `NotImplementedError`，错误信息包含 `"ISSUE-008"` 字样。
- [ ] `bound_delta` 的边界参数化测试覆盖 `[-5,-2,-1,0,1,2,5]` 共 7 个点。

**文档：**
- [ ] 每个 protocol 的 docstring 引用 §16.2 对应条目。
- [ ] `AnalyzerInterface` docstring 明示"P2 阶段 analyzer_type 固定为 single_prompt_v1（§16.3）"。

#### 验证命令
```bash
# Unit tests
pytest tests/protocols -v

# Protocol import sanity
python -c "from main_core.common.protocols import AnalyzerInterface, WorldStatePolicy, RecommendationConstraintProvider; from main_core.l6_alpha.stubs import SinglePromptAnalyzerStub; assert isinstance(SinglePromptAnalyzerStub(), AnalyzerInterface); print('ok')"

# Boundary regression
lint-imports

# Full regression (schemas + protocols + boundaries)
pytest -q
```

#### 依赖
依赖 #ISSUE-001（package 骨架）, 依赖 #ISSUE-002（运行时 context 与 stub 需要引用 Pydantic formal object schema）

---

## 阶段 1：P2a 纯数据骨架 — L1-L3（milestone-1）

**目标**：按 §21 阶段 0 与 §25.2 第 2 步，落地 `l1_l2_basis` 读取层与 `l3_features` 特征/信号主干，支持在无图谱、无子系统的纯市场数据输入下产出可消费的 `FeatureSignalBundle`，并在 L3 中实现 `feature_weight_multiplier` 的在线写入。
**前置依赖**：阶段 0 完整完成（milestone-0）

### ISSUE-004: 实现 l1_l2_basis 基础数据读取层
**labels**: P0, feature, milestone-1
**摘要**：基于 `data-platform` 提供的 L2 数据读取接口，落地 `main_core.l1_l2_basis` 的对象/市场/日历基础读取函数，产出供 L3 消费的原始数据对象；不直连存储，只经由平台 API。
**所属模块**: `src/main_core/l1_l2_basis/`（writable）；`src/main_core/common/schemas/*`、`src/main_core/common/types.py`（read-only）；禁止修改 `data-platform` 或任何外部仓库的 serving 接口。
**写入边界**: 允许修改 `src/main_core/l1_l2_basis/**`、`tests/l1_l2_basis/**`；禁止修改 `src/main_core/l3_features/**` 及以上任何 L 层。
**实现顺序**: (1) 定义 L2 读取的显式 DTO（`MarketBar`、`CalendarDay`、`EntityMasterRow`）——与 ISSUE-002 formal object 分离；(2) 实现 `read_market_bars(cycle_id)` / `read_calendar(cycle_id)` / `read_entity_master(cycle_id)` 三个函数，依赖注入 `DataPlatformPort` 协议便于 mock；(3) 引入 `DataPlatformPort` 协议（仅为 main-core 内部使用，不污染 common/protocols）；(4) 写入 fixture-based 单测 + 一条使用 fake 的集成烟测。保持单 issue 在 ~1000-1500 行以内。
**依赖**: #ISSUE-001, #ISSUE-002, #ISSUE-003

---

### ISSUE-005: 实现 l3_features 特征/信号主干与 feature_weight_multiplier 在线写入
**labels**: P0, feature, milestone-1
**摘要**：按 §11.1 与 §16.3，落地 `build_feature_signal_bundle(cycle_id)`，完成特征合并、signal bundle 组装、`feature_weight_multiplier` 在线写入并在当轮 `FeatureSignalBundle` 生效；该 multiplier 写入能力必须归 `l3_features` 而非 `audit-eval`（§4.1 OWN）。
**所属模块**: `src/main_core/l3_features/`（writable）；`src/main_core/l1_l2_basis/*`、`src/main_core/common/schemas/feature_bundle.py`（read-only）；禁止修改 `audit-eval` 或任何 multiplier 审计下游。
**写入边界**: 允许修改 `src/main_core/l3_features/**`、`tests/l3_features/**`；禁止修改 `l1_l2_basis` 已经稳定的 API；禁止 import `l4_world_state` 及以上。
**实现顺序**: (1) `multiplier_store.py`：定义 `MultiplierStore` 协议 + `InMemoryMultiplierStore` 默认实现（真实持久化归未来 issue）；(2) `builder.py`：`build_feature_signal_bundle(cycle_id, store, *, graph_impact=None, candidate_signals=None) -> FeatureSignalBundle`，默认 `graph_impact` / `candidate_signals` 为空，保证 P2a 纯数据闭环；(3) `weight_api.py`：`apply_weight_multiplier(cycle_id, updates: dict[str, float]) -> None` 写入当轮并使下一次 `build_*` 生效；(4) 单测覆盖 multiplier 生效 / 越界（负数）拒绝 / 空图谱可跑通。该 issue 必须**单独成单**，§25.1 明确 multiplier 改动单独成 issue。
**依赖**: #ISSUE-004

---

## 阶段 2：P2b L4-L7 正式判断链（milestone-2）

**目标**：按 §21 阶段 1 与 §25.2 第 3 步，打通 `l4_world_state` → `l5_universe` → `l6_alpha`（默认 `SinglePromptAnalyzer`）→ `l7_recommendation` 的正式判断链，生成前四类 formal object 的真实实例，默认走 `single_prompt_v1`。
**前置依赖**：milestone-1 完成，可稳定产出 `FeatureSignalBundle`

### ISSUE-006: 实现 l4_world_state 混合驱动共享状态
**labels**: P0, algorithm, milestone-2
**摘要**：按 §11.2 与 §9 WorldStateSnapshot，落地 `derive_world_state(bundle, policy) -> WorldStateSnapshot`：规则骨架产出 baseline，调用 `reasoner-runtime` 获取结构化 llm_delta，强制 `±1` 上限，合成 final_regime；必须对 LLM 基础设施级失败硬停（§12.3），不允许静默降级。
**所属模块**: `src/main_core/l4_world_state/`（writable）；`src/main_core/common/protocols/world_state_policy.py`、`common/schemas/world_state.py`、`l3_features/*`（read-only）；禁止直连任何 provider SDK，必须通过 `reasoner-runtime` port。
**写入边界**: 允许修改 `src/main_core/l4_world_state/**`、`tests/l4_world_state/**`；删除 ISSUE-003 的 `DefaultWorldStatePolicyStub` 并替换为真实实现。
**实现顺序**: (1) 落地 `rules.py`：规则骨架实现 `WorldStatePolicy.baseline`；(2) 落地 `reasoner_port.py`：定义 `ReasonerPort` 协议（本模块内部 port）+ fake 实现；(3) `service.py`：`derive_world_state` 主流程 + 硬停错误传播（抛 `MainCoreError` 子类）；(4) 强制 `llm_delta ∈ {-1,0,1}` 的入口保护；(5) 测试覆盖越界拒绝 / LLM 失败硬停 / 正常 happy path。
**依赖**: #ISSUE-005

---

### ISSUE-007: 实现 l5_universe 正式池选择与冻结
**labels**: P0, feature, milestone-2
**摘要**：按 §11.3 与 §9 OfficialAlphaPool，落地 `select_official_alpha_pool(world_state, bundle) -> OfficialAlphaPool`，实现 observation pool / core pool 选择、容量上限（默认 100，参数化）、`added_entities` / `removed_entities` / `freeze_reason_map` 计算；capacity 必须服从参数化上限，越界率 = 0（§19.2）。
**所属模块**: `src/main_core/l5_universe/`（writable）；`common/schemas/pool.py`、`common/schemas/world_state.py`、`l3_features/*`（read-only，**不得**直连 l4 内部实现，只通过 `WorldStateSnapshot` 消费——§5.4）。
**写入边界**: 允许修改 `src/main_core/l5_universe/**`、`tests/l5_universe/**`；禁止 import `main_core.l4_world_state` 的内部模块，只允许 import `common.schemas.world_state`。
**实现顺序**: (1) `rules.py`：observation → core 规则；(2) `freezer.py`：冻结/解冻记录；(3) `service.py`：`select_official_alpha_pool` 主入口；(4) 测试：容量 100 上限边界、冻结解冻、add/remove 差分正确。
**依赖**: #ISSUE-006

---

### ISSUE-008: 实现 l6_alpha SinglePromptAnalyzer 与 inconclusive 降级
**labels**: P0, algorithm, milestone-2
**摘要**：按 §11.3 与 §12.3，替换 ISSUE-003 `SinglePromptAnalyzerStub` 为真实 `SinglePromptAnalyzer`，实现 `analyze(context) -> AlphaResultSnapshot`；P2 阶段 `analyzer_type` 固定 `single_prompt_v1`（§16.3）；单股票任务级失败必须标记 `inconclusive`，不得用上一轮 recommendation 顶替（§4 原则 4）；LLM 基础设施级失败则硬停。
**所属模块**: `src/main_core/l6_alpha/`（writable）；`common/protocols/analyzer.py`、`common/schemas/alpha.py`、`common/contexts.py`（read-only）；禁止触碰 `reasoner-runtime` 内部或 provider SDK。
**写入边界**: 允许修改 `src/main_core/l6_alpha/**`、`tests/l6_alpha/**`；`analyzer_type` 默认值改动若与 `single_prompt_v1` 冲突必须升级为 blocker（§25.3）。
**实现顺序**: (1) `single_prompt_analyzer.py`：真实实现 + 复用 ISSUE-006 的 `ReasonerPort`；(2) `fallback.py`：任务级失败检测 + inconclusive 标记路径；(3) `service.py`：`analyze_stock(entity_id, context)` 顶层入口；(4) 测试：happy / 任务失败 inconclusive / 基础设施硬停 / analyzer_type 校验。
**依赖**: #ISSUE-007

---

### ISSUE-009: 实现 l7_recommendation 正式建议、override 与 constraint gate
**labels**: P0, feature, milestone-2
**摘要**：按 §11.3 + §12.3 + §9 RecommendationSnapshot，落地 `generate_recommendations(pool, analyses, world_state) -> list[RecommendationSnapshot]` 与 `submit_override(override_input)`；Gate 优先于 override（§12.3）；`entity_id` 必须属于对应 cycle 的 `OfficialAlphaPool`（§9/§10.3）；`inconclusive` 显式落地。
**所属模块**: `src/main_core/l7_recommendation/`（writable）；`common/schemas/recommendation.py`、`common/schemas/override.py`、`common/protocols/constraint_provider.py`（read-only）；禁止 import `l4_world_state`、`l5_universe`、`l6_alpha` 的内部实现，只消费 formal object。
**写入边界**: 允许修改 `src/main_core/l7_recommendation/**`、`tests/l7_recommendation/**`；替换 `NullConstraintProviderStub` 为真实 `DefaultConstraintProvider`。
**实现顺序**: (1) `constraints.py`：regime/risk Gate 实现 `RecommendationConstraintProvider`；(2) `override.py`：override 记录 + 应用；(3) `service.py`：主流程 + entity_id ⊂ pool 的强校验；(4) 测试：override 应用、Gate 覆盖 override、inconclusive 透传、非池内 entity 拒绝。
**依赖**: #ISSUE-008

---

## 阶段 3：P2c 发布与审计对接（milestone-3）

**目标**：按 §21 阶段 2 与 §25.2 第 4 步，完成 `l8_publish` 的 formal object 装配、`cycle_publish_manifest` 发起、audit payload / retrospective seed 产出；同时落地 `dashboard_snapshot` 与 `report` 的正式业务内容。
**前置依赖**：milestone-2 完成，四类 formal object 能真实生成

### ISSUE-010: 实现 l8_publish 发布装配与 manifest 发起
**labels**: P0, integration, milestone-3
**摘要**：按 §11.4 与 §12.3，落地 `prepare_publish_bundle(cycle_id) -> PublishBundle`：装配 world_state / pool / alpha / recommendation 四类 formal object；单表 commit 逐类写入；全部成功后发起 `cycle_publish_manifest`；任一失败 → 本轮发布失败、不写 manifest、已写部分对消费方不可见；产出 audit payload 与 retrospective seed。manifest 语义改动必须单独成 issue（§25.1）。
**所属模块**: `src/main_core/l8_publish/`（writable）；`common/schemas/publish.py`、所有前序 formal object schema（read-only）；禁止直接写入 formal 表 head（§6.2 反模式）——必须通过 `data-platform` 提供的 publish API。
**写入边界**: 允许修改 `src/main_core/l8_publish/**`、`tests/l8_publish/**`；禁止修改 `cycle_publish_manifest` 的表定义（归 `data-platform`）。
**实现顺序**: (1) `assembler.py`：`prepare_publish_bundle` 装配入口；(2) `publish_port.py`：`DataPlatformPublishPort` 协议（本模块内 port）+ fake；(3) `manifest.py`：manifest 发起、失败回滚语义；(4) `audit_payload.py`：audit payload / retrospective seed 组装；(5) 测试：happy path、单表 commit 失败回滚、manifest 读后不可出现半提交。
**依赖**: #ISSUE-009

---

### ISSUE-011: 实现 dashboard_snapshot 与 formal report 的正式业务内容
**labels**: P1, feature, milestone-3
**摘要**：按 §9.3 DashboardSnapshot / FormalReport 与 §20.1，在 `l8_publish` 下落地 `build_dashboard_snapshot(cycle_id, bundle) -> DashboardSnapshot` 与 `build_formal_report(cycle_id, bundle) -> FormalReport`；两者均引用 ISSUE-010 发布的 world_state / pool / recommendation ref，不重复计算业务语义。
**所属模块**: `src/main_core/l8_publish/dashboard.py`、`src/main_core/l8_publish/report.py`（writable）；ISSUE-010 的 `PublishBundle`（read-only）。
**写入边界**: 允许修改 `src/main_core/l8_publish/dashboard.py`、`report.py`、对应测试；禁止修改 ISSUE-010 的 `prepare_publish_bundle` 主流程（只在其末尾 wire 调用 `build_dashboard_snapshot` / `build_formal_report`）。
**实现顺序**: (1) `dashboard.py`：汇总 summary_cards；(2) `report.py`：narrative_sections / appendix_refs；(3) 在 `PublishBundle.formal_objects` 中注册这两类产物；(4) 测试：ref 字段必须与同轮发布的实际 ref 一致。
**依赖**: #ISSUE-010

---

## 阶段 4：P3-P5 图谱与子系统接入（milestone-4）

**目标**：按 §21 阶段 3，接入 `graph-engine` 正式 `graph_snapshot` / `graph_impact_snapshot` 与 Layer B 候选信号，形成 `world_state → graph → L3 → world_state` 的时序闭环。
**前置依赖**：milestone-3 完成，纯市场数据最小闭环稳定

### ISSUE-012: 接入 graph_snapshot 与 graph_impact_snapshot 只读消费
**labels**: P1, integration, milestone-4
**摘要**：在 `l3_features` / `l4_world_state` 中引入只读 graph 消费：`l3_features` 注入 `graph_features`（来自 `graph_impact_snapshot`）；`l4_world_state` 将 graph regime context 作为 baseline 输入；严格只读，不回写图谱（§4.2）。
**所属模块**: `src/main_core/l3_features/graph_adapter.py`、`src/main_core/l4_world_state/graph_adapter.py`（writable）；禁止修改 `graph-engine` 任何内部实现。
**写入边界**: 允许修改 `l3_features` / `l4_world_state` 下新增 adapter 文件与对应测试；必须通过 `GraphEnginePort` 协议依赖注入，且只定义 read 方法。
**实现顺序**: (1) `GraphEnginePort` 协议 + fake；(2) L3 adapter 合并 `graph_features`；(3) L4 adapter 注入 regime context；(4) 时序闭环集成测试：上一轮 `world_state_snapshot` → graph 输入 → 本轮 L3/L4 可消费。
**依赖**: #ISSUE-011

---

### ISSUE-013: 接入 Layer B 候选信号到 l3_features
**labels**: P1, integration, milestone-4
**摘要**：将 `data-platform` 承载的 Layer B 候选 facts/signals 接入 `l3_features`，合并进 `FeatureSignalBundle.signal_values`；仍然受 `feature_weight_multiplier` 控制；保留 Layer B 缺席时的纯市场数据 fallback（§21 阶段 0 退出条件不得回退）。
**所属模块**: `src/main_core/l3_features/candidate_signals.py`（writable）；`l1_l2_basis/*`、`common/schemas/feature_bundle.py`（read-only）。
**写入边界**: 允许修改 `l3_features` 新增 candidate_signals 模块与测试；禁止在 `l1_l2_basis` 内混入 Layer B 专属读取——必须放在 L3。
**实现顺序**: (1) `CandidateSignalPort` 协议 + fake；(2) `build_feature_signal_bundle` 参数新增 `candidate_signals` 源；(3) multiplier 对 Layer B 信号同样生效；(4) 测试覆盖 Layer B 缺席回退 / multiplier 正确作用 / bundle 字段完整。
**依赖**: #ISSUE-012

---

## 阶段 5：P8 MultiAgent 选项（milestone-5）

**目标**：按 §21 阶段 4 与 §16.3，在不破坏 `AnalyzerInterface` 的前提下接入 `MultiAgentAnalyzer`，并提供 A/B 评估工具；`analyzer_type = "multi_agent_v1"` 仅在 P8 A/B 通过后允许，默认仍为 `single_prompt_v1`。
**前置依赖**：milestone-4 完成（完整业务闭环已成）

### ISSUE-014: 实现 MultiAgentAnalyzer 与 A/B 评估脚本
**labels**: P2, algorithm, milestone-5
**摘要**：按 §16.3 与 §21 阶段 4，新增 `MultiAgentAnalyzer` 实现 `AnalyzerInterface`，`analyzer_type = "multi_agent_v1"`；提供 A/B parity / scoring 脚本，用于判断是否满足切换到 multi_agent 生产的三要素；生产默认仍 `single_prompt_v1`，切换开关受配置控制，配置改动单独成 issue（§25.1）。
**所属模块**: `src/main_core/l6_alpha/multi_agent_analyzer.py`（writable）；`src/main_core/l6_alpha/ab_runner.py`（writable，A/B 脚本）；ISSUE-008 的 `SinglePromptAnalyzer`（read-only 对照基线）。
**写入边界**: 允许修改 `l6_alpha` 下新增两个文件与其测试；禁止修改 `SinglePromptAnalyzer` 主流程；禁止把 default analyzer 切到 `multi_agent_v1`——切换属 §25.3 blocker 条件。
**实现顺序**: (1) `multi_agent_analyzer.py`：实现 `AnalyzerInterface`，服从 ISSUE-003 协议；(2) `ab_runner.py`：按同一 cycle 并行跑两种 analyzer，产出 parity 指标；(3) 评估脚本输出 markdown/json 报告；(4) 测试：协议一致性、parity 指标结构、default analyzer 未被修改。
**依赖**: #ISSUE-013
