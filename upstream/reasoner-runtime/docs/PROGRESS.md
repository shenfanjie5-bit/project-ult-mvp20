# reasoner-runtime 项目进度追踪

> **项目版本**：v0.1.2
> **文档生成日期**：2026-04-17
> **路线图来源**：§21 实施路线图

---

## 总览

| 阶段 | 里程碑 | Issue 数 | 状态 | 预估工期 |
|------|--------|---------|------|---------|
| 阶段 0 | P2b 运行时骨架 | 2 | 🔲 未开始 | 2-3 天 |
| 阶段 1 | P2b 主链路打通 | 3 | 🔲 未开始 | 3-5 天 |
| 阶段 2 | P2b 安全与观测 | 2 | 🔲 未开始 | 2-4 天 |
| 阶段 3 | P2-P4 跨模块接入 | 2 | 🔲 未开始 | 3-5 天 |
| 阶段 4 | P6+ 可选观测后端 | 2 | 🔲 未开始 | 按需 |

**总计**：11 个 Issue

---

## 阶段 0：P2b 运行时骨架

**目标**：建立统一调用接口与最小 provider 配置骨架
**退出条件**：main-core 能 import 并发起最小空调用

| Issue | 标题 | 优先级 | 能力链 | 状态 |
|-------|------|--------|--------|------|
| ISSUE-001 | 项目基础设施、核心领域对象与配置模块 | P0 | 横切基础 | 🔲 未开始 |
| ISSUE-002 | 统一调用入口骨架与 Provider 抽象 | P0 | 统一调用入口 | 🔲 未开始 |

**依赖关系**：ISSUE-002 → ISSUE-001

---

## 阶段 1：P2b 主链路打通

**目标**：打通 LiteLLM + Instructor + replay bundle 完整链路
**退出条件**：1 条正式调用可产出完整结构化结果与回放字段

| Issue | 标题 | 优先级 | 能力链 | 状态 |
|-------|------|--------|--------|------|
| ISSUE-003 | LiteLLM + Instructor 结构化输出主链路 | P0 | 结构化输出校验 | 🔲 未开始 |
| ISSUE-004 | Replay Bundle 五字段生成与 Lineage 记录 | P0 | PII scrub + replay bundle | 🔲 未开始 |
| ISSUE-005 | Fallback/Retry 链路与失败分类 | P0 | 统一调用入口 + fallback/retry | 🔲 未开始 |

**依赖关系**：ISSUE-003 → ISSUE-002；ISSUE-004 → ISSUE-003；ISSUE-005 → ISSUE-003

---

## 阶段 2：P2b 安全与观测

**目标**：补齐 PII scrub、OTEL 最小观测层与供应链锁定
**退出条件**：外发前脱敏成立，最小观测数据可用

| Issue | 标题 | 优先级 | 能力链 | 状态 |
|-------|------|--------|--------|------|
| ISSUE-006 | PII Scrub Handler 与统一脱敏链 | P1 | PII scrub + replay bundle | 🔲 未开始 |
| ISSUE-007 | OTEL Callbacks 最小观测层与供应链锁定 | P1 | 健康探测 + 观测 callback | 🔲 未开始 |

**依赖关系**：ISSUE-006 → ISSUE-004；ISSUE-007 → ISSUE-005

---

## 阶段 3：P2-P4 跨模块接入

**目标**：接入 main-core / entity-registry，完成 health_check() 与 orchestrator 对接
**退出条件**：orchestrator 可在 Phase 0 调用健康探测，业务模块不再直连 provider

| Issue | 标题 | 优先级 | 能力链 | 状态 |
|-------|------|--------|--------|------|
| ISSUE-008 | health_check() 实现与 Provider 健康探测 | P1 | 健康探测 + 观测 callback | 🔲 未开始 |
| ISSUE-009 | 跨模块接入适配与端到端集成验证 | P1 | 横切集成 | 🔲 未开始 |

**依赖关系**：ISSUE-008 → ISSUE-006；ISSUE-009 → ISSUE-008

---

## 阶段 4：P6+ 可选观测后端

**目标**：在不改变调用接口的前提下接入 Langfuse 等 callback backend
**退出条件**：观测后端变化不影响调用方代码

| Issue | 标题 | 优先级 | 能力链 | 状态 |
|-------|------|--------|--------|------|
| ISSUE-010 | Langfuse Callback Backend 适配器 | P2 | 健康探测 + 观测 callback | 🔲 未开始 |
| ISSUE-011 | 观测后端配置切换与回归验证 | P2 | 横切测试 | 🔲 未开始 |

**依赖关系**：ISSUE-010 → ISSUE-007；ISSUE-011 → ISSUE-010

---

## 全局依赖图

```
ISSUE-001 (基础设施+领域对象)
  └── ISSUE-002 (调用入口骨架)
        └── ISSUE-003 (结构化输出主链路)
              ├── ISSUE-004 (Replay Bundle)
              │     └── ISSUE-006 (PII Scrub)
              │           └── ISSUE-008 (Health Check)
              │                 └── ISSUE-009 (跨模块集成)
              └── ISSUE-005 (Fallback/Retry)
                    └── ISSUE-007 (OTEL + 供应链锁定)
                          └── ISSUE-010 (Langfuse Adapter)
                                └── ISSUE-011 (回归验证)
```

---

## 验收标准对照（§23）

| 验收条目 | 对应 Issue | 状态 |
|----------|-----------|------|
| 所有业务模块通过 reasoner-runtime 完成统一结构化调用 | ISSUE-009 | 🔲 |
| generate_structured() 稳定产出结构化结果 + llm_lineage + replay bundle 五字段 | ISSUE-003 + ISSUE-004 | 🔲 |
| health_check() 按 provider/model 组合执行探测 | ISSUE-008 | 🔲 |
| PII scrub 落地 | ISSUE-006 | 🔲 |
| fallback/retry 落地 | ISSUE-005 | 🔲 |
| 依赖 hash 锁定落地 | ISSUE-007 | 🔲 |
| 主项目角色与模块边界一致 | ISSUE-009 | 🔲 |
