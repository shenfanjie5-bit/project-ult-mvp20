# 因子目录总表（166 条）

可行性：GREEN=现数据+字段直接可算 · YELLOW=数据有需新增派生/dp_id · RED=数据不足

| # | 因子 | 族 | 映射 score_target | 可行 | 把握 | 周期 |
|---|---|---|---|---|---|---|
| 1 | 行业内横截面 EP（盈利收益率·行业中性化） | 价值/估值（Value） | `valuation_rerating` | GREEN | high | 1-3 个月；对本系统 2-4 周短 |
| 2 | 账面市值比 BP（Book-to-Price） | 价值/估值（Value） | `valuation_rerating` | GREEN | high | 1-3 个月（月均再平衡） |
| 3 | 自由现金流收益率 FCF/P（市值口径） | 价值/估值（Value） | `valuation_rerating` | GREEN | high | 1-3 个月（适合本系统 2-4 周 |
| 4 | EV/EBITDA 倒数（企业倍数因子） | 价值/估值（Value） | `valuation_rerating` | GREEN | high | 1-3 个月 |
| 5 | FCF/EV（企业价值口径 FCF 收益率） | 价值/估值（Value） | `valuation_rerating` | GREEN | med | 1-3 个月 |
| 6 | 股息率（Dividend Yield） | 价值/估值（Value） | `valuation_rerating` | GREEN | high | 中长期（1-6 个月），在利率下行  |
| 7 | PEG 因子（PE 对增长率比值） | 价值/估值（Value） | `valuation_rerating` | GREEN | med | 1-6 个月（中长期更有效） |
| 8 | PS（市销率）倒数 SP（Sales-to-Price） | 价值/估值（Value） | `valuation_rerating` | GREEN | high | 1-3 个月 |
| 9 | AH 股折价因子 | 价值/估值（Value） | `valuation_rerating` | GREEN | high | 2-8 周（中期） |
| 10 | 预期 PE（Forward PE 横截面排名） | 价值/估值（Value） | `expectation_gap` | GREEN | high | 1-3 个月（短期分析师覆盖更新快） |
| 11 | 历史估值百分位（自身时序 PE 分位）横截面化改进 | 价值/估值（Value） | `valuation_rerating` | GREEN | high | 1-3 个月 |
| 12 | 现金流市值比 CFP（Cash Flow Yield） | 价值/估值（Value） | `fundamental_score` | GREEN | med | 1-3 个月 |
| 13 | 应计异象因子（Sloan Accruals / 盈利质量调整估值） | 价值/估值（Value） | `fundamental_score` | GREEN | med | 3-12 个月（长期） |
| 14 | 行业相对 PB（分层 Book-to-Market + 资产质量调整） | 价值/估值（Value） | `valuation_rerating` | GREEN | high | 1-3 个月 |
| 15 | 利率调整 EP（BEER 模型 / 债股收益比） | 价值/估值（Value） | `valuation_rerating` | YELLOW | med | 中长期（宏观 regime 因子，1 |
| 16 | 负 PE 处理：EP 插补与哑变量（负盈利估值修正） | 价值/估值（Value） | `risk_discount` | GREEN | high | 横截面统计，非独立预测因子；适用所有 |
| 17 | Piotroski F-Score | quality | `fundamental_score` | GREEN | high | 季报/年报更新后1-3个月持有；典型 |
| 18 | Sloan BS-Accruals | quality | `fundamental_score` | GREEN | high | 年报更新后持有12个月典型；季度频率 |
| 19 | CF-Accruals (现金流应计比率) | quality | `fundamental_score` | GREEN | high | 季度更新，3-6个月预测窗口；季频r |
| 20 | Novy-Marx GP/Assets | quality | `fundamental_score` | GREEN | high | 年报/季报更新后持有1-4个季度；1 |
| 21 | RONOA (净经营资产回报率) | quality | `fundamental_score` | GREEN | high | 年报更新后持有6-12个月；季频计算 |
| 22 | ROE Stability (ROE稳定性/持续性) | quality | `fundamental_score` | GREEN | high | 需8个季度历史数据（2年），典型持仓 |
| 23 | Asset Growth (总资产增长率) | quality | `fundamental_score` | GREEN | med | 年报更新后持有12个月最优；季度同比 |
| 24 | Net Operating Assets (净营运资产/NOA) | quality | `fundamental_score` | GREEN | med | 年报级别，持有12个月；季度更新版持 |
| 25 | Altman Z'-Score | quality | `risk_discount` | GREEN | med | 年报更新后有效期12-24个月；季报 |
| 26 | Merton Distance-to-Default (违约距离) | quality | `risk_discount` | YELLOW | med | 日频更新（市价驱动），2-4周内有效 |
| 27 | DuPont ROE Decomposition Quality | quality | `fundamental_score` | GREEN | med | 年报/季报更新，持有6-12个月；作 |
| 28 | FCFF/IC (自由现金流投入资本回报) | quality | `fundamental_score` | GREEN | med | TTM平滑季度波动，持有6-12个月 |
| 29 | SUE (标准化非预期盈余) | quality | `expectation_gap` | GREEN | high | 业绩公告后2-8周最强（覆盖系统2- |
| 30 | Earnings Revision Momentum (盈余预测修正动量) | quality | `expectation_gap` | GREEN | high | 2-8周（完全覆盖系统2-4周窗）— |
| 31 | Ohlson O-Score (财务困境Logit模型) | quality | `risk_discount` | GREEN | med | 年报级别，有效期12个月；可用快报季 |
| 32 | Gross Margin Trend (毛利率趋势变化) | quality | `fundamental_score` | GREEN | med | 季报更新后1-3个月；2-4周窗内是 |
| 33 | Cross-Sectional 12-1 Price Momentum | momentum_reversal | `capital_sentiment` | GREEN | med | 1个月持有（月频换仓），2-4周持有 |
| 34 | Short-Term 1-Month Reversal | momentum_reversal | `capital_sentiment` | GREEN | high | 1-4周（A股最强的量价信号之一） |
| 35 | Residual/Idiosyncratic Momentum (Alpha Momentum) | momentum_reversal | `capital_sentiment` | GREEN | high | 1-3个月（比原始动量更稳定，适配系 |
| 36 | 52-Week High Momentum (George-Hwang) | momentum_reversal | `capital_sentiment` | GREEN | med | 1-3个月（中期动量信号） |
| 37 | Industry/Sector Momentum | momentum_reversal | `capital_sentiment` | GREEN | high | 1-2个月（月频行业轮动，A股日频和 |
| 38 | Northbound Capital Holding Change Momentum | momentum_reversal | `capital_sentiment` | GREEN | med | 2-4周（与系统核心窗口完全吻合） |
| 39 | Margin Financing Balance Momentum | momentum_reversal | `capital_sentiment` | GREEN | med | 1-4周（短期），月度高融资比率转为 |
| 40 | Chip Cost Distribution Momentum (CYQ-based) | momentum_reversal | `capital_sentiment` | GREEN | high | 1-4周，周频版信号更强（年化多空5 |
| 41 | Turnover-Rate-Adjusted Momentum | momentum_reversal | `capital_sentiment` | GREEN | med | 1-3个月 |
| 42 | Block Trade Discount/Premium Signal | momentum_reversal | `capital_sentiment` | GREEN | med | 2-6周（事件驱动，买方建仓完成后涨 |
| 43 | Hot Money (LHB) Flow Momentum | momentum_reversal | `capital_sentiment` | GREEN | med | 3-15个交易日（短线，题材发酵窗口 |
| 44 | Dynamic Momentum Crash Signal (Daniel-Moskowitz) | momentum_reversal | `risk_discount` | GREEN | med | 风险控制模块（择时overlay）， |
| 45 | Earnings Surprise Momentum (SUE / PEAD) | momentum_reversal | `expectation_gap` | YELLOW | med | 2-8周（A股PEAD窗口约20-4 |
| 46 | Analyst Revision Momentum | momentum_reversal | `expectation_gap` | YELLOW | med | 1-2个月（分析师报告覆盖周期） |
| 47 | Volume-Weighted Return Divergence (Price-Volume Divergence) | momentum_reversal | `capital_sentiment` | GREEN | med | 1-3周 |
| 48 | Shareholder Count Decrease Momentum | momentum_reversal | `capital_sentiment` | GREEN | med | 1-3个月（季度信号，月频使用时需插 |
| 49 | Short-Term Reversal Post-Limit-Up/Down | momentum_reversal | `capital_sentiment` | GREEN | high | 3-10个交易日（事件驱动） |
| 50 | Intraday-to-Close Return Persistence (Overnight + Intraday Split) | momentum_reversal | `capital_sentiment` | GREEN | med | 2-4周 |
| 51 | SUE_Q | growth_expectation | `expectation_gap` | GREEN | high | 事件后 20-60 个交易日；与本系 |
| 52 | FY1_EPS_REV_MOM | growth_expectation | `expectation_gap` | GREEN | high | 20-60 个交易日；对本系统 2- |
| 53 | ANALYST_RATING_REV | growth_expectation | `expectation_gap` | GREEN | med | 事件驱动型，评级发布后 10-30  |
| 54 | TARGET_PRICE_UPSIDE | growth_expectation | `valuation_rerating` | GREEN | med | 中期信号（1-3 月）；目标价通常设 |
| 55 | EPS_DISPERSION | growth_expectation | `risk_discount` | GREEN | med | 中期信号（1-3 月）；适合作为风险 |
| 56 | FORECAST_SURPRISE | growth_expectation | `expectation_gap` | YELLOW | high | 事件驱动，预告发布后 20-60 个 |
| 57 | EXPRESS_SURPRISE | growth_expectation | `expectation_gap` | GREEN | high | 事件后 10-40 个交易日；快报集 |
| 58 | REVENUE_ACC | growth_expectation | `fundamental_score` | GREEN | med | 季频信号；加速度信号在 2-4 个季 |
| 59 | NET_PROFIT_ACC | growth_expectation | `fundamental_score` | GREEN | med | 季频，1-2 个季度有效；配合预期修 |
| 60 | PEAD_DRIFT_SCORE | growth_expectation | `expectation_gap` | YELLOW | med | 事件后 20-60 交易日；季度调仓 |
| 61 | ANALYST_COVERAGE_CHG | growth_expectation | `expectation_gap` | GREEN | med | 覆盖增加后 20-60 交易日有效； |
| 62 | FY1_FY2_REVISION_SPREAD | growth_expectation | `expectation_gap` | YELLOW | med | 2-6 周，月频调仓；属于短期预期确 |
| 63 | CONSENSUS_UPGRADE_RATIO | growth_expectation | `expectation_gap` | GREEN | med | 月频信号，有效周期 20-60 日； |
| 64 | GUIDANCE_BEAT | growth_expectation | `expectation_gap` | YELLOW | med | 年度/半年度信号；配合季度 SUE_ |
| 65 | COMPOSITE_EXPECTATION_SCORE | growth_expectation | `expectation_gap` | YELLOW | high | 月频至季频调仓；合成因子比单一因子更 |
| 66 | 北向持股变化率 (HK_Hold_Chg) | institutional_flow | `capital_sentiment` | YELLOW | med | 季度(63TD)为主；日频NF_Ra |
| 67 | 融资买入动量因子 (Margin_Buy_Momentum) | institutional_flow | `capital_sentiment` | GREEN | high | 10-21TD动量信号；60-90T |
| 68 | 融券余额变化率 (Short_Interest_Chg) | institutional_flow | `risk_discount` | GREEN | med | 21-63TD；空头压力具有中期持续 |
| 69 | 主力净流入率 CNIR (Composite Net Inflow Rate) | institutional_flow | `capital_sentiment` | GREEN | med | 5-10TD短期信号最强；21TD动 |
| 70 | 东财/同花顺个股资金流净流入强度 (MF_THS_NetIn) | institutional_flow | `capital_sentiment` | GREEN | med | 3-10TD；情绪动量信号，不宜持有 |
| 71 | 游资净买入强度 (HM_Net_Buy) | institutional_flow | `capital_sentiment` | GREEN | med | 5-10TD超短期（游资做多后散户跟 |
| 72 | 大宗交易成交额占比因子 (Block_Trade_Ratio) | institutional_flow | `capital_sentiment` | GREEN | med | 21-63TD；大宗交易信息传递有滞 |
| 73 | 大宗折溢价率信号 (Block_Trade_Discount) | institutional_flow | `capital_sentiment` | GREEN | med | 10-21TD事件后效应 |
| 74 | 筹码获利盘比例 (Winner_Rate_Factor) | institutional_flow | `capital_sentiment` | GREEN | med | 5-21TD反转信号；与动量因子反向 |
| 75 | 筹码集中度因子 (Chip_Concentration) | institutional_flow | `capital_sentiment` | GREEN | med | 10-63TD中期建仓完成信号 |
| 76 | 股东人数变化率 (Shareholder_Count_Chg) | institutional_flow | `capital_sentiment` | GREEN | med | 63-126TD（季报/半年报披露周 |
| 77 | 大股东增减持强度 (Insider_Trade_Signal) | institutional_flow | `capital_sentiment` | GREEN | med | 63-126TD；内部人增持效应持续 |
| 78 | 股权质押风险因子 (Pledge_Risk_Score) | institutional_flow | `risk_discount` | GREEN | med | 长期风险信号（持续高质押→风险积累） |
| 79 | 解禁压力因子 (Unlock_Overhang) | institutional_flow | `risk_discount` | GREEN | med | 前瞻21-63TD预警；解禁后30- |
| 80 | 行业资金流轮动因子 (Sector_Moneyflow_Rotation) | institutional_flow | `capital_sentiment` | YELLOW | med | 10-21TD行业资金动量有效；63 |
| 81 | AH溢价套利压力 (AH_Premium_Arbitrage) | institutional_flow | `valuation_rerating` | GREEN | med | 63-126TD均值回归信号 |
| 82 | 北向资金流速动量 (HSGT_Flow_Momentum) | institutional_flow | `capital_sentiment` | GREEN | med | 10-21TD市场择时信号；个股层面 |
| 83 | Amihud ILLIQ 月均非流动性 | liquidity_micro | `risk_discount` | GREEN | high | 月度重算（20交易日），预测窗口 2 |
| 84 | 超额换手率（DTURN） | liquidity_micro | `capital_sentiment` | GREEN | high | 月度换手率差分预测下1个月；日频 Z |
| 85 | 换手率波动率（成交稳定性因子） | liquidity_micro | `capital_sentiment` | GREEN | high | 20日换手率稳定性预测 2-4 周超 |
| 86 | 量比（Volume Ratio） | liquidity_micro | `capital_sentiment` | GREEN | med | 日频，预测 3-10 个交易日内价格 |
| 87 | Corwin-Schultz 高低价买卖价差估计量 | liquidity_micro | `risk_discount` | GREEN | med | 月度均值，预测 2-4 周风险折价水 |
| 88 | Roll 隐含价差 | liquidity_micro | `risk_discount` | GREEN | med | 月度均值，预测 2-4 周流动性状态 |
| 89 | 零收益天数比例（Lesmond 流动性） | liquidity_micro | `risk_discount` | GREEN | med | 月度，预测 4-8 周流动性状态（低 |
| 90 | 筹码获利比例（CYQ 胜率） | liquidity_micro | `capital_sentiment` | GREEN | med | 日频，预测 2-3 周方向；与价格动 |
| 91 | 筹码集中度（CYQ 峰值集中度） | liquidity_micro | `capital_sentiment` | GREEN | med | 周度/月度信号，预测 3-6 周趋势 |
| 92 | 股东人数变化率（筹码集中信号） | liquidity_micro | `capital_sentiment` | GREEN | high | 季度更新（约每60个交易日），预测  |
| 93 | 解禁压力因子 | liquidity_micro | `risk_discount` | GREEN | high | 20日/60日解禁窗口，预测 1-3 |
| 94 | 大宗交易折价率因子 | liquidity_micro | `capital_sentiment` | GREEN | med | 日频发生，月度累计信号；预测 1-4 |
| 95 | 融资余额变化率（杠杆资金信号） | liquidity_micro | `funding_score` | GREEN | high | 5日/20日变化率，预测 1-3 周 |
| 96 | 换手率调整后动量反转（STREV_TO） | liquidity_micro | `capital_sentiment` | GREEN | high | 20日滚动，预测 2-4 周反转（系 |
| 97 | 北向资金持股变化率（流动性质量信号） | liquidity_micro | `capital_sentiment` | GREEN | high | 5日/20日变化率，预测 2-4 周 |
| 98 | 融券余额比率（卖空压力因子） | liquidity_micro | `risk_discount` | GREEN | med | 日频/月度均值，预测 2-6 周卖压 |
| 99 | IVOL_FF3 | volatility_risk | `risk_discount` | GREEN | high | 1个月重新估计，预测1个月收益；在A |
| 100 | MAX5 | volatility_risk | `risk_discount` | GREEN | high | 过去1个月数据，预测1个月收益；A股 |
| 101 | BAB_A | volatility_risk | `risk_discount` | GREEN | med | 月度再平衡；预测1个月。 |
| 102 | RVOL_20 | volatility_risk | `risk_discount` | GREEN | high | 20日估计，预测1-4周收益；202 |
| 103 | RVOL_HIGHFREQ | volatility_risk | `risk_discount` | YELLOW | med | 月度更新，预测2-4周；日内分钟数据 |
| 104 | SKEW_REALIZED | volatility_risk | `risk_discount` | GREEN | med | 月度估计，预测1个月收益；中国A股文 |
| 105 | COSKEW | volatility_risk | `risk_discount` | GREEN | low | 60日或更长期估计（需稳定估计），预 |
| 106 | DOWNSIDE_BETA | volatility_risk | `risk_discount` | GREEN | med | 252日估计，预测1个月；2-4周窗 |
| 107 | VaR_HS | volatility_risk | `risk_discount` | GREEN | med | 252日历史窗口，月度更新，预测1个 |
| 108 | CYQ_WIDTH | volatility_risk | `risk_discount` | GREEN | med | 日更新，月度截面信号，预测2-4周。 |
| 109 | LIMIT_FREQ | volatility_risk | `risk_discount` | GREEN | med | 60日窗口，月度截面信号，预测2-4 |
| 110 | PLEDGE_VOL | volatility_risk | `risk_discount` | GREEN | med | 季度或月度更新（披露频率），预测1个 |
| 111 | IVOL_RESID_NEUTRAL | volatility_risk | `risk_discount` | GREEN | high | 月度截面信号，预测1个月；双重中性化 |
| 112 | VOL_REGIME | volatility_risk | `risk_discount` | YELLOW | med | 用作调节权重的元因子（factor- |
| 113 | MARGIN_VOL_RATIO | volatility_risk | `risk_discount` | GREEN | med | 月度截面信号，预测2-4周（融资平仓 |
| 114 | SKEW_UNLOCK | volatility_risk | `risk_discount` | GREEN | med | 前向30日滚动，预测未来2-4周内的 |
| 115 | limit_seal_strength | sentiment_attention | `priced_in_discount` | GREEN | high | 1-5日（次日信号最强；5日后衰减） |
| 116 | dc_hot_rank_reversal | sentiment_attention | `priced_in_discount` | GREEN | med | 1-3周（DA研究1-2周最强；A股 |
| 117 | chip_profit_ratio | sentiment_attention | `capital_sentiment` | GREEN | med | 2-6周（筹码结构变化慢，持仓逻辑适 |
| 118 | turnover_acceleration | sentiment_attention | `priced_in_discount` | GREEN | high | 2-4周（与系统核心窗口完全匹配） |
| 119 | limit_board_consecutive | sentiment_attention | `capital_sentiment` | GREEN | med | 1-2周（单只连板股信号短；市场层面 |
| 120 | board_burst_rate | sentiment_attention | `capital_sentiment` | GREEN | med | 市场层面1-3周（情绪低谷持续性）； |
| 121 | irm_qa_intensity | sentiment_attention | `priced_in_discount` | GREEN | med | 1-3周（关注度反转周期） |
| 122 | kpl_concept_momentum_reversal | sentiment_attention | `priced_in_discount` | GREEN | med | 1-2周（题材炒作持续性窗口） |
| 123 | hot_money_presence | sentiment_attention | `capital_sentiment` | GREEN | med | 3-7日(动量)；1-2周(反转，当 |
| 124 | new_share_hype_decay | sentiment_attention | `priced_in_discount` | GREEN | med | 4-12周（次新炒作衰减周期长于普通 |
| 125 | overnight_ret_reversal | sentiment_attention | `priced_in_discount` | GREEN | high | 1-3日（极短期，日频信号） |
| 126 | stk_holder_count_change | sentiment_attention | `capital_sentiment` | GREEN | med | 4-12周（季度数据频率决定；信号持 |
| 127 | margin_balance_sentiment | sentiment_attention | `funding_score` | GREEN | high | 2-4周（融资仓位调整周期；与系统核 |
| 128 | hk_hold_change | sentiment_attention | `capital_sentiment` | GREEN | high | 2-6周（机构建仓周期长；与系统2- |
| 129 | block_trade_discount | sentiment_attention | `risk_discount` | GREEN | med | 2-6周（减持信号持续性；机构接盘后 |
| 130 | share_unlock_pressure | sentiment_attention | `risk_discount` | GREEN | high | 2-8周（事件前后窗口） |
| 131 | sector_rotation_momentum | sentiment_attention | `capital_sentiment` | GREEN | med | 2-4周（行业动量持续性；与系统核心 |
| 132 | ICIR-Optimal Factor Synthesis Weight | multifactor_models | `fundamental_score` | GREEN | high | 月度再平衡（参数 Sigma_IC  |
| 133 | Barra CNE6 Industry + Size Two-Step Neutralization | multifactor_models | `fundamental_score` | GREEN | high | 每次截面计算（周频或月频重算），无单 |
| 134 | Fama-French Five-Factor Composite (FF5) | multifactor_models | `fundamental_score` | GREEN | med | 月度重平衡，因子持有 1-3 个月 |
| 135 | q-Factor: ROE and Investment Factor | multifactor_models | `fundamental_score` | GREEN | med | 季度财报更新后重算，持有 1-3 个 |
| 136 | Piotroski F-Score (A-Share Adapted) | multifactor_models | `fundamental_score` | GREEN | med | 年度财报更新后触发（每年约 4-5  |
| 137 | Carhart Momentum Factor (12-1 Month) | multifactor_models | `capital_sentiment` | GREEN | med | 月度重平衡，2-3 个月持有；中期（ |
| 138 | IVOL: Idiosyncratic Volatility (Low-Vol Anomaly) | multifactor_models | `risk_discount` | GREEN | high | 月度再平衡，持有 1-3 个月 |
| 139 | Northbound (HK Connect) Net Flow Factor | multifactor_models | `capital_sentiment` | GREEN | med | 5 日动量信号，持有 2-4 周 |
| 140 | Margin Financing Change Rate Factor | multifactor_models | `capital_sentiment` | GREEN | med | 5 日变化率信号，持有 2-3 周； |
| 141 | Chip Distribution Profitability Ratio Factor | multifactor_models | `capital_sentiment` | GREEN | med | 短期 3-10 日（博弈层面信号） |
| 142 | Analyst Earnings Revision Momentum (ARM) | multifactor_models | `expectation_gap` | GREEN | med | 4 周修正窗口，持有 4-8 周（P |
| 143 | Factor Crowding Score (FCS) | multifactor_models | `risk_discount` | YELLOW | med | 月度计算拥挤度评分，实时风控监控 |
| 144 | Factor Timing via Macro Regime (Factor Rotation) | multifactor_models | `NEW` | YELLOW | med | 月度体制识别，因子权重月度更新；短期 |
| 145 | LightGBM/GBDT Multi-Factor Synthesis | multifactor_models | `fundamental_score` | YELLOW | med | 月度再平衡，预测 +4 周超额收益 |
| 146 | AlphaNet: End-to-End Price-Volume Neural Factor | multifactor_models | `capital_sentiment` | YELLOW | med | 日频更新信号，持有 2-10 日（高 |
| 147 | Lasso / ElasticNet Factor Selection & Synthesis | multifactor_models | `fundamental_score` | GREEN | med | 月度更新合成权重，预测 +4 周超额 |
| 148 | Symmetric Orthogonalization (Factor Decorrelation) | multifactor_models | `fundamental_score` | GREEN | med | 月度重算正交化矩阵（协方差矩阵用 2 |
| 149 | Sloan Accruals Quality Factor | multifactor_models | `fundamental_score` | GREEN | high | 年度财报触发，持有 6-12 个月 |
| 150 | 货币-信用四象限 Regime 分类器 | macro_regime_timing | `capital_sentiment` | GREEN | high | 1-3 个月调仓，覆盖系统 2-4  |
| 151 | 信用脉冲 Credit Impulse | macro_regime_timing | `capital_sentiment` | YELLOW | high | 6-12 个月预测窗口（价值/成长风 |
| 152 | ERP 股权风险溢价择时信号 | macro_regime_timing | `valuation_rerating` | GREEN | high | 1-3 个月（中期择时），信号更新月 |
| 153 | PMI 扩散指数 + 新订单-库存差 | macro_regime_timing | `fundamental_score` | GREEN | high | 1-2 个月（PMI 公布后当月生效 |
| 154 | 库存周期四阶段定位器 | macro_regime_timing | `capital_sentiment` | YELLOW | med | 3-6 个月（库存周期转换持续 6- |
| 155 | CPI-PPI 剪刀差风格信号 | macro_regime_timing | `capital_sentiment` | GREEN | med | 1-3 个月（通胀周期持续数月），月 |
| 156 | M1-M2 剪刀差资金活化信号 | macro_regime_timing | `capital_sentiment` | GREEN | med | 1-3 个月（货币周期更新月频） |
| 157 | HMM 宏观-资金-市场三维状态机 | macro_regime_timing | `risk_discount` | YELLOW | med | 日频更新，2-4 周持仓为主 |
| 158 | 北向资金流净值动量 | macro_regime_timing | `capital_sentiment` | GREEN | med | 2-4 周（周频更新，1-2 周领先 |
| 159 | 融资余额变化率 + 杠杆情绪温度计 | macro_regime_timing | `funding_score` | GREEN | high | 2-4 周（周频更新），覆盖系统核心 |
| 160 | 全市场换手率百分位温度计 | macro_regime_timing | `capital_sentiment` | GREEN | high | 2-4 周（中期均值回归），日频更新 |
| 161 | CICSI 综合投资者情绪指数 | macro_regime_timing | `capital_sentiment` | YELLOW | med | 1-2 个月（月频更新，领先 1 个 |
| 162 | 多资产相关性骤升系统性风险信号 | macro_regime_timing | `risk_discount` | YELLOW | med | 2-4 周（日频计算，周频确认），覆 |
| 163 | SHIBOR/LPR 利率趋势与利差信号 | macro_regime_timing | `valuation_rerating` | GREEN | med | 1-3 个月（货币政策变化周期），月 |
| 164 | PMI 服务业-制造业背离信号 | macro_regime_timing | `fundamental_score` | GREEN | med | 1-3 个月（行业轮动信号），月频更 |
| 165 | 社融-M2 增速差（信用扩张强度） | macro_regime_timing | `capital_sentiment` | GREEN | med | 2-4 个月（信用传导滞后），月频信 |
| 166 | 风格轮动综合打分器（价值/成长/大盘/小盘） | macro_regime_timing | `valuation_rerating` | GREEN | med | 1-3 个月（风格周期在 6-18  |