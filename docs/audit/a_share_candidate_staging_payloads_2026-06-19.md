# A-share candidate staging payloads

- Generated: `2026-06-19T19:47:42+08:00`
- Candidate rows checked: `32`
- Deterministic staging payloads: `0`
- Generator-required rows: `32`
- Blocked: `0`
- Staging payloads bridge-ready: `0`
- Dry-run bridge-ready rows: `32`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Payload Status Counts

| Status | Count |
|---|---:|
| `requires_generator_output` | 32 |

## Rows

| dp_id | route | payload status | next action | staging bridge | production write |
|---|---|---|---|---:|---:|
| `L0.compete.new_entrant` | `event_llm_from_runtime_news` | `requires_generator_output` | `generate_event_llm_candidate` | - | no |
| `L0.compete.price_war` | `event_llm_from_runtime_news` | `requires_generator_output` | `generate_event_llm_candidate` | - | no |
| `L0.compete.share_concentration` | `event_llm_from_runtime_news` | `requires_generator_output` | `generate_event_llm_candidate` | - | no |
| `L0.cost.cac` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.cost.labor` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.cost.rent` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.demand.frequency` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.demand.penetration` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.demand.replacement` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.demand.terminal` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.demand.user_count` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.policy.access_license` | `event_llm_from_runtime_news` | `requires_generator_output` | `generate_event_llm_candidate` | - | no |
| `L0.policy.regulation` | `event_llm_from_runtime_news` | `requires_generator_output` | `generate_event_llm_candidate` | - | no |
| `L0.policy.subsidy` | `event_llm_from_runtime_news` | `requires_generator_output` | `generate_event_llm_candidate` | - | no |
| `L0.policy.tax_trade` | `event_llm_from_runtime_news` | `requires_generator_output` | `generate_event_llm_candidate` | - | no |
| `L0.price.contract_spot` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.price.discount` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.price.pricing_power` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.price.product_asp` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.supply.capacity` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.supply.chain_eff` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.supply.channel_service` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.supply.inventory` | `local_llm_closed_loop` | `requires_generator_output` | `generate_local_llm_candidate` | - | no |
| `L0.tech.ai_automation` | `event_llm_from_runtime_news` | `requires_generator_output` | `generate_event_llm_candidate` | - | no |
| `L0.tech.breakthrough` | `event_llm_from_runtime_news` | `requires_generator_output` | `generate_event_llm_candidate` | - | no |
| `L0.tech.substitute_tech` | `event_llm_from_runtime_news` | `requires_generator_output` | `generate_event_llm_candidate` | - | no |
| `L8.shock.black_swan` | `event_llm_from_runtime_news` | `requires_generator_output` | `generate_event_llm_candidate` | - | no |
| `L8.shock.supply_break` | `event_llm_from_runtime_news` | `requires_generator_output` | `generate_event_llm_candidate` | - | no |
| `L6.mult.dcf` | `manual_design_review` | `requires_generator_output` | `generate_manual_policy_candidate` | - | no |
| `L6.priced.realization_risk` | `manual_design_review` | `requires_generator_output` | `generate_manual_policy_candidate` | - | no |
| `L7.reflex.tag` | `manual_design_review` | `requires_generator_output` | `generate_manual_policy_candidate` | - | no |
| `L8.val.slope_risk_off` | `manual_design_review` | `requires_generator_output` | `generate_manual_policy_candidate` | - | no |

## Interpretation

- This report prepares review packets only; it does not claim candidate values are correct.
- Only deterministic neutral / not-applicable rows receive concrete staging payloads here.
- The remaining rows require governed local/event/manual candidate generation before staging.
- Production score-affecting writes remain disabled for all rows.
