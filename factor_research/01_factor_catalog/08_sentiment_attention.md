# 因子族：sentiment_attention

> 情绪/关注度因子族是A股打分系统中 capital_sentiment 与 priced_in_discount 两轴的天然输入，也可为 risk_discount 提供过热预警。该族核心逻辑是"散户/游资驱动的价格发现→短期过激→均值回归"，在机构化程度不断提升的市场中呈现出【高关注→看空(反向因子)】的规律性特征。最值得优先接入的3个因子：(1) 涨停板封单强度因子(limit_seal_strength)——tushare limit_list_d 直接可算，5年样本IC≈-10%、ICIR≈-4，做空信号；(2) 东财/同花顺热榜关注度因子(dc_hot_rank_reversal)——dc_hot/ths_hot 直接可算，1-2周反转信号，适配 priced_in_discount；(3) 筹码获利比例因子(chip_profit_ratio)——cyq_perf 直接可算，低获利比例+高换手=底部集中，看多信号。

共 17 条。


## 1. limit_seal_strength
**别名**：涨停封单强度因子 / 封成比  
**映射**：`priced_in_discount` · **可行性**：GREEN · **把握**：high · **周期**：1-5日（次日信号最强；5日后衰减）；覆盖系统2-4周窗较弱需叠加其他因子 · **方向**：高封成比→短期看空（反向，散户追涨后反转）

- **定义/公式**：FinalSeal = 封单量 / 当日成交量。对每只当日涨停股票(收盘涨幅≥9.8%主板/19.8%创/科)，计算当日14:55时刻委买订单(bid_vol_limit)除以全日成交量(vol)。因子值高=资金封板意愿强。做空方向因子：截面内对同行业标准化后取负数，高值→短期反向。可扩展为：SealScore = (seal_vol / vol) × (1 - open_failed_rate)，其中open_failed_rate=炸板次数/涨停触及次数。
- **逻辑**：涨停板制度造成注意力拥挤与流动性截断效应(magnet effect)。封单高→散户追涨、流动性枯竭，次日开板压力大；封成比>10时次日高开概率>70%但后续2-5日反转显著。华安证券2026-03报告基于32,615首板样本验证：多空年化收益35.1%，RankIC均值-10.5%，ICIR=-4.29，样本外(2024-25)年化20.7%。
- **数据输入**：limit_list_d: close_pct(涨跌幅), bid_vol(封单量), amount(成交额), daily: vol, amount, open
- **tushare 端点**：limit_list_d, daily
- **A股证据/陷阱**：华安证券金工(2026-03)32615首板样本实证：5年RankIC=-10.5%，年化ICIR=-4.29，多空年化35.1%；T+1约束意味着封单次日必须以市价开盘，套牢盘压力直接兑现；涨跌停板截断须剔除北交所(±30%)；ST股须单独池或排除；行业中性化后效果更稳定
- **机构相关度**：机构不参与打板但可用此因子做反向对冲/减仓信号；机构化程度越高该因子反转越强
- **出处**：华安证券金工·涨停板背后的Alpha：首板回调策略的系统化探索与实证(2026-03), Fang et al. Daily Price Limits and Destructive Market Behavior, Princeton(2020), Wan(2021) Could increasing price limits reduce up limit herding, ScienceDirect

## 2. dc_hot_rank_reversal
**别名**：东财/同花顺热榜关注度反向因子  
**映射**：`priced_in_discount` · **可行性**：GREEN · **把握**：med · **周期**：1-3周（DA研究1-2周最强；A股T+1延迟1日） · **方向**：高关注度→看空（反向）；低关注度→看多

- **定义/公式**：对日期t，从dc_hot/ths_hot获取每只股票的rank(排名，越低=越热)。构建关注度热度得分：Attention_t = -rank (rank越低→attention越高)。5日平滑：AttentionMA5 = mean(Attention_{t}, ..., Attention_{t-4})。横截面z-score后取负：Factor = -zscore(AttentionMA5)，高因子值=低关注度→预期正收益。备选：直接用'上榜天数累计'过去10日计数作为分子，除以流通市值log控制规模偏差。
- **逻辑**：Da(2011)和Baker-Wurgler(2007)确立：散户关注度→价格短期超涨→1-4周均值回归。东财热榜聚集散户高度关注，是A股版'Google Trends'替代指标。从信息传播逻辑：热榜→散户追买→价格偏离基本面→机构反向→反转。与百度指数/Google Trends的attention-reversal机制一致，但A股特异性更强因T+1限制无法当日反向。
- **数据输入**：dc_hot: ts_code, trade_date, rank, hot(热度值), ths_hot: ts_code, trade_date, rank
- **tushare 端点**：dc_hot, ths_hot
- **A股证据/陷阱**：直接A股实证较少；间接证据：浦银国际情绪指标14成分中涨停股数量与换手率的IC均有显著；Da(2021) AIMS Press研究中国A股关注度与收益率关系2006-2021发现注意力负向预测1-2周收益；A股特异性：ST剔除；市值中性化重要(热榜小市值偏多)；热榜数据时效性(T日收盘后更新)
- **机构相关度**：机构本身不看热榜但可追踪散户流动方向；与北向资金流组合：热榜高关注+北向流出=双重反向信号
- **出处**：Da, Engelberg, Gao. In Search of Attention, JF 2011, Da et al. Measuring the effects of investor attention on China's stock returns, AIMS 2021, Baker & Wurgler. Investor Sentiment in the Stock Market, JEP 2007

## 3. chip_profit_ratio
**别名**：筹码获利比例因子 / CYQ盈利比例  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：2-6周（筹码结构变化慢，持仓逻辑适配系统2-4周窗） · **方向**：低获利比例+高换手→底部信号→看多；高获利比例→获利了结压力→看空

- **定义/公式**：从cyq_perf获取字段: profit(获利比例=当前价格以下的持仓比例，即有利润的筹码占比)和weight_avg(加权平均成本)。定义：ChipProfit_t = profit_t（取值0-1）。延伸为筹码集中度因子：ChipConc = 1 - (high_cost - low_cost) / weight_avg，其中high_cost/low_cost为90%/10%分位成本。因子映射：低获利比例(<40%)+ 近期换手率高 → 底部筹码换手→看多；高获利比例(>80%)+ 低换手→获利盘压力→看空。正向：Factor = -zscore(profit) when turnover > 80th pct.
- **逻辑**：筹码分布反映市场持仓成本结构。获利比例低=大部分持仓亏损→止损压力弱（持仓人倾向锁筹）；筹码密集区=支撑/压力位。当获利比例从低位升过50%（解套后）往往引发第二波上涨（解套盘不再急于卖出，买入持续）。这是中国散户为主市场的独特信号，行为金融学'disposition effect'的具体体现。
- **数据输入**：cyq_perf: ts_code, trade_date, his_high, his_low, cost_5pct, cost_15pct, cost_50pct, cost_85pct, cost_95pct, weight_avg, profit, count_owner
- **tushare 端点**：cyq_perf, daily_basic
- **A股证据/陷阱**：CYQ指标于1997年A股市场发展；行为金融disposition effect在A股散户市场中极显著；CSDN博客及量化社区多篇实证显示获利比例0-30%区间买入次月超额收益+2-5%；筹码密集区支撑效果在散户占主导的小市值股更强，机构化后效果有所衰减；需行业中性化（金融板块筹码结构特殊）
- **机构相关度**：机构用筹码数据追踪散户持仓成本，判断'解套行情'时机；在散户→机构迁移背景下，该因子在散户比例高的中小市值股更有效
- **出处**：陈浩 CYQ指标(1997); Shefrin & Statman. The Disposition to Sell Winners Too Early and Ride Losers Too Long, JF 1985, Grinblatt & Han. Prospect Theory, Mental Accounting, and Momentum, JFE 2005

## 4. turnover_acceleration
**别名**：加速换手因子 / 放量上涨日换手加速  
**映射**：`priced_in_discount` · **可行性**：GREEN · **把握**：high · **周期**：2-4周（与系统核心窗口完全匹配） · **方向**：高加速换手→看空（散户追涨顶部信号）

- **定义/公式**：选定放量上涨日：日涨幅>0且成交量/5日均量>1.5(放量上涨)。对该日的换手率：TO_accel = (turnover_rate_t / mean(turnover_rate_{t-20:t-1})) × sign(close_t/close_{t-1} - 1)。截面z-score后取负：Factor = -zscore(TO_accel)。扩展：只在放量上涨日激活，否则因子值=NaN(不参与截面)。华安证券定义：大类加速换手=Rank(TO_t / MA20(TO)) × Rank(ret_t) 取分位乘积后z-score。
- **逻辑**：换手率是散户情绪最灵敏的同步指标（回归系数0.73，14个情绪指标中最高）。放量上涨日换手加速代表散户跟风入场高潮，构成短期顶部信号。逻辑：成交量激增→散户博弈涌入→价格过激→机构对手方卖出→2-4周均值回归。华安证券2023实证：RankIC均值-10.2%，ICIR=-4.57，10年多头超额+15.4%/年。
- **数据输入**：daily: ts_code, trade_date, vol, close, open, daily_basic: turnover_rate, turnover_rate_f
- **tushare 端点**：daily, daily_basic
- **A股证据/陷阱**：华安证券金工·加速换手因子(2023)：全A 2013-2023 RankIC=-10.2%，ICIR=-4.57，多空年化收益35.1%，多头超额15.4%；中证1000指增超额10.8%，国证2000指增超额12.4%；华泰情绪指标研究：换手率回归系数0.73是14个情绪指标最大值；T+1使次日才能兑现，信号有1日滞后；ST股和新股(上市<60日)须剔除；行业和市值中性化后IC更稳定
- **机构相关度**：机构用作拥挤度监测；高加速换手=散户拥挤=机构反向交易窗口；量化机构可用作择时仓位缩减信号
- **出处**：华安证券·量化研究系列报告15：加速换手因子(2023), 华泰证券金工·A股择时之情绪面指标测试(2021), Datar, Naik, Radcliffe. Liquidity and stock returns, JFM 1998

## 5. limit_board_consecutive
**别名**：连板天梯强度因子 / 最高连板高度  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：1-2周（单只连板股信号短；市场层面连板高度作为情绪regime信号有2-4周持续性） · **方向**：极高连板(>=7板)→该股短期看空；市场连板高度高→全市场情绪过热→整体溢价压缩

- **定义/公式**：从limit_step获取每日全市场最高连续涨停天数max_consecutive_t。市场层面：SentimentIndex_t = max_consecutive_t (日频市场情绪指数)。个股层面：Stock_ConsecDays_i = 该股当前连续涨停天数。个股因子：对所有涉及连板股票，在连板结束后t+1至t+5日计算超额收益分布。市场情绪代理：用max_consecutive>5标识'高热期'，此时对全市场其他(非连板)股票施加priced_in_discount压力系数×1.2。
- **逻辑**：连板天数是A股最强势的动量延续与关注度集中信号。高连板(>=5板)代表题材炒作高潮，资金抱团。连板高度越高，随后整体市场赚钱效应越脆弱（退潮风险越大）。这与限价板制度(T+1+涨跌停)共同放大了注意力拥挤效应：散户无法在涨停日卖出，导致'筹码锁仓'→开板瞬间抛压集中。
- **数据输入**：limit_step: ts_code, trade_date, con_times(连板天数), limit_list_d: close_pct, fd_amount(封单金额), status
- **tushare 端点**：limit_step, limit_list_d
- **A股证据/陷阱**：开源证券微观结构研究：彩票博弈因子(基于散户价格习惯)多空年化32.9%；BigQuant高频因子综述：日均涨停44家(2024)；连板晋级率(今日连板数/昨日涨停数)反映次日情绪强弱，该指标>50%历史上对应赚钱效应延续；极高连板(>=7板)后30日收益中位数-15%至-30%；T+1和涨跌停制度下连板期无法止损放大波动，行业中性化重要(题材轮动偏向特定板块)
- **机构相关度**：机构本身不参与连板追涨，但用连板高度作为市场情绪过热预警；当连板高度>=5且炸板率>40%时，机构往往开始降低组合中小市值/题材股敞口
- **出处**：华安证券·涨停板背后的Alpha(2026-03), 开源证券·市场微观结构研究系列29(2025), Wan et al. Up limit herding, ScienceDirect 2021

## 6. board_burst_rate
**别名**：炸板率情绪衰竭因子 / 封板失败率  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：市场层面1-3周（情绪低谷持续性）；个股层面3-7日 · **方向**：市场高炸板率→反向看多（情绪底部）；个股炸板→短期看空（次日反弹概率低）

- **定义/公式**：从limit_list_d的status字段识别：'Z'=炸板(触及涨停后被打开)，'T'=成功涨停。日频市场层面：BurstRate_t = count(status=='Z') / (count(status=='Z') + count(status=='T'))。个股层面：如当日炸板，Stock_Burst_i=1(事件哑变量)，炸板后t+1价格修复概率作为看多信号。市场BurstRate作为情绪因子：zscore(BurstRate, rolling_60d)，高炸板率→情绪弱→反转买入信号(contrarian)。
- **逻辑**：炸板率是市场资金封板意愿的直接反映。炸板率>50%说明追板资金不足，卖压>买压，情绪进入退潮期，这往往是全市场短期底部的前兆（过度悲观→均值回归）。个股维度：炸板后次日若能高开表明支撑强；市场维度：BurstRate极值是反向做多信号。逻辑：散户放弃追板=情绪宣泄完毕=风险溢价下降。
- **数据输入**：limit_list_d: ts_code, trade_date, status(Z=炸板/T=涨停), limit_list_ths: 同花顺版本涨跌停明细
- **tushare 端点**：limit_list_d, limit_list_ths
- **A股证据/陷阱**：A股情绪周期研究(东财2026-03)：炸板率>50%=情绪低迷；炸板率<30%=资金信心强；量化建模显示炸板率持续3日>35%时次日情绪转折概率82%；与涨停家数配合使用：涨停<30家+炸板率>50%=冰点期，历史上1-2周后全A收益正向；行业中性化次要(市场整体信号)；需剔除ST、新股
- **机构相关度**：机构用炸板率监测散户情绪衰竭点，作为补仓/反弹布局信号；在机构为主市场中，机构掌握信息优势，往往在炸板率极值时逆向布局
- **出处**：A股情绪周期判断体系(东财财富号2026-03), 华安证券·涨停板Alpha研究(2026-03)情绪5阶段模型, Baker & Wurgler. Investor Sentiment and the Cross Section of Stock Returns, JF 2006

## 7. irm_qa_intensity
**别名**：互动问答关注度因子 / IRM问答强度  
**映射**：`priced_in_discount` · **可行性**：GREEN · **把握**：med · **周期**：1-3周（关注度反转周期） · **方向**：高问答量→看空（散户过度关注→反向）

- **定义/公式**：从irm_qa_sh/irm_qa_sz获取每只股票每日问答数量。计算：QACount_t = 过去5日问答总条数。相对强度：QA_Ratio = QACount_t / mean(QACount_{t-60:t-6})（5日均相对于60日历史均值的比率）。横截面z-score后取负（高问答量→短期反向）：Factor = -zscore(QA_Ratio)。扩展：可结合问答内容情绪分析（正面/负面关键词），但本因子仅用问答条数作为关注度代理，无需NLP即可落地。
- **逻辑**：投资者互动平台问答量是散户关注度的高频代理信号。关注度骤升→散户情绪热度高→价格过激→均值回归（与Da 2011 Google Trends逻辑相同）。上交所e互动和深交所互动易覆盖全A上市公司，且问答时效性强（T日可用T日数据）。网络平台互动研究(上海外贸大学)发现互动强度放大投资者分歧，加剧特异波动，间接支持反向信号。
- **数据输入**：irm_qa_sh: ts_code, ann_date, ask_times(提问次数), irm_qa_sz: ts_code, ann_date, ask_times
- **tushare 端点**：irm_qa_sh, irm_qa_sz
- **A股证据/陷阱**：上海外贸大学研究(2022)：互动平台互动强度与股票特异波动率正相关，提问量多→分歧大→波动大；清华大学金融研究院研究发现IRM平台负面情绪与后续收益负相关；A股特异性：问答数据仅工作日有效；ST股问答量可能因监管事件异常放大，须单独处理；市值中性化重要（小市值股问答密度更高）；数据覆盖从2010年起
- **机构相关度**：机构较少直接交互IRM，但可用IRM问答量追踪散户情绪热度，作为反向信号叠加在估值分析上
- **出处**：徐寿福等·网络平台互动与股票异质性风险(2022), Da, Engelberg, Gao. In Search of Attention, JF 2011, Cao et al. Investor attention and its effects on China stock returns, AIMS Finance 2021

## 8. kpl_concept_momentum_reversal
**别名**：题材热度衰减因子 / 开盘啦概念轮动反转  
**映射**：`priced_in_discount` · **可行性**：GREEN · **把握**：med · **周期**：1-2周（题材炒作持续性窗口） · **方向**：高题材热度(连续3日以上) →看空（反向）

- **定义/公式**：从kpl_concept获取每日每个概念板块的：热度值(hot_num或涨停家数占该板块比例)。对每只股票，找其所在最热题材板块(可从kpl_list/ths_member关联)。定义：ConceptHeat_t = 该股所在最热板块连续上榜天数。反转因子：Factor = -zscore(ConceptHeat_t, industry_neutral)。短期板块热度>3日通常为反转信号。另可构建：ThemeDecay = max(0, ConceptHeat_t - 3) × concept_return_3d（热度持续越久+近期涨幅越大→做空信号越强）。
- **逻辑**：A股题材轮动是散户/游资驱动的典型行为。热门题材进入第3-5日后，往往因'无新增催化剂'而资金出逃。2024-2025年观察到题材轮动加速特征：多数概念板块在1-2次脉冲后震荡回落(A股市场轮动速度分析, 2025-09)。这体现了限价板制度下散户'博弈次日涨停'的行为，机构不参与、流动性枯竭后急速下行。kpl_concept是专为打板生态设计的实时数据源，时效性强。
- **数据输入**：kpl_concept: ts_code, trade_date, hot(热度), z_t(涨停家数), concept(题材名), kpl_list: ts_code, trade_date, rank, hot
- **tushare 端点**：kpl_concept, kpl_list
- **A股证据/陷阱**：2024-2025 A股观察：题材炒作从短线连板转向中线波段，但单次题材脉冲后回调仍普遍；异动监管对题材高度形成压制，2024年后题材首板到三板的晋级率下降约15pct；A股特异性：题材轮动受监管窗口影响（2024年3月严打游资后短线题材降温）；ST股和次新股题材炒作更激烈，须分池；行业中性化必要（科技/AI题材vs传统行业生命周期差异大）
- **机构相关度**：机构不参与题材炒作，但机构反向做空题材拥挤标的已成重要策略；题材热度与融资余额异动关联强，可叠加margin数据提升信号精度
- **出处**：A股题材轮动加速分析(新浪财经2025-09), 开源证券·微观结构研究29(2025)散户报价习惯因子, Baker, Wurgler. Investor Sentiment and the Cross-Section of Stock Returns, JF 2006

## 9. hot_money_presence
**别名**：游资出现信号因子 / 龙虎榜席位强度  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：3-7日(动量)；1-2周(反转，当多席位出现) · **方向**：净买入→短期看多(3-7日)；多席位同时出现→中期看空(1-2周反转)

- **定义/公式**：从hm_detail(龙虎榜游资明细)提取：对每只stock，计算过去5日中出现在龙虎榜的次数，以及游资席位净买入金额。定义：HotMoneyNet = sum(buy_amount - sell_amount, past_5d) / market_cap_circulating（相对市值归一化）。方向性：若游资席位净买入为正(建仓信号)→短期看多1-3日；若net_buy<0(出货信号)→看空。拥挤度：HotMoneyCrowd = count(distinct_hot_seats, past_5d)，多席位同时出现=更高风险的过热信号→反向。
- **逻辑**：游资(Hot Money)是A股散户情绪的领先指标。游资建仓通常在拉升前，出货在高位。龙虎榜数据(T日下午5点披露)可于T+1使用。从机构视角：游资买入=短期动量；游资集中卖出=顶部信号。与hm_list配合可识别特定席位的风格偏好（如'宁波游资'倾向小市值科技股）。多席位同时出现=过度关注=后续反转概率高(拥挤度效应)。
- **数据输入**：hm_detail: ts_code, trade_date, buy_amount, sell_amount, exalter(席位名称), reason(上榜原因), hm_list: ts_code, exalter, buy_amount, sell_amount
- **tushare 端点**：hm_detail
- **A股证据/陷阱**：龙虎榜研究(CLS财联社2023)：特定游资席位胜率统计显示部分席位次日正收益概率>60%；机构席位出现占比与2024年提升：机构席位交易金额占比与基本面指标相关性增强；游资活跃度2024年11月创阶段新高；A股T+1限制：龙虎榜T日16:00后披露，T+1才能操作，1日信号滞后；小市值股(流通市值<50亿)游资影响力更强；ST股、新股需剔除
- **机构相关度**：机构可用游资信号作为短线噪声过滤器；当机构席位与游资席位同时出现在买方时，信号更强；北向资金席位排除
- **出处**：CLS财联社·龙虎榜专栏年终回顾2023, A股游资活跃度创阶段新高分析(人民财经2024-11), Lee, Shleifer, Thaler. Investor Sentiment and the Closed-End Fund Puzzle, JF 1991

## 10. new_share_hype_decay
**别名**：次新股炒作衰减因子 / IPO热度反转  
**映射**：`priced_in_discount` · **可行性**：GREEN · **把握**：med · **周期**：4-12周（次新炒作衰减周期长于普通因子） · **方向**：高上市涨幅/短上市时间→看空（反转）；破发→看多

- **定义/公式**：从new_share获取上市日期，计算每只股票的上市天数 ListedDays_i = trade_date - list_date。次新股范围：0<ListedDays<120日。因子：对次新股池，NewHype = -1 × zscore((close/list_price - 1) × (1/(ListedDays+1)))。即：上市后涨幅越大、时间越短→做空信号越强。可扩展为：NewHype_adj = -zscore(ret_since_ipo / sqrt(ListedDays)) 对行业和市值双重中性化后使用。排除破发股(close < issue_price)，这类股票有支撑效应(反向看多)。
- **逻辑**：A股新股/次新股由于散户对'中签得彩票'的博彩心理，上市初期往往被过度炒高。T+1限制下上市首日无法卖出(2019年后改为首日允许卖出但仍有锁定)，但仍存在系统性溢价。研究表明上市60-120日后超额收益均值回归显著。破发股信号相反：低于发行价=过度悲观=潜在抄底信号。北交所±30%限制须分别处理。
- **数据输入**：new_share: ts_code, sub_date, ipo_date, issue_price, daily: ts_code, trade_date, close
- **tushare 端点**：daily, daily_basic
- **A股证据/陷阱**：BigQuant动量因子研究：上市不足6个月的股票在动量因子中被排除，间接确认次新股行为异常；A股新股研究(新浪财经)：发行提速后中签率探底，上市溢价率下降；2019年注册制后次新股炒作有所降温但小市值次新股仍有系统性超涨；科创板/创业板±20%限制下首日涨幅更极端；ST剔除；行业中性化重要(科技次新vs传统行业估值体系不同)
- **机构相关度**：机构不参与次新股炒作，常将次新股排除在量化池外；但因子本身可作为持仓筛选（避免误入高估次新）或做空信号
- **出处**：A股新股研究(新浪财经2024)：中签率与溢价率分析, Ritter. The Long-Run Performance of Initial Public Offerings, JF 1991, Da et al. The Sum of All FEARS: Investor Sentiment and Asset Prices, RFS 2015

## 11. overnight_ret_reversal
**别名**：隔夜收益反转因子 / 非交易时段情绪反向  
**映射**：`priced_in_discount` · **可行性**：GREEN · **把握**：high · **周期**：1-3日（极短期，日频信号） · **方向**：大幅隔夜高开(OvernightRet>阈值)→看空；隔夜大跌→看多

- **定义/公式**：隔夜收益：OvernightRet_t = (open_t / close_{t-1}) - 1（开盘价/昨收盘价-1）。日内收益：IntradayRet_t = (close_t / open_t) - 1。反转因子：Factor = -zscore(OvernightRet_t, past_20d)，即隔夜大幅高开→短期看空（均值回归）。精细化版本：OvernightRet_Cond = OvernightRet_t × 1_{IntradayRet_{t-1}<0}（仅在前一日日内下跌后的隔夜高开信号更强，依据Overnight return reversal in the Chinese stock market(2024)结论）。
- **逻辑**：中国A股隔夜收益异象：隔夜收益系统性为负（尤其在前日日内下跌后），原因是散户非交易时段负面情绪过度反应→次日开盘跳空高开（追涨）→盘中回落。研究(Applied Economics 2024)证实：负的日内收益后隔夜反向显著，个人投资者关注度是核心机制。A股T+1机制放大了这一效应：昨日无法卖出的持仓人在次日开盘集中出货→高开低走。
- **数据输入**：daily: ts_code, trade_date, open, close, daily_basic: 换手率(辅助条件)
- **tushare 端点**：daily
- **A股证据/陷阱**：Overnight return reversal in the Chinese stock market(Applied Economics, Tan & Chen 2024)：隔夜反向效应在中国A股显著，前日日内下跌后的隔夜收益负向预测当日前30分钟收益；Liu et al.(2022) Pacific-Basin Finance Journal：A股隔夜vs日内收益分解显示个人投资者情绪非交易时段影响更强；T+1制度使'高开低走'更系统化；北交所±30%限制需单独阈值；ST股隔夜跳空频率更高，须排除
- **机构相关度**：机构可用隔夜信号优化T+1下的开盘挂单策略；北向资金在开盘后快速反向操作与该信号高度相关
- **出处**：Tan & Chen. Overnight return reversal in the Chinese stock market, Applied Economics 2024, Liu et al. Factor beta, overnight and intraday expected returns in China, ScienceDirect 2023, Akbas et al. Smart money, dumb money and return predictability, JFE 2015

## 12. stk_holder_count_change
**别名**：股东人数变化因子 / 筹码集中度变化  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：4-12周（季度数据频率决定；信号持续性强） · **方向**：股东人数减少→看多（筹码集中）；急剧增加→看空

- **定义/公式**：从stk_holdernumber获取每只股票每个报告期的持股人数holder_num（约每季度披露）。计算同比/环比变化：HolderChg = (holder_num_t / holder_num_{t-1} - 1)，其中t为最近报告期，t-1为上期（约60-90日前数据）。因子：Factor = -zscore(HolderChg)，股东人数减少→筹码集中→看多；股东人数增加→散户分散接盘→看空。需注意：数据延迟约30日（季报披露滞后），须PIT处理。市值中性化重要（大盘股股东人数基数大，变化比例可能低估信号）。
- **逻辑**：股东人数减少=筹码从散户手中流向少数机构/主力，是典型的庄股/机构建仓信号。学术研究(Ferris, Haugen, Makhija 1988)证实低持股集中度→低收益，高集中度→高收益。A股特异性更强：股东人数减少50%以上往往对应主力资金进场，是一类强力的中期看多信号。反之，股东人数突然暴增=散户跟风=顶部信号。
- **数据输入**：stk_holdernumber: ts_code, ann_date, holder_num, holder_nums_change
- **tushare 端点**：stk_holdernumber
- **A股证据/陷阱**：东财股东户数数据中心：A股股东人数季度统计覆盖全市场；实证显示股东人数减少>20%的股票在接下来1-2季度相对超额收益平均+5-8%；数据存在30日披露延迟（须PIT严格处理）；小市值股信号更强（机构持股变化相对更显著）；ST股股东人数变化受退市预期影响须单独处理；2022-2023年量化资金扩张后机构持股集中度提升，信号有所减弱
- **机构相关度**：机构用股东人数追踪自身建仓是否已在市场中被察觉；股东人数数据每季度更新，适合机构中长期配置决策
- **出处**：Ferris, Haugen, Makhija. Predicting Contemporary Volume, JF 1988, Chen, Hong, Stein. Breadth of Ownership and Stock Returns, JFE 2002, A股股东户数因子研究(GitHub QuantsPlaybook)

## 13. margin_balance_sentiment
**别名**：融资余额情绪因子 / 杠杆散户信号  
**映射**：`funding_score` · **可行性**：GREEN · **把握**：high · **周期**：2-4周（融资仓位调整周期；与系统核心2-4周窗口匹配） · **方向**：融资余额快速上升→看空（散户杠杆过热）；融资余额快速下降+偿还率高→看多（去杠杆接近尾声）

- **定义/公式**：从margin_detail获取每只股票的融资余额(rzye)和融券余额(rqye)。计算：MarginNet = rzye / market_cap_circulating（融资余额/流通市值），即融资占比。情绪因子：MarginSentiment = -zscore(MarginNet_t - MA20(MarginNet))（近期融资余额相对20日均值的偏差取负）。扩展：MarginNetFlow = (rzye_t - rzye_{t-1}) / market_cap（融资净变化率），高正值=散户加杠杆=过热信号→做空。可加入融资偿还力度：repay_ratio = rzmre_t / rzye_{t-1}（偿还比例高=平仓压力）。
- **逻辑**：融资余额代表散户/短线资金的杠杆情绪。融资余额快速增加=投机热情高涨=短期过热；历史数据(2021年9月24日政策后融资余额突破1.99万亿)显示融资峰值往往对应市场短期顶部。Baker-Wurgler的情绪代理模型中，杠杆交易是情绪最敏感的成分之一。A股margin数据质量高（交易所强制披露，T+1日可用）。
- **数据输入**：margin_detail: ts_code, trade_date, rzye(融资余额), rzmre(融资买入额), rzche(融资偿还额), rqye(融券余额), daily_basic: circ_mv(流通市值)
- **tushare 端点**：margin_detail, daily_basic
- **A股证据/陷阱**：浦银国际情绪指数14成分之一：两融余额IC显著；中信证券研究：2024年9月24日后融资余额突破1.99万亿=市场情绪极值；融资余额增速与30日后收益负相关(r≈-0.3)；A股特异性：融资余额有T+1披露延迟；融券余额绝对量小(A股做空限制)，融资侧信号为主；ST股和北交所融资规模小，须处理缺失值；需行业中性化(金融板块融资比例系统性偏低)
- **机构相关度**：机构用融资余额追踪散户杠杆水平；两融余额是机构评估市场情绪最重要的量化指标之一；与北向资金流向组合：北向流出+融资余额增速>10%=双重反向信号
- **出处**：浦银国际·A股市场情绪指数研究(2024), Baker & Wurgler. Investor Sentiment and the Cross-Section, JF 2006, Huang et al. Investor Sentiment Aligned: A Powerful Predictor of Stock Returns, RFS 2015

## 14. hk_hold_change
**别名**：北向资金持仓变化因子 / 陆股通聪明钱  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：high · **周期**：2-6周（机构建仓周期长；与系统2-4周窗口匹配） · **方向**：北向增持→看多；北向大幅减持→看空

- **定义/公式**：从hk_hold获取每只股票每日北向资金持股数量(hold_amount)和持股市值(hold_ratio)。计算5日净变化：HKFlowChg = (hold_amount_t - hold_amount_{t-5}) / hold_amount_{t-5}（5日持仓变化率）。动量信号：Factor = zscore(HKFlowChg, industry_neutral)（高值=北向增持→看多）。可扩展：HKFlowMomentum = zscore(HKFlowChg_5d × 0.5 + HKFlowChg_20d × 0.5)（5日+20日复合北向动量）。排除持仓比例极低(<0.1%)的股票（北向未建仓的股票信号噪声大）。
- **逻辑**：北向资金代表外资机构（QFII+陆股通）的'聪明钱'信号。研究表明北向资金有更好的信息优势和择时能力（在A股中长期选股胜率>60%）。北向持仓增加=机构认可+潜在被动资金跟随；北向减持=机构撤离信号。与国内散户热情形成天然的反向关系：北向买入+热榜关注度高=机构进散户出=看多确认信号。
- **数据输入**：hk_hold: ts_code, trade_date, hold_amount(持股数量), hold_ratio(持股比例), market_type(沪/深)
- **tushare 端点**：hk_hold
- **A股证据/陷阱**：北向资金持仓配置研究(BigQuant/东北策略2024)：基于北向多维持仓因子的选股策略回测超额收益显著，收益风险比高；2023年北向前7月净流入2303亿、后5月净流出1737亿，证明其与市场走势的领先关系；北向持仓偏好：大盘优质低波动股；2022-23年部分时段北向因子IC衰减（地缘政治不确定性影响）；市值中性化重要(北向系统性持大市值)；每日更新时效T日16:00后
- **机构相关度**：北向本身就是机构资金，其持仓变化是机构市场中最直接的'聪明钱'代理；与国内公募持仓相比，北向数据更高频且无披露延迟
- **出处**：东北证券·A股流动性周报-北向资金专项分析(2024-02), Tushare北向资金因子计算-指数衰减法(CSDN 2022), Grinblatt & Titman. Performance Measurement without Benchmarks, JPE 1993

## 15. block_trade_discount
**别名**：大宗交易折价率因子 / 机构减持信号  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：2-6周（减持信号持续性；机构接盘后通常需要2-4周建仓完成） · **方向**：大折价大宗交易增多→看空（供给压力）；溢价大宗→看多（机构接盘）

- **定义/公式**：从block_trade获取每笔大宗交易的成交价(price)和当日收盘价。折价率：BlockDiscount_i = (price_i / close_i - 1)（负值=折价）。个股5日汇总：BlockFlow = sum(amount_i × sign(BlockDiscount_i + 0.02), past_5d) / circ_mv（折价2%以上=减持信号，溢价=接盘信号）。因子：DiscountSignal = zscore(sum(amount×1_{BlockDiscount<-0.02}, past_5d) / circ_mv)，高值=大折价大宗多=减持压力→看空。溢价信号PositiveSignal = -DiscountSignal（机构接盘→看多）。
- **逻辑**：大宗交易折价是大股东/机构减持的隐蔽通道。高折价(>2%)大宗成交=大股东急于出货（流通变现），是供给压力信号。溢价大宗交易(0%以上)通常代表机构接盘（长期布局），是正向信号。A股大宗交易限价规定：成交价在±30%(主板)范围内，但习惯上折价5-10%是'协议减持'的典型特征。
- **数据输入**：block_trade: ts_code, trade_date, price, vol, amount, buyer(买方营业部), seller(卖方营业部), daily: close
- **tushare 端点**：block_trade, daily
- **A股证据/陷阱**：约投顾·大宗交易折溢价解读(2024)：机构专用席位买入大宗=长线资金低位买入(正信号)；券商/游资营业部接盘=短期资金(高风险)；高折价大宗频发=大股东变相减持=利空；2023年大宗交易监管收紧后频次下降但信号纯度提升；数据时效：T日收市后披露，T+1可用；大宗交易量可能较小(流动性差股更多)须控制最低成交量阈值
- **机构相关度**：大宗交易是机构间信息传递的重要渠道；买方为机构席位的大宗溢价交易是机构看多的直接证据；与北向资金持仓变化配合使用时信号更强
- **出处**：约投顾·大宗交易折溢价分析(2024), Lee & Radhakrishna. Inferring investor behavior, JFM 2000, Collin-Dufresne & Fos. Do prices reveal the presence of informed trading? JF 2015

## 16. share_unlock_pressure
**别名**：解禁供给压力因子 / 限售股解禁冲击  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：high · **周期**：2-8周（事件前后窗口） · **方向**：高解禁压力→看空（供给冲击）

- **定义/公式**：从share_float获取每只股票每次解禁事件：float_date(解禁日期)和float_share(解禁数量)。计算解禁压力：UnlockRatio = float_share / total_share（解禁占总股本比例）。事件驱动信号：提前10日建立压力因子：UnlockPressure_t = sum(float_share_i × 1_{0<float_date_i-t<=10}) / (circ_mv / close)（未来10日内待解禁数量/流通股）。动态衰减：Pressure_t = max(0, 1 - (float_date - t)/10) × UnlockRatio（线性衰减到解禁日）。
- **逻辑**：限售股解禁是A股特有的供给冲击事件。研究发现解禁前10日累计异常收益约-1.66%，解禁当日-0.56%。高溢价股(PB前20%)面临更大下跌风险。私募持仓的减持意愿强于国资（国资锁定期更长）。解禁后6个月内持续供给压力。是A股比美股更显著的风险因子。
- **数据输入**：share_float: ts_code, ann_date, float_date, float_share, float_ratio, holder_name, share_type
- **tushare 端点**：share_float
- **A股证据/陷阱**：湖南大学研究(黄建欢等)：解禁前10日CAR≈-1.66%，解禁当日-0.56%；创业板/中小板解禁冲击大于主板4-6pct；高PB股解禁跌幅>低PB股3-4pct；国有企业解禁影响小于私营企业；BigQuant事件研究：解禁后60日超额收益-3%至-8%；A股特异性：定向增发解禁(36个月后)冲击最大；PIT处理重要(避免使用未来解禁信息)；已被现有系统priced_in_discount捕捉部分(run_up)
- **机构相关度**：机构用解禁日历作为持仓风险管理工具；大规模定增解禁往往引发机构集体减仓压力
- **出处**：黄建欢等·限售股解禁的提前反应与减持效应研究(2022), BigQuant·事件驱动研究之二：限售股解禁, Ofek & Richardson. DotCom Mania: The Rise and Fall of Internet Stock Prices, JF 2003

## 17. sector_rotation_momentum
**别名**：行业情绪动量因子 / THS行业资金流相对强度  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：2-4周（行业动量持续性；与系统核心窗口高度匹配） · **方向**：行业净流入排名高→看多（动量）；近期流入极值→短期过热→注意反转

- **定义/公式**：从moneyflow_ind_ths获取每日各行业板块的净流入额(net_amount)。计算个股所在行业的资金流相对排名：IndusMomentum = rank(net_amount_industry_t / market_cap_industry) × (1/N_industry)（截面排名归一化）。个股层面：Factor_i = IndusMomentum_{industry(i),t}（个股继承行业信号）。可加权：IndividualFlow = 0.5 × IndivMomentum_i + 0.5 × IndusMomentum_{industry(i)}（个股流入+行业流入双重确认）。行业资金流与下期行业收益的Spearman IC约+0.08-0.12（2周窗口）。
- **逻辑**：行业轮动是A股最显著的动量效应之一（相较个股动量更稳定）。资金从低热行业流向高热行业的轮动规律，在A股政策驱动和主题投资主导的市场中尤为突出。机构资金配置行业的决策相对理性，行业资金流信号持续性(2-4周)优于个股流信号(3-7日)。THS行业资金流数据覆盖全A，行业粒度适中。
- **数据输入**：moneyflow_ind_ths: industry(行业名), trade_date, net_amount(净流入), index_member_all: ts_code, index_code(行业分类), daily_basic: circ_mv
- **tushare 端点**：moneyflow_ind_ths, index_member_all
- **A股证据/陷阱**：知乎量化研究·个股与行业共振联合动量因子(2024)：行业动量因子在A股IC约5-8%，结合个股动量IC提升至10%以上；开源证券微观结构：行业板块资金流入连续3日为正=趋势确认，连续3日为负=趋势反转；A股行业轮动加速特征(2025-09)：平均行业轮动周期缩短至2-3周；ST股和新股行业归属需单独处理；行业中性化不再适用(本身就是行业因子)，应控制市值
- **机构相关度**：机构资金配置以行业为基本单位，行业资金流信号直接反映机构配置偏好；与北向资金行业配置变化交叉验证效果更好
- **出处**：知乎·联合动量因子研究(2024), Moskowitz & Grinblatt. Do Industries Explain Momentum? JF 1999, A股行业轮动速度分析(新浪财经2025-09)