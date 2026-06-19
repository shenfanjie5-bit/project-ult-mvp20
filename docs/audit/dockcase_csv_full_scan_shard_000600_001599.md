# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T03:14:07+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `78.375` seconds
- CSV files scanned: `1000`
- Rows scanned: `3448755`
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
| `max_files_limit` | `1000` |
| `skip_files` | `600` |

## Issue Counts

- `ohlc_invariant_violation`: 1
- `stale_primary_market_date_gt_45d`: 700

## Domain Issue Counts

- `ohlc_invariant_violation`: 1

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/行情数据/历史日线/by_symbol/001296.SZ+长江材料.csv` | 1014 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001298.SZ+好上好.csv` | 811 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001299.SZ+美能能源.csv` | 811 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001300.SZ+三柏硕.csv` | 819 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001306.SZ+夏厦精密.csv` | 556 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001311.SZ+多利科技.csv` | 732 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001313.SZ+粤海饲料.csv` | 982 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001314.SZ+亿道信息.csv` | 732 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001316.SZ+润贝航科.csv` | 896 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001317.SZ+三羊马.csv` | 1027 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001318.SZ+阳光乳业.csv` | 920 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001319.SZ+铭科精技.csv` | 926 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001322.SZ+箭牌家居.csv` | 814 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001323.SZ+慕思股份.csv` | 897 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001324.SZ+长青科技.csv` | 676 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001325.SZ+元创股份.csv` | 49 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001326.SZ+联域股份.csv` | 561 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001328.SZ+登康口腔.csv` | 703 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001331.SZ+胜通能源.csv` | 834 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/001332.SZ+锡装股份.csv` | 835 | 1 | stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `c00a50db1789a41108a9c682898cc2237e9a38405143a6c2beb0294e127785cd` | 1000 | 3448755 | ohlc_invariant_violation=1, stale_primary_market_date_gt_45d=700 |
