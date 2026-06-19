# A-share approval review packets

- Generated: `2026-06-19T19:47:44+08:00`
- Approval-review packets: `25`
- Known packets: `25`
- NotApplicable packets: `0`
- Final-score-target ready: `25`
- Missing approvals: `25`
- Approval templates: `25`
- Approval template contracts valid: `25`
- Approval template contracts invalid: `0`
- Skipped not bridge/contract ready: `0`
- Approval payload hash mismatches: `0`
- Approved runtime writes: `0`
- Write-plan entries: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Packets

| dp_id | target | status | source | confidence | payload hash | bridge-ready |
|---|---|---|---|---:|---|---:|
| `L0.compete.price_war` | `fundamental_score` | `Known` | `event_text_policy_pilot` | 0.46 | `e2a7f7cc6b48` | yes |
| `L0.compete.share_concentration` | `fundamental_score` | `Known` | `event_text_policy_pilot` | 0.44 | `a429d036b612` | yes |
| `L0.cost.cac` | `fundamental_score` | `Known` | `local_structured_policy_pilot` | 0.36 | `6a3ade7a34d7` | yes |
| `L0.cost.labor` | `fundamental_score` | `Known` | `local_structured_policy_pilot` | 0.38 | `297cc9bf7589` | yes |
| `L0.demand.terminal` | `fundamental_score` | `Known` | `local_structured_policy_pilot` | 0.34 | `6197126ae1ca` | yes |
| `L0.demand.user_count` | `fundamental_score` | `Known` | `local_structured_text_policy_pilot` | 0.37 | `5eba65953cb1` | yes |
| `L0.policy.access_license` | `fundamental_score` | `Known` | `event_text_policy_pilot` | 0.43 | `57830cf99f6b` | yes |
| `L0.policy.regulation` | `fundamental_score` | `Known` | `event_text_policy_pilot` | 0.41 | `ca7488d55518` | yes |
| `L0.policy.subsidy` | `fundamental_score` | `Known` | `event_text_policy_pilot` | 0.4 | `51d5a418dbe0` | yes |
| `L0.policy.tax_trade` | `fundamental_score` | `Known` | `event_text_policy_pilot` | 0.42 | `b2aa6c4db0af` | yes |
| `L0.price.contract_spot` | `fundamental_score` | `Known` | `local_structured_policy_pilot` | 0.32 | `7ded9d212d6d` | yes |
| `L0.price.discount` | `fundamental_score` | `Known` | `local_structured_text_policy_pilot` | 0.38 | `8989414184c8` | yes |
| `L0.price.pricing_power` | `fundamental_score` | `Known` | `local_single_dependency_policy_pilot` | 0.42 | `558ce523a35a` | yes |
| `L0.supply.capacity` | `fundamental_score` | `Known` | `local_structured_policy_pilot` | 0.34 | `c4e4ee476a98` | yes |
| `L0.supply.chain_eff` | `fundamental_score` | `Known` | `local_structured_policy_pilot` | 0.38 | `3389de7fbe9f` | yes |
| `L0.supply.channel_service` | `fundamental_score` | `Known` | `local_structured_text_policy_pilot` | 0.36 | `399da47ac60b` | yes |
| `L0.supply.inventory` | `fundamental_score` | `Known` | `local_single_dependency_policy_pilot` | 0.42 | `2a2d3f496335` | yes |
| `L0.tech.ai_automation` | `fundamental_score` | `Known` | `event_text_policy_pilot` | 0.45 | `e2af21734ddc` | yes |
| `L0.tech.breakthrough` | `fundamental_score` | `Known` | `event_text_policy_pilot` | 0.44 | `37afb1b434f4` | yes |
| `L6.priced.realization_risk` | `priced_in_discount` | `Known` | `manual_policy_pilot` | 0.45 | `ea4d95ce002a` | yes |
| `L7.reflex.tag` | `reflexivity_multiplier` | `Known` | `manual_policy_pilot` | 0.4 | `f6b0d749ec2e` | yes |
| `L8.shock.black_swan` | `risk_discount` | `Known` | `event_text_policy_pilot` | 0.48 | `93165e7ebe05` | yes |
| `L8.shock.supply_break` | `risk_discount` | `Known` | `event_text_policy_pilot` | 0.47 | `29b80f5eb542` | yes |
| `L8.val.slope_risk_off` | `risk_discount` | `Known` | `manual_policy_pilot` | 0.45 | `aceb6b5215d3` | yes |
| `L6.mult.dcf` | `valuation_rerating` | `Known` | `manual_policy_pilot` | 0.32 | `1af34bc1abcf` | yes |

## Interpretation

- These packets are review-ready, not approved.
- Approval templates are intentionally incomplete and cannot be used as valid approvals without reviewer input.
- The report does not write runtime values or change scores.
