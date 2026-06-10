# A 股评分系统 · 无超前 (Point-in-Time) 回测报告

**基准日 (today):** 20260607　**池子:** 1641 只 A 股 (survivorship-biased)　**git:** `14ee05e1e26de1a638e971041c36ba764c512c6e`

**基准日序列:** T0=20260605 · T-30=20260421 · T-60=20260309 · T-90=20260116

**复权:** hfq · **打分口径:** 排除 LLM 定性层 (L0-L3) + 冻结行业景气 L0 · **信号阈值:** BUY≥0.30 / HOLD≥−0.10 / WATCH≥−0.45 (固定)


## 结论 (One-line verdict)

- **+30d:** mean rank-IC = -0.0189 (±0.1175, 3 窗口) · signal 单调=False · BUY−AVOID(pooled)=-0.0411 · n_obs=4853
- **+60d:** mean rank-IC = 0.0091 (±0.0824, 2 窗口) · signal 单调=False · BUY−AVOID(pooled)=-0.0567 · n_obs=3230
- **+90d:** mean rank-IC = 0.0384 (±—, 1 窗口) · signal 单调=False · BUY−AVOID(pooled)=-0.0435 · n_obs=1612

> ⚠️ 小样本 (n≈1641/截面, 每 horizon 1–3 个跨窗口且非独立)，IC 标准误大；**这是泄漏/合理性审计，不是 alpha 证明**。survivorship 使 IC 上偏。


## 泄漏审计 (independent re-verification)

- HARD violations: **0**　WARN: 27　→ **PASS**
- [20260421] 151231 rows; 所有特征 observation-date ≤ asof (无越界)
- [20260309] 150444 rows; 所有特征 observation-date ≤ asof (无越界)
- [20260116] 151212 rows; 所有特征 observation-date ≤ asof (无越界)
- 前向收益: 9846 行, end_date≤T0 violations=0

## 各 horizon 明细


### +30d horizon

| base→end | n | rank-IC | p | IC 95%CI | 五分位 顶−底 | BUY−AVOID | perm-p |
|---|---|---|---|---|---|---|---|
| 20260116→20260309 | 1609 | 0.0637 | 0.0106 | [0.01, 0.11] | 0.0033 | 0.0152 | 0.3698 |
| 20260309→20260421 | 1617 | 0.0330 | 0.1850 | [-0.02, 0.08] | -0.0103 | -0.0145 | 0.3209 |
| 20260421→20260605 | 1627 | -0.1534 | 0.0000 | [-0.20, -0.11] | -0.1573 | -0.1231 | 0.0001 |

**pooled signal buckets (+30d, n_obs=4853):**

| signal | n | mean fwd-ret | hit-rate |
|---|---|---|---|
| BUY | 691 | 0.0145 | 0.4226 |
| HOLD | 697 | 0.0257 | 0.4290 |
| WATCH | 836 | 0.0347 | 0.4689 |
| AVOID | 2629 | 0.0555 | 0.4656 |

### +60d horizon

| base→end | n | rank-IC | p | IC 95%CI | 五分位 顶−底 | BUY−AVOID | perm-p |
|---|---|---|---|---|---|---|---|
| 20260116→20260421 | 1610 | 0.0674 | 0.0068 | [0.02, 0.12] | -0.0094 | -0.0023 | 0.9278 |
| 20260309→20260605 | 1620 | -0.0491 | 0.0481 | [-0.10, -0.00] | -0.0894 | -0.1108 | 0.0015 |

**pooled signal buckets (+60d, n_obs=3230):**

| signal | n | mean fwd-ret | hit-rate |
|---|---|---|---|
| BUY | 462 | 0.0455 | 0.4437 |
| HOLD | 471 | 0.0781 | 0.4607 |
| WATCH | 550 | 0.0947 | 0.4836 |
| AVOID | 1747 | 0.1022 | 0.4751 |

### +90d horizon

| base→end | n | rank-IC | p | IC 95%CI | 五分位 顶−底 | BUY−AVOID | perm-p |
|---|---|---|---|---|---|---|---|
| 20260116→20260605 | 1612 | 0.0384 | 0.1229 | [-0.01, 0.09] | -0.0402 | -0.0435 | 0.3356 |

**pooled signal buckets (+90d, n_obs=1612):**

| signal | n | mean fwd-ret | hit-rate |
|---|---|---|---|
| BUY | 230 | 0.1168 | 0.4957 |
| HOLD | 234 | 0.1606 | 0.4316 |
| WATCH | 273 | 0.1543 | 0.5018 |
| AVOID | 875 | 0.1603 | 0.4571 |

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

