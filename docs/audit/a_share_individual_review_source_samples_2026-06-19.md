# A-share individual-review source-sample audit

- Generated: `2026-06-19T23:28:06+08:00`
- Individual review packets checked: `10`
- Structured proxy reviews required: `4`
- Policy reviews required: `6`
- Source payloads match candidates: `10`
- Evidence refs complete: `10`
- Text sample evidence ready: `2`
- Event source-sample packets complete: `2`
- Individual review templates: `10`
- Individual review template contracts valid: `10`
- Individual review templates blank/pending: `10`
- Reviewer packets complete: `10`
- Auto approvals allowed: `0`
- Runtime writes allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; source-sample audit is read-only and does not alter realtime_current`

## Candidate Evidence Matrix

| dp_id | risk | source | target | source match | evidence refs | review template | reviewer packet |
|---|---|---|---|---:|---:|---:|---:|
| `L6.mult.dcf` | `individual_policy_review_required` | `manual_policy_pilot` | `valuation_rerating` | yes | yes | yes | yes |
| `L6.priced.realization_risk` | `individual_policy_review_required` | `manual_policy_pilot` | `priced_in_discount` | yes | yes | yes | yes |
| `L7.reflex.tag` | `individual_policy_review_required` | `manual_policy_pilot` | `reflexivity_multiplier` | yes | yes | yes | yes |
| `L8.shock.black_swan` | `individual_policy_review_required` | `event_text_policy_pilot` | `risk_discount` | yes | yes | yes | yes |
| `L8.shock.supply_break` | `individual_policy_review_required` | `event_text_policy_pilot` | `risk_discount` | yes | yes | yes | yes |
| `L8.val.slope_risk_off` | `individual_policy_review_required` | `manual_policy_pilot` | `risk_discount` | yes | yes | yes | yes |
| `L0.demand.terminal` | `individual_structured_review_required` | `local_structured_policy_pilot` | `fundamental_score` | yes | yes | yes | yes |
| `L0.demand.user_count` | `individual_structured_review_required` | `local_structured_text_policy_pilot` | `fundamental_score` | yes | yes | yes | yes |
| `L0.price.contract_spot` | `individual_structured_review_required` | `local_structured_policy_pilot` | `fundamental_score` | yes | yes | yes | yes |
| `L0.price.discount` | `individual_structured_review_required` | `local_structured_text_policy_pilot` | `fundamental_score` | yes | yes | yes | yes |

## Interpretation

- Complete individual reviewer packets still are not approvals.
- Structured proxy, manual policy, non-fundamental score-target, and event risk-discount semantics remain reviewer decisions.
- Runtime writes remain blocked until approval records and individual review decisions are filled with matching payload hashes.
