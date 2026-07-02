# A-share option-universe / N/A verification

- Generated: `2026-06-19T16:52:35+08:00`
- Option-universe packets: `3`
- No current A-share input: `3`
- Listed-option universe required: `3`
- N/A or Unavailable allowed after review: `3`
- Known value allowed now: `0`
- Verification contracts valid: `3`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Code Evidence

| evidence | value |
|---|---|
| `collector_path` | `scripts/collector.py` |
| `collector_options_excluded` | `True` |
| `futu_source_path` | `mvp20/sources/futu_source.py` |
| `futu_option_fields_present` | `True` |
| `futu_hk_us_filter_count` | `3` |
| `futu_hk_us_filter_present` | `True` |

## Packets

| dp_id | target | closure | valid ts_codes | required source | known allowed now |
|---|---|---|---:|---|---|
| `L6.priced.iv` | `volatility_risk` | `no_valid_a_share_target_data` | 0 | real implied volatility from a listed option chain or licensed IV surface mapped to the specific underlying | False |
| `L7.trade.iv` | `volatility_risk` | `no_valid_a_share_target_data` | 0 | real implied volatility from a listed option chain or licensed IV surface mapped to the specific underlying | False |
| `L7.trade.options_cp` | `options_momentum_multiplier` | `no_valid_a_share_target_data` | 0 | real option-chain call/put volume or open-interest data for a legitimate listed-option universe | False |

## Interpretation

- These fields must not be filled from stock turnover, sentiment, realized volatility, or broad index option data without explicit mapping.
- A future implementation can emit Known rows only for a legitimate listed-option universe or licensed underlying mapping.
- For ordinary A-share rows outside that universe, the safe resolution is reviewed NotApplicable/Unavailable rather than a fabricated numeric score.
