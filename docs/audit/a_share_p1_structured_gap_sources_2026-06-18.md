# A-share P1 structured gap source audit

Generated: `2026-06-18`

This note narrows the wider A-share score gap report to the fields previously
classified as `P1_add_tushare_or_structured_collector`.

## Result

The A-share P1 set is now **0 remaining structured-collector fields plus 0
runtime-refresh fields**, not 6. The three option-chain fields were reclassified
to governance/design review because the current production code intentionally
skips A-share single-stock option rows and must not fabricate IV or call/put
ratios from unrelated instruments. `L5.surprise.preprice` was refreshed through
`tushare-preprice` on 2026-06-18 and now has A-share runtime rows.
`L10.industry.inventory_orders` and `L10.industry.sales_price` were refreshed
through `tushare-macro` on 2026-06-18 and now have industry sentinel `Proxy`
rows in `runtime/hot.sqlite`.

| dp_id | Current route | Evidence | Next implementation step |
|---|---|---|---|
| `L5.surprise.preprice` | `resolved_runtime_direct` | DOCKCASE/Tushare has A-share `forecast` rows with `ann_date`, `end_date`, `p_change_min`, `p_change_max`; it also has stock daily bars for price-window calculation. Code derives the A-share payload in `mvp20/sources/tushare_source.py` from `forecast + daily` and maps it to `expectation_gap` in `mvp20/aggregator.py`. Runtime now has 39 A-share `Known` rows and 1,602 explicit `Inactive` rows from `tushare:forecast+daily.derived`. | Keep monitored by score trace; no P1 collector action remains. |
| `L10.industry.inventory_orders` | `resolved_runtime_proxy` | DOCKCASE/Tushare PMI rows include manufacturing PMI subindices for production, new orders, backlog, finished-goods inventory, and raw-material inventory. Code emits `INDUSTRY:<id>` `Proxy` confidence-validation rows from `cn_pmi` only for semantically relevant manufacturing / hardware / cyclical industries. Runtime now has 8 `Proxy` rows from `tushare:cn_pmi.industry_validation`. | Keep monitored by score trace; no P1 collector action remains unless the industry whitelist changes. |
| `L10.industry.sales_price` | `resolved_runtime_proxy` | DOCKCASE/Tushare CPI/PPI rows include producer, means-of-production, raw-material, consumer-goods, durable-goods, and CPI price fields. Code emits `INDUSTRY:<id>` `Proxy` confidence-validation rows from national `cn_ppi + cn_cpi`; this is a macro price proxy, not industry ASP or sales-volume observation. Runtime now has 10 `Proxy` rows from `tushare:cn_ppi+cn_cpi.industry_validation`. | Keep monitored by score trace; no P1 collector action remains unless the industry whitelist changes. |
| `L6.priced.iv` | `a_share_listed_options_or_na_required` | `mvp20.sources.futu_source.fetch_l6_priced_iv` filters to `.HK` / `.US`; tests assert A-share rows are skipped. | Only populate for a legitimate listed-option universe or licensed A-share option mapping; otherwise emit/keep N/A or Unavailable. |
| `L7.trade.iv` | `a_share_listed_options_or_na_required` | Same Futu option-chain path filters to `.HK` / `.US`; A-share rows have no broad single-stock IV source in this repo. | Do not proxy from turnover, sentiment, or index IV without explicit governance. |
| `L7.trade.options_cp` | `a_share_listed_options_or_na_required` | Futu option-chain call/put ratio is implemented for HK/US only; A-share single-stock call/put ratios are not broad runtime coverage. | Require real option-chain volume/OI or keep out of scoring. |

## Checked Evidence

- `runtime/hot.sqlite` now has 1,641 refreshed A-share
  `L5.surprise.preprice` rows under `.SH` / `.SZ` / `.BJ` tickers:
  39 `Known` and 1,602 explicit `Inactive`.
- `runtime/hot.sqlite` now has 18 refreshed `INDUSTRY:<id>` `Proxy` rows for
  the two L10 validation fields.
- Non-A runtime rows exist for `L5.surprise.preprice` (`fmp:earnings.derived`)
  and the three option-chain fields (`futu:option_chain` /
  `futu:option_chain.cp`), so the field model exists but is not A-share
  coverage.
- DOCKCASE source samples:
  - `股票数据/财务数据/业绩预告/by_symbol/000001.SZ+平安银行.csv`
  - `股票数据/行情数据/历史日线/by_symbol/000001.SZ+平安银行.csv`
  - `股票数据/行情数据/每日指标/by_symbol/000001.SZ+平安银行.csv`
  - `指数专题/申万行业指数日行情/by_symbol/000002.SH+A股指数.csv`
  - `指数专题/指数技术面因子(专业版)/by_symbol/000002.SH+A股指数.csv`
  - `宏观经济/国内宏观/景气度/采购经理指数（PMI）/all.csv`
  - `宏观经济/国内宏观/价格指数/工业生产者出厂价格指数（PPI）/all.csv`

## Current Counts

| Participating gap bucket | Count |
|---|---:|
| `P1_add_tushare_or_structured_collector` | 0 |
| `P1_refresh_runtime_data` | 0 |
| `P2_llm_or_web_extraction` | 29 |
| `P2_low_coverage_formula` | 11 |
| `P3_governance_or_design_review` | 21 |
| `P3_manual_review` | 5 |
