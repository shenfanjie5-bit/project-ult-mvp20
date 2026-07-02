# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T04:24:57+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `344.425` seconds
- CSV files scanned: `1000`
- Rows scanned: `1440602`
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
| `skip_files` | `98009` |

## Issue Counts

- `sparse_columns_lt_5pct_non_empty`: 204
- `stale_primary_market_date_gt_45d`: 1000

## Domain Issue Counts

- No domain-invariant issues detected.

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/001285.SZ+瑞立科密.csv` | 93 | 6 | sparse_columns_lt_5pct_non_empty=5, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000939.SZ+凯迪退(退).csv` | 30 | 5 | sparse_columns_lt_5pct_non_empty=4, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002071.SZ+长城退(退).csv` | 265 | 5 | sparse_columns_lt_5pct_non_empty=4, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002173.SZ+创新医疗.csv` | 1468 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002348.SZ+高乐股份.csv` | 1461 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002147.SZ+新光退(退).csv` | 551 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002872.SZ+ST天圣.csv` | 1467 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002220.SZ+天宝退(退).csv` | 102 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300027.SZ+华谊兄弟.csv` | 1468 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300051.SZ+琏升科技.csv` | 1451 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002260.SZ+德奥退(退).csv` | 30 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300093.SZ+_ST金刚.csv` | 1466 | 4 | sparse_columns_lt_5pct_non_empty=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000918.SZ+_ST嘉凯(退).csv` | 795 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002309.SZ+中利集团.csv` | 1422 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002374.SZ+中锐股份.csv` | 1468 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002480.SZ+新筑股份.csv` | 1458 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002530.SZ+金财互联.csv` | 1463 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002547.SZ+春兴精工.csv` | 1468 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/002586.SZ+ST围海.csv` | 1464 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/300013.SZ+新宁物流.csv` | 1461 | 3 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `d20d0849c1ca675fca5c0a55123c8c09929f85fae897cc7f86786c2775cb096f` | 1000 | 1440602 | sparse_columns_lt_5pct_non_empty=204, stale_primary_market_date_gt_45d=1000 |
