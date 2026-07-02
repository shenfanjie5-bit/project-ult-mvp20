# DOCKCASE CSV stratified semantic audit

- Generated: `2026-06-18T22:10:18+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `header_signature_stratified_bounded_row_semantics`
- Elapsed: `43.025` seconds
- Sample strategy: `head_tail`
- As-of date: `2026-06-18`
- CSV files seen: `160567`
- Files grouped by signature: `160567`
- Header signatures: `187`
- Selected signatures: `187`
- Sampled signatures: `184`
- Selected files: `332`
- Sampled files / rows: `329` / `25205`
- Header read errors: `0`

## Sampling Coverage

| Metric | Value |
|---|---:|
| Sampled signature ratio | `0.984` |
| Selected file ratio of grouped CSV | `0.0021` |
| Sampled file ratio of grouped CSV | `0.002` |
| Sampled rows per sampled file | `76.61` |

| Coverage gap | Count |
|---|---:|
| Header-read error files | `0` |
| Unsampled signatures | `3` |
| Signatures selected but no sampled rows | `3` |
| CSV files not selected for row sampling | `160235` |
| CSV files selected but no sampled rows | `3` |

## Issue Counts

- `duplicate_grain_key_sample`: 326
- `future_primary_date_gt_7d`: 4
- `high_empty_cell_ratio_signature`: 3
- `index_by_symbol_bundle_mismatch`: 900
- `invalid_date`: 121
- `invalid_numeric`: 30
- `invalid_ts_code`: 317
- `no_sampled_rows`: 3
- `ohlc_invariant_violation`: 3
- `sparse_columns_lt_5pct_non_empty`: 230
- `stale_primary_market_date_gt_45d`: 70
- `zero_ohlc_no_trade_carry_forward`: 2

## Domain Issue Counts

- `duplicate_grain_key_sample`: 326
- `index_by_symbol_bundle_mismatch`: 900
- `ohlc_invariant_violation`: 3
- `zero_ohlc_no_trade_carry_forward`: 2

## Largest Header Signatures

| Rank | Files | Sampled rows | Empty cell ratio | Issues | Columns | Example |
|---:|---:|---:|---:|---|---|---|
| 1 | 17738 | 196 | 0.2000 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 | ts_code, trade_date, fd_share, fund_type, market | `公募基金/基金规模/by_symbol/000003.OF+中海可转换债券A.csv` |
| 2 | 13656 | 300 | 0.0909 | sparse_columns_lt_5pct_non_empty=1 | l1_code, l1_name, l2_code, l2_name, l3_code, l3_name, ts_code, name, ... | `指数专题/申万行业成分（分级）/by_symbol/000008.CJ+信息技术与硬件(长江).csv` |
| 3 | 11827 | 300 | 0.0000 | stale_primary_market_date_gt_45d=1 | ts_code, trade_date, close, open, high, low, pre_close, change, ... | `股票数据/行情数据/周线行情/by_symbol/000004.SZ+_ST国华.csv` |
| 4 | 5833 | 300 | 0.0000 | - | ts_code, trade_date, open, high, low, close, pre_close, change, ... | `股票数据/行情数据/历史日线/by_symbol/000001.SZ+平安银行.csv` |
| 5 | 5816 | 142 | 0.0935 | - | ts_code, trade_date, close, turnover_rate, turnover_rate_f, volume_ratio, pe, pe_ttm, ... | `股票数据/行情数据/每日指标/by_symbol/600519.SH+贵州茅台.csv` |
| 6 | 5800 | 300 | 0.0000 | stale_primary_market_date_gt_45d=1 | trade_date, ts_code, name, pct_change, close, net_amount, net_amount_rate, buy_elg_amount, ... | `股票数据/资金流向数据/个股资金流向（DC）/by_symbol/600631.SH+百联股份(已合并)(退).csv` |
| 7 | 5787 | 112 | 0.5773 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=31 | ts_code, ann_date, f_ann_date, end_date, report_type, comp_type, end_type, basic_eps, ... | `股票数据/财务数据/利润表/by_symbol/688783.SH+西安奕材-U.csv` |
| 8 | 5765 | 144 | 0.1401 | - | ts_code, ann_date, end_date, eps, dt_eps, total_revenue_ps, revenue_ps, capital_rese_ps, ... | `股票数据/财务数据/财务指标数据/by_symbol/000002.SZ+万科Ａ.csv` |
| 9 | 5764 | 52 | 0.6145 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=75 | ts_code, ann_date, f_ann_date, end_date, report_type, comp_type, end_type, total_share, ... | `股票数据/财务数据/资产负债表/by_symbol/000063.SZ+中兴通讯.csv` |
| 10 | 5757 | 133 | 0.4809 | sparse_columns_lt_5pct_non_empty=30 | ts_code, ann_date, f_ann_date, end_date, comp_type, report_type, end_type, net_profit, ... | `股票数据/财务数据/现金流量表/by_symbol/688256.SH+寒武纪-U.csv` |
| 11 | 5741 | 145 | 0.1000 | - | ts_code, end_date, bz_item, bz_code, bz_sales, bz_profit, bz_cost, curr_type | `股票数据/财务数据/主营业务构成/by_symbol/300502.SZ+新易盛.csv` |
| 12 | 5702 | 300 | 0.1542 | stale_primary_market_date_gt_45d=1 | ts_code, trade_date, open, open_hfq, open_qfq, high, high_hfq, high_qfq, ... | `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000001.SZ+平安银行.csv` |
| 13 | 5687 | 62 | 0.1161 | - | ts_code, ann_date, end_date, pre_date, actual_date | `股票数据/财务数据/财报披露日期表/by_symbol/000002.SZ+万科Ａ.csv` |
| 14 | 5605 | 300 | 0.0190 | - | ts_code, trade_date, buy_sm_vol, buy_sm_amount, sell_sm_vol, sell_sm_amount, buy_md_vol, buy_md_amount, ... | `股票数据/资金流向数据/个股资金流向/by_symbol/000001.SZ+平安银行.csv` |
| 15 | 5600 | 65 | 0.3242 | - | ts_code, end_date, ann_date, div_proc, stk_div, stk_bo_rate, stk_co_rate, cash_div, ... | `股票数据/财务数据/分红送股数据/by_symbol/688256.SH+寒武纪-U.csv` |
| 16 | 5514 | 300 | 0.0000 | stale_primary_market_date_gt_45d=1 | ts_code, trade_date, his_low, his_high, cost_5pct, cost_15pct, cost_50pct, cost_85pct, ... | `股票数据/特色数据/每日筹码及胜率/by_symbol/000006.SZ+深振业Ａ.csv` |
| 17 | 5484 | 23 | 0.3645 | - | ts_code, ann_date, end_date, type, p_change_min, p_change_max, net_profit_min, net_profit_max, ... | `股票数据/财务数据/业绩预告/by_symbol/301666.SZ+大普微-UW.csv` |
| 18 | 5444 | 89 | 0.1509 | - | ts_code, ann_date, end_date, audit_result, audit_fees, audit_agency, audit_sign | `股票数据/财务数据/财务审计意见/by_symbol/000002.SZ+万科Ａ.csv` |
| 19 | 5224 | 300 | 0.0000 | stale_primary_market_date_gt_45d=1 | trade_date, ts_code, name, pct_change, latest, net_amount, net_d5_amount, buy_lg_amount, ... | `股票数据/资金流向数据/个股资金流向（THS）/by_symbol/000006.SZ+深振业Ａ.csv` |
| 20 | 4864 | 53 | 0.0720 | duplicate_grain_key_sample=1 | ts_code, ann_date, holder_name, holder_type, in_de, change_vol, change_ratio, after_share, ... | `股票数据/参考数据/股东增减持/by_symbol/000001.SZ+平安银行.csv` |
| 21 | 4670 | 105 | 0.2499 | sparse_columns_lt_5pct_non_empty=1 | ts_code, name, report_date, report_title, report_type, classify, org_name, author_name, ... | `股票数据/特色数据/券商盈利预测数据/by_symbol/600584.SH+长电科技.csv` |
| 22 | 4529 | 300 | 0.0000 | stale_primary_market_date_gt_45d=1 | index_code, con_code, trade_date, weight | `指数专题/指数成分和权重/by_symbol/000003.SH+B股指数.csv` |
| 23 | 3761 | 24 | 0.1417 | sparse_columns_lt_5pct_non_empty=2 | ts_code, ann_date, end_date, revenue, operate_profit, total_profit, n_income, total_assets, ... | `股票数据/财务数据/业绩快报/by_symbol/600452.SH+涪陵电力.csv` |
| 24 | 3404 | 300 | 0.0000 | stale_primary_market_date_gt_45d=1 | ts_code, trade_date, price, percent | `股票数据/特色数据/每日筹码分布/by_symbol/000002.SZ+万科Ａ.csv` |
| 25 | 3208 | 300 | 0.0000 | stale_primary_market_date_gt_45d=1 | ts_code, trade_date, open, high, low, close, pre_close, change, ... | `指数专题/指数技术面因子(专业版)/by_symbol/000001.SH+上证指数.csv` |
| 26 | 236 | 300 | 0.0000 | stale_primary_market_date_gt_45d=1 | ts_code, trade_date, close, open, high, low, vol, amount, ... | `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000002.SZ+万科Ａ.csv` |
| 27 | 192 | 300 | 0.0020 | index_by_symbol_bundle_mismatch=300, stale_primary_market_date_gt_45d=1 | ts_code, trade_date, name, open, low, high, close, change, ... | `指数专题/申万行业指数日行情/by_symbol/114701.MI+MSCI中国_食品饮料与烟草.csv` |
| 28 | 164 | 208 | 0.0000 | - | ts_code, ann_date, end_date, holder_num | `股票数据/参考数据/股东人数/by_symbol/000003.SZ+PT金田A(退).csv` |
| 29 | 144 | 300 | 0.0619 | stale_primary_market_date_gt_45d=1, zero_ohlc_no_trade_carry_forward=2 | ts_code, trade_date, name, pct_change, close, change, open, high, ... | `股票数据/行情数据/备用行情/by_symbol/000002.SZ+万科Ａ.csv` |
| 30 | 139 | 300 | 0.0000 | - | ts_code, end_date, name, ind_name, ind_value | `港股数据/港股利润表/by_symbol/00003.HK+香港中华煤气.csv` |

## Highest-Issue Signatures

- Rank 1, files 17738, sampled rows 196: sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1; example `公募基金/基金规模/by_symbol/000003.OF+中海可转换债券A.csv`
- Rank 2, files 13656, sampled rows 300: sparse_columns_lt_5pct_non_empty=1; example `指数专题/申万行业成分（分级）/by_symbol/000008.CJ+信息技术与硬件(长江).csv`
- Rank 3, files 11827, sampled rows 300: stale_primary_market_date_gt_45d=1; example `股票数据/行情数据/周线行情/by_symbol/000004.SZ+_ST国华.csv`
- Rank 6, files 5800, sampled rows 300: stale_primary_market_date_gt_45d=1; example `股票数据/资金流向数据/个股资金流向（DC）/by_symbol/600631.SH+百联股份(已合并)(退).csv`
- Rank 7, files 5787, sampled rows 112: high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=31; example `股票数据/财务数据/利润表/by_symbol/688783.SH+西安奕材-U.csv`
- Rank 9, files 5764, sampled rows 52: high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=75; example `股票数据/财务数据/资产负债表/by_symbol/000063.SZ+中兴通讯.csv`
- Rank 10, files 5757, sampled rows 133: sparse_columns_lt_5pct_non_empty=30; example `股票数据/财务数据/现金流量表/by_symbol/688256.SH+寒武纪-U.csv`
- Rank 12, files 5702, sampled rows 300: stale_primary_market_date_gt_45d=1; example `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000001.SZ+平安银行.csv`
- Rank 16, files 5514, sampled rows 300: stale_primary_market_date_gt_45d=1; example `股票数据/特色数据/每日筹码及胜率/by_symbol/000006.SZ+深振业Ａ.csv`
- Rank 19, files 5224, sampled rows 300: stale_primary_market_date_gt_45d=1; example `股票数据/资金流向数据/个股资金流向（THS）/by_symbol/000006.SZ+深振业Ａ.csv`
- Rank 20, files 4864, sampled rows 53: duplicate_grain_key_sample=1; example `股票数据/参考数据/股东增减持/by_symbol/000001.SZ+平安银行.csv`
- Rank 21, files 4670, sampled rows 105: sparse_columns_lt_5pct_non_empty=1; example `股票数据/特色数据/券商盈利预测数据/by_symbol/600584.SH+长电科技.csv`
- Rank 22, files 4529, sampled rows 300: stale_primary_market_date_gt_45d=1; example `指数专题/指数成分和权重/by_symbol/000003.SH+B股指数.csv`
- Rank 23, files 3761, sampled rows 24: sparse_columns_lt_5pct_non_empty=2; example `股票数据/财务数据/业绩快报/by_symbol/600452.SH+涪陵电力.csv`
- Rank 24, files 3404, sampled rows 300: stale_primary_market_date_gt_45d=1; example `股票数据/特色数据/每日筹码分布/by_symbol/000002.SZ+万科Ａ.csv`
- Rank 25, files 3208, sampled rows 300: stale_primary_market_date_gt_45d=1; example `指数专题/指数技术面因子(专业版)/by_symbol/000001.SH+上证指数.csv`
- Rank 26, files 236, sampled rows 300: stale_primary_market_date_gt_45d=1; example `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000002.SZ+万科Ａ.csv`
- Rank 27, files 192, sampled rows 300: index_by_symbol_bundle_mismatch=300, stale_primary_market_date_gt_45d=1; example `指数专题/申万行业指数日行情/by_symbol/114701.MI+MSCI中国_食品饮料与烟草.csv`
- Rank 29, files 144, sampled rows 300: stale_primary_market_date_gt_45d=1, zero_ohlc_no_trade_carry_forward=2; example `股票数据/行情数据/备用行情/by_symbol/000002.SZ+万科Ａ.csv`
- Rank 31, files 132, sampled rows 300: index_by_symbol_bundle_mismatch=300, stale_primary_market_date_gt_45d=1; example `指数专题/中信行业指数日行情/by_symbol/106507.MI+MSCI欧盟(除德国).csv`

## Largest Sampling-Limited Signatures

- Rank 1, files 17738, selected 3, sampled files 3, sampled rows 196, unselected 17735; example `公募基金/基金规模/by_symbol/000003.OF+中海可转换债券A.csv`
- Rank 2, files 13656, selected 3, sampled files 3, sampled rows 300, unselected 13653; example `指数专题/申万行业成分（分级）/by_symbol/000008.CJ+信息技术与硬件(长江).csv`
- Rank 3, files 11827, selected 3, sampled files 3, sampled rows 300, unselected 11824; example `股票数据/行情数据/周线行情/by_symbol/000004.SZ+_ST国华.csv`
- Rank 4, files 5833, selected 3, sampled files 3, sampled rows 300, unselected 5830; example `股票数据/行情数据/历史日线/by_symbol/000001.SZ+平安银行.csv`
- Rank 5, files 5816, selected 3, sampled files 3, sampled rows 142, unselected 5813; example `股票数据/行情数据/每日指标/by_symbol/600519.SH+贵州茅台.csv`
- Rank 6, files 5800, selected 3, sampled files 3, sampled rows 300, unselected 5797; example `股票数据/资金流向数据/个股资金流向（DC）/by_symbol/600631.SH+百联股份(已合并)(退).csv`
- Rank 7, files 5787, selected 3, sampled files 3, sampled rows 112, unselected 5784; example `股票数据/财务数据/利润表/by_symbol/688783.SH+西安奕材-U.csv`
- Rank 8, files 5765, selected 3, sampled files 3, sampled rows 144, unselected 5762; example `股票数据/财务数据/财务指标数据/by_symbol/000002.SZ+万科Ａ.csv`
- Rank 9, files 5764, selected 3, sampled files 3, sampled rows 52, unselected 5761; example `股票数据/财务数据/资产负债表/by_symbol/000063.SZ+中兴通讯.csv`
- Rank 10, files 5757, selected 3, sampled files 3, sampled rows 133, unselected 5754; example `股票数据/财务数据/现金流量表/by_symbol/688256.SH+寒武纪-U.csv`
- Rank 11, files 5741, selected 3, sampled files 3, sampled rows 145, unselected 5738; example `股票数据/财务数据/主营业务构成/by_symbol/300502.SZ+新易盛.csv`
- Rank 12, files 5702, selected 3, sampled files 3, sampled rows 300, unselected 5699; example `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000001.SZ+平安银行.csv`
- Rank 13, files 5687, selected 3, sampled files 3, sampled rows 62, unselected 5684; example `股票数据/财务数据/财报披露日期表/by_symbol/000002.SZ+万科Ａ.csv`
- Rank 14, files 5605, selected 3, sampled files 3, sampled rows 300, unselected 5602; example `股票数据/资金流向数据/个股资金流向/by_symbol/000001.SZ+平安银行.csv`
- Rank 15, files 5600, selected 3, sampled files 3, sampled rows 65, unselected 5597; example `股票数据/财务数据/分红送股数据/by_symbol/688256.SH+寒武纪-U.csv`
- Rank 16, files 5514, selected 3, sampled files 3, sampled rows 300, unselected 5511; example `股票数据/特色数据/每日筹码及胜率/by_symbol/000006.SZ+深振业Ａ.csv`
- Rank 17, files 5484, selected 3, sampled files 3, sampled rows 23, unselected 5481; example `股票数据/财务数据/业绩预告/by_symbol/301666.SZ+大普微-UW.csv`
- Rank 18, files 5444, selected 3, sampled files 3, sampled rows 89, unselected 5441; example `股票数据/财务数据/财务审计意见/by_symbol/000002.SZ+万科Ａ.csv`
- Rank 19, files 5224, selected 3, sampled files 3, sampled rows 300, unselected 5221; example `股票数据/资金流向数据/个股资金流向（THS）/by_symbol/000006.SZ+深振业Ａ.csv`
- Rank 20, files 4864, selected 3, sampled files 3, sampled rows 53, unselected 4861; example `股票数据/参考数据/股东增减持/by_symbol/000001.SZ+平安银行.csv`

## Signatures Without Sampled Rows

- Rank 121, files 1, selected 1, sampled files 0; example `_workspace/_meta/manifests/master_dictionary_index.csv`
- Rank 124, files 1, selected 1, sampled files 0; example `_workspace/_meta/exports/curated_sample_20260310_60d_20stocks/tables/dim_us_security.csv`
- Rank 128, files 1, selected 1, sampled files 0; example `_workspace/_meta/exports/curated_sample_20260310_60d_20stocks/tables/fact_overseas_financial_indicator.csv`

## Interpretation

This audit is stronger than first-row cataloging because it samples real rows from each header signature and now records the file/signature sampling boundary explicitly. It is still bounded evidence: it does not read every CSV row and high sparsity can be normal for some vendor tables.
