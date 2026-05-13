# data-platform 项目进度跟踪

> 与 `docs/TASK_BREAKDOWN.md` 配套使用。基于 `data-platform.project-doc.md` v0.1.1 §21 实施路线图。
> 状态符号：`⬜ 未开始` / `🟡 进行中` / `✅ 已完成` / `🚧 阻塞`

## 阶段总览

| 阶段 | 标签 | 名称 | 文档退出条件 | Issue 数 | 状态 | 起止 |
|------|------|------|--------------|----------|------|------|
| 阶段 0 | milestone-0 | P1a 骨架 | DuckDB 可查到 snapshot；§23-2 闭环跑通 | 14 (#001-#014) | ✅ 已完成 | 2026-05-04 |
| 阶段 1 | milestone-1 | P1b 铺量 | 结构化数据层每日自动更新 | 12 (#015-#026) | ⬜ 未开始 | — |
| 阶段 2 | milestone-2 | P1c Lite Layer B + cycle 控制 | 候选冻结与 manifest 机制单独演练通过 | 10 (#027-#036) | ⬜ 未开始 | — |

**阶段依赖**：阶段 N+1 严格在阶段 N 全部完成后启动。

> **同步说明（2026-05-04 post-merge evidence update）**：
>
> **本轮同步区分两种状态**，避免用"实现已落地"代替"验收已通过"：
>
> - **实现已落地 + 已验收完成（✅）**：`ISSUE-001~012` —— 代码 / 配置 / 脚手架 / 单测均在仓内，且不依赖外部服务即可验收的交付项目均已核对通过。
> - **实现已落地 + post-merge real-PG evidence 已验收完成（✅）**：`ISSUE-013`（Iceberg spike）+ `ISSUE-014`（smoke-p1a 闭环）。2026-05-04 在 `main` merge commit `91038f69127677153f7bc4d1bab19859841915f8` 之后记录非跳过证据：
>   `DP_ENV=test DP_SMOKE_P1A_CONFIRM_DESTRUCTIVE=1 DP_PG_DSN=<redacted-dsn> DP_ICEBERG_CATALOG_NAME=data_platform_p1a_smoke_20260504 DP_SMOKE_WORK_DIR=<temporary-work-dir> make smoke-p1a`
>   返回 `P1a smoke OK duration_s=8 log_dir=<temporary-log-dir>`（wrapper 9s）；`DATABASE_URL=<redacted> DP_PG_DSN=<redacted> .venv/bin/pytest -m spike tests/spike/test_iceberg_write_chain.py -v` 返回 3 passed, 0 failed, 0 skipped, 0 errors in 1.25s。
>
> 因为 `ISSUE-013/014` 已有非跳过 real-PG evidence，**阶段 0 整体更新为 ✅ 已完成**。原始 smoke 日志仍位于 `<temporary-log-dir>`，不提交入仓。
>
> **Holdings P0 evidence sync（2026-05-06）**：
>
> - Live smoke 已完成 5 个 holdings 接口覆盖：
>   `top10_holders`、`top10_floatholders`、`fund_portfolio`、`hsgt_top10`、
>   `hsgt_hold_top10`。HSGT 使用历史可验证日期；evidence 只记录
>   `SET/redacted` 状态，不记录 token、具体 TS code 或 fund code。
> - Backfill orchestration 已合并：
>   `9629604dae9ed64dafd4d6c223e8b89941f6ad72`。默认 plan-only，要求
>   bounded inputs，live execution 必须显式 opt-in 并提供 Raw Zone / warehouse
>   paths；`hsgt_hold_top10` 在 2024-08-20 cutoff 后 skip/fail-closed。
> - Derivation marts 已合并：
>   `32289f14252d530fab6cc1aed46c2f0cd5b7c39e`。后续
>   `subsystem-holdings` 只能将 top-holder QoQ change、fund co-holding、
>   northbound z-score 作为 data-platform 只读输入，不直接调用 Tushare。
> - Curated evidence 见
>   `docs/evidence/holdings-backfill-derivation-evidence-20260506.md`；raw
>   logs/provider payloads/dbt build artifacts/runtime noise 不入仓。
>
> **Queue/freeze operational hardening sync**：
>
> - Holdings queue/freeze runbook hardening now treats idempotent Ex-3 submit,
>   safe public receipts, worker rejection metrics, and targeted freeze filters
>   as landed operational checks for bounded holdings rollout evidence.
> - This sync does **not** mark P1c broad/default rollout complete, does not
>   enable unfiltered production freezes, and does not introduce financial-doc
>   scope or contracts subtypes.
>
> 后续 `ISSUE-015+`（P1b / P1c）的真实进度不在本次 doc-sync 范围内，保留 `⬜ 未开始` 标记待各自 issue 走完正式流程后再更新。

---

## 阶段 0（milestone-0）：P1a 骨架

**目标**：1 个 API → Raw → staging → Canonical → DuckDB 最小闭环 + Iceberg 写入链 spike。

| ID | 标题 | 优先级 | 状态 | 依赖 |
|----|------|--------|------|------|
| ISSUE-001 | 项目脚手架与 Python 包结构初始化 | P0 | ✅ | — |
| ISSUE-002 | 配置加载与运行环境管理 | P0 | ✅ | #001 |
| ISSUE-003 | PostgreSQL 连接与 SQL 迁移框架 | P0 | ✅ | #002 |
| ISSUE-004 | PG-backed Iceberg SQL Catalog 初始化 | P0 | ✅ | #003 |
| ISSUE-005 | Raw Zone 归档骨架与写入接口 | P0 | ✅ | #002 |
| ISSUE-006 | Canonical/Formal/Analytical 表注册框架 + stock_basic schema | P0 | ✅ | #004 |
| ISSUE-007 | DataSourceAdapter 协议与基础抽象 | P0 | ✅ | #001 |
| ISSUE-008 | Tushare adapter 最小实现（stock_basic） | P0 | ✅ | #005, #007 |
| ISSUE-009 | dbt 项目骨架与 dbt-duckdb profile | P0 | ✅ | #002, #004 |
| ISSUE-010 | stg_stock_basic dbt staging model | P0 | ✅ | #008, #009 |
| ISSUE-011 | canonical.stock_basic 写入逻辑 | P0 | ✅ | #006, #010 |
| ISSUE-012 | Canonical / DuckDB 基础读取接口 | P0 | ✅ | #011 |
| ISSUE-013 | Iceberg 写入链 spike 验证 | P0 | ✅ | #006 |
| ISSUE-014 | 端到端最小闭环冒烟 smoke-p1a | P0 | ✅ | #003, #004, #005, #006, #008, #010, #011, #012 |

**完成判定（§23 验收 1+2）**：
- [x] Raw / Canonical / Formal / Analytical 边界与落地方式明确并可运行
- [x] 至少 1 个 API 样例完成 Raw → staging → Canonical → DuckDB 读取闭环（2026-05-04 `make smoke-p1a` 非跳过 real-PG run 返回 `P1a smoke OK duration_s=8 log_dir=<temporary-log-dir>`，wrapper 9s）
- [x] `make smoke-p1a` 一次成功且 `< 5 分钟`（同上；运行命令使用 `DP_PG_DSN=<redacted-dsn>`，raw/warehouse/DuckDB 均位于 `<temporary-work-dir>` 下）
- [x] Iceberg 写入链 spike 三类用例全部通过（2026-05-04 `DATABASE_URL=<redacted> DP_PG_DSN=<redacted> .venv/bin/pytest -m spike tests/spike/test_iceberg_write_chain.py -v` 返回 3 passed, 0 failed, 0 skipped, 0 errors in 1.25s）

**关键交付物实际落点（2026-04-24 sync 时核验存在）**：

- ISSUE-001：`src/data_platform/` 包结构 + `pyproject.toml` + `scripts/bootstrap_dev.sh`
- ISSUE-002：`src/data_platform/config/settings.py`（pydantic-settings）
- ISSUE-003：`src/data_platform/ddl/runner.py` + `src/data_platform/ddl/migrations/`
- ISSUE-004：`src/data_platform/serving/catalog.py` + `scripts/init_iceberg_catalog.py`
- ISSUE-005：`src/data_platform/raw/writer.py`（`RawWriter` / `RawArtifact`）
- ISSUE-006：`src/data_platform/ddl/iceberg_tables.py`（`TUSHARE_STOCK_BASIC_SCHEMA` 等）
- ISSUE-007：`src/data_platform/adapters/base.py`（`DataSourceAdapter` ABC + `AdapterRegistry`）
- ISSUE-008：`src/data_platform/adapters/tushare/adapter.py`（`TushareAdapter`）+ `assets.py`
- ISSUE-009：`src/data_platform/dbt/dbt_project.yml` + `profiles.yml.example` + `macros/`
- ISSUE-010：`src/data_platform/dbt/models/staging/stg_stock_basic.sql` + `_sources.yml` + `_schema.yml`
- ISSUE-011：`src/data_platform/serving/canonical_writer.py`
- ISSUE-012：`src/data_platform/serving/reader.py`（`get_canonical_stock_basic` 等）
- ISSUE-013：`tests/spike/test_iceberg_write_chain.py` + `@pytest.mark.spike` marker（`pyproject.toml`）+ `docs/spike/iceberg-write-chain.md`（**2026-05-04 post-merge run：3 passed, 0 failed, 0 skipped, 0 errors in 1.25s**）
- ISSUE-014：`scripts/smoke_p1a.sh` + `tests/integration/test_p1a_smoke.py` + `Makefile` 中 `smoke-p1a:` target（**2026-05-04 post-merge `make smoke-p1a`：`P1a smoke OK duration_s=8 log_dir=<temporary-log-dir>`，wrapper 9s**）

---

## 阶段 1（milestone-1）：P1b 铺量

**目标**：扩展到 ~40 API 的完整结构化数据接入主线，结构化数据层每日自动更新。

| ID | 标题 | 优先级 | 状态 | 依赖 |
|----|------|--------|------|------|
| ISSUE-015 | Tushare 行情类 API adapter 扩展 | P1 | ⬜ | #008, #014 |
| ISSUE-016 | Tushare 财务类 API adapter 扩展 | P1 | ⬜ | #015 |
| ISSUE-017 | Tushare 指数与基础信息类 API adapter 扩展 | P1 | ⬜ | #015 |
| ISSUE-018 | Tushare 公告与事件元数据 API adapter 扩展 | P1 | ⬜ | #015 |
| ISSUE-019 | Raw Zone 归档规范文档与健康检查脚本 | P1 | ⬜ | #005 |
| ISSUE-020 | dbt staging 层批量 model（约 40 个） | P1 | ⬜ | #010, #016, #017, #018 |
| ISSUE-021 | dbt intermediate 层关键 join 模型 | P1 | ⬜ | #020 |
| ISSUE-022 | dbt marts 层 canonical 维度与事实表 | P1 | ⬜ | #021, #011 |
| ISSUE-023 | dbt 测试覆盖完善 | P1 | ⬜ | #022 |
| ISSUE-024 | asset / resource 工厂供 orchestrator 装配 | P1 | ⬜ | #022 |
| ISSUE-025 | Canonical 表 schema 演化与 backfill 流程 | P1 | ⬜ | #013, #022 |
| ISSUE-026 | 每日自动更新冒烟 daily_refresh.sh | P1 | ⬜ | #023, #024, #025 |

**完成判定**：
- [ ] 结构化数据层每日自动更新可跑通（mock 调度即可）
- [ ] dbt 基础测试通过率 100%
- [ ] `data-platform` 不出现任何 Dagster job/schedule/sensor 定义（边界守护）

---

## 阶段 2（milestone-2）：P1c Lite Layer B + cycle 控制

**目标**：候选队列、cycle 控制三表与 manifest 读取语义全部可用。

| ID | 标题 | 优先级 | 状态 | 依赖 |
|----|------|--------|------|------|
| ISSUE-027 | PostgreSQL 候选队列表与 ingest metadata 字段 | P1 | ⬜ | #003 |
| ISSUE-028 | submit_candidate Python 接口与 payload 校验 | P1 | ⬜ | #027 |
| ISSUE-029 | 队列校验 worker（pending → accepted/rejected） | P1 | ⬜ | #028 |
| ISSUE-030 | cycle_metadata 表与 cycle 创建接口 | P1 | ⬜ | #027 |
| ISSUE-031 | cycle_candidate_selection 表与 freeze_cycle_candidates 事务 | P1 | ⬜ | #029, #030 |
| ISSUE-032 | cycle_publish_manifest 表与 publish 写入接口 | P1 | ⬜ | #030 |
| ISSUE-033 | Formal Serving 通过 manifest 读取 | P1 | ⬜ | #032, #012 |
| ISSUE-034 | 100 条候选冻结性能与一致性测试 | P1 | ⬜ | #031 |
| ISSUE-035 | manifest 一致性读取测试 | P1 | ⬜ | #033, #013 |
| ISSUE-036 | P1c 端到端 cycle 演练 smoke-p1c | P1 | ⬜ | #034, #035, #026 |

**完成判定（§23 验收 3+4）**：
- [ ] Lite 队列、`cycle_candidate_selection`、`cycle_metadata`、`cycle_publish_manifest` 全部可用
- [ ] `main-core`、`entity-registry`、`orchestrator` 能直接消费本项目接口
- [ ] 100 条候选冻结事务耗时 `< 3 秒`
- [ ] manifest 一致性读取错误率 0
- [ ] 摄取元数据 `submitted_at`/`ingest_seq` 仅出现在 Layer B 落库逻辑，不进入 producer payload

---

## Blocker 升级条件（任一触发立即停下）

参见 `CLAUDE.md` / 项目文档 §25.3：

- Raw / Canonical / Formal / Analytical 任一层边界被改写
- `submitted_at` / `ingest_seq` 重新进入 producer payload
- `cycle_publish_manifest` 语义不清或出现绕开 manifest 直读 formal head 的设计
- 需要新增文档未冻结的长期基础服务 / daemon

## 关键性能与质量指标（§19）

| 指标 | 目标 | 验证 issue |
|------|------|-----------|
| 1 API 最小闭环跑通时间 | < 5 分钟 | ISSUE-014 |
| Formal Serving 单次读取延迟 | < 2 秒 | ISSUE-033 |
| 100 条候选冻结事务耗时 | < 3 秒 | ISSUE-034 |
| Iceberg 写入链 spike 成功率 | 100% | ISSUE-013 |
| dbt 基础测试通过率 | 100% | ISSUE-023 |
| manifest 一致性读取错误率 | 0 | ISSUE-035 |
| 摄取元数据与 producer payload 混淆率 | 0 | ISSUE-028 / 全程审查 |
