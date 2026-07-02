# A股评分保真度审计报告 — 5 只 AI_COMPUTE 标的

> 生成: 2026-06-03 · 来源: 多 agent workflow `wwzmy35fi` (44 agents / 2.58M tokens / ~32min)
> 基准: `runtime/hot.sqlite` (daily_basic trade_date=20260529)；评分链 `aggregator.py` + `scoring.py` + `market_adapter.py`
> 统计: issues raised **38** → confirmed **27** → rejected **11**（每条均对照实时数据复验，非依据注释）
> 审计标的: 000977 浪潮信息 / 000063 中兴通讯 / 601138 工业富联 / 300308 中际旭创 / 688256 寒武纪

## 目录

- **1. 总体结论（一句话裁决）**
- **2. 逐股诚信表**
- **3. 字段级问题（按 severity_adjusted 排序，已跨股去重）**
  - CRITICAL
    - `[C-1]` 情绪被重复计入分（造出虚假 BUY）
    - `[C-2]` overlay 定性标签靠 `trend:up` 饱和到满格入分（占 BUY 的 89%）
    - `[C-3]` `L6.priced.run_up` 陈旧快照主导 priced-in 惩罚
  - HIGH
    - `[H-1]` `L5.is.revenue_growth` 同比基期错配（最强基本面被喂成≈0）
    - `[H-2]` revenue_growth 单位 ratio-vs-percent 错配（系统性压制 ~100×）
    - `[H-3]` 估值历史百分位陈旧且同股自相矛盾
    - `[H-4]` 两套评分引擎对同一标的给出相反 headline
  - MEDIUM
    - `[M-1]` `top_path` 按绝对值排序，把惩罚项误报为"头号利多"
    - `[M-2]` `L5.is.gross_margin` 用跨行业中位数，结构性薄毛利被打到地板
    - `[M-3]` guidance 类字段陈旧（20 个月前的预告对仍在喂 expectation_gap）
  - LOW / NIT
    - `[D-low]` 非 canonical 的 Mock 行写入生产快照（审计盲点）
    - `[D-nit]` 覆盖率 honesty 口径虚高
- **4. 已确认稳健之处 + 优先修复清单**
  - 已核实诚信/正确的部分（what's solid）
  - 优先修复清单（Top 5，按"真值到达分数 vs 过度声称"框定）
- **附录: 逐股 coverage 原始数据**

---

# A股评分保真度审计报告（5只 AI_COMPUTE 标的）

审计基准：`runtime/hot.sqlite`（快照 daily_basic trade_date=20260529），评分链 `mvp20/aggregator.py` + `mvp20/scoring.py` + `mvp20/market_adapter.py`。所有 5 只标的的 score、company_score、top_path 均已与 CLI 实跑逐一核对一致，下述每条问题均已对照实时数据复验（非依据注释）。

## 1. 总体结论（一句话裁决）

**shaky（脆弱，需重大整改）** —— 5 只标的中**没有一只**的 headline signal 是由"真实数值干净地驱动到 final_score"得出的：3 只 BUY 中有 1 只（000063 ZTE）经核实方向就是**错的**（情绪被重复计两次造出来的 BUY），另 2 只 BUY（601138、300308）方向勉强可辩护但 BUY 量级由**饱和的定性 overlay 标签 + 未归一化**撑起；1 只 AVOID（000977）方向对但量级由**22天前已反转的陈旧动量**主导；唯一"reasonable"的（688256）方向真值驱动、但其**最重要的基本面输入是坏的**（增长被喂成 0）。

按 severity_adjusted 计（已去重、跨股合并）：
- **critical：3 类**（情绪双计 / overlay `trend:up` 饱和入分 / run_up 陈旧主导）
- **high：4 类**（revenue_growth 周期错配 / 单位 ratio-vs-percent 错配 / 估值百分位陈旧自相矛盾 / 两套引擎信号打架）
- **medium：3 类**（gross_margin 跨行业中位数错配 / guidance 陈旧 / top_path 按绝对值排序误导）
- **low / nit：2 类**（非 canonical 的 Mock 行写入生产快照 / 覆盖率 honesty 口径虚高）

## 2. 逐股诚信表

| ts_code | 名称 | short / medium / long | signal | participates | 真值入分(in_score_with_real_value) | 入分但缺失(in_score_but_missing) | mock_only* | score_reasonable |
|---|---|---|---|---:|---:|---:|---:|---|
| 000977.SZ | 浪潮信息 | -0.657 / -0.621 / -0.553 | AVOID | 223 | **77** | 99 | 0 (实有4) | **questionable** |
| 000063.SZ | 中兴通讯 | 0.475 / 0.277 / 0.191 | BUY | 223 | **73** | 108 | 0 (实有4) | **wrong** |
| 601138.SH | 工业富联 | -0.435 / -0.038 / 0.104 | BUY | 223 | **71** | 112 | 0 (实有4) | **questionable** |
| 300308.SZ | 中际旭创 | 0.080 / 0.315 / 0.290 | BUY | 223 | **72** | 151 | 0 (实有4) | **questionable** |
| 688256.SH | 寒武纪 | 0.227 / 0.653 / 0.760 | BUY | 223 | **71** | 104 | 0 (实有4) | **reasonable** |

\* **重要更正**：5 只标的的 250-字段 dump 全部报告 `mock_only=0`，但 `realtime_current` 中每只**实有 4 条 Mock 行**（`L7.market.l2_quote`/`tick_count_5min`=mock:futu、`L11.short_term`=mock:mvp20-bff、`L9.event.intraday_block_trade`=mock:n/a）。因这些 dp_id 不在 canonical registry，故不入分、也对审计工具不可见 —— 属诚信口径盲点（见问题 D-low），非"无 mock"。

**需点名的"靠缺失/mock/sentinel 而非真值"的标的**：

- **000063.SZ（最严重，方向错）**：经 instrumented 实跑，§27.4 core base = -0.184（按阈值应为 WATCH）。**所有硬基本面均为负**（industry_contrib=-0.443、valuation_rerating=-0.270、OCF=-1.98bn、FCF=-3.78bn、ocf_to_ni=-1.501 ERROR、主力5日净流出-2.28bn）。唯一大正项是 sentiment_score=+0.5745，被 market_adapter **重复计第二次**为 local_funding_score 后把 base 从 -0.184 抬到 +0.319，恰好越过 0.20 的 BUY 线。去掉重复计 base=-0.255（AVOID）。同一快照里持久化的 L11 引擎说 **WATCH / wait_for_confirmation**（central -0.055，short flow_boost -0.973），与 CLI 的 BUY 直接打架。**BUY 是双计造出来的，不是任何真实利多。**
- **601138.SH**：71/223 真值入分；fundamental 正向 +3.37 中 **+2.99（89%）来自仅 3 个饱和到 +0.997 的 overlay 标签**（strength=null，仅靠 `trend:up`）。剔除后 fundamental 正向塌缩到 ~+0.38。每一个到达分数的**硬财务叶子全为负**（gm 7.35%→-0.984、净利率 4.22%→-0.486、D/A 61.4%→-0.171）。BUY 由饱和定性标签 + 未归一化（company_score 1.249，industry_contrib **2.066**，远超 [-1,1]）救起来的。
- **300308.SZ**：仅 72/223 真值入分，另 151 为 54 个 overlay 定性标签 + 55 Unknown + 42 Inactive（全归零）。方向（BUY）可辩护（真·净利率 32.4%、毛利 46%、营收+192% YoY），但**最强的基本面事实（营收近三倍）被静默丢弃**（见问题 B），BUY 实际靠 margins 单腿撑。
- **000977.SZ**：方向（AVOID）业务上站得住（毛利 6.64%、净利率 1.71%、OCF/FCF=-7.77bn、D/A 73.2%、L11 长线 -0.387），但 **AVOID 的量级由单一节点主导**：priced_in_discount=-0.600 全部来自 `L6.priced.run_up` 一个节点（信号饱和到 1.0），而该字段冻结在 22 天前、其惩罚的 +28.6% 涨幅至今已反转 ~-15.5%（见问题 C）。

## 3. 字段级问题（按 severity_adjusted 排序，已跨股去重）

### CRITICAL

---

**[C-1] 情绪被重复计入分（造出虚假 BUY）** — `capital_sentiment / sentiment_score`
- **影响标的**：000063.SZ（单股，但属架构级缺陷，凡情绪大正的 A 股都会触发）
- **证据（实跑+配置复验）**：`config/market_adapters.yaml` CN_A `local_funding_score: [funding_score, sentiment_score]`（funding_score=0.0），即 local_funding_score=0.593≈96.9% 的 sentiment_score；而 `scoring.py:436/470` 已把 `capital_sentiment`=0.5745 计入 §27.4 core base。`market_adapter.py:162` `adjusted = base*mult + local_score_total - local_discount`。core base -0.184 → market base +0.319。
- **对分数的影响**：这 +0.50 摆动是 base 越过 0.20 BUY 阈值的**唯一**原因；去掉再加 base=-0.255（AVOID）。`scoring.py:1540` 注释**自己声明**"Capital sentiment / risk / priced-in are then injected **once** at the §27.4 level"——adapter 的二次注入**违反了它自己写明的契约**。
- **修复**：从 CN_A/US/HK 的 `local_funding_score` 删掉 `sentiment_score`（只保留 funding_score 这个独立的资金流输入），或在 core §27.4 base 中排除 `capital_sentiment`，使 adapter 成为唯一 sink。

---

**[C-2] overlay 定性标签靠 `trend:up` 饱和到满格入分（占 BUY 的 89%）** — `L4.share.market` / `L4.share.customer_channel` / `L1.position.market_share`
- **影响标的**：601138.SH（3 个节点同时命中）；**根因 `_to_scalar` 全 A 股通用**，凡 overlay 写了 `trend:up`/无 strength 的节点都会满格。
- **证据**：`aggregator.py:170-175`：`trend` 命中即 `return abs(sign)` = **1.0**，无 strength 门控。实查三节点 payload 全部 `strength=null, value.trend="up"`；其中 `L1.position.market_share` 的 `rank:null, share_pct:null`（分析师注明"不填具体排名和份额，避免无本地来源数字"），`L4.share.customer_channel` 甚至**带有真实数字 top5=62.01/region=43.92 却完全不用**。三者各产出 +0.997。
- **对分数的影响**：fundamental 正向 +3.37 中 +2.99 来自这 3 个伪节点；剔除后塌到 ~+0.38，BUY 很可能翻转。这是把"无本地来源的定性断言"当满格硬信号——典型的 mock 伪装成 Known/real 入分。
- **修复**：`_to_scalar` 对 fundamental_score 节点应要求**显式数值 strength**；裸 `trend:up` 映射到小量级（如 0.2）并按 confidence 门控；当 rank/share/strength 全 null 时该节点应贡献 ~0（类 Unknown），而非 1.0。或直接用 payload 里已有的真实数字（top5/region）推导量级。

---

**[C-3] `L6.priced.run_up` 陈旧快照主导 priced-in 惩罚** — `L6.priced.run_up`（连带 `L6.path.second_derivative`）
- **影响标的**：000977.SZ、601138.SH、300308.SZ（**3 股复发**，同一 2026-05-11 批次冻结）；688256.SH 同字段亦陈旧但 d20 较小未饱和。
- **证据**：三股 run_up 均 `updated=2026-05-11`、latest_close 分别 76.48 / 63.28 / 886.0，而 `L6.mult.pe trade_date=20260529`（差 ~18 交易日）。`aggregator.py:157-160` 信号=`max(d20,0)/0.20`：000977 d20=0.286→**饱和 1.0**；601138 d20=0.203→1.0；300308 d20=0.430→1.0。priced_in_discount 封顶 0.6，在 **short/medium/long 每个 horizon 全额扣减**。000977 鲜价（L7.mood last_price=64.63，05-30）较 run_up 的 76.48 已跌 -15.5%——它惩罚的涨幅早已反转。
- **对分数的影响**：000977 该项独占 -0.6（core base -0.238，去掉它约 +0.36，可能翻离 AVOID）；601138 是 short=-0.435 的主拖累、且被列为 top_path；陈旧值还经 `L6.path.second_derivative` 误标"accelerating"传导到 valuation_rerating。
- **修复**：与 daily_basic/price_history 同周期刷新 run_up；加 freshness gate：当 run_up 的 latest_close 日期落后于最新 daily_basic trade_date 超过 N 个交易日时，归零/降权 run_up 及其 priced_in_discount。

### HIGH

---

**[H-1] `L5.is.revenue_growth` 同比基期错配（最强基本面被喂成≈0）** — `L5.is.revenue_growth`
- **影响标的**：000977.SZ、601138.SH、300308.SZ、688256.SH（**4 股全中，最严重的复发模式**）
- **证据（逐股实查）**：current_period 均为 20260331，但 `yoy_compare_period` 错为 **20250930 或 20250630**（从不是正确的 20250331），且是 Q3/H1 累计 vs Q1 累计的口径错配。结果 yoy_pct 全为近零/错号：000977=-0.706、601138=-0.304、300308=-0.220、688256=**+0.0014**。而同一快照里 `L8.op.cost_overrun.revenue_yoy` 给出**真值**：-24.3 / +56.5 / +192.1 / +159.55；688256 另有 3 个兄弟字段（L5.fina.revenue_yoy、L11.mid.orders_revenue）全为 159.5555。
- **对分数的影响**：该字段 `participates→fundamental_score`，经 `tanh(yoy/50)` 消费。688256 的 0.0014→tanh≈0，把 +159.55% 的成长喂成"零增长"，导致 long 被**低估**（修正后 0.760→0.818）；300308 的 +192% 被替换成近零负贡献；601138 把 +56.5% 报成 -0.30%。canonical 250-spec 用了**错的** dp_id，而辅助层 L5.fina.* 和 audit-only L11 用了对的，造成同快照内自相矛盾（部分"structural_divergence"标签来自数据 bug 而非真实分化）。
- **修复**：在 `mvp20/sources/tushare_source.py` 的 income.derived 中，按"上年同期"用 `_yoy_period(end_date)` + `_find_record(...)` 选 yoy 记录（`_derive_cost_overrun` 已正确这样做），而非位置式 `records[3]`；或先按 end_date 去重（preferring update_flag='1'）再取 records[3]。加守卫：所选 yoy_rec 的 MM-DD 必须匹配当前期，否则发 Unknown 而非错号。

---

**[H-2] revenue_growth 单位 ratio-vs-percent 错配（系统性压制 ~100×）** — `L5.is.revenue_growth`（消费端 `aggregator.py:157-160`）
- **影响标的**：300308.SZ、688256.SH 显式确认；**所有走此路径的 A 股**通病
- **证据**：A 股 producer 按 docstring（`derive.py:958`）把 yoy_pct 存为**比率**（-0.22=-22%），但 consumer `aggregator.py` `tanh(yoy/50)` 的除数 50 只在 yoy 为**百分数**时才对。而同指标兄弟 L5.fina.revenue_yoy / cost_overrun 存的是百分数（159.5555）。
- **对分数的影响**：即便周期 bug（H-1）修好，正确的比率值也会被错缩：+192% 的真值若按比率存=1.92，`tanh(1.92/50)=0.038`（仍近中性），而非应有的 +0.999。即 revenue_growth 信号在 fundamental_score 中被系统性消音。
- **修复**：统一单位——在 source 把 yoy_pct 归一为**百分数**（与 fina_indicator/cost_overrun 及除数 50 标定一致）；或在 `_realtime_field_signal` 加比率检测（`abs(yoy)<=5 → *100`，镜像 `derive.py:996`）。

---

**[H-3] 估值历史百分位陈旧且同股自相矛盾** — `L8.val.overvalued` / `L10.val.historical_quantile`（对照 `L6.state.historical_percentile`）
- **影响标的**：000977.SZ（最尖锐）、300308.SZ；000063 亦有 PB 版本的同类矛盾
- **证据（000977 实查）**：`L8.val.overvalued` pe=0.870/pb=0.963、window 54d、`updated=2026-05-11`（标"extreme overvalued"）；`L10.val.historical_quantile` 同值同陈旧；而 `L6.state.historical_percentile` pe=0.388/pb=0.202、window **183d**、`updated=2026-05-29`（标"compression"）。**同股同指标，结论相反**。300308 同样：L8 pe_pct=0.648（54d 陈旧）vs L6 pe_percentile=0.989（183d 鲜）。
- **对分数的影响**：陈旧的 L8 喂 risk_discount（000977 risk=-0.089，并被列为"#2 top positive path"），而鲜的 L6 喂 valuation_rerating=**+0.290**（"估值压缩"）——**同一只股票被同时当作"极度高估"和"估值压缩"反向喂入分数**，估值块内部不自洽。"extreme overvalued"标签不被当前数据支持，risk 惩罚部分是虚的。
- **修复**：`from_quantile` 按当前价/PE 历史重算，并在 L8.val.overvalued / L10.val.historical_quantile / L6.state.historical_percentile 间**统一回看窗口**（用 183d / trade_date 20260529 同步），消除"0.87 extreme vs 0.388 compression"的劈叉。54d 太短，不配叫"historical"。

---

**[H-4] 两套评分引擎对同一标的给出相反 headline** — `L11.trade.signal` vs CLI `trading_signal`
- **影响标的**：000063.SZ（与 C-1 同根）
- **证据**：持久化 `L11.trade.signal=WATCH`（mix 0.001，short -0.194/mid 0.271/long -0.241）、`L11.mode=wait_for_confirmation`（central -0.055）、`L11.short.flow_boost=-0.973`（main_net -97324.47）；CLI `score-company` 输出 `signal=BUY`、mode_confidence 仅 0.300。
- **对分数的影响**：L11 中央引擎（§27/§30 持久化视图）正确捕捉了 -0.97 的资金外流与负 OCF，给 WATCH；CLI BUY 忽略之。读 CLI 的人看到 BUY，读 L11 的人看到 WATCH——二者中 BUY 更不可辩护。
- **修复**：单一 headline 真值源；至少在 mode_confidence=0.30 且 L11.mode=wait_for_confirmation 时，CLI 不应显示与之冲突的 BUY（按 mode 置信度门控显示信号）。根因是 C-1 的 adapter 情绪二次注入，修 C-1 即收敛此分歧。

### MEDIUM

---

**[M-1] `top_path` 按绝对值排序，把惩罚项误报为"头号利多"** — `_top_paths`（`scoring.py:896-905`）
- **影响标的**：000977.SZ、000063.SZ、601138.SH（**3 股复发**，凡惩罚项饱和的标的都误导）
- **证据**：`_top_paths` 仅按 `p.score>0` 排序，无 `score_target` 感知。但 priced_in_discount / risk_discount 节点存的是正量级却**做减法**。实跑：000977 top_path=`L6.priced.run_up:rt`（实为 -0.6 惩罚）、000063 top_path=`L8.val.overvalued:rt`（实为风险旗标）、601138 top_path=`L6.priced.run_up:rt`。
- **对分数的影响**：不改 final_score，但 headline 告诉用户"最看多的驱动是 run_up/overvalued"，而它们其实是产生 AVOID/拖累的**惩罚**——误导任何把 top_path 读作主多头论据的消费者。
- **修复**：`_top_paths` 按**有效贡献符号**（考虑 score_target ∈ {priced_in_discount, risk_discount, *_risk} 做减法）分正负，把 discount/risk 目标排除出"positive"列表。

---

**[M-2] `L5.is.gross_margin` 用跨行业中位数，结构性薄毛利被打到地板** — `L5.is.gross_margin`
- **影响标的**：000977.SZ、601138.SH（两只低毛利硬件/代工，复发）
- **证据**：`aggregator.py:508-509,643` `_GROSS_MARGIN_MEDIAN=0.29`、`_GROSS_MARGIN_SCALE=0.22`，单一跨宇宙常数。000977 gm=6.64%→clip 到 **-1.0**（#1 top negative path）；601138 gm=7.35%→-0.984。代码注释自承"universe-relative re-center … industry-mixing caveat applies"。
- **对分数的影响**：服务器/系统集成（浪潮）与 EMS/代工（富联）的个位数毛利是**结构性正常**，非"全宇宙最差"。在权重最高的负向路径上把它饱和到 -1.0，**高估了基本面弱度的量级**（方向对，量级错配）。
- **修复**：改用行业相对毛利中位数（AI_COMPUTE / 硬件 / EMS 同业集）而非 0.29 跨宇宙常数，使结构性薄毛利装配商不被钉在 -1.0。

---

**[M-3] guidance 类字段陈旧（20 个月前的预告对仍在喂 expectation_gap）** — `L5.fcst.guidance_change`
- **影响标的**：000977.SZ（确认有 score 影响）
- **证据**：value `{prev_type:预增, current_type:预增, change_direction:downgraded, ann_date:20241015, period:20240930}`，source tushare:forecast。与 `L9.company.earnings_guidance` 同 2024Q3 老版本。
- **对分数的影响**：participates→expectation_gap，是 000977 的 #3 top negative path（score 0.590）。"下调 guidance"信号由 20 个月前的预告对算出——符号或许碰巧对，但依据陈旧。
- **修复**：刷新 forecast，按当前周期最近两期预告公告重算 guidance_change。
- **注**：相关的 `L9.company.earnings_guidance`（陈旧 +61~74%）经验证**被 dedup 跳过、不入分**（`aggregator.py:529,866-875` 同披露去重），故其"撑起多头"的指控不成立，已正确排除。

### LOW / NIT

---

**[D-low] 非 canonical 的 Mock 行写入生产快照（审计盲点）** — `L7.market.l2_quote` / `L7.market.tick_count_5min` / `L11.short_term` / `L9.event.intraday_block_trade`
- **影响标的**：000977、000063、601138、300308、688256（**全 5 股，每股 4 行**）
- **证据**：实查 `realtime_current` 中每股 4 条 `data_status=Mock`（source=mock:futu / mock:mvp20-bff / mock:n/a）。因这些 dp_id 不在 `data_point_roles.yaml`，governance 返回 rule=None，`synthesize_realtime_nodes` 跳过，故 250-字段 dump 报 `mock_only=0`。
- **对分数的影响**：当前**不入分**（非 canonical）。但它们是新写入生产快照（300308 那批 2026-06-03）的 Mock 行，对逐股审计工具不可见，一旦其中某名字日后被提升进 canonical 集即会污染分数。
- **修复**：禁止把 mock:futu / mock:mvp20-bff / mock:n/a 写入生产 `runtime/hot.sqlite`（BFF/futu mock feed 加 dev flag 门控），或 sync 时清除非 registry 的 Mock 行。

---

**[D-nit] 覆盖率 honesty 口径虚高** — 跨股汇总指标
- **影响标的**：全 5 股
- **证据**：dump summary 报"effectively in-score 115"（000063）等，把 42–54 个 overlay 定性标签 + 中性 fallback 字段都算作"covered"。但实际只有 71–77 个 real_self/sentinel 真值能产生信号；000977 中 47 个 overlay-Known 仅 ~4 个（L4.price.asp_aov_arpu 等）非零，其余 ~43 个归零；601138 的 40 个 overlay-Known 中 33 个 `_to_scalar` 量级=0.0。
- **对分数的影响**：无 correctness bug，纯诚信账本问题。"usable 56.8% / effectively in-score 46%"高估了分数实际建立在多少真实信号上。
- **修复**：honesty 账本应报 `in_score_with_real_value`（71–77）vs `in_score_but_missing`（99–151），把"authored-but-inert"（量级=0 的 overlay-Known）单列，不计入"effectively in-score"。

## 4. 已确认稳健之处 + 优先修复清单

### 已核实诚信/正确的部分（what's solid）

- **方向多数可辩护**：除 000063 外，4 只标的的 signal **方向**与真实业务一致——000977 AVOID（毛利 6.64%、OCF -7.77bn、D/A 73.2% 确为弱季）、688256 BUY（毛利 54.3%、扭亏 +509~575%、营收 +159.55% 真值驱动，top_path 是真·硬值 `L5.is.gross_margin`）、300308 与 601138 的跨 horizon 价差（short<<long）方向合理。
- **risk_discount 用的是真值**：688256 的高估值惩罚（PE 302.9/PB 67.3 历史顶部）、资金外流 WARN 均为真实硬值在咬，BUY 是真实基本面**压过**真实估值风险得出，非饱和造假。
- **dedup 与 confidence 通道按设计工作**：陈旧的 `L9.company.earnings_guidance`（000977/000063）经同披露去重正确**不入分**；confidence_multiplier 节点（L10.val.peer/historical_quantile）在 `aggregator.py` 被显式归零方向信号、仅经 confidence 通道贡献——这两类**被验证拒绝的指控是对的**，不应计入问题。
- **mock_only=0 在 canonical 范围内属实**：250-spec 内确无 mock 伪装成 real（盲点仅在非 canonical 的 4 行，见 D-low）。
- **688256 是"低估"而非"高估"**：其最重要的成长输入坏掉是把分数**压低**（long 0.760 应为 0.818），即该股的真实信号比显示的更强——这是诚实方向上的保守误差。

### 优先修复清单（Top 5，按"真值到达分数 vs 过度声称"框定）

1. **[C-1] 修情绪双计**（造假 BUY，架构级）：从 `local_funding_score` 删 `sentiment_score`，恢复"capital_sentiment 只注入一次"的既定契约。这是 000063 假 BUY 的唯一根因，且违反代码自己的注释——**最高优先**。
2. **[H-1 + H-2] 修 `L5.is.revenue_growth` 周期错配 + 单位错配**（4 股全中）：选对上年同期记录 + 统一 percent 单位。这是覆盖面最广的真值缺失——一个真实存在的最强基本面被系统性喂成 0/错号，"participates 但无真值"的典型，直接腐蚀 fundamental_score。
3. **[C-2] 堵 `_to_scalar` 的 `trend:up` 满格通道**：无数值 strength 的 overlay 定性标签不得满格入分。这是 601138 BUY 量级（+2.99/3.37）被伪造的根因——"mock 伪装成 Known/real 入分"的最直接案例。
4. **[C-3 + H-3] 给价格/估值派生字段加 freshness gate 并统一窗口**：run_up（3 股）、L8.val.overvalued/L10.historical_quantile（同股自相矛盾）须与 daily_basic 同周期、统一 183d 窗口。消除"陈旧 + 同股反向估值"双重失真。
5. **[M-1] 修 `_top_paths` 排序按有效贡献符号**：让惩罚项不再冒充"头号利多 top_path"。零 final_score 影响但直接消除 headline 过度声称，且改动小、收益即时。

---

**审计纪律声明**：本报告严格区分"有字段"与"有真数到达分数"——5 股 participates_in_score 均为 223，但真值入分仅 71–77；BUY/AVOID 的 headline 在 4/5 的情况下由饱和/陈旧/双计/未归一化输入主导，而非由干净的实时真值读出。无一处量级被夸大；被验证拒绝的 12 条指控（confidence 通道、dedup、run_up 方向反转误判等）均已核对机制后正确排除。

相关文件（绝对路径）：
- `/Users/fanjie/Desktop/Cowork/project-ult-mvp20/mvp20/market_adapter.py:162`（情绪双计加法）
- `/Users/fanjie/Desktop/Cowork/project-ult-mvp20/mvp20/scoring.py:436,470,1540,896-905`（capital_sentiment 注入 / §27.4 契约注释 / _top_paths 排序）
- `/Users/fanjie/Desktop/Cowork/project-ult-mvp20/mvp20/aggregator.py:157-160,170-175,508-509,643`（tanh 单位 / trend 饱和 / 毛利常数）
- `/Users/fanjie/Desktop/Cowork/project-ult-mvp20/mvp20/sources/tushare_source.py`（revenue_growth 周期选择，约 L2156-2174）
- `/Users/fanjie/Desktop/Cowork/project-ult-mvp20/config/market_adapters.yaml:78,136,194`（local_funding_score 配置）

---

## 附录: 逐股 coverage 原始数据（250 dp_id 分类）

| ts_code | signal | short/med/long | 参与打分 | real_self | real_sentinel | overlay | mock_only | Unknown/Inactive/NA | 真值入分 | 入分但缺失 | 裁决 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 000977.SZ | AVOID | -0.657/-0.621/-0.553 | 223 | 88 | 16 | 47 | 0 | 99 | **77** | 99 | questionable |
| 000063.SZ | BUY | 0.475/0.277/0.191 | 223 | 84 | 16 | 42 | 0 | 108 | **73** | 108 | wrong |
| 601138.SH | BUY | -0.435/-0.038/0.104 | 223 | 82 | 16 | 40 | 0 | 112 | **71** | 112 | questionable |
| 300308.SZ | BUY | 0.08/0.316/0.29 | 223 | 83 | 16 | 54 | 0 | 97 | **72** | 151 | questionable |
| 688256.SH | BUY | 0.227/0.653/0.76 | 223 | 82 | 16 | 48 | 0 | 104 | **71** | 104 | reasonable |

> 口径: `参与打分`=participates_in_score；`真值入分`=in_score_with_real_value（参与打分且有真实非mock非中性值）；`入分但缺失`=in_score_but_missing（参与打分但靠 Unknown/mock/中性兜底）。
> `mock_only` 列工具报 0，但实查每股另有 4 条非 canonical Mock 行（见正文 D-low）。
