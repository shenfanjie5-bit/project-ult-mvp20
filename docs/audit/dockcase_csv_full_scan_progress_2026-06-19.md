# DOCKCASE CSV full-row scan progress

- Generated: `2026-06-19T05:26:30+0800`
- Shards: `27`
- CSV files scanned: `160596` / `160596`
- Coverage ratio: `1.0`
- Rows scanned: `212621857`
- Row read errors: `0`
- Complete: `True`

## Issue Counts

- `duplicate_grain_key_sample`: 2491811
- `future_primary_date_gt_7d`: 8
- `high_empty_cell_ratio_signature`: 15188
- `index_by_symbol_bundle_mismatch`: 34631768
- `invalid_date`: 3990
- `invalid_numeric`: 118
- `invalid_ts_code`: 233330
- `no_sampled_rows`: 4
- `ohlc_invariant_violation`: 32038
- `sparse_columns_lt_5pct_non_empty`: 1012704
- `stale_primary_market_date_gt_45d`: 76722
- `zero_ohlc_no_trade_carry_forward`: 4448

## Shards

| Range | Files | Rows | Path |
|---|---:|---:|---|
| `0-199` | 200 | 1522830 | `docs/audit/dockcase_csv_full_scan_2026-06-19.json` |
| `200-399` | 200 | 1198204 | `docs/audit/dockcase_csv_full_scan_shard_000200_000399.json` |
| `400-599` | 200 | 855820 | `docs/audit/dockcase_csv_full_scan_shard_000400_000599.json` |
| `600-1599` | 1000 | 3448755 | `docs/audit/dockcase_csv_full_scan_shard_000600_001599.json` |
| `1600-3599` | 2000 | 5445437 | `docs/audit/dockcase_csv_full_scan_shard_001600_003599.json` |
| `3600-7599` | 4000 | 6956175 | `docs/audit/dockcase_csv_full_scan_shard_003600_007599.json` |
| `7600-15599` | 8000 | 2905079 | `docs/audit/dockcase_csv_full_scan_shard_007600_015599.json` |
| `15600-31599` | 16000 | 18914846 | `docs/audit/dockcase_csv_full_scan_shard_015600_031599.json` |
| `31600-63599` | 32000 | 673770 | `docs/audit/dockcase_csv_full_scan_shard_031600_063599.json` |
| `63600-93599` | 30000 | 8887851 | `docs/audit/dockcase_csv_full_scan_shard_063600_093599.json` |
| `93600-97405` | 3806 | 7735266 | `docs/audit/dockcase_csv_full_scan_shard_093600_097405.json` |
| `97406-97406` | 1 | 6021 | `docs/audit/dockcase_csv_full_scan_shard_097406_097406.json` |
| `97407-97407` | 1 | 6062 | `docs/audit/dockcase_csv_full_scan_shard_097407_097407.json` |
| `97408-97408` | 1 | 7111 | `docs/audit/dockcase_csv_full_scan_shard_097408_097408.json` |
| `97409-97508` | 100 | 337366 | `docs/audit/dockcase_csv_full_scan_shard_097409_097508.json` |
| `97509-98008` | 500 | 648740 | `docs/audit/dockcase_csv_full_scan_shard_097509_098008.json` |
| `98009-99008` | 1000 | 1440602 | `docs/audit/dockcase_csv_full_scan_shard_098009_099008.json` |
| `99009-100008` | 1000 | 1343582 | `docs/audit/dockcase_csv_full_scan_shard_099009_100008.json` |
| `100009-101008` | 1000 | 1204227 | `docs/audit/dockcase_csv_full_scan_shard_100009_101008.json` |
| `101009-102008` | 1000 | 1328610 | `docs/audit/dockcase_csv_full_scan_shard_101009_102008.json` |
| `102009-103040` | 1032 | 1022382 | `docs/audit/dockcase_csv_full_scan_shard_102009_103040.json` |
| `103041-113040` | 10000 | 9502084 | `docs/audit/dockcase_csv_full_scan_shard_103041_113040.json` |
| `113041-120262` | 7222 | 11054154 | `docs/audit/dockcase_csv_full_scan_shard_113041_120262.json` |
| `120263-139999` | 19737 | 122214184 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
| `140000-141803` | 1804 | 2439936 | `docs/audit/dockcase_csv_full_scan_shard_140000_141803.json` |
| `141804-159590` | 17787 | 349695 | `docs/audit/dockcase_csv_full_scan_shard_141804_159590.json` |
| `159591-160595` | 1005 | 1173068 | `docs/audit/dockcase_csv_full_scan_shard_159591_160595.json` |

## Top Issue Files

| Path | Issues | Source shard |
|---|---:|---|
| `股票数据/特色数据/每日筹码分布/by_symbol/000627.SZ+_ST天茂(退).csv` | 182967 | `docs/audit/dockcase_csv_full_scan_shard_093600_097405.json` |
| `股票数据/特色数据/每日筹码分布/by_symbol/600225.SH+退市卓朗(退).csv` | 177208 | `docs/audit/dockcase_csv_full_scan_shard_093600_097405.json` |
| `股票数据/特色数据/每日筹码分布/by_symbol/600387.SH+退市海越(退).csv` | 168184 | `docs/audit/dockcase_csv_full_scan_shard_093600_097405.json` |
| `股票数据/特色数据/每日筹码分布/by_symbol/002336.SZ+人乐退(退).csv` | 164967 | `docs/audit/dockcase_csv_full_scan_shard_093600_097405.json` |
| `股票数据/特色数据/每日筹码分布/by_symbol/000851.SZ+_ST高鸿(退).csv` | 148364 | `docs/audit/dockcase_csv_full_scan_shard_093600_097405.json` |
| `股票数据/特色数据/每日筹码分布/by_symbol/000584.SZ+工智退(退).csv` | 146655 | `docs/audit/dockcase_csv_full_scan_shard_093600_097405.json` |
| `股票数据/特色数据/每日筹码分布/by_symbol/300379.SZ+东通退(退).csv` | 141707 | `docs/audit/dockcase_csv_full_scan_shard_093600_097405.json` |
| `指数专题/国际主要指数/by_symbol/652689.MI+MSCI金砖四国中盘价值.csv` | 141230 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
| `指数专题/国际主要指数/by_symbol/000002.SH+A股指数.csv` | 141230 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
| `指数专题/国际主要指数/by_symbol/000002.CJ+原材料(长江).csv` | 141230 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
| `指数专题/国际主要指数/by_symbol/133707.MI+MSCI阿拉伯市场.csv` | 141230 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
| `指数专题/国际主要指数/by_symbol/000001.CJ+能源(长江).csv` | 141230 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
| `指数专题/国际主要指数/by_symbol/652692.MI+MSCI哥伦比亚中盘价值.csv` | 141230 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
| `指数专题/国际主要指数/by_symbol/000001.SH+上证指数.csv` | 141230 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
| `指数专题/国际主要指数/by_symbol/652690.MI+MSCI智利中盘价值.csv` | 141230 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
| `指数专题/国际主要指数/by_symbol/652691.MI+MSCI中国中盘价值.csv` | 141230 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
| `指数专题/国际主要指数/by_symbol/861207.CJ+沪深300成长（长江）.csv` | 141230 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
| `指数专题/国际主要指数/by_symbol/861205.CJ+双创成长动量(长江).csv` | 141230 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
| `指数专题/国际主要指数/by_symbol/861206.CJ+双创成长反转(长江).csv` | 141230 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
| `指数专题/国际主要指数/by_symbol/133638.MI+MSCI中国A股_独立电力生产与能源贸易商.csv` | 141230 | `docs/audit/dockcase_csv_full_scan_shard_120263_139999.json` |
