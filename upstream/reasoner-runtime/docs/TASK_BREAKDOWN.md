# 项目任务拆解

## 阶段 0：P2b 运行时骨架

**目标**：建立统一调用接口与最小 provider 配置骨架，使 main-core 能 import 并发起最小空调用
**前置依赖**：无

### ISSUE-001: 项目基础设施、核心领域对象与配置模块
**labels**: P0, infrastructure, milestone-0

#### 背景与目标
根据 §21 路线图阶段 0 要求，本 issue 建立 `reasoner-runtime` 的完整 Python 包结构、核心依赖配置、以及 §9 中定义的全部领域对象。这是整个项目的基石——后续所有能力链（调用入口、结构化输出、scrub/replay、health/callback）都依赖这些领域对象进行数据传递和类型约束。当前项目仅有脚手架文件（pyproject.toml placeholder、空 docs/），需要建立 `reasoner_runtime` 包及 §14 定义的 8 个子模块的目录结构，并实现 §9 中的 5 个运行时对象（ReasonerRequest、StructuredGenerationResult、ReplayBundle、ProviderHealthStatus、FallbackDecision）和 4 个配置对象（ProviderProfile、ScrubRuleSet、CallbackProfile、DependencyLockEntry）。所有对象使用 Pydantic v2 BaseModel 实现，字段设计严格遵循 §9.3 的建议字段表。配置模块（§10.2）需支持从 YAML 文件加载 provider/scrub/callback 配置。依赖管理需满足 §4.1 第 7 条供应链约束，对 `litellm` 和 `instructor` 执行版本号 + SHA-256 hash 锁定。

#### 所属模块
**主要写入路径**：
- `reasoner_runtime/__init__.py`
- `reasoner_runtime/core/__init__.py` + `reasoner_runtime/core/models.py`
- `reasoner_runtime/providers/__init__.py` + `reasoner_runtime/providers/models.py`
- `reasoner_runtime/structured/__init__.py`
- `reasoner_runtime/scrub/__init__.py`
- `reasoner_runtime/callbacks/__init__.py`
- `reasoner_runtime/health/__init__.py` + `reasoner_runtime/health/models.py`
- `reasoner_runtime/replay/__init__.py` + `reasoner_runtime/replay/models.py`
- `reasoner_runtime/config/__init__.py` + `reasoner_runtime/config/loader.py` + `reasoner_runtime/config/models.py`
- `tests/__init__.py` + `tests/unit/test_models.py` + `tests/unit/test_config.py`
- `pyproject.toml`
- `requirements.txt`
- `config/providers.example.yaml` + `config/scrub.example.yaml`

**只读/集成路径**：无（首个 issue）

**禁止路径**：不写业务 prompt 模板、不写 analyzer 逻辑、不写 Iceberg/PostgreSQL/Dagster 持久化代码、不实现任何调用逻辑或 scrub 逻辑

#### 实现范围
**包结构搭建（§14）**：
- `reasoner_runtime/__init__.py`：顶层包，定义 `__version__ = "0.1.0"`，导出核心公共类型
- 8 个子模块各自的 `__init__.py`：`core`、`providers`、`structured`、`scrub`、`callbacks`、`health`、`replay`、`config`；其中 `structured`、`scrub`、`callbacks` 为空占位模块

**运行时对象（§9.3 全部 5 个）**：
- `reasoner_runtime/core/models.py`：
  - `class ReasonerRequest(BaseModel)`：`request_id: str`、`caller_module: str`、`target_schema: str`、`messages: list[dict[str, Any]]`、`configured_provider: str`、`configured_model: str`、`max_retries: int = Field(ge=0)`（无默认值，强制显式传入）、`metadata: dict[str, Any] = Field(default_factory=dict)`
  - `class StructuredGenerationResult(BaseModel)`：`parsed_result: dict[str, Any]`、`actual_provider: str`、`actual_model: str`、`fallback_path: list[str] = Field(default_factory=list)`、`retry_count: int = 0`、`token_usage: dict[str, int]`、`cost_estimate: float`、`latency_ms: int`
- `reasoner_runtime/replay/models.py`：
  - `class ReplayBundle(BaseModel)`：核心五字段 `sanitized_input: str`、`input_hash: str`、`raw_output: str`、`parsed_result: dict[str, Any]`、`output_hash: str`（全部必填不可选）；附加字段 `llm_lineage: dict[str, Any]`
- `reasoner_runtime/health/models.py`：
  - `class QuotaStatus(str, Enum)`：`ok = "ok"`、`limited = "limited"`、`exhausted = "exhausted"`
  - `class ProviderHealthStatus(BaseModel)`：`provider: str`、`model: str`、`reachable: bool`、`latency_ms: int`、`quota_status: QuotaStatus`、`error: str | None = None`
- `reasoner_runtime/providers/models.py`：
  - `class FailureClass(str, Enum)`：`none = "none"`、`success_with_fallback = "success_with_fallback"`、`task_level = "task_level"`、`infra_level = "infra_level"`
  - `class FallbackDecision(BaseModel)`：`configured_target: str`、`attempts: list[str] = Field(default_factory=list)`、`final_target: str | None = None`、`failure_class: FailureClass = FailureClass.none`、`terminal_reason: str | None = None`、`error_classification: ReasonerErrorClassification | None = None`

**配置对象（§9.1 + §10.2）**：
- `reasoner_runtime/config/models.py`：
  - `class ProviderProfile(BaseModel)`：`provider: str`、`model: str`、`timeout_ms: int = 30000`、`fallback_priority: int = 0`、`rate_limit_rpm: int | None = None`
  - `class ScrubRule(BaseModel)`：`pattern_type: Literal["name", "phone", "account"]`、`enabled: bool = True`
  - `class ScrubRuleSet(BaseModel)`：`enabled: bool = True`、`rules: list[ScrubRule] = Field(default_factory=list)`
  - `class CallbackProfile(BaseModel)`：`backend: Literal["otel", "langfuse", "none"] = "none"`、`endpoint: str | None = None`、`enabled: bool = False`
  - `class DependencyLockEntry(BaseModel)`：`package: str`、`version: str`、`sha256: str`

**配置加载（§10.2）**：
- `reasoner_runtime/config/loader.py`：
  - `def load_provider_profiles(config_path: Path) -> list[ProviderProfile]`：从 YAML 文件解析 provider 配置列表，缺失必填字段时抛出 `ValidationError`
  - `def load_scrub_rules(config_path: Path) -> ScrubRuleSet`：从 YAML 文件加载脱敏规则集
  - `def load_callback_profile(config_path: Path) -> CallbackProfile`：从 YAML 文件加载 callback 配置

**依赖与构建**：
- `pyproject.toml`：更新 `dependencies` 添加 `pydantic>=2.0`、`pyyaml>=6.0`、`litellm`、`instructor`；更新 `[tool.setuptools] packages` 为 `reasoner_runtime` 及子包；`requires-python` 改为 `>=3.12`（§15）
- `requirements.txt`：对 `litellm` 和 `instructor` 添加版本号 + `--hash=sha256:...` 锁定（§4.1 第 7 条、§15）
- `config/providers.example.yaml`：示例 provider 配置（至少包含 2 个 provider/model 组合）
- `config/scrub.example.yaml`：示例脱敏规则配置

**测试**：
- `tests/unit/test_models.py`：所有 5 个运行时对象和 4 个配置对象的构造、字段校验、JSON 序列化/反序列化测试；ReasonerRequest 的 `max_retries >= 0` 校验测试；ReplayBundle 五字段完整性测试；枚举字段约束测试
- `tests/unit/test_config.py`：YAML 加载正常路径测试、必填字段缺失报错测试、默认值生效测试、示例配置文件可解析测试

#### 不在本次范围
- 不实现 `generate_structured()` 的任何调用逻辑——本 issue 只定义数据模型，调用入口骨架归 #ISSUE-002
- 不实现 `build_client()` 工厂函数——归 #ISSUE-002
- 不实现 PII scrub 脱敏逻辑——归 #ISSUE-006，本 issue 只定义 `ScrubRuleSet` 配置模型
- 不实现 replay bundle 生成逻辑（hash 计算、lineage 填充）——归 #ISSUE-004，本 issue 只定义 `ReplayBundle` 数据模型
- 不实现 OTEL / callback 后端代码——归 #ISSUE-007
- 不定义 `contracts` 共享 schema——属于其他项目边界（§5.4）
- 如发现需要改动 `contracts` 或其他项目的共享类型定义，必须作为 blocker 上报而非扩展本 issue 范围

#### 关键交付物
- `class ReasonerRequest(BaseModel)`：含 `request_id`、`caller_module`、`target_schema`、`messages`、`configured_provider`、`configured_model`、`max_retries`（无默认值）、`metadata` 共 8 个字段
- `class StructuredGenerationResult(BaseModel)`：含 `parsed_result`、`actual_provider`、`actual_model`、`fallback_path`、`retry_count`、`token_usage`、`cost_estimate`、`latency_ms` 共 8 个字段
- `class ReplayBundle(BaseModel)`：核心五字段 `sanitized_input`、`input_hash`、`raw_output`、`parsed_result`、`output_hash` + `llm_lineage`，五字段全部必填
- `class ProviderHealthStatus(BaseModel)`：含 `provider`、`model`、`reachable`、`latency_ms`、`quota_status`（枚举）、`error` 共 6 个字段
- `class FallbackDecision(BaseModel)`：含 `configured_target`、`attempts`、`final_target`、`failure_class`（枚举）、`terminal_reason`、`error_classification` 字段
- `class ProviderProfile(BaseModel)`：provider 运行配置对象
- `class ScrubRuleSet(BaseModel)`：脱敏规则集配置对象
- `class CallbackProfile(BaseModel)`：观测回调后端配置对象
- `class DependencyLockEntry(BaseModel)`：依赖锁定条目对象
- `def load_provider_profiles(config_path: Path) -> list[ProviderProfile]`：YAML 配置加载函数
- `requirements.txt`：`litellm` + `instructor` 版本号 + SHA-256 hash 锁定
- 8 个子模块目录结构完整且可 import

#### 验收标准
**核心功能：**
- [ ] `ReasonerRequest` 可正确构造，`max_retries` 字段存在且 `ge=0` 校验生效（传入负数抛出 `ValidationError`）
- [ ] `StructuredGenerationResult` 所有 8 个字段可正确序列化为 JSON 并反序列化
- [ ] `ReplayBundle` 核心五字段（`sanitized_input`、`input_hash`、`raw_output`、`parsed_result`、`output_hash`）全部为必填字段，缺少任一字段时构造失败
- [ ] `ProviderHealthStatus.quota_status` 为枚举类型，仅接受 `ok` / `limited` / `exhausted`
- [ ] `FallbackDecision.failure_class` 为枚举类型，仅接受 `none` / `success_with_fallback` / `task_level` / `infra_level`

**配置加载：**
- [ ] `load_provider_profiles()` 能从 YAML 文件正确加载 ≥2 个 provider 配置
- [ ] YAML 缺失必填字段时抛出 `ValidationError`
- [ ] 示例配置文件 `config/providers.example.yaml` 和 `config/scrub.example.yaml` 均可被成功解析
- [ ] `ProviderProfile` 的 `timeout_ms` 默认值为 30000、`fallback_priority` 默认值为 0

**包结构：**
- [ ] `from reasoner_runtime.core import ReasonerRequest, StructuredGenerationResult` 可成功 import
- [ ] `from reasoner_runtime.replay import ReplayBundle` 可成功 import
- [ ] `from reasoner_runtime.health import ProviderHealthStatus` 可成功 import
- [ ] 所有 8 个子模块（core、providers、structured、scrub、callbacks、health、replay、config）均可 import 且无 `ImportError`

**依赖：**
- [ ] `requirements.txt` 中 `litellm` 和 `instructor` 有明确版本号和 SHA-256 hash
- [ ] `pip install -e .` 可成功安装且 `import reasoner_runtime` 无报错

**测试：**
- [ ] 单元测试 ≥ 20 个，覆盖所有 9 个模型的构造、字段校验、序列化场景
- [ ] 所有测试通过 (`pytest tests/ -v`)

#### 验证命令
```bash
# Unit tests
pytest tests/unit/test_models.py tests/unit/test_config.py -v

# Import check — all 8 submodules + key objects
python -c "
from reasoner_runtime.core import ReasonerRequest, StructuredGenerationResult
from reasoner_runtime.replay import ReplayBundle
from reasoner_runtime.health import ProviderHealthStatus
from reasoner_runtime.providers import FallbackDecision
from reasoner_runtime.config import load_provider_profiles
import reasoner_runtime.structured
import reasoner_runtime.scrub
import reasoner_runtime.callbacks
print('All imports OK')
"

# Install check
pip install -e . && python -c "import reasoner_runtime; print(reasoner_runtime.__version__)"

# Dependency hash verification
pip install --require-hashes -r requirements.txt --dry-run

# Regression
pytest tests/ -v
```

#### 依赖
无前置依赖

---

### ISSUE-002: 统一调用入口骨架与 Provider 抽象
**labels**: P0, infrastructure, milestone-0

#### 背景与目标
根据 §21 阶段 0 退出条件——"main-core 能 import 并发起最小空调用"——本 issue 实现 §16.1 中的 `generate_structured()` 调用入口骨架和 `build_client()` 客户端工厂函数。这是能力链 1（统一调用入口 + fallback/retry，归属 `reasoner_runtime.core` / `providers`）的骨架实现。此阶段 `generate_structured()` 不需要真正调用 LLM，只需建立完整的函数签名、请求标准化流程和返回类型，使调用方能 import 并编译通过。同时实现 §16.1 中的 `classify_failure()` 骨架和 provider 路由选择的基础框架。根据 §16.3 的强制约束，`build_client()` 必须显式接收 `max_retries` 参数，不允许设置默认值，也不允许在内部隐式依赖 Instructor 默认重试次数。本 issue 建立的骨架将在 ISSUE-003（结构化输出）和 ISSUE-005（fallback/retry）中被填充为完整实现。

#### 所属模块
**主要写入路径**：
- `reasoner_runtime/core/engine.py`
- `reasoner_runtime/core/__init__.py`（追加导出 `generate_structured`）
- `reasoner_runtime/providers/routing.py`
- `reasoner_runtime/providers/client.py`
- `reasoner_runtime/providers/__init__.py`（追加导出 `build_client`、`select_provider`、`classify_failure`）
- `tests/unit/test_engine.py`
- `tests/unit/test_providers.py`

**只读/集成路径**：
- `reasoner_runtime/core/models.py`（读取 `ReasonerRequest`、`StructuredGenerationResult`）
- `reasoner_runtime/providers/models.py`（读取 `FallbackDecision`、`FailureClass`）
- `reasoner_runtime/config/models.py`（读取 `ProviderProfile`）

**禁止路径**：
- `reasoner_runtime/structured/`（Instructor 集成归 #ISSUE-003）
- `reasoner_runtime/scrub/`（PII scrub 归 #ISSUE-006）
- `reasoner_runtime/replay/`（replay bundle 生成归 #ISSUE-004）
- `reasoner_runtime/health/`（health check 归 #ISSUE-008）
- `reasoner_runtime/callbacks/`（OTEL 归 #ISSUE-007）

#### 实现范围
**调用入口骨架（§16.1 `generate_structured`）**：
- `reasoner_runtime/core/engine.py`：
  - `def generate_structured(request: ReasonerRequest) -> StructuredGenerationResult`：骨架实现，接收标准化请求，返回 placeholder 结果对象；内部预留五个调用槽位——`scrub` -> `route` -> `call` -> `parse` -> `bundle`——后续 issue 依次填充
  - `def _normalize_request(request: ReasonerRequest) -> ReasonerRequest`：请求标准化内部函数，校验必填字段齐全、自动补全空 `request_id`（生成 UUID）、验证 `max_retries >= 0`

**客户端工厂（§16.1 `build_client`）**：
- `reasoner_runtime/providers/client.py`：
  - `def build_client(profile: ProviderProfile, max_retries: int) -> Any`：构建 LiteLLM + Instructor 运行时 client 的工厂函数骨架；`max_retries` 为位置参数无默认值，强制调用方显式传入；内部校验 `max_retries >= 0`，违反时抛 `ValueError`
  - 骨架阶段返回包含 `profile` 和 `max_retries` 的配置字典，真实 LiteLLM 初始化在 #ISSUE-003 实现

**Provider 路由（§11.2 基础）**：
- `reasoner_runtime/providers/routing.py`：
  - `def select_provider(configured_provider: str, configured_model: str, profiles: list[ProviderProfile]) -> ProviderProfile`：从 profile 列表中按 `fallback_priority` 升序排序，优先匹配 `configured_provider` + `configured_model`，匹配不到时返回优先级最高的 fallback；列表为空时抛 `ValueError`
  - `def classify_failure(error: Exception, context: dict[str, Any]) -> FailureClass`：仅在显式解析上下文（`failure_source` 或 `phase` 为 `parse`）中将 `ParseValidationError` / Pydantic `ValidationError` / `ValueError` 归为 `task_level`；provider 配置、LiteLLM 常见 provider 异常、连接/超时和无上下文异常归为 `infra_level`。公开错误通过 typed `FallbackExecutionError.decision.error_classification` 暴露。

**模块导出更新**：
- `reasoner_runtime/core/__init__.py`：追加导出 `generate_structured`
- `reasoner_runtime/providers/__init__.py`：追加导出 `build_client`、`select_provider`、`classify_failure`

**测试**：
- `tests/unit/test_engine.py`：`generate_structured` 骨架调用测试（传入合法 `ReasonerRequest` 返回 `StructuredGenerationResult`）、`_normalize_request` 补全 request_id 测试、传入非法请求的校验测试
- `tests/unit/test_providers.py`：`build_client` 参数校验测试（缺少 `max_retries` 触发 `TypeError`、负数触发 `ValueError`）、`select_provider` 路由匹配测试（精确匹配、fallback 回退、空列表报错）、`classify_failure` 异常分类测试（网络异常 vs 显式解析上下文异常）

#### 不在本次范围
- 不实现 LiteLLM 真实 API 调用——`build_client` 骨架阶段只返回配置字典，LiteLLM + Instructor 初始化归 #ISSUE-003
- 不实现 fallback 链重试循环——归 #ISSUE-005，本 issue 只实现单次 provider 选择
- 不实现 PII scrub 处理——归 #ISSUE-006，`generate_structured` 中仅预留 scrub 槽位
- 不实现 replay bundle 生成——归 #ISSUE-004，仅预留 bundle 槽位
- 不实现 OTEL callback 触发——归 #ISSUE-007
- `build_client()` 绝不能设置 `max_retries` 默认值——这是 §16.3 的硬约束，违反即打回

#### 关键交付物
- `def generate_structured(request: ReasonerRequest) -> StructuredGenerationResult`：统一调用入口骨架，含五个预留调用槽位
- `def _normalize_request(request: ReasonerRequest) -> ReasonerRequest`：请求标准化，自动补全 `request_id`
- `def build_client(profile: ProviderProfile, max_retries: int) -> Any`：客户端工厂，`max_retries` 无默认值强制显式传入
- `def select_provider(configured_provider: str, configured_model: str, profiles: list[ProviderProfile]) -> ProviderProfile`：按 `fallback_priority` 排序的 provider 路由选择
- `def classify_failure(error: Exception, context: dict[str, Any]) -> FailureClass`：基于异常类型与显式 parse/provider 上下文的失败分类
- 所有函数的异常处理行为：`build_client` 负数 -> `ValueError`、`select_provider` 空列表 -> `ValueError`
- `generate_structured` 内部五个调用槽位：scrub / route / call / parse / bundle

#### 验收标准
**核心功能：**
- [ ] `generate_structured(request)` 接收 `ReasonerRequest` 返回 `StructuredGenerationResult` 且不抛异常
- [ ] `_normalize_request()` 对空 `request_id` 自动生成 UUID 格式字符串
- [ ] `build_client(profile, max_retries)` 中 `max_retries` 为必传参数且无默认值（缺少时 `TypeError`）
- [ ] `build_client()` 传入负数 `max_retries` 时抛出 `ValueError`

**Provider 路由：**
- [ ] `select_provider()` 精确匹配 `configured_provider` + `configured_model` 时返回对应 profile
- [ ] `select_provider()` 无精确匹配时按 `fallback_priority` 升序返回第一个 profile
- [ ] `select_provider()` 传入空列表时抛出 `ValueError`

**失败分类：**
- [ ] `classify_failure()` 对 `ConnectionError` 返回 `FailureClass.infra_level`
- [ ] `classify_failure()` 对 `TimeoutError` 返回 `FailureClass.infra_level`
- [ ] `classify_failure()` 仅在 `failure_source="parse"` 或 `phase="parse"` 上下文中对 `ValueError` / `ValidationError` 返回 `FailureClass.task_level`，无解析上下文时返回 `FailureClass.infra_level`

**集成：**
- [ ] `from reasoner_runtime.core import generate_structured` 可成功 import
- [ ] `from reasoner_runtime.providers import build_client, select_provider, classify_failure` 可成功 import

**测试：**
- [ ] 单元测试 ≥ 15 个，覆盖入口调用、请求标准化、参数校验、路由选择、失败分类
- [ ] 所有 ISSUE-001 的测试仍通过（无回归）

#### 验证命令
```bash
# Unit tests
pytest tests/unit/test_engine.py tests/unit/test_providers.py -v

# Import check
python -c "
from reasoner_runtime.core import generate_structured
from reasoner_runtime.providers import build_client, select_provider, classify_failure
print('All imports OK')
"

# max_retries enforcement check
python -c "
from reasoner_runtime.providers.client import build_client
from reasoner_runtime.config.models import ProviderProfile
import inspect
sig = inspect.signature(build_client)
p = sig.parameters['max_retries']
assert p.default is inspect.Parameter.empty, 'FAIL: max_retries has a default value'
print('PASS: max_retries is required (no default)')
"

# Skeleton call check
python -c "
from reasoner_runtime.core import generate_structured
from reasoner_runtime.core.models import ReasonerRequest
req = ReasonerRequest(
    request_id='test-001',
    caller_module='test',
    target_schema='TestSchema',
    messages=[{'role': 'user', 'content': 'hello'}],
    configured_provider='openai',
    configured_model='gpt-4',
    max_retries=2
)
result = generate_structured(req)
print(f'PASS: got {type(result).__name__}')
"

# Regression
pytest tests/ -v
```

#### 依赖
依赖 #ISSUE-001（核心领域对象与配置模块必须先就位，否则无法 import ReasonerRequest 等类型）

---

## 阶段 1：P2b 主链路打通

**目标**：打通 LiteLLM + Instructor + replay bundle 完整链路，使 1 条正式调用可产出完整结构化结果与回放字段
**前置依赖**：阶段 0

### ISSUE-003: LiteLLM + Instructor 结构化输出主链路
**labels**: P0, feature, milestone-1
**摘要**: 实现 `reasoner_runtime.structured` 模块，通过 LiteLLM 发起 provider 调用并使用 Instructor 强制解析为 Pydantic schema，填充 `generate_structured()` 中的 `call` 和 `parse` 槽位，使主链路可执行真实结构化 LLM 调用。同时补充 `build_client()` 的真实 LiteLLM + Instructor 初始化逻辑，确保 `max_retries` 显式传递（§16.3）。
**所属模块**: `reasoner_runtime/structured/` (主要写入) + `reasoner_runtime/core/engine.py` (填充 call/parse 槽位) + `reasoner_runtime/providers/client.py` (补充 LiteLLM/Instructor 初始化) + `tests/unit/test_structured.py`
**写入边界**: 允许修改 `structured/`、`core/engine.py` 的 call/parse 槽位、`providers/client.py` 的 client 初始化逻辑；禁止修改 `scrub/`、`replay/`、`health/`、`callbacks/`、领域模型定义（`models.py`）
**实现顺序**: 先实现 `structured/parser.py`（Instructor 初始化与结构化解析封装，显式 `max_retries` 传递），再更新 `providers/client.py`（LiteLLM client 真实初始化 + Instructor `from_litellm()` 或等价 patch），最后填充 `core/engine.py` 的 call/parse 槽位并编写集成测试（mock LiteLLM 响应验证解析流程）
**依赖**: #ISSUE-002（调用入口骨架与 build_client 工厂必须先就位）

---

### ISSUE-004: Replay Bundle 五字段生成与 Lineage 记录
**labels**: P0, feature, milestone-1
**摘要**: 实现 `reasoner_runtime.replay` 模块的 `build_replay_bundle()` 函数（§16.1），在每次结构化调用完成后生成包含 `sanitized_input`、`input_hash`（SHA-256）、`raw_output`、`parsed_result`、`output_hash`（SHA-256）核心五字段和 `llm_lineage` 的完整 ReplayBundle 对象，填充 `generate_structured()` 的 `bundle` 槽位。`raw_output` 持久化前不得额外变形（§18.4）。
**所属模块**: `reasoner_runtime/replay/` (主要写入：`builder.py`) + `reasoner_runtime/core/engine.py` (填充 bundle 槽位) + `tests/unit/test_replay.py`
**写入边界**: 允许修改 `replay/`、`core/engine.py` 的 bundle 槽位；禁止修改 `scrub/`（脱敏逻辑归 ISSUE-006）、`structured/`、`health/`、`callbacks/`；禁止修改 ReplayBundle 模型定义（核心五字段命名和语义必须保持 §9.3 定义不变）
**实现顺序**: 先实现 `replay/builder.py`（`build_replay_bundle(sanitized_input: str, raw_output: str, parsed_result: dict, lineage: dict) -> ReplayBundle`，含 SHA-256 hash 计算），再实现 lineage 构建辅助函数（从 StructuredGenerationResult 提取 provider/model/fallback_path/retry_count），最后填充 `core/engine.py` 的 bundle 槽位并编写单元测试（hash 正确性、五字段完整性、lineage 结构验证、raw_output 不变形回归测试）
**依赖**: #ISSUE-003（结构化输出主链路打通后才有 raw_output 和 parsed_result 供 bundle 消费）

---

### ISSUE-005: Fallback/Retry 链路与失败分类
**labels**: P0, feature, milestone-1
**摘要**: 实现 §11.2 描述的完整 fallback/retry 算法——当主 provider 失败时沿 fallback 链切换 provider，当结构化解析失败时在当前 provider 上按 `max_retries` 重试，全链失败后通过 `classify_failure()` 区分 `infra_level`（基础设施级硬停）和 `task_level`（任务级降级），并记录完整的 `FallbackDecision` 路由决策。重试次数必须显式从 `ReasonerRequest.max_retries` 获取，禁止在 `build_client` 内部隐藏重试策略（§16.3）。
**所属模块**: `reasoner_runtime/providers/` (主要写入：`routing.py` 扩展、`fallback.py` 新建) + `reasoner_runtime/core/engine.py` (替换 route/call 槽位为 fallback 循环) + `tests/unit/test_fallback.py`
**写入边界**: 允许修改 `providers/routing.py`（扩展 `classify_failure` 完整逻辑）、新建 `providers/fallback.py`、修改 `core/engine.py` 的 route/call 逻辑；禁止修改 `scrub/`、`replay/`、`health/`、`callbacks/`；禁止在 `build_client` 内部隐藏重试策略
**实现顺序**: 先实现 `providers/fallback.py`（`execute_with_fallback(request: ReasonerRequest, profiles: list[ProviderProfile], call_fn: Callable) -> tuple[StructuredGenerationResult, FallbackDecision]`，含 provider 切换循环和按 max_retries 的解析重试），再扩展 `classify_failure()` 为完整异常分类（覆盖 LiteLLM 常见异常类型如 `RateLimitError`、`AuthenticationError`、`ServiceUnavailableError`），最后将 `core/engine.py` 的 route/call 槽位替换为 fallback 循环调用并编写测试（主 provider 失败 fallback 成功、解析失败重试成功、全链失败分类、成本追踪记入 retry_count）
**依赖**: #ISSUE-003（需要真实的结构化调用能力才能构建 fallback 循环）

---

## 阶段 2：P2b 安全与观测

**目标**：补齐 PII scrub、OTEL 最小观测层与供应链锁定，使外发前脱敏成立且最小观测数据可用
**前置依赖**：阶段 1

### ISSUE-006: PII Scrub Handler 与统一脱敏链
**labels**: P1, feature, milestone-2
**摘要**: 实现 `reasoner_runtime.scrub` 模块的 `scrub_input()` 函数（§16.1），对外发 LLM 调用前的 messages 和 metadata 执行统一 PII 脱敏，至少覆盖姓名、手机、账户三类敏感信息（§11.4），确保外发链、落盘链、日志链复用同一脱敏结果（§6.1 原则 4：Security Before Observability），填充 `generate_structured()` 的 `scrub` 槽位。脱敏覆盖率目标 >= 95%（§19.2）。
**所属模块**: `reasoner_runtime/scrub/` (主要写入：`handler.py`、`rules.py`) + `reasoner_runtime/core/engine.py` (填充 scrub 槽位) + `tests/unit/test_scrub.py`
**写入边界**: 允许修改 `scrub/`、`core/engine.py` 的 scrub 槽位；禁止修改 `replay/`（replay bundle 消费 sanitized_input 但不改写其生成逻辑）、`structured/`、`health/`、`callbacks/`
**实现顺序**: 先实现 `scrub/rules.py`（正则规则引擎，支持 name/phone/account 三类 pattern），再实现 `scrub/handler.py`（`scrub_input(messages: list[dict], metadata: dict, rule_set: ScrubRuleSet) -> str`，应用规则集生成 sanitized_input），再填充 `core/engine.py` scrub 槽位（调用 scrub_input 并将结果传给 replay builder），最后编写单元测试（姓名/手机/账户样本集覆盖率验证、外发链与落盘链一致性验证 §18.4）
**依赖**: #ISSUE-004（replay bundle 生成就位后，scrub 输出的 sanitized_input 才能被正确消费）

---

### ISSUE-007: OTEL Callbacks 最小观测层与供应链锁定
**labels**: P1, infrastructure, milestone-2
**摘要**: 实现 `reasoner_runtime.callbacks` 模块的最小可用观测层（§15 LiteLLM callbacks / OTEL），记录 request_id、token usage、cost、latency、error 等最小可用观测数据（§20.2），同时完善 `requirements.txt` 的供应链锁定（§4.1 第 7 条），添加 hash 校验脚本确保 `litellm` 和 `instructor` 的版本与 SHA-256 一致。Callback 通过 LiteLLM 的 callback 机制注入，不改变 `generate_structured()` 的返回结构（§5.4）。
**所属模块**: `reasoner_runtime/callbacks/` (主要写入：`otel.py`、`base.py`) + `scripts/verify_deps.py` (新建) + `requirements.txt` (完善 hash) + `tests/unit/test_callbacks.py` + `tests/unit/test_dep_lock.py`
**写入边界**: 允许修改 `callbacks/`、`requirements.txt`、新建 `scripts/`；禁止修改 `core/engine.py` 的调用逻辑（callback 通过 LiteLLM 的 callback 机制注入，不改变 `generate_structured()` 返回结构 §5.4）；禁止修改 `scrub/`、`replay/`、`health/`
**实现顺序**: 先实现 `callbacks/base.py`（`CallbackBackend` 协议：`on_start`/`on_success`/`on_error` 三个钩子 §16.2），再实现 `callbacks/otel.py`（OTEL 适配实现，通过 LiteLLM success/failure callback 记录 span），再完善 `requirements.txt` hash 锁定并编写 `scripts/verify_deps.py`（读取 requirements.txt 验证已安装包的 hash），最后编写测试（callback 协议合规测试、OTEL span 记录验证、dependency hash 校验测试 §18.1）
**依赖**: #ISSUE-005（fallback/retry 链路稳定后才接入观测层，避免观测数据不完整）

---

## 阶段 3：P2-P4 跨模块接入

**目标**：接入 main-core / entity-registry，完成 health_check() 与 orchestrator 对接，使业务模块不再直连 provider
**前置依赖**：阶段 2

### ISSUE-008: health_check() 实现与 Provider 健康探测
**labels**: P1, feature, milestone-3
**摘要**: 实现 `reasoner_runtime.health` 模块的 `health_check()` 函数（§16.1），按 provider/model 组合执行可调用性和延迟探测（§11.3），生成 `ProviderHealthStatus[]` 与聚合结论（含 `all_critical_targets_available` 布尔值和 `summary` 文本 §13.3），供 orchestrator 在 Phase 0 执行 Gate 判定（§8.2）。单 provider/model 探测耗时 < 3 秒（§19.1）。
**所属模块**: `reasoner_runtime/health/` (主要写入：`checker.py`、`aggregator.py`) + `tests/unit/test_health.py`
**写入边界**: 允许修改 `health/`；禁止修改 `core/engine.py`（health check 是独立能力，不嵌入调用主链路）；禁止修改 `providers/`（health check 复用 provider 配置但不改写路由逻辑）；禁止修改 `callbacks/`
**实现顺序**: 先实现 `health/checker.py`（`health_check(provider_profiles: list[ProviderProfile]) -> list[ProviderHealthStatus]`，对每个 provider/model 组合发送最小测试请求并记录 reachable/latency/quota），再实现 `health/aggregator.py`（聚合整体可用性判定、生成 `all_critical_targets_available` 布尔值和 summary 文本），最后编写测试（mock provider 响应验证探测逻辑，单 provider 探测耗时 < 3 秒基线 §19.1，critical target 不可静默失败 §19.2）
**依赖**: #ISSUE-006（PII scrub 稳定后才开 health/callback 类 issue——遵循 CLAUDE.md 任务拆分规则"replay/scrub/retry 未稳定前不开 callback 或观测增强类 Issue"）

---

### ISSUE-009: 跨模块接入适配与端到端集成验证
**labels**: P1, integration, milestone-3
**摘要**: 提供 main-core、entity-registry、subsystem-* 接入 `reasoner-runtime` 的适配层与集成验证，确保所有业务模块通过统一入口调用 LLM（§23 第 1 条），验证 health_check() 可被 orchestrator 直接消费（§23 第 3 条），并通过静态检查确保无业务模块直连 provider SDK（§19.2 发生率 = 0）。同时验证 §23 全部 5 条验收标准在端到端流程中成立。
**所属模块**: `reasoner_runtime/` 顶层导出整理 (主要写入) + `tests/integration/` (新建集成测试目录) + `tests/integration/test_e2e_call.py` + `tests/integration/test_health_gate.py` + `scripts/check_direct_imports.py` (新建)
**写入边界**: 允许修改 `reasoner_runtime/__init__.py`（整理公共 API 导出）、新建 `tests/integration/`、新建 `scripts/check_direct_imports.py`；禁止修改 `core/engine.py`、`providers/`、`scrub/`、`replay/`、`health/` 的内部实现逻辑（本 issue 只做接入适配和集成验证，不改内部逻辑）
**实现顺序**: 先整理 `reasoner_runtime/__init__.py` 的公共 API 导出（`generate_structured`、`health_check`、`build_client`、`scrub_input`、`build_replay_bundle`、`classify_failure` 六个接口 §16.1），再编写 `scripts/check_direct_imports.py`（扫描项目代码树确保无 `import openai`/`import anthropic` 等直连 provider SDK §18.3），再编写端到端集成测试（mock provider 的完整调用链路：request -> scrub -> call -> parse -> bundle -> result，验证 replay bundle 五字段完整且 raw_output 未变形），最后编写 health gate 集成测试（mock 多 provider 探测 -> 聚合 -> Gate 判定，验证 §13.3 输出结构）
**依赖**: #ISSUE-008（health_check 实现就位后才能做跨模块集成验证）

---

## 阶段 4：P6+ 可选观测后端

**目标**：在不改变调用接口的前提下接入 Langfuse 等 callback backend，观测后端变化不影响调用方代码
**前置依赖**：阶段 3

### ISSUE-010: Langfuse Callback Backend 适配器
**labels**: P2, feature, milestone-4
**摘要**: 基于 ISSUE-007 建立的 `CallbackBackend` 协议，实现 Langfuse 适配器（§15 可选观测后端），支持通过配置切换在 OTEL 和 Langfuse 之间选择 callback backend，确保切换不改变 `generate_structured()` 的返回结构（§5.4、§16.3）。
**所属模块**: `reasoner_runtime/callbacks/` (主要写入：`langfuse.py`) + `reasoner_runtime/config/` (扩展 CallbackProfile 加载逻辑) + `tests/unit/test_langfuse_callback.py`
**写入边界**: 允许修改 `callbacks/`（新增 langfuse 适配器）、`config/loader.py`（支持 langfuse backend 配置加载）；禁止修改 `core/engine.py`（callback 通过注入机制生效，不改调用入口）；禁止修改 `generate_structured()` 的返回类型 `StructuredGenerationResult`
**实现顺序**: 先实现 `callbacks/langfuse.py`（实现 `CallbackBackend` 协议的 Langfuse 版本），再扩展 `config/loader.py` 支持 `backend: langfuse` 配置解析，再编写测试（mock Langfuse SDK 验证 span 记录，验证切换后 generate_structured 返回结构不变）
**依赖**: #ISSUE-007（OTEL callback 层和 CallbackBackend 协议必须先就位）

---

### ISSUE-011: 观测后端配置切换与回归验证
**labels**: P2, testing, milestone-4
**摘要**: 建立观测后端热切换能力的完整回归验证套件，确保在 OTEL / Langfuse / none 三种 backend 之间切换时，`generate_structured()` 的返回结构、replay bundle 五字段、fallback/retry 行为均无回归（§21 阶段 4 退出条件），并编写配置切换的端到端测试。
**所属模块**: `tests/integration/test_callback_switching.py` (新建) + `tests/unit/test_callback_regression.py` (新建) + `config/callbacks.example.yaml` (新建示例)
**写入边界**: 允许新建测试文件和示例配置；禁止修改 `reasoner_runtime/` 下的任何实现代码（本 issue 纯测试与验证）
**实现顺序**: 先编写 `config/callbacks.example.yaml`（三种 backend 的示例配置），再编写 `test_callback_regression.py`（验证切换 backend 后 generate_structured 返回结构不变、replay bundle 五字段完整、fallback 行为一致），最后编写 `test_callback_switching.py`（端到端配置切换测试：加载不同配置 -> 执行调用 -> 验证观测数据写入正确 backend）
**依赖**: #ISSUE-010（Langfuse 适配器实现就位后才能做切换回归验证）
