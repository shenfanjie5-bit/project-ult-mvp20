# 项目任务拆解

## 阶段 0：图谱性能与模型 Spike

**目标**：验证 Neo4j + GDS 在目标规模下可承受，搭建项目基础设施与核心领域模型
**前置依赖**：无

### ISSUE-001: 项目基础设施、Neo4j 连接层、Schema 定义与核心领域模型
**labels**: P0, infrastructure, milestone-0

#### 背景与目标
`graph-engine` 是一个从零开始的 Python 项目，当前仅有 scaffold 文件（§14）。在实现任何图谱能力之前，必须先搭建完整的项目骨架、Neo4j 连接管理层、基础 schema 定义与所有核心领域模型。本 issue 覆盖项目的地基层：包括 `pyproject.toml` 依赖声明、`graph_engine/` 包结构、Neo4j 驱动封装（§15 技术选型）、节点/边/索引/约束的 Cypher DDL（§14 `graph_engine.schema`）、以及 §9.1 中定义的全部 7 个持久层领域对象的 Pydantic 模型。这些模型是后续所有 issue 的数据契约基础——promotion、propagation、snapshot、status 都依赖这些模型定义。Schema 设计必须支持 §11.1-§11.5 中描述的所有算法对图结构的要求。

#### 所属模块
**主要写入路径：**
- `graph_engine/__init__.py`（包入口）
- `graph_engine/config.py`（Neo4j 连接配置）
- `graph_engine/client.py`（Neo4j 驱动封装）
- `graph_engine/models.py`（§9.1 全部持久层领域模型）
- `graph_engine/schema/__init__.py`
- `graph_engine/schema/definitions.py`（节点标签、关系类型枚举）
- `graph_engine/schema/indexes.py`（索引与约束 Cypher DDL）
- `graph_engine/schema/manager.py`（schema 应用/校验/清除）
- `graph_engine/promotion/__init__.py`（空包占位）
- `graph_engine/sync/__init__.py`（空包占位）
- `graph_engine/propagation/__init__.py`（空包占位）
- `graph_engine/snapshots/__init__.py`（空包占位）
- `graph_engine/reload/__init__.py`（空包占位）
- `graph_engine/status/__init__.py`（空包占位）
- `graph_engine/query/__init__.py`（空包占位）
- `pyproject.toml`（依赖声明更新）
- `tests/__init__.py`
- `tests/conftest.py`（共享 fixtures）
- `tests/unit/__init__.py`
- `tests/unit/test_config.py`
- `tests/unit/test_client.py`
- `tests/unit/test_models.py`
- `tests/unit/test_schema.py`
- `tests/integration/__init__.py`

**只读参考路径：**
- `docs/graph-engine.project-doc.md`（§9、§10、§14、§15 领域对象与技术选型定义）
- `CLAUDE.md`（不可协商约束参照）

**禁止修改路径：**
- `docs/graph-engine.project-doc.md`（项目文档只读）
- 任何 `main-core`、`contracts`、`data-platform` 等外部模块路径

#### 实现范围
**项目骨架：**
- `pyproject.toml`: 添加依赖 `neo4j>=5.0`, `pydantic>=2.0`, `pytest>=8.0`, `pytest-asyncio`, `mypy`, `ruff` 到 `[project.dependencies]` 和 `[project.optional-dependencies.dev]`；配置 `[tool.setuptools.packages]` 为 `find` 模式
- `graph_engine/__init__.py`: 包版本声明 `__version__ = "0.1.0"`；暴露核心公共 API 名称
- 所有子包 `__init__.py`: 空文件占位（`promotion/`, `sync/`, `propagation/`, `snapshots/`, `reload/`, `status/`, `query/`）

**配置模块：**
- `graph_engine/config.py`:
  - `class Neo4jConfig(BaseModel)` — 字段：`uri: str = "bolt://localhost:7687"`, `user: str = "neo4j"`, `password: str`, `database: str = "neo4j"`, `max_connection_pool_size: int = 50`, `connection_timeout_seconds: float = 30.0`
  - `def load_config_from_env() -> Neo4jConfig` — 从环境变量 `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` 读取

**Neo4j 客户端：**
- `graph_engine/client.py`:
  - `class Neo4jClient` — 封装 `neo4j.GraphDatabase.driver`
  - `def __init__(self, config: Neo4jConfig) -> None`
  - `def connect(self) -> None` — 创建 driver 实例
  - `def close(self) -> None` — 关闭 driver
  - `def execute_read(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]` — 只读事务
  - `def execute_write(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]` — 写事务
  - `def verify_connectivity(self) -> bool` — 连通性校验
  - `def __enter__(self) -> Neo4jClient` / `def __exit__(self, *args: Any) -> None` — 上下文管理器

**核心领域模型（§9.1 持久层对象）：**
- `graph_engine/models.py`:
  - `class GraphNodeRecord(BaseModel)` — 字段：`node_id: str`, `canonical_entity_id: str`, `label: str`, `properties: dict[str, Any]`, `created_at: datetime`, `updated_at: datetime`
  - `class GraphEdgeRecord(BaseModel)` — 字段：`edge_id: str`, `source_node_id: str`, `target_node_id: str`, `relationship_type: str`, `properties: dict[str, Any]`, `weight: float = 1.0`, `created_at: datetime`, `updated_at: datetime`
  - `class GraphAssertionRecord(BaseModel)` — 字段：`assertion_id: str`, `source_node_id: str`, `target_node_id: str | None`, `assertion_type: str`, `evidence: dict[str, Any]`, `confidence: float`, `created_at: datetime`
  - `class CandidateGraphDelta(BaseModel)` — 字段按 §9.3：`delta_id: str`, `cycle_id: str`, `delta_type: Literal["node_add", "edge_add", "edge_update", "assertion_add"]`, `source_entity_ids: list[str]`, `payload: dict[str, Any]`, `validation_status: Literal["validated", "rejected", "frozen"]`
  - `class GraphSnapshot(BaseModel)` — 字段按 §9.3：`cycle_id: str`, `snapshot_id: str`, `graph_generation_id: int`, `node_count: int`, `edge_count: int`, `key_label_counts: dict[str, int]`, `checksum: str`, `created_at: datetime`
  - `class GraphImpactSnapshot(BaseModel)` — 字段按 §9.3：`cycle_id: str`, `impact_snapshot_id: str`, `regime_context_ref: str`, `activated_paths: list[dict[str, Any]]`, `impacted_entities: list[dict[str, Any]]`, `channel_breakdown: dict[str, Any]`
  - `class Neo4jGraphStatus(BaseModel)` — 字段按 §9.3：`graph_status: Literal["ready", "rebuilding", "failed"]`, `graph_generation_id: int`, `node_count: int`, `edge_count: int`, `key_label_counts: dict[str, int]`, `checksum: str`, `last_verified_at: datetime | None`, `last_reload_at: datetime | None`

**Schema 定义与管理：**
- `graph_engine/schema/definitions.py`:
  - `class NodeLabel(str, Enum)` — 定义核心节点标签：`ENTITY`, `SECTOR`, `INDUSTRY`, `REGION`, `EVENT`, `ASSERTION`
  - `class RelationshipType(str, Enum)` — 定义核心关系类型：`SUPPLY_CHAIN`, `OWNERSHIP`, `INDUSTRY_CHAIN`, `SECTOR_MEMBERSHIP`, `EVENT_IMPACT`, `ASSERTION_LINK`
- `graph_engine/schema/indexes.py`:
  - `def get_index_statements() -> list[str]` — 返回所有 `CREATE INDEX` Cypher 语句
  - `def get_constraint_statements() -> list[str]` — 返回所有 `CREATE CONSTRAINT` 语句（如 node_id 唯一性）
- `graph_engine/schema/manager.py`:
  - `class SchemaManager`
  - `def __init__(self, client: Neo4jClient) -> None`
  - `def apply_schema(self) -> None` — 幂等地创建所有索引与约束
  - `def verify_schema(self) -> bool` — 校验所有必需的索引和约束是否存在
  - `def drop_all(self) -> None` — 清除所有节点/边/索引（仅用于测试和 Cold Reload）

**测试基础设施：**
- `tests/conftest.py`:
  - `@pytest.fixture def neo4j_config() -> Neo4jConfig` — 返回测试用配置
  - `@pytest.fixture def mock_neo4j_client() -> Neo4jClient` — 返回 mock 客户端（单元测试用）
- `tests/unit/test_config.py`: 测试 `load_config_from_env` 环境变量解析、默认值
- `tests/unit/test_client.py`: 测试 `Neo4jClient` 初始化、上下文管理器协议、mock 连接
- `tests/unit/test_models.py`: 测试所有 7 个 Pydantic 模型的序列化、反序列化、字段验证、`validation_status` / `delta_type` 枚举约束
- `tests/unit/test_schema.py`: 测试 `get_index_statements()` / `get_constraint_statements()` 返回合法 Cypher、`SchemaManager.verify_schema` 逻辑

#### 不在本次范围
- 不实现 graph promotion 逻辑（归 ISSUE-003）
- 不实现 propagation 算法（归 ISSUE-004）
- 不实现 `neo4j_graph_status` 状态机流转逻辑（归 ISSUE-005）
- 不实现 Cold Reload 流程（归 ISSUE-006）
- 不定义 §9.2 运行时对象（`PromotionPlan`、`PropagationContext` 等），由各自 issue 创建
- 不连接真实 Iceberg / PostgreSQL，持久层接口用抽象协议预留
- 如发现需要修改 `contracts` 模块的 schema 定义，必须拆出独立 issue 而不是在本 issue 中越界

#### 关键交付物
- `Neo4jConfig` 配置类：支持环境变量注入，字段类型 `str | int | float`，带默认值
- `Neo4jClient` 驱动封装类：`execute_read(query, params) -> list[dict]`、`execute_write(query, params) -> list[dict]`、`verify_connectivity() -> bool`，支持上下文管理器
- 7 个 Pydantic 持久层模型：`GraphNodeRecord`, `GraphEdgeRecord`, `GraphAssertionRecord`, `CandidateGraphDelta`, `GraphSnapshot`, `GraphImpactSnapshot`, `Neo4jGraphStatus`，每个模型具备完整的字段类型注解和验证规则
- `NodeLabel` 和 `RelationshipType` 枚举类：覆盖 §9 中所有核心图元素类型
- `get_index_statements() -> list[str]` 和 `get_constraint_statements() -> list[str]`：返回幂等 Cypher DDL
- `SchemaManager` 类：`apply_schema()` 幂等创建、`verify_schema() -> bool` 校验、`drop_all()` 清除
- 错误处理：`Neo4jClient` 在连接失败时抛出 `ConnectionError`；模型验证失败抛出 Pydantic `ValidationError`
- `tests/conftest.py` 共享 fixtures：`neo4j_config`、`mock_neo4j_client`
- 更新后的 `pyproject.toml`：声明所有运行时和开发依赖

#### 验收标准
**Core functionality:**
- [ ] `pip install -e ".[dev]"` 在干净环境中成功，所有依赖可解析
- [ ] `from graph_engine.models import CandidateGraphDelta, GraphSnapshot, GraphImpactSnapshot, Neo4jGraphStatus` 导入成功
- [ ] 所有 7 个 Pydantic 模型可正确序列化/反序列化 JSON，字段约束（Literal 枚举、类型校验）生效
- [ ] `CandidateGraphDelta(validation_status="invalid")` 抛出 `ValidationError`
- [ ] `Neo4jClient` 支持上下文管理器协议（`__enter__` / `__exit__`）
- [ ] `Neo4jClient.verify_connectivity()` 在连接不可用时返回 `False` 而不是异常崩溃
**Schema:**
- [ ] `get_index_statements()` 返回 >= 4 条合法 `CREATE INDEX` 语句
- [ ] `get_constraint_statements()` 返回 >= 2 条合法 `CREATE CONSTRAINT` 语句（至少覆盖 node_id 唯一性）
- [ ] `SchemaManager.apply_schema()` 幂等——重复调用不报错
**Infrastructure:**
- [ ] `graph_engine/` 下所有 8 个子包（schema, promotion, sync, propagation, snapshots, reload, status, query）均可 import
- [ ] `mypy graph_engine/` 零错误通过
- [ ] `ruff check graph_engine/` 零警告通过
**Tests:**
- [ ] 单元测试 >= 20 个，覆盖配置加载、客户端初始化、全部 7 个模型验证、schema DDL 生成、SchemaManager 逻辑
- [ ] 所有测试通过：`pytest tests/unit/ -q` 退出码 0

#### 验证命令
```bash
# 安装
pip install -e ".[dev]"

# 单元测试
pytest tests/unit/test_config.py tests/unit/test_client.py tests/unit/test_models.py tests/unit/test_schema.py -v

# 导入检查
python -c "from graph_engine.models import CandidateGraphDelta, GraphSnapshot, GraphImpactSnapshot, Neo4jGraphStatus; print('models OK')"
python -c "from graph_engine.client import Neo4jClient; from graph_engine.config import Neo4jConfig; print('client OK')"
python -c "from graph_engine.schema.manager import SchemaManager; from graph_engine.schema.definitions import NodeLabel, RelationshipType; print('schema OK')"

# 类型检查
mypy graph_engine/

# 风格检查
ruff check graph_engine/

# 回归（全量）
pytest tests/ -q
```

#### 依赖
无前置依赖

---

### ISSUE-002: GDS 规模压测脚本与传播预算验证
**labels**: P0, testing, milestone-0

#### 背景与目标
在进入正式图谱主干开发之前，必须先验证 Neo4j + GDS 在目标规模（10 万节点 / 50-100 万边）下的传播性能是否落在 §19.1 定义的预算内：单轮传播 < 60 秒、一致性校验 < 5 秒、Cold Reload < 90 秒（§21 阶段 0 退出条件）。本 issue 交付完整的压测脚本套件：合成图生成器、GDS projection 创建与传播算法基准测试、性能结果采集与报告生成。这是 §21 阶段 0 的核心交付物，直接决定后续传播算法的设计约束。如果 Lite 规模传播无法在 1 分钟内完成，则需要在进入 P3a 之前调整 schema 或传播策略。

#### 所属模块
**主要写入路径：**
- `benchmarks/__init__.py`
- `benchmarks/conftest.py`（压测共享 fixtures）
- `benchmarks/generate_synthetic.py`（合成图数据生成）
- `benchmarks/run_benchmark.py`（GDS 传播基准测试）
- `benchmarks/report.py`（结果采集与报告输出）
- `tests/unit/test_benchmark_generate.py`
- `tests/integration/test_benchmark_neo4j.py`

**只读参考路径：**
- `graph_engine/client.py`（调用 `Neo4jClient` 执行 Cypher）
- `graph_engine/config.py`（调用 `load_config_from_env`）
- `graph_engine/schema/manager.py`（调用 `SchemaManager.apply_schema()` 初始化 schema）
- `graph_engine/schema/definitions.py`（引用 `NodeLabel`, `RelationshipType` 枚举）
- `graph_engine/models.py`（引用 `GraphNodeRecord`, `GraphEdgeRecord` 作为生成模板）

**禁止修改路径：**
- `graph_engine/` 下已有代码（ISSUE-001 交付物）——只调用，不修改
- `docs/graph-engine.project-doc.md`

#### 实现范围
**合成图生成器：**
- `benchmarks/generate_synthetic.py`:
  - `def generate_synthetic_nodes(count: int, labels: list[str]) -> list[dict[str, Any]]` — 生成指定数量节点，随机分配标签，每个节点包含 `node_id`, `canonical_entity_id`, `label`, `properties`
  - `def generate_synthetic_edges(nodes: list[dict[str, Any]], edge_count: int, relationship_types: list[str]) -> list[dict[str, Any]]` — 基于节点列表生成指定数量的边，随机分配关系类型和权重
  - `def load_synthetic_graph(client: Neo4jClient, nodes: list[dict[str, Any]], edges: list[dict[str, Any]], batch_size: int = 5000) -> None` — 分批写入 Neo4j（使用 `UNWIND` 批量 MERGE）
  - `def clear_graph(client: Neo4jClient) -> None` — 清空 Neo4j 全部数据

**GDS 基准测试：**
- `benchmarks/run_benchmark.py`:
  - `@dataclass class BenchmarkResult` — 字段：`operation: str`, `node_count: int`, `edge_count: int`, `duration_seconds: float`, `memory_mb: float | None`, `passed: bool`
  - `def benchmark_gds_projection_create(client: Neo4jClient, graph_name: str) -> BenchmarkResult` — 创建 GDS 命名投影并计时
  - `def benchmark_pagerank(client: Neo4jClient, graph_name: str, max_iterations: int = 20) -> BenchmarkResult` — 在投影图上执行 PageRank
  - `def benchmark_path_traversal(client: Neo4jClient, seed_node_id: str, max_depth: int = 5) -> BenchmarkResult` — BFS/DFS 路径遍历计时
  - `def benchmark_cold_reload_simulation(client: Neo4jClient, nodes: list[dict], edges: list[dict]) -> BenchmarkResult` — 清空 + 全量重建 + 索引重建计时
  - `def benchmark_consistency_check(client: Neo4jClient, expected_node_count: int, expected_edge_count: int) -> BenchmarkResult` — 计数校验计时
  - `def run_full_benchmark_suite(client: Neo4jClient, target_nodes: int = 100_000, target_edge_factor: int = 8) -> list[BenchmarkResult]` — 编排全部测试

**报告生成：**
- `benchmarks/report.py`:
  - `def generate_text_report(results: list[BenchmarkResult], budget: dict[str, float]) -> str` — 生成人类可读文本报告，包含 PASS/FAIL 标记
  - `def check_budgets(results: list[BenchmarkResult], budget: dict[str, float]) -> bool` — 按 §19.1 预算检查是否全部通过
  - 预算默认值：`{"propagation": 60.0, "consistency_check": 5.0, "cold_reload": 90.0, "cold_reload_hard": 300.0}`

**测试：**
- `tests/unit/test_benchmark_generate.py`: 测试合成数据生成的正确性（节点格式、边引用有效性、标签分布）
- `tests/integration/test_benchmark_neo4j.py`: 小规模（1000 节点 / 5000 边）集成测试，验证 load + projection + PageRank 流程可跑通

#### 不在本次范围
- 不实现正式的传播算法（fundamental / event / reflexive），只用 GDS 内置 PageRank 和路径遍历做预算验证
- 不修改 `graph_engine/` 下任何已有代码
- 不生成正式 `GraphSnapshot` 或 `GraphImpactSnapshot`——这是 ISSUE-004 的职责
- 不做 schema 优化或传播算法调参——如果预算不达标，记录结论并交由后续 issue 处理
- 不实现自动化 CI 集成（需要 Neo4j 服务）——本 issue 只交付手动可执行的脚本
- 如果发现 `Neo4jClient` 缺少 GDS 特有的调用方式，在 ISSUE-001 上追加而不是在本 issue 中修改

#### 关键交付物
- `generate_synthetic_nodes(count, labels) -> list[dict]`：生成合成节点，支持 10 万级规模
- `generate_synthetic_edges(nodes, edge_count, types) -> list[dict]`：生成合成边，支持 50-100 万级规模
- `load_synthetic_graph(client, nodes, edges, batch_size) -> None`：批量写入 Neo4j，使用 `UNWIND` + `MERGE` 模式
- `BenchmarkResult` dataclass：标准化测试结果结构
- `run_full_benchmark_suite(client, target_nodes, target_edge_factor) -> list[BenchmarkResult]`：一键执行全部基准测试
- `generate_text_report(results, budget) -> str`：输出包含 PASS/FAIL 判定的文本报告
- `check_budgets(results, budget) -> bool`：返回 §19.1 预算检查总结果
- 错误处理：GDS 不可用时 `benchmark_gds_projection_create` 抛出 `RuntimeError("GDS plugin not available")`；Neo4j 连接失败时所有 benchmark 函数抛出 `ConnectionError`
- 预算阈值配置：`propagation < 60s`, `consistency_check < 5s`, `cold_reload < 90s`, `cold_reload_hard < 300s`

#### 验收标准
**Core functionality:**
- [ ] `generate_synthetic_nodes(100_000, ["Entity", "Sector"])` 在 < 10 秒内生成 10 万节点
- [ ] `generate_synthetic_edges(nodes, 800_000, [...])` 生成 80 万边，所有边的 source/target 引用有效节点
- [ ] `load_synthetic_graph` 能将 10 万节点 / 80 万边写入 Neo4j（需要可用的 Neo4j 实例）
- [ ] `benchmark_gds_projection_create` 成功创建 GDS 命名投影并返回耗时
- [ ] `benchmark_pagerank` 在投影图上完成 PageRank 并返回耗时
**Budget verification:**
- [ ] `benchmark_pagerank` 结果的 `duration_seconds < 60.0`（Lite 规模）
- [ ] `benchmark_consistency_check` 结果的 `duration_seconds < 5.0`
- [ ] `benchmark_cold_reload_simulation` 结果的 `duration_seconds < 90.0`
- [ ] `check_budgets` 在全部预算通过时返回 `True`
**Reporting:**
- [ ] `generate_text_report` 输出包含每项测试名称、耗时、PASS/FAIL 标记的可读文本
**Tests:**
- [ ] 单元测试 >= 8 个，覆盖合成数据生成格式、引用完整性、报告格式
- [ ] 小规模集成测试可跑通（1000 节点 / 5000 边，需 Neo4j）
- [ ] 所有单元测试通过：`pytest tests/unit/test_benchmark_generate.py -q` 退出码 0

#### 验证命令
```bash
# 单元测试（不需要 Neo4j）
pytest tests/unit/test_benchmark_generate.py -v

# 集成测试（需要 Neo4j 可用）
pytest tests/integration/test_benchmark_neo4j.py -v

# 手动执行完整压测（需要 Neo4j + GDS）
python -m benchmarks.run_benchmark

# 回归
pytest tests/ -q
```

#### 依赖
依赖 #ISSUE-001（需要 `Neo4jClient`、`Neo4jConfig`、`SchemaManager`、`NodeLabel`、`RelationshipType` 和领域模型）

---

## 阶段 1：P3a 图谱主干

**目标**：打通 graph promotion、增量同步、单通道传播和 snapshot 回写的完整闭环
**前置依赖**：阶段 0

### ISSUE-003: Graph Promotion — CandidateGraphDelta 到正式图的提升与 Live Graph 同步
**labels**: P0, feature, milestone-1
**摘要**: 实现 §11.1 Graph Promotion 算法和 §11.2 增量同步算法：从冻结的 `CandidateGraphDelta` 生成 `PromotionPlan`，先写 Layer A canonical records，再通过 `MERGE/UPDATE` 操作同步到 Neo4j live graph。覆盖 `graph_engine.promotion` 和 `graph_engine.sync` 两个子包。
**所属模块**: `graph_engine/promotion/`（主要写入）+ `graph_engine/sync/`（主要写入）+ `graph_engine/models.py`（添加 `PromotionPlan` 运行时模型）；只读引用 `graph_engine/client.py`、`graph_engine/schema/`
**写入边界**: 允许修改 `graph_engine/promotion/`、`graph_engine/sync/`、`graph_engine/models.py`（仅追加 `PromotionPlan`）、`tests/unit/test_promotion.py`、`tests/unit/test_sync.py`、`tests/integration/test_promotion_sync.py`；禁止修改 `graph_engine/propagation/`、`graph_engine/snapshots/`、`graph_engine/reload/`、`graph_engine/status/`、`graph_engine/query/`
**实现顺序**: 先定义 `PromotionPlan` 运行时模型 → 实现 `validate_entity_anchors()` 校验 → 实现 `build_promotion_plan()` → 实现 Layer A 写入抽象接口 `CanonicalWriter`（协议类，具体实现留给 data-platform 对接）→ 实现 `promote_graph_deltas()` 主入口 → 实现 `sync_live_graph()` Neo4j 增量同步 → 实现幂等性保障 → 单元测试 → 集成测试
**依赖**: 依赖 #ISSUE-001（`Neo4jClient`、`CandidateGraphDelta`、`GraphNodeRecord`、`GraphEdgeRecord`、`GraphAssertionRecord`、`SchemaManager`）

---

### ISSUE-004: 单通道传播引擎与 Snapshot 生成回写
**labels**: P0, feature, milestone-1
**摘要**: 实现 §11.3 传播算法的 fundamental 单通道版本和 §11.4 Snapshot 生成算法：构建 `PropagationContext`，在 GDS 投影上执行 fundamental 传播，生成 `GraphSnapshot` 与 `GraphImpactSnapshot` 并回写 Layer A。覆盖 `graph_engine.propagation`（单通道）和 `graph_engine.snapshots`。
**所属模块**: `graph_engine/propagation/`（主要写入）+ `graph_engine/snapshots/`（主要写入）+ `graph_engine/models.py`（添加 `PropagationContext`、`PropagationResult` 运行时模型）；只读引用 `graph_engine/client.py`、`graph_engine/schema/`、`graph_engine/models.py`（`GraphSnapshot`、`GraphImpactSnapshot`）
**写入边界**: 允许修改 `graph_engine/propagation/`、`graph_engine/snapshots/`、`graph_engine/models.py`（仅追加运行时模型）、`tests/unit/test_propagation.py`、`tests/unit/test_snapshots.py`、`tests/integration/test_propagation_snapshot.py`；禁止修改 `graph_engine/promotion/`、`graph_engine/sync/`、`graph_engine/reload/`、`graph_engine/status/`、`graph_engine/query/`
**实现顺序**: 先定义 `PropagationContext` 和 `PropagationResult` 运行时模型 → 实现 `world_state_snapshot` 只读读取接口（协议类 `RegimeContextReader`）→ 实现 `build_propagation_context()` → 实现 fundamental 通道传播（使用 GDS PageRank + 自定义权重公式 `path_score = relation_weight * evidence_confidence * channel_multiplier * regime_multiplier * recency_decay`）→ 实现 `compute_graph_snapshots()` 主入口 → 实现 snapshot Layer A 回写抽象接口 `SnapshotWriter` → 单元测试 → 集成测试
**依赖**: 依赖 #ISSUE-003（需要已 promoted 的正式图才能执行传播）

---

## 阶段 2：P3a 运维闭环

**目标**：补齐 neo4j_graph_status 状态机、一致性校验和 Cold Reload，使 Neo4j 可被清空、重建、校验并重新进入 ready
**前置依赖**：阶段 1

### ISSUE-005: Neo4j Graph Status 状态机与一致性校验
**labels**: P0, feature, milestone-2
**摘要**: 实现 §9.3 `Neo4jGraphStatus` 的状态机流转（`ready -> rebuilding -> ready/failed`）和 §8.1 Phase 0 一致性主线中的 `check_live_graph_consistency()` 逻辑。覆盖 `graph_engine.status` 子包。所有读取 Neo4j 的动作必须先校验 `graph_status == ready`（§不可协商约束 7），本 issue 交付该 status guard 机制。
**所属模块**: `graph_engine/status/`（主要写入）+ `graph_engine/models.py`（`Neo4jGraphStatus` 已存在，可能追加辅助方法）；只读引用 `graph_engine/client.py`、`graph_engine/models.py`
**写入边界**: 允许修改 `graph_engine/status/`、`tests/unit/test_status.py`、`tests/integration/test_status.py`；禁止修改 `graph_engine/promotion/`、`graph_engine/sync/`、`graph_engine/propagation/`、`graph_engine/snapshots/`、`graph_engine/reload/`、`graph_engine/query/`
**实现顺序**: 先实现 `GraphStatusManager` 状态读写（PostgreSQL 当前态抽象接口 `StatusStore` 协议类）→ 实现状态流转规则（`ready -> rebuilding`, `rebuilding -> ready/failed`, `failed -> rebuilding`）→ 实现 `status_guard` 装饰器或检查函数 → 实现 `check_live_graph_consistency(snapshot_ref)` 对比 Neo4j 与 Iceberg 计数/checksum → 单元测试（状态机全路径）→ 集成测试
**依赖**: 依赖 #ISSUE-001（`Neo4jClient`、`Neo4jGraphStatus` 模型）

---

### ISSUE-006: Cold Reload 全量重建与 GDS Projection 恢复
**labels**: P0, feature, milestone-2
**摘要**: 实现 §11.5 Cold Reload 算法：从 Iceberg 全量清空并重建 Neo4j live graph，重建索引与 GDS projection，校验 node_count + edge_count + checksum，成功后 bump `graph_generation_id` 并置 `graph_status = ready`。覆盖 `graph_engine.reload` 子包。Cold Reload 是正式主路径（设计原则 4），不是异常补丁。
**所属模块**: `graph_engine/reload/`（主要写入）+ `graph_engine/models.py`（添加 `ColdReloadPlan` 运行时模型）；只读引用 `graph_engine/client.py`、`graph_engine/schema/manager.py`（`drop_all`、`apply_schema`）、`graph_engine/status/`（状态流转）
**写入边界**: 允许修改 `graph_engine/reload/`、`graph_engine/models.py`（仅追加 `ColdReloadPlan`）、`tests/unit/test_reload.py`、`tests/integration/test_reload.py`；禁止修改 `graph_engine/promotion/`、`graph_engine/propagation/`、`graph_engine/snapshots/`、`graph_engine/query/`
**实现顺序**: 先定义 `ColdReloadPlan` 运行时模型 → 实现 Iceberg 全量读取抽象接口 `CanonicalReader`（协议类）→ 实现 `cold_reload(snapshot_ref)` 主入口：`set rebuilding` → `drop_all` → `full load from Iceberg` → `apply_schema` → `rebuild GDS projection` → `verify counts + checksum` → `set ready + bump generation_id` 或 `set failed` → 实现硬超时（< 5 分钟）→ 单元测试 → 集成测试
**依赖**: 依赖 #ISSUE-005（需要 `GraphStatusManager` 进行状态流转）

---

## 阶段 3：P3b 完整传播

**目标**：补齐 event / reflexive 两类传播通道，实现三通道融合与 regime-aware 权重调整，使正式 impact snapshot 稳定产出
**前置依赖**：阶段 2

### ISSUE-007: Event 与 Reflexive 传播通道实现
**labels**: P1, feature, milestone-3
**摘要**: 在 ISSUE-004 交付的 fundamental 单通道基础上，实现 §11.3 中 event 通道（公告/政策/制裁/停复牌事件冲击传播）和 reflexive 通道（资金/情绪/行为反馈与二阶影响传播）。每个通道使用独立的 `channel_multiplier` 和衰减策略，但共享 `path_score` 核心公式。不得退化成不可解释的黑盒分数。
**所属模块**: `graph_engine/propagation/`（主要写入，新增 `event.py`、`reflexive.py` 或在已有传播模块中扩展）；只读引用 `graph_engine/client.py`、`graph_engine/models.py`
**写入边界**: 允许修改 `graph_engine/propagation/`、`tests/unit/test_propagation_event.py`、`tests/unit/test_propagation_reflexive.py`；禁止修改 `graph_engine/promotion/`、`graph_engine/sync/`、`graph_engine/snapshots/`（通道融合归 ISSUE-008）、`graph_engine/reload/`、`graph_engine/query/`
**实现顺序**: 先实现 event 通道传播逻辑（事件冲击权重、影响路径）→ 再实现 reflexive 通道传播逻辑（二阶反馈、情绪衰减）→ 每个通道独立可测 → 单元测试覆盖各通道的权重计算与路径选择
**依赖**: 依赖 #ISSUE-004（需要 fundamental 通道实现和 `PropagationContext` / `PropagationResult` 模型作为模板）

---

### ISSUE-008: 三通道融合、Regime-aware 权重调整与完整 Impact Snapshot
**labels**: P1, algorithm, milestone-3
**摘要**: 实现 §11.3 中的 channel merge 逻辑：将 fundamental、event、reflexive 三通道的传播结果按权重融合，应用 `regime_multiplier`（来自只读 `world_state_snapshot`）和 `recency_decay`，输出完整的 `channel_breakdown` 字段。更新 `graph_engine.snapshots` 使 `GraphImpactSnapshot` 包含完整的三通道分解。核心公式 `path_score = relation_weight * evidence_confidence * channel_multiplier * regime_multiplier * recency_decay` 的每一项必须可解释、可审计。
**所属模块**: `graph_engine/propagation/`（主要写入，新增 `merge.py` 或融合逻辑）+ `graph_engine/snapshots/`（更新以支持完整 channel_breakdown）；只读引用 `graph_engine/models.py`、`graph_engine/status/`
**写入边界**: 允许修改 `graph_engine/propagation/`（merge 逻辑）、`graph_engine/snapshots/`（更新 snapshot 生成逻辑）、`tests/unit/test_propagation_merge.py`、`tests/integration/test_full_propagation.py`；禁止修改 `graph_engine/promotion/`、`graph_engine/sync/`、`graph_engine/reload/`、`graph_engine/query/`
**实现顺序**: 先实现 channel merge 函数（三通道结果合并）→ 实现 regime_multiplier 读取与应用 → 实现 recency_decay 时间衰减 → 更新 snapshot 生成逻辑以包含 `channel_breakdown` → 端到端集成测试：三通道传播 + merge + impact snapshot 生成
**依赖**: 依赖 #ISSUE-007（需要 event 和 reflexive 通道实现）

---

## 阶段 4：P3b 只读服务与消费方接入

**目标**：为 main-core、audit-eval、stream-layer 提供稳定的只读图查询与局部模拟接口
**前置依赖**：阶段 3

### ISSUE-009: 子图查询与传播路径查询接口
**labels**: P1, feature, milestone-4
**摘要**: 实现 §16.1 中的 `query_subgraph(seed_entities, depth)` 和传播路径查询能力。覆盖 `graph_engine.query` 子包。所有查询必须先通过 status guard 校验 `graph_status == ready`（§不可协商约束 7）。返回 §13.3 定义的 `GraphQueryResult` 结构。
**所属模块**: `graph_engine/query/`（主要写入）；只读引用 `graph_engine/client.py`、`graph_engine/status/`（status guard）、`graph_engine/models.py`
**写入边界**: 允许修改 `graph_engine/query/`、`graph_engine/models.py`（追加 `GraphQueryResult` 如未有）、`tests/unit/test_query.py`、`tests/integration/test_query.py`；禁止修改 `graph_engine/promotion/`、`graph_engine/propagation/`、`graph_engine/reload/`；禁止在查询路径中写入 Neo4j
**实现顺序**: 先定义 `GraphQueryResult` 模型 → 实现 `query_subgraph()` BFS 子图查询 → 实现传播路径查询（沿 impact 路径回溯）→ 集成 status guard → 单元测试 → 集成测试
**依赖**: 依赖 #ISSUE-005（需要 status guard 机制）

---

### ISSUE-010: 只读局部传播模拟与消费方接入样例
**labels**: P1, feature, milestone-4
**摘要**: 实现 §11.6 Read-only 局部模拟算法和 §16.1 中的 `simulate_readonly_impact(seed_entities, context)` 接口。在 Neo4j 上创建只读命名投影，执行局部传播模拟，返回 interim impact 结果后销毁投影。严格禁止写 live graph 和产出正式 snapshot（§不可协商约束 4）。同时交付面向 `main-core`、`stream-layer` 的消费方接入样例代码。
**所属模块**: `graph_engine/query/`（主要写入，扩展只读模拟能力）+ `examples/`（消费方接入样例）；只读引用 `graph_engine/client.py`、`graph_engine/propagation/`（复用传播算法逻辑）、`graph_engine/status/`
**写入边界**: 允许修改 `graph_engine/query/`、`graph_engine/models.py`（追加 `ReadonlySimulationRequest`）、`examples/consumer_main_core.py`、`examples/consumer_stream_layer.py`、`tests/unit/test_simulation.py`、`tests/integration/test_simulation.py`；禁止修改 `graph_engine/promotion/`、`graph_engine/sync/`、`graph_engine/reload/`；禁止在模拟路径中写入 live graph 或生成正式 snapshot
**实现顺序**: 先定义 `ReadonlySimulationRequest` 运行时模型 → 实现 `simulate_readonly_impact()` 主入口 → 实现只读命名投影创建与销毁 → 复用传播引擎在只读投影上执行局部传播 → 实现回归测试确保不写 live graph → 编写消费方样例代码 → 集成测试
**依赖**: 依赖 #ISSUE-008（需要完整的三通道传播引擎作为模拟基础）和 #ISSUE-009（需要子图查询能力和 status guard 集成）
