# 项目进度追踪 — audit-eval

> 最后更新：2026-05-11
> 总体阶段：核心库能力已落地；生产编排和 downstream 接入仍待 orchestrator 串联

## 里程碑总览

| 里程碑 | 名称 | Issue 数 | 预估工期 | 当前状态 | 前置依赖 |
|--------|------|----------|----------|----------|----------|
| milestone-0 | 项目骨架与 Replay 格式 Spike | 2 | 2-3 天 | 已实现 | 无 |
| milestone-1 | P2c 在线审计闭环（audit_record / replay_record） | 3 | 3-5 天 | 已实现库能力 | milestone-0 |
| milestone-2 | P2c 基础 retrospective（T+1） | 2 | 3-5 天 | 已实现库能力 | milestone-1 |
| milestone-3 | P5 多时域评估与 drift | 2 | 4-6 天 | 已实现基础库能力，生产告警编排待接入 | milestone-2 |
| milestone-4 | P10 回测能力 | 2 | 4-7 天 | 已实现基础库能力，研究/生产回测链路待接入 | milestone-3 |

## 当前已落地能力

- 包边界和公开入口已存在：`audit_eval.audit`、`audit_eval.retro`、
  `audit_eval.drift`、`audit_eval.backtest`、`audit_eval.public` 和
  `audit_eval_fixtures` 都有可导入实现与测试覆盖。
- Replay Spike 和正式 replay 语义已落地：sample cycle 能基于持久化历史、
  manifest refs 和 `read_history` 模式重建 replay view，不重调当前模型。
- Audit/replay durable storage 已落地：包含写入入口、DuckDB/Lite 适配层、
  replay repository 和 manifest-bound 查询路径。
- Retrospective 基础能力已落地：包含 `RetrospectiveEvaluation` 相关 schema、
  T+1 计算、summary、cumulative alert、multi-horizon/backfill 辅助，以及
  retrospective hook。
- Shared fixtures 已落地：包含 minimal cycle、event cases、historical replay
  pack，供 downstream 回归测试复用。
- Drift/backtest 基础能力已落地：包含 drift report schema/rules/runner/storage、
  PIT checker、BacktestResult schema、Alphalens adapter 边界、runner 和
  backtest result persistence。

## Issue 明细

### milestone-0 — 项目骨架与 Replay 格式 Spike

| ID | 标题 | 优先级 | 状态 | 依赖 |
|----|------|--------|------|------|
| ISSUE-001 | 项目骨架与内部包边界初始化 | P0 | 已实现 | 无 |
| ISSUE-002 | Replay 格式与 manifest 对账 Spike | P0 | 已实现 | #ISSUE-001 |

**当前结果**：给定 sample cycle，可不调用模型完成 manifest-bound replay 重建。

### milestone-1 — P2c 在线审计闭环

| ID | 标题 | 优先级 | 状态 | 依赖 |
|----|------|--------|------|------|
| ISSUE-003 | AuditRecord / ReplayRecord 正式 schema 与 AuditWriteBundle 契约 | P0 | 已实现 | #ISSUE-002 |
| ISSUE-004 | persist_audit_records / persist_replay_records 持久化实现 | P0 | 已实现 | #ISSUE-003 |
| ISSUE-005 | replay_cycle_object 查询接口与 ReplayView 重建 | P0 | 已实现 | #ISSUE-004 |

**当前结果**：库内已具备 audit/replay record 写入、durable/Lite storage、
manifest-bound replay 查询和 replay view 重建能力。生产日频写入由
orchestrator 后续接入，不在本模块内完成。

### milestone-2 — P2c 基础 retrospective

| ID | 标题 | 优先级 | 状态 | 依赖 |
|----|------|--------|------|------|
| ISSUE-006 | RetrospectiveEvaluation schema 与 T+1 compute_retrospective | P0 | 已实现 | #ISSUE-005 |
| ISSUE-007 | Retrospective summary 与累积告警 | P1 | 已实现 | #ISSUE-006 |

**当前结果**：库内已具备 T+1 计算、summary、alert、storage 边界和
retrospective hook。T+5/T+20 等多 horizon 能力已进入后续基础库实现，
但生产回填调度仍归 orchestrator 接入。

### milestone-3 — P5 多时域评估与 drift

| ID | 标题 | 优先级 | 状态 | 依赖 |
|----|------|--------|------|------|
| ISSUE-008 | T+5 / T+20 回填与多 horizon 支持 | P1 | 已实现基础库能力 | #ISSUE-007 |
| ISSUE-009 | Evidently drift_report 与第三层结构性告警 | P1 | 已实现基础库能力 | #ISSUE-008 |

**剩余缺口**：

- 生产 Dagster/AssetCheck 编排尚未把 drift report 作为日常 analytical 资产发布。
- 真实 reference/target 窗口的数据平台读取和报告落盘策略仍需 production profile
  接入验证。
- Drift 告警只输出第三层结构性告警；不得写 `feature_weight_multiplier`
  或任何在线控制字段。

### milestone-4 — P10 回测能力

| ID | 标题 | 优先级 | 状态 | 依赖 |
|----|------|--------|------|------|
| ISSUE-010 | Point-in-time 检查器与 BacktestResult schema | P2 | 已实现基础库能力 | #ISSUE-009 |
| ISSUE-011 | Alphalens 回测集成与 backtest_result 写入 | P2 | 已实现基础库能力 | #ISSUE-010 |

**剩余缺口**：

- 生产/研究回测任务配置、历史特征读取和结果发布还没有形成完整日频闭环。
- Backtest 结果必须继续以 PIT 检查作为硬前置；检查失败不得发布正式
  `backtest_result`。
- 具体 downstream 消费、module pin 和 orchestrator DAG 接入由 orchestrator
  后续处理，不在 `audit-eval` 内完成。

## 生产集成待办

- orchestrator 负责把 audit/replay 写入、retrospective 回填、drift report、
  backtest job 和 AssetCheck 串成 production profile。
- downstream 模块接入 `audit_eval_fixtures` 或 pin `audit-eval` 版本时，由
  orchestrator/assembly 的后续 PR 处理；本仓库只维护可复用库能力和测试资产。
- 真正的生产健康检查需要覆盖 PostgreSQL/Iceberg、Dagster run history、
  data-platform manifest gateway 和 analytical report 写入位置；当前 public
  health/smoke 仍是轻量导入与契约 smoke。

## 关键守门指标（§19.2）

| 指标 | 目标值 |
|------|--------|
| formal LLM 调用 replay 字段缺失率 | 0 |
| replay 错读非 manifest 版本发生率 | 0 |
| retrospective 多时域回填完成率 | 100% |
| drift 告警误写在线控制字段次数 | 0 |
| backtest PIT 检查通过前发布次数 | 0 |

## 边界红线（CLAUDE.md 同步）

- 任何 issue 不得写 `feature_weight_multiplier`。
- replay 唯一合法模式为 `read_history`，不得重调模型。
- 所有 replay / retrospective 必须先经过 `cycle_publish_manifest`。
- backtest 必须通过 PIT 检查才能入库。
- P10 之前不引入 NautilusTrader 或第二套研究平台。
