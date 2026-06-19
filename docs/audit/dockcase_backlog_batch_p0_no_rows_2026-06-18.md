# DOCKCASE backlog batch semantic pass

- Generated: `2026-06-19T00:38:44+0800`
- Status: `ready`
- Data root: `/Volumes/dockcase2tb/database_all`
- Source: `/Users/fanjie/Desktop/Cowork/project-ult-mvp20/docs/audit/dockcase_csv_semantics_2026-06-18.json`
- Target ranks: `[121, 124, 128]`
- Matched files: `3`
- Sampled files / rows: `0` / `0`
- Header read errors: `0`

## Issue Counts

- `no_sampled_rows`: 3

## Signatures

### Rank `121`

- Matched files: `1`
- Sampled files / rows: `0` / `0`
- Columns: `group, api, label, path, normalized_path, rate_limit, note, rows, pages, strategy, truncated, skipped_existing`

Examples:
- `_workspace/_meta/manifests/master_dictionary_index.csv`

### Rank `124`

- Matched files: `1`
- Sampled files / rows: `0` / `0`
- Columns: `ts_code, name, enname, classify, list_date, delist_date, source_api, updated_at`

Examples:
- `_workspace/_meta/exports/curated_sample_20260310_60d_20stocks/tables/dim_us_security.csv`

### Rank `128`

- Matched files: `1`
- Sampled files / rows: `0` / `0`
- Columns: `market, ts_code, security_name, end_date, report_type, ind_type, std_report_date, notice_date, start_date, financial_date, date_type, currency`

Examples:
- `_workspace/_meta/exports/curated_sample_20260310_60d_20stocks/tables/fact_overseas_financial_indicator.csv`
