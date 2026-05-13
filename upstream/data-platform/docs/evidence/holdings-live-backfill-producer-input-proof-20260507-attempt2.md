# Holdings live backfill producer-input proof - 2026-05-07 attempt2

## Scope

- Module: `data-platform`
- Source commit under test: `74ea60aef4cbee644e2a871bb7b3df6c87a8dbc7`
  (`main` at proof time)
- Evidence type: bounded live holdings Raw Zone backfill, downstream DuckDB
  holdings mart build/test, lineage parity, and curated producer-input readiness
  evidence for `subsystem-holdings`.
- Supersedes: the earlier 2026-05-07 provider-timeout blocker evidence for
  the same holdings live backfill and producer-input proof goal.
- Secret handling: no token values, DSNs, concrete stock codes, concrete fund
  codes, raw provider payloads, dbt logs, target artifacts, or local runtime
  paths are recorded here.

## Boundary

This evidence is limited to:

- `data-platform` bounded holdings live backfill using redacted bounded inputs.
- Raw Zone holdings artifacts produced by the command-scoped live gate.
- DuckDB holdings marts and lineage models built from the resulting inputs.
- Curated, read-only producer-input readiness evidence for
  `subsystem-holdings`.

This evidence does not claim production queue behavior, live graph propagation,
graph-engine #55 behavior, contracts subtype changes, or financial-doc/M4.7
behavior.

## Live Gate And Inputs

- `DP_TUSHARE_TOKEN=SET/redacted`.
- `DP_TUSHARE_LIVE_HOLDINGS_BACKFILL=1` was scoped to the live backfill
  command invocation only.
- No permanent `.env` change was made or required by this evidence.
- Bounded inputs included one redacted stock code, one redacted fund code, one
  redacted report period, one redacted historical HSGT trade date, one bounded
  market type, and one bounded exchange.

No concrete provider identifiers are recorded in this evidence.

## Plan-Only Backfill

Command shape:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../contracts/src \
  .venv/bin/python scripts/holdings_backfill.py \
  --dataset top10_holders \
  --dataset top10_floatholders \
  --dataset fund_portfolio \
  --dataset hsgt_top10 \
  --dataset hsgt_hold_top10 \
  --stock-code '<redacted-stock-code>' \
  --fund-code '<redacted-fund-code>' \
  --period '<redacted-report-period>' \
  --trade-date '<redacted-historical-hsgt-date>' \
  --market-type '<bounded-market-type>' \
  --exchange '<bounded-exchange>' \
  --max-plan-items 10 \
  --json-report '<runtime-report>'
```

Curated result:

| Dataset | Status | Partition basis | Bound summary |
|---|---|---|---|
| `top10_holders` | planned | report period | `stock_code_class=stock_code`, `stock_code_count=1` |
| `top10_floatholders` | planned | report period | `stock_code_class=stock_code`, `stock_code_count=1` |
| `fund_portfolio` | planned | report period | `fund_code_class=fund_code`, `fund_code_count=1` |
| `hsgt_top10` | planned | historical trade date | `stock_code_class=stock_code`, `stock_code_count=1`, bounded `market_type` |
| `hsgt_hold_top10` | planned | historical trade date | `stock_code_class=stock_code`, `stock_code_count=1`, bounded `exchange` |

Summary: `ok=true`, `planned_count=5`, `skipped_count=0`,
`rejected_count=0`, `max_plan_items=10`, `execute_live=false`.

## Live Backfill

Command shape:

```bash
DP_TUSHARE_LIVE_HOLDINGS_BACKFILL=1 \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../contracts/src \
  .venv/bin/python scripts/holdings_backfill.py \
  --dataset top10_holders \
  --dataset top10_floatholders \
  --dataset fund_portfolio \
  --dataset hsgt_top10 \
  --dataset hsgt_hold_top10 \
  --stock-code '<redacted-stock-code>' \
  --fund-code '<redacted-fund-code>' \
  --period '<redacted-report-period>' \
  --trade-date '<redacted-historical-hsgt-date>' \
  --market-type '<bounded-market-type>' \
  --exchange '<bounded-exchange>' \
  --max-plan-items 10 \
  --execute-live \
  --raw-zone-path '<runtime-raw-zone>' \
  --iceberg-warehouse-path '<runtime-warehouse>' \
  --json-report '<runtime-report>'
```

Curated result:

| Dataset | Status | Rows |
|---|---|---:|
| `top10_holders` | ok | 10 |
| `top10_floatholders` | ok | 10 |
| `fund_portfolio` | ok | 10 |
| `hsgt_top10` | ok | 1 |
| `hsgt_hold_top10` | ok | 1 |

Summary: `execution.ok=true`, `artifact_count=5`, `row_count=32`.

## Mart And Lineage Build

Command shapes:

```bash
./scripts/dbt.sh run \
  --profiles-dir '<runtime-profiles-dir>' \
  --target-path '<runtime-target-dir>' \
  --log-path '<runtime-log-dir>' \
  --select '<holdings-mart-and-lineage-selectors>' \
  --no-use-colors

./scripts/dbt.sh test \
  --profiles-dir '<runtime-profiles-dir>' \
  --target-path '<runtime-target-dir>' \
  --log-path '<runtime-log-dir>' \
  --select '<holdings-mart-and-lineage-selectors>' \
  --no-use-colors
```

Curated dbt result:

| Check | Result |
|---|---|
| `dbt run` | passed, 12 successes |
| `dbt test` | passed, 118 tests passed |

DuckDB table presence and row counts:

| Table | Rows |
|---|---:|
| `mart_fact_holding_position_v2` | 36 |
| `mart_deriv_top_holder_qoq_change` | 20 |
| `mart_deriv_fund_co_holding` | 45 |
| `mart_deriv_northbound_holding_z_score` | 10 |
| `mart_deriv_lineage_top_holder_qoq_change` | 20 |
| `mart_deriv_lineage_fund_co_holding` | 45 |
| `mart_deriv_lineage_northbound_holding_z_score` | 10 |

Validation summary:

- Seven required DuckDB tables were present and non-empty.
- Required columns missing: `0`.
- Lineage row counts paired with the business derivation marts:
  `20`, `45`, and `10`.
- Lineage parity: `0` key differences for all three business/lineage pairs.

## Producer-Input Boundary

The live backfill and marts produced the curated holdings datasets needed as
read-only producer inputs for downstream holdings consumers. This proof stops
at producer-input readiness:

- No production queue enqueue/dequeue behavior is claimed.
- No live graph propagation is claimed.
- No graph-engine #55 behavior is claimed.
- No contracts subtype change or compatibility claim is made.
- No raw provider payloads or concrete provider identifiers are recorded.

## Result

Status: `PASS`.

Attempt2 completed the bounded live holdings backfill and downstream
mart/lineage proof. The earlier provider-timeout blocker is superseded for the
data-platform live backfill plus mart/lineage producer-input evidence scope
described above.
