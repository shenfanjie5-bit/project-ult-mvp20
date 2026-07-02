# 系统勘察 / 因子映射"菜单"（authoritative reference）

> 因子要"代入系统"，必须能映射到本文的【可用数据】+【dp_id/score_target】。本文是 Phase 2 可行性判定的唯一基准。
> 源：`mvp20/scoring.py`、`mvp20/aggregator.py`、`mvp20/derive.py`、`mvp20/peer_context.py`、`docs/audit/base_score_redesign_proposal.md`、`docs/data_sources/tushare_endpoints.csv`、`pit_backtest/`。读于 2026-06-08。

## A. 打分架构（dual-axis Merit + Timing）

**最终分**（`scoring.py::compute_company_score`）：
```
total = industry_bounded            # = fundamental/merit 轴：Σ(score×权重×conf)/Σ(权重×conf)，跳过 score≈0 节点（覆盖率归一加权均值，非 Σ→tanh）
      + event                       # company_event_score（catalyst/事件）
      + capital                     # capital_sentiment_score（资金情绪 / funding）
      - risk                        # risk_discount
      - val_pressure                # valuation_pressure / valuation_rerating（贵→减）
      - priced_in                   # priced_in_discount（已被price-in→减）
```
+ `expectation_gap`（分析师/盈利修正）按 horizon 加权进短/中/长。

**score_target（因子接入口，共 7 类）**：
| score_target | 轴 | 方向 | 现状 |
|---|---|---|---|
| `fundamental_score` | Merit | + 好公司 | 已接 6 财务硬指标 + L0/L1-L3 行业定性 |
| `expectation_gap` | Merit/短中 | + 超预期 | 分析师修正/指引/预告 |
| `valuation_rerating` | Timing | − 贵 | R-3b.2 已横截面（peer_compare 锚 + 分层池）|
| `capital_sentiment` | Timing | + 资金流入 | **近乎死**（仅 active_inflow）|
| `funding_score` | Timing | + 杠杆/融资 | **死轴**（median 0 / 1% 股）|
| `risk_discount` | 减项 | − 风险 | L8.cap/fin/op/gov.* |
| `priced_in_discount` | 减项 | − 已price-in | run_up/crowdedness/news_age |

**horizon 权重**（`scoring.py:91-106`）：
- short：fundamental 0.20 / expectation_gap 0.30 / valuation_rerating 0.10 / capital_sentiment 0.40
- medium：expectation_gap 0.30 / valuation_rerating 0.10 / capital_sentiment 0.10
- long：expectation_gap 0.05 / valuation_rerating 0.30 / capital_sentiment 0.05

**信号阈值**（绝对刻度，`scoring.py:194-197`；market_adapter 对 A 股≈恒等）：
`BUY ≥ +0.20 / HOLD ≥ −0.15 / WATCH ≥ −0.50 / AVOID < −0.50`。

## B. 现有 dp_id → score_target 路由（`aggregator.py`，具体）

- **fundamental_score**：`L5.fina.roe` `L5.fina.roa` `L5.fina.debt_ratio` `L5.fina.ocf_quality` `L5.fina.net_profit_yoy` `L5.fina.asset_turnover` `L5.bs.leverage` `L5.bs.goodwill_ppe` `L5.is.gross_margin` `L5.is.margins` `L4.eff.cycle` `L4.eff.turnover` `L4.cost.labor` + L0/L1-L3 行业定性（经 industry_variables）
- **valuation_rerating**：`L6.state.peer_compare`(横截面锚) `L6.state.historical_percentile`(时序*) `L6.state.expansion_compression`(时序*) `L6.path.tag`(时序*) `L6.mult.ps` `L6.mult.ev_ebitda` `L6.mult.forward_pe`(绝对*) `L8.val.overvalued`（*=有 peer_context 时被压制）
- **expectation_gap**：`L6.priced.analyst_revision` `L9.company.earnings_guidance`→`L5.fcst.guidance_change` `L7.mood.analyst_rating`（+ forecast/express 派生）
- **capital_sentiment / funding_score**：`L7.flow.active_inflow`（**唯一**）
- **priced_in_discount**：`L8.val.priced_in` `L6.priced.run_up` `L6.priced.crowdedness` `L6.priced.news_age`
- **risk_discount**：`L8.cap.crowdedness/liquidity_short/outflow_cut/short_increase` `L8.fin.cash_ar/debt_pressure/eps_downward` `L8.op.cost_overrun/inventory_glut` `L8.gov.litigation/insider_sell/management_change`

dp_id 层级语义：L0 行业景气 · L1-L3 定性(护城河/格局/客户) · L4 运营效率 · L5 财务硬数据/预测 · L6 估值(state/mult/path/priced) · L7 交易(flow/mood) · L8 风险(cap/fin/op/gov)+估值压力(val) · L9 公司事件/披露 · L11 trade signal。

## C. 可用数据（tushare，107 个 "covered" 端点；机构/资金侧尤其丰富）

**机构/资金流/筹码（机构为主市场的关键，当前几乎全未用）**：
- `moneyflow` `moneyflow_dc` `moneyflow_ths` 个股资金流 · `moneyflow_hsgt` **沪深港通资金流** · `moneyflow_ind_ths` 行业资金流 · `moneyflow_mkt_dc` 大盘资金流 · `moneyflow_cnt_ths` 板块资金流
- `hk_hold` **沪深股通持股明细（北向持股）** · `ggt_daily/ggt_monthly` 港股通成交
- `hm_detail` **游资交易每日明细** · `hm_list` 游资名录（龙虎榜系）
- `block_trade` **大宗交易** · `cyq_perf` **每日筹码及胜率（筹码分布）**
- `margin` `margin_detail` **融资融券** · `slb_len` 转融资
- `stk_holdernumber` **股东人数** · `stk_holdertrade` 增减持 · `pledge_detail/pledge_stat` 股权质押 · `share_float` 限售解禁

**价量/技术**：`daily` `daily_basic`(PE/PB/PS/换手/量比/总市值) `weekly` `monthly` `bak_daily` `stk_factor_pro` **股票技术面因子(专业版)** `idx_factor_pro` 指数技术因子 `stk_limit` `cyq_perf`
**财务**：`income` `balancesheet` `cashflow` `fina_indicator` `fina_mainbz` `express` 快报 `forecast` 预告 `dividend` `repurchase`
**分析师/预期**：`report_rc` 券商盈利预测
**情绪/题材**：`dc_hot` 东财热榜 · `kpl_concept/kpl_list` 开盘啦题材/榜单 · `limit_list_d/limit_list_ths` 涨跌停 · `limit_cpt_list` 涨停最强板块 · `limit_step` 连板天梯 · `irm_qa_sh/sz` 互动问答
**宏观/利率**：`cn_cpi` `cn_gdp` `cn_m` 货币供应 `cn_pmi` `cn_ppi` `sf_month` 社融 `shibor/shibor_lpr/libor/hibor`
**指数/行业**：`index_basic` `index_dailybasic` `index_member_all`(申万分级) `index_classify` `ci_daily`(中信) `dc_daily`(东财) `index_global`
**风险/其它**：`st` ST · `namechange` · `new_share` · `stk_ah_comparison` AH 比价 · `disclosure_date`

> 全表 `docs/data_sources/tushare_endpoints.csv`（107 covered / 38 out_of_scope）。已落地缓存 DockCase 2TB（按股只读命中 + 写回 + 增量 append）。

## D. 回测能力（impact study 的证据手段）

`pit_backtest/`（**只读，勿改**；可在本目录复刻方法论）：
- PIT collector（DockCase 缓存，as-of 过滤防泄漏）→ `score.py`（复用生产引擎，冻 L0-L3 + 4 个事件节点）→ `metrics.py`。
- `metrics.py` 提供：**rank_ic**(Spearman + t 检验 p + Fisher CI)、**quantile_groups**(分档 mean/SE + top-bottom spread)、**signal_buckets**(BUY/HOLD/WATCH/AVOID 前向收益 + 单调性 + 置换 p)、bootstrap CI。
- 横截面口径：每个 (base_date, horizon) 一组；小样本（n≈116~1641，3 base date），IC SE 大 → 是泄漏/sanity 审计，非 alpha 证明。
- **已知结论（量化核）**：是"2-4 周"短中期信号。+10d rankIC **+0.113**(p<.001)、+15d +0.088、+20d +0.078，十档单调正；+5d 噪声；+30d 弱；**+60-90d 反转**（普涨市低质量反弹）。

## E. 已知缺口 / 机械性痛点（= 研究机会清单）

1. **资金/机构轴是死轴**：`capital_sentiment`/`funding_score` 仅 `active_inflow`。北向(hk_hold/moneyflow_hsgt)、游资(hm_detail)、大宗(block_trade)、融资融券(margin)、筹码(cyq_perf)、股东人数(stk_holdernumber) 全未成因子。**机构为主市场的最大空白**。
2. **无显式 quality 因子族**：只有 6 个孤立财务比率；缺 Piotroski F-score、Sloan 应计/盈利质量、Novy-Marx 毛利率、资产增长(asset growth)、Z/O-score 财务困境。
3. **无 momentum/reversal 因子**：run_up 只当 priced_in 罚分；A 股短期反转(1M reversal)与行业动量(industry momentum)是强 anomaly，未建模。
4. **无 low-vol / 特异波动 因子**：低波动、特异波动率(idio vol)、MAX effect、beta 异象未用。
5. **估值仍有时序/绝对残留**：peer_compare 横截面已是锚，但 historical_percentile/expansion/path.tag(时序)、ps/ev_ebitda/forward_pe(全局绝对) 仍在（有 peer_context 时压制）；无跨市场池(R-3b.3)。
6. **宏观 regime 休眠（R-7 deferred）**：market_regime 因子算出但被 beta 压成≈1.0；用户要用 PIT 回测验证再定 beta。
7. **expectation_gap 浅**：仅分析师评级/指引；缺 SUE/标准化盈利惊喜(PEAD)、分析师修正动量、预测分歧度(dispersion)。
8. **confidence 现为 band**（R-2c），覆盖率→置信而非缩分（已修，可作因子加权参考）。

## F. 硬约束

- 本研究**只读**；不改 `mvp20/`、`config/`、`pit_backtest/`、`scripts/` 等任何文件。
- 产出只写 `factor_research/`。
- 因子"可行"判定标准：能由 C 的数据算出，且能映射到 B 的某 score_target（或明确为需新增 dp_id）。
