# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T04:47:38+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `248.693` seconds
- CSV files scanned: `1032`
- Rows scanned: `1022382`
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
| `max_files_limit` | `1032` |
| `skip_files` | `102009` |

## Issue Counts

- `high_empty_cell_ratio_signature`: 2
- `sparse_columns_lt_5pct_non_empty`: 2560
- `stale_primary_market_date_gt_45d`: 1032

## Domain Issue Counts

- No domain-invariant issues detected.

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/688816.SH+C易思.csv` | 12 | 61 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=59, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/920166.BJ+N海圣.csv` | 11 | 61 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=59, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/688818.SH+C电科.csv` | 13 | 57 | sparse_columns_lt_5pct_non_empty=56, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/920180.BJ+爱得科技.csv` | 13 | 57 | sparse_columns_lt_5pct_non_empty=56, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/688712.SH+北芯生命-U.csv` | 16 | 40 | sparse_columns_lt_5pct_non_empty=39, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/688785.SH+恒运昌.csv` | 22 | 39 | sparse_columns_lt_5pct_non_empty=38, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/920159.BJ+农大科技.csv` | 22 | 39 | sparse_columns_lt_5pct_non_empty=38, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/920050.BJ+爱舍伦.csv` | 27 | 33 | sparse_columns_lt_5pct_non_empty=32, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/920076.BJ+国亮新材.csv` | 26 | 33 | sparse_columns_lt_5pct_non_empty=32, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/920119.BJ+美德乐.csv` | 20 | 33 | sparse_columns_lt_5pct_non_empty=32, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/920086.BJ+科马材料.csv` | 30 | 24 | sparse_columns_lt_5pct_non_empty=23, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/688809.SH+强一股份.csv` | 41 | 18 | sparse_columns_lt_5pct_non_empty=17, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/920045.BJ+蘅东光.csv` | 40 | 18 | sparse_columns_lt_5pct_non_empty=17, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/920121.BJ+江天科技.csv` | 44 | 18 | sparse_columns_lt_5pct_non_empty=17, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/688790.SH+昂瑞微-UW.csv` | 51 | 17 | sparse_columns_lt_5pct_non_empty=16, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/688802.SH+沐曦股份-U.csv` | 50 | 17 | sparse_columns_lt_5pct_non_empty=16, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/832317.BJ+观典防务(退).csv` | 349 | 16 | sparse_columns_lt_5pct_non_empty=15, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/833874.BJ+泰祥股份(退).csv` | 354 | 16 | sparse_columns_lt_5pct_non_empty=15, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/833994.BJ+翰博高新(退).csv` | 354 | 16 | sparse_columns_lt_5pct_non_empty=15, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/688805.SH+健信超导.csv` | 45 | 15 | sparse_columns_lt_5pct_non_empty=14, stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `d20d0849c1ca675fca5c0a55123c8c09929f85fae897cc7f86786c2775cb096f` | 1032 | 1022382 | high_empty_cell_ratio_signature=2, sparse_columns_lt_5pct_non_empty=2560, stale_primary_market_date_gt_45d=1032 |
