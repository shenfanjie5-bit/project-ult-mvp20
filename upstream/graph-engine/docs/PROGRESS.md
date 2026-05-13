# graph-engine 项目进度总览

> **最后更新**: 2026-05-08
> **项目文档**: [graph-engine.project-doc.md](./graph-engine.project-doc.md)
> **任务拆解**: [TASK_BREAKDOWN.md](./TASK_BREAKDOWN.md)

## 当前状态

graph-engine 已进入 holdings extension 阶段。核心 P3a/P3b 能力不再处于
原始任务拆解中的“未开始”状态：promotion、status guard、cold reload、
event/reflexive propagation、readonly query/simulation、snapshot generation
和 #56 holdings enum/planner/query/channel 基础已经落地。

本轮 #55 范围已被收窄并 supersede 旧 issue 文本：

- 已实现 `CO_HOLDING` co-holding crowding algorithm。
- 已实现 `NORTHBOUND_HOLD` northbound anomaly algorithm。
- 第一版只提供显式入口：`run_co_holding_crowding`、
  `run_northbound_anomaly`、`run_holdings_algorithms`。
- 未接入默认 `run_full_propagation`，避免与 generic event/reflexive
  propagation 双计数。
- 未实现担保链、关联交易、financial-doc、contracts subtype、
  `MAJOR_CUSTOMER`、`MAJOR_SUPPLIER`、`TOP_SHAREHOLDER` 或
  `PLEDGE_STATUS`。
- 未声明 live Neo4j production rollout；算法仅读取 ready live graph，
  不写 Neo4j。
- bounded gated canary / live production evidence 已达到 PASS，但该
  PASS 只覆盖 holdings-scoped `CO_HOLDING` / `NORTHBOUND_HOLD` proof /
  canary 路径，不表示默认传播已启用，也不表示 broad production
  rollout 已完成。
- production hardening prerequisites / guards 已落地：显式环境确认、
  safe namespace / artifact root、非默认 disposable Neo4j database label、
  client database match、ready status guard、relationship allowlist、
  evidence manifest 与 sanitized proof output。
- propagation canary runbook hardening baseline 已补在
  [PROPAGATION_CANARY_RUNBOOK.md](./PROPAGATION_CANARY_RUNBOOK.md)：锁定
  disposable DB/default DB guard、Layer A -> sync verification、rollback /
  read-only algorithm diagnostics 与 evidence hygiene。
- 下一步是按 hardened runbook 做 post-canary operationalization；之后才
  评估 controlled opt-in default-propagation canary，不提前声明 default /
  full propagation enabled。

## 里程碑进度

| 阶段 | 目标 | 当前状态 |
|------|------|----------|
| Phase 0 | 图谱性能与模型 Spike | 基础设施与模型已落地；性能预算仍需单独实测更新 |
| Phase 1 | P3a 图谱主干 | CandidateGraphDelta promotion + Layer A before live sync 已落地 |
| Phase 2 | P3a 运维闭环 | Neo4j graph status、consistency guard、Cold Reload 已落地 |
| Phase 3 | P3b 传播 | fundamental / event / reflexive 已落地；#55 holdings-only 显式算法已落地 |
| Phase 4 | P3b 只读服务 | subgraph/path query 与 readonly local simulation 已落地 |

## Holdings Issue 状态

| Issue | 当前状态 | 说明 |
|------|----------|------|
| #56 | 已完成 | `CO_HOLDING` / `NORTHBOUND_HOLD` enum、planner、query、channel 基础能力 |
| #55 | holdings-only 已完成/closed | 已完成 co-holding crowding 与 northbound anomaly 显式算法；bounded gated canary/live evidence PASS；broad/default propagation、financial-doc 与 contracts subtype 均不在本 scope |

## 下一步

1. 按 [PROPAGATION_CANARY_RUNBOOK.md](./PROPAGATION_CANARY_RUNBOOK.md)
   做 post-canary operationalization。
2. 在 runbook 与操作 guard 继续经实跑验证后，再评估 controlled opt-in
   default-propagation canary。
3. 在单独证据完成前，不声明 default/full propagation enabled、broad
   production rollout complete、M4.7 / financial-doc complete 或 contracts
   subtype 支持。

## 验证命令

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/unit/test_propagation_holdings.py tests/unit/test_propagation_merge.py \
  tests/unit/test_snapshots.py tests/unit/test_propagation_channels.py \
  tests/unit/test_schema.py tests/boundary/test_red_lines.py

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/unit/test_rollout.py tests/unit/test_rollout_runbook.py \
  tests/unit/test_holdings_live_graph_proof.py
```

## 保留边界

- 不改 `contracts`，不新增 holdings-specific subtype。
- 不新增 relationship enum。
- 不 import `data_platform`、`subsystem_*`、`main_core`、`assembly` 或
  `orchestrator`。
- 不直接写 Neo4j live graph。
- 不恢复旧 #55 的 financial-doc、担保链或关联交易 scope。
