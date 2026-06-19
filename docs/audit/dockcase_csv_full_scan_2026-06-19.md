# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T03:04:05+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `37.981` seconds
- CSV files scanned: `200`
- Rows scanned: `1522830`
- Header signatures: `12`
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
| `skip_files` | `0` |

## Issue Counts

- `future_primary_date_gt_7d`: 1
- `invalid_date`: 914
- `ohlc_invariant_violation`: 17
- `stale_primary_market_date_gt_45d`: 117

## Domain Issue Counts

- `ohlc_invariant_violation`: 17

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `股票数据/基础数据/上市公司管理层/all.csv` | 4000 | 625 | invalid_date=625 |
| `股票数据/基础数据/股票历史列表/all.csv` | 255830 | 290 | invalid_date=289, stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000004.SZ+_ST国华.csv` | 8158 | 4 | ohlc_invariant_violation=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000003.SZ+PT金田A(退).csv` | 2419 | 4 | ohlc_invariant_violation=3, stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000020.SZ+深华发Ａ.csv` | 7703 | 3 | ohlc_invariant_violation=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000013.SZ+_ST石化A(退).csv` | 2907 | 3 | ohlc_invariant_violation=2, stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000006.SZ+深振业Ａ.csv` | 8028 | 2 | ohlc_invariant_violation=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000011.SZ+深物业A.csv` | 8035 | 2 | ohlc_invariant_violation=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000014.SZ+沙河股份.csv` | 8046 | 2 | ohlc_invariant_violation=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000016.SZ+深康佳Ａ.csv` | 8071 | 2 | ohlc_invariant_violation=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000019.SZ+深粮控股.csv` | 7732 | 2 | ohlc_invariant_violation=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000015.SZ+PT中浩A(退).csv` | 1972 | 2 | ohlc_invariant_violation=1, stale_primary_market_date_gt_45d=1 |
| `股票数据/基础数据/交易日历/all.csv` | 13162 | 1 | future_primary_date_gt_7d=1 |
| `股票数据/基础数据/ST股票列表/all.csv` | 2785 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/基础数据/沪深港通股票列表/all.csv` | 19713 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000001.SZ+平安银行.csv` | 8348 | 1 | ohlc_invariant_violation=1 |
| `股票数据/行情数据/历史日线/by_symbol/000002.SZ+万科Ａ.csv` | 8301 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000007.SZ+全新好.csv` | 7526 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000005.SZ+ST星源(退).csv` | 7168 | 1 | stale_primary_market_date_gt_45d=1 |
| `股票数据/行情数据/历史日线/by_symbol/000008.SZ+神州高铁.csv` | 7836 | 1 | stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `c00a50db1789a41108a9c682898cc2237e9a38405143a6c2beb0294e127785cd` | 189 | 1192592 | ohlc_invariant_violation=17, stale_primary_market_date_gt_45d=114 |
| `0e4aa3e43ff5f3a40cb3b206aeb322a9d6eb59fa2c590747aab1286af4c5f7af` | 1 | 5499 | - |
| `758f93ed59903d0d2b12c75c23c2d63e10d65c12c8a66523f2837d07ec18b257` | 1 | 13162 | future_primary_date_gt_7d=1 |
| `b00d11bb7b84900c2081aac06304c18ce0eeb3a98944d9ffcaefead22904af43` | 1 | 2785 | stale_primary_market_date_gt_45d=1 |
| `950fa13b61e9a440d1370fc3c0ce3815e430031347bd046b68beb48bdc268115` | 1 | 1017 | - |
| `6a3eb482ab90efced7296ee0e3567b4f9e2484bab836cae0491651f1645f589d` | 1 | 19713 | stale_primary_market_date_gt_45d=1 |
| `355d5a3aaf031db7f9b915b63bbe6d9a822866474f2c1082e46c99d8d501c13e` | 1 | 19737 | - |
| `e8d0e998dc593e0546a2323d9da549848a9034948dcaf85969d1ae672aea058d` | 1 | 6301 | - |
| `0295dec535693fc05b70e8d599713d5d17d43e17632c951fae0c4eff7644332b` | 1 | 4000 | invalid_date=625 |
| `5d75d232226f8ceb7ad818feef54a6612a7c760d2f60cae97e1449166fc9e232` | 1 | 192 | - |
| `b22ddf9025e0af2d884c1943ed16ab0e877be22d0261451dab854587cbd26c25` | 1 | 2002 | - |
| `4a816bb8ebbb6c24a89b28f8e98c9292825b232a7b9d7b456b75553488dd68ba` | 1 | 255830 | invalid_date=289, stale_primary_market_date_gt_45d=1 |
