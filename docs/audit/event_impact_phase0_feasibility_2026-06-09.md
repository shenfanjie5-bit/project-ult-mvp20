# Phase 0 — 事件/新闻→个股影响系数:数据可行性审计 (THE GATE)

**Date:** 2026-06-09  ·  **Branch:** feature/a-share-fixes  ·  **Mode:** read-only, `DOCKCASE_WRITEBACK=0`
**Verdict:** ✅ **GO on Track A (结构化事件,可历史回测)** · ⛔ **Track B 无历史归档,只能向前验证**

---

## 1. 命门结论:有没有可回测的历史?

| 问题 | 结论 | 证据 |
|---|---|---|
| 自由文本新闻有历史时序吗? | **没有** | `mvp20/storage.py:4` — `realtime_current` 是 "current value … UPSERT" 的**热快照**;`handle_market_events` (server.py:578) 只读 `L9.event.intraday_news`/`L9.media.report` 当前值,无系数、无归档。Track B 历史回测**不可能**,只能从现在起向前收集。 |
| 结构化事件有带日期的历史吗? | **有,且巨量** | DockCase 挂载在线 (`/Volumes/dockcase2tb`),5 个 Track A endpoint 各有 3.7k–5.6k 只 per-symbol CSV,带 `ann_date`/`report_date` PIT 时间戳。 |
| 前向收益引擎在吗? | **在** | `factor_research/_datalib.load_price_matrices` 加载成功:**20230103→20260605,816 交易日,1617 股**(RET=pct_chg/100)。 |
| Walk-forward 面板? | **14 个** | `factor_research/pit_extra/{20240131…20251231}` 14 个 PIT 打分面板 + 3 个冻结全宇宙 `pit.sqlite`。 |

**"假系数" 前提已坐实**:`derive.py:2675` 的 `L11.short.event_impact = clip((news_count+ann_count)/40-0.25)` 是数新闻条数的粗代理,非情绪/非逐条,且不回流到事件时间轴;前端 `coefficient:0` 写死。

---

## 2. Track A 各事件类型:样本量 / 日期覆盖 / 字段 / 带符号维度

在价格面板窗口 `[20230103 .. 20260531]` 内抽样 55 只/类,按 `(代码,公告日)` 去重计 distinct event,再按 文件总数 外推全宇宙(**估计值**):

| Endpoint | 在盘文件 | 全样本日期跨度 | **估全宇宙可回测事件** | 带符号维度 (样本分布) | 评级 |
|---|---|---|---|---|---|
| **forecast 业绩预告** | 5,477 | 2001→2026 | **~17,500** | `type`: 预增54/预减51/续亏71/首亏49/扭亏44/略增23 + `p_change_min/max` 幅度 | ⭐ 主线 |
| **stk_holdertrade 增减持** | 4,864 | 2007→2026 | **~24,000** | `in_de`: DE(减持)385 / IN(增持)106 + `change_ratio` | ⭐ 主线 |
| **report_rc 卖方评级** | 4,670 | 2006→2026 | **~169,000**(per-analyst-row) | `rating`: 买入/增持为主(几乎无卖出)+ `tp` 目标价 | 次线(需"评级变动/目标价修订"特征,否则全是买入退化) |
| **dividend 分红送转** | 5,600 | 2021→2026 | **~19,000** | `div_proc`: 预案/股东大会通过/实施 + `cash_div`/`stk_div` | 次线(信号被预期、生命周期多阶段) |
| **express 业绩快报** | 3,761 | 2020→2026 | **~4,400** | `yoy_net_profit`: 正61/负3(**强正偏选择性**) | 末位(N 小、偏正) |

**带符号映射(初定):** 业绩预告 预增/扭亏/略增→+ ,预减/首亏/续亏/略减→− ;增减持 IN→+ ,DE→− (按 change_ratio 加权);评级 仅取**上调/下调与目标价修订**方向;分红 预案首次披露为事件。

---

## 3. 现成基建(已核对存在)

- 前向收益:`factor_research/_datalib.load_price_matrices("20230101")` → RET/TO/MV/cal/cols(已缓存 npz,秒级)。
- PIT 打分:`pit_backtest/score.py::score_one(ts, db, freeze_l0=True)`,冻结 L0–L3 质性层 + 4 个会泄漏的 Track-B 事件节点(score.py:62-66 已写明)。
- 冻结快照:`runtime/backtest/{20260116,20260309,20260421}/pit.sqlite`(各 1641 股)。

---

## 4. 预注册 KILL 标准(开工前写死,事后不许挪)

事件后收益窗一律从 **t+1 起算**(`ann_date` 无盘中时刻 → 一律当下一交易日影响,严杜同日 look-ahead)。Abnormal = 个股收益 − 截面/行业均值。

1. **事件研究单调+显著**:各事件类型,CAR[t+1, t+h] (h∈{1,3,5,10}) 随系数符号单调;top-vs-bottom 桶 CAR 差在**全样本** t≥2(或 bootstrap 95% CI 不含 0)。
2. **Walk-forward 样本外符号正确率**:在不重叠时间折上,预测系数符号 = 实现 abnormal 符号 的比例 > 50%,且 **95% CI 下界也 > 50%**(二项检验,给区间)。
3. **组合 P&L 扣成本跑赢基准**:"正事件买 / 负事件避(或空)" 组合,扣现实成本后,在**多数非重叠窗口**跑赢等权基准。成本基线 **25bps 往返**(印花税 5bps 卖出 + 双边佣金 ~5bps + 滑点 10-20bps),并做 15/40bps 敏感性。
4. **任一不过 → 如实判负,不硬塞生产**。rank-IC 显著但 P&L 死 = 否决。Phase 3 额外检验:剔除头尾 1% 极端事件后 P&L 是否存活(防被少数事件撑起)。

---

## 5. 必须在 Phase 1/3 处理的泄漏与偏差风险(诚实清单)

- **幸存者偏差(最大隐患)**:价格面板 universe 来自 `backtest.sqlite` 在 base_date=20260116 的打分股 → **以 2026 年存活股回看 2023–2025 事件**,退市股缺失 → 收益上偏。Abnormal(减均值)只能部分缓解。**Phase 3 必查,报告需明确标注此天花板。**
- **首次公告**:forecast 有 `first_ann_date` 与 `update_flag`,须取每 (股,end_date) **最早**一次,不能把修订稿当原始信号。
- **t+1 对齐**:无盘中时刻,收益窗起点 = `ann_date` 之后第一个完整交易日;严格 `event_time < 窗起点`。
- **卖方羊群/回声**:report_rc 同股多券商同周扎堆 → 每股每窗去重为一个事件;评级层面几乎全"买入" → 必须用**变动**而非水平。
- **express 选择性**:倾向只在好消息时披露快报 → 正偏,单独建模需谨慎。

---

## 6. 建议的 Phase 1 fan-out(待批)

- **Phase 1a(基础,1 agent / 先建)** `factor_research/04_event_study/eventlib.py`:5 endpoint 事件归一化加载器 → `(ts, event_date, sign, magnitude, type)`;t+1 对齐;前向 & abnormal 收益(减市场/行业均值);bootstrap 显著性;walk-forward 折;A 股成本模型;§4 三条 kill 函数。**这是 A/B 共用脊柱**(把任务里的 Agent C 防泄漏&评估并入此处,消除重复)。
- **Phase 1b(并行)**:
  - **Agent A 事件研究**:用 eventlib 对 forecast/增减持(主)+ report_rc/dividend(次)算事件窗 CAR、按符号/分桶看单调性与显著性,挑真有 alpha 的。
  - **Agent B 标签&特征**:定义带符号影响目标(连续 abnormal 回归 vs 分桶);Track B 的 LLM 抽取 prompt(事件类型/利空利好/强度)+ 便宜基线(关键词/FinBERT)设计,**为向前验证备料**(本阶段不跑历史)。
- **Phase 2**:对通过 Phase 1 的事件类型建系数模型,多个非重叠窗 walk-forward(事件研究 + P&L 双标准)。
- **Phase 3(独立对抗审查)**:幸存者偏差 / 泄漏 / P&L 被极端事件撑起 / IC≠P&L / 诚实天花板。
- **Phase 4(集成预案,不落地)**:`/market-events` 加 `coefficient` → 前端 `useRealMarketEvents.ts:48` 去写死 0 → 修 chip 颜色/符号语义。仅出 diff + 测试计划。

---

## 7. 一句话建议

**做 Track A,先 forecast + 增减持两类干净带符号事件打通 eventlib+kill 全链路,拿到第一组扣成本 P&L 数字;report_rc/dividend 次线;express 末位;Track B 推迟到"向前收集 + LLM 抽取"阶段。** Track B 现在无法历史证伪,任何"现在就上 LLM 情绪系数"都是装饰性数字。
