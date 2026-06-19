# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T03:24:29+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `161.996` seconds
- CSV files scanned: `4000`
- Rows scanned: `6956175`
- Header signatures: `2`
- Header read errors: `0`
- Row read errors: `0`
- Full row semantic scan: `False`

## Coverage Boundary

| Boundary | Value |
|---|---:|
| `all_business_csv_files_selected` | `False` |
| `all_selected_files_read_to_eof` | `True` |
| `full_row_semantic_scan` | `False` |
| `max_files_limit` | `4000` |
| `skip_files` | `3600` |

## Issue Counts

- `ohlc_invariant_violation`: 3
- `stale_primary_market_date_gt_45d`: 3477

## Domain Issue Counts

- `ohlc_invariant_violation`: 3

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/行情数据/历史日线/by_symbol/920489.BJ+佳先股份.csv` | 2390 | 3 | ohlc_invariant_violation=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600807.SH+济高发展.csv` | 7263 | 2 | ohlc_invariant_violation=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600551.SH+时代出版.csv` | 5482 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600556.SH+天下秀.csv` | 4299 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600557.SH+康缘药业.csv` | 5628 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600558.SH+大西洋.csv` | 5920 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600559.SH+老白干酒.csv` | 5369 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600560.SH+金自天正.csv` | 5648 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600561.SH+江西长运.csv` | 5620 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600562.SH+国睿科技.csv` | 5493 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600566.SH+济川药业.csv` | 5776 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600567.SH+山鹰国际.csv` | 5746 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600568.SH+ST中珠.csv` | 5561 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600569.SH+安阳钢铁.csv` | 5810 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600571.SH+信雅达.csv` | 5455 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600572.SH+康恩贝.csv` | 5104 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600573.SH+惠泉啤酒.csv` | 5552 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600576.SH+祥源文旅.csv` | 5091 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/300178.SZ+腾邦退(退).csv` | 2630 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/600579.SH+中化装备.csv` | 5286 | 1 | stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `c00a50db1789a41108a9c682898cc2237e9a38405143a6c2beb0294e127785cd` | 2236 | 5454585 | ohlc_invariant_violation=3, stale_primary_market_date_gt_45d=1713 |
| `babb7a89817667592b8bdbbf0abfd2bd2f17223d7c3e46e8119a0063142eb506` | 1764 | 1501590 | stale_primary_market_date_gt_45d=1764 |
