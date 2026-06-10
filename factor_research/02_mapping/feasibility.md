# Phase 2 — 可行性映射 / 去重 / 优先级（代入系统）

> 把 166 条因子比对 `00_system_inventory.md` 的【可用数据】+【现有 dp_id 路由】，判定：已在系统/新增、可行性、与现有轴的去重，并选出 Phase 3 影响研究的优先清单。

## 1. 总览

- 166 条全部 ≥ YELLOW（数据可得）：**144 GREEN / 22 YELLOW / 0 RED**（agents 被要求只收 tushare 可算的，故无 RED）。
- 映射分布：**capital_sentiment 58**（死轴！）· risk_discount 37 · fundamental_score 26 · valuation_rerating 17 · expectation_gap 17 · priced_in_discount 7 · funding_score 3 · NEW 1。
- 把握度：high 58 / med 107 / low 1。

**一句话**：与"机构为主市场"最相关的两个轴（capital_sentiment / funding_score）现在系统里几乎是空的（仅 active_inflow），而候选因子里 **61 条**（58+3）正好喂这两轴 —— 这是把系统从"机械"变"机构适配"的最大杠杆。

## 2. 去重：哪些因子【已在系统】vs【新增】

| 因子族 | 与现有系统的关系 | 结论 |
|---|---|---|
| **价值/估值** | 多数与现有 valuation 节点重叠：EV/EBITDA=`L6.mult.ev_ebitda`(已激活,全局ref)、PS=`L6.mult.ps`(已)、forward_pe=`L6.mult.forward_pe`(已)、行业内EP/PB≈`L6.state.peer_compare`(已横截面锚)、历史分位=`L6.state.historical_percentile`(已,时序,被压制)；**BP=`L6.mult.pb`(mapped=0 死)**、**FCF/P=`L6.mult.mcap_fcf`(data-only 死)** —— 数据在但没接进分。 | 大多"改进现有"，非新增。**真新增=股息率、AH折价、FCF/EV**。 |
| **质量** | 系统仅 6 个孤立比率(roe/roa/debt/ocf/net_profit_yoy/asset_turnover)+gross_margin/margins。Piotroski/Sloan/Novy-Marx/asset growth/Altman/Ohlson/RONOA 全无。 | **几乎全新**。fundamental_score(Merit)的最大富矿。 |
| **动量/反转** | 系统无任何动量因子；`L6.priced.run_up` 只作 priced_in 罚分。 | **全新**。注意 12-1 动量在 A 股弱/负，1M 反转强——须实测方向。 |
| **盈利预期** | 有 analyst_revision/analyst_rating/guidance_change。SUE/PEAD/express超预期/分歧度/覆盖变化 全无。 | expectation_gap 的**深化**（多为新）。 |
| **机构资金流** | **全新**。系统仅 `L7.flow.active_inflow`。北向/融资融券/游资/大宗/筹码/股东人数 全未成因子。 | **全新 + 最高价值（thesis 核心）**。 |
| **流动性/微观** | 全新。Amihud/turnover/Corwin-Schultz/Roll/Lesmond/零收益天数 无。 | 全新（部分喂 risk_discount，与波动率族重叠）。 |
| **波动率/风险** | 全新。IVOL/MAX/BAB/skew/downside-beta 无。 | 全新。低波动异象在 A 股方向需实测。 |
| **情绪/关注** | 全新。涨停/连板/dc_hot/kpl题材/irm互动/隔夜反转 无。 | 全新（多为反向→priced_in_discount/capital_sentiment）。 |
| **多因子模型** | 是**组合方法**非单因子：ICIR加权/Barra中性化/对称正交/ML合成。系统现用"覆盖率加权均值"做 Merit 聚合。 | 影响【聚合层】，决定新因子如何并入 Merit/Timing。 |
| **宏观regime** | R-7 已诊断但休眠(market_regime beta≈1.0)。货币-信用四象限/信用脉冲/ERP/PMI/M1-M2/换手温度计/融资温度计 无。 | 喂【全局 regime/beta】（市场级，非个股），即 R-7。 |

## 3. 确认的系统缺口（= 机会，与 inventory §E 互证）

1. **资金/机构轴空**（capital_sentiment/funding 仅 active_inflow）← 61 条候选可填。**最高 ROI**。
2. **无 quality 因子族** ← Piotroski/Sloan/Novy-Marx/asset growth 等可填 Merit。
3. **无 momentum/reversal** ← 1M 反转、残差动量、行业动量。
4. **无 low-vol/特异波动** ← IVOL/MAX/BAB。
5. **expectation_gap 浅** ← SUE/PEAD/express 超预期/分歧度。
6. **估值仍有时序/绝对残留** ← 行业内 EP、AH 折价、股息率（横截面/新口径）。
7. **regime 休眠（R-7）** ← 货币-信用四象限、融资/换手温度计 → 动态 beta。
8. **聚合层是简单加权均值** ← ICIR 加权 / 行业+市值中性化 / 对称正交可升级。

## 4. Phase 3 影响研究【优先清单】（24 条，分层）

选择标准：① 贴合"机构为主"thesis ② 填真缺口（非已在系统）③ 周期落在系统 2-4 周甜区 ④ GREEN + 把握高 ⑤ 跨轴覆盖。每条 Phase 3 逐个研究"接进系统是正面/负面"。

### Tier 1 — 机构/资金轴复活（capital_sentiment / funding，thesis 核心）
| ID | 因子 | 目标轴 | 数据 |
|---|---|---|---|
| T1-1 | 北向持股变化率 / HSGT 流速动量 (#66/#82/#97/#128) | capital_sentiment | hk_hold, moneyflow_hsgt |
| T1-2 | 融资买入动量 / 融资余额变化率 (#67/#95/#140) | capital_sentiment/funding | margin, margin_detail |
| T1-3 | 主力净流入率 CNIR（大单/超大单占比）(#69/#70) | capital_sentiment | moneyflow, moneyflow_dc/ths |
| T1-4 | 游资净买入强度 (#71/#123) | capital_sentiment | hm_detail, hm_list |
| T1-5 | 大宗交易折溢价/占比 (#72/#73/#94) | capital_sentiment | block_trade |
| T1-6 | 筹码获利盘比例 + 集中度 (#74/#75/#90/#91) | capital_sentiment | cyq_perf |
| T1-7 | 股东人数变化率（筹码集中）(#76/#92/#48) | capital_sentiment | stk_holdernumber |

### Tier 2 — 填补缺失因子族（Merit / risk / expectation）
| ID | 因子 | 目标轴 | 数据 |
|---|---|---|---|
| T2-1 | Piotroski F-Score (#17/#136) | fundamental_score | income/balancesheet/cashflow/fina_indicator |
| T2-2 | Sloan 应计 / 盈利质量 (#18/#19/#149) | fundamental_score | balancesheet/cashflow |
| T2-3 | Novy-Marx GP/Assets (#20) | fundamental_score | income/balancesheet |
| T2-4 | 资产增长 Asset Growth (#23) | fundamental_score(负向) | balancesheet |
| T2-5 | SUE 标准化盈余惊喜 + PEAD (#29/#51/#45) | expectation_gap | income/express/forecast |
| T2-6 | 盈利预测修正动量 ARM (#30/#52/#142) | expectation_gap | report_rc |
| T2-7 | 业绩快报/预告超预期 (#57/#56/#63) | expectation_gap | express, forecast |

### Tier 3 — 价量/风险异象（risk_discount / timing）
| ID | 因子 | 目标轴 | 数据 |
|---|---|---|---|
| T3-1 | 短期 1 个月反转 STREV（换手调整）(#34/#96/#102) | capital_sentiment(反向) | daily, daily_basic |
| T3-2 | 残差/特异动量 (#35) | capital_sentiment | daily + 因子回归 |
| T3-3 | 行业动量 Industry Momentum (#37) | capital_sentiment | ci_daily/dc_daily/index |
| T3-4 | 特异波动率 IVOL (#99/#111/#138) | risk_discount | daily + FF3 残差 |
| T3-5 | MAX effect 极端日收益 (#100) | risk_discount | daily |
| T3-6 | Amihud 非流动性 (#83) | risk_discount | daily |

### Tier 4 — 价值新增 + 聚合/regime（架构层）
| ID | 因子 | 目标轴 | 数据 |
|---|---|---|---|
| T4-1 | 行业内横截面 EP（替时序/全局残留）(#1/#11) | valuation_rerating | daily_basic + 申万 |
| T4-2 | AH 股折价因子（现完全未用）(#9/#81) | valuation_rerating | stk_ah_comparison |
| T4-3 | 股息率高股息因子 (#6) | valuation_rerating | dividend, daily_basic |
| T4-4 | ICIR 最优因子合成权重 (#132) | 聚合层 | 因子 IC 历史 |
| T4-5 | 行业+市值中性化 / 对称正交 (#133/#148) | 聚合层 | 因子矩阵 |
| T4-6 | 股权质押 + 解禁压力（机构风险）(#78/#79/#110/#130) | risk_discount | pledge, share_float |
| T4-7 | 货币-信用四象限 / 融资+换手温度计（R-7 动态 regime）(#150/#159/#160) | 全局 regime/beta | cn_m, sf_month, margin, 全市场换手 |

> Tier 4 共 7 条（含 regime/聚合）。合计 Phase 3 = 7+7+6+7 = **27 条研究单元**（部分已合并相似因子）。

## 5. Phase 3 方法

- **3a（先做）— 逐因子影响研究（多 agent）**：每条研究单元一个 agent，读 `00_system_inventory.md` + 该因子 catalog 条目 + 可读源码核对现有节点，输出：与现有轴的**正交性/冗余/双计风险**、**方向在系统框架内是否正确**、A股有效性证据、**接入设计**（score_target/中性化/权重/horizon 契合）、**正面/负面/有条件 裁决** + 把握度。
- **3b（后做，需较重数据，建议先给用户看 3a）— 实证验证**：对 3a 选出的赢家，在隔离目录复刻 `pit_backtest/metrics.py` 方法（rank IC + 分档 + 与现有 base 成分相关性），用 DockCase 缓存的历史数据算单因子 IC。**只读数据、不碰原 pit_backtest/**。
- 3a 完成后，我综合出**"更优模型"提案**（双轴下新因子如何编排：Merit 加质量族、Timing 复活机构资金轴、risk 加波动/质押、全局加 regime/beta），交用户。
