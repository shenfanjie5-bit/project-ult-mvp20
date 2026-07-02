# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T04:02:03+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `201.182` seconds
- CSV files scanned: `30000`
- Rows scanned: `8887851`
- Header signatures: `12`
- Header read errors: `0`
- Row read errors: `0`
- Full row semantic scan: `False`

## Coverage Boundary

| Boundary | Value |
|---|---:|
| `all_business_csv_files_selected` | `False` |
| `all_selected_files_read_to_eof` | `True` |
| `full_row_semantic_scan` | `False` |
| `max_files_limit` | `30000` |
| `skip_files` | `63600` |

## Issue Counts

- `duplicate_grain_key_sample`: 19946
- `high_empty_cell_ratio_signature`: 198
- `invalid_date`: 5
- `sparse_columns_lt_5pct_non_empty`: 12272
- `stale_primary_market_date_gt_45d`: 5279

## Domain Issue Counts

- `duplicate_grain_key_sample`: 19946

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/参考数据/限售股解禁/by_symbol/601686.SH+友发集团.csv` | 22366 | 10962 | duplicate_grain_key_sample=10962 |
| `股票数据/参考数据/限售股解禁/by_symbol/601698.SH+中国卫通.csv` | 10150 | 5076 | duplicate_grain_key_sample=5076 |
| `股票数据/参考数据/限售股解禁/by_symbol/000301.SZ+东方盛虹.csv` | 403 | 185 | duplicate_grain_key_sample=185 |
| `股票数据/参考数据/限售股解禁/by_symbol/000002.SZ+万科Ａ.csv` | 268 | 134 | duplicate_grain_key_sample=134 |
| `股票数据/参考数据/限售股解禁/by_symbol/300463.SZ+迈克生物.csv` | 412 | 130 | duplicate_grain_key_sample=130 |
| `股票数据/参考数据/限售股解禁/by_symbol/300464.SZ+星徽股份.csv` | 344 | 120 | duplicate_grain_key_sample=120 |
| `股票数据/参考数据/限售股解禁/by_symbol/300456.SZ+赛微电子.csv` | 500 | 107 | duplicate_grain_key_sample=107 |
| `股票数据/参考数据/限售股解禁/by_symbol/000001.SZ+平安银行.csv` | 214 | 105 | duplicate_grain_key_sample=105 |
| `股票数据/参考数据/限售股解禁/by_symbol/000008.SZ+神州高铁.csv` | 457 | 100 | duplicate_grain_key_sample=100 |
| `股票数据/参考数据/限售股解禁/by_symbol/300462.SZ+ST华铭.csv` | 338 | 64 | duplicate_grain_key_sample=64 |
| `股票数据/参考数据/限售股解禁/by_symbol/601669.SH+中国电建.csv` | 231 | 62 | duplicate_grain_key_sample=62 |
| `股票数据/参考数据/股东增减持/by_symbol/603259.SH+药明康德.csv` | 136 | 51 | duplicate_grain_key_sample=51 |
| `股票数据/参考数据/限售股解禁/by_symbol/000156.SZ+华数传媒.csv` | 130 | 46 | duplicate_grain_key_sample=46 |
| `股票数据/参考数据/限售股解禁/by_symbol/000099.SZ+中信海直.csv` | 88 | 44 | duplicate_grain_key_sample=44 |
| `股票数据/参考数据/限售股解禁/by_symbol/000009.SZ+中国宝安.csv` | 329 | 39 | duplicate_grain_key_sample=39 |
| `股票数据/参考数据/股东增减持/by_symbol/600817.SH+宇通重工.csv` | 48 | 33 | duplicate_grain_key_sample=33 |
| `股票数据/参考数据/限售股解禁/by_symbol/601696.SH+中银证券.csv` | 10292 | 32 | duplicate_grain_key_sample=32 |
| `股票数据/参考数据/限售股解禁/by_symbol/000032.SZ+深桑达Ａ.csv` | 125 | 31 | duplicate_grain_key_sample=31 |
| `股票数据/参考数据/限售股解禁/by_symbol/300457.SZ+赢合科技.csv` | 287 | 29 | duplicate_grain_key_sample=29 |
| `股票数据/参考数据/限售股解禁/by_symbol/000155.SZ+川能动力.csv` | 86 | 29 | duplicate_grain_key_sample=29 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `7c3b5648b0749139c71889239613404bf3bede2504b74b732cdb5a1edefcf8e4` | 5741 | 765852 | sparse_columns_lt_5pct_non_empty=80 |
| `fe175dad161b3198b154553f38670da26eeb821197f7b277290bf8f55a4d304f` | 5683 | 37433 | sparse_columns_lt_5pct_non_empty=77 |
| `c3720fd7c652a69a62fda511b3c2d469b083a7ae03a53e6c24002dee7d61a281` | 5179 | 6797785 | stale_primary_market_date_gt_45d=5179 |
| `2b25d60d8a9e579f47d501fe27c0448d4ff7de03f9eef6b13e4ec1f6571ce1d1` | 4864 | 102360 | duplicate_grain_key_sample=2358, sparse_columns_lt_5pct_non_empty=882 |
| `4d4c03851503f4f3afd959836bfbe81830b1c8e80d685c0ba4d119de9509de48` | 4670 | 1087773 | high_empty_cell_ratio_signature=195, sparse_columns_lt_5pct_non_empty=11072 |
| `6f19fd0d2299caf2cf8f6f772f12ccca3f2483a7bc1d822ce2461ca387914383` | 3302 | 21514 | sparse_columns_lt_5pct_non_empty=36 |
| `d9ca0794a2e2201a32392e779c62cb3e5829b3b05c0a0450a2e64c12fea32271` | 164 | 16026 | - |
| `bf10c82623bf4d50b2038f0dbe12211de40063ff25ce8a4b45641a91b60489e1` | 100 | 4305 | duplicate_grain_key_sample=18, stale_primary_market_date_gt_45d=100 |
| `7407bb8a2e76ebc8d6bff9e5a93035fcee87b80fc4a52d266ce3f58f1c2eab60` | 91 | 400 | - |
| `21110954a9fd3562200ab7eef70c8fdb68e896342d7f3bcc25dc6c85a30a5b8a` | 71 | 49866 | duplicate_grain_key_sample=17570, sparse_columns_lt_5pct_non_empty=1 |
| `e54ffcfb9c8d4c14a44005695f8b28a294f51533a0f82f166cba30c5d5b75d11` | 69 | 2987 | high_empty_cell_ratio_signature=3, invalid_date=5, sparse_columns_lt_5pct_non_empty=68 |
| `ab510fb02b252ae43c8a28e19bd9dc080d2cc48c0db8b5ac7a7164e30cc90e44` | 66 | 1550 | sparse_columns_lt_5pct_non_empty=56 |
