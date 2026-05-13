# Holdings live backfill producer-input proof - 2026-05-07

## Scope

- Module: `data-platform`
- Source commit under test: `b83a82ddadacac2d9bfdef7d5847710731e5cb1e`
  (`main`, PR #105 merge commit)
- Evidence type: bounded live holdings backfill preflight, plan-only proof,
  live execution blocker, and downstream mart/producer-input status.
- Secret handling: no token values, DSNs, concrete stock codes, concrete fund
  codes, raw provider payloads, dbt logs, target artifacts, or local runtime
  paths are recorded here.

## Boundary

This evidence is limited to:

- `data-platform` bounded holdings Raw Zone backfill planning.
- Intended downstream path from Raw Zone holdings inputs into DuckDB holdings
  marts and lineage.
- Intended read-only producer-input boundary for `subsystem-holdings`.

This evidence does not claim production queue behavior, live graph propagation,
graph-engine #55 behavior, contracts subtype changes, or financial-doc/M4.7
behavior.

## Repo And Env Preflight

- `data-platform` was on `main` with PR #105 merge commit
  `b83a82ddadacac2d9bfdef7d5847710731e5cb1e` present.
- `subsystem-holdings` was on `main` with PR #6 merge commit
  `362ad8c91a0e46070aa02ed4530e291b7bc1af41` present.
- Both working trees were clean before evidence edits.
- `DP_TUSHARE_TOKEN=SET/redacted`.
- `DP_TUSHARE_LIVE_HOLDINGS_BACKFILL` was intentionally set only for the live
  backfill command.

## Bounded Inputs

The proof used one bounded value for each required input class:

| Input class | Evidence value |
|---|---|
| A-share stock code | `<redacted-stock-code>` |
| Fund code | `<redacted-fund-code>` |
| Report period | `<redacted-report-period>` |
| Historical HSGT trade date | `<historical-hsgt-date>` |
| Market type | `<bounded-market-type>` |
| Exchange | `<bounded-exchange>` |

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
  --trade-date '<historical-hsgt-date>' \
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

## Live Backfill Blocker

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
  --trade-date '<historical-hsgt-date>' \
  --market-type '<bounded-market-type>' \
  --exchange '<bounded-exchange>' \
  --max-plan-items 10 \
  --execute-live \
  --raw-zone-path '<runtime-raw-zone>' \
  --iceberg-warehouse-path '<runtime-warehouse>' \
  --json-report '<runtime-report>'
```

Exact blocker:

- `AdapterFetchError`
- Provider fetch failed for `source_id='tushare'`,
  `asset_id='tushare_top10_holders'`.
- Error summary: `HTTPConnectionPool(host='api.waditu.com', port=80): Read
  timed out. (read timeout=30)`.

Retry notes:

- The same-session proof made a bounded retry and then a clean rerun with one
  bounded stock-scope change.
- One same-session attempt reached `hsgt_top10` but returned an empty provider
  table before a complete five-dataset execution summary could be produced.
- The clean rerun still blocked at `tushare_top10_holders` with the timeout
  above.

Because the live backfill did not complete, there is no complete live
execution summary, no complete Raw Zone holdings input set, and no curated row
count to promote into DuckDB mart proof.

## Downstream Status

DuckDB marts were not built from live holdings inputs in this proof. The seven
required downstream tables therefore remain unproven for this live run:

- `mart_fact_holding_position_v2`
- `mart_deriv_top_holder_qoq_change`
- `mart_deriv_fund_co_holding`
- `mart_deriv_northbound_holding_z_score`
- `mart_deriv_lineage_top_holder_qoq_change`
- `mart_deriv_lineage_fund_co_holding`
- `mart_deriv_lineage_northbound_holding_z_score`

Lineage parity checks, row counts, and producer payload construction were not
claimed because the upstream bounded live backfill was blocked.

## Result

Status: `BLOCKED`.

The blocker is external to the local live gate and token preflight: bounded
provider fetches did not complete reliably enough to produce the required
five-dataset live holdings input set. No production queue, live graph
propagation, contracts subtype, graph-engine #55, or financial-doc/M4.7 claim
is made.
