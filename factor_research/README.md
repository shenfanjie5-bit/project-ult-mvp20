# 量化因子/模型 研究（隔离目录）

> 启动：2026-06-08。驱动方式：`/loop` 动态自调度（多 agent 研究）。
> **硬约束：本研究只读，绝不改动本项目任何文件/代码/数据。所有产出只写在本目录 `factor_research/` 内。**

## 根因（用户原话）

> 系统中很多数据/指标偏机械性，无法较好地适应现在**机构为主**的市场，需要纳入各种类型的公式/模型去找到**更优模型**。

机械性 = 时序自身百分位、全局固定 ref、abs() 压负、覆盖率代理、死常数 confidence。这些在 R-1~R-7 已部分修过（见 `docs/audit/base_score_redesign_proposal.md`），但仍留下：
- **`funding_score`/`capital_sentiment` 轴近乎死轴**（只接了 `L7.flow.active_inflow`），而 tushare 侧的**机构/资金/筹码数据极其丰富**（北向 `hk_hold`/`moneyflow_hsgt`、游资 `hm_detail`、大宗 `block_trade`、融资融券 `margin`、筹码 `cyq_perf`、龙虎榜）。这正是"机构为主市场"适配的最大缺口。
- 缺显式 **quality 因子族**（Piotroski F、Sloan 应计、Novy-Marx 毛利率）、**momentum/reversal**（A 股短期反转强）、**low-vol / 特异波动**、**宏观 regime**（R-7 deferred）。

## 方法（三阶段，逐阶段在 loop 迭代里推进）

- **Phase 1 — 搜集（多 agent，并行）**：按因子族分类，搜集 A 股可用的量化因子 / 公式 / 模型，结构化落盘到 `01_factor_catalog/`。每条记录：定义/公式、经济学逻辑、典型周期、所需数据输入、证据/出处、A 股特异性与陷阱、机构资金相关度。
- **Phase 2 — 代入系统（可行性映射）**：对每条因子，比对 `00_system_inventory.md` 的【可用数据】+【spec dp_id / score_target】，判定：✅ 现有数据+字段直接可算 / 🟡 数据有但需新增 dp_id 或派生 / 🔴 数据不足。产出 `02_mapping/feasibility.md`。
- **Phase 3 — 影响研究（多 agent，逐个）**：只对 ✅/🟡 可行因子，逐个研究"接进系统是**正面还是负面**"。优先用 `pit_backtest/` 的 IC/分档/信号桶方法论（在本目录复刻，不碰原文件）做证据级判断；否则给机制级论证 + 与现有轴的相关/冗余/冲突分析。产出 `03_impact_studies/`。

## 目录

- **`FINAL_REPORT.md`** — ⭐ 最终结论（先读）：证据链 + "更优模型"处方 + 对原 thesis 的回应。
- `PROPOSAL_better_model.md` — 设计蓝图（逐轴增强 + 6 条纪律 + 4 波路线，含 3b 实证回填）。
- `run_ic.py`/`run_regime.py`/`run_sue.py`/`run_flow.py`/`_datalib.py` — Phase 3b 回测 harness（隔离、只读数据）。
- `00_system_inventory.md` — 系统"菜单"：可用数据 + 打分架构 + dp_id→score_target 路由 + 阈值 + 回测能力 + 已知缺口。因子必须能映射到这里才算"代入成功"。
- `01_factor_catalog/` — Phase 1 搜集产出（每族一文件 + 汇总 catalog）。
- `02_mapping/` — Phase 2 可行性映射。
- `03_impact_studies/` — Phase 3 逐因子影响研究。
- `data/` — 结构化中间产物（json/csv）。

## 运行日志

| 时间 | 迭代 | 动作 | 状态 |
|---|---|---|---|
| 2026-06-08 | 0 | 建隔离目录 + 系统勘察 + 写 inventory | ✅ |
| 2026-06-08 | 1 | Phase 1 多 agent 搜集（10 族/166 因子） | ✅ 见 01_factor_catalog/ |
| 2026-06-08 | 2 | Phase 2 可行性映射 + 去重 + 27 单元优先清单 | ✅ 见 02_mapping/feasibility.md |
| 2026-06-08 | 3 | Phase 3a 逐因子影响研究（27 agent）：1 POSITIVE/23 CONDITIONAL/3 NEGATIVE | ✅ 见 03_impact_studies/ |
| 2026-06-08 | 4 | 综合"更优模型"提案（6 条纪律 + 逐轴增强 + 4 波路线 + 3b 计划） | ✅ 见 PROPOSAL_better_model.md |
| 2026-06-08 | 5 | Phase 3b 实证 IC（STREV/IVOL，2023-26/76窗）：**符号随regime翻转，2026逆风** | ✅ 见 03_impact_studies/3b_empirical/RESULTS.md |
| 2026-06-08 | 6 | Phase 3b 续：regime-conditioning **验证成功**（翻转可预测）+ SUE 更稳更正交但很弱 | ✅ 见 03_impact_studies/3b_empirical/RESULTS2_regime_and_sue.md |
| 2026-06-08 | 7 | Phase 3b 续：实证机构资金流（CNIR≈0/CYQ弱/北向稀疏/融资未缓存）→ **flow thesis 不成立** | ✅ 见 03_impact_studies/3b_empirical/RESULTS3_flow.md |
| 2026-06-08 | 8 | **最终报告**：结论=regime-aware(R-7) 是唯一数据强支持的增益 | ✅ 见 **FINAL_REPORT.md** |
| 2026-06-08 | 9 | regime-conditioned 原型：真 base_score IC 一月内 +0.24→−0.24；overlay 救2026伤好年(净略负)→方向对但非一行开关 | ✅ 见 03_impact_studies/3b_empirical/RESULTS4_prototype.md |
| 2026-06-08 | 10 | Agent A：regime-gate 真分 2026 避损 **+4pp**；但 IC 看不见门控、全样本略拖累 → 需"坏regime+IC衰减"双条件 | ✅ RESULTS5_gate.md |
| 2026-06-08 | 11 | Agent B：真分扩 4 日期(250股)；IC 跨2024-26随regime翻转(+0.24→−0.19)；OOS 无 IC 增益(因门控对IC不可见) | ✅ RESULTS6_realbase.md |
| 2026-06-08 | 12 | **A+B 收口**：问题/解法在【决策/P&L层】非IC层；只降权不反号、双条件、用P&L验证 | ✅ **RESULTS7_synthesis_A_B.md** + FINAL_REPORT §3.8 |
