# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T03:27:45+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `69.397` seconds
- CSV files scanned: `8000`
- Rows scanned: `2905079`
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
| `max_files_limit` | `8000` |
| `skip_files` | `7600` |

## Issue Counts

- `stale_primary_market_date_gt_45d`: 8000

## Domain Issue Counts

- No domain-invariant issues detected.

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/行情数据/周线行情/by_symbol/300183.SZ+东软载波.csv` | 747 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300184.SZ+力源信息.csv` | 704 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300185.SZ+通裕重工.csv` | 759 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300187.SZ+永清环保.csv` | 722 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300188.SZ+国投智能.csv` | 748 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300189.SZ+神农种业.csv` | 712 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300190.SZ+维尔利.csv` | 721 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300191.SZ+潜能恒信.csv` | 749 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300192.SZ+科德教育.csv` | 703 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/002325.SZ+_ST洪涛(退).csv` | 720 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300193.SZ+佳士科技.csv` | 763 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300194.SZ+福安药业.csv` | 725 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300195.SZ+长荣股份.csv` | 736 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300196.SZ+长海股份.csv` | 733 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300197.SZ+节能铁汉.csv` | 703 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300198.SZ+ST纳川.csv` | 710 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300199.SZ+翰宇药业.csv` | 735 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300200.SZ+高盟新材.csv` | 754 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300201.SZ+海伦哲.csv` | 696 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/周线行情/by_symbol/300203.SZ+聚光科技.csv` | 745 | 1 | stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `babb7a89817667592b8bdbbf0abfd2bd2f17223d7c3e46e8119a0063142eb506` | 8000 | 2905079 | stale_primary_market_date_gt_45d=8000 |
