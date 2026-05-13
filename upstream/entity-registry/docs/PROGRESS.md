# entity-registry 项目进度总览

> 最后更新：2026-05-07

## 里程碑概览

| 阶段 | 里程碑 | Issues | 状态 | 退出条件 |
|------|--------|--------|------|----------|
| 阶段 0 | P1 最小实体锚点 | ISSUE-001, ISSUE-002 | ✅ 已实现 | 全部 A 股上市公司有正式 canonical_entity_id |
| 阶段 1 | P1-P2 确定性解析 | ISSUE-003, ISSUE-004 | ✅ 已实现 | 主系统和图谱能稳定读取 ENT_* 锚点 |
| 阶段 2 | P4 模糊解析与 LLM 辅助 | ISSUE-005, ISSUE-006 | 🟨 已实现基础链路，待生产化 | 复杂新闻/公告 mention 能进入完整解析链 |
| 阶段 3 | P4-P5 批量回补与人工复核 | ISSUE-007, ISSUE-008 | 🟨 已实现内存工作流，待持久化生产化 | 未解析引用不再静默堆积 |

## Issue 详细状态

| Issue | 标题 | 优先级 | 里程碑 | 依赖 | 状态 |
|-------|------|--------|--------|------|------|
| ISSUE-001 | 项目基础设施与核心领域对象模型 | P0 | milestone-0 | 无 | ✅ 已实现 |
| ISSUE-002 | stock_basic 初始化管线与别名生成 | P0 | milestone-0 | #001 | ✅ 已实现 |
| ISSUE-003 | 别名查表与确定性匹配引擎 | P1 | milestone-1 | #002 | ✅ 已实现 |
| ISSUE-004 | 实体画像查询与 resolve_mention 确定性路径 | P1 | milestone-1 | #003 | ✅ 已实现 |
| ISSUE-005 | HanLP NER 集成与模糊候选接口 | P2 | milestone-2 | #004 | 🟨 基础链路已实现，外部后端待生产化 |
| ISSUE-006 | reasoner-runtime LLM 辅助消歧与完整解析链 | P2 | milestone-2 | #005 | 🟨 边界与注入链路已实现，运行时接入待生产化 |
| ISSUE-007 | 批量解析与未解析引用回补 | P2 | milestone-3 | #006 | 🟨 内存工作流已实现，持久化适配待生产化 |
| ISSUE-008 | 人工复核队列与解析审计链 | P2 | milestone-3 | #007 | 🟨 内存工作流与审计 payload 已实现，持久化适配待生产化 |

## M4.8 focused proof

状态：✅ 已覆盖 focused proof，待生产化扩展。

本轮新增 `scripts/m4_8_focused_resolution_proof.py`，复用现有
`resolve_mention_with_repositories()` 解析链和 in-memory repositories，验证：

- deterministic exact/code/rule 命中
- ambiguous injected fuzzy candidates 不自动乱选，进入 manual review 语义
- no-candidate unresolved fail-closed
- runtime `ResolutionCase`
- `get_resolution_audit_payload()` 审计 payload
- contracts `ResolutionCase` projection

边界声明：

- 不修改 contracts。
- 不新增 holdings subtype。
- 不新增核心 resolver 能力。
- proof 使用 injected fake fuzzy matcher；外部 fuzzy 后端生产化仍待后续工作。

## 依赖链

```
ISSUE-001 (核心模型)
  └── ISSUE-002 (stock_basic 初始化)
        └── ISSUE-003 (确定性匹配)
              └── ISSUE-004 (画像查询 + resolve_mention 确定性)
                    └── ISSUE-005 (HanLP + fuzzy 候选接口)
                          └── ISSUE-006 (LLM 辅助消歧)
                                └── ISSUE-007 (批量回补)
                                      └── ISSUE-008 (人工复核)
```

## 关键指标红线

| 指标 | 红线 | 验证阶段 |
|------|------|----------|
| alias 解析延迟 | < 50ms（纯查表路径） | 阶段 1 |
| mention resolution 平均耗时 | < 2 秒 | 阶段 2 |
| A+H 错误合并率 | 0（零容忍） | 阶段 0 起持续验证 |
| 裸文本进入 formal 链路 | 0（零容忍） | 阶段 1 起持续验证 |
| unresolved 误判为 resolved | < 1% | 阶段 2 |
| A 股上市公司覆盖率 | 100% | 阶段 0 |
