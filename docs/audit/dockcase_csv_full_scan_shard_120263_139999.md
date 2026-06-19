# DOCKCASE CSV full-row semantic scan

- Generated: `2026-06-19T05:20:44+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_selected_business_csv_full_row_semantics`
- Elapsed: `1406.283` seconds
- CSV files scanned: `19737`
- Rows scanned: `122214184`
- Header signatures: `16`
- Header read errors: `0`
- Row read errors: `0`
- Full row semantic scan: `False`

## Coverage Boundary

| Boundary | Value |
|---|---:|
| `all_business_csv_files_selected` | `False` |
| `all_selected_files_read_to_eof` | `True` |
| `full_row_semantic_scan` | `False` |
| `max_files_limit` | `19737` |
| `skip_files` | `120263` |

## Issue Counts

- `index_by_symbol_bundle_mismatch`: 34631768
- `invalid_ts_code`: 120
- `ohlc_invariant_violation`: 29793
- `sparse_columns_lt_5pct_non_empty`: 13681
- `stale_primary_market_date_gt_45d`: 6076
- `zero_ohlc_no_trade_carry_forward`: 12

## Domain Issue Counts

- `index_by_symbol_bundle_mismatch`: 34631768
- `ohlc_invariant_violation`: 29793
- `zero_ohlc_no_trade_carry_forward`: 12

## Top Issue Files

| Path | Rows | Issue total | Issues |
|---|---:|---:|---|
| `指数专题/国际主要指数/by_symbol/652689.MI+MSCI金砖四国中盘价值.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/000002.SH+A股指数.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/000002.CJ+原材料(长江).csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/133707.MI+MSCI阿拉伯市场.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/000001.CJ+能源(长江).csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/652692.MI+MSCI哥伦比亚中盘价值.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/000001.SH+上证指数.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/652690.MI+MSCI智利中盘价值.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/652691.MI+MSCI中国中盘价值.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/861207.CJ+沪深300成长（长江）.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/861205.CJ+双创成长动量(长江).csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/861206.CJ+双创成长反转(长江).csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/133638.MI+MSCI中国A股_独立电力生产与能源贸易商.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/861208.CJ+沪深300成长动量（长江）.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/133625.MI+MSCI中国A股在岸_综合消费者服务.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/932069CNY210.CSI+港股通医疗主题(全)CNY.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/133625L.MI+MSCI中国A股在岸_综合消费者服务(人民币).csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/932070.CSI+北银理财北京科技领先.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/932070CNY01.CSI+北银理财北京科技领先全收益.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |
| `指数专题/国际主要指数/by_symbol/932071.CSI+SSH煤炭.csv` | 140213 | 141230 | index_by_symbol_bundle_mismatch=140213, ohlc_invariant_violation=1016, stale_primary_market_date_gt_45d=1 |

## Top Header Signatures

| SHA-256 | Files | Rows scanned | Issues |
|---|---:|---:|---|
| `4796da88dc65926c3358735d28406f3dc68dffc732964dc8d6fbdb87e92537db` | 13656 | 41320048 | sparse_columns_lt_5pct_non_empty=13656 |
| `ea41873008e76172daf1366e99f658a8fcf6b9bb7abcff83e2467a915e333738` | 4529 | 43803932 | stale_primary_market_date_gt_45d=4529 |
| `11908695cc41786a22ec4236f12db766f24e56b16cf9479f9f7e7dc1b248f340` | 915 | 1229805 | sparse_columns_lt_5pct_non_empty=24, stale_primary_market_date_gt_45d=915 |
| `babb7a89817667592b8bdbbf0abfd2bd2f17223d7c3e46e8119a0063142eb506` | 230 | 167137 | ohlc_invariant_violation=1, stale_primary_market_date_gt_45d=230, zero_ohlc_no_trade_carry_forward=12 |
| `8ee1d0c6625fe0eae4b7c3d2dd954636f5f36c592bef942d56ac73a23c074915` | 192 | 21326016 | index_by_symbol_bundle_mismatch=21326016, ohlc_invariant_violation=1344, stale_primary_market_date_gt_45d=192 |
| `92eecfa50dda084f2ed456c74c8dfc06a6c0802df31372f390caa1fec97ac41b` | 132 | 9379788 | index_by_symbol_bundle_mismatch=9379788, stale_primary_market_date_gt_45d=132 |
| `c3add1f07845e9230cbb05d96f3a04eff1ee7ebd1d63bd21b7614a92c9a00324` | 28 | 3925964 | index_by_symbol_bundle_mismatch=3925964, ohlc_invariant_violation=28448, stale_primary_market_date_gt_45d=28 |
| `797978f9999a1c57930090c01f7522b7cf8071cd9e42e8fdfd521cc8fe21e774` | 24 | 28341 | stale_primary_market_date_gt_45d=24 |
| `f969dd2ca3129fcfaa3e292c06a25fde86c15d6cd6459056aa60a1c1eaf76a2a` | 21 | 19531 | stale_primary_market_date_gt_45d=21 |
| `90cd2c5e8a3680ef8c8c4aae0c1d09243b0f0e4bea75f7937040c68f43b0f07f` | 4 | 5836 | stale_primary_market_date_gt_45d=4 |
| `9b2dce55d0fab7658beb483af53a26db062afcec2db50e23b98ecc9c8c925e84` | 1 | 885695 | stale_primary_market_date_gt_45d=1 |
| `a86c7f94b01f12ba37ece4fffd302eff3d6cd8a05c8fccacebebf7fb548d53fb` | 1 | 3235 | - |
| `72a48202a5afb133315e4e4d6152205da2cde7a6d69eaef41949b995b0ea8f6b` | 1 | 1495 | invalid_ts_code=1 |
| `69f6360ee769d2c6f54a950aa26bcba6c6fe11bedd3711b65545efc7d35cab6f` | 1 | 103464 | - |
| `3ffb1fd0488e1c791755aab60d738c3939a7a3395a2fdb38a1ca546526ab4840` | 1 | 13538 | invalid_ts_code=119 |
| `8083a4d637d512fcd54b0ddb0906b85ffea7addbd7dd67b5d2bcce512231e7dd` | 1 | 359 | sparse_columns_lt_5pct_non_empty=1 |
