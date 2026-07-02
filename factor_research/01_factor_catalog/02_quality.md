# 因子族：quality

> 质量/盈利质量族对本系统的核心价值在于：填补 fundamental_score 轴的量化深度，以及通过盈利质量(accruals)和财务困境距离(Merton DD)为 risk_discount 提供前瞻性信号。系统已有 fina_indicator/income/balancesheet/cashflow 四张表的 API 预算（约 580 calls/cycle），因此 GREEN 级因子几乎无额外成本。最值得优先接入的 2-3 个因子：①RONOA（净经营资产回报率）——比 ROE 更纯粹的经营质量，ic 稳定且机构易理解；②Sloan 资产负债表应计比率（BS-Accruals）——A 股盈余管理程度高，应计异象更强，且现有 income+balancesheet 字段直接可算；③Piotroski F-Score 9 项子分——可用 fina_indicator 已有字段直接组合，同时覆盖盈利/杠杆/效率三维度，对机构基本面审核流程高度兼容。

共 16 条。


## 1. Piotroski F-Score
**别名**：皮尔托斯基9分/F分  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：high · **周期**：季报/年报更新后1-3个月持有；典型调仓频率为季度。不覆盖系统2-4周窗但可作为季度级fundamental_score输入。 · **方向**：高F值→看多（F≥7强多，F≤2强空）

- **定义/公式**：9个0/1指标之和（满分9）：盈利能力4项: F1=ROA_t>0; F2=CFO_t>0; F3=ΔROA_t>0; F4=Accrual=CFO/Total_Assets−ROA>0; 财务质量3项: F5=ΔLeverage_t<0(长期负债率下降); F6=ΔLiquidity_t>0(流动比率上升); F7=ΔShares_t≤0(未增发); 运营效率2项: F8=ΔGross_Margin_t>0; F9=ΔAsset_Turnover_t>0。ROA=净利润/期初总资产；CFO=经营活动现金流/期初总资产；Leverage=长期负债/期末总资产。High(F≥7) minus Low(F≤2)构成多空组合。
- **逻辑**：通过二值信号综合刻画公司财务健康的多维度变化，过滤财务异常公司（特别是高BM低质量陷阱）。行为金融学解释：投资者对基本面改善的系统性低估。
- **数据输入**：net_profit(利润表), n_cashflow_act(现金流表经营活动), total_assets(资产负债表), lt_borr+total_nca(长期负债), current_assets/current_liab(流动比率), total_share(总股本), grossprofit_margin/revenue(毛利), revenue/total_assets(资产周转)
- **tushare 端点**：income, cashflow, balancesheet, fina_indicator
- **A股证据/陷阱**：A股实证中High F vs Low F年化超额收益约8-12%（样本2005-2022），但行业集中度较高（金融/周期权重大）需行业中性化。涨跌停截断对F-Score信号影响小（月频）。ST股已自然排除（ROA持续为负）。PIT关键：财报披露有1-4个月滞后，必须以ann_date而非end_date为准，否则产生前视偏差。机构化程度上升后（2019后）单纯F-Score的alpha衰减，需与价值/动量组合使用。
- **机构相关度**：高——F-Score逻辑与机构基本面分析框架完全一致；机构持仓换手率低适合季度频率信号。
- **出处**：Piotroski, J.D. (2000). Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers. JAR., Sohu财经(2019): 高F-Score投资策略可行吗 https://m.sohu.com/n/479161467/, 知乎(2022): F-Score股票基本面的强弱 https://zhuanlan.zhihu.com/p/538250499

## 2. Sloan BS-Accruals
**别名**：资产负债表应计比率/Sloan应计异象  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：high · **周期**：年报更新后持有12个月典型；季度频率计算可缩短至3-6月。接近2-4周的信号需与快报(express)结合使用。 · **方向**：低应计比率→看多（应计比率与未来股票收益负相关）

- **定义/公式**：BS_Accrual = (ΔNet_Operating_Assets) / Avg_Total_Assets
其中 ΔNOA = (Total_Assets − Cash_and_ST_Invest − Total_Liabilities + STDebt + LTDebt_current + LTDebt)_t − 同项_t-1
或简化版: BS_Accrual = (ΔCA − ΔCash − ΔCL + ΔShort_term_debt + ΔDDA) / Avg_Total_Assets
其中DDA=折旧摊销。看多方向：低应计（高现金盈利占比）→预期超额回报正。
- **逻辑**：Sloan(1996)发现应计成分持续性显著低于现金流成分，市场系统性高估高应计公司盈余。A股盈余管理程度更高（国企政策性利润平滑、民企避税），应计异象理应更强。2022年PMC研究(2007-2019样本)确认: 应计收益与下期超额收益ACCR系数-0.709***。
- **数据输入**：total_assets, cash_and_equivalent(货币资金), total_liab, 短期借款+一年内到期长期借款(short_term_debt), lt_borr(长期借款), depreciation_amort(折旧摊销,来自cashflow)
- **tushare 端点**：balancesheet, cashflow, income
- **A股证据/陷阱**：PMC/Frontiers 2022: A股2007-2019,16281观测,ACCR系数-0.709(p<0.001)。环境不确定性下异象更强(国企−0.218***,民企−0.041)。应用陷阱：①季报只含简表，仅年报有完整NOA科目——建议以年报+TTM估算；②需行业中性化（制造vs金融应计结构差异大）；③ST/退市股应计急剧变化会污染信号，需剔除。
- **机构相关度**：高——机构调研时会审查CFO/净利润比，与本因子信号一致。
- **出处**：Sloan, R.G. (1996). Do Stock Prices Fully Reflect Information in Accruals and Cash Flows? TAR 71(3)., PMC/Frontiers (2022): Does environmental uncertainty aggravate the accrual anomaly in China https://pmc.ncbi.nlm.nih.gov/articles/PMC9595132/, Quantpedia: Accrual Anomaly https://quantpedia.com/strategies/accrual-anomaly

## 3. CF-Accruals (现金流应计比率)
**别名**：现金流版应计/CFO质量比  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：high · **周期**：季度更新，3-6个月预测窗口；季频rebalance适合2-4周系统作为季度分层信号。 · **方向**：低CF_Accrual(CFO>净利润)→看多

- **定义/公式**：CF_Accrual = (Net_Income − CFO) / Avg_Total_Assets
其中 CFO = 经营活动现金流净额(n_cashflow_act)
直接公式: CF_Accrual = (net_profit − n_cashflow_act) / ((TA_t + TA_t-1)/2)
负值越大 → 盈利质量越高(现金流超过利润)。也可用 Cash_Earnings_Ratio = CFO / Net_Income(排除分母为负情形)。
- **逻辑**：CFO法与BS法互补：CFO法直接测量利润的现金化程度，不受会计核算口径差异影响；A股公司惯用提前确认收入/推迟费用，CFO持续低于净利润是财务舞弊早期信号。
- **数据输入**：n_cashflow_act(经营现金流,cashflow表), net_profit(利润表), total_assets(资产负债表)
- **tushare 端点**：cashflow, income, balancesheet
- **A股证据/陷阱**：chindices 2024年质量因子报告: ACC(盈利中现金占比)是其质量族6项指标之一，A股样本中盈利能力+现金流质量复合因子IC均值约0.04-0.06(月)。注意：A股cashflow表区分"直接法"与"间接法"报告，需统一口径；T+1约束和涨跌停不影响季频因子计算。
- **机构相关度**：高——机构财务分析标配，CFO/净利润比是卖方研究核心质量指标。
- **出处**：华证风格因子 2024 https://www.chindices.com/attach/华证风格因子表征指数体系简介.pdf, 质量因子及其在海外指数产品中的应用 2024 https://www.chindices.com/attach/质量因子及其在海外指数产品中的应用.pdf

## 4. Novy-Marx GP/Assets
**别名**：Novy-Marx毛利润资产比/GPOA  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：high · **周期**：年报/季报更新后持有1-4个季度；12个月IC最强。本系统2-4周窗内GPOA作为底层fundamental分层信号。 · **方向**：高GPOA→看多

- **定义/公式**：GPOA = (Revenue − COGS) / Total_Assets = Gross_Profit / Total_Assets
= (operate_income_tb + cogs) / total_assets (利润表字段)
或直接用 grossprofit_margin × revenue / total_assets
行业中性化版：同行业内Z-score后取值。高GPOA →看多。
- **逻辑**：Novy-Marx(2013)发现毛利润比净利润更能预测未来回报，因净利润含大量噪音（会计选择、非经常损益）。毛利润更接近企业真实竞争优势。GPOA与BM（价值因子）负相关但独立，两者组合显著优于单因子。
- **数据输入**：revenue(营业总收入,income), operate_cost(营业成本,income), total_assets(balancesheet)
- **tushare 端点**：income, balancesheet, fina_indicator
- **A股证据/陷阱**：A股2024研究(BigQuant/chindices): GPOA在A股质量因子中IC稳定(月均IC≈0.03-0.04)，但2024年毛利率单因子表现偏弱(-0.000)，需与其他盈利能力组合。金融股应剔除（无COGS概念），需按申万行业中性化。行业内标准化后效果更稳定。
- **机构相关度**：中-高——机构分析师关注毛利率趋势，GPOA将截面维度系统化。
- **出处**：Novy-Marx, R. (2013). The Other Side of Value: The Gross Profitability Premium. JFE 108(1)., 质量因子及其在海外指数产品中的应用 chindices 2024 https://www.chindices.com/

## 5. RONOA (净经营资产回报率)
**别名**：经营资产收益率/净经营资产报酬率  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：high · **周期**：年报更新后持有6-12个月；季频计算可用于2-4周short-term fundamental scoring。 · **方向**：高RONOA→看多

- **定义/公式**：RONOA = NOPAT / Net_Operating_Assets
NOPAT = 营业利润 × (1 − 有效税率) = operate_profit × (1 − income_tax/profit_before_tax)
NOA(净经营资产) = 经营性资产 − 经营性负债
= (total_assets − monetary_fund − tradable_financial_assets) − (total_liab − short_term_loan − lt_borr − bond_payable)
改进版(参考2026量化论坛研报): NOPLAT = EBIT×(1-t); IC = eq_equity + interest_bearing_debt − cash
- **逻辑**：相比ROE剔除财务杠杆效应，相比ROA剔除金融资产干扰，RONOA纯粹衡量核心经营业务的资本效率，是杜邦分析的起点。机构投资者用RONOA与WACC比较衡量价值创造能力。
- **数据输入**：operate_profit(营业利润,income), income_tax(所得税,income), profit_before_tax(利润总额,income), total_assets(balancesheet), monetary_fund(货币资金,balancesheet), total_liab(balancesheet), lt_borr+short_term_loan(有息负债,balancesheet)
- **tushare 端点**：income, balancesheet, fina_indicator
- **A股证据/陷阱**：2026量化论坛研报复现: RONOA在A股行业中性化后IC更稳定、分位组单调性好，相比ROE/ROA显著改善头部衰减。国信证券2024报告: 基于ROE的高质量选股策略中，RONOA分解比简单ROE更有效区分经营质量。系统已有roic字段(fina_indicator)可作为近似，但RONOA定义更精确。
- **机构相关度**：极高——与DCF模型中ROIC>WACC价值创造逻辑完全对应，是机构fundamental分析标配。
- **出处**：量化论坛研报复现: 财务质量类因子改进 2026 https://news.qq.com/rain/a/20260507A06G3600, 国信证券2024: 探寻股价回报的源动力—基于ROE的高质量选股策略 https://finance.sina.com.cn/roll/2024-07-31/doc-incfysvm9263286.shtml

## 6. ROE Stability (ROE稳定性/持续性)
**别名**：ROE波动率/质量稳定因子  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：high · **周期**：需8个季度历史数据（2年），典型持仓6-12个月；作为fundamental_score的调节项适合本系统。 · **方向**：高稳定性×高ROE→看多

- **定义/公式**：ROE_Stability = −σ(ROE_t, ROE_t-1, …, ROE_t-7) / |mean(ROE_t…t-7)|
即负的变异系数(−CV)，近8个季度滚动
或: ROE_Stability_Score = ROE_level × (1 − CV_8Q)
其中CV_8Q = std(ROE_8Q)/abs(mean(ROE_8Q))
高稳定性（低变异）且高水平 ROE → 看多
- **逻辑**：单期高ROE可能来自非经常性因素，持续稳定的高ROE才反映真实竞争优势（护城河）。A股市场波动大，ROE稳定性相当于对盈利能力加以"噪音过滤"，机构更偏好。BigQuant 2024: ROE加稳定性筛选后头端衰减明显改善。
- **数据输入**：roe(净资产收益率,fina_indicator), roe_dt(扣非ROE,fina_indicator), q_roe(单季ROE,fina_indicator)
- **tushare 端点**：fina_indicator
- **A股证据/陷阱**：BigQuant 2024高频因子研究: ROE+稳定性因子在2024年趋势由负转正，进入"强趋势-低拥挤"区间。质量因子高暴露组合累计超额收益1720%(vs沪深300),IC正月占比77.71%。陷阱：新上市<2年公司历史季度不足8期，需剔除或用现有数据填充；涨跌停股价截断不影响基本面计算。
- **机构相关度**：极高——A股机构"GARP"(合理价格买成长)策略核心指标，适合机构为主市场。
- **出处**：BigQuant 2024有效因子 https://bigquant.com/square/paper/65a32e79-39be-4c90-83ed-0b4067daebd4, 新浪财经: 稀缺ROE连续十年超15%仅12股 https://m.thepaper.cn/baijiahao_26922595

## 7. Asset Growth (总资产增长率)
**别名**：Cooper资产增长效应  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：年报更新后持有12个月最优；季度同比版可缩短至3-6个月。 · **方向**：低资产增长率→看多（高AG负向预测）

- **定义/公式**：AG = (Total_Assets_t − Total_Assets_t-1) / Total_Assets_t-1
年度版: AG_YoY = (total_assets_t − total_assets_t-1) / total_assets_t-1
季度版: AG_QoQ = (total_assets_t − total_assets_t-4) / total_assets_t-4 (同比)
看空方向：高资产增长 → 未来回报负
- **逻辑**：Cooper et al.(2008): 过度投资/扩张公司未来股票回报显著低于收缩公司。经济逻辑：管理层帝国建造行为+投资者对增长的过度乐观。资本错配在A股尤为突出（政策导向扩张）。与Piotroski F5(ΔLeverage)互补：AG测量规模扩张，F5测量融资方式。
- **数据输入**：total_assets(资产负债表), ann_date(披露日期,disclosure_date)
- **tushare 端点**：balancesheet, fina_indicator
- **A股证据/陷阱**：A股实证(PanAgora 2018, CAIA): 资产增长负向因子在A股有效，且与价值因子组合稳健。但2020-2023年政策扩张期（"专精特新"国家战略）高AG公司获政策溢价，因子效力阶段性弱化。需剔除金融股（银行资产增长逻辑不同）和2年内新股（扭曲AG基数）。行业中性化对本因子影响大（制造vs服务AG基准差异显著）。
- **机构相关度**：中——机构关注ROIC趋势更甚于AG绝对值，但AG作为"过度扩张预警"信号有用。
- **出处**：Cooper, M.J., Gulen, H., Schill, M.J. (2008). Asset Growth and the Cross-Section of Stock Returns. JF 63(4)., PanAgora (2018): Factor Investing in the China A-share Market https://www.panagora.com/wp-content/uploads/2018/11/Factor-Investing-in-the-China-A-share-Market.pdf

## 8. Net Operating Assets (净营运资产/NOA)
**别名**：Hirshleifer净营运资产水平  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：年报级别，持有12个月；季度更新版持有3-6个月。 · **方向**：低NOA(较少净营运资产积累)→看多

- **定义/公式**：NOA = Operating_Assets − Operating_Liabilities
Operating_Assets = total_assets − monetary_fund − tradable_fin_assets
Operating_Liabilities = total_liab − short_term_loan − lt_borr − bond_payable
标准化: NOA_scaled = NOA / total_assets
因子值取负(−NOA_scaled)用于排序，低NOA积累→看多
- **逻辑**：Hirshleifer et al.(2004): NOA代表历史过度投资的累积，企业持续把利润转化为非现金经营性资产是会计操纵的信号；高NOA企业未来收益倾向低。与Sloan BS-Accruals同源但测量绝对存量而非流量变化。
- **数据输入**：total_assets, monetary_fund(货币资金), total_liab, lt_borr(长期借款), st_borr(短期借款), bond_payable(应付债券)
- **tushare 端点**：balancesheet, fina_indicator
- **A股证据/陷阱**：chindices 2024质量因子报告: NOA(净经营性资产)是质量族3项子成分之一，A股实证中NOA与应计异象高度相关。金融板块NOA定义需特殊处理（保险/银行资产负债表结构完全不同），建议剔除金融或单独建模。
- **机构相关度**：中——机构分析师更直接用NWC(净营运资本)而非NOA，但逻辑相通。
- **出处**：Hirshleifer, D., Hou, K., Teoh, S.H., Zhang, Y. (2004). Do investors overvalue firms with bloated balance sheets? JFE 75., 质量因子及其在海外指数产品中的应用 chindices 2024

## 9. Altman Z'-Score
**别名**：阿特曼Z分数(修正私有版)/财务困境分  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：年报更新后有效期12-24个月；季报简表可更新X1/X3/X5部分。 · **方向**：高Z'→看多（低财务困境概率）；低Z'→风险折扣

- **定义/公式**：Z' = 0.717×X1 + 0.847×X2 + 3.107×X3 + 0.420×X4 + 0.998×X5
X1 = (流动资产-流动负债)/总资产 = (total_cur_assets−total_cur_liab)/total_assets
X2 = 留存收益/总资产 = undist_profit/total_assets
X3 = 息税前利润/总资产 = (operate_profit+financial_exp)/total_assets
X4 = 权益账面值/负债账面值 = total_equity_oth_non_liab/total_liab
X5 = 营业收入/总资产 = revenue/total_assets
Z'<1.23→困境区，Z'>2.9→安全区。因子用Z'正向排序或取−1/Z'作为风险折扣。
- **逻辑**：Z'-Score为非上市公司修正版（市值→账面权益），更适合A股中小市值。财务困境概率高的公司有潜在退市/暂停上市风险，应给予风险折扣。同时高Z'公司体现多维财务健康（盈利+流动性+偿债）。
- **数据输入**：total_cur_assets, total_cur_liab, undist_profit(未分配利润,balancesheet), operate_profit(income), financial_exp(财务费用,income), total_assets, total_equity_oth_non_liab(股东权益,balancesheet), total_liab, revenue(income)
- **tushare 端点**：balancesheet, income, fina_indicator
- **A股证据/陷阱**：A股2023数据集(草莓科研)包含1991-2023年上市公司Z-Score/O-Score数据。Altman原始模型预测1年破产准确率~95%，但在A股ST制度下（退市前有预警期）实际运用需对应ST警示而非破产。Z-Score对金融股不适用（需另建模型）。行业中性化后低Z'的风险信号更纯净。A股特有风险：質押比例高+Z低→退市风险叠加，需结合pledge_stat。
- **机构相关度**：高——信用分析是机构风控核心，Z-Score是基础工具。
- **出处**：Altman, E.I. (1968). Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy. JF 23(4)., Altman(1983)修正版Z'模型, 草莓科研: 2023-1991年上市公司财务困境数据 https://www.caomeikeyan.com/forum.php?mod=viewthread&tid=488

## 10. Merton Distance-to-Default (违约距离)
**别名**：默顿模型DD/KMV违约距离  
**映射**：`risk_discount` · **可行性**：YELLOW · **把握**：med · **周期**：日频更新（市价驱动），2-4周内有效信号。完全覆盖系统2-4周预测窗。 · **方向**：高DD→看多；DD骤降（滚动ΔDD<−2σ）→风险折扣触发

- **定义/公式**：DD = [ln(V_A/D) + (μ_A − σ_A²/2)×T] / (σ_A×√T)
其中 V_A = 公司资产市值（由股权市值+负债通过B-S方程迭代求解）
D = 违约点 = 短期债务 + 0.5×长期债务 = st_borr + 0.5×lt_borr
σ_A = 资产波动率（由σ_E×E/V_A迭代）
σ_E = 过去252日股权日收益率标准差 × √252
E = 总市值(daily_basic.total_mv×10000)
μ_A ≈ 无风险利率(shibor_lpr.lpr_1y)
T=1年
高DD→低违约概率→看多（作为质量因子）
- **逻辑**：将市场价格信息（股权波动率/市值）融入财务困境度量，比纯财务比率更前瞻。DD下降是市场提前定价财务风险的信号，比Z-Score对短期风险更敏感。特别适合A股机构主导市场——机构定价能力强，DD能更快反映信用恶化。
- **数据输入**：total_mv(daily_basic), close(daily), lt_borr+st_borr(balancesheet,季度), shibor_lpr(无风险利率)
- **tushare 端点**：daily_basic, daily, balancesheet, shibor_lpr
- **A股证据/陷阱**：DD计算需迭代求解B-S方程(牛顿法)，计算量较大但可批量化。A股特有：涨跌停板使日收益率截断，σ_E会被低估——建议用20日ATR/close替代（或剔除连续涨停区间）。T+1制度使σ_E不含当日，需用前一日收盘计算。退市制度改革后，DD对真实退市风险预测力增强。Stata/Python实现方案知乎已有详细教程。
- **机构相关度**：极高——机构信用分析/风险管理部门标配，DD是CDS定价基础。
- **出处**：Merton, R.C. (1974). On the Pricing of Corporate Debt. JF 29(2)., KMV公司模型(Kealhofer, McQuown, Vasicek 1993), 知乎: Credit Risk信用风险(二)结构模型与KMV违约距离 https://zhuanlan.zhihu.com/p/660185124, 知乎: Stata如何构建企业违约距离变量 https://zhuanlan.zhihu.com/p/614566910

## 11. DuPont ROE Decomposition Quality
**别名**：三层杜邦拆解/经营杠杆分离  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：年报/季报更新，持有6-12个月；作为ROE因子的质量调节项。 · **方向**：经营驱动ROE占比高→看多；杠杆驱动占比高→折扣

- **定义/公式**：ROE = 净利率 × 资产周转率 × 权益乘数
= (net_profit/revenue) × (revenue/total_assets) × (total_assets/total_equity)
质量版杜邦分解(分离经营vs财务): ROE = NOPAT_Margin × NOA_Turnover + Leverage_Contribution
其中 NOPAT_Margin = NOPAT/Revenue; NOA_Turnover = Revenue/NOA
高"经营杠杆贡献占比"(NOPAT_Margin×NOA_Turnover/ROE>0.7) → 质量驱动型ROE → 看多
低占比（主要靠财务杠杆提升ROE）→ 质量折扣
- **逻辑**：同样的ROE水平，经营驱动 vs 财务杠杆驱动有本质差异：前者可持续，后者高风险。A股地产/基建公司高杠杆ROE被高估，剥离后经营质量暴露。机构分析师用此拆解判断ROE可持续性。
- **数据输入**：net_profit(income), revenue(income), total_assets(balancesheet), total_equity(balancesheet), operate_profit(income), financial_exp(income), total_liab(balancesheet)
- **tushare 端点**：income, balancesheet, fina_indicator
- **A股证据/陷阱**：华泰证券2020金工报告系列: 改进杜邦分解(净经营资产净利率+杠杆贡献率)区分能力显著优于简单ROE。国信证券2024: ROE需多角度拆分，综合考虑非经常损益和财务杠杆。陷阱：金融股ROE拆解需不同框架（利差替代毛利率）；小市值公司分母权益可能极小导致ROE异常，需做分位数截断。
- **机构相关度**：极高——基本面机构研究的标准框架，与"PB-ROE估值体系"完全对接。
- **出处**：华泰证券金工2020: PB-ROE模型理解 https://crm.htsc.com.cn/doc/2020/10750101/7bbe6d23-078d-428b-acab-4418ff9bc34f.pdf, 国信证券2024: 探寻股价回报的源动力 https://finance.sina.com.cn/roll/2024-07-31/doc-incfysvm9263286.shtml

## 12. FCFF/IC (自由现金流投入资本回报)
**别名**：FCFFIC/自由现金流质量比  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：TTM平滑季度波动，持有6-12个月；系统已有L5.cf.fcf dp_id可直接复用。 · **方向**：高FCFFIC→看多

- **定义/公式**：FCFFIC = FCFF_TTM / Invested_Capital
FCFF_TTM = 近4季度TTM自由现金流 = 经营现金流 − 维持性资本支出
≈ n_cashflow_act_TTM − capex_TTM (其中capex=购建固定资产无形资产净额)
或用 fina_indicator.fcff 字段(已计算)
IC = 股东权益 + 有息负债 − 现金 = total_equity + (st_borr+lt_borr) − monetary_fund
高FCFFIC→看多
- **逻辑**：FCFF消除了盈余管理影响，是企业真实产生现金流能力的最纯粹体现。相比ROIC使用NOPAT(含应计)，FCFFIC全程用现金流，对A股盈余管理更鲁棒。富时中国A股自由现金流聚焦指数(LSEG 2025)就采用此逻辑。
- **数据输入**：fcff(fina_indicator.fcff或自算), n_cashflow_act(cashflow), c_pay_acq_const_fiolta(资本支出,cashflow), total_equity(balancesheet), lt_borr+st_borr(balancesheet), monetary_fund(balancesheet)
- **tushare 端点**：cashflow, balancesheet, fina_indicator
- **A股证据/陷阱**：LSEG富时中国A股自由现金流聚焦指数2025: 自由现金流策略在A股2020-2024年显著跑赢市场。量化论坛研报2026: FCFFIC用TTM平滑后IC稳定性优于单季度。注意：tushare cashflow表free_cashflow为YTD累计值，需做TTM季度还原（系统_derive_ttm_fcf()函数已实现）。
- **机构相关度**：高——"自由现金流"是2024-2025年A股机构投资者最关注的质量指标，机构主题ETF大量布局。
- **出处**：LSEG富时中国A股自由现金流聚焦指数规则 2025 https://www.lseg.com.cn/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-china-a-free-cash-flow-focus-index-ground-rules-chinese.pdf, 量化论坛研报: 财务质量类因子改进 2026 https://news.qq.com/rain/a/20260507A06G3600, 新浪财经2025: 投资新范式 自由现金流策略 https://finance.sina.com.cn/stock/wbstock/2025-04-21/doc-inetxsmv6211385.shtml

## 13. SUE (标准化非预期盈余)
**别名**：盈余惊喜/SUE/PEAD驱动因子  
**映射**：`expectation_gap` · **可行性**：GREEN · **把握**：high · **周期**：业绩公告后2-8周最强（覆盖系统2-4周窗）。 · **方向**：高正SUE(实际超预期)→看多；大负SUE→风险折扣

- **定义/公式**：SUE = (EPS_actual − EPS_expected) / σ_forecast_error
方法A-时间序列预期: EPS_expected = EPS_t-4 + drift
  SUE = (eps_t − eps_t-4 − mean_drift) / std(eps_t-k − eps_t-k-4, k=1..8)
方法B-分析师预期: SUE = (eps_t − analyst_consensus_eps_t) / |analyst_consensus_eps_t|
  analyst_consensus来自report_rc表的eps字段(mean_eps)
A股快报版: 用express.net_profit_YoY的超预期部分
PEAD: 在公告日后持有20-60交易日捕捉漂移
- **逻辑**：Bernard & Thomas(1989): 市场对盈余信息消化不完全，导致公告后20-60天的异常漂移。A股散户比例历史较高时PEAD更强；随机构化推进(2019+)PEAD衰减但仍存在，尤其在信息传播慢的中小盘股。
- **数据输入**：eps(fina_indicator或income), eps_t-4(同比对比), report_rc.eps(分析师预期共识), express.net_profit(快报净利润), ann_date(披露日期,disclosure_date)
- **tushare 端点**：fina_indicator, income, report_rc, express
- **A股证据/陷阱**：2024年电子与信息科学期刊: A股一季报样本中，SUE选取为市场异象代理变量，PEAD效应显著存在。A股特有：①涨跌停板导致PEAD在公告日当天无法完全释放，漂移延长至5-10天后；②T+1制度使公告当日无法当天反应完全；③快报(express)比正式年报早1-2月，建议以express.ann_date作为事件日触发SUE。
- **机构相关度**：高——分析师修正跟踪是机构研究核心流程，SUE直接量化预期差。
- **出处**：Bernard, V.L., Thomas, J.K. (1989). Post-Earnings-Announcement Drift. JFQA., 2024电子与信息科学Vol.41: A股PEAD研究 https://cdn.sciengine.com/, Frontiers 2024: PEAD.txt Post-Earnings-Announcement Drift Using Text https://www.frbsf.org/research-and-insights/publications/

## 14. Earnings Revision Momentum (盈余预测修正动量)
**别名**：分析师修正动量/预期修正因子  
**映射**：`expectation_gap` · **可行性**：GREEN · **把握**：high · **周期**：2-8周（完全覆盖系统2-4周窗）——是本族中最适合2-4周预测窗的因子之一。 · **方向**：正修正动量(EPS上调)→看多

- **定义/公式**：ERM = Σ(EPS_revision_i × w_t) / |EPS_prior|
其中 EPS_revision_i = (eps_current_i − eps_prior_i) / |eps_prior_i|
w_t = 时间权重(近期修正权重更高)
用report_rc表: 按ts_code聚合同一季度预测修正
ERM = (mean_eps_last30d − mean_eps_prev30d) / abs(mean_eps_prev30d)
正ERM(上调) → 看多
- **逻辑**：分析师盈余预测修正包含大量非公开调研信息，尤其在A股机构主导市场中，大型券商分析师的集体上调是机构买入的先行指标。预测修正动量在1-8周内有显著预测力。
- **数据输入**：report_rc(券商盈利预测), report_rc.eps, report_rc.ann_date, report_rc.est_date
- **tushare 端点**：report_rc
- **A股证据/陷阱**：本系统已有L5.fcst.revisions和L5.surprise.sell_side dp_id，report_rc接口已接入。A股特有：①卖方分析师倾向保守预测以维持关系，修正往往滞后于真实信息——上调比下调更可靠；②需区分覆盖分析师数量（小盘股仅1-2个分析师时修正信噪比低）；③季报快报期（4月/10月）修正信号最强。
- **机构相关度**：极高——直接反映机构信息网络中卖方预期变化，是机构之间信息传导的核心机制。
- **出处**：Hawkins, E.H., Chamberlain, S.L., Daniel, W.E. (1984). Earnings Expectations and Security Prices. FAJ., 本系统report_rc接口(L5.fcst.revisions已接入)

## 15. Ohlson O-Score (财务困境Logit模型)
**别名**：奥尔森O分/破产概率Logit  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：年报级别，有效期12个月；可用快报季度数据做中间更新。 · **方向**：低O-Score(低破产概率)→看多；高O-Score→风险折扣

- **定义/公式**：O-Score = −1.32 − 0.407×X1 + 6.03×X2 − 1.43×X3 + 0.076×X4 − 1.72×X5 − 2.37×X6 − 1.83×X7 + 0.285×X8 − 1.72×X9 − 0.521×X10
X1=ln(total_assets/GNP_price_index)→用ln(total_assets/10e8)近似
X2=total_liab/total_assets
X3=(current_assets_−current_liab)/total_assets
X4=current_liab/current_assets(流动比率倒数)
X5=1 if total_liab>total_assets else 0
X6=net_profit/total_assets
X7=cashflow_from_ops/total_liab
X8=1 if net_profit<0 for 2 consecutive years else 0
X9=(net_profit_t−net_profit_t-1)/(|net_profit_t|+|net_profit_t-1|)
P_distress = 1/(1+exp(−O_Score))
高O-Score(高P_distress) → 风险折扣
- **逻辑**：Ohlson(1980)用Logit方法改进Altman,用9个财务指标预测破产，比Z-Score更灵活。在A股结合ST制度：O-Score高→ST概率高→股价表现差（退市风险溢价）。
- **数据输入**：total_assets, total_liab, current_assets, current_liab, net_profit, n_cashflow_act(经营现金流)
- **tushare 端点**：balancesheet, income, cashflow
- **A股证据/陷阱**：草莓科研2023: A股1991-2023年Z-Score+O-Score数据集已有完整构建记录。O-Score在A股的预测力受ST制度影响：中国特有的财务救助机制（地方政府注资、债务豁免）使实际破产率低于O-Score预测。建议将O-Score作为ST风险预警信号而非破产预测，与st表结合使用。需排除金融股（银行杠杆率正常很高）。
- **机构相关度**：中——机构内部信用研究使用，但不如Merton DD前瞻性强。
- **出处**：Ohlson, J.A. (1980). Financial Ratios and the Probabilistic Prediction of Bankruptcy. JAR 18(1)., 草莓科研: 2023-1991上市公司财务困境Z-Score+O-Score数据 https://www.caomeikeyan.com/forum.php?mod=viewthread&tid=488

## 16. Gross Margin Trend (毛利率趋势变化)
**别名**：毛利率改善因子  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：季报更新后1-3个月；2-4周窗内是本系统fundamental_score的边际调节项。 · **方向**：毛利率同比/环比改善→看多

- **定义/公式**：GM_Trend = grossprofit_margin_t − grossprofit_margin_t-4 (同比季度变化)
或 GM_Accel = (GM_t − GM_t-1) − (GM_t-1 − GM_t-2) (环比加速)
TTM版: GM_Trend_TTM = (gross_profit_TTM / revenue_TTM) − (gross_profit_TTM_4Q_ago / revenue_TTM_4Q_ago)
在fina_indicator中直接用 q_gsprofit_margin(单季毛利率)同比变化
- **逻辑**：毛利率趋势改善反映定价能力提升或成本下降，是竞争格局好转的先行信号。区别于GPOA的截面高低，GM_Trend更关注边际变化，与基金经理"边际改善"选股逻辑高度一致。
- **数据输入**：q_gsprofit_margin(单季毛利率,fina_indicator), grossprofit_margin(fina_indicator), revenue(income), cogs(operate_cost,income)
- **tushare 端点**：fina_indicator, income
- **A股证据/陷阱**：BigQuant 2024: 毛利率单因子IC在2024年表现偏弱(近0)但作为组合成分稳定。PanAgora A股研究: 盈利能力改善类因子在A股相比截面水平因子更有效，尤其在市场风格切换时。陷阱：季节性强的行业（农业/旅游）季度毛利率波动大，需同比而非环比；ST股毛利率异常波动需剔除。
- **机构相关度**：高——卖方研究中"毛利率拐点"是最常见的推荐逻辑之一，本因子量化了这一逻辑。
- **出处**：BigQuant 2024有效因子研究 https://bigquant.com/square/paper/65a32e79-39be-4c90-83ed-0b4067daebd4, PanAgora Factor Investing China A-share