# DOCKCASE backlog batch semantic pass

- Generated: `2026-06-19T00:35:04+0800`
- Status: `ready`
- Data root: `/Volumes/dockcase2tb/database_all`
- Source: `/Users/fanjie/Desktop/Cowork/project-ult-mvp20/docs/audit/dockcase_csv_semantics_2026-06-18.json`
- Target ranks: `[27, 31]`
- Matched files: `324`
- Sampled files / rows: `100` / `20000`
- Header read errors: `0`

## Issue Counts

- `index_by_symbol_bundle_mismatch`: 20000
- `stale_primary_market_date_gt_45d`: 2

## Signatures

### Rank `27`

- Matched files: `192`
- Sampled files / rows: `50` / `10000`
- Columns: `ts_code, trade_date, name, open, low, high, close, change, pct_change, vol, amount, pe`

Examples:
- `指数专题/申万行业指数日行情/by_symbol/114701.MI+MSCI中国_食品饮料与烟草.csv`
- `指数专题/申万行业指数日行情/by_symbol/000001.CJ+能源(长江).csv`
- `指数专题/申万行业指数日行情/by_symbol/000002.CJ+原材料(长江).csv`
- `指数专题/申万行业指数日行情/by_symbol/000002.SH+A股指数.csv`
- `指数专题/申万行业指数日行情/by_symbol/000001.SH+上证指数.csv`
- `指数专题/申万行业指数日行情/by_symbol/000003.CJ+工业(长江).csv`
- `指数专题/申万行业指数日行情/by_symbol/000003.SH+B股指数.csv`
- `指数专题/申万行业指数日行情/by_symbol/000004.CJ+可选消费(长江).csv`

### Rank `31`

- Matched files: `132`
- Sampled files / rows: `50` / `10000`
- Columns: `ts_code, trade_date, open, low, high, close, pre_close, change, pct_change, vol, amount`

Examples:
- `指数专题/中信行业指数日行情/by_symbol/106507.MI+MSCI欧盟(除德国).csv`
- `指数专题/中信行业指数日行情/by_symbol/000001.SH+上证指数.csv`
- `指数专题/中信行业指数日行情/by_symbol/000002.CJ+原材料(长江).csv`
- `指数专题/中信行业指数日行情/by_symbol/000002.SH+A股指数.csv`
- `指数专题/中信行业指数日行情/by_symbol/000001.CJ+能源(长江).csv`
- `指数专题/中信行业指数日行情/by_symbol/000003.CJ+工业(长江).csv`
- `指数专题/中信行业指数日行情/by_symbol/000003.SH+B股指数.csv`
- `指数专题/中信行业指数日行情/by_symbol/000004.CJ+可选消费(长江).csv`
