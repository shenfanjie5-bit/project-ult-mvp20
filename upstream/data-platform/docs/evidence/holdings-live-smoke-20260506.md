# Holdings live smoke evidence - 2026-05-06

## Scope

- Module: `data-platform`
- Source commit under test: `0192dbc72222fb32062d944b6bbea75f53d3c159`
  (`main`, PR #100 merge; includes PR #99 merge
  `8e43608e496adaad228d3259f760db303637c95e`)
- Evidence type: live Tushare holdings smoke plus daily cutoff regression tests
- Secret handling: environment was loaded out-of-band. Token status was
  `SET/redacted`; configured TS code scope was `SET/redacted`. No secret
  values, provider responses, or runtime transcripts are recorded here.

## Commands

Command shape for the live holdings smoke:

```bash
# environment loaded out-of-band; token=SET/redacted; ts_code_scope=SET/redacted
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../contracts/src \
  .venv/bin/python -m pytest -p no:cacheprovider \
  tests/adapters/test_tushare_holdings.py::test_live_tushare_holdings_smoke_requires_token \
  -q -rs
```

Command shape for the daily cutoff checks:

```bash
# environment loaded out-of-band; token=SET/redacted; ts_code_scope=SET/redacted
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:../contracts/src \
  .venv/bin/python -m pytest -p no:cacheprovider \
  tests/integration/test_daily_refresh.py::test_live_hk_hold_daily_refresh_skips_after_publication_cutoff \
  tests/integration/test_daily_refresh.py::test_hk_hold_daily_refresh_cutoff_keeps_last_publication_date_live \
  tests/integration/test_daily_refresh.py::test_hk_hold_skip_plan_makes_full_live_refresh_partial_after_cutoff \
  -q -rs
```

## Result Summary

Live holdings smoke result: passed, 1 selected pytest test passed, 0 skipped,
0 failed.

Interface coverage:

| Interface | Data-platform dataset | Result |
|---|---|---|
| `top10_holders` | `top10_holders` | passed |
| `top10_floatholders` | `top10_floatholders` | passed |
| `fund_portfolio` | `fund_portfolio` | passed |
| `hsgt_top10` | `hsgt_top10` | passed |
| `hk_hold` | `hsgt_hold_top10` | passed |

Daily cutoff result: passed, 3 selected pytest tests passed, 0 skipped,
0 failed.

## Date Selection

The live smoke uses `20240402` for `hsgt_top10` and `hsgt_hold_top10`
because those endpoints are trade-date based and need a known historical
publication date with rows. The date is after the 2024 Q1 report period used
by the other holdings smoke parameters and before the `hk_hold` daily
northbound publication cutoff. This proves the live endpoint path without
claiming current daily freshness for `hsgt_hold_top10`.

## Daily Cutoff Expectation

Tushare `hk_hold` daily northbound publication stopped after `2024-08-20`.
For post-cutoff daily refreshes, `hsgt_hold_top10` must be skipped with an
explicit `daily_publication_discontinued` reason. The skip is fail-closed:
no current-date Raw artifact is written and the refresh does not claim daily
live freshness. The last publication date, `2024-08-20`, remains eligible for
live refresh.

The cutoff regression tests covered:

- post-cutoff live daily refresh skips `hsgt_hold_top10`
- `2024-08-20` remains live while `2024-08-21` is skipped
- full live refresh after the cutoff becomes partial and excludes
  `hsgt_hold_top10` from the active asset plan

## Noise And Secret Controls

- No provider response payloads were copied into this repository.
- No runtime transcript artifact was committed.
- No local environment file was committed.
- No secret values are present in this evidence.
