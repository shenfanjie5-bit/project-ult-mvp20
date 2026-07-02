# A-share completion next actions

- Generated: `2026-06-19T19:47:44+08:00`
- Actionable gaps: `32`
- Approval-ready packets: `25`
- Runtime write-plan ready: `0`
- Approval templates: `25`
- Approval payload hash mismatches: `0`
- Unknown resolution required: `7`
- Approved runtime writes: `0`
- Write-plan entries: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Next Action Buckets

| Bucket | Count |
|---|---:|
| `event_text_classification_required` | 2 |
| `human_approval_required` | 25 |
| `local_structured_mapping_required` | 4 |
| `single_dependency_policy_required` | 1 |

## Rows

| dp_id | target | data status | source | next action bucket | blocker |
|---|---|---|---|---|---|
| `L0.compete.price_war` | `fundamental_score` | `Known` | `event_text_policy_pilot` | `human_approval_required` | - |
| `L0.compete.share_concentration` | `fundamental_score` | `Known` | `event_text_policy_pilot` | `human_approval_required` | - |
| `L0.cost.cac` | `fundamental_score` | `Known` | `local_structured_policy_pilot` | `human_approval_required` | - |
| `L0.cost.labor` | `fundamental_score` | `Known` | `local_structured_policy_pilot` | `human_approval_required` | - |
| `L0.demand.terminal` | `fundamental_score` | `Known` | `local_structured_policy_pilot` | `human_approval_required` | - |
| `L0.demand.user_count` | `fundamental_score` | `Known` | `local_structured_text_policy_pilot` | `human_approval_required` | - |
| `L0.policy.access_license` | `fundamental_score` | `Known` | `event_text_policy_pilot` | `human_approval_required` | - |
| `L0.policy.regulation` | `fundamental_score` | `Known` | `event_text_policy_pilot` | `human_approval_required` | - |
| `L0.policy.subsidy` | `fundamental_score` | `Known` | `event_text_policy_pilot` | `human_approval_required` | - |
| `L0.policy.tax_trade` | `fundamental_score` | `Known` | `event_text_policy_pilot` | `human_approval_required` | - |
| `L0.price.contract_spot` | `fundamental_score` | `Known` | `local_structured_policy_pilot` | `human_approval_required` | - |
| `L0.price.discount` | `fundamental_score` | `Known` | `local_structured_text_policy_pilot` | `human_approval_required` | - |
| `L0.price.pricing_power` | `fundamental_score` | `Known` | `local_single_dependency_policy_pilot` | `human_approval_required` | - |
| `L0.supply.capacity` | `fundamental_score` | `Known` | `local_structured_policy_pilot` | `human_approval_required` | - |
| `L0.supply.chain_eff` | `fundamental_score` | `Known` | `local_structured_policy_pilot` | `human_approval_required` | - |
| `L0.supply.channel_service` | `fundamental_score` | `Known` | `local_structured_text_policy_pilot` | `human_approval_required` | - |
| `L0.supply.inventory` | `fundamental_score` | `Known` | `local_single_dependency_policy_pilot` | `human_approval_required` | - |
| `L0.tech.ai_automation` | `fundamental_score` | `Known` | `event_text_policy_pilot` | `human_approval_required` | - |
| `L0.tech.breakthrough` | `fundamental_score` | `Known` | `event_text_policy_pilot` | `human_approval_required` | - |
| `L6.mult.dcf` | `valuation_rerating` | `Known` | `manual_policy_pilot` | `human_approval_required` | - |
| `L6.priced.realization_risk` | `priced_in_discount` | `Known` | `manual_policy_pilot` | `human_approval_required` | - |
| `L7.reflex.tag` | `reflexivity_multiplier` | `Known` | `manual_policy_pilot` | `human_approval_required` | - |
| `L8.shock.black_swan` | `risk_discount` | `Known` | `event_text_policy_pilot` | `human_approval_required` | - |
| `L8.shock.supply_break` | `risk_discount` | `Known` | `event_text_policy_pilot` | `human_approval_required` | - |
| `L8.val.slope_risk_off` | `risk_discount` | `Known` | `manual_policy_pilot` | `human_approval_required` | - |
| `L0.compete.new_entrant` | `fundamental_score` | `Unknown` | `event_text_policy_pilot` | `event_text_classification_required` | market_doc_direct_transmission_link_required |
| `L0.tech.substitute_tech` | `fundamental_score` | `Unknown` | `event_text_policy_pilot` | `event_text_classification_required` | market_doc_clean_substitution_risk_evidence_required |
| `L0.cost.rent` | `fundamental_score` | `Unknown` | `local_structured_policy_pilot` | `local_structured_mapping_required` | ppe_capex_cannot_identify_rent_or_lease_burden |
| `L0.demand.frequency` | `fundamental_score` | `Unknown` | `local_structured_policy_pilot` | `local_structured_mapping_required` | revenue_growth_cannot_separate_purchase_frequency |
| `L0.demand.penetration` | `fundamental_score` | `Unknown` | `local_structured_policy_pilot` | `local_structured_mapping_required` | revenue_growth_cannot_identify_penetration_without_tam |
| `L0.price.product_asp` | `fundamental_score` | `Unknown` | `local_structured_policy_pilot` | `local_structured_mapping_required` | revenue_and_margin_cannot_identify_unit_asp_without_volume_mix |
| `L0.demand.replacement` | `fundamental_score` | `Unknown` | `local_single_dependency_policy_pilot` | `single_dependency_policy_required` | revenue_only_cannot_identify_replacement_cycle |

## Interpretation

- Approval templates are incomplete by design and are not valid approval records.
- Unknown rows need evidence/classification/mapping before they can become concrete review packets.
- This report does not write runtime values and does not reduce score blockers by itself.
