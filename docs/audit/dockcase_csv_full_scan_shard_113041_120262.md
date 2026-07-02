# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T04:53:54+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `155.298` seconds
- CSV files scanned: `7222`
- Rows scanned: `11054154`
- Header signatures: `76`
- Header read errors: `0`
- Row read errors: `0`
- Full row semantic scan: `False`

## Coverage Boundary

| Boundary | Value |
|---|---:|
| `all_business_csv_files_selected` | `False` |
| `all_selected_files_read_to_eof` | `True` |
| `full_row_semantic_scan` | `False` |
| `max_files_limit` | `7222` |
| `skip_files` | `113041` |

## Issue Counts

- `duplicate_grain_key_sample`: 4668
- `future_primary_date_gt_7d`: 5
- `invalid_ts_code`: 2
- `no_sampled_rows`: 4
- `sparse_columns_lt_5pct_non_empty`: 57
- `stale_primary_market_date_gt_45d`: 7138

## Domain Issue Counts

- `duplicate_grain_key_sample`: 4668

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `_workspace/_meta/deliveries/formal_first_batch_20260311/cn_stock_daily_bar.csv` | 621730 | 1168 | duplicate_grain_key_sample=1167, stale_primary_market_date_gt_45d=1 |
| `_workspace/_meta/deliveries/formal_first_batch_20260311/cn_stock_daily_adjusted.csv` | 621730 | 1168 | duplicate_grain_key_sample=1167, stale_primary_market_date_gt_45d=1 |
| `_workspace/_meta/deliveries/formal_first_batch_v1.0-rc2/cn_stock_daily_bar.csv` | 621730 | 1168 | duplicate_grain_key_sample=1167, stale_primary_market_date_gt_45d=1 |
| `_workspace/_meta/deliveries/formal_first_batch_v1.0-rc2/cn_stock_daily_adjusted.csv` | 621730 | 1168 | duplicate_grain_key_sample=1167, stale_primary_market_date_gt_45d=1 |
| `股票数据/打板专题数据/榜单数据（开盘啦）/all.csv` | 106902 | 10 | sparse_columns_lt_5pct_non_empty=9, stale_primary_market_date_gt_45d=1 |
| `_workspace/_meta/analysis/complete_but_not_available_interfaces_20260428.csv` | 5 | 5 | sparse_columns_lt_5pct_non_empty=5 |
| `股票数据/打板专题数据/东方财富App热榜/all.csv` | 5700 | 4 | invalid_ts_code=1, sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `_workspace/_meta/analysis/api_download_completeness_audit_20260420.csv` | 235 | 4 | sparse_columns_lt_5pct_non_empty=4 |
| `_workspace/_meta/analysis/available_complete_interfaces_20260428.csv` | 138 | 4 | sparse_columns_lt_5pct_non_empty=4 |
| `_workspace/_meta/analysis/tushare_api_request_manifest_20260310.csv` | 227 | 4 | sparse_columns_lt_5pct_non_empty=4 |
| `_workspace/_meta/archive/analysis_cleanup_20260310/tushare_api_request_manifest_20260309.csv` | 227 | 3 | sparse_columns_lt_5pct_non_empty=3 |
| `_workspace/_meta/exports/curated_sample_20260310_60d_20stocks/tables/dim_theme_membership.csv` | 112 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `_workspace/_meta/analysis/tushare_api_catalog_20260309.csv` | 235 | 3 | sparse_columns_lt_5pct_non_empty=3 |
| `股票数据/打板专题数据/同花顺涨跌停榜单/all.csv` | 43430 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/打板专题数据/同花顺App热榜数/all.csv` | 1865 | 2 | invalid_ts_code=1, stale_primary_market_date_gt_45d=1 |
| `_workspace/tushare_doc2_leaf_api.csv` | 235 | 2 | sparse_columns_lt_5pct_non_empty=2 |
| `_workspace/_meta/analysis/api_download_completeness_problems_20260420.csv` | 92 | 2 | sparse_columns_lt_5pct_non_empty=2 |
| `股票数据/资金流向数据/个股资金流向（THS）/by_symbol/603050.SH+科林电气.csv` | 287 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/资金流向数据/个股资金流向（THS）/by_symbol/603051.SH+鹿山新材.csv` | 287 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/资金流向数据/个股资金流向（THS）/by_symbol/603052.SH+可川科技.csv` | 287 | 1 | stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `d8e7b4f9bd7824b9526b85463f4642b8afdffe4609c02317ec96cfa82115de7f` | 5800 | 3281266 | stale_primary_market_date_gt_45d=5800 |
| `f335d00113996279808bb09c59d1e2348931d607c224cd0eec76a6edebc53f57` | 1282 | 356620 | stale_primary_market_date_gt_45d=1282 |
| `c00a50db1789a41108a9c682898cc2237e9a38405143a6c2beb0294e127785cd` | 8 | 1273222 | duplicate_grain_key_sample=2334, stale_primary_market_date_gt_45d=8 |
| `6b79be19329d1a3132341d501b0161db1aa8523f932cadd1fb5734e6fa22726e` | 4 | 152 | - |
| `149ceff0c2efd27b07f83ac12bd4a79fcc43a9e6a899e1000e4fc714249232e2` | 4 | 470 | sparse_columns_lt_5pct_non_empty=15 |
| `037acbdca9fcf297b4ee33bf0512cc1ffe4c4fd297ea4411df335f68528f9f4f` | 4 | 11002 | - |
| `758f93ed59903d0d2b12c75c23c2d63e10d65c12c8a66523f2837d07ec18b257` | 4 | 52648 | future_primary_date_gt_7d=4 |
| `8083a4d637d512fcd54b0ddb0906b85ffea7addbd7dd67b5d2bcce512231e7dd` | 4 | 1436 | sparse_columns_lt_5pct_non_empty=4 |
| `c22439c20f97d19bfc769e5e89cb3f45b7fef411bc543969b8df6ae1b800fd8a` | 4 | 6024 | sparse_columns_lt_5pct_non_empty=4 |
| `e504f5928f4b0449ec589154b5899fe787a40461c90445aa53a2e13e3abd0f6b` | 4 | 6178 | - |
| `3b9893490b1ec1c09ff1467eaa4b1b518bb0b7f19090b5ce84a65eb9a736d0af` | 4 | 1246190 | duplicate_grain_key_sample=2334, stale_primary_market_date_gt_45d=4 |
| `3546f354c743f50f06826758cf6bf4823822afb2753d8b241eab57ce40b77558` | 4 | 1254802 | stale_primary_market_date_gt_45d=4 |
| `9b2dce55d0fab7658beb483af53a26db062afcec2db50e23b98ecc9c8c925e84` | 4 | 899900 | no_sampled_rows=1, stale_primary_market_date_gt_45d=3 |
| `90cd2c5e8a3680ef8c8c4aae0c1d09243b0f0e4bea75f7937040c68f43b0f07f` | 4 | 1744 | stale_primary_market_date_gt_45d=4 |
| `683816ba2f6d16e2435c0ef394d4af6649f25e2ea87e6f28ef69772310a5e4a2` | 4 | 18728 | stale_primary_market_date_gt_45d=4 |
| `d767ab21752fcb01d13a45099616dd68553dd8cc65c0fb3c76177dd8e8b222b0` | 4 | 77486 | - |
| `c30c167dba5ea99967368adcb7c736bb36ffa17ac77b56d339c8db291848ca45` | 4 | 77452 | - |
| `e215559a61529ec114e1bc5e9ccc8d7b0564199d9238f118e34c9ded87b30f9a` | 4 | 78172 | - |
| `fe175dad161b3198b154553f38670da26eeb821197f7b277290bf8f55a4d304f` | 4 | 21906 | - |
| `69f6360ee769d2c6f54a950aa26bcba6c6fe11bedd3711b65545efc7d35cab6f` | 2 | 201647 | - |
