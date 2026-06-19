# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T04:16:18+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `82.661` seconds
- CSV files scanned: `100`
- Rows scanned: `337366`
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
| `max_files_limit` | `100` |
| `skip_files` | `97409` |

## Issue Counts

- `sparse_columns_lt_5pct_non_empty`: 20
- `stale_primary_market_date_gt_45d`: 100

## Domain Issue Counts

- No domain-invariant issues detected.

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000564.SZ+供销大集.csv` | 1458 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000571.SZ+新大洲A.csv` | 1466 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000409.SZ+云鼎科技.csv` | 6415 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000509.SZ+华塑控股.csv` | 1466 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000510.SZ+新金路.csv` | 1458 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000518.SZ+_ST四环.csv` | 1467 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000520.SZ+凤凰航运.csv` | 1468 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000526.SZ+学大教育.csv` | 1468 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000533.SZ+顺钠股份.csv` | 1468 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000536.SZ+华映科技.csv` | 1466 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000558.SZ+天府文旅.csv` | 1458 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000566.SZ+海南海药.csv` | 1468 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000405.SZ+ST鑫光(退).csv` | 1638 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000572.SZ+海马汽车.csv` | 1466 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000412.SZ+ST五环(退).csv` | 1627 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000586.SZ+汇源通信.csv` | 1458 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000159.SZ+国际实业.csv` | 5910 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000166.SZ+申万宏源.csv` | 2668 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000301.SZ+东方盛虹.csv` | 5950 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000333.SZ+美的集团.csv` | 2964 | 1 | stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `d20d0849c1ca675fca5c0a55123c8c09929f85fae897cc7f86786c2775cb096f` | 100 | 337366 | sparse_columns_lt_5pct_non_empty=20, stale_primary_market_date_gt_45d=100 |
