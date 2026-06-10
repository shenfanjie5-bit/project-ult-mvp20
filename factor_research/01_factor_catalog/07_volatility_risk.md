# 因子族：volatility_risk

> 波动率/风险族是本系统最值得优先补入的因子群，直接对应现有 risk_discount 节点几乎空置的痛点。三个最值得接入的因子：(1) IVOL_FF3（特异波动率）——tushare daily 直接可算，IC均值约-5~-9%，ICIR绝对值>2，是A股最稳健的风险定价信号，负向映射 risk_discount；(2) MAX5（极端日收益均值）——彩票偏好驱动，A股散户结构放大效应，涨停截断需特殊处理，同样映射 risk_discount；(3) IVOL_CYQ_Width（筹码宽度波动代理）——利用已有 cyq_perf 端点，不依赖回归，对散户/游资主导个股有独特的筹码集中度信号，映射 risk_discount。

共 16 条。


## 1. IVOL_FF3
**别名**：特异波动率（Ang-Hodrick-Xing-Zhang型）  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：high · **周期**：1个月重新估计，预测1个月收益；在A股2周至4周持有期与系统2-4周窗口吻合。 · **方向**：IVOL高 → 看空（未来收益低）；因子取负值后高分=低IVOL=看多

- **定义/公式**：每月末，对过去一个月（至少15个交易日）的日超额收益 r_{i,t} 对 Fama-French 三因子（市场MKT、规模SMB、价值HML）做 OLS 回归：r_{i,t} = α + β₁·MKT_t + β₂·SMB_t + β₃·HML_t + ε_{i,t}，IVOL = std(ε_{i,t})；剔除当月含涨跌停日≥5天或停牌天数≥3天的股票；对结果做行业中性化和市值中性化（残差法）后取负值用于打分。
- **逻辑**：高特异波动率股票被散户/彩票偏好者过度追捧导致定价高估，未来收益低。在A股散户占比55%+的市场结构下，该效应更强。随机构化进程效应轻微衰减但仍显著（2023-2024研究确认）。
- **数据输入**：日收盘价（含前复权）, 中国FF三因子（market/SMB/HML）, ST/退市/停牌标记
- **tushare 端点**：daily, daily_basic, stk_factor_pro
- **A股证据/陷阱**：Ang等(2006)中国扩展研究及后续大量文献确认负向关系（Pacific-Basin Finance J. 2023；Computational Economics 2022）；A股IVOL异象显著强于美股，散户情绪驱动可放大至IC均值-8.92%、年化ICIR -5.04（PCA隐式因子框架）。陷阱：涨跌停日实际收益被截断→波动率低估，需剔除这些日期；T+1限制下信号衰减快，月频换仓合适；ST股票需剔除；机构化加深后异象可能缓慢收敛。
- **机构相关度**：高——机构持仓的低波动股票集中于蓝筹，IVOL恰好筛出高波散户题材股；北向资金也倾向规避高IVOL个股。
- **出处**：Ang, Hodrick, Xing, Zhang (2006) JF 'The Cross-Section of Volatility and Expected Returns', Ang et al. (2009) JFE 'High Idiosyncratic Volatility and Low Returns: International and Further US Evidence', Pacific-Basin Finance Journal v.81 (2023) - 投资者情绪与IVOL异象, heth.ink/IdiosyncraticRisk/ 特质风险类因子研究

## 2. MAX5
**别名**：最大日收益均值（Bali-Cakici-Whitelaw MAX效应）  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：high · **周期**：过去1个月数据，预测1个月收益；A股证据支持2-4周窗口。 · **方向**：MAX5高 → 看空；负值后高分=低MAX5=看多

- **定义/公式**：每月末计算过去一个月内最大的5个日收益率的算术均值：MAX5_i = mean(top-5 daily returns in month t)；A股特殊处理：涨停日（日收益≥9.9%主板 或≥19.9%科创/创业板）计为极端，但需保留（因为涨停本身即散户彩票需求的直接体现）；对因子做行业中性化；用于打分时取负值（高MAX5→看空）。
- **逻辑**：投资者对极端正收益的彩票式偏好使高MAX个股被高估，未来收益低。A股涨停板制度（10%/20%上限）及连板文化强化了彩票效应——主板10%上限实际上把最大收益截断，因此用5日均值而非单日MAX更稳健。
- **数据输入**：日收盘价（复权）, 涨停标志（stk_limit或limit_list_d）
- **tushare 端点**：daily, stk_limit, limit_list_d
- **A股证据/陷阱**：中国A股MAX效应实证：2000-2022年因子MAX策略较股票MAX策略风险调整收益8.50 vs 5.47（EFMA 2025）；SCIRP 2023确认A股负向显著；彩票偏好驱动被行业中性化后仍显著。陷阱：①涨停截断使MAX值右删失——科创/创业板20%上限 vs 主板10%需分板块处理；②ST股5%上限需剔除；③连板效应（彩票偏好峰值）在信号形成后可能有短期反弹→建议T+2后建仓以规避短期动量干扰。
- **机构相关度**：中高——机构普遍规避连板涨停题材股，MAX高者恰是机构卖出对象；北向资金流入方向与低MAX负相关。
- **出处**：Bali, Cakici, Whitelaw (2011) JFE 'Maxing Out: Stocks as Lotteries and the Cross-Section of Expected Returns', Wang Liyao 'Factor MAX in the Chinese Market' EFMA 2025, SCIRP Theoretical Economics Letters 2023 'The MAX Effect in China A-Share Market', Lottery Preference and Skewness Risk Premium, Wiley JFM 2025

## 3. BAB_A
**别名**：A股版Betting Against Beta（杠杆约束套利）  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：月度再平衡；预测1个月。 · **方向**：高β → 看空；BAB多头=低β看多

- **定义/公式**：1.估算β：用过去252个交易日的日收益，对沪深300指数做OLS估计，再用贝叶斯压缩至截面均值：β̂ = 0.6·β_OLS + 0.4·1.0；2.按β的截面秩构建多空：多头=低β组（β<中位数）、空头=高β组（β>中位数），权重∝|β_rank - median_rank|；3.多头杠杆化至β=1、空头去杠杆化至β=1（使组合β中性）：BAB = (1/β_L)·r_L - (1/β_H)·r_H；A股修正：因T+1和融资券限制，空头通过融券（margin_detail可查）模拟，或简化为纯多头低β策略；行业中性化后使用。
- **逻辑**：受融资约束的投资者（散户及部分机构）倾向持有高β股票以获取更高预期收益，导致高β股被高估。A股融资约束比美股更紧（T+1、融券稀缺），理论上BAB效应更强，但实证显示驱动因素更多来自波动率而非beta本身。
- **数据输入**：日收盘价, 市场指数日收益（沪深300）, 融资融券数据
- **tushare 端点**：daily, daily_basic, margin, margin_detail
- **A股证据/陷阱**：中国实证：beta异象在中国A股显著存在，但驱动因素以波动率为主而非杠杆约束（ScienceDirect 2021；Journal of Asset Management 2021）；Han et al.应用BAB于A股有正alpha。陷阱：①A股融券极度受限，多头单腿实操性更强；②T+1制度使做空高beta后次日买入的时序错配；③市场快速上涨期（9·24行情）高beta股短期显著超额，BAB出现剧烈回撤（类似2024年10月事件）；④需同时控制市值和行业暴露。
- **机构相关度**：高——机构资金（公募、险资）天然偏好低beta稳健股，BAB多头与机构持仓重叠度高。
- **出处**：Frazzini & Pedersen (2014) JFE 'Betting Against Beta', Does behavioral-motivated volatility effect explain the beta anomaly? ScienceDirect 2021, The Volatility Effect in China, Journal of Asset Management 2021, Low liquidity beta anomaly in China, Emerging Markets Review 2021

## 4. RVOL_20
**别名**：实现波动率（20日历史波动率）  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：high · **周期**：20日估计，预测1-4周收益；2024年中金高频手册确认30日换仓IC均值-0.118，ICIR -0.541。 · **方向**：RVOL高 → 看空

- **定义/公式**：RVOL_20_i = std(日对数收益率, 过去20个交易日) × √252；日对数收益 r_t = ln(P_t/P_{t-1})，使用前复权价格；剔除停牌日；涨跌停日的收益率保留（截断本身是信息）；月末截面因子值取负值（高波动→看空）；行业+市值中性化后用于打分。
- **逻辑**：历史波动率是IVOL的简化代理，无需因子模型。在A股，波动率与未来收益的负向关系在全市场层面极强（Barra-CNE5中的DASTD/CMRA即此类因子）。实现波动率较IVOL更简单稳健，适合日频数据直接计算。
- **数据输入**：前复权日收盘价, 停牌/复牌标记
- **tushare 端点**：daily, daily_basic
- **A股证据/陷阱**：Barra CNE5/CNE6模型核心风险因子。2024年高频因子研究（中金手册）：30日换仓波动率因子IC均值-0.118，IC_IR -0.541，全市场有效。陷阱：①A股涨跌停日RVOL被人为压低（10%封板→次日放量）；②ST股波动率异常高需剔除；③行情极端期（如924后急涨）低波动股无法受益，需因子择时；④市值效应混杂（小市值高波动），需严格市值中性化。
- **机构相关度**：高——是Barra风险模型标配，机构风险系统广泛使用，直接影响组合构建中的风险预算分配。
- **出处**：Barra CNE5 Factor Model, 中金公司《高频因子手册》波动率因子章节, The Volatility Effect in China, Journal of Asset Management 2021

## 5. RVOL_HIGHFREQ
**别名**：高频上行/下行波动率不对称（日内分钟数据）  
**映射**：`risk_discount` · **可行性**：YELLOW · **把握**：med · **周期**：月度更新，预测2-4周；日内分钟数据与系统持仓周期匹配。 · **方向**：高上行RVOL → 看空（彩票溢价）；高ASYM_VOL → 看空

- **定义/公式**：基于日内5分钟K线（或1分钟）数据：上行RVOL_UP = std(5min正收益) × √(每日分钟数 × 252)；下行RVOL_DOWN = std(5min负收益) × √(每日分钟数 × 252)；不对称比 ASYM_VOL = RVOL_UP / RVOL_DOWN；月度合计（过去20个交易日）；中金手册结论：上行波动率ICIR绝对值1.35，IC均值-8.4%（全市场）。
- **逻辑**：上行波动率高表明股价偶发性暴涨，反映彩票偏好和游资操纵；下行波动率高表明恐慌抛售。两者分开构建的因子比合并RVOL含有更丰富的信息。上行波动率高→预期收益更低（彩票溢价被高估）。
- **数据输入**：日内5分钟或1分钟K线收益率（stk_mins类数据）
- **tushare 端点**：none
- **A股证据/陷阱**：中金《高频因子手册》实证：上行波动率因子有效性优于普通波动率和下行波动率，全市场ICIR绝对值可达1.35，IC均值-8.4%（2014-2023年）。陷阱：tushare标准版无日内分钟数据，需外部数据源；涨跌停日的分钟K线失真（开板后即封板）。
- **机构相关度**：中——机构量化策略广泛使用日内数据，但对基本面投资者信号意义较弱。
- **出处**：中金公司《高频因子手册》分享3：波动率因子，从构建到回测 (pandaai.online/community/article/102)

## 6. SKEW_REALIZED
**别名**：实现偏度（日内数据构建）  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：月度估计，预测1个月收益；中国A股文献样本2000-2022年持续显著。 · **方向**：高RSKEW（正偏）→ 看空；因子取负值后高分=低偏度=看多

- **定义/公式**：月度实现偏度：RSKEW_i = [T/(( T-1)(T-2))] × Σ[(r_t - r̄)³/σ³]，其中 r_t 为日内5分钟收益率，T为期间总分钟数，σ为样本标准差；也可用日频版本（月度T=20日）：RSKEW_daily = standardized third moment of daily log returns over past month；股票收益率分布右偏→彩票偏好→高估→预测收益低→因子取负值。
- **逻辑**：Harvey & Siddique (2000) 共偏度理论：投资者为规避负偏度风险要求补偿，正偏度股票被高估。A股散户对高偏度（涨停潜力）股票的追捧放大此效应。ScienceDirect 2023确认中国A股已实现偏度与未来收益显著负相关。
- **数据输入**：日对数收益率, （更准确）日内5分钟收益率
- **tushare 端点**：daily
- **A股证据/陷阱**：ScienceDirect 2023 'Does realized skewness predict the cross-section of Chinese stock returns?'：负向显著；Lottery Preference and Skewness Risk Premium, JFM 2025确认正偏度溢价为负。陷阱：日频偏度估计噪声大（需20+观测值），涨跌停日截断使偏度系统性低估；有研究发现在中国控制有符号跳跃方差（signed jump variance）后偏度效应消失，需关注替代变量。
- **机构相关度**：中——偏度因子在机构为主市场中更多用于尾部风险管理而非选股，但A股散户驱动的彩票溢价使其仍有选股alpha。
- **出处**：Does realized skewness predict the cross-section of Chinese stock returns, ScienceDirect Finance Research Letters 2023, Harvey & Siddique (2000) JF 'Conditional Skewness in Asset Pricing Tests', Lottery Preference and Skewness Risk Premium: Evidence From the Chinese Market, JFM 2025

## 7. COSKEW
**别名**：协偏度（系统性偏度风险暴露）  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：low · **周期**：60日或更长期估计（需稳定估计），预测1个月。 · **方向**：负协偏度（大负值）→ 理论上应有风险溢价，但在A股定价偏差下为看空信号

- **定义/公式**：Harvey-Siddique协偏度：COSKEW_i = E[ε_i,t · ε²_m,t] / [std(ε_i) · std(ε_m)²]，其中 ε_i,t = r_i,t - β_i · r_m,t，ε_m,t = r_m,t - E[r_m]；实操：用过去60个月日收益对市场做二次项回归：r_i,t = α + β₁·r_m,t + β₂·r²_m,t + ε，β₂即协偏度暴露；负协偏度意味股票在市场下跌时损失更大→应有正风险溢价（高价）→未来收益低。
- **逻辑**：投资者需要对系统性下行尾部风险（负协偏度）获得补偿。负协偏度股票在市场崩溃时雪上加霜，应有更高收益要求，但若市场高估其避险价值则反而预测收益低。A股证据：股权质押行为加剧协偏度传染风险（中国人民大学IMI 2023研究）。
- **数据输入**：日收盘价, 沪深300指数日收益
- **tushare 端点**：daily, daily_basic
- **A股证据/陷阱**：Co-skewness pricing in international markets显著（Asia-Pacific evidence, ScienceDirect 2021）；中国A股文献较少，中国人民大学IMI(2023)确认股权质押通过协偏度传导系统性风险。陷阱：参数估计需较长窗口，A股历史较短；协偏度与beta高度共线；实际选股中IC较低。
- **机构相关度**：中低——协偏度主要用于宏观尾部风险管理，对2-4周选股信号较弱。
- **出处**：Harvey & Siddique (2000) JF, Co-skewness and expected return: Evidence from international stock markets, ScienceDirect 2021, 中国人民大学IMI 2023：股权质押对系统性风险的影响

## 8. DOWNSIDE_BETA
**别名**：下行beta（条件CAPM下行侧）  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：252日估计，预测1个月；2-4周窗口有效。 · **方向**：高下行beta → 看空（需要更高风险溢价，但散户高估这类股票→预测负alpha）

- **定义/公式**：仅使用市场超额收益为负时的样本估计beta：β⁻_i = Cov(r_i,t, r_m,t | r_m,t < 0) / Var(r_m,t | r_m,t < 0)；实操：取过去252个交易日中市场下跌的天数（约50-100天），对这些观测做OLS；上行beta：β⁺_i 同理（r_m,t > 0子样本）；因子DBETA = β⁻_i - β⁺_i（下行beta超额），高DBETA→下行风险高→看空。
- **逻辑**：Ang等(2006)：下行beta比普通beta更好地预测截面收益；投资者对下行风险的厌恶超过对称假设。A股证据：Does downside risk matter more in asset pricing? Evidence from China (Emerging Markets Review 2019)确认中国市场下行beta与预期收益正相关，但也存在高估风险问题。
- **数据输入**：日收盘价, 沪深300日收益率
- **tushare 端点**：daily, daily_basic
- **A股证据/陷阱**：Emerging Markets Review 2019和2024研究确认下行风险在中国A股显著定价。2024'Uncertainty and cross-sectional stock returns: China'同样支持。陷阱：下行子样本小（约100观测），估计噪声大；A股T+1在大跌日翌日无法立即卖出，增加了下行风险暴露的不对称性；小市值股票下行beta偏高，需严格市值中性化。
- **机构相关度**：高——险资和公募基金的回撤控制直接依赖下行beta管理，该因子与机构风险预算体系高度相关。
- **出处**：Ang, Chen, Xing (2006) RFS 'Downside Risk', Does downside risk matter more in asset pricing? Emerging Markets Review 2019, Extreme downside risk in the cross-section of asset returns, IRFA 2024

## 9. VaR_HS
**别名**：历史模拟VaR（Historical Simulation Value at Risk）  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：252日历史窗口，月度更新，预测1个月。 · **方向**：高VaR → 看空

- **定义/公式**：VaR_HS(5%)_i = −percentile(r_1,...,r_T, 5%)，其中收益率为过去252个交易日的日对数收益，取第5百分位（即损失侧），VaR值为正数表示潜在损失；用月度截面值做因子，高VaR→看空；亦可用条件超额损失CVaR(5%) = −E[r|r < −VaR]，信息量更丰富。
- **逻辑**：VaR/CVaR是监管和机构使用的尾部风险度量。高VaR个股被散户忽视（散户不关注尾部），被机构减仓，因此存在系统性高估→负风险溢价。A股文献：VaR与截面收益显著负相关（Pacific-Basin Finance J. 2021）。
- **数据输入**：前复权日收益率
- **tushare 端点**：daily
- **A股证据/陷阱**：Value at risk and the cross-section of expected returns: Evidence from China, Pacific-Basin Finance J. 2021确认显著负相关。与IVOL高度相关（两者皆反映尾部），需正交化后使用以贡献增量信息。陷阱：涨跌停截断使VaR系统低估（日收益被人为限制）；ST股和小市值股票VaR极高，需分层处理。
- **机构相关度**：高——机构风控直接监控个股VaR，该指标与机构持仓边界一致。
- **出处**：Value at risk and the cross-section of expected returns: Evidence from China, Pacific-Basin Finance J. 2021, Downside risk measures in cross-section of returns

## 10. CYQ_WIDTH
**别名**：筹码分布宽度（胜率波动代理）  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：日更新，月度截面信号，预测2-4周。 · **方向**：CYQ_WIDTH高 → 未来波动高 → 看空

- **定义/公式**：利用 tushare cyq_perf 端点：CYQ_WIDTH_i = (cost_95pct - cost_5pct) / weight_avg_cost × 100（相对价格范围，%）；即筹码分布90%区间归一化宽度；较宽→持仓成本高度分散→套牢/解套分歧大→未来波动率高→风险高→看空；月末截面因子，取负值打分；备选：筹码宽度变化速度 ΔWIDTH = WIDTH_t - WIDTH_{t-1}，代理信息分歧变化。
- **逻辑**：筹码分布宽度反映持仓成本分散程度：宽分布意味大量持仓者在不同价位存在套牢或解套压力，股价在穿越关键成本区时遭遇阻力，是A股特有的散户行为指标。宽筹码 = 高分歧 = 高波动预期。
- **数据输入**：cyq_perf端点：cost_5pct, cost_95pct, weight_avg
- **tushare 端点**：cyq_perf
- **A股证据/陷阱**：筹码分布是A股技术分析核心指标，已有量化策略将其用于选股（BigQuant/CSDN实践）。直接学术证据较少，但作为波动率代理（相关性高）和散户行为指标（A股专有）有独特价值。陷阱：数据仅从2018年开始；极端行情下（暴涨暴跌）筹码快速重置，历史分布失效；新上市股票筹码分布不稳定（建议剔除上市<6个月标的）。
- **机构相关度**：中低——机构不直接使用筹码分析，但筹码宽度隐含的散户行为与机构逆向交易机会相关。
- **出处**：Tushare文档：cyq_perf接口说明 (tushare.pro/document/2?doc_id=293), BigQuant量化知识库：筹码分布因子研究

## 11. LIMIT_FREQ
**别名**：涨跌停频率因子（A股特有彩票信号）  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：60日窗口，月度截面信号，预测2-4周。 · **方向**：高LIMIT_FREQ → 高波动风险 → 看空

- **定义/公式**：LIMIT_UP_FREQ_i = (过去60个交易日中涨停次数) / 60；LIMIT_DOWN_FREQ_i = (过去60个交易日中跌停次数) / 60；综合波动信号：LIMIT_FREQ = LIMIT_UP_FREQ + LIMIT_DOWN_FREQ；高频率→高波动→高彩票属性→看空（预期未来收益低）；也可构建：LIMIT_UP_RATIO = 涨停次数/(涨停+跌停次数)作为方向信号。
- **逻辑**：A股独有制度：涨跌停次数直接量化了极端收益频率（MAX效应的离散版本），同时反映散户追捧热度。频繁涨停个股是典型散户彩票，被机构规避；频繁跌停则是恐慌抛售信号。两者结合代理总体波动暴露。
- **数据输入**：日涨跌停标记（stk_limit或limit_list_d）
- **tushare 端点**：stk_limit, limit_list_d, limit_list_ths
- **A股证据/陷阱**：华安证券金工2026年3月研报《涨停板背后的Alpha》确认首板回调策略有超额；A股涨停板彩票效应已被Factor MAX论文证实与MAX因子高度相关。陷阱：主板10%、科创/创业板20%、北交所30%、ST股5%板块差异需分板标准化；新股上市初期（前5日无限制）需剔除；涨停频率与市值高度负相关，需严格市值中性化。
- **机构相关度**：高——机构持仓系统普遍剔除频繁涨跌停个股；北向资金从不参与连板题材，频繁涨停频率是机构规避信号。
- **出处**：华安证券金工 2026 《涨停板背后的Alpha，首板回调策略》, Bali et al. (2011) MAX因子与涨停频率的理论连接, limit_list_d Tushare文档

## 12. PLEDGE_VOL
**别名**：质押压力波动放大因子  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：季度或月度更新（披露频率），预测1个月，极端事件预警信号。 · **方向**：高PLEDGE_RATIO → 高尾部风险 → 看空

- **定义/公式**：PLEDGE_RATIO_i = 控股股东质押股数 / 总股本（来自pledge_stat）；构建质押波动放大因子：PLEDGE_VOL_i = RVOL_20_i × (1 + PLEDGE_RATIO_i)，即波动率被质押率加权放大；或直接用PLEDGE_RATIO作为独立的尾部风险因子，高质押率→强迫平仓风险→尾部下跌暴露→看空。
- **逻辑**：高质押率意味着大股东在股价下跌至预警线时面临强制平仓，产生螺旋式下跌风险（PLOS One 2021；IMI 2023）。这是A股特有的系统性尾部风险来源，与波动率交互后形成非线性风险暴露。
- **数据输入**：pledge_stat：质押股数、总股本, daily_basic：收盘价
- **tushare 端点**：pledge_stat, pledge_detail, daily_basic
- **A股证据/陷阱**：Linkages between share pledging, stock price risk and profitability: Evidence from P.R. China (PLOS One 2021)：质押率与股价波动正相关；IMI/中国人民大学(2023)：质押行为通过协偏度加剧系统性风险传导。A股2018年质押危机是极端案例。截至2024年底，质押规模降至十年新低（~3.1%市值），但个股差异大。陷阱：质押数据有披露滞后（季度为主）；政策救市时质押风险被临时消除（如2018年底、2024年9月）；需设定质押率阈值（如>30%）才有显著效果。
- **机构相关度**：高——机构风控系统明确将高质押率列为风险红线；北向资金持仓中极少出现高质押率个股。
- **出处**：Linkages between share pledging, stock price risk and profitability, PLOS One 2021, 中国人民大学IMI 2023 股权质押对系统性风险影响研究, 中信证券2024 当前股票质押风险整体可控报告

## 13. IVOL_RESID_NEUTRAL
**别名**：行业市值双重中性化IVOL（纯净特异风险）  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：high · **周期**：月度截面信号，预测1个月；双重中性化提升信号纯度。 · **方向**：高中性IVOL → 看空

- **定义/公式**：在IVOL_FF3基础上进行两步中性化：步骤1，截面回归：IVOL_i = α + Σγ_k·Industry_k + δ·ln(MktCap) + η_i；步骤2，取残差η_i作为纯净IVOL；可选加入价值（PB倒数）和动量（12-1月收益）的控制；最终因子取负值，分位数打分；月度更新。
- **逻辑**：原始IVOL含有大量行业和市值暴露（小市值、高科技行业本身就高IVOL），中性化后的残差才是真正反映个股特异风险水平的信号。行业中性化是A股多因子系统的标配，尤其在行业轮动剧烈时期。
- **数据输入**：日收盘价（FF3残差）, 行业分类（SW申万或中信）, 市值（daily_basic）
- **tushare 端点**：daily, daily_basic, index_classify, index_member_all
- **A股证据/陷阱**：东北证券2025《特质波动率因子的重构》报告：通过创新方法重构IVOL，年化超额收益7.63%，解决传统因子多头收益不显著、单调性弱的痛点。行业+市值中性化是A股标配，显著提升IC稳定性（月度RankIC从-0.05提升至-0.09）。陷阱：中性化会损耗部分信息量；过度中性化后因子可能无法区分同行业同市值个股；申万一级行业仅31个，中性化粒度需均衡。
- **机构相关度**：高——机构量化组合普遍要求行业中性，该因子是机构可直接使用的风险暴露信号。
- **出处**：东北证券2025 特质波动率因子重构报告, heth.ink/IdiosyncraticRisk/ 特质风险类因子（PCA框架）, Barra CNE5/6因子模型中的DASTD因子

## 14. VOL_REGIME
**别名**：波动率机制择时因子（波动率与收益的条件关系）  
**映射**：`risk_discount` · **可行性**：YELLOW · **把握**：med · **周期**：用作调节权重的元因子（factor-on-factor），短期动态调整，2-4周有效。 · **方向**：高波动机制 → 低IVOL因子权重上调；低波动机制 → 权重下调

- **定义/公式**：构建波动率机制指示变量：REGIME_t = 1 if 市场30日RVOL_20 > 市场过去252日RVOL中位数（高波动机制），0 otherwise（低波动机制）；在高波动机制下，低IVOL个股防御溢价更强（权重增加）；在低波动机制下，低IVOL溢价可能减弱；动态调整方案：IVOL_SCORE_adjusted = IVOL_SCORE × (1 + 0.5 × REGIME_t)；也可构建VOL_TREND = MA(RVOL_20, 5d) / MA(RVOL_20, 60d) − 1（短期波动率相对趋势）作为独立因子。
- **逻辑**：低波动异象在不同市场机制下强弱不同：熊市/高波动期，低波动股票防御价值更高，因子更有效；牛市/低波动期（如2024年底A股单边上涨），高beta股票表现大幅超越，传统低波因子容易回撤。2024年国信证券研究：价值/质量因子择时优于波动因子择时，需结合宏观机制。
- **数据输入**：市场指数日收益（沪深300）, 个股RVOL_20, 宏观机制信号（可选）
- **tushare 端点**：daily_basic, index_dailybasic
- **A股证据/陷阱**：2024年量化研究专题（未来智库）：因子择时方案探索显示动态调权优于静态，但波动类因子择时效果弱于基本面因子（价值/质量）；2024年9月后的急涨行情中，低波动策略遭受较大回撤（低波红利2025年仅+0.44% vs 中证500+30.39%）。陷阱：机制划分本身会引入过拟合风险；A股政策干预（如央行购ETF、印花税减半）会突发改变机制，难以预判。
- **机构相关度**：中高——机构资产配置中动态调整风险预算与波动率机制高度相关，但对个股选股信号直接作用有限。
- **出处**：2024年量化研究专题：破解Alpha投资困境，因子择时方案再探索（未来智库）, A股低波红利指数及产品的投资价值与发展趋势，中国资本市场研究网2025

## 15. MARGIN_VOL_RATIO
**别名**：融资余额波动率比（杠杆驱动风险放大）  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：月度截面信号，预测2-4周（融资平仓风险为中期事件）。 · **方向**：高MARGIN_VOL → 强迫平仓风险高 → 看空

- **定义/公式**：MARGIN_RATIO_i = 融资余额_i / 流通市值_i（来自margin_detail × daily_basic）；MARGIN_VOL_i = MARGIN_RATIO_i × RVOL_20_i；构建方式：月末截面，取MARGIN_RATIO高且RVOL_20高的个股为高风险（两者同向则杠杆放大波动）；也可直接用：MARGIN_CHANGE = (融资余额_t - 融资余额_{t-4周}) / 融资余额_{t-4周}，融资余额快速增加 + 高波动 → 强迫平仓风险。
- **逻辑**：融资余额高意味散户和短线资金加杠杆买入，一旦股价下跌触发维保线则触发强迫平仓，进一步压低股价，形成波动率螺旋。该因子将A股特有的融资结构与波动率结合，是BAB因子在A股的杠杆约束代理。
- **数据输入**：margin_detail：个股融资余额, daily_basic：流通市值、收盘价, daily：日收益率
- **tushare 端点**：margin, margin_detail, daily_basic, daily
- **A股证据/陷阱**：A股融资余额是重要的散户杠杆指标，与个股未来收益负相关在多篇量化研究中被确认（尤其在市场下行周期）。2015年和2024年的融资强制平仓事件是历史验证案例。陷阱：融资政策变化（如监管限制融资比例）会影响因子有效性；创业板和科创板融资占比较高，需分板处理；融资余额数据有T+1披露，信号轻微滞后。
- **机构相关度**：高——北向资金和公募基金普遍规避融资余额过高的高波动个股；机构风控将融资余额占比作为流动性风险指标。
- **出处**：Frazzini & Pedersen (2014) BAB理论（杠杆约束）, 中国融资融券制度研究 Tushare margin端点, Betting Against (Bad) Beta, arXiv 2024

## 16. SKEW_UNLOCK
**别名**：解禁压力尾部风险因子  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：前向30日滚动，预测未来2-4周内的事件驱动风险。 · **方向**：高解禁压力+高波动 → 看空

- **定义/公式**：UNLOCK_PRESSURE_i = 未来30日内解禁股份数 / 流通股本（来自share_float）；高解禁压力 + 高波动 = 高尾部风险；构建：UNLOCK_SKEW_i = UNLOCK_PRESSURE_i × RSKEW_i（解禁量×偏度），二者同向时放大尾部风险信号；或简化：当UNLOCK_PRESSURE > 0.05（5%流通股本）且RVOL > 行业中位数时，给出负向风险调整分。
- **逻辑**：大额解禁在高波动期间产生极端下行压力（解禁股持有成本远低于市价，减持动机强），这是A股独有的定期尾部风险事件。解禁数量与波动率的交乘项可以预测短期内超常规下行风险。
- **数据输入**：share_float：解禁日期、解禁量, daily_basic：流通股本, daily：RVOL计算
- **tushare 端点**：share_float, daily_basic, daily
- **A股证据/陷阱**：A股解禁效应有大量文献支持（预解禁前股价显著下跌）。与波动率交乘可放大信号纯度，高波动期（如2024年初市场下跌期）解禁压力引发更大跌幅。陷阱：解禁不一定减持（战略股东锁定期后也可能增持）；政策可能推迟解禁；小市值个股解禁比例高但成交量也小，实际冲击更大；需区分首发解禁、定增解禁、股权激励解禁等不同类型。
- **机构相关度**：高——机构投资者的股票池维护中，解禁压力是重要的时点回避指标；北向资金在大额解禁前往往提前减仓。
- **出处**：A股解禁效应实证研究（多篇国内学术文献）, share_float Tushare文档, 中信证券2024：质押与解禁压力分析