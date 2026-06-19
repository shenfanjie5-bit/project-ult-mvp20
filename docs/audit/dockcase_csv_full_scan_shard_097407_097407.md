# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T04:13:16+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `2.832` seconds
- CSV files scanned: `1`
- Rows scanned: `6062`
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
| `max_files_limit` | `1` |
| `skip_files` | `97407` |

## Issue Counts

- `stale_primary_market_date_gt_45d`: 1

## Domain Issue Counts

- No domain-invariant issues detected.

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/特色数据/股票技术面因子(专业版）/by_symbol/000158.SZ+常山北明.csv` | 6062 | 1 | stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `d20d0849c1ca675fca5c0a55123c8c09929f85fae897cc7f86786c2775cb096f` | 1 | 6062 | stale_primary_market_date_gt_45d=1 |
