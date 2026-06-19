# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T03:19:29+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `123.745` seconds
- CSV files scanned: `2000`
- Rows scanned: `5445437`
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
| `max_files_limit` | `2000` |
| `skip_files` | `1600` |

## Issue Counts

- `stale_primary_market_date_gt_45d`: 1449

## Domain Issue Counts

- No domain-invariant issues detected.

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/行情数据/历史日线/by_symbol/002933.SZ+新兴装备.csv` | 1818 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002935.SZ+天奥电子.csv` | 1817 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002940.SZ+昂利康.csv` | 1777 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002941.SZ+新疆交建.csv` | 1761 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002942.SZ+新农股份.csv` | 1756 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002946.SZ+新乳业.csv` | 1721 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002949.SZ+华阳国际.csv` | 1704 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002950.SZ+奥美医疗.csv` | 1695 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002951.SZ+金时科技.csv` | 1688 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002952.SZ+亚世光电.csv` | 1682 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002953.SZ+日丰股份.csv` | 1656 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002955.SZ+鸿合科技.csv` | 1642 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002956.SZ+西麦食品.csv` | 1628 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002959.SZ+小熊电器.csv` | 1581 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002960.SZ+青鸟消防.csv` | 1591 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002961.SZ+瑞达期货.csv` | 1572 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002962.SZ+五方光电.csv` | 1565 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002963.SZ+豪尔赛.csv` | 1541 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002965.SZ+祥鑫科技.csv` | 1542 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/002967.SZ+广电计量.csv` | 1532 | 1 | stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `c00a50db1789a41108a9c682898cc2237e9a38405143a6c2beb0294e127785cd` | 2000 | 5445437 | stale_primary_market_date_gt_45d=1449 |
