# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T04:51:11+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `201.57` seconds
- CSV files scanned: `10000`
- Rows scanned: `9502084`
- Header signatures: `11`
- Header read errors: `0`
- Row read errors: `0`
- Full row semantic scan: `False`

## Coverage Boundary

| Boundary | Value |
|---|---:|
| `all_business_csv_files_selected` | `False` |
| `all_selected_files_read_to_eof` | `True` |
| `full_row_semantic_scan` | `False` |
| `max_files_limit` | `10000` |
| `skip_files` | `103041` |

## Issue Counts

- `duplicate_grain_key_sample`: 34
- `ohlc_invariant_violation`: 85
- `sparse_columns_lt_5pct_non_empty`: 139
- `stale_primary_market_date_gt_45d`: 8383

## Domain Issue Counts

- `duplicate_grain_key_sample`: 34
- `ohlc_invariant_violation`: 85

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/两融及转融通/做市借券交易汇总(停）/all.csv` | 55214 | 36 | duplicate_grain_key_sample=34, sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000011.SZ+深物业A.csv` | 4169 | 12 | ohlc_invariant_violation=11, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000002.SZ+万科Ａ.csv` | 4166 | 11 | ohlc_invariant_violation=10, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000017.SZ+深中华A.csv` | 4169 | 11 | ohlc_invariant_violation=10, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000018.SZ+神城A退(退).csv` | 2678 | 7 | ohlc_invariant_violation=6, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000006.SZ+深振业Ａ.csv` | 4169 | 6 | ohlc_invariant_violation=5, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000010.SZ+美丽生态.csv` | 4169 | 6 | ohlc_invariant_violation=5, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000012.SZ+南玻Ａ.csv` | 4169 | 6 | ohlc_invariant_violation=5, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000001.SZ+平安银行.csv` | 4169 | 4 | ohlc_invariant_violation=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000019.SZ+深粮控股.csv` | 4169 | 4 | ohlc_invariant_violation=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000021.SZ+深科技.csv` | 4169 | 4 | ohlc_invariant_violation=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/神奇九转指标/by_symbol/000004.SZ+_ST国华.csv` | 8157 | 4 | ohlc_invariant_violation=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/神奇九转指标/by_symbol/000019.SZ+深粮控股.csv` | 7731 | 4 | ohlc_invariant_violation=1, sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/神奇九转指标/by_symbol/000020.SZ+深华发Ａ.csv` | 7702 | 4 | ohlc_invariant_violation=2, sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000004.SZ+_ST国华.csv` | 4164 | 3 | ohlc_invariant_violation=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000009.SZ+中国宝安.csv` | 4169 | 3 | ohlc_invariant_violation=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000016.SZ+深康佳Ａ.csv` | 4168 | 3 | ohlc_invariant_violation=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/股票开盘集合竞价数据/by_symbol/000020.SZ+深华发Ａ.csv` | 4168 | 3 | ohlc_invariant_violation=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/神奇九转指标/by_symbol/000006.SZ+深振业Ａ.csv` | 8027 | 3 | ohlc_invariant_violation=1, sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/特色数据/神奇九转指标/by_symbol/000001.SZ+平安银行.csv` | 8303 | 3 | ohlc_invariant_violation=1, sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `85b2dfc3f2d43d2a4b02c0b1e1f2417dcd48b1a9808c0a7d4aeb7e8d86f823c7` | 5605 | 7358171 | stale_primary_market_date_gt_45d=4015 |
| `f335d00113996279808bb09c59d1e2348931d607c224cd0eec76a6edebc53f57` | 3942 | 1100982 | stale_primary_market_date_gt_45d=3942 |
| `72ffb50c44ab6cea6d70054a08259b70f29ec8bbb745cdb5960f4d3b7a1283ae` | 236 | 507853 | ohlc_invariant_violation=74, stale_primary_market_date_gt_45d=236 |
| `e3574a77e11169d1c77ec490a6bef4901fc7080c4d2eac17a495684931b25cd0` | 103 | 295398 | ohlc_invariant_violation=11, sparse_columns_lt_5pct_non_empty=121, stale_primary_market_date_gt_45d=103 |
| `6abf304b7f92e5e94f9632f94ce918885cad57006af3c605bb52c805a829c9a6` | 80 | 121964 | stale_primary_market_date_gt_45d=80 |
| `181c32e16bc2a953206219c1f4781a8e26c811ecf9d7acd54dc4c302c46bc716` | 27 | 3636 | sparse_columns_lt_5pct_non_empty=16 |
| `f454174669bf572ad8563db56377ddc132e9b5b8abc8fbc0f18ede49ee140ab7` | 3 | 357 | stale_primary_market_date_gt_45d=3 |
| `cd42d8e81384f64c54586efadfc9b88e10be100f9c3af07066a8c37082caa9a1` | 1 | 54055 | stale_primary_market_date_gt_45d=1 |
| `66cd3fc8216f0277af60b269f662d7c2e79cb19632de9adabd3f01b82afa4638` | 1 | 1643 | stale_primary_market_date_gt_45d=1 |
| `85d93570069eab773077f9c2dc867b7f3e0b8858b592973be8eaa25a2cf5379a` | 1 | 2811 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
| `9876af9bc1753039ded043f84d13727ef178779fe5f9b59b5a9267cfbc6cfa55` | 1 | 55214 | duplicate_grain_key_sample=34, sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=1 |
