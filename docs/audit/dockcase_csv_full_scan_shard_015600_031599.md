# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T03:40:37+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `649.103` seconds
- CSV files scanned: `16000`
- Rows scanned: `18914846`
- Header signatures: `8`
- Header read errors: `0`
- Row read errors: `0`
- Full row semantic scan: `False`

## Coverage Boundary

| Boundary | Value |
|---|---:|
| `all_business_csv_files_selected` | `False` |
| `all_selected_files_read_to_eof` | `True` |
| `full_row_semantic_scan` | `False` |
| `max_files_limit` | `16000` |
| `skip_files` | `15600` |

## Issue Counts

- `high_empty_cell_ratio_signature`: 7983
- `sparse_columns_lt_5pct_non_empty`: 448530
- `stale_primary_market_date_gt_45d`: 6313
- `zero_ohlc_no_trade_carry_forward`: 3437

## Domain Issue Counts

- `zero_ohlc_no_trade_carry_forward`: 3437

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/行情数据/备用行情/by_symbol/000029.SZ+深深房Ａ.csv` | 2102 | 817 | stale_primary_market_date_gt_45d=1, zero_ohlc_no_trade_carry_forward=816 |
| `股票数据/行情数据/备用行情/by_symbol/000031.SZ+大悦城.csv` | 2102 | 186 | stale_primary_market_date_gt_45d=1, zero_ohlc_no_trade_carry_forward=185 |
| `股票数据/行情数据/备用行情/by_symbol/000019.SZ+深粮控股.csv` | 2102 | 158 | stale_primary_market_date_gt_45d=1, zero_ohlc_no_trade_carry_forward=157 |
| `股票数据/财务数据/资产负债表/by_symbol/000515.SZ+攀渝钛业(退).csv` | 2 | 142 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=141 |
| `股票数据/行情数据/备用行情/by_symbol/000007.SZ+全新好.csv` | 2102 | 140 | stale_primary_market_date_gt_45d=1, zero_ohlc_no_trade_carry_forward=139 |
| `股票数据/财务数据/资产负债表/by_symbol/000583.SZ+S_ST托普(退).csv` | 33 | 125 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=124 |
| `股票数据/行情数据/备用行情/by_symbol/000006.SZ+深振业Ａ.csv` | 2102 | 118 | stale_primary_market_date_gt_45d=1, zero_ohlc_no_trade_carry_forward=117 |
| `股票数据/财务数据/资产负债表/by_symbol/000689.SZ+ST宏业(退).csv` | 23 | 118 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=117 |
| `股票数据/财务数据/资产负债表/by_symbol/000594.SZ+国恒退(退).csv` | 3 | 116 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=115 |
| `股票数据/财务数据/资产负债表/by_symbol/600901.SH+江苏金租.csv` | 39 | 115 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=114 |
| `股票数据/财务数据/资产负债表/by_symbol/000699.SZ+S_ST佳纸(退).csv` | 25 | 114 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=113 |
| `股票数据/财务数据/资产负债表/by_symbol/000405.SZ+ST鑫光(退).csv` | 31 | 113 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=112 |
| `股票数据/财务数据/资产负债表/by_symbol/000563.SZ+陕国投Ａ.csv` | 33 | 112 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=111 |
| `股票数据/财务数据/资产负债表/by_symbol/000033.SZ+新都退(退).csv` | 36 | 111 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=110 |
| `股票数据/财务数据/资产负债表/by_symbol/001236.SZ+弘业期货.csv` | 24 | 111 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=110 |
| `股票数据/财务数据/资产负债表/by_symbol/000832.SZ+_ST龙涤(退).csv` | 20 | 109 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=108 |
| `股票数据/行情数据/备用行情/by_symbol/000040.SZ+_ST旭蓝(退).csv` | 1251 | 106 | sparse_columns_lt_5pct_non_empty=2, stale_primary_market_date_gt_45d=1, zero_ohlc_no_trade_carry_forward=103 |
| `股票数据/财务数据/资产负债表/by_symbol/600015.SH+华夏银行.csv` | 27 | 106 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=105 |
| `股票数据/财务数据/资产负债表/by_symbol/601658.SH+邮储银行.csv` | 41 | 105 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=104 |
| `股票数据/财务数据/资产负债表/by_symbol/601916.SH+浙商银行.csv` | 26 | 105 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=104 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `3546f354c743f50f06826758cf6bf4823822afb2753d8b241eab57ce40b77558` | 5812 | 17875474 | sparse_columns_lt_5pct_non_empty=452, stale_primary_market_date_gt_45d=4215 |
| `a0bd3c991042edf40edbd34a815a07d892a750db2e4aed5937b4367076a36c55` | 5787 | 300410 | high_empty_cell_ratio_signature=5718, sparse_columns_lt_5pct_non_empty=260132 |
| `f46907a0d8bc2627a8b7e7fa5ae34b8a7b0fa991efddad65bae1f0b2cd57617d` | 2302 | 77133 | high_empty_cell_ratio_signature=2265, sparse_columns_lt_5pct_non_empty=187796 |
| `babb7a89817667592b8bdbbf0abfd2bd2f17223d7c3e46e8119a0063142eb506` | 1833 | 142665 | stale_primary_market_date_gt_45d=1833 |
| `8a865230deaf0db78974a1d3f4da799bc39ffc3df315ea9def3dfbcc41ed6531` | 144 | 243990 | sparse_columns_lt_5pct_non_empty=150, stale_primary_market_date_gt_45d=144, zero_ohlc_no_trade_carry_forward=3437 |
| `9b2dce55d0fab7658beb483af53a26db062afcec2db50e23b98ecc9c8c925e84` | 120 | 272454 | stale_primary_market_date_gt_45d=120 |
| `dafe65f8f36710d85de48b6bc03b14059b35ead0ae8206d9854293a9464589a3` | 1 | 2572 | stale_primary_market_date_gt_45d=1 |
| `f773ef8f085ceb27a862e5bec055ae2c456969a3157922b2de46a07a878115ec` | 1 | 148 | - |
