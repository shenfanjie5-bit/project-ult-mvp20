# A-share bulk-review source-sample audit

- Generated: `2026-06-19T21:32:28+08:00`
- Candidates checked: `7`
- Strict bulk candidates: `6`
- Borderline sample-check candidates: `1`
- Source reports found: `7`
- Source rows found: `7`
- Source payloads match candidates: `7`
- Evidence refs complete: `7`
- Blank approval drafts valid: `7`
- Borderline sample evidence ready: `1`
- Reviewer packets complete: `7`
- Auto approvals allowed: `0`
- Runtime writes allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; source-sample audit is read-only and does not alter realtime_current`

## Candidate Evidence Matrix

| dp_id | risk | source row | payload match | deps refs | sample ready | reviewer packet |
|---|---|---:|---:|---:|---:|---:|
| `L0.cost.cac` | `bulk_structured_review_candidate` | yes | yes | 2/2 | yes | yes |
| `L0.cost.labor` | `bulk_structured_review_candidate` | yes | yes | 2/2 | yes | yes |
| `L0.price.pricing_power` | `bulk_structured_review_candidate` | yes | yes | 1/1 | yes | yes |
| `L0.supply.capacity` | `bulk_structured_review_candidate` | yes | yes | 2/2 | yes | yes |
| `L0.supply.chain_eff` | `bulk_structured_review_candidate` | yes | yes | 2/2 | yes | yes |
| `L0.supply.inventory` | `bulk_structured_review_candidate` | yes | yes | 1/1 | yes | yes |
| `L0.supply.channel_service` | `borderline_structured_text_review_candidate` | yes | yes | 2/2 | yes | yes |

## Interpretation

- Complete reviewer packets still are not approvals.
- The audit only verifies traceability from approval candidates back to source reports, runtime dependency references, and sample evidence.
- Runtime writes remain blocked until a reviewer fills approval records with matching payload hashes and risk acknowledgement.
