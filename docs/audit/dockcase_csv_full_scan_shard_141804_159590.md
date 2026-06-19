# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T05:25:21+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `18.968` seconds
- CSV files scanned: `17787`
- Rows scanned: `349695`
- Header signatures: `3`
- Header read errors: `0`
- Row read errors: `0`
- Full row semantic scan: `False`

## Coverage Boundary

| Boundary | Value |
|---|---:|
| `all_business_csv_files_selected` | `False` |
| `all_selected_files_read_to_eof` | `True` |
| `full_row_semantic_scan` | `False` |
| `max_files_limit` | `17787` |
| `skip_files` | `141804` |

## Issue Counts

- `high_empty_cell_ratio_signature`: 3
- `sparse_columns_lt_5pct_non_empty`: 17841
- `stale_primary_market_date_gt_45d`: 17750

## Domain Issue Counts

- No domain-invariant issues detected.

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `公募基金/基金分红/by_symbol/000009.OF+易方达天天A.csv` | 2 | 10 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=9 |
| `公募基金/基金分红/by_symbol/000010.OF+易方达天天B.csv` | 2 | 10 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=9 |
| `公募基金/基金分红/by_symbol/000013.OF+易方达天天R.csv` | 2 | 10 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=9 |
| `公募基金/基金净值/by_symbol/000009.OF+易方达天天A.csv` | 3156 | 5 | sparse_columns_lt_5pct_non_empty=4, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金净值/by_symbol/000010.OF+易方达天天B.csv` | 3154 | 5 | sparse_columns_lt_5pct_non_empty=4, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金净值/by_symbol/000013.OF+易方达天天R.csv` | 3154 | 5 | sparse_columns_lt_5pct_non_empty=4, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金净值/by_symbol/000008.OF+嘉实中证500ETF联接A.csv` | 3128 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金净值/by_symbol/000004.OF+中海可转换债券C.csv` | 3134 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金净值/by_symbol/000001.OF+华夏成长.csv` | 5861 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金净值/by_symbol/000003.OF+中海可转换债券A.csv` | 3134 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金净值/by_symbol/000006.OF+西部利得量化成长A.csv` | 1691 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金净值/by_symbol/000011.OF+华夏大盘精选A.csv` | 5230 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金净值/by_symbol/000007.OF+鹏华国有企业债.csv` | 1300 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金净值/by_symbol/000014.OF+华夏聚利A.csv` | 2970 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金分红/by_symbol/000008.OF+嘉实中证500ETF联接A.csv` | 1 | 3 | sparse_columns_lt_5pct_non_empty=3 |
| `公募基金/基金分红/by_symbol/000026.OF+泰达宏利信用合利A.csv` | 4 | 3 | sparse_columns_lt_5pct_non_empty=3 |
| `公募基金/基金分红/by_symbol/000027.OF+泰达宏利信用合利B.csv` | 4 | 3 | sparse_columns_lt_5pct_non_empty=3 |
| `公募基金/基金分红/by_symbol/000037.OF+广发景宁纯债A.csv` | 2 | 3 | sparse_columns_lt_5pct_non_empty=3 |
| `公募基金/基金规模/by_symbol/000003.OF+中海可转换债券A.csv` | 50 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金规模/by_symbol/000001.OF+华夏成长.csv` | 96 | 2 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `12b19a2d5876b643cf2d5a94117bb17935a6abd1661f46031a59dc246fb7dfd8` | 17738 | 310348 | sparse_columns_lt_5pct_non_empty=17722, stale_primary_market_date_gt_45d=17738 |
| `410cba50e61bafce1521a1b8c8b1f361b9b1beaff4aa3de1e8e57f3134921d3e` | 37 | 262 | high_empty_cell_ratio_signature=3, sparse_columns_lt_5pct_non_empty=82 |
| `ac55385c9688426c6a541018371fc9788db126d2619c63d02d02fda41fd3afec` | 12 | 39085 | sparse_columns_lt_5pct_non_empty=37, stale_primary_market_date_gt_45d=12 |
