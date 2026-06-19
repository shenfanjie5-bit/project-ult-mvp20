# A-share candidate value contracts

- Generated: `2026-06-19T19:47:42+08:00`
- Candidate rows checked: `32`
- Contract valid: `32`
- Contract invalid: `0`
- Concrete payloads valid: `0`
- Placeholder payloads valid: `32`
- Concrete payloads bridge-validated: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Validation Mode Counts

| Mode | Count |
|---|---:|
| `placeholder` | 32 |

## Rows

| dp_id | payload status | mode | valid | errors |
|---|---|---|---:|---|
| `L0.compete.new_entrant` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.compete.price_war` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.compete.share_concentration` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.cost.cac` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.cost.labor` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.cost.rent` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.demand.frequency` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.demand.penetration` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.demand.replacement` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.demand.terminal` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.demand.user_count` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.policy.access_license` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.policy.regulation` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.policy.subsidy` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.policy.tax_trade` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.price.contract_spot` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.price.discount` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.price.pricing_power` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.price.product_asp` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.supply.capacity` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.supply.chain_eff` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.supply.channel_service` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.supply.inventory` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.tech.ai_automation` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.tech.breakthrough` | `requires_generator_output` | `placeholder` | yes | - |
| `L0.tech.substitute_tech` | `requires_generator_output` | `placeholder` | yes | - |
| `L8.shock.black_swan` | `requires_generator_output` | `placeholder` | yes | - |
| `L8.shock.supply_break` | `requires_generator_output` | `placeholder` | yes | - |
| `L6.mult.dcf` | `requires_generator_output` | `placeholder` | yes | - |
| `L6.priced.realization_risk` | `requires_generator_output` | `placeholder` | yes | - |
| `L7.reflex.tag` | `requires_generator_output` | `placeholder` | yes | - |
| `L8.val.slope_risk_off` | `requires_generator_output` | `placeholder` | yes | - |

## Interpretation

- Valid placeholders prove the review contract is complete; they do not produce a scoring signal.
- Valid concrete payloads must pass schema, bounds, evidence/rationale checks, and the production scoring bridge.
- Production score-affecting writes remain disabled.
