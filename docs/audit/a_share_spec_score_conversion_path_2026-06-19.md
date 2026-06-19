# A-share spec score conversion-path audit

- Generated: `2026-06-19T21:46:30+08:00`
- Score mutation: `none; this audit is read-only`
- DOCKCASE scan: `not_performed`
- Total checked: `256`
- Score-relevant final targets: `174`
- Current numeric final-score fields: `121`
- Candidate numeric score-path ready fields: `32`
- Numeric and score-path ready fields: `157`
- Unresolved score-relevant fields: `17`
- Formula-policy review required fields: `6`
- Governance suppression verified fields: `8`
- Option-universe / N/A verified fields: `3`
- Review-decision backed not-ready fields: `17`
- Remaining unclassified conversion gaps: `0`
- Not numeric / no formula or normalizer: `14`
- No current numeric input: `3`
- No weight or non-scoring: `82`
- Not entering final score: `99`

## Conversion Status

| Status | Count |
|---|---:|
| `candidate_numeric_score_path_ready` | 32 |
| `current_numeric_final_score` | 121 |
| `no_current_numeric_input` | 3 |
| `no_weight_or_non_scoring` | 82 |
| `not_numeric_no_formula_or_normalizer` | 14 |
| `sample_numeric_score_path_ready` | 4 |

## Blocked Score-Relevant Rows

| dp_id | target | status | closure | review evidence | runtime valid | runtime numeric |
|---|---|---|---|---|---:|---:|
| `L2.segment.revenue_share` | `fundamental_score` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `segment_concentration_and_strategy` | 1637 | 0 |
| `L5.cf.capex` | `fundamental_score` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `capex_intensity_and_trend` | 1640 | 0 |
| `L6.mult.ev_ebitda` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `suppressed_with_replacement_ready` | 1197 | 0 |
| `L6.mult.mcap_fcf` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `data_only_suppression_verified` | 1548 | 0 |
| `L6.mult.pb` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `valuation_peer_context` | 1641 | 0 |
| `L6.mult.pe` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `valuation_peer_context` | 1405 | 0 |
| `L6.mult.peg` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `data_only_suppression_verified` | 909 | 0 |
| `L6.priced.iv` | `volatility_risk` | `no_current_numeric_input` | `no_valid_a_share_target_data` | `listed_option_universe_or_na` | 0 | 0 |
| `L6.state.expansion_compression` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `suppressed_with_replacement_ready` | 31 | 0 |
| `L6.state.industry_center` | `valuation_rerating` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `valuation_peer_context` | 1641 | 0 |
| `L7.flow.block_trade` | `funding_score` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `block_trade_directional_flow` | 115 | 0 |
| `L7.mood.media_social` | `sentiment_score` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `derived_replacement_ready` | 79 | 0 |
| `L7.trade.iv` | `volatility_risk` | `no_current_numeric_input` | `no_valid_a_share_target_data` | `listed_option_universe_or_na` | 0 | 0 |
| `L7.trade.margin_short` | `funding_score` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `data_only_suppression_verified` | 1514 | 0 |
| `L7.trade.options_cp` | `options_momentum_multiplier` | `no_current_numeric_input` | `no_valid_a_share_target_data` | `listed_option_universe_or_na` | 0 | 0 |
| `L9.company.mgmt_litigation` | `risk_discount` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `duplicate_with_canonical_ready` | 389 | 0 |
| `L9.media.social_buzz` | `expectation_gap` | `not_numeric_no_formula_or_normalizer` | `valid_real_but_formula_unmapped` | `duplicate_with_transitive_replacement_ready` | 79 | 0 |

## Interpretation

- `current_numeric_final_score` means the field already has current A-share evidence reaching the final-score path.
- `candidate_numeric_score_path_ready` means a dry-run candidate payload can be normalized, emitted as a realtime node, and routed by `score_company`; it is not a production write.
- `formula_policy_review_required` means real current inputs exist and the score route is available, but a direct formula needs explicit reviewed policy before runtime writing.
- `governance_suppression_verified` means the non-numeric field is intentionally suppressed, duplicated, data-only, or replaced by another scored path.
- `option_universe_na_verified` means A-share option/IV fields have no current legitimate listed-option source and may only remain Unknown/Unavailable or become reviewed N/A.
- `not_numeric_no_formula_or_normalizer` means current real runtime values exist, but `_realtime_signal` has no formula/normalizer for that payload shape.
- `no_weight_or_non_scoring` means governance does not route the field into a final score target.
