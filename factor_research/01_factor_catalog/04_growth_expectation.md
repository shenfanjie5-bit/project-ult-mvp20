# 因子族：growth_expectation

> 成长/盈利预期因子族对本系统的核心价值：该族直接填补 expectation_gap 轴，是系统两周窗口信号最强的基本面来源。最值得优先接入的三个因子：① FY1_EPS_REV_MOM（分析师盈利修正动量）——华泰金工 2024 实证月度 RankIC 3.99%、年化超额 9.55%，tushare report_rc 直接可算，GREEN；② SUE_Q（单季度标准化盈利惊喜）——国盛量化 PEAD.notice 验证 IC 3.0%、ICIR 2.89，60 日 PEAD 超额 4.1%，forecast + express + fina_indicator 可算，GREEN；③ FORECAST_SURPRISE（盈利预告超预期）——bigquant 实证预告超预期 60 日超额 5.4%，forecast 可算，YELLOW（覆盖率仅 20-46%）。三者合成后与价量因子相关性 <0.10，具有独立 Alpha。

共 15 条。


## 1. SUE_Q
**别名**：单季度标准化盈利惊喜 / Standardized Unexpected Earnings (Quarterly)  
**映射**：`expectation_gap` · **可行性**：GREEN · **把握**：high · **周期**：事件后 20-60 个交易日；与本系统 2-4 周窗口高度吻合。季频信号，持有 1-3 月。 · **方向**：高 SUE_Q → 看多（正惊喜持续漂移）；低 SUE_Q → 看空（负惊喜持续下跌）

- **定义/公式**：SUE_Q = (EPS_actual_q − EPS_expected_q) / σ(EPS_surprise, trailing 8Q)
其中：EPS_actual_q = 当季实际归母净利润(从 fina_indicator 单季度字段取) / 当季平均总股本；EPS_expected_q = 基于过去同期的随机游走预期，即 EPS_actual_{q−4}；σ = 过去 8 个季度盈利惊喜的滚动标准差（若分析师一致预期可得，则用一致预期 EPS 替代随机游走预期，即 report_rc 的 eps 均值）。截面标准化后按分位数排名。
- **逻辑**：Bernard & Thomas (1989) 经典 PEAD 理论：市场对盈利信息存在系统性低估反应，导致正盈利惊喜后持续漂移。A 股散户/机构两元结构使信息消化更慢，PEAD 比美股更强。
- **数据输入**：单季度归母净利润(fina_indicator: q_profit/profit_dedt), 分析师一致预期 EPS(report_rc: eps), 总股本(daily_basic: total_share)
- **tushare 端点**：fina_indicator, report_rc, daily_basic
- **A股证据/陷阱**：国盛量化 PEAD.notice(2022)：p_score 因子月度 IC 均值 3.0%、ICIR 2.89；盈余惊喜事件后 60 日超额 4.1%（中证 500 基准）；bigquant 实证预告超预期策略年化超额 23.96%。陷阱：①财报公告日次日常触碰涨跌停板，需在公告后第 2 交易日建仓（剔除涨跌停）；②PIT 严格要求：季报披露窗口 4 月末/8 月末/10 月末，需按实际披露日期而非会计期末录入；③ST/退市股票剔除；④小市值偏向需中性化。
- **机构相关度**：机构为主市场中 PEAD 仍显著——研究表明机构投资者反而能从零售投资者低估反应中获利(SSRN 4589824 A 股 2000-2020 数据)；北向资金流入与正 SUE 高度协同。
- **出处**：Bernard & Thomas (1989) JFE, 国盛量化 PEAD.notice 研报 2022-07, bigquant 超预期投资全攻略

## 2. FY1_EPS_REV_MOM
**别名**：分析师盈利修正动量 / Analyst EPS Revision Momentum  
**映射**：`expectation_gap` · **可行性**：GREEN · **把握**：high · **周期**：20-60 个交易日；对本系统 2-4 周窗口有效。调仓频率可双周至月频。 · **方向**：高正修正 → 看多；大幅下调 → 看空

- **定义/公式**：FY1_EPS_REV_MOM = Σ_{i∈analysts} w_i × [(EPS_{i,t} − EPS_{i,t−1}) / |EPS_{i,t−1}|]
其中对股票 s 在过去 N 天（N=20 或 60）内所有分析师的 FY1 净利润预测修正求加权平均；w_i 可等权或按分析师历史准确度加权。
改进版（华泰 2024）：先对每位分析师的原始修正幅度做横截面 Winsorize（1-99%），再取 zscore 后在股票层面等权聚合；然后通过对 12M 价格动量做线性回归，取残差去掉惯性污染。
- **逻辑**：Chan et al. (1996)：分析师修正后市场存在价格漂移，属于有限注意力下的慢扩散效应。A 股中机构同质化分析师报告存在「羊群效应」，首次修正方向具有极强信息含量；后续跟风修正会摊薄，故用 20 日短窗口捕捉先行修正。
- **数据输入**：分析师 FY1 净利润预测(report_rc: net_profit/eps), 修正时间戳(report_rc: report_date), 分析师机构标识(report_rc: org_name/analyst)
- **tushare 端点**：report_rc
- **A股证据/陷阱**：华泰金工 2024-12 研报：分析师盈利修正因子月度 RankIC 均值 3.99%，TOP 组合年化超额 9.55%（2011-2024 回测）；与 AI 量价因子相关性仅 0.03。陷阱：①近 50% A 股无分析师覆盖，对小市值/北交所覆盖稀疏；②A 股分析师集中于季报前后密集发布，月中信号稀薄，建议用 60 日滚动而非单日截面；③需剔除仅有 1 名分析师覆盖的股票（个人意见偏差过大）；④行业中性化必要——不同行业覆盖深度差异大。
- **机构相关度**：直接反映机构卖方研究员的预期变化，是机构资金流入的领先指标；华泰综合因子（含修正）在沪深 300 增强组合中 IR=2.02，中证 1000 IR=4.44。
- **出处**：华泰金工 2024-12《分析师预期类因子初探》, Chan, Jegadeesh & Lakonishok (1996) JF

## 3. ANALYST_RATING_REV
**别名**：分析师评级修正因子 / Analyst Rating Revision  
**映射**：`expectation_gap` · **可行性**：GREEN · **把握**：med · **周期**：事件驱动型，评级发布后 10-30 交易日有效；本系统 2-4 周窗口内显著。 · **方向**：评级上调/高值 → 看多；评级下调/低值 → 看空

- **定义/公式**：RATING_SCORE_PREV = 过去 N 日内（N=30）每位分析师评级数值（买入=5, 增持=4, 中性=3, 减持=2, 卖出=1）的加权平均；
RATING_SCORE_CUR = 近 10 日评级均值；
ANALYST_RATING_REV = (RATING_SCORE_CUR − RATING_SCORE_PREV) / RATING_SCORE_PREV
改进版（华泰 2024）：筛选历史上对「小市值、反转、低估值、高 ROE」四类异象有捕捉能力的分析师子集，只取其评级计算；去除全市场系统性评级漂移偏差。
- **逻辑**：评级上调包含分析师更新基本面判断的信号；「优质分析师」筛选可降低跟风评级噪声，保留有信息量的修正。机构客户对特定分析师评级有跟踪习惯，形成短期资金流。
- **数据输入**：分析师评级(report_rc: rating), 报告日期(report_rc: report_date), 分析师机构(report_rc: org_name/analyst)
- **tushare 端点**：report_rc
- **A股证据/陷阱**：华泰金工 2024：改进分析师评级因子月度 RankIC 均值 2.26%（普通版 1.85%），TOP 组合年化超额 5.17%。中信建投 2022 研报：EPS 修正因子优于评级修正因子，评级修正因子在 A 股存在「买入扎堆」偏差（超 80% 研报为买入评级），信噪比低。陷阱：①A 股卖方评级严重右偏，需做分析师内部标准化；②评级发布日次日若遇涨跌停需推迟建仓；③ST 股剔除。
- **机构相关度**：评级变化直接触发机构持仓调整，华泰综合三因子（含评级）在增强组合中 IR 全面提升。
- **出处**：华泰金工 2024-12《分析师预期类因子初探》, 中信建投因子深度研究系列 13

## 4. TARGET_PRICE_UPSIDE
**别名**：分析师目标价隐含上涨空间 / Implied Upside from Target Price  
**映射**：`valuation_rerating` · **可行性**：GREEN · **把握**：med · **周期**：中期信号（1-3 月）；目标价通常设 12M 期限，但短期价格向目标价靠拢的漂移发生在 2-8 周。 · **方向**：高隐含上涨空间（正值大）→ 看多；隐含下行（负值）→ 看空

- **定义/公式**：TP_UPSIDE_i = median(TP_{analyst,j} over past 90d) / P_{current} − 1
其中 TP_{analyst,j} 为第 j 位分析师最新目标价（12M）；P_{current} 为当前收盘价。
修正版：TP_UPSIDE_ADJ = (TP_UPSIDE_i − median_sector_TP_UPSIDE) / std_sector_TP_UPSIDE
（行业内标准化，去除行业系统性乐观偏差）。
- **逻辑**：目标价综合分析师 DCF/倍数估值预期，直接反映机构预期与当前价格的差距。A 股中机构配置以「买入+目标价」模式驱动资金入场，隐含空间高的股票吸引 QFII/北向资金关注。
- **数据输入**：分析师目标价(report_rc: tp_max/tp_min), 当前股价(daily: close), 行业分类(index_member_all)
- **tushare 端点**：report_rc, daily, index_member_all
- **A股证据/陷阱**：中信建投 2022：目标价修正因子效力弱于 EPS 修正，因 A 股目标价常跟随股价上调（锚定效应）；建议用行业内标准化抵消行业乐观偏差；报告覆盖率较低（约 50% A 股无目标价）。华泰 2024：目标价因子作为综合因子组成部分，贡献独立 IC。陷阱：①目标价存在显著系统性上偏；②目标价更新频率低（多为季报后），对高频调仓不友好；③需剔除 180 天未更新的「过期目标价」。
- **机构相关度**：目标价驱动机构委托单；外资机构（北向）对头部覆盖分析师目标价高度敏感。
- **出处**：中信建投因子深度研究系列 13(2022), 华泰金工 2024-12《分析师预期类因子初探》

## 5. EPS_DISPERSION
**别名**：分析师预测分歧度 / Analyst EPS Forecast Dispersion  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：中期信号（1-3 月）；适合作为风险折扣叠加在 expectation_gap 上。 · **方向**：高分歧度 → 风险折扣（看空方向叠加使用）；分歧度突破高位后下行 → 看多

- **定义/公式**：EPS_DISP = std(EPS_{analyst,j,FY1}) / |mean(EPS_{analyst,j,FY1})|
（变异系数，对不同盈利绝对值规模做标准化）
或 EPS_DISP_NORM = EPS_DISP − median_sector(EPS_DISP)（行业内去中心化）
作为风险折扣因子时，高分歧度 → 看空（风险溢价信号）；
作为信息扩散加速信号时，分歧度「高位突破后下降」→ 看多（分歧收敛）。
- **逻辑**：Diether, Malloy & Scherbina (2002)：高分歧度对应卖空约束下的悲观预期压制，后续高估值修正。中国市场卖空更受限，分歧度信号更强。另一逻辑：分歧收敛时机构达成共识，形成集中买入。
- **数据输入**：分析师 FY1 净利润/EPS 预测(report_rc: net_profit/eps), 分析师数量(report_rc: analyst)
- **tushare 端点**：report_rc
- **A股证据/陷阱**：CSDN 2023：提供 A 股 2001-2023 分析师预测分歧度数据与计算代码；华泰 2024 研报提及「分析师因子离散度高位突破信号展现一致正向预测能力」。陷阱：①覆盖不足股票（<3 名分析师）分歧度估计噪声大，需最低 N=3 截断；②行业差异显著（周期行业分歧天然高于消费行业），必须行业内标准化；③2024 年部分传统分析师预期因子失效，需结合分歧度变化趋势而非绝对值。
- **机构相关度**：机构一致买入的前提是预期收敛；北向资金更倾向持有低分歧度股票（信息透明度高）。
- **出处**：Diether, Malloy & Scherbina (2002) JF, 华泰金工 2024-12《分析师预期类因子初探》

## 6. FORECAST_SURPRISE
**别名**：盈利预告超预期 / Earnings Pre-announcement Surprise  
**映射**：`expectation_gap` · **可行性**：YELLOW · **把握**：high · **周期**：事件驱动，预告发布后 20-60 个交易日；配合 PEAD 漂移使用。预告密集期为每年 1 月、4 月、7-8 月、10 月。 · **方向**：正超预期（高值）→ 看多；负超预期（低值/预告低于预期）→ 看空

- **定义/公式**：FORECAST_SURPRISE = (FORECAST_MID − ANALYST_CONSENSUS) / |ANALYST_CONSENSUS|
其中 FORECAST_MID = (forecast.p_change_max + forecast.p_change_min) / 2（盈利预告增速中值）；
ANALYST_CONSENSUS = 来自 report_rc 对应期间的一致预期增速（过去 90d 内报告的 net_profit 预测的加权中位数）。
若无分析师预期，退化为与上年同期相比的随机游走超预期：FORECAST_SURPRISE_RW = (FORECAST_MID − YoY_NET_PROFIT_{t−4}) / |YoY_NET_PROFIT_{t−4}|
- **逻辑**：盈利预告早于正式财报 1-3 个月披露，是信息领先信号；预告超分析师预期表明公司信息不对称优势，且管理层倾向于保守指引→实际超预期往往是「double surprise」（预告超预期 + 财报再超预期）。
- **数据输入**：盈利预告(forecast: p_change_max/p_change_min/type), 一致预期(report_rc: net_profit), 历史财务(fina_indicator: nprofit_yoy)
- **tushare 端点**：forecast, report_rc, fina_indicator
- **A股证据/陷阱**：bigquant 超预期策略：预告超预期后 60 日持有超额收益 5.4%，年化超额 23.96%；国盛量化 PEAD.notice：财报超预告中值后 60 日超额 4.1%。陷阱：①覆盖率低——全 A 覆盖仅 46%，2022 年部分时期降至 20%；②A 股预告方式分为「预增/预减/扭亏/首亏/续亏」等类型（forecast.type 字段），需对每类型做差异化处理；③预告发布日当天常涨停，需 T+2 建仓；④部分上市公司习惯保守预告（系统性低报），需对历史「预告偏差」做公司级别修正；⑤PIT 严格要求按 ann_date 而非期末处理。
- **机构相关度**：预告超预期是机构紧急调研的触发信号；北向资金在超预期预告后 5 日内增持频率显著高于基准。
- **出处**：国盛量化 PEAD.notice 研报 2022-07, bigquant 超预期投资全攻略

## 7. EXPRESS_SURPRISE
**别名**：业绩快报超预期 / Earnings Express Report Surprise  
**映射**：`expectation_gap` · **可行性**：GREEN · **把握**：high · **周期**：事件后 10-40 个交易日；快报集中披露期 1-3 月/7-8 月（上年年报/中报）。 · **方向**：正超预期 → 看多；快报低于预期 → 看空（较预告更强信号）

- **定义/公式**：EXPRESS_SURPRISE = (EXPRESS_NET_PROFIT − ANALYST_CONSENSUS_NP) / |ANALYST_CONSENSUS_NP|
其中 EXPRESS_NET_PROFIT = express.net_profit（快报归母净利润）；
ANALYST_CONSENSUS_NP = 来自 report_rc 对应年度/季度的一致预期净利润（快报发布前 90d 内的预测中位数）。
若无一致预期，退化为：
EXPRESS_SURPRISE_RW = express.yoy（同比增速）− median(yoy_{同行业股票}）
- **逻辑**：快报比正式年报早 1-3 个月，信息领先优势显著。快报数据接近正式财报，比盈利预告更精确，属于「更确定性的 PEAD 触发信号」。机构机构对快报有严格关注流程，快报超预期后机构资金集中入场。
- **数据输入**：业绩快报(express: net_profit/yoy/ann_date), 一致预期(report_rc: net_profit), 行业分类(index_member_all)
- **tushare 端点**：express, report_rc, index_member_all
- **A股证据/陷阱**：快报超预期事件后 60 日超额约 3-5%（bigquant 综合测算）。陷阱：①快报仅年报和中报有，季报通常无快报；②快报与正式报告可能存在差异（后续修正），建议以正式报告数据覆盖；③快报发布日当日/次日常出现涨跌停，需 T+2 建仓；④上市不足 1 年的新股无可比历史期，需单独处理；⑤ann_date PIT 严格校验，防止前视偏差。
- **机构相关度**：快报是机构分析师更新财务模型的触发点；头部公司快报超预期后北向资金 5 日净买入显著正向。
- **出处**：bigquant 超预期投资全攻略, 国盛量化 PEAD.notice 研报 2022-07

## 8. REVENUE_ACC
**别名**：营收增速加速度 / Revenue Growth Acceleration  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：季频信号；加速度信号在 2-4 个季度内持续有效，适合本系统 2-4 周至 1 季度视窗。 · **方向**：正加速（ΔYoY > 0）→ 看多；减速（ΔYoY < 0）→ 看空

- **定义/公式**：REVENUE_ACC = ΔYoY_Revenue = YoY_Revenue_Q_t − YoY_Revenue_Q_{t−1}
其中 YoY_Revenue_Q_t = (Revenue_Q_t − Revenue_Q_{t−4}) / |Revenue_Q_{t−4}|（单季度营收同比增速）
Δ 即二阶导数（增速的变化量），也可表示为：
REVENUE_ACC_NORM = (YoY_t − YoY_{t−1}) − median_sector(YoY_t − YoY_{t−1})（行业内标准化）
以 fina_indicator.q_revenue_qoq 辅助验证。
- **逻辑**：增速加速意味着景气周期上行拐点；机构在景气度拐点处集中调研和建仓，形成持续资金流。营收增速加速（区别于利润加速）反映真实业务量扩张，不受费用/减值操纵影响。
- **数据输入**：季度营收(income: q_revenue 或 fina_indicator: q_revenue), 单季度同比增速(fina_indicator: yoy_sales)
- **tushare 端点**：income, fina_indicator
- **A股证据/陷阱**：广发金工 2025-08 Alpha 因子跟踪月报：单季度净利润增长率作为成长类核心因子持续有效；2024 Q3 净利润同比增速反弹 6.18pct 驱动相关因子多头组合超额。陷阱：①季度财务数据存在 PIT 问题（需严格使用 ann_date）；②跨行业比较需行业中性化（科技行业营收加速显著优于周期行业）；③小市值股票营收波动大，需 Winsorize 处理；④营收确认政策差异（分部确认 vs 完工百分比）需注意。
- **机构相关度**：营收加速是机构景气投资框架的核心指标；行业景气度向上时北向资金配置倾向于营收加速标的。
- **出处**：广发金工 Alpha 因子跟踪月报 2025-08, 海量量化「如何计算盈利指标的趋势」

## 9. NET_PROFIT_ACC
**别名**：净利润增速加速度 / Net Profit Growth Acceleration  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：季频，1-2 个季度有效；配合预期修正因子（FY1_EPS_REV_MOM）使用有协同增强效果。 · **方向**：正加速 → 看多；持续减速 → 看空（尤其结合负 SUE_Q）

- **定义/公式**：NP_ACC = ΔYoY_NP = YoY_NP_Q_t − YoY_NP_Q_{t−1}
其中 YoY_NP_Q_t = (NP_Q_t − NP_Q_{t−4}) / |NP_Q_{t−4}|（单季度归母净利润同比增速）
分拆版：NP_ACC_DECOMP = ROE_ACC + LEVERAGE_ACC
（杜邦分解视角：利润加速来源分解为盈利能力提升 vs 杠杆扩张）
可用 fina_indicator.q_profit_yoy 直接差分。
- **逻辑**：净利润加速是 Novy-Marx 盈利质量框架的动态扩展；结合 Piotroski F-score 的 ΔROa 指标，捕捉基本面改善的「速度」而非「位置」。净利润加速比营收加速更受 A 股机构投资者关注（景气度打分主要看利润端）。
- **数据输入**：季度净利润(fina_indicator: q_profit/q_dt_eps), 单季度 YoY 增速(fina_indicator: yoy_net_profit_qoq 或自算)
- **tushare 端点**：fina_indicator, income
- **A股证据/陷阱**：广发金工 2025-08：净利润增长率作为主流成长因子之一有效性「明确」，但 2024 年部分季度因宏观下行而失效，需结合宏观 regime 调整权重。陷阱：①净利润含非经常性损益，建议用扣非净利润（q_profit_dedt）；②商誉减值/资产减值可能造成季度净利润突变，需识别并中性化；③基数效应导致低基期季度 YoY 数据失真，需用中位数/截断处理。
- **机构相关度**：净利润加速是大多数机构投研体系中景气评分的核心维度；与分析师 EPS 修正高度相关（互相验证）。
- **出处**：广发金工 Alpha 因子跟踪月报 2025-08, Piotroski (2000) JAR

## 10. PEAD_DRIFT_SCORE
**别名**：盈余公告后价格漂移得分 / PEAD Drift Score  
**映射**：`expectation_gap` · **可行性**：YELLOW · **把握**：med · **周期**：事件后 20-60 交易日；季度调仓（与财报周期同步）。 · **方向**：高分 → 看多；低分（负 SUE + 无后续研报关注）→ 看空

- **定义/公式**：PEAD_DRIFT_SCORE = SUE_Q × (1 + INVESTOR_ATTN_FACTOR)
其中 INVESTOR_ATTN_FACTOR = log(1 + N_analyst_reports_post30d)（公告后 30 日内研报数量的对数）
简化版（当无投资者关注度数据时）：
PEAD_DRIFT_SCORE = SUE_Q × sign(POST_ANN_ABNORMAL_RET_5D)
即：盈利惊喜方向与公告后 5 日异常收益方向一致时增强信号，否则减弱（防止公告日反向冲击）。
- **逻辑**：SSRN 4589824(2024)：投资者关注度与 PEAD 强度正相关——高关注股票 PEAD 效应平均季度超额 6.78%，低关注股票仅 3.2%。A 股机构投资者比例增加使高关注度股票 PEAD 减弱，但中小市值低关注股票 PEAD 依然显著。
- **数据输入**：SUE_Q（见上）, 公告后研报数量(report_rc: report_date + ts_code), 公告后 5 日日收益率(daily: close)
- **tushare 端点**：fina_indicator, report_rc, daily
- **A股证据/陷阱**：ScienceDirect 2022(2000-2020 A 股数据)：有限注意力下当投资者预期分歧大时 PEAD 效应更显著；季度超额 6.78%（全样本）。陷阱：①研报数量可能受报告期集中效应干扰；②涨跌停截断影响漂移计算（公告后多连板股票持有成本高）；③T+1 限制使第一日涨跌停无法参与；④覆盖率不足（50% A 股无分析师覆盖）使关注度维度缺失。
- **机构相关度**：机构投资者是 PEAD 的主要受益者；研究表明 A 股机构能从散户低估反应中获利。
- **出处**：SSRN 4589824 (2024) Lan et al., Heterogeneous investor attention and PEAD (2022) ScienceDirect

## 11. ANALYST_COVERAGE_CHG
**别名**：分析师覆盖变化 / Analyst Coverage Change  
**映射**：`expectation_gap` · **可行性**：GREEN · **把握**：med · **周期**：覆盖增加后 20-60 交易日有效；共同覆盖因子为月频调仓信号。 · **方向**：覆盖增加/首次覆盖 → 看多；覆盖消失（分析师停止跟踪）→ 看空

- **定义/公式**：COVERAGE_CHG = N_analysts_{t} − N_analysts_{t−1}
（过去 90 日有报告的分析师数量 vs 前 90 日；N 基于 report_rc 的 analyst/org_name 去重）

INITIATION_FLAG = 1 if N_analysts_{t} > 0 and N_analysts_{t−1} == 0（首次覆盖信号）

华泰改进（2022 AI-58 共同覆盖因子）：
COVERAGE_OVERLAP_SCORE = Σ_{j∈analysts_covering_s} [avg_return_of_other_stocks_analyst_j_covers in past 30d]
（分析师组合关联网络的信息溢出信号）
- **逻辑**：新分析师覆盖是机构注意力转移的领先信号；覆盖增加 → 信息不对称降低 → 估值修复。A 股中首次覆盖几乎总是「买入」评级，形成短期资金驱动。「共同覆盖」逻辑：同一分析师覆盖的股票间存在信息溢出，可捕捉跨股票预期传导。
- **数据输入**：分析师报告历史(report_rc: ts_code/analyst/org_name/report_date), 覆盖分析师数去重
- **tushare 端点**：report_rc
- **A股证据/陷阱**：华泰金工 2024：分析师异常覆盖因子月度 RankIC 2.34%，TOP 组合年化超额 6.59%（剔除市值/行业/动量/换手/机构持仓后的残差）。陷阱：①首次覆盖效应在 A 股受「首次覆盖必买入」惯例污染；②覆盖稀疏期（春节、业绩窗口静默期）会产生虚假覆盖下降信号；③需对分析师自然更换（人员流动）与主动停止跟踪做区分；④大市值股票覆盖变化小（信号弱），因子在中小市值更有效。
- **机构相关度**：分析师覆盖变化直接反映机构卖方资源配置方向；新覆盖是机构客户入场的「首发号角」。
- **出处**：华泰金工 2024-12《分析师预期类因子初探》（异常覆盖因子）, Irvine (2003) JFE（分析师首次覆盖效应）

## 12. FY1_FY2_REVISION_SPREAD
**别名**：FY1/FY2 盈利预期修正差值 / Near-Far Term Revision Spread  
**映射**：`expectation_gap` · **可行性**：YELLOW · **把握**：med · **周期**：2-6 周，月频调仓；属于短期预期确定性信号。 · **方向**：FY1 修正显著 > FY2 修正（正 SPREAD）→ 看多；FY2 修正 > FY1 → 长期故事未兑现 → 中性或看空

- **定义/公式**：FY1_REV = (EPS_FY1_consensus_t − EPS_FY1_consensus_{t−30d}) / |EPS_FY1_consensus_{t−30d}|
FY2_REV = (EPS_FY2_consensus_t − EPS_FY2_consensus_{t−30d}) / |EPS_FY2_consensus_{t−30d}|
REV_SPREAD = FY1_REV − FY2_REV
（若 FY1 修正大幅领先 FY2，说明近期盈利改善确定性强于长期，属于「短期景气催化」信号）

一致预期 EPS 由当期有效的 report_rc 记录加权平均合成（等权或按发布时新近度加权）。
- **逻辑**：当 FY1 上调幅度 > FY2 时，分析师对近期业绩确定性更强——这是短期催化因子而非长期重估因子，适合本系统 2-4 周窗口。FY1-FY2 扩散方向捕捉「催化因子落地」的确定性。
- **数据输入**：FY1/FY2 净利润/EPS 预测(report_rc: net_profit/eps/period), 报告日期(report_rc: report_date)
- **tushare 端点**：report_rc
- **A股证据/陷阱**：A 股 report_rc 中需从 period 字段区分 FY1/FY2，数据工程复杂度中等。实证上，FY1>FY2 修正组合在季报后 4-8 周超额约 3-4%（来源：bigquant 综合分析，无直接 IC 数据）。陷阱：①需严格处理 report_rc 中会计年度与自然年度的对应关系；②报告数量不足时 FY2 一致预期样本量极少（噪声大）；③A 股分析师对 FY2 预测更新频率远低于 FY1，需设置最近性截断（90 日内有效）。
- **机构相关度**：FY1 vs FY2 分析是机构 roadshow 路演核心话题；外资机构对近期业绩确定性更敏感。
- **出处**：bigquant 超预期投资全攻略, 中信建投因子深度研究系列 13

## 13. CONSENSUS_UPGRADE_RATIO
**别名**：一致预期上调占比 / Consensus Upgrade Ratio  
**映射**：`expectation_gap` · **可行性**：GREEN · **把握**：med · **周期**：月频信号，有效周期 20-60 日；与 FY1_EPS_REV_MOM 高度相关（互相验证，注意因子重复）。 · **方向**：高净上调占比（接近 +1）→ 看多；持续净下调（接近 -1）→ 看空

- **定义/公式**：N_up = count(analysts where EPS_FY1_{t} > EPS_FY1_{t−30d})（过去 30 日内上调 FY1 的分析师数）
N_down = count(analysts where EPS_FY1_{t} < EPS_FY1_{t−30d})（下调数）
N_total = N_up + N_down + N_unchanged
CONSENSUS_UPG_RATIO = (N_up − N_down) / N_total
（取值 [-1, 1]，正值表示净上调）

改进版（华泰 2024）：CREATIVE_REV_RATIO = 高创新性修正占比 ×∑|修正幅度|
（创新性=修正方向与过去 3 个月市场一致预期变化方向相反——即「逆流」分析师信号更有价值）
- **逻辑**：上调占比是分析师集体情绪的度量；「逆流」修正的分析师往往拥有更强的基本面信息，其上调信号更有预测力。A 股机构会议驱动效应：多数机构集中上调后往往是入场窗口。
- **数据输入**：分析师 FY1 EPS/净利润预测(report_rc: eps/net_profit), 报告日期(report_rc: report_date)
- **tushare 端点**：report_rc
- **A股证据/陷阱**：华泰金工 2024：盈利修正因子（含上调占比）月度 RankIC 3.99%，为三类分析师因子中最强。陷阱：①需过滤「机械性」重复报告（同一分析师 30 日内多次小幅修正）；②样本量 < 3 的股票排除；③A 股存在「报告堆积」现象（季报后大量同向修正），降低逆流分析师信号密度；④行业内标准化必须，因周期行业上调占比系统性高于防御行业。
- **机构相关度**：上调占比是机构基本面 roadshow 路演结果的直接反映；北向资金对净上调股票配置偏向明显。
- **出处**：华泰金工 2024-12《分析师预期类因子初探》, 中信建投因子深度研究系列 13

## 14. GUIDANCE_BEAT
**别名**：管理层指引超预期 / Management Guidance Beat  
**映射**：`expectation_gap` · **可行性**：YELLOW · **把握**：med · **周期**：年度/半年度信号；配合季度 SUE_Q 使用，提升胜率。有效期 1-4 个季度。 · **方向**：正 GUIDANCE_BEAT（实际超指引）→ 看多；负值（不及指引）→ 强烈看空信号

- **定义/公式**：GUIDANCE_BEAT = (actual_YoY_profit_Q − guidance_midpoint_YoY) / |guidance_midpoint_YoY|
其中 guidance_midpoint_YoY = (forecast.p_change_max + forecast.p_change_min) / 2（预告利润增速中值，作为管理层指引代理）
actual_YoY_profit_Q = 正式财报披露后的实际净利润同比增速（fina_indicator.nprofit_yoy）

当快报先发：GUIDANCE_BEAT_EXPRESS = (express.net_profit − forecast_net_profit_implied) / |forecast_net_profit_implied|
（forecast_net_profit_implied = last_year_net_profit × (1 + forecast.p_change_min/100)）
- **逻辑**：「管理层指引偏差」衡量管理层保守指引后的超额实现能力——习惯性保守指引的公司（如台积电式低调管理）股价长期向上修正。A 股中部分行业（消费、制造业）管理层系统性保守，识别此类公司可预测下一次超预期。
- **数据输入**：盈利预告(forecast: p_change_max/p_change_min/ann_date), 实际财报(fina_indicator: nprofit_yoy), 业绩快报(express: net_profit/ann_date)
- **tushare 端点**：forecast, fina_indicator, express
- **A股证据/陷阱**：bigquant：预告超预期（GUIDANCE_BEAT > 0）后 60 日超额约 5.4%；反向（不及指引）信号更强（-7% 至 -12%）。陷阱：①预告覆盖率问题（46% 全 A）；②预告类型为「不确定」或「无法预计」时无法计算（需剔除）；③A 股部分公司「先预减后实际超预期」的操纵行为，需识别；④正式报告披露窗口与预告之间平均间隔 60-90 天，需 PIT 处理。
- **机构相关度**：管理层指引是机构投研最重要的 channel check 维度；机构反向投资（做多系统性保守指引公司）是 A 股常见策略。
- **出处**：bigquant 超预期投资全攻略, 国盛量化 PEAD.notice 研报 2022-07

## 15. COMPOSITE_EXPECTATION_SCORE
**别名**：综合预期偏差得分 / Composite Expectation Gap Score  
**映射**：`expectation_gap` · **可行性**：YELLOW · **把握**：high · **周期**：月频至季频调仓；合成因子比单一因子更平滑，适合 2-8 周持仓。 · **方向**：高合成分 → 看多；低合成分 → 看空

- **定义/公式**：COMPOSITE_EXPECT = w1×RANK(SUE_Q) + w2×RANK(FY1_EPS_REV_MOM) + w3×RANK(FORECAST_SURPRISE) + w4×RANK(CONSENSUS_UPG_RATIO)
其中 w1=0.35, w2=0.35, w3=0.20, w4=0.10（基于华泰 2024 IC 贡献度估算的等量参考权重，需实证校准）
各子因子在截面上先行业中性化、市值中性化、Winsorize(1%-99%)、zscore 标准化后再合成。

多空分层版：将 COMPOSITE_EXPECT 分 10 组，TOP20% 做多，BOTTOM20% 做空（与指数增强策略一致）。
- **逻辑**：子因子（基本面惊喜 + 预期修正 + 预告惊喜 + 上调占比）从财报、分析师、管理层三个角度共同度量「市场预期低估」，合成后因子相关性低，多源验证提升稳健性。华泰综合因子 RankIC 4.27% 即对应此类合成逻辑。
- **数据输入**：以上各子因子所需字段, 市值(daily_basic: total_mv), 行业(index_member_all)
- **tushare 端点**：fina_indicator, report_rc, forecast, express, daily_basic, index_member_all
- **A股证据/陷阱**：华泰金工 2024：分析师综合因子（三子因子等权合成）月度 RankIC 4.27%，年化超额 10.55%；沪深 300 增强 IR=2.02，中证 1000 增强 IR=4.44。陷阱：①合成过程中覆盖率不均（SUE_Q/FORECAST_SURPRISE 约 46%，FY1_EPS_REV_MOM 约 50%）导致合成权重需动态调整；②2024 年部分传统预期类因子出现短期失效，需因子择时或缩短持仓；③行业/市值中性化是合成前必须步骤，否则因子退化为行业轮动信号。
- **机构相关度**：综合预期因子是机构 Alpha 量化组合的核心配置，与 AI 量价因子相关性极低（0.03），提供真正的增量 Alpha。
- **出处**：华泰金工 2024-12《分析师预期类因子初探》, bigquant 超预期投资全攻略, 国盛量化 PEAD.notice 研报 2022-07