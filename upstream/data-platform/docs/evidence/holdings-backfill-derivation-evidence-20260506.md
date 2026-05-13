# Holdings backfill and derivation evidence - 2026-05-06

## Scope

- Module: `data-platform`
- Source commit under test: `32289f14252d530fab6cc1aed46c2f0cd5b7c39e`
  (`main`, PR2 derivation marts)
- Prior backfill orchestration commit:
  `9629604dae9ed64dafd4d6c223e8b89941f6ad72`
- Evidence type: curated holdings backfill plan dry run, live backfill gate
  status, local derivation mart dbt run/test summary, and docs update.
- Secret handling: no `.env`, token values, DSNs, concrete TS codes, concrete
  fund codes, raw provider payloads, dbt logs, `target/`, or runtime transcripts
  are recorded here.

## Backfill Plan Dry Run

Command shape:

```bash
# token/code inputs redacted; command ran plan-only with bounded inputs
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
  --max-plan-items 10
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

The dry run covered all five holdings interfaces with bounded inputs only.
Provider identifiers were redacted from this evidence and the public plan
summary only exposed identifier class/count.

## Live Backfill Gate Status

Live backfill was not executed.

Environment status observed in the local shell:

- `DP_TUSHARE_TOKEN=SET/redacted`

Live backfill blocker observed in the local shell:

- `DP_TUSHARE_LIVE_HOLDINGS_BACKFILL missing`

The live path remains explicit opt-in only. With the token set, operators must
still set `DP_TUSHARE_LIVE_HOLDINGS_BACKFILL`, pass `--execute-live` plus
explicit Raw Zone and warehouse paths, and commit only curated execution
summaries.

## Derivation Mart Evidence

Fixture shape:

- Local DuckDB profile/database under `<temporary-profile-dir>`.
- Provider-neutral canonical input tables only:
  `mart_fact_holding_position_v2` and
  `mart_lineage_fact_holding_position`.
- Fixture identifiers used generic security/holder names, not provider TS
  codes or fund codes.
- No raw provider payloads, dbt logs, or dbt target artifacts were committed.

dbt command shapes:

```bash
./scripts/dbt.sh parse --profiles-dir <temporary-profile-dir> --target-path <temporary-target-dir> --log-path <temporary-log-dir> --no-use-colors
./scripts/dbt.sh run --profiles-dir <temporary-profile-dir> --target-path <temporary-target-dir> --log-path <temporary-log-dir> \
  --select path:models/marts_derivations path:models/marts_derivation_lineage --no-use-colors
./scripts/dbt.sh test --profiles-dir <temporary-profile-dir> --target-path <temporary-target-dir> --log-path <temporary-log-dir> \
  --select path:models/marts_derivations path:models/marts_derivation_lineage --no-use-colors
```

Curated dbt result:

| Check | Result |
|---|---|
| `dbt parse` | passed |
| `dbt run` | passed, 6 table models built |
| `dbt test` | passed, 72 tests passed |

Row counts and lineage pairing:

| Model | Rows | Lineage parity |
|---|---:|---|
| `mart_deriv_top_holder_qoq_change` | 2 | key diff with lineage = 0 |
| `mart_deriv_lineage_top_holder_qoq_change` | 2 | paired to business mart |
| `mart_deriv_fund_co_holding` | 3 | key diff with lineage = 0 |
| `mart_deriv_lineage_fund_co_holding` | 3 | paired to business mart |
| `mart_deriv_northbound_holding_z_score` | 6 | key diff with lineage = 0 |
| `mart_deriv_lineage_northbound_holding_z_score` | 6 | paired to business mart |

Provider-neutral guard:

- Business derivation marts read from canonical `mart_fact_holding_position_v2`
  via `ref`, not staging/raw models.
- Provider-shaped identifiers and lineage columns stay out of the business
  derivation marts.
- Lineage marts keep source attribution in the paired lineage namespace.

## Hygiene Notes

- No `.env`, token, DSN, concrete TS code, concrete fund code, raw response,
  dbt log, `target/`, or local absolute temp path is committed by this PR.
- Environment status is recorded only as exact missing variable names or
  `SET/redacted` style statements.
- `hsgt_hold_top10` remains fail-closed after the 2024-08-20 publication
  cutoff: post-cutoff live daily refresh/backfill dates must skip instead of
  writing empty current-date Raw artifacts.
