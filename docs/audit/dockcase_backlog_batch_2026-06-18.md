# DOCKCASE backlog batch semantic pass

- Generated: `2026-06-19T00:31:24+0800`
- Status: `ready`
- Data root: `/Volumes/dockcase2tb/database_all`
- Source: `/Users/fanjie/Desktop/Cowork/project-ult-mvp20/docs/audit/dockcase_csv_semantics_2026-06-18.json`
- Target ranks: `[46]`
- Matched files: `28`
- Sampled files / rows: `28` / `5600`
- Header read errors: `0`

## Issue Counts

- `index_by_symbol_bundle_mismatch`: 5600
- `ohlc_invariant_violation`: 28
- `stale_primary_market_date_gt_45d`: 1

## Signatures

### Rank `46`

- Matched files: `28`
- Sampled files / rows: `28` / `5600`
- Columns: `ts_code, trade_date, open, close, high, low, pre_close, change, pct_chg, swing, vol`

Examples:
- `指数专题/国际主要指数/by_symbol/652689.MI+MSCI金砖四国中盘价值.csv`
- `指数专题/国际主要指数/by_symbol/000002.SH+A股指数.csv`
- `指数专题/国际主要指数/by_symbol/000002.CJ+原材料(长江).csv`
- `指数专题/国际主要指数/by_symbol/133707.MI+MSCI阿拉伯市场.csv`
- `指数专题/国际主要指数/by_symbol/000001.CJ+能源(长江).csv`
- `指数专题/国际主要指数/by_symbol/652692.MI+MSCI哥伦比亚中盘价值.csv`
- `指数专题/国际主要指数/by_symbol/000001.SH+上证指数.csv`
- `指数专题/国际主要指数/by_symbol/652690.MI+MSCI智利中盘价值.csv`
