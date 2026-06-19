# A-share Unknown external business metric value candidates

- Generated: `2026-06-19T15:35:49+08:00`
- Policy draft packets: `18`
- Rows adjudicated: `18`
- Rows with value-candidate tokens: `9`
- Value-candidate tokens: `13`
- Rejected numeric tokens: `31`
- Shortlist review required: `6`
- Metric inputs ready: `0`
- Known-draft sufficient: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Status Counts

| status | count |
|---|---:|
| `no_scoreable_numeric_candidate` | 9 |
| `scope_rejected` | 3 |
| `value_candidate_shortlist_review_required` | 6 |

## Rows

| dp_id | status | value tokens | scope |
|---|---|---:|---|
| `L0.demand.frequency` | `no_scoreable_numeric_candidate` | 0 | `reject_foreign_or_non_a_share_scope` |
| `L0.demand.penetration` | `scope_rejected` | 2 | `reject_foreign_or_non_a_share_scope` |
| `L0.demand.penetration` | `scope_rejected` | 2 | `reject_foreign_or_non_a_share_scope` |
| `L0.demand.penetration` | `no_scoreable_numeric_candidate` | 0 | `reject_foreign_or_non_a_share_scope` |
| `L0.demand.penetration` | `scope_rejected` | 1 | `reject_non_a_share_company_scope` |
| `L0.demand.penetration` | `value_candidate_shortlist_review_required` | 1 | `review_a_share_or_domestic_scope` |
| `L0.demand.penetration` | `no_scoreable_numeric_candidate` | 0 | `review_a_share_or_domestic_scope` |
| `L0.demand.penetration` | `no_scoreable_numeric_candidate` | 0 | `review_a_share_or_domestic_scope` |
| `L0.demand.penetration` | `value_candidate_shortlist_review_required` | 2 | `review_a_share_or_domestic_scope` |
| `L0.demand.penetration` | `value_candidate_shortlist_review_required` | 1 | `review_a_share_or_domestic_scope` |
| `L0.demand.penetration` | `value_candidate_shortlist_review_required` | 1 | `review_domestic_or_industry_scope` |
| `L0.demand.penetration` | `no_scoreable_numeric_candidate` | 0 | `review_domestic_or_industry_scope` |
| `L0.demand.penetration` | `no_scoreable_numeric_candidate` | 0 | `review_domestic_or_industry_scope` |
| `L0.demand.penetration` | `no_scoreable_numeric_candidate` | 0 | `review_domestic_or_industry_scope` |
| `L0.demand.penetration` | `no_scoreable_numeric_candidate` | 0 | `review_domestic_or_industry_scope` |
| `L0.demand.penetration` | `value_candidate_shortlist_review_required` | 1 | `review_forecast_or_assumption_scope` |
| `L0.demand.penetration` | `no_scoreable_numeric_candidate` | 0 | `review_forecast_or_assumption_scope` |
| `L0.demand.penetration` | `value_candidate_shortlist_review_required` | 2 | `review_forecast_or_assumption_scope` |

## Interpretation

- Shortlisted rows still require source-scope, value, bounds, formula-policy, and approval review.
- Rejected or ambiguous rows remain Unknown and should not be treated as valid score information.
- This audit does not create Known values and does not write runtime scores.
