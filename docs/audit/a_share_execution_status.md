# A-share Execution Status

Generated on 2026-05-27.

## What Ran

1. `TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare --max-cycles 1`
   - Result: interrupted after the slow full Tushare batch exceeded the
     useful wait window.
   - Observed failures: remote Tushare read timeouts on per-stock financial
     endpoints such as `balancesheet` / `income`.
   - No complete batch upsert from this command.

2. `.venv/bin/python scripts/collector.py --source tushare-core --max-cycles 1`
   - Result: completed.
   - Rows upserted: 576.
   - Purpose: fast A-share market/flow refresh only, before the slow
     financial/report endpoints.

3. `.venv/bin/python -m mvp20.cli derive-snapshot --db runtime/hot.sqlite`
   - Result: completed.
   - Companies processed: 328.
   - Rows emitted: 9493.

4. `.venv/bin/python scripts/check_a_share_spec_completion.py`
   - Result: completed and regenerated the A-share report.

5. `TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-market-env --max-cycles 1`
   - Result: completed.
   - Rows upserted: 2.
   - Purpose: market-level A-share environment sentinel refresh.

6. `TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-crowding --max-cycles 1`
   - Result: completed.
   - Rows upserted: 116.
   - Purpose: low-frequency A-share turnover-history crowdedness refresh.

7. `TUSHARE_TIMEOUT_SECONDS=3 .venv/bin/python scripts/collector.py --source tushare-report-rc --max-cycles 1`
   - Result: completed.
   - Rows upserted: 464.
   - Purpose: focused A-share sell-side forecast/report refresh.

## Current A-share Completion

| metric | before core refresh | after core refresh | current |
|---|---:|---:|---:|
| effective runtime real-source dp_ids | 111 / 250 | 115 / 250 | 121 / 250 |
| compiled overlay dp_ids | 66 / 250 | 66 / 250 | 66 / 250 |
| combined real A-share dp_ids | 175 / 250 | 179 / 250 | 185 / 250 |
| remaining gaps | 75 | 71 | 65 |
| mock-only effective runtime dp_ids | 10 | 6 | 4 |

## Fields Fixed by `tushare-core`

| dp_id | current real source |
|---|---|
| `L6.mult.pe` | `tushare:daily_basic` |
| `L6.mult.pb` | `tushare:daily_basic` |
| `L7.trade.volume_turnover` | `tushare:daily_basic` |
| `L7.flow.active_inflow` | `tushare:moneyflow` |

## Fields Fixed by derive / focused Tushare

| dp_id | current real source |
|---|---|
| `L11.trade.signal` | `derive:l11_trade_signal` |
| `L7.env.market_trend` | `tushare:index_daily` (`MARKET:CN` sentinel) |
| `L6.priced.crowdedness` | `tushare:daily_basic.history` |
| `L5.fcst.revenue_margin` | `tushare:report_rc` |
| `L5.fcst.eps_cf` | `tushare:report_rc` |
| `L5.fcst.revisions` | `tushare:report_rc.derived` |

## Still Mock-only

| dp_id | current mock source | next action |
|---|---|---|
| `L7.flow.passive_northbound` | `mock:tushare` | Replace per-stock rows with `hk_hold` when available, or mark unavailable/derive from valid sentinel/proxy. |
| `L7.mood.media_social` | `mock:akshare` | Replace with bounded real AKShare/Tushare hot-list snapshots. |
| `L7.mood.theme` | `mock:akshare` | Replace with bounded real AKShare/Tushare hot-list snapshots. |
| `L9.media.social_buzz` | `mock:akshare` | Replace with bounded real AKShare/Tushare hot-list snapshots. |

## Operational Notes

- `tushare-core` is intentionally narrow. It provides a reliable fast path for
  market/flow rows while the full Tushare source remains available for deeper
  financial/report rows.
- Full `--source tushare` should be refactored into staged upserts before it is
  used as an unattended refresh path. The current implementation still holds
  earlier successful rows in memory until all later per-stock sections finish.
