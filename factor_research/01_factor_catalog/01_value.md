# 因子族：价值/估值（Value）

> 价值/估值族是本系统 valuation_rerating 轴的核心原料，也是 A 股机构化后争议最大的因子族。当前系统最大短板是：valuation_rerating 轴的 7 个有效节点中仅 1 个（peer_compare）做到行业级横截面，其余 3 个是自身时序、3 个是全局绝对参照，严重污染信号。最值得优先接入的三条：① 行业内 EP（反转收益率 EP_Industry_Neutral）——直接替换现有全局 forward_pe/ps，横截面对行业估值排名，IC 最高；② FCF/EV（企业价值口径自由现金流收益率）——北向机构偏好用 EV 口径，tushare cashflow + daily_basic 可直接算，映射 valuation_rerating 又与 fundamental_score 质量轴协同；③ AH 折价因子——完全独占 stk_ah_comparison 且系统内无任何 AH 比价信号，对 AH 两地同时上市股可作为估值参照基准，机构套利逻辑清晰。

共 16 条。


## 1. 行业内横截面 EP（盈利收益率·行业中性化）
**别名**：EP_IndustryNeutral / 行业内 E/P 排名  
**映射**：`valuation_rerating` · **可行性**：GREEN · **把握**：high · **周期**：1-3 个月；对本系统 2-4 周短中窗口仍适用（IC 随 horizon 先升后降，2-4 周 IC 正但略低于月度） · **方向**：高 EP_IND（同业中最便宜）→ 看多

- **定义/公式**：EP_raw = TTM_净利润 / 总市值（= 1/PE_TTM）；对盈利为负的股票置 0 或用行业中位数替代（避免负 PE 陷阱）；在申万二级行业截面内做 z-score 标准化：EP_IND = (EP_raw − μ_ind) / σ_ind；全市场再做二次 z-score 截尾（±3σ winsorize）。高值看多。
- **逻辑**：Fama-French HML 的 A 股版本。A 股机构化后，纯绝对 PE 对行业轮动极其敏感（周期股 PE 经常最低但不是最好买点），行业内横截面排名剥离行业间估值差异，让因子捕捉的是'同业中谁更便宜'，与机构行业配置视角一致。标准化后 IC 比原始 EP 稳定，国泰君安、中信金工研报（2022-2024）均记录行业中性 EP 月度 IC 均值 4-5%，ICIR ~1.5-2.0。
- **数据输入**：daily_basic.pe_ttm（或 pb，total_mv）, income.net_income TTM（季报累加）, index_member_all / index_classify（申万行业分类）, st / namechange（剔除 ST、退市预警）
- **tushare 端点**：daily_basic, income, index_member_all, index_classify, st
- **A股证据/陷阱**：行业中性化后 EP Rank IC 月均 ~4-5%，ICIR ~1.6-2.0（源达研究 2025、bigquant.com 2024 实证）。陷阱：①负净利润股须做 0-替换或排除，否则极端负值破坏单调性；②涨跌停日股价截断导致当日 PE 失真，可用前一日收盘；③T+1 规则不影响月度再平衡。机构化后 EP 相对 BP 更稳定，但 2022-2024 成长风格期间短暂失效（价值-成长轮动）。
- **机构相关度**：高。机构选股 roadshow 惯用同业 PE 对比，行业内 EP 排名直接对应机构相对配置逻辑。
- **出处**：Fama & French (1993) JFE, 国泰君安金工多因子系列 2022, 源达证券：自由现金流因子研究 2025（新浪财经）, bigquant.com 2024年有效选股因子大解析

## 2. 账面市值比 BP（Book-to-Price）
**别名**：BM / 账面市值比 / 账市比  
**映射**：`valuation_rerating` · **可行性**：GREEN · **把握**：high · **周期**：1-3 个月（月均再平衡） · **方向**：高 BP（便宜）→ 看多

- **定义/公式**：BP = 最新季报归母净资产（book equity）/ 当日总市值。使用 PIT 口径：确认财报披露日后再引入（中国财报披露：年报 4 月底、半年报 8 月底、Q1 4 月底、Q3 10 月底）。剔除破净壳公司（BP > 1 但实为亏损壳），过滤：排除 ST、上市不足 12 个月、BP < 0（负净资产）。行业内标准化同 EP_IND。
- **逻辑**：Fama-French HML 核心。BP 代理未来盈利能力的市场折价（低 BP = 市场给高溢价预期，高 BP = 被低估或困境）。A 股 BP 因子月度 IC ~4.7%，ICIR ~1.66（2010 年以来，2024 bigquant 实证）。机构化后 BP 比散户市场时代更依赖基本面质量，避免陷入壳价值陷阱（shell value BP），需配合盈利质量过滤。
- **数据输入**：daily_basic.pb（PB = 1/BP 的倒数）或 daily_basic.total_mv + balancesheet.total_hldr_eqy_exc_min_int, balancesheet（PIT）, disclosure_date（PIT）, st、namechange
- **tushare 端点**：daily_basic, balancesheet, disclosure_date, st
- **A股证据/陷阱**：BP 月度 IC 均值 4.73%，ICIR 1.66（2010 以来，bigquant 2024）。陷阱：①小市值带壳股 BP 极高但并非 value premium，需剔除市值低于 8 亿或破净股；②行业中性化关键：金融板块 BP 系统高于非金融，不中性化则因子受行业结构污染；③财报延迟 PIT 必须严格（避免使用还未公告的最新季报）。
- **机构相关度**：高。公募基金价值评分必含 PB，北向外资惯用 P/BV。
- **出处**：Fama & French (1992) JF, 华泰证券：低市净率 FF-Score 选股模型（studocu）, bigquant：SDICPB-ROE 策略框架 2024-09, 华证指数：从资产结构角度解构市净率 2024-11

## 3. 自由现金流收益率 FCF/P（市值口径）
**别名**：FCF_Yield_Mcap / 现金盈余率  
**映射**：`valuation_rerating` · **可行性**：GREEN · **把握**：high · **周期**：1-3 个月（适合本系统 2-4 周窗口） · **方向**：高 FCF/P → 看多

- **定义/公式**：FCF_TTM = 经营性净现金流 TTM − 购建固定资产/无形资产/其他长期资产支付现金 TTM（= capex TTM）；FCF_Yield = FCF_TTM / total_mv。TTM 拼接：当季 YTD + 上年全年 − 上年同期 YTD（A 股会计准则季报为 YTD 累计值，需季间差分再加总）。剔除 FCF < 0 的亏现金流股或保留用于排名但设 0 地板。行业内 z-score 标准化。
- **逻辑**：FCF yield 剔除了应计（accrual）会计的扭曲，捕捉公司实际产生可分配现金的能力。Sloan (1996) 应计异象：高应计→低未来收益；FCF yield 天然是低应计信号。A 股 2025 富时罗素推出中国 A 股自由现金流聚焦指数、中证也于 2024 年推出 FCF 系列指数，机构认可度正在提升。源达研究（2025）实证：FCF_TTM 因子 Rank IC 均值 1.18%，ICIR 0.19；比经营净现金流因子（IC 0.85%，ICIR 0.06）更稳定。
- **数据输入**：cashflow.c_fr_operate_a（经营净现金流，YTD）, cashflow.c_pay_acq_const_fiolta（资本开支，YTD）, daily_basic.total_mv, disclosure_date（PIT）
- **tushare 端点**：cashflow, daily_basic, disclosure_date
- **A股证据/陷阱**：FCF_TTM 因子 Rank IC 均值 1.18%，ICIR 0.19（源达证券 2025 实证，2014/1-2025/8 月度回测）。FCF yield 多空年化收益率 1.13%，最大回撤 15.98%。陷阱：①A 股 YTD 季报须做差分才能得单季，易引入财报披露时点噪音；②重资产行业（钢铁/电力）capex 大导致 FCF 系统性低，行业中性化后才可比；③成长科技公司 FCF 为负是正常（扩张期），应与行业中位对比而非绝对 0 截断。
- **机构相关度**：高。机构（主动管理/量化）正在加大 FCF yield 权重，2024 FCF 指数基金发行量提升佐证。
- **出处**：Sloan (1996) TAR：应计异象, 源达证券：自由现金流因子研究与策略构建 2025, 富时罗素：中国 A 股自由现金流聚焦指数 2024, 中证指数：沪深 300 FCF 指数系列 2024

## 4. EV/EBITDA 倒数（企业倍数因子）
**别名**：EBITDA_Yield / Enterprise Multiple 低值 / Loughran-Wellman EM  
**映射**：`valuation_rerating` · **可行性**：GREEN · **把握**：high · **周期**：1-3 个月 · **方向**：高 EBITDA_Yield（= 低 EV/EBITDA）→ 看多

- **定义/公式**：EM = EV / EBITDA，其中 EV = total_mv + 有息债务（short_loan + long_loan + bonds_payable）− 现金及等价物（money_cap）；EBITDA = EBIT + 折旧摊销 = 营业利润 + 财务费用 + 折旧摊销（取 fina_indicator 或 income/cashflow 推算）。因子值用 1/EM（EBITDA_Yield）使方向一致（高值→便宜→看多）。行业内百分位排名标准化；EBITDA ≤ 0 时置 NaN 排除。
- **逻辑**：Loughran & Wellman (2011, JFQA) 记录：EM 低值组合年超额收益 5.28%（美国）；国际证据（英法德日澳等）支持 EM 每月超额 ~1%。EM 比 PE 更好：① 资本结构中性（EV 消除了债务杠杆对 PE 的扭曲）；② EBITDA 剔除折旧政策差异和利息税差；③ 在高杠杆行业（房地产/基建）和重资产行业应用优于 PE。本系统已有 L6.mult.ev_ebitda 节点但以全局绝对参照（_EVEBITDA_REF=13），缺横截面化。
- **数据输入**：daily_basic.total_mv, balancesheet.short_loan + long_loan + bonds_payable（有息负债）, balancesheet.money_cap（货币资金）, income.ebit 或 cashflow.depr_fa_coga_dpba（折旧摊销）+ income.operate_profit
- **tushare 端点**：daily_basic, balancesheet, income, cashflow
- **A股证据/陷阱**：现有系统 L6.mult.ev_ebitda 已有节点但以全局参照（_EVEBITDA_REF=13）导致绝对值污染。横截面 EM 在 A 股实证：中信金工多因子报告显示 EV 系估值因子在行业内横截面 IC ~2-3%；但对金融股（银行/保险）EBITDA 概念不适用，需剔除或改用 P/B。陷阱：①重组/并购后 EV 突变（标购溢价进商誉，扭曲 EBITDA Yield）；②房地产/建筑行业有息债规模大，EM 天然高，行业中性化关键。
- **机构相关度**：高。机构 DCF 分析师惯用 EV/EBITDA 跨国、跨资本结构比较，是并购定价基准。
- **出处**：Loughran & Wellman (2011) JFQA：'New Evidence on the Relation Between the Enterprise Multiple and Average Stock Returns', Alpha Architect (2014): 'Digging into the Enterprise Multiple Value Factor', ValueWalk: International Evidence For The Acquirer's Multiple (2015), 中信证券金工多因子框架（fxbaogao.com）

## 5. FCF/EV（企业价值口径 FCF 收益率）
**别名**：FCF_EV_Yield / 企业自由现金流倍数  
**映射**：`valuation_rerating` · **可行性**：GREEN · **把握**：med · **周期**：1-3 个月 · **方向**：高 FCF/EV → 看多

- **定义/公式**：FCF_EV_Yield = FCF_TTM / EV，其中 EV = total_mv + 净有息债务（= 有息债务 − 货币资金）；FCF_TTM 同 FCF/P 定义（经营净现金流 − capex，TTM 口径）。行业内 z-score 标准化，EBITDA/EV 可作为 FCF/EV 的稳定版替代（在无 capex 数据精度时）。
- **逻辑**：FCF/EV 是 FCF/P 的企业价值改进版：消除资本结构差异（高杠杆公司 P 低但 EV 高，FCF/P 过高而 FCF/EV 合理）。在机构主导市场下，PE 收购者视角评估的正是 FCF/EV。Greenblatt 的 magic formula 本质是 EBIT/EV + ROIC 组合。FCF/EV 比 FCF/P 在债务密集型行业（地产/电力/基建）更能横向比较。
- **数据输入**：cashflow.c_fr_operate_a（TTM）, cashflow.c_pay_acq_const_fiolta（TTM）, daily_basic.total_mv, balancesheet.short_loan + long_loan + bonds_payable − money_cap
- **tushare 端点**：cashflow, daily_basic, balancesheet
- **A股证据/陷阱**：A 股 FCF/EV 专项实证少于 FCF/P，但机构实践中常用。陷阱与 FCF/P 类似，叠加有息债务数据质量问题（部分公司借款在关联方不入表，导致 EV 低估）。金融行业不适用（银行 EV 定义不同）。
- **机构相关度**：高。PE/VC 机构估值标准指标，北向外资也用 EV 口径做跨市场比较。
- **出处**：Greenblatt (2005) 'The Little Book That Beats the Market'（magic formula 原始出处）, 源达证券 FCF 因子研究 2025, SSRN Loughran & Wellman 2011 EM 因子

## 6. 股息率（Dividend Yield）
**别名**：DY / 分红收益率 / 高股息因子  
**映射**：`valuation_rerating` · **可行性**：GREEN · **把握**：high · **周期**：中长期（1-6 个月），在利率下行 / 风险规避市场中短期也有效 · **方向**：高 DY → 看多

- **定义/公式**：DY = 最近 12 个月已实施现金分红总额 / 当日总市值 = 实际派息（ex-dividend 口径，非预告）。使用 PIT：仅累计已有除权除息记录。计算：从 dividend 表取 ex_date ≤ 当日、cash_div_tax（税后每股现金股息）× 总股本 / total_mv。行业内百分位标准化；剔除 DY = 0 样本单独分析或保留赋 0（决定于是否做多/空分档）。
- **逻辑**：高股息 = 现金流回报率高 + 管理层股东导向；同时是机构（保险/社保/红利 ETF）的强制配置信号。2024-2025 实证：银行指数两年涨幅 52.2%，银行、煤炭、电力等高股息板块在利率下行周期显著跑赢（来源：界面新闻 2025 高股息策略）。国金证券量化 2025 指出高波动环境下高股息表现稳健。月度 Rank IC 均值约 2-3%（因行业集中需中性化）。
- **数据输入**：dividend.cash_div_tax（每股税后现金股息）, dividend.ex_date（除权除息日）, daily_basic.total_mv（或 stock_basic.总股本）
- **tushare 端点**：dividend, daily_basic
- **A股证据/陷阱**：2024-2025 高股息 alpha 最强时段，银行/煤炭/电力 DY 5-8% 股票显著跑赢；国金证券量化系列 33（高波动市场环境下红利资产表现稳健，2025-04）记录 DY 因子在风险规避期 IC 提升。陷阱：①周期行业（煤炭/钢铁）DY 高但分红可持续性差，需配合盈利质量过滤；②ST 股偶发高分红（补偿性）需剔除；③前复权股价分红会降低 DY 幻觉。
- **机构相关度**：极高。保险/社保/年金强制配置高股息资产；红利 ETF 规模持续扩大，机构流量明确。
- **出处**：界面新闻：高股息个股迎来黄金机遇 2025, 国金证券：高波动市场环境下红利资产表现稳健 2025-04, 中证指数：华证龙头红利 50 分析 2024-05

## 7. PEG 因子（PE 对增长率比值）
**别名**：PEG / GARP 估值 / 成长调整 PE  
**映射**：`valuation_rerating` · **可行性**：GREEN · **把握**：med · **周期**：1-6 个月（中长期更有效） · **方向**：低 PEG（=高−PEG）→ 看多

- **定义/公式**：PEG = PE_TTM / EPS_growth_fwd_3y × 100（Peter Lynch 定义）。实操改进：① 用分析师一致预期 EPS 增速（report_rc 字段 eps_avg / net_profit_avg 近 3 年 CAGR）替代历史增速；② 增速取正值才计算（负增速 PEG 无意义）；③ PEG ≤ 1 视为合理，>2 视为偏贵；因子化：以 −PEG 排名（低 PEG → 看多）；剔除增速 < 5% 和 > 100% 的极端股。行业内百分位标准化（成长型行业 PE 系统性高）。
- **逻辑**：纯 PE 忽略成长性，PEG 把成长预期纳入估值分母，是 GARP（Growth at Reasonable Price）策略核心。Lynch（1989）提出；北向外资和外资机构普遍用 PEG 对比中美同行。机构用 PEG 甄别'价值陷阱'（高增长但 PE 合理）vs.'估值陷阱'（低增长低 PE 但无成长）。2024 年 A 股科技股 AI 行情中，PEG<1 成长科技股显著跑赢（21 经济网 2026-04 报道）。
- **数据输入**：daily_basic.pe_ttm, report_rc.eps_avg 或 net_profit_avg（分析师预测，近 1-3 年 CAGR）
- **tushare 端点**：daily_basic, report_rc
- **A股证据/陷阱**：A 股 PEG 因子单独 IC 约 2-3%（弱于纯 EP，但 GARP 组合效果好）。陷阱：①report_rc 覆盖率不足（中小盘股分析师覆盖少）；②增速预测错误导致 PEG 失真（尤其周期性行业峰值盈利时 PEG 陷阱）；③分析师覆盖稀少的北交所/小市值股几乎无法计算；④ A 股 2022-2023 分析师系统性高估增速，导致 forward PEG 比历史 PEG 噪声大。
- **机构相关度**：高。主动基金经理和外资研报均标配 PEG，尤其科技/消费成长赛道。
- **出处**：Lynch (1989) 'One Up on Wall Street'（PEG 原始定义）, 21 经济网：高 ROE + 低 PEG 优质科技股 2026-04, 华泰金工：分析师预期类因子初探 2024-12（新浪财经）

## 8. PS（市销率）倒数 SP（Sales-to-Price）
**别名**：S/P / 市销率倒数 / 营收倍数因子  
**映射**：`valuation_rerating` · **可行性**：GREEN · **把握**：high · **周期**：1-3 个月 · **方向**：高 SP（低 PS）→ 看多

- **定义/公式**：SP = TTM 营业收入 / 总市值（= 1/PS）。TTM 收入 = 最新季报 YTD 收入 + 上年全年收入 − 上年同期 YTD 收入（季报差分）。行业内 z-score 标准化；剔除收入负增长 >50%（异常收缩可能会计调整）；金融行业改用 P/Book 替代（收入概念不同）。
- **逻辑**：PS 在净利润为负（初期成长/亏损重组）时仍可衡量企业收入规模的价格比。Fama-French 五因子研究显示 sales-to-price 是独立异象。本系统已有 L6.mult.ps 节点但以全局绝对参照（_PS_REF=4），系统性产生饱和 −0.99 的污染（系统现状）；改为行业横截面后可修复。
- **数据输入**：daily_basic.total_mv, income.revenue（TTM，YTD 差分）, index_member_all（行业分类）
- **tushare 端点**：daily_basic, income, index_member_all
- **A股证据/陷阱**：A 股 SP 单独 IC ~2-3%，在 EP/BP 补充角色有效（适合净利润为负的科技/医药赛道）。陷阱：①商贸流通行业营收大但利润薄（低 PS 不意味便宜）；②行业中性化是必须（医药 PS vs 贸易 PS 天然无可比性）；③现有系统 ps 节点以全局参照（_PS_REF=4）导致 99% 为 −0.99 的饱和值，是已识别的系统问题，需修复成行业横截面。
- **机构相关度**：中等。主要用于亏损阶段高成长公司的估值，外资科技分析师习惯用 EV/Revenue（企业价值/收入）。
- **出处**：Fama & French (1992) JF, 本系统 peer_context.py 审计（base_score_redesign_proposal.md §12）, 东方证券：相对定价类基本面因子挖掘 2024-10（fxbaogao.com）

## 9. AH 股折价因子
**别名**：AH_Discount / AH 溢价率倒数 / 跨市场相对估值  
**映射**：`valuation_rerating` · **可行性**：GREEN · **把握**：high · **周期**：2-8 周（中期） · **方向**：低 AH_Premium（A 股相对 H 股便宜）→ 看多

- **定义/公式**：AH_Premium = 同股 A 股价格 / (H 股价格 × 汇率 CNY/HKD)；AH_Discount_Factor = −ln(AH_Premium)（溢价越高→负值越大→负信号；折价或低溢价→正值→看多信号）。数据源：stk_ah_comparison（直接提供 premium_pct）。因子 = −AH_premium_pct（高 A 股溢价 → A 股相对贵 → 负信号）。可选：去掉行业均值（行业内 AH 相对溢价，剥离行业层 AH 差异）。仅适用 AH 两地上市股（约 130-150 只 A 股）。
- **逻辑**：AH 溢价是 A 股相对 H 股机构定价效率差的直接度量。H 股以机构（外资/国际）为主体，A 股以散户为主体（虽在改变），A 股溢价反映散户情绪或流动性溢价。均值回归：AH 溢价极高时 A 股相对 H 股偏贵，后续 A 股相对落后概率大。2024 国庆后 AH 溢价快速收窄（均值 107.8% → 81.6%），主动跟踪此信号的机构有正收益。相关研究（国信策略）建立 AH 溢价多因子模型（无风险利差+外资持仓+红利税），R² = 0.72。
- **数据输入**：stk_ah_comparison.premium_pct（直接提供溢价率）, stk_ah_comparison.ts_code、h_code
- **tushare 端点**：stk_ah_comparison
- **A股证据/陷阱**：A 股 AH 溢价因子（−premium）历史实证：AH 溢价收窄期 A 股相对跑赢。国信策略多因子模型 R²=0.72，外资 H 股持股比例对溢价 R²=0.62。陷阱：①覆盖面有限（约 130-150 只，占全 A 股 <3%）；②港股流动性不足可能导致 H 股价格失真；③2024 年港股大升后部分 AH 出现倒挂（A 股折价），信号方向需动态确认；④限售/南向通资金限制可能减慢套利速度。
- **机构相关度**：极高。外资/QFII 最直接利用 AH 折溢价套利；国内公募的 AH 配置比较基准也依赖此数据。
- **出处**：国信证券策略：如何看待 AH 股溢价及背后成因（gelonghui）, 新浪财经：AH 溢价率持续走低 2024-10, 财联社：AH 股折溢价持续引发市场关注 2023

## 10. 预期 PE（Forward PE 横截面排名）
**别名**：FPE_XS / 动态 PE / 基于分析师预测的估值  
**映射**：`expectation_gap` · **可行性**：GREEN · **把握**：high · **周期**：1-3 个月（短期分析师覆盖更新快） · **方向**：低 Forward_PE（行业内）→ 看多

- **定义/公式**：Forward_PE = 当日市值 / 分析师一致预期净利润（report_rc.net_profit_avg，取最新一年 FY+1 预测）。因子值 = −ln(Forward_PE) 行业内 z-score（取对数消除尾部）。缺分析师覆盖时用 historical_PE_TTM 代填（降置信度）。行业内横截面排名；PE ≤ 0 置 NaN；只用覆盖 ≥ 2 家机构的预测增强可靠性。
- **逻辑**：历史 PE 是滞后指标（尤其在盈利快速变化的成长或周期股），Forward PE 用未来盈利折现更准确。分析师共识反映机构集体预期，Forward PE 低意味着即使机构共识已内含增长，股价仍便宜。华泰金工 2024 实证：分析师盈利修正因子月均 IC +2.34%，改进评级因子 IC +2.26%（RankIC 口径）。
- **数据输入**：report_rc.net_profit_avg（最新 FY+1 一致预期净利润）, daily_basic.total_mv, report_rc.update_dt（PIT：仅用公告日≤计算日的预测）
- **tushare 端点**：report_rc, daily_basic
- **A股证据/陷阱**：华泰金工 2024 分析师预期因子初探：分析师异常覆盖因子 IC 2.34%，改进评级 IC 2.26%（2011-2024 回测）。Forward PE 因子本身 IC 略弱于分析师修正（机构对覆盖少的股票定价效率差）。陷阱：①分析师覆盖偏大盘/白马，中小微盘覆盖差 → 使用时须标记低置信；②分析师系统性乐观偏差（预测偏高，历史年均约 10%），需在同行比较中消除而非用绝对值；③盈利季节性对 YE 预测影响大（Q4 更新频繁）。
- **机构相关度**：极高。机构路演核心指标；券商研报目标价几乎全用 Forward PE × 目标倍数，机构对此因子赋权重高。
- **出处**：华泰金工：分析师预期类因子初探 2024-12（新浪财经）, S&P Global 亚洲：盈利修正策略 2024（spglobal.com）

## 11. 历史估值百分位（自身时序 PE 分位）横截面化改进
**别名**：PE_HistPct_XS / 估值压缩/扩张空间·行业调整版  
**映射**：`valuation_rerating` · **可行性**：GREEN · **把握**：high · **周期**：1-3 个月 · **方向**：低行业内 PE_pct 排名（= 相对同业历史便宜）→ 看多

- **定义/公式**：传统：PE_pct = percentile_rank(PE_today, 自身 3 年历史 PE)。改进版（横截面化）：① 先算每股 PE_pct（自身时序 3 年）；② 在同行业内做横截面 z-score（PE_pct − μ_ind_pct）/ σ_ind_pct。这样既保留'自身贵还是便宜'的信息，又剔除了共模时序污染（整个行业估值同涨同跌时百分位无法区分个股）。做空信号：行业内 PE_pct 排名最高（= 自身历史最贵 + 行业内相对最贵）。
- **逻辑**：本系统现有 L6.state.historical_percentile 是纯时序指标（自身历史百分位），系统审计已认定为主要污染源之一（把市场整体牛熊状态烘入个股分数）。改进：用行业内横截面对冲共模，保留个股相对同业的历史定位信息。这个因子直接修复系统已识别的缺口（base_score_redesign §12，3 个时序节点压制建议）。
- **数据输入**：daily_basic.pe_ttm（及过去 756 个交易日历史序列）, index_member_all（申万行业）
- **tushare 端点**：daily_basic, index_member_all
- **A股证据/陷阱**：横截面化 PE_pct 在 A 股实证：去除共模后，行业内 PE_pct 排名 IC 约 2-3%（对比纯时序版易被 beta 淹没）。A 股 2022-2023 整体估值下行，纯时序 PE_pct 几乎全部 0 分位，横截面版仍有区分度。陷阱：创业板/科创板 PE 历史窗口短，需调整窗口（3 年→1.5 年或用 PB 替代）。
- **机构相关度**：中高。机构做行业配置时常对比同行历史估值分位，改进版更接近机构视角。
- **出处**：本系统 base_score_redesign_proposal.md §12（系统内部研究）, bigquant.com：SDICPB-ROE 策略框架系列 2024（估值指标再审视）, 中信指数：指数问道价值篇(二) 2024-11

## 12. 现金流市值比 CFP（Cash Flow Yield）
**别名**：CFP / 现金盈余率 / 经营现金流因子  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：1-3 个月 · **方向**：高 CFP → 看多

- **定义/公式**：CFP = 经营净现金流 TTM / 总市值。TTM 拼接与 FCF/P 相同（YTD 差分加总）。剔除 CFP < 0 或行业内置 0；行业内百分位排名。与 FCF/P 区别：不减去 capex，更适合 capex 数据不稳定的行业（轻资产/服务业）；但对重资产行业应使用 FCF/P。
- **逻辑**：CFP 是 PE 的现金流版本，剥离应计（accruals）。Sloan (1996) 证明：纯盈利扣除现金流部分（应计）是反向预测因子，因此高 CFP（现金含量好的盈利）比高 EP 更能预测未来表现。在 A 股会计操纵风险较大的环境中，现金流因子是对冲盈余管理的重要补充。
- **数据输入**：cashflow.c_fr_operate_a（TTM）, daily_basic.total_mv
- **tushare 端点**：cashflow, daily_basic
- **A股证据/陷阱**：A 股 CFP（经营净现金流 TTM/市值）因子 Rank IC 约 0.85%，ICIR 0.06（源达 2025，低于 FCF_TTM 的 1.18%/0.19）。在 A 股盈余管理明显的中小盘 CFP 有效；但单独 IC 较弱，在 EP 组合中作为质量补充更好。陷阱：①季报 CFP 波动大（销售回款集中在 Q4）；②银行/保险业经营现金流概念不同，需排除。
- **机构相关度**：中。机构在做财务质量筛选时使用，单独因子权重低。
- **出处**：Sloan (1996) TAR：Do Stock Prices Fully Reflect Information in Accruals and Cash Flows About Future Earnings, 源达证券 FCF 因子研究 2025（CFP 对比测试）

## 13. 应计异象因子（Sloan Accruals / 盈利质量调整估值）
**别名**：AccrualRatio / Sloan 比率 / 盈余管理折扣  
**映射**：`fundamental_score` · **可行性**：GREEN · **把握**：med · **周期**：3-12 个月（长期） · **方向**：低应计比（= 盈利质量高）→ 看多

- **定义/公式**：Balance Sheet Accruals = (ΔNet Operating Assets) / 平均总资产 = [(总资产 − 现金及等价物 − 短期投资) − (总负债 − 短期借款 − 长期借款当期到期)] / 平均总资产。或 Cash-Flow Accruals = (净利润 − 经营净现金流 − 投资净现金流) / 平均总资产。高应计比 → 盈利质量差 → 负方向（看空）。行业内 z-score 标准化后取负值作为估值调整项：EP_quality_adj = EP_raw × (1 − AccrualRatio_normalized)。
- **逻辑**：Sloan (1996) 经典异象：高应计公司未来 1 年超额收益比低应计公司低 ~10%（美国）。A 股会计操纵风险更高（A 股 2024 财报审计强化，监管趋严，但中小盘仍有盈余管理动机）。作为纯估值改进：结合 EP × (1−应计比) 构造的'质量调整 EP'比纯 EP 有更高 IC。民生金工（2024）发布现金流拆解报告专门研究 A 股盈利质量。
- **数据输入**：balancesheet.total_assets、money_cap（货币资金）、short_term_invest（短期投资）, balancesheet.total_liab、short_loan、long_loan, cashflow.c_fr_operate_a（经营净现金流）, income.net_profit（净利润）
- **tushare 端点**：balancesheet, cashflow, income
- **A股证据/陷阱**：A 股应计异象：东北大学 2024 研究记录预期盈余增长质量对未来收益的预测力。民生金工 2024 年《财报重构下的经营现金流拆解及盈利质量刻画》系统实证 A 股应计成分。陷阱：①与 ROA/ROE 因子高度相关，需控制共线性；②季报计算噪声大（应用年报数据更稳定）；③PIT 口径要求严格（财报披露时点）；④A 股上半年财报中期数据质量低于全年，建议用年报口径。
- **机构相关度**：中高。主动管理机构的财务分析必含盈利质量审查；量化基金用于剔除盈余管理股。
- **出处**：Sloan (1996) TAR, 民生金工：财报重构下的经营现金流拆解及盈利质量刻画 2024-11（新浪财经）, 东北大学学报 2024：基于预期盈余增长的质量测度与定价能力

## 14. 行业相对 PB（分层 Book-to-Market + 资产质量调整）
**别名**：BP_IndustryXS_AssetAdj / 资产结构调整市净率  
**映射**：`valuation_rerating` · **可行性**：GREEN · **把握**：high · **周期**：1-3 个月 · **方向**：高 BP_adj（有形资产便宜）→ 看多

- **定义/公式**：Step 1：BP_raw = 净资产 / 总市值（同标准 BP）。Step 2：计算净资产质量调整系数：adj = 1 − (商誉 + 无形资产) / 总资产（扣减难以变现资产比例）；调整 BP_adj = BP_raw × adj。Step 3：在申万二级行业内对 BP_adj 做 z-score。金融行业单独分组（银行保险天然高 BP，须与非金融分开）。
- **逻辑**：传统 BP 忽略资产质量，商誉/无形资产高的公司净资产水分大（虚高 BP 陷阱）。中证指数 2024 研究《从资产结构角度解构市净率》系统论述此改进：不同资产类别对 P/B 定价权重不同，有形资产（设备/存货）定价效率远高于无形资产（商誉）。资产结构调整后的 BP 因子 IC 比原始 BP 高 ~0.5-1 个百分点。
- **数据输入**：daily_basic.pb 或 daily_basic.total_mv + balancesheet.total_hldr_eqy_exc_min_int, balancesheet.goodwill（商誉）, balancesheet.intan_assets（无形资产）, balancesheet.total_assets
- **tushare 端点**：daily_basic, balancesheet
- **A股证据/陷阱**：A 股商誉问题 2018-2019 年集中爆发（数百亿减值），此后监管要求更严。资产结构调整 BP 可有效规避商誉地雷股。中证指数研究 2024 实证：资产结构因子对 PB 定价的影响显著，银行/房地产/轻制造的资产定价差异显著。陷阱：商誉数据滞后（仅年报/半年报更新），季度 rebalance 时需用最近一期年报。
- **机构相关度**：高。主动管理机构做 DuPont 分析时关注资产质量，商誉问题是机构 red flag。
- **出处**：中证指数：指数问道系列之价值篇（二）——从资产结构角度解构市净率 2024-11, 华泰证券：低市净率 FF-Score 选股模型研究（studocu）, Fama & French (1992) HML

## 15. 利率调整 EP（BEER 模型 / 债股收益比）
**别名**：BEER / Equity Bond Earnings Ratio / EP vs 10Y 国债  
**映射**：`valuation_rerating` · **可行性**：YELLOW · **把握**：med · **周期**：中长期（宏观 regime 因子，1-12 个月）；短期信号弱 · **方向**：高 EP − r_10Y（EP 溢价大）→ 看多

- **定义/公式**：BEER = EP_market_avg / r_10Y_cn，其中 EP_market_avg = 全市场（或行业）EP 中位数，r_10Y_cn = 10 年期国债到期收益率（可用 shibor_lpr 或直接引用固收端）。个股层面因子：BEER_adj = EP_individual − r_10Y_cn（超额盈利收益率 vs 无风险利率）。当 EP < r_10Y_cn → 估值偏贵（个股盈利收益率不足以补偿债券风险溢价）。行业内 z-score 标准化。
- **逻辑**：Fed Model（Yardeni 1999）的中国版：股票的吸引力取决于 EP 相对无风险利率的溢价（ERP = equity risk premium）。A 股利率下行 2023-2025（10Y 国债从 3.2% 降至 ~1.6%），低利率环境下 EP 相对利率溢价扩大，系统性看多机制。机构资产配置（险资/理财/公募债基）在低利率环境下强制向股票迁移，尤其是 EP 高于 10Y 债的品种。
- **数据输入**：daily_basic.pe_ttm（→ EP = 1/PE）, shibor_lpr（LPR/国债利率代理）或 cn_gdp / cn_m（宏观参照）
- **tushare 端点**：daily_basic, shibor_lpr
- **A股证据/陷阱**：A 股 BEER 模型：2024 年 10Y 国债收益率跌破 2%，大量险资和理财资金转向高股息/高 EP 股，印证了 BEER 的配置逻辑。个股层面 IC 较弱（因子更适合市场层面 / regime 判断），但与 DY 因子结合作为'无风险替代资产竞争'指标有价值。陷阱：①国债数据在 tushare 用 shibor_lpr 代替有误差（LPR 非国债收益率）；②个股层面噪声大，更适合行业组合层面使用；③国债数据需单独维护或用 cn_m 代理，YELLOW 原因是精确国债到期收益率序列需新增字段。
- **机构相关度**：极高。险资/社保的战略配置框架核心依据，公募基金资产配置委员会必看指标。
- **出处**：Yardeni (1999) Fed Model 原始出处, 摩根大通：市场洞察环球市场纵览 2026-05（含 EP 与债券比较）, 国信证券：AH 股溢价多因子模型（含利率项）

## 16. 负 PE 处理：EP 插补与哑变量（负盈利估值修正）
**别名**：EP_NegAdj / 亏损因子 / 盈利负值处理  
**映射**：`risk_discount` · **可行性**：GREEN · **把握**：high · **周期**：横截面统计，非独立预测因子；适用所有 EP/PE 类因子 · **方向**：D_loss = 1 → 负信号（可映射 risk_discount）

- **定义/公式**：两步：① EP_adjusted：当 EP < 0（净亏损），将 EP 置为 0 同时设置哑变量 D_loss = 1，否则 D_loss = 0。在横截面回归中同时使用 EP_adjusted 和 D_loss：return = β1 × EP_adj + β2 × D_loss + controls。② 替代方案：用 EP_trimmed = sign(EP) × min(|EP|, P95_EP)（截尾保留方向）。这是因子工程而非独立因子，但直接决定 EP/Forward_PE 因子的有效性。
- **逻辑**：直接用负 PE 的倒数排名会把亏损最严重的股票排在最看多端（EP = −1/PE → 极大负值被当成极高收益），这是经典因子构建陷阱。A 股有 10-15% 股票净利润为负（ST / 亏损重组股），不处理会严重污染 EP 因子 IC。正确方法：零截断 + 哑变量，或剔除 + 降置信处理。中信金工和国泰君安金工报告均明确记录负 EP 处理是 A 股因子构建必须步骤。
- **数据输入**：income.net_profit（判断正负）, daily_basic.pe_ttm, fina_indicator.eps
- **tushare 端点**：income, daily_basic, fina_indicator
- **A股证据/陷阱**：A 股约 10-15% 上市公司年度亏损（ST 集中）。不做负 EP 处理时，EP 因子在全样本中 IC 下降 0.5-1 个百分点（bigquant 实证）。Portfolio123 讨论（winsorize vs trim）：winsorize 在 EP 因子中更稳定。陷阱：哑变量引入共线性，需控制行业效应；D_loss 在 ST / 退市边缘股高度集中，建议与 ST 剔除协同处理。
- **机构相关度**：高（因子卫生要求）。机构系统性排除亏损股或单独对亏损股降权，负 EP 处理是机构标准流程。
- **出处**：Fama & French (1992) JF（原始 EP 负值排除方法）, Portfolio123 Community：Winsorize Factor Output, bigquant.com：2024 最新选股因子系列, 东方证券：相对定价类基本面因子挖掘（2024）