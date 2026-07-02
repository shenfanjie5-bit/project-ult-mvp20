# Data Interface Update Schedule (Draft)

日期：2026-05-11  
状态：暂存稿。本文档只定义建议更新时间段和更新频率，尚未落地为调度器配置。

## 口径

- 覆盖范围：当前代码中实际调用的 `tushare`、FMP、Futu OpenD 接口，以及 `docs/data_sources/*.csv` 中标记为 `covered` 且当前可用的接口。FMP Premium/Ultimate 才能用的接口单列为“升级后启用”。
- 最高频率：最高按 `1m` 入库。Futu push / tick 等秒级数据也先聚合成 1 分钟分区写入。
- 时区：A 股和港股用 `Asia/Shanghai` / `Asia/Hong_Kong`，美股用 `America/New_York`。不要把美股时间硬编码成北京时间，避免 DST 切换错位。
- 交易日判断：A 股用 Tushare `trade_cal`，港/美用 Futu `request_trading_days` 或 FMP `/market-hours`、`/holiday-calendar`。休市日不跑高频轮询，只跑低频健康检查和公告/新闻补扫。
- EOD/公告类数据的窗口是“调度轮询窗口”，不是上游 SLA。落库时仍以 provider 返回的 `trade_date`、`ann_date`、`end_date` 做幂等去重和迟到修正。

## 交易时段基准

| 市场 | 高频价格/盘口更新时间段 | 高频频率 | 依据和备注 |
|---|---|---:|---|
| A 股 | 09:15-11:30、13:00-15:30 CST | 1m | 竞价交易覆盖 09:15-09:25、09:30-11:30、13:00-14:57、14:57-15:00；科创/创业及大宗相关盘后固定价/盘后定价覆盖 15:05-15:30。当前 `mvp20/sources/tushare_source.py` 多数是 EOD 接口，真实 A 股分钟价要等 Tushare/Futu 对应权限开通后再跑 1m。 |
| 港股 | 09:00-12:00、13:00-16:10 HKT | 1m | 覆盖 HKEX POS 09:00-09:30、连续交易 09:30-12:00 / 13:00-16:00、CAS 16:00-随机 16:08-16:10。午休只保留 15m 状态检查。 |
| 美股股票 | 04:00-20:00 ET；Futu 支持 overnight 时另加 20:00-04:00 ET | 1m | Nasdaq 当前系统时段 04:00-20:00 ET，常规交易 09:30-16:00 ET；Futu OpenAPI 有 PreMarket、AfterHours、Night/Overnight 状态。overnight 只对 Futu `Session_ALL` / 权限可用标的启用。 |
| 美股期权 | 09:30-16:15 ET | 1m | 个股期权不按 overnight 跑；收盘后 16:15-17:30 ET 做链和 IV 补扫。 |
| 美股指数/期货 | 以 Futu `get_market_state` 返回状态为准 | 1m open / 15m closed | 不用固定单一时段套所有 futures；不同合约交易时间差异大。 |

## 当前代码实际调用

| Provider | 当前实际调用接口 | 数据性质 | 建议更新时间段 | 频率 | 备注 |
|---|---|---|---|---:|---|
| Tushare | `trade_cal` | 健康检查 / A 股交易日历 | 每日 06:30、18:30 CST；调度启动时立即查一次 | daily + startup | `mvp20 check-tushare` 用它探活；调度器也应作为 A 股交易日 gate。 |
| Tushare | `daily_basic`, `moneyflow`, `margin_detail`, `block_trade`, `top_list` | A 股 EOD 行情、资金流、两融、大宗、龙虎榜 | 交易日 15:05-18:30 CST | 5m 至有当日分区；之后 30m | 现在 collector 每 60 秒重拉，但这些值通常只在盘后更新。建议拆出 EOD 调度，避免把 EOD 接口伪装成分钟行情。`top_list` 已补入 `tushare_endpoints.csv`。 |
| Tushare | `hk_hold` | 沪深股通持股 | 历史分区补数；不做当前日 live | daily/quarterly | `daily_refresh.py` 已标注官方日频持股发布止于 2024-08-20，当前日不能宣称日频 fresh。 |
| Tushare | `income`, `balancesheet`, `cashflow`, `dividend` | A 股财报 / 分红 | 财报季 07:00-09:30、11:30-13:00、15:00-23:30 CST；非财报季 20:30-23:30 CST | 财报季 15m；非财报季 daily | collector 当前每轮拉最新一批。建议按公告窗口跑，保留 T+1 07:30 修正扫。 |
| FMP | `/quote` | 健康检查 / 美股报价 | 美股交易日 04:00-20:00 ET | 1m | `mvp20 check-fmp` 用 `/quote?symbol=AAPL` 探活。 |
| FMP | `/income-statement`, `/balance-sheet-statement`, `/cash-flow-statement`, `/ratios-ttm` | 美股财报 / TTM 估值 | 财报季 05:00-09:30、16:00-22:00 ET；非财报季 06:30、17:30 ET | 财报季 30m；非财报季 daily | `fmp_endpoints.csv` now uses the code path `/ratios-ttm` for the ratio/TTM capability. |
| Futu OpenD | `get_global_state` | OpenD / 市场状态健康检查 | 所有交易日前后；守护进程启动时 | 1m during live / 15m off-hours | 用于确认 OpenD、行情登录和各市场状态。 |
| Futu OpenD | `get_market_snapshot` | 港/美实时快照、顶层买卖盘、PE/PB、成交额 | 港股 09:00-16:10 HKT；美股 04:00-20:00 ET；overnight 20:00-04:00 ET 仅权限可用时 | 1m | 当前生产路径主要靠 snapshot，不占订阅配额。 |
| Futu OpenD | `get_capital_flow` | 个股资金流 | 港股 09:30-16:10 HKT；美股 04:00-20:00 ET | 1m live / 5m extended | 当前代码按标的逐个拉 `INTRADAY`，建议只在对应市场开盘或 extended 有数据时跑。 |

## Tushare 可用接口调度

按 `docs/data_sources/tushare_endpoints.csv` 中 `status=covered` 统计，可用接口 107 条；其中 Raw Zone adapter 已有 typed asset 的 41 个接口应优先按本表落地。`trade_cal` 在 CSV 中有股票/期货两行，调度上按同一接口处理。

| 调度桶 | 接口 | 数据性质 | 更新时间段 | 频率 |
|---|---|---|---|---:|
| A_LIVE_IF_PERMISSION | `daily`, `daily_basic`, `moneyflow`, `moneyflow_dc`, `moneyflow_ths`, `stk_limit`, `limit_list_ths`, `limit_list_d`, `cyq_perf`, `stk_factor_pro`, `stk_nineturn` | A 股价格、盘中资金流、涨跌停、筹码、技术因子 | 若接入实时/准实时权限：交易日 09:15-11:30、13:00-15:30 CST；否则按 EOD 桶 | 1m live；EOD 5m |
| A_EOD_PRICE_FEATURE | `daily`, `weekly`, `monthly`, `bak_daily`, `daily_basic`, `stk_limit`, `moneyflow`, `moneyflow_dc`, `moneyflow_ths`, `cyq_perf`, `stk_factor_pro`, `stk_nineturn`, `idx_factor_pro` | 日/周/月 K、估值、换手、涨跌停、资金流、技术因子 | 交易日 15:05-18:30 CST；T+1 07:30 补扫 | 5m 到当日数据出现；之后 daily |
| A_INDEX_SECTOR_EOD | `index_global`, `index_dailybasic`, `index_weekly`, `index_monthly`, `daily_info`, `sz_daily_info`, `ci_daily`, `sw_daily`, `dc_daily`, `ths_daily`, `tdx_daily` | 指数/行业/板块行情 | 交易日 15:05-19:00 CST；T+1 07:30 补扫 | 15m 到当日数据出现；之后 daily |
| A_REFERENCE_STATIC | `stock_basic`, `stock_company`, `stk_managers`, `stock_st`, `st`, `bse_mapping`, `bak_basic`, `namechange`, `index_basic`, `index_classify`, `index_member_all`, `ci_index_member`, `ths_index`, `ths_member`, `tdx_index`, `tdx_member`, `stock_hsgt`, `trade_cal` | 证券主数据、交易日历、行业/板块成分 | 06:30、18:30 CST；周日 20:00 全量校验 | daily；static weekly full |
| A_CORPORATE_EVENTS | `dividend`, `repurchase`, `share_float`, `stk_holdernumber`, `pledge_detail`, `pledge_stat`, `stk_holdertrade`, `stk_surv`, `forecast`, `express`, `disclosure_date`, `new_share`, `fina_mainbz`, `report_rc`, `top10_holders` | 分红回购、解禁、股东、质押、调研、业绩预告/快报、主营构成、券商预测、前十大股东 | 交易日 07:00-09:30、11:30-13:00、15:00-23:30 CST；财报季扩大到每日 | 财报/公告季 15m；平时 60m + daily |
| A_FINANCIAL_STATEMENTS_RAW | `income`, `balancesheet`, `cashflow`, `fina_indicator` | 三表和财务指标 Raw Zone typed assets | 财报季 07:00-23:30 CST；非财报季 20:30-23:30 CST | 财报季 30m；非财报季 daily |
| A_MARGIN_BLOCK_DRAGON | `margin`, `margin_detail`, `slb_len`, `slb_len_mm`, `block_trade`, `hm_list`, `kpl_list`, `hm_detail`, `limit_cpt_list`, `limit_step`, `kpl_concept` | 两融、转融通、大宗交易、游资/龙虎榜/涨停题材 | 交易日 15:05-20:30 CST；`limit_*` 可在 09:15-15:30 做 live | live 1m for limit；EOD 5m/15m |
| A_MARKET_CAPITAL_FLOW | `moneyflow_mkt_dc`, `moneyflow_cnt_ths`, `moneyflow_ind_ths` | 大盘、板块、行业资金流 | 交易日 09:15-15:30 CST 如上游盘中更新；否则 15:05-20:30 CST | live 1m if available；EOD 15m |
| A_CROSS_BORDER_FLOW | `hk_hold`, `ggt_daily`, `ggt_monthly`, `moneyflow_hsgt`, `stk_ah_comparison` | 沪深港通、港股通、AH 溢价 | 交易日 16:30-20:30 CST；月度数据月初 06:30 补扫 | daily 15m 到出现；monthly daily until present |
| A_MACRO_RATES | `cn_cpi`, `cn_ppi`, `cn_gdp`, `cn_pmi`, `sf_month`, `cn_m`, `shibor`, `shibor_quote`, `shibor_lpr`, `hibor`, `libor`, `wz_index`, `us_trycr`, `us_tycr`, `us_tltr`, `us_trltr`, `us_tbr` | 宏观、利率、货币信用 | 08:00-12:00、16:00-20:00 CST；按发布日重点扫 | 发布日 15m；非发布日 daily |
| A_SENTIMENT_IR | `dc_hot`, `ths_hot`, `irm_qa_sh`, `irm_qa_sz` | 热榜、互动问答 | 交易日 09:00-23:00 CST；非交易日 10:00、18:00 | 热榜 15m；问答 60m |

## FMP 可用接口调度

按 `docs/data_sources/fmp_endpoints.csv` 当前 `currently_subscribed=yes` 统计，Starter 当前可直接调用 endpoint row 48 条，其中 46 条映射到 covered mvp20 capability。Premium/Ultimate 锁定接口不应进入当前生产调度，除非订阅字段更新。

| 调度桶 | 当前可用接口 | 数据性质 | 更新时间段 | 频率 |
|---|---|---|---|---:|
| US_LIVE_QUOTES | `/quote`, `/quote-short` | 美股实时报价 / 快照 | 04:00-20:00 ET；重大财报日可延长 stale check 到 22:00 ET | 1m live；15m stale check |
| US_INTRADAY_BARS_STARTER | `/historical-chart/1hour`, `/historical-chart/4hour` | Starter 可用小时级 K 线 | 04:00-20:00 ET；按 bar close 后 2-5 分钟补拉 | 15m |
| US_DAILY_PRICE | `/historical-price-full`, `/historical-chart/1day` | 日线 / EOD | 16:05-20:30 ET；T+1 06:30 ET 补扫 | 15m 到当日 bar 出现；之后 daily |
| US_PROFILE_REFERENCE | `/stock/list`, `/profile`, `/company-outlook`, `/key-executives`, `/historical-employees`, `/stock_peers` | 股票列表、公司画像、同业、管理层 | 06:30 ET；周日 20:00 ET 全量校验 | daily；full weekly |
| US_FUNDAMENTALS | `/income-statement`, `/balance-sheet-statement`, `/cash-flow-statement`, `/key-metrics`, `/key-metrics-ttm`, `/ratios-ttm`, `/financial-growth`, `/enterprise-values` | 财报、指标、估值 | 财报季 05:00-09:30、16:00-22:00 ET；非财报季 06:30、17:30 ET | 财报季 30m；非财报季 daily |
| US_EARNINGS_CALENDAR | `/earning_calendar`, `/earnings-confirmed`, `/earning-historical`, `/earnings-surprises` | 财报日历、已确认财报、历史 surprise | 05:00-22:00 ET；财报季扩大 | 60m；财报季 15m |
| US_ANALYST_FILINGS_DCF_STARTER | `/stable/analyst-estimates`, `/stable/sec-filings-search/symbol`, `/stable/discounted-cash-flow` | 券商预期、SEC filing index、DCF 估值 | 06:00-22:00 ET；财报季/重大事件日扩大 | 60m；事件窗口 15m |
| US_NEWS | `/stock_news`, `/general_news`, `/press-releases` | 新闻、公告稿 | 04:00-22:00 ET；非交易日 08:00-20:00 ET | 5m during live；30m off-hours |
| US_INSIDER | `/insider-trading` | 内部人交易基础版 | 06:00-22:00 ET | 60m；收盘后 15m |
| US_ACTIONS_RETURN | `/historical-stock-dividend`, `/dividend-calendar`, `/historical/buyback`, `/shares_float`, `/historical-stock-split`, `/stock_split_calendar` | 分红、回购、股本、拆股 | 06:30、17:30、21:30 ET | daily；事件窗口 60m |
| US_INDEX_MACRO | `/historical-index`, `/sector-performance`, `/stock-market-performance`, `/stable/treasury-rates`, `/stable/economic-calendar` | 指数、板块表现、国债利率、经济指标 | 指数随 US_LIVE_QUOTES；宏观/treasury 在 07:00-18:00 ET | 指数 1m/15m；宏观发布日 15m，否则 daily |
| US_CALENDAR_IPO | `/market-hours`, `/holiday-calendar`, `/ipo_calendar` | 交易时间、假日、IPO | 06:00 ET；IPO 窗口 16:00-22:00 ET | daily；IPO 60m |

### FMP 升级后才启用

| 调度桶 | 当前锁定接口 | 启用条件 | 建议更新时间段 | 频率 |
|---|---|---|---|---:|
| US_MINUTE_BARS_PREMIUM | `/historical-chart/30min`, `/historical-chart/15min`, `/historical-chart/5min`, `/historical-chart/1min` | Premium | 04:00-20:00 ET | 1m for 1min；5m/15m/30m at bar close |
| US_OPTIONS_PREMIUM | `/historical-chain`, `/historical-volatility` | Premium；或继续用 Futu 替代 | 09:30-16:15 ET；16:15-17:30 ET 补扫 | 1m live；15m EOD |
| US_FILINGS_TRANSCRIPTS_PREMIUM | `/rss_feed`, `/earning_call_transcript`, `/earning_call_transcript-list` | Premium | 06:00-23:00 ET；财报季扩大 | 15m |
| US_ANALYST_13F_PREMIUM | `/analyst-stock-recommendations`, `/price-target`, `/upgrades-downgrades`, `/grade`, `/institutional-holder`, `/13F`, `/etf-holder`, `/institutional-symbol-ownership` | Premium | 06:00-22:00 ET | 60m；13F 窗口 daily |
| US_DCF_QUALITY_PREMIUM | `/levered-discounted-cash-flow`, `/historical-discounted-cash-flow-statement`, `/financial-score`, `/owner_earnings`, `/market_risk_premium`, `/mergers-acquisitions`, `/executive-compensation`, `/insider-roster`, `/insider-trades-statistics` | Premium | 06:30、17:30 ET | daily |
| US_ALT_ULTIMATE | `/esg-environmental-social-governance-data`, `/esg-environmental-social-governance-ratings`, `/senate-trading`, `/senate-disclosure`, `/house-disclosure` | Ultimate | 06:00-22:00 ET | 60m for government trades；ESG daily/weekly |

## Futu OpenD 可用接口调度

按 `docs/data_sources/futu_endpoints.csv` 中 `covered` + `operational` 统计，当前可用/运维映射 39 条。实际权限仍以 `get_global_state`、`query_subscription` 和每次 SDK 返回码为准。

| 调度桶 | 接口 | 数据性质 | 更新时间段 | 频率 |
|---|---|---|---|---:|
| FUTU_OPS | `get_global_state`, `get_market_state`, `query_subscription`, `request_history_kline_quota`, `get_rt_data_quota` | OpenD 状态、市场状态、配额 | 交易日全时段；调度启动和异常后立即执行 | live 1m；off-hours 15m |
| FUTU_HK_US_SNAPSHOT | `get_market_snapshot`, `get_cur_kline`, `get_rt_data` | 港/美快照、当前 K、分时 | 港股 09:00-16:10 HKT；美股 04:00-20:00 ET；overnight 20:00-04:00 ET 仅权限可用时 | 1m |
| FUTU_TICK_L2_PUSH | `get_rt_ticker`, `get_ticker`, `get_order_book`, `subscribe`, `unsubscribe`, `set_handler` | 逐笔、L2、订阅推送 | 港股 09:00-16:10 HKT；美股 04:00-20:00 ET；overnight 对 quote only | 秒级输入聚合为 1m |
| FUTU_HK_BROKER_QUEUE | `get_broker_queue` | 港股经纪队列 | 港股 09:00-16:10 HKT | 1m；当前账号若无 LV2 则跳过 |
| FUTU_CAPITAL_FLOW | `get_capital_flow`, `get_capital_distribution` | 个股资金流、资金分布 | 对应市场交易时段；港股 CAS 后补到 16:30 HKT；美股 extended 到 20:00 ET | 1m live；5m extended |
| FUTU_HISTORY_KLINE | `request_history_kline`, `get_history_kl` | 历史 K 线 / EOD 补数 | 港股 16:10-18:30 HKT；美股 16:05-20:30 ET；A 股如有权限 15:05-18:30 CST | 15m 到当日 bar 出现；backfill daily |
| FUTU_OPTIONS | `get_option_chain`, `get_option_expiration_date`, `get_option_condition_filter` | 期权链、到期日、筛选 | 美股期权 09:30-16:15 ET；16:15-17:30 ET 补扫 | 链/报价 1m；到期日 daily |
| FUTU_WARRANTS | `get_warrant`, `get_reference` | 港股窝轮、牛熊证、正股关联 | 港股 09:00-16:10 HKT | 1m for quote-sensitive；reference daily |
| FUTU_INDEX_FUTURES | `get_future_info`, `get_future_kline` | 指数期货合约和 K 线 | 以 `get_market_state` 的 futures 状态为准 | open 1m；closed 15m；合约信息 daily |
| FUTU_REFERENCE | `get_security_info`, `get_stock_basicinfo`, `get_owner_plate`, `get_plate_security`, `get_plate_list`, `get_holding_change_list`, `get_ipo_list`, `request_trading_days` | 标的资料、板块、持仓变动、IPO、交易日 | 06:30、18:30 market local；IPO/持仓事件 16:00-22:00 | daily；事件 60m |

## 复核结论

1. 当前 collector 的 `--source real` 默认每 60 秒跑一轮，但 Tushare 和 FMP 的财报/EOD 接口不应长期按分钟重拉；建议拆成 live/EOD/event/quarterly 四类调度。
2. A 股“盘前/盘后”高频窗口应覆盖 09:15-15:30 CST，但当前代码没有真正 A 股分钟价源。当前 Tushare `daily_basic`、`moneyflow` 等只能作为 EOD 或准 EOD 源。
3. 港股 Futu live 窗口应覆盖 09:00-16:10 HKT，CAS 的随机收盘要留 2 分钟缓冲。
4. 美股 live 窗口应至少覆盖 04:00-20:00 ET；Futu overnight 单独按权限开启，FMP Starter 不应假设 overnight 可用。
5. `hk_hold` 当前日频持股在代码中已有 cutoff：2024-08-20 后不再按当前日 daily fresh 处理，应改为历史补数/季度披露口径。
6. 已补齐本轮复核发现的 catalog/code 口径差异：Tushare `top_list` / `top10_holders` / 财报三表和 FMP `/ratios-ttm`、`/stable/treasury-rates`、`/stable/economic-calendar` 都已在对应 CSV 中使用当前代码口径。

## 参考来源

- 本仓库：`scripts/collector.py`、`mvp20/sources/tushare_source.py`、`mvp20/sources/fmp_source.py`、`mvp20/sources/futu_source.py`、`upstream/data-platform/src/data_platform/adapters/tushare/assets.py`、`docs/data_sources/{tushare,fmp,futu}_endpoints.csv`。
- A 股时段：上海证券交易所“股票投资”页面列明 09:15-09:25、09:30-11:30、13:00-14:57、14:57-15:00，以及科创板 15:05-15:30 盘后固定价格交易；深交所交易概览/投资者问答列明同类竞价与 15:05-15:30 盘后定价/大宗窗口。
- 港股时段：HKEX Securities Market Trading Hours，POS 09:00-09:30、CTS 09:30-12:00 / 13:00-16:00、CAS 16:00 至随机 16:08-16:10。
- 美股时段：Nasdaq market/system hours 当前列明 market 09:30-16:00 ET、system 04:00-20:00 ET；NYSE extended-hours 页面列明当前 early 04:00-09:30、core 09:30-16:00、late 16:00-20:00，并披露未来 extended early 方案。
- Futu OpenAPI：Quotation Definitions 中有 US pre-market、after-hours、night market 状态和 `Session_ALL` / `OVERNIGHT` 定义。
