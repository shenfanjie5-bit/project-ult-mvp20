# 因子族：multifactor_models

> 多因子模型族对本系统的核心价值在于：(1) 提供行业+市值中性化的正交残差信号，可显著提升 fundamental_score 和 expectation_gap 的截面区分度；(2) IC/ICIR 加权合成框架可将现有分散的单因子得分统一为最优线性组合，直接替换系统当前的等权加总逻辑；(3) 因子拥挤度监控可实时感知量化策略拥挤风险，驱动 risk_discount。最值得优先接入的 3 个因子：① ICIR 最优加权合成器（将现有 L1-L6 基本面因子合成为 fundamental_score，立竿见影）；② Barra CNE6 行业+市值二阶中性化（消除 fundamental_score 的行业/规模偏差，任何单因子入库前都需要）；③ 融资余额变化率因子（margin_chg_5d，tushare margin 端点直接可算，填充 capital_sentiment 空白）。

共 18 条。


## 1. ICIR-Optimal Factor Synthesis Weight
**别名**：最优ICIR因子合成权重  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：high · **周期**：月度再平衡（参数 Sigma_IC 用 24 个月滚动窗口），信号持有 2-4 周 · **方向**：合成因子高值看多

- **定义/公式**：对 N 个因子截面标准化后，滚动计算各因子的 IC 向量 ic_t 与协方差矩阵 Sigma_IC。最优权重 w* = Sigma_IC^{-1} * mu_IC / (1^T Sigma_IC^{-1} mu_IC)，其中 mu_IC = EMA(ic_t, half_life=12个月)。合成因子 F_composite_t = sum_i w*_i * f_i_t（各因子先做行业+市值中性化 + 去极值 + 截面 z-score 标准化）。IC 胜率阈值：单因子 Rank IC 绝对值均值 < 0.02 时权重压缩至 0。
- **逻辑**：在多因子框架下，IC 加权（等同于 OLS）忽略因子间相关性；ICIR 最大化等价于信噪比最优的线性组合，能在因子拥挤期自动降低权重已衰减的因子，等权合成在 A 股高波动截面下噪声大、鲁棒性差。
- **数据输入**：各单因子截面值, 因子IC时序, 因子间IC相关矩阵
- **tushare 端点**：fina_indicator, daily_basic, report_rc, moneyflow
- **A股证据/陷阱**：华安证券 2024 年研报：三维择时框架下 ICIR 优化合成使沪深 300 增强年化超额升至 15.32%，IR 提升至 3.46；行业市值中性化是前置条件，剔除 ST 及近 90 日停牌股；涨跌停日因子值截断处理（T+1 约束导致当日信号次日才可交易）。机构为主市场中，低相关性的基本面与资金因子组合效果最佳。
- **机构相关度**：高 — 机构用 Barra 框架做归因，ICIR 优化合成与之对齐，便于沟通 alpha 来源
- **出处**：华安证券《破解 Alpha 投资困境：因子择时方案再探索》2024Q3, 星火证券《借因子组合之力，优化 Alpha 因子合成》2019, Grinold & Kahn Active Portfolio Management (2000)

## 2. Barra CNE6 Industry + Size Two-Step Neutralization
**别名**：行业+市值二阶中性化残差  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：high · **周期**：每次截面计算（周频或月频重算），无单独持有周期 · **方向**：残差高值方向由原始因子决定

- **定义/公式**：对任意原始因子 f_raw，在每个截面 t 做截面 WLS 回归：f_raw_i = alpha + beta_size * ln(mktcap_i) + sum_k gamma_k * I_{industry_i=k} + epsilon_i，其中权重 w_i = sqrt(mktcap_i)（市值开方加权），回归残差 epsilon_i 即为中性化后因子值。后续再做 3 sigma 截断 + 截面 z-score。行业分类使用申万一级 28 个行业（index_member_all 端点）或中信一级行业（ci_daily）。
- **逻辑**：A 股强行业轮动效应和小盘溢价会让未中性化因子暗含行业/规模赌注，与机构基准（中证 800/沪深 300）产生不可控 tracking error；Barra CNE6 的核心工程就是将风格因子正交分离，本步骤是所有截面因子入库前的必要预处理。
- **数据输入**：股票总市值/流通市值, 申万一级行业分类, 原始因子截面值
- **tushare 端点**：daily_basic, index_member_all, index_classify, ci_daily
- **A股证据/陷阱**：江海证券 2024 年研报（CNE6 实测）：行业市值中性化后非中心化交叉验证 R² 均值 0.32，波动率和流动性因子 IC 显著提升；未中性化时，小市值偏倚会在 ST 剔除后仍然残存；涨跌停股票当日因子值应剔除或置空（T+1 不可操作）。
- **机构相关度**：极高 — 机构组合基准敏感，行业偏离 TE 是首要风控指标
- **出处**：MSCI Barra CNE6 Model Documentation (2018), 江海证券《量价类因子实测，基于 Barra CNE6》2024-04-15, BigQuant Barra CNE6 因子构建 GitHub (2024)

## 3. Fama-French Five-Factor Composite (FF5)
**别名**：Fama-French五因子合成暴露  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：月度重平衡，因子持有 1-3 个月 · **方向**：RMW 高分位 + CMA 低分位（保守投资）+ HML 高分位看多

- **定义/公式**：五因子：MKT=Rm-Rf；SMB=小盘减大盘（按市值三分位，6 个投资组合的平均超额收益差）；HML=高BM减低BM（按 B/P 三分位）；RMW=高盈利减低盈利（按 Operating Profitability=毛利/总资产三分位）；CMA=低投资减高投资（按总资产变化率三分位）。单股 alpha = r_i - (beta_MKT*MKT + b_SMB*SMB + b_HML*HML + b_RMW*RMW + b_CMA*CMA)，以 36 个月滚动窗口 OLS 估计因子暴露。选股用 RMW 高分位 + CMA 保守投资 + HML 价值联合筛选。
- **逻辑**：RMW（盈利质量）和 CMA（保守资产扩张）捕捉 Investment CAPM 逻辑：盈利强且扩张保守的公司 NPV 高，预期回报正；对应 A 股中机构偏好的白马股。
- **数据输入**：总资产, 毛利润/营业收入, 净资产账面价值, 总市值, 总资产同比变化
- **tushare 端点**：fina_indicator, balancesheet, income, daily_basic
- **A股证据/陷阱**：Atlantis Press 2023 研究（2006-2023 A 股）：五因子 GRS 检验下模型解释力优于三因子，但 HML 在 A 股整体 t 值较弱（市场散户驱动，价值溢价不稳定）；RMW 在机构持股比高的公司中效力更强；CMA 在 2022-2024 年受政策性扩张干扰（国企定向增发）。需剔除 ST、财务造假预警、年报滞后 PIT 处理（4月30日后才可用上年度数据）。
- **机构相关度**：高 — 外资和 FOF 常用 FF5 做业绩归因，alpha 相对 FF5 比相对 CAPM 更干净
- **出处**：Fama & French (2015) JFE, Analysis of FF5 Applicability in Chinese A-Share Market, Atlantis Press ICEDBC-23 (2023), ResearchGate: Comparison FF3 vs FF5 in China (2023)

## 4. q-Factor: ROE and Investment Factor
**别名**：Hou-Xue-Zhang q因子(ROE+投资因子)  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：季度财报更新后重算，持有 1-3 个月 · **方向**：高 ROE + 低 I/A 看多

- **定义/公式**：q 模型四因子：MKT（市场）、ME（规模，同 SMB）、I/A（资产扩张保守性，I/A_i = (TA_t - TA_{t-1})/TA_{t-1}，低 I/A 做多）、ROE（季度 ROE = 净利润 / 期初净资产，高 ROE 做多）。具体：I/A 因子 = 低投资三分位组合平均收益 - 高投资三分位组合平均收益；ROE 因子 = 高 ROE 三分位 - 低 ROE 三分位，按市值加权构建。单股因子暴露用 5 年滚动 OLS，合成信号 = w_ROE * zROE_i + w_IA * zIA_i（ICIR 加权）。
- **逻辑**：Investment CAPM（Zhang 2017）：高 ROE 代表高 NPV 项目已实现盈利，低投资说明内部项目 hurdle rate 高 → 预期回报高；在机构主导市场中，高 ROE + 保守扩张的公司获得机构持仓溢价。
- **数据输入**：净利润(季报), 净资产(期初), 总资产(同期), 总市值
- **tushare 端点**：fina_indicator, balancesheet, daily_basic
- **A股证据/陷阱**：q 模型 ROE 因子在 A 股的 A 股月度 RankIC 约 0.06-0.08（衡泰技术 2023 年年度因子分析报告），优于 FF5 RMW；I/A 因子受国企政策性投资干扰（尤其基建行业），建议行业中性化后使用；季报披露延迟 PIT（一季报 4/30，半年报 8/31，三季报 10/31，年报 4/30 次年）需严格遵守。
- **机构相关度**：高 — 与机构 ROE 选股框架天然对齐
- **出处**：Hou, Xue, Zhang (2015) RFS: Digesting Anomalies, Zhang (2017): The Investment CAPM, 衡泰技术《2023年A股市场因子分析》

## 5. Piotroski F-Score (A-Share Adapted)
**别名**：Piotroski F分 质量打分  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：年度财报更新后触发（每年约 4-5 月），持有 1 年；可降低至半年报触发 · **方向**：高 F 分看多

- **定义/公式**：9 项 0/1 指标求和（0-9 分）：盈利类(4项)：ROA>0得1分；经营现金流/总资产>0得1分；ROA同比提升得1分；Accruals=经营现金流/总资产 - ROA>0得1分；财务结构(3项)：长期负债/总资产同比下降得1分；流动比率同比提升得1分；未新增股份融资(无新增普通股)得1分；效率(2项)：毛利率同比提升得1分；资产周转率同比提升得1分。F≥7 为高质量，F≤3 为低质量。A 股适配：剔除 ST 和退市预警；使用最新披露年报（PIT，披露日起生效）。
- **逻辑**：Piotroski(2000)原理：财务质量好转的公司（9 个维度全面改善）会被市场持续低估，买入 F≥7 + 卖出 F≤3 的多空对冲。A 股机构资产定价能力上升后，该信号捕捉机构从散户手中发现隐藏价值改善的过程。
- **数据输入**：ROA, 经营现金流, 长期负债, 流动比率, 股本, 毛利率, 资产周转率
- **tushare 端点**：fina_indicator, balancesheet, cashflow, income
- **A股证据/陷阱**：A 股实证：F 分区分力存在但偏粗（知乎量化实战 2021）；F≥7 策略在 2015-2020 年年化超额约 8-12%，2021 后因机构持仓集中于 ROE 白马导致 F 分已 priced-in；建议作为过滤器（F≤3 直接排除）而非主因子；需叠加行业中性化避免集中于金融行业（其盈利模式导致 Accruals 指标失真）。
- **机构相关度**：中高 — 机构常用综合质量评分做选股初筛
- **出处**：Piotroski (2000) JAR: Value Investing: Use of Historical Financial Statement Information, 知乎《Quantametal 基本面量化初探：从 Piotroski F-Score 开始》2020

## 6. Carhart Momentum Factor (12-1 Month)
**别名**：Carhart动量因子 / 中期价格动量  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：月度重平衡，2-3 个月持有；中期（6 个月）动量最稳定 · **方向**：高动量（过去赢家）看多

- **定义/公式**：MOM_12_1_i = P_{t-1} / P_{t-12} - 1（跳过最近一个月，防止短期反转污染）。截面 z-score 标准化后，按 ICIR 加权合入组合。A 股改进版：使用过去 12 个月中选取 t-2 到 t-12 共 11 个月收益（月频），剔除最近 1 个月；或用 t-2 到 t-6（中期，6 个月）以规避 A 股强反转问题。可叠加行业内动量（在同行业内排序，消除行业轮动的截面影响）。
- **逻辑**：Carhart(1997) UMD 因子捕捉过去赢家持续跑赢的趋势；机构羊群效应（慢速信息扩散）是 A 股动量来源；但零售投资者主导时段反转效应压制动量，2017 年后机构化提升使动量有效性恢复。
- **数据输入**：月度收盘价（复权）, 月度收益率
- **tushare 端点**：monthly, daily
- **A股证据/陷阱**：证券市场导报 2023 年研究：机构持股比例作为调节因子，机构比高时动量效应增强（t≈3.2）；A 股 12-1 月动量 2010-2022 年年化多空约 12-15%，但 2021Q4-2022 受大宗转向打断；行业内动量比跨行业动量更稳定（开源金工 2024）；涨跌停股票跳过排序；退市风险股反转效应更强应剔除。
- **机构相关度**：中 — 机构基金经理用动量做行业轮动，个股动量信号辅助；外资动量交易风格显著
- **出处**：Carhart (1997) JF: On Persistence in Mutual Fund Performance, 证券市场导报 2023 年 11 月：投资者结构与股票预期收益, 开源金工《市场微观结构观察与 2023 年以来的高频因子回顾》2024

## 7. IVOL: Idiosyncratic Volatility (Low-Vol Anomaly)
**别名**：特异波动率因子 / 低波异象  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：high · **周期**：月度再平衡，持有 1-3 个月 · **方向**：IVOL 低值看多（低波溢价）

- **定义/公式**：FF3 模型残差标准差为特异波动率：IVOL_i = std(epsilon_{i,d})，epsilon_{i,d} = r_{i,d} - alpha_i - beta_i*MKT_d - s_i*SMB_d - h_i*HML_d，使用过去 T=21 个交易日（1 个月）日度收益估计。截面标准化后，IVOL 低值即低波因子（做多低特异波动率股票）。替代方案：直接用日收益率过去 21 日标准差（total vol）做因子，相关性 > 0.9。
- **逻辑**：Ang et al.(2006) 发现 IVOL 高的股票未来收益反而更低（低波异象）；A 股解释：散户博彩性偏好使高 IVOL 股票被高估；机构限制卖空使错误定价无法纠正；保险/银行理财偏好低波红利股（2024 年 OCI 账户配置大幅增加）。
- **数据输入**：日度收益率（过去 21 日）, Fama-French 因子日度值
- **tushare 端点**：daily, daily_basic, stk_factor_pro
- **A股证据/陷阱**：中国资本市场研究网 2025 年：低波动率指数年化超额收益 5.41%，显著优于红利指数（1.60%）；2024 年险资 OCI 账户低波权益配置同比增 75.74%，成为最大机构增量资金；低波因子 2024 年 IC 胜率约 62%，是全年表现最稳定的大类因子（2024 A 股因子大解析）；A 股小盘高波股涨跌停截断需特别处理（虚假低波）。
- **机构相关度**：极高 — 险资/银行理财是 2024-2025 最大增量机构资金，低波是其核心约束
- **出处**：Ang, Hodrick, Xing, Zhang (2006) JF: The Cross-Section of Volatility and Expected Returns, 中国资本市场研究网《A股低波红利指数及产品的投资价值与发展趋势》2025, 知乎《低波因子：真正的大盘选股终结者》2024

## 8. Northbound (HK Connect) Net Flow Factor
**别名**：北向资金净流入因子  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：5 日动量信号，持有 2-4 周 · **方向**：北向净买入看多

- **定义/公式**：NBF_5d_i = sum_{t-4}^{t}(hk_hold_chg_{i,d}) / avg_daily_volume_{i,60d}，其中 hk_hold_chg 为每日北向持股变化量（股数）；量化时用 hk_hold 端点中 ratio_float_a（占流通 A 股比例）日环比变化，或 hold_amount 日变化额 / 流通市值，构造 5 日累积净买入比例。截面行业+市值中性化后使用。注意：2024年8月后北向数据降频为季度披露，需用 ETF 资金流因子作为替代代理。
- **逻辑**：北向资金（QFII/沪深港通外资）信息优势显著（彭博/JP Morgan 研究：北向净买入超额收益 IC≈0.08-0.12）；外资偏好高质量、低估值的蓝筹股，其买入行为具有价格发现功能且散户跟随（羊群效应放大信号）。
- **数据输入**：北向持股变化（hk_hold/moneyflow_hsgt）, 流通市值, 日均成交量
- **tushare 端点**：hk_hold, moneyflow_hsgt
- **A股证据/陷阱**：金融市场研究 2024 年 1 月《北向资金是 A 股的风向标吗》：北向净买入行为对投资者情绪有显著影响，市场上涨时北向多头信号放大；2024Q3 起数据降频，建议结合海外 A 股 ETF 资金流（1904 只，规模 3124 亿）替代；国联证券 2024 年 12 月：北向因子在沪深 300 成分股中有效性高于中小盘；需剔除 ST 及北向零持股股票。
- **机构相关度**：极高 — 外资是 A 股最重要的价格发现机构，北向持仓方向代表全球机构共识
- **出处**：金融市场研究 2024-01《北向资金是 A 股的风向标吗》, 国联证券金工 2024-12 周报

## 9. Margin Financing Change Rate Factor
**别名**：融资余额变化率因子 / 杠杆资金信号  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：5 日变化率信号，持有 2-3 周；高水位警告持有周期缩短至 1 周 · **方向**：5日融资余额正增长看多（但极端高位看空）

- **定义/公式**：MRG_5d_i = (margin_balance_{i,t} - margin_balance_{i,t-5}) / margin_balance_{i,t-5}（5 日融资余额变化率）；或用 MRG_buy_ratio_i = margin_buy_amount_{i,t} / total_volume_{i,t}（当日融资买入占总成交额比例）。截面行业+市值中性化后，ICIR 加权。融资余额绝对水平（margin_balance_i / float_mktcap）可作为杠杆拥挤度风险指标。
- **逻辑**：融资余额增长反映有信念投资者加杠杆买入（情绪强度信号）；融资买入占比高代表短期资金追涨，与后续 2 周收益正相关（信息效应 > 流动性效应）；但极端高融资余额/市值比（>5%）预示强制平仓风险（反转因子）。
- **数据输入**：融资余额（margin_balance）, 融资买入额（margin_buy）, 流通市值, 成交额
- **tushare 端点**：margin, margin_detail, daily_basic
- **A股证据/陷阱**：东吴证券金工 2024-03：融资余额日度因子在中证 500 成分股年化多空 IC 约 0.07；2024 年融资余额突破 1.99 万亿后出现明显短期预测衰减（拥挤迹象）；建议用 5 日变化率而非绝对水平；需结合每日融资买入占比（margin_detail）区分追涨（短空）与价值加仓（短多）。
- **机构相关度**：中高 — 融资客中散户居多，但融资买入集中于机构持仓股时信号质量提升
- **出处**：东吴证券金工《专题报告 20240305》, 开源金工《市场微观结构观察 2023 年以来》BigQuant 2024

## 10. Chip Distribution Profitability Ratio Factor
**别名**：筹码获利比例因子 / 成本分布信号  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：短期 3-10 日（博弈层面信号） · **方向**：WIN_RATIO < 30% 且价格突破筹码密集区时看多；WIN_RATIO > 75% 时看空（压力位）

- **定义/公式**：WIN_RATIO_i = 当前价格下方的筹码比例，即 P(成本 < P_current)，由每日筹码分布（cyq_perf 端点的 cost_5pct/cost_85pct/weight_avg）插值估算：WIN_RATIO ≈ (P_t - cost_5pct_t) / (cost_85pct_t - cost_5pct_t)，截断至 [0,1]。更精确：使用 cyq_perf.profit 字段（获利盘比例直接给出）。高获利比例（>70%）时信号：已充分盈利者倾向兑现 → 短期阻力信号（看空）；低获利比例（<30%）+ 价格站上筹码密集区：解套盘压力释放 → 看多。
- **逻辑**：筹码理论：获利盘过高时卖压强（套现心理）；获利盘过低时解套盘压制上涨；筹码均匀分布（集中度低）时趋势延续性强。对应机构分析框架中的成本基础分析（cost basis analysis）。
- **数据输入**：cyq_perf 筹码分布字段（cost_5pct, cost_85pct, weight_avg, profit）, 日收盘价
- **tushare 端点**：cyq_perf
- **A股证据/陷阱**：BigQuant 2024：筹码集中度因子（价格区间宽度比）在全 A 股年化 IC 约 0.06；获利比例因子（profit 字段）在短期（5-10 日）RankIC 约 0.04-0.06，在超跌股中效力更强；2024 全年低波+筹码集中因子联合使用年化多空约 11%；T+1 制度下筹码数据需用前一日值，避免使用当日收盘前数据。
- **机构相关度**：中 — 机构内部用筹码分析评估建仓/减仓成本分布，但不作为主要量化信号
- **出处**：tushare cyq_perf 文档, BigQuant《筹码集中度》2024, 2024 A 股因子分析：量化投资大类因子表现

## 11. Analyst Earnings Revision Momentum (ARM)
**别名**：分析师盈利预测修正动量  
**映射**：`expectation_gap` · **可行性**：GREEN · **把握**：med · **周期**：4 周修正窗口，持有 4-8 周（PEAD 效应持续约 60 日） · **方向**：ARM 上调看多

- **定义/公式**：ARM_i = (EPS_consensus_{t} - EPS_consensus_{t-4w}) / abs(EPS_consensus_{t-4w})，即一致预期 EPS 过去 4 周的变化率（report_rc 端点的 eps 预测均值/中位数）。更精细版本：SUE = (Actual_EPS_{Q} - Expected_EPS_{Q-1}) / std(forecast_errors_trailing)，其中 Expected_EPS 用最近一期分析师预测均值。截面行业+市值中性化 + ICIR 加权。
- **逻辑**：分析师预测修正（上调）领先市场重估：预期修正动量捕捉机构信息优势的传播过程（sell-side 信息→买方行动→价格）。A 股机构化加深后 ARM 有效性提升，因分析师覆盖广度和预测更新频率上升（SUE/PEAD 效应显著）。
- **数据输入**：一致预期 EPS（report_rc.eps）, 预测日期, 实际 EPS 季报值
- **tushare 端点**：report_rc, fina_indicator, express
- **A股证据/陷阱**：东方证券因子系列 87 期：分析师研报类 alpha（研报数量+预测修正）在全 A 年化 IC 约 0.08-0.10，研报发布后 5 日超额显著；但 2022 年后分析师覆盖同质化（券商 AI 批量覆盖）导致部分 ARM 因子拥挤；建议使用非共识分析师（覆盖家数少但准确率高）的修正幅度加权；ST 股分析师覆盖极少，需剔除。
- **机构相关度**：极高 — 机构投资者直接消费卖方研报，预测修正信号反映机构共识变化
- **出处**：东方证券《因子选股系列之八十七：分析师研报类 alpha 增强》2024-10, Ball & Brown (1968): An Empirical Evaluation of Accounting Income Numbers

## 12. Factor Crowding Score (FCS)
**别名**：因子拥挤度评分 / 量化拥挤风险  
**映射**：`risk_discount` · **可行性**：YELLOW · **把握**：med · **周期**：月度计算拥挤度评分，实时风控监控 · **方向**：FCS 高值（因子拥挤）→ 对应因子权重下调（用于 risk_discount）

- **定义/公式**：FCS_f_t = corr(factor_exposure_rank_f, institutional_holding_rank_i, t) across stocks，即当前因子暴露截面排序与机构持仓排序的 Spearman 相关系数。高 FCS（>0.6）表示该因子被机构大量持仓（拥挤），未来因子收益衰减概率高。替代计算：拥挤度 = factor_loading_dispersion_{t} / factor_loading_dispersion_{trailing_60m}（当前分散度相对历史分位数）；或对 stk_holdernumber 数据构造股东人数变化：人数骤降 + 筹码集中 → 机构集中持仓信号。
- **逻辑**：MSCI 拥挤度模型（2020）：多因子策略在大量资金涌入后，因子暴露股票被抬至相对高估，因子拥挤时解仓风险（拥挤崩塌）导致系统性损失。A 股 2024 年初小盘量化拥挤崩塌事件（微盘股雪崩）是典型案例。
- **数据输入**：机构持仓比例（stk_holdertrade）, 因子截面暴露, 股东人数变化（stk_holdernumber）
- **tushare 端点**：stk_holdertrade, stk_holdernumber, pledge_stat
- **A股证据/陷阱**：中国基金报 2024-03：2023 年底小盘量化拥挤度达五年高峰，2024 年 2 月微盘股系统性下跌；BigQuant MSCI 拥挤度模型文档：交易拥挤度（成交量加权持仓变化）是最领先的预警指标；A 股中 stk_holdernumber 季报披露频率低（季度），实时性弱，可用 cyq_perf 筹码集中度替代日频监控。
- **机构相关度**：极高 — 机构量化风控部门核心指标，防范量化策略集体平仓风险
- **出处**：MSCI《因子拥挤度分析模型》BigQuant 译本 2020, 中国基金报《中国量化基金面临的微盘股拥挤与流动性紧缩》2024-03

## 13. Factor Timing via Macro Regime (Factor Rotation)
**别名**：宏观体制因子择时 / 因子轮动  
**映射**：`NEW` · **可行性**：YELLOW · **把握**：med · **周期**：月度体制识别，因子权重月度更新；短期 2-4 周预测 · **方向**：体制利好时对应因子加权，体制不利时降权

- **定义/公式**：定义 3 个宏观状态变量：(1) 信用扩张 = SF_month(社融同比增速)，高于 12 个月均值为扩张；(2) 流动性宽松 = shibor_3m 低于 12 个月均值；(3) 风险偏好 = 上证综指 20 日收益率 > 0。构造 8 种体制组合，每种体制下计算 6 大因子（价值/动量/质量/低波/规模/盈利修正）的历史平均月 IC。当前体制下取 IC 最高的 2-3 个因子，提升其在 ICIR 合成中的权重（乘以择时倍数 k = 1 + 0.5 * IC_regime / IC_full_sample_mean）。
- **逻辑**：宏观体制决定哪类股票的现金流折现预期最易修正：信用扩张期价值/小盘占优（融资环境改善）；风险偏好高时动量因子强；流动性宽松时成长因子获溢价。因子择时能在不同市场环境中维持超额收益的稳定性。
- **数据输入**：社融同比数据（sf_month）, SHIBOR（shibor）, 上证/沪深 300 指数日收益, PMI（cn_pmi）
- **tushare 端点**：sf_month, shibor, cn_pmi, cn_m, index_dailybasic
- **A股证据/陷阱**：未来智库 2024 年 9 月：外生（宏观）+ 内生（因子自身动量）三维因子择时框架使沪深 300 增强年化超额升至 15.32%；2025 年 VZKOO 报告：不同市场体制下价量因子 vs 基本面因子的相对 IC 差距高达 3 倍；2025 年量化策略展望：高频量价因子在波动市（无明确体制）中超额显著，传统低频因子受压。信用/流动性双维度是 A 股最强宏观 regime 分类器。
- **机构相关度**：高 — 机构资产配置委员会用宏观框架决定风格偏配，与机构操作周期对齐
- **出处**：华安证券《因子择时方案再探索》2024-09, 未来智库《2025年量化研究系列：因材施策》2025, Asness et al. (2013): Value and Momentum Everywhere

## 14. LightGBM/GBDT Multi-Factor Synthesis
**别名**：LightGBM多因子非线性合成  
**映射**：`fundamental_score` · **可行性**：YELLOW · **把握**：med · **周期**：月度再平衡，预测 +4 周超额收益 · **方向**：模型高预测分值看多

- **定义/公式**：以行业市值中性化后的 N 个单因子 z-score 值为特征 X，以截面 t+20d（约 4 周）超额收益 y = r_{i,t+20d} - r_{benchmark,t+20d} 为标签，训练滚动 LightGBM 排序模型（LambdaRank 目标函数，或回归目标 MSE + 自定义 IC 损失）。滚动训练窗口 24 个月，预测窗口前滚 1 个月。特征重要性（feature importance by gain）提取各因子的非线性贡献。输出：股票排序分（0-1 之间的预测超额收益分位数）。防过拟合：5 折时序交叉验证，max_depth≤4，min_child_samples≥50，特征随机化（colsample_bytree≈0.7）。
- **逻辑**：线性因子模型忽略因子间交互效应（如高 ROE + 低估值协同）和非线性阈值（如极端财务杠杆的非线性风险）；GBDT 能自动捕捉 2 阶交互，且对异常值鲁棒（对 A 股财务操纵噪声友好）；2024 年 BigQuant 实测（2021-2024 训练，2025 前滚）年化超额约 12-18%（中证 1000 成分股）。
- **数据输入**：所有经行业市值中性化的单因子 z-score, 4周后实际超额收益（训练标签）
- **tushare 端点**：fina_indicator, daily_basic, report_rc, moneyflow, margin, hk_hold
- **A股证据/陷阱**：BigQuant 2024《基于 LightGBM 排序算法的多因子选股》：2021-2024 训练，2025-2026 滚动预测，CSI 1000 年化多空约 15%+；2024 年 Stacking 集成（RF+GBDT+SVM）在沪深 300 回测中 Sharpe 优于单模型约 40%；主要风险：短样本过拟合（A 股可用历史 < 20 年）；需要严格 PIT 处理财务数据（避免财报公布前使用数据）；2022 量化策略集体收益下滑表明模型在体制转换时容易失效。
- **机构相关度**：高 — 量化私募头部机构（幻方/九坤/明汯）核心策略，机构赛道核心竞争点
- **出处**：BigQuant《基于 LightGBM 排序算法的多因子选股策略》2024, 2024 arXiv: AlphaForge 动态 Alpha 因子挖掘框架, 计量经济学报 2024 第 4 卷第 2 期：机器学习在资产定价中的应用

## 15. AlphaNet: End-to-End Price-Volume Neural Factor
**别名**：AlphaNet 神经网络量价因子  
**映射**：`capital_sentiment` · **可行性**：YELLOW · **把握**：med · **周期**：日频更新信号，持有 2-10 日（高频短周期） · **方向**：模型输出高分看多

- **定义/公式**：AlphaNet 结构（华泰证券 2020）：输入层为近 T=10 日的量价特征矩阵 X_{i,t} = [open,high,low,close,vwap,volume,amount,turn_over]（8 个字段 × 10 日 = 80 维）；第一层：9 种预设扩展运算（StdDev, Corr, Decay_linear, Mean, Delta, Max, Rank, Return, Covariance）在 3/5/10 日窗口上两两计算，生成约 200 维合成特征；第二层：LSTM 或 GRU 从时序维提取记忆特征；全连接层输出 1 维截面得分。损失函数为 IC 损失（-RankCorr(y_pred, y_true)）。输入归一化：各特征做 T 日滑动 z-score（防止量级差异）。
- **逻辑**：A 股量价数据丰富（tushare daily/stk_factor_pro 可提供全历史），线性因子只能捕捉一阶量价信号；AlphaNet 通过特定扩展运算保持因子可解释性，同时引入非线性组合和时序记忆；2021 年华泰报告：AlphaNet 在全 A 股中 IC 达 0.054，优于单一量价因子约 30%。
- **数据输入**：日度 OHLCV + 换手率 + 成交额（过去 10-30 日）
- **tushare 端点**：daily, daily_basic, stk_factor_pro
- **A股证据/陷阱**：华泰证券 2020-2021：AlphaNet v1/v2/v3 在 CSI 800 多头 IC 约 0.054，年化多空约 15%+；2021-2022 后因量化私募广泛使用导致量价因子拥挤衰减（开源金工 2024 年高频因子回顾中确认）；2024 年改进版（AlphaForge arXiv 2024）引入动态权重仍维持有效；A 股涨跌停日量价数据失真（需剔除或特殊处理），ST 股量价模式异常（剔除）。
- **机构相关度**：高 — 量化机构核心量价 alpha 来源；但普通机构基本面选股者较少使用
- **出处**：华泰证券林晓明团队《AlphaNet：股票因子挖掘神经网络构建》2020, 2024 arXiv: AlphaForge Framework, 开源金工《2023年以来高频因子回顾》2024

## 16. Lasso / ElasticNet Factor Selection & Synthesis
**别名**：Lasso/弹性网多因子稀疏合成  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：月度更新合成权重，预测 +4 周超额 · **方向**：合成因子高分看多

- **定义/公式**：在每个截面 t，设因子矩阵 X_{N×K}（N 只股票 × K 个因子，已行业+市值中性化），目标变量 y = 未来 20 日超额收益，最小化：L = ||y - X*w||² + lambda1 * ||w||_1 + lambda2 * ||w||_2²。ElasticNet 混合 L1（稀疏选择）+L2（Ridge，处理多重共线性）。lambda 通过 5 折时序交叉验证（walk-forward，不允许未来信息泄漏）选择。滚动训练窗口 36 个月，月度更新权重 w。L1 压缩后非零权重因子即为当期有效因子集。
- **逻辑**：A 股因子池中大量因子高度相关（动量与换手率 r>0.7；价值与盈利 r>0.6），等权或 OLS 在高相关性下不稳定；Lasso 的软阈值特性自动做稀疏选择（压缩冗余因子权重至 0），ElasticNet 进一步解决高相关因子组同时入选问题；滚动训练确保 look-ahead free。
- **数据输入**：所有经中性化的单因子 z-score（K≥20）, 未来 20 日超额收益（训练用）
- **tushare 端点**：fina_indicator, daily_basic, report_rc, margin, hk_hold, moneyflow
- **A股证据/陷阱**：BigQuant Lasso 多因子选股实战（2024）：在 CSI 300/500 成分股上，Lasso 滚动模型 2013-2023 年年化 IC 约 0.08，超额年化约 10%；2022 年后因子有效性分化加剧，Lasso 能动态淘汰失效因子（如部分分析师预期因子 2022 后 IC 趋零）；风险：lambda 参数敏感，小样本期（熊市/政策突变）容易过拟合；需配合因子拥挤度监控避免选中已拥挤因子。
- **机构相关度**：高 — 量化私募标配方法；对比 GBDT 更可解释，受机构合规要求欢迎
- **出处**：BigQuant《Lasso 滚动多因子选股策略》2024, 统计学与应用 2024 第 13(4) 期：Lasso 与 ElasticNet 在量化选股中的应用

## 17. Symmetric Orthogonalization (Factor Decorrelation)
**别名**：对称正交化因子去相关 / Gram-Schmidt正交化  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：月度重算正交化矩阵（协方差矩阵用 24 个月滚动估计） · **方向**：正交化后各因子方向不变，正交分量高值方向与原始因子一致

- **定义/公式**：对 K 个因子构成的矩阵 F_{N×K}（已行业市值中性化），对协方差矩阵 C = F^T F 做特征分解 C = P * Lambda * P^T，对称正交化矩阵 O = P * Lambda^{-1/2} * P^T，正交化因子集 F_orth = F * O。Gram-Schmidt 顺序正交化步骤：先固定「最重要」因子 f1 不变，f2_orth = f2 - proj(f2, f1)，f3_orth = f3 - proj(f3, f1) - proj(f3, f2_orth)，依此类推。对称正交化保持原始因子载荷方向的对称性，不依赖因子排序，Gram-Schmidt 结果依赖初始顺序（建议按 IC 大小降序）。正交化后因子两两 Pearson 相关≈0。
- **逻辑**：A 股相关性高的因子组（如 ROE+盈利修正，流动性+换手率）在 ICIR 加权后虽各自 IC 高，但方向相近会重复计数同一信号；正交化后，每个因子贡献独立信息维度，组合预期 IC 等于单因子 IC 之和（而非相关打折后）。
- **数据输入**：所有候选因子截面 z-score 矩阵（K 因子 × N 股票）
- **tushare 端点**：fina_indicator, daily_basic, report_rc, moneyflow
- **A股证据/陷阱**：衡泰技术 2024 年 5 月华证风格因子体系：正交化是标准流程，三层结构（46 个三级因子→20 个正交二级→9 个一级）；A 股经验：未正交化时 FF5 的 RMW 与 HML 相关性高达 0.55，正交化后各自 IC 均提升约 15%；国联证券 2024 年实践：对称正交优于 Gram-Schmidt 因其不依赖因子优先级假设，在因子有效性快速轮换期（2022-2024）表现更稳健。
- **机构相关度**：高 — Barra 体系核心工程步骤，机构风险模型标配
- **出处**：华证《风格因子表征指数体系简介》2024-05, MSCI Barra CNE6 Model Documentation (2018), Ledoit & Wolf (2004): A well-conditioned estimator for large-dimensional covariance matrices

## 18. Sloan Accruals Quality Factor
**别名**：Sloan 应计项目质量因子 / 盈利质量  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：high · **周期**：年度财报触发，持有 6-12 个月 · **方向**：低 ACCRUAL（现金流驱动利润）看多

- **定义/公式**：ACCRUAL_i = (NI_i - CFO_i) / avg_TA_i，其中 NI = 净利润，CFO = 经营现金流，avg_TA = 期初期末总资产均值。ACCRUAL 高表示利润由应计项（非现金）驱动 → 盈利质量低 → 未来收益预测向下修正。截面标准化后取负值作为「盈利质量」因子（低 ACCRUAL 绝对值 / 负方向），行业+市值中性化。扩展版：Dechow et al. 操控性应计项目 = 总应计 - 正常应计（用 Jones 模型估计正常应计）。
- **逻辑**：Sloan(1996)：应计项目持久性远低于现金流；高应计 = 管理层盈余管理信号；机构尽调中会检查应计质量，但市场（散户）错误定价被机构套利所纠正 → 低应计股未来超额收益正。A 股盈余管理（盈利调节）问题尤为突出，此因子在 A 股效力强。
- **数据输入**：净利润（income.n_income）, 经营现金流（cashflow.n_cashflow_act）, 总资产（balancesheet.total_assets）
- **tushare 端点**：income, cashflow, balancesheet
- **A股证据/陷阱**：A 股盈余管理研究（计量经济学报 2024）：应计异象在 A 股显著，低应计组合年化超额约 6-9%（行业中性化后），尤其在民营企业和小盘股中更强；机构持股比高的公司应计指标已 partially priced-in；需严格 PIT（年报 4/30 次年才可用，季报各季度末后约 30 日），否则回测存在严重前视偏差；金融/银行行业应计逻辑不同（贷款减值非现金为主），需剔除或单独行业内计算。
- **机构相关度**：高 — 机构尽调必查应计质量，该因子与机构行为高度同步
- **出处**：Sloan (1996) TAR: Do Stock Prices Fully Reflect Information in Accruals and Cash Flows about Future Earnings?, 中国量化 A 股应计异象实证文献（多篇 2020-2024）