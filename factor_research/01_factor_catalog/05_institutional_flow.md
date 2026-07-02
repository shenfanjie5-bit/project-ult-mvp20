# 因子族：institutional_flow

> 机构/资金流族是本系统 capital_sentiment 和 funding_score 轴的核心填充来源，当前两个轴近乎空置。该族直接利用 tushare 机构/资金/筹码侧极丰富的端点，将北向持股变动、游资净买、大宗折溢价、融资动量、筹码集中度等7大维度转化为量化因子。最值得优先接入的3个因子为：①北向持股变化率(hk_hold季度差分→cyq辅助填日内)，信息含量高、与机构行为高度相关；②融资买入动量(margin日度融资买入占成交比变化，数据完整、日更)；③主力净流入率CNIR改进版(moneyflow超大单+大单净流入/成交额)，大单阈值动态标准化后2022-2024年IC仍显著。筹码获利盘比例(cyq_perf.winner_rate)作为散户/套牢盘压力因子，是A股特异性极强的补充信号。

共 17 条。


## 1. 北向持股变化率 (HK_Hold_Chg)
**别名**：陆股通持仓变动因子 / 外资增减持动量  
**映射**：`capital_sentiment` · **可行性**：YELLOW · **把握**：med · **周期**：季度(63TD)为主；日频NF_Ratio可捕捉2-4周趋势；注意2024年8月19日起停止日度披露，改为季度公布，日频因子须切换为moneyflow_hsgt替代。 · **方向**：高值(外资增持)→看多

- **定义/公式**：HK_Hold_Chg_t = (hk_hold.vol_t - hk_hold.vol_{t-N}) / shares_float_t × 100%
其中 N=63个交易日(约1季度)；vol 取 hk_hold 接口的 vol 字段(持股数量)；shares_float 取 daily_basic.float_share。
可扩展：用 moneyflow_hsgt 的 north_money(日度北向净流入额)做归一化——将近21日累计北向净买入额 / 个股近21日日均成交额，得到【北向资金压力比率 NF_Ratio】作为日频版替代。
- **逻辑**：陆股通投资者以机构为主、价值导向，持股增加代表外资认可基本面与估值，具备信息优势（实际持有2.59万亿元A股，2025年末）。增持趋势通常领先或同步机构配置行为，对大盘/龙头股预测力强。
- **数据输入**：hk_hold.vol, hk_hold.trade_date, daily_basic.float_share, moneyflow_hsgt.north_money(替代)
- **tushare 端点**：hk_hold, moneyflow_hsgt, daily_basic
- **A股证据/陷阱**：2024年8月起北向日度数据停播，日频版本须改用moneyflow_hsgt净额代理；外资持股占A股流通市值约3.48%，对小微盘预测力弱；需行业中性化（外资偏好消费/金融/白酒），ST/新股剔除。季度因子有效，日频因子噪声大。东北证券2024报告确认外资更多受市场波动驱动而非行业择时。
- **机构相关度**：极高——外资机构代表价值定价者，增持是机构认可信号
- **出处**：东北证券策略2024-02 《北向资金分析方法论》, 陈健/曾世强《北向资金是A股的风向标吗》金融市场研究2024, tushare hk_hold文档

## 2. 融资买入动量因子 (Margin_Buy_Momentum)
**别名**：融资买入占比变化 / 杠杆资金净买压  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：high · **周期**：10-21TD动量信号；60-90TD反转风险 · **方向**：中短期高值→看多；极端高值(行业前5%)→反转风险看空

- **定义/公式**：步骤1: 日频融资买入占比 MB_ratio_t = margin.buy_amount_t / daily.amount_t
步骤2: 动量 MB_Mom_N = MB_ratio_t - MB_ratio_{t-N}，推荐 N=10或21TD
步骤3: 行业内对 MB_Mom 做截面rank标准化，市值加权中性化后得最终因子值
亦可计算融资余额变化率: dME/ME = (margin_balance_t - margin_balance_{t-N}) / margin_balance_{t-N}
- **逻辑**：融资买入反映杠杆散户/小机构的乐观预期，短期内形成价格正反馈；融资余额增加→做多动能增强→短期看多；但高融资余额同时积累强制平仓风险，极端高值是反转信号。两融余额占A股流通市值约2.5%(2024)，融资交易额占成交约7.7%，规模可观。
- **数据输入**：margin.buy_amount(融资买入额), margin.close_amount(融资偿还额), margin.fin_balance(融资余额), daily.amount(成交额)
- **tushare 端点**：margin, margin_detail, daily, daily_basic
- **A股证据/陷阱**：张峥等(2014)确认融资余额作为情绪代理对A股短期收益有显著正向预测；2024年政策催化后融资余额快速扩张至1.99万亿元，因子短期动量效应仍有效但极端高位需设置截断（涨跌停日成交失真）；ST股/停牌股剔除。
- **机构相关度**：中——主要捕捉杠杆散户行为，但极端值也反映机构止损/追涨
- **出处**：张峥等《融资融券与投资者情绪》2014, 方正证券量化研究2023年《融资融券日报》, tushare margin文档

## 3. 融券余额变化率 (Short_Interest_Chg)
**别名**：融券空头压力因子  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：21-63TD；空头压力具有中期持续性 · **方向**：高值(融券增加)→看空

- **定义/公式**：SI_Ratio_t = margin.stk_balance_t / daily_basic.float_share_t × circulating_price_t  (融券市值/流通市值)
SI_Chg_N = (SI_Ratio_t - SI_Ratio_{t-N}) / SI_Ratio_{t-N}，N=21TD
行业截面rank后取负向因子（高融券增速→看空）
注：slb_len（转融资）余额变化可作为补充验证
- **逻辑**：融券卖出反映机构做空意愿，融券余额增加表明智慧资金预期股价下跌，含有负向信息。国际文献(Dechow et al.2001)证实短售兴趣与未来负收益相关；A股融券规模小但信息含量高，卖方多为机构。
- **数据输入**：margin.stk_balance(融券余额), margin.sell_amount(融券卖出额), slb_len.slbamt(转融券余额), daily_basic.float_share
- **tushare 端点**：margin, margin_detail, slb_len, daily_basic
- **A股证据/陷阱**：A股融券规模较小(占流通市值<0.5%)，信息含量高但信号稀疏，小市值/ST股几乎无融券；需区分机构对冲融券 vs 投机性融券；2023年8月监管收紧融券规模，2024年后数据结构变化需注意；涨跌停日融券无法执行，因子应滞后1TD。
- **机构相关度**：高——融券主体几乎全为机构或大资金
- **出处**：Dechow et al. 'Short-sellers, fundamental analysis, and stock returns' JFE 2001, 方正证券2023年融资融券研究日报, 浦银国际《融资融券专题》2024

## 4. 主力净流入率 CNIR (Composite Net Inflow Rate)
**别名**：广义主力资金净流入因子 / 大单净流入率  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：5-10TD短期信号最强；21TD动量有意义 · **方向**：高值(净流入)→看多

- **定义/公式**：CNIR_t = (超大单净流入 + 大单净流入) / 当日总成交额
= (moneyflow.buy_elg_amount - moneyflow.sell_elg_amount + moneyflow.buy_lg_amount - moneyflow.sell_lg_amount) / moneyflow.trade_amount
周期化：CNIR_N = sum(CNIR_t, t-N+1..t)，N=5或10TD
改进版（开源金工2022）：动态标准化大单阈值——依据当年成交分布将大单下限设为前12个月中位订单金额的2倍，解决阈值漂移（2022→26万元, 2023→12万元, 2024→40万元）
- **逻辑**：大单/超大单净流入代表主力机构的方向性判断，信息含量高于散户小单。净流入持续为正说明主动买入行为，价格上涨概率提升。CNIR是国内量化最常用的资金流因子之一。
- **数据输入**：moneyflow.buy_elg_amount(超大单买入), moneyflow.sell_elg_amount(超大单卖出), moneyflow.buy_lg_amount(大单买入), moneyflow.sell_lg_amount(大单卖出), moneyflow.trade_amount(总成交)
- **tushare 端点**：moneyflow, moneyflow_dc
- **A股证据/陷阱**：华泰证券2018单因子测试：大单净流入因子IC≈0.03-0.05；开源金工2022改进版CNIR在沪深300内多头组月均超额+0.8%左右，但2024年9月政策催化后分组收益出现较大回撤。阈值不稳定是主要缺陷；涨停日大单买入失真需截断；ST/新股剔除。
- **机构相关度**：高——大单流入实际代表机构/游资/主力行为
- **出处**：华泰证券《单因子测试之资金流向因子》2018, 开源金工《大小单重定标与资金流因子改进》2022, 开源金工《资金流与交易行为：因子失效原因与讨论》2025

## 5. 东财/同花顺个股资金流净流入强度 (MF_THS_NetIn)
**别名**：同花顺主力净流入强度  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：3-10TD；情绪动量信号，不宜持有过长 · **方向**：高值(净流入)→短期看多

- **定义/公式**：MF_Net_t = (moneyflow_ths.buy_lg_amount + moneyflow_ths.buy_elg_amount - moneyflow_ths.sell_lg_amount - moneyflow_ths.sell_elg_amount)
MF_Strength_t = MF_Net_t / mktcap_float_t  (相对流通市值归一化)
N日累积：MF_Strength_N = sum(MF_Strength_t, t-N..t), N=5,10
同花顺版与东财版可对比验证，取均值或最大一致性
- **逻辑**：同花顺资金流以散户用户行为为基础，叠加主力订单分类，净流入强度反映短期做多势能。相比moneyflow（主要是机构端数据），moneyflow_ths更接近散户关注度，可作为情绪辅助指标。
- **数据输入**：moneyflow_ths中大单字段, daily_basic.circ_mv(流通市值)
- **tushare 端点**：moneyflow_ths, moneyflow_dc, daily_basic
- **A股证据/陷阱**：同花顺/东财数据与Wind数据存在差异（分类标准不同），单独使用噪声较大；应与CNIR交叉验证；涨跌停日需截断；行业中性化后IC约0.02-0.04。
- **机构相关度**：中——混合散户与机构信号
- **出处**：BigQuant资金流因子cn_stock_moneyflow文档, 华泰证券量化研究2018

## 6. 游资净买入强度 (HM_Net_Buy)
**别名**：龙虎榜游资资金因子  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：5-10TD超短期（游资做多后散户跟风期）；机构卖出信号21-63TD有效 · **方向**：游资净买入高值→短期看多；机构席位净卖出→看空/风险信号

- **定义/公式**：步骤1：从 hm_detail 获取 ts_code 在 [t-5, t] 区间内的上榜记录
步骤2：按 buy_amount - sell_amount 计算个股期间游资净买入额
步骤3：归一化 HM_Net_t = Σ(buy-sell)_{t-5..t} / avg_daily_amount_{t-20..t}
步骤4：若出现机构专用席位(trader='机构')净卖出，设置反向信号 HM_Inst_Sell = 机构席位净卖出额/成交额（负向因子）
事件标记：若 HM_Net_t > 阈值，则为短期看多事件；机构席位净卖出 → 减持风险信号
- **逻辑**：游资（hm_list中的活跃营业部）是A股特有的短期做多/题材炒作力量，龙虎榜上榜后往往引发散户跟风；而机构专用席位出现在龙虎榜卖出侧，是机构在高位减持的明确信号，含有负向信息。
- **数据输入**：hm_detail.buy_amount, hm_detail.sell_amount, hm_detail.trader(席位名), hm_list(游资名录)
- **tushare 端点**：hm_detail, hm_list
- **A股证据/陷阱**：华创证券报告(2022)：龙虎榜机构席位模型择时沪深300年化21.06%，Sharpe 0.938，胜率61.4%；单一游资席位胜率仅24%，须聚合多席位信号；T+1限制下龙虎榜信号次日才能买入，高估超短期IC；涨跌停集中出现使样本有限；ST股剔除。
- **机构相关度**：高——机构席位卖出是机构行为的直接观察
- **出处**：华创证券《特征分布建模择时系列之一：物极必反，龙虎榜机构模型》2022, 证券时报龙虎榜游资胜率分析2025

## 7. 大宗交易成交额占比因子 (Block_Trade_Ratio)
**别名**：大宗交易量比 / 大宗成交活跃度  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：21-63TD；大宗交易信息传递有滞后效应 · **方向**：高成交额占比+低波动率→看多；高折价率+高成交量波动率→看空

- **定义/公式**：BT_Ratio_t = Σ_{t-N..t} block_trade.amount / Σ_{t-N..t} daily.amount × 100%
N=21TD
行业内rank后中性化。
辅助因子——大宗成交量波动率：BT_VolStd = std(block_trade.vol_{t-N..t}) / mean(block_trade.vol_{t-N..t})
- **逻辑**：大宗交易是机构/大股东大笔转让的专属渠道，活跃度高说明机构在该股有大资金配置/减配需求，含有价格发现信息。光大证券2023报告证实：高成交额占比+低成交量波动率→主力建仓信号→后续超额收益显著。
- **数据输入**：block_trade.amount(成交额), block_trade.vol(成交量), block_trade.trade_date, daily.amount
- **tushare 端点**：block_trade, daily
- **A股证据/陷阱**：光大证券量化选股系列报告11（2023）：大宗成交额占比+低成交量波动率组合可产生显著超额收益；大宗折价率可能误导（机构过桥业务非真实看空）；需区分机构专用席位 vs 普通营业部；小市值股大宗交易噪声大，建议市值中性化。
- **机构相关度**：极高——大宗交易几乎只有机构/大股东参与
- **出处**：光大证券《提炼大宗交易背后蕴含的超额信息》量化选股系列报告11, 2023

## 8. 大宗折溢价率信号 (Block_Trade_Discount)
**别名**：大宗折价率因子 / 大宗溢价因子  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：10-21TD事件后效应 · **方向**：溢价高值→看多；深度折价→看空（过桥信号需过滤）

- **定义/公式**：BT_Disc_t = (block_trade.trade_price - daily.close) / daily.close × 100%  (当日收盘价为基准)
过去 N 笔大宗的加权平均折溢价率：BT_Disc_avg = Σ(BT_Disc × amount) / Σ(amount)，N=最近5笔或21TD内所有笔
溢价(>0)看多, 折价(<0)看空(但需甄别过桥用途——机构代持过桥折价无信息含量)
- **逻辑**：大宗溢价成交说明买方愿付出额外价格换取大宗量，表明对未来价格看涨；深度折价成交可能是主力出货（但过桥交易会稀释信号）。溢价大宗交易后超额收益显著，折价大宗交易后存在负收益倾向。
- **数据输入**：block_trade.trade_price, block_trade.amount, block_trade.buyer(买方机构), daily.close
- **tushare 端点**：block_trade, daily
- **A股证据/陷阱**：金融界2024报告：2023年折价率超30%的案例存在，折价大宗不等于卖出信号（主要为过桥代持）；溢价成交信号纯度更高；需过滤同一机构买卖两端均出现（过桥特征）的大宗记录；行业中性化后IC约0.02-0.03。
- **机构相关度**：高——识别机构大资金真实方向性意图
- **出处**：金融界《藏在大宗交易里的秘密》2024, 光大证券量化选股系列报告11, 2023

## 9. 筹码获利盘比例 (Winner_Rate_Factor)
**别名**：CYQ胜率因子 / 浮盈筹码占比  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：5-21TD反转信号；与动量因子反向配合 · **方向**：超高获利盘(>75%)→反转看空；极低获利盘(<25%)→反弹看多

- **定义/公式**：WR_t = cyq_perf.winner_rate_t  (当前价格下有浮盈的筹码比例，0-100%)
WR_Change_N = WR_t - WR_{t-N}  (筹码获利盘变化，N=5或10TD)
Supply_Pressure = WR_t > 70%  → 高获利盘时潜在卖压大→反转信号(看空)
Buy_Zone = WR_t < 30% → 低获利盘时套牢盘少→支撑较强(看多)
行业截面rank中性化
- **逻辑**：大量持仓者处于盈利状态时，随时可能止盈卖出，形成供给压力；反之当获利盘极少时，套牢盘不愿卖出，卖压小，支撑强。这是A股散户持仓成本意识的量化体现。
- **数据输入**：cyq_perf.winner_rate, cyq_perf.cost_50pct(中位成本), cyq_perf.weight_avg(加权平均成本)
- **tushare 端点**：cyq_perf
- **A股证据/陷阱**：华创证券双重筹码集中选股策略报告：筹码集中度+获利盘过滤组合有超额收益；A股散户占比高使获利盘效应更明显；T+1限制下高获利盘卖压在次日才能释放；注意cyq_perf数据从2018年起可用，限量6000条/次需循环拉取；行业中性化必要。
- **机构相关度**：中——散户持仓成本效应，机构持仓也受成本影响
- **出处**：华创证券《双重筹码集中的基本面选股策略》(hcquant.com), tushare cyq_perf文档(doc_id=293)

## 10. 筹码集中度因子 (Chip_Concentration)
**别名**：CYQ集中度 / 成本分布峰度  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：10-63TD中期建仓完成信号 · **方向**：低分散度(高集中)→看多；高分散度→中性或略看空

- **定义/公式**：方法1（基于cyq_perf分位数）：
  Conc_t = (cyq_perf.cost_95pct - cyq_perf.cost_5pct) / cyq_perf.cost_50pct
  值越小→筹码越集中（主力控盘），值越大→筹码越分散
方法2（基于cyq_chips价格-占比分布）：
  Peak_pct = max(cyq_chips.percent)  → 最大单峰占比
  活跃筹码集中度 = sum(percent for price in [0.95*close, 1.05*close])
行业截面rank后，低 Conc_t（高集中度）→看多
- **逻辑**：筹码集中于狭窄价区说明主力控盘程度高、散户筹码少，后续上涨阻力小；筹码分散时卖压来自多个价位，股价上行摩擦大。筹码集中+低位往往是主力建仓完成的形态信号。
- **数据输入**：cyq_perf.cost_5pct, cyq_perf.cost_95pct, cyq_perf.cost_50pct, cyq_chips.percent(分布)
- **tushare 端点**：cyq_perf, cyq_chips
- **A股证据/陷阱**：筹码集中度在A股量化中是成熟辅助指标，通达信/同花顺等平台均有标准化实现；独立IC约0.02-0.04；与获利盘配合使用时效果更稳定；A股散户主导市场特性使筹码信号在中小盘更有效，大盘股机构持仓主导、CYQ信号偏弱；数据从2018年起可用。
- **机构相关度**：中——筹码集中主要反映主力/游资控盘程度
- **出处**：华创证券《双重筹码集中的基本面选股策略》, BigQuant筹码集中度wiki, tushare cyq_chips文档(doc_id=294)

## 11. 股东人数变化率 (Shareholder_Count_Chg)
**别名**：户均持股变化因子 / 股东集中度变化  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：63-126TD（季报/半年报披露周期，数据频率低） · **方向**：股东人数减少(高户均持股增加)→看多

- **定义/公式**：HolderChg_t = (stk_holdernumber.holder_num_t - stk_holdernumber.holder_num_{t-N}) / stk_holdernumber.holder_num_{t-N}
N=1个报告期(约63TD)，取最新公告期 vs 上期
户均持股量变化：
  AvgHold_t = float_share / holder_num_t
  AvgHold_Chg = (AvgHold_t - AvgHold_{t-N}) / AvgHold_{t-N}
负向 HolderChg（股东人数减少/户均持股上升）→筹码集中→看多
- **逻辑**：股东人数减少意味着散户出逃/机构/主力增持（筹码集中），是机构建仓的间接证据；股东人数增加往往是主力出货/散户接盘（筹码分散），是减仓信号。兴业证券确认此指标能部分反映主力资金操作动向。
- **数据输入**：stk_holdernumber.holder_num(股东总数), stk_holdernumber.holder_num_ratio(环比变化率), stk_holdernumber.avg_hold_amount(户均持股量), daily_basic.float_share
- **tushare 端点**：stk_holdernumber, daily_basic
- **A股证据/陷阱**：兴业证券量化研究确认股东人数变化可反映主力资金动向；主要缺陷是数据频率低（季报/半年报，约每3个月更新一次），不适合2-4周频率；需注意送股/分红后股东人数会上升造成误判；PIT处理要求严格（防止使用披露日之前的数据）；小市值股效果更显著。
- **机构相关度**：中高——间接反映机构/主力的筹码集散程度
- **出处**：兴业证券量化研究《股东人数变化与股价关系》, 知乎2024《有效选股因子大解析》

## 12. 大股东增减持强度 (Insider_Trade_Signal)
**别名**：重要股东净增持因子 / 内部人交易信号  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：63-126TD；内部人增持效应持续时间较长 · **方向**：净增持高值→看多；大额减持→看空

- **定义/公式**：IT_Net_t = Σ_{t-63..t} (stk_holdertrade.change_vol[where change_type='增持'] × price) 
          - Σ_{t-63..t} (stk_holdertrade.change_vol[where change_type='减持'] × price)
IT_Strength_t = IT_Net_t / mktcap_t
注意：stk_holdertrade 包括大股东/高管/董监高的增减持公告，需按 holder_type 过滤控股股东/5%以上股东的战略性增持（信号最强）
- **逻辑**：大股东/高管了解公司内部情况，主动增持是强正向信号（知情者愿意加仓）；减持尤其是控股股东大额减持是负向信号。国际文献（Seyhun 1986）和A股实证均确认内部人增持后超额收益显著。
- **数据输入**：stk_holdertrade.change_vol(变动数量), stk_holdertrade.change_type(增持/减持), stk_holdertrade.holder_type(股东类型), stk_holdertrade.ann_date(公告日)
- **tushare 端点**：stk_holdertrade
- **A股证据/陷阱**：A股需严格PIT处理（以公告日ann_date为信号日，非报告期）；计划减持公告→实际减持期间需分两阶段处理；控股股东减持与财务造假相关性较高；减持窗口期限制（解禁后3个月内锁定期等）须纳入过滤；2024年翻倍股后普遍出现大股东减持（美之高、宗申动力等）验证了负向信号有效性。
- **机构相关度**：高——内部人是信息最丰富的市场参与者
- **出处**：Seyhun 'Insiders' Profits, Costs of Trading, and Market Efficiency' JFE 1986, 新浪财经2024翻倍股减持案例分析

## 13. 股权质押风险因子 (Pledge_Risk_Score)
**别名**：控股股东质押比例 / 强制平仓风险  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：长期风险信号（持续高质押→风险积累）；触发平仓线时短期负面冲击明显 · **方向**：高质押比例且接近平仓线→看空/风险折价

- **定义/公式**：Pledge_Ratio_t = pledge_stat.pledge_count / stk_holdernumber.total_share × 100%  (质押股数/总股本)
高风险区间判断：Pledge_Ratio > 50% AND stock_price 接近 pledge_detail.close_price（平仓线估算）
综合风险分：
  PR_Score = Pledge_Ratio × (close/pledge_price_est)^{-1}
  pledge_price_est ≈ pledge_detail.lclose × (1 - discount_ratio)，按市场通行80%质押率/130%维持担保估算
- **逻辑**：控股股东高比例质押时，股价下跌可能触发强制平仓，形成股价下跌→补充质押→再次下跌的负反馈循环。2024年A股质押比例16.38%，超过80%质押比例的公司中115家当年净利润亏损，是重大风险因子。
- **数据输入**：pledge_stat.pledge_count(质押股数), pledge_stat.unrest_pledge(无限售质押), pledge_detail.close_price(质押参考价), daily.close
- **tushare 端点**：pledge_stat, pledge_detail, daily
- **A股证据/陷阱**：证监会数据2024：A股整体质押比例16.38%；高质押公司与股价崩盘风险显著正相关（多篇学术文献证实）；2018年质押危机（大盘跌30%触发大量平仓）是典型历史事件；需定期更新（pledge_stat更新频率为季报/半年报）；ST股高质押更常见，需与ST标记联动。
- **机构相关度**：高——机构做投前尽调必查项；质押风险会引发机构回避
- **出处**：证监会2023年股权质押专题报告, 郑维伟等《控股股东股权质押与企业违规行为》现代金融研究2024, SAIF李峰教授高比例质押风险研究

## 14. 解禁压力因子 (Unlock_Overhang)
**别名**：股票解禁供给压力 / Float_Unlock  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：med · **周期**：前瞻21-63TD预警；解禁后30-60TD持续承压 · **方向**：高解禁压力→看空/负向

- **定义/公式**：Unlock_Overhang_t = share_float.float_share_t / daily_basic.circ_mv_t × price_ratio
其中：share_float.float_share 是未来 N 天内待解禁股数量
解禁压力比率：UP_t = share_float.float_ratio_sum_{t..t+21} / total_float_share
若 UP_t > 5% 则为高解禁压力事件；
注意：解禁日期为 share_float.float_date，需前瞻性使用（提前21TD建立压力信号）
- **逻辑**：大量股票解禁后增加流通股供给，市场需消化供给压力，股价往往承压。尤其是私募/PE的锁定期到期解禁，持有者急于变现，负向供给冲击明显。
- **数据输入**：share_float.float_date(解禁日期), share_float.float_share(解禁数量), share_float.float_ratio(占比), share_float.holder_name(解禁对象类型)
- **tushare 端点**：share_float, daily_basic
- **A股证据/陷阱**：A股解禁压力因子是成熟量化事件因子；实证研究（中证指数等）表明解禁前1-2周和解禁后2周是最大承压区间；小市值/高解禁比例冲击更大；IPO后6个月/1年/3年锁定期到期是最明确的解禁节点；需区分大股东战略性减持vs财务投资者减持（前者信号弱，后者信号强）。
- **机构相关度**：高——私募PE/VC解禁是机构投资退出的标准路径
- **出处**：中证指数《解禁效应研究》, 知乎因子研究系列《解禁压力与股价表现》

## 15. 行业资金流轮动因子 (Sector_Moneyflow_Rotation)
**别名**：申万行业主力资金净流入轮动  
**映射**：`capital_sentiment` · **可行性**：YELLOW · **把握**：med · **周期**：10-21TD行业资金动量有效；63TD以上存在均值回归 · **方向**：所在行业主力资金净流入强→个股看多

- **定义/公式**：步骤1：从 moneyflow_ind_ths 获取申万二级行业的主力净流入额
步骤2：行业动量：IND_MF_Mom_N = 行业近N日累计净流入/行业总成交额 排名
步骤3：个股映射：stock_IND_score_i = IND_MF_Mom_N[行业(i)]  × IND_weight
步骤4：行业前20%→个股加分；行业后20%→个股扣分
可以与 dc_daily(东财行业资金流) 交叉验证
- **逻辑**：机构资金的行业轮动是A股市场结构性行情的核心驱动力。资金大幅流入某行业时，该行业内个股获得估值扩张和流动性溢价；资金流出行业则相反。用行业维度的资金流叠加个股选择，可捕捉行业β中的主动配置信号。
- **数据输入**：moneyflow_ind_ths.industry(行业), moneyflow_ind_ths.net_amount(净流入额), index_member_all(申万行业成分)
- **tushare 端点**：moneyflow_ind_ths, index_member_all, dc_daily
- **A股证据/陷阱**：行业资金流轮动在A股政策驱动行情（如2024年9月科技牛）中效果显著；中性化问题：个股因子应在行业内做相对排名，不能直接叠加行业β；行业资金流数据平台间差异较大（同花顺 vs 东财定义不同）；需与行业相对强弱指标联合使用提高稳定性。
- **机构相关度**：高——主动型机构配置行为的行业维度直接体现
- **出处**：新浪财经证券研究2024行业轮动策略, tushare moneyflow_ind_ths文档, 东方证券ETF资金流轮动研究2024

## 16. AH溢价套利压力 (AH_Premium_Arbitrage)
**别名**：A/H股溢价因子 / 跨市场估值差  
**映射**：`valuation_rerating` · **可行性**：GREEN · **把握**：med · **周期**：63-126TD均值回归信号 · **方向**：AH溢价极高→A股看空；AH折价→A股看多（稀少）

- **定义/公式**：AH_Premium_t = stk_ah_comparison.premium_latest (已有标准字段)
  = (A股价格 / H股价格) × 汇率 - 1
选股信号：对于双重上市公司，AH_Premium 超过行业均值2个标准差→A股相对高估→看空信号（估值回归压力）；低于均值1个标准差→A股相对低估→看多
可构建 Z-score: AH_Z = (AH_Premium_t - MA(AH_Premium, N)) / std(AH_Premium, N), N=63
- **逻辑**：A股与H股理论上代表同一公司，长期应趋于均衡。A股溢价过高时，机构投资者（尤其是可跨市场的QFII/跨境基金）会通过卖A买H套利，对A股形成下行压力。2023-2025年沪深港通打通后此通道更顺畅。
- **数据输入**：stk_ah_comparison.premium_latest(最新溢价率), stk_ah_comparison.ts_code_hk(港股代码)
- **tushare 端点**：stk_ah_comparison
- **A股证据/陷阱**：AH溢价因子在A股量化中有较长研究历史；主要局限是样本量小（A+H双重上市约120家公司，以金融/大盘为主）；跨境套利存在资本管制摩擦，使均值回归时间更长；节假日差异（春节港股交易/A股停市）需处理；可与moneyflow_hsgt南向资金流联动判断套利窗口。
- **机构相关度**：极高——跨境机构套利的核心工具
- **出处**：恒生指数公司《沪深港通AH股溢价研究》, tushare stk_ah_comparison文档, 智通财经港股多因子研究2025

## 17. 北向资金流速动量 (HSGT_Flow_Momentum)
**别名**：沪深港通净流入动量 / 北向资金趋势因子  
**映射**：`capital_sentiment` · **可行性**：GREEN · **把握**：med · **周期**：10-21TD市场择时信号；个股层面(hk_hold季频)63-126TD · **方向**：北向净流入加速→整体看多；流出加速→防御

- **定义/公式**：注：2024年8月后北向不再日度披露个股，此因子改用大盘聚合层面构建市场择时信号，不做个股因子。
大盘层面：HSGT_Mom_t = Σ_{t-N..t} moneyflow_hsgt.north_money / MA(north_money, 63)
作为regime开关：HSGT_Mom > 1.2 → 北向加速流入 → 整体加强capital_sentiment权重
N=10TD短期动量；N=21TD中期动量
替代个股因子：用 hk_hold 季度数据做cross-sectional rank，仅在季报披露后更新
- **逻辑**：沪深港通净流入速度加快表明外资对A股风险偏好上升，通常伴随估值扩张和市场上涨。作为宏观情绪regime指标，可调整individual因子权重（北向大幅流入期间fundamental因子权重上升，capital_sentiment权重亦上升）。
- **数据输入**：moneyflow_hsgt.north_money(北向净流入), moneyflow_hsgt.trade_date
- **tushare 端点**：moneyflow_hsgt
- **A股证据/陷阱**：光大证券替代指标体系(2024)：北向大幅流入时基本满足PMI>49.8%、全A PE<16、月换手率<18%等条件，多因素模型历史回溯准确率较高；2024年8月后日度数据停播影响个股应用，但大盘层面moneyflow_hsgt仍可用；外资持仓占A股流通市值3.48%，体量有限但引领性强。
- **机构相关度**：极高——外资机构资金流入是A股机构化进程的核心驱动
- **出处**：光大证券《北向资金看不到了？还有这些指标可以判断》2024, 东北证券《北向资金分析方法论》2025, tushare moneyflow_hsgt文档(doc_id=47)