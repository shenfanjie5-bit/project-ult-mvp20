# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T04:09:07+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `170.578` seconds
- CSV files scanned: `3806`
- Rows scanned: `7735266`
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
| `max_files_limit` | `3806` |
| `skip_files` | `93600` |

## Issue Counts

- `duplicate_grain_key_sample`: 2444487
- `ohlc_invariant_violation`: 17
- `stale_primary_market_date_gt_45d`: 3806

## Domain Issue Counts

- `duplicate_grain_key_sample`: 2444487
- `ohlc_invariant_violation`: 17

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/特色数据/每日筹码分布/by_symbol/000627.SZ+_ST天茂(退).csv` | 184255 | 182967 | duplicate_grain_key_sample=182966, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/600225.SH+退市卓朗(退).csv` | 178396 | 177208 | duplicate_grain_key_sample=177207, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/600387.SH+退市海越(退).csv` | 169457 | 168184 | duplicate_grain_key_sample=168183, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/002336.SZ+人乐退(退).csv` | 166237 | 164967 | duplicate_grain_key_sample=164966, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/000851.SZ+_ST高鸿(退).csv` | 149728 | 148364 | duplicate_grain_key_sample=148363, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/000584.SZ+工智退(退).csv` | 147918 | 146655 | duplicate_grain_key_sample=146654, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/300379.SZ+东通退(退).csv` | 143123 | 141707 | duplicate_grain_key_sample=141706, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/300208.SZ+中程退(退).csv` | 135548 | 134271 | duplicate_grain_key_sample=134270, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/300280.SZ+紫天退(退).csv` | 132858 | 131612 | duplicate_grain_key_sample=131611, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/603003.SH+退市龙宇(退).csv` | 128109 | 126320 | duplicate_grain_key_sample=126319, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/600190.SH+退市锦港(退).csv` | 120818 | 119561 | duplicate_grain_key_sample=119560, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/600070.SH+_ST富润(退).csv` | 114504 | 113261 | duplicate_grain_key_sample=113260, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/300630.SZ+普利退(退).csv` | 113669 | 112463 | duplicate_grain_key_sample=112462, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/002750.SZ+龙津退(退).csv` | 109397 | 108124 | duplicate_grain_key_sample=108123, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/300344.SZ+_ST立方.csv` | 78245 | 76801 | duplicate_grain_key_sample=76800, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/300117.SZ+_ST嘉寓(退).csv` | 72323 | 71082 | duplicate_grain_key_sample=71081, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/000040.SZ+_ST旭蓝(退).csv` | 66431 | 65272 | duplicate_grain_key_sample=65271, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/000622.SZ+恒立退(退).csv` | 57239 | 55962 | duplicate_grain_key_sample=55961, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/300108.SZ+_ST吉药(退).csv` | 55020 | 53803 | duplicate_grain_key_sample=53802, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/每日筹码分布/by_symbol/600462.SH+退市九有(退).csv` | 50660 | 49395 | duplicate_grain_key_sample=49394, stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `11474a6fe3324d5ed30970e5b7485d897c7695ebc0542fb43d91b6e1716b5902` | 3404 | 7030651 | duplicate_grain_key_sample=2444487, stale_primary_market_date_gt_45d=3404 |
| `c3720fd7c652a69a62fda511b3c2d469b083a7ae03a53e6c24002dee7d61a281` | 335 | 250999 | stale_primary_market_date_gt_45d=335 |
| `d20d0849c1ca675fca5c0a55123c8c09929f85fae897cc7f86786c2775cb096f` | 67 | 453616 | ohlc_invariant_violation=17, stale_primary_market_date_gt_45d=67 |
