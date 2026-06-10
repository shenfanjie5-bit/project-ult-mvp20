# A 股评分系统 · 无超前 (Point-in-Time) 回测报告

**基准日 (today):** 20260605　**池子:** 116 只 A 股 (survivorship-biased)　**git:** `fa4689453c39fa55a917db1618517e2ac7c69a3e`

**基准日序列:** T0=20260605 · T-30=20260421 · T-60=20260309 · T-90=20260116

**复权:** hfq · **打分口径:** 排除 LLM 定性层 (L0-L3) + 冻结行业景气 L0 · **信号阈值:** BUY≥0.30 / HOLD≥−0.10 / WATCH≥−0.45 (固定)


## 结论 (One-line verdict)

- **+30d:** mean rank-IC = 0.0102 (±0.1346, 3 窗口) · signal 单调=False · BUY−AVOID(pooled)=0.0280 · n_obs=348
- **+60d:** mean rank-IC = 0.0789 (±0.0341, 2 窗口) · signal 单调=False · BUY−AVOID(pooled)=0.0600 · n_obs=232
- **+90d:** mean rank-IC = 0.1646 (±—, 1 窗口) · signal 单调=False · BUY−AVOID(pooled)=0.1811 · n_obs=116

> ⚠️ 小样本 (n≈116/截面, 每 horizon 1–3 个跨窗口且非独立)，IC 标准误大；**这是泄漏/合理性审计，不是 alpha 证明**。survivorship 使 IC 上偏。


## 泄漏审计 (independent re-verification)

- HARD violations: **0**　WARN: 8　→ **PASS**
- [20260421] 10858 rows; 所有特征 observation-date ≤ asof (无越界)
- [20260309] 10842 rows; 所有特征 observation-date ≤ asof (无越界)
- [20260116] 10861 rows; 所有特征 observation-date ≤ asof (无越界)
- 前向收益: 696 行, end_date≤T0 violations=0

## 各 horizon 明细


### +30d horizon

| base→end | n | rank-IC | p | IC 95%CI | 五分位 顶−底 | BUY−AVOID | perm-p |
|---|---|---|---|---|---|---|---|
| 20260116→20260309 | 116 | -0.0742 | 0.4289 | [-0.25, 0.11] | 0.0212 | 0.0581 | 0.2008 |
| 20260309→20260421 | 116 | 0.1655 | 0.0759 | [-0.02, 0.34] | 0.0620 | 0.0516 | 0.2438 |
| 20260421→20260605 | 116 | -0.0606 | 0.5183 | [-0.24, 0.12] | -0.0755 | -0.0272 | 0.6893 |

**pooled signal buckets (+30d, n_obs=348):**

| signal | n | mean fwd-ret | hit-rate |
|---|---|---|---|
| BUY | 60 | 0.0323 | 0.3833 |
| HOLD | 63 | -0.0072 | 0.3651 |
| WATCH | 84 | 0.0090 | 0.3810 |
| AVOID | 141 | 0.0044 | 0.3688 |

### +60d horizon

| base→end | n | rank-IC | p | IC 95%CI | 五分位 顶−底 | BUY−AVOID | perm-p |
|---|---|---|---|---|---|---|---|
| 20260116→20260421 | 116 | 0.1029 | 0.2715 | [-0.08, 0.28] | 0.1176 | 0.1118 | 0.0838 |
| 20260309→20260605 | 116 | 0.0548 | 0.5594 | [-0.13, 0.23] | 0.0786 | 0.0089 | 0.9310 |

**pooled signal buckets (+60d, n_obs=232):**

| signal | n | mean fwd-ret | hit-rate |
|---|---|---|---|
| BUY | 39 | 0.0571 | 0.3590 |
| HOLD | 46 | 0.0221 | 0.3913 |
| WATCH | 56 | 0.0696 | 0.5000 |
| AVOID | 91 | -0.0029 | 0.3516 |

### +90d horizon

| base→end | n | rank-IC | p | IC 95%CI | 五分位 顶−底 | BUY−AVOID | perm-p |
|---|---|---|---|---|---|---|---|
| 20260116→20260605 | 116 | 0.1646 | 0.0775 | [-0.02, 0.34] | 0.2064 | 0.1811 | 0.1068 |

**pooled signal buckets (+90d, n_obs=116):**

| signal | n | mean fwd-ret | hit-rate |
|---|---|---|---|
| BUY | 16 | 0.1628 | 0.4375 |
| HOLD | 19 | 0.0309 | 0.3158 |
| WATCH | 28 | 0.0584 | 0.3214 |
| AVOID | 53 | -0.0183 | 0.3208 |

## 方法论与残留风险 (Methodology & residual risk)

**口径.** 基准日 T-30/-60/-90 为交易日 (tushare `trade_cal`)。前向收益 = hfq 复权收盘
`close(end)/close(base) − 1`，6 组 (base→end) 终点全部 ≤ T0（已实现）。打分复用生产引擎
(`aggregate_company_graph` + `score_company`)，但喂的是**独立 PIT 采集**的数据：财报按
`f_ann_date/ann_date ≤ 基准日` 过滤取最近一期、估值/资金/价按基准日当日、横截面 peer_context
每个基准日单独重建。rank-IC = Spearman(base_score, fwd_ret) 截面相关；signal 桶按 BUY/HOLD/
WATCH/AVOID 统计均收益/命中率/多空。跨同 horizon 窗口报 **per-window IC 的均值±std**（不堆叠成
单帧，避免伪独立）。

**残留泄漏风险（诚实告知）.**
1. **行业景气 L0 冻结** ⇒ fundamental 退化为硬财务(L5)+估值+资金+风险骨干；覆盖度低于生产，
   行业层信号被剔除（既因 overlay 内嵌当前 YoY 会泄漏，也按口径排除）。
2. **拟合常数** (信号阈值 BUY≥0.30 等、横截面再中心化基准 ROE_BENCH=3.1、archetype 毛利率中位数)
   均在当前 2026 池子上标定；过去基准日套用属**标签层二阶超前**（缓变的再中心化偏移，非预测标签
   本身）。按确认接受并在此说明，未按基准日重标。
3. **引擎内残留时间假设**（`aggregator._recency` wall-clock、DeriveRunner news_age）只作用于已排除
   的定性/新闻节点，低实质性。
4. **情绪类 dp_id**（雪球热度/新闻）无历史端点 → PIT 里 Inactive；它们属 sentiment/expectation_gap，
   非核心。
5. **生产泄漏 bug**（财报无 `f_ann_date` 过滤、forecast 无日期过滤、价无复权、`now` 锚定、peer_context
   读活库）见 `production_lookahead_findings.md`；本回测通过独立 PIT 采集**绕开**它们，未修改生产代码。

**LLM 隐性记忆.** 即便把检索输入约束到 ≤ 基准日，LLM 的参数化记忆仍“知道”基准日之后的事 —— 这无法
清除。因此严格无超前的唯一稳妥做法就是**分数不含 LLM 主观判断**：本回测正是如此（L0-L3 定性层完全
排除，分数只由确定性数值链驱动）。

**survivorship / 选样偏差.** 池子是**今天**精选的主题龙头 (config/mvp20.universe.yaml)，无退市/失败
标的；回测只回测了“幸存者”，IC 系统性上偏。结论仅在“幸存者内”成立。

**统计功效.** n≈100+/截面、每 horizon 仅 1–3 个跨窗口且复用同一池子（时间不重叠但截面非独立），
IC 标准误大；单点 IC 不显著属正常。本报告是**泄漏审计 + 合理性检查**，非策略验证。

