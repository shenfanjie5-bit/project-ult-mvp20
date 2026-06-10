# 更优模型提案（Phase 3a 综合）

> 基于 166 因子搜集 → 27 单元逐个影响研究（1 POSITIVE / 23 CONDITIONAL / 3 NEGATIVE）综合。本提案是**研究结论与设计蓝图**，非代码改动。证据见 `03_impact_studies/<unit>.md`。

## 0. TL;DR（最重要的三个结论）

1. **用户 thesis 方向正确，但"加机构流因子"比想象的难**。capital_sentiment/funding 确是死轴（仅 active_inflow），但**naive 机构流因子多数低优先**：北向**日频个股数据 2024-08 已停播**（只剩季度，错过 2-4 周窗、60% 小盘失效）；融资买入=**散户杠杆**非机构、且快照无历史无法算变化率；CNIR 分子=现有 `active_inflow` 的 `big_orders_net`（**重叠**）；股东人数是**季度**信号（与 2-4 周窗错配 3-6×）。
2. **2-4 周窗口下复活资金轴的最佳方式，其实是价量异象**：**短期反转 STREV（换手调整）**（A 股最强 2-4 周信号、纯价量零 PIT 风险）+ **残差动量**（必须残差版，原始截面动量 IC≈−0.03 反而有害）+ **市场级温度计/regime**（融资余额温度计直填 funding 死轴，aggregator.py:1047 自己点名要它）。
3. **最干净的新 alpha 不在资金轴，而在 expectation_gap 与 risk**：**SUE/PEAD**（唯一 POSITIVE——现 3 个 expectation 节点全测"预期形成"，无一测"实际业绩 vs 预期"这个 PEAD 核心，20-60 日窗完美贴合）；**IVOL 低波异象**（A 股最稳健截面信号之一，volatility_risk 轴已有路由+2 个死节点待激活）。

**贯穿性发现**：23 个 CONDITIONAL 的"条件"高度一致 → 收敛成 **6 条普适接入纪律**（§1）。这套纪律本身比任何单因子都重要——它定义了"如何把因子诚实地代入这个系统"。

> ### ⚠️ 实证更新（Phase 3b，2026-06-08，见 `03_impact_studies/3b_empirical/RESULTS.md`）
> 对 Wave 1 价量因子做了 2023-2026、1618 股、76 窗口的真实 IC 回测，结论**修订了 Phase 3a 的乐观**：
> - **STREV（反转）与 IVOL（低波）符号随 regime 翻转，且 2026 当期都逆风**（反转→动量、低波→高波动跑赢）；全样本 |IC|≈0.04-0.06（弱）。
> - 二者与现有 `short_total` 相关 **±0.5**——系统**已隐含**反转+低波 tilt（priced_in/crowdedness），裸加 = 放大一个当期正在拖累的押注。
> - **重心转移**：最大杠杆**不是加静态因子，而是让模型 regime-aware**。**R-7 动态 regime/beta（原 Wave 4）应升为最高优先**，用 regime 调制现有 tilt，而非叠加更多固定符号因子。价量异象**须 regime-conditioned 才接**。fundamental/expectation 类（SUE/PEAD/accruals）预计 regime 更稳但**尚待实证**（下一步）。
>
> **续测确认（regime + SUE，RESULTS2_regime_and_sue.md）**：① regime-条件化**验证成功**——反转/低波的符号翻转是市场趋势/波动的**可预测函数**（反转在【跌+高波】panic regime IC +0.12；低波仅在【高波 risk-on】失效），坐实 R-7 是正解。② SUE **是所测因子里 regime 最稳、最正交**的（与现有分重叠仅 ±0.1-0.25），但**很弱**(IC≈+0.01)——疑因 A 股【预告/快报】提前 price-in 正式财报惊喜 → 须走**预告/快报时点(T2-7)**才有料。

## 1. 六条普适接入纪律（每个因子的前提）

| # | 纪律 | 为什么（来自反复出现的失败模式） |
|---|---|---|
| D1 | **行业 + 市值双中性化**（申万内 z-score 后 tanh）| 不做则几乎每个因子退化成**小盘暴露或行业 bet**（IVOL/MAX/STREV/动量/质押/DY 全中招）|
| D2 | **横截面 rank，不用绝对值/时序自身分位** | 重蹈 R-3a 共模问题（涨势市所有股同向）；系统已为此付出过代价 |
| D3 | **PIT 严格**：财报/事件用 `ann_date`/`f_ann_date` 非 `end_date` | 否则前视泄漏直接污染回测（SUE/accruals/asset_growth/surprise）|
| D4 | **去重**：先查现有节点，避免双计 | 3 个 NEGATIVE 全因双计（GPOA=毛利×周转、EP=peer_compare、ICIR=已有加权均值）|
| D5 | **覆盖率 gating**：稀疏因子设 confidence=0 回退"未知"，**不**用 0 注入伪信号 | 北向小盘/AH(<3%)/游资(5-20%上榜) 覆盖稀疏；系统已有"跳过零分节点"机制可复用 |
| D6 | **horizon 纪律**：季度/月频信号别塞进 short(2-4周)高权重轴 | 北向季度、股东人数季度、asset_growth 年频 → 限 long 或设信号存活期 |

## 2. 提案模型：逐轴增强（含 dp_id / 公式 / 归一 / 权重 / 条件）

### 2.1 Merit（fundamental_score）— 加"盈余质量/趋势"维度
现状：13 个**水平**指标（ROE/ROA/负债/OCF质量/毛利/周转…），无一个测**盈余的现金含量结构或趋势**。
- ✅ **Sloan 应计 BS-Accrual**（T2-2，prio high）：`L5.fina.bs_accrual` = ΔNOA/Avg_TA，负向（高应计=低质量）。字段全已 fetch，零额外 API。权重 0.10-0.15（防与 ocf_quality 双计）。
- 🟡 **Asset Growth**（T2-4，prio med）：`L5.fina.asset_growth` = 总资产 YoY，负向（过度投资）。限 **long** 权重，不污染短窗。
- 🟡 **F-Score 仅取 3 个正交子项**（T2-1）：ΔROA趋势/ΔLiquidity/ΔShares稀释——**不要整体 9 分**（6/9 与现有节点双计、二值化是信息退化）。
- ❌ **Novy-Marx GPOA**（T2-3，NEGATIVE）：= gross_margin × asset_turnover，与两现有节点 corr>0.85，纯双计。**不接**。

### 2.2 expectation_gap — 最干净的新 alpha 富矿
现状：analyst_revision/guidance_change/analyst_rating 全测"**预期形成**"，无"**业绩落地 vs 预期**"。
- ✅✅ **SUE 标准化盈余惊喜 + PEAD**（T2-5，**唯一 POSITIVE**，prio high）：`L5.fina.sue_q` = (EPS_actual − EPS_expected)/σ_8Q。20-60 日窗贴合 2-4 周甜区。**首批必做**。
- ✅ **业绩快报/预告超预期**（T2-7，prio high）：`L9.express.earnings_surprise` = tanh((express.净利 − 一致预期)/|一致预期|/0.3)。比正式财报更早。需扩 `_REALTIME_DEDUP_PRIMARY` 防与 guidance 双计。
- ✅ **分析师 EPS 修正动量 ARM**（T2-6，prio high）：`L6.priced.eps_rev_mom`（区别于现有评级计数 revision）= 60 日内各分析师 FY1 净利预测的修正幅度，≥3 分析师否则 Inactive。

### 2.3 capital_sentiment（死轴复活）— 价量异象优先于 naive 机构流
- ✅✅ **短期反转 STREV（换手调整）**（T3-1，prio high）：`L7.rev.strev_adj` = −(20日收益)/max(AvgTO,0.5)，正向（超卖=买）。**纯价量、零 PIT 风险、A 股最强 2-4 周信号**。权重≤0.08 + 过滤 ST/连板/新股 + 沪深300降权0.5。**首批必做**。
- ✅ **残差/特异动量**（T3-2，prio high）：`L7.mom.residual_momentum` = 对市场+行业回归后的残差累积(6M skip 1M)。**必须残差版**（原始动量 IC≈−0.03 有害）+ 动量崩溃保护（CSI300 年化<−15% 且近 20 日σ>25% → confidence×0.3）。
- 🟡 **行业动量**（T3-3，prio med）：`L7.ind.industry_momentum` = 申万一级 2-3 月动量(skip 1M)，截面去市场均值。机构 ETF 化驱动，贴合机构市。
- 🟡 **改造 active_inflow → CNIR 比率**（T1-3，prio med）：不新增节点，把 `tanh(main_net/50000)` 改 `tanh(cnir/0.15)`（÷成交额去规模偏误）+ 行业中性 + 市值≥50亿门槛。
- 🟡 **次级真机构信号**（覆盖-gated，辅助）：筹码集中度 CYQ（T1-6 `L7.chip.concentration`）、大宗**溢价端** only（T1-5 `L7.block.premium_signal`）、季度北向 cap-gated（T1-1 `L7.flow.hsgt_hold_chg`，仅市值>50亿）。
- ⬇️ **低优先/暂缓**：北向日频（数据停播）、融资买入动量（需改造缓存+散户属性）、游资（覆盖低、需拆游资/机构席位两节点）、股东人数（季度错配）。

### 2.4 funding_score（死轴复活）— 市场级温度计
- ✅ **融资余额变化率温度计**（T4-7 #159，prio high）：aggregator.py:1047-1055 **明确点名缺的就是这个**。双向：过热→risk，出清→capital_sentiment。市场级 + 个股级两路。

### 2.5 risk_discount — 加统计风险维度（现 9 节点全是基本面/治理风险）
- ✅ **IVOL 特异波动率/低波异象**（T3-4，prio high）：`L8.cap.rvol20`（先用 20 日实现波动率代理 IVOL，最易算），volatility_risk 轴已有路由 + 2 个死节点待激活。**首批可做**。
- 🟡 **MAX effect 极端日收益**（T3-5，prio med）：`L8.cap.max_effect` = 近 20 日 top-5 日收益均值，负向（彩票偏好溢价）。分板块标准化涨跌停上限。
- 🟡 **Amihud 非流动性**（T3-6，prio med，conf high）：`L8.cap.illiq` = |R|/成交额 月均，连续因子（区别于现有二值 liquidity_short 告警）。走 damp 平均防双重惩罚。
- 🟡 **股权质押 + 解禁压力**（T4-6，prio med）：解禁 `L8.cap.unlock_overhang`（POSITIVE，日历事件干净）优先；质押 `L8.cap.pledge_risk`（需平仓线估算+中性化）次之。

### 2.6 valuation_rerating — 已最成熟，少动
- 🟡 **AH 折价**（T4-2，prio low）：`L6.mult.ah_premium`，独占 stk_ah_comparison，但覆盖<3% + 需先写 fetch。低优先。
- 🟡 **股息率**（T4-3，prio low）：接 **capital_sentiment 非 valuation**（捕险资/社保流入，非估值折价）+ 必须 regime-gating（低利率×1.5/成长市×0.3）。
- ❌ **行业内 EP**（T4-1，NEGATIVE）：与 peer_compare(R-3b.2 已横截面 PE/PS)等价，双计会 2× 估值轴破坏阈值。**不接**（除非作 peer_compare 无池时的降级替代）。

### 2.7 聚合层 & 全局 regime（架构，谨慎）
- 🟡 **行业内中位数替换**（T4-5 Step A）：把 `_ROE_BENCH` 等全市场硬编码常数换成申万行业内中位数（R-3b.2 模式扩到 fundamental）。低成本高价值。
- 🟡 **R-7 动态 regime/beta**（T4-7 #150 货币-信用四象限 + #160 换手温度计）：放大 market_regime_beta 实现"牛市整体抬升/熊市下沉 + 固定绝对阈值"。**须 PIT 回测定 beta**（用户既定）。
- ❌ **ICIR 最优合成 / 完整 Barra WLS**（T4-4 NEGATIVE / T4-5 Step B）：3 个 base date 样本根本估不稳协方差，且系统已用覆盖率加权均值。**不做**（过拟合）。

## 3. 实施顺序（按 ROI/风险/数据洁净度分波）

- **Wave 1（首批，最干净、最高 ROI、2-4周完美贴合）**：**SUE/PEAD**（T2-5）· **IVOL**（T3-4）· **STREV**（T3-1）。三者：纯/近纯可得数据、填真缺口、零或低 PIT 风险、横截面。
- **Wave 2**：快报/预告超预期（T2-7）· ARM 修正动量（T2-6）· 残差动量（T3-2）· Amihud（T3-6）· MAX（T3-5）· 解禁压力（T4-6 解禁部分）。
- **Wave 3**：Sloan 应计（T2-2）· 行业动量（T3-3）· CNIR 改造（T1-3）· 筹码集中度（T1-6）· 大宗溢价（T1-5）· 融资温度计（T4-7 #159）· 质押（T4-6）。
- **Wave 4（架构）**：R-7 动态 regime/beta（T4-7 #150/#160）· 行业内中位数聚合（T4-5 StepA）· asset growth（T2-4）· F-Score 3 子项（T2-1）· 股息率（T4-3）· 季度北向（T1-1）· AH 折价（T4-2）。
- **丢弃**：Novy-Marx GPOA、行业内 EP、ICIR 合成（3 NEGATIVE）；北向日频、融资买入动量、游资、股东人数（naive 机构流，低优先）。

## 4. Phase 3b — 实证验证计划（下一步，仍只读/隔离）

逐因子"正面/负面"的**最强证据=实测 IC**。计划在隔离目录复刻 `pit_backtest/metrics.py` 方法（绝不碰原文件）：
- **范围**：先验 Wave 1（STREV/IVOL/SUE）——数据最易（前两者纯价量、SUE 财务）。
- **方法**：用 DockCase 缓存历史，对 universe 在若干 base date 算单因子值 → 前向 +10/+15/+20d 收益 → **rank IC + Fisher CI + 十档单调性 + 与现有 base 成分相关性**（验正交）。
- **接受标准**：IC 方向正确 + 在 2-4 周窗显著 + 与现有轴 corr<0.5（正交）+ 十档单调。
- **产出**：`03_impact_studies/3b_empirical/<factor>_ic.md` + csv。验证后把 Wave 1 升级为"实证级 POSITIVE"，再决定是否扩到 Wave 2。

> ⚠️ 全程仍**不改本项目任何文件**；3b 只读缓存数据、代码只写隔离目录。回测口径小样本（base date 少），IC 是 sanity/排序证据非 alpha 证明（沿用系统既有 caveat）。
