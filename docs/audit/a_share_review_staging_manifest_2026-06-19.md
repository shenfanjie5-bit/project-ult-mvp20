# A-share review staging manifest

- Generated: `2026-06-19T19:47:44+08:00`
- Candidate blocking rows: `32`
- Review manifest entries: `32`
- Review-ready concrete entries: `25`
- Review-gated Unknown entries: `7`
- Contracts valid: `32`
- Contracts invalid: `0`
- Concrete entries bridge-ready: `25`
- Safe to upsert without review: `0`
- Production writes allowed: `0`
- Approved runtime writes: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Source Kind Counts

| Source kind | Count |
|---|---:|
| `event_text_policy_pilot` | 12 |
| `local_single_dependency_policy_pilot` | 3 |
| `local_structured_policy_pilot` | 10 |
| `local_structured_text_policy_pilot` | 3 |
| `manual_policy_pilot` | 4 |

## Rows

| dp_id | target | source | data status | review status | contract | bridge-ready | write allowed |
|---|---|---|---|---|---:|---:|---:|
| `L0.compete.new_entrant` | `fundamental_score` | `event_text_policy_pilot` | `Unknown` | `review_gated_unknown` | yes | - | no |
| `L0.compete.price_war` | `fundamental_score` | `event_text_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.compete.share_concentration` | `fundamental_score` | `event_text_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.cost.cac` | `fundamental_score` | `local_structured_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.cost.labor` | `fundamental_score` | `local_structured_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.cost.rent` | `fundamental_score` | `local_structured_policy_pilot` | `Unknown` | `review_gated_unknown` | yes | - | no |
| `L0.demand.frequency` | `fundamental_score` | `local_structured_policy_pilot` | `Unknown` | `review_gated_unknown` | yes | - | no |
| `L0.demand.penetration` | `fundamental_score` | `local_structured_policy_pilot` | `Unknown` | `review_gated_unknown` | yes | - | no |
| `L0.demand.replacement` | `fundamental_score` | `local_single_dependency_policy_pilot` | `Unknown` | `review_gated_unknown` | yes | - | no |
| `L0.demand.terminal` | `fundamental_score` | `local_structured_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.demand.user_count` | `fundamental_score` | `local_structured_text_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.policy.access_license` | `fundamental_score` | `event_text_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.policy.regulation` | `fundamental_score` | `event_text_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.policy.subsidy` | `fundamental_score` | `event_text_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.policy.tax_trade` | `fundamental_score` | `event_text_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.price.contract_spot` | `fundamental_score` | `local_structured_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.price.discount` | `fundamental_score` | `local_structured_text_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.price.pricing_power` | `fundamental_score` | `local_single_dependency_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.price.product_asp` | `fundamental_score` | `local_structured_policy_pilot` | `Unknown` | `review_gated_unknown` | yes | - | no |
| `L0.supply.capacity` | `fundamental_score` | `local_structured_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.supply.chain_eff` | `fundamental_score` | `local_structured_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.supply.channel_service` | `fundamental_score` | `local_structured_text_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.supply.inventory` | `fundamental_score` | `local_single_dependency_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.tech.ai_automation` | `fundamental_score` | `event_text_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.tech.breakthrough` | `fundamental_score` | `event_text_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L0.tech.substitute_tech` | `fundamental_score` | `event_text_policy_pilot` | `Unknown` | `review_gated_unknown` | yes | - | no |
| `L8.shock.black_swan` | `risk_discount` | `event_text_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L8.shock.supply_break` | `risk_discount` | `event_text_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L6.mult.dcf` | `valuation_rerating` | `manual_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L6.priced.realization_risk` | `priced_in_discount` | `manual_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L7.reflex.tag` | `reflexivity_multiplier` | `manual_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |
| `L8.val.slope_risk_off` | `risk_discount` | `manual_policy_pilot` | `Known` | `review_ready_concrete` | yes | yes | no |

## Interpretation

- The manifest is a review queue, not an approval list.
- Concrete entries are bridge-ready but still require human approval before any runtime write.
- Unknown entries document the exact policy/classification blocker that prevents a Known score value.
