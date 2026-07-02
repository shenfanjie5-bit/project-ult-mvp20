# Session 状态 / 续作锚点 — 2026-06-06

> compaction 前落盘。续会话先读此文 + `base_score_redesign_proposal.md`(§14-15)
> + `a_share_spec_completeness_2026-06-05.md`(§7)+ `production_lookahead_findings.md`。
> 分支 `feature/a-share-fixes`。只测 A 股、沟通用中文。

## 提交链(本轮 8 个,均已提交、工作树干净)
1. `2ddd122` Phase-2c — codex 填全 A 股 L1-L3 定性层
2. `c258154` R-6 — 55 个 filled-but-dead 定性 dp_id 标 `participates_in_score=false` + onboard 加 build-peer-context 步
3. `653c6b5` Phase-3 — R-2c(去 confidence 死乘数,记成 band 不压 base)+ R-5(阈值绝对意义)
4. `fa46894` — 删 300750 根目录空壳 overlay(潜伏地雷)
5. `a018da1` review 返工 — **field_governance 让 spec 的 participates 权威覆盖**(R-6 之前是 runtime no-op)+ damp 去死节点稀释 + onboard save_peer_context 原子写
6. `f4fe505` — L11.trade.signal 引用 scoring 阈值常数(死信号、非打分)
7. `1f151f8` 超前修复 — L3 hfq 复权价 + L1/L2 ann_date 可见性过滤(财报/预告 fetcher)
8. `ae1a431` onboard parity — collect 补调 fetch_tushare_batch(财务批)+ codex 步加固

## 诚实终态(关键数,核对用)
- base median **−0.401**(诚实刻度,risk 去死节点稀释后);signal **BUY=10 / HOLD=30 / WATCH=28 / AVOID=48**(@阈值 0.20/−0.15/−0.50)。
- R-5 阈值 **0.20/−0.15/−0.50 绝对意义**(用户定:不卡百分位、市场差可没 buy);market adapter ≈ identity(median 1.007),base=0 中性。
- 真实打分面 LIVE **79** dp_id;55 个死定性已运行时退出(participates 权威化)。
- 回测裁决:**中长期(60–90d)有方向预测力**(rank-IC 0.165/0.079、AVOID 桶唯一负收益),30d 无效;样本小(p≈0.08)+ 幸存者偏差 → "方向合理"非"已验证 alpha"。

## 待办(全部 user-gated 或 backtest-gated)
1. **重跑 onboard 测试**确认财务 parity(ae1a431 修法机械正确,但 live tushare 这边跑不了 → 交 onboard 测试者复跑,确认 fundamental/expectation_gap/财务risk 3 个 base 项实际填上)。
2. **codex 硬质量门**(verify_overlay_closed_loop / check_c1_quality 当门 + xhigh 重跑)——post-R-6 codex 层非打分=展示质量,不影响分;做不做用户定。
3. **R-7 动态宏观 regime** — regime 层已建但休眠(market_regime 因子 +0.0815 但 multiplier≈1.0);放大 = 择时押注,**用专门 PIT 回测实验验前向 IC 再用数据定 beta**,不手调。
4. **Inactive(9.7%)/真零(13.4%)damp 稀释** — 该不该让 benign 读数稀释 = 建模分岔(再去 base −0.20 到 −0.60),用回测验"排除 benign 是否提升 IC"再定。
5. **L4 asof 架构**(now 锚定/缓存串日/peer_context 读活库)——仅生产端历史复算用,大改,暂缓(回测已有独立 PIT harness)。

## gotcha(别踩)
- **回测对话只读、隔离**:`pit_backtest/` + `scripts/run_pit_backtest.py` + `tests/test_pit_*`/`test_backtest_*` + `runtime/backtest/` + `production_lookahead_findings.md` 都是回测对话产物,**不归我改**;改生产不影响它(它有独立 PIT collector)。
- R-6 的"非打分"是经 `field_governance.apply_to_node` 让 spec 权威覆盖 overlay 陈旧 `participates_in_score` 实现的(a018da1);别以为改 data_point_roles.yaml 就自动生效(c258154 当时就是 runtime no-op)。
- damp 分母会被 score=0 节点稀释(`_sum_role_target` damp);f4a63a7 只修了 merit mean。
- 审计文档按惯例 **untracked**(只提交代码/spec/test)。
- /tmp harness:spec_strict_chain.py、r6_measure.py、rev_decomp.py、rev_honest_scale.py、newstock_sim.py 等(只读复核用)。
- 数据质量旧 flag:A 股 revenue_growth 疑 qoq-vs-cumulative base artifact,未核。
