# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T03:11:08+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `19.193` seconds
- CSV files scanned: `200`
- Rows scanned: `855820`
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
| `max_files_limit` | `200` |
| `skip_files` | `400` |

## Issue Counts

- `stale_primary_market_date_gt_45d`: 126

## Domain Issue Counts

- No domain-invariant issues detected.

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/行情数据/历史日线/by_symbol/000838.SZ+财信发展.csv` | 6663 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000594.SZ+国恒退(退).csv` | 4262 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000848.SZ+承德露露.csv` | 6769 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000850.SZ+华茂股份.csv` | 6435 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000852.SZ+石化机械.csv` | 6397 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000856.SZ+冀东装备.csv` | 6556 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000858.SZ+五粮液.csv` | 6617 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000859.SZ+国风新材.csv` | 6513 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000860.SZ+顺鑫农业.csv` | 6525 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000862.SZ+银星能源.csv` | 6190 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000863.SZ+三湘印象.csv` | 5423 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000868.SZ+安凯客车.csv` | 6750 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000869.SZ+张裕Ａ.csv` | 6089 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000876.SZ+新希望.csv` | 6539 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000602.SZ+金马集团(退).csv` | 3826 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000881.SZ+中广核技.csv` | 6437 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000882.SZ+华联股份.csv` | 6514 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000606.SZ+顺利退(退).csv` | 6128 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000885.SZ+城发环境.csv` | 6030 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000886.SZ+海南高速.csv` | 6727 | 1 | stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `c00a50db1789a41108a9c682898cc2237e9a38405143a6c2beb0294e127785cd` | 200 | 855820 | stale_primary_market_date_gt_45d=126 |
