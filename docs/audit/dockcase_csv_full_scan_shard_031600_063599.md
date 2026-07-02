# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T03:45:19+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `108.291` seconds
- CSV files scanned: `32000`
- Rows scanned: `673770`
- Header signatures: `7`
- Header read errors: `0`
- Row read errors: `0`
- Full row semantic scan: `False`

## Coverage Boundary

| Boundary | Value |
|---|---:|
| `all_business_csv_files_selected` | `False` |
| `all_selected_files_read_to_eof` | `True` |
| `full_row_semantic_scan` | `False` |
| `max_files_limit` | `32000` |
| `skip_files` | `31600` |

## Issue Counts

- `high_empty_cell_ratio_signature`: 6982
- `sparse_columns_lt_5pct_non_empty`: 514015

## Domain Issue Counts

- No domain-invariant issues detected.

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/财务数据/资产负债表/by_symbol/600253.SH+天方药业(退).csv` | 2 | 143 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=142 |
| `股票数据/财务数据/资产负债表/by_symbol/600799.SH+_ST龙科(退).csv` | 5 | 120 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=119 |
| `股票数据/财务数据/资产负债表/by_symbol/600659.SH+_ST花雕(退).csv` | 6 | 114 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=113 |
| `股票数据/财务数据/资产负债表/by_symbol/600752.SH+_ST哈慈(退).csv` | 3 | 113 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=112 |
| `股票数据/财务数据/资产负债表/by_symbol/002961.SZ+瑞达期货.csv` | 32 | 110 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=109 |
| `股票数据/财务数据/资产负债表/by_symbol/300028.SZ+金亚退(退).csv` | 3 | 109 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=108 |
| `股票数据/财务数据/资产负债表/by_symbol/603284.SH+C林平.csv` | 5 | 109 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=108 |
| `股票数据/财务数据/资产负债表/by_symbol/600286.SH+S_ST国瓷(退).csv` | 25 | 108 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=107 |
| `股票数据/财务数据/资产负债表/by_symbol/600625.SH+PT水仙(退).csv` | 21 | 108 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=107 |
| `股票数据/财务数据/资产负债表/by_symbol/920076.BJ+国亮新材.csv` | 11 | 108 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=107 |
| `股票数据/财务数据/资产负债表/by_symbol/600670.SH+_ST斯达(退).csv` | 18 | 107 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=106 |
| `股票数据/财务数据/资产负债表/by_symbol/600709.SH+ST生态(退).csv` | 29 | 107 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=106 |
| `股票数据/财务数据/资产负债表/by_symbol/600852.SH+_ST中川(退).csv` | 17 | 107 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=106 |
| `股票数据/财务数据/资产负债表/by_symbol/600007.SH+中国国贸.csv` | 32 | 106 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=105 |
| `股票数据/财务数据/资产负债表/by_symbol/600870.SH+退市厦华(退).csv` | 17 | 106 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=105 |
| `股票数据/财务数据/资产负债表/by_symbol/601860.SH+紫金银行.csv` | 35 | 106 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=105 |
| `股票数据/财务数据/资产负债表/by_symbol/002807.SZ+江阴银行.csv` | 45 | 105 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=104 |
| `股票数据/财务数据/资产负债表/by_symbol/002839.SZ+张家港行.csv` | 26 | 105 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=104 |
| `股票数据/财务数据/资产负债表/by_symbol/688382.SH+益方生物-U.csv` | 26 | 105 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=104 |
| `股票数据/财务数据/资产负债表/by_symbol/920119.BJ+美德乐.csv` | 6 | 105 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=104 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `e19a0e459f5c1e3aeb146cba0a9f0fa1fc202866a128605f0a8c39315b98f985` | 5765 | 212139 | high_empty_cell_ratio_signature=7, sparse_columns_lt_5pct_non_empty=7486 |
| `3bf00731c9cdc79419868e7d33f3901c2edf1b73ce978b8fc3e3669959b8343a` | 5757 | 198644 | high_empty_cell_ratio_signature=3538, sparse_columns_lt_5pct_non_empty=186017 |
| `0687a94f112620bbbdc6eb80738c92827244420c63338260454b64554136d96d` | 5600 | 73498 | sparse_columns_lt_5pct_non_empty=17187 |
| `7b08a7fe50938bfb032bf86effecad7e985d4efe88349802058207df50daff61` | 5485 | 61708 | sparse_columns_lt_5pct_non_empty=428 |
| `9d5b2d42ca01652f0e40a89c5ac9c2081fe701b9bf532753e2ab8f53412e2822` | 3789 | 10548 | high_empty_cell_ratio_signature=3, sparse_columns_lt_5pct_non_empty=7949 |
| `f46907a0d8bc2627a8b7e7fa5ae34b8a7b0fa991efddad65bae1f0b2cd57617d` | 3462 | 103445 | high_empty_cell_ratio_signature=3434, sparse_columns_lt_5pct_non_empty=294941 |
| `6f19fd0d2299caf2cf8f6f772f12ccca3f2483a7bc1d822ce2461ca387914383` | 2142 | 13788 | sparse_columns_lt_5pct_non_empty=7 |
