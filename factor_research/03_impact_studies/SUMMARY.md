# Phase 3a 裁决汇总（27 单元）

裁决分布：{'CONDITIONAL': 23, 'NEGATIVE': 3, 'POSITIVE': 1}　把握：{'med': 13, 'high': 14}　优先级：{'low': 10, 'med': 8, 'high': 8, 'low — 满足条件下可接入，但当前 capital_sentiment 死轴更高优先级的修复是北向（hk_hold/moneyflow_hsgt）+ 游资（hm_detail）因子（见系统缺口 e.1），这些因子 2-4 周 ic 更高且与系统 horizon 匹配。dy 的 regime-gating 工程复杂度额外提高实施成本，建议在北向/游资因子接入后再评估 dy 是否仍有边际价值。': 1}

| 单元 | 因子 | 目标轴 | 裁决 | 把握 | 优先级 |
|---|---|---|---|---|---|
| T1-1 | 北向持股变化率 / HSGT 流速动量（HK_Hold_Chg +  | capital_sentiment | **CONDITIONAL** | med | low |
| T1-2 | 融资买入动量 / 融资余额变化率 (Margin_Buy_Momen | capital_sentiment / fu | **CONDITIONAL** | med | low |
| T1-3 | 主力净流入率 CNIR（大单+超大单净流入 / 当日成交额，N日累积 | capital_sentiment | **CONDITIONAL** | med | med |
| T1-4 | 游资净买入强度 (HM_Net_Buy) — 龙虎榜/游资明细净买入 | capital_sentiment（游资净买 | **CONDITIONAL** | med | low |
| T1-5 | 大宗交易折溢价 / 成交额占比（Block_Trade_Discou | capital_sentiment | **CONDITIONAL** | med | med |
| T1-6 | 筹码获利盘比例 + 集中度 (CYQ Winner_Rate + C | capital_sentiment（主）;  | **CONDITIONAL** | med | med |
| T1-7 | 股东人数变化率（Shareholder_Count_Chg / 筹码 | capital_sentiment | **CONDITIONAL** | med | low |
| T2-1 | Piotroski F-Score（皮尔托斯基9分） | fundamental_score | **CONDITIONAL** | high | low |
| T2-2 | Sloan 应计比率 / 盈利质量（BS-Accruals） | fundamental_score | **CONDITIONAL** | high | high |
| T2-3 | Novy-Marx 毛利率 GP/Assets (GPOA) | fundamental_score | **NEGATIVE** | high | low |
| T2-4 | Asset Growth (AG负向) + NOA净营运资产水平 | fundamental_score | **CONDITIONAL** | med | med |
| T2-5 | SUE 标准化盈余惊喜 + PEAD（Standardized Un | expectation_gap | **POSITIVE** | high | high |
| T2-6 | 盈利预测修正动量 (Analyst Revision Momentu | expectation_gap | **CONDITIONAL** | high | high |
| T2-7 | 业绩快报/预告超预期（EXPRESS_SURPRISE #57 主力 | expectation_gap | **CONDITIONAL** | high | high |
| T3-1 | 短期1月反转 STREV（换手调整版） | capital_sentiment（正向加分 | **CONDITIONAL** | high | high |
| T3-2 | 残差/特异动量 (Residual/Idiosyncratic Mo | capital_sentiment | **CONDITIONAL** | high | high |
| T3-3 | 行业动量 Industry Momentum (IND_MOM_2_ | capital_sentiment | **CONDITIONAL** | med | med |
| T3-4 | 特异波动率 IVOL（低波异象） | risk_discount（子目标：vola | **CONDITIONAL** | high | high |
| T3-5 | MAX effect 极端日收益均值（MAX5） | risk_discount | **CONDITIONAL** | med | med |
| T3-6 | Amihud ILLIQ 月均非流动性（价格冲击比率） | risk_discount | **CONDITIONAL** | high | med |
| T4-1 | 行业内横截面 EP（盈利收益率·行业中性化 / EP_Industr | valuation_rerating | **NEGATIVE** | high | low |
| T4-2 | AH 股折价因子（stk_ah_comparison.premium | valuation_rerating | **CONDITIONAL** | med | low |
| T4-3 | 股息率 / 高股息因子（Dividend Yield / DY） | valuation_rerating（建议， | **CONDITIONAL** | high | low  |
| T4-4 | ICIR 最优因子合成权重（聚合层） | aggregation（建议）；实际映射路径 | **NEGATIVE** | high | low |
| T4-5 | 行业+市值二阶中性化 (#133 Barra CNE6) + 对称正 | aggregation（预处理层，非新 sc | **CONDITIONAL** | med | low |
| T4-6 | 股权质押 + 解禁压力（机构风险） | risk_discount | **CONDITIONAL** | med | med |
| T4-7 | 货币-信用四象限 + 融资余额变化率温度计 + 全市场换手率百分位温 | 三轴分拆：#150→market_regim | **CONDITIONAL** | high | high |