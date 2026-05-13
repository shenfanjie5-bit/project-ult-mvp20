# main-core 项目进度总览

> 任务源：`docs/TASK_BREAKDOWN.md`
> 项目文档：`docs/main-core.project-doc.md` (v0.1.2)
> 更新日期：2026-04-17

## 里程碑总览

| Milestone | 名称 | 对应项目文档 | 状态 | Issues | 说明 |
|-----------|------|------------|------|--------|------|
| milestone-0 | 包骨架与 formal 对象基线 | §25.2 第 1 步 | not-started | ISSUE-001, ISSUE-002, ISSUE-003 | 骨架 + 9 个 Pydantic schema + 3 个 protocol |
| milestone-1 | P2a 纯数据骨架 (L1-L3) | §21 阶段 0 / §25.2 第 2 步 | blocked | ISSUE-004, ISSUE-005 | L1-L3 主干 + multiplier 在线写入 |
| milestone-2 | P2b L4-L7 正式判断链 | §21 阶段 1 / §25.2 第 3 步 | blocked | ISSUE-006, ISSUE-007, ISSUE-008, ISSUE-009 | 默认 `single_prompt_v1` |
| milestone-3 | P2c 发布与审计对接 | §21 阶段 2 / §25.2 第 4 步 | blocked | ISSUE-010, ISSUE-011 | publish bundle + manifest + dashboard/report |
| milestone-4 | P3-P5 图谱与子系统接入 | §21 阶段 3 | blocked | ISSUE-012, ISSUE-013 | graph snapshot + Layer B 候选信号 |
| milestone-5 | P8 MultiAgent 选项 | §21 阶段 4 / §16.3 | blocked | ISSUE-014 | A/B 评估后方可切换 |

## Issue 状态明细

| Issue | 标题 | Milestone | Priority | 状态 | 依赖 |
|-------|------|-----------|----------|------|------|
| ISSUE-001 | 搭建 main-core 单项目强 package 骨架与边界静态检查 | milestone-0 | P0 | todo | 无 |
| ISSUE-002 | 定义六类 formal object 与运行时 bundle 的 Pydantic schema | milestone-0 | P0 | todo | #ISSUE-001 |
| ISSUE-003 | 定义 AnalyzerInterface / WorldStatePolicy / RecommendationConstraintProvider 三类协议接口 | milestone-0 | P0 | todo | #ISSUE-001, #ISSUE-002 |
| ISSUE-004 | 实现 l1_l2_basis 基础数据读取层 | milestone-1 | P0 | blocked | #ISSUE-001, #ISSUE-002, #ISSUE-003 |
| ISSUE-005 | 实现 l3_features 特征/信号主干与 feature_weight_multiplier 在线写入 | milestone-1 | P0 | blocked | #ISSUE-004 |
| ISSUE-006 | 实现 l4_world_state 混合驱动共享状态 | milestone-2 | P0 | blocked | #ISSUE-005 |
| ISSUE-007 | 实现 l5_universe 正式池选择与冻结 | milestone-2 | P0 | blocked | #ISSUE-006 |
| ISSUE-008 | 实现 l6_alpha SinglePromptAnalyzer 与 inconclusive 降级 | milestone-2 | P0 | blocked | #ISSUE-007 |
| ISSUE-009 | 实现 l7_recommendation 正式建议、override 与 constraint gate | milestone-2 | P0 | blocked | #ISSUE-008 |
| ISSUE-010 | 实现 l8_publish 发布装配与 manifest 发起 | milestone-3 | P0 | blocked | #ISSUE-009 |
| ISSUE-011 | 实现 dashboard_snapshot 与 formal report 的正式业务内容 | milestone-3 | P1 | blocked | #ISSUE-010 |
| ISSUE-012 | 接入 graph_snapshot 与 graph_impact_snapshot 只读消费 | milestone-4 | P1 | blocked | #ISSUE-011 |
| ISSUE-013 | 接入 Layer B 候选信号到 l3_features | milestone-4 | P1 | blocked | #ISSUE-012 |
| ISSUE-014 | 实现 MultiAgentAnalyzer 与 A/B 评估脚本 | milestone-5 | P2 | blocked | #ISSUE-013 |

## §23 验收对照

| 验收条目 | 覆盖 Issue |
|----------|-----------|
| 纯市场数据最小 L1-L8 闭环跑通 | ISSUE-001 → ISSUE-010 |
| 六类主业务 formal object 定义与生成路径 | ISSUE-002（定义）, ISSUE-006/007/008/009/011（生成） |
| `feature_weight_multiplier` 在 `l3_features` 生效 | ISSUE-005 |
| Phase 3 发布走 manifest 且禁止用上一轮顶替 | ISSUE-008（inconclusive）, ISSUE-010（manifest） |
| OWN/BAN 边界与主项目一致 | ISSUE-001（边界 lint）全程约束 |

## 下一步

1. 启动 **ISSUE-001**（无前置依赖，可立即开工）。
2. ISSUE-001 合入后可并行启动 ISSUE-002；ISSUE-003 需等 ISSUE-002 合入。
3. milestone-0 全部合入后解锁 milestone-1，且由 Codex 在 milestone-1 启动前自动把 ISSUE-004/005 的骨架 body 细化为完整 8 段。
