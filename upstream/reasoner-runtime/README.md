# reasoner-runtime

`reasoner-runtime` 是 project-ult 中**唯一**的 LLM 调用运行时模块。所有业务模块通过它发起结构化生成、PII scrub、replay bundle、fallback/retry、health check —— 不允许业务模块直连任何 provider SDK。

Source of truth: [`docs/reasoner-runtime.project-doc.md`](docs/reasoner-runtime.project-doc.md)
Per-module guardrails: [`CLAUDE.md`](CLAUDE.md)

## 公共 API

```python
from reasoner_runtime import generate_structured, ReasonerRequest
from reasoner_runtime.config.models import ProviderProfile
```

| 入口 | 用途 |
|---|---|
| `generate_structured(request, schema_registry, provider_profiles=...)` | 业务模块的标准调用入口 |
| `generate_structured_with_replay(...)` | 同上 + 同时返回 5 字段 ReplayBundle |
| `health_check(provider_profiles)` | orchestrator Phase 0 健康探测 |
| `build_client(profile, max_retries)` | 内部 client 工厂；外部一般不直接调 |

## 三种受支持的 LLM 后端

启用项目时，由上层（`assembly setup` wizard / orchestrator Phase 0）让用户从下面三选一加载到 `provider_profiles`。本 runtime **不在三者之间降级** —— 选定的那一个失败就直接报错，由调用方决定重试或上报。

| 后端 | provider 字段 | 调用路径 | 鉴权来源 | env 网关 |
|---|---|---|---|---|
| **MiniMax** | `minimax` | LiteLLM 默认 → MiniMax 官方公开 API | `MINIMAX_API_KEY` (+ optional `MINIMAX_API_BASE`) | 无（公开 API，无网关） |
| **OpenAI Codex** | `openai-codex` | 自定义 httpx → `chatgpt.com/backend-api/codex/responses` | 借用 codex CLI 的 `~/.codex/auth.json`（只读，过期不自动刷新） | `REASONER_RUNTIME_ENABLE_CODEX_OAUTH=1` |
| **Claude Code** | `claude-code` | subprocess → `claude --print --output-format json --json-schema ...` | 由 `claude` CLI 自管（macOS Keychain / Linux secret-service / Windows Credential Manager） | `REASONER_RUNTIME_ENABLE_CLAUDE_CODE_CLI=1` |

完整 example：[`config/providers.three-backends.example.yaml`](config/providers.three-backends.example.yaml)

三后端 example 不是 fallback 链。加载时必须显式选择一个 backend：

```python
from pathlib import Path
from reasoner_runtime.config import load_provider_profiles

provider_profiles = load_provider_profiles(
    Path("config/providers.three-backends.example.yaml"),
    selector="minimax",  # or "codex" / "claude_code"
)
```

### Backend 启用步骤

#### A. MiniMax（公开 API key，零额外步骤）
```bash
export MINIMAX_API_KEY="<your-key>"
# optional:
export MINIMAX_API_BASE="https://api.minimax.chat/v1"
```
配置：
```yaml
- provider: minimax
  model: MiniMax-M2.5
  timeout_ms: 30000
```
LiteLLM 1.83.0 已原生支持 minimax 9 个模型（`MiniMax-M2.5` / `M2` / `M2.1` / `M2.1-lightning` / speech 系列）。

#### B. OpenAI Codex（ChatGPT 订阅）
```bash
codex login                                       # 一次性，写 ~/.codex/auth.json
export REASONER_RUNTIME_ENABLE_CODEX_OAUTH=1     # 显式 opt-in（chatgpt.com 是非公开 API）
```
配置：
```yaml
- provider: openai-codex
  model: gpt-5.5                  # 与你 codex CLI 账号能用的模型对齐（参考 ~/.codex/config.toml）
  timeout_ms: 60000
  auth:
    kind: codex_cli
```
runtime **只读** `~/.codex/auth.json`；token 过期会抛 `CodexAuthError("...run \`codex login\` to refresh")`，需手动重新登录。

#### C. Claude Code（Claude Pro/Max 订阅）
```bash
claude /login                                     # 一次性，凭证由 claude CLI 自管（keychain/secret-service）
export REASONER_RUNTIME_ENABLE_CLAUDE_CODE_CLI=1  # 显式 opt-in（subprocess 模式 + 订阅额度）
```
配置：
```yaml
- provider: claude-code
  model: claude-sonnet-4-6        # 任何 claude CLI 支持的模型别名 / 全名都行（sonnet / opus / claude-sonnet-4-6 ...）
  timeout_ms: 60000
  auth:
    kind: claude_code_cli
    # binary_path: /usr/local/bin/claude   # 可选；默认走 PATH 查找
```
**实现方式：** `subprocess` 调 `claude --print --output-format json --json-schema <schema> --no-session-persistence --tools "" --strict-mcp-config --mcp-config '{"mcpServers":{}}' --setting-sources user --disable-slash-commands --permission-mode default --system-prompt <text> <prompt>`，从 stdout JSON 的 `structured_output` 字段直接拿结构化结果。OAuth 凭证、token refresh、必需的 identity prefix system prompt 都由 `claude` CLI 自管，runtime 不触碰 keychain。

冷启动开销 ≈ 1 秒；不适合超低延迟场景。

## 失败语义

| 场景 | 异常 | 失败分类 | 调用方应如何处理 |
|---|---|---|---|
| codex auth.json 缺失 / token 过期 / 401 / 403 | `CodexAuthError` | infra_level | 提示用户跑 `codex login` |
| codex 429（限流） | `CodexRateLimitError` | infra_level | 等待或换 backend |
| codex 5xx | `CodexResponsesError` | infra_level | 重试或上报 |
| claude CLI 不在 PATH / `binary_path` 错 | `ClaudeCodeError` | infra_level | 安装 claude CLI 或修配置 |
| claude CLI 退出码非零 / `is_error: true` | `ClaudeCodeError` | infra_level | 看 stderr / `claude /login` 重登 |
| claude CLI timeout | `ClaudeCodeError` | infra_level | 调大 `timeout_ms` 或减小 prompt |
| schema 校验失败 | `ParseValidationError` | task_level | 重试链耗尽即终止 |
| env 网关未开（codex / claude-code） | `ProviderConfigError` | infra_level | 设置对应 env 变量 |
| MiniMax / 其它 LiteLLM 路径 401/429/5xx | LiteLLM 原生异常 | 由 `classify_failure` 分类 | 同 LiteLLM 通用语义 |

所有异常最终被 `execute_with_fallback` 包成 `FallbackExecutionError`，原始异常在 `last_error` 字段里。

## 验证 / 测试

```bash
# 单元测试（mock 全网 / mock subprocess）
pytest tests/unit/ -v

# 全量回归
pytest tests/ --ignore=tests/regression/test_with_shared_fixtures.py
```

端到端 smoke（需要本机已登录对应 backend + 网关已开）：

<details>
<summary>codex smoke</summary>

```bash
export REASONER_RUNTIME_ENABLE_CODEX_OAUTH=1
python -c "
from pydantic import BaseModel
from reasoner_runtime import generate_structured
from reasoner_runtime.core.models import ReasonerRequest
from reasoner_runtime.config.models import ProviderProfile, CodexCliAuthSpec

class Pong(BaseModel):
    answer: str

req = ReasonerRequest(
    request_id='smoke-1', caller_module='manual', target_schema='Pong',
    configured_provider='openai-codex', configured_model='gpt-5.5',
    max_retries=0,
    messages=[
        {'role': 'system', 'content': 'You are a JSON-only responder.'},
        {'role': 'user', 'content': 'Reply with {\"answer\":\"pong\"}.'},
    ],
    metadata={},
)
profile = ProviderProfile(provider='openai-codex', model='gpt-5.5',
                          timeout_ms=60000, auth=CodexCliAuthSpec())
print(generate_structured(req, schema_registry={'Pong': Pong},
                          provider_profiles=[profile]).parsed_result)
"
```
</details>

<details>
<summary>claude-code smoke</summary>

```bash
export REASONER_RUNTIME_ENABLE_CLAUDE_CODE_CLI=1
python -c "
from pydantic import BaseModel
from reasoner_runtime import generate_structured
from reasoner_runtime.core.models import ReasonerRequest
from reasoner_runtime.config.models import ProviderProfile, ClaudeCodeCliAuthSpec

class Pong(BaseModel):
    answer: str

req = ReasonerRequest(
    request_id='smoke-cc-1', caller_module='manual', target_schema='Pong',
    configured_provider='claude-code', configured_model='claude-sonnet-4-6',
    max_retries=0,
    messages=[
        {'role': 'system', 'content': 'You are a JSON-only responder.'},
        {'role': 'user', 'content': 'Reply with {\"answer\":\"pong\"}.'},
    ],
    metadata={},
)
profile = ProviderProfile(provider='claude-code', model='claude-sonnet-4-6',
                          timeout_ms=60000, auth=ClaudeCodeCliAuthSpec())
print(generate_structured(req, schema_registry={'Pong': Pong},
                          provider_profiles=[profile]).parsed_result)
"
```
</details>

## 边界（CLAUDE.md 强约束）

- ✅ 本模块拥有：统一调用入口 / fallback / retry / scrub / replay / health
- ❌ 不拥有：业务 prompt、analyzer、Iceberg/PostgreSQL 写入、Dagster resource 装配、API key 注入逻辑
- ❌ replay bundle 5 字段不可缺漏：`sanitized_input` / `input_hash` / `raw_output` / `parsed_result` / `output_hash`
- ❌ `max_retries` 不可隐式（必须由调用方显式传入）
- ❌ 不在三个 backend 之间自动降级（启动时由 setup wizard 选定一个）

详见 [`CLAUDE.md`](CLAUDE.md) §"严格非目标"和"审查 Checklist"。
