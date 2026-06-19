# A-share bulk-review approval candidates

- Generated: `2026-06-19T20:07:11+08:00`
- Candidates: `7`
- Strict bulk candidates: `6`
- Borderline sample-check candidates: `1`
- Approval drafts: `7`
- Approval draft contracts valid: `7`
- Approval draft contracts invalid: `0`
- Auto approvals allowed: `0`
- Runtime writes allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; draft approvals only and no realtime_current mutation`

## Candidates

| dp_id | source | confidence | impact | risk class | draft valid |
|---|---|---:|---:|---|---:|
| `L0.cost.cac` | `local_structured_policy_pilot` | 0.36 | 0.022717 | `bulk_structured_review_candidate` | yes |
| `L0.cost.labor` | `local_structured_policy_pilot` | 0.38 | 0.080821 | `bulk_structured_review_candidate` | yes |
| `L0.price.pricing_power` | `local_single_dependency_policy_pilot` | 0.42 | 0.076791 | `bulk_structured_review_candidate` | yes |
| `L0.supply.capacity` | `local_structured_policy_pilot` | 0.34 | 0.063117 | `bulk_structured_review_candidate` | yes |
| `L0.supply.chain_eff` | `local_structured_policy_pilot` | 0.38 | 0.011778 | `bulk_structured_review_candidate` | yes |
| `L0.supply.inventory` | `local_single_dependency_policy_pilot` | 0.42 | 0.144172 | `bulk_structured_review_candidate` | yes |
| `L0.supply.channel_service` | `local_structured_text_policy_pilot` | 0.36 | 0.124543 | `borderline_structured_text_review_candidate` | yes |

## Interpretation

- Draft records are intentionally incomplete and cannot pass the approval gate.
- Strict bulk candidates may be reviewed together, but the reviewer must still fill approval identity, timestamp, status, and risk acknowledgement.
- Borderline sample-check candidates need source-text sampling before approval.
- The report does not write runtime values or change scores.
