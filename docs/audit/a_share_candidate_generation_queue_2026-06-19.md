# A-share candidate generation queue

- Generated: `2026-06-19T19:47:42+08:00`
- Generator-required tasks: `32`
- Skipped non-generator rows: `0`
- Placeholder contracts valid: `True`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Generator Kind Counts

| Kind | Count |
|---|---:|
| `event_llm_candidate` | 12 |
| `local_llm_candidate` | 16 |
| `manual_policy_candidate` | 4 |

## Batches

- `event_llm_candidate` (12): `L0.compete.new_entrant`, `L0.compete.price_war`, `L0.compete.share_concentration`, `L0.policy.access_license`, `L0.policy.regulation`, `L0.policy.subsidy`, `L0.policy.tax_trade`, `L0.tech.ai_automation`, `L0.tech.breakthrough`, `L0.tech.substitute_tech`, `L8.shock.black_swan`, `L8.shock.supply_break`
- `local_llm_candidate` (16): `L0.cost.cac`, `L0.cost.labor`, `L0.cost.rent`, `L0.demand.frequency`, `L0.demand.penetration`, `L0.demand.replacement`, `L0.demand.terminal`, `L0.demand.user_count`, `L0.price.contract_spot`, `L0.price.discount`, `L0.price.pricing_power`, `L0.price.product_asp`, `L0.supply.capacity`, `L0.supply.chain_eff`, `L0.supply.channel_service`, `L0.supply.inventory`
- `manual_policy_candidate` (4): `L6.mult.dcf`, `L6.priced.realization_risk`, `L7.reflex.tag`, `L8.val.slope_risk_off`

## Tasks

| dp_id | kind | priority | target | evidence refs |
|---|---|---|---|---:|
| `L0.compete.new_entrant` | `event_llm_candidate` | `P2_event_classification_candidate` | `fundamental_score` | 3 |
| `L0.compete.price_war` | `event_llm_candidate` | `P2_event_classification_candidate` | `fundamental_score` | 3 |
| `L0.compete.share_concentration` | `event_llm_candidate` | `P2_event_classification_candidate` | `fundamental_score` | 3 |
| `L0.cost.cac` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 3 |
| `L0.cost.labor` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 3 |
| `L0.cost.rent` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 3 |
| `L0.demand.frequency` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 3 |
| `L0.demand.penetration` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 3 |
| `L0.demand.replacement` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 2 |
| `L0.demand.terminal` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 3 |
| `L0.demand.user_count` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 3 |
| `L0.policy.access_license` | `event_llm_candidate` | `P2_event_classification_candidate` | `fundamental_score` | 3 |
| `L0.policy.regulation` | `event_llm_candidate` | `P2_event_classification_candidate` | `fundamental_score` | 3 |
| `L0.policy.subsidy` | `event_llm_candidate` | `P2_event_classification_candidate` | `fundamental_score` | 3 |
| `L0.policy.tax_trade` | `event_llm_candidate` | `P2_event_classification_candidate` | `fundamental_score` | 3 |
| `L0.price.contract_spot` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 4 |
| `L0.price.discount` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 3 |
| `L0.price.pricing_power` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 2 |
| `L0.price.product_asp` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 3 |
| `L0.supply.capacity` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 3 |
| `L0.supply.chain_eff` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 3 |
| `L0.supply.channel_service` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 3 |
| `L0.supply.inventory` | `local_llm_candidate` | `P2_local_closed_loop_candidate` | `fundamental_score` | 2 |
| `L0.tech.ai_automation` | `event_llm_candidate` | `P2_event_classification_candidate` | `fundamental_score` | 3 |
| `L0.tech.breakthrough` | `event_llm_candidate` | `P2_event_classification_candidate` | `fundamental_score` | 3 |
| `L0.tech.substitute_tech` | `event_llm_candidate` | `P2_event_classification_candidate` | `fundamental_score` | 3 |
| `L8.shock.black_swan` | `event_llm_candidate` | `P1_risk_discount_candidate` | `risk_discount` | 3 |
| `L8.shock.supply_break` | `event_llm_candidate` | `P1_risk_discount_candidate` | `risk_discount` | 3 |
| `L6.mult.dcf` | `manual_policy_candidate` | `P1_manual_policy_before_known_value` | `valuation_rerating` | 7 |
| `L6.priced.realization_risk` | `manual_policy_candidate` | `P1_manual_policy_before_known_value` | `priced_in_discount` | 5 |
| `L7.reflex.tag` | `manual_policy_candidate` | `P1_manual_policy_before_known_value` | `reflexivity_multiplier` | 5 |
| `L8.val.slope_risk_off` | `manual_policy_candidate` | `P1_manual_policy_before_known_value` | `risk_discount` | 6 |

## Interpretation

- This queue packages generator work only; it does not generate candidate business values.
- Every task must produce a reviewed output that passes the value-contract audit before it can become a Known staging payload.
- Production score-affecting writes remain disabled.
