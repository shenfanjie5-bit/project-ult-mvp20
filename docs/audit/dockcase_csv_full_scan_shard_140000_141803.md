# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T05:24:48+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `198.404` seconds
- CSV files scanned: `1804`
- Rows scanned: `2439936`
- Header signatures: `6`
- Header read errors: `0`
- Row read errors: `0`
- Full row semantic scan: `False`

## Coverage Boundary

| Boundary | Value |
|---|---:|
| `all_business_csv_files_selected` | `False` |
| `all_selected_files_read_to_eof` | `True` |
| `full_row_semantic_scan` | `False` |
| `max_files_limit` | `1804` |
| `skip_files` | `140000` |

## Issue Counts

- `future_primary_date_gt_7d`: 1
- `high_empty_cell_ratio_signature`: 8
- `invalid_date`: 60
- `invalid_ts_code`: 132684
- `ohlc_invariant_violation`: 2121
- `sparse_columns_lt_5pct_non_empty`: 620
- `stale_primary_market_date_gt_45d`: 1801

## Domain Issue Counts

- `ohlc_invariant_violation`: 2121

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `指数专题/沪深市场每日交易统计/all.csv` | 101487 | 101488 | invalid_ts_code=101487, stale_primary_market_date_gt_45d=1 |
| `指数专题/深圳市场每日交易情况/all.csv` | 36518 | 30541 | invalid_ts_code=30540, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金经理/all.csv` | 69300 | 657 | invalid_ts_code=657 |
| `指数专题/指数技术面因子(专业版)/by_symbol/NHPMI.NH+南华贵金属指数.csv` | 1459 | 285 | ohlc_invariant_violation=284, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/NHCI.NH+南华商品指数.csv` | 1459 | 235 | ohlc_invariant_violation=234, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/NHECI.NH+南华能化指数.csv` | 1459 | 229 | ohlc_invariant_violation=228, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/NHNFI.NH+南华有色金属.csv` | 1459 | 226 | ohlc_invariant_violation=225, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/NHII.NH+南华工业品指数.csv` | 1459 | 220 | ohlc_invariant_violation=219, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/NHMI.NH+南华金属指数.csv` | 1459 | 218 | ohlc_invariant_violation=217, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/NHAI.NH+南华农产品指数.csv` | 1459 | 209 | ohlc_invariant_violation=208, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/NHFI.NH+南华黑色指数.csv` | 1459 | 199 | ohlc_invariant_violation=198, stale_primary_market_date_gt_45d=1 |
| `公募基金/基金管理人/all.csv` | 23743 | 63 | future_primary_date_gt_7d=1, invalid_date=60, sparse_columns_lt_5pct_non_empty=2 |
| `指数专题/指数技术面因子(专业版)/by_symbol/932447.CSI+中新亚洲100红利聚焦HKD.csv` | 6 | 51 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=49, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/932578.CSI+中新亚洲100红利聚焦SGD.csv` | 6 | 51 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=49, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/932583.CSI+中新亚洲100红利聚焦USD.csv` | 6 | 51 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=49, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/932597.CSI+中新亚洲100USD.csv` | 6 | 51 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=49, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/932600.CSI+中新亚洲100SGD.csv` | 6 | 51 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=49, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/932601.CSI+中新亚洲100红利聚焦.csv` | 6 | 51 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=49, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/932603.CSI+中新亚洲100HKD.csv` | 6 | 51 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=49, stale_primary_market_date_gt_45d=1 |
| `指数专题/指数技术面因子(专业版)/by_symbol/932607.CSI+中新亚洲100.csv` | 6 | 51 | high_empty_cell_ratio_signature=1, sparse_columns_lt_5pct_non_empty=49, stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `11908695cc41786a22ec4236f12db766f24e56b16cf9479f9f7e7dc1b248f340` | 1799 | 2178058 | high_empty_cell_ratio_signature=8, ohlc_invariant_violation=2121, sparse_columns_lt_5pct_non_empty=614, stale_primary_market_date_gt_45d=1799 |
| `f9cce54168bf5e67a63771151ae17dbe235a3f6bce3bf10aac56ed27e51630d1` | 1 | 101487 | invalid_ts_code=101487, stale_primary_market_date_gt_45d=1 |
| `edf535bff8ad591ea92f7234ff7eab9ebaa96a9e3c95ebd1b033df76b6140217` | 1 | 36518 | invalid_ts_code=30540, stale_primary_market_date_gt_45d=1 |
| `e7c6fd1e5495268323c2b6cbc61b46362464aee075a44c41b07fee9888f2c7e0` | 1 | 30830 | sparse_columns_lt_5pct_non_empty=4 |
| `e691871e2d6ba60b4f420383f99c099dcca13d10998cf4fdb1b75301480d4d14` | 1 | 23743 | future_primary_date_gt_7d=1, invalid_date=60, sparse_columns_lt_5pct_non_empty=2 |
| `bd7e81ea067ff6da39ea44c0454e02756287fe1c955a808314816b58c71ee69a` | 1 | 69300 | invalid_ts_code=657 |
