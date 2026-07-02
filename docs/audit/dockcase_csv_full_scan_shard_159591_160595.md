# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T05:26:14+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `46.163` seconds
- CSV files scanned: `1005`
- Rows scanned: `1173068`
- Header signatures: `51`
- Header read errors: `0`
- Row read errors: `0`
- Full row semantic scan: `False`

## Coverage Boundary

| Boundary | Value |
|---|---:|
| `all_business_csv_files_selected` | `False` |
| `all_selected_files_read_to_eof` | `True` |
| `full_row_semantic_scan` | `False` |
| `max_files_limit` | `1005` |
| `skip_files` | `159591` |

## Issue Counts

- `duplicate_grain_key_sample`: 22676
- `future_primary_date_gt_7d`: 1
- `high_empty_cell_ratio_signature`: 12
- `invalid_date`: 3011
- `invalid_numeric`: 118
- `invalid_ts_code`: 100524
- `ohlc_invariant_violation`: 1
- `sparse_columns_lt_5pct_non_empty`: 1801
- `stale_primary_market_date_gt_45d`: 546
- `zero_ohlc_no_trade_carry_forward`: 999

## Domain Issue Counts

- `duplicate_grain_key_sample`: 22676
- `ohlc_invariant_violation`: 1
- `zero_ohlc_no_trade_carry_forward`: 999

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `期权数据/期权合约信息/all.csv` | 230726 | 84171 | future_primary_date_gt_7d=1, invalid_ts_code=84170 |
| `现货数据/上海黄金现货日行情/all.csv` | 13517 | 13518 | invalid_ts_code=13517, stale_primary_market_date_gt_45d=1 |
| `外汇数据/外汇日线行情/all.csv` | 28409 | 2186 | invalid_ts_code=2185, stale_primary_market_date_gt_45d=1 |
| `美股数据/美股基础信息/all.csv` | 23528 | 2032 | invalid_date=1896, invalid_ts_code=135, sparse_columns_lt_5pct_non_empty=1 |
| `美股数据/美股资产负债表/by_symbol/AAL+AAL.csv` | 891 | 867 | duplicate_grain_key_sample=867 |
| `美股数据/美股资产负债表/by_symbol/AA+AA.csv` | 887 | 863 | duplicate_grain_key_sample=863 |
| `美股数据/美股现金流量表/by_symbol/AA+AA.csv` | 753 | 729 | duplicate_grain_key_sample=729 |
| `美股数据/美股资产负债表/by_symbol/AAOI+AAOI.csv` | 744 | 721 | duplicate_grain_key_sample=721 |
| `美股数据/美股资产负债表/by_symbol/AAP+AAP.csv` | 732 | 708 | duplicate_grain_key_sample=708 |
| `美股数据/美股资产负债表/by_symbol/AAON+AAON.csv` | 713 | 690 | duplicate_grain_key_sample=690 |
| `美股数据/美股现金流量表/by_symbol/AAON+AAON.csv` | 712 | 689 | duplicate_grain_key_sample=689 |
| `美股数据/美股现金流量表/by_symbol/A+A.csv` | 707 | 684 | duplicate_grain_key_sample=684 |
| `美股数据/美股资产负债表/by_symbol/AACG+AACG.csv` | 705 | 682 | duplicate_grain_key_sample=682 |
| `美股数据/美股利润表/by_symbol/AAL+AAL.csv` | 703 | 679 | duplicate_grain_key_sample=679 |
| `美股数据/美股资产负债表/by_symbol/A+A.csv` | 693 | 670 | duplicate_grain_key_sample=670 |
| `美股数据/美股资产负债表/by_symbol/AAPL+AAPL.csv` | 694 | 670 | duplicate_grain_key_sample=670 |
| `美股数据/美股利润表/by_symbol/AACG+AACG.csv` | 664 | 641 | duplicate_grain_key_sample=641 |
| `美股数据/美股资产负债表/by_symbol/AAME+AAME.csv` | 662 | 639 | duplicate_grain_key_sample=639 |
| `美股数据/美股现金流量表/by_symbol/AAOI+AAOI.csv` | 647 | 624 | duplicate_grain_key_sample=624 |
| `美股数据/美股利润表/by_symbol/AA+AA.csv` | 634 | 610 | duplicate_grain_key_sample=610 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `11908695cc41786a22ec4236f12db766f24e56b16cf9479f9f7e7dc1b248f340` | 494 | 403848 | ohlc_invariant_violation=1, sparse_columns_lt_5pct_non_empty=157, stale_primary_market_date_gt_45d=494, zero_ohlc_no_trade_carry_forward=936 |
| `6cc7b1bd7e4ec2c9f567b0f9129fece098e23928a5c9b33740991e6753f0500e` | 139 | 41876 | - |
| `c84955d03d551c6acb2a2f48b211ec592066a4f1696b45c60c70230a544048f7` | 70 | 812 | invalid_date=812, sparse_columns_lt_5pct_non_empty=1026 |
| `4863abc10e58f6c3a3b9a8c7b6e08a5030fd982ad3912eee187ceef8393fc56c` | 68 | 30364 | - |
| `54629efed8f9fd5d2520dc1fc580925c45943879229af9656fbb5e5f2f53a970` | 58 | 23579 | duplicate_grain_key_sample=22676 |
| `db0a76d4aa20eea27fd5d5edc0e23a6699862fe09025630ce111444301bef6a4` | 56 | 56 | - |
| `797978f9999a1c57930090c01f7522b7cf8071cd9e42e8fdfd521cc8fe21e774` | 21 | 14344 | stale_primary_market_date_gt_45d=21, zero_ohlc_no_trade_carry_forward=63 |
| `f00c584d1d032b9600cc7b716bd0815fbc3d640ed56e23eb3f78d3879a8745b1` | 20 | 64 | high_empty_cell_ratio_signature=3, sparse_columns_lt_5pct_non_empty=5 |
| `bcf44d80f900ae7278326a43151c4a03a811a5b697e1d2acf5820a4f3ea77574` | 19 | 5116 | sparse_columns_lt_5pct_non_empty=1, stale_primary_market_date_gt_45d=19 |
| `7d0469a7e8fce5b5fcd4466eb7c1b7320f4434e3e048427b0eb1c0ad1afd3ecd` | 18 | 303 | high_empty_cell_ratio_signature=9, invalid_date=303, sparse_columns_lt_5pct_non_empty=604 |
| `15184bfd13fb366f6bc43bf5cf3358ac0aa7f0f32e73fbf1f4e4dcaba4f5bd49` | 2 | 4402 | stale_primary_market_date_gt_45d=2 |
| `06b523e119a041806c01e97279ec179cefc6be0633c7625eecd55004d429a379` | 1 | 10821 | invalid_ts_code=6 |
| `758f93ed59903d0d2b12c75c23c2d63e10d65c12c8a66523f2837d07ec18b257` | 1 | 2201 | stale_primary_market_date_gt_45d=1 |
| `f2eb561d541802ec0473cee2e9bbc53e89eba42040954aaa535704befe1b7a40` | 1 | 246751 | invalid_ts_code=498, stale_primary_market_date_gt_45d=1 |
| `276c8aecbe200667ca139f075587085ae29f56375925e117e4121bfbd2efec12` | 1 | 8000 | - |
| `4dc3330d84730e5c3ae2ee0de7600bc6a6b0b6fdd0a512563fc04b21ae133939` | 1 | 13 | invalid_ts_code=13 |
| `199c75eae80a40afaa2d86f1df85cf5fc0aeb91303b27458a80f75cb79855af8` | 1 | 13517 | invalid_ts_code=13517, stale_primary_market_date_gt_45d=1 |
| `4dd01c9100fc005278a60f7bd28e50738ea253045e5669b421d4d32cb13d1039` | 1 | 230726 | future_primary_date_gt_7d=1, invalid_ts_code=84170 |
| `05bdef0f19e00b23ff6147d4bafc21a80e73822ee9039a72c204b207e432f1ab` | 1 | 1099 | sparse_columns_lt_5pct_non_empty=1 |
| `e8f77d4b4c282a8c45485df8f37288cfaf5d1e06f23b203b0ec46ece709f5738` | 1 | 13779 | stale_primary_market_date_gt_45d=1 |
