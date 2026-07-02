# AKShare CLS refresh check

- Generated: `2026-06-19T02:02:55+08:00`
- Status: `direct_cls_web_api_valid_rows`
- Purpose: verify whether the A-share CLS media/report fields can refresh from real current CLS data and enter the score path.

## Result

The legacy AKShare `stock_info_global_cls` wrapper is stale: it still points at `https://www.cls.cn/nodeapi/telegraphList`, which currently returns 404 HTML or times out. The current cls.cn web page loads signed JSON from `/v1/roll/get_roll_list`, so the collector now tries that signed endpoint first and keeps `stock_info_global_cls` as a legacy fallback.

| Check | Result |
|---|---|
| Legacy endpoint probe | `/nodeapi/telegraphList` returned HTTP 404 HTML, not JSON. |
| Signed web API probe | `/v1/roll/get_roll_list` returned `errno=0` with 20 `roll_data` rows in about 1.3 seconds. |
| Focused collector retry | `AKSHARE_CALL_TIMEOUT_S=30 .venv/bin/python scripts/collector.py --source akshare-cls --max-cycles 1` completed in about 2 seconds and upserted three `Known` rows. |
| Known/Proxy rows | `3` |
| Latest database write | Three `MARKET:CN` rows were upserted as `Known`. |

## Rows

| dp_id | Status | count_24h | Score payload |
|---|---|---:|---|
| `L9.media.report` | `Known` | 20 | `positive_media_count=1`, `negative_media_count=0`, `net_media_score=1` |
| `L9.industry.policy_change` | `Known` | 6 | `positive_policy_count=1`, `negative_policy_count=2`, `net_policy_score=-1` |
| `L9.industry.compete_risk` | `Known` | 3 | `event_active=true` |

## Interpretation

`L9.media.report`, `L9.industry.policy_change`, and `L9.industry.compete_risk` now have both valid runtime rows and bounded score formulas. This raised effective A-share score-path dp_ids from 116 to 119, reduced participating gaps from 58 to 55, reduced actionable participating gaps from 37 to 34, and cleared `conditional_formula_ready_pending_valid_data_dp_ids`.

The safe retry path is the dedicated `--source akshare-cls` collector path, not the full `--source akshare` collector, because full AKShare also attempts per-stock news calls.
