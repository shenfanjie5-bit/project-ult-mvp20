# A-share data semantic audit

- Generated at: `2026-06-18T04:25:25+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `bounded_a_share_semantic_rows`
- Symbols: `000001.SZ, 300750.SZ, 600519.SH`
- Max rows per file: `0`

## Summary

| Metric | Value |
|---|---:|
| `dataset_count` | `6` |
| `ok_dataset_count` | `2` |
| `review_dataset_count` | `4` |
| `total_rows_read` | `40007` |
| `total_files_loaded` | `14` |
| `total_issues` | `6` |
| `severity_counts` | `{'P2': 6}` |

## Dataset results

| Dataset | Status | Files | Rows | Missing columns | Complete ratio | Freshness lag | Issues |
|---|---|---:|---:|---|---:|---:|---|
| A-share stock list | `review` | 1 | 5499 |  | 0.999636 |  | required_value_gaps |
| A-share historical daily OHLCV | `ok` | 3 | 16185 |  | 1.0 | 13 |  |
| A-share income statement | `review` | 3 | 217 |  | 0.843318 | 54 | required_value_gaps, duplicate_key_rows, freshness_lag_gt_30d |
| A-share individual money flow | `ok` | 3 | 6936 |  | 1.0 | 13 |  |
| Sell-side broker forecast | `review` | 3 | 2585 |  | 0.326112 | 20 | required_value_gaps |
| Index daily OHLCV | `review` | 1 | 8585 |  | 1.0 | 125 | freshness_lag_gt_30d |

## Notes

- This audit reads real rows for selected high-value A-share sources. It is stronger than header-only cataloging, but it is still bounded sampling, not a full semantic review of every CSV row.
- Review-status datasets are not automatically unusable; they indicate missing files, stale sampled data, duplicate keys, invalid values, or required-field sparsity that should be interpreted per source.
