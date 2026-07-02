# A-share event-text sufficiency gate

- Generated: `2026-06-19T08:58:17+08:00`
- Sufficiency packets: `12`
- Target-headline packets: `3`
- Broad-market-only transmission packets: `11`
- Same-headline target + any transmission packets: `0`
- Same-headline target + direct transmission packets: `0`
- Title-signal sufficient for classifier: `0`
- Known candidates allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | target | sufficiency status | target headlines | same headline direct | broad-market only | classifier-ready title signal |
|---|---|---|---:|---:|---:|---:|
| `L0.compete.new_entrant` | `fundamental_score` | `insufficient_no_target_event_evidence` | 0 | 0 | yes | no |
| `L0.compete.price_war` | `fundamental_score` | `insufficient_no_target_event_evidence` | 0 | 0 | yes | no |
| `L0.compete.share_concentration` | `fundamental_score` | `insufficient_no_target_event_evidence` | 0 | 0 | yes | no |
| `L0.policy.access_license` | `fundamental_score` | `insufficient_no_target_event_evidence` | 0 | 0 | yes | no |
| `L0.policy.regulation` | `fundamental_score` | `insufficient_target_hit_with_broad_market_only_transmission` | 1 | 0 | yes | no |
| `L0.policy.subsidy` | `fundamental_score` | `insufficient_no_target_event_evidence` | 0 | 0 | yes | no |
| `L0.policy.tax_trade` | `fundamental_score` | `insufficient_target_hit_missing_a_share_transmission` | 1 | 0 | no | no |
| `L0.tech.ai_automation` | `fundamental_score` | `insufficient_no_target_event_evidence` | 0 | 0 | yes | no |
| `L0.tech.breakthrough` | `fundamental_score` | `insufficient_no_target_event_evidence` | 0 | 0 | yes | no |
| `L0.tech.substitute_tech` | `fundamental_score` | `insufficient_no_target_event_evidence` | 0 | 0 | yes | no |
| `L8.shock.black_swan` | `risk_discount` | `insufficient_target_hit_with_broad_market_only_transmission` | 5 | 0 | yes | no |
| `L8.shock.supply_break` | `risk_discount` | `insufficient_no_target_event_evidence` | 0 | 0 | yes | no |

## Interpretation

- A broad China A50/futures headline is market context, not target-specific transmission.
- Separate target and market headlines inside one packet do not establish a direct A-share event path.
- All rows remain blocked from Known candidate generation and runtime writes until stronger evidence exists.
