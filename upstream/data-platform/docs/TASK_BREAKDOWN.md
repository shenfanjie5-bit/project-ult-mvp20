# 项目任务拆解

> 基于 `data-platform.project-doc.md` v0.1.1 §21 实施路线图拆分。
> 阶段 0（P1a 骨架）使用完整 8 段 body；阶段 1（P1b 铺量）与阶段 2（P1c 摄取与 cycle 控制）使用骨架格式，待 milestone 启动前自动细化。

## 阶段 0：P1a 骨架 —— 最小数据链路打通

**目标**：打通 1 个 API → Raw → staging → Canonical → DuckDB 读取的最小闭环，并完成 Iceberg 写入链 spike。
**前置依赖**：无

### ISSUE-001: 项目脚手架与 Python 包结构初始化
**labels**: P0, milestone-0, infrastructure

#### 背景与目标
按照项目文档 §14 的模块拆分与 §15 的技术路线，建立 `data-platform` 子项目的 Python 包结构与依赖管理基线，使后续所有 P1a issue 都能在统一的工程骨架内实现。当前仓库只有 README/CLAUDE.md/pyproject.toml 等占位文件，必须先固化包目录与依赖锁，避免后续 issue 各自定义模块路径。

#### 所属模块
data_platform（顶层包）+ pyproject.toml + scripts/

#### 实现范围
- 在 `src/data_platform/` 下创建子包：`raw/`、`adapters/`、`queue/`、`cycle/`、`serving/`、`ddl/`、`dbt/`，每个子包带 `__init__.py` 与 `README.md` 占位
- 在 `pyproject.toml` 写入运行依赖：`pyiceberg[sql-postgres,pyarrow]`、`duckdb>=1.0`、`dbt-core>=1.7`、`dbt-duckdb>=1.7`、`sqlalchemy>=2.0`、`psycopg[binary]>=3.1`、`pydantic>=2`、`pandas`、`pyarrow`
- 在 `pyproject.toml` 写入开发依赖：`pytest>=8`、`pytest-cov`、`ruff`、`mypy`、`pre-commit`
- 配置 `[tool.ruff]`、`[tool.mypy]`、`[tool.pytest.ini_options]`，启用 src 布局
- 创建 `scripts/bootstrap_dev.sh`：创建 venv、安装 dependencies、安装 pre-commit hook
- 在 `tests/` 下建立镜像目录，写一个最小 `tests/test_smoke.py` 验证包可被 import

#### 不在本次范围
- 不写任何业务逻辑、表结构或 adapter
- 不引入 Dagster / orchestrator 依赖（违反 OWN/BAN 边界）
- 不引入 LLM SDK
- 不创建 dbt 项目（留给 ISSUE-009）

#### 关键交付物
- `pyproject.toml` 包含 `[project]` 元信息与依赖锁；`requires-python = ">=3.12"`
- 包结构 `src/data_platform/{raw,adapters,queue,cycle,serving,ddl,dbt}/__init__.py`
- `scripts/bootstrap_dev.sh` 可执行（chmod +x），脚本失败时退出码非零
- `tests/test_smoke.py` 至少包含 `def test_import_data_platform(): import data_platform`
- ruff 行宽 100、target Python 3.12
- mypy `strict = true`、忽略 `dbt`、`pyiceberg.cli`

#### 验收标准
- [ ] `pip install -e .[dev]` 在干净 venv 内一次成功
- [ ] `pytest -q` 通过且 ≥1 用例
- [ ] `ruff check src tests` 无错误
- [ ] `python -c "import data_platform; import data_platform.raw; import data_platform.adapters; import data_platform.queue; import data_platform.cycle; import data_platform.serving"` 退出码 0
- [ ] `pyproject.toml` 内未出现 dagster、langchain、openai、anthropic 等 BAN 依赖

#### 验证命令
```bash
cd <workspace>/data-platform
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
pytest -q
python -c "import data_platform.raw, data_platform.adapters, data_platform.queue, data_platform.cycle, data_platform.serving, data_platform.ddl"
```

#### 依赖
无前置依赖

---

### ISSUE-002: 配置加载与运行环境管理
**labels**: P0, milestone-0, infrastructure

#### 背景与目标
项目文档 §15 要求 PostgreSQL、DuckDB、Iceberg catalog 共享一份配置；§25 要求自动化脚本可读取统一参数。需要建立基于 pydantic-settings 的配置层，集中管理数据库连接、Raw Zone 路径、Iceberg warehouse 路径与 DuckDB 路径，避免后续 issue 各自硬编码。

#### 所属模块
data_platform.config

#### 实现范围
- 新建 `src/data_platform/config/__init__.py` 与 `settings.py`
- 定义 `Settings(BaseSettings)`：`pg_dsn: PostgresDsn`、`data_storage_root_path: Path`、`raw_zone_path: Path`、`processed_data_path: Path`、`iceberg_warehouse_path: Path`、`duckdb_path: Path`、`iceberg_catalog_name: str = "data_platform"`、`env: Literal["dev","test","prod"] = "dev"`
- 支持从 `.env` 与环境变量加载（前缀 `DP_`）
- 提供 `get_settings() -> Settings`（lru_cache），并提供 `reset_settings_cache()` 用于测试
- 提供 `.env.example` 与 `tests/test_config.py`

#### 不在本次范围
- 不创建 PG schema 或 Iceberg catalog（留给 ISSUE-003 / ISSUE-004）
- 不实现日志框架（依赖标准 logging 即可）
- 不解析 dbt profile（dbt 自管）

#### 关键交付物
- 类签名 `class Settings(BaseSettings): model_config = SettingsConfigDict(env_prefix="DP_", env_file=".env", extra="ignore")`
- 函数 `def get_settings() -> Settings`
- `.env.example` 至少包含全部字段示例值
- 单测覆盖：从 env 加载、缺失必填字段抛 `pydantic.ValidationError`、lru_cache 行为

#### 验收标准
- [ ] `from data_platform.config import get_settings; get_settings()` 在测试环境可读取 `.env.example` 副本
- [ ] 缺失 `DP_PG_DSN` 时调用 `get_settings()` 抛出 `ValidationError`
- [ ] `pytest tests/test_config.py -q` 通过
- [ ] `Settings` 字段类型明确，无 `Any`
- [ ] 文档化路径默认值不指向系统目录

#### 验证命令
```bash
cd <workspace>/data-platform
cp .env.example .env.test
DP_PG_DSN="<postgres-dsn>" pytest tests/test_config.py -q
```

#### 依赖
依赖 #ISSUE-001（Python 包脚手架）

---

### ISSUE-003: PostgreSQL 连接与 SQL 迁移框架
**labels**: P0, milestone-0, infrastructure

#### 背景与目标
项目文档 §10.2 与 §15 指定 PostgreSQL 承载控制表、队列与 Iceberg PG-backed catalog。本 issue 建立基于 SQLAlchemy + 顺序 SQL migration 文件的迁移框架，所有后续表（cycle 控制表、队列表、catalog 表）共享同一 migration runner，保证 §11.1 中 "单 PG 事务冻结" 的依赖关系干净落地。

#### 所属模块
data_platform.ddl

#### 实现范围
- 新建 `src/data_platform/ddl/migrations/` 存放 `NNNN_<name>.sql` 文件
- 新建 `src/data_platform/ddl/runner.py`：实现 `MigrationRunner.apply_pending(dsn) -> list[str]`
- 在 PG 中自动创建元数据表 `dp_schema_migrations(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())`
- 提供 CLI 入口 `python -m data_platform.ddl.runner --upgrade`
- 第一份迁移 `0001_init.sql`：`CREATE SCHEMA IF NOT EXISTS data_platform;`
- 单测使用 `pytest-postgresql` 或 docker compose 启动的 PG 验证 idempotency

#### 不在本次范围
- 不创建业务表（cycle / queue 留给 ISSUE-028 等）
- 不实现 down migration（Lite 阶段不要求）
- 不引入 alembic（保持 Lite 简单）

#### 关键交付物
- `MigrationRunner` 类：方法 `apply_pending(dsn: str) -> list[str]` 返回新应用的 version 列表
- 文件命名规范：`NNNN_<snake_case>.sql`，4 位数字递增
- CLI：`python -m data_platform.ddl.runner --upgrade [--dry-run]`
- 错误处理：单个迁移失败时回滚事务并抛出 `MigrationError(version, sql, cause)`
- 测试：重复执行不重复应用、并发 lock 通过 `pg_advisory_lock(91234)`

#### 验收标准
- [ ] 在空 PG 上 `python -m data_platform.ddl.runner --upgrade` 创建 `dp_schema_migrations` 与 schema `data_platform`
- [ ] 第二次执行返回空列表且不报错
- [ ] 迁移 SQL 中 syntax error 时整体回滚，`dp_schema_migrations` 不留半提交记录
- [ ] 并发两个 runner 进程串行执行（advisory lock 验证）
- [ ] `pytest tests/ddl/` 全部通过

#### 验证命令
```bash
cd <workspace>/data-platform
docker run -d --rm --name dp-pg -e POSTGRES_PASSWORD=dp -p 5433:5432 postgres:16
sleep 3
DP_PG_DSN="<postgres-dsn>" python -m data_platform.ddl.runner --upgrade
DP_PG_DSN="<postgres-dsn>" python -m data_platform.ddl.runner --upgrade
psql "<postgres-dsn>" -c "select * from dp_schema_migrations;"
docker rm -f dp-pg
```

#### 依赖
依赖 #ISSUE-002（配置加载）

---

### ISSUE-004: PG-backed Iceberg SQL Catalog 初始化
**labels**: P0, milestone-0, infrastructure

#### 背景与目标
项目文档 §10.2 与 §15 明确 Lite 模式 Iceberg catalog 选型为 PG-backed SQL catalog，复用同一 PostgreSQL。本 issue 通过 PyIceberg 创建 catalog、声明 namespace（`canonical`、`formal`、`analytical`），为 ISSUE-005~ISSUE-013 的 Iceberg 写入与查询提供基底。注意 Raw Zone 不进入 catalog（§3 / §6.2 约束）。

#### 所属模块
data_platform.ddl + data_platform.serving.catalog

#### 实现范围
- 新建 `src/data_platform/serving/catalog.py`：函数 `load_catalog() -> SqlCatalog`，配置 uri、warehouse、jdbc 兼容
- 新建 `scripts/init_iceberg_catalog.py` CLI：调用 `catalog.create_namespace_if_not_exists("canonical")` 等
- 创建 namespace：`canonical`、`formal`、`analytical`（不创建 `raw`）
- 在 `tests/serving/test_catalog.py` 验证 namespace 创建幂等
- 写入 `docs/runbook/iceberg-catalog.md` 简短说明

#### 不在本次范围
- 不创建任何具体表（留给 ISSUE-006 / ISSUE-011）
- 不实现 catalog 升级或迁移
- 不接入 S3 / MinIO（Lite 用本地文件 warehouse）

#### 关键交付物
- 函数签名 `def load_catalog(name: str | None = None) -> SqlCatalog`
- 创建 namespace 的幂等函数 `def ensure_namespaces(catalog: SqlCatalog, names: Iterable[str]) -> None`
- CLI 退出码：成功 0、失败 1
- catalog SQL 表前缀使用 `iceberg_` 避免与业务表冲突
- 错误处理：catalog uri 不可达时抛 `CatalogConnectError(detail)`

#### 验收标准
- [ ] CLI 在空 PG + 空 warehouse 上运行成功，PG 中出现 `iceberg_*` 元数据表
- [ ] 重复运行 CLI 不报错且不重复创建 namespace
- [ ] `catalog.list_namespaces()` 返回 `[(canonical,), (formal,), (analytical,)]`
- [ ] 不存在名为 `raw` 的 namespace（边界守护）
- [ ] `pytest tests/serving/test_catalog.py` 通过

#### 验证命令
```bash
cd <workspace>/data-platform
mkdir -p <proof-workspace>/dp_warehouse
DP_ICEBERG_WAREHOUSE_PATH=<proof-workspace>/dp_warehouse \
DP_PG_DSN="<postgres-dsn>" \
  python scripts/init_iceberg_catalog.py
python -c "from data_platform.serving.catalog import load_catalog; print(load_catalog().list_namespaces())"
```

#### 依赖
依赖 #ISSUE-003（PG 迁移已就绪）

---

### ISSUE-005: Raw Zone 归档骨架与写入接口
**labels**: P0, milestone-0, infrastructure

#### 背景与目标
项目文档 §3、§6.2、§10.2 明确 Raw Zone 是 Parquet/JSON 文件归档，不是 Iceberg namespace。本 issue 实现 Raw Zone 的目录约定与最小写入接口，供 ISSUE-008 Tushare adapter 调用。Raw Zone 的稳定性是后续 dbt staging 可重跑的前提。

#### 所属模块
data_platform.raw

#### 实现范围
- 在 `src/data_platform/raw/writer.py` 实现 `RawWriter`
- 路径约定：`<raw_zone_path>/<source_id>/<dataset>/dt=<YYYYMMDD>/<run_id>.<ext>`
- 支持两种 payload：`pyarrow.Table` → parquet；`dict | list[dict]` → json (gzip)
- 提供 `RawArtifact` dataclass：`source_id`、`dataset`、`partition_date`、`run_id`、`path`、`row_count`、`written_at`
- 写入完成后落地一份 `_manifest.json` 描述本次 artifact
- 提供读取辅助 `RawReader.list_artifacts(source_id, dataset, partition_date)`

#### 不在本次范围
- 不进入 Iceberg（明确 BAN）
- 不做 schema 归一化（留给 dbt staging）
- 不实现压缩策略调优

#### 关键交付物
- `RawWriter.write_arrow(source_id: str, dataset: str, partition_date: date, run_id: str, table: pa.Table) -> RawArtifact`
- `RawWriter.write_json(source_id: str, dataset: str, partition_date: date, run_id: str, payload: list[dict]) -> RawArtifact`
- 文件命名 `run_id` 必须是 ULID 或 UUID4
- 文件写入采用 `<path>.tmp` → `os.replace` 原子重命名
- `RawReader.list_artifacts` 返回按 `written_at` 升序

#### 验收标准
- [ ] 写入 1 行 arrow table 后能被 `pyarrow.parquet.read_table` 读回且行数一致
- [ ] 写入 dict 列表后 `_manifest.json` 中 `row_count` 正确
- [ ] 同一 `(source, dataset, partition_date, run_id)` 重复写抛 `RawArtifactExists`
- [ ] 路径不进入 Iceberg warehouse 目录（防止边界混淆）
- [ ] `pytest tests/raw/` 通过

#### 验证命令
```bash
cd <workspace>/data-platform
DP_DATA_STORAGE_ROOT_PATH=<proof-workspace>/dp_data pytest tests/raw/ -q
ls <proof-workspace>/dp_data/raw
```

#### 依赖
依赖 #ISSUE-002（配置）

---

### ISSUE-006: Canonical/Formal/Analytical 表注册框架与 stock_basic canonical schema
**labels**: P0, milestone-0, infrastructure

#### 背景与目标
项目文档 §9.1 / §10 / §20.1 要求 `data-platform` 提供 Canonical / Formal / Analytical 表的存储位点。本 issue 建立 Iceberg 表注册的 Python 工厂，并落地首张 canonical 表 `canonical.stock_basic`（供 `entity-registry` 初始化使用，业务规则不在本项目）。

#### 所属模块
data_platform.ddl + data_platform.serving

#### 实现范围
- 新建 `src/data_platform/ddl/iceberg_tables.py`：`TableSpec` dataclass（namespace、name、schema、partition_spec、properties）
- 实现 `register_table(catalog, spec, replace=False)` 与 `ensure_tables(catalog, specs)`
- 定义 `canonical.stock_basic` schema：`ts_code: string` (PK 候选)、`symbol: string`、`name: string`、`area: string`、`industry: string`、`market: string`、`list_date: date`、`is_active: bool`、`source_run_id: string`、`canonical_loaded_at: timestamp`
- 同时声明 `canonical_entity` 与 `entity_alias` 表的存储位点（schema 字段最小化，仅留位点供 `entity-registry` 后续填充）
- 不在本 issue 创建 formal / analytical 具体表，只验证 namespace 工作

#### 不在本次范围
- 不写入数据（留给 ISSUE-011）
- 不定义 `canonical_entity_id` 生成规则（明确 BAN）
- 不实现 schema 演化迁移工具（留给 P1b）

#### 关键交付物
- `TableSpec(namespace: str, name: str, schema: pa.Schema, partition_by: list[str] | None, properties: dict[str, str] | None)`
- 函数 `ensure_tables(catalog: SqlCatalog, specs: Sequence[TableSpec]) -> list[Table]`
- 包级常量 `CANONICAL_STOCK_BASIC_SPEC`、`CANONICAL_ENTITY_SPEC`、`ENTITY_ALIAS_SPEC`
- `entity_alias` 字段位点至少包含：`alias: string`、`canonical_entity_id: string`、`source: string`、`created_at: timestamp`
- CLI `python -m data_platform.ddl.iceberg_tables --ensure`

#### 验收标准
- [ ] CLI 在 ISSUE-004 catalog 上创建 3 张表
- [ ] `catalog.load_table("canonical.stock_basic").schema()` 字段与定义一致
- [ ] 重复 ensure 不报错且不重复建表
- [ ] schema 中不含 `submitted_at` / `ingest_seq`（边界守护）
- [ ] `pytest tests/ddl/test_iceberg_tables.py` 通过

#### 验证命令
```bash
cd <workspace>/data-platform
python -m data_platform.ddl.iceberg_tables --ensure
python -c "from data_platform.serving.catalog import load_catalog; \
c=load_catalog(); print(c.load_table('canonical.stock_basic').schema())"
```

#### 依赖
依赖 #ISSUE-004（catalog 已就绪）

---

### ISSUE-007: DataSourceAdapter 协议定义与基础抽象
**labels**: P0, milestone-0, feature

#### 背景与目标
项目文档 §9.3、§14、§16.2 要求 `data-platform` 提供 `DataSourceAdapter` 协议实现。注意：协议本身定义在 `contracts` 模块（外部仓库），本项目实现 Python 抽象基类与运行期校验，并提供基础工具方法。先固化抽象层，避免后续 adapter 各自实现散乱。

#### 所属模块
data_platform.adapters.base

#### 实现范围
- 新建 `src/data_platform/adapters/base.py` 定义 `DataSourceAdapter` ABC
- 抽象方法：`source_id() -> str`、`get_assets() -> list[AssetSpec]`、`get_resources() -> dict[str, Any]`、`get_staging_dbt_models() -> list[str]`、`get_quota_config() -> QuotaConfig`、`fetch(asset_id, params) -> pa.Table | list[dict]`
- dataclass `QuotaConfig`：`requests_per_minute: int`、`daily_credit_quota: int | None`、`backoff_seconds: float = 1.0`
- 提供 `AdapterRegistry`：`register(adapter)`、`get(source_id) -> DataSourceAdapter`、`list_sources() -> list[str]`
- 提供 `BaseAdapter` 基类，封装 quota 限流 token-bucket 与 retry-on-429 通用逻辑
- 抛错类型：`AdapterQuotaExceeded`、`AdapterFetchError(source_id, asset_id, cause)`

#### 不在本次范围
- 不实现 Tushare 具体 adapter（留给 ISSUE-008）
- 不直接调用 LLM（明确 BAN）
- 不定义 Dagster asset（明确 BAN，asset spec 仅是数据结构）

#### 关键交付物
- `class DataSourceAdapter(ABC)` + `AssetSpec(name: str, dataset: str, partition: Literal["daily","static"], schema: pa.Schema)`
- `BaseAdapter` 内的 `_throttle()` 实现 token bucket，单测覆盖
- `AdapterRegistry` 是模块级单例 `_REGISTRY`，提供线程安全的 register（用 threading.Lock）
- 所有 fetch 错误必须包装为 `AdapterFetchError` 不裸抛 requests / 第三方异常
- 公共 hook：`on_fetch_complete(asset_id, row_count, duration_s)` 默认空实现，子类可覆盖

#### 验收标准
- [ ] `DataSourceAdapter` 任一方法未实现时实例化抛 `TypeError`
- [ ] `BaseAdapter._throttle()` 在 `requests_per_minute=60` 下连续 60 调用总耗时 ≥ 60s（允许 ±5%）
- [ ] `AdapterRegistry.register` 同一 source_id 重复注册抛 `AdapterAlreadyRegistered`
- [ ] `pytest tests/adapters/test_base.py` 通过且覆盖率 ≥80%
- [ ] mypy 严格模式无错误

#### 验证命令
```bash
cd <workspace>/data-platform
pytest tests/adapters/test_base.py -q --cov=data_platform.adapters.base --cov-report=term
mypy src/data_platform/adapters/base.py
```

#### 依赖
依赖 #ISSUE-001（包结构）

---

### ISSUE-008: Tushare adapter 最小实现（stock_basic 单 API）
**labels**: P0, milestone-0, feature

#### 背景与目标
项目文档 §4.1、§14、§21 阶段 0 的"1 个 API 样板"指定首个参考实现。本 issue 实现 Tushare adapter 的最小可运行版本，仅接入 `stock_basic` 一个 API，输出 Raw Zone artifact 供 dbt staging 消费。Tushare 选型由 §5.2 确认。

#### 所属模块
data_platform.adapters.tushare

#### 实现范围
- 新建 `src/data_platform/adapters/tushare/__init__.py`、`adapter.py`、`assets.py`
- 实现 `TushareAdapter(BaseAdapter)`：`source_id()="tushare"`
- `get_assets()` 仅返回一个 `AssetSpec(name="tushare_stock_basic", dataset="stock_basic", partition="static", schema=...)`
- `fetch("tushare_stock_basic", params)` 调用 tushare pro API（依赖 `tushare>=1.4`），返回 `pa.Table`
- 在 `data_platform.raw.writer` 协助下，提供顶层入口 `python -m data_platform.adapters.tushare.adapter --asset tushare_stock_basic --date 20260415`
- token 通过 `DP_TUSHARE_TOKEN` 环境变量读取，缺失时抛 `AdapterConfigError`

#### 不在本次范围
- 不实现其他 Tushare API（行情/财务/指数留给 P1b）
- 不写入 canonical / staging 表（留给 ISSUE-010 / ISSUE-011）
- 不实现 incremental backfill 策略

#### 关键交付物
- `TushareAdapter.fetch` 返回 schema 与 `AssetSpec.schema` 一致的 `pa.Table`
- CLI 入口写入 Raw Zone 后打印 `RawArtifact` 路径
- 单测使用 `responses` / `pytest-mock` 桩 tushare 客户端，无需真实 token
- quota 默认 `requests_per_minute=200`、`daily_credit_quota=None`
- 失败时 stderr 输出 JSON 结构 `{"error": "...", "asset": "..."}` 便于 orchestrator 抓取

#### 验收标准
- [ ] 单测中 mock tushare 返回 5000 行，CLI 写出 1 个 parquet artifact 且行数=5000
- [ ] 没有 `DP_TUSHARE_TOKEN` 时 CLI 退出码非零并输出明确错误
- [ ] `TushareAdapter` 通过 `AdapterRegistry.register` 后可被 `get("tushare")` 取出
- [ ] Raw Zone 路径符合 `tushare/stock_basic/dt=YYYYMMDD/<run_id>.parquet`
- [ ] `pytest tests/adapters/test_tushare.py` 通过

#### 验证命令
```bash
cd <workspace>/data-platform
pytest tests/adapters/test_tushare.py -q
# 真实拉取（需要 token，可选）
DP_TUSHARE_TOKEN="${DP_TUSHARE_TOKEN:?set DP_TUSHARE_TOKEN}" DP_DATA_STORAGE_ROOT_PATH=<proof-workspace>/dp_data \
  python -m data_platform.adapters.tushare.adapter --asset tushare_stock_basic --date 20260415
```

#### 依赖
依赖 #ISSUE-005（Raw Writer）, #ISSUE-007（adapter 抽象）

---

### ISSUE-009: dbt 项目骨架与 dbt-duckdb profile
**labels**: P0, milestone-0, infrastructure

#### 背景与目标
项目文档 §15 / §20.2 / §21 阶段 0 要求建立 dbt 骨架，使用 dbt-duckdb 直读 Iceberg。本 issue 在 `src/data_platform/dbt/` 下创建 dbt project 骨架与 profile，使后续 staging / intermediate / marts 模型有统一目录与执行入口。

#### 所属模块
data_platform.dbt（dbt project root）

#### 实现范围
- 在 `src/data_platform/dbt/` 下创建 `dbt_project.yml`、`profiles.yml.example`、`models/{staging,intermediate,marts}/`、`seeds/`、`macros/`
- `dbt_project.yml`：`name: data_platform`、`profile: data_platform`、`materialized` 默认按层（staging=view、intermediate=table、marts=table）
- `profiles.yml.example`：dbt-duckdb target，path 来自 `DP_DUCKDB_PATH`，配置 `extensions: [iceberg]` 与 `attach: [{ path: pg_dsn, type: postgres }]`
- 提供 `scripts/dbt.sh`：自动设置 `DBT_PROFILES_DIR` 指向 `src/data_platform/dbt/`
- 创建空的 `models/staging/_sources.yml` 占位
- 在 `tests/dbt/test_dbt_skeleton.py` 验证 `dbt parse` 成功

#### 不在本次范围
- 不创建任何具体 model（留给 ISSUE-010 等）
- 不开启 dbt 测试覆盖（留给 P1b）
- 不接入 elementary / dbt artifacts 平台

#### 关键交付物
- `dbt_project.yml` 含 `version: 2`、`require-dbt-version: ">=1.7"`
- profile 模板含 `extensions: ["iceberg", "httpfs"]`
- `scripts/dbt.sh` 转发参数：`./scripts/dbt.sh parse`、`./scripts/dbt.sh run`
- README 内说明如何生成本地 profile
- 单测调用 `dbt parse --project-dir src/data_platform/dbt` 退出码=0

#### 验收标准
- [ ] `dbt parse` 在干净环境运行成功
- [ ] `dbt list --resource-type model` 返回空（尚无 model）
- [ ] DuckDB 中可手动 `INSTALL iceberg; LOAD iceberg;` 成功
- [ ] `scripts/dbt.sh debug` 通过
- [ ] `pytest tests/dbt/` 通过

#### 验证命令
```bash
cd <workspace>/data-platform
cp src/data_platform/dbt/profiles.yml.example src/data_platform/dbt/profiles.yml
DBT_PROFILES_DIR=src/data_platform/dbt dbt parse --project-dir src/data_platform/dbt
DBT_PROFILES_DIR=src/data_platform/dbt dbt debug --project-dir src/data_platform/dbt
```

#### 依赖
依赖 #ISSUE-002（配置）, #ISSUE-004（catalog）

---

### ISSUE-010: stg_stock_basic dbt staging model
**labels**: P0, milestone-0, feature

#### 背景与目标
项目文档 §8.1 / §21 阶段 0 退出条件要求 1 个 staging model 跑通。本 issue 实现首个 staging model `stg_stock_basic`，从 Raw Zone 的 parquet 文件读取，做最小字段重命名/类型对齐后落到 DuckDB view，作为 canonical 表的输入源。

#### 所属模块
data_platform.dbt/models/staging

#### 实现范围
- 创建 `models/staging/_sources.yml`：source `raw.tushare_stock_basic`，loader 描述 Raw Zone 路径模式
- 创建 `models/staging/stg_stock_basic.sql`：`materialized='view'`，使用 DuckDB `read_parquet('<raw_zone>/tushare/stock_basic/**/*.parquet', hive_partitioning=1)`
- 字段转换：`ts_code` → trim、`list_date` → `strptime(..., '%Y%m%d')::date`、增加 `source_run_id`、`raw_loaded_at`
- 添加 dbt schema test：`unique`、`not_null` on `ts_code`
- 提供 `macros/dp_raw_path.sql` 宏，封装 raw zone 路径拼装

#### 不在本次范围
- 不写入 canonical 表（留给 ISSUE-011）
- 不实现 SCD（留给 P1b）
- 不建立其他 staging model

#### 关键交付物
- `models/staging/stg_stock_basic.sql` 单 model
- `_sources.yml` 内对 `tushare_stock_basic` 的描述
- `dp_raw_path('tushare','stock_basic')` 宏返回 glob 路径字符串
- schema test `dbt test --select stg_stock_basic` 通过
- 单测固定 fixture：`tests/dbt/fixtures/raw/tushare/stock_basic/dt=20260415/sample.parquet`

#### 验收标准
- [ ] `dbt run --select stg_stock_basic` 在 fixture 数据上成功
- [ ] `dbt test --select stg_stock_basic` 通过（unique + not_null）
- [ ] `duckdb $DP_DUCKDB_PATH "select count(*) from stg_stock_basic"` 返回 fixture 行数
- [ ] 字段类型：`list_date` 是 DATE，`ts_code` 是 VARCHAR
- [ ] 不直读 Iceberg canonical 表（边界守护）

#### 验证命令
```bash
cd <workspace>/data-platform
cp -r tests/dbt/fixtures/raw <proof-workspace>/dp_data/raw
DP_DATA_STORAGE_ROOT_PATH=<proof-workspace>/dp_data ./scripts/dbt.sh run --select stg_stock_basic
DP_DATA_STORAGE_ROOT_PATH=<proof-workspace>/dp_data ./scripts/dbt.sh test --select stg_stock_basic
duckdb $DP_DUCKDB_PATH "select count(*), min(list_date), max(list_date) from stg_stock_basic"
```

#### 依赖
依赖 #ISSUE-008（Tushare adapter 输出 Raw fixture）, #ISSUE-009（dbt 骨架）

---

### ISSUE-011: canonical.stock_basic 写入逻辑（Iceberg upsert）
**labels**: P0, milestone-0, feature

#### 背景与目标
项目文档 §8.1 与 §21 阶段 0 退出条件要求把 staging 数据落到 Canonical Iceberg 表，供下游 `entity-registry` / `main-core` 消费。本 issue 实现 `stg_stock_basic` → `canonical.stock_basic` 的 upsert 流程，使用 PyIceberg `overwrite` 或 `merge`，保证 Lite 模式可重跑。

#### 所属模块
data_platform.serving.canonical_writer

#### 实现范围
- 新建 `src/data_platform/serving/canonical_writer.py`：函数 `load_canonical_stock_basic(catalog, duckdb_path) -> WriteResult`
- 流程：读取 DuckDB `stg_stock_basic` → `pa.Table` → PyIceberg `Table.overwrite(table_arrow)`（Lite 简单策略：全量覆盖）
- 落库时补写 `canonical_loaded_at = now()`
- 提供 CLI `python -m data_platform.serving.canonical_writer --table stock_basic`
- `WriteResult(table: str, snapshot_id: int, row_count: int, duration_ms: int)`
- 单测使用临时 catalog + 内存 DuckDB 验证幂等

#### 不在本次范围
- 不写其他 canonical 表（留给 P1b）
- 不实现增量 merge（Lite 阶段允许全量）
- 不暴露 `submitted_at`/`ingest_seq`（明确 BAN，仅 Layer B 用）
- 不触发下游通知

#### 关键交付物
- 函数签名 `def load_canonical_stock_basic(catalog: SqlCatalog, duckdb_path: Path) -> WriteResult`
- CLI 退出码：成功 0、失败 1，stderr 输出 JSON
- 写入前校验目标表字段集与 `pa.Table` 字段集严格一致（多/少均 raise）
- 失败回滚：PyIceberg overwrite 失败时不留半快照
- 日志：`logger.info("canonical_write", extra={"table":..., "rows":..., "snapshot":...})`

#### 验收标准
- [ ] CLI 在 fixture 上跑通，`catalog.load_table('canonical.stock_basic').current_snapshot()` 非空
- [ ] 重跑 CLI 行数不变、产生新 snapshot（time travel 可见旧版本）
- [ ] DuckDB 通过 iceberg 扩展 `select count(*) from iceberg_scan('<warehouse>/canonical/stock_basic')` 返回正确行数
- [ ] payload 中无 `submitted_at` / `ingest_seq` 字段（边界守护）
- [ ] `pytest tests/serving/test_canonical_writer.py` 通过

#### 验证命令
```bash
cd <workspace>/data-platform
python -m data_platform.serving.canonical_writer --table stock_basic
duckdb -c "INSTALL iceberg; LOAD iceberg; \
  select count(*) from iceberg_scan('$DP_ICEBERG_WAREHOUSE_PATH/canonical/stock_basic');"
```

#### 依赖
依赖 #ISSUE-006（canonical 表已注册）, #ISSUE-010（staging model 可用）

---

### ISSUE-012: Canonical / DuckDB 基础读取接口
**labels**: P0, milestone-0, feature

#### 背景与目标
项目文档 §16.1 要求提供 `get_formal_*` 与 canonical 查询的 Python 接口。P1a 阶段先落 canonical 读取通道，formal serving 留待 P1c 与 manifest 联动。本 issue 提供下游模块（`entity-registry` 等）可调用的最小接口。

#### 所属模块
data_platform.serving.reader

#### 实现范围
- 新建 `src/data_platform/serving/reader.py`：函数 `read_canonical(table: str, columns: list[str] | None = None, filters: list[tuple] | None = None) -> pa.Table`
- 内部使用 DuckDB connection（带连接池单例），通过 iceberg 扩展直读 catalog
- 提供 `get_canonical_stock_basic(active_only: bool = True) -> pa.Table` 便捷函数
- 提供 `with_duckdb_connection()` 上下文管理器
- 错误处理：表不存在抛 `CanonicalTableNotFound(table)`

#### 不在本次范围
- 不实现 formal serving / manifest 读取（留给 P1c ISSUE-034）
- 不实现写入接口
- 不暴露 PyIceberg 对象给消费方（封装边界）

#### 关键交付物
- 函数签名 `def read_canonical(table: str, columns: list[str] | None = None, filters: list[tuple[str,str,Any]] | None = None) -> pa.Table`
- 单例 DuckDB 连接通过 `functools.lru_cache(maxsize=1)`
- `filters` 支持 `("col","=",val)`、`("col","in",[...])`，超出抛 `UnsupportedFilter`
- 单测使用 ISSUE-011 写入后的数据
- `get_canonical_stock_basic(active_only=True)` 默认 `is_active = TRUE`

#### 验收标准
- [ ] `read_canonical("stock_basic", columns=["ts_code","name"])` 返回正确字段
- [ ] `read_canonical("stock_basic", filters=[("market","=","主板")])` 行数与 DuckDB CLI 验证一致
- [ ] 读取不存在的表抛 `CanonicalTableNotFound`
- [ ] 单次读取 `< 2 秒`（§19.1 性能基线）
- [ ] `pytest tests/serving/test_reader.py` 通过

#### 验证命令
```bash
cd <workspace>/data-platform
python -c "from data_platform.serving.reader import get_canonical_stock_basic; \
print(get_canonical_stock_basic().num_rows)"
pytest tests/serving/test_reader.py -q
```

#### 依赖
依赖 #ISSUE-011（canonical 已有数据）

---

### ISSUE-013: Iceberg 写入链 spike 验证（schema 演化 / time travel / 并发 commit）
**labels**: P0, milestone-0, testing

#### 背景与目标
项目文档 §11.3 / §19.2 / §22 把 "Iceberg 写入链 spike" 列为 P1 全部 issue 的前置依赖，要求在阶段 0 内验证：1) add column 后旧 snapshot 仍可读；2) time travel 取历史 snapshot；3) 并发 overwrite 不破坏元数据。本 issue 把 spike 固化为可重复跑的测试集。

#### 所属模块
tests/spike/iceberg_write_chain

#### 实现范围
- 新建 `tests/spike/test_iceberg_write_chain.py`，包含三类测试：`test_add_column_backward_compat`、`test_time_travel_by_snapshot`、`test_concurrent_overwrite`
- `test_add_column_backward_compat`：建表写 v1 → `update_schema().add_column('extra', StringType())` → 写 v2 → 用 v1 snapshot_id 读取应得到旧字段集
- `test_time_travel_by_snapshot`：连续写 3 次，每次记录 snapshot_id，校验按 snapshot_id 读取版本数据匹配
- `test_concurrent_overwrite`：使用 `concurrent.futures` 启 2 个 worker overwrite 同一表，断言至少 1 次失败（PyIceberg 乐观锁）且元数据未损坏
- 输出结果到 `docs/spike/iceberg-write-chain.md`，记录耗时与结论
- 在 README 中加入运行命令

#### 不在本次范围
- 不替换为 PyIceberg 直写备选（属于风险应对，未触发不做）
- 不测试 S3/MinIO（Lite 文件系统即可）
- 不做大规模性能测试

#### 关键交付物
- 三个独立 pytest 用例，全部 marker `@pytest.mark.spike`
- 每个用例使用临时目录 + 临时 PG schema，跑完清理
- `docs/spike/iceberg-write-chain.md` 含：环境版本、用例耗时表、结论（pass/fail）、风险备注
- 当 spike 失败时退出码非零并保留产物供分析
- 可通过 `pytest -m spike` 单独运行

#### 验收标准
- [x] 三个用例全部通过
- [x] add column 后旧 snapshot 读取不报错且字段不含新列
- [x] time travel 按 snapshot_id 读取行数与写入时记录一致
- [x] 并发 overwrite 至少有 1 次抛 `CommitFailedException` 且最终表可读
- [x] `docs/spike/iceberg-write-chain.md` 已生成且含 "P1a Iceberg 写入链 spike 成功率: 100%"

#### 实现状态 / 验收状态（2026-05-04）
- **实现已落地**：`tests/spike/test_iceberg_write_chain.py` 包含 3 个用例 + `@pytest.mark.spike` marker（在 `pyproject.toml` 注册）；`docs/spike/iceberg-write-chain.md` 骨架文件也已存在。
- **验收已通过**：2026-05-04 post-merge run 使用 `DATABASE_URL=<redacted> DP_PG_DSN=<redacted> .venv/bin/pytest -m spike tests/spike/test_iceberg_write_chain.py -v`，结果为 3 passed, 0 failed, 0 skipped, 0 errors in 1.25s。
- **覆盖用例**：`test_add_column_backward_compat`、`test_time_travel_by_snapshot`、`test_concurrent_overwrite`。
- **运行说明**：使用 local `.env` PG DSN 的临时 schema 行为；因当前账号无 `CREATE DATABASE` 权限，没有创建新的 primary worktree artifact。

#### 验证命令
```bash
cd <workspace>/data-platform
DATABASE_URL=<redacted> DP_PG_DSN=<redacted> .venv/bin/pytest -m spike tests/spike/test_iceberg_write_chain.py -v
cat docs/spike/iceberg-write-chain.md
```

#### 依赖
依赖 #ISSUE-006（catalog + 表注册框架）

---

### ISSUE-014: 端到端最小闭环冒烟（Raw → staging → Canonical → DuckDB）
**labels**: P0, milestone-0, integration

#### 背景与目标
项目文档 §21 阶段 0 退出条件 "DuckDB 可查到 snapshot" 与 §23 验收第 2 条 "至少 1 个 API 样例完成 Raw → staging → Canonical → DuckDB 读取闭环"。本 issue 把前面 13 个 issue 串成一条可重复执行的 smoke pipeline，是 P1a 完成的最终判定。

#### 所属模块
scripts/smoke + tests/integration

#### 实现范围
- 新建 `scripts/smoke_p1a.sh`：依次执行 `migrate → init catalog → ensure tables → fetch tushare → dbt run → canonical write → reader query`
- 新建 `tests/integration/test_p1a_smoke.py`：使用 mock tushare + 临时 PG/warehouse/duckdb，跑完整链路并断言最终行数
- 提供 `make smoke-p1a` target（在 `Makefile` 中）
- 总耗时记录到 stdout（用于验证 `< 5 分钟` SLA）
- 失败时打印每一步的最后 50 行日志便于排查

#### 不在本次范围
- 不接入 CI（CI 配置留给后续 issue）
- 不接入 Layer B 队列（属于 P1c）
- 不执行真实 Tushare 调用（用 fixture）

#### 关键交付物
- `scripts/smoke_p1a.sh` 单一脚本，每步退出码检查
- `tests/integration/test_p1a_smoke.py` 单测覆盖完整链路
- `Makefile` 含 `smoke-p1a:` 目标
- 测试断言：`canonical.stock_basic` 行数 == fixture 行数
- 测试断言：DuckDB 查询返回正确字段集

#### 验收标准
- [x] `make smoke-p1a` 在干净环境一次成功
- [x] 总耗时 `< 5 分钟`（§19.1 性能基线）
- [ ] 重跑 smoke 行为幂等（重跑后最新 snapshot 行数仍正确；需要具备 `CREATE DATABASE` 权限的 pytest harness 或一次明确的 repeated-smoke operator run）
- [x] 测试日志显示 "P1a smoke OK" 字样
- [ ] `pytest tests/integration/test_p1a_smoke.py` 通过（fixture 仍要求 `CREATE DATABASE` 权限；2026-05-04 evidence 走 `make smoke-p1a`）

#### 实现状态 / 验收状态（2026-05-04）
- **实现已落地**：`scripts/smoke_p1a.sh` + `tests/integration/test_p1a_smoke.py` + `Makefile` 的 `smoke-p1a:` target 都已存在。
- **两条验证路径，环境变量要求不同**：
  - `make smoke-p1a` → `scripts/smoke_p1a.sh` → 要求 `DP_PG_DSN`；脚本第 26 行明确 "DATABASE_URL is not used by this destructive smoke path"。
  - `pytest tests/integration/test_p1a_smoke.py` → `postgres_dsn` fixture → 要求 `DATABASE_URL`（fixture 读 `os.environ.get("DATABASE_URL")`，line ~38）。
- **make 路径验收已通过**：2026-05-04 post-merge run 使用 `DP_ENV=test`、`DP_SMOKE_P1A_CONFIRM_DESTRUCTIVE=1`、`DP_PG_DSN=<postgres-dsn>`、`DP_ICEBERG_CATALOG_NAME=data_platform_p1a_smoke_20260504`、`DP_SMOKE_WORK_DIR=<proof-workspace>`，且 `DP_RAW_ZONE_PATH` / `DP_ICEBERG_WAREHOUSE_PATH` / `DP_DUCKDB_PATH` 均在该 workdir 下，然后执行 `make smoke-p1a`。
- **结果**：`P1a smoke OK duration_s=8 log_dir=<proof-workspace>/logs`；wrapper duration 9s。日志只保留在 `<proof-workspace>`，不提交入仓。
- **pytest 路径说明**：`pytest tests/integration/test_p1a_smoke.py -v` 仍要求具备 `CREATE DATABASE` 权限的 `DATABASE_URL`；2026-05-04 evidence 采用已经隔离好的 smoke database + destructive confirmation 的 `make smoke-p1a` 路径。

#### 验证命令
```bash
cd <workspace>/data-platform
# make 路径：shell 脚本读 DP_PG_DSN，DATABASE_URL 被脚本明确忽略
DP_ENV=test DP_SMOKE_P1A_CONFIRM_DESTRUCTIVE=1 DP_PG_DSN=<postgres-dsn> DP_ICEBERG_CATALOG_NAME=data_platform_p1a_smoke_20260504 DP_SMOKE_WORK_DIR=<proof-workspace> make smoke-p1a
# pytest 路径：fixture 读 DATABASE_URL
DATABASE_URL=<redacted> pytest tests/integration/test_p1a_smoke.py -v
```

#### 依赖
依赖 #ISSUE-003, #ISSUE-004, #ISSUE-005, #ISSUE-006, #ISSUE-008, #ISSUE-010, #ISSUE-011, #ISSUE-012

---

## 阶段 1：P1b 铺量 —— 完整结构化数据接入主线

**目标**：在 P1a 骨架上扩展到 ~40 API 接入与对应 staging/intermediate/marts 模型，结构化数据层每日自动更新可跑通。
**前置依赖**：阶段 0 全部完成

### ISSUE-015: Tushare 行情类 API adapter 扩展（daily/weekly/monthly bar）
**labels**: P1, milestone-1, feature
**摘要**: 在 ISSUE-008 基础上扩展 Tushare 行情类 API（daily、weekly、monthly），按交易日分区写入 Raw Zone。
**依赖**: #ISSUE-008（Tushare 基础 adapter）, #ISSUE-014（P1a smoke）

---

### ISSUE-016: Tushare 财务类 API adapter 扩展（income / balancesheet / cashflow / fina_indicator）
**labels**: P1, milestone-1, feature
**摘要**: 接入 Tushare 财务报表类 API，处理报告期分区与多版本（修正报表）问题。
**依赖**: #ISSUE-015（adapter 扩展模式确立）

---

### ISSUE-017: Tushare 指数与基础信息类 API adapter 扩展
**labels**: P1, milestone-1, feature
**摘要**: 接入指数行情、指数成分、行业分类等基础维表 API，作为 marts 维度表来源。
**依赖**: #ISSUE-015

---

### ISSUE-018: Tushare 公告与事件元数据 API adapter 扩展
**labels**: P1, milestone-1, feature
**摘要**: 接入公告元数据、停复牌、分红送股等事件类 API（不含原文，原文非本项目职责）。
**依赖**: #ISSUE-015

---

### ISSUE-019: Raw Zone 归档规范文档与目录健康检查脚本
**labels**: P1, milestone-1, infrastructure
**摘要**: 形成 Raw Zone 命名/分区/manifest 规范文档，并提供脚本扫描归档完整性。
**依赖**: #ISSUE-005

---

### ISSUE-020: dbt staging 层批量 model（约 40 个）
**labels**: P1, milestone-1, feature
**摘要**: 为 ISSUE-015~018 的全部 API 各自编写 staging model + schema test，覆盖类型对齐与基础唯一性。
**依赖**: #ISSUE-010, #ISSUE-016, #ISSUE-017, #ISSUE-018

---

### ISSUE-021: dbt intermediate 层关键 join 模型
**labels**: P1, milestone-1, feature
**摘要**: 实现常用 join 逻辑（行情 × 复权因子、财务 × 报告期对齐等）作为 intermediate 表。
**依赖**: #ISSUE-020

---

### ISSUE-022: dbt marts 层 canonical 维度与事实表
**labels**: P1, milestone-1, feature
**摘要**: 将 intermediate 落到 canonical Iceberg 维度表与事实表，供下游模块按表族读取。
**依赖**: #ISSUE-021, #ISSUE-011

---

### ISSUE-023: dbt 测试覆盖完善（schema + custom data tests）
**labels**: P1, milestone-1, testing
**摘要**: 为 staging/intermediate/marts 增补 unique/not_null/relationships 与自定义新鲜度测试，达成 100% 通过率。
**依赖**: #ISSUE-022

---

### ISSUE-024: asset / resource 工厂供 orchestrator 装配
**labels**: P1, milestone-1, integration
**摘要**: 提供 `data_platform.assets:build_assets()` 与 `build_resources()` 工厂，输出 Dagster 中性的 spec（不在本项目定义 job/schedule，属 BAN）。
**依赖**: #ISSUE-022

---

### ISSUE-025: Canonical 表 schema 演化与 backfill 流程
**labels**: P1, milestone-1, infrastructure
**摘要**: 形成 add column / type widening 的 SOP 与 backfill 脚本框架，复用 ISSUE-013 spike 经验。
**依赖**: #ISSUE-013, #ISSUE-022

---

### ISSUE-026: 每日自动更新冒烟（mock 调度器触发）
**labels**: P1, milestone-1, integration
**摘要**: 在不引入 Dagster 的前提下，提供 `scripts/daily_refresh.sh` 串联全部 adapter + dbt run + canonical write，并验证幂等。
**依赖**: #ISSUE-023, #ISSUE-024, #ISSUE-025

---

## 阶段 2：P1c Lite Layer B 摄取与 cycle 控制基础设施

**目标**：补完 PostgreSQL 候选队列、cycle 控制三表与 manifest 读取语义，使 `main-core` 与 `subsystem-sdk` 可独立演练 Lite 摄取与 formal 发布。
**前置依赖**：阶段 1 全部完成

### ISSUE-027: PostgreSQL 候选队列表与 ingest metadata 字段
**labels**: P1, milestone-2, infrastructure
**摘要**: 创建 `candidate_queue` 表，含 `id` BIGSERIAL、`payload_type` enum、`payload` JSONB、`submitted_at` timestamptz default now()、`ingest_seq` BIGSERIAL、`validation_status`、`rejection_reason`，并落迁移脚本。字段严格不进入 producer payload。
**依赖**: #ISSUE-003

---

### ISSUE-028: submit_candidate Python 接口与 payload 校验
**labels**: P1, milestone-2, feature
**摘要**: 实现 `data_platform.queue.submit_candidate(payload) -> QueueWriteResult`，含 contracts schema 校验、ingest metadata 服务端补写、错误分类。
**依赖**: #ISSUE-027

---

### ISSUE-029: 队列校验 worker（pending → accepted/rejected）
**labels**: P1, milestone-2, feature
**摘要**: 实现按 `validation_status='pending'` 拉取并执行 contracts 校验的同步函数，落地 rejection_reason，提供 `python -m data_platform.queue.worker --once`。
**依赖**: #ISSUE-028

---

### ISSUE-030: cycle_metadata 表与 cycle 创建接口
**labels**: P1, milestone-2, infrastructure
**摘要**: 落地 §9.3 字段集，提供 `create_cycle(cycle_date) -> CycleMetadata` 与状态机迁移辅助。
**依赖**: #ISSUE-027

---

### ISSUE-031: cycle_candidate_selection 表与 freeze_cycle_candidates 事务
**labels**: P1, milestone-2, feature
**摘要**: 在单个 PG 事务内读取 accepted 候选 → 写入 selection → 更新 cycle_metadata（cutoff_*、selection_frozen_at），保证 §11.1 算法语义。
**依赖**: #ISSUE-029, #ISSUE-030

---

### ISSUE-032: cycle_publish_manifest 表与 publish 写入接口
**labels**: P1, milestone-2, feature
**摘要**: 落地 §9.3 字段集，提供 `publish_manifest(cycle_id, formal_table_snapshots)` 接口；调用方为 `main-core`，本项目仅提供存储与写入入口。
**依赖**: #ISSUE-030

---

### ISSUE-033: Formal Serving 通过 manifest 读取（latest / by_id / by_snapshot）
**labels**: P1, milestone-2, feature
**摘要**: 实现 §16.1 三个 `get_formal_*` 接口，必须先查 `cycle_publish_manifest` 再用 PyIceberg snapshot_id time travel；禁止直读 formal head。
**依赖**: #ISSUE-032, #ISSUE-012

---

### ISSUE-034: 100 条候选冻结性能与一致性测试
**labels**: P1, milestone-2, testing
**摘要**: 写入 100 条候选后调用 freeze 接口，断言事务耗时 `< 3 秒`、selection 行数与 cutoff_ingest_seq 一致、并发写入不影响冻结快照。
**依赖**: #ISSUE-031

---

### ISSUE-035: manifest 一致性读取测试（add column / 半提交场景）
**labels**: P1, milestone-2, testing
**摘要**: 模拟 formal 表新增列与 publish 中断场景，验证 manifest 反查路径不会读到半提交版本，错误率为 0。
**依赖**: #ISSUE-033, #ISSUE-013

---

### ISSUE-036: P1c 端到端 cycle 演练 smoke
**labels**: P1, milestone-2, integration
**摘要**: 串联 submit → validate → freeze → publish_manifest → formal serving 完整路径，提供 `make smoke-p1c` 单命令验证；满足 §23 验收第 3、4 条。
**依赖**: #ISSUE-034, #ISSUE-035, #ISSUE-026

---
