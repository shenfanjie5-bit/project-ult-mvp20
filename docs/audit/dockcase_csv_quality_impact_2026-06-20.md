# DOCKCASE CSV quality impact audit

- Generated: `2026-06-20T02:31:29+08:00`
- CSV scan coverage: `160596` / `160596` (1.0)
- Rows scanned: `212621857`
- Read/shape errors: `0`
- Current-MVP data-quality actionable gaps: `0`
- Watchlist issue types: `6`
- Non-blocking issue types: `6`
- Score mutation: `none; this audit classifies existing full-scan evidence only`

## Issues

| Issue | Count | Impact | Scope |
|---|---:|---|---|
| `duplicate_grain_key_sample` | 2491811 | `current_mvp_non_blocking` | raw_csv_history |
| `future_primary_date_gt_7d` | 8 | `watchlist` | raw_date_cells |
| `high_empty_cell_ratio_signature` | 15188 | `current_mvp_non_blocking` | wide_optional_tables |
| `index_by_symbol_bundle_mismatch` | 34631768 | `current_mvp_non_blocking` | index_bundle_metadata |
| `invalid_date` | 3990 | `watchlist` | raw_date_cells |
| `invalid_numeric` | 118 | `watchlist` | raw_numeric_cells |
| `invalid_ts_code` | 233330 | `current_mvp_non_blocking` | non_equity_or_legacy_symbols |
| `no_sampled_rows` | 4 | `current_mvp_non_blocking` | header_only_files |
| `ohlc_invariant_violation` | 32038 | `watchlist` | historical_market_bars |
| `sparse_columns_lt_5pct_non_empty` | 1012704 | `current_mvp_non_blocking` | optional_statement_columns |
| `stale_primary_market_date_gt_45d` | 76722 | `watchlist` | inactive_or_legacy_files |
| `zero_ohlc_no_trade_carry_forward` | 4448 | `watchlist` | historical_market_bars |
