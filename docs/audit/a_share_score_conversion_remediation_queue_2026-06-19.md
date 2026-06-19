# A-share score-conversion remediation queue

- Generated: `2026-06-19T19:46:32+08:00`
- Score mutation: `none; this audit is read-only`
- DOCKCASE scan: `not_performed`
- Unresolved score-relevant fields: `17`
- Existing current inputs: `14`
- No current input: `3`
- Score route ready: `17`
- Direct Tushare/derived input available: `14`
- Safe formula-now fields: `0`
- Production writes allowed: `0`

## Remediation Classes

| class | count |
|---|---:|
| `formula_policy_required` | 6 |
| `intentional_governance_or_duplicate` | 8 |
| `missing_or_not_applicable_source` | 3 |

## Next Actions

| action | count |
|---|---:|
| `define_reviewed_policy_or_peer_context_before_formula` | 6 |
| `obtain_real_source_universe_or_keep_na` | 3 |
| `verify_replacement_or_keep_suppressed` | 8 |

## Queue

| class | dp_id | target | status | valid ts_codes | source state | replacement/canonical | next action | repair hint |
|---|---|---|---|---:|---|---|---|---|
| `formula_policy_required` | `L5.cf.capex` | `fundamental_score` | `not_numeric_no_formula_or_normalizer` | 1640 | `valid_real` |  | `define_reviewed_policy_or_peer_context_before_formula` | capex needs a defined intensity/trend policy; high capex can be investment or drag |
| `formula_policy_required` | `L2.segment.revenue_share` | `fundamental_score` | `not_numeric_no_formula_or_normalizer` | 1637 | `valid_real` |  | `define_reviewed_policy_or_peer_context_before_formula` | segment revenue share needs a concentration/strategy policy before it has a score direction |
| `formula_policy_required` | `L7.flow.block_trade` | `funding_score` | `not_numeric_no_formula_or_normalizer` | 115 | `valid_real` |  | `define_reviewed_policy_or_peer_context_before_formula` | block-trade amount/count needs buyer/seller direction or discount/premium before funding_score has a sign |
| `formula_policy_required` | `L6.mult.pb` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | 1641 | `valid_real` | `L6.state.peer_compare` | `define_reviewed_policy_or_peer_context_before_formula` | PB needs peer/historical valuation context; direct absolute PB scoring would mix balance-sheet intensity across industries |
| `formula_policy_required` | `L6.state.industry_center` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | 1641 | `valid_real` | `L6.state.peer_compare` | `define_reviewed_policy_or_peer_context_before_formula` | industry-center payload is a reference baseline; score the stock-vs-peer spread through peer_compare/percentile, not as a standalone direction |
| `formula_policy_required` | `L6.mult.pe` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | 1405 | `valid_real` | `L6.state.peer_compare` | `define_reviewed_policy_or_peer_context_before_formula` | trailing PE should be scored through peer/historical valuation context; a direct scalar formula would double-count or ignore industry regime |
| `intentional_governance_or_duplicate` | `L9.media.social_buzz` | `expectation_gap` | `not_numeric_no_formula_or_normalizer` | 79 | `valid_real` | `L7.mood.media_social` | `verify_replacement_or_keep_suppressed` | same Tushare ths_hot 热股 evidence as L7.mood.media_social in the current adapter; do not score as a separate expectation_gap field without a distinct source |
| `intentional_governance_or_duplicate` | `L7.trade.margin_short` | `funding_score` | `not_numeric_no_formula_or_normalizer` | 1514 | `valid_real` |  | `verify_replacement_or_keep_suppressed` | snapshot margin/short payload lacks clean directional signal |
| `intentional_governance_or_duplicate` | `L9.company.mgmt_litigation` | `risk_discount` | `not_numeric_no_formula_or_normalizer` | 389 | `valid_real` | `L8.gov.management_change` | `verify_replacement_or_keep_suppressed` | legacy duplicate of L8.gov.management_change in the current Tushare adapter; do not double-count the same stk_managers events into risk_discount |
| `intentional_governance_or_duplicate` | `L7.mood.media_social` | `sentiment_score` | `not_numeric_no_formula_or_normalizer` | 79 | `valid_real` | `L7.mood.fomo` | `verify_replacement_or_keep_suppressed` | already consumed by L7.mood.fomo -> overheat_risk/risk_discount; a direct sentiment_score formula would reuse the same hot-list evidence |
| `intentional_governance_or_duplicate` | `L6.mult.mcap_fcf` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | 1548 | `valid_real` |  | `verify_replacement_or_keep_suppressed` | negative FCF makes mcap/FCF sign-aware; no safe scalar formula yet |
| `intentional_governance_or_duplicate` | `L6.mult.ev_ebitda` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | 1197 | `valid_real` | `L6.state.peer_compare` | `verify_replacement_or_keep_suppressed` | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| `intentional_governance_or_duplicate` | `L6.mult.peg` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | 909 | `valid_real` | `L6.state.peg_match` | `verify_replacement_or_keep_suppressed` | scored through L6.state.peg_match; direct raw PEG would double-count |
| `intentional_governance_or_duplicate` | `L6.state.expansion_compression` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | 31 | `valid_real` | `L6.state.peer_compare` | `verify_replacement_or_keep_suppressed` | Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead. |
| `missing_or_not_applicable_source` | `L7.trade.options_cp` | `options_momentum_multiplier` | `no_current_numeric_input` | 0 | `not_applicable_or_unlicensed` |  | `obtain_real_source_universe_or_keep_na` | A-share per-stock call/put ratios require real option-chain volume/OI; do not infer them from stock turnover or sentiment |
| `missing_or_not_applicable_source` | `L6.priced.iv` | `volatility_risk` | `no_current_numeric_input` | 0 | `not_applicable_or_unlicensed` |  | `obtain_real_source_universe_or_keep_na` | A-share single-stock option coverage is not broad enough to fabricate; only populate for a legitimate listed-option universe or mark N/A/Unavailable |
| `missing_or_not_applicable_source` | `L7.trade.iv` | `volatility_risk` | `no_current_numeric_input` | 0 | `not_applicable_or_unlicensed` |  | `obtain_real_source_universe_or_keep_na` | A-share per-stock IV needs a licensed listed-option mapping; otherwise keep it out of scoring instead of proxying from unrelated instruments |

## Interpretation

- `safe_formula_now_count = 0` means none of the unresolved score-relevant rows should be auto-wired into scoring without policy, source-universe, or duplicate-evidence review.
- `formula_policy_required` rows have current inputs, but need a reviewed scoring direction, peer context, or baseline before a formula is defensible.
- `intentional_governance_or_duplicate` rows should be verified through their replacement/canonical dp_id or kept suppressed to avoid double-counting.
- `missing_or_not_applicable_source` rows require a real listed-option source universe or explicit N/A handling for A-share coverage.
