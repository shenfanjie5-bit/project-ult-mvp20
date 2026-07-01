# A-share update health audit

- Generated at: `2026-06-25 00:05:12.542237`
- Expected trade date: `20260624`
- Universe: `1641` A-share overlay stocks
- Overall status: `pass_with_known_limitations`

## DockCase by-symbol coverage

| endpoint | current count | coverage | not current | missing files | read errors |
|---|---:|---:|---:|---:|---:|
| `daily` | 1640 | 99.94% | 1 | 0 | 0 |
| `daily_basic` | 1640 | 99.94% | 1 | 0 | 0 |
| `moneyflow` | 1630 | 99.33% | 11 | 7 | 0 |

## hot.sqlite critical dp coverage

| dp_id | rows | missing | status counts | payload dates | max updated |
|---|---:|---:|---|---|---|
| `L6.mult.pb` | 1641 | 0 | `{'Known': 1641}` | `{'20260624': 1640, '20260610': 1}` | `2026-06-24 22:40:10` |
| `L6.mult.ps` | 1639 | 2 | `{'Known': 1639}` | `{'20260624': 1638, '20260610': 1}` | `2026-06-24 22:40:10` |
| `L7.trade.volume_turnover` | 1641 | 0 | `{'Known': 1641}` | `{'20260624': 1640, '20260610': 1}` | `2026-06-24 22:40:10` |
| `L7.flow.active_inflow` | 1631 | 10 | `{'Known': 1631}` | `{'20260624': 1630, '20260610': 1}` | `2026-06-24 22:40:10` |
| `L6.priced.run_up` | 1641 | 0 | `{'Known': 1641}` | `{}` | `2026-06-24 21:46:35` |
| `L6.priced.crowdedness` | 1641 | 0 | `{'Known': 1641}` | `{'20260611': 1}` | `2026-06-24 21:46:35` |
| `L10.val.historical_quantile` | 1641 | 0 | `{'Known': 1641}` | `{}` | `2026-06-24 21:46:35` |
| `L11.short.score` | 1641 | 0 | `{'Known': 1641}` | `{}` | `2026-06-24 23:53:37` |
| `L11.mid.score` | 1641 | 0 | `{'Known': 1641}` | `{}` | `2026-06-24 23:53:37` |
| `L11.long.score` | 1641 | 0 | `{'Known': 1641}` | `{}` | `2026-06-24 23:53:37` |
| `L11.mode` | 1641 | 0 | `{'Known': 1641}` | `{}` | `2026-06-24 23:53:37` |
| `L11.trade.signal` | 1641 | 0 | `{'Known': 1641}` | `{}` | `2026-06-24 23:53:37` |

## Artifacts

| artifact | asof | rows | validated | probability_source | mtime |
|---|---|---:|---:|---|---|
| `quant_score` | `20260624` | 1612 | 1115 | `None` | `2026-06-25 00:03:15.798018` |
| `signal_5d` | `20260624` | 1613 | 1125 | `score_pct_linear_bin10` | `2026-06-25 00:03:30.876673` |
| `signal_up_5d` | `20260624` | 1613 | 0 | `train_base_rate_unvalidated` | `2026-06-25 00:03:31.015494` |

## Known limitations
- signal_up_5d remains unvalidated because the absolute-up model gate fails; this is model validation, not data freshness.
- 688146.SH has no 20260624 daily/daily_basic/moneyflow snapshot from Tushare in this run.
- Several BJ symbols have no 20260624 moneyflow snapshot from Tushare.
