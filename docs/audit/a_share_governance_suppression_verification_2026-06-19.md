# A-share governance suppression verification

- Generated: `2026-06-19T16:45:09+08:00`
- Governance/suppression packets: `8`
- Suppression verified: `8`
- Replacement/canonical ready: `6`
- Direct signal suppressed: `8`
- Peer-context suppressed: `2`
- Requires governance review: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Verification Status

| status | count |
|---|---:|
| `data_only_suppression_verified` | 3 |
| `derived_replacement_ready` | 1 |
| `duplicate_with_canonical_ready` | 1 |
| `duplicate_with_transitive_replacement_ready` | 1 |
| `suppressed_with_replacement_ready` | 2 |

## Rows

| subtype | dp_id | target | valid ts_codes | replacement/canonical | status |
|---|---|---|---:|---|---|
| `data_only_no_safe_signal` | `L6.mult.mcap_fcf` | `valuation_rerating` | 1548 |  | `data_only_suppression_verified` |
| `data_only_no_safe_signal` | `L6.mult.peg` | `valuation_rerating` | 909 | `L6.state.peg_match` | `data_only_suppression_verified` |
| `data_only_no_safe_signal` | `L7.trade.margin_short` | `funding_score` | 1514 |  | `data_only_suppression_verified` |
| `derived_replacement` | `L7.mood.media_social` | `sentiment_score` | 79 | `L7.mood.fomo` | `derived_replacement_ready` |
| `duplicate_evidence` | `L9.company.mgmt_litigation` | `risk_discount` | 389 | `L8.gov.management_change` | `duplicate_with_canonical_ready` |
| `duplicate_evidence` | `L9.media.social_buzz` | `expectation_gap` | 79 | `L7.mood.media_social -> L7.mood.fomo` | `duplicate_with_transitive_replacement_ready` |
| `peer_context_suppressed` | `L6.mult.ev_ebitda` | `valuation_rerating` | 1197 | `L6.state.peer_compare` | `suppressed_with_replacement_ready` |
| `peer_context_suppressed` | `L6.state.expansion_compression` | `valuation_rerating` | 31 | `L6.state.peer_compare` | `suppressed_with_replacement_ready` |

## Interpretation

- These rows are intentionally not auto-scored by their raw payloads.
- Replacement/canonical-ready rows should be reviewed through their scoring path rather than duplicated.
- Data-only rows remain available as evidence but need sign semantics or a safer replacement before scoring.
