# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T04:32:46+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `316.698` seconds
- CSV files scanned: `1000`
- Rows scanned: `1343582`
- Header signatures: `1`
- Header read errors: `0`
- Row read errors: `0`
- Full row semantic scan: `False`

## Coverage Boundary

| Boundary | Value |
|---|---:|
| `all_business_csv_files_selected` | `False` |
| `all_selected_files_read_to_eof` | `True` |
| `full_row_semantic_scan` | `False` |
| `max_files_limit` | `1000` |
| `skip_files` | `99009` |

## Issue Counts

- `sparse_columns_lt_5pct_non_empty`: 125
- `stale_primary_market_date_gt_45d`: 1000

## Domain Issue Counts

- No domain-invariant issues detected.

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002450.SZ+康得退(退).csv` | 30 | 5 | sparse_columns_lt_5pct_non_empty=4, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002604.SZ+龙力退(退).csv` | 30 | 5 | sparse_columns_lt_5pct_non_empty=4, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300169.SZ+天晟新材.csv` | 1458 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300189.SZ+神农种业.csv` | 1460 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002359.SZ+北讯退(退).csv` | 118 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300264.SZ+佳创视讯.csv` | 1463 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300268.SZ+_ST佳沃.csv` | 1465 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300301.SZ+ST长方.csv` | 1457 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002447.SZ+晨鑫退(退).csv` | 551 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002509.SZ+天茂退(退).csv` | 87 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002711.SZ+欧浦退(退).csv` | 82 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300157.SZ+新锦动力.csv` | 1467 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300204.SZ+舒泰神.csv` | 1468 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300370.SZ+安控科技.csv` | 1464 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300469.SZ+信息发展.csv` | 1464 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002473.SZ+圣莱退(退).csv` | 550 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300528.SZ+幸福蓝海.csv` | 1468 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002504.SZ+_ST弘高(退).csv` | 806 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002619.SZ+_ST艾格(退).csv` | 512 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300134.SZ+大富科技.csv` | 1468 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `d20d0849c1ca675fca5c0a55123c8c09929f85fae897cc7f86786c2775cb096f` | 1000 | 1343582 | sparse_columns_lt_5pct_non_empty=125, stale_primary_market_date_gt_45d=1000 |
