# A-share event-text market-doc review packets

- Generated: `2026-06-19T11:01:45+08:00`
- Event-text packets: `12`
- Market-doc review-ready: `11`
- Requires target-event evidence: `0`
- Requires direct-transmission link: `1`
- Candidate examples: `53`
- Packet contracts valid: `12`
- Packet contracts invalid: `0`
- Auto Known candidates allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | target | status | examples | contract | production write |
|---|---|---|---:|---:|---:|
| `L0.compete.new_entrant` | `fundamental_score` | `requires_direct_transmission_link` | 0 | yes | no |
| `L0.compete.price_war` | `fundamental_score` | `market_doc_review_ready` | 3 | yes | no |
| `L0.compete.share_concentration` | `fundamental_score` | `market_doc_review_ready` | 5 | yes | no |
| `L0.policy.access_license` | `fundamental_score` | `market_doc_review_ready` | 5 | yes | no |
| `L0.policy.regulation` | `fundamental_score` | `market_doc_review_ready` | 5 | yes | no |
| `L0.policy.subsidy` | `fundamental_score` | `market_doc_review_ready` | 5 | yes | no |
| `L0.policy.tax_trade` | `fundamental_score` | `market_doc_review_ready` | 5 | yes | no |
| `L0.tech.ai_automation` | `fundamental_score` | `market_doc_review_ready` | 5 | yes | no |
| `L0.tech.breakthrough` | `fundamental_score` | `market_doc_review_ready` | 5 | yes | no |
| `L0.tech.substitute_tech` | `fundamental_score` | `market_doc_review_ready` | 5 | yes | no |
| `L8.shock.black_swan` | `risk_discount` | `market_doc_review_ready` | 5 | yes | no |
| `L8.shock.supply_break` | `risk_discount` | `market_doc_review_ready` | 5 | yes | no |

## Interpretation

- Review-ready packets are classifier/reviewer inputs only.
- They do not contain Known score values and cannot be written to runtime.
- A separate reviewed classification plus approval gate is still required.
